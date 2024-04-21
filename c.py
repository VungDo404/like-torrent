import hashlib
import threading
import socket
import os
import time
import requests
import math
import json
import pprint


TRACKER_URL = 'http://localhost:8000' 
TORRENT_TRACKER = {}
START_PORT = 5000
NUM_PEERS = 3

class File: 
    def __init__(self, path: str, id):
        self.piece_size = 102400
        self.block_size = self.piece_size / 2
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

        # First, calculate total size for progress
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
                    file_size = os.path.getsize(file_path)
                    file_info[relative_path] = file_size
                    with open(file_path, 'rb') as f:
                        file_data = f.read()
                        total_data.extend(file_data)
                        start_piece_index = current_offset // self.piece_size
                        end_piece_index = (current_offset + file_size - 1) // self.piece_size
                        piece_mappings.append({
                            'file_path': relative_path,
                            'start_piece': start_piece_index,
                            'end_piece': end_piece_index,
                            'start_offset': current_offset % self.piece_size,
                            'end_offset': (current_offset + file_size - 1) % self.piece_size
                        })
                        current_offset += file_size
                        self.show_progress(name, current_offset, total_size)
        elif os.path.isfile(self.path):
            with open(self.path, 'rb') as f:
                file_data = f.read()
                total_data.extend(file_data)
                file_info[name] = total_size
                piece_mappings.append({
                    'file_path': name,
                    'start_piece': 0,
                    'end_piece': (total_size - 1) // self.piece_size,
                    'start_offset': 0,
                    'end_offset': (total_size - 1) % self.piece_size
                })
                self.show_progress(name, total_size, total_size)

        # Divide total data into pieces
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
        torrent_data = {
            'announce': TRACKER_URL,
            'info': {
                'piece length': self.piece_size,
                'pieces': ''.join([self.calculate_sha1(piece) for piece in file_data['pieces']])
            }
        }
        if len(file_data['info']) > 1 or os.path.isdir(self.path):
            torrent_data['info']['files'] = []
            torrent_data['info']['name'] = file_data['name']  
            for file_name, size in file_data['info'].items():
                file_path = os.path.relpath(os.path.join(self.path, file_name), start=os.path.dirname(self.path))
                torrent_data['info']['files'].append({
                    'length': size,
                    'path': file_path.split(os.sep)
                })
        else:
            torrent_data['info']['name'] = file_data['name']
            torrent_data['info']['length'] = file_data['info'][file_data['name']]
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
        self.server_socket.listen(5)
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

    def update_tracker(self, torrent_data):
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
            print("Received peer data:", peer_data)
            return peer_data
        except requests.RequestException as e:
            print(f"Failed to get peer data: {e}")
            return {}
    
    def handle_client(self, client_socket):
        with client_socket:
            while True:
                data = client_socket.recv(1024).decode()
                response = 'Response OK'
                if not data:
                    break
                parts = data.split()
                data = ' '.join(parts[1:])
                file, cmd = data.rsplit(' ', 1)
                if(cmd == 'download'):
                    first_part = file.split('/')[0]
                    peer_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    peer_socket.connect(('localhost', START_PORT + int(TORRENT_TRACKER[first_part])))
                    peer_socket.sendall(f"{self.peer_id} {first_part} torrent".encode())
                    response = peer_socket.recv(1024).decode() 
                    torrent_data = json.loads(response)
                    print(f'Peer {self.peer_id} has received torrent file:')
                    pprint.pprint(torrent_data)
                    peer_socket.close()
                    requested_pieces = self.calculate_piece_indices_for_file(torrent_data, file)
                    peer_set = self.get_peers_for_pieces(torrent_data['announce'], first_part, requested_pieces)
                    print(peer_set)
                    print(f"Peer {self.peer_id} has downloaded: {file}")
                elif(cmd == 'upload'):
                    self.handle_file.path = file
                    res = self.handle_file.divide_file_into_pieces()
                    self.files.append(res)
                    torrent_data = self.handle_file.create_torrent_file(res)
                    self.torrents.append(torrent_data)
                    pprint.pprint(torrent_data)
                    # self.update_tracker(torrent_data)
                    TORRENT_TRACKER[res['name']] = self.peer_id
                    print(f"Peer {self.peer_id} has uploaded: {file}")
                elif(cmd == 'torrent'):
                    response = next((item for item in self.torrents if item['info']['name'] == file), None)
                    response = json.dumps(response)
                    print(f"Peer {self.peer_id} has sent torrent file: {file}")
                client_socket.sendall(response.encode())

    def stop(self):
        self.running = False
        temp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        temp_socket.connect(('localhost', self.port))
        temp_socket.close()

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
        elif cmd == "STOP":
            break

    for peer in peers:
        peer.stop()
        peer.join()

if __name__ == "__main__":
    main()
    
    
'''
def create_torrent_file(self, file_data):
        pieces_hash = ''.join([self.calculate_sha1(piece) for piece in file_data['pieces']])
        torrent_data = {
            'announce': 'http://localhost:8000', 
            'info': {
                'piece length': self.piece_size,
                'pieces': pieces_hash
            }
        }
        
        if 'file_mappings' in file_data['info']:  # This implies multiple files
            torrent_data['info']['files'] = []
            torrent_data['info']['name'] = file_data['name']  # Directory name
            for mapping in file_data['info']['file_mappings']:
                torrent_data['info']['files'].append({
                    'length': mapping['file_size'],
                    'path': mapping['file_path'].split(os.sep),
                    'mapping': {
                        'start_piece': mapping['start_piece'],
                        'end_piece': mapping['end_piece'],
                        'start_offset': mapping['start_offset'],
                        'end_offset': mapping['end_offset']
                    }
                })
        else:  # Single file scenario
            torrent_data['info']['name'] = file_data['name']
            torrent_data['info']['length'] = file_data['info']['file_info'][file_data['name']]

        return torrent_data
'''