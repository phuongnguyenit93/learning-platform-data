# Batch Operations, Backpressure, and Consumer Scaling

> **Chapter:** Queues and Notifications  
> **Module:** `CLOUD_PROVIDERS_AWS` — explore the AWS ecosystem from Regions/AZs, IAM, and VPC to compute, storage, databases, integration, and serverless; practice selecting services and designing and deploying secure, observable, resilient, and cost-controlled applications.

In an order-processing system, a **producer** can generate thousands of events in seconds, while a **consumer** must validate payments, update databases, and call shipping partners—operations typically slower than pushing a message onto a queue. If processed synchronously along the HTTP path, a traffic spike easily causes request timeouts, connection pool exhaustion, and cascading failures.

**Amazon Simple Queue Service (Amazon SQS)** decouples the rate of work creation from the rate of work execution. However, simply adding a queue is not enough. The system must **batch messages to reduce API calls**, apply **backpressure** to protect consumers and downstream dependencies from overload, and **scale consumers** based on queued work as well as actual processing capacity.

Three core concepts:

| Concept | Problem to solve | Typical measures |
| --- | --- | --- |
| **Batch operations** | How to send, receive, and acknowledge many messages efficiently without losing messages when part of a batch fails? | SQS batch APIs, per-entry result inspection, Lambda partial batch responses |
| **Backpressure** | When message arrival exceeds processing capacity, what absorbs the load and how do we prevent downstream collapse? | Queue buffering, bounded concurrency, rate limiting, retries/backoff, DLQ |
| **Consumer scaling** | How many workers are needed, when to scale up/down, and which signals should drive scaling? | CloudWatch queue metrics, backlog per task, age of oldest message, ECS Service Auto Scaling / Lambda event source scaling |

This lesson focuses on **SQS Standard/FIFO and common consumers** such as Lambda, ECS/Fargate, or EC2. Amazon SNS and EventBridge can sit in front of SQS to distribute events, but **they do not replace SQS's batching and acknowledgment rules**.

## 1. Learning Objectives

After this lesson, learners will be able to:

1. Explain **producer → SQS → consumer → downstream**, the message lifecycle, visibility timeout, receipt handles, retention, and Dead-Letter Queues (DLQs).
2. Apply **`SendMessageBatch`, `ReceiveMessage`, `DeleteMessageBatch`, and `ChangeMessageVisibilityBatch`**, understanding the 10-entry cap on those APIs and **partial success** handling.
3. Distinguish **SQS batch APIs** from **Lambda event source mapping batches**, including `batchSize`, `maximumBatchingWindowInSeconds`, and `ReportBatchItemFailures`.
4. Design **at-least-once** handling, idempotency, FIFO ordering, retries, visibility extension, and DLQ redrive.
5. Recognize **backpressure** when producers outpace consumers and handle downstream 429/503 responses without causing a retry storm.
6. Calculate consumer demand from arrival rate, processing rate, backlog, and SLOs; know when autoscaling helps versus hurts.
7. Choose between a **Lambda SQS trigger** and an **ECS/EC2 poller** based on workload type, concurrency control needs, and operations.
8. Read Java AWS SDK v2 code, partial-batch Lambda handlers, and read-only AWS CLI commands, then design a safe production workflow.

## 2. Overall Architecture

~~~mermaid
flowchart LR
    API["API / Producer\nPlace order"] -->|"SendMessage / Batch"| Q["Amazon SQS\nStandard or FIFO"]
    SNS["SNS / EventBridge\nif fan-out"] -->|"Subscription / rule"| Q
    Q -->|"ReceiveMessage / Lambda poll"| WORK["Consumer fleet\nLambda or ECS/EC2"]
    WORK -->|"Business processing"| DB["Downstream DB / API"]
    WORK -->|"Delete after success"| Q
    Q -->|"Exceeds maxReceiveCount"| DLQ["Dead-letter queue"]
    MON["CloudWatch + Alerts"] -.-> Q
    MON -.-> WORK
    MON -.-> DLQ
    SCALER["Scaling policy"] -.->|"Adjust consumer concurrency"| WORK
~~~

*The Delete arrows represent the consumer **deleting the message by receipt handle** upon successful processing, not writing content directly to the queue. With Lambda event source mapping, the Lambda service handles polling and deleting messages after a successful invocation.*

### 2.1. Why do queues reduce coupling?

Without a queue:

~~~text
HTTP request → send email → call partner → write database → HTTP response
                  (a slow partner slows the entire request)
~~~

With a queue:

~~~text
HTTP request → write order / outbox → send event to SQS → appropriate HTTP 202/200
                                                          |
                                                          v
                                            Worker processes later
~~~

The system can **absorb short bursts** without forcing every request to wait for full completion. Still, returning HTTP **202 Accepted** only means the job was accepted per contract; if the producer fails to persist work durably or implements the outbox poorly, events can still be lost.

### 2.2. Message states in SQS

| Logical state | Meaning |
| --- | --- |
| **Visible** | Available to be received by a consumer |
| **In flight / Not visible** | Received and currently within its visibility timeout |
| **Visible again** | Visibility expired before deletion; eligible for redelivery |
| **Deleted** | Consumer confirmed completion with a valid receipt handle |
| **Moved to DLQ** | After failed receives exceed `redrive policy`, moved to the DLQ |
| **Expired** | Exceeded retention period and removed by SQS, even if unprocessed |

**Receive does not equal completion.** SQS does not know whether a database commit succeeded, an email was sent, or a downstream call returned a status. Messages are only removed through acknowledgment/deletion once work is confirmed at the application layer.

### 2.3. SQS Standard and FIFO

| Characteristic | **Standard queue** | **FIFO queue** |
| --- | --- | --- |
| Delivery | **At least once**; duplicates can occur | Deduplication and ordering per FIFO rules |
| Ordering | Best-effort ordering; no global order guarantee | Preserves order **within the same message group** |
| Parallelism | Scales easily across many workers; tolerates duplicates | Parallelism bounded by independent message groups |
| Deduplication | Implemented by application | `MessageDeduplicationId` or content-based deduplication within the service-defined window |
| When to choose | Independent tasks, high throughput, duplicate-tolerant | Workflows needing per-entity/key ordering and enqueue-time deduplication |

**FIFO does not make side effects exactly-once.** If a worker updates a database and fails before SQS receives `Delete`, the message can be redelivered; consumers must still be idempotent. FIFO deduplication protects **enqueueing**, not downstream processing idempotency.

## 3. Batch Operations: Optimizing API Calls Without Dropping Per-Message Errors

Common SQS APIs:

| API | Role | Limits / notes |
| --- | --- | --- |
| `SendMessage` | Send one message | Supports message attributes, delay, FIFO group/dedup per rules |
| **`SendMessageBatch`** | Send **up to 10 entries** per request | Each entry has its own `Id`; partial success is possible |
| **`ReceiveMessage`** | Receive **up to 10 messages** per request | `MaxNumberOfMessages=1..10`; may return **fewer** than requested, or none |
| `DeleteMessage` | Delete one message by receipt handle | Never use `MessageId` in place of receipt handle |
| **`DeleteMessageBatch`** | Delete **up to 10 entries** per request | Returns separate `Successful` and `Failed` lists |
| `ChangeMessageVisibility` | Extend/shorten hide duration for one message | Requires a valid receipt handle |
| **`ChangeMessageVisibilityBatch`** | Change visibility of **up to 10 entries** | Also supports partial success |

**An HTTP 200 API response does not mean the whole batch succeeded.** For batch APIs, always inspect both `Successful` and `Failed` arrays and handle errors by each entry's `Id`. `Failed` entries include `Code`, `Message`, and `SenderFault`; retry only retryable failures, never retrying malformed data or configuration errors forever.

### 3.1. `SendMessageBatch` and partial success example

Producer wants to send four jobs:

~~~json
{
  "Entries": [
    {"Id": "a1", "MessageBody": "{\"orderId\":\"o-101\"}"},
    {"Id": "a2", "MessageBody": "{\"orderId\":\"o-102\"}"},
    {"Id": "a3", "MessageBody": "{\"orderId\":\"o-103\"}"},
    {"Id": "a4", "MessageBody": "{\"orderId\":\"o-104\"}"}
  ]
}
~~~

Illustrative response (abbreviated):

~~~json
{
  "Successful": [
    {"Id": "a1", "MessageId": "m-101"},
    {"Id": "a2", "MessageId": "m-102"},
    {"Id": "a4", "MessageId": "m-104"}
  ],
  "Failed": [
    {
      "Id": "a3",
      "Code": "InternalError",
      "Message": "Transient service error",
      "SenderFault": false
    }
  ]
}
~~~

This is **illustrative data**, not a live AWS log. Given this response, **do not resend a1, a2, or a4 as if they failed**. Retry only `a3` after backoff. If the request timed out and the client **received no response at all**, individual send outcomes are uncertain; idempotency and a producer outbox mitigate the impact of duplicate sends.

### 3.2. SQS message size is not batch size

Distinguish actual limits:

- **Entry count:** `SendMessageBatch` allows at most **10 messages** per API request.
- **Size:** each individual message and total batch payload must fit current SQS message/payload limits (e.g., around **1 MiB** for SQS operations supporting that size, depending on request and API docs).
- **Business payload:** oversized payloads should store an **S3 reference** rather than stuffing files into the body, alongside proper access control, expiry, and encryption.
- **Actual returned count:** `ReceiveMessage(MaxNumberOfMessages=10)` **does not promise to always return 10**.

**Batching 10 messages** cuts API call costs for the same workload; it does not squeeze a 100 MB task past SQS size limits.

### 3.3. When does batching slow things down?

Batching comes with trade-offs:

- Waiting to accumulate 10 messages delays the first message during low traffic.
- Large batch sizes lengthen a single Lambda invocation or bundle many failed messages together.
- If a consumer commits an entire batch only at the end, one slow or invalid item stretches visibility requirements for all others.
- Large downstream batches (e.g., bulk DB inserts) reduce call overhead at the cost of higher transaction/lock pressure.

Prefer tuning **max batch size** and **maximum wait time** to backlog, latency SLOs, and downstream throughput rather than blindly picking maximums.

## 4. Receive, Visibility Timeout, and Acknowledgment Mechanics

### 4.1. A message can be redelivered

~~~mermaid
sequenceDiagram
    participant Q as Amazon SQS
    participant W as Worker
    participant D as Database
    W->>Q: ReceiveMessage
    Q-->>W: message + receiptHandle; visibility timeout starts
    W->>D: Process and commit
    D-->>W: Commit succeeds
    alt Delete confirmed
        W->>Q: DeleteMessage(receiptHandle)
        Q-->>W: Accepted
    else Worker crashes before Delete
        Note over Q: Visibility timeout expires
        Q-->>W: Same message may be redelivered
    end
~~~

The **receipt handle** is the token required to delete or modify visibility for a **specific receive attempt**. It is **different from `MessageId`**. When a message is redelivered, the receipt handle can change; operating with an old receipt handle may no longer work as expected.

### 4.2. Choosing visibility timeout

`VisibilityTimeout` is how long a message stays hidden after receive so the worker can process and delete it. Too short lets another consumer pick up the message while the first is still running; too long delays crash recovery.

Example:

~~~text
P50 processing:  2 seconds
P99 processing: 25 seconds
Visibility:     60 seconds (illustrative starting point)
~~~

If jobs occasionally run for several minutes, the worker can call `ChangeMessageVisibility` while making progress. Enforce a **total duration cap** and handle visibility-update failures—never extend a stuck message forever.

### 4.3. When to delete?

A practical rule:

~~~text
Receive → validate → idempotency check → side effects committed
        → DeleteMessage using receipt handle
~~~

For a payment notification, “side effect committed” might mean durably writing an event/outbox row to a database rather than waiting on every downstream email/SMS provider. Still, the contract must be explicit: deleting a message after buffering it only in RAM risks losing work on a crash.

### 4.4. Retention, delay, and DLQ

- **Message retention** caps how long a message can sit in a queue; SQS typically allows **1 minute to 14 days**.
- **Delivery delay** defers new messages (commonly up to **15 minutes**) but does not replace a general scheduler.
- **Redrive policy** moves messages to a **DLQ** once receives exceed `maxReceiveCount` per SQS rules.
- **A DLQ does not replace observability:** alert on DLQ message counts/age and diagnose failures before redriving.

With Standard queues, messages may arrive duplicated and out of order. With FIFO, handle failures per **message group** so later messages do not leapfrog a failing message.

## 5. Long Polling and Polling Cadence

Custom consumers typically call `ReceiveMessage` in a loop. When a queue is empty, tight loops with `WaitTimeSeconds=0` (short polling) generate floods of empty responses.

**Long polling** lets SQS hold the request open waiting for messages, up to **20 seconds** under standard API limits:

~~~text
ReceiveMessage:
  MaxNumberOfMessages = 10
  WaitTimeSeconds     = 20
  VisibilityTimeout   = 60
~~~

When the queue is empty, the request waits; when messages arrive early, it can return immediately. Long polling cuts empty API calls and related cost, though it does not manage downstream concurrency.

### 5.1. Consumer loops must not busy-spin

~~~text
BAD:
  while true:
    receive(WaitTimeSeconds=0)
    if empty: continue immediately

BETTER:
  while running and capacity available:
    receive(MaxNumberOfMessages<=10, WaitTimeSeconds=20)
    process with bounded concurrency
    delete completed messages
    retry/backoff on poller errors
~~~

In custom pollers, avoid pulling 10 more messages when all worker threads and DB connections are busy. Over-fetching and buffering messages “in flight” in RAM risks expiring their visibility timeouts before processing even begins.

### 5.2. HTTP client timeout constraints

The AWS SDK's HTTP client must use a **request/socket timeout longer than the expected long poll**, plus connection/network overhead. If the SDK HTTP timeout is 5 seconds while `WaitTimeSeconds=20`, the client times out prematurely and triggers wasteful retries.

## 6. Backpressure: Controlling Pressure Before Overload

**Backpressure** prevents upstream flows from **pushing work into downstream systems faster than they can safely serve**. With a queue:

~~~text
Producer rate = λ messages/sec
Consumer throughput = μ messages/sec

If λ > μ for a sustained period:
  backlog grows steadily, processing latency climbs

If μ > λ while backlog exists:
  backlog drains gradually
~~~

A queue is a buffer—**it does not conjure compute out of thin air**. If producers emit 2,000 msg/s while downstream sustains at most 200 msg/s continuously, backlog grows until you throttle producers, optimize processing, scale effectively, or adjust the architecture.

### 6.1. Layers needing backpressure

| Layer | Overload symptom | Control mechanism |
| --- | --- | --- |
| **Producer → SQS** | Traffic exceeds quotas, invalid messages, duplicate requests | Admission control, token bucket, batching, jittered retries |
| **SQS → consumer** | Excessive in-flight count, saturated CPU/memory/threads | Bounded concurrency, low prefetch, capped autoscaling |
| **Consumer → database** | Exhausted DB connection pool, 429/503, lock contention | Semaphores, rate limits, connection pool caps, circuit breakers |
| **Consumer → partner API** | Rate limits / timeouts | Honor `Retry-After`, exponential backoff, dedicated queue for slow calls |
| **Consumer → outputs** | Slow replies or callback failures | Durable state, async retries, DLQ, high-age backlog alerts |

### 6.2. Bounded concurrency matters more than “spin up as many as possible”

Suppose a database safely handles at most **40 concurrent writes**. Launching 100 ECS tasks with 20 DB threads each can unleash **2,000 concurrent queries**—far beyond 40. The result is DB queueing, rising latency, timeouts, and synchronized retries, making overall throughput **drop** despite having more workers.

Design guidelines:

- Cap concurrency to **downstream capacity**: total DB writers/tokens across the entire fleet must stay within benchmarked limits.
- Use bounded connection pools and **bounded** internal queues.
- When processing slots are full, pause polling or scale down workers; **never buffer unbounded messages in RAM**.
- Apply **exponential backoff + jitter** on transient errors, distinguishing permanent errors (schema/permissions).
- For per-tenant fairness, split queues or apply fair scheduling/quotas so noisy tenants do not starve all workers.

### 6.3. Rate limiters and circuit breakers

Example where consumers call a partner with a 100 requests/sec quota:

~~~text
Consumer fleet demand: 300 req/s
Partner quota:         100 req/s

Solution:
  - Fleet-wide rate limit ~100 req/s or lower with safety margin;
  - Queue holds remaining work until its turn;
  - On 429, honor Retry-After when provided;
  - Backoff with jitter and bounded retry attempts;
  - Trip a circuit breaker during prolonged outages;
  - Route unprocessable work to DLQ / retry queue.
~~~

**Note:** a rate limit inside **each task** does not enforce a **fleet-wide** cap as task count scales. You may need a token distributor, distributed limiter, quota-aware coordination, or a dedicated queue for rate-limited APIs.

### 6.4. Preventing retry storms

When downstream returns `503`:

1. Consumers may retry immediately within the same invocation.
2. Visibility timeouts expire, prompting SQS redelivery.
3. Autoscalers add more consumers because backlog grows.
4. More workers hammer the failing downstream even harder.

Unchecked, this becomes a **retry storm**. Layer retries with clear error classification and budgets, cap concurrency, add jitter, use DLQs/scheduled retries, and pause or throttle consumers when downstream is unhealthy.

## 7. Consumer Scaling: Use Business Metrics Instead of CPU Alone

An ECS worker spends much of its time **waiting on the queue** when idle, so low CPU does not tell you how many workers are needed. Conversely, a worker at 5% CPU waiting 5 seconds per partner API call may process only a handful of messages per second.

Key signals:

| Metric | Source | How to interpret |
| --- | --- | --- |
| `ApproximateNumberOfMessagesVisible` | SQS CloudWatch | Approximate number of messages ready to receive |
| `ApproximateNumberOfMessagesNotVisible` | SQS CloudWatch | Approximate number of in-flight messages |
| `ApproximateAgeOfOldestMessage` | SQS CloudWatch | Wait time of oldest message per metric semantics |
| `NumberOfMessagesSent` | SQS CloudWatch | Enqueue rate (measured messages, not necessarily unique business jobs) |
| `NumberOfMessagesReceived` | SQS CloudWatch | Receive rate; includes redeliveries |
| `NumberOfMessagesDeleted` | SQS CloudWatch | Delete operations recorded; not necessarily unique completed jobs |
| **Processing duration / success rate** | Application metrics | Actual worker speed, errors, and completions |
| **RunningTaskCount / concurrent Lambda** | ECS/CloudWatch | Active compute count, not useful throughput by itself |
| **DLQ depth and age** | SQS CloudWatch | Accumulating unprocessable work |

SQS metrics prefixed with **Approximate** are estimates with CloudWatch aggregation lag. Never treat them as exact transactional counts or assume second-by-second real-time precision.

### 7.1. Backlog per task

A common autoscaling metric for ECS:

~~~text
BacklogPerTask
  = ApproximateNumberOfMessagesVisible / RunningTaskCount

TargetBacklogPerTask
  ≈ acceptableQueueWaitSeconds
    × messagesProcessedPerSecondPerTask
~~~

For example, if one task sustainably processes **20 msg/s** and acceptable queue wait is **30 seconds**:

~~~text
Target backlog per task ≈ 20 × 30 = 600 messages

If visible backlog = 6,000 messages:
  Target task count by backlog ≈ 6,000 / 600 = 10 tasks
~~~

This is a **heuristic**, not a p99 latency guarantee: arrival rates, downstream concurrency, networking, queue semantics, scale-out lag, and in-flight messages all matter. In CloudWatch metric math, guard against `RunningTaskCount=0` to avoid division by zero and configure a sensible **min capacity**.

### 7.2. Throughput and backlog drain formulas

Suppose:

~~~text
Incoming rate λ = 600 msg/s
Each worker processes μ = 40 msg/s

Minimum workers to keep up with ingress:
  ceil(600 / 40) = 15

With ~25% headroom above minimum workers:
  ceil(15 × 1.25) = 19 workers
~~~

Backlog drain example:

~~~text
Current backlog B = 60,000 messages
Incoming during drain = 400 msg/s
20 workers × 35 msg/s/worker = 700 msg/s
Net drain rate = 700 - 400 = 300 msg/s

Ideal drain time ≈ 60,000 / 300 = 200 seconds
~~~

**200 seconds is an idealized estimate** assuming constant throughput, zero failed retries, unthrottled downstream systems, and already-warm workers. For real SLOs, factor in scale-out lag, cold starts, queue polling, long-tail tasks, and safety margins.

### 7.3. Scale on age or backlog?

- **Backlog count** reflects pending work volume and maps cleanly to task allocation.
- **Age of oldest message** reflects SLO breach risk and excels for alerting, though poison-message/DLQ semantics can skew single-point age readings.
- **Processing duration** governs real throughput: 1,000 tiny thumbnails are completely different from 1,000 long videos.
- **Downstream health** sets the concurrency ceiling: scaling up simply because backlog rose during a DB outage worsens the incident.

A strong strategy combines **backlog-per-task target tracking** with **message-age/DLQ alarms**, min/max capacity bounds, and downstream guardrails.

## 8. Lambda Consumers: Event Source Mapping and Batching

**AWS Lambda** integrates with Amazon SQS via **event source mapping (ESM)**. Lambda's pollers pull messages from SQS, package them into function event batches, adjust concurrency via ESM scaling, and delete successfully processed messages.

### 8.1. What makes up an event source mapping?

| Parameter | Meaning | Notes |
| --- | --- | --- |
| `EventSourceArn` | ARN of the SQS queue | Queue and function must comply with Region/feature rules |
| `BatchSize` | Max messages per invocation | Standard supports larger batches; FIFO has a smaller cap |
| `MaximumBatchingWindowInSeconds` | Wait window to gather larger batches | Improves batch efficiency at the cost of added latency |
| `FunctionResponseTypes: ReportBatchItemFailures` | Lets the function return IDs of failed messages | Avoids retrying the whole batch when only a subset fails |
| `ScalingConfig.MaximumConcurrency` | Caps concurrency used by this mapping, when supported | Protects databases and dependencies |
| `FilterCriteria` | Filters messages using ESM-supported patterns | Understand impact on filtered-out messages and business data |

Common limits: SQS Standard mappings can receive **batches larger than 10** (up to **10,000** records in supported configurations), whereas FIFO caps at a **maximum batch of 10**. Setting `BatchSize > 10` on Standard requires configuring a batching window per service rules (typically at least **1 second**). Beyond record count, the **invocation payload size limit** also applies; a batch can close early due to byte size.

This is a **Lambda event batch**, not a custom Java `ReceiveMessage` call. Lambda ESM performs **multiple SQS receive calls** under the hood to assemble up to `BatchSize`/window before invoking; never assume a single SQS Receive API call returns 1,000 records.

### 8.2. Default behavior when one record fails

Suppose an invocation receives:

~~~text
Batch: [m1, m2, m3, m4, m5]
m1 → success
m2 → success
m3 → downstream error
m4 → success
m5 → success
~~~

If the handler **throws an error for the whole invocation** without a partial batch response, the entire batch can be marked failed and already-processed messages can return after visibility expires. **Never assume each Lambda invocation contains only one message.**

Conversely, catching the error and returning invocation success lets Lambda **delete failed messages**, losing work. Simply catching and logging **is not enough**; return the exact contract so failures are not falsely acknowledged.

### 8.3. Partial batch responses

With `ReportBatchItemFailures` enabled on the event source mapping, the function returns failed IDs:

~~~json
{
  "batchItemFailures": [
    { "itemIdentifier": "m3" }
  ]
}
~~~

With a valid partial batch response, Lambda deletes m1, m2, m4, and m5 and **leaves m3 for retry** per SQS retry/visibility rules. `itemIdentifier` must be the **SQS `messageId`**, not the receipt handle or business order ID.

**Mandatory requirement:** `ReportBatchItemFailures` must be enabled on the event source mapping. Returning this JSON without enabling it on the mapping will not produce the desired retry behavior.

### 8.4. Illustrative Node.js Lambda code for Standard queues

~~~javascript
// Lambda Node.js example: Standard SQS trigger.
// processDurablyIdempotent must implement your business logic
// with durable storage and idempotency keys.
async function processDurablyIdempotent(record) {
  // Pseudocode: validate schema, insert unique eventId,
  // commit business side effects, never swallow errors.
  throw new Error("Implement real business logic before use");
}

exports.handler = async (event) => {
  const failed = [];

  for (const record of event.Records) {
    try {
      await processDurablyIdempotent(record);
    } catch (error) {
      console.error("Message failed", {
        messageId: record.messageId,
        errorType: error.name
      });
      failed.push({ itemIdentifier: record.messageId });
    }
  }

  return { batchItemFailures: failed };
};
~~~

**The snippet above illustrates the contract and intentionally omits business logic**, marking all messages failed if run verbatim. That is safer than a stub pretending to “succeed” without durable commits. Production must implement `processDurablyIdempotent` before attaching triggers, alongside metrics, error policies, and alarms.

For large batches, sequential processing can lengthen invocations. For independent Standard-queue jobs, process concurrently with **bounded concurrency**—never unbounded `Promise.all` firing thousands of DB calls at once—and track each record's outcome accurately.

### 8.5. FIFO: stop on the first failure to protect ordering

For FIFO, ordering must hold within each **`MessageGroupId`**. When using `ReportBatchItemFailures` with FIFO, AWS recommends **stopping on the first error** and returning **both the failed message and all unprocessed messages** in `batchItemFailures` so later items never bypass a failure.

~~~javascript
async function processDurablyIdempotent(record) {
  throw new Error("Implement real business logic before use");
}

exports.handler = async (event) => {
  for (let i = 0; i < event.Records.length; i++) {
    try {
      await processDurablyIdempotent(event.Records[i]);
    } catch (error) {
      console.error("FIFO batch stopped at failing record", {
        messageId: event.Records[i].messageId
      });
      return {
        batchItemFailures: event.Records.slice(i).map((r) => ({
          itemIdentifier: r.messageId
        }))
      };
    }
  }
  return { batchItemFailures: [] };
};
~~~

This sample intentionally stops the whole batch on error for simplicity. Production code may group by `MessageGroupId` to optimize across independent groups, but **must never process past a failing item in the same group**.

### 8.6. Visibility timeout for Lambda SQS triggers

AWS recommends setting queue visibility timeout to **at least ~6 times the Lambda function timeout**, plus the batching window if configured, giving Lambda room to retry if invocations are throttled or fail. For example, a 30-second function timeout with a 5-second batching window starts around **185 seconds or more**:

~~~text
6 × 30 seconds + 5 seconds = 185 seconds
~~~

This is a **configuration guideline**, not a guarantee an invocation uses that full span. Check current service rules and SQS visibility caps. Too short risks concurrent duplicate execution while the first invocation runs; too long delays retries and DLQ routing.

### 8.7. Lambda concurrency caps

Allowing Lambda concurrency to spike unboundedly when a queue grows can cause:

- Database connection exhaustion.
- Third-party APIs returning **429 Too Many Requests**.
- Account/Region Lambda concurrency exhaustion affecting other triggers.
- Increased cold starts and KMS/Secrets/connection setup pressure.

Consider:

- Mapping-level `ScalingConfig.MaximumConcurrency` where supported.
- Function `ReservedConcurrency` and any other triggers sharing the function.
- Account/Region quotas and downstream capacity.
- How backlog queues up once the cap is hit; alert if `ApproximateAgeOfOldestMessage` breaches SLOs.

Never set `MaximumConcurrency` higher than databases or APIs can sustain simply because Lambda can scale fast.

## 9. Custom Consumers on ECS/EC2: Controlling Polling and Parallelism

For long-running continuous tasks, native/Java libraries, or fine-grained thread-pool control, **ECS/Fargate or EC2 workers** are a strong fit. You own polling, batching, deletion, scaling, deployments, and graceful shutdown.

### 9.1. Parameters of a Java poller

~~~text
Per worker container:
  Polling threads:             1..N, by design
  ReceiveMessage max records:  10
  WaitTimeSeconds:             20
  Local processing slots:      8
  Database max concurrency:    sized fleet-wide, not just per task
  VisibilityTimeout:           greater than expected processing time
  Graceful shutdown:           stop receiving, finish/extend active work
~~~

If a task fetches 10 messages while having only two slots, eight messages sit idle in memory with their visibility timers ticking down. A healthy worker enforces **poller-level backpressure**: receive only when slots are free or remaining visibility is guaranteed.

### 9.2. Java AWS SDK v2: `SendMessageBatch` producer

The following is a **Java fragment** using `software.amazon.awssdk:sqs`; replace the queue URL and body with lab values.

~~~java
import java.util.List;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sqs.model.SendMessageBatchRequest;
import software.amazon.awssdk.services.sqs.model.SendMessageBatchRequestEntry;
import software.amazon.awssdk.services.sqs.model.SendMessageBatchResponse;

String queueUrl = "https://sqs.ap-southeast-1.amazonaws.com/"
    + "123456789012/jobs-lab";

try (SqsClient sqs = SqsClient.builder()
        .region(Region.AP_SOUTHEAST_1).build()) {
    List<SendMessageBatchRequestEntry> entries = List.of(
        SendMessageBatchRequestEntry.builder()
            .id("a")
            .messageBody("{\"eventId\":\"evt-101\"}")
            .build(),
        SendMessageBatchRequestEntry.builder()
            .id("b")
            .messageBody("{\"eventId\":\"evt-102\"}")
            .build());

    SendMessageBatchResponse response = sqs.sendMessageBatch(
        SendMessageBatchRequest.builder()
            .queueUrl(queueUrl)
            .entries(entries)
            .build());

    response.successful().forEach(s ->
        System.out.println("Sent: " + s.id() + " -> " + s.messageId()));

    response.failed().forEach(f ->
        System.err.println("Failed: " + f.id() + " / "
            + f.code() + " / senderFault=" + f.senderFault()));

    // Production: retry only failed retryable entries;
    // never replay already-succeeded entries in the batch.
}
~~~

This demonstrates a **queue-mutating operation**; **do not run** against production. The SDK resolves credentials via the standard provider chain (task role/instance profile/SSO)—never hardcode AWS access keys. Place fragments inside an appropriate Java method in real code.

### 9.3. Java AWS SDK v2: receiving and deleting only succeeded messages

~~~java
import java.util.ArrayList;
import java.util.List;
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sqs.model.*;

// sqs and queueUrl initialized by application class.
ReceiveMessageResponse response = sqs.receiveMessage(
    ReceiveMessageRequest.builder()
        .queueUrl(queueUrl)
        .maxNumberOfMessages(10)
        .waitTimeSeconds(20)
        .visibilityTimeout(60)
        .build());

List<DeleteMessageBatchRequestEntry> deletions = new ArrayList<>();
int nextId = 0;

for (Message m : response.messages()) {
    try {
        // Business method MUST commit durably and idempotently,
        // throwing an exception if incomplete.
        businessService.processIdempotently(m.body(), m.messageId());

        deletions.add(DeleteMessageBatchRequestEntry.builder()
            .id("del-" + nextId++)
            .receiptHandle(m.receiptHandle())
            .build());
    } catch (Exception error) {
        // Do not delete failed message; let retry/DLQ policy handle it.
        log.warn("Processing failed, messageId={}", m.messageId(), error);
    }
}

if (!deletions.isEmpty()) {
    DeleteMessageBatchResponse deleted = sqs.deleteMessageBatch(
        DeleteMessageBatchRequest.builder()
            .queueUrl(queueUrl)
            .entries(deletions)
            .build());
    deleted.failed().forEach(f ->
        log.error("Delete failed: {} / {}", f.id(), f.code()));
}
~~~

**This is an architectural fragment, not a standalone runnable Java class:** `sqs`, `queueUrl`, `businessService`, and `log` must be injected. It demonstrates that **only committed messages are added to `DeleteMessageBatch`**.

Mandatory production upgrades:

- Map `DeleteMessageBatchRequestEntry.Id` back to its message/receipt handle so failed deletes can be retried.
- Catch and classify **API call-level exceptions** (timeouts, throttling, IAM), not just `deleted.failed()`.
- Use a durable idempotency key from the business event instead of assuming `messageId` stays invariant across retries or re-enqueues.
- Pause polling when local capacity is full, handle process shutdown, and extend visibility on long tasks.
- For FIFO, preserve `MessageGroupId` ordering; never run two messages from the same group concurrently if doing so breaks semantics.

### 9.4. Why not delete the whole batch when only part succeeded?

Suppose 10 messages are received and only 7 succeed:

~~~text
10 received:
  7 committed → delete 7
  2 transient errors → let retry per visibility/retry policy
  1 permanent validation error → route per error/DLQ policy; don't hot-retry
~~~

If the consumer sends `DeleteMessageBatch` for all 10, **the 3 failed jobs risk being lost**. If it throws and deletes nothing, **the 7 succeeded jobs get reprocessed**. The solution is **per-message acknowledgment** backed by idempotency and retry policies.

### 9.5. Clean shutdown for ECS services

During ECS scale-in or new image rollouts:

1. Worker receives `SIGTERM`.
2. Stops starting new `ReceiveMessage` calls.
3. Waits for bounded in-flight tasks to finish, extending visibility if needed.
4. Deletes messages that committed successfully.
5. Exits within the configured stop timeout; any unfinished messages reappear after visibility expires.

In multi-AZ deployments, never rely solely on in-memory RAM state as proof of completion. Workers can die at any moment.

## 10. FIFO Ordering, Message Groups, and Throughput Trade-Offs

A FIFO queue guarantees **ordering within each message group**, not a single queue that scales infinitely in parallel.

~~~text
FIFO queue:
  Group order#A: A1 → A2 → A3 → A4
  Group order#B: B1 → B2 → B3

A1 and B1 can process concurrently when conditions allow.
Never treat A2 as complete before A1 if order#A requires sequence.
~~~

### 10.1. Choosing `MessageGroupId`

- **By order ID:** events for one order stay sequential; different orders run in parallel.
- **By customer ID:** preserves per-customer order; highly active customers can become hot groups.
- **One fixed `"global"` value for all messages:** simple to code, yet **needlessly bottlenecks concurrency** across the entire queue.

`MessageGroupId` should represent **actual ordering boundaries**, not an arbitrary random string for load balancing. Having huge numbers of groups also requires checking throughput quotas, storage, and downstream consistency.

### 10.2. Deduplication does not replace idempotency

FIFO provides deduplication within an SQS-defined window (commonly **5 minutes**). Producers can supply `MessageDeduplicationId` or enable content-based dedup where appropriate.

However:

- After the dedup window expires or when an event is re-enqueued, business duplicates can still arrive.
- If a worker commits to the DB but `Delete` fails, the message can still be redelivered.
- If `MessageDeduplicationId` changes across retries of the same business event, dedup cannot help.

Durable idempotency in the business datastore—such as a unique constraint on `eventId` or a DynamoDB conditional write—remains the primary safeguard.

### 10.3. FIFO and partial failures

In a FIFO batch:

- Ensure no message is processed after a failing element in the same group.
- With Lambda `ReportBatchItemFailures`, stop at the first error and return IDs for **failed + unprocessed** items per AWS guidance.
- With custom ECS consumers, commit and delete sequentially per group using a clear worker/partition coordination model.
- DLQs can disrupt business order when messages leave the queue; if strict absolute ordering is mandatory, evaluate DLQ usage carefully.

Never trade order integrity just to squeeze out more concurrency.

## 11. Idempotency: Essential Requirement for Batch Processing

### 11.1. Side effects occurring twice

~~~mermaid
sequenceDiagram
    participant Q as SQS
    participant W as Consumer
    participant DB as Database
    W->>Q: Receive eventId=evt-101
    Q-->>W: receiptHandle H1
    W->>DB: INSERT delivery record
    DB-->>W: Commit succeeds
    Note over W: Crash before Delete
    Q-->>W: Redelivery evt-101 with receiptHandle H2
    W->>DB: Attempt INSERT again
    DB-->>W: Unique eventId already exists
    W->>Q: DeleteMessage H2
~~~

Without duplicate detection, a system could create two shipments or send two emails. In some workflows duplicate emails are merely annoying; in payments, duplicates can be catastrophic.

### 11.2. Database unique event ID pattern

Suppose table `processed_events` has unique key `event_id`:

~~~sql
BEGIN;

INSERT INTO processed_events(event_id, processed_at)
VALUES ('evt-101', CURRENT_TIMESTAMP);

-- Only when unique insert succeeds:
UPDATE orders SET status = 'READY_TO_SHIP'
WHERE order_id = 'order-101';

COMMIT;
~~~

This SQL illustrates the concept; application code must also:

- Catch **unique conflicts** for already-processed events and treat them as valid idempotent no-ops once the target state exists.
- Perform **marker insertion and business update in the same transaction** so the marker never commits without the business change.
- For side effects calling **external APIs outside the database**, use outboxes, provider idempotency keys, or durable state machines; a local DB transaction is not atomic with external systems.
- Keep idempotency keys long enough to cover the full retry/replay window; never purge markers prematurely.

### 11.3. Payment systems

For payments, use a **business-level idempotency key** such as `paymentId` or a trusted `eventId` from the event emitter. Never rely on `MessageId` as a payment transaction identifier when events may be routed across queues or republished with new `MessageId`s.

## 12. Dead-Letter Queues and Poison Message Handling

A **poison message** is one that repeatedly fails consumer processing—for instance due to schema errors, missing IDs, or unauthorized operations.

~~~mermaid
flowchart LR
    Q["Source SQS queue"] --> C["Consumer"]
    C -->|"Success"| DONE["Delete message"]
    C -->|"Transient error"| WAIT["Visibility expires + retry"]
    WAIT --> Q
    Q -->|"Receive count exceeds threshold"| DLQ["SQS DLQ"]
    DLQ --> REVIEW["Investigate root cause\nClassify + decide fix"]
    REVIEW -->|"Controlled redrive"| Q
~~~

### 12.1. What should `maxReceiveCount` be?

No single value suits every workload:

| Scenario | Considerations |
| --- | --- |
| Brief network/timeout glitches | Allow a few retries with backoff |
| Prolonged partner API outage | Defer to a retry queue instead of hot-looping |
| Invalid JSON/schema | Fix producer or route to DLQ early; do not spam retries |
| IAM/permanent permission errors | Alert engineers and fix policies; retries alone will not heal |

**Do not set `maxReceiveCount` too low** if transient errors occur, nor so high that poison messages linger and degrade backlog-age SLOs.

### 12.2. A DLQ does not fix data automatically

A DLQ runbook:

1. Monitor DLQ message counts and age.
2. Sample payloads **within data-access permissions** and inspect error context in logs/traces.
3. Classify the failure: producer schema, IAM, dependency, bug, or expired business state.
4. Fix the root cause or record an explicit decision that the message is **unprocessable**.
5. Run **redrive** with a rate limit suited to downstream capacity; verify idempotency.
6. Verify outcomes post-redrive and keep an audit trail.

SQS supports **DLQ redrive** mechanisms subject to API rules and conditions. Large-scale redrives also create traffic bursts and need the same backpressure controls as normal ingress. Grant IAM and queue policies strictly scoped to required source/destination queues.

### 12.3. DLQ retention duration

In Standard queues, message age calculation after moving to a DLQ differs from FIFO. When choosing DLQ retention, AWS generally recommends **setting DLQ retention longer than source queue retention** to allow investigation time. Never look solely at `ApproximateAgeOfOldestMessage` to judge total data age; cross-check original enqueue/first-received timestamps when precision matters.

### 12.4. When a DLQ is not the only answer

If all messages fail because a downstream service is down for 2 hours, dumping everything into a DLQ only to redrive later may be suboptimal. Instead, you can **throttle or pause consumers**, hold the backlog in the source queue, or route to a delayed retry queue by error type—balancing message retention, SLOs, and prioritization of fresh work.

## 13. Scaling Consumers with ECS/Fargate

When running workers as an **ECS service**, you can scale task counts via **Service Auto Scaling**. For SQS workloads, queued message count is usually a far better signal than CPU utilization alone.

### 13.1. Autoscaling flow

~~~mermaid
flowchart LR
    Q["SQS queue\nvisible backlog"] --> METRIC["CloudWatch metric\nbacklog per running task"]
    RUN["ECS running tasks\ncurrent capacity"] --> METRIC
    METRIC --> POLICY["Application Auto Scaling\ntarget tracking/custom policy"]
    POLICY --> ECS["ECS Service\nDesiredCount"]
    ECS --> WORK["Worker tasks\nbounded concurrency"]
    WORK --> DB["Database / APIs\ncapacity guardrails"]
    WORK -->|"Delete on success"| Q
~~~

An operational setup might:

- Keep a **minimum desired count** for fast response and to avoid divide-by-zero metrics when messages arrive.
- Cap **maximum desired count** by ECS/Fargate quotas, VPC IP space, DB/API limits, and budget.
- Publish a **custom CloudWatch metric** for backlog-per-running-task or use supported metric math.
- Use target tracking on target messages per task, setting **scale-in/scale-out cooldowns** aligned with task startup and processing duration.
- Implement **graceful shutdown** and bounded in-flight work so scale-in does not dump huge batches back onto the queue simultaneously.

### 13.2. SLO-driven policy example

Suppose:

~~~text
SLO: messages must begin processing within 30 seconds (queue wait)
1 worker sustains: 25 msg/s
Target backlog per worker: 25 × 30 = 750 visible messages

Downstream-capped max workers: 30 tasks
Target desired count:
  ceil(VisibleBacklog / 750), clamped to [minTasks, 30]
~~~

If visible backlog jumps to 45,000, ideal capacity is `ceil(45000/750) = 60` tasks, **yet `maxTasks = 30`** because downstream cannot handle more. The system cannot satisfy both the 30-second wait SLO and the downstream limit during this surge; an explicit **business decision** is needed: tolerate higher latency, throttle producers, optimize downstream, or expand downstream capacity first.

**Autoscaling never bypasses backpressure.** Capping concurrency to real capacity matters more than making backlog charts look flat.

### 13.3. Scale-in and in-flight work

When backlog drops, the autoscaler reduces task count while a task may still be processing a batch:

~~~text
ECS service sends SIGTERM
→ worker stops new ReceiveMessage calls
→ finishes/commits in-flight messages
→ deletes succeeded messages
→ releases unfinished messages to retry after visibility
→ exits
~~~

Designing stop timeouts, visibility extensions, and idempotency prevents disruption during deployments and scale-ins. Avoid `minTasks=0` unless scale-from-zero triggers (metrics, alarms, target tracking, startup latency) are thoroughly verified.

### 13.4. Autoscaling does not solve queue priority

If one queue mixes:

- Regular notifications: 100,000 messages.
- Urgent refunds: 20 messages.

Workers may chew through mountains of regular notifications before reaching urgent work. SQS Standard **does not act as a priority queue** just because a `priority` field sits in the body. Use **separate queues** (urgent vs. normal) with dedicated worker pools or fair scheduling. Never assume adding more workers enforces priority.

## 14. Connecting SNS, EventBridge, and SQS

### 14.1. Fan-out via SNS

An `order.placed` event may need to reach:

- Inventory service.
- Email notification service.
- Fraud screening service.

Instead of the producer publishing three messages to three queues, use **an SNS topic → multiple SQS subscriptions**:

~~~mermaid
flowchart TB
    P["Order Service"] --> SNS["Amazon SNS Topic\norder-events"]
    SNS --> Q1["SQS queue: inventory"]
    SNS --> Q2["SQS queue: email"]
    SNS --> Q3["SQS queue: fraud-check"]
    Q1 --> W1["Inventory consumer"]
    Q2 --> W2["Email consumer"]
    Q3 --> W3["Fraud consumer"]
~~~

**Benefit:** each team gets an isolated queue with independent backlog, retries, DLQ, and scaling. If the email provider returns 429s, you can throttle email consumers without slowing down Fraud workers.

### 14.2. SNS filter policies and message envelopes

SNS subscription filter policies keep irrelevant notifications out of a queue. When SNS delivers to SQS, the body contains either an **SNS notification envelope** or the original payload depending on whether **raw message delivery** is enabled. Consumers must parse the exact configured format—never assume producer JSON arrives unwrapped if passing through SNS.

### 14.3. Queue policy for SNS

Example **SQS queue resource policy** allowing only one SNS topic to deliver to the queue:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowOnlyOrderEventsTopic",
      "Effect": "Allow",
      "Principal": { "Service": "sns.amazonaws.com" },
      "Action": "sqs:SendMessage",
      "Resource": "arn:aws:sqs:ap-southeast-1:123456789012:inventory-queue",
      "Condition": {
        "ArnEquals": {
          "aws:SourceArn": "arn:aws:sns:ap-southeast-1:123456789012:order-events"
        }
      }
    }
  ]
}
~~~

Illustrative only: configure IAM/KMS permissions if the queue uses SSE-KMS and enforce source-account or organizational conditions per policy. Never use `Principal: "*"` or broad resources unnecessarily. When the source is EventBridge, principals, conditions, and integration patterns differ from SNS.

### 14.4. What does EventBridge do?

**EventBridge** excels when routing and filtering events by source, event type, and payload structure; rules can target SQS queues where supported. EventBridge does not replace consumer retry and acknowledgment semantics once events enter SQS.

When choosing between SNS and EventBridge, weigh:

- Event schemas, filtering, and routing needs.
- Ordering/deduplication requirements and target support.
- Failure handling: DLQ for **event delivery to the queue** versus DLQ for **consumer processing after queue delivery**—two distinct failure stages.
- IAM/resource policies, per-message/request pricing, and latency.

## 15. Security, IAM, and Data Protection

### 15.1. Which principal needs which permissions?

| Component | Relevant AWS permissions | Why |
| --- | --- | --- |
| **Producer** | `sqs:SendMessage` | Push one message to the queue |
| **Batch producer** | `sqs:SendMessage` (covers the `SendMessageBatch` API) | Send multiple messages via batch API |
| **Custom consumer** | `sqs:ReceiveMessage`, `sqs:DeleteMessage`, `sqs:ChangeMessageVisibility`, `sqs:GetQueueAttributes` | Poll, ack, extend visibility, and inspect queue attributes |
| **Lambda SQS event source** | Execution role with SQS polling/deleting permissions | Lets Lambda pollers read and delete messages |
| **DLQ operator** | Permissions to inspect, triage, and redrive queues per IAM and redrive policies | Controlled recovery |
| **SNS/EventBridge publisher** | `sqs:SendMessage` in queue resource policy from trusted source | Allows service delivery to target queue |
| **KMS** | `kms:GenerateDataKey`, `kms:Decrypt`, or matching grants for customer-managed keys | Allows producers/consumers to use SSE-KMS queues per policy |

**Distinguish API names from IAM action names:** `SendMessageBatch` requires `sqs:SendMessage`; likewise, `DeleteMessageBatch` requires `sqs:DeleteMessage`, and `ChangeMessageVisibilityBatch` requires `sqs:ChangeMessageVisibility`. Never assume every batch API name corresponds to a distinct IAM action. Verify against the current **AWS Service Authorization Reference** before applying policies, and scope permissions to **specific queue ARNs** rather than `sqs:*`.

### 15.2. Separate IAM roles for producers and consumers

For example, with ECS/Fargate:

- **Producer task role** can only send messages to `jobs-queue`.
- **Consumer task role** receives/deletes/updates visibility on that queue and calls authorized downstream services.
- **ECS task execution role** (for ECR/logging/secrets) should not double as the application's business role.

For Lambda consumers, the execution role needs matching SQS permissions plus KMS permissions if the queue uses a customer-managed SSE-KMS key. Missing permissions can stop pollers from receiving messages even while producers succeed.

### 15.3. Data hygiene in messages

SQS bodies and attributes can hold sensitive data; never treat SQS as public space just because it is “a queue”:

- **Never store passwords, long-lived tokens, or payment card details** in messages unnecessarily.
- Pass IDs and look up sensitive records via authorized APIs where appropriate.
- Enable **server-side encryption** and manage KMS keys properly.
- Apply VPC endpoint policies, IAM, CloudTrail, and queue policies as needed.
- Log `messageId`, `eventId`, and status; avoid logging full bodies containing PII.
- Set **retention** and purge sensitive data in line with legal compliance.

### 15.4. Defending against spoofed client data

A producer might send:

~~~json
{
  "eventId": "evt-99",
  "orderId": "order-777",
  "status": "PAID"
}
~~~

Consumers should not blindly treat that body as proof of payment. Validate the source or verify state against the system of record, validate schemas, enforce authorization, and apply idempotency. A queue is a transport pipe—**it does not automatically make message contents trustworthy**.

## 16. Production Observability and SLO-Based Alerting

Define separate SLOs:

1. **Ingress SLO:** are producers able to enqueue messages?
2. **Queue wait SLO:** how long do messages wait before a consumer picks them up?
3. **Processing SLO:** once started, how long does processing take?
4. **End-to-end SLO:** how long from business event commit until downstream side effects finish?
5. **Failure/recovery:** how many messages retried, entered the DLQ, or expired retention?

### 16.1. Recommended dashboard

| Panel | Metric/source | How to use |
| --- | --- | --- |
| Visible backlog | `ApproximateNumberOfMessagesVisible` | Track waiting work |
| In-flight messages | `ApproximateNumberOfMessagesNotVisible` | Watch active or over-buffered work |
| Oldest message age | `ApproximateAgeOfOldestMessage` | Alert on queue-wait SLA breaches |
| Sent/received/deleted | `NumberOfMessagesSent/Received/Deleted` | Track ingress/processing trends (may include duplicates) |
| DLQ visible backlog | DLQ queue metrics | Detect poison messages |
| Lambda errors/duration/throttles | CloudWatch Lambda | Monitor trigger health and concurrency |
| ECS running/desired tasks | ECS Service / Container Insights | Compare actual vs. target capacity |
| DB pool, 429s, latency | Custom metrics / APM | Pinpoint downstream bottlenecks |
| Cost | AWS Cost Explorer / Budgets | Control API requests, Lambda/ECS, logs, and KMS spend |

If queue metrics drop while business errors climb, consumers may be **mistakenly deleting failed messages**. Always track application-level **business success counters** rather than assuming an empty queue means everything worked.

### 16.2. Meaningful alert thresholds

Suppose a team sets an SLO: 99% of notifications must be processed within 2 minutes.

~~~text
Warning:
  ApproximateAgeOfOldestMessage > 60 seconds sustained

Critical:
  ApproximateAgeOfOldestMessage > 120 seconds sustained
  or unexpected messages present in DLQ

Scale signal:
  BacklogPerRunningTask exceeds target backlog
  with cooldowns and DB/API-aligned max capacity
~~~

Thresholds are illustrative and must be calibrated to **metric lag**, burst patterns, FIFO group blocking, and workload shape. Add synthetic events or trace timestamps to measure end-to-end latency more accurately.

### 16.3. Avoiding misreadings of SQS metrics

- `NumberOfMessagesReceived` can count the same message received multiple times.
- `NumberOfMessagesDeleted` counts recorded delete requests per metric semantics, not unique business transactions.
- `ApproximateNumberOfMessagesVisible` has lag and estimation variance; it is not an exact transaction count.
- `ApproximateAgeOfOldestMessage` has specific semantics during retries/redrives; never equate it directly with p99 latency.
- A FIFO queue with **one stuck `MessageGroupId`** may hold many waiting messages while adding more consumers **cannot parallelize** that group.

## 17. Runbook for Sudden Backlog Spikes

Suppose a dashboard reports:

~~~text
Visible backlog: 150,000 messages, rising
Oldest age: 9 minutes
Consumer count: 20 ECS tasks
DB p99 latency: 5 seconds, connections near limit
DLQ: 0 messages so far
~~~

**Do not immediately scale from 20 to 200 tasks.** The DB is already saturated. Runbook:

1. **Verify the data:** confirm Region/account, verify backlog is real, check in-flight counts and arrival rate.
2. **Isolate the cause:** producer burst, consumer crashes, IAM, throttling, or DB latency? Check ECS/Lambda logs and APM.
3. **Stabilize downstream:** cap DB concurrency, safely scale DB capacity if feasible, and resolve lock/query bottlenecks.
4. **Relieve pressure:** shed non-critical producer load, prioritize urgent queues, enable circuit breakers and bounded retry backoff.
5. **Measure safe throughput:** as the DB recovers, establish sustainable msg/s per task.
6. **Scale with a cap:** increase tasks within DB/IP/quota bounds while watching message age and DB p99.
7. **Audit duplicates/DLQ:** after recovery, check retried/failed jobs and verify idempotency.
8. **Postmortem:** refine alarms, capacity runbooks, load tests, and queue-splitting plans.

### 17.1. When should you throttle producers?

If producer ingress exceeds safe total throughput over a long period, adding workers without expanding downstream capacity **will not clear the backlog**. Options include:

- Apply admission control or return HTTP `429`/`503` per contract for retryable requests.
- Rate-limit ingress by tenant or job class.
- Coalesce low-priority updates (e.g., keeping only the latest dashboard state) when business rules allow.
- Split urgent and non-urgent streams into separate queues.
- Enter a temporary degraded service mode instead of letting every request time out.

**Dropping messages** should be an explicit business policy, never an accidental side effect of queue retention expiring.

## 18. CloudFormation Configuration Example: SQS + DLQ + Lambda Mapping

The snippet below illustrates the relationship between an SQS source queue, DLQ, and event source mapping; **it omits the Lambda function and IAM role definitions**. Replace placeholders with real ARNs/functions in an authorized lab environment.

~~~yaml
AWSTemplateFormatVersion: '2010-09-09'
Description: SQS worker batching and partial failures (learning fragment)

Parameters:
  WorkerFunctionArn:
    Type: String

Resources:
  JobsDLQ:
    Type: AWS::SQS::Queue
    Properties:
      QueueName: jobs-lab-dlq
      MessageRetentionPeriod: 1209600  # 14 days

  JobsQueue:
    Type: AWS::SQS::Queue
    Properties:
      QueueName: jobs-lab
      VisibilityTimeout: 185
      MessageRetentionPeriod: 345600  # 4 days
      ReceiveMessageWaitTimeSeconds: 20
      RedrivePolicy:
        deadLetterTargetArn: !GetAtt JobsDLQ.Arn
        maxReceiveCount: 5

  JobsEventSourceMapping:
    Type: AWS::Lambda::EventSourceMapping
    Properties:
      EventSourceArn: !GetAtt JobsQueue.Arn
      FunctionName: !Ref WorkerFunctionArn
      Enabled: true
      BatchSize: 10
      MaximumBatchingWindowInSeconds: 5
      FunctionResponseTypes:
        - ReportBatchItemFailures
      ScalingConfig:
        MaximumConcurrency: 20
~~~

**Limitations of this fragment:**

- Does not create the function; lacks execution-role grants for `ReceiveMessage`/`DeleteMessage`/`GetQueueAttributes` and KMS if using SSE-KMS customer keys.
- `VisibilityTimeout=185` fits only the matching example function timeout and batching window; recalculate for your actual function and AWS guidance.
- Lambda code **must return `batchItemFailures` per contract**; toggling the flag alone does not implement partial handling.
- `MaximumConcurrency=20` is an illustrative guardrail, **not an optimal setting** for every downstream system.
- Uses Standard queues; FIFO requires FIFO queues/DLQs with `FifoQueue: true` and proper message group/dedup rules.
- CloudFormation creates billable resources; plan rollbacks and clean up labs afterward.

## 19. Read-Only AWS CLI: Inspecting Queues, DLQs, and Mappings

Replace account IDs, queue names, API IDs, and Regions with resources **you are authorized to view**. The commands below are read-only; never run `ReceiveMessage` casually because receiving **changes visibility and receive counts**, impacting production consumers.

### 19.1. Inspect caller identity and queues

~~~bash
aws sts get-caller-identity

aws sqs list-queues \
  --region ap-southeast-1 \
  --queue-name-prefix jobs-lab

aws sqs get-queue-attributes \
  --region ap-southeast-1 \
  --queue-url https://sqs.ap-southeast-1.amazonaws.com/123456789012/jobs-lab \
  --attribute-names All
~~~

Inspect attributes such as `VisibilityTimeout`, `ReceiveMessageWaitTimeSeconds`, `RedrivePolicy`, `MessageRetentionPeriod`, `ApproximateNumberOfMessages`, and `ApproximateNumberOfMessagesNotVisible`. Message counts are **approximate**, not exact transactional tallies.

### 19.2. Inspect Lambda → SQS mapping

~~~bash
aws lambda list-event-source-mappings \
  --region ap-southeast-1 \
  --event-source-arn arn:aws:sqs:ap-southeast-1:123456789012:jobs-lab \
  --query "EventSourceMappings[].{UUID:UUID,State:State,BatchSize:BatchSize,Window:MaximumBatchingWindowInSeconds,ResponseTypes:FunctionResponseTypes,Scaling:ScalingConfig}" \
  --output json
~~~

Review the function ARN, mapping state, batch size, batching window, and `FunctionResponseTypes`. If function code returns `batchItemFailures` while `FunctionResponseTypes` lacks `ReportBatchItemFailures`, partial batch responses are not active.

### 19.3. Inspect CloudWatch queue metrics

~~~bash
aws cloudwatch list-metrics \
  --region ap-southeast-1 \
  --namespace AWS/SQS \
  --metric-name ApproximateAgeOfOldestMessage

aws cloudwatch list-alarms \
  --region ap-southeast-1 \
  --alarm-name-prefix jobs-lab
~~~

`list-metrics` only returns series metadata and may omit series without recent datapoints; it does not return a time series to analyze. To retrieve datapoints, use `get-metric-data`/`get-metric-statistics` or the CloudWatch Console with appropriate dimensions and time ranges.

### 19.4. Inspect ECS consumer service if using ECS

~~~bash
aws ecs describe-services \
  --region ap-southeast-1 \
  --cluster shop-workers \
  --services notification-worker \
  --query "services[].{Name:serviceName,Desired:desiredCount,Running:runningCount,Pending:pendingCount,Events:events[0:5].message}" \
  --output json
~~~

If the service does not exist, that simply means no ECS service is deployed under that name/Region—do not conclude the queue has no consumer, as it may use Lambda or another compute layer.

## 20. Reinforcement Exercises

### Exercise 1 — `SendMessageBatch` partial success

A 10-message batch returns `Successful=8` and `Failed=2`. The producer plans to resend all 10.

**Hint:** do not resend the eight already-acknowledged messages; retry only the two failed entries if retryable, and maintain business idempotency in case of request timeouts or uncertain acknowledgments.

### Exercise 2 — Asked for 10, received only 3

A consumer calls `ReceiveMessage(MaxNumberOfMessages=10, WaitTimeSeconds=20)` and gets three messages even though the queue holds many more.

**Hint:** `MaxNumberOfMessages` is an **upper bound**, not a guaranteed batch fill. Do not treat this as an error needing immediate retry; long polling and concurrency design matter far more.

### Exercise 3 — Lambda partial failure

An invocation receives five records: the third fails while the other four commit cleanly. The mapping has not enabled `ReportBatchItemFailures`, yet the code returns:

~~~json
{"batchItemFailures":[{"itemIdentifier":"m3"}]}
~~~

**Hint:** `FunctionResponseTypes: ReportBatchItemFailures` must be enabled on the mapping. Otherwise the runtime may not honor partial failure responses as intended, risking mistaken deletions or improper retries.

### Exercise 4 — FIFO message groups

A FIFO queue holds 50,000 messages, **all** using `MessageGroupId=global`. Raising workers from 2 to 100 yields no meaningful throughput gain.

**Hint:** one message group requires sequential ordering, so there are not 100 independent groups for 100 workers to process concurrently. Partition groups along business ordering boundaries like order ID where possible without breaking required order.

### Exercise 5 — Database backpressure

A database safely supports 50 concurrent requests, while 20 ECS tasks × 10 threads/task can fire 200 concurrent requests. Backlog grows and DB p99 skyrockets.

**Hint:** adding more workers will make things worse. Cap fleet-wide concurrency to DB limits, trim local threads or add distributed semaphores, then optimize DB/throughput or absorb backlog intentionally.

### Exercise 6 — Capacity planning

SQS receives 450 msg/s and each worker sustains 30 msg/s. Ignoring headroom, how many workers minimum are needed to keep pace with arrivals?

**Hint:** `ceil(450/30) = 15 workers`. In reality, add margin for errors/retries, AZ disruptions, and downstream quotas.

### Exercise 7 — Ack after commit

A worker writes data successfully, then crashes before `DeleteMessage`. The message is redelivered.

**Hint:** enforce idempotency via unique business event IDs/conditional writes and delete only after durable commits. Redelivery is expected under at-least-once semantics.

### Exercise 8 — DLQ redrive

Following a partner outage, a DLQ holds 40,000 notifications. Ops wants to redrive everything at once without confirming partner recovery.

**Hint:** identify the root cause, verify the endpoint has recovered, throttle the redrive rate, validate duplicate protection, watch backlog/429 metrics, and keep a stop plan ready if overload recurs.

### Exercise 9 — Low backlog age, high business errors

CloudWatch shows the queue nearly empty, yet customers report missing emails. Worker code catches every exception and deletes the message anyway.

**Hint:** never rely on queue depth alone; the consumer is **acknowledging failures as successes**. Fix per-message outcome handling, test retries/DLQ, and track business success metrics.

### Exercise 10 — Splitting SNS fan-out

Order Service emits events for Inventory, Email, and Fraud. The Email API has a tight quota and frequently returns 429s.

**Hint:** have SNS/EventBridge route events into **separate independent queues**, each with its own consumer capacity, retry policy, and DLQ. Never let an email retry storm stall inventory or fraud.

## 21. Production Deployment Checklist

- [ ] Classified Standard vs. FIFO; message groups, ordering rules, and deduplication are defined.
- [ ] Producers use batching with per-entry `Successful/Failed` checks, bounded retries, and idempotency/outbox where needed.
- [ ] Consumers pull within SQS batch limits using proper long-poll timeouts; no over-prefetching when workers are full.
- [ ] Side effects commit durably before `Delete`; receipt handles and duplicate deliveries are tested.
- [ ] Visibility timeout fits P99 runtime with bounded extensions; Lambda mappings align with function timeout and batch window.
- [ ] Lambda ESM enables `ReportBatchItemFailures` when using partial responses; FIFO stops on the first failing item per group.
- [ ] Bounded concurrency, downstream rate limiters, jittered exponential backoff, and circuit breakers are implemented.
- [ ] Autoscaling uses backlog, oldest age, and real throughput; max concurrency stays within DB/API limits.
- [ ] DLQ/redrive policies, retention, and operator permissions are configured; poison messages and controlled redrives are tested.
- [ ] Producer and consumer IAM roles are separated; queue policies, SNS/EventBridge sources, and SSE-KMS are verified.
- [ ] Metrics cover queue depth, age, in-flight, retries, processing errors, DLQ, business successes, and cost.
- [ ] Graceful shutdown and ECS scale-in do not drop work or flood in-flight counts.
- [ ] Capacity under single-AZ failure, service quotas, and costs (Lambda/ECS/SQS/KMS/logs) have been evaluated.
- [ ] Runbooks exist for bursts, downstream outages, duplicate messages, and dead-letter triage.
- [ ] Lab/staging environments validated partial failures, concurrency caps, and graceful recovery before production.

## 22. Key Takeaways

A resilient queue architecture coordinates **batching, backpressure, and consumer scaling**:

1. **Batch operations** cut request overhead, yet SQS batch APIs have **partial success**; avoid data loss by checking outcomes **per message**.
2. **Visibility timeouts, Delete, and at-least-once** mean messages can reappear. **Idempotency** in the business datastore is an essential safeguard.
3. **Backpressure** does not mean “add as many workers as possible”: cap concurrency to DB/API capacity and use backed-off retries to avoid cascading failures.
4. **Consumer scaling** must track backlog, message age, and **actual** throughput, bounded by capacity ceilings and unhealthy-downstream protections.
5. **Lambda SQS event source mapping** provides built-in batching, partial failures, and capped concurrency; **ECS/EC2 workers** offer full control over polling loops and bounded thread pools.
6. **FIFO ordering, DLQs, and SNS fan-out** introduce constraints you must design around; no single service creates end-to-end exactly-once processing on its own.

The ultimate goal is not merely **emptying the queue**, but ensuring every business job is processed **accurately, on time, recoverably, and within approved cost and availability bounds**.

### Official AWS Documentation for Further Reading

- [Amazon SQS Developer Guide](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/welcome.html) — SQS concepts, APIs, and operations.
- [Using SendMessageBatch with SQS](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-batch-api-actions.html) — batch APIs and partial failure handling.
- [Amazon SQS short and long polling](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-short-and-long-polling.html) — polling modes and `WaitTimeSeconds`.
- [Amazon SQS visibility timeout](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-visibility-timeout.html) — in-flight state, redelivery, and extensions.
- [Amazon SQS dead-letter queues](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-dead-letter-queues.html) — `maxReceiveCount`, retention, and redrive.
- [Amazon SQS FIFO queues](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-fifo-queues.html) — message groups, ordering, and deduplication.
- [Configuring Lambda to use Amazon SQS](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-configure.html) — batching window, timeouts, permissions, and scaling.
- [Handling errors for an SQS event source in Lambda](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-errorhandling.html) — retries and partial batch responses.
- [Using Lambda with Amazon SQS](https://docs.aws.amazon.com/lambda/latest/dg/with-sqs.html) — polling, invocation, and failure semantics.
- [Using maximum concurrency for Amazon SQS event sources](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-scaling.html) — scaling behavior and guardrails.
- [Amazon ECS Service Auto Scaling](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-auto-scaling.html) — ECS task count scaling policies.
- [SQS available CloudWatch metrics](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-available-cloudwatch-metrics.html) — backlog, age, sent/received/deleted.
- [SQS IAM and security](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-authentication-and-access-control.html) — queue access control and resource policies.
- [Amazon SNS fanout to SQS queues](https://docs.aws.amazon.com/sns/latest/dg/sns-sqs-as-subscriber.html) — distributing events to multiple queues.
- [AWS SDK for Java 2.x: SQS examples](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/java_sqs_code_examples.html) — Java SDK send, receive, and delete.
- [Amazon SQS pricing](https://aws.amazon.com/sqs/pricing/) — API requests and cost structure.
