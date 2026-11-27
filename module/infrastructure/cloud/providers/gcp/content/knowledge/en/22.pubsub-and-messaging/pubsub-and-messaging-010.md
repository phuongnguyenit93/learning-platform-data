# Flow control, batching, and optimizing publishers and subscribers

In an online learning platform, the course enrollment service can emit tens of thousands of `EnrollmentCreated` events during peak hours. A **publisher** sending too fast accumulates queues in RAM and times out; a **subscriber** receiving too many messages increases processing latency, exhausts database connections, and repeatedly triggers message redeliveries. Simply adding more workers does not always fix the issue.

**Google Cloud Pub/Sub** is a managed asynchronous messaging service that decouples event emitters from event processors. Within the **Pub/Sub and Messaging** chapter of module **CLOUD_PROVIDERS_GCP**, this lesson guides tuning **batching**, **flow control**, **concurrency**, and **acknowledgment** to balance throughput, latency, resilience, and cost. Examples connect publishers on Cloud Run/GKE/Compute Engine, subscribers updating databases, and end-to-end reliability monitoring.

After this lesson, you will be able to:

1. Distinguish publisher batching from publisher-side and subscriber-side flow control.
2. Configure message count, byte size, and batch delay limits using the client library.
3. Design backpressure mechanisms to avoid accumulating messages in memory or overloading databases.
4. Tune StreamingPull, handle ack/nack, lease extension, and redelivery safely.
5. Measure backlog, oldest unacked age, publish/ack latency, and cost to select configurations.
6. Run controlled publish/subscribe experiments and solve sizing calculations.

## 1. Message path and three throttling mechanisms

~~~mermaid
flowchart LR
    A["Application generates events"] --> PF["Publisher flow control<br/>bounds outstanding"]
    PF --> BAT["Publisher batching<br/>groups messages by count/bytes/time"]
    BAT --> TOP["Pub/Sub topic"]
    TOP --> SUB["Subscription + backlog"]
    SUB --> SF["Subscriber flow control<br/>bounds unacked messages/bytes"]
    SF --> WORK["Callback / worker<br/>business processing"]
    WORK -->|"Success: ack"| SUB
    WORK -. "Error: nack / ack deadline expired" .-> SUB
~~~

| Mechanism | Where it operates | What does it limit? | What it does NOT solve alone |
| --- | --- | --- | --- |
| **Publisher batching** | Publisher client | Message count, total bytes, or wait time before sending a publish request. | Unbounded RAM growth when input arrives faster than publish speed. |
| **Publisher flow control** | Publisher client | Unfinished **in-flight publish** messages/bytes, and behavior when reaching the limit. | Service quotas and subscriber processing speed. |
| **Subscriber flow control** | Pull/StreamingPull client | Messages/bytes **received but not yet acked/nacked**. | Overly fast publishers or sustained insufficient subscriber capacity. |
| **Subscriber concurrency** | Process/executor/thread pool | Number of handlers executing truly concurrently. | Backlog if downstream/database still cannot keep up. |
| **Ack deadline/lease management** | Subscription + client | How long Pub/Sub waits for an ack before redelivering; SDK can auto-extend. | Non-idempotent transactions or long-running failures. |

Both sides throttle **independently**: a subscriber slowing down its receive rate does not automatically make publishers stop sending; messages accumulate in the **subscription backlog**. Likewise, a publisher blocked by flow control does not imply the subscription backlog is empty. When troubleshooting, identify whether the queue sits in the **publisher client**, **Pub/Sub service**, or **subscriber client**.

### 1.1. Distinguishing message, batch, and subscription

- A **message** contains `data` bytes, attributes, and metadata; it may carry an `ordering_key` when message ordering is used.
- **Batch publishing** sends multiple messages together in **one Publish API request**. Messages still receive individual message IDs after publishing succeeds.
- A **topic** receives messages from publishers; each **subscription** has its own delivery stream and backlog. Two subscriptions on the same topic need separate subscriber capacity.
- **Outstanding publish** refers to messages on the publisher side waiting to be sent/confirmed; **outstanding receive** refers to messages received on the subscriber side not yet acked/nacked.

Client libraries vary in defaults, property names, and feature support. Examples in this lesson use **Python `google-cloud-pubsub`** with explicit parameters; when using Java/Go/Node.js, verify against the exact running SDK version.

## 2. Publisher batching: grouping requests for efficiency

Batching reduces Publish API call counts when sending many small messages. Instead of making one RPC per event, the client buffers messages and sends when **any one of three thresholds** is reached:

| Threshold | Example | Meaning |
| --- | --- | --- |
| **Message count** | 100 messages | Batch is sent when message count reaches the threshold. |
| **Byte size** | 1 MiB | Batch is sent when total size reaches/exceeds the SDK's configured threshold. |
| **Max latency / delay** | 50 ms | Flushes a partial batch after the client's maximum wait interval. |

The trigger condition is **OR**, not waiting for all three thresholds simultaneously. At 10,000 messages/s of small messages, the count threshold usually fires first; at only 5 messages/s, the latency threshold keeps messages from waiting too long.

**Service limits:** a single Pub/Sub Publish request has a total size limit of roughly **10 MB** and **1,000 messages**. Choose thresholds below these limits while accounting for overhead; a **single message** cannot be split across two publish requests by batching. High-level client libraries generally help keep requests within limits, yet applications should still validate input payload sizes.

### 2.1. Latency vs. throughput trade-offs

| Configuration | Benefits | Risks |
| --- | --- | --- |
| Very small batch or `max_messages=1` | Low batch wait latency, easy single-message testing. | High RPC count, overhead, and processing cost. |
| Large batch, long `max_latency` | High efficiency under steady/large traffic. | Sparse messages wait longer; p99 publish latency rises. |
| Medium batch, short latency | Balanced for near-real-time APIs/event streams. | Requires load testing to tune thresholds. |
| Large batch without publisher flow control | Sends RPCs efficiently, yet risks RAM backlog. | Timeouts, memory pressure, data loss if process exits before futures finish. |

Batching affects both **publish latency** and **end-to-end latency**; there is no universal optimal config for every workload. SDKs may enable batching by default, though defaults differ across languages and versions.

### 2.2. Message ID and publish confirmation

Calling `publish(...)` in many SDKs returns a **Future/Promise** as soon as the message is queued locally; that **does not prove Pub/Sub received it**. Only when the future completes successfully and yields a `message_id` does the application have confirmation from the service.

Therefore:

1. Keep the publisher client alive long enough for batches to send, preferring **reuse** across requests.
2. Await/handle future outcomes rather than treating "called publish" as success.
3. On controlled shutdown, perform flush/shutdown per the SDK's API.
4. For events that must be emitted reliably right after a database transaction, consider a **transactional outbox** rather than committing the DB and calling Pub/Sub "best effort."

**Duplicate data note:** a publisher can time out after Pub/Sub already persisted the message but before the client received the response. Retrying can create a new message with a different message ID. Thus do not rely solely on `message_id` for business deduplication; add a stable `event_id` and make subscribers idempotent.

## 3. Publisher flow control: backpressure before OOM

If a producer generates 30,000 messages/s while the client can only publish 10,000 messages/s, roughly **20,000 messages/s** accumulate in the local queue. After one minute, queued messages alone can grow by around **1.2 million**. Batching improves send efficiency, yet if the imbalance persists, **backpressure or greater capacity is mandatory**.

In Python, `PublishFlowControl` has two thresholds:

- `message_limit`: number of messages awaiting publish completion.
- `byte_limit`: total bytes awaiting publish completion.

When a limit is reached, `limit_exceeded_behavior` can be:

| Behavior | Effect | Use when |
| --- | --- | --- |
| `BLOCK` | `publish()` call waits until capacity frees up. | You want **backpressure** on the producer and bounded memory. |
| `ERROR` | Raises an error when local queue cannot accept more. | Application has a durable queue or custom retry/backoff mechanism. |
| `IGNORE` | Ignores client-side flow-control limits. | Only when memory pressure is well understood; usually unsuitable under unbounded load. |

This is a **per-publisher-process limit**, not a Pub/Sub service quota or a global cap across all publishers to a topic. Multiple processes each maintain their own counters; their combined load can still exceed project/region quotas or subscriber capacity.

### 3.1. Python example: batching and flow control together

Example using the current `google-cloud-pubsub` library. Run in an environment with an **existing lab topic**, Application Default Credentials (ADC), and `roles/pubsub.publisher` on the topic:

~~~python
import json
import os
import uuid

from google.cloud import pubsub_v1
from google.cloud.pubsub_v1.types import (
    BatchSettings,
    LimitExceededBehavior,
    PublisherOptions,
    PublishFlowControl,
)

project_id = os.environ["PROJECT_ID"]
topic_id = os.environ["TOPIC_ID"]

# A batch is sent when ANY ONE of these thresholds is reached.
batch = BatchSettings(
    max_messages=50,
    max_bytes=1024 * 1024,  # 1 MiB
    max_latency=0.05,       # 50 ms
)

# Apply backpressure so the publisher does not buffer unboundedly.
flow = PublishFlowControl(
    message_limit=200,
    byte_limit=5 * 1024 * 1024,  # 5 MiB
    limit_exceeded_behavior=LimitExceededBehavior.BLOCK,
)

publisher = pubsub_v1.PublisherClient(
    batch_settings=batch,
    publisher_options=PublisherOptions(flow_control=flow),
)
topic_path = publisher.topic_path(project_id, topic_id)

futures = []
for index in range(100):
    event = {
        "event_id": str(uuid.uuid4()),
        "type": "EnrollmentCreated",
        "enrollment_id": f"lab-{index}",
    }
    payload = json.dumps(event).encode("utf-8")
    future = publisher.publish(
        topic_path, payload, event_type="EnrollmentCreated"
    )
    futures.append(future)

# Consider successful only when each future is confirmed.
published = 0
for future in futures:
    message_id = future.result(timeout=60)
    published += 1
    print("Published:", message_id)

print("Confirmed messages:", published)
~~~

Meaning:

- 100 `publish()` calls represent **100 individual messages**; the SDK may pack them into fewer publish RPCs.
- `max_latency=0.05` prevents waiting too long when a batch is not yet full during normal client operation.
- `BLOCK` makes the producer wait when too many messages/bytes are outstanding; this is backpressure, **not durable persistence**.
- `future.result()` can raise exceptions or time out; production code must track state, retry per rules, and handle failures **per message**.
- The example only prints confirmed message IDs; never send real PII or secrets to a lab topic.

**Real-world usage:** use a singleton publisher or reused client per worker/process. Creating a new client for every HTTP request defeats batching, multiplies connections/threads, and complicates flushing on shutdown. During graceful shutdown, stop accepting new events and await pending futures within an operational deadline.

### 3.2. Choosing limits from a memory budget

Suppose average payload size is **8 KiB**, allowing up to 500 outstanding messages:

\[
500 \times 8\ \text{KiB} \approx 3.9\ \text{MiB}
\]

This covers **payload bytes only**, excluding Python objects, futures, batching overhead, attributes, gRPC buffers, and application variables. Never set `byte_limit` equal to all remaining RAM. Leave generous headroom, measure actual RSS/heap under load, and set **both `message_limit` and `byte_limit`** since message sizes can vary.

### 3.3. Publisher errors and remediation

| Signal | Common causes | Actions |
| --- | --- | --- |
| `publish()` blocks long with `BLOCK` | Pub/Sub quota, network, service latency, or thresholds too low | Inspect publish latency/errors, quotas, and producer rate; do not simply remove flow control. |
| `DEADLINE_EXCEEDED`, failing futures | Stalled publish requests or client accepting faster than send rate | Retry with backoff and deadlines, check batch/flow control, detect business duplicates. |
| RAM climbs continuously | `IGNORE`, accumulating futures, or app retaining all payloads/futures | Cap outstanding work, resolve completed futures, reduce app memory retention. |
| Pub/Sub returns `RESOURCE_EXHAUSTED` | Quota/throughput limits or traffic exceeding provisioned capacity | Inspect quotas, publish rate, and formal quota increase process. |
| Publish p99 latency spikes after raising batch size | Batches wait too long to fill count/bytes | Lower `max_latency` or count threshold; inspect request size/RPS. |
| Shutdown loses unsent events | Process exits before futures/flush finish | Graceful shutdown, durable queue/outbox, and publish confirmation. |

**Do not "fix" publish failures with infinite retries:** if the producer persistently outpaces capacity, retries worsen congestion. Balance **input event rate, publish capacity, quotas, and downstream processing capacity**.

## 4. Subscriber flow control: receiving only what you can handle

Pull/StreamingPull subscribers fetch messages from a subscription. With high-level client libraries, flow control limits messages **already delivered to the client but not yet acked/nacked**, preventing RAM exhaustion or excessive concurrent execution. Upon hitting either threshold, the client pauses pulling more until outstanding work drops.

| Python `FlowControl` parameter | Meaning | Risk if misconfigured |
| --- | --- | --- |
| `max_messages` | Maximum outstanding messages. | Too high overloads handlers; too low wastes capacity. |
| `max_bytes` | Maximum total bytes of outstanding messages. | Too high risks OOM with large payloads. |
| `max_lease_duration` | Max time client holds leases / auto-extends ack deadlines for messages. | Shorter than processing increases redeliveries; too long delays recovery when a worker hangs. |
| `min_duration_per_lease_extension` / `max_duration_per_lease_extension` | Bounds per lease extension where supported by SDK. | Check semantics with exactly-once/latency and your specific SDK. |

Current Python `FlowControl` defaults are roughly **1,000 messages** and **100 MiB**; however, defaults and support vary across SDKs and languages. For critical apps, set values explicitly based on benchmarks.

### 4.1. Safe Python StreamingPull example for lab

This example reads `EnrollmentCreated` events and prints the event ID for illustration. In production, replace printing with an **actual idempotent processing transaction** before acking.

~~~python
import json
import os

from google.cloud import pubsub_v1

project_id = os.environ["PROJECT_ID"]
subscription_id = os.environ["SUBSCRIPTION_ID"]

subscriber = pubsub_v1.SubscriberClient()
subscription_path = subscriber.subscription_path(
    project_id, subscription_id
)

flow = pubsub_v1.types.FlowControl(
    max_messages=40,
    max_bytes=10 * 1024 * 1024,  # 10 MiB
    max_lease_duration=600,      # 10 minutes
)

def callback(message):
    try:
        event = json.loads(message.data.decode("utf-8"))
        event_id = event["event_id"]  # required

        # LAB: no durable side effect.
        # PROD: commit idempotent DB transaction before ack.
        print("Handled event:", event_id)

    except Exception as error:
        print("Processing failed:", type(error).__name__)
        message.nack()  # eligible for redelivery
    else:
        message.ack()   # only after processing succeeds

streaming = subscriber.subscribe(
    subscription_path, callback=callback, flow_control=flow
)
print("Listening for messages; Ctrl+C to stop")

try:
    streaming.result()
except KeyboardInterrupt:
    streaming.cancel()
finally:
    subscriber.close()
~~~

**Why set both 40 messages and 10 MiB?** With many small messages, the count limit engages first; with huge payloads, the byte limit keeps a handful of messages from consuming excessive RAM. This is a **client-side cap**, not a guarantee that exactly 40 threads run simultaneously—actual concurrency also depends on the executor/scheduler, CPU, and callback code.

**Production handling:** if the callback writes to a database, call `ack()` only after commit succeeds. When using a transaction with a unique `event_id` key for deduplication, a redelivered message is recognized as already handled and acked safely. Avoid holding DB transactions or connections open across slow external I/O.

### 4.2. Ack/nack and redelivery

Pub/Sub normally provides **at-least-once delivery**: a message may arrive again if its ack deadline expires, the client disconnects, or a transient failure triggers retry. Therefore:

1. **Process first, ack after**: early acking risks losing work if a worker crashes.
2. **Nack on transient errors** with an appropriate retry/delay strategy; continuously nacking immediately can trigger a retry storm.
3. **Poison messages** (corrupt payloads, unsupported schemas) need a dead-letter policy and quarantine workflow rather than infinite redelivery.
4. **Idempotency** by business key/event ID is required even when using pull exactly-once, because exactly-once does not combine application DB operations and Pub/Sub into a single atomic transaction.
5. Log message ID, event ID, delivery attempt, and error category **without PII** to investigate redeliveries.

With **exactly-once delivery**, only eligible pull subscriptions are supported; it adds latency/cost and imposes regional, ack-confirmation, and quota constraints. Never enable it merely to paper over missing database idempotency.

### 4.3. Ack deadline and lease extension

Subscriptions have an initial **ack deadline**. If the subscriber fails to ack in time, the message can be redelivered. High-level client libraries automatically **extend leases** for messages still being processed, up to configured limits. However:

- Processing longer than `max_lease_duration` can trigger redelivery even while the callback is still running.
- Process crashes, network drops, or wedged callbacks stop lease renewal.
- Do not set a massive ack deadline just to "hold" every message; that prolongs failure recovery.
- Tasks taking tens of minutes or hours should consider **job orchestration** (e.g., Cloud Tasks/Workflows/Batch) rather than holding a Pub/Sub lease forever.

A redelivered message may be picked up by a different worker; use idempotency keys, transaction isolation, or proper business synchronization.

### 4.4. Pull, StreamingPull, and push are not the same

| Mode | Who throttles reception? | How to optimize |
| --- | --- | --- |
| **StreamingPull (high-level SDK)** | Subscriber client maintains stream, uses flow control/lease management. | `max_messages`, `max_bytes`, callback concurrency, process count. |
| **Unary Pull** | Application calls Pull RPC in batches/intervals. | Cap `maxMessages` per pull, tune polling, avoid deprecated `returnImmediately=true`. |
| **Push subscription** | Pub/Sub sends HTTP requests to endpoint; HTTP responses drive ack/retry. | Endpoint capacity/latency, instance count/concurrency, retry policy, auth; **do not** apply client `FlowControl` to push endpoints. |
| **Cloud Run/GKE subscriber** | Depends on whether pull worker or HTTP push is used. | Pull: tune worker/flow. Push: tune HTTP handler, instances, concurrency, and response-based ack. |

For **push**, return HTTP success only when processing meets business durability criteria; returning 2xx before persisting lets Pub/Sub treat the message as acked and skip redelivery if later steps fail. Under high load, the backend needs proper backpressure and principled concurrency limits.

### 4.5. Concurrency differs from flow control

A process with `max_messages=200` but only **5 worker threads** leaves 195 messages sitting in the client while leases are repeatedly renewed. Conversely, 100 threads on a 1-vCPU VM increases context switching, holds too many DB connections, and worsens p99 latency.

To tune:

- **I/O-bound**: increase concurrency within bounds if network/database allows.
- **CPU-bound**: account for vCPU count, process count, and profiling before adding threads.
- **DB-bound**: cap connection pools, transactions, and QPS; adding subscribers does not cure DB saturation.
- **Ordering key**: messages with the same key require sequential handling under ordered delivery; adding parallel workers cannot speed up a single hot key indefinitely.

In Java, configure **`FlowControlSettings` on the subscriber**, distinct from callback executor/concurrency settings. Never treat `maxOutstandingElementCount` as the thread count without inspecting scheduler configuration.

## 5. Sizing: from throughput to outstanding limits

Derive configuration from **measured workload numbers** instead of multiplying defaults blindly. Under steady traffic, Little's Law provides a baseline estimate:

\[
\text{Average outstanding} \approx
\text{messages/s} \times \text{average processing time (s)}
\]

For example, a subscriber receives **200 messages/s** and callbacks take **250 ms** on average:

\[
200 \times 0.25 = 50\ \text{messages processing/waiting on average}
\]

`max_messages=50` leaves **zero headroom** when p99 rises or bursts hit. Test values like **80–120** (illustrative only), measure outstanding counts and memory, and tune against SLOs. If the worker executor can only run 10 callbacks concurrently, raising the limit to 1,000 will not yield matching throughput.

### 5.1. Check both limits together

Suppose average payload size is **256 KiB**, with occasional **2 MiB** messages. If `max_messages=100`:

- At **average payload**: `100 × 256 KiB = 25 MiB`.
- At **large payload**: up to `100 × 2 MiB = 200 MiB`.

In a memory-constrained container, set `max_bytes` according to real budget (e.g., **32 MiB**) to prevent buffering 100 large messages at once. Reserve memory for the runtime, JSON parsing, business objects, TLS buffers, client libraries, and caches.

**Rule:** whichever limit hits first (messages or bytes) stops the subscriber from pulling more. SDKs can slightly overshoot due to in-flight network frames; never treat flow control as a strict hard memory sandbox.

### 5.2. Backlog growth from sustained under-capacity

If publishers steadily send **500 messages/s** while all subscribers combined only process/ack **300 messages/s**, backlog grows at roughly:

\[
(500-300)\times 3600=720{,}000\ \text{messages/hour}
\]

Raising one subscriber's `max_messages` from 100 to 1,000 only pulls more backlog into RAM—it **does not create the missing 200 messages/s of processing capacity**. You must optimize handlers, add replicas/workers, scale database capacity, or throttle producers acceptably.

### 5.3. Publisher batch sizing example

A producer emits **2,000 messages/s**, averaging **1 KiB** each. With `max_messages=100`, `max_bytes=1 MiB`, `max_latency=50 ms`:

- In 50 ms, the producer generates roughly **100 messages**.
- Count and latency thresholds fire around the same time, ideally producing roughly **20 batch RPCs/s**.
- Each batch is about **100 KiB of payload**, well below the 1 MiB byte threshold.

Real numbers differ due to traffic bursts, framing overhead, network/RPC latency, client flushing, and retries. Never treat 20 RPC/s as a Pub/Sub-guaranteed quota.

### 5.4. Starting configuration matrix

| Workload profile | Publisher | Subscriber |
| --- | --- | --- |
| Small, high-volume events prioritizing throughput | Raise batch count/bytes sensibly; short-to-medium latency, `BLOCK`/`ERROR` flow control | Multiple workers, RAM/CPU-bounded flow control, watch backlog |
| Interactive requests needing near-real-time handling | Low batch latency; avoid waiting for huge batches | Fewer outstanding, sufficient concurrency, low p99 ack latency |
| Large messages, memory-heavy parsing | Tighter byte limit than count, measure serialization overhead | Tight byte limit, avoid duplicating payload buffers in handler |
| I/O-heavy database processing | Avoid unbounded publish rates | Size concurrency and connection pool to DB capacity, idempotency |
| Time-varying / spiky traffic | Producer backpressure + durable buffer if needed | Autoscale workers by backlog age/throughput, not CPU alone |
| Ordered messages on a hot key | Enable ordering only when needed, manage per-key errors | Do not expect adding threads to parallelize the same ordering key |

## 6. Tuning by metrics and SLOs

### 6.1. Monitor the pipeline across three tiers

| Tier | Metrics/questions | Guidance |
| --- | --- | --- |
| Publisher client | Publish future success/failure, p95/p99 publish latency, outstanding messages/bytes, `BLOCK` time | Detect congestion before messages even reach Pub/Sub. |
| Topic/Pub/Sub | Publish request/error rates, quota utilization, message sizes, service-side latency | Spot quotas, oversized payloads, or traffic shifts. |
| Subscription | **`subscription/num_unacked_messages_by_region`**, **`subscription/oldest_unacked_message_age_by_region`** | Measure regional backlog and oldest message age. |
| Pull/StreamingPull | **`subscription/expired_ack_deadlines_count`**, ack latency, redelivery/nack, flow-control saturation | Detect slow processing or leases failing to keep up. |
| Push endpoint | **`subscription/push_request_count`** by response code, HTTP latency, container concurrency | Separate push/HTTP errors from business logic issues. |
| Business | Newly processed `event_id` count, event-to-DB-commit duration, duplicate rate | Measure business objectives rather than raw request volume. |

When alerting by regional availability, prefer **metrics with the `_by_region` suffix** so a single regional issue does not blind visibility into other regions. Verify metric names, labels, sampling, and scope in current Cloud Monitoring docs; do not assume all charts share the same ingestion lag.

### 6.2. Interpreting backlog accurately

| Trend | Likely causes | Action direction |
| --- | --- | --- |
| Backlog count **and** oldest age both rise | Subscribers process slower than input | Scale capacity properly, optimize handlers/downstream. |
| Low backlog yet very high oldest age | A few poison/stuck messages | Inspect failing messages, retries, DLQ, ack timeouts. |
| Expired ack deadlines rise | Slow processing, wedged callbacks, lease gaps, or excessive outstanding | Lower flow limits, optimize processing, tune leases sensibly. |
| Low subscriber CPU, high backlog | Too few workers/connections, low flow limit, hot ordering key, or DB blocking | Inspect executor, stream health, ordering, DB metrics. |
| Publish latency rises while subscriber backlog is low | Publisher/quota/network bottleneck | Check batching, futures, `BLOCK` behavior, publish RPC latency. |
| Redeliveries spike after autoscaling | Workers killed mid-processing, poor graceful shutdown | Drain in-flight callbacks, never ack early, idempotency, shutdown hooks. |

Do not look solely at `num_unacked_messages` and scale workers indefinitely. If the downstream database is already at connection/IOPS limits, adding subscribers causes even more timeouts and redeliveries.

### 6.3. Iterative optimization workflow

~~~mermaid
flowchart TD
    M["Collect baseline:<br/>publish/ack latency, backlog, errors"] --> B{"Primary bottleneck?"}
    B -->|Producer| P["Batching + publisher flow control,<br/>quotas/network/RAM"]
    B -->|Consumer| C["Flow control + handler concurrency,<br/>CPU/DB/ack lease"]
    B -->|Downstream| D["DB/HTTP capacity, idempotency,<br/>backpressure and retries"]
    P --> T["Change only one parameter group,<br/>load test with realistic traffic"]
    C --> T
    D --> T
    T --> S{"SLOs, backlog age,<br/>cost, error rate met?"}
    S -->|No| M
    S -->|Yes| E["Document decision and alerts;<br/>monitor post-release"]
~~~

**Never simultaneously raise batch size, worker count, and DB pool size**, or you will not know which change helped or hurt. Test distinct profiles: small/large messages, sustained bursts, failing callbacks, worker restarts, slow databases, and peak load. Measure at least **p95/p99 end-to-end latency**, backlog age, memory, and total cost.

## 7. Reliability and related limits

### 7.1. At-least-once, idempotency, and outbox

An enrollment system must not send duplicate emails just because a message arrives twice. Safe processing pattern:

1. Publisher creates a **unique, stable `event_id`** and places it in payload/attributes.
2. Subscriber uses a DB transaction to check whether `event_id` has been processed, updating business state and recording completion atomically.
3. **Ack only after the transaction commits**.
4. For external side effects (sending email/charging cards), use idempotency keys or durable workflows to prevent duplicates even when workers crash.

If a DB write succeeds while the publisher is unsure the event was sent, a **transactional outbox** writes the event inside the same DB transaction; an independent relay publishes and marks it sent. An outbox reduces event loss at the DB/Pub/Sub boundary, though subscribers still need idempotency because publishing can repeat.

### 7.2. Ordering keys and throughput limits

Pub/Sub supports **message ordering** when publisher and subscription are configured properly by region/key. Ordering applies **within a single ordering key**, not across the whole topic.

For instance, `ordering_key="student-42"` ensures events that must run sequentially for one student are delivered in order under product conditions. If **one hot key** carries all traffic, subscribers cannot run callbacks for that key across parallel threads while preserving order. Choose keys fine-grained enough for parallelism without violating business invariants.

With ordered delivery, acks for messages sharing a key must occur **in order**; missing/failed acks on earlier messages can cause later ones to be redelivered. Publisher batching does not replace ordering configuration and can widen blast radius when one message in a group fails.

### 7.3. Retries, dead letters, and autoscaling

- Choose a retry policy with backoff to prevent poison messages from hot-looping.
- Use a **dead-letter topic** for messages failing past appropriate attempts; configure IAM, delivery attempts, and separate DLQ processing.
- For GKE/Compute Engine workers, autoscale on **backlog/oldest age** and backend capacity, not CPU alone.
- For Cloud Run push, configure request timeouts, concurrency, min/max instances, and HTTP success codes; do not apply StreamingPull client settings to push endpoints.
- When a process shuts down, stop accepting new messages and either finish or let Pub/Sub redeliver in-flight messages per strategy; never ack before true state commits.

**Exactly-once pull** differs in scope, cost, and latency from default at-least-once. Pick it when requirements truly need confirmed ack guarantees—never as a substitute for transactions, deduplication, or idempotent side effects.

## 8. Lab: batching publisher and StreamingPull subscriber

**Goal:** create a new topic/subscription in a lab project, publish **100 messages** using the Section 3 batching/flow-control config, consume with the Section 4 subscriber, monitor metrics, and clean up resources. This lab is **not** a large-scale load benchmark.

**Prerequisites:** approved project with billing and Pub/Sub API enabled; account permitted to create topics/subscriptions, and publisher/subscriber runtimes with appropriate IAM. Never run in production or against topics/subscriptions serving real customers. Typical IAM:

- Principal creating/deleting lab resources needs appropriate Pub/Sub management permissions; project-wide Owner is unnecessary.
- Publisher needs only `roles/pubsub.publisher` on the **topic**.
- Subscriber needs only `roles/pubsub.subscriber` on the **subscription**.
- On Compute Engine/GKE/Cloud Run prefer a **workload-attached service account**, never baking JSON keys into images. Locally, use ADC configured per org policy.

### 8.1. Prepare the project and create isolated resources

In authenticated Bash/Cloud Shell:

~~~bash
export PROJECT_ID="YOUR_APPROVED_LAB_PROJECT"
export TOPIC_ID="pubsub-batching-lab-UNIQUE"
export SUBSCRIPTION_ID="pubsub-flow-lab-UNIQUE"

gcloud config set project "$PROJECT_ID"
gcloud config get-value project

# Verify no topic/subscription with these names exists first
gcloud pubsub topics list --filter="name:$TOPIC_ID"
gcloud pubsub subscriptions list --filter="name:$SUBSCRIPTION_ID"

# WRITE OPERATION: use only lab resource names you own
gcloud pubsub topics create "$TOPIC_ID"
gcloud pubsub subscriptions create "$SUBSCRIPTION_ID" \
  --topic="$TOPIC_ID" \
  --ack-deadline=30

# Inspect created subscription
gcloud pubsub subscriptions describe "$SUBSCRIPTION_ID"
~~~

`--ack-deadline=30` is the subscription's initial deadline, **not** a hard ceiling on SDK processing time; with StreamingPull, the client can renew leases per configuration.

If the Pub/Sub API is not enabled yet, have an authorized user follow approval procedures to enable `pubsub.googleapis.com`. If names already exist, **do not overwrite or delete someone else's resources**; pick fresh lab names.

### 8.2. Run the two scripts from the lesson

Create local `publisher.py` with the code in **Section 3.1** and `subscriber.py` with the code in **Section 4.1**. Install the package inside a **lab machine** virtual environment:

~~~bash
python -m pip install google-cloud-pubsub
~~~

In terminal one, with environment variables set for the same project/subscription:

~~~bash
python subscriber.py
~~~

In terminal two, targeting the lab project/topic:

~~~bash
python publisher.py
~~~

Expected outcome:

- Publisher receives **100 message IDs** from successful futures unless an error requires investigation.
- Subscriber prints each `event_id` and acks **after** callback completion.
- Pub/Sub backlog drains over time as long as subscriber throughput exceeds publish rate and no competing consumer interferes.

It is **not** guaranteed that exactly 100 subscriber lines appear the instant the publisher exits: clients run asynchronously, redeliveries can occur, and stopping the subscriber too early leaves messages in the subscription. A Pub/Sub-confirmed message ID does not prove the subscriber succeeded. Evaluate using **publish success count, business event IDs, and ack/backlog**.

### 8.3. Experiment by changing one variable at a time

Starting from the baseline config, rerun in the lab with the same message count/size and test sequentially:

| Experiment | Change only | What to observe |
| --- | --- | --- |
| A | `max_latency: 0.05` → `0.5` | Does publish p95/p99 latency increase under sparse load? |
| B | BatchSettings `max_messages` from 50 → 1 | How do publish RPC count/overhead and latency change? |
| C | PublishFlowControl `message_limit` from 200 → 20 | Does the producer `BLOCK` when sending rapidly? |
| D | Subscriber `max_messages` from 40 → 10 | Do backlog/ack throughput, RSS, and wait time change? |
| E | Add simulated **100 ms** delay in lab callback | How do ack latency, backlog age, and outstanding count respond? |

Meaningful benchmarks require identical traffic profiles and enough samples; a 100-message lab only proves **mechanics and correctness**, not production sizing. Do not generate hundreds of thousands of messages just to make prettier graphs without quota, budget, and approval.

### 8.4. Safe resource cleanup

After stopping the subscriber and ensuring no other job uses the topic/subscription **you created**:

~~~bash
gcloud config get-value project
gcloud pubsub subscriptions describe "$SUBSCRIPTION_ID"
gcloud pubsub topics describe "$TOPIC_ID"

# DELETE OPERATION: only for verified lab resources
gcloud pubsub subscriptions delete "$SUBSCRIPTION_ID"
gcloud pubsub topics delete "$TOPIC_ID"

# Verify lab objects are gone
gcloud pubsub topics list --filter="name:$TOPIC_ID"
gcloud pubsub subscriptions list --filter="name:$SUBSCRIPTION_ID"
~~~

Deleting a subscription discards unacked messages in that subscription per product rules; never run this on data that must be kept. If a topic has other people's subscriptions or is used by another system, **do not delete the topic**. Billing, Monitoring, and logs may reflect cleanup with a delay.

## 9. Runbook when the system falls behind load

When backend requests slow down or backlog grows, investigate in order:

1. **Pinpoint the bottleneck:** publisher futures/latency, Pub/Sub subscription backlog, subscriber callbacks/acks, or database.
2. **Measure actual rates:** successful publishes/s, acks/s, and oldest unacked age over the same measurement window.
3. **Inspect active limits:** batch thresholds, publisher message/byte limits, subscriber message/byte/lease limits, worker threads/replicas, and quotas.
4. **Check resources:** CPU/RAM, network, DB connection pools, IOPS, retry rates, and redacted logs.
5. **Test one change:** e.g., lower subscriber flow limits if OOM, add workers if CPU/DB have headroom, or adjust batch latency if publish p99 is high.
6. **Verify outcome and resilience:** did backlog age drop, did redelivery/duplicate rates rise, and did cost and SLO improve?

| Symptom | Do NOT do immediately | Do FIRST |
| --- | --- | --- |
| Publisher OOM with large batches | Blindly add RAM | Enable proper flow control, count futures, measure payload/overhead. |
| Subscriber holds thousands of in-flight messages | Set threads equal to `max_messages` | Inspect CPU, executor, DB pool, and ack latency. |
| Backlog climbs steadily | Only raise `max_bytes` | Compare publish vs. ack throughput; scale real capacity or throttle input. |
| Expired ack deadlines rise | Max out ack deadline | Check slow processing, worker restarts, lease limits, and poison messages. |
| 429/quota or `RESOURCE_EXHAUSTED` | Tight-retry without backoff | Review quotas, peak load, retry policy, and publish thresholds. |
| One ordering key slows everything down | Add unlimited threads | Review ordering-key granularity and mandatory sequential steps. |
| Duplicate transactions after redelivery | Disable retries or ack on receipt | Add idempotency/transactions and ack only after commit. |

**Security and cost:** Pub/Sub charges for publish/delivery, storage/retention, and related items per current pricing; unnecessary redeliveries amplify downstream compute. Never log payloads containing PII, credentials, or tokens; use Cloud Monitoring labels/metrics and sanitized event IDs.

## 10. Real-world scenarios and exercises

### Scenario A — Subscriber loses database connectivity

A subscription receives 1,200 messages/s across 12 subscriber instances. Each instance sets `max_messages=1,000`, and callbacks open DB connections; the database allows only 100 total connections.

**Question:** why can scaling from 12 to 30 instances make things worse? What should you adjust first?

**Guidance:** `max_messages` does not equal DB capacity. If each instance opens multiple connections, exceeding 100 causes timeouts, nacks/redeliveries, and a growing backlog. **Cap pool size/concurrency per instance**, align subscriber count with DB capacity, apply backpressure, and measure commit throughput; scale workers only when downstream has headroom.

### Scenario B — Large batches delay notification emails

A publisher sends a few dozen events per second yet configures `max_messages=1,000` and `max_latency=2` seconds. Learners complain notification emails arrive slowly even though Pub/Sub is healthy.

**Question:** which tuning improves end-to-end latency? Should you lower subscriber flow control first?

**Guidance:** when wait time sits inside the publisher batch, **lower `max_latency`** and measure publish p95/p99 first. There is no reason to cut subscriber flow limits before the subscriber even receives the message. For near-real-time notifications, accept slightly more RPCs to improve latency.

### Scenario C — Redelivery storm during worker restarts

A subscriber takes 90 seconds per message, while `max_lease_duration=60` seconds and the autoscaler frequently replaces instances. After a deploy, several orders are written twice.

**Question:** list at least three layers to fix.

**Guidance:** align lease management with actual processing time; implement graceful shutdown to finish in-flight work where possible; lower outstanding limits to prevent overload; and enforce idempotency keys/DB transactions against duplicate writes. If work takes too long, move to an appropriate workflow/job service. **Extending leases** never replaces deduplication when processes crash.

### Scenario D — Hot ordering key

A publisher sets `ordering_key="all-enrollments"` on every event; the subscriber must handle 10,000 messages/s, yet throughput remains low despite adding lots of CPU.

**Question:** what is limiting throughput? Propose a better key.

**Guidance:** all messages sharing one key must be processed sequentially, eliminating per-key parallelism. If business logic only requires order **per student or per order**, use `student_id`/`order_id` as the ordering key. Verify that changing the key does not violate transactional business ordering.

### Quantitative exercise

A system processes **400 messages/s** with average callback duration **0.2 seconds**, p99 **1.2 seconds**, average payload 32 KiB, and spikes up to 1 MiB. RAM budgeted for outstanding message payloads is only **16 MiB**.

1. Compute average in-flight/waiting messages using Little's Law.
2. If `max_messages=500` is set with no byte limit, what is the risk if 500 large messages arrive concurrently?
3. Propose a starting **`max_messages`/`max_bytes` pair for benchmarking**, and explain why you cannot size from averages alone.
4. If total subscriber ack throughput is only **350 messages/s**, roughly how much does backlog grow after **30 minutes**?

**Hints/answers:**

- Average outstanding `400 × 0.2 = 80`.
- 500 messages × 1 MiB equals **500 MiB of payload**, massively exceeding the 16 MiB budget.
- You could start benchmarking with `max_messages=100` and `max_bytes=8 MiB`, then adjust based on real RSS, callback concurrency, p99, ack latency, and payload distribution; **this is not a guaranteed production config**.
- Backlog grows by `(400 - 350) × 1800 = 90,000` messages if the gap stays steady with no other changes.

### Self-check

1. **Is batching the same as flow control?** No; batching groups requests, while flow control limits outstanding work.
2. **Must all three batch thresholds (count/bytes/latency) trigger together?** No; whichever triggers first sends the batch.
3. **Does `publish()` returning a Future mean Pub/Sub received the message?** Not yet; you must observe the Future completing successfully.
4. **What does publisher `BLOCK` do?** Applies backpressure when outstanding work exceeds client limits.
5. **Is subscriber `max_messages` the thread count?** No; it caps outstanding messages, whereas concurrency is a separate mechanism.
6. **When should a subscriber ack?** Only after business processing and durable state persistence succeed.
7. **Does subscriber flow control stop publishers from sending to the topic?** No; the subscription backlog can continue growing.
8. **Why can a message be delivered again?** At-least-once delivery, ack deadline expiry, retries, or connection failures.
9. **Does exactly-once eliminate the need for DB-write idempotency?** No; Pub/Sub ack and a DB transaction do not form one atomic distributed transaction.
10. **When backlog age climbs, should you just add subscriber RAM?** No; diagnose whether the cause is insufficient throughput, poison messages, lease settings, or a downstream bottleneck.

## 11. Google Cloud references

- [Pub/Sub — Publish best practices](https://cloud.google.com/pubsub/docs/publish-best-practices): batching, retries, publish confirmation, and throughput.
- [Pub/Sub — Batch messaging](https://cloud.google.com/pubsub/docs/batch-messaging): count/byte/delay thresholds and batch limits.
- [Pub/Sub — Publisher flow control](https://cloud.google.com/pubsub/docs/flow-control-messages): outstanding messages/bytes, `BLOCK`/`ERROR`/`IGNORE`.
- [Pub/Sub — Subscribe best practices](https://cloud.google.com/pubsub/docs/subscribe-best-practices): ack after processing, redelivery, ordering, and subscriber flow control.
- [Pub/Sub — Subscriber flow control](https://cloud.google.com/pubsub/docs/flow-control): tuning StreamingPull/Pull during traffic spikes.
- [Pub/Sub — Lease management](https://cloud.google.com/pubsub/docs/lease-management): ack deadlines and lease extension.
- [Pub/Sub — Message ordering](https://cloud.google.com/pubsub/docs/ordering): ordering keys, order, and throughput.
- [Pub/Sub — Exactly-once delivery](https://cloud.google.com/pubsub/docs/exactly-once-delivery): pull subscription scope and trade-offs.
- [Pub/Sub — Dead-letter topics](https://cloud.google.com/pubsub/docs/dead-letter-topics): handling poison messages.
- [Pub/Sub — Monitor subscriptions](https://cloud.google.com/pubsub/docs/monitoring): backlog, oldest age, expired deadlines, and health metrics.
- [Pub/Sub — Quotas and limits](https://cloud.google.com/pubsub/quotas): message sizes, publish requests, and quotas.
- [Pub/Sub — Pricing](https://cloud.google.com/pubsub/pricing): publish/delivery/retention fees per current pricing.
- [Python Pub/Sub SDK](https://cloud.google.com/python/docs/reference/pubsub/latest): `BatchSettings`, `PublishFlowControl`, and `FlowControl`.

**Conclusion:** optimizing Pub/Sub means balancing **publisher batching for efficient sending**, **publisher flow control to prevent local queue buildup**, and **subscriber flow control/concurrency to protect workers and databases**. Results must be proven through **publish/ack throughput, oldest backlog age, p95/p99 latency, redelivery rate, memory, and cost**—not merely by increasing message or thread counts in configuration.
