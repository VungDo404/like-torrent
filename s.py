from http.server import HTTPServer, BaseHTTPRequestHandler
import json
from urllib.parse import urlparse, parse_qs


class TrackerHTTPServer(BaseHTTPRequestHandler):
    registry = {}

    def do_POST(self):
        if self.path == '/peer-update':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode())

            file_name = data['file_name']
            peer_id = data['peer_id']
            pieces_indices = data['pieces_indices']
            file_details = data.get('file_details', None)
            if file_name not in self.registry:
                self.registry[file_name] = {
                    "piece_indices": {},
                    "files_nested": []
                }
            for index in pieces_indices:
                if index not in self.registry[file_name]["piece_indices"]:
                    self.registry[file_name]["piece_indices"][index] = []
                if peer_id not in self.registry[file_name]["piece_indices"][index]:
                    self.registry[file_name]["piece_indices"][index].append(peer_id)
            if file_details:
                self.registry[file_name]['files_nested'] = file_details
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            response = {"message": "Update successful"}
            self.wfile.write(json.dumps(response).encode('utf-8'))
            print(self.registry)

    def do_GET(self):
        if self.path == '/show':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            temp = []
            for key in self.registry.keys():
                if(len(self.registry[key]['files_nested'])):
                    for each in self.registry[key]['files_nested']:
                        temp.append(each['name'])
                temp.append(key)
            self.wfile.write(json.dumps({'files':  temp}, indent=4).encode('utf-8'))
        elif self.path.startswith('/get-peer'): 
            query_components = parse_qs(urlparse(self.path).query)
            piece_indices = query_components.get('piece_indices', [''])[0]
            filename = query_components.get('filename', [''])[0]
            print('INDEX: ', piece_indices)
            print('NAME: ', filename)
            try:
                piece_indices = [int(index) for index in piece_indices.split(',')]
            except ValueError:
                self.send_error(400, "Invalid piece indices")
                return
            response_data = self.find_peers_by_piece_indices(filename, piece_indices)
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response_data).encode('utf-8'))
        else:
            self.send_error(404, "File Not Found")

    def find_peers_by_piece_indices(self, filename, piece_indices):
        file_data = self.registry.get(filename, {})
        pieces_info = file_data.get('piece_indices', {})
        result = {index: pieces_info.get(index, []) for index in piece_indices}
        return result


def run(server_class=HTTPServer, handler_class=TrackerHTTPServer, port=8000):
    server_address = ('', port)
    httpd = server_class(server_address, handler_class)
    print(f"Starting httpd server on port {port}")
    httpd.serve_forever()

if __name__ == "__main__":
    run()