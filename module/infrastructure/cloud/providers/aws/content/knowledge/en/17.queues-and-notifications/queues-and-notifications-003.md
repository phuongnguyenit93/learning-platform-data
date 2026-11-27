# Visibility Timeout, Long Polling, and Acknowledgment Mechanisms in Amazon SQS

## Learning Objectives

After this lesson, learners will be able to:

- Describe the complete **lifecycle of an SQS message**: producer sends, message waits, consumer receives, message becomes *in-flight*, processing succeeds/fails, and the message is either deleted or redelivered.
- Explain **visibility timeout** as the period a message is temporarily hidden **after being received**, not its retention period or a lock guaranteeing single execution.
- Choose visibility timeout values based on **p95/p99 processing time**, shutdown duration, retries, batch size, and recovery objectives.
- Use `ReceiveMessage`, `DeleteMessage`, and `ChangeMessageVisibility` with **`ReceiptHandle`**, including extending timeouts via heartbeats and releasing messages early with a timeout of 0.
- Distinguish **short polling** from **long polling**, configure `WaitTimeSeconds` from 0 to 20 seconds, and understand *empty receives*, HTTP client timeouts, and cost impacts.
- Design **acknowledgment** after side effects are durably persisted, ensuring **idempotency** on message redelivery; distinguish `MessageId` from `ReceiptHandle`.
- Handle **batches**, **dead-letter queues (DLQs)**, **FIFO message groups**, in-flight limits, and *poison message* failures.
- Differentiate **self-polling consumers** from **AWS Lambda event source mapping**: who receives messages, who deletes them, and why batch errors can reprocess already-succeeded records.
- Test receive/delete flows with the AWS CLI, write a Java consumer using **AWS SDK for Java v2**, monitor with CloudWatch, and diagnose duplicate or backlogged messages.
- Connect SQS to **SNS fanout**, IAM, VPC endpoints, KMS, Lambda/ECS/EC2, Regions/AZs, cost, and application recovery planning on AWS.

**Context:** This lesson belongs to the **Queues and Notifications** chapter of the **CLOUD_PROVIDERS_AWS** module. In a sales system, an API might commit an order in RDS/DynamoDB and emit an event; SQS serves as the buffer decoupling request ingestion from downstream processing. Whether the application runs on **EC2, ECS, EKS, or Lambda**, choosing the right polling, visibility, and ack settings determines whether orders are processed safely, backlogs drain, and the system withstands failures.

> **Scope:** This lesson focuses on **Amazon Simple Queue Service (Amazon SQS)**. Amazon SNS is a notification/event distribution service with different delivery and retry mechanics; an SNS topic can fan out to SQS queues, but **message acknowledgment after SQS processing** is not SNS acknowledgment. The commands and ARNs below are **lab samples** and must be replaced with authorized account/Region resources.

## 1. The Problem: What If a Consumer Crashes After Receiving an Order?

Suppose an application produces an event:

~~~json
{
  "eventId": "evt-1001",
  "eventType": "OrderCreated",
  "orderId": "ORD-1001",
  "occurredAt": "2026-11-20T03:00:00Z"
}
~~~

The producer sends the event to SQS; a worker pulls the event to generate an invoice, store it in S3, and update the order status.

Possible outcomes include:

1. The worker receives the message, **processes it successfully**, and deletes it: work is complete.
2. The worker receives the message, then **crashes before writing the invoice**: SQS must allow another consumer to retry.
3. The worker **writes the invoice successfully, then crashes before deleting the message**: another consumer can reprocess it, causing duplicate writes or notifications if the application is not idempotent.
4. The worker receives the message and takes **longer than the visibility timeout**: the message may be handed to another consumer while the first worker is still running.
5. The worker encounters **permanently invalid** data: retries must be bounded and the message moved to a DLQ so it neither causes error storms nor blocks other messages.

SQS solves part of this through **durable storage and message redelivery**. However, **SQS does not know whether the business transaction has committed**. The application must decide when work qualifies for **acknowledgment via message deletion**.

~~~mermaid
flowchart LR
    P[Producer / Order API] -->|SendMessage| Q[(SQS queue)]
    Q -->|ReceiveMessage| C[Consumer]
    C --> B{Processing & commit succeeded?}
    B -->|Yes| D[DeleteMessage with ReceiptHandle]
    D --> X[Message deleted]
    B -->|No / crash| V[Do not delete]
    V --> T[Visibility timeout expires]
    T --> Q
    Q -. Exceeds retry threshold .-> DLQ[(Dead-letter queue)]
~~~

**Key point:** *ReceiveMessage* does not confirm successful processing. For active SQS consumers using an SDK or CLI, business “ack” corresponds to **`DeleteMessage` after success**.

## 2. Message Lifecycle: Visible, In-Flight, Deleted

An SQS message must be understood through its states:

| State | When? | Can another consumer receive it? |
| --- | --- | --- |
| **Sent / stored / available** | Producer sent successfully; message is not delayed or hidden by visibility | Yes, subject to FIFO rules and quotas |
| **Delayed** | Queue delay or per-message timer has not expired | Not yet |
| **In-flight / not visible** | Consumer received it, message is not yet deleted, and visibility has not expired | Normally no; Standard queues allow rare exceptions due to at-least-once delivery |
| **Visible again** | Visibility expired or was set to 0, and message was not deleted | Yes |
| **Deleted** | `DeleteMessage` succeeded with current handle and message was removed | No longer in the queue under normal behavior; Standard queues still require idempotency for rare duplicates |
| **Moved to DLQ** | Redrive policy reached receive threshold while message kept failing | Handled separately in the DLQ |

**Distinguish three timers:**

- **Delivery delay**: hides the message **immediately after send**, before the first receive; up to 15 minutes via queue/message timers.
- **Visibility timeout**: hides the message **after `ReceiveMessage` returns it to a consumer**; defaults to 30 seconds, with a 12-hour maximum from the corresponding receive.
- **Message retention period**: how long SQS retains an undeleted message before expiring it; defaults to 4 days, configurable up to 14 days.

A message still within retention whose visibility has expired can be redelivered. **Retention is not the time a worker is allowed to spend on a single processing attempt**.

## 3. What Does Visibility Timeout Actually Mean?

**Visibility timeout** is the period during which SQS **temporarily hides a received message from other receive calls**, giving the consumer an opportunity to process and delete it.

Suppose a queue has a **60-second** visibility timeout:

~~~text
T = 00s  Consumer A calls ReceiveMessage → gets M1 + ReceiptHandle A.
         M1 enters in-flight state; 60-second visibility timer starts.

T = 10s  Consumer B long polls; normally does not receive M1.

T = 40s  A is still calling the PDF generation service.

T = 60s  A has not called DeleteMessage → M1 can become visible again.

T = 65s  Consumer B calls ReceiveMessage → receives M1 again,
         with a new ReceiptHandle B.

T = 70s  A finally finishes; if A still tries to delete using handle A,
         it cannot assume that deletes the redelivered copy.
~~~

### Visibility timeout is not an absolute distributed lock

For **standard queues**, AWS SQS uses an **at-least-once delivery** model. Due to distributed storage mechanics, a message can occasionally be redelivered unexpectedly, even while visibility appears active. Therefore:

- Do not write code assuming **“a `MessageId` is processed at most once”**.
- Do not treat visibility as a **lease with a fencing token** to guard database transactions.
- If a side effect must be unique (charging, invoicing, sending email), enforce **idempotency** and conditional commits at the target data store.
- If a timed-out worker runs late, the system must prevent it from overwriting a newer worker's result.

**Key relationship:** Visibility helps reduce concurrent duplicate work, while data **correctness** must be protected at the application/database layer.

## 4. Visibility Configuration Milestones: Defaults, Overrides, and Limits

Key AWS SQS values to remember:

| Attribute | Typical value/limit | Scope |
| --- | --- | --- |
| Queue default visibility | **30 seconds** | Received messages when not overridden |
| Minimum visibility | **0 seconds** | Message can be made visible immediately |
| Maximum visibility | **43,200 seconds (12 hours)** | Measured as the cap from when the message was received |
| `VisibilityTimeout` queue attribute | Queue-level configuration | Applies to receives under queue defaults |
| `ReceiveMessage.VisibilityTimeout` | Overrides **only messages returned by that `ReceiveMessage` call** | Does not change the queue's global setting |
| `ChangeMessageVisibility` | Changes hide duration for an **already received** message | Requires a valid receipt handle |
| Message retention | Default **4 days**, maximum **14 days** | Maximum lifetime of a message in the queue |

Common pitfall: **`ChangeMessageVisibility(120)` sets a new 120-second visibility interval from the moment of the call**, but **it does not reset the 12-hour maximum measured from `ReceiveMessage`**. If only 10 minutes remain before the 12-hour cap and you request 60 more minutes, SQS returns an error; it **does not clamp down to 10 minutes**.

**A visibility change on one receive is not remembered for future receives of the same message.** If the message is not deleted, the next `ReceiveMessage` uses the queue default or a new override, not the seconds passed to `ChangeMessageVisibility` during the previous attempt.

### Visibility in batches

A single `ReceiveMessage` call can return **up to 10 messages**. The visibility setting applies to all messages in that response. If processed **sequentially**, the last message may wait too long and expire its visibility **before processing even starts**. Therefore, choose the batch size based on concurrency, service time, worker limits, and extension strategy.

## 5. Choosing Visibility Timeout Based on Processing Time

No single timeout fits every workload. Too short invites duplicate processing; too long slows down crash recovery.

### 5.1. A starting formula

For a worker processing one message at a time:

\[
V_{\text{initial}} \gtrsim T_{\text{processing p99}} + T_{\text{commit/delete}} + T_{\text{safety}}
\]

Where:

- `T_processing p99`: near-worst-case processing duration during normal system health;
- `T_commit/delete`: time to commit work and call `DeleteMessage`;
- `T_safety`: buffer for network jitter, GC pauses, brief retries, and scheduler delays.

**This is a design heuristic, not an AWS-mandated algorithm**. Always use real measurements and inspect latency distribution.

Example:

~~~text
p99 processing time:           42 seconds
Commit and delete message:      3 seconds
Safety buffer:                 15 seconds
Initial reference visibility:  60 seconds
~~~

If a job typically takes 2 minutes but occasionally takes 10 minutes, you do not have to set a 12-hour visibility on every message. You can pick **2–3 minutes initially**, then use a **heartbeat** to extend it only while work is genuinely progressing.

### 5.2. Choosing based on recovery targets

| Scenario | Visibility too short | Visibility too long |
| --- | --- | --- |
| Worker processes images in 90 seconds | Message may be redelivered while first worker is still generating image | When a worker crashes, message stays hidden too long |
| Transaction processes in 1 second | Usually fine, but vulnerable when DB slows unexpectedly | Crash retries are slower than necessary |
| Long-running job of unpredictable length | Fixed timeout is hard to choose | Heartbeat is usually better, though the 12-hour cap still applies |
| FIFO message group with failing message | Can trigger multiple duplicate attempts | **Entire group** is delayed a long time before retry |
| Lambda batch processes for 30 seconds | 10-second timeout causes failures/duplicates | Timeout misaligned with Lambda/DLQ timeouts |

### 5.3. Accounting for batches

If you receive 10 messages and process them sequentially, up to 20 seconds each, the 10th message may not start until nearly 180 seconds after receive; total batch time approaches 200 seconds. A 30-second visibility is clearly inadequate.

Options:

- Receive fewer messages (e.g., `maxNumberOfMessages=1` for long jobs).
- Use a bounded worker pool, ensuring each message is extended independently.
- Size visibility for **internal queue wait time** plus processing time, not handler time alone.
- If batch items are independent, use `DeleteMessageBatch` as items complete, handling **batch API partial failures**.
- Avoid prefetching thousands of messages where they sit **in-flight** without active workers.

## 6. ChangeMessageVisibility and Heartbeats

When a worker is still processing and approaches expiration, call:

~~~text
ChangeMessageVisibility(
  QueueUrl = queue URL,
  ReceiptHandle = current receipt handle,
  VisibilityTimeout = seconds to remain hidden from the time of this call
)
~~~

Example:

~~~text
T = 00s  Receive message, visibility = 60 seconds.
T = 40s  Worker is still processing and knows work remains.
         Call ChangeMessageVisibility(60).
         New expiration moves out to roughly T = 100s.
T = 75s  Call ChangeMessageVisibility(60) again while making progress.
         New expiration moves out to roughly T = 135s.
T = 88s  Complete side effects and call DeleteMessage successfully.
~~~

### Rules for sound heartbeats

1. Send heartbeats only while the consumer **truly owns the current receive's receipt handle**.
2. Renew **before the prior timeout expires**, leaving margin for network/GC delays.
3. Renew only if the work **is actually making progress**; if a worker hangs forever, heartbeats should not hold the message indefinitely.
4. **Stop the heartbeat** once the message is deleted or ownership ends.
5. Cap total processing time and move overly long work to a checkpointed pattern.
6. Log extension counts, elapsed time, attempt numbers, and reasons for investigation.

**Do not treat `ChangeMessageVisibility` as an exactly-once guarantee.** If another worker already received the message after a timeout with a new receipt handle, extending with the old handle may fail or behave differently than expected.

### Returning a message to the queue early

When a worker receives a message and intentionally declines to process it immediately (e.g., imminent host shutdown, insufficient local capacity), it can set:

~~~bash
aws sqs change-message-visibility \
  --queue-url "https://sqs.ap-southeast-1.amazonaws.com/111122223333/orders-work-lab" \
  --receipt-handle "LATEST_RECEIPT_HANDLE" \
  --visibility-timeout 0 \
  --region ap-southeast-1 \
  --profile lab
~~~

This makes the message **immediately available for redelivery** (subject to queue rules). It **does not record a permanent processing failure** and **does not automatically move the message to a DLQ**. Never run this in a tight loop while backend failures remain unresolved, or you will create a **hot-loop retry** wasting API requests and hammering downstream services.

## 7. Acknowledgment in SQS Is DeleteMessage

SQS has no API named `AckMessage` like some message brokers. For **self-polling consumers**, acknowledgment means:

1. `ReceiveMessage` fetches the message and receipt handle.
2. Execute logic, persist data, and **commit** successfully.
3. Call `DeleteMessage` with the **current receive's receipt handle**.
4. If delete fails or its outcome is uncertain, **do not assume the message vanished**; retry carefully and rely on idempotent processing.

### Distinguishing MessageId and ReceiptHandle

| Field | Who issues it / when? | What is it used for? |
| --- | --- | --- |
| **MessageId** | Returned by SQS when the message is sent | Identifying, logging, and correlating an enqueued message |
| **ReceiptHandle** | Returned by SQS on each successful `ReceiveMessage` | **`DeleteMessage`** and `ChangeMessageVisibility` for that receive |
| **eventId/orderId** | Defined by the application in message body/attributes | Idempotency and business correlation |
| **MessageGroupId** (FIFO) | Supplied by producer | Preserving per-group order and bounding parallelism |
| **MessageDeduplicationId** (FIFO) | Supplied by producer or computed by SQS from body when content-based is enabled | Deduplicating sends within the deduplication window |
| **ApproximateReceiveCount** | SQS system attribute | Observing receive/retry counts; does not replace an idempotency key |

A message can be received the first time with `ReceiptHandle=A` and the second time with `ReceiptHandle=B`. Calling delete with `A` after the second receive **can return HTTP 200 without deleting the message**. Always use the latest receipt handle and prevent multiple workers from executing side effects without deduplication.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant Q as Amazon SQS
    participant A as Consumer A
    participant B as Consumer B
    participant DB as Database
    P->>Q: SendMessage(eventId=evt-1001)
    Q-->>P: MessageId=M1
    A->>Q: ReceiveMessage
    Q-->>A: M1, ReceiptHandle=H1
    A->>DB: Process/commit business logic
    alt A succeeds within visibility
      A->>Q: DeleteMessage(H1)
      Q-->>A: Success
    else A crashes before delete
      Note over Q: Visibility expires, M1 visible again
      B->>Q: ReceiveMessage
      Q-->>B: M1, ReceiptHandle=H2
      B->>DB: Idempotent processing
      B->>Q: DeleteMessage(H2)
    end
~~~

**Ack after commit, never ack before commit.** Yet “commit then delete” still leaves a **non-atomic gap between the DB and SQS**, which is why data-layer idempotency/outbox/inbox patterns are necessary.

## 8. At-Least-Once Delivery and Why Idempotency Is Mandatory

With standard queues, receiving a message multiple times is a scenario you must **design for upfront**:

~~~text
1. Consumer processes order ORD-1001 and commits to DB successfully.
2. Consumer loses connection right before or after calling DeleteMessage.
3. SQS may still redeliver the message.
4. Another consumer receives the same event and tries to write, charge, or email again.
~~~

### 8.1. Idempotency key

Prefer an immutable **business event ID**:

~~~json
{
  "eventId": "evt-order-created-1001-v1",
  "orderId": "ORD-1001",
  "eventType": "OrderCreated",
  "schemaVersion": 1
}
~~~

Never use **ReceiptHandle** as an idempotency key because it **changes on every receive**. `MessageId` is stable for a single enqueue, but a business event can be republished as a new SQS message; in such cases the business **`eventId`** is much safer.

### 8.2. Conditional writes / inbox

A common approach stores processed markers in **DynamoDB** or a SQL table with a **unique constraint**:

~~~text
processed_events
  event_id (primary/unique)
  state (PROCESSING | COMPLETED)
  lease_owner
  lease_expires_at
  updated_at
~~~

Conceptual flow:

1. Claim `eventId` using a conditional write or suitable transaction.
2. If already `COMPLETED`, skip side effects and delete the message with the current receipt handle.
3. If another worker is `PROCESSING` with an active lease, avoid duplicate execution; handle retry/visibility per policy.
4. Execute retryable business actions using **unique business keys** in target systems.
5. Commit `COMPLETED` only once side effects are durably persisted per business rules.
6. Call `DeleteMessage` afterward.

**Caution:** Writing a `PROCESSING` record and skipping all future deliveries **can drop work** if a worker crashes mid-flight. Implement **lease expiration, safe takeover, and recovery**. When side effects span non-transactional systems (DB, email, payments), design outboxes, downstream idempotency, and compensating steps.

### 8.3. There is no atomic transaction across SQS Delete and DB commit

`DeleteMessage` does not participate in the same ACID transaction as PostgreSQL or DynamoDB. You cannot guarantee an exactly-once business side effect merely by calling `DeleteMessage` “at the right time”.

**Realistic goal:** *At-least-once delivery + idempotent processing* yields **effectively once** behavior for properly designed business logic—not an infrastructure guarantee that a handler runs strictly once.

## 9. Long Polling: Waiting for Messages Instead of Constant Polling

SQS offers two polling modes via `ReceiveMessage`:

| Characteristic | **Short polling** | **Long polling** |
| --- | --- | --- |
| `WaitTimeSeconds` | **0** | **1–20 seconds** |
| Query behavior | Samples a subset of SQS servers | Checks across servers using long-poll mechanics |
| When queue is empty | Returns immediately with empty list | Waits until a message arrives or timeout expires |
| When few messages exist | Can return **false empty responses** | Reduces false empties and empty responses |
| API calls while idle | Can be very high in a tight loop | Typically drops substantially |
| Latency to receive new message | Depends on polling frequency | Can return immediately upon arrival without waiting the full 20 seconds |
| Request cost | Can be high with frequent polling | Usually cheaper for sparse workloads |
| Client timeout | Short wait | **HTTP read/response timeout must exceed `WaitTimeSeconds`** |

**Key point:** Long polling **does not make messages invisible**; visibility timeout only begins **after a message is received**. `WaitTimeSeconds=20` does not limit the consumer to 20 seconds of processing.

### 9.1. Why do “false empties” occur?

Short polling samples a subset of storage servers. One `ReceiveMessage` call may find no messages on the sampled servers even though deliverable messages exist in the queue. Long polling mitigates this, though it does not turn the API into an instantaneous consistent snapshot of the entire queue.

**Never delete a queue or declare backlog zero based on a single empty `ReceiveMessage` response.** Check approximate metrics, in-flight/delayed counts, FIFO group blocking, and retention.

### 9.2. Why is 20 seconds commonly chosen?

AWS generally recommends the maximum **20-second** long poll unless requirements dictate shorter waits. When a queue is often idle, instead of firing tens of thousands of empty receives, the consumer holds a single request open until work arrives.

**Illustrative** example for a continuously empty queue:

\[
\text{Short poll every second} = 86{,}400\ \text{requests/day}
\]

\[
\text{20-second long poll} = 4{,}320\ \text{requests/day}
\]

In theory this reduces receive requests by \(\approx 95\%\) when **zero messages arrive**, ignoring network overhead, reconnects, and retries. When messages flow steadily, long polls return early so request counts differ. Actual costs also depend on Regional pricing and SQS billing rules.

### 9.3. A waiting request should not starve other queues

If a consumer uses one thread to long poll **queue A then queue B** sequentially, a 20-second wait on queue A delays receives on queue B. Use **dedicated polling workers per queue** or async clients with appropriate backpressure and connection pools.

## 10. Configuring Long Polling at the Queue Level vs. Per ReceiveMessage

There are two ways:

1. **Queue-level** `ReceiveMessageWaitTimeSeconds`: default applied when `ReceiveMessage` omits `WaitTimeSeconds`.
2. **Per-request** `ReceiveMessage.WaitTimeSeconds`: overrides the default for that specific call.

| Configuration | Effective wait | Behavior |
| --- | --- | --- |
| Queue wait = 0, receive unset | `0` | Short polling |
| Queue wait = 20, receive unset | `20` | Long polling up to 20 seconds |
| Queue wait = 20, receive wait = 5 | `5` | Long polling up to 5 seconds |
| Queue wait = 20, receive wait = 0 | `0` | Short polling for this call |
| Receive wait = 30 | Invalid | Exceeds 20-second maximum |

### Choosing the HTTP client timeout

If `WaitTimeSeconds=20`, set **HTTP response/socket timeout > 20 seconds**, with headroom for network/service latency. If the HTTP client times out at 10 seconds, the client aborts the long poll before SQS can reply.

Distinguish:

- **`WaitTimeSeconds`**: how long SQS waits for a message to appear.
- **HTTP read timeout**: how long the client waits for an HTTP response.
- **`VisibilityTimeout`**: how long a received message stays hidden.
- **Lambda timeout**: maximum execution duration for a Lambda handler.

**These four timeouts serve four distinct purposes**; never reuse a single `timeout=30` variable for all of them.

## 11. Message Batching, In-Flight Quotas, and Backpressure

A `ReceiveMessage` call requests `MaxNumberOfMessages` from 1 to **10**. SQS **may return fewer** than requested.

### Sizing batches to real capacity

A worker that can run only 2 concurrent jobs but prefetches 10 messages leaves 8 messages sitting in-flight, hidden from other workers without being processed. If jobs are long, those 8 messages may expire visibility while waiting in a local queue.

**Do:**

- Cap received messages to **available worker slots**;
- use a bounded queue or semaphore instead of unbounded local buffering;
- size visibility for local queue wait + processing time;
- delete **each message upon completion**, or use batch delete while handling partial failures;
- monitor `ApproximateNumberOfMessagesNotVisible` and worker utilization.

### In-flight quotas

For standard SQS queues, the in-flight limit is typically **around 120,000 messages**, subject to quotas and traffic. When reached:

- **Short polling** may return an `OverLimit` error.
- **Long polling** generally **does not return `OverLimit`**, but stops returning new messages until in-flight counts drop.

For FIFO queues, limits also depend on quotas and **active message groups**. Do not assume a queue is empty when long polling returns nothing while `NotVisible` is high.

**Remediation:** Reduce prefetch, delete promptly after commit, fix stuck workers, tune visibility/heartbeats, split queues if warranted, and review quotas where justified.

### DeleteMessageBatch can partially succeed

`DeleteMessageBatch` accepts up to **10 entries**. A batch response can include both **`Successful` and `Failed` entries** even on an HTTP 200 response. Code must correlate each entry ID, retry valid failed handles, and never equate “HTTP 200” with all messages acknowledged.

**Avoid delaying deletion of all 10 messages until the slowest job finishes** if batch items are independent and finished earlier.

## 12. FIFO, MessageGroupId, and Visibility Timeout

**Standard queues** offer flexible throughput and an at-least-once model without strict message ordering. **FIFO queues** preserve order per **`MessageGroupId`** and deduplicate **sends**.

Example:

~~~text
FIFO queue: orders-events.fifo

Message group ORD-1001:
  M1 = OrderCreated
  M2 = PaymentCaptured
  M3 = InvoiceRequested

Message group ORD-1002:
  N1 = OrderCreated
  N2 = PaymentCaptured
~~~

While `M1` in group `ORD-1001` is in-flight, SQS **will not deliver subsequent messages from that group to another receive call** until the in-flight messages for that group are deleted or their visibility expires. Within a single **`ReceiveMessage` batch**, SQS can still return **multiple messages from the same group** in order; consumers must handle them sequentially rather than assuming FIFO delivers one message at a time.

~~~mermaid
flowchart TB
    Q[(FIFO queue)] --> G1[Group ORD-1001]
    Q --> G2[Group ORD-1002]
    G1 --> A[M1 is in-flight]
    A --> B{Deleted or visibility expired?}
    B -->|No| W[M2/M3 wait in group]
    B -->|Yes| C[Group can continue]
    G2 --> D[N1/N2 can process in parallel with group 1]
~~~

**Performance impact:** A group with a slow message stalls progress for that group. If all events share **a single `MessageGroupId`**, adding more consumers will not raise throughput. Choose group keys matching true ordering boundaries (e.g., `orderId`, `accountId`) and understand per-group concurrency limits.

### FIFO deduplication != exactly-once business side effects

FIFO uses **`MessageDeduplicationId`** or **content-based deduplication** over an approximately **5-minute** window. This reduces duplicate messages entering the queue during producer retries. It **does not replace consumer idempotency**, because:

- Consumers can crash after committing and before deleting;
- Visibility can expire and trigger redelivery;
- A business event can be replayed outside the 5-minute dedup window;
- Side effects across separate systems do not share one transaction.

Even though AWS describes FIFO with stronger delivery guarantees than Standard, **business-level once-only execution** must still be enforced at the data layer.

## 13. Dead-Letter Queues: Never Retry a Poison Message Forever

A **dead-letter queue (DLQ)** stores messages that have been received but failed processing enough times under the source queue's **redrive policy**.

Example:

~~~text
Source queue: orders-work-lab
DLQ: orders-work-dlq-lab
maxReceiveCount: 5

Each time a message is received without deletion:
  visibility expires → message can be received again.
When SQS redrive threshold is reached:
  SQS moves the message to the DLQ for analysis.
~~~

### Why use a DLQ?

- Permanently malformed schemas (`quantity="abc"`).
- Consumer versions incompatible with legacy payloads.
- External systems rejecting data for business errors that cannot succeed on retry.
- Dependencies failing persistently beyond the retry policy.

A DLQ lets operations continue **without deleting failing messages from observability**. Still, you need **alarms, an owner, a runbook, and a redrive procedure**; a DLQ sitting silent for weeks is still an operational failure.

### maxReceiveCount and retention

| Setting | Meaning | Notes |
| --- | --- | --- |
| `maxReceiveCount` | Receive threshold before SQS moves the message to the DLQ under redrive | Too low sends transient errors to DLQ; for Lambda, AWS guidance often starts at ≥5 |
| Source retention | Maximum lifetime in the source queue | Not synonymous with retry budget |
| DLQ retention | Retention duration in the DLQ | Typically set **longer than source retention** for standard queues |
| Redrive allow policy | Which queues may target this DLQ | Prevents unauthorized sources from pushing messages |
| DLQ type | Standard ↔ standard, FIFO ↔ FIFO | Must match the source queue type |

**Retention nuance:** For **standard queues**, a message's age in the DLQ still counts from its **original enqueue timestamp** for retention expiration; set DLQ retention longer than the source queue's. For **FIFO**, the enqueue timestamp resets upon moving to the DLQ. **Do not rely solely on the DLQ's `ApproximateAgeOfOldestMessage` metric to infer original data age**.

### FIFO with a DLQ can affect business order

If a critical message moves to the DLQ so later messages proceed, end-to-end workflow order may violate business intent. For transactions requiring **strict absolute ordering**, design blocking error handling, compensation, group quarantine, or controlled redrive procedures.

## 14. SNS Fanout to SQS: Which Layer Owns Acknowledgment?

An **Amazon SNS topic** can push a single notification to multiple subscriptions: SQS queues, Lambda, HTTP endpoints, or other supported targets.

~~~mermaid
flowchart TD
    OrderAPI[Order API] --> SNS[(SNS topic: order-events)]
    SNS --> Q1[(SQS invoice queue)]
    SNS --> Q2[(SQS analytics queue)]
    SNS --> Q3[(SQS email queue)]
    Q1 --> W1[Invoice worker]
    Q2 --> W2[Analytics worker]
    Q3 --> W3[Email worker]
    W1 -->|DeleteMessage after commit| Q1
    W2 -->|DeleteMessage after commit| Q2
    W3 -->|DeleteMessage after commit| Q3
~~~

Each SQS queue has **independent visibility, polling, DLQ, and `DeleteMessage`**. When the invoice worker deletes a message from the invoice queue, it **does not acknowledge or delete** the copies in the analytics or email queues.

Distinguish:

- **SNS publish acknowledgment:** SNS confirms accepting the publish API request, not that every consumer finished business work.
- **SNS delivery/retry:** SNS has per-protocol delivery policies distinct from queue visibility timeouts.
- **Subscription confirmation:** Certain endpoints must confirm subscriptions; this **is not per-notification ack**.
- **SQS consumer acknowledgment:** `DeleteMessage` with a receipt handle after durable processing.

When fanning out SNS to SQS, configure a **queue resource policy** allowing the SNS principal to send messages, typically constraining `aws:SourceArn` to the specific topic ARN. Watch out for **SNS envelope vs. raw message delivery**: without raw delivery enabled, the SQS body wraps the business JSON inside an SNS JSON envelope.

## 15. SQS Consumers on EC2/ECS/EKS vs. Lambda: Who Manages Ack?

| Consumer model | Who calls `ReceiveMessage`? | Who calls `DeleteMessage`? | Things to watch |
| --- | --- | --- | --- |
| **Java app on EC2** | Application via AWS SDK | Application after commit | IAM instance role, shutdown/heartbeat |
| **ECS task/worker** | Code inside container | Code inside container | ECS task role, task draining, autoscaling |
| **EKS Pod** | Code inside Pod | Code inside Pod | Pod Identity/IRSA, node termination, visibility |
| **AWS Lambda SQS event source mapping** | **Lambda service poller** | **Lambda deletes batch messages on success**, or per partial batch response | Batch semantics, visibility ≥ Lambda timeout |
| **Client library with built-in auto-ack/auto-delete** | SDK/framework per config | May happen automatically | Must verify **when auto-delete fires**; never assume all SDKs behave identically |

**Common pitfall:** When Lambda is triggered **directly by SQS via event source mapping**, the handler **must not poll SQS itself**. It receives an event containing `Records`; Lambda handles polling/batching and deletes messages based on success or failure. For Java consumers on ECS/EC2, application code itself performs receive and delete.

Even when an SDK or framework offers auto-delete helpers, the **underlying SQS API model remains receive → process → delete**; never treat library conveniences as atomic transactions.

## 16. CLI Practice: Creating a Queue and Inspecting Attributes

> **This lab may incur charges for SQS requests, CloudWatch Logs, KMS, or worker resources.** Create queues only in authorized accounts, add tags, and clean up after confirming no needed messages remain. Never purge or delete production queues for demos. Use AWS CLI v2 with a temporary AWS profile/role.

### 16.1. Verify AWS identity

~~~bash
aws sts get-caller-identity --profile lab

aws configure get region --profile lab
~~~

Examples below use Region **`ap-southeast-1`** and placeholder account **`111122223333`**. Substitute your own values.

### 16.2. Create a standard source queue

~~~bash
aws sqs create-queue \
  --queue-name orders-work-lab \
  --attributes VisibilityTimeout=60,ReceiveMessageWaitTimeSeconds=20,MessageRetentionPeriod=345600 \
  --region ap-southeast-1 \
  --profile lab
~~~

Explanation:

- `VisibilityTimeout=60`: 60 seconds after a message is received.
- `ReceiveMessageWaitTimeSeconds=20`: 20-second default long polling.
- `MessageRetentionPeriod=345600`: 4 days in seconds.

`create-queue` returns the **QueueUrl**. Example:

~~~text
https://sqs.ap-southeast-1.amazonaws.com/111122223333/orders-work-lab
~~~

### 16.3. Read queue configuration

~~~bash
aws sqs get-queue-url \
  --queue-name orders-work-lab \
  --region ap-southeast-1 \
  --profile lab

aws sqs get-queue-attributes \
  --queue-url "https://sqs.ap-southeast-1.amazonaws.com/111122223333/orders-work-lab" \
  --attribute-names VisibilityTimeout ReceiveMessageWaitTimeSeconds MessageRetentionPeriod ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible \
  --region ap-southeast-1 \
  --profile lab
~~~

**Note:** `ApproximateNumberOfMessages` from the SQS queue API and `ApproximateNumberOfMessagesVisible` in CloudWatch represent related concepts with **different names**, and both are approximate. Never rely on a single reading as an exact business counter.

### 16.4. Update queue-level defaults

~~~bash
aws sqs set-queue-attributes \
  --queue-url "https://sqs.ap-southeast-1.amazonaws.com/111122223333/orders-work-lab" \
  --attributes VisibilityTimeout=90,ReceiveMessageWaitTimeSeconds=20 \
  --region ap-southeast-1 \
  --profile lab
~~~

This changes the queue default visibility from 60 to 90 seconds. Queue attribute changes can take a brief period to propagate per AWS rules; always re-read and verify empirically. **Active per-message visibility timers should not be assumed to extend automatically simply because the queue attribute changed**.

## 17. CLI Practice: Send, Receive, Delete, and Verify Acknowledgment

### 17.1. Send a message

~~~bash
aws sqs send-message \
  --queue-url "https://sqs.ap-southeast-1.amazonaws.com/111122223333/orders-work-lab" \
  --message-body '{"eventId":"evt-1001","orderId":"ORD-1001","eventType":"OrderCreated"}' \
  --region ap-southeast-1 \
  --profile lab
~~~

The response includes `MessageId` and API confirmation fields. **`MessageId` cannot be used for `DeleteMessage`**.

### 17.2. Long poll and retrieve ReceiptHandle

~~~bash
aws sqs receive-message \
  --queue-url "https://sqs.ap-southeast-1.amazonaws.com/111122223333/orders-work-lab" \
  --max-number-of-messages 1 \
  --wait-time-seconds 20 \
  --visibility-timeout 60 \
  --message-system-attribute-names ApproximateReceiveCount SentTimestamp \
  --region ap-southeast-1 \
  --profile lab
~~~

Illustrative output (the receipt handle below is a placeholder):

~~~json
{
  "Messages": [
    {
      "MessageId": "message-id-example",
      "ReceiptHandle": "ACTUAL_HANDLE_RETURNED_BY_RECEIVE",
      "Body": "{\"eventId\":\"evt-1001\",\"orderId\":\"ORD-1001\",\"eventType\":\"OrderCreated\"}",
      "Attributes": {
        "ApproximateReceiveCount": "1",
        "SentTimestamp": "1795143600000"
      }
    }
  ]
}
~~~

**Passing `--visibility-timeout 60`** on receive overrides the queue default visibility for **the messages returned by this call**. If another consumer is polling the same queue, you might not receive the message you just sent because SQS may deliver it to the other consumer.

### 17.3. Try receiving again immediately

Within 60 seconds of the first receive, run the same receive command again (omitting `--visibility-timeout` if testing the queue default). When no other messages exist, it typically returns **an empty list or no `Messages` field** after the long-polling window.

This does not prove the message was deleted; it is simply **in-flight**. Once visibility expires **without deletion**, the next receive can return **the same `MessageId` with a new `ReceiptHandle`** and an incremented `ApproximateReceiveCount`.

### 17.4. Acknowledge after processing completes

Only after simulating processing and confirming success, pass the **latest** receipt handle:

~~~bash
aws sqs delete-message \
  --queue-url "https://sqs.ap-southeast-1.amazonaws.com/111122223333/orders-work-lab" \
  --receipt-handle "ACTUAL_HANDLE_FROM_LATEST_RECEIVE" \
  --region ap-southeast-1 \
  --profile lab
~~~

**Do not execute the literal placeholder** `ACTUAL_HANDLE_FROM_LATEST_RECEIVE`. Copy the real `ReceiptHandle` from the latest receive output, never `MessageId`.

### 17.5. Demonstrate what happens when you forget to delete

Send a second test message, receive it with a 10-second visibility, **skip calling delete**, and receive again after timeout. The same business event reappears; this is the built-in retry mechanism when a consumer crashes.

**Never run this lab on a production queue**: if other workers are active, you can trigger unwanted retries or DLQ moves.

## 18. CLI Practice: Extending Visibility or Releasing Messages Early

### 18.1. Extending visibility during long processing

Suppose you just received a message and still have remaining visibility:

~~~bash
aws sqs change-message-visibility \
  --queue-url "https://sqs.ap-southeast-1.amazonaws.com/111122223333/orders-work-lab" \
  --receipt-handle "ACTUAL_HANDLE_FROM_LATEST_RECEIVE" \
  --visibility-timeout 120 \
  --region ap-southeast-1 \
  --profile lab
~~~

From the moment of the call, SQS sets a new **120-second** hide period, within the maximum cap from the initial receive. Infer timer behavior from receive behavior and logs; the API **does not inspect remaining visibility seconds**.

### 18.2. Releasing a message early

~~~bash
aws sqs change-message-visibility \
  --queue-url "https://sqs.ap-southeast-1.amazonaws.com/111122223333/orders-work-lab" \
  --receipt-handle "ACTUAL_HANDLE_FROM_LATEST_RECEIVE" \
  --visibility-timeout 0 \
  --region ap-southeast-1 \
  --profile lab
~~~

Another consumer can receive the message immediately (subject to queue rules). `visibility=0` acts conceptually like a **release or NACK with immediate requeue**, though it is not a formal `NackMessage` API and carries no failure reason. If you need failure context, emit logs/metrics or update status in your observability store.

### 18.3. Need to wait a few seconds before retrying?

`ChangeMessageVisibility` can set a small positive delay such as 10 seconds to defer the next delivery during the **current processing attempt**. However, SQS **is not an arbitrary delayed job scheduler beyond 12 hours**. For complex delayed workflows, evaluate **EventBridge Scheduler**, Step Functions, or controlled idempotent requeuing.

## 19. Java SDK v2: Long Polling and Manual Acknowledgment

Example standalone Java worker running on **EC2/ECS/EKS**. Assume the project uses Maven/Gradle with the AWS SDK for Java v2 module `software.amazon.awssdk:sqs` and a team-verified BOM.

### Sample code processing one message at a time

~~~java
package com.example.worker;

import java.util.Objects;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sqs.model.DeleteMessageRequest;
import software.amazon.awssdk.services.sqs.model.Message;
import software.amazon.awssdk.services.sqs.model.ReceiveMessageRequest;
import software.amazon.awssdk.services.sqs.model.ReceiveMessageResponse;

public final class OrderSqsConsumer {

    public static void main(String[] args) {
        String queueUrl = Objects.requireNonNull(
            System.getenv("ORDERS_QUEUE_URL"),
            "ORDERS_QUEUE_URL is required"
        );

        try (SqsClient sqs = SqsClient.builder()
                .region(Region.AP_SOUTHEAST_1)
                .build()) {

            while (!Thread.currentThread().isInterrupted()) {
                ReceiveMessageRequest receive = ReceiveMessageRequest.builder()
                    .queueUrl(queueUrl)
                    .maxNumberOfMessages(1)
                    .waitTimeSeconds(20)
                    .visibilityTimeout(90)
                    .build();

                ReceiveMessageResponse result = sqs.receiveMessage(receive);

                for (Message message : result.messages()) {
                    try {
                        processOrderIdempotently(message.body());

                        // Ack only after side effects/commit succeed.
                        sqs.deleteMessage(DeleteMessageRequest.builder()
                            .queueUrl(queueUrl)
                            .receiptHandle(message.receiptHandle())
                            .build());

                        System.out.println("Acknowledged: " + message.messageId());
                    } catch (Exception error) {
                        System.err.println(
                            "Processing failed for message "
                            + message.messageId()
                            + ", reason=" + error.getClass().getSimpleName()
                        );
                        // Do not delete; message becomes available after visibility.
                        // Production: alert/trace/retry policy + DLQ.
                    }
                }
            }
        }
    }

    private static void processOrderIdempotently(String body) {
        // DEMO: replace with JSON parsing + business validation + transaction,
        // inbox/idempotency key + durable S3/DB side effects + commit.
        // Do not log raw body if it contains PII/secrets.
        System.out.println("Processing demo order event");
    }
}
~~~

**Adjustments needed for real workloads:**

- `processOrderIdempotently` here is a **stub** that only logs and **does not enforce idempotency**. Production code must implement durable DB/side-effect idempotency before deleting the message.
- In a lab, the environment needs `ORDERS_QUEUE_URL`, a valid IAM identity, `sqs:ReceiveMessage`/`DeleteMessage` permissions, and network connectivity to the SQS endpoint.
- Fetching **1 message** per receive avoids queuing messages locally; raise batch size or concurrency only after measuring.
- `visibilityTimeout(90)` makes sense only if processing + deletion normally finish well under 90 seconds. Longer jobs require heartbeats.
- The SDK's HTTP client must allow read/response timeouts **greater than 20 seconds**; adjust if customized away from defaults.
- If `DeleteMessage` fails after commit, the message can arrive again; idempotency must cover this case.
- Production code should also include graceful shutdown and proper handling of thread interruption and SDK exceptions.

### IAM permissions for the consumer

Illustrative identity policy attached to the worker's **EC2 instance role / ECS task role / EKS Pod Identity**:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ConsumeOrdersQueue",
      "Effect": "Allow",
      "Action": [
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:ChangeMessageVisibility",
        "sqs:GetQueueAttributes"
      ],
      "Resource": "arn:aws:sqs:ap-southeast-1:111122223333:orders-work-lab"
    }
  ]
}
~~~

**Never attach `sqs:*` across all queues** just to work around errors. Producers only need permissions like `sqs:SendMessage`; consumers do not automatically need send access. If the queue uses an **SSE-KMS customer managed key**, also review KMS permissions/key policies for the consumer and the queue setup.

## 20. Java Heartbeat Worker: Safe Design

The Java snippet above fits short jobs. For long jobs, run a **concurrent heartbeat** to extend visibility before expiration. A clean design:

~~~text
receive = SQS.ReceiveMessage(wait=20s, visibility=120s)
handle = receive.ReceiptHandle
startedAt = now
heartbeatInterval = 60s
maxJobTime = 45min

start heartbeat:
    every 60 seconds:
        if job is still running and making progress
           and elapsed time has not exceeded maxJobTime:
              SQS.ChangeMessageVisibility(handle, 120s)
        if ownership lost, handle expired,
           or limit exceeded: stop extending and alert

process:
    validate eventId
    claim idempotency lease in DB
    execute work with timeouts/retries
    commit durable state
    stop heartbeat
    SQS.DeleteMessage(handle)

on failure:
    stop heartbeat
    do not delete
    log/metric and let message retry or route to DLQ
~~~

**This is pseudocode**, not a built-in heartbeat library automatically enabled when you use `SqsClient`. You must manage the scheduler thread, deadlines, shutdown, `ChangeMessageVisibility` errors, and distinguish *invalid/expired handle* exceptions from transient network errors.

### Critical race condition

If the heartbeat and delete run concurrently:

1. The worker commits and calls delete.
2. The heartbeat thread sends `ChangeMessageVisibility` with the same handle.
3. One call succeeds while the other fails or arrives out of order.

Solution: synchronize state transitions `PROCESSING → COMMITTED → ACKNOWLEDGED`, **stop the heartbeat before deleting**, and prevent heartbeats from extending once a job is canceled or ownership is lost. Use DB fencing/idempotency where needed to stop stale workers from writing after a lease expires.

**Do not extend up to the 12-hour cap and expect to keep running forever.** If work is that long, split the job, checkpoint to DB/S3, or use Step Functions / ECS / AWS Batch.

## 21. Lambda Triggered by SQS: How Automatic Acknowledgment Differs

With **AWS Lambda event source mapping (ESM)**, the Lambda service **polls SQS**, gathers a batch of messages, and invokes your function. Your handler receives an event containing `Records` and **does not call `ReceiveMessage` itself**.

~~~mermaid
sequenceDiagram
    participant Q as SQS Queue
    participant ESM as Lambda event source mapping
    participant F as Java Lambda handler
    ESM->>Q: ReceiveMessage (poll)
    Q-->>ESM: Batch [M1, M2, ...] + receipt handles
    ESM->>F: Invoke batch event
    alt Handler returns valid success
      F-->>ESM: Success
      ESM->>Q: Delete messages in batch
    else Handler throws error / failed batch
      F-->>ESM: Error
      Note over Q: Visibility expires, records can be received again
    end
~~~

### 21.1. Visibility timeout with Lambda

AWS guidance states:

- **Queue visibility timeout must be ≥ Lambda function timeout**; AWS Lambda validates this when creating or updating an ESM.
- AWS **recommends** setting the source queue's visibility timeout to **at least roughly 6 times the function timeout** to leave room for retries during throttling.
- When the ESM uses a **batching window**, AWS recommends adding the window duration to visibility:

\[
V_{\text{queue}} \gtrsim 6 \times T_{\text{Lambda timeout}} + T_{\text{batching window}}
\]

This is **ESM guidance**, not a complete substitute for measuring SLOs and processing time. For example, with a 30-second Lambda timeout and 5-second batching window → pick visibility around **185 seconds or more** and verify service constraints, keeping in mind the 12-hour max, retention, and DLQ settings.

### 21.2. Why does a Lambda batch retry in full?

Suppose a batch has 5 records: M1, M2, M3, M4, M5. The handler finishes M1–M4, then throws an exception on M5.

**By default**, Lambda treats the **entire invocation/batch as failed**. After the visibility timeout expires, all messages in the batch can become visible again, causing M1–M4 to be reprocessed too. Thus every SQS-backed handler must be **idempotent**, even when events appear to arrive only once.

### 21.3. When should Lambda call `DeleteMessage` manually?

AWS allows deleting individual succeeded records inside a handler in certain patterns, but **it is not recommended by default** when using an ESM. For most workloads, use **ESM batch acknowledgment** or **partial batch responses** instead of managing receipt handles and extra permissions out-of-band.

## 22. Lambda Partial Batch Failures: Avoiding Retries of Succeeded Records

Enable **`ReportBatchItemFailures`** on the ESM. The handler returns a list of **failed message IDs** (not receipt handles).

Example for batch M1–M5 where M2 and M4 fail:

~~~json
{
  "batchItemFailures": [
    {"itemIdentifier": "M2"},
    {"itemIdentifier": "M4"}
  ]
}
~~~

Lambda treats records **absent from the failure list** as succeeded and deletes them; failed records return to SQS for retry after visibility expires.

**Critical rules:**

- If the handler **throws an unhandled exception**, Lambda still marks the **entire batch failed** even if some records succeeded.
- Returning an invalid format or an `itemIdentifier` not in the batch can fail the entire batch.
- Returning an **empty `batchItemFailures`** tells Lambda the whole batch succeeded; never return empty when records actually failed.
- With **FIFO**, stop processing after the first error and report **both the failing message and all unprocessed messages** so ordering stays intact.

### Illustrative Java Lambda handler

The project requires compatible `aws-lambda-java-core` and `aws-lambda-java-events` dependencies for `SQSEvent`:

~~~java
package com.example.lambda;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.RequestHandler;
import com.amazonaws.services.lambda.runtime.events.SQSEvent;

public final class OrderBatchHandler
    implements RequestHandler<SQSEvent, Map<String, Object>> {

    @Override
    public Map<String, Object> handleRequest(
        SQSEvent event, Context context) {

        List<Map<String, String>> failures = new ArrayList<>();

        for (SQSEvent.SQSMessage msg : event.getRecords()) {
            try {
                processIdempotently(msg.getBody());
            } catch (Exception ex) {
                context.getLogger().log(
                    "Failed messageId=" + msg.getMessageId());
                failures.add(Map.of(
                    "itemIdentifier", msg.getMessageId()
                ));
            }
        }

        return Map.of("batchItemFailures", failures);
    }

    private void processIdempotently(String jsonBody) {
        // Production: parse/validate, durable idempotency + side effects.
        // Stub for learners to replace with real business logic.
    }
}
~~~

**For FIFO**, modify the loop above to **break on the first error** and add **all remaining unprocessed messages** to `batchItemFailures`; continuing to process later records after an earlier failure can violate business ordering. Consider **AWS Lambda Powertools Batch Processor for Java** to reduce per-record boilerplate errors.

### Enable `ReportBatchItemFailures` via AWS CLI

~~~bash
aws lambda update-event-source-mapping \
  --uuid "a1b2c3d4-5678-90ab-cdef-11111example111" \
  --function-response-types ReportBatchItemFailures \
  --region ap-southeast-1 \
  --profile lab
~~~

`UUID` is an example; look up the real mapping via `aws lambda list-event-source-mappings` and confirm the right function and queue before modifying. Changing failure handling affects retries and cost, so test single-record failures and monitor the DLQ.

## 23. IAM, KMS, Networking, and Security While Polling

### 23.1. What permissions does each principal need?

| Principal | Typical permissions | Additional conditions |
| --- | --- | --- |
| **Producer** | `sqs:SendMessage` | Queue resource policy/cross-account, KMS when using SSE-KMS |
| **Manual consumer** | `sqs:ReceiveMessage`, `sqs:DeleteMessage`, `sqs:ChangeMessageVisibility`, `sqs:GetQueueAttributes` as needed | IAM role, resource policy, `kms:Decrypt` if applicable |
| **Lambda SQS consumer** | Execution role with SQS read/delete permissions and CloudWatch Logs | ESM config, queue policy, `kms:Decrypt` for encrypted queues by key type |
| **SNS fanout producer** | Queue policy `sqs:SendMessage` for the SNS service | `aws:SourceArn` topic condition, cross-account/KMS policies |
| **DLQ/redrive admin** | `sqs:StartMessageMoveTask` and related task permissions | Separate ops permissions from app permissions; review before redrive |

**Encryption:** SQS supports server-side encryption via SQS-managed keys or AWS KMS as configured. With a customer managed KMS key, involved principals need matching KMS permissions; **encryption at rest does not replace SQS permissions**. For SNS → encrypted SQS queue, verify KMS key policy grants for the **SNS service principal** per supported architecture.

### 23.2. VPC endpoints for workers in private subnets

ECS/EC2/EKS workers in private subnets calling the SQS API need either:

- Outbound connectivity to the public SQS endpoint via an appropriate egress path **or**
- An **Interface VPC endpoint for Amazon SQS** with Private DNS, an endpoint SG allowing inbound TLS/443 from worker SGs, an endpoint policy, and proper DNS/routes.

**SQS API traffic uses HTTPS/443**, not TCP/2049 like EFS or database ports. Never open inbound traffic from the Internet to workers so SQS can push messages; **consumers actively initiate `ReceiveMessage`**.

**Lambda SQS ESM** polling is managed by the Lambda service itself, not a `ReceiveMessage` loop inside your VPC-attached function code. The function only needs VPC networking, endpoints, or NAT for **AWS APIs your code calls directly** or private database connections.

### 23.3. Data and policy controls

- Never put passwords, tokens, cardholder data, or sensitive PII in message bodies without proper requirement and protection.
- Even when bodies contain only IDs referencing sensitive data, IAM and encryption must restrict access per principal and queue.
- Use temporary AWS credentials from IAM instance profiles, ECS task roles, EKS Pod Identity, or Lambda execution roles instead of static access keys.
- Use queue policies restricting cross-account/SNS source ARNs, KMS key policies, SCPs, and VPC endpoint policies per environment.
- Never write **`ReceiptHandle`** or full sensitive message bodies to public logs; a receipt handle is an actionable token for receiving/deleting within SQS permissions.

## 24. Monitoring: Watching Backlog, In-Flight, and Ack Errors Together

Amazon SQS publishes metrics under CloudWatch's **`AWS/SQS`** namespace. Backlog counts are **approximate** because SQS is a distributed system.

| Metric | Meaning | When to alert |
| --- | --- | --- |
| **`ApproximateNumberOfMessagesVisible`** | Messages currently available to receive | Steadily rising backlog, under-provisioned consumers |
| **`ApproximateNumberOfMessagesNotVisible`** | In-flight messages | Workers holding messages too long, excessive prefetch, or missing acks |
| **`ApproximateNumberOfMessagesDelayed`** | Messages held by delivery delay | Avoid mistaking delayed messages for an empty queue |
| **`ApproximateAgeOfOldestMessage`** | Age of oldest unprocessed message per SQS semantics | Risk of violating business SLA; mind poison-pill/FIFO nuances |
| **`NumberOfMessagesReceived`** | Messages returned by receive calls | High redeliveries; not unique business events |
| **`NumberOfMessagesDeleted`** | Delete operations recorded by SQS | Not equal to unique successful business transactions |
| **`NumberOfEmptyReceives`** | Receive calls returning no messages | Excessive short polling, long polling/idle behavior |
| **`NumberOfMessagesSent`** | Messages sent via API | Traffic spikes, anomalous producers |
| **`ApproximateNumberOfGroupsWithInflightMessages`** (FIFO) | Groups with active in-flight messages | Large backlog with few active groups limits parallelism |
| **DLQ `ApproximateNumberOfMessagesVisible`** | Messages available in the DLQ | Poison messages or retries exceeding threshold |

### Avoiding metric misinterpretation

- `NumberOfMessagesReceived` can exceed `NumberOfMessagesSent` because **the same message is redelivered**.
- `NumberOfMessagesDeleted` counts valid delete calls; **not unique `eventId`s committed**.
- Standard queue `ApproximateAgeOfOldestMessage` has specific rules for **repeatedly received poison-pill messages**; never diagnose solely from a single age datapoint.
- DLQ auto-redrive does not necessarily increment the DLQ's `NumberOfMessagesSent` the same way a direct producer send does; monitor **DLQ visible count** and age.

### Minimum recommended alarms

1. **DLQ messages > 0** over a meaningful evaluation period.
2. **Visible backlog** growing continuously or breaching backlog/time-to-process SLOs.
3. **Oldest message age** exceeding order-processing thresholds.
4. **High in-flight count** without corresponding delete/success rates.
5. **High `NumberOfEmptyReceives`** relative to real traffic; review long polling.
6. Worker errors/timeouts/throttles, Lambda Errors/Duration/ConcurrentExecutions, or ECS task health.
7. Unexpected surges in SQS, KMS, NAT, or CloudWatch costs.

**CloudWatch does not replace application metrics**. Emit `orders_processed_success`, `orders_duplicate_ignored`, `processing_duration_p99`, `delete_error_count`, `heartbeat_extensions`, and `side_effect_commit_failures` directly from workers.

## 25. Performance and Cost: Request Count Is Not Order Count

SQS pricing depends on requests, message payload size/tiers, queue type, and Region, alongside KMS, data transfer, VPC endpoints, Lambda invocations, logs, and worker compute. Track total cost accordingly:

\[
C_{\text{approx}} \approx
C_{\text{SQS API}}
+ C_{\text{worker compute}}
+ C_{\text{KMS/requests}}
+ C_{\text{network}}
+ C_{\text{logging}}
+ C_{\text{DLQ/re-drive}}
\]

### 25.1. Batching cuts overhead but raises in-flight exposure

To process 1,000 events if every receive returns exactly 10 messages, the minimum `ReceiveMessage` count in that idealized example is 100 instead of 1,000. In practice, SQS can return **fewer than requested** and batch deletes can partially fail. Never assume API calls always equal 1,000/10.

### 25.2. Long polling cuts empty receives

For sparse queues, `WaitTimeSeconds=20` with a sufficient client timeout usually costs less than polling every few hundred milliseconds. Keep in mind:

- Holding a 20-second wait on a client thread consumes worker/connection resources;
- Tight retries after an HTTP timeout inflate requests and logs;
- When messages are waiting, long polls return immediately without waiting 20 seconds;
- Lambda ESM handles polling itself; never add a second long-poll loop inside the handler.

### 25.3. Both overly short and overly long visibility affect cost

- **Too short** → duplicate processing, extra S3/DB/API calls, retries/DLQ churn, and wasted worker capacity.
- **Too long** → slow recovery after crashes, degraded backlog/SLOs, and potentially higher standby worker/concurrency needs.
- **Frequent heartbeats** → extra SQS API calls, though often worthwhile to avoid restarting expensive long jobs.

**Better metric:** cost per **unique successfully processed event** and end-to-end latency from enqueue to commit, rather than raw receive counts.

## 26. Common Errors and How to Handle Them

| Symptom | Common cause | Diagnostic action |
| --- | --- | --- |
| Message processed twice | Visibility too short, crash after commit before delete, standard at-least-once | Trace `eventId`, `ReceiptHandle` per receive (mask sensitive values), check DB idempotency |
| Queue has backlog but `ReceiveMessage` returns empty | Short polling false empty, in-flight/delayed messages, FIFO group blocking | Use `Wait=20`, check Visible/NotVisible/Delayed, inspect FIFO group count |
| Worker cannot delete message | Passing `MessageId` instead of `ReceiptHandle`, stale handle, IAM deny | Use latest `ReceiptHandle`, verify `sqs:DeleteMessage`, check queue policy |
| `DeleteMessage` returns 200 but message remains | Stale `ReceiptHandle`, distributed duplicate, race condition | Check idempotency + logs/metrics; ensure current receive's handle is used |
| Message stays hidden too long after crash | Visibility timeout set too high | Measure processing time, lower default / use heartbeats, alert on age |
| Message keeps returning | Delete skipped after success, handler throws, timeout, poison data | Check app logs, DLQ, receive count, commit/ack sequence |
| `ChangeMessageVisibility` fails | Handle expired, exceeded remaining 12-hour cap, IAM deny | Check elapsed time since receive, latest handle, `sqs:ChangeMessageVisibility` |
| Consumer receives `OverLimit` | Too many in-flight standard messages | Reduce prefetch, delete promptly, check hung workers and quotas |
| Long poll returns empty despite backlog | Hit in-flight cap; FIFO group locked; visibility/delay | Check CloudWatch NotVisible/FIFO groups, inspect worker status |
| Long polls frequently hit socket/read timeouts | HTTP client timeout ≤ `WaitTimeSeconds` | Set client timeout > wait, check SDK settings, proxy/network |
| FIFO throughput stays low despite more workers | Too few `MessageGroupId`s, one message blocking a group | Partition group key appropriately; verify ordering needs |
| Lambda succeeds yet messages reprocess | Another record in batch failed, handler threw, timeout | Check ESM batch errors, `ReportBatchItemFailures`, idempotency |
| Lambda mapping creation/update rejected | Function timeout > queue visibility | Raise visibility, review 6x + batching window guidance |
| Lambda fails to poll encrypted queue | Missing execution role or KMS key policy grants | Verify `sqs:ReceiveMessage`, `kms:Decrypt`, queue/key policies |
| DLQ fills up rapidly | Business validation failures, schema drift, failing dependency | Sample messages safely, classify retryable vs. permanent, fix root cause before redrive |
| Messages expire in DLQ | DLQ retention too short; standard queue original age | Adjust retention strategy, set alarms and runbooks |
| SNS fanout never reaches queue | Queue policy lacks SNS `sqs:SendMessage`, wrong `SourceArn`, KMS policy | Check subscription status, SNS delivery metrics, SQS/KMS policies |
| Consumer in private VPC times out | Missing NAT or SQS interface endpoint, DNS, or endpoint SG | Check routes/VPC endpoint, HTTPS 443, endpoint policy |
| DB updated multiple times by same event | Missing idempotency/atomic constraints | Implement inbox/outbox, unique keys, conditional writes, reconciliation |

### Step-by-step investigation flow

~~~text
1. Verify account, Region, queue URL/ARN, and Standard vs. FIFO.
2. Inspect queue attributes: VisibilityTimeout, ReceiveMessageWaitTimeSeconds,
   MessageRetentionPeriod, RedrivePolicy, encryption, and delay.
3. Review CloudWatch Visible, NotVisible, Delayed, OldestAge, EmptyReceives.
4. Check real consumer state: EC2/ECS/EKS/Lambda mapping, IAM, KMS, networking.
5. Inspect eventId, MessageId, ApproximateReceiveCount, processing duration.
6. If ack fails: verify latest ReceiptHandle, DeleteMessage response,
   timing relative to visibility, and batch delete partial errors.
7. If retrying: classify transient vs. permanent, DLQ maxReceiveCount,
   visibility/heartbeat, idempotency, and business transactions.
8. If FIFO: inspect MessageGroupId, group blocking, and record order.
9. Fix the smallest root cause, test happy-path + failure-path in lab,
   monitor backlog/success/duplicates, and document in a runbook.
~~~

**Never “fix” issues by** setting 12-hour visibility on every message, removing the DLQ, purging the queue, opening IAM `sqs:*`/KMS `*`, or disabling idempotency for speed. Those shortcuts hide failures and increase data-loss risk.

## 27. Recommended Architectures by Scenario

### A. Generating invoices after order placement

**Requirement:** Fast storefront checkout; PDF generation takes 10–90 seconds; system uses S3 and DynamoDB.

**Design:**

- API Gateway/Lambda or ECS Order API commits the order, then emits `OrderCreated` via a transactional outbox or suitable event bridge.
- SQS standard queue `invoices`, 20-second long polling for ECS workers or Lambda ESM.
- Initial visibility around p99 processing + margin; heartbeat extensions if unpredictable long jobs occur.
- Worker writes invoices with idempotent key `invoices/{orderId}.pdf` and conditional DynamoDB status updates.
- Call **`DeleteMessage` only after S3/DB commits succeed**; configure a DLQ with `maxReceiveCount` aligned to the retry budget.
- CloudWatch DLQ alarms, message age, worker errors, S3/KMS permissions, and backup/versioning.

**Lesson:** The same event can be reprocessed; idempotency lives in the data store, not in setting a huge visibility timeout.

### B. Payment event sequence strictly ordered per order

**Requirement:** `OrderCreated → PaymentCaptured → InvoiceIssued` must never reorder within an order, while different orders run concurrently.

**Design:**

- SQS FIFO `order-events.fifo` with `MessageGroupId=orderId`.
- Producer supplies a stable `MessageDeduplicationId` across send retries within 5 minutes.
- Consumer processes sequentially and persists business state with version checks / optimistic locking.
- An in-flight message in a group holds back subsequent messages in that group; configure visibility, retries, and DLQ carefully.
- When using Lambda partial batch failures on FIFO, **stop at the first error** and return all failed and unprocessed IDs.

**Lesson:** FIFO solves in-group delivery ordering, not transactions, state-transition guards, or idempotency.

### C. Notification fanout to multiple independent teams

**Requirement:** When an order is created, send an email, update BI, and generate an invoice concurrently.

**Design:**

- SNS topic `orders-events` fans out to three separate SQS queues.
- Each consumer configures its own visibility, long polling, DLQ, and retry policy tailored to its processing time.
- Email worker records idempotency alongside/with the email provider to prevent duplicate sends.
- SNS topic, queue, and KMS policies enforce exact principals and `SourceArn`.
- Never share a single queue across three independent services expecting each to get a copy: **multiple SQS consumers on one queue compete for messages rather than fanning out**.

### D. Extremely long jobs over 12 hours

**Requirement:** Video transcoding or data analytics running for hours or days.

**Unsuitable approach:** Keeping an SQS message in-flight indefinitely with heartbeats; the **12-hour maximum limit** still applies.

**Better design:** Use **Step Functions** or AWS Batch/ECS jobs suited to the workload, checkpoint progress to S3/DB, split into smaller stages/tasks, and emit the next message after each checkpoint commits. SQS acts as a work trigger, not an unbounded execution lock.

## 28. Exercises and Self-Check Questions

### Exercise 1 — Sizing visibility with p99 processing

A worker processes 99% of messages within 38 seconds; commit + `DeleteMessage` typically take 2 seconds; allow a 20-second safety margin.

1. Pick initial visibility via the starting formula: **38 + 2 + 20 = 60 seconds**.
2. If 1% of jobs take 4 minutes, explain why heartbeats or a separate queue/job tier are needed.
3. If a worker crashes at second 3, how does a 60-second visibility compare to 10 minutes in terms of retry delay?
4. Propose metrics to measure **duplicate processing** and **time from enqueue to commit**.

### Exercise 2 — Received successfully, failed to delete

A consumer receives `MessageId=M1`, `ReceiptHandle=H1` at 10:00:00 with 30-second visibility. The worker commits to the DB at 10:00:25 but crashes before calling delete. Another consumer receives the message at 10:00:35 with `ReceiptHandle=H2`.

**Task:** State the message state at 10:00:15 and 10:00:31; explain why `H1` and `H2` differ; design idempotency so two invoices are never created; identify when deletion is safe.

### Exercise 3 — “Deleted it, yet the message came back”

Worker A holds onto an old handle after visibility expires. B receives the same M1 with a new handle; A calls `DeleteMessage` using the old handle, receives HTTP 200, yet the message reappears.

Explain why **`DeleteMessage` requires the latest receipt handle**, why HTTP 200 alone does not prove a unique event is finished, and how `eventId`/conditional writes achieve once-only business effects.

### Exercise 4 — Long polling and cost

An idle worker continuously short-polls `ReceiveMessage` once per second. Propose 20-second long polling and compute the theoretical daily request counts:

- Short: **86,400**.
- Idle long: **4,320**.
- Difference: **82,080** calls/day.

State assumptions: zero messages, no reconnects/retries; real numbers differ when traffic exists. Also adjust **HTTP read timeout** and monitor **`NumberOfEmptyReceives`**.

### Exercise 5 — Lambda SQS batch

A batch contains M1–M5, and M3 fails:

1. What does Lambda ESM do by default if the handler throws?
2. With `ReportBatchItemFailures` enabled, what minimal response must be returned?
3. On a standard queue, why do M1/M2/M4/M5 avoid retries when partial response is valid?
4. On FIFO, why must the handler stop at M3 and return **M3, M4, M5** as failed/unprocessed?
5. Why do all records still need idempotency even with partial batch failures enabled?

### Exercise 6 — Excessive in-flight messages

An ECS service has 500 workers, each prefetching 10 messages while processing only one at a time. Average processing is 2 minutes, visibility is 60 seconds.

Analyze:

- Maximum messages held in-flight reaches roughly **5,000** if every worker fetches 10.
- Why 9 messages per worker can expire visibility while waiting in the local queue.
- How to adjust `MaxNumberOfMessages`, worker pools, heartbeats, and `DeleteMessage`.
- Which metric reveals high in-flight counts with low successful throughput.

### Exercise 7 — FIFO message groups

A FIFO queue holds 1,000 messages, all sharing **a single `MessageGroupId`**. Scaling consumers from 2 to 50 yields no throughput gain.

Explain group blocking and ordering; propose partitioning `MessageGroupId` by `orderId` or an appropriate key, and discuss cases where grouping **cannot** be split due to global business ordering.

### Exercise 8 — DLQ and retry policy

An order has a permanent `InvalidSku` error, gets received repeatedly, and lands in the DLQ.

Choose `maxReceiveCount` based on reliability and allowed retry window; classify transient vs. permanent failures; draft a runbook to inspect message samples safely, fix data or code, and redrive in a controlled way. Explain why **a DLQ does not absolve teams of responsibility for failed messages**.

### Short Questions

1. **Does `ReceiveMessage` delete a message?** No; it moves in-flight and becomes temporarily hidden.
2. **What is the primary ack API for a self-polling SQS consumer?** `DeleteMessage` with the latest `ReceiptHandle` after success.
3. **Can `MessageId` be used as `ReceiptHandle`?** No.
4. **Is a message deleted when visibility expires?** No; it can become visible again for redelivery.
5. **Does `WaitTimeSeconds=20` mean a 20-second visibility timeout?** No; that is the long-polling wait time.
6. **Does long polling always wait the full 20 seconds?** No; it returns early as soon as messages are available.
7. **Can `ChangeMessageVisibility` extend indefinitely?** No; there is a 12-hour total limit from receive time.
8. **Does a standard queue guarantee no duplicate deliveries within visibility?** Not absolutely; idempotency is required.
9. **Does FIFO deduplication replace business idempotency?** No.
10. **With Lambda SQS ESM, who deletes messages by default after batch success?** The Lambda service.
11. **Does a default Lambda batch failure affect already-succeeded records?** Yes, the whole batch can be retried.
12. **When an SNS topic fans out to three SQS queues, does the invoice worker deleting a message affect the analytics queue?** No.
13. **Does a DLQ automatically repair poison messages?** No; investigation and controlled redrive are required.
14. **Does one empty `ReceiveMessage` prove a queue has no messages?** No.

## 29. Pre-Production Checklist

- [ ] Selected **standard vs. FIFO** based on actual ordering, deduplication, and throughput needs—not FIFO just to “avoid all duplicates”.
- [ ] Producers emit events with a stable **business `eventId`** and schema version; `eventId` is never confused with `ReceiptHandle`.
- [ ] Appropriate publishing/transactional outbox flow prevents committed DB writes with lost events.
- [ ] Consumers strictly follow **receive → process → commit → delete** and handle uncertain delete retries safely.
- [ ] Durable **idempotency**, unique constraints/conditional writes, and mid-flight crash recovery are implemented.
- [ ] Visibility timeout is sized for p99 processing + margin, tested against long-tail jobs and crash recovery.
- [ ] If heartbeats are used, they renew ahead of expiration, stop on completion, cap job duration, and stay within 12 hours.
- [ ] Long polling `WaitTimeSeconds` is justified; HTTP client timeout exceeds wait time.
- [ ] Prefetch count never exceeds active processing slots; backpressure and batch delete partial errors are handled.
- [ ] For FIFO, `MessageGroupId` matches domain ordering with enough groups to sustain target throughput.
- [ ] **DLQ**, `maxReceiveCount`/retention, alarms, and a redrive runbook exist; failures are classified properly.
- [ ] For Lambda ESM, queue visibility aligns with Lambda timeout/batch window; full and partial batch failures are tested.
- [ ] For SNS fanout, queue/KMS policies, raw-vs-envelope delivery, and per-queue independent retry/ack are verified.
- [ ] Least-privilege IAM: producer `SendMessage`, consumer `Receive/Delete/ChangeVisibility`; no arbitrary wildcards.
- [ ] VPC workers have NAT or an **SQS interface endpoint** with HTTPS/443, Private DNS, and endpoint policy.
- [ ] SSE-SQS or SSE-KMS is enabled per requirements; KMS key policies, lifecycle, and producer/consumer grants are managed.
- [ ] SQS and application metrics/alerts cover visible/not-visible backlog, oldest age, empty receives, successful commits, and DLQ.
- [ ] Estimated costs for SQS requests/batching, Lambda/ECS/EC2 compute, KMS, VPC endpoints/NAT, logs, and retries.
- [ ] Rehearsed worker crashes **before commit**, **after commit before delete**, visibility expiration, FIFO poison messages, and redrive.
- [ ] IaC, tags, staging/prod isolation, rollback plans, and safe lab cleanup procedures are in place.

## 30. Summary

**Visibility timeout, long polling, and acknowledgment are three distinct mechanisms that work tightly together:**

- **Visibility timeout** hides a message after delivery so the consumer has time to process it; expiring without deletion makes it eligible for redelivery. It is **not a lock guaranteeing exactly-once execution**.
- **Long polling** lets `ReceiveMessage` wait up to 20 seconds for messages to arrive, cutting empty receives and typically lowering cost on quiet queues.
- **Acknowledgment** in SDK/CLI SQS consumers is **`DeleteMessage` with the latest `ReceiptHandle` after committing side effects**. With **Lambda SQS event source mapping**, Lambda handles message deletion according to full or partial batch results.

Combined with **DLQs, idempotency, FIFO message groups, IAM/KMS, VPC networking, CloudWatch, and budget controls**, a simple queue becomes a reliable event-processing backbone for AWS workloads on **Lambda, ECS, EC2, or EKS**. The goal is not “each handler runs strictly once”, but rather **every critical business effect is safe under retries, processed accurately, and recoverable when failures occur**.

### Official AWS Documentation

- [Amazon SQS visibility timeout](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-visibility-timeout.html)
- [ChangeMessageVisibility API](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/APIReference/API_ChangeMessageVisibility.html)
- [DeleteMessage API and receipt handles](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/APIReference/API_DeleteMessage.html)
- [SQS short and long polling](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-short-and-long-polling.html)
- [Best practices: setting up long polling](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/best-practices-setting-up-long-polling.html)
- [SQS best practices: processing messages in a timely manner](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/best-practices-processing-messages-timely-manner.html)
- [FIFO queue delivery logic](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/FIFO-queues-understanding-logic.html)
- [FIFO exactly-once processing/deduplication](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/FIFO-queues-exactly-once-processing.html)
- [SQS dead-letter queues](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-dead-letter-queues.html)
- [SQS CloudWatch metrics](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-available-cloudwatch-metrics.html)
- [AWS Lambda with Amazon SQS](https://docs.aws.amazon.com/lambda/latest/dg/with-sqs.html)
- [Configure Lambda SQS event source mapping](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-configure.html)
- [Lambda SQS error handling and partial batch responses](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-errorhandling.html)
- [AWS CLI sqs receive-message](https://docs.aws.amazon.com/cli/latest/reference/sqs/receive-message.html)
- [AWS SDK for Java v2 SQS examples](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/java_sqs_code_examples.html)
- [SQS with SNS subscriptions](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-configure-subscribe-queue-sns-topic.html)
- [SQS pricing](https://aws.amazon.com/sqs/pricing/) and [Lambda pricing](https://aws.amazon.com/lambda/pricing/)

**Operational note:** Pricing, AWS quotas, SDK/API parameters, and integration behaviors can vary by Region, account, and over time. Cross-check current documentation and validate in a lab environment before applying to production data.
