"""Build week-27/lab.ipynb — Production pipelines: S3 → Lambda → EventBridge."""
import json
from pathlib import Path
def md(t):
    L=[l+"\n" for l in t.split("\n")]
    if L: L[-1]=L[-1].rstrip("\n")
    return {"cell_type":"markdown","metadata":{},"source":L}
def code(t):
    L=[l+"\n" for l in t.split("\n")]
    if L: L[-1]=L[-1].rstrip("\n")
    return {"cell_type":"code","execution_count":None,"metadata":{},"outputs":[],"source":L}
cells=[]
cells.append(md(
"""# Week 27: Production pipelines — S3 → Lambda → EventBridge

**Track:** Space GIS Architect (Expert)
**Full primer + quiz:** [https://launchdetect.com/academy/week/27/](https://launchdetect.com/academy/week/27/)

---

_The notebook code you've written through Week 26 is **a detection function**. Production wraps that function in three layers: **event-driven triggers** (so it runs the instant new data lands), **observability** (so failures don't silently lose detections), and **fan-out** (so downstream services like push notifications and the dashboard get the result). This week walks the canonical AWS shape — **S3 → Lambda → EventBridge → SNS/SQS/HTTP** — and shows how to express it as Infrastructure-as-Code (CDK)._
"""))

cells.append(md("""## The reference architecture

```
NOAA s3://noaa-goes18 (new Band-7 NetCDF arrives, ~every 5 min)
       │  S3 event notification
       ▼
AWS EventBridge (cross-account event bus, NOAA → us)
       │
       ▼
AWS Lambda detector       ← runs your Week-30 pipeline
       │
       ├─→ EventBridge (custom bus)
       │      ├─→ SNS topic → APNs/FCM push (mobile alert)
       │      ├─→ SQS queue → batch enrichment Lambda
       │      └─→ HTTP API destination → STM dashboard live feed
       ▼
DynamoDB (detection ledger, GSI by lat-lon-time)
```

**Why event-driven**: zero polling cost, latency from satellite scan to user push is < 30 seconds. **Why EventBridge over direct invocation**: decouples producers from consumers — adding a 4th consumer is a route rule, not a code change to the detector."""))

cells.append(md("""## Setup"""))
cells.append(code("""!pip install -q boto3 moto"""))

cells.append(md("""## Step 1 — Simulate the data flow locally with `moto` (no AWS account needed)

`moto` is a Python library that mocks the AWS APIs in-process. Same boto3 client calls; no network. Lets us prove the pipeline shape works before deploying real infra."""))
cells.append(code(
"""import boto3, json
# moto 5+ exposes a unified `mock_aws`; older 4.x uses per-service decorators.
try:
    from moto import mock_aws
except ImportError:
    # Fallback: chain per-service mocks (DynamoDB, SNS, SQS) — same effect.
    from moto import mock_dynamodb, mock_sns, mock_sqs
    def mock_aws(fn):
        return mock_dynamodb(mock_sns(mock_sqs(fn)))

@mock_aws
def run_pipeline_demo():
    region = 'us-east-1'
    s3  = boto3.client('s3', region_name=region)
    sns = boto3.client('sns', region_name=region)
    sqs = boto3.client('sqs', region_name=region)
    ddb = boto3.client('dynamodb', region_name=region)

    # 1) Create the detection-ledger DynamoDB table
    ddb.create_table(
        TableName='detections',
        AttributeDefinitions=[{'AttributeName':'detection_id','AttributeType':'S'}],
        KeySchema=[{'AttributeName':'detection_id','KeyType':'HASH'}],
        BillingMode='PAY_PER_REQUEST',
    )
    print('[ddb] created table detections')

    # 2) SNS topic + SQS queue for the fan-out side
    topic = sns.create_topic(Name='ld-detections')['TopicArn']
    queue = sqs.create_queue(QueueName='ld-enrich')['QueueUrl']
    qarn = sqs.get_queue_attributes(QueueUrl=queue, AttributeNames=['QueueArn'])['Attributes']['QueueArn']
    sns.subscribe(TopicArn=topic, Protocol='sqs', Endpoint=qarn)
    print(f'[sns] topic ARN: {topic}')
    print(f'[sqs] queue URL: {queue}')

    # 3) Simulate the detector: ingest a 'new scene', emit one detection
    #    (in real prod, S3 Event → Lambda triggers this function)
    new_scene_key = 'ABI-L1b-RadC/2026/133/04/OR_ABI-L1b-RadC-M6C07_G18_s20261330401193.nc'
    print(f'\\n[s3-event] new scene arrived: {new_scene_key}')

    detection = {
        'detection_id': 'det-2026133-040123-cape',
        'scene': new_scene_key,
        'lat': 28.5618, 'lon': -80.5772,
        'bt_K': 412.3, 'confidence': 0.87,
    }
    # 4) Write to detection ledger
    ddb.put_item(TableName='detections', Item={
        'detection_id': {'S': detection['detection_id']},
        'lat': {'N': str(detection['lat'])},
        'lon': {'N': str(detection['lon'])},
        'bt_K': {'N': str(detection['bt_K'])},
        'confidence': {'N': str(detection['confidence'])},
    })
    print(f'[ddb] put_item: {detection[\"detection_id\"]}')

    # 5) Fan-out via SNS
    sns.publish(TopicArn=topic, Message=json.dumps(detection), Subject='LD detection')
    print(f'[sns] publish → topic ld-detections')

    # 6) Downstream enrichment Lambda would receive from SQS — we simulate by reading the queue
    msg = sqs.receive_message(QueueUrl=queue, MaxNumberOfMessages=1, WaitTimeSeconds=1)
    if 'Messages' in msg:
        body = json.loads(msg['Messages'][0]['Body'])
        payload = json.loads(body.get('Message', body))
        print(f'\\n[sqs-consumer] dequeued: {payload[\"detection_id\"]}  conf={payload[\"confidence\"]}')

    # 7) Verify in DynamoDB
    rt = ddb.get_item(TableName='detections', Key={'detection_id':{'S':detection['detection_id']}})
    print(f'[ddb] get_item round-trip: lat={rt[\"Item\"][\"lat\"][\"N\"]}, bt_K={rt[\"Item\"][\"bt_K\"][\"N\"]}')

    return detection, rt

result = run_pipeline_demo()
print('\\nFull pipeline executed locally (mocked).')"""))

cells.append(md("""## Step 2 — Express it as CDK (TypeScript reference, what real production looks like)

The notebook simulation above maps to ~120 lines of AWS CDK. Below is the snippet that creates the Lambda + EventBridge rule + DynamoDB table; deploy with `cdk deploy DetectorStack`:

```typescript
import * as cdk from 'aws-cdk-lib';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as events from 'aws-cdk-lib/aws-events';
import * as targets from 'aws-cdk-lib/aws-events-targets';
import * as ddb from 'aws-cdk-lib/aws-dynamodb';
import * as sns from 'aws-cdk-lib/aws-sns';

export class DetectorStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    const ledger = new ddb.Table(this, 'Ledger', {
      tableName: 'detections',
      partitionKey: { name: 'detection_id', type: ddb.AttributeType.STRING },
      billingMode: ddb.BillingMode.PAY_PER_REQUEST,
    });

    const topic = new sns.Topic(this, 'DetectionTopic', { topicName: 'ld-detections' });

    const detector = new lambda.Function(this, 'Detector', {
      runtime: lambda.Runtime.PYTHON_3_11,
      handler: 'index.handler',
      code: lambda.Code.fromAsset('lambda/detector'),
      timeout: cdk.Duration.seconds(60),
      environment: { LEDGER_TABLE: ledger.tableName, TOPIC_ARN: topic.topicArn },
    });
    ledger.grantReadWriteData(detector);
    topic.grantPublish(detector);

    // EventBridge rule: trigger detector on every new GOES-18 Band-7 NetCDF
    new events.Rule(this, 'NewScene', {
      eventPattern: {
        source: ['aws.s3'],
        detailType: ['Object Created'],
        detail: {
          bucket: { name: ['noaa-goes18'] },
          object: { key: [{ prefix: 'ABI-L1b-RadC/' }] },
        },
      },
      targets: [new targets.LambdaFunction(detector)],
    });
  }
}
```
"""))

cells.append(md(
"""## Common gotchas

- **S3 Event Notifications + cross-account.** NOAA's bucket is in their account; you can't add a notification to it. Use **EventBridge Rules in your account** with the `aws.s3 / Object Created` source — works if the producer account has emitted events to the partition-wide bus.
- **Lambda cold-start vs warm-start.** First invocation after idle takes 1-3 s; subsequent < 100 ms. For 5-min cadence, build a provisioned-concurrency pool or accept the cold start; per-launch fast paths use SnapStart.
- **Idempotency.** S3 events can deliver "at least once" — your detector may receive the same scene key twice. Always upsert to DynamoDB on `detection_id` (key derived deterministically from `scene_key + cluster_idx`).
- **EventBridge schema vs payload.** EventBridge events have a tight schema (`source`, `detail-type`, `detail`). Stuff your custom payload in `detail`. Don't reuse fields like `source` for app-level routing.
- **SQS visibility timeout.** When a Lambda consumes an SQS message it has N seconds to ack; if it crashes, the message reappears. Set timeout to ~3× the Lambda's max-runtime expectation. Default 30 s often too short for image-processing Lambdas.
- **CloudWatch costs.** Default-on Lambda logs into CloudWatch can eat budget. Set retention (e.g., 7 days) on the log group at provision time.
"""))

cells.append(md(
"""## Self-check
- [ ] Mocked pipeline ran end-to-end without raising.
- [ ] DynamoDB ledger has the detection record after `put_item`.
- [ ] SQS queue dequeued the SNS message that the detector published.
- [ ] You can map every component in the mocked pipeline to a line in the CDK snippet.
- [ ] Quiz on the [Week 27 page](https://launchdetect.com/academy/week/27/).
"""))

nb={"cells":cells,"metadata":{"kernelspec":{"display_name":"Python 3","language":"python","name":"python3"},"language_info":{"name":"python","version":"3.11"},"colab":{"provenance":[]}},"nbformat":4,"nbformat_minor":5}
Path(__file__).parent.joinpath("lab.ipynb").write_text(json.dumps(nb,indent=1,ensure_ascii=False)+"\n",encoding="utf-8")
print(f"Wrote week-27/lab.ipynb ({len(cells)} cells)")
