import config
import urllib, urllib2, json, os, time, random,hmac,hashlib
import SocketServer
import threading
import PictorriaHTTPServer

stats_requests = 0
token = ''
self_port = 0
self_ip = ''


def init():
    # test folder permission
    try:
        t1 = open(config.request_path + 'soft_permission_test.txt','w')
        t2 = open(config.response_path + 'soft_permission_test.txt','w')
        t3 = open(config.image_path + 'soft_permission_test.txt','w')
    except:
        print "You don't have write permission"
        return 'error'
    os.system('rm '+config.request_path + 'soft_permission_test.txt')
    os.system('rm '+config.response_path + 'soft_permission_test.txt')
    os.system('rm '+config.image_path + 'soft_permission_test.txt')

    #TODO: check for matlab info file

    # Finding the PORT to run
    global httpd
    if len(config.default_port)>0:
        server_running = False
        for PORT in config.default_port:
            try:
                httpd = SocketServer.ThreadingTCPServer(("", PORT), req_handler, False)
                httpd.allow_reuse_address = True
                httpd.server_bind()
                httpd.server_activate()
                server_running = True
            except:
                pass
            if server_running:
                break
        if not server_running:
            print 'Cannot open server socket on port ' + str(PORT)
            print 'Change the default port number on config.py or leave it blank for random port allocation'
            return 'error'
    else:
        server_running = False
        tries = 0
        while (not server_running) and (tries<20):
            PORT = random.randint(1024,65535)
            tries += 1
            try:
                httpd = SocketServer.ThreadingTCPServer(("", PORT), req_handler)
                server_running = True
            except:
                pass
        if not server_running:
            print 'Cannot open server socket'
            print 'Make sure that python has the permission to open socket server'
            return 'error'
    server_thread = threading.Thread(target=httpd.serve_forever)
    server_thread.setDaemon(True)
    server_thread.start()
    print "Listening on port#: "+str(PORT)

    # find self ip
    global self_ip
    self_ip = ip_echo()
    if not self_ip:
        return 'error'
    global self_port
    self_port = PORT


    # Register Server on Pictorria
    hmac = compute_hmac(self_ip + str(PORT),config.secret_key)
    msg = json.dumps({'command':'register', 'api_key':config.api_key , 'hmac':hmac , 'port':self_port , 'ip':self_ip , 'version':config.version })
    req = urllib2.Request(config.pictorria,msg,{'content-type':'application/json'})
    try:
        response = json.loads(urllib2.urlopen(req).read())
        if response['status']=='successful':
            global token
            token = response['token']
            global server_time
            server_time = response['server_time']
            print ':) Server registered successfully.'
        else:
            print ':( Server registration failed.'
            return 'error'
    except:
        print ':( Server registration message not sent.'
        return 'error'

    check_result_thread = check_result()
    check_result_thread.setDaemon(True)
    check_result_thread.start()

    # Verify server
    verified = False
    msg = json.dumps({'command':'check_me', 'api_key':config.api_key , 'port':self_port , 'ip':self_ip, 'token' : token})
    req = urllib2.Request(config.pictorria,msg,{'content-type':'application/json'})
    try:
        response = json.loads(urllib2.urlopen(req).read())
        if response['status'] == 'successful':
            verified = True
            print ':) Connection verified successfully.'
    except:
        response = ''
        pass
    if not verified:
        if 'error_msg' in response:
            print ':( Connection verification failed.'
            print response['error_msg']
#            print response
        else:
            print ':( Connection verification failed.'
        return 'error'
    send_feed_me()
    return 'success'

def verify_connection():
    verified = False
    msg = json.dumps({'command':'check_me', 'api_key':config.api_key , 'port':self_port , 'ip':self_ip, 'token' : token})
#    print msg
    req = urllib2.Request(config.pictorria,msg,{'content-type':'application/json'})
    try:
        response = json.loads(urllib2.urlopen(req).read())
        if response['status'] == 'successful':
            verified = True
            print ':) Connection verified successfully.'
    except:
        response = ''
        pass
    if not verified:
        if 'error_msg' in response:
            print ':( Connection verification failed.'
            print response['error_msg']
        else:
            print ':( Connection verification failed.'
        return 'error'

    return verified

def send_feed_me():
    global self_port, self_ip, token
    msg = json.dumps({'command':'feed_me', 'api_key':config.api_key , 'port':self_port , 'ip':self_ip, 'token' : token})
    req = urllib2.Request(config.pictorria,msg,{'content-type':'application/json'})
    try:
        urllib2.urlopen(req)
    except:
        pass

class req_handler(PictorriaHTTPServer.BaseHTTPRequestHandler):
    def do_POST(self):
        msg = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
#        print 'POST request came '
        if msg['command']:
            command = msg['command']
        else:
            self.send_error_msg(':( Command not specified')

        if command=='check_status':
            response = json.dumps({'status':'successful'})
            self.send_json_response(response)

        elif command=='process':
        # Process Request Handler
            url =  msg['url']
            req_id = msg['image_id'] + '-' + msg['api_key']
            # Request filename
            req_filename = str(req_id) + '_' + str(time.time())
            # Request image file location
            tmp_image_location = config.image_path + 'temp_image_' + req_filename
            try:
                # Download image
                urllib.urlretrieve(url, tmp_image_location)
            except:
                # Remove image and write error response
                os.system('rm ' + tmp_image_location)
                tmp_response_location = config.response_path + 'temp_result_' + req_filename
                f = open(tmp_response_location,'w')
                f.write('{"status":"failed","error_message":"could not download image", "req_id":"%s"}'%req_id)
                f.flush()
                f.close()
                response_location = config.response_path + 'result_' + req_filename
                os.system('mv '+ tmp_response_location + ' ' + response_location)
                self.send_error_msg('could not download image')
                return

            # Move image in the location for processing
            image_location = config.image_path + req_id
            os.system('mv ' + tmp_image_location + ' ' + image_location)

            # Prepare json for processing
            msg['image'] = image_location
            msg_json = json.dumps(msg)

            # Write json in location for processing
            f = open(config.request_path + req_filename ,'w')
            f.write(msg_json)
            f.flush()
            f.close()
            f = open(config.response_path +'result_'+ req_filename ,'w')
            f.write(msg_json)
            f.flush()
            f.close()

            response = json.dumps({'status':'successful'})
            self.send_json_response(response)

        elif command=='message':
        # Process message from Pictorria
            command_msg = msg['command']
            if command_msg=='shut_down':
            #TODO: stop this application!
                pass
            elif command_msg=='print':
                print msg['message']
            elif command_msg=='re-register':
            #TODO: stop threds and register again
                init()

            response = json.dumps({'status':'successful'})
            self.send_json_response(response)
        else:
            self.send_error_msg(':( Command not recognized')

    def send_error_msg(self,msg):
        print 'ERROR : ' + msg
        response = json.dumps({'status':'failed','error_msg':msg})
        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.send_header("Last-Modified", self.date_time_string(time.time()))
        self.end_headers()
        self.wfile.write(response)

#    def do_GET(self):
#        print 'get request came'
#        response = 'yes I am'
#        self.my_send_response(response)

    def send_json_response(self,response):
        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.send_header("Last-Modified", self.date_time_string(time.time()))
        self.end_headers()
        self.wfile.write(response)

    def my_send_response(self,response):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.send_header("Content-Length", str(len(response)))
        self.send_header("Last-Modified", self.date_time_string(time.time()))
        self.end_headers()
        self.wfile.write(response)


class check_result ( threading.Thread ):
    def __init__(self):
        threading.Thread.__init__ (self)

    def run ( self ):
        while True:
            prefix = 'result_'
            ls = [x for x in os.listdir(config.response_path) if x[0:len(prefix)]==prefix]
            for filename in ls:
                try:
                    # Move response to location for sending
                    response_location = config.response_path + filename
                    sending_response_location = config.response_path + 'sending_' + filename
                    os.system('mv ' + response_location + ' ' + sending_response_location)

                    # get request id
                    req_id = filename[len(prefix):]

                    # put response for sending
                    t = result_sender(req_id, sending_response_location,response_location)
                    t.setDaemon(True)
                    t.start()

                    # remove image
                    t = req_id.split('_')[0].split('-')
                    image_location = config.image_path + t[0] + '-' + t[1]
                    if config.remove_images:
                        os.remove(image_location)
                except :
                    pass
            time.sleep(.1)

class result_sender( threading.Thread ):
    def __init__(self, req_id, sending_response_location,response_location):
        threading.Thread.__init__ (self)
        self.req_id = req_id
        self.sending_response_location = sending_response_location
        self.response_location = response_location

    def run (self):
        f = open(self.sending_response_location)
        result = json.loads(f.read())
        f.close()
        t = self.req_id.split('_')[0].split('-')
        msg = {'api_key':config.api_key , 'port':self_port , 'ip':self_ip}
        msg['result'] = result
        msg['image_id'] = t[0]
        msg['command'] = 'result'
        msg['token'] = token
        msg = json.dumps(msg)
        print msg
        req = urllib2.Request(config.pictorria,msg,{'content-type':'application/json'})
        try:
            a = urllib2.urlopen(req).read()
            server_response = json.loads(a)
            if server_response['status']=='successful':
                success = True
            else:
                print 'hamedfosh'
                success = False
                print server_response['error_msg']
        except:
            success = False
            print 'Could not submit result to Pictorria server'
        # remove the result file if it has been submitted, else move it back for resubmission
        if success:
            os.system('rm ' + self.sending_response_location)
            print t[0] + ':' + t[1] + ':' + 'Successfully submitted to the server'
        else:
            #os.system('mv ' + self.sending_response_location + ' ' + self.response_location)
            pass

# get self IP address
def ip_echo():
    msg = json.dumps({'command':'ip_echo'})
    req = urllib2.Request(config.pictorria,msg,{'content-type':'application/json'})
    response = json.loads(urllib2.urlopen(req).read())
    if response['ip']:
        print ':) Self IP is : ' + response['ip']
        return response['ip']
    else:
        print ':( Could not find self IP'
        return False

def compute_hmac(message,secret_key):
    return hmac.new(str(secret_key), str(message), hashlib.sha1).hexdigest()

def send_shut_down_signal():
    msg = json.dumps({'command':'shut_down' , 'api_key':config.api_key , 'port':self_port , 'ip':self_ip, 'token' : token})
    req = urllib2.Request(config.pictorria,msg,{'content-type':'application/json'})
    response = json.loads(urllib2.urlopen(req).read())
    if response['status']=='successful':
        print ':) Successfully disconnected from Pictorria.'
    else:
        print ':( Error in shutting down, Pictorria might think you are still serving.'
        return False


def main():
    result = init()
    if result == 'error':
        return
    global stats_requests
    stats_requests_pre = -1
    while True:
        #critical error -> print critical error, stop
        #if stats_requests != stats_requests_pre:
        #    print 'Processed '+ str(stats_requests) + ' pictures!'
        #    stats_requests_pre = stats_requests
        time.sleep(1)
        
if __name__ == '__main__':
    try:
        main()
    except (KeyboardInterrupt, SystemExit):
        print 'Shutting down the service'
        send_shut_down_signal()
        global httpd
        httpd.shutdown()


