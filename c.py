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
from contextlib import suppress


TRACKER_URL = 'http://192.168.100.6:8000' 
class File: 
    def __init__(self, path: str, ip):
        self.piece_size = 102400
        self.block_size = self.piece_size // 2
        self.path = path
        self.peer_ip = ip

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

    def show_progress(self, filename, processed, total):
        progress = int(50 * processed / total)
        progress_bar = '#' * progress + '-' * (50 - progress)
        print(f"\rPeer {self.peer_ip}~{filename} {progress_bar} {int(100 * processed / total)}%", end='')
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
    def __init__(self, port= 5000):
        super().__init__()
        self.host_name = socket.gethostname()
        self.peer_ip = socket.gethostbyname(self.host_name)
        self.port = port
        self.server_socket = None
        self.running = True
        self.OUTPUT_PATH = os.path.join(os.getcwd(), 'output')
        self.files = []
        self.SERVER_IP = '192.168.100.6' # CHANGE THIS TO YOUR SERVER IP
        self.SERVER_PORT = 6000 # THIS SHOULD MATCH THE PORT IN s.py
        self.handle_file = File('', self.peer_ip)

    def run(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind((self.peer_ip, self.port))
        self.server_socket.listen(10)
        print(f"\033[33mPeer {self.peer_ip}:{self.port} listening on port {self.port}\033[0m")
        try:
            while self.running:
                client_socket, addr = self.server_socket.accept()
                if not self.running: 
                    break
                print(f"\033[96mPeer {self.peer_ip}:{self.port} connected to {addr}\033[0m")
                threading.Thread(target=self.handle_client, args=(client_socket,)).start()
        finally:
            print(f"\033[33mPeer {self.peer_ip} listening on port {self.port}\033[0m")
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
            "peer_ip": self.peer_ip,
            "peer_port": self.port,
            "file_name": torrent_data['info']['name'],
            "pieces_indices": list(range(number_of_pieces)),
            "file_details": file_details
        }
        response = requests.post(torrent_data['announce'] + '/peer-update', json=payload)
        print(f'Peer {self.peer_ip}:{self.port} ' + response.text)
        
    def update_tracker_download(self, torrent_data):
        payload = {
            "peer_ip": self.peer_ip,
            "peer_port": self.port,
            "file_name": torrent_data['file_name'],
            "pieces_indices": torrent_data['pieces_indices'],
        }
        response = requests.post(TRACKER_URL + '/peer-update-download', json=payload)
        print(f'Peer {self.peer_ip}:{self.port} ' + response.text)

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
            print(f"\033[34mReceived peer-set: \033[0m{peer_data}\033[0m")
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
                file, cmd = data.rsplit(' ', 1)
                if(cmd == 'download'):
                    first_part = file.split('/')[0]
                    torrent_data = self.get_torrent(first_part)
                    requested_pieces = self.calculate_piece_indices_for_file(torrent_data, file)
                    peer_set = self.get_peers_for_pieces(torrent_data['announce'], first_part, requested_pieces)
                    info = {first_part: {}}
                    is_success = True
                    for piece_index, peer_ips in peer_set.items():
                        result = self.request_piece_from_peer(piece_index, peer_ips, first_part)
                        if('is_success' in result and result['is_success']):
                            temp_byte = result['piece'] if 'piece' in result else bytearray()
                            if(temp_byte):
                                info[first_part][piece_index] = temp_byte
                            else:   
                                print(f"\033[31mFailed to download piece {piece_index}, there seems to be an issue with the peer.\033[0m")
                                is_success = False
                                break
                        else:
                            print(f"\033[31mFailed to download piece {piece_index}, there seems to be an issue with the peer.\033[0m")
                            is_success = False
                            break
                    if is_success:
                        temp = dict(sorted(info[first_part].items()))
                        temp_hash = ''
                        for index in temp:
                            temp_hash += self.handle_file.calculate_sha1(temp[index])
                        print(f"\033[34mDownloaded pieces hash: \033[0m{temp_hash}")
                        if temp_hash == torrent_data['info']['pieces']:
                            print("\033[34mDownloaded pieces match the hash in the torrent file.\033[0m")
                            self.files.append(info)
                            data_update = {
                                "file_name": first_part,
                                "pieces_indices": requested_pieces
                            }
                            self.update_tracker_download(data_update)
                            self.reconstruct_file(file, torrent_data)
                            client_socket.sendall(response.encode())
                            print(f"\033[34mPeer {self.peer_ip}:{self.port} has downloaded: {file}\033[0m")
                        else:
                            print("\033[31mDownloaded pieces do not match the hash in the torrent file.\033[0m")

                            response = 'Response Failed'
                            client_socket.sendall(response.encode())
                    else:
                        response = 'Response Failed'
                        client_socket.sendall(response.encode())
                elif(cmd == 'upload'):
                    self.handle_file.path = file
                    res = self.handle_file.divide_file_into_pieces()
                    self.files.append({res['name']: {str(i): value for i, value in enumerate(res['pieces'])}})
                    torrent_data = self.handle_file.create_torrent_file(res)
                    self.update_tracker_upload(torrent_data)
                    json_str = json.dumps(torrent_data)
                    self.update_torrent_server(f"{json_str} add")
                    client_socket.sendall(response.encode())
                    print(f"\033[34mPeer {self.peer_ip}:{self.port} has uploaded: {file}\033[0m")
                elif(cmd == 'block'):
                    index, offset = parts[0].split('-')
                    parts = file.split(' ', 1)  
                    filename = parts[1]
                    response = bytearray()
                    for each in self.files:
                        if filename in each and index in each[filename]:
                            piece = each[filename].get(index)
                            piece_length = len(piece)
                            offset = int(offset)
                            if(offset < piece_length):
                                end = min(offset + self.handle_file.block_size, piece_length)
                                response = piece[offset:end]
                            break
                        else:
                            raise ValueError(f"Piece {index} not found for file {filename}")
                    client_socket.sendall(response)
                elif(cmd == 'length'):
                    filename, index = file.rsplit(' ', 1)
                    piece_length = 0
                    for each in self.files:
                        if filename in each:
                            piece = each[filename].get(index)
                            piece_length = len(piece)
                            break
                    client_socket.sendall(str(piece_length).encode())
                elif(cmd == 'construct'):
                    self.reconstruct_file(file)
                    client_socket.sendall('Response OK'.encode())

    def stop(self):
        self.running = False
        temp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        temp_socket.connect((self.peer_ip, self.port))
        temp_socket.close()

    def get_torrent(self, file):
        peer_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        peer_socket.connect((self.SERVER_IP, self.SERVER_PORT))
        peer_socket.sendall(f"{file} get".encode())
        response = peer_socket.recv(1024).decode() 
        peer_socket.close()
        
        torrent = json.loads(response)
        print(f"\033[34mPeer {self.peer_ip}:{self.port} has received torrent file:\033[0m")
        pprint.pprint(torrent)
        return torrent

    def request_block_from_peer(self, piece_index, block_offset, peer_ips, file, index, blocks, info):
        temp = peer_ips
        
        while True:
            value = random.choice(temp)
            try: 
                peer_ip, peer_port = value
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.connect((peer_ip, peer_port))
                sock.sendall(f"{piece_index}-{block_offset} {file} block".encode())
                response = sock.recv(self.handle_file.block_size)
                sock.close()
                blocks[index] = response
                break
            except: 
                with suppress(ValueError):
                    temp.remove(value)
                if len(temp) == 0:
                    info['is_success'] = False
                    break

    def request_piece_from_peer(self, piece_index, peer_ips, file):
        piece_size = 0
        temp = peer_ips
        while True:
            value = random.choice(temp)
            try: 
                peer_ip, peer_port = value
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.connect((peer_ip, peer_port))
                sock.sendall(f"{file} {piece_index} length".encode())
                piece_size = sock.recv(1024)
                sock.close()
                if(piece_size):
                    break
                else: 
                    with suppress(ValueError):
                        temp.remove(value)
                    if len(temp) == 0:
                        return {'is_success': False}
            except: 
                with suppress(ValueError):
                    temp.remove(value)
                if len(temp) == 0:
                    return {'is_success': False}
        piece = bytearray()
        blocks = {}
        block_offset = 0
        info = {'is_success': True}
        num = math.ceil(int(piece_size.decode()) / self.handle_file.block_size)
        pool = []
        for index in range(num):
            block_offset = index * self.handle_file.block_size
            thread = threading.Thread(target=self.request_block_from_peer, args=(piece_index, block_offset, peer_ips, file, index, blocks, info))
            thread.start()
            pool.append(thread)

        for thread in pool:
            thread.join()

        blocks = dict(sorted(blocks.items()))
        for index in blocks:
            piece.extend(blocks[index])
        info['piece'] = piece
        return info

    def reconstruct_file(self, target_filename, torrent_data):
        root = target_filename.split('/')[0]
        
        for file_dict in self.files:
            if root in file_dict:
                pieces = file_dict[root]
                sorted_piece_keys = sorted(pieces.keys(), key=int)
                complete_file_data = bytearray()
                for key in sorted_piece_keys:
                    complete_file_data.extend(pieces[key])
                if not os.path.exists(self.OUTPUT_PATH):
                    os.makedirs(self.OUTPUT_PATH)
                if('length' in torrent_data['info']):
                    output_path = os.path.join(self.OUTPUT_PATH, root)
                    with open(output_path, 'wb') as file:
                        file.write(complete_file_data)
                    print(f"\033[34mFile successfully reconstructed and saved to \033[0m{output_path}\033[0m")
                else: 
                    name = torrent_data['info']['name']
                    files = torrent_data['info']['files']
                    for file_info in files:
                        file_path = os.path.join(*file_info['path'])
                        if target_filename == file_path:
                            dirs = file_info['path'][:-1]
                            output_dir = os.path.join(*dirs)
                            os.makedirs(output_dir, exist_ok=True)
                            output_path = os.path.join(self.OUTPUT_PATH, file_info['path'][-1])
                            with open(output_path, 'wb') as file:
                                start = file_info['mapping']['start_offset']
                                end = file_info['mapping']['end_offset']
                                file.write(complete_file_data[start:end])
                            print(f"\033[34mFile successfully reconstructed and saved to \033[0m{output_path}\033[0m")
                            return
                    if target_filename == name:
                        for file_info in files:
                            dirs = file_info['path'][:-1]
                            output_dir = os.path.join(self.OUTPUT_PATH, *dirs)
                            os.makedirs(output_dir, exist_ok=True)
                            output_path = os.path.join(output_dir, file_info['path'][-1])
                            with open(output_path, 'wb') as file:
                                start = file_info['mapping']['start_offset']
                                end = file_info['mapping']['end_offset']
                                file.write(complete_file_data[start:end])
                        print(f"\033[34mFile successfully reconstructed and saved to \033[0m{target_filename}\033[0m")
                            
                return
        print(f"File {target_filename} not found in the provided data.")

    def update_torrent_server(self, data):
        peer_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        peer_socket.connect((self.SERVER_IP, self.SERVER_PORT))
        peer_socket.sendall(data.encode())
        response = peer_socket.recv(1024).decode() 
        peer_socket.close()

def main():
    peer = Peer()
    peer.start()
    while True:
        cmd = input("> ").upper()
        if cmd == "DOWNLOAD":
            file_name = input(">> file_name: ")
            peer_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            peer_socket.connect((peer.peer_ip, peer.port))
            peer_socket.sendall(f"{file_name} download".encode())
            response = peer_socket.recv(1024)
            peer_socket.close()
        elif cmd == 'UPLOAD':
            file_name = input(">> file_name: ")
            peer_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            peer_socket.connect((peer.peer_ip, peer.port))
            peer_socket.sendall(f"{file_name} upload".encode())
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

    peer.stop()
    peer.join()

if __name__ == "__main__":
    main()

'''

'''