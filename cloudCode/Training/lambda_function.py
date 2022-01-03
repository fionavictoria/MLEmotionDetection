iimport json
import boto3
import os
import csv

def lambda_handler(event, context):
    event['GSR'] = round(event['GSR'],3)
    event['BPM'] = round(event['BPM'],3)
    client = boto3.client('firehose')
    response = client.put_record(
           DeliveryStreamName='iotproj_firehose',
           Record={
                'Data': json.dumps(event)
            }
        )
