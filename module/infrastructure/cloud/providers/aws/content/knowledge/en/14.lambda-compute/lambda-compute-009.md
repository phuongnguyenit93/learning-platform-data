# Retries, Destinations, and Dead-Letter Queues

> **Chapter:** Lambda Compute  
> **Module:** CLOUD_PROVIDERS_AWS — explore the AWS ecosystem across Regions/AZs, IAM, VPC, compute, storage, databases, integration, and serverless; learn to design deployments that are secure, observable, resilient, and cost-controlled.

## Learning Objectives

In an **event-driven** system, an **AWS Lambda** invocation can fail due to application bugs, timeouts, missing permissions, unavailable downstream services, or concurrency exhaustion. If handled improperly, the same order can be charged twice, emails can be sent repeatedly, messages can get stuck, or data can vanish once retry windows expire.

Three mechanism groups must be distinguished:

- **Retry:** who decides to retry, how many times, when to stop, and over what time window?
- **Destination:** where Lambda sends an **invocation record** when an asynchronous execution succeeds (`OnSuccess`) or exhausts its processing attempts (`OnFailure`).
- **Dead-letter queue (DLQ):** where unprocessable events/messages are held for investigation and redrive. A **Lambda async invocation** DLQ differs from an **Amazon SQS source queue** DLQ.

After this lesson, you will be able to:

1. Classify **synchronous**, **asynchronous**, and **event source mapping** invocations without misapplying retry policies across sources.
2. Explain default retries for Lambda **asynchronous invocations**, `MaximumRetryAttempts`, and `MaximumEventAgeInSeconds`.
3. Compare **Lambda `OnSuccess`/`OnFailure` destinations**, **Lambda async DLQs**, **SQS redrive policies**, and **stream event source mapping failure destinations**.
4. Read invocation record structures, design IAM/KMS permissions, and protect sensitive data in destinations.
5. Handle **SQS batch failures**, partial batch responses, visibility timeouts, and `maxReceiveCount`.
6. Explain Kinesis/DynamoDB Streams behavior when a **poison-pill record** appears.
7. Design **idempotent** handlers, bounded retries, backoff, observability, and safe **replay** procedures.
8. Use the AWS CLI and CloudWatch to inspect settings, testing mutations or injected failures only on approved sandbox resources.

## 1. Start with the Question: Who Invokes Lambda?

### 1.1. Three Distinct Invocation Mechanisms

| Model | Example sources | Who waits for the result? | Who owns primary retries? |
|---|---|---|---|
| **Synchronous** | API Gateway, ALB, SDK `Invoke(RequestResponse)` | Caller waits for response | **Caller or invoking service** per its own policy; Lambda does not auto-retry function errors asynchronously |
| **Asynchronous** | Amazon S3 event notifications, SNS, EventBridge targets in async mode, SDK `Invoke(Event)` | Caller receives queued acknowledgment | **Lambda async queue** and function/alias/version retry settings |
| **Event source mapping (ESM)** | Amazon SQS, Kinesis, DynamoDB Streams, Kafka | Lambda service polls/batches the source and invokes the function | **Event source mapping mechanics**, source retention/visibility/redrive, and mapping-specific settings |

**Common mistake:** seeing a Lambda reading SQS and setting `MaximumRetryAttempts=0` under **Asynchronous invocation** expecting failed SQS messages to jump straight into a DLQ. In reality, SQS triggers run through an **event source mapping**; messages retry according to the queue's visibility timeout and redrive policy. Depending on the ESM source, retry controls differ too.

### 1.2. Mechanism Selection Diagram

~~~mermaid
flowchart TD
    A[Event to process] --> B{How is Lambda invoked?}
    B -->|Synchronous SDK/API| SY[RequestResponse]
    B -->|Async event| AS[Lambda-managed async event queue]
    B -->|Queue / stream poller| ESM[Event source mapping]
    SY --> C[Caller decides retries]
    AS --> D[Async invocation retries / max age]
    ESM --> E{Source type?}
    E -->|SQS| S[SQS visibility timeout + redrive policy]
    E -->|Kinesis / DynamoDB| K[ESM retries / record age / bisect / destination]
    E -->|Kafka| F[ESM offsets/commits and source failure policy]
    D --> OUT[OnSuccess / OnFailure destination or Lambda DLQ]
    S --> SQDLQ[SQS source queue DLQ]
    K --> KDEST[ESM OnFailure destination where supported]
~~~

This is a **conceptual diagram**. A single system can have **two retry layers**: for instance, EventBridge retries delivering to its target, and once Lambda accepts the async event, Lambda applies its own queue and retries. Never add retry counts across two services mechanically to claim an exact total attempt count.

### 1.3. At Which Layer Did Success Occur?

| Situation | What did the caller receive? | Is business work guaranteed complete? |
|---|---|---|
| `Invoke(Event)` returns **202 Accepted** | Lambda queued the async call for execution | **Not yet**; the handler may not have run yet |
| `Invoke(RequestResponse)` returns HTTP 200 from Lambda API yet payload contains `FunctionError` | Invoke API succeeded at the Lambda transport layer | **No**; the function may have thrown or timed out |
| Handler returns `{"statusCode": 500}` **without throwing** in async mode | Runtime considers the handler to have returned normally | **No**; a business failure is treated as an invocation success |
| SQS batch handler returns success despite one bad message without reporting `batchItemFailures` | Mapping treats the whole batch as succeeded and deletes messages | **No**; business error silently lost |
| Lambda `OnSuccess` destination receives a record | Handler completed per runtime semantics | **Not guaranteed** that end-to-end transactions committed or downstream work finished |

**Lesson:** define “success” using **business invariants**, not merely HTTP status codes or Lambda's `Errors=0` metric.

## 2. Lambda Asynchronous Invocation and Default Retries

### 2.1. Processing Flow

When a source invokes Lambda **asynchronously**, Lambda places the event onto an **internal Lambda-managed queue** and invokes the handler when capacity is available. Callers generally do not wait for the handler to return.

~~~mermaid
sequenceDiagram
    participant P as Event producer
    participant L as Lambda async queue
    participant F as Lambda handler
    participant D as OnFailure destination / DLQ
    P->>L: Invoke asynchronous (Event)
    L-->>P: Accepted (e.g., 202)
    L->>F: Initial invoke
    F-->>L: Function error
    Note over L: Wait ~1 minute (default)
    L->>F: Retry #1
    F-->>L: Function error
    Note over L: Wait ~2 minutes (default)
    L->>F: Retry #2
    F-->>L: Function error
    L->>D: Store event/record if configured
~~~

For **function errors** (handler throws, runtime crash, or timeout), Lambda defaults to **2 retries** after the initial run; per AWS docs, typical wait intervals are **1 minute** and then **2 minutes**. Actual intervals can shift under overload or if the event expires.

### 2.2. Function Errors vs. Throttling/System Errors

| Error category | Examples | Async retry behavior |
|---|---|---|
| **Function error** | Code exception, runtime error, timeout | Default up to **2 retries** beyond initial run; configurable via `MaximumRetryAttempts` |
| **Throttling** | 429 due to concurrency or quota limits | Event returns to async queue and retries with **backoff**, subject to max event age |
| **System error** | 5xx service error in execution/invoke path | Retries per service behavior and event age |
| **Expired event age** | Prolonged backlog or extended retries | Dropped from queue; triggers configured failure sink if enabled |
| **Duplicate events** | Queue eventual consistency, at-least-once delivery | Handler must be **idempotent**, even after prior success |

For throttling/system errors, Lambda retries with exponential backoff starting around 1 second up to roughly **5 minutes**, for **up to 6 hours by default**. Setting max event age bounds queue retention; **`MaximumRetryAttempts`** governs function errors, so never interpret it as “every error type retries at most twice.”

### 2.3. Two Primary Settings

| Property | Scope | Limit per AWS async invoke config | Meaning |
|---|---|---|---|
| `MaximumRetryAttempts` | Function errors on async invocations | **0–2** retry attempts | Number of retries after the first invocation |
| `MaximumEventAgeInSeconds` | Event age in Lambda's async queue | **60–21,600 seconds** (up to 6 hours) | Events older than this are discarded |
| `DestinationConfig.OnFailure` | Async invocation record | Supported destination ARN | Captures metadata/request/response on failure or expiry |
| `DestinationConfig.OnSuccess` | Async invocation record | Supported destination ARN | Sends record when handler completes normally |
| `DeadLetterConfig.TargetArn` | Function async DLQ | SQS/SNS **standard** | Captures discarded raw event payload |

Setting `MaximumRetryAttempts=0` means **do not retry after a function error** — it does not stop Lambda from retrying delivery after throttling or system errors before the event expires.

### 2.4. Example: Choosing Event Age and Retry Count

Suppose a service sends course registration confirmation emails:

- Each event carries `registrationId`.
- Sending email produces an external side effect.
- If the email provider hits a transient outage, bounded retries with backoff help.
- If sending still fails after a limit, retain the record for investigation and replay.

An **illustrative** configuration:

~~~text
MaximumRetryAttempts = 2
MaximumEventAgeInSeconds = 3600 (1 hour)
OnFailure = SQS standard queue holding invocation records
OnSuccess = left unset if no follow-up pipeline step is needed
~~~

**There is no universal optimal config.** Time-sensitive notifications warrant shorter event ages; delay-tolerant batch tasks require evaluating backlog, cost, and SLAs. If work must survive outages beyond 6 hours with independent queue retention, use **SQS** as the source queue with a redrive policy.

## 3. How Destinations and Lambda Async DLQs Compare

### 3.1. `OnSuccess` and `OnFailure` Destinations

For asynchronous invocations, Lambda can send an **invocation record** to a destination after processing:

- **`OnSuccess`:** handler completed normally at the runtime level.
- **`OnFailure`:** event expired or exhausted retries without completing.

Supported targets per AWS documentation:

| Destination | `OnSuccess`? | `OnFailure`? | Notes |
|---|---|---|---|
| **SQS standard queue** | Yes | Yes | Stores record as a message for sequential consumer handling |
| **SNS standard topic** | Yes | Yes | Fan-out notifications; subject to message size limits |
| **AWS Lambda function** | Yes | Yes | Invokes another function; guard against retry loops |
| **Amazon EventBridge bus** | Yes | Yes | Routes via rules; EventBridge has its own retry/DLQ layer |
| **Amazon S3 bucket** | No | **Yes** | Stores JSON invocation record as an object; supports larger payloads per API limits |

**SQS FIFO and SNS FIFO cannot be used as async invocation destinations in this manner.** Capabilities for **event source mappings** or other integrations may differ — never generalize one table to every trigger type.

### 3.2. Sample `OnFailure` Invocation Record

**Simplified** sample record delivered to an SQS `OnFailure` queue:

~~~json
{
  "version": "1.0",
  "timestamp": "2026-11-20T02:15:00.000Z",
  "requestContext": {
    "requestId": "request-id-placeholder",
    "functionArn": "arn:aws:lambda:ap-southeast-1:111122223333:function:aws-lab-worker",
    "condition": "RetriesExhausted",
    "approximateInvokeCount": 3
  },
  "requestPayload": {
    "eventId": "registration-123",
    "registrationId": "reg-123",
    "type": "SEND_CONFIRMATION_EMAIL"
  },
  "responseContext": {
    "statusCode": 200,
    "functionError": "Unhandled",
    "executedVersion": "$LATEST"
  },
  "responsePayload": {
    "errorType": "RuntimeError",
    "errorMessage": "Email provider unavailable"
  }
}
~~~

This JSON is **illustrative of the structure**, not guaranteed output across every runtime, version, and failure condition. `requestPayload` holds the original event; `responseContext` and `responsePayload` help diagnose why the handler failed.

For `OnSuccess`, the record also includes request and response payloads without error fields. Because payloads can hold sensitive data, **never point destinations to targets unauthorized to receive request/response payloads**.

### 3.3. Lambda Async DLQ

A function's async DLQ is configured via **`DeadLetterConfig.TargetArn`**, supporting an **SQS standard queue** or **SNS standard topic**. Unlike destinations, a Lambda async DLQ primarily delivers the **original event**, plus message attributes such as:

~~~text
RequestID
ErrorCode
ErrorMessage
~~~

Consider an input:

~~~json
{
  "eventId": "registration-123",
  "type": "SEND_CONFIRMATION_EMAIL"
}
~~~

Inside the Lambda DLQ, the message body is essentially the **event input**, not the full invocation record with `requestContext` and `responsePayload` delivered by an `OnFailure` destination.

### 3.4. Direct Comparison

| Criterion | Async `OnFailure` destination | Lambda async DLQ |
|---|---|---|
| Trigger condition | Unprocessed after retries/event age | Unprocessed after retries/event age |
| Payload delivered | **Invocation record**: request + response + context | **Original event**, plus select message attributes |
| Supported targets | SQS, SNS, Lambda, EventBridge, S3 (failure) | SQS standard or SNS standard |
| `OnSuccess` support | **Yes** | No |
| Configuration scope | Function, version, or alias as supported | Function-level per AWS docs |
| Purpose | Downstream routing, audit/diagnostic metadata | Preserve raw input for inspection/replay |
| Delivery failure metric | `DestinationDeliveryFailures` | `DeadLetterErrors` |

**Destinations carry richer failure context**, though neither is automatically safer: large record sizes, pricing, IAM permissions, personal data handling, and replay procedures must still be designed.

### 3.5. Choosing by Goal

- **Need to diagnose why the handler failed:** prefer **`OnFailure` destination** for full request/response context.
- **Only need to keep the raw input for later replay:** **Lambda async DLQ** works.
- **Need to fan out failure alerts to multiple systems:** SNS/EventBridge with protected rules and consumers.
- **Large payloads or long retention/storage cost:** consider **S3 `OnFailure`** with lifecycle policies and KMS.
- **Need durable sequential work queues:** use an **SQS source queue** with a redrive policy instead of treating Lambda's internal async queue as a permanent work store.

## 4. Configuring `OnFailure`/`OnSuccess` via AWS CLI and IaC

### 4.1. `put` vs. `update`

AWS Lambda provides:

~~~text
put-function-event-invoke-config
    Creates or replaces the entire async invoke config at the given scope.

update-function-event-invoke-config
    Updates specific fields without intentionally resetting other options.
~~~

**Warning:** `put-function-event-invoke-config` can **overwrite existing configuration**, including retry settings and destinations. Always **read current settings first** and prefer IaC with change reviews. Settings can attach to a function, published version, or alias; when using qualifiers, confirm which version/alias callers actually invoke.

### 4.2. Read Existing Configuration (Read-Only)

~~~bash
REGION=ap-southeast-1
FUNCTION=aws-lab-worker

aws lambda get-function-event-invoke-config \
  --function-name "$FUNCTION" \
  --region "$REGION" \
  --query '{FunctionArn:FunctionArn,Retries:MaximumRetryAttempts,MaxAge:MaximumEventAgeInSeconds,Destinations:DestinationConfig}' \
  --output json
~~~

If no custom config exists yet, `get-function-event-invoke-config` may return `ResourceNotFoundException`. **Do not mistake this for a missing function** if `get-function`/`list-functions` confirms it exists; check the qualifier scope and default behavior.

### 4.3. Sample IaC Configuration

Illustrative CloudFormation snippet:

~~~yaml
Resources:
  AsyncFailureConfig:
    Type: AWS::Lambda::EventInvokeConfig
    Properties:
      FunctionName: aws-lab-worker
      Qualifier: "$LATEST"
      MaximumRetryAttempts: 2
      MaximumEventAgeInSeconds: 3600
      DestinationConfig:
        OnFailure:
          Destination: arn:aws:sqs:ap-southeast-1:111122223333:aws-lab-failures
~~~

This is only a template fragment; it **does not provision the function, queue, policies, or encryption keys**. In real workloads, manage ARNs, roles, and permissions via IaC and review deployment plans. `Qualifier` must match how triggers/producers invoke the function (version/alias vs. unqualified).

### 4.4. Mutating CLI Update Example (Do Not Run Blindly)

Only after verifying config, destination ARN, and permissions in a sandbox:

~~~bash
# ILLUSTRATIVE ONLY; MODIFIES FUNCTION CONFIGURATION
aws lambda update-function-event-invoke-config \
  --function-name aws-lab-worker \
  --maximum-retry-attempts 2 \
  --maximum-event-age-in-seconds 3600 \
  --destination-config '{"OnFailure":{"Destination":"arn:aws:sqs:ap-southeast-1:111122223333:aws-lab-failures"}}' \
  --region ap-southeast-1
~~~

If no async event invoke config exists at that scope yet, use `put-function-event-invoke-config` per the API, **making sure to include every property you intend to keep**. Never copy production commands without knowing IAM, cost, destination ownership, and blast radius.

### 4.5. Configuring a Lambda Async DLQ (Alternative)

Example `DeadLetterConfig` (distinct from `DestinationConfig`):

~~~json
{
  "DeadLetterConfig": {
    "TargetArn": "arn:aws:sqs:ap-southeast-1:111122223333:aws-lab-dlq"
  }
}
~~~

Illustrative command on a **sandbox function**:

~~~bash
# MUTATES RESOURCE; do not run without review
aws lambda update-function-configuration \
  --function-name aws-lab-worker \
  --dead-letter-config "TargetArn=arn:aws:sqs:ap-southeast-1:111122223333:aws-lab-dlq" \
  --region ap-southeast-1
~~~

Check whether the environment already uses a DLQ or destinations. Record existing config before changing it, since updating an ARN does not migrate events already sitting in the previous DLQ.

## 5. IAM, KMS, and Integrity of Failure Destinations

### 5.1. Execution Role Must Have Permission to Deliver Records

For Lambda to deliver records/events to a destination, the **function execution role** needs matching permissions:

| Target | Minimum task-level IAM action |
|---|---|
| SQS destination/DLQ | `sqs:SendMessage` |
| SNS destination/DLQ | `sns:Publish` |
| Lambda destination | `lambda:InvokeFunction` |
| EventBridge destination | `events:PutEvents` |
| S3 `OnFailure` destination | `s3:PutObject` and `s3:ListBucket` as required |
| S3 destination with customer-managed KMS key | May require `kms:GenerateDataKey` and matching key policy |

Across accounts, queue/topic/bucket/bus resource policies and KMS key policies may also need to allow the principal. Never use `Resource: "*"` when you can specify the exact destination ARN.

### 5.2. Least-Privilege Example for SQS `OnFailure`

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "SendOnlyFailureRecords",
      "Effect": "Allow",
      "Action": [
        "sqs:SendMessage"
      ],
      "Resource": "arn:aws:sqs:ap-southeast-1:111122223333:aws-lab-failures"
    }
  ]
}
~~~

If the SQS queue uses an **SSE-KMS customer-managed key**, grant matching KMS permissions and update the key policy for the principal; across accounts, check the queue's resource policy as well. IAM Allow never overrides an explicit Deny, permissions boundary, or SCP.

### 5.3. Risk When an S3 Destination Bucket Is Deleted and Recreated

For `OnFailure` S3 destinations, AWS warns against deleting a bucket **while a destination config still points to that bucket name**. If someone else claims that globally unique bucket name, failure records could be delivered to a bucket you no longer own.

Mitigations:

1. Before deleting a bucket, **remove or update destination configs** across all related functions, aliases, and versions.
2. Constrain `s3:PutObject` with IAM conditions binding the expected bucket owner account.
3. Enforce encryption, Block Public Access, lifecycle rules, versioning, and logging.
4. Restrict read access to invocation records since they may carry sensitive `requestPayload`/`responsePayload`.
5. Never create an S3 notification → Lambda failure → same S3 bucket loop without recursion protection.

### 5.4. Payload Limits and Delivery Failures

An `OnFailure` invocation record is **larger than the raw input event** because it includes metadata and the response. SNS enforces message size caps (e.g., **256 KiB**); oversized records or incompatible target formats trigger **`DestinationDeliveryFailures`**. Lambda DLQs can similarly emit **`DeadLetterErrors`** due to attributes, size, or permissions.

If `AsyncEventsDropped` climbs while the DLQ/destination remains empty:

- Check ARN, Region, destination type, and whether the target resource still exists.
- Check execution role, resource policies, and KMS permissions.
- Check payload size, quotas, and destination limits.
- Inspect `DestinationDeliveryFailures` and `DeadLetterErrors`.
- Assess whether events were permanently lost if no durable upstream replay source exists.

**Monitoring the failure delivery path must be mandatory**, not just monitoring handler `Errors`.

## 6. SQS → Lambda: Retries and DLQ Belong to the Source Queue

### 6.1. How Does Lambda Poll SQS?

With SQS, Lambda uses an **event source mapping** to poll messages and call the handler **synchronously in batches**. SQS holds messages in the queue and hides them during **`VisibilityTimeout`**. When the handler returns success, Lambda deletes the batch's messages from SQS. On failure, undeleted messages reappear once the visibility timeout expires for retry.

~~~mermaid
sequenceDiagram
    participant Q as SQS source queue
    participant E as Lambda event source mapping
    participant F as Lambda handler
    participant D as SQS dead-letter queue
    E->>Q: ReceiveMessage batch
    Q-->>E: Messages temporarily invisible
    E->>F: Invoke batch
    F-->>E: Error / failed items
    Note over Q: Visibility timeout expires
    Q-->>E: Failed messages become visible again
    Note over Q: Receive count hits redrive threshold
    Q->>D: Redrive failed message per policy
~~~

**Lambda's async event invoke config** does not govern this flow. For SQS, configure:

- **Visibility timeout**;
- **Redrive policy** on the source queue (DLQ ARN + `maxReceiveCount`);
- Batch size and batching window;
- `ReportBatchItemFailures` when partial batch responses are needed;
- Concurrency and idempotency.

### 6.2. Example SQS Source Queue Redrive Policy

**Illustrative** JSON for `RedrivePolicy` on the source queue:

~~~json
{
  "deadLetterTargetArn": "arn:aws:sqs:ap-southeast-1:111122223333:aws-lab-orders-dlq",
  "maxReceiveCount": "5"
}
~~~

Once a message has been received `maxReceiveCount` times per SQS semantics, SQS moves it to the DLQ. For SQS sources, AWS recommends setting `maxReceiveCount` to **at least 5** to allow sufficient retries for transient errors.

**Queue types must match:** FIFO sources require FIFO DLQs; standard sources require standard DLQs under SQS rules. Do not confuse the rule that **Lambda async DLQs only support standard queues/topics** with **SQS source queue DLQs**.

### 6.3. Visibility Timeout Must Be Long Enough

Per AWS guidance for SQS event source mappings:

- Function timeout **must not exceed** SQS visibility timeout.
- AWS recommends setting visibility timeout to **at least roughly 6 times** the function timeout to leave room for retries on throttles.
- When using a batching window, add the batching window to that estimate per AWS docs.
- Too short a visibility timeout lets messages reappear before the running attempt finishes, causing duplicate processing.
- Too long a visibility timeout delays retries and slows DLQ arrival.

Example:

~~~text
Lambda timeout = 20 seconds
Initial target SQS visibility timeout >= 120 seconds
  (plus batching window if configured per guidance)
maxReceiveCount = 5
~~~

This is a **starting baseline**, not a substitute for benchmarks and SLO analysis. For workloads with wide duration variance, combine idempotency, visibility extension/heartbeats, and splitting long tasks.

### 6.4. Default Batch Failure Behavior

An SQS batch holds 5 messages:

~~~text
m1: processed successfully
m2: processed successfully
m3: data validation error
m4: not yet processed
m5: not yet processed
~~~

If the handler throws an exception **without partial batch responses enabled**, the entire batch returns to the queue after visibility timeout. That causes **`m1` and `m2` to run again** even though their side effects already occurred — which is why SQS workflows require **idempotency** and partial batch responses.

### 6.5. Partial Batch Responses

When the ESM enables `FunctionResponseTypes=["ReportBatchItemFailures"]`, the handler can return a list of **failed message IDs**:

~~~json
{
  "batchItemFailures": [
    {
      "itemIdentifier": "message-id-3"
    }
  ]
}
~~~

When formatted properly, Lambda deletes succeeded messages and returns only reported failed messages to the queue. If the handler **throws an uncaught exception** instead of returning this JSON structure, the whole batch is still treated as failed.

**Illustrative Python handler catching per-message errors:**

~~~python
import json
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def process_order(order):
    # Replace with business logic designed for idempotency.
    if not order.get("orderId"):
        raise ValueError("Missing orderId")
    # business processing here

def lambda_handler(event, context):
    failed = []

    for record in event.get("Records", []):
        message_id = record["messageId"]

        try:
            payload = json.loads(record["body"])
            process_order(payload)
        except Exception:
            # Never log raw bodies, credentials, or PII.
            logger.exception("Failed to process message id=%s", message_id)
            failed.append({"itemIdentifier": message_id})

    return {"batchItemFailures": failed}
~~~

For this response to take effect, the ESM must enable `ReportBatchItemFailures`. **Never use this snippet directly for real payment flows**: `process_order` must implement real idempotency, transactions, and clear error classification.

**SQS FIFO note:** to preserve per-group ordering, upon encountering an error you must **stop processing subsequent records** and report both the failed message and all unprocessed subsequent messages per AWS guidance. Never copy the standard-queue pattern of “keep processing `m4`/`m5`” if doing so breaks FIFO ordering.

### 6.6. Retry Loops and Poison-Pill Messages

A record with a permanently invalid schema fails on every delivery — known as a **poison pill**. Without a DLQ and bounded retries, it can:

- Drive up Lambda invocation and SQS receive costs;
- Grow queue backlog and message age;
- Starve or delay valid messages;
- Cause repeated batch reprocessing if partial responses are disabled.

Remediation:

1. Validate schemas and classify transient vs. permanent errors.
2. Enable partial batch responses where appropriate.
3. Set sensible `maxReceiveCount` and DLQ retention.
4. Alert on DLQ backlog.
5. Maintain a least-privilege runbook to inspect, repair, and replay.

## 7. Kinesis / DynamoDB Streams: Retries Belong to the Event Source Mapping

### 7.1. Mechanics Differ from SQS

Kinesis and DynamoDB Streams store an **ordered sequence of records** per shard/stream; Lambda's ESM polls, batches, and checkpoints. If the handler fails, retries can **block shard progress** until records succeed, expire by max age, exhaust retries, or fall past source retention.

~~~mermaid
flowchart TD
    ST[Stream shard] --> B[Event source mapping reads batch]
    B --> F[Lambda handler]
    F -->|Success| CP[Commit/checkpoint progress]
    F -->|Function error| R{Retry policy / record age}
    R -->|Retries remaining| F
    R -->|Limit reached| D[Discard + OnFailure destination if configured]
    D --> CP
~~~

Common ESM parameters:

| Option | Meaning |
|---|---|
| `MaximumRetryAttempts` | Caps retries for failed stream records/batches in ESM |
| `MaximumRecordAgeInSeconds` | Caps record age eligible for ESM retry |
| `BisectBatchOnFunctionError` | Splits failing batches in half to isolate the bad record |
| `FunctionResponseTypes=ReportBatchItemFailures` | Reports per-record failures where supported |
| `DestinationConfig.OnFailure` | Captures discarded failed records/batches |
| `ParallelizationFactor` | Concurrent batch reads per shard where supported while preserving key order |

Do not confuse ESM `MaximumRecordAgeInSeconds` with **`MaximumEventAgeInSeconds`** on Lambda's async queue: same age-limit concept, completely different invocation path.

### 7.2. Default Stream Retries Can Last Very Long

Many stream mappings default to `MaximumRetryAttempts=-1` and `MaximumRecordAgeInSeconds=-1` (no mapping-level cap), though **records remain bounded by stream data retention**. Practically, a single poison pill can stall a shard until retention expires; always configure retry/age limits, `IteratorAge` alarms, and a failure destination.

**Depending on the source**, a stream's failed-record destination can be SQS, SNS, S3, or another supported target. With **SQS/SNS** destinations, messages primarily contain metadata; **S3 destinations** where supported can store full record payloads to simplify replay. Check exact docs for Kinesis, DynamoDB Streams, or Kafka.

### 7.3. `BisectBatchOnFunctionError`

Suppose an 8-record batch contains 1 poison pill. With `BisectBatchOnFunctionError` enabled, Lambda halves the failing batch repeatedly to isolate the culprit:

~~~text
[1 2 3 4 5 6 7 8] -> failure
[1 2 3 4]          -> success
[5 6 7 8]          -> failure
[5 6]              -> success
[7 8]              -> failure
[7]                -> failure
[8]                -> success
~~~

This is conceptual; exact behavior depends on source, config, and handler. Batch bisection **does not fix the poison pill**. Pair it with max record age, max retries, `OnFailure` destinations, logs, and replay runbooks.

## 8. Retries Cannot Replace Idempotency

### 8.1. Why Does “At-Least-Once” Duplicate Side Effects?

An event `order-123` can go through:

1. Lambda calls the payment API; payment succeeds.
2. Before returning, Lambda times out due to networking or runtime issues.
3. The source/Lambda treats the attempt as failed and retries.
4. The handler calls the payment API again, causing a **double charge** unless idempotency is enforced.

~~~mermaid
sequenceDiagram
    participant SRC as Event source
    participant L as Lambda
    participant PAY as Payment API
    SRC->>L: order-123
    L->>PAY: Charge 100 USD
    PAY-->>L: Success
    Note over L: Timeout before returning result
    SRC->>L: Retry order-123
    L->>PAY: Charge 100 USD again?
    Note over L,PAY: Must use an idempotency key
~~~

**Bottom line:** setting `MaximumRetryAttempts=0` never guarantees once-only processing, because duplicate delivery can happen outside handler retry logic.

### 8.2. Designing Idempotency Keys

Options:

| Event | Viable idempotency key | Notes |
|---|---|---|
| Order | `orderId` or `paymentIntentId` | Must stay identical across all retries |
| S3 upload | Bucket + object key + version ID/ETag per logic | Key alone fails if objects are overwritten |
| SQS message | Business event ID inside body | `MessageId` changes if republished |
| EventBridge event | Event ID **or** business operation ID | EventBridge ID won't catch duplicate events emitted by producer |
| Daily report | Tenant + report date + report type | Define policy when users explicitly request regeneration |

**Never use Lambda `awsRequestId` as your sole idempotency key**, since every invocation can receive a new request ID. Use a **business operation ID** supplied by the producer.

### 8.3. Idempotent Consumer Pattern

~~~text
Input event {eventId, operationId, payload}
  |
  v
Validate schema + authorization/business rules
  |
  v
Atomic claim on operationId (DynamoDB conditional write or DB transaction)
  |
  +-- Already COMPLETED --> return success, skip side effect
  |
  +-- Valid IN_PROGRESS --> handle concurrency/lease per design
  |
  +-- Claim succeeded   --> call downstream with same idempotency key
                              |
                              +-- Success        --> atomically mark COMPLETED
                              +-- Transient err  --> release/expire lease per policy
                              +-- Permanent err  --> failure record / DLQ
~~~

`IN_PROGRESS`/`COMPLETED` states with lease timeouts handle mid-execution Lambda termination. Note that **claiming before a side effect** risks losing work without recovery, while **marking complete after a side effect** leaves a duplicate window unless downstream also enforces idempotency.

Robust solutions typically combine:

- **Downstream idempotency keys** (e.g., passing the same key to a payment provider);
- **Transactional outbox/inbox** when database commits must stay coupled to event emission;
- State machines / Step Functions for multi-step workflows needing compensation;
- Conditional writes and transactions in DynamoDB/RDS where appropriate.

### 8.4. Retrying with Exponential Backoff and Jitter

Inside a handler, downstream API calls can use bounded retries for transient errors:

~~~text
attempt 1: immediate
attempt 2: ~ 200 ms + jitter
attempt 3: ~ 400 ms + jitter
attempt 4: ~ 800 ms + jitter
stop when exceeding timeout budget or max attempts
~~~

**Never retry infinitely inside Lambda**; it burns execution duration and pushes the invocation into a timeout that triggers outer Lambda/ESM retries. Budget total retry time across **caller → Lambda → downstream SDK → database/API** to prevent retry storms.

## 9. Observability: Metrics and Alerts You Cannot Skip

### 9.1. Key Metrics

| Metric / namespace | Meaning | Action on anomaly |
|---|---|---|
| `AWS/Lambda Invocations` | Recorded invocation count | Track traffic and cost |
| `AWS/Lambda Errors` | Function/runtime errors | Check logs; classify permanent vs. transient |
| `AWS/Lambda Throttles` | Concurrency/quota limits hit | Check reserved/account concurrency and downstream scaling |
| `AWS/Lambda Duration` | Execution time | Compare vs. timeout; spot slow dependencies |
| `AWS/Lambda ConcurrentExecutions` | Concurrent executions | Capacity, throttling, and cost |
| `AsyncEventsReceived` | Events entering Lambda's async queue | Watch for spikes |
| `AsyncEventAge` | Event age when invoked | Alert on backlog/lag and expiry risk |
| `AsyncEventsDropped` | Events dropped due to failures/age/etc. | Assess data loss risk and DLQ/destination |
| `DestinationDeliveryFailures` | Lambda failed to deliver invocation record | Check IAM/KMS/size/destination type |
| `DeadLetterErrors` | Lambda failed to deliver to async DLQ | Check IAM/resource policy/size |
| `SQS ApproximateNumberOfMessagesVisible` | Approximate queue/DLQ backlog | Poison pills or stopped consumer? |
| `SQS ApproximateAgeOfOldestMessage` | Age of oldest waiting message | Are processing/replay SLAs slipping? |
| Stream ESM `IteratorAge` | Shard processing lag | Poison pill or throughput/capacity gap? |

Metric **dimensions, statistics, granularity, and emission** vary by compute mode and source. Never treat `Errors=0` alone as proof that zero events were lost: events can expire before running, be dropped, or fail destination delivery.

### 9.2. Example SLO and Alerts

For a post-registration email service:

~~~text
SLO:
  99.9% of registration events reach final completion
  within 10 minutes.
  100% of failed events leave a record in a durable sink for investigation.

Reference alerts:
  AsyncEventAge p95 or max exceeds expected threshold
  AsyncEventsDropped > 0
  DestinationDeliveryFailures > 0
  SQS DLQ visible messages > 0
  SQS DLQ oldest message age climbing continuously
  Lambda Errors/Throttles elevated above baseline
~~~

**These SLOs are illustrative**, not AWS SLA commitments. In real systems, tune thresholds, evaluation periods, on-call ownership, and runbooks.

### 9.3. Do Not Alert Only on Lambda `Errors`

An event can be lost before the function even runs if the async backlog expires. Or a function can fail yet fail to reach an SQS destination because its execution role lacks `sqs:SendMessage`. Monitor the full pipeline:

1. **Source enqueue:** did the producer successfully publish the event?
2. **Lambda queue/ESM backlog:** are events waiting too long?
3. **Handler:** errors, timeouts, throttles, resource usage.
4. **Failure sink:** are destinations/DLQs receiving and retaining records?
5. **Replay:** how many records await triage vs. successfully reprocessed?

## 10. Practice 1 — Inspecting Lambda Async Config (Read-Only)

> **Prerequisites:** AWS CLI v2 and an IAM identity permitted to read Lambda/SQS/CloudWatch in a **sandbox**. Do not create functions, queues, triggers, or send events. Bash examples use Region `ap-southeast-1`. All names/ARNs are placeholders.

### Step 1 — Confirm Account, Profile, and Region

~~~bash
export AWS_PROFILE=aws-lab-dev
export AWS_DEFAULT_REGION=ap-southeast-1

aws sts get-caller-identity --profile "$AWS_PROFILE"
~~~

If using AWS CloudShell with console session credentials, omit `AWS_PROFILE` and `--profile` flags if no local profile is configured. **Verify Account and Arn first** to avoid touching the wrong environment.

### Step 2 — Read Function Configuration

~~~bash
REGION=ap-southeast-1
FUNCTION=aws-lab-worker

aws lambda get-function-configuration \
  --function-name "$FUNCTION" \
  --region "$REGION" \
  --query '{Name:FunctionName,Runtime:Runtime,Timeout:Timeout,Memory:MemorySize,State:State,DeadLetterConfig:DeadLetterConfig}' \
  --output json
~~~

Project only needed fields; **avoid printing all `Environment.Variables`**, which may contain sensitive values.

**Analysis:** if `DeadLetterConfig` is empty, do not conclude the function has no **`OnFailure` destination**; that is a separate setting inspected via `get-function-event-invoke-config`.

### Step 3 — Read Async Invoke Config

~~~bash
aws lambda get-function-event-invoke-config \
  --function-name "$FUNCTION" \
  --region "$REGION" \
  --query '{MaxRetry:MaximumRetryAttempts,MaxAgeSeconds:MaximumEventAgeInSeconds,Destinations:DestinationConfig}' \
  --output json
~~~

If the application invokes **alias `prod`**:

~~~bash
aws lambda get-function-event-invoke-config \
  --function-name "$FUNCTION" \
  --qualifier prod \
  --region "$REGION" \
  --output json
~~~

Match the exact qualifier invoked by producers. Alias-level config can differ from `$LATEST`. Never alter another function's config merely because values look “non-default.”

### Step 4 — List Event Source Mappings

~~~bash
aws lambda list-event-source-mappings \
  --function-name "$FUNCTION" \
  --region "$REGION" \
  --query 'EventSourceMappings[].{UUID:UUID,Source:EventSourceArn,State:State,BatchSize:BatchSize,PartialResponses:FunctionResponseTypes,Retries:MaximumRetryAttempts,RecordAge:MaximumRecordAgeInSeconds,Destination:DestinationConfig}' \
  --output json
~~~

If SQS, Kinesis, or DynamoDB Streams mappings exist, **analyze by source type**. ESM `MaximumRetryAttempts` is not the same property you inspected in async invoke config; some fields may be blank if unsupported by that source.

### Step 5 — Read SQS Source Queue Redrive Policy

With a real sandbox queue URL:

~~~bash
QUEUE_URL=https://sqs.ap-southeast-1.amazonaws.com/111122223333/aws-lab-orders

aws sqs get-queue-attributes \
  --queue-url "$QUEUE_URL" \
  --attribute-names QueueArn VisibilityTimeout RedrivePolicy \
  --region "$REGION" \
  --output json
~~~

Inspect `VisibilityTimeout` and the `RedrivePolicy` JSON. **Never call `receive-message` on a production queue just to “peek”**, because receiving makes messages temporarily invisible, disrupts consumers, and exposes payloads. With read-only access, inspect attributes and metrics only.

### Step 6 — Check Concurrency Settings

~~~bash
aws lambda get-function-concurrency \
  --function-name "$FUNCTION" \
  --region "$REGION" \
  --output json
~~~

If `ReservedConcurrentExecutions=0`, invocations are blocked and event delivery is impacted; check backlogs/drops and failure sinks. If the API reports no reserved concurrency configured, **do not conclude the function has 0 concurrency**; it simply has no dedicated cap/reservation set.

## 11. Practice 2 — CloudWatch and Destination Checks (Read-Only)

### Step 1 — List Async Metrics

~~~bash
aws cloudwatch list-metrics \
  --namespace AWS/Lambda \
  --metric-name AsyncEventsDropped \
  --dimensions "Name=FunctionName,Value=$FUNCTION" \
  --region "$REGION" \
  --output table
~~~

Metrics without recent datapoints may not appear; never conclude “zero errors ever occurred” from an empty list. In CloudWatch, specify exact function/qualifier dimensions when isolating a specific alias.

### Step 2 — Sum Dropped Events Over 30 Minutes

Bash example in AWS CloudShell (GNU date):

~~~bash
START_UTC=$(date -u -d '30 minutes ago' +%Y-%m-%dT%H:%M:%SZ)
END_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)

aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name AsyncEventsDropped \
  --dimensions "Name=FunctionName,Value=$FUNCTION" \
  --start-time "$START_UTC" \
  --end-time "$END_UTC" \
  --period 300 \
  --statistics Sum \
  --region "$REGION" \
  --output json
~~~

**Interpretation:** `Sum` per 300-second period is the total count of dropped events, not an error percentage. Any drop warrants investigating root causes and recovery paths. Repeat for `AsyncEventsReceived`, `DeadLetterErrors`, and `DestinationDeliveryFailures`.

### Step 3 — Check DLQ Backlog Without Reading Payloads

~~~bash
DLQ_URL=https://sqs.ap-southeast-1.amazonaws.com/111122223333/aws-lab-failures

aws sqs get-queue-attributes \
  --queue-url "$DLQ_URL" \
  --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesDelayed ApproximateNumberOfMessagesNotVisible \
  --region "$REGION" \
  --output json
~~~

SQS counts are **approximations** with reporting lag. For the age of the oldest message, query CloudWatch `AWS/SQS ApproximateAgeOfOldestMessage` for that exact `QueueName`. **Never dump DLQ messages casually** because they may hold requests/responses, access tokens, or personal data.

### Step 4 — Verification Table

| Check | Observed result | Conclusion to verify |
|---|---|---|
| Producer InvocationType | Sync / async / ESM | Identifies the governing retry layer |
| Async `MaximumRetryAttempts` | ... | How many times function errors retry? |
| Async `MaximumEventAgeInSeconds` | ... | When do backlogged events expire? |
| `DestinationConfig.OnFailure` | ... | Are invocation records captured? |
| `DeadLetterConfig.TargetArn` | ... | Are raw async events captured? |
| SQS `RedrivePolicy` | ... | Source queue DLQ and `maxReceiveCount` |
| SQS `VisibilityTimeout` | ... | Retry spacing and duplicate risk |
| `DestinationDeliveryFailures` / `DeadLetterErrors` | ... | Can Lambda actually write to the failure sink? |
| DLQ backlog | ... | Are records awaiting triage and replay? |

## 12. Practice 3 — Controlled Failure Injection in Sandbox (Optional)

> **Has real side effects.** Only run if you own an isolated sandbox function/queue, have invoke/update permissions, have budgets enabled, and own cleanup. This section is optional and must never target functions that process real payments or emails.

### 12.1. Lab Preparation

- Function `aws-lab-retry-demo` with zero permissions to mutate real data.
- A dedicated **SQS standard queue**, e.g., `aws-lab-lambda-failures`, attached as the `OnFailure` destination with `sqs:SendMessage` on the execution role.
- Short Lambda timeout and a handler that fails **intentionally** when `simulateFailure=true`.
- Bounded `MaximumRetryAttempts` and max event age so failures finish quickly.
- CloudWatch logs/metrics and queue alarms.
- Zero PII, credentials, or production data in test events.

Simple Python handler example:

~~~python
import json

def lambda_handler(event, context):
    if event.get("simulateFailure") is True:
        raise RuntimeError("Expected training failure")

    return {
        "processed": True,
        "eventId": event.get("eventId")
    }
~~~

This snippet only demonstrates inducing failure. **Never deploy outside a sandbox and never leave intentional `raise` backdoors in real business handlers.**

### 12.2. Send a Sample Async Event

Local `training-event.json` with synthetic data only:

~~~json
{
  "eventId": "training-001",
  "simulateFailure": true,
  "source": "lambda-retry-lab"
}
~~~

Illustrative AWS CLI v2 command:

~~~bash
# RUN ONLY against an approved sandbox function
aws lambda invoke \
  --function-name aws-lab-retry-demo \
  --invocation-type Event \
  --payload fileb://training-event.json \
  --region ap-southeast-1 \
  invoke-response.json
~~~

`StatusCode=202` only confirms the async event was queued; **not that the handler succeeded**. Local `invoke-response.json` does not contain a synchronous invocation result.

### 12.3. Observe and Verify

1. Inspect function logs containing **no sensitive data**.
2. Track invocation/error counts and intervals between retries.
3. Inspect `AsyncEventAge` and `AsyncEventsDropped` if applicable.
4. Confirm the `OnFailure` destination received **one matching business record** — never assume exactly-once, as transports/handlers can duplicate events.
5. Check `requestContext.condition` and `approximateInvokeCount` through an authorized safe viewer.
6. Confirm `DestinationDeliveryFailures=0` and handle the DLQ backlog per runbook.

### 12.4. Restore and Clean Up

- Record pre-test config and restore retry/destination settings on the **sandbox function only** per change review.
- Clear test records from the sandbox queue carefully without touching real messages.
- If dedicated lab queues/functions were created, tear them down in **dependency order** (detach destinations/mappings first, then delete owned resources).
- Verify CloudWatch log retention, SQS queues, Lambda functions, and Regional costs.
- **Never delete a shared S3/SQS DLQ** serving other systems.

## 13. Redrive and Replay: Recovering Events Without Duplicate Side Effects

### 13.1. Redrive Is Not a Blind “Rerun Everything” Button

A DLQ accumulates messages that failed for **many different reasons**:

- Missing required fields in input data;
- Downstream outages;
- Denied IAM/KMS permissions;
- Prolonged throttling;
- Application bugs;
- Obsolete events no longer valid for the business.

Redriving everything without fixing the root cause simply loops messages straight back into the DLQ or creates duplicate side effects.

### 13.2. Safe Replay Workflow

~~~mermaid
flowchart TD
    A[DLQ / failure destination records] --> B[Classify errors]
    B --> C{Transient or permanent?}
    C -->|Transient| D[Verify downstream recovered]
    C -->|Permanent| E[Fix schema / reconcile data]
    D --> F[Check event age and business validity]
    E --> F
    F --> G[Idempotency key + dedup state]
    G --> H[Controlled / rate-limited replay]
    H --> I[Monitor success, errors, and side effects]
    I --> J{Outcome healthy?}
    J -->|Yes| K[Audit / mark resolved]
    J -->|No| B
~~~

Suggested procedure:

1. Distinguish **Lambda async DLQ bodies** (raw event) from **`OnFailure` destination bodies** (full invocation record). When replaying from `OnFailure`, extract and validate only `requestPayload`.
2. Check the business operation ID against current state; if already completed, **never re-execute the side effect**.
3. Normalize event schemas/versions and discard obsolete records.
4. Rate-limit replays, staging through a quarantine queue if needed.
5. Monitor metrics, success counts, new DLQ entries, and audit logs.
6. Keep a cancel/rollback switch ready if replay causes issues.

### 13.3. Automated SQS DLQ Redrive vs. Manual Tooling

SQS supports **dead-letter queue redrive** when authorized across compatible source/destination queues. Still:

- Redrive moves messages back to the source queue or a permitted queue per AWS features; verify ARNs, queue types, and permissions.
- It does not automatically heal broken or half-committed downstream transactions.
- Messages must still be inside their retention window.
- With FIFO queues, ordering and deduplication require separate analysis.
- Never redrive cross-account or customer data without formal approval.

**Do not put `start-message-move-task` into mandatory labs**, since it can push bulk live messages back into processing. In production, run it only under an approved runbook with active monitoring and an abort plan.

### 13.4. When Do You Need Step Functions Instead of Simple Retries?

If a workflow spans multiple dependent steps:

~~~text
Charge payment -> Reserve inventory -> Send email -> Update CRM
~~~

where each step needs tailored retries and compensation, **AWS Step Functions** fits far better than simple Lambda async retries. Step Functions provides state machines, per-state retries, catches, and step tracking — while still requiring idempotency and compensation logic.

**Never sleep inside a Lambda runtime for minutes** waiting on another step; that wastes money and ties up concurrency unnecessarily.

## 14. Availability and Cost When Designing Retries

### 14.1. Concurrency Impacts Backlog

Suppose a system receives 1,000 events/minute, each averaging 2 seconds of processing. Theoretical concurrency needed is roughly:

~~~text
1,000 events / 60 seconds * 2 seconds
≈ 33.3 concurrent executions
~~~

If reserved concurrency is only 10 while traffic holds steady, backlog grows. Adding retries while downstream is failing pushes real concurrency demand even higher, raising costs and risking expired events.

These figures are **theoretical**; cold starts, runtime variance, reserved/account concurrency, traffic bursts, source scaling, and throttling all change real throughput.

### 14.2. Direct and Indirect Costs

| Component | Potential charges | How to control |
|---|---|---|
| Lambda invokes | Every execution attempt (requests/duration/memory) | Fix root bugs, cut futile retries, optimize handlers |
| Lambda async backlog | Higher latency/age, risk of dropped events | Right-size concurrency, configure alarms |
| SQS source/DLQ | API requests, payload/storage per pricing | Tune retention, batching, and controlled redrives |
| SNS/EventBridge | Publishing/delivery/rule evaluations | Prevent loops and unnecessary fan-outs |
| S3 `OnFailure` | Objects, PUT requests, storage, lifecycle, KMS | Enforce retention, encryption, and bucket governance |
| CloudWatch | Log ingestion/retention, metrics, alarms | Redact PII and target retention windows |
| Downstream | DB/API calls, third-party transactions | Enforce idempotency and backoff; never retry forever |

**Trade-off:** fewer retries save money yet send more events to the DLQ. Too many retries delay recovery and inflate bills. Choose based on **RTO/SLO, data validity, and replayability**, not “more retries is always safer.”

### 14.3. Failure Isolation

- Set **reserved concurrency** carefully so Lambda does not overwhelm downstream systems — yet avoid setting it so low that async event age spikes and events drop.
- Split workloads with different SLOs into **separate queues/functions**.
- Route poison-pill events to a **DLQ/quarantine** instead of letting one message stall all traffic.
- Apply **circuit breakers** or throttle throughput during downstream outages, backed by durable queues and recovery runbooks.
- When SQS is the source, tune visibility, redrive, and partial batches instead of misconfiguring Lambda async retries.

## 15. Common Pitfalls and How to Diagnose Them

| Symptom | Likely root cause | First check |
|---|---|---|
| `Invoke(Event)` returns 202 yet no email arrives | 202 only confirms queuing; handler or downstream failed | Async metrics, logs, destination/DLQ |
| Function throws yet runs 3 times | Async function error defaults to 2 retries | `get-function-event-invoke-config`, idempotency logic |
| Retries set to 0 yet event still runs again | Throttling/system errors, duplicate async delivery, or ESM source | Identify invocation type and failure class |
| `OnSuccess` fires even though app returned `statusCode:500` | Handler returned normally without throwing | Define business success; throw or handle errors properly |
| `AsyncEventsDropped` rises while `OnFailure` queue stays empty | Destination delivery failed or wrong qualifier/config | `DestinationDeliveryFailures`, ARN/IAM/KMS |
| `DeadLetterErrors` rises | Lambda cannot deliver to async DLQ | SQS/SNS standard type, policies, payload size |
| DLQ holds raw event instead of `responsePayload` | Configured Lambda async DLQ instead of `OnFailure` destination | Inspect `DeadLetterConfig` vs. `DestinationConfig` |
| SQS poison pill loops endlessly | Missing `RedrivePolicy` / improper `maxReceiveCount` | SQS queue attributes, visibility, metrics |
| One bad SQS message causes whole batch to rerun | Partial batch disabled or handler threw uncaught exception | `ReportBatchItemFailures` and response schema |
| Successful SQS message vanishes despite business error | Handler swallowed exception and returned success | Propagate errors, return partial failures, or throw |
| FIFO records after a failing record still ran | Partial batch response broke ordering | Stop on first failed record and return all remaining items |
| Stream `IteratorAge` climbs continuously | Poison pill or insufficient throughput/capacity | Retry/age/bisect settings, shard lag, destinations |
| Large `OnFailure` record fails to reach SNS | 256 KiB SNS message cap or destination limit | `DestinationDeliveryFailures`; use SQS/S3 instead |
| Lambda timeout causes duplicate charge | Side effect succeeded right before timeout | Downstream idempotency keys, transactional design |
| Event replayed yet creates duplicate state | Replay skipped checking current business state | Business operation ID and deduplication store |
| Function lacks concurrency and events expire | Throttles/backlog exceeded max event age | `Throttles`, `AsyncEventAge`, reserved concurrency |
| Logs show no errors yet events are missing | Events dropped before handler ran | `AsyncEventsDropped`, source and sink metrics |
| CloudWatch DLQ backlog never shrinks | No owner/runbook/consumer, or consumer failing | Queue age, consumer errors, redrive plan |
| S3 destination bucket was deleted | Stale destination ARN risks delivering to another owner's bucket | Detach destination before deleting bucket; bind owner account |
| Nobody knows who owns the failure | Missing correlation IDs, owners, and alerts | Attach `eventId`, `traceId`, owner; runbooks & dashboards |

### 15.1. Step-by-Step Investigation Sequence

~~~text
1. Confirm account, Region, function/alias/trigger.
2. Identify invocation type: synchronous / async / event source mapping.
3. Classify error: handler exception, timeout, throttle, system error.
4. Inspect retry settings at the exact governing layer.
5. Check concurrency, backlog, age, and source retention.
6. Inspect OnFailure, Lambda DLQ, or source queue DLQ / ESM sink.
7. Check execution role, resource policies, KMS, and payload size limits.
8. Verify whether side effects committed via business operation ID.
9. Fix root cause and replay at an approved rate.
10. Monitor success, duplicates, latency, and cost; document audit and close incident.
~~~

## 16. Real-World Scenario: Course Registration and Email Confirmation

### 16.1. Context

An online learning platform on AWS includes:

- **API Gateway + Lambda** accepting course registrations;
- **DynamoDB** storing registration status and business operation IDs;
- **EventBridge** (or another event bus/source) forwarding registration events;
- **Lambda `email-worker`** calling an email provider;
- **SQS DLQ / `OnFailure` destination** capturing exhausted failures;
- **CloudWatch** tracking event lag, failures, and emails sent.

Requirements:

- Never send duplicate emails if an event is delivered twice.
- If the email provider has a 15-minute outage, the system can retry or replay.
- Malformed-schema events must be isolated.
- Never forward email addresses/PII to unapproved destinations.
- On-call teams have dashboards and runbooks.

### 16.2. Two Architectural Options

**Option A — Direct Lambda Asynchronous Invocation:**

~~~mermaid
flowchart LR
    API[Registration API] --> EVT[EventBridge/S3/SNS async trigger]
    EVT --> L[Lambda async event queue]
    L --> W[Email worker]
    W --> P[Email provider]
    L -->|OnFailure| D[SQS standard destination]
    L -->|Optional OnSuccess| S[EventBridge audit bus]
    D --> R[Quarantine / repair / replay]
~~~

Fits small events whose recovery fits within Lambda's async queue limits, adjusting retry attempts, max event age, and failure destinations.

**Option B — Durable SQS Work Queue:**

~~~mermaid
flowchart LR
    API[Registration API] --> Q[SQS source queue]
    Q --> E[Lambda event source mapping]
    E --> W[Email worker - partial batch response]
    W --> P[Email provider]
    Q -->|Redrive policy| D[SQS DLQ]
    D --> R[Controlled redrive]
~~~

Fits when you want **queue retention, receive-count retries, backlog visibility, and source DLQs** decoupled from Lambda async invoke settings. Both models require idempotency and monitoring.

### 16.3. Mechanism Selection Table

| Question | Choose Async Lambda | Choose SQS Source + ESM |
|---|---|---|
| Need a few retries for function errors within 6 hours? | Good fit | Also possible via queue policy, with different mechanics |
| Need durable backlog retention independent of Lambda? | More limited | **SQS** fits better |
| Need explicit receive count before hitting DLQ? | `MaximumRetryAttempts` covers function errors only | `maxReceiveCount` on source queue |
| Need batching and partial batch failure handling? | Not an ESM batch flow | **SQS ESM** supports `ReportBatchItemFailures` |
| Need multi-target notification on success? | `OnSuccess` destination | Consumer can emit downstream events after commit |
| Need failure records with request/response metadata? | `OnFailure` destination | App logs/records or ESM features per source |
| Have batch poison pills to isolate? | Single-event handling or source design | DLQ, partial batches, idempotency |

### 16.4. Recommended Operational Practices

1. Every registration event carries a stable `registrationId` and `eventId` across retries.
2. Call the email provider with an idempotency key or equivalent deduplication check.
3. Retry transient failures with bounded backoff; isolate permanent errors.
4. Protect failure sinks with IAM/KMS, minimal payload data, and bounded retention.
5. Alert when event lag, age, drops, or delivery failures cross thresholds.
6. Assign owners and triage/replay runbooks to SQS DLQs/`OnFailure` queues.
7. After replays, reconcile the email-sent ledger against registration states.
8. Test duplicates, post-side-effect timeouts, downstream outages, and invalid payloads.

## 17. Exercises and Self-Check Questions

1. Does `InvocationType=Event` returning `StatusCode=202` mean the handler already sent the email?
2. Why doesn't Lambda synchronous invocation auto-retry function errors like async invocation?
3. Does `MaximumRetryAttempts=2` mean 2 total runs or **2 retries** after the initial run?
4. Why do throttling and function errors follow different async retry rules?
5. What happens if an event sits in Lambda's async queue longer than `MaximumEventAgeInSeconds`?
6. How does an `OnFailure` destination differ from a Lambda async DLQ in **message body**?
7. Can an `OnSuccess` destination receive a record even when business logic actually failed?
8. For a Lambda reading SQS, why doesn't `MaximumRetryAttempts` in async invoke config govern `maxReceiveCount`?
9. What risk arises if the SQS visibility timeout is shorter than the function timeout?
10. In a 10-message batch where the third message fails, why might the first two messages execute again?
11. Where must `ReportBatchItemFailures` be enabled, and what structure must the handler return?
12. Why should an SQS FIFO handler stop processing after the first failing record?
13. Which metric climbs when a Kinesis poison-pill record stalls processing?
14. What does `BisectBatchOnFunctionError` help isolate? Does it fix the bad record itself?
15. Why is a business operation ID better than a Lambda request ID for deduplication?
16. Once an event lands in a DLQ, can you skip IAM/KMS or PII controls?
17. When `DestinationDeliveryFailures` rises, which layers must you check?
18. If function `Errors` rise while the source queue DLQ stays empty, what are possible explanations?
19. Why is blindly redriving an entire DLQ after backend recovery still dangerous?
20. Which costs can rise when a prolonged upstream outage triggers heavy retries?

### 17.1. Brief Suggested Answers

1. No; it only confirms the async request was accepted into the queue.
2. The caller or invoking service decides on retries.
3. Two **retries** — typically up to three total attempts unless bounded by event age or capacity.
4. Function errors obey configured retry count; throttles/system errors follow backoff and max event age.
5. The event can be discarded; configure `OnFailure`/DLQ to capture it.
6. `OnFailure` delivers a full invocation record; a Lambda DLQ delivers primarily the original event input.
7. Yes, if the handler returns normally despite a logical business failure.
8. SQS uses ESM polling, queue visibility timeouts, and queue redrive policies.
9. Duplicate concurrent in-flight processing and inconsistent side effects.
10. Default batch behavior retries the entire batch on failure.
11. Set `FunctionResponseTypes=ReportBatchItemFailures` on the ESM and return `batchItemFailures` from the handler.
12. To preserve strict ordering within each message group.
13. `IteratorAge` climbs; monitor ESM metrics and stream retention.
14. Splits failing batches to isolate the poison record; it does not repair invalid data.
15. Each invocation can get a new request ID; a business ID stays constant.
16. No; failure records can contain PII/responses and must remain protected.
17. Destination type, ARN, IAM permissions, KMS, payload size, and target resource existence.
18. Wrong DLQ layer checked, `maxReceiveCount` not reached yet, DLQ permission failure, wrong alias, or retention/config mismatch.
19. It can cause duplicate side effects or replay invalid messages.
20. Lambda invocations/duration, SQS requests/storage, DLQs, CloudWatch logs/metrics, downstream API calls, and data transfer.

## 18. Pre-Production Checklist

### Sources and Retries

- [ ] Identified whether each trigger uses **sync, async, or event source mapping**.
- [ ] Async function errors have retry counts and max event ages aligned with SLOs.
- [ ] SQS sources have tuned visibility timeouts, redrive policies, and `maxReceiveCount`.
- [ ] Stream sources configure retention, max record age/retries, bisection, and destinations as needed.
- [ ] Plans exist for duplicate deliveries and poison-pill records.
- [ ] Neither handlers nor SDKs retry infinitely without a timeout budget.

### Failure Handling

- [ ] Clearly distinguished **`OnFailure` destination**, **Lambda async DLQ**, and **SQS source DLQ**.
- [ ] Failure record format is understood so parsers/replays handle it accurately.
- [ ] Destination/queue ARNs, types, and Regions are verified.
- [ ] Function execution roles, resource policies, and KMS policies grant exact permissions.
- [ ] S3 destinations have ownership checks and safeguards before bucket deletion.
- [ ] Event payloads, response payloads, PII, and secrets are protected from unprotected logs/failure sinks.
- [ ] Metrics/alarms watch `DeadLetterErrors`, `DestinationDeliveryFailures`, and `AsyncEventsDropped`.
- [ ] On-call owners, retention windows, runbooks, and approved redrive procedures are documented.

### Business Logic, Operations, and Cost

- [ ] Handlers enforce idempotency keyed by business operation ID.
- [ ] Strategy handles side effects that committed right before a timeout.
- [ ] Tested duplicate events, transient errors, permanent errors, throttling, and backlog growth.
- [ ] Dashboards track `Errors`/`Throttles`/`Duration`, `AsyncEventAge` or `IteratorAge`, and DLQ age.
- [ ] End-to-end completion SLOs reconcile events processed vs. events accepted.
- [ ] Safe rollback/replay procedures and audit trails exist.
- [ ] Budgets, tagging, cost allocation, and post-lab sandbox cleanup are in place.

**Expected outcome:** learners do not merely know how to “turn on retries” — they can identify **which layer owns retries**, design **the right failure sink**, explain when events expire, handle **at-least-once delivery** via idempotency, and operate event-driven systems that are observable, resilient, and cost-controlled.

## Official AWS Documentation

- [Understanding retry behavior in AWS Lambda](https://docs.aws.amazon.com/lambda/latest/dg/invocation-retries.html)
- [How Lambda handles errors and retries with asynchronous invocation](https://docs.aws.amazon.com/lambda/latest/dg/invocation-async-error-handling.html)
- [Configuring error handling settings for asynchronous invocations](https://docs.aws.amazon.com/lambda/latest/dg/invocation-async-configuring.html)
- [Capturing records of Lambda asynchronous invocations](https://docs.aws.amazon.com/lambda/latest/dg/invocation-async-retain-records.html)
- [Invoking Lambda functions asynchronously](https://docs.aws.amazon.com/lambda/latest/dg/invocation-async.html)
- [AWS Lambda CloudWatch metrics](https://docs.aws.amazon.com/lambda/latest/dg/monitoring-metrics-types.html)
- [Using Lambda with Amazon SQS](https://docs.aws.amazon.com/lambda/latest/dg/with-sqs.html)
- [Configuring an Amazon SQS event source mapping](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-configure.html)
- [Handling errors for SQS event sources](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-errorhandling.html)
- [Partial batch response for SQS event sources](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-errorhandling.html#services-sqs-batchfailurereporting)
- [Using Lambda with Kinesis Data Streams](https://docs.aws.amazon.com/lambda/latest/dg/with-kinesis.html)
- [Retain discarded batch records for a Kinesis event source](https://docs.aws.amazon.com/lambda/latest/dg/kinesis-on-failure-destination.html)
- [Handling DynamoDB Streams errors](https://docs.aws.amazon.com/lambda/latest/dg/services-dynamodb-errors.html)
- [AWS Lambda API: EventInvokeConfig](https://docs.aws.amazon.com/lambda/latest/api/API_PutFunctionEventInvokeConfig.html)
- [AWS CloudFormation: AWS::Lambda::EventInvokeConfig](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-lambda-eventinvokeconfig.html)
- [Amazon SQS dead-letter queues](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-dead-letter-queues.html)
- [AWS Step Functions retry and catch](https://docs.aws.amazon.com/step-functions/latest/dg/concepts-error-handling.html)
- [AWS Lambda pricing](https://aws.amazon.com/lambda/pricing/)
- [AWS Pricing Calculator](https://calculator.aws/)

> **Usage note:** Function names, queues, ARNs, account IDs, numbers, and JSON responses in this lesson are training examples. AWS parameters, event sources, destination types, limits, pricing, and features can vary by Region and over time. Before modifying production configurations, verify current AWS APIs/docs, test in a sandbox with synthetic data, audit IAM/KMS, and maintain an approved recovery plan.
