import socket
import time

class PersistentConnection:
    def __init__(self, server_address, server_port):
        self.server_address = server_address
        self.server_port = server_port
        self.socket = None

        self.connect()

    def connect(self):
        """Establish the socket connection."""
        while True:
            try:
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.socket.connect((self.server_address, self.server_port))
                print("Connected to the server")
                break  # Exit the loop if connection is successful
            except socket.error as e:
                print(f"Connection attempt failed: {e}")

    def send_data(self, data):
        """Send data to the server, with reconnection handling."""
        try:
            self.socket.sendall(data.encode('utf-8'))
        except socket.error as e:
            print(f"Connection lost: {e}. Reconnecting...")
            self.connect()  # Attempt to reconnect
            self.socket.sendall(data.encode('utf-8'))  # Retry sending data

    def close(self):
        """Close the socket connection."""
        if self.socket:
            self.socket.close()
            print("Connection closed")

    def __enter__(self):
        """Context manager entry: establish the connection."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit: close the connection."""
        self.close()
