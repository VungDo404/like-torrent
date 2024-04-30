import socket
import threading

class Server(threading.Thread): 
    def __init__(self, port = 6000):
        super().__init__()
        self.host_name = socket.gethostname()
        self.ip = socket.gethostbyname(self.host_name)
        self.port = port
        self.peers = []
        self.torrent_tracker = {}
        self.max_peers = 10
        self.running = True
    def handle_client(self, server_socket):
        try:
            while self.running:
                client_socket, addr = server_socket.accept()
                if not self.running: 
                    break
                print(f"Sever {self.ip}:{self.port} connected to {addr}")
                while True:
                    data = client_socket.recv(1024).decode()
                    if not data:
                        break
                    parts = data.split()
                    cmd = parts.pop()
                    if cmd == 'add':
                        info = parts.pop()
                        ip,port = info.split('-')
                        file = ' '.join(parts)
                        self.torrent_tracker[file] = (ip, port)
                        print(self.torrent_tracker)
                        print(f"Added {file} with {ip}:{port} to torrent tracker")
                        client_socket.sendall("Added".encode())
                    if cmd == 'get':
                        file = ' '.join(parts)
                        if file in self.torrent_tracker:
                            ip, port = self.torrent_tracker[file]
                            client_socket.sendall(f"{ip} {port}".encode())
                        else:
                            client_socket.sendall("File not found".encode())
        finally:
            print(f"Closing server socket on {self.ip}")
            server_socket.close()
    def run(self):
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.bind((self.ip, self.port))
        server_socket.listen(self.max_peers)
        print(f"Server is listening on {self.ip}:{self.port}")
        thread1 = threading.Thread(target=self.handle_client, args=(server_socket,))
        thread1.start()
        thread1.join()
    def stop(self):
        self.running = False
        temp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        temp_socket.connect((self.ip, self.port))
        temp_socket.close()


    def command_line(self):
        while True:
            command = input("Enter a command: ")
            if command == "exit":
                break
            elif command == "peers":
                print(self.peers)
            else:
                print("Invalid command")


def main():
    server = Server()
    server.start()
    while True:
        cmd = input("> ").upper()
        if cmd == "DOWNLOAD":
            pass
        elif cmd == "STOP":
            break
    server.stop()
    server.join()
    
if __name__ == "__main__":
    main()
