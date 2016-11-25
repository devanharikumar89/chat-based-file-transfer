#! /usr/bin/python

from library import *
from socket import *
from chatRoom import *
import logging

logging.basicConfig(filename='server.log', level=logging.DEBUG)


  class ClientNode(object):
    """
    Class object for holding client related information
    """

    def __init__(self, server_reference, ip, socket, client_id):
      """

      :param ip: IP address of client.
      :param socket: Socket at server used to communicate with client.
      :param client_id:
      """
      # TODO: Client ID cant be used to index clients array if previous clients have exited.
      # TODO: User cannot exit and relogin with same username if entry not deleted.
      self.server = server_reference
      self.ip = ip
      self.socket = socket
      self.client_id = client_id
      self.username = None
      self.suspended = False
      self.chatroom = None

    def execute(self):
      """
      This is the main per-client execution thread for the server.
      Enable a client to login and proceed to listen to, and forward, its messages.
      """
      msg = 'Connected to ' + self.server.ip + ' at port ' + str(self.server.port)
      msg += '\nPlease enter your username\n'
      send_data(self.socket, msg)
      self.accept_login()
      if not self.suspended:
        msg = 'Welcome to ' + self.chatroom.name + '. You are all set to pass messages\n'
        send_data(self.socket, msg)
      while not self.suspended:
        self.accept_message()
      self.chatroom.clients.remove(self.client_id)
      send_data(self.socket, 'exit')
      self.socket.close()

    def accept_login(self):
      """
      Establish the clients username and create a new chatroom, or add it to an existing one.
      """
      self.check_username()
      self.create_or_join()

    def check_username(self, tries=5):
      """
      Try tries number of times to get a unique username from client.
      """
      logging.info('Check_username')
      msg = decode_data(recv_data(self.socket))
      name = msg[0]
      usernames = [i.username for i in self.server.clients]
      if name in usernames + ['server', 'all']:  # 'all', 'server' not valid usernames
        if tries > 0:
          send_err(self.socket, 'Username taken, kindly choose another.\n')
          self.check_username(tries - 1)
        else:
          send_err(self.socket, 'Max tries reached, closing connection.\n')
          self.suspended = True
      else:
        self.username = name
        send_ok(self.socket, 'Username ' + name + ' accepted. Send create/join a chatroom\n')
      return

    def create_or_join(self, tries=5):
      """
      Check if client wants to create a new chatroom or join an existing one.
      """
      logging.info('create_or_join')
      if self.suspended:
        return
      msg = decode_data(recv_data(self.socket))
      option = str(msg[0]).lower()
      if option == 'create':  # Create chatroom - check chatroom name
        send_ok(self.socket, 'Specify a chatroom name to create.\n')
        self.create_chatroom()
      elif option == 'join':  # Join existing chatroom - Send list of available peers.
        if len(self.server.chatrooms):
          send_ok(self.socket, 'Here is a list of chatrooms you can join.\n')
          send_list(self.socket, self.server.get_chatrooms())
          self.join_chatroom()
        else:  # There are no chatrooms to join
          if tries > 0:
            send_err(self.socket, 'There are no chatrooms to join now\n')
            self.create_or_join(tries - 1)
          else:
            send_err(self.socket, 'Max tries reached, closing connection.\n')
            self.suspended = True
      else:
        if tries > 0:
          send_err(self.socket, 'Sorry, specify join/create to join or create a chatroom\n')
          self.create_or_join(tries - 1)
        else:
          send_err(self.socket, 'Max tries reached, closing connection.\n')
          self.suspended = True

    def create_chatroom(self, tries=5):
      """
      Create chatroom - Add client as first user of room when a unique name is received
      :param tries: Retry 'tries' number of times to get a unique chatroom name.
      """
      logging.info('Create_chatroom')
      if self.suspended:
        return
      msg = decode_data(recv_data(self.socket))
      name, names = msg[0], [i.name for i in self.server.chatrooms]
      if name in names:
        if tries > 0:
          send_err(self.socket, 'Sorry, chatroom already taken. Please try again.\n')
          self.create_chatroom(tries - 1)
        else:
          send_err(self.socket, 'Max tries reached, closing connection.\n')
          self.suspended = True
      else:
        new_room = ChatRoom(self.server, name, self.client_id)
        self.server.chatrooms.append(new_room)
        self.chatroom = new_room
        send_ok(self.socket, 'Chatroom ' + name + ' created.\n')

    def join_chatroom(self, tries=5):
      """
      Join chatroom - Add client to client list of room when request is received
      :param tries: Retry 'tries' number of times to get an existent chatroom name.
      """
      logging.info('join_chatroom')
      if self.suspended:
        return
      msg = decode_data(recv_data(self.socket))
      name = msg[0]
      for room in self.server.chatrooms:
        if name == room.name:
          room.broadcast('INFO| New user ' + self.username + ' has joined\n', self.username)
          send_ok(self.socket, 'You have joined chatroom - ' + name + '\n')
          self.chatroom = room
          if len(room.clients):
            send_data(self.socket, 'Here is a list of peers in the room:\n')
            send_list(self.socket, self.chatroom.get_usernames())
          else:
            send_data(self.socket, 'There are no peers in the room:\n')
          room.clients.append(self.client_id)
          return
      if tries > 0:
        send_err(self.socket, 'Sorry, chatroom name not found. Please try again.\n')
        self.join_chatroom(tries - 1)
      else:
        send_err(self.socket, 'Max tries reached, closing connection.\n')
        self.suspended = True

    def accept_message(self):
      """
      Check the destination field in a message and unicast it to the destination or,
      broadcast if destination is 'all'. Edit message to include source instead of destination
      Messages with destination as 'server' may be an exit or quit message.
      """
      # TODO
      msg = decode_data(recv_data(self.socket))
      destination = msg[0]
      if destination[:1] != '@':
        send_err(self.socket, 'Sorry, first field in message should be @<destination>\n')
        return
      destination = destination[1:]
      msg[0] = '#' + self.username
      if destination == 'all':
        self.chatroom.broadcast('|'.join(msg), self.username)
      elif destination == 'server':
        # TODO: This piece of code may need more features
        if len(msg) > 1:
          if msg[1].lower() in ['exit', 'quit']:
            self.suspended = True
          elif msg[1].lower() == 'get_peers':
            send_list(self.socket, self.chatroom.get_usernames())
          elif msg[1].lower() == 'get_rooms':
            send_list(self.socket, self.server.get_chatrooms())
          else:  # Just deliver the message to server console
            print '|'.join(msg)
      else:
        dest_client = self.chatroom.get_client(destination)
        if dest_client is None:
          send_err(self.socket, 'Sorry, destination client not present in chatroom\n')
        else:
          send_list(dest_client.socket, msg)