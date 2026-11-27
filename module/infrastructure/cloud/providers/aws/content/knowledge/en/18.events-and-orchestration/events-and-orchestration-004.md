# EventBridge Pipes and connecting sources to targets

## Learning objectives

After this lesson, learners will be able to:

- Explain **Amazon EventBridge Pipes** and clearly distinguish **source**, **filter**, **input transformation**, **enrichment**, and **target**.
- Identify sources that Pipes can actively poll, such as **Amazon SQS**, **DynamoDB Streams**, **Kinesis Data Streams**, **Amazon MQ**, **Amazon MSK**, and **self-managed Apache Kafka**.
- Design **one source → one target** integrations and know when to forward events to an **EventBridge event bus** to fan out to multiple consumers instead of attaching multiple Pipes to the same queue.
- Write filter patterns for SQS message bodies, and distinguish **filtering** from **payload transformation** and **enrichment** via Lambda/Step Functions Express/API Gateway/API Destination.
- Choose appropriate targets such as **Lambda**, **Step Functions**, **SQS**, **SNS**, **event bus**, **ECS task**, or **API Destination**, and understand synchronous/asynchronous behavior.
- Configure batching, concurrency, retries, DLQs, idempotency, and latency control—especially for **SQS FIFO** or **Kinesis/DynamoDB Streams** requiring ordering.
- Grant the proper **IAM execution role** for Pipes with `pipes.amazonaws.com` trust, source/enrichment/target permissions, KMS, and VPC/broker connectivity when required.
- Create a Pipe with **AWS CLI**, test matching/non-matching events, observe state, logs, and metrics, and troubleshoot common configuration errors.
- Compare Pipes with **EventBridge rules**, **Lambda event source mapping**, **Step Functions**, and self-managed pollers to pick a right-sized solution.
- Estimate costs by event count **after filtering**, payload size, batching, and related services; set up alerts, backup/replay, and recovery plans.

**Module context:** This lesson belongs to the **Events and Orchestration** chapter of the **CLOUD_PROVIDERS_AWS** module. Learners have already covered Region/AZ, IAM, VPC, compute, storage, databases, integration, and serverless. EventBridge Pipes ties those pieces together in an event-driven architecture, reducing glue code while **not replacing the responsibility of designing semantics, security, monitoring, resilience, and budgets**.

> **Scope:** The primary example is **SQS queue → EventBridge Pipe → AWS Lambda Java** in one Region within a lab account. ARNs, queue URLs, role names, API IDs, and resources are illustrative. Before production use, verify supported sources/targets and limits by **Region, account, date, and source/target type** in current AWS documentation.

## 1. Real-world scenario: delivering events to the right place without writing a poller

An ordering system emits several event types into SQS:

~~~json
{
  "eventId": "evt-order-501",
  "eventType": "OrderPaid",
  "orderId": "ORD-501",
  "customerId": "C-42",
  "occurredAt": "2026-11-20T04:00:00Z"
}
~~~

Consumers have different needs:

- `OrderPaid`: generate an invoice in Lambda or trigger an order fulfillment workflow.
- `OrderCancelled`: invoke refund logic.
- `OrderViewed`: analytics only—no need to invoke the invoicing Lambda.

If implemented manually, the team must write code to call `ReceiveMessage`, filter JSON, call target APIs, manage visibility, retries, rate/concurrency, logs, metrics, and delete messages appropriately. **EventBridge Pipes** turns this connection and transport plumbing into **configuration**.

~~~mermaid
flowchart LR
    Producer[Order API / producer] --> Queue[(SQS orders-events)]
    Queue --> Pipe[EventBridge Pipe]
    Pipe --> Filter{Filter eventType=OrderPaid}
    Filter -->|Match| Enrich[Optional enrichment]
    Enrich --> Target[Lambda / Step Functions / SQS]
    Filter -->|No match| Drop[Not sent to target]
    Target --> Data[(S3 / DynamoDB / RDS)]
    Pipe --> Obs[CloudWatch logs & metrics]
~~~

With an **SQS** source, messages that **do not match the filter are removed from the queue by Pipes** rather than remaining for another consumer to pick up. This is an essential design point: **SQS is not a fan-out event bus**.

## 2. What is Pipes and what is it not?

**Amazon EventBridge Pipes** provides **point-to-point** integration:

\[
\text{Source} \rightarrow [\text{Filter}] \rightarrow [\text{Enrichment}] \rightarrow \text{Target}
\]

Where:

| Component | Responsibility | Required? |
| --- | --- | --- |
| **Source** | Source from which Pipes receives/polls events | Yes |
| **Filter** | Selects events matching an event pattern | No |
| **Enrichment** | Calls a service to add data/validate/shape before target | No |
| **Target** | Final destination where the Pipe sends data or invokes an API | Yes |
| **Execution role** | Permissions for Pipes to read source and invoke enrichment and target | Yes |
| **Logging/metrics** | Operational observability, errors, throttling, and throughput | Configure as needed |

One Pipe has **one source and one target**. Multiple Pipes can write to the same target, but **not** one Pipe with multiple targets.

Pipes **is not**:

- A new durable queue replacing SQS.
- An EventBridge rule fanning out events from an event bus to multiple targets.
- A transactional system guaranteeing once-only writes to DB/S3.
- A multi-step business workflow orchestrator with wait/choice/compensation like **Step Functions**.
- An unlimited custom ETL engine: filtering/transformation are bounded, and enrichment must use supported services.
- A container worker you run 24/7: Pipes manages receiving/pushing from supported sources.

**Service selection question:** Do you need to **move events from one supported source to one target with filtering/enrichment**? Pipes fits well. Need **fan-out**? Use an event bus/SNS or multiple queues. Need a **multi-step/stateful workflow**? Use Step Functions, which Pipes can trigger.

## 3. Comparing Pipes, EventBridge rules, Scheduler, and Lambda ESM

| Criterion | **EventBridge Pipes** | **EventBridge event bus + rules** | **EventBridge Scheduler** | **Lambda event source mapping (ESM)** |
| --- | --- | --- | --- | --- |
| Starting point | Supported SQS/streams/brokers | Event published to a bus | Recurring/one-time schedule | Lambda poller-compatible source |
| Goal | One source → one target, with filter/enrichment | Match and route events to multiple targets | Invoke target at a specific time/cadence | Invoke a Lambda from a source |
| Filter | Event patterns on source records | Event patterns on bus events | Not for filtering stream events | Filter criteria in ESM per source |
| Enrichment | Lambda, API Gateway, API Destination, Express workflow | Typically Lambda/Step Functions targets for enrichment | Not an enrichment pipeline | Enrichment logic written inside Lambda |
| Fan-out | Not directly; can send to a bus | Well-suited | No | Not directly |
| Retry/DLQ | Depends on source and target invocation | Event bus target retries/DLQ per rule | Scheduler retries/DLQ per schedule | Per ESM + source |
| Best fit | Connecting data source and target with minimal glue code | Routing domain events | Time-based/scheduled tasks | Only need Lambda consuming SQS/stream |

**Selection examples:**

- **SQS → Step Functions** with filtering and enrichment: consider **Pipes**.
- **One `OrderPaid` event → 5 systems**: use **EventBridge bus/rules** or **SNS fan-out → multiple queues**, not 5 Pipes competing over one SQS queue.
- **Job at 02:00**: use **Scheduler**.
- **Only SQS → Lambda with all logic inside Lambda**: **Lambda ESM** can be simpler than a Pipe.

## 4. Supported sources and their different semantics

Per the EventBridge Pipes source catalog, key sources include:

| Source | Data type | Key points to remember |
| --- | --- | --- |
| **Amazon SQS** | Queue messages, standard or FIFO | Pipes polls and **deletes messages when pipe processing succeeds**; visibility, source DLQ |
| **DynamoDB Streams** | Change data capture records | Stream checkpoints/retention, starting position, shard ordering |
| **Kinesis Data Streams** | Streaming records by shard/partition key | Shard positions, throughput, parallelization factor |
| **Amazon MQ** | Broker messages | Broker/network/auth, broker-specific acknowledgments |
| **Amazon MSK** | Managed Kafka topics | Partitions, offsets, networking, broker auth |
| **Self-managed Apache Kafka** | Kafka topics from self-managed or third-party clusters | Bootstrap brokers, VPC/connectivity, secrets, offset semantics |

**Do not treat an `S3 bucket`, `RDS database`, or `EventBridge event bus` as a direct Pipes source just because they are AWS services.** To trigger Pipes from S3 data, you typically design **S3 notification → SQS** or **EventBridge event bus → target**. For RDS data, events/CDC must be published to a supported source.

### Choosing a source by data characteristics

- **Queue (SQS):** suited for distributing work across consumers; messages are deleted after successful processing; retries rely on visibility timeout.
- **Stream (Kinesis/DynamoDB):** records remain in the stream for its retention period while consumers/iterators track checkpoints; replayable within the retention window.
- **Broker (MQ/Kafka):** uses message acknowledgments or offsets/partitions, requiring dedicated network/auth and ordering design.

**Do not copy SQS retry/DLQ settings blindly to Kinesis or Kafka.** Each source has different commit/checkpoint, retention, and failure semantics.

## 5. Designing a one-source → one-target architecture

A Pipe should be tied to a clear data contract:

~~~text
Producer: Order Service
  source: SQS orders-events-lab
  event contract: OrderEvent v1

EventBridge Pipe: paid-orders-pipe
  filter: eventType == OrderPaid
  transform/enrichment: optional
  target: Lambda process-paid-order

Target:
  validate eventId/orderId
  check idempotency & tenant
  write state/S3 and commit

Operations:
  SQS DLQ, CloudWatch alerts, IAM role & KMS
  logs without secrets, retry/rollback strategy
~~~

Decide early:

1. **Who owns messages that do not match the filter?** With an SQS source, Pipes deletes them from the queue; ideally the queue is dedicated to that event type, or the producer pre-routes.
2. **What if the target returns success before business work finishes?** Choose appropriate invocation semantics, idempotency, and durable handoff mechanisms.
3. **What if enrichment is unavailable?** The Pipe may retry and stall source progress depending on source characteristics.
4. **What if the source loses retention or is deleted?** Maintain backups/replay/outbox and runbooks.
5. **What if downstream is slower than the source rate?** Plan quotas/concurrency/backpressure or intermediate buffering queues.

**A properly configured Pipe does not mean the system meets HA/DR requirements.** You must evaluate the data source, target, database, and resources in every AZ/Region.

## 6. SQS source: who manages Receive, visibility, and acknowledgment?

With an **SQS** source, EventBridge Pipes behaves much like a managed consumer:

1. Polls SQS and retrieves a message/batch.
2. Messages become **in-flight**, hidden for the **queue visibility timeout**.
3. Evaluates the filter.
4. On match, optionally transforms/enriches and invokes the target.
5. When the Pipe processes the batch successfully per target semantics, Pipes **deletes the corresponding messages** from the source queue.
6. On failure, messages typically become visible again when visibility expires; the **source queue's DLQ** applies after `maxReceiveCount` per the redrive policy.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant SQS as Source SQS
    participant Pipe as EventBridge Pipes
    participant T as Target Lambda
    P->>SQS: SendMessage
    Pipe->>SQS: ReceiveMessage
    SQS-->>Pipe: Message + receipt handle
    Pipe->>Pipe: Filter / transform / enrichment
    alt Target invocation succeeds
      Pipe->>T: Invoke
      T-->>Pipe: Success
      Pipe->>SQS: DeleteMessage
    else Target or enrichment fails
      Pipe->>T: Invoke or enrichment failed
      T-->>Pipe: Error
      Note over SQS: Message retried per visibility/retry
    end
~~~

**With an SQS source, do not attach another manual consumer to the same queue to "help the Pipe"** unless you intentionally load-share identical consumers. Two consumers/pipes on one queue **compete for messages**, rather than copying them.

### Warning about SQS filtering

If a filter pattern does not match, Pipes **automatically deletes the non-matching message** from the source queue. It does not *put it back for another filter*. For instance, a Pipe filtering only `OrderPaid` on a shared queue can drop `OrderCancelled` messages on that queue. If both need processing, **design producer routing/fan-out or use an event bus/SNS**.

### SQS visibility timeout with enrichment

AWS recommends setting source queue visibility to **at least roughly 6 times the combined runtime of enrichment and target** so the Pipe has headroom to retry on throttling, plus margin and batching window. This is a **guideline**, not a guarantee against duplicate delivery. A Pipe execution also has its own duration limit (see batching), and business side effects must be idempotent.

## 7. Stream sources: Kinesis, DynamoDB, and starting positions

### DynamoDB Streams

Pipes reads change records from a DynamoDB Stream. You configure:

- **StartingPosition**: `TRIM_HORIZON` or `LATEST`;
- batch size/window, parallelization factor;
- retry attempts and maximum record age;
- DLQ per stream-source capabilities;
- IAM `DescribeStream`, `GetShardIterator`, `GetRecords`, `ListStreams`.

DynamoDB Streams typically retain records for **24 hours**. If a target outage lasts longer than retention, records can expire before the Pipe processes them. **DLQ and retry age must be set smaller than actual retention** if you need to capture failed records.

### Kinesis Data Streams

Kinesis has shards and partition keys, affecting throughput/ordering. A Pipe can increase per-shard concurrency via `ParallelizationFactor` (typically 1–10 as supported), while still preserving order per partition key.

**Do not assume multiple shards mean all events reach the target in one global order.** Ordering applies only per shard/partition key and source semantics.

### `LATEST` vs. `TRIM_HORIZON`

| Position | Behavior | When appropriate |
| --- | --- | --- |
| `LATEST` | Starts near the newest records | Historical data not needed; creation/update window risk acceptable |
| `TRIM_HORIZON` | Starts from the oldest un-expired record | Must avoid missing events emitted before the poller becomes active |

**Eventual consistency warning:** AWS notes that when creating or updating a stream-source Pipe, the poller can take some time to start; using `LATEST` **risks missing records written during the create/update window**. If event completeness is mandatory, evaluate `TRIM_HORIZON`, idempotency, and retention windows.

### A stream is not SQS

Kinesis/DynamoDB records are not deleted by `DeleteMessage`; the Pipe manages checkpoints/iterators, and records expire at retention end. Never describe stream retries as "waiting a 30-second visibility timeout."

## 8. Amazon MQ, MSK, and self-managed Kafka sources

For broker sources:

- **Amazon MQ**: brokers have engine-specific queues/topics and acknowledgments; the Pipe needs broker connectivity, credentials, and describe/network permissions.
- **Amazon MSK**: reads records from Kafka partitions, managing offsets and ordering within a partition.
- **Self-managed Kafka**: requires bootstrap brokers, auth (such as SASL credentials/TLS per config), reachability, and operating external clusters if applicable.

### Networking is an architectural component, not optional

Brokers typically sit in private subnets or private networks. A Pipe may need:

- VPC subnets and security groups aligned with the broker;
- ENIs and permissions to describe/create/delete network interfaces per documentation;
- routes/DNS to broker endpoints and exact Kafka/MQ ports;
- Secrets Manager/KMS policies when credentials are used;
- NAT or a **`pipes-data` VPC endpoint** where Pipes control/data connectivity requires it per AWS guidance.

**Distinction:** An SQS source uses AWS-managed SQS APIs and does not require placing a "Pipe compute node" in your VPC; private broker sources have different VPC/network requirements. Never open broker ports to the Internet just so a Pipe can read them.

### Ordering, parallelism, and retries

Kafka partitions and MQ sources have different concurrency constraints than SQS standard. One failing partition/group can stall progress. Measure **consumer lag**, throughput, and processing duration; increase partitions or Pipe concurrency only when business ordering and broker capacity allow.

## 9. `FilterCriteria`: deciding which events move forward

Filtering in Pipes uses **EventBridge event patterns**; it can inspect metadata or fields inside JSON payloads parsed/decoded per source. With SQS, the message body can be a JSON string:

~~~json
{
  "eventId": "evt-2001",
  "eventType": "OrderPaid",
  "orderId": "ORD-2001",
  "amount": 150000
}
~~~

When the SQS message body is valid JSON, a filter pattern to match only `OrderPaid` is:

~~~json
{
  "body": {
    "eventType": ["OrderPaid"]
  }
}
~~~

**The `body` wrapper is critical.** The filter evaluates against the **SQS record envelope**; `eventType` lives inside the JSON `body`, not at the root of the SQS record.

### `FilterCriteria` structure in the Pipes API

~~~json
{
  "Filters": [
    {
      "Pattern": "{\"body\":{\"eventType\":[\"OrderPaid\"]}}"
    }
  ]
}
~~~

`Pattern` in the AWS API is **a JSON string containing an event pattern**, not a raw JSON object attached directly to the field. Multiple `Filters` inside `FilterCriteria` follow service semantics; test concrete cases rather than assuming JavaScript `&&` combination behavior.

### Adding an amount condition

~~~json
{
  "body": {
    "eventType": ["OrderPaid"],
    "amount": [
      {
        "numeric": [">=", 100000]
      }
    ]
  }
}
~~~

The example above forwards only `OrderPaid` events with `amount >= 100,000` when the input is a JSON number. If `amount` is a string `"150000"`, the numeric filter will not match; enforce a producer schema contract.

### Filters do not replace business validation

- Filters select/discard events; they do not verify DB transactions.
- Filters do not know whether the customer is entitled to goods or the card charge actually settled.
- With an SQS source, **non-matching messages are deleted from the queue**; a wrong filter drops events.
- If a body is not valid JSON as expected, a JSON-based filter may discard that message; test with canary/sample payloads before enabling.
- **EventBridge Pipes bills for events matching the filter**, alongside SQS/broker/source and downstream costs.

## 10. Why not put two differently filtered Pipes on the same SQS queue?

Imagine:

~~~text
SQS orders-events
   ├── Pipe A filters eventType=OrderPaid  → invoice Lambda
   └── Pipe B filters eventType=OrderCancelled → refund Lambda
~~~

This is **not fan-out**. The two Pipes are competing consumers. If Pipe A receives `OrderCancelled`, filter A does not match and Pipes **deletes the message**—Pipe B never gets a chance to see it.

### Proper architecture for fan-out

~~~mermaid
flowchart TB
    Producer[Order Service] --> Bus[(EventBridge event bus)]
    Bus --> Rule1[Rule: OrderPaid]
    Bus --> Rule2[Rule: OrderCancelled]
    Rule1 --> Invoice[Invoice Lambda / SQS]
    Rule2 --> Refund[Refund Lambda / SQS]
    Bus --> Rule3[Rule: All business events]
    Rule3 --> Analytics[Analytics destination]
~~~

Or:

~~~text
Order Service → SNS topic → SQS invoice queue
                          → SQS refund queue
                          → SQS analytics queue

Each queue has its own Pipe / Lambda ESM / worker.
~~~

If starting from a single stream source that needs fan-out, you can configure **Pipe → supported EventBridge event bus target**, then use **rules** to route to multiple targets. Pipes target documentation specifies restrictions on same-account/Region buses and bus types, so verify the destination bus ARN/type before deploying; **do not assume every custom/cross-account bus works directly**.

## 11. Input transformation: reshaping payloads without running code

After filtering, you can use **`InputTemplate`** to normalize data sent to enrichment or the target.

Example SQS envelope:

~~~json
{
  "messageId": "msg-123",
  "body": "{\"eventId\":\"evt-2001\",\"orderId\":\"ORD-2001\",\"eventType\":\"OrderPaid\"}",
  "attributes": {
    "ApproximateReceiveCount": "1"
  }
}
~~~

If the target only needs `eventId`, `orderId`, and `eventType`, `InputTemplate` can be:

~~~text
{
  "eventId": "<$.body.eventId>",
  "orderId": "<$.body.orderId>",
  "eventType": "<$.body.eventType>"
}
~~~

Pipes can **parse SQS JSON bodies** when valid, allowing JSONPath to reference `$.body.eventId`. Pay attention to `InputTemplate` formatting and quoting for scalar vs. JSON object variables; **do not use ad-hoc string replacement that breaks JSON escaping**.

### Where does `InputTemplate` live?

| Location | Input transformed | Output sent to |
| --- | --- | --- |
| **`EnrichmentParameters.InputTemplate`** | Event read from source | Enrichment service |
| **`TargetParameters.InputTemplate`** | Enrichment result if present, otherwise source event | Target |

**If enrichment returns a new object**, the target input transformer usually sees **the object from enrichment**, no longer all original source metadata fields. If the target needs `messageId`, `eventId`, or correlation IDs for idempotency, **enrichment must preserve them in its response**.

### Reserved variables

Pipes provides service-reserved variables in `InputTemplate`, such as:

- `<aws.pipes.pipe-name>`: Pipe name;
- `<aws.pipes.pipe-arn>`: Pipe ARN;
- `<aws.pipes.source-arn>`: source ARN;
- `<aws.pipes.event.ingestion-time>`: timestamp when the event entered the transform stage;
- `<aws.pipes.event>` and `<aws.pipes.event.json>`: raw/JSON payload subject to conditions.

Do not place `<aws.pipes.event.json>` where a JSON string is expected if an object could be injected without proper escaping; consult the transform docs and test with real payloads.

### Data pitfalls

An `InputTemplate` that extracts only `orderId` while **dropping `eventId`** strips downstream of its idempotency key. Conversely, forwarding full message metadata and unnecessary PII/secrets bloats **payloads, logs, costs, and leak surfaces**. Choose **minimum necessary fields**.

## 12. Enrichment: adding context before sending to the target

**Enrichment** is an optional step that calls a service to turn a raw event into richer contextual data. For example, if the source provides `orderId`, enrichment queries DynamoDB to add customer tier, payment status, or fields needed by the target.

AWS-supported enrichment types include:

- **AWS Lambda function**;
- **API Gateway**;
- **EventBridge API Destination**;
- **AWS Step Functions Express workflow**.

**Do not use a Standard Step Functions workflow for enrichment**: enrichment requires a **synchronous response** so the Pipe knows what to forward to the target, whereas Step Functions **Express** supports synchronous integration.

~~~mermaid
sequenceDiagram
    participant S as SQS source
    participant P as Pipe
    participant E as Enrichment Lambda
    participant T as Target
    S->>P: Message OrderPaid
    P->>P: Filter match
    P->>E: Sync invoke(orderId, eventId)
    E->>E: Lookup customer/DB
    E-->>P: Enriched event + eventId
    P->>T: Enriched payload
    T-->>P: Ack / response per integration
    P->>S: Delete source message if entire pipe succeeds
~~~

### Enrichment limits to remember

1. Enrichment is invoked **synchronously**; the Pipe waits for a response before calling the target.
2. Enrichment response size is capped at **6 MB** per AWS limits.
3. One pipe execution (including enrichment and target) is capped at roughly **5 minutes**; do not choose Pipes to wait synchronously on a multi-hour workflow.
4. **Partial batch failure handling for enrichment is not supported** per published AWS batch semantics; if enrichment fails, the entire batch may have to retry.
5. Enrichment used as an **additional filter** can return an empty payload so the Pipe skips the target per service rules; test `""`, `{}`, `[]`, and `[{}]` cases to avoid unintended target calls.
6. If the target partially fails, retries may **re-run enrichment**, invoking enrichment a second time. Enrichment must avoid non-idempotent side effects.

**Prefer read/transform enrichment.** If enrichment charges a payment and the target subsequently fails, a retry risks double charging. Business side effects belong in a workflow with clear idempotency/transactions/recovery.

## 13. Lambda enrichment hands-on: preserving correlation and schema

Illustrative Java Lambda example taking one JSON event and adding `priority`. It skips DB calls to stay focused on shape:

~~~java
package com.example.events;

import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.RequestHandler;

import java.util.LinkedHashMap;
import java.util.Map;

public final class OrderEnrichmentHandler
    implements RequestHandler<Map<String, Object>, Map<String, Object>> {

    @Override
    public Map<String, Object> handleRequest(
        Map<String, Object> event, Context context) {

        String eventId = String.valueOf(event.getOrDefault("eventId", ""));
        String orderId = String.valueOf(event.getOrDefault("orderId", ""));

        if (eventId.isBlank() || orderId.isBlank()) {
            throw new IllegalArgumentException("eventId and orderId required");
        }

        Map<String, Object> enriched = new LinkedHashMap<>(event);
        enriched.put("priority", "NORMAL");
        enriched.put("enrichedBy", "orders-enrichment-v1");
        return enriched;
    }
}
~~~

**Note:** This example handles **a single JSON object**, not every Pipes SQS record/batch shape. When batching is enabled, an enrichment Lambda can receive an **array of events**, even when batch size equals 1 per Pipes mechanics. Write handlers to accept `List<...>` or `Object`, return matching batch results, and test actual payloads before production.

### Choosing retry behavior

- Permanent data errors: inspect filters/schemas and DLQ; do not retry forever.
- DynamoDB throttling/transient errors: use SDK retries with backoff/jitter and bounded Pipe retries.
- Timeouts: reduce I/O and raise Lambda timeout within the Pipe execution limit—not indefinitely.
- Missing permissions: fix IAM/enrichment roles and KMS; adding retries never solves permanent `AccessDenied`.

## 14. Targets: which services can a Pipe invoke?

AWS-supported targets fall into these groups (verify specific Regions and limits):

| Target | Use case | Pitfalls |
| --- | --- | --- |
| **AWS Lambda** | Business logic, validation, transformations, or writes | Sync/async invocation, batch errors, function concurrency |
| **Step Functions Express / Standard** | Multi-step workflows | Standard targets must be invoked **async**; Express supports sync/async |
| **SQS queue** | Durable handoff to another worker | Target queue policy, DLQ, FIFO dedup, and message attributes |
| **SNS topic** | Notifications/fan-out to subscribers | Standard/FIFO SNS support rules by target type |
| **Supported EventBridge event bus** | Forward events to bus rules/fan-out | Same-account/Region and bus-type constraints; proper event formatting needed |
| **Kinesis stream** | Write streaming records | Partition key, payload/batch limits, and throughput |
| **Firehose delivery stream** | Deliver data to S3/analytics destinations | Batching, response/latency |
| **CloudWatch Logs group** | Event logging/auditing in labs | Do not treat logs as a business database |
| **ECS task** | Trigger container tasks per event | Task definition, cluster, networking, and `RunTask`/`PassRole` permissions |
| **AWS Batch** | Run batch jobs | Queues, job definitions, quotas |
| **API Gateway / API Destination** | Call REST APIs or SaaS | Auth, payload transforms, rate limits/retries |
| **Redshift Data API, SageMaker AI Pipeline, Timestream** | Analytics, ML, metrics | Payloads/schemas/permissions and service-specific parameters |

**One Pipe, one target.** If business logic needs the same event in Lambda, SQS, SNS, and analytics, use **bus rules** or **SNS fan-out**—do not assume a `Targets` array exists on a Pipe.

### Target parameters

Depending on the target, `TargetParameters` can include:

- `InputTemplate` to shape outbound data;
- `LambdaFunctionParameters.InvocationType` for Lambda;
- `StepFunctionStateMachineParameters.InvocationType` for Step Functions;
- `SqsQueueParameters` when sending to a FIFO queue;
- `EventBridgeEventBusParameters` such as source/detail-type per target type;
- `EcsTaskParameters` with task definition/networking/launch settings;
- other API-specific parameters.

**Dynamic JSONPath in target parameters** has syntax restrictions and field exceptions; do not treat it as a JavaScript template capable of arbitrary string concatenation. For complex mappings, use tested `InputTemplate`/enrichment.

## 15. Target invocation: synchronous vs. asynchronous

Pipes has two invocation modes:

- **`REQUEST_RESPONSE` / synchronous**: the Pipe waits for the target's response. If the target returns an error, the Pipe can retry the source event/batch per semantics.
- **`FIRE_AND_FORGET` / asynchronous**: the Pipe submits the request and does not wait for the target to **finish business processing**. Acceptance by the target service does not equal a business commit.

| Scenario | Choice |
| --- | --- |
| SQS → Lambda creating invoices; delete source only after Lambda finishes | **Sync invoke** with proper error handling |
| SQS → another SQS queue for durable handoff | Target API accepts message; destination worker owns DLQ/idempotency |
| SQS → Standard Step Functions workflow | **Async `StartExecution`**; source may be acked once workflow start is accepted |
| Stream with strict ordering | Use sync per source/target requirements to preserve sequencing |
| External API returns 202 while processing in background | Must treat as **handoff accepted**, not business work completed |

AWS invokes targets **synchronously** by default for sources that require ordering; some targets allow choosing the invocation mode. **Step Functions Standard only supports async** targets in Pipes, while **Express** supports sync/async as applicable.

### Critical data rule

If a Pipe deletes the SQS source message after a target returns only **202 Accepted**, a later business failure has no source message left to retry. Ensure the target has its own **durable queue/state machine retries/DLQ**, or use synchronous business commits and idempotency.

## 16. Batching: not every source and target accepts the same batch size

Pipes supports grouping multiple source records into one pipe execution when enrichment/target support it. Maximum batch size is constrained by **both source and target**.

For example, a Kinesis source supports batches up to **10,000 records**, yet if the target is **SQS**, the batch API sends at most **10 messages**. Never configure Pipe `BatchSize=1000` expecting an SQS target to handle it.

| Batch-capable target | Illustrative max limit from docs |
| --- | --- |
| **SQS** | **10** messages |
| **SNS** | **10** entries |
| **EventBridge event bus** | **10** events |
| **Kinesis** | **500** records |
| **Firehose** | **500** records |
| **CloudWatch Logs** | **10,000** log events |
| **Lambda / Step Functions** | Constrained by payload/invoke limits and configuration |

**These limits should be verified against current documentation when deploying**—do not hardcode them without checking target type and Region.

### When batching is enabled: payload is usually an array

If source batching is enabled and the target/enrichment receives full JSON payloads (like Lambda), Pipes sends an **array of records**, which may still be a **single-element array** even when batch size = 1.

~~~json
[
  {
    "messageId": "msg-1",
    "body": "{\"eventId\":\"evt-1\",\"eventType\":\"OrderPaid\"}"
  }
]
~~~

If a Java handler expects `Map<String,Object>` while Pipes sends a `List`, deserialization/casting throws `ClassCastException`. **Test the real event shape in a lab before deploying.**

### Batching window

Pipes can wait longer to gather events when supported by the source. For low-traffic SQS sources, AWS notes a Pipe may wait up to **around 20 seconds** even when the batching window is configured shorter. Do not set a short window and promise sub-second end-to-end latency.

### Pipe execution duration

A Pipe execution is limited to roughly **5 minutes**, covering enrichment and target processing. If a task takes hours, trigger **Step Functions Standard asynchronously** or an ECS/Batch job; a Pipe is a **routing/handoff step**, not a long-running job waiter.

## 17. Partial batch failures and enrichment re-invocation

Within a batch, only some records may fail. Pipes supports partial failure handling for **compatible sources/targets**.

For instance, a target Lambda receives 3 records; M1 and M3 succeed, while M2 fails. The response format looks like:

~~~json
{
  "batchItemFailures": [
    {
      "itemIdentifier": "M2"
    }
  ]
}
~~~

**Only return this response when the target/pipe source supports partial batch semantics and is configured appropriately.** `itemIdentifier` must match the **source record's original ID**, not a UUID generated by enrichment:

- **SQS**: `messageId`.
- **Kinesis/DynamoDB**: the record's `eventID`.

If enrichment strips `messageId`/`eventID` from the returned array, the Pipe **cannot identify which records to retry**. With FIFO/ordered streams, verify how failed/unprocessed records are returned so business ordering is not broken.

### Distinguishing partial failures in target vs. enrichment

- **Target partial failure:** when supported by target/response type, Pipes can retry only the failed records.
- **Enrichment partial failure:** no equivalent partial-batch acknowledgment exists; an enrichment failure can force the **entire batch** to retry.
- When a target partially fails and Pipes retries, **enrichment may be invoked again** for the failed records; enrichment must be idempotent.

### What if a target receives a batch and returns HTTP 200?

Never assume "status 200 means every record in the batch succeeded" if the target supports partial writes. For native AWS batch APIs, Pipes inspects partial failure responses per service behavior. For custom Lambda/Step Functions logic, you must **return the proper failure structure** when needed rather than swallowing exceptions and returning success.

## 18. Retries, DLQ, and backpressure by source

| Source | Primary retry/DLQ mechanism | Risk |
| --- | --- | --- |
| **SQS** | **SQS visibility timeout**, source queue **redrive policy** and DLQ | Message redelivered, duplicate processing; visibility expires before target finishes |
| **Kinesis** | `MaximumRetryAttempts`/`MaximumRecordAge`, checkpoints, source stream retention, supported DLQ | Shard blocked by poison record; records expire |
| **DynamoDB Streams** | Retries, maximum age, typical **24-hour retention**, DLQ | Losing records if retries exceed retention |
| **Kafka/MSK** | Partition/offset semantics and broker retention, retries per source feature | Consumer lag/offsets, permissions/networking |
| **Amazon MQ** | Broker ack/requeue/DLQ per engine | Poison message blocks the queue |

### SQS source DLQ is not a stream Pipe DLQ

AWS guidance: for an **SQS source**, configure the **dead-letter queue on the SQS source queue itself**. Do not assume a Pipe-level DLQ intended for stream retries automatically manages SQS message redrive.

For **Kinesis/DynamoDB stream sources**, you can configure **`DeadLetterConfig`** per source type and API limits; stream DLQs support SQS standard or SNS targets per rules, with specific constraints. Set `MaximumRecordAgeInSeconds` shorter than stream retention so failed records can still reach the DLQ.

### Idempotency is mandatory

Even when the Pipe retries properly, this can still happen:

~~~text
1. Target writes invoice to S3/DB successfully.
2. Response from target to Pipe times out / is lost.
3. Pipe treats invocation as failed and retries.
4. Target processes the same eventId again.
~~~

Use a stable **`eventId`**, unique DB constraints, or an idempotency store. SQS `ReceiptHandle` **changes on every receive**, so it is not a business idempotency key. A Pipe manages event delivery—**it does not create an atomic transaction between SQS ack and DB commit**.

### Backpressure

Concurrency/throughput limits come from:

- SQS in-flight message limits, visibility, and capacity quotas;
- Kinesis shards/parallelization factor;
- FIFO `MessageGroupId`;
- Kafka partitions;
- enrichment Lambda/API rate limits;
- target Lambda reserved concurrency, ECS capacity, Step Functions quotas;
- downstream DB/APIs.

If the target is slow, **do not simply increase Pipe concurrency**. Measure source backlog/iterator age and real downstream capacity, then tune batching or add a backpressure-aware intermediate queue.

## 19. IAM execution role: on whose behalf does Pipes act?

Pipes uses an **IAM execution role** to read the source and invoke enrichment/target. The trust policy allows **`pipes.amazonaws.com`** to assume the role.

Example `pipe-trust-policy.json`:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "pipes.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
~~~

**Mitigating confused deputy:** In production, review AWS guidance on `aws:SourceAccount`/`aws:SourceArn` conditions where feasible. Never copy a trust policy for `lambda.amazonaws.com` or `ecs-tasks.amazonaws.com` expecting Pipes to assume it.

### Permissions for SQS source and Lambda target

Illustrative identity policy for a Pipe reading one queue and invoking one function:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadSourceQueue",
      "Effect": "Allow",
      "Action": [
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:GetQueueAttributes"
      ],
      "Resource": "arn:aws:sqs:ap-southeast-1:111122223333:orders-events-lab"
    },
    {
      "Sid": "InvokeTargetLambda",
      "Effect": "Allow",
      "Action": "lambda:InvokeFunction",
      "Resource": "arn:aws:lambda:ap-southeast-1:111122223333:function:process-orderpaid-lab"
    }
  ]
}
~~~

This is **only for SQS → Lambda without enrichment**. If you have a separate enrichment Lambda, add `lambda:InvokeFunction` for the enrichment ARN. If the target is an event bus, SQS, ECS, or Step Functions, include the corresponding API actions/ARNs/`PassRole`.

### Three distinct role layers

| Role / principal | Permissions |
| --- | --- |
| **Pipes execution role** | Receive SQS/Kinesis records, invoke enrichment/target, write logs per config |
| **Lambda target execution role** | Permissions for Java code inside Lambda to call DynamoDB/S3/KMS |
| **Deployer role/user** | `pipes:CreatePipe`/`UpdatePipe`, `iam:PassRole` on the Pipes role, deployment updates |

**The Pipe role does not grant S3 permissions to Lambda business code.** Conversely, a Lambda role with `s3:PutObject` does not help a Pipe fix `sqs:ReceiveMessage AccessDenied`.

### IAM for stream/broker sources

- DynamoDB Streams: `DescribeStream`, `GetRecords`, `GetShardIterator`, `ListStreams`.
- Kinesis: APIs to describe streams/shards and read records/subscribe per mode.
- Amazon MQ/MSK/self-managed Kafka: describe/network APIs, Secrets Manager, KMS, broker auth, and sometimes CloudWatch Logs.
- Customer-managed KMS keys: the principal/Pipe role needs decrypt permissions via key policies/grants, not just IAM allow on the source.

**Principle:** Grant least privilege per source/target; never use `pipes:*`, `sqs:*`, `kms:*` on `*` just to make an error disappear.

## 20. KMS, VPC, and data management in the pipeline

### 20.1. Encryption and access control

Event data may flow through SSE-KMS SQS, encrypted DynamoDB Streams/Kinesis, TLS, log destinations, and target DBs/S3. Pipes supports encryption/configuration options depending on the resource.

Always check:

- **SQS queue policy** or resource policy allowing the right role/source.
- **KMS key policy** allowing the Pipe role to read sources encrypted with a customer-managed key.
- **Enrichment target** permissions: the Pipe role only invokes; the Lambda role calls DB/S3.
- **Log destinations** have write permissions, retention, and KMS access.
- **Event payloads** avoid plaintext secrets, payment cards, or unnecessary PII.

### 20.2. Private broker/VPC

If the source is private MQ/MSK/Kafka, the Pipe needs connectivity to brokers per supported config. Verify:

~~~text
VPC / subnets / routes / SG / NACL
    ↓
DNS resolves broker endpoints
    ↓
TCP/TLS broker connection and authentication
    ↓
Pipes poller / consumer
    ↓
Target invocation via service integration
~~~

Some connection patterns require NAT or an interface endpoint to **`pipes-data`** per AWS documentation. Do not apply a private-subnet Lambda's network configuration blindly to every Pipe: **not every Pipe attaches an ENI in the user's VPC**.

### 20.3. Payload schema and PII

A record may contain data inappropriate for the target. Standardize:

- `eventId`, `eventType`, `schemaVersion`, `occurredAt`, `correlationId`;
- business resource IDs instead of detailed personal data wherever possible;
- transformations to strip unnecessary tokens, emails, and addresses;
- source, DLQ, and log data retention per policy;
- access controls on **execution logs** as well when TRACE is enabled.

**Enabling "Include execution data" can log source payloads, enrichment requests, and target responses.** Only enable it with security justification, masking/retention, and properly restricted log readers.

## 21. Step-by-step lab: SQS → EventBridge Pipe → Lambda Java

> **Prerequisites:** Lab account/Region with appropriate IAM, SQS, Lambda, Pipes, and CloudWatch permissions. Charges for SQS, Pipes, Lambda, and Logs may apply. Use AWS CLI v2 with an IAM role/profile—never hardcode access keys. Prepare a **Lambda Java 21 function** named `process-orderpaid-lab` whose handler properly processes an **array of source records** or a transformed event per configuration. The code in the next section is a reference model.

### 21.1. Prepare the queue

~~~bash
aws sts get-caller-identity --profile lab

aws sqs create-queue \
  --queue-name orders-events-lab \
  --attributes VisibilityTimeout=180,ReceiveMessageWaitTimeSeconds=20 \
  --region ap-southeast-1 \
  --profile lab
~~~

Get the queue URL and ARN:

~~~bash
aws sqs get-queue-url \
  --queue-name orders-events-lab \
  --region ap-southeast-1 \
  --profile lab

aws sqs get-queue-attributes \
  --queue-url "https://sqs.ap-southeast-1.amazonaws.com/111122223333/orders-events-lab" \
  --attribute-names QueueArn VisibilityTimeout \
  --region ap-southeast-1 \
  --profile lab
~~~

**Why 180-second visibility in the lab:** Provides headroom for a short Lambda target and retries. In production, size it based on combined target/enrichment duration, SLA, latency, batching window, and the **at least 6× runtime** guideline for SQS sources rather than copying 180 to every application.

### 21.2. Create the IAM role for Pipes

Assuming `pipe-trust-policy.json` and `pipe-role-policy.json` contain the JSON from section 19, create the role:

~~~bash
aws iam create-role \
  --role-name orders-pipe-role-lab \
  --assume-role-policy-document file://pipe-trust-policy.json \
  --profile lab

aws iam put-role-policy \
  --role-name orders-pipe-role-lab \
  --policy-name orders-pipe-policy-lab \
  --policy-document file://pipe-role-policy.json \
  --profile lab
~~~

Wait for IAM propagation and ensure the **role ARN/account** matches what the Pipe uses. The principal running the commands needs `iam:PassRole` for this role, appropriately scoped to the service.

### 21.3. Create the Pipe configuration JSON

File `pipe.json`:

~~~json
{
  "Name": "orders-paid-pipe-lab",
  "Description": "Filter OrderPaid from SQS into Lambda in lab",
  "DesiredState": "STOPPED",
  "RoleArn": "arn:aws:iam::111122223333:role/orders-pipe-role-lab",
  "Source": "arn:aws:sqs:ap-southeast-1:111122223333:orders-events-lab",
  "SourceParameters": {
    "FilterCriteria": {
      "Filters": [
        {
          "Pattern": "{\"body\":{\"eventType\":[\"OrderPaid\"]}}"
        }
      ]
    },
    "SqsQueueParameters": {
      "BatchSize": 1
    }
  },
  "Target": "arn:aws:lambda:ap-southeast-1:111122223333:function:process-orderpaid-lab",
  "TargetParameters": {
    "LambdaFunctionParameters": {
      "InvocationType": "REQUEST_RESPONSE"
    }
  },
  "Tags": {
    "environment": "lab",
    "application": "orders"
  }
}
~~~

**Configuration notes:**

- `Source` is the **SQS ARN**, not the Queue URL.
- `Target` is the Lambda function ARN; `TargetParameters` chooses synchronous invoke so the Pipe receives the processing outcome.
- `FilterCriteria.Filters[0].Pattern` is a **JSON string**.
- `BatchSize=1` makes ordering easier to inspect in the lab; **the handler must still handle an array shape** per configured batch semantics.
- `DesiredState=STOPPED` lets you inspect the Pipe before it starts consuming messages that could be deleted by the filter.

### 21.4. Create the Pipe and inspect status

~~~bash
aws pipes create-pipe \
  --cli-input-json file://pipe.json \
  --region ap-southeast-1 \
  --profile lab

aws pipes describe-pipe \
  --name orders-paid-pipe-lab \
  --region ap-southeast-1 \
  --profile lab
~~~

Wait for the expected state and check `CurrentState`, `DesiredState`, `StateReason`, `Source`, `Target`, and role. **`CreatePipe` is an asynchronous state-transitioning operation** (`CREATING`, `STARTING`, `RUNNING`, `STOPPED`, etc.)—a 200 API response alone does not prove the Pipe is running and polling the queue.

### 21.5. Send matching and non-matching messages

Send sequentially:

~~~bash
aws sqs send-message \
  --queue-url "https://sqs.ap-southeast-1.amazonaws.com/111122223333/orders-events-lab" \
  --message-body '{"eventId":"evt-2001","eventType":"OrderPaid","orderId":"ORD-2001"}' \
  --region ap-southeast-1 \
  --profile lab

aws sqs send-message \
  --queue-url "https://sqs.ap-southeast-1.amazonaws.com/111122223333/orders-events-lab" \
  --message-body '{"eventId":"evt-2002","eventType":"OrderCancelled","orderId":"ORD-2002"}' \
  --region ap-southeast-1 \
  --profile lab
~~~

Start the Pipe:

~~~bash
aws pipes start-pipe \
  --name orders-paid-pipe-lab \
  --region ap-southeast-1 \
  --profile lab

aws pipes describe-pipe \
  --name orders-paid-pipe-lab \
  --region ap-southeast-1 \
  --profile lab
~~~

**Expected behavior:**

- `evt-2001` matches the filter and is sent to Lambda.
- `evt-2002` **does not match** and is **removed from the SQS source queue**.
- When Lambda succeeds per Pipe invocation, the matching SQS message is deleted.
- If Lambda errors, the message may be received again per visibility/retention and eventually moved to the DLQ if the queue has redrive configured.

**Never test destructive filtering like this on a queue holding real uncategorized events.**

## 22. Lambda Java target: handling the right payload type and idempotency

Java handler example accepting **`Object`** to demonstrate handling sources that pass **an array of SQS records or a single object**; requires compatible `aws-lambda-java-core` and `jackson-databind` dependencies in the JAR/ZIP/image.

~~~java
package com.example.events;

import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.RequestHandler;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.util.List;
import java.util.Map;

public final class OrderPaidTarget
    implements RequestHandler<Object, String> {

    private static final ObjectMapper JSON = new ObjectMapper();

    @Override
    public String handleRequest(Object event, Context context) {
        List<?> records =
            event instanceof List<?> list ? list : List.of(event);

        for (Object raw : records) {
            if (!(raw instanceof Map<?, ?> record)) {
                throw new IllegalArgumentException("Unexpected record shape");
            }

            Object body = record.get("body");
            if (body == null) {
                throw new IllegalArgumentException("Missing SQS body");
            }

            try {
                JsonNode payload = body instanceof String s
                    ? JSON.readTree(s)
                    : JSON.valueToTree(body);

                String eventId = payload.path("eventId").asText("");
                String orderId = payload.path("orderId").asText("");
                String eventType = payload.path("eventType").asText("");

                if (eventId.isBlank() || orderId.isBlank()
                    || !"OrderPaid".equals(eventType)) {
                    throw new IllegalArgumentException("Invalid event");
                }

                // Production: conditional write by eventId, commit
                // business transaction, update S3/DB, then return.
                context.getLogger().log(
                    "Processed event " + eventId + " for " + orderId);
            } catch (Exception ex) {
                context.getLogger().log(
                    "Target processing failed: "
                    + ex.getClass().getSimpleName());
                throw new IllegalStateException(
                    "Target invocation failed; allow Pipe retry", ex);
            }
        }
        return "OK";
    }
}
~~~

**This is illustrative code and does not implement durable idempotency.** Logging success does not prove business state committed. Production must use **DynamoDB conditional puts, SQL unique constraints, or inbox/outbox**, ensuring downstream side effects are retry-safe.

### Why must the handler support an array?

A Pipe with batching enabled can send `[record1, record2]`, and **even a single-record batch can still be an array**. A Java handler expecting only `Map<String,String>` may throw `ClassCastException` before business logic runs.

**If `InputTemplate` is enabled on the target**, the payload may no longer be an SQS envelope with `body`. Update the handler for the **transformed output schema** rather than blindly calling `record.get("body")`.

### Handler success vs. failure

- Finish processing and return success: the Pipe can ack the source per target invocation mode.
- Throw an exception: the Pipe can retry the event/batch, making **idempotency** essential.
- Swallow exceptions, log, and return `"OK"`: the Pipe can **delete the SQS message despite a business failure**, which is a serious anti-pattern.

## 23. Safely modifying a Pipe and cleaning up the lab

### Inspect and pause

~~~bash
aws pipes describe-pipe \
  --name orders-paid-pipe-lab \
  --region ap-southeast-1 \
  --profile lab

aws pipes stop-pipe \
  --name orders-paid-pipe-lab \
  --region ap-southeast-1 \
  --profile lab
~~~

Wait for `CurrentState=STOPPED` before making major configuration changes, and monitor `STOPPING`/stop failures. The stop API is asynchronous; do not assume the transition is complete immediately when the CLI returns.

### Updating filter/source/target

Use `update-pipe` for API-supported fields while checking restrictions/side effects on a running Pipe. For changes that risk **deleting non-matching SQS messages**:

1. Create the configuration in a separate lab/canary queue;
2. Build matching and non-matching fixture payloads;
3. Validate target schemas, ID mappings, and IAM roles;
4. Stop/update the Pipe following a reviewed procedure;
5. Restart and watch `StateReason`, logs, source backlog, and DLQs;
6. Have a configuration rollback plan **while understanding that messages already filtered/deleted will not auto-recover**.

### Cleaning up lab resources

~~~bash
aws pipes delete-pipe \
  --name orders-paid-pipe-lab \
  --region ap-southeast-1 \
  --profile lab
~~~

Delete the queue, Lambda, IAM role, and log group **only if created solely for the lab with no remaining dependencies**, after preserving needed diagnostic/event data. **Never use `PurgeQueue` to clean production** or hide a misconfigured filter.

## 24. CloudFormation/IaC: declaring a reviewable Pipe

Infrastructure as Code lets teams review source/target ARNs, IAM least privilege, and lifecycle alongside application code. **Abbreviated** CloudFormation example (IAM role/queue/Lambda are existing resources passed as parameters):

~~~yaml
AWSTemplateFormatVersion: "2010-09-09"
Description: Pipe from lab SQS OrderPaid events to Lambda
Parameters:
  SourceQueueArn:
    Type: String
  TargetFunctionArn:
    Type: String
  PipeRoleArn:
    Type: String
Resources:
  OrdersPaidPipe:
    Type: AWS::Pipes::Pipe
    Properties:
      Name: orders-paid-pipe-lab
      Description: Route OrderPaid messages to Lambda
      DesiredState: STOPPED
      RoleArn: !Ref PipeRoleArn
      Source: !Ref SourceQueueArn
      SourceParameters:
        SqsQueueParameters:
          BatchSize: 1
        FilterCriteria:
          Filters:
            - Pattern: '{"body":{"eventType":["OrderPaid"]}}'
      Target: !Ref TargetFunctionArn
      TargetParameters:
        LambdaFunctionParameters:
          InvocationType: REQUEST_RESPONSE
~~~

**Notes:**

- This template does not define the IAM role, source queue, target Lambda, source queue DLQ, or logging; a complete deployment must add them.
- CloudFormation `Pattern` is a **string**, even though YAML single quotes make it resemble a JSON object.
- Separate `DesiredState: STOPPED` from enabling the Pipe after testing.
- Check drift, IAM policies, resource replacement/updates, and rollback plans; **IaC rollback does not restore messages deleted by a filter**.
- Tags, `LogConfiguration`, and KMS can be added in IaC per organizational policy.

## 25. Logging and CloudWatch monitoring for Pipes

Pipes provides **CloudWatch metrics** and logging to AWS-supported destinations such as **CloudWatch Logs**, **Firehose**, or **S3**. When logging is enabled, a Pipe can emit logs across execution stages.

### Logging levels

| Level | What is included? | When to use |
| --- | --- | --- |
| **OFF** | No execution logs emitted via this config | Systems needing metrics only, at the cost of reduced debugging visibility |
| **ERROR** | Records related to errors, timeouts, throttling | Sensible default for production |
| **INFO** | Errors plus some stage transitions/successes | Operations and investigations |
| **TRACE** | Fine-grained details across execution steps | Enable temporarily only when debugging |

**Note:** Console and API/CLI defaults may differ. If you create a Pipe via CLI/IaC **without configuring `LogConfiguration`**, do not assume CloudWatch execution logs exist. Also, Pipe logging is **separate from** the target Lambda's CloudWatch logs.

### Include execution data

When enabled, logs can contain:

- Source event/batch payloads;
- requests sent to enrichment/target;
- returned responses.

This can include **PII, internal documents, tokens, or business data**. Only enable it after reviewing data classification, retention, encryption, and log access permissions. With CloudWatch Logs, Pipe log records have size limits and may be truncated.

### Signals to monitor

| Metric/log source | Signal | Interpretation |
| --- | --- | --- |
| **Pipes** | Execution started/succeeded/failed/partially failed, throttled, duration | Is the Pipe running and delivering to the target? |
| **SQS source** | Visible/NotVisible, age of oldest, DLQ visible | Backlog, visibility/processing failures |
| **Kinesis/DynamoDB Streams** | Iterator age/lag, shard throughput, retry errors | Stream lagging or checkpoint stalled |
| **Lambda enrichment/target** | Invocations, Errors, Duration, Throttles | Code errors or quota limits? |
| **Downstream event bus/target** | Failed invocations, DLQ, workflow failures | Handoff accepted, yet business work incomplete |
| **IAM/CloudTrail** | `CreatePipe`, `UpdatePipe`, `Start/StopPipe`, policy edits | Who altered routing/filters/roles? |
| **CloudWatch Logs** | Pipe `StateReason`, error records, `correlationId` | Pinpoint specific errors |

CloudWatch metrics arrive on a **best-effort** basis. A missing or delayed datapoint is not absolute proof of zero events. Also emit **business metrics** such as `orders_paid_received`, `invoices_created`, `duplicates_ignored`, and `dlq_count`.

### Correlation ID across the pipeline

~~~text
Producer eventId
  → SQS messageId / body eventId
  → Pipe execution logs / pipe ARN
  → Enrichment request/response carrying eventId
  → Target invocation logs carrying eventId
  → DB/S3 commit record carrying eventId
~~~

**Preserve `eventId` through every transformation and enrichment** to reconcile data and detect lost or duplicated business operations.

## 26. Architectural scenarios and choosing Pipes

### A. SQS invoicing: filter and invoke Lambda

**Requirement:** Only `OrderPaid` should generate an invoice.

**Recommendation:** If the producer can send to a **dedicated queue for `OrderPaid`**, use SQS → Lambda via Pipe with optional transform; avoid destructive filtering on a queue shared by other workflows. Lambda performs a conditional write by `eventId`, writes S3, and handles errors/timeouts properly; the source SQS queue has a DLQ.

### B. DynamoDB Streams → EventBridge event bus

**Requirement:** Orders change in DynamoDB, and multiple subscribers need to know about `OrderShipped`.

~~~mermaid
flowchart TB
    Table[(DynamoDB Orders)] --> Stream[DynamoDB Streams]
    Stream --> Pipe[EventBridge Pipe]
    Pipe --> Filter[Filter MODIFY + status SHIPPED]
    Filter --> Bus[(Supported EventBridge event bus)]
    Bus --> Rule1[Rule: Logistics]
    Bus --> Rule2[Rule: Notifications]
    Rule1 --> Queue1[(Logistics SQS)]
    Rule2 --> Queue2[(Email SQS)]
~~~

**Note:** DynamoDB Streams have limited retention, and `dynamodb.NewImage` uses AttributeValue wrappers. Filters must match the exact `{"S":"SHIPPED"}` shape rather than `"SHIPPED"` at the root. Use `TRIM_HORIZON` starting position if losing records during Pipe startup is unacceptable, and enforce idempotency in consumers.

### C. Kinesis telemetry → Firehose/analytics

**Requirement:** The system ingests many sensor records and forwards only measurements exceeding a temperature threshold.

**Recommendation:** Kinesis source, filter on decoded `data`, transform to trim payload, and target Firehose/S3 analytics as supported; size batch size/window, shard/partition concurrency, and monitor iterator age. Avoid pushing excessive unneeded metadata to the target.

### D. MSK Kafka → Step Functions

**Requirement:** A Kafka event triggers a multi-step workflow.

**Recommendation:** Pipe from MSK source, filter, optional enrichment, targeting Step Functions Express/Standard per supported invocation type. With **async Standard**, starting the workflow successfully **does not prove the entire workflow succeeded**; monitor the state machine, retries/DLQ, and business idempotency separately. Mind partition ordering and consumer lag.

### E. EventBridge Pipes does not replace workflows

**Requirement:** Payment → wait 48 hours for approval → send notification → refund if rejected.

**Do not:** Call an enrichment Lambda and hold a synchronous connection for 48 hours. Pipe executions are time-limited.

**Do:** Have the Pipe trigger **Step Functions Standard** asynchronously; the workflow provides `Wait`, `Choice`, `Retry/Catch`, compensation, persistence, and observability.

## 27. Troubleshooting: from `StateReason` to source and target

| Symptom | Common cause | What to check |
| --- | --- | --- |
| Pipe `CREATE_FAILED` / `START_FAILED` | Wrong source/target ARN, bad IAM `PassRole`/trust, disabled source | `describe-pipe`, `StateReason`, CloudTrail |
| `AccessDenied` reading SQS | Role missing `ReceiveMessage/DeleteMessage/GetQueueAttributes`, queue policy, or KMS | Pipe role, `SourceArn`, resource policy, KMS |
| Message never reaches Lambda and disappears from SQS | **Filter mismatch** → Pipes deleted the message | `FilterCriteria` body/JSON types, logging, source events |
| Two Pipes read SQS, both targets miss events | Competing consumers, non-matching messages deleted | Redesign fan-out with bus/SNS or separate queues |
| Source backlog grows | Pipe `STOPPED`, target throttled/failing, insufficient capacity | `CurrentState`, metrics, SQS visible/not visible |
| Target Lambda fails repeatedly | Wrong batch shape in handler, timeout, missing role/data | Lambda logs, event payload, target role, retry/DLQ |
| Handler returns success yet order is unprocessed | Code swallows exceptions, async target handoff | Business commit/idempotency, `InvocationType`, downstream logs |
| Pipe passes malformed payload | `InputTemplate` bad JSON quoting, enrichment changed schema | Sample transformed event, template paths, logs |
| Batch target reports partial failures | Wrong `itemIdentifier`, metadata stripped in enrichment | `messageId`/`eventID`, partial response shape |
| Enrichment invoked multiple times | Target retry caused Pipe to re-run enrichment | Idempotency, pure lookups, duplicate metrics |
| SQS message processed twice | Visibility too short, worker/target error, network timeout | 6× visibility guidance, retries, idempotency |
| SQS DLQ empty despite Pipe failures | Source redrive not configured or `maxReceiveCount` not reached | Queue `RedrivePolicy`/DLQ, receive count |
| DynamoDB stream records missed | `LATEST` during create/update window | `TRIM_HORIZON`, stream retention, replay |
| Kinesis iterator age rises | Shard bottleneck, slow target/enrichment | `ParallelizationFactor`, batch/throughput, target latency |
| Kafka source connection error | SG, DNS, broker port, IAM/SASL secret, endpoint | VPC subnet/SG, `pipes-data`, broker logs |
| Pipe `STOPPED` due to disabled source | Source stream was disabled/deleted | `StateReason`, source lifecycle, recreate/reconfigure per docs |
| Empty logs | `LogConfiguration` not enabled or Level `OFF` | Pipe logging, destination IAM, CloudWatch retention |
| Unexpected cost spike | High matched events/batches, large payloads, retries, verbose logging | Pipes metrics, Pricing Calculator, KMS/SQS/logs |
| SQS FIFO group stalled | One failing message in group, ordered processing | `MessageGroupId`, visibility/retry, DLQ runbook |

### Ordered investigation procedure

~~~text
1. Confirm account, Region, Pipe name/ARN, and source/target ARNs.
2. DescribePipe: CurrentState, DesiredState, StateReason, role, filter,
   enrichment, target parameters, LogConfiguration.
3. Check source:
   SQS Visible/NotVisible/DLQ or Kinesis/DDB iterator lag,
   Kafka/MQ broker state and networking.
4. If records vanish: inspect filter, especially SQS non-matching drops.
5. Check role trust pipes.amazonaws.com, IAM actions, KMS/key policies.
6. Check enrichment logs/latency; verify input/output payload schemas.
7. Check target logs/responses, sync/async invocation, batch/partial failures.
8. Check business eventId: committed, duplicated, or lost data?
9. Fix one root cause in lab, replay fixture cleanly,
   confirm CloudWatch metrics, DLQ, and idempotency.
~~~

**Never "fix" issues by** granting `AdministratorAccess`, opening broker SGs to `0.0.0.0/0`, removing filters blindly, leaving `TRACE` with PII on permanently, or setting infinite retries. Those mask bugs, increase security exposure, and can exhaust queue/stream retention.

## 28. Performance and cost: billed after filtering, factoring in batching

EventBridge Pipes is generally billed by **requests after filtering** and payload/batch size according to Regional pricing. AWS documentation describes **each 64 KB chunk of payload** as counted as one request for Pipes; source, enrichment, and target services also have their own pricing schedules.

### Estimation example

Suppose over 30 days:

- SQS receives **10,000,000** messages;
- Filter matches **25%** = 2,500,000 events;
- Average **5 events/batch**, with each batch payload assumed within one 64 KB unit;
- Ignoring retries/empty batches.

\[
N_{\text{billable Pipe requests}}
\approx
\frac{10{,}000{,}000\times 25\%}{5}
=
500{,}000
\]

At an illustrative rate of **\$0.40 USD per million requests** from AWS's example pricing, the Pipes portion is roughly:

\[
0.5 \times \$0.40=\$0.20
\]

**This is an example from the pricing model, not a fixed quote for every Region or date.** If a batch payload is **256 KB**, each batch can count as **4 units of 64 KB**, so consider **bytes**, not just batch count.

### Total architectural cost

\[
C_{\text{total}}
\approx C_{\text{Pipes}}
+ C_{\text{source}}
+ C_{\text{enrichment}}
+ C_{\text{target}}
+ C_{\text{data/KMS}}
+ C_{\text{network}}
+ C_{\text{logs/monitoring}}
\]

Examples:

- **SQS:** requests, data transfer, KMS depending on encryption.
- **Lambda enrichment/target:** invocations, duration × memory, concurrency, CloudWatch Logs.
- **API Destination:** external API fees and quotas.
- **Kinesis/MSK:** shards/stream capacity, storage, broker networking.
- **VPC endpoints/NAT:** connections and data processing per architecture.
- **CloudWatch Logs/S3/Firehose:** log volume/retention, storage, transfers.
- **Retries:** increase executions and downstream costs even for a single business `eventId`.

### Reducing cost without breaking semantics

- Filter early, **without dropping data on a shared queue**.
- Shrink payload size via transformations while preserving `eventId`.
- Batch within source/target limits and latency SLOs.
- Avoid enrichment Lambdas that merely copy/rename a few fields already handled by `InputTemplate`.
- Set sensible CloudWatch Logs levels/retention; avoid `TRACE` on sensitive payloads.
- Configure **AWS Budgets**, tags, and anomaly alerts; track cost per successfully processed business event.

## 29. Applied exercises and self-check questions

### Exercise 1 — Choosing Pipes vs. event bus

An SQS queue `orders` contains three event types: `OrderPaid`, `OrderCancelled`, and `OrderShipped`. Three teams need to receive each type independently with separate retries/DLQs.

**Task:** Explain why creating three Pipes reading the same queue will **lose messages**. Propose an **event bus + rules** or SNS fan-out → dedicated queues design; indicate where idempotency and DLQs live.

### Exercise 2 — Filtering the right `body` structure

SQS message body:

~~~json
{
  "eventId": "evt-501",
  "eventType": "OrderPaid",
  "amount": 90000
}
~~~

Write a filter for `OrderPaid` with `amount >= 100,000`. Predict whether this record reaches the target and **what happens to the message** on the source SQS queue when the filter rejects it. Contrast with Kinesis stream filtering.

### Exercise 3 — Enrichment and idempotency

Pipe SQS → enrichment Lambda reading DynamoDB → target Lambda creating invoices. The target writes to S3, yet the response times out; the Pipe retries.

Describe:

1. Why enrichment may be invoked again.
2. Why `eventId` must survive the enrichment payload.
3. How conditional puts prevent creating duplicate invoices.
4. How to distinguish a target that committed before ACK loss from one that never ran.

### Exercise 4 — Batching and target limits

A Kinesis source permits very large batches, while the target is SQS.

Explain why you cannot arbitrarily set a batch of 1,000 records when an SQS target accepts at most 10 entries/batch under current limits. If the target is Lambda, which **6 MB payload**, array shape, execution duration, and retry semantics must be checked?

### Exercise 5 — SQS visibility and DLQ

Enrichment takes at most 8 seconds, target Lambda takes at most 22 seconds, and typical total runtime is ≤ 30 seconds.

1. Apply the **6 × (8 + 22) = 180 seconds** guideline for source queue visibility.
2. If the target is throttled or execution exceeds 30 seconds, what must be tested?
3. Why must the DLQ be configured on the **SQS source queue**?
4. Why is idempotency still necessary even with 180-second visibility?

### Exercise 6 — `LATEST` can lose data

DynamoDB Streams receives continuous writes. A team creates a new Pipe with `StartingPosition` `LATEST`, and polling starts a few minutes late.

Explain eventual consistency and the risk of missing records, when to choose `TRIM_HORIZON`, how to bound retry age relative to 24-hour retention, and how to verify zero loss using business event IDs.

### Exercise 7 — Async target does not prove business completion

A Pipe sends events to **Step Functions Standard** with **async** invocation. `StartExecution` succeeds, yet the workflow fails 15 minutes later.

Who owns retry/recovery? Does the source SQS queue still hold the message? Design state machine retry/Catch, alerts, DLQ/compensation, business correlation, and a replay workflow that avoids duplicate side effects.

### Exercise 8 — IAM and VPC

A Pipe uses a private MSK broker, an enrichment Lambda, and an SSE-KMS encrypted SQS target queue.

List IAM actions across the **Pipe execution role**, **Lambda execution role**, and **deployer**, plus VPC subnets/SGs/DNS/broker authentication, KMS key policies, queue resource policies, and network tests. Explain why granting `sqs:SendMessage` to the Lambda role does not let the Pipe write to the SQS target.

### Exercise 9 — Observability and cost

A Pipe processes 1 million events/day while the target writes only 200 thousand business records, and `ExecutionFailed` rises.

Propose a dashboard covering source backlog/iterator age, Pipe failures/throttles, enrichment/target errors, DLQ, `eventId` commit/duplicate rate, and payload size. Estimate cost drivers during continuous retries and draft a runbook prioritizing data integrity before cost.

### Short questions

1. **How many sources and targets does one Pipe have?** One source and one target.
2. **Is a filter required?** No.
3. **Does enrichment run after the filter?** Yes, for events passing the filter.
4. **Does an SQS message that fails a filter stay in the queue for another Pipe?** No; Pipes removes non-matching messages from the source queue.
5. **For a successful SQS-source Pipe invocation, who deletes the message?** Pipes handles `DeleteMessage`.
6. **Does DynamoDB Streams have a 30-second visibility timeout like SQS?** No; it uses iterators/checkpoints and retention.
7. **Does Kinesis `LATEST` risk missing records at Pipe creation time?** Yes, due to poller eventual consistency.
8. **Can Step Functions Standard act as synchronous enrichment?** No; enrichment supports synchronous Express.
9. **Can a Standard workflow be an async target?** Yes, per supported integration.
10. **Is enrichment partial batch failure supported like target partial batch failure?** No.
11. **Which ID does target partial failure need for SQS?** The source event's `messageId`.
12. **Does setting batch size 1 guarantee the target Lambda receives an object instead of an array?** No; check the batch event shape.
13. **What is the Pipe execution role principal?** `pipes.amazonaws.com`.
14. **Does granting `s3:PutObject` to the Pipe role automatically grant it to Java code inside the target Lambda?** No.
15. **Can a Pipe execution wait synchronously for 2 hours?** No; it has an execution duration limit—use an async workflow.
16. **Does Pipes replace idempotency?** No.
17. **Does a Pipe target returning 202 prove a DB commit?** No.
18. **Why might an SQS queue be non-empty while Pipes is not consuming?** Could be `STOPPED`, IAM/KMS, filter, throttling, visibility, target errors, or source networking.

## 30. Production deployment checklist

- [ ] **One source, one target** confirmed; fan-out requirements use bus/SNS/queues properly.
- [ ] Right source selected (**SQS, Kinesis, DynamoDB Streams, MQ, MSK, or self-managed Kafka**) with retention/ack/checkpoint understood.
- [ ] Message body/schema versions classified; **`eventId`** and correlation IDs preserved across the Pipe.
- [ ] Filter patterns tested with matching, non-matching, malformed, metadata, and type-variant payloads.
- [ ] For **SQS sources**, understood that **non-matching messages are deleted**; never point multiple Pipes competitively at one queue for fan-out.
- [ ] `InputTemplate` produces valid JSON per target contract without dropping idempotency keys or leaking extra PII.
- [ ] Enrichment uses a supported sync integration (Lambda/API Gateway/API Destination/Express), stays under Pipe execution limits, and is retry-idempotent.
- [ ] Target service/API mode chosen; business commit vs. handoff semantics documented.
- [ ] Source/target batch sizes and windows fit payload limits, latency SLOs, and ordering.
- [ ] Target Lambda/Step Functions handle array event/batch response formats; partial failures tested.
- [ ] SQS source visibility includes margin for combined runtime and retries; source queue has redrive/DLQ/`maxReceiveCount`.
- [ ] Stream source starting position, shard/partition ordering, retry age, and retention designed.
- [ ] Pipe IAM execution role trusts `pipes.amazonaws.com`, with least privilege on source/enrichment/target and KMS.
- [ ] Target Lambda/Step Functions IAM separated from Pipe role; deployer has scoped `iam:PassRole`.
- [ ] Broker/VPC subnets/SGs/DNS/TLS, Secrets Manager, and `pipes-data` endpoints verified when needed.
- [ ] `TRACE` with execution data containing PII/secrets is not left on permanently; retention/masking/encryption enforced.
- [ ] CloudWatch metrics/logs, `StateReason`, source backlog/iterator age, DLQ alarms, and business success metrics configured.
- [ ] Tested failure modes: IAM deny, KMS deny, target timeout, enrichment failure, partial batch, FIFO blocking, stream retention.
- [ ] Replay/restore/idempotency, route-change auditing, and IaC/change review/rollback plans established.
- [ ] Pipes pricing estimated on matched events, **64 KB units**, batches, retries, and source/enrichment/target costs.
- [ ] AWS Budgets, cost allocation tags, dashboards, runbooks, and a separate canary environment in place.
- [ ] When updating/deleting a Pipe, backlog inspected and production queues never purged or stripped of messages accidentally.

## 31. Summary

**EventBridge Pipes connects one event source to one target**, allowing you to add **filtering, input transformation, and enrichment** without writing polling or routing boilerplate. It is especially useful for **SQS/streams/brokers → Lambda, Step Functions, event buses, or other supported targets**.

Key takeaways:

- **Pipes does not fan out by itself**; multiple Pipes reading the same SQS queue **compete for and delete non-matching messages**.
- **Filter** selects events, **transform** reshapes payloads, and **enrichment** calls a service to add data—three distinct responsibilities.
- **SQS sources** rely on visibility/acks and source DLQs; **Kinesis/DynamoDB Streams** rely on iterators/checkpoints/retention; brokers have their own semantics.
- **Enrichment is synchronous**, partial batch failures primarily belong to the target stage, and Pipe executions are time-bounded—never a replacement for Step Functions workflows.
- **IAM execution roles, KMS/VPC, idempotency, logging/metrics, and cost** are integral to the design, not afterthoughts once the Pipe runs.

When deploying a secure, resilient AWS architecture, validate **`eventId`, ordering, duplicate side effects, payload schemas, target completion semantics, replay, and budgets** in a lab environment before going to production.

### Official AWS documentation for reference

- [Amazon EventBridge Pipes overview](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-pipes.html)
- [Concepts: source, filter, enrichment, target](https://docs.aws.amazon.com/eventbridge/latest/userguide/pipes-concepts.html)
- [Supported Pipes sources](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-pipes-event-source.html)
- [Supported Pipes targets](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-pipes-event-target.html)
- [Event filtering in Pipes](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-pipes-event-filtering.html)
- [Input transformations for Pipes](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-pipes-input-transformation.html)
- [Enrichment in EventBridge Pipes](https://docs.aws.amazon.com/eventbridge/latest/userguide/pipes-enrichment.html)
- [Pipes batching and concurrency](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-pipes-batching-concurrency.html)
- [Amazon SQS source for Pipes](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-pipes-sqs.html)
- [DynamoDB Streams source for Pipes](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-pipes-dynamodb.html)
- [Kinesis source for Pipes](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-pipes-kinesis.html)
- [Pipes event source permissions](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-pipes-permissions.html)
- [Pipes error handling and troubleshooting](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-pipes-error-troubleshooting.html)
- [Pipes logging](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-pipes-logs.html)
- [Pipes monitoring via CloudWatch](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-pipes-monitoring.html)
- [AWS CLI pipes create-pipe](https://docs.aws.amazon.com/cli/latest/reference/pipes/create-pipe.html)
- [AWS CLI pipes describe-pipe](https://docs.aws.amazon.com/cli/latest/reference/pipes/describe-pipe.html)
- [AWS CloudFormation AWS::Pipes::Pipe](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-pipes-pipe.html)
- [EventBridge Pipes pricing](https://aws.amazon.com/eventbridge/pricing/)

**Operational note:** Pricing, quotas, supported sources/targets, invocation behaviors, and AWS CLI/Console interfaces can change by Region, account, and time. Always verify current documentation, rehearse retries/filter failures, and test with sanitized realistic data before production release.
