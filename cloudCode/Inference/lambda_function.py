import os
import json
import boto3
import urllib
import logging

s3_client = boto3.client('s3',
                   aws_access_key_id='aws_access_key_id',
                   aws_secret_access_key='aws_secret_access_key'
                 )
iot_client = boto3.client('iot-data', aws_access_key_id='aws_access_key_id',
                   aws_secret_access_key='aws_secret_access_key',
                  region_name='us-west-2', endpoint_url='ats.iot.us-west-2.amazonaws.com')

def lambda_handler(event, context):
    # Step 1: when new file is upload in s3, lambda function is triggered
    bucket = event['Records'][0]['s3']['bucket']['name']
    key = urllib.parse.unquote_plus(event['Records'][0]['s3']['object']['key'], encoding='utf-8')

    # Step 2: Read the contents of uploaded sensor data file
    content = s3_client.get_object(Bucket=bucket, Key=key)
    text = content["Body"].read().decode()
    text = json.loads(text)
    print(text,type(text))

    emotion = { 0: "Angry",
                1: "Happy",
                2: "Sad"}

    sagemaker_client = boto3.client('sagemaker-runtime')
    gsr = text['GSR']
    bpm = text['BPM']

    sensor_list = [gsr,bpm]
    reportedValues = []
    for i in sensor_list:
        reportedValues.append(str(i))
    input_data = ','.join(reportedValues)

    # Step 3: Invoke sagemaker endpoint
    endpoint_name = os.environ['SAGEMAKER_ENDPOINT']
    content_type = "text/csv"
    accept = "application/json"
    payload = input_data
    response = sagemaker_client.invoke_endpoint(
        EndpointName=endpoint_name,
        ContentType=content_type,
        Accept=accept,
        Body=payload
        )

    # Step 4: Retreive the categorical value from numerical output
    body = response['Body'].read()
    print('received this response from inference endpoint: {}'.format(body))
    result = json.loads(body)['predictions'][0]
    result = result['predicted_label']
    final_result = str(emotion.get(result))
    print(final_result)

    # Step 5: Use the result and retreive appropriate recommendation message from another json file
    content = s3_client.get_object(Bucket="iotproj-inference", Key="output.json")
    text = content["Body"].read().decode('utf-8')
    json_content = json.loads(text)

    if final_result == "Happy":
        message = json_content['Happy']
    elif final_result == "Sad":
        message = json_content['Sad']
    else:
        message = json_content['Angry']

    # Step 6: Publish new message to AWS IoT Core
    topic = 'iotsensors/infer/result'
    iot.publish(
            topic=topic,
            qos=1,
            payload=json.dumps(message, ensure_ascii=False)
        )
        
   # Step 7: Publish message to SNS topic
    arn = "arn:aws:sns:us-west-2:account-id:sns-topic-name"
    sns_client = boto3.client('sns')
    response = sns_client.publish(
        TargetArn=arn,
        Message=str(message),
        MessageStructure='string',
    )

    print("success!")
    return {
            'result': final_result
        }
