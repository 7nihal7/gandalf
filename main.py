'''
(Synchronized) Gandalf gif over network, with music!
Run as: python main.py [mode]
Where mode is:
0: Transmit mode (run only one instance over the network with mode 0)
1(or no mode specified): Receiver mode

The receiver will not play music nor show gif unless sync packets are received
and will promptly stop if sync packets stop arriving

Requirements:
cv2 (OpenCV) - for window and loading video/gif
sounddevice/soundfile - play and load audio


While the video/gif is playing:
press 'q' or <escape> to exit
press 'f' to toggle fullscreen
press 'm' on Transmitting instance to mute all instances

Usage:
First make sure you have permission to do this! This may be
amusing, but can land you into trouble. I am not responsible for this!

Find pc's in one network (works only on PCs on same LAN, may work outside with some tweekings)

Install requirements on all pc's on the network

run "python main.py" on all but one pc
(Allow firewall if your OS asks)

finally, run "python main.py 0" and enjoy the show!

'''

import socket
import struct
import sys
import time

#External dependencies
import cv2
import sounddevice
import soundfile

AUD_SYNC_MILLIS = 250
DEFAULT_FULLSCREEN = True
RECV_MUSIC_TIMEOUT = 500

MAX_BUFFER_SIZE = 65507
AUD_BUFFER_SIZE = 4096
VID_SYNC_HEADER = b"\x00\x00\x01"
AUD_SYNC_HEADER = b"\x00\x00\x02"

BROADCAST_GROUP = "239.192.1.100"
BROADCAST_PORT = 50000

isWindowShowing = False
audioData = b''
posit = 0
sock = None
musicPlay = False
allFrames = []
frameIdx = 0
wndIsFS = False

if len(sys.argv) is 1:
    mode = 1
else:
    mode = sys.argv[1]
    try:
        mode = int(mode)
    except:
        pass

if mode is not 1 and mode is not 0:
    print("Mode argument not correct:", mode, ", setting as 1")
    mode = 1


#Milliseconds wrapper
millis = lambda: int(time.time()*1000)

def setFullscreen(isFullscreen):
    global wndIsFS
    wndIsFS = isFullscreen
    cv2.setWindowProperty("Output", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN if isFullscreen else cv2.WINDOW_NORMAL)

def showImg(image):
    global isWindowShowing
    
    if not isWindowShowing:
        cv2.namedWindow("Output", cv2.WND_PROP_FULLSCREEN)          
        setFullscreen(DEFAULT_FULLSCREEN)
        isWindowShowing = True
    
    cv2.imshow("Output", image)

#Audio playback callback
def callback(outdata, frames, time, status):
    global posit, audioData, sock, musicPlay
    assert frames == AUD_BUFFER_SIZE
    
    if status.output_underflow:
        print('Output underflow: increase blocksize?', file=sys.stderr)
        raise sounddevice.CallbackAbort
    assert not status
    
    data = audioData[posit:posit+len(outdata)]
    posit += len(outdata)
    if posit>=len(audioData):
        posit = 0
    
    if musicPlay:
        if len(data) < len(outdata):
            outdata[:len(data)] = data
            outdata[len(data):] = audioData[:len(outdata) - len(data)]
            posit += len(outdata) - len(data)
        else:
            outdata[:] = data
    else:
        outdata[:] = b'\x00'*len(outdata)

def loadMusic(sndFile):
    global audioData
    with soundfile.SoundFile(sndFile) as f:
        while True:
            data = f.buffer_read(AUD_BUFFER_SIZE*1024, dtype='float32')
            if not data:
                break
            audioData += data[:]

def initSStream():
    stream = sounddevice.RawOutputStream(
        samplerate=44100, blocksize=AUD_BUFFER_SIZE,
        channels=2, dtype='float32',
        callback=callback)
    stream.start()


#======== MAIN ========
if __name__ == "__main__":
    #Load music into memory
    loadMusic("epicsaxguy.wav")
    
    #Create Sound Stream to play (with callback)
    initSStream()
    
    
    #====Load video into memory====
    cap = cv2.VideoCapture('gandalf.gif')
    
    #FPS
    vid_fps = cap.get(cv2.CAP_PROP_FPS)
    
    while True:
        ret, frame = cap.read()
        
        if not ret:
            break
        
        allFrames.append(frame)
    
    cap.release()
    #====Done video load====
    
    
    #TX or RX
    if mode == 0:
        print("--------Transmitting--------")
        
        #Broadcast Socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 20)
        
        #Start music!
        musicPlay = True
        
        prevMillis = millis()
        
        while True:
            try:
                #Read frame
                image = allFrames[frameIdx]
                
                #Sync video
                if sock is not None:
                    sock.sendto(VID_SYNC_HEADER + struct.pack(">Q", frameIdx), (BROADCAST_GROUP, BROADCAST_PORT))
                
                #Sync audio
                if millis() - prevMillis > AUD_SYNC_MILLIS:
                    if sock is not None and musicPlay:
                        sock.sendto(AUD_SYNC_HEADER + struct.pack(">Q", posit), (BROADCAST_GROUP, BROADCAST_PORT))

                    prevMillis = millis()
                
                #Show frame
                showImg(image)
                
                #Next frame
                frameIdx += 1
                if frameIdx >= len(allFrames):
                    frameIdx = 0
                
                #Delay
                keyIn = cv2.waitKey(int(1000/vid_fps))
                if keyIn==27 or keyIn == ord('q') or keyIn == ord('Q'):
                    break
                if keyIn == ord("m") or keyIn == ord("M"):
                    musicPlay = not musicPlay
                if keyIn == ord("f") or keyIn == ord("F"):
                    setFullscreen(not wndIsFS)
                    
            except Exception as e:
                isWindowShowing = False
                cv2.destroyAllWindows()
                print(e)
                break
        
        isWindowShowing = False
        cv2.destroyAllWindows()
        
        sock.close()
    elif mode == 1:
        print("--------Receiving--------")
        
        #Multicast receiver socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except AttributeError:
            pass

        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_IP, socket.IP_MULTICAST_TTL, 20)
        sock.setsockopt(socket.SOL_IP, socket.IP_MULTICAST_LOOP, 1)
        sock.bind(('', BROADCAST_PORT))
        
        #Join Multicast Group
        group = socket.inet_aton(BROADCAST_GROUP)
        mreq = struct.pack('4sL', group, socket.INADDR_ANY)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        
        #Recv timeout
        sock.settimeout(RECV_MUSIC_TIMEOUT/1000.0)
        
        prevMillis = millis()
        
        while True:
            try:
                data, ip_from = sock.recvfrom(MAX_BUFFER_SIZE)
                
                if data[0:3] == VID_SYNC_HEADER:
                    frameIdx = struct.unpack(">Q", data[3:11])[0]
                elif data[0:3] == AUD_SYNC_HEADER:
                    musicPlay = True
                    prevMillis = millis()
                    posit = struct.unpack(">Q", data[3:11])[0]
                
                if millis() - prevMillis > RECV_MUSIC_TIMEOUT:
                    musicPlay = False
                    prevMillis = millis()
                
                showImg(allFrames[frameIdx])
            except socket.timeout:
                musicPlay = False
                isWindowShowing = False
                cv2.destroyAllWindows()
            
            keyIn = cv2.waitKey(16)
            if keyIn==27 or keyIn == ord('q'):
                break
            if keyIn == ord("f") or keyIn == ord("F"):
                setFullscreen(not wndIsFS)
        
        musicPlay = False
        isWindowShowing = False
        cv2.destroyAllWindows()
        sock.close()