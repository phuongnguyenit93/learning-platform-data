# Building an SQS Producer, Consumer, and DLQ Workflow

Amazon Simple Queue Service (Amazon SQS) is a managed message queuing service that enables producers to send work into a queue while consumers process messages independently of arrival rates. Producers do not need to know where consumers run or whether they are online when sending. SQS retains messages for a configured retention period and provides mechanisms for receiving, temporarily hiding, acknowledging deletion, and retrying.

When a consumer repeatedly fails to process a message, that message can consume processing time and stall the main queue. A dead-letter queue (DLQ) isolates failing messages so operations teams can inspect them, diagnose root causes, and decide how to recover. Redrive moves fixed messages from the DLQ back to the queue for reprocessing.

This hands-on lab builds an order processing flow using SQS Standard, Python, and boto3. Learners create the DLQ first, configure a redrive policy on the main queue, send messages with a producer, receive and delete messages with a consumer, intentionally inject a poison message to observe retries/DLQ routing, then fix the defect and redrive the message. All resources are created inside a sandbox AWS account and Region.

## 1. Learning Objectives

After this hands-on lab, learners will be able to:

- Explain the roles of producer, consumer, queue, and message.
- Distinguish SQS Standard and FIFO queues.
- Create queues and DLQs using the AWS CLI.
- Configure `VisibilityTimeout`, long polling, retention, and redrive policies.
- Send messages and message attributes using boto3.
- Receive messages in batches and process them with a consumer.
- Delete messages after successful processing.
- Explain visibility timeout, receipt handle, and approximate receive count.
- Inject a poison message to observe retries and DLQ transfer.
- Inspect messages in a DLQ and read CloudWatch metrics.
- Fix the consumer and redrive messages back to the main queue.
- Design idempotency to tolerate duplicate deliveries.
- Grant IAM permissions following least privilege.
- Clean up queues and identify operational risks.

## 2. Architecture and Processing Flow

In this lab, the producer sends `OrderCreated` events to the `orders` queue. The consumer receives messages, validates the payload, executes processing, and calls `DeleteMessage`. If the consumer encounters an error, it does not delete the message. Once the visibility timeout expires, the message becomes receivable again. When the receive count reaches `maxReceiveCount`, SQS moves the message to the DLQ.

~~~text
+------------------+
| Order Producer   |
| Python / boto3   |
+--------+---------+
         |
         | SendMessage
         v
+------------------+       Redrive policy
| orders queue     |--------------------------+
| SQS Standard     |                          |
+--------+---------+                          |
         |                                    |
         | ReceiveMessage                     |
         v                                    |
+------------------+                          |
| Order Consumer   |                          |
| Python / boto3   |                          |
+--------+---------+                          |
         |                                    |
         +-- Success --> DeleteMessage        |
         |                                    |
         +-- Failure --> No delete            |
                          |                   |
                          | Visibility timeout|
                          | Retry              |
                          +-------------------+
                                              |
                            maxReceiveCount reached
                                              |
                                              v
                                   +------------------+
                                   | orders DLQ       |
                                   | Inspect / Fix    |
                                   +--------+---------+
                                            |
                                            | StartMessageMoveTask
                                            v
                                      orders queue
~~~

Components:

| Component | Role |
|---|---|
| Producer | Creates events and sends messages to the queue |
| Source queue | Stores work waiting to be processed by consumers |
| Consumer | Receives, validates, and processes messages |
| Visibility timeout | Duration during which a received message is hidden from other consumers |
| Receipt handle | Token representing a specific receive attempt, used to delete or change visibility |
| Redrive policy | Defines the DLQ and maximum receive count |
| DLQ | Holds messages that failed processing for investigation |
| Redrive task | Moves messages from the DLQ to a destination queue |

SQS Standard provides at-least-once delivery. A message can be delivered more than once, so consumers must tolerate duplicates. Receiving a message must never be treated as proof that processing succeeded; a message should only be deleted after required side effects have succeeded.

## 3. Environment Preparation

### 3.1 Requirements

Prepare:

- A sandbox AWS account.
- An IAM role/user granted SQS permissions for this lab.
- AWS CLI v2.
- Python 3.10 or later.
- `boto3`.
- PowerShell on Windows or an equivalent shell.
- An approved Region, such as `ap-southeast-1`.

Do not run this lab in a production account. Queues are billed per request and can incur charges if messages or resources remain active long-term.

### 3.2 Signing In with IAM Identity Center

If your organization uses AWS IAM Identity Center, configure an SSO profile:

~~~powershell
aws configure sso --profile sandbox
aws sso login --profile sandbox
aws sts get-caller-identity --profile sandbox
~~~

Verify the returned account ID and ARN match the sandbox account. Do not use root access keys or embed access keys in source code.

If your organization grants access via another mechanism, use the profile configured per internal guidelines.

### 3.3 Creating a Python Virtual Environment

In the lab working directory:

~~~powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install boto3
~~~

Set environment variables for profile, Region, and queue URL after creating the queue:

~~~powershell
$env:AWS_PROFILE = "sandbox"
$env:AWS_REGION = "ap-southeast-1"
~~~

Verify boto3 picks up the right identity:

~~~powershell
python -c "import boto3; print(boto3.Session().region_name)"
aws sts get-caller-identity --profile $env:AWS_PROFILE
~~~

If PowerShell blocks the activate script, invoke Python via `.\.venv\Scripts\python.exe` or adjust execution policy per machine policy. Never relax policies on shared machines solely to run a lab.

## 4. Choosing the Queue Type

SQS has two primary queue types:

| Criterion | Standard | FIFO |
|---|---|---|
| Ordering | Best-effort ordering | Preserves ordering within each `MessageGroupId` |
| Throughput | High, automatically scales | Depends on throughput mode and message groups |
| Duplicates | Can occur | Deduplication within the supported interval; consumers should still be idempotent |
| Queue name | Regular name | Ends with `.fifo` |
| DLQ | Standard DLQ | FIFO DLQ |
| Best suited for | Events, independent tasks, parallel processing | Workflows requiring per-group ordering |

This lab uses a Standard queue because order events are processed independently. If business logic requires ordering per customer or per order, FIFO may fit better. When using FIFO, select `MessageGroupId` to define ordering scope and account for DLQ impact on processing order: moving a message to a DLQ can interrupt original business ordering.

## 5. Understanding Key Attributes

### 5.1 Visibility Timeout

When a consumer receives a message, SQS does not delete it. It marks the message invisible for the `VisibilityTimeout` duration. During this window, other consumers cannot see that message through normal receive calls.

- If processing succeeds, the consumer calls `DeleteMessage`.
- If the consumer fails or exits before deleting, the message becomes visible again after the timeout expires.
- If processing takes longer than the timeout, another consumer can receive the message while the first consumer is still working.
- `ChangeMessageVisibility` can be called to extend or shorten the hidden duration.

Choose a timeout longer than expected processing time and the SDK read timeout. For variable-duration tasks, consumers can extend visibility via heartbeats. Maximum visibility timeout is 12 hours per receive; longer work should be broken into smaller steps or orchestrated with an appropriate workflow service.

### 5.2 Long Polling

Long polling allows SQS to wait for messages to arrive before returning a response. `WaitTimeSeconds` accepts values from 1 to 20 seconds; this lab uses 20 seconds to reduce empty responses and unnecessary requests.

When using long polling, the SDK's HTTP read timeout must exceed `WaitTimeSeconds`. Boto3's default read timeout is long enough for this example; if customizing client config, double-check it.

### 5.3 Retention Period

Message retention period is how long SQS retains undeleted messages. Configurable range is 1 minute to 14 days. This lab sets the source queue to 4 days and the DLQ to 14 days.

With Standard queues, the original enqueue timestamp is preserved when a message moves to a DLQ. Time spent in the source queue counts toward the DLQ retention period. The `ApproximateAgeOfOldestMessage` metric on a DLQ reflects when the message entered the DLQ, whereas expiration still relies on the original enqueue timestamp. Therefore, configure DLQ retention longer than source queue retention to allow sufficient investigation time.

### 5.4 Redrive Policy and maxReceiveCount

A redrive policy links a source queue to a DLQ. `maxReceiveCount` defines how many times a consumer can receive a message without deleting it before SQS moves it to the DLQ.

This lab sets `maxReceiveCount = 3` for fast observation. That is an illustrative value; production requires choosing thresholds based on failure modes, retry duration, SLAs, and cost. When using Lambda event source mappings, AWS recommends `maxReceiveCount` of at least 5 to allow adequate function retries.

## 6. Creating the DLQ First

The DLQ must exist before attaching it to a source queue. The DLQ and source queue must share the same AWS account, Region, and queue type.

Set PowerShell environment variables:

~~~powershell
$Region = "ap-southeast-1"
$Profile = "sandbox"
$Suffix = Get-Date -Format "yyyyMMddHHmmss"
$DlqName = "orders-dlq-lab-$Suffix"
$SourceName = "orders-lab-$Suffix"
~~~

Create a Standard DLQ with 14-day retention and 20-second long polling:

~~~powershell
$DlqUrl = aws sqs create-queue --queue-name $DlqName --attributes '{"MessageRetentionPeriod":"1209600","ReceiveMessageWaitTimeSeconds":"20"}' --query QueueUrl --output text --region $Region --profile $Profile
~~~

Retrieve the DLQ ARN:

~~~powershell
$DlqArn = aws sqs get-queue-attributes --queue-url $DlqUrl --attribute-names QueueArn --query "Attributes.QueueArn" --output text --region $Region --profile $Profile
~~~

Verify URL and ARN:

~~~powershell
$DlqUrl
$DlqArn
~~~

If the queue name already exists or the create call errors, check account, Region, and previously existing queues. Do not delete a queue used by another workload just to rerun the lab.

## 7. Creating the Source Queue and Configuring the Redrive Policy

Create the redrive policy using the ARN retrieved above:

~~~powershell
$RedrivePolicy = @{ deadLetterTargetArn = $DlqArn; maxReceiveCount = "3" } | ConvertTo-Json -Compress
$QueueAttributes = @{ VisibilityTimeout = "30"; ReceiveMessageWaitTimeSeconds = "20"; MessageRetentionPeriod = "345600"; RedrivePolicy = $RedrivePolicy } | ConvertTo-Json -Compress
$SourceUrl = aws sqs create-queue --queue-name $SourceName --attributes $QueueAttributes --query QueueUrl --output text --region $Region --profile $Profile
~~~

Explanation:

| Attribute | Value | Meaning |
|---|---:|---|
| VisibilityTimeout | 30 seconds | Message hidden after being received |
| ReceiveMessageWaitTimeSeconds | 20 seconds | Enables long polling |
| MessageRetentionPeriod | 345600 seconds | Retains messages for 4 days |
| RedrivePolicy.maxReceiveCount | 3 | Receive attempts before moving to DLQ |
| RedrivePolicy.deadLetterTargetArn | DLQ ARN | Destination for failed messages |

Retrieve the source queue ARN:

~~~powershell
$SourceArn = aws sqs get-queue-attributes --queue-url $SourceUrl --attribute-names QueueArn --query "Attributes.QueueArn" --output text --region $Region --profile $Profile
~~~

Set environment variables so Python scripts use the queue URL:

~~~powershell
$env:SQS_QUEUE_URL = $SourceUrl
$env:AWS_PROFILE = $Profile
$env:AWS_REGION = $Region
~~~

Verify attributes:

~~~powershell
aws sqs get-queue-attributes --queue-url $SourceUrl --attribute-names All --region $Region --profile $Profile
~~~

Verify `RedrivePolicy` points to the right DLQ ARN and `maxReceiveCount` is 3. Verify the DLQ has longer retention than the source queue.

SQS provides `RedriveAllowPolicy` to restrict which queues may use a DLQ. By default, a DLQ allows source queues in the same account/Region. In production, consider a `byQueue` policy permitting only designated source queues; this mode supports up to 10 source queue ARNs. Do not configure `denyAll` on an active DLQ.

## 8. Granting Role-Based IAM Permissions

Producers and consumers do not need SQS administrative permissions. Separate permissions by responsibility:

| Principal | Required Permissions | Resource |
|---|---|---|
| Queue provisioner | `sqs:CreateQueue`, `sqs:GetQueueAttributes`, `sqs:SetQueueAttributes`, `sqs:GetQueueUrl`, `sqs:TagQueue`, `sqs:DeleteQueue` | Both lab queues |
| Producer | `sqs:SendMessage` | Source queue |
| Consumer | `sqs:ReceiveMessage`, `sqs:DeleteMessage`, `sqs:ChangeMessageVisibility`, `sqs:GetQueueAttributes` | Source queue |
| DLQ operator | `sqs:ReceiveMessage`, `sqs:GetQueueAttributes` | DLQ |
| Redrive operator | `sqs:StartMessageMoveTask`, `sqs:ListMessageMoveTasks`, `sqs:ReceiveMessage`, `sqs:DeleteMessage`, `sqs:GetQueueAttributes` on DLQ and `sqs:SendMessage` on destination queue | DLQ and source queue |

Abbreviated example policy for producer and consumer:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "SendOrderEvents",
      "Effect": "Allow",
      "Action": [
        "sqs:SendMessage"
      ],
      "Resource": "arn:aws:sqs:ap-southeast-1:123456789012:orders-lab-REPLACE"
    },
    {
      "Sid": "ConsumeOrderEvents",
      "Effect": "Allow",
      "Action": [
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:ChangeMessageVisibility",
        "sqs:GetQueueAttributes"
      ],
      "Resource": "arn:aws:sqs:ap-southeast-1:123456789012:orders-lab-REPLACE"
    }
  ]
}
~~~

Replace account ID, Region, and queue name with the real ARN. This combined policy illustrates both action groups; when granting real permissions, split into two separate policies/roles so the producer only has `SendMessage` and the consumer only has the required receive/delete/visibility permissions.

For redrive, AWS requires permissions to start move tasks and receive/delete/read attributes on the DLQ; the destination queue requires `sqs:SendMessage`. If queues are encrypted with AWS KMS, redrive may require `kms:Decrypt` on the source key and `kms:GenerateDataKey`/`kms:Decrypt` on the destination key depending on configuration.

## 9. Creating the Producer with Python and boto3

The producer constructs JSON events and sends them to the source queue. Each event has a unique `eventId` for consumers to use as an idempotency key in real systems.

Create `producer.py`:

~~~python
import argparse
import json
import os
import uuid
from datetime import datetime, timezone

import boto3


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument(
        "--poison",
        action="store_true",
        help="Send one event that the initial consumer will reject",
    )
    args = parser.parse_args()

    if args.count < 1:
        parser.error("--count must be at least 1")

    session = boto3.Session(
        profile_name=os.getenv("AWS_PROFILE"),
        region_name=os.getenv("AWS_REGION", "ap-southeast-1"),
    )
    sqs = session.client("sqs")
    queue_url = os.environ["SQS_QUEUE_URL"]

    for index in range(args.count):
        event = {
            "eventId": str(uuid.uuid4()),
            "eventType": "OrderCreated",
            "orderId": f"ORD-{uuid.uuid4().hex[:12].upper()}",
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "simulateFailure": bool(args.poison and index == 0),
        }

        response = sqs.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(event, separators=(",", ":")),
            MessageAttributes={
                "eventType": {
                    "DataType": "String",
                    "StringValue": "OrderCreated",
                }
            },
        )

        print(
            f"Sent orderId={event['orderId']} "
            f"eventId={event['eventId']} "
            f"messageId={response['MessageId']}"
        )


if __name__ == "__main__":
    main()
~~~

Run the producer to send 5 normal messages:

~~~powershell
python producer.py --count 5
~~~

Send one poison message:

~~~powershell
python producer.py --count 1 --poison
~~~

The producer does not process messages after sending. The `SendMessage` response includes the SQS-assigned `MessageId` and `MD5OfMessageBody`/related checksums depending on the response. `MessageId` is SQS's identifier for the message; `eventId` is the application-generated business ID and should remain stable if the event is replayed.

## 10. Creating the Consumer with Python and boto3

The consumer uses long polling to wait for messages. When processing succeeds, the consumer calls `DeleteMessage` using the current receive's `ReceiptHandle`. If processing fails—such as with a poison message—the consumer does not delete the message.

Create `consumer.py`:

~~~python
import argparse
import json
import os

import boto3


def process_order(event, fix_poison=False):
    if event.get("simulateFailure") and not fix_poison:
        raise ValueError("Simulated poison message: unsupported order payload")

    # Lab handler: replace this print with the real business operation.
    # In production, persist eventId as an idempotency key before acknowledging.
    print(
        f"Processed orderId={event.get('orderId')} "
        f"eventId={event.get('eventId')}"
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fix-poison",
        action="store_true",
        help="Simulate a deployed handler fix for the lab poison event",
    )
    args = parser.parse_args()

    session = boto3.Session(
        profile_name=os.getenv("AWS_PROFILE"),
        region_name=os.getenv("AWS_REGION", "ap-southeast-1"),
    )
    sqs = session.client("sqs")
    queue_url = os.environ["SQS_QUEUE_URL"]

    print("Consumer started. Press Ctrl+C to stop.")

    while True:
        response = sqs.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=10,
            WaitTimeSeconds=20,
            VisibilityTimeout=30,
            MessageSystemAttributeNames=["ApproximateReceiveCount"],
            MessageAttributeNames=["All"],
        )

        messages = response.get("Messages", [])
        if not messages:
            print("No visible messages; waiting...")
            continue

        for message in messages:
            receipt_handle = message["ReceiptHandle"]
            receive_count = message.get("Attributes", {}).get(
                "ApproximateReceiveCount", "unknown"
            )

            try:
                event = json.loads(message["Body"])
                print(
                    f"Received messageId={message['MessageId']} "
                    f"receiveCount={receive_count}"
                )

                process_order(event, fix_poison=args.fix_poison)

                # Acknowledge only after the business operation succeeds.
                sqs.delete_message(
                    QueueUrl=queue_url,
                    ReceiptHandle=receipt_handle,
                )
                print(f"Deleted messageId={message['MessageId']}")

            except Exception as error:
                # Deliberately do not delete failed messages.
                # SQS makes them visible again after the visibility timeout.
                print(
                    f"Processing failed for messageId={message['MessageId']}: "
                    f"{error}. Message was not deleted."
                )


if __name__ == "__main__":
    main()
~~~

Run the consumer:

~~~powershell
python consumer.py
~~~

The consumer continues long polling until you press Ctrl+C. When the queue is empty, it waits up to 20 seconds per receive call. In real applications, configure shutdown handling to stop polling for new messages, finish or safely abort in-flight work, and release resources.

## 11. Verifying the Success Flow

With the consumer running:

1. Open a second terminal.
2. Copy the URLs and ARNs printed in the first terminal, then set variables in the second terminal:

~~~powershell
$Region = "ap-southeast-1"
$Profile = "sandbox"
$SourceUrl = "<paste the source queue URL from terminal 1>"
$DlqUrl = "<paste the DLQ URL from terminal 1>"
$SourceArn = "<paste the source queue ARN from terminal 1>"
$DlqArn = "<paste the DLQ ARN from terminal 1>"
$env:AWS_PROFILE = $Profile
$env:AWS_REGION = $Region
$env:SQS_QUEUE_URL = $SourceUrl
~~~

3. Send 5 messages with the producer.
4. Watch the consumer receive and process each event.
5. Confirm the consumer calls `DeleteMessage` after processing.

Check the visible and not-visible message counts:

~~~powershell
aws sqs get-queue-attributes --queue-url $SourceUrl --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible --region $Region --profile $Profile
~~~

These attributes are approximate metrics and may lag slightly. Do not rely on a single read to conclude the queue is strictly empty. Combine consumer logs, CloudWatch metrics, and business processing state.

Expected results:
- Producer prints `MessageId` for each event.
- Consumer prints `orderId` and `eventId`.
- Consumer prints deletion confirmation for each message.
- Visible message count drops to 0 after processing finishes.
- DLQ contains no messages from normal events.

## 12. Injecting a Poison Message and Observing Retries

A poison message is a message that consistently fails consumer processing, such as a malformed schema, invalid field value, or an unresolvable business condition.

Stop the current consumer with Ctrl+C if needed, then send one poison message:

~~~powershell
python producer.py --count 1 --poison
~~~

Start the consumer without `--fix-poison`:

~~~powershell
python consumer.py
~~~

The consumer receives the message with `simulateFailure = true`, throws the simulated exception, and skips `DeleteMessage`. After the 30-second visibility timeout, the message becomes receivable again. `ApproximateReceiveCount` increments across receives; upon reaching the redrive policy threshold, SQS moves the message to the DLQ.

To observe:
- Monitor consumer logs and `ApproximateReceiveCount`.
- Wait for the message to leave the source queue.
- Check the visible message count on the DLQ.
- Verify the source queue no longer holds the poison message in visible state.

Retrieve message counts on the DLQ:

~~~powershell
aws sqs get-queue-attributes --queue-url $DlqUrl --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible --region $Region --profile $Profile
~~~

With a 30-second visibility timeout and a receive threshold of 3, this process can take over a minute because SQS takes time between receive attempts. SQS is distributed, so do not depend on exact second-level timing in this lab.

### 12.1 Why Not Delete Messages on Processing Failure?

If a consumer deletes a message before completing the business operation, the application can lose work. If a consumer fails to delete after successful processing, the message can be redelivered and side effects may repeat.

Key rules:
- Only delete after processing succeeds.
- On transient errors, let the message retry or adjust visibility with backoff.
- On unrecoverable errors, use a DLQ to isolate them.
- Log enough context to diagnose root causes.
- Design idempotency so duplicates do not cause incorrect side effects.

## 13. Inspecting Messages in the DLQ

You can open the Amazon SQS console:
1. Select the correct Region.
2. Open the queue named `orders-dlq-lab-...`.
3. Choose Send and receive messages.
4. Poll for messages to view message bodies and attributes.
5. Note `eventId`, `orderId`, receive count, and the corresponding application error.

Note: Polling a DLQ is itself a message receive. Messages become invisible for the visibility timeout. Before starting a redrive task, wait for the visibility timeout to expire or reset visibility to 0 via a controlled procedure. Do not delete messages from the DLQ before saving investigation details and deciding on a recovery plan.

A DLQ isolates failing messages, but it does not fix payloads or pinpoint root causes on its own. Correlate messages with producer/consumer logs, schema versions, deployment versions, and downstream dependencies called by the consumer.

## 14. Fixing the Defect and Redriving Messages

In this lab, the poison message fails because the consumer intentionally rejects `simulateFailure`. Simulate deploying a fixed handler by running the consumer with `--fix-poison`.

Stop the old consumer. Before redriving:
- Confirm the root cause is fixed.
- Confirm the updated consumer can process the message.
- Verify the main queue has sufficient capacity.
- Verify messages are not currently invisible due to inspection polling.
- Confirm the operator has redrive permissions.

Start the message move task:

~~~powershell
aws sqs start-message-move-task --source-arn $DlqArn --destination-arn $SourceArn --max-number-of-messages-per-second 5 --region $Region --profile $Profile
~~~

SQS redrive is an asynchronous task. Check status:

~~~powershell
aws sqs list-message-move-tasks --source-arn $DlqArn --max-results 10 --region $Region --profile $Profile
~~~

Monitor the task status until completion. Then run the consumer with the fixed handler:

~~~powershell
python consumer.py --fix-poison
~~~

The message is redriven back to the source queue and the updated consumer processes it successfully. Check source queue visible count and DLQ count after the task finishes.

### 14.1 Limitations of Redrive

SQS redrive:
- Moves messages from a DLQ back to its source queue or another destination queue of the same type.
- Supports rate-limiting move velocity to avoid overwhelming consumers.
- Does not support filtering or modifying messages during redrive.
- Resets the retention period for redriven messages.
- Assigns a new `MessageId` and enqueue timestamp after redrive.

If payloads must be modified before replay, do not use direct redrive. An operator can read the message, publish a corrected message to the destination queue keeping the same business `eventId` if appropriate, verify delivery succeeded, and only then delete the old message from the DLQ. Maintain an audit trail to avoid double replays.

## 15. Idempotency and Duplicate Delivery

SQS Standard provides an at-least-once delivery model. In certain scenarios a message can be redelivered even if a consumer received it previously. Examples:
- The consumer finishes processing but crashes before calling `DeleteMessage`.
- `DeleteMessage` fails due to a network error.
- The visibility timeout expires while the consumer is still processing.
- A message is redriven or a producer re-sends the same event.

Production consumers must be idempotent. A common pattern uses the business event ID as an idempotency key and records processed state in a durable database.

Example logic:

~~~text
Receive message
      |
      v
Read eventId
      |
      v
Check idempotency record
      |
      +-- Already processed --> Delete message
      |
      +-- Not processed
              |
              v
       Apply business operation
              |
              v
       Persist result + eventId
              |
              v
       Delete message
~~~

If the business side effect and the idempotency record live in the same database, use a transaction so you never commit the side effect without recording idempotency. If the side effect lives in an external system, design appropriate idempotency keys or reconciliation workflows.

Do not rely solely on SQS `MessageId` to prevent business duplicates. Redrive can assign a new `MessageId`, while the producer-generated `eventId` remains unchanged.

## 16. Visibility Timeout and Long-Running Work

If processing a message takes longer than the visibility timeout, the message can be delivered to another consumer before the first finishes.

Mitigation approaches:
- Set visibility timeout larger than expected processing duration.
- Call `ChangeMessageVisibility` to extend the timeout while processing.
- Use periodic heartbeats to extend visibility.
- Split long tasks into smaller steps.
- Move long-running workflows to Step Functions or an appropriate job engine.

Example extending visibility with boto3:

~~~python
sqs.change_message_visibility(
    QueueUrl=queue_url,
    ReceiptHandle=receipt_handle,
    VisibilityTimeout=120,
)
~~~

This keeps the message invisible for an additional 120 seconds from the API call time. Total visibility duration for a single receive cannot exceed the 12-hour limit. If processing aborts, you can set `VisibilityTimeout = 0` to make the message visible immediately, but only after stopping work and avoiding consumer contention.

`ReceiptHandle` changes on every receive. Always use the latest receipt handle from the current receive when calling `DeleteMessage` or `ChangeMessageVisibility`.

## 17. Monitoring Queues and DLQs with CloudWatch

Amazon SQS integrates with CloudWatch metrics. Key metrics:

| Metric | Meaning | What to Watch |
|---|---|---|
| `ApproximateNumberOfMessagesVisible` | Messages available for receive | Sustained backlog growth |
| `ApproximateNumberOfMessagesNotVisible` | Messages currently in-flight | Slow consumers or missing deletes |
| `ApproximateNumberOfMessagesDelayed` | Messages currently delayed | Delivery delay or message timers |
| `ApproximateAgeOfOldestMessage` | Age of oldest message per queue semantics | Processing SLA breaches |
| `NumberOfMessagesSent` | Messages sent | Producer throughput |
| `NumberOfMessagesReceived` | Message receive calls | Rising retries or duplicates |
| `NumberOfMessagesDeleted` | Message delete calls | Processing completion rate |

Configure an alarm on the DLQ when `ApproximateNumberOfMessagesVisible` exceeds 0. On the source queue, monitor backlog, age of oldest message, and receive/delete ratios. Message count metrics are approximate and may not update immediately after every operation.

### 17.1 Suggested Alert Signals

- DLQ visible count greater than 0.
- `ApproximateAgeOfOldestMessage` breaches SLA.
- Source queue backlog grows continuously.
- Received count climbs sharply while Deleted does not keep pace.
- In-flight message count rises and stays elevated.
- Consumer error rate spikes after deployment.
- Redrive task runs too long or fails to complete.

Do not rely on message counts alone. Correlate application logs, request IDs, `eventId`, queue metrics, and deployment versions to pinpoint root causes.

## 18. SQS Encryption and Message Security

SQS supports server-side encryption. Choose SSE-SQS or SSE-KMS depending on key management and access control needs. With SSE-KMS, producers, consumers, and operators may need corresponding KMS permissions; the KMS key policy must also authorize the appropriate principals.

Principles:
- Use IAM roles for producers and consumers.
- Grant `SendMessage` only to producers.
- Grant `ReceiveMessage`/`DeleteMessage` only to required consumers.
- Separate redrive permissions into an operator or runbook role.
- Scope policies to queue ARNs instead of `Resource: *`.
- Never place passwords, access keys, tokens, or unnecessary sensitive data in message bodies.
- Encrypt data at the application layer when required.
- Use TLS when calling AWS APIs.
- Monitor CloudTrail for queue administration and redrive actions.

When using a DLQ, restrict who can read failed messages. A DLQ may contain sensitive payloads or debug information that should not be visible to all developers.

## 19. Integrating SQS with AWS Lambda

This lab uses a self-polling Python consumer so learners clearly see `ReceiveMessage`, visibility timeout, and `DeleteMessage`. In serverless architectures, Lambda event source mappings let Lambda poll SQS and invoke functions in batches.

Key points to remember:
- The queue and Lambda function must be in the same Region; cross-account is possible with proper permissions.
- The Lambda execution role needs queue read permissions, typically `AWSLambdaSQSQueueExecutionRole`.
- Source queue visibility timeout should be at least 6 times the function timeout.
- If using a batching window, add the batching window duration to the visibility timeout.
- AWS recommends `maxReceiveCount` of at least 5 for Lambda consumers.
- By default, if one message in a batch fails, the entire batch can be retried.
- Use `ReportBatchItemFailures` to return only failed messages when processing batches.
- Lambda event source mappings also exhibit at-least-once behavior; functions must be idempotent.

Do not use the lab's 30-second visibility timeout as a production Lambda default. Calculate it from function timeout, batch size, batching window, and actual processing duration.

## 20. Common Issues and Resolutions

| Symptom | Possible Cause | How to Check |
|---|---|---|
| Producer `AccessDenied` | Missing `sqs:SendMessage` or blocked by queue policy | Check IAM, queue resource policy, and SCPs |
| Consumer receives no messages | Wrong queue URL/Region/profile or messages are invisible | Check `GetQueueAttributes`, caller identity, and in-flight count |
| Consumer receives duplicate messages | At-least-once delivery or failed to delete message | Check receipt handle, `DeleteMessage`, and idempotency |
| Messages return to source queue | Consumer did not delete or visibility timeout expired | Inspect error logs and receive count |
| Messages do not enter DLQ | Misconfigured redrive policy, wrong ARN, or mismatched DLQ type | Inspect `RedrivePolicy`, queue type, and `RedriveAllowPolicy` |
| DLQ stays empty despite consumer errors | Receive count not reached yet or consumer still processing | Monitor `ApproximateReceiveCount` and visibility timeout |
| `DeleteMessage` fails | Stale receipt handle or wrong queue URL | Use the receipt handle from the current receive call |
| Long polling times out | HTTP read timeout shorter than `WaitTimeSeconds` | Increase SDK read timeout above 20 seconds |
| Redrive `AccessDenied` | Missing permissions on DLQ or destination queue | Check `StartMessageMoveTask`, DLQ Receive/Delete/GetAttributes, and destination `SendMessage` |
| Redrive moves nothing | Messages currently invisible, task already running, or mismatched queue type | Wait for visibility timeout, check move tasks, and verify queue types |
| DLQ messages expire early | DLQ retention too short | Set DLQ retention longer than source queue retention |
| Lambda retries whole batch | Partial batch response not enabled | Configure `ReportBatchItemFailures` and update handler |

When encountering `AccessDenied`, identify the principal, action, queue ARN, and Region first. Never grant `sqs:*` across all queues as a temporary workaround before locating the denying policy layer.

## 21. Post-Lab Resource Cleanup

Before deleting:
1. Stop both producer and consumer.
2. Confirm no redrive task is still `RUNNING`.
3. Save any required logs or screenshots.
4. Confirm no messages remain that require investigation.
5. Verify the queues are the exact queues created for this lab.

Delete the source queue first, then delete the DLQ:

~~~powershell
aws sqs delete-queue --queue-url $SourceUrl --region $Region --profile $Profile
aws sqs delete-queue --queue-url $DlqUrl --region $Region --profile $Profile
~~~

Deleting a queue permanently destroys stored messages. Never run these commands against production or shared queue URLs.

After cleanup, revoke temporary IAM permissions if dedicated lab policies were created, and remove unneeded local files or environment variables. If queues were provisioned via IaC in real environments, tear down the stack via the stack owner's workflow rather than deleting resources manually.

## 22. Expected Outcomes and Completion Criteria

The lab is complete when:

- [ ] Signed in to the right sandbox AWS account and Region.
- [ ] Created the DLQ before the source queue.
- [ ] Source queue has a redrive policy pointing to the correct DLQ.
- [ ] Long polling is enabled at 20 seconds.
- [ ] Visibility timeout is configured appropriately for the lab consumer.
- [ ] Producer sent at least 5 normal messages.
- [ ] Consumer received and deleted messages after successful processing.
- [ ] Poison message was received multiple times and routed to the DLQ.
- [ ] Learner inspected the message and receive count in the DLQ.
- [ ] Consumer was fixed and the message was redriven back to the source queue.
- [ ] Updated consumer successfully processed the redriven message.
- [ ] Checked CloudWatch metrics for both the source queue and DLQ.
- [ ] Can explain why consumers must be idempotent.
- [ ] Deleted both queues upon completing the lab.

## 23. Extension Exercises

### Exercise 1: Changing maxReceiveCount

Change `maxReceiveCount` from 3 to 5.

Task: observe receive attempts and time taken before the message moves to the DLQ. Explain why production should not set the threshold too low if transient failures can self-recover.

### Exercise 2: Changing Visibility Timeout

Set visibility timeout to 5 seconds in the lab environment and simulate 10-second processing.

Task: observe duplicate processing with two consumers. Propose an appropriate timeout and show how to use `ChangeMessageVisibility`.

### Exercise 3: Running Two Consumers

Start two consumer processes reading from the same source queue.

Task: observe message distribution and explain why two consumers should not process the same message concurrently under normal conditions, yet must still be idempotent due to at-least-once delivery.

### Exercise 4: Injecting Payload Errors

Modify the producer to send JSON missing `eventId` or with invalid data types.

Task: design validation, error logging, and decide which cases should retry versus route to the DLQ.

### Exercise 5: Manual Redrive Inspection

Send a failing message to the DLQ, fix the payload by publishing a new message to the source queue, and delete the old message after confirmation.

Task: record `eventId`, old/new `MessageId`, and reason for modification. Explain why a redrive task cannot alter message bodies.

### Exercise 6: Switching to FIFO

Create two FIFO queues with names ending in `.fifo`.

Task: configure `FifoQueue`, `MessageGroupId`, `MessageDeduplicationId`, or content-based deduplication. Create a FIFO DLQ and explain ordering implications when a message moves to the DLQ.

### Exercise 7: Lambda Integration

Create a Lambda function reading events from the source queue via an event source mapping.

Task: configure the execution role, minimum visibility timeout based on function timeout, `maxReceiveCount`, and partial batch responses. Verify one failing message does not cause successful messages in the batch to retry unnecessarily.

## 24. Self-Check Questions

1. What are the responsibilities of producer and consumer in the SQS model?
2. Why does a producer not need to know whether a consumer is online?
3. How do Standard queues and FIFO queues differ?
4. What does visibility timeout do after a consumer receives a message?
5. Which operations use a receipt handle?
6. Why must a message be deleted after successful processing?
7. What happens if a consumer errors and does not delete a message?
8. What is the maximum wait time in seconds for long polling?
9. What does `maxReceiveCount` control?
10. Why must the DLQ be created before the source queue?
11. Which properties must the DLQ and source queue share?
12. Why should Standard DLQ retention be longer than source queue retention?
13. What is a poison message?
14. Why can SQS Standard deliver a message more than once?
15. Which event field should an idempotency key be based on?
16. When is `ChangeMessageVisibility` used?
17. Why should a message not be deleted before side effects complete?
18. Can a redrive task edit or filter messages?
19. Why should a message with a new `MessageId` after redrive keep its business `eventId`?
20. Which IAM permissions does a consumer need?
21. Which IAM permissions does a redrive operator need?
22. Which CloudWatch metrics help monitor queue backlog?
23. Why should Lambda/SQS visibility timeout be at least 6 times the function timeout?
24. What problem does partial batch response solve?

Suggested answers:

1. Producer sends events; consumer receives and processes events.
2. The queue stores messages until consumers receive them later.
3. Standard prioritizes throughput and best-effort order; FIFO preserves order per message group.
4. Temporarily hides the message from other consumers.
5. `DeleteMessage` and `ChangeMessageVisibility` for that specific receive.
6. To acknowledge that the message has been processed.
7. The message becomes visible again after the visibility timeout and can be retried.
8. 20 seconds.
9. The number of receives before moving a message to the DLQ.
10. SQS requires the DLQ ARN to exist when configuring a redrive policy.
11. Same account, Region, and queue type.
12. For Standard queues, the original enqueue timestamp is still used to calculate retention after moving to the DLQ.
13. A message that consistently causes errors or cannot be processed successfully.
14. SQS Standard uses at-least-once delivery.
15. A producer-generated business event ID, such as `eventId`.
16. When you need to extend or shorten how long a message stays hidden.
17. Deleting before completion risks losing the message if processing fails.
18. No; redrive only moves messages.
19. To identify the same business event and prevent duplicate processing.
20. `ReceiveMessage`, `DeleteMessage`, `ChangeMessageVisibility`, and `GetQueueAttributes`.
21. `StartMessageMoveTask` and receive/delete/attribute permissions on the DLQ, plus `SendMessage` on the destination.
22. `ApproximateNumberOfMessagesVisible`, `ApproximateAgeOfOldestMessage`, and `ApproximateNumberOfMessagesNotVisible`.
23. To give Lambda time to process batches and retry under throttling.
24. Returns only failed messages instead of retrying the entire batch.

## 25. Official References

- [Amazon SQS Developer Guide](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/welcome.html)
- [Creating an Amazon SQS standard queue](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/creating-sqs-standard-queues.html)
- [Using dead-letter queues in Amazon SQS](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-dead-letter-queues.html)
- [Configuring a dead-letter queue](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-configure-dead-letter-queue.html)
- [Dead-letter queue redrive](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-configure-dead-letter-queue-redrive.html)
- [Setting up long polling](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/best-practices-setting-up-long-polling.html)
- [Configuring visibility timeouts](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/working-with-visibility-timeouts.html)
- [Amazon SQS CloudWatch metrics](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-available-cloudwatch-metrics.html)
- [Amazon SQS security best practices](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-security-best-practices.html)
- [Using Lambda with Amazon SQS](https://docs.aws.amazon.com/lambda/latest/dg/with-sqs.html)
- [Creating and configuring an Amazon SQS event source mapping](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-configure.html)
- [Handling errors for an SQS event source in Lambda](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-errorhandling.html)
- [Boto3 SQS client reference](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/sqs.html)

Timeout, retention, throughput, and quota values must be validated against queue type, Region, and workload. Before production deployment, measure actual processing times and test duplicate delivery, retries, DLQ redrive, encryption, and cleanup in staging.
