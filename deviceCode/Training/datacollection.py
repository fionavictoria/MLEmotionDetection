import math
import sys
import time
import json
import argparse
import threading
from uuid import uuid4
from grove.adc import ADC
from datetime import datetime
from datetime import timedelta
from awscrt import io, mqtt, auth, http
from awsiot import mqtt_connection_builder

parser = argparse.ArgumentParser(description="Send and receive messages through and MQTT connection.")
parser.add_argument('--endpoint', default = "a2j2jl42nz3mit-ats.iot.us-west-2.amazonaws.com", help="Your AWS IoT custom endpoint, not including a port")
parser.add_argument('--port', type=int, help="Specify port. AWS IoT supports 443 and 8883.")
parser.add_argument('--cert', default="/home/pi/Desktop/Iot_Project/certs/certificate.pem.crt", help="File path to your client certificate, in PEM format.")
parser.add_argument('--key', default = "/home/pi/Desktop/Iot_Project/certs/private.pem.key", help="File path to your private key, in PEM format.")
parser.add_argument('--root-ca', default = "/home/pi/Desktop/Iot_Project/certs/AmazonRootCA1.pem", help="File path to root certificate authority, in PEM format")
parser.add_argument('--client-id', default="iot-sensor", help="Client ID for MQTT connection.")
parser.add_argument('--topic', default="iotsensors/train", help="Topic to subscribe to, and publish messages to.")
parser.add_argument('--use-websocket', default=False, action='store_true',
    help="To use a websocket instead of raw mqtt. If you " +
    "specify this option you must specify a region for signing.")
parser.add_argument('--signing-region', default='us-east-1', help="If you specify --use-web-socket, this " +
    "is the region that will be used for computing the Sigv4 signature")
parser.add_argument('--proxy-host', help="Hostname of proxy to connect to.")
parser.add_argument('--proxy-port', type=int, default=8080, help="Port of proxy to connect to.")
parser.add_argument('--verbosity', choices=[x.name for x in io.LogLevel], default=io.LogLevel.NoLogs.name,
    help='Logging level')

# Using globals to simplify sample code
args = parser.parse_args()

io.init_logging(getattr(io.LogLevel, args.verbosity), 'stderr')

received_count = 0
received_all_event = threading.Event()

rate = [0]*10
amp = 100
GAIN = 2/3
curState = 0
stateChanged = 0


# Callback when connection is accidentally lost.
def on_connection_interrupted(connection, error, **kwargs):
    print("Connection interrupted. error: {}".format(error))


# Callback when an interrupted connection is re-established.
def on_connection_resumed(connection, return_code, session_present, **kwargs):
    print("Connection resumed. return_code: {} session_present: {}".format(return_code, session_present))

    if return_code == mqtt.ConnectReturnCode.ACCEPTED and not session_present:
        print("Session did not persist. Resubscribing to existing topics...")
        resubscribe_future, _ = connection.resubscribe_existing_topics()

        # Cannot synchronously wait for resubscribe result because we're on the connection's event-loop thread,
        # evaluate result with a callback instead.
        resubscribe_future.add_done_callback(on_resubscribe_complete)


def on_resubscribe_complete(resubscribe_future):
        resubscribe_results = resubscribe_future.result()
        print("Resubscribe results: {}".format(resubscribe_results))

        for topic, qos in resubscribe_results['topics']:
            if qos is None:
                sys.exit("Server rejected resubscribe to topic: {}".format(topic))


# Callback when the subscribed topic receives a message
def on_message_received(topic, payload, dup, qos, retain, **kwargs):
    print("Received message from topic '{}': {}".format(topic, payload))
    global received_count
    received_count += 1
    if received_count == args.count:
        received_all_event.set()

def read_sensor():
    firstBeat = True
    secondBeat = False
    sampleCounter = 0
    lastBeatTime = 0
    lastTime = int(time.time()*1000)
    threshold = 525 #threshold a little above the trough
    P = 512 #peak at 1/2 the input range of 0..1023
    T = 512 #trough at 1/2 the input range.
    IBI = 600 #600ms per beat = 100 Beats Per Minute (BPM)
    Pulse = False
    adc = ADC()
    while True:

        # Read Heart rate sensor's raw data from Analog port 4 Of Raspberry pi
        # Grove base hat

        Signal = adc.read(4)
        curTime = int(time.time()*1000)
        sampleCounter += curTime - lastTime
        lastTime = curTime
        N = sampleCounter - lastBeatTime

        if Signal > threshold and  Signal > P:
            P = Signal

        if Signal < threshold and N > (IBI/5.0)*3.0 :
            if Signal < T :
              T = Signal

        if N > 250 :
            if  (Signal > threshold) and  (Pulse == False) and  (N > (IBI/5.0)*3.0)  :
              Pulse = 1;
              IBI = sampleCounter - lastBeatTime #keep track of the time in mS with this variable
              lastBeatTime = sampleCounter  #monitor the time since the last beat to avoid noise

              if secondBeat : #not yet looking for the second beat in a row
                secondBeat = 0;
                for i in range(0,10):
                  rate[i] = IBI

              if firstBeat : #looking for the first beat
                firstBeat = 0
                secondBeat = 1
                continue

              runningTotal = 0;
              for i in range(0,9):
                rate[i] = rate[i+1]
                runningTotal += rate[i]

              rate[9] = IBI;
              runningTotal += rate[9]
              runningTotal /= 10;
              BPM = 60000/runningTotal #60,000 milliseconds in a minute
              #how many beats can fit into a minute? that's BPM!

              print("runningTotal",runningTotal)
              resistance = adc.read(0)
              conductance = (1/float(resistance)) * 1000000
              print('GSR: {0}'.format(conductance))
              print('BPM: {}'.format(BPM))
              print("-------------")
              from datetime import datetime
              now = datetime.now()
              current_date =now.strftime("%m/%d/%Y")
              current_time = now.strftime("%H:%M:%S")

              # Video stimuli to collected sensor Data
              # Data is tagged with the appropriate emotion of the individual

              message = {"GSR": conductance+1000, "BPM": BPM, "Mood": "Happy", "Date": current_date, "Time": current_time}

              # publish message to "iotsensors/train" topic

              message_json = json.dumps(message)
              mqtt_connection.publish(
                  topic=args.topic,
                  payload=message_json,
                  qos=mqtt.QoS.AT_LEAST_ONCE)

        if Signal < threshold and Pulse == 1 :
            amp = P - T
            threshold = amp/2 + T
            T = threshold
            P = threshold
            Pulse = 0


        if N > 2500 :
            threshold = 512
            T = threshold
            P = threshold
            lastBeatTime = sampleCounter
            firstBeat = 0
            secondBeat = 0
            print("no beats found")


        time.sleep(0.005) #5 milliseconds #200hz

if __name__ == '__main__':
    # Spin up resources
    event_loop_group = io.EventLoopGroup(1)
    host_resolver = io.DefaultHostResolver(event_loop_group)
    client_bootstrap = io.ClientBootstrap(event_loop_group, host_resolver)

    proxy_options = None
    if (args.proxy_host):
        proxy_options = http.HttpProxyOptions(host_name=args.proxy_host, port=args.proxy_port)

    if args.use_websocket == True:
        credentials_provider = auth.AwsCredentialsProvider.new_default_chain(client_bootstrap)
        mqtt_connection = mqtt_connection_builder.websockets_with_default_aws_signing(
            endpoint=args.endpoint,
            client_bootstrap=client_bootstrap,
            region=args.signing_region,
            credentials_provider=credentials_provider,
            http_proxy_options=proxy_options,
            ca_filepath=args.root_ca,
            on_connection_interrupted=on_connection_interrupted,
            on_connection_resumed=on_connection_resumed,
            client_id=args.client_id,
            clean_session=False,
            keep_alive_secs=30)

    else:
        mqtt_connection = mqtt_connection_builder.mtls_from_path(
            endpoint=args.endpoint,
            port=args.port,
            cert_filepath=args.cert,
            pri_key_filepath=args.key,
            client_bootstrap=client_bootstrap,
            ca_filepath=args.root_ca,
            on_connection_interrupted=on_connection_interrupted,
            on_connection_resumed=on_connection_resumed,
            client_id=args.client_id,
            clean_session=False,
            keep_alive_secs=30,
            http_proxy_options=proxy_options)

    print("Connecting to {} with client ID '{}'...".format(
        args.endpoint, args.client_id))

    connect_future = mqtt_connection.connect()

    connect_future.result()
    print("Connected!")

    # Subscribe
    print("Subscribing to topic '{}'...".format(args.topic))
    subscribe_future, packet_id = mqtt_connection.subscribe(
        topic=args.topic,
        qos=mqtt.QoS.AT_LEAST_ONCE,
        callback=on_message_received)

    subscribe_result = subscribe_future.result()
    print("Subscribed with {}".format(str(subscribe_result['qos'])))

    read_sensor()
