import hashlib
import threading
import socket
import os
import time
import requests
import math
import json
import pprint
import random


TRACKER_URL = 'http://localhost:8000' 
TORRENT_TRACKER = {}
START_PORT = 5000
NUM_PEERS = 3
OUTPUT_PATH = r'C:\Users\Admin\Downloads\btl cn\output'
class File: 
    def __init__(self, path: str, id):
        self.piece_size = 102400
        self.block_size = self.piece_size // 2
        self.path = path
        self.peer_id = id

    def calculate_sha1(self, data):
        sha1_hash = hashlib.sha1()
        if isinstance(data, str):
            data = data.encode()
        sha1_hash.update(data)
        sha1_digest = sha1_hash.hexdigest()
        return sha1_digest

    def divide_file_into_pieces(self):
        name = os.path.basename(self.path)
        pieces = []
        total_data = bytearray()
        file_info = {}
        piece_mappings = []
        current_offset = 0

        if os.path.isdir(self.path):
            total_size = sum(os.path.getsize(os.path.join(root, file))
                            for root, _, files in os.walk(self.path) for file in files)
        elif os.path.isfile(self.path):
            total_size = os.path.getsize(self.path)
        else:
            raise ValueError("Provided path is neither a file nor a directory.")

        if os.path.isdir(self.path):
            for root, dirs, files in os.walk(self.path):
                for file in files:
                    file_path = os.path.join(root, file)
                    relative_path = os.path.relpath(file_path, start=self.path)
                    full_path = os.path.join(name, relative_path)
                    file_size = os.path.getsize(file_path)
                    file_info[full_path] = file_size
                    with open(file_path, 'rb') as f:
                        file_data = f.read()
                        total_data.extend(file_data)
                        start_piece_index = current_offset // self.piece_size
                        end_piece_index = (current_offset + file_size - 1) // self.piece_size
                        piece_mappings.append({
                            'file_path': full_path,
                            'start_piece': start_piece_index,
                            'end_piece': end_piece_index,
                            'start_offset': current_offset ,
                            'end_offset': (current_offset + file_size - 1)
                            
                        })
                        current_offset += file_size
                        self.show_progress(name, current_offset, total_size)
        elif os.path.isfile(self.path):
            with open(self.path, 'rb') as f:
                file_data = f.read()
                total_data.extend(file_data)
                full_path = name
                file_info[full_path] = total_size
                self.show_progress(name, total_size, total_size)
        for i in range(0, len(total_data), self.piece_size):
            piece = total_data[i:i + self.piece_size]
            pieces.append(piece)
        return {
            'name': name,
            'pieces': pieces,
            'info': {
                'file_info': file_info,
                'piece_mappings': piece_mappings
            }
        }


    def divide_piece_into_blocks(self, piece):
        blocks = []
        piece_length = len(piece)
        for start in range(0, piece_length, self.block_size):
            end = min(start + self.block_size, piece_length)
            blocks.append(piece[start:end])
        return blocks
    
    def show_progress(self, filename, processed, total):
        progress = int(50 * processed / total)
        progress_bar = '#' * progress + '-' * (50 - progress)
        print(f"\rPeer {self.peer_id}~{filename} {progress_bar} {int(100 * processed / total)}%", end='')
        if processed >= total:
            print()
        time.sleep(0.5) 
    def create_torrent_file(self, file_data):
        pieces_hash = ''.join([self.calculate_sha1(piece) for piece in file_data['pieces']])
        torrent_data = {
            'announce': TRACKER_URL,
            'info': {
                'piece length': self.piece_size,
                'pieces': pieces_hash
            }
        }
        if 'piece_mappings' in file_data['info'] and len(file_data['info']['piece_mappings']) > 0 :
            torrent_data['info']['files'] = []
            torrent_data['info']['name'] = file_data['name'] 
            for mapping in file_data['info']['piece_mappings']:
                file_length = file_data['info']['file_info'].get(mapping['file_path'])
                if file_length is None:
                    raise ValueError(f"File size missing for {mapping['file_path']}")
                file_entry = {
                    'length': file_length,
                    'path': mapping['file_path'].split(os.sep), 
                    'mapping': {
                        'start_piece': mapping['start_piece'],
                        'end_piece': mapping['end_piece'],
                        'start_offset': mapping['start_offset'],
                        'end_offset': mapping['end_offset']
                    }
                }
                torrent_data['info']['files'].append(file_entry)
        else: 
            single_file_key = next(iter(file_data['info']['file_info']))
            torrent_data['info']['name'] = single_file_key
            torrent_data['info']['length'] = file_data['info']['file_info'][single_file_key]
        return torrent_data



class Peer(threading.Thread):
    def __init__(self, peer_id, port):
        super().__init__()
        self.peer_id = peer_id
        self.port = port
        self.server_socket = None
        self.running = True
        self.files = []
        
        self.handle_file = File('', self.peer_id)
        self.torrents = []
    def run(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind(('localhost', self.port))
        self.server_socket.listen(10)
        print(f"Peer {self.peer_id} listening on port {self.port}")
        try:
            while self.running:
                client_socket, addr = self.server_socket.accept()
                if not self.running: 
                    break
                print(f"Peer {self.peer_id} connected to {addr}")
                threading.Thread(target=self.handle_client, args=(client_socket,)).start()
        finally:
            print(f"Closing server socket for peer {self.peer_id}")
            self.server_socket.close()

    def update_tracker_upload(self, torrent_data):
        piece_length = torrent_data['info']['piece length']
        if 'length' in torrent_data['info']:
            file_length = torrent_data['info']['length']
            file_details = None 
        else:
            file_length = sum(file['length'] for file in torrent_data['info']['files'])
            file_details = [{'name': "/".join(f['path']), 'length': f['length']} for f in torrent_data['info']['files']]
        number_of_pieces = math.ceil(file_length / piece_length)
        payload = {
            "peer_id": self.peer_id,
            "file_name": torrent_data['info']['name'],
            "pieces_indices": list(range(number_of_pieces)),
            "file_details": file_details
        }
        response = requests.post(torrent_data['announce'] + '/peer-update', json=payload)
        print(f'Peer {self.peer_id} ' + response.text)
        
    def update_tracker_download(self, torrent_data):
        payload = {
            "peer_id": self.peer_id,
            "file_name": torrent_data['file_name'],
            "pieces_indices": torrent_data['pieces_indices'],
        }
        response = requests.post(TRACKER_URL + '/peer-update-download', json=payload)
        print(f'Peer {self.peer_id} ' + response.text)

    def calculate_piece_indices_for_file(self, torrent_data, filename):
        piece_length = torrent_data['info']['piece length']
        files = torrent_data['info'].get('files', [])
        total_length = 0
        file_byte_ranges = {}
        for file in files:
            file_path = '/'.join(file['path'])
            start_byte = total_length
            end_byte = start_byte + file['length'] - 1
            file_byte_ranges[file_path] = (start_byte, end_byte)
            total_length += file['length']
        if filename not in file_byte_ranges:
            if filename == torrent_data['info']['name']:
                total_length = torrent_data['info']['length'] if 'length' in torrent_data['info'] else total_length
                start_index = 0
                end_index = (total_length - 1) // piece_length
            else: return []
        else:
            start_byte, end_byte = file_byte_ranges[filename]
            start_index = start_byte // piece_length
            end_index = end_byte // piece_length
        return list(range(start_index, end_index + 1))

    def get_peers_for_pieces(self, tracker_url, filename, piece_indices):
        piece_indices_str = ','.join(map(str, piece_indices))
        url = f"{tracker_url}/get-peer?filename={filename}&piece_indices={piece_indices_str}"
        try:
            response = requests.get(url)
            response.raise_for_status()
            peer_data = response.json()
            print("Received peer-set:", peer_data)
            return peer_data
        except requests.RequestException as e:
            print(f"Failed to get peer data: {e}")
            return {}
    
    def handle_client(self, client_socket):
        with client_socket:
            while True:
                data = client_socket.recv(1024)
                response = 'Response OK'
                if not data:
                    break
                data = data.decode()
                parts = data.split()
                data = ' '.join(parts[1:])
                file, cmd = data.rsplit(' ', 1)
                if(cmd == 'download'):
                    first_part = file.split('/')[0]
                    torrent_data = self.get_torrent(first_part)
                    requested_pieces = self.calculate_piece_indices_for_file(torrent_data, file)
                    peer_set = self.get_peers_for_pieces(torrent_data['announce'], first_part, requested_pieces)
                    info = {first_part: {}}
                    for piece_index, peer_ids in peer_set.items():
                        piece_byte = self.request_piece_from_peer(piece_index, random.choice(peer_ids), first_part)
                        info[first_part][piece_index] = piece_byte
                    self.files.append(info)
                    data_update = {
                        "peer_id": self.peer_id,
                        "file_name": first_part,
                        "pieces_indices": requested_pieces
                    }
                    self.update_tracker_download(data_update)
                    self.reconstruct_file(file, torrent_data)
                    client_socket.sendall(response.encode())
                    print(f"Peer {self.peer_id} has downloaded: {file}")
                elif(cmd == 'upload'):
                    self.handle_file.path = file
                    res = self.handle_file.divide_file_into_pieces()
                    self.files.append({res['name']: {str(i): value for i, value in enumerate(res['pieces'])}})
                    torrent_data = self.handle_file.create_torrent_file(res)
                    self.torrents.append(torrent_data)
                    self.update_tracker_upload(torrent_data)
                    TORRENT_TRACKER[res['name']] = self.peer_id
                    client_socket.sendall(response.encode())
                    print(f"Peer {self.peer_id} has uploaded: {file}")
                elif(cmd == 'torrent'):
                    response = next((item for item in self.torrents if item['info']['name'] == file), None)
                    response = json.dumps(response)
                    client_socket.sendall(response.encode())
                    # print(f"Peer {self.peer_id} has sent torrent file: {file}")
                elif(cmd == 'block'):
                    index, offset = parts[0].split('-')
                    for each in self.files:
                        if file in each:
                            piece = each[file].get(index)
                            piece_length = len(piece)
                            offset = int(offset)
                            if(offset >= piece_length):
                                response = b'finish'
                            else: 
                                end = min(offset + self.handle_file.block_size, piece_length)
                                response = piece[offset:end]
                            break
                    client_socket.sendall(response)
                elif(cmd == 'construct'):
                    self.reconstruct_file(file)
                    client_socket.sendall('Response OK'.encode())

    def stop(self):
        self.running = False
        temp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        temp_socket.connect(('localhost', self.port))
        temp_socket.close()
        
    def get_torrent(self, file):
        peer_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        peer_socket.connect(('localhost', START_PORT + int(TORRENT_TRACKER[file])))
        peer_socket.sendall(f"{self.peer_id} {file} torrent".encode())
        response = peer_socket.recv(1024).decode() 
        peer_socket.close()
        torrent = json.loads(response)
        print(f'Peer {self.peer_id} has received torrent file:')
        pprint.pprint(torrent)
        return torrent

    def request_piece_from_peer(self, piece_index, peer_id, file):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect(('localhost', START_PORT + peer_id))
        piece = bytearray()
        block_offset = 0
        while True: 
            sock.sendall(f"{piece_index}-{block_offset} {file} block".encode())
            response = sock.recv(self.handle_file.block_size)
            if response == b'finish': 
                break
            block_offset += self.handle_file.block_size
            piece.extend(response)
        sock.close()
        return piece
    def reconstruct_file(self, target_filename, torrent_data):
        root = target_filename.split('/')[0]
        
        for file_dict in self.files:
            if root in file_dict:
                pieces = file_dict[root]
                sorted_piece_keys = sorted(pieces.keys(), key=int)
                complete_file_data = bytearray()
                for key in sorted_piece_keys:
                    complete_file_data.extend(pieces[key])
                if not os.path.exists(OUTPUT_PATH):
                    os.makedirs(OUTPUT_PATH)
                if('length' in torrent_data['info']):
                    output_path = os.path.join(OUTPUT_PATH, root)
                    with open(output_path, 'wb') as file:
                        file.write(complete_file_data)
                    print(f"File successfully reconstructed and saved to {output_path}")
                else: 
                    name = torrent_data['info']['name']
                    files = torrent_data['info']['files']
                    for file_info in files:
                        file_path = os.path.join(*file_info['path'])
                        if target_filename == file_path:
                            dirs = file_info['path'][:-1]
                            output_dir = os.path.join(*dirs)
                            os.makedirs(output_dir, exist_ok=True)
                            output_path = os.path.join(OUTPUT_PATH, file_info['path'][-1])
                            with open(output_path, 'wb') as file:
                                start = file_info['mapping']['start_offset']
                                end = file_info['mapping']['end_offset']
                                file.write(complete_file_data[start:end])
                            print(f"File successfully reconstructed and saved to {output_path}")
                            return
                    if target_filename == name:
                        for file_info in files:
                            dirs = file_info['path'][:-1]
                            output_dir = os.path.join(OUTPUT_PATH, *dirs)
                            os.makedirs(output_dir, exist_ok=True)
                            output_path = os.path.join(output_dir, file_info['path'][-1])
                            with open(output_path, 'wb') as file:
                                start = file_info['mapping']['start_offset']
                                end = file_info['mapping']['end_offset']
                                file.write(complete_file_data[start:end])
                        print(f"File successfully reconstructed and saved to {target_filename}")
                            
                return
        print(f"File {target_filename} not found in the provided data.")
        

def main():
    peers = []
    for i in range(NUM_PEERS):
        peer = Peer(peer_id=i, port=START_PORT + i)
        peer.start()
        peers.append(peer)

    while True:
        cmd = input("> ").upper()
        if cmd == "DOWNLOAD":
            user_input = input(">> peer_id file_name: ")
            peer_id, file_name = user_input.split(maxsplit=1)
            peer_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            peer_socket.connect(('localhost', START_PORT + int(peer_id)))
            peer_socket.sendall(f"{peer_id} {file_name} download".encode())
            response = peer_socket.recv(1024)
            peer_socket.close()
        elif cmd == 'UPLOAD':
            user_input = input(">> peer_id file_name: ")
            peer_id, file_name = user_input.split(maxsplit=1)
            peer_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            peer_socket.connect(('localhost', START_PORT + int(peer_id) ))
            peer_socket.sendall(f"{peer_id} {file_name} upload".encode())
            response = peer_socket.recv(1024)
            peer_socket.close()
        elif cmd == "SHOW": 
            response = requests.get(TRACKER_URL + '/show')
            response.raise_for_status()
            data = response.json()  
            if 'files' in data:
                for name in data['files']:
                    print(name)
        elif cmd == "CONSTRUCT":
            user_input = input(">> peer_id file_name: ")
            peer_id, file_name = user_input.split(maxsplit=1)
            peer_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            peer_socket.connect(('localhost', START_PORT + int(peer_id) ))
            peer_socket.sendall(f"{peer_id} {file_name} construct".encode())
            response = peer_socket.recv(1024)
            peer_socket.close()
        elif cmd == "STOP":
            break

    for peer in peers:
        peer.stop()
        peer.join()

if __name__ == "__main__":
    main()

'''

'''