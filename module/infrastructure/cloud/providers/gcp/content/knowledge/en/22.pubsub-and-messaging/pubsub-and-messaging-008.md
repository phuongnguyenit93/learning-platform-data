# Message retention and backlog management in Google Cloud Pub/Sub

A retail system publishes `order.created` events from **Cloud Run** to **Google Cloud Pub/Sub**. Workers on **GKE** process invoices and update **Cloud SQL**, while another pipeline writes analytics data to **Cloud Storage**. During a flash sale, the publisher emits messages faster than workers can process them. Backlog grows, customers receive invoices late; if the condition lasts past the retention window, some messages may no longer be delivered. Operations needs to answer: **how long are messages kept, why is the backlog growing, when must we scale, and if a subscriber processes wrongly, can we replay?**

This lesson belongs to the **Pub/Sub and Messaging** chapter of module **CLOUD_PROVIDERS_GCP**. It connects project/IAM, Cloud Run, GKE, Compute Engine, networking, storage, and database knowledge with designing resilient asynchronous systems, monitoring reliability, and controlling costs. The focus is **message retention and backlog management**; examples and exercises are self-contained and concise for practical application.

## 1. Learning objectives

After this lesson, you will be able to:

1. Distinguish **topic retention**, **subscription retention**, **retain acknowledged messages**, **subscription expiration**, and **ack deadline**.
2. Understand why messages exceeding retention can be purged **even if unacked**, and why replay must be designed upfront.
3. Read backlog metrics such as **unacked message count**, **oldest unacked message age**, and **delivery latency health score**.
4. Estimate the processing capacity needed to stop backlog growth and drain it before data expires.
5. Tune **flow control, concurrency, subscriber count, retries, and dead-letter topics** without overloading Cloud SQL or partner APIs.
6. Use **snapshots** and **seek** for controlled replay/recovery while applying idempotency to avoid duplicate side effects.
7. Configure test setups with `gcloud`, troubleshoot failures, and build a production operations checklist.

## 2. Pub/Sub model and message lifecycle

### 2.1. A topic is not a subscription

~~~mermaid
flowchart LR
    P["Publisher: Cloud Run"] --> T["Topic: orders-events"]
    T --> S1["Subscription: invoices-sub"]
    T --> S2["Subscription: analytics-sub"]
    S1 --> W["GKE invoice workers"]
    S2 --> A["Analytics processor"]
    W --> DB["Cloud SQL"]
    A --> GCS["Cloud Storage"]
~~~

- **Publisher** writes messages to a **topic**.
- Each **subscription** receives its own message stream from the topic per its configuration. An ack on `invoices-sub` **does not ack on behalf of** `analytics-sub`.
- **Subscriber** receives a message, performs business processing, and sends an **ack** once work completes safely.
- **Backlog** is the set of unacknowledged messages in a subscription (including messages waiting to be delivered and messages currently in flight).

This is standard Pub/Sub, not a single-consumer queue for the whole topic. If two apps pull from the **same subscription**, they share that subscription's work; if each app has its **own subscription**, both receive deliveries with independent state.

### 2.2. Three easily confused durations

| Concept | Unit/reference point | Meaning |
| --- | --- | --- |
| **Message retention duration** | Measured from **when the message is published**. | How long Pub/Sub can keep a message per topic/subscription policy. |
| **Acknowledgment deadline** | Seconds after a message is delivered. | Window for a subscriber to ack or extend lease; expiry may trigger redelivery. |
| **Subscription expiration period** | Duration of subscription inactivity. | When a subscription can be deleted due to inactivity; **distinct from** message retention. |

**Example:** a message is published at 09:00, subscription retention is 7 days, and ack deadline is 30 seconds. If a worker receives it at 09:05 and fails to ack within 30 seconds, the message can be redelivered; it is **not** kept an extra 7 days from each retry. The retention clock stays anchored to the original publish time.

## 3. Subscription retention and topic retention

### 3.1. Subscription retention: protecting each consumer's backlog

Per current Pub/Sub documentation:

| Property | Value |
| --- | --- |
| Default subscription retention | **7 days** for unacked messages. |
| Configurable retention | **10 minutes to 31 days**. |
| Default after ack | Messages are no longer available to pull again through the subscription. |
| `retain acknowledged messages` | Retains acked messages too within the retention window to support replay. |
| Default subscription expiration | **31 days** of inactivity; configurable per service rules. |

A message can be discarded once retention expires **even if unacked**. Increasing retention widens the incident recovery window, yet **does not make subscribers faster**, does not guarantee infinite storage, and can incur storage charges. <https://cloud.google.com/pubsub/docs/subscription-properties>

### 3.2. Topic retention: retaining at the event source

**Topic message retention** is **off by default**. When enabled, the topic retains messages from publish time for a configured window of **10 minutes to 31 days**, regardless of whether subscriptions have acked them. As a result, eligible subscriptions can replay already-acked messages or messages published before the subscription was created, as long as they remain within the retention window. <https://cloud.google.com/pubsub/docs/topic-message-retention>

When **both topic retention and subscription retention are present**, evaluate the **longer retention duration** per Pub/Sub rules; do not assume that once a 7-day subscription expires, messages are permanently unrecoverable if the topic retains them longer. Conversely, once both windows pass and messages are expunged, **seek cannot recreate data that is no longer stored**.

### 3.3. Keep retention on the topic or on the subscription?

| Requirement | Option to consider | Impact |
| --- | --- | --- |
| One consumer needs more time to drain backlog | Increase that subscription's retention accordingly. | Protects that subscription; monitor message age. |
| Multiple consumers need shared publish-history replay | Enable topic retention. | Stores one topic-level data source for eligible subscriptions; topic project incurs the fee. |
| One subscription needs to replay acked messages | `retain-acked-messages` or topic retention. | Allows `seek` while messages remain stored; incurs storage charges per feature pricing. |
| Need months/years of data retention | Design export/archival to Cloud Storage or another durable store. | Pub/Sub retention maxes out at 31 days; it is **not a long-term system of record**. |

**Do not enable long topic retention and long `retain-acked-messages` across many subscriptions out of habit.** Define actual replay requirements and estimate each cost line item.

### 3.4. Subscription expiration is not retention

A subscription with **no subscriber activity and no updates** can expire after the expiration period, **31 days** by default. Recreating a deleted subscription with the **same name** does not restore its previous backlog. For DR subscriptions or rarely active consumers, set the expiration policy deliberately and check data retention as well. <https://cloud.google.com/pubsub/docs/subscription-overview>

## 4. Ack deadline, retry, and dead-letter are distinct mechanisms

### 4.1. Ack only after committing

~~~mermaid
sequenceDiagram
    participant PS as Pub/Sub
    participant W as Subscriber
    participant DB as Cloud SQL
    PS->>W: Deliver message
    W->>DB: Write task via transaction / idempotency key
    DB-->>W: Commit succeeded
    W-->>PS: Acknowledge
    Note over PS,W: If not acked in time, message may redeliver
~~~

Acking **before** writing to Cloud SQL can mark a message as handled even if the transaction fails. Acking **after** commit protects the result, yet if the worker dies between commit and ack, the message can still redeliver: therefore subscribers must be **idempotent**.

### 4.2. Ack deadline does not extend retention

The default ack deadline is **10 seconds**, with supported initial configuration from **10–600 seconds**. Client libraries can **extend the ack deadline** for in-flight messages via lease management; retention measured from publish time stays unchanged. Setting the ack deadline too short invites duplicate deliveries; setting it too long delays redelivery of failed messages. <https://cloud.google.com/pubsub/docs/subscription-properties>

### 4.3. Retry and backoff

When a subscriber **nacks** or exceeds the ack deadline, Pub/Sub can redeliver the message. Subscription retry policy can be **retry immediately** or **exponential backoff**, depending on configuration. Push subscriptions also apply **push backoff**, affecting redelivery cadence.

| Error type | Recommended handling |
| --- | --- |
| Cloud SQL temporarily overloaded | Retry with backoff, jitter/concurrency limits; avoid a retry storm. |
| Partner API returns 429 | Respect rate limits, back off, and monitor retry lag. |
| Permanently invalid JSON schema | Do not retry infinitely; log diagnostics and use a dead-letter path. |
| Caller lacks permission for action | Record valid/idempotent error; do not retry hoping to bypass permissions. |

**Retry is not retention.** A message can be retried many times and still hit retention expiration; increasing retry count does not fix insufficient subscriber throughput.

### 4.4. Dead-letter topic (DLQ)

A **Dead-letter topic** is configured on the **source subscription** to forward unprocessable messages to a dedicated topic for investigation. `maxDeliveryAttempts` is typically set between **5–100**; actual attempts are **best effort**, not an exact hard counter. Misconfiguring IAM for the Pub/Sub service agent can break DLQ counting/forwarding. <https://cloud.google.com/pubsub/docs/dead-letter-topics>

~~~mermaid
flowchart LR
    S["orders-sub"] --> W["Subscriber"]
    W -- "Success / ack" --> DONE["Completed"]
    W -- "Error, ack expired / retry" --> S
    S -- "Exceeds expected delivery attempts" --> DLQ["orders-dlq topic"]
    DLQ --> DLS["DLQ subscription + investigation"]
~~~

DLQs **isolate poison messages**; they do not repair payloads automatically and do not replace backups. You must create a **subscription attached to the DLQ topic** to actually read forwarded messages; design dedicated retention, IAM, alerts, and replay procedures. When redriving from a DLQ, guard against duplicate side effects just as with any retry.

## 5. Backlog is a signal, not just a message count

### 5.1. Key metrics in Cloud Monitoring

Google Cloud recommends using **regional** Pub/Sub metrics when monitoring backlog so dashboards continue reporting from healthy regions if one region has an outage:

| Cloud Monitoring metric | Interpretation | Signal |
| --- | --- | --- |
| `pubsub.googleapis.com/subscription/num_unacked_messages_by_region` | Unacked message count per region. | Size of current backlog. |
| `pubsub.googleapis.com/subscription/oldest_unacked_message_age_by_region` | Age (seconds) of the oldest unacked message per region. | Processing lag and risk of hitting retention. |
| `pubsub.googleapis.com/subscription/delivery_latency_health_score` | Status of factors affecting delivery latency. | Isolates delivery degradation. |
| `pubsub.googleapis.com/topic/num_retained_messages` | Count of messages retained by the topic when retention is on. | Volume of retained topic data. |

Verify exact metric names and support at <https://cloud.google.com/pubsub/docs/monitoring>. Metrics can have **gaps of a few minutes**; a single data point does not represent overall state. For `_by_region` metrics, configure alerts with region labels and intentional aggregation rules.

### 5.2. Reading count and age together

| Unacked count | Oldest message age | Likely cause | Action |
| --- | --- | --- | --- |
| Rising | Rising | Publishing faster than ack capacity, failing subscribers, or downstream bottleneck. | Measure publish/ack rates, scale subscribers, check dependencies. |
| Small, fairly steady | Rising | A few stuck **poison/stuck messages**. | Check error logs, delivery attempts, DLQ. |
| High but falling | Falling | System is draining backlog. | Track drain ETA and retention risk. |
| Near 0 | Low | Possibly healthy, or publisher stopped sending. | Cross-check publish rate and business targets. |
| Any | Approaching retention | **Risk of message expiration and data loss**. | Prioritize incident response and policy-compliant preservation/recovery. |

**Do not alert solely on a fixed message count threshold.** One million messages may be normal for a system processing millions per second, yet catastrophic for a consumer handling only a few messages per second.

### 5.3. Two rates that govern backlog

Let:

- \(\lambda\): publish rate entering the subscription (messages/second).
- \(\mu\): sustainable **successful processing and ack** rate (messages/second).
- \(B\): backlog message count.

Over a sufficiently steady interval, you can estimate:

~~~text
Backlog rate of change ≈ lambda - mu

If mu > lambda:
  Time to drain backlog ≈ B / (mu - lambda)

If mu <= lambda:
  Backlog cannot sustainably shrink merely by waiting.
~~~

**Hypothetical example:** backlog is 120,000 messages; publisher continues sending 300 messages/s; workers process and ack 500 messages/s. Net drain rate is 200 messages/s, so draining takes roughly **600 seconds = 10 minutes**, *assuming steady rates and negligible retries/poison messages*. In reality, account for traffic variance, message sizes, database latency, errors, and quota limits.

To protect retention, always compare **oldest unacked age** against **remaining retention time**, not just the drain ETA computed from total backlog.

## 6. Actions when backlog grows

### 6.1. Identify the bottleneck before scaling

~~~mermaid
flowchart TD
    A["Backlog / oldest age rising"] --> B{"Publish rising or ack dropping?"}
    B -->|Publish rising| C["Check scaling headroom + quotas"]
    B -->|Ack dropping| D["Logs, errors, downstream, leases"]
    C --> E["Add subscribers / optimize processing"]
    D --> F{"Transient error or poison?"}
    F -->|Transient| G["Backoff + limit concurrency"]
    F -->|Poison| H["DLQ + investigation"]
    E --> I["Re-measure ack rate, backlog age, SLO"]
    G --> I
    H --> I
~~~

If Cloud SQL is already at its connection limit, scaling from 10 to 100 workers can actually **lower effective ack rate** due to extra retries. The right fix may be reducing pool size, batching writes, tuning concurrency, or scaling the database before adding subscribers.

### 6.2. Pull subscribers: flow control and lease management

For pull/StreamingPull:

- Prefer **client libraries** to handle connections, lease extension, batching, and flow control.
- Cap **outstanding messages** and **outstanding bytes** according to worker memory/CPU.
- Ack **after** committing work; nack or allow retry on transient errors per policy.
- Size threads/streams/instances to real processing capacity to avoid `OOM` from pulling too many messages.
- Set proper timeouts and retries for Cloud SQL/Cloud Storage/HTTP clients; raising ack deadline does not cure a slow dependency.

~~~text
Publisher → Pub/Sub → StreamingPull → bounded worker pool → commit → ack
                                ↑
                max outstanding messages / bytes
~~~

**Backpressure** keeps receivers from pulling more messages than they can handle; it stabilizes the system though it may temporarily increase backlog. Pair it with autoscaling and alerts ahead of retention limits.

### 6.3. Push subscribers: HTTP responses and load tolerance

For a **push subscription** targeting Cloud Run/HTTP endpoints:

- Returning an **HTTP success status is treated by Pub/Sub as an ack** under push semantics—return it only after durable processing.
- HTTP errors, timeouts, or rejected responses trigger redelivery per push/retry policy.
- Configure Cloud Run **concurrency/min/max instances** and downstream capacity to absorb event bursts.
- Use an **OIDC token/service account** to authenticate Pub/Sub push requests to secured endpoints.
- If processing exceeds request timeouts, consider a **pull worker** or an appropriate async workflow instead of holding HTTP requests open too long.

Never return `2xx` upon receiving a request unless the application has persisted the message durably and still expects Pub/Sub retry guarantees if processing fails.

### 6.4. Alerts tied to the retention budget

Suppose a subscription retains messages for 7 days, while the SLO requires processing within 10 minutes:

1. **Early SLO alert:** oldest unacked exceeds a few minutes and is rising, regardless of how far away retention is.
2. **Capacity alert:** \(\mu \le \lambda\) over a sustained window; workers or downstream are bottlenecked.
3. **Safety alert:** oldest unacked approaches retention; prioritize data-loss risk immediately rather than waiting until day 7.
4. **DLQ alert:** messages appear in DLQ or retry/ack-deadline-expiration rates spike.

Derive thresholds from **SLOs, traffic profile, retention configuration, and actual capacity scale-up time** rather than copying one number across all subscriptions.

## 7. Replay: seek and snapshot

### 7.1. `seek` by timestamp

`seek` bulk-updates **ack state** on a subscription for messages that are still retained:

- Seeking to a **past** timestamp makes previously acked messages deliverable again when **topic retention** or **retain-acked-messages** is enabled.
- Seeking to a **future** timestamp bulk-marks messages as acked, effectively **skipping backlog**; this carries the risk of losing processing for valid data.
- Seek cannot resurrect messages whose retention has expired and been expunged.

Seek can take a short while to take full effect on in-flight deliveries; "old" messages may briefly still arrive after a seek. **Never use seek to wipe production backlog just to make dashboards look clean.** <https://cloud.google.com/pubsub/docs/replay-overview>

### 7.2. Snapshot stores ack state, not a permanent copy

A **Snapshot** captures a subscription's ack state at a point in time to support recovery/replay. A snapshot has a maximum lifetime of **7 days**, and can be shorter depending on the **age of the oldest unacked message** at creation time. With a very old backlog, snapshot creation may be rejected because remaining useful lifetime is too short. <https://cloud.google.com/pubsub/docs/replay-overview>

| Mechanism | When appropriate | Limits |
| --- | --- | --- |
| Seek by timestamp | Proper retention exists; replay from a publish time | Imprecise relative to business event time; may redeliver extra messages |
| Seek by snapshot | Return to ack state captured before a rollout | Snapshot must exist beforehand; finite TTL; still needs idempotency |
| New subscription | Add an independent consumer for future events or replay when topic retention allows | Does not automatically get history no longer retained by the topic |
| Export/backup | Need >31-day retention or independent auditing | Must manage Cloud Storage, IAM, retention, cost, and restore |

### 7.3. Replay is not business exactly-once

Pub/Sub offers **exactly-once delivery** under supported conditions for pull subscriptions, yet it does not guarantee side effects in Cloud SQL, HTTP partners, or Cloud Storage occur only once. A commit followed by a failed ack still requires idempotency. Seek/replay intentionally causes messages to be delivered again even if already processed earlier.

**Practical design:** define a business idempotency key (`orderId` + event type + version), use transactions/unique constraints to persist results, and ack only after commit.

## 8. Hands-on `gcloud pubsub` in a lab project

Illustrative commands use **Bash** and hypothetical resource IDs. `create`, `update`, `publish`, `seek`, and `delete` are **write operations that can incur charges or alter data**. Run only in an authorized project; **never test `seek` on a production subscription** for learning because it alters delivery state in bulk.

### 8.1. Inspect context and existing resources

~~~bash
PROJECT_ID="retail-lab"
TOPIC="orders-events-lab"
SUB="invoices-sub-lab"

# READ-ONLY: active principal/project.
gcloud auth list
gcloud config get-value project

# READ-ONLY: list visible topics and subscriptions.
gcloud pubsub topics list --project="$PROJECT_ID"
gcloud pubsub subscriptions list --project="$PROJECT_ID"
~~~

### 8.2. Create topic and subscription with retention

~~~bash
# WRITE: use only unused names in a lab project.
gcloud pubsub topics create "$TOPIC" \
  --project="$PROJECT_ID"

# WRITE: a pull subscription retaining 7d, initially not retaining acked messages.
gcloud pubsub subscriptions create "$SUB" \
  --project="$PROJECT_ID" \
  --topic="$TOPIC" \
  --message-retention-duration=7d \
  --ack-deadline=30

# READ-ONLY: verify properties.
gcloud pubsub subscriptions describe "$SUB" \
  --project="$PROJECT_ID" \
  --format=yaml
~~~

If multiple learners share a lab, pick unique resource names per policy. A subscription retains messages **from creation time onward** (unless eligible topic retention history and a replay operation are used); it does not automatically inherit the topic's prior history.

### 8.3. Enable replay as needed

~~~bash
# WRITE: enable 14-day topic retention; topic storage charges may increase.
gcloud pubsub topics update "$TOPIC" \
  --project="$PROJECT_ID" \
  --message-retention-duration=14d

# WRITE: allow subscription to retain acked messages within its window.
gcloud pubsub subscriptions update "$SUB" \
  --project="$PROJECT_ID" \
  --message-retention-duration=7d \
  --retain-acked-messages

# READ-ONLY: inspect topic + subscription after changes.
gcloud pubsub topics describe "$TOPIC" --project="$PROJECT_ID"
gcloud pubsub subscriptions describe "$SUB" --project="$PROJECT_ID"
~~~

In production, do not enable both mechanisms by default: choose based on which consumers need replay, duration, and cost. Updating retention **does not restore previously expunged messages**. When adjusting subscription retention and expiration policies, ensure the durations remain compatible.

### 8.4. Test publish and pull

~~~bash
# WRITE: create test data.
gcloud pubsub topics publish "$TOPIC" \
  --project="$PROJECT_ID" \
  --message='{"eventType":"order.created","orderId":"O-1001"}' \
  --attribute=source=lab

# READ+ACK WRITE: --auto-ack is for lab use only.
gcloud pubsub subscriptions pull "$SUB" \
  --project="$PROJECT_ID" \
  --limit=10 \
  --auto-ack
~~~

**`--auto-ack` marks messages as processed upon CLI receipt**, without running Cloud SQL business logic. Never use this command to "clear" production backlog: messages will be acked with zero side effects committed.

### 8.5. Snapshot and seek in the lab

~~~bash
SNAPSHOT="invoices-before-release-lab"

# WRITE: capture ack state; snapshot has a finite TTL.
gcloud pubsub snapshots create "$SNAPSHOT" \
  --project="$PROJECT_ID" \
  --subscription="$SUB"

# READ-ONLY: inspect snapshot.
gcloud pubsub snapshots describe "$SNAPSHOT" \
  --project="$PROJECT_ID"

# WRITE: restore ack state from snapshot, affecting message delivery.
gcloud pubsub subscriptions seek "$SUB" \
  --project="$PROJECT_ID" \
  --snapshot="$SNAPSHOT"
~~~

Create snapshots **before** deploying sensitive subscriber versions; creating one after buggy code has already wrongly acked a batch will not rewind to the pre-incident state. Timestamp `seek` is also available, e.g., `--time=2026-11-19T00:00:00Z`, provided the timestamp falls within retained data and is explicitly approved.

### 8.6. Dead-letter for a new subscription

Example procedure:

~~~bash
DLQ_TOPIC="orders-dlq-lab"
DLQ_SUB="orders-dlq-reader-lab"
SOURCE_SUB="invoices-with-dlq-lab"

# WRITE: create a topic for failed messages and a consumer to read the DLQ.
gcloud pubsub topics create "$DLQ_TOPIC" --project="$PROJECT_ID"
gcloud pubsub subscriptions create "$DLQ_SUB" \
  --project="$PROJECT_ID" --topic="$DLQ_TOPIC"

# WRITE: subscription with dead-letter topic and max attempts.
gcloud pubsub subscriptions create "$SOURCE_SUB" \
  --project="$PROJECT_ID" \
  --topic="$TOPIC" \
  --dead-letter-topic="$DLQ_TOPIC" \
  --max-delivery-attempts=10
~~~

**Not yet production-ready for DLQ:** you must grant the required permissions to the subscription project's **Pub/Sub service agent** on the DLQ topic and source subscription per documentation; check IAM for cross-project DLQs. Never grant broad `roles/pubsub.admin` just to fix DLQ issues. Monitor the DLQ subscription separately, along with retention and redrive/idempotency runbooks.

## 9. Idempotent consumer example: Java and Cloud SQL

Suppose each message carries `eventType=order.created`, `eventId`, and `orderId`. A Java worker can use the Pub/Sub client library with StreamingPull and a **bounded executor**; the pseudocode below shows business ordering, not directly compilable source code:

~~~java
void onMessage(Message m, AckReply ack) {
    try {
        String eventId = required(m.attributes(), "eventId");
        String orderId = parseAndValidateOrder(m.data());

        database.transaction(tx -> {
            // processed_events table has UNIQUE(event_id).
            if (tx.insertProcessedEventIfAbsent(eventId)) {
                tx.createInvoiceIfAbsent(orderId);
            }
        });

        // Ack only when DB commit succeeds.
        ack.ack();
    } catch (InvalidPayloadException permanent) {
        // Log with redaction and route to DLQ/permanent error workflow;
        // do not return successful ACK unless error state is durably saved.
        ack.nack();
    } catch (TransientException temporary) {
        ack.nack(); // Pub/Sub retry/backoff; do not tight-spin forever.
    }
}
~~~

**Technical note:** a retry after DB commit can see the same `eventId` again. The unique constraint prevents repeating the side effect; however, if the workflow also **calls a partner outside the transaction**, use an outbox/unique delivery key or partner-side idempotency. Do not equate `messageId` with a business ID when a publisher might emit **two different messages** for the same business event.

## 10. End-to-end scenario: peak-hour backlog

### 10.1. Context

Order-event pipeline:

~~~mermaid
flowchart TB
    RUN["Cloud Run: orders API"] --> TOPIC["Topic: orders-events"]
    TOPIC --> INV["Subscription: invoices"]
    TOPIC --> ANA["Subscription: analytics"]
    INV --> GKE["GKE invoice workers"]
    GKE --> SQL["Cloud SQL"]
    ANA --> STORE["Analytics → Cloud Storage"]
    DL["DLQ: invoice-poison-events"] -. "Unprocessable error messages" .-> INV
    MON["Cloud Monitoring"] -. "Backlog/oldest age/retries/DB" .-> INV
~~~

During a 15-minute peak (hypothetical numbers):

| Signal | Hypothetical value | Assessment |
| --- | ---: | --- |
| Publish rate | 400 msg/s | Spiked sharply over daytime baseline. |
| Ack rate | 250 msg/s | Workers cannot keep up; backlog grows ~150 msg/s. |
| Backlog after 15 minutes at steady rates | 135,000 messages | `150 × 900` newly unprocessed messages. |
| Subscription retention | 7 days | Far from data loss limit, yet SLO can still be breached. |
| Invoice SLO | 5 minutes | Capacity action needed immediately, do not wait until day 7. |

### 10.2. Proper response

1. **Diagnose:** did ack rate drop due to Cloud SQL connections/locks/latency, or insufficient workers?
2. **Stabilize:** cap outstanding messages, prevent retry storms, and bound DB pools and error handling.
3. **Increase throughput sustainably:** scale workers by backlog and resource metrics while checking quotas and Cloud SQL capacity.
4. **Verify:** oldest unacked age must fall back toward the SLO threshold; falling unacked count alone is insufficient if old poison messages remain stuck.
5. **Recover:** if a deployment wrongly acked messages, use snapshot/seek when retention allows and ensure idempotency; if retention expired, rely on prepared durable sources/backups.
6. **Review costs:** retention, storage, DLQ, Cloud SQL, network, worker compute, and log volume.

Do not pick "raise retention to 31 days" as the primary fix for a subscriber with a severe code bug: retention only **buys time**; without fixing the root cause, backlog stays high and costs rise.

### 10.3. Runbook when approaching retention

- Confirm actual `messageRetentionDuration` on the topic/subscription and **oldest publish age**, rather than assuming doc defaults in production.
- Trigger an incident alert, recording start time, unacked count, rates, and error traces.
- Assess drain feasibility in the remaining window, scale carefully, and avoid crashing downstream systems.
- If data must be preserved longer, activate a **pre-prepared storage/recovery path**; never promise Pub/Sub can export already-expired messages.
- Do not seek to the future or delete a subscription during an incident without explicit data-preservation approval.

## 11. IAM, data security, and cost

### 11.1. Least privilege

| Principal | Typical permission | Avoid granting by default |
| --- | --- | --- |
| Cloud Run publisher | `roles/pubsub.publisher` on target topic. | Project-wide Pub/Sub Admin. |
| GKE invoice subscriber | `roles/pubsub.subscriber` on target subscription. | Admin over all topics/subscriptions. |
| Pub/Sub service agent for DLQ | Required permissions to pull source subscription and publish to DLQ. | Owner on the topic project. |
| SRE/operator | Monitoring viewer, describe permissions, and approved config changes. | Unrestricted `seek`/delete on any subscription. |

With **push subscriptions**, authenticate the Cloud Run endpoint via OIDC/service account and proper invoker permissions. **Pub/Sub IAM does not replace Cloud SQL IAM or Cloud Storage read permissions**.

### 11.2. Message payload and retention duration

Retained messages, logs, and DLQs can contain PII or transaction data. Never place secrets directly inside message payloads; use short-lived tokens or references per architecture where appropriate. Set retention short enough for data minimization policies yet long enough to survive real outages. Pub/Sub encrypts data at rest by default; if CMEK or specific storage regions are required, verify feature support and resource configuration.

### 11.3. Commonly overlooked costs

~~~text
Total cost ≈
  publish/delivery and throughput per pricing
  + topic/subscription retention storage
  + long-lived unacked message storage (additional charges per rules)
  + retaining acknowledged messages when enabled
  + snapshots/DLQ and replay operations
  + Compute Engine/GKE/Cloud Run subscriber compute
  + Cloud SQL/Cloud Storage, Logging/Monitoring, and network
~~~

Per Pub/Sub documentation, **unacknowledged messages retained in a subscription for more than 24 hours** can incur **additional storage charges**. Retaining acknowledged messages and topic retention also carry separate storage fees. Estimate based on **byte volume, subscription count, retention duration, rates**, and regional pricing/terms—not message count alone. <https://cloud.google.com/pubsub/pricing>

## 12. Troubleshooting: looking at the right failure layer

| Symptom | Possible cause | First check |
| --- | --- | --- |
| Backlog and age rising together | Low ack throughput, subscriber crashes, or CPU/DB bottleneck. | Publish/ack rates, worker logs, DB metrics. |
| Few unacked yet oldest age rising | Poison/stuck message. | Retry/error logs, delivery attempts, and DLQ. |
| Message redelivered despite code running | Ack deadline expired, ack failed, or process crashed after commit. | Lease management, ack metrics, idempotency table. |
| Not in DLQ despite many retries | Missing DLQ service agent IAM, misconfigured DLQ, best-effort attempt count. | Dead-letter policy, IAM, source subscription. |
| `seek` does not replay old messages | Retention was not enabled beforehand or messages were expunged. | Topic/subscription retention and publish timestamp. |
| Snapshot creation fails | Backlog has unacked messages too old, making snapshot TTL too short. | Oldest unacked age and snapshot constraints. |
| Subscription vanishes on its own | Subscription expiration due to inactivity. | Expiration policy and audit logs. |
| `--auto-ack` pull shrinks backlog yet no invoices exist | Messages were acked by CLI before business processing ran. | Audit test commands; recover if still in retention. |
| Cloud Run push returns 403 | Pub/Sub push identity lacks invoke rights or token audience mismatch. | Push SA, OIDC, Cloud Run IAM, and logs. |
| More workers lower ack rate | Cloud SQL/quota/thread contention, retry storm. | DB connections/locks, flow control, and 5xx errors. |
| Raising retention leaves old data missing | Policy updates do not restore already-deleted messages. | Time of policy change, topic retention, and backups. |

**Short workflow:** identify exact project/topic/subscription → read retention/expiration/retry/DLQ settings → inspect both regional backlog metrics → compare publish vs. ack rates → check workers, leases, and downstream → assess expiration risk → fix cleanly and confirm SLO recovery.

## 13. Exercises

### Exercise 1 — Distinguish five mechanisms

A subscription has 7-day message retention, 20-second ack deadline, and 31-day expiration period. Message A was published 6 days ago and remains unacked. A worker receives A and stalls for 20 seconds. What can happen after 20 seconds? If A stays unacked past retention, is redelivery still guaranteed?

### Exercise 2 — Topic vs. subscription

Two subscriptions share one topic. Analytics wants to replay all messages for 14 days, while Invoices only needs 2 days. Choose appropriate topic retention and subscription retention, specify who pays storage, and explain why `retain-acked` is not necessarily needed on every subscription.

### Exercise 3 — Compute backlog drain time

Current backlog is 90,000 messages. Publisher continues sending 200 msg/s, and subscriber acks 350 msg/s. Estimate drain time assuming constant rates. If ack rate drops to 180 msg/s, what do you conclude? State at least two assumptions that could invalidate the calculation.

**Hint:** with a net drain of 150 msg/s, about 600 seconds. When \(\mu < \lambda\), backlog continues to grow.

### Exercise 4 — Find the poison message

Unacked message count stays steady around 60, while oldest message age climbs continuously. Should you immediately add 50 workers? Outline the order to inspect error logs, retry attempts, schema, idempotency, and DLQ.

### Exercise 5 — Ack, commit, and exactly-once

A worker writes an invoice to Cloud SQL and is killed before acking. Pub/Sub redelivers the event. Design a unique key/transaction to avoid creating a duplicate invoice. Explain why exactly-once delivery does not automatically guarantee exactly-once side effects.

### Exercise 6 — Snapshot/seek

Before deploying a new consumer version, SRE creates a snapshot. Post-deploy, the consumer wrongly acks many messages. Describe how to seek to the snapshot, replay risks, and why snapshots are not multi-month backups. If no snapshot was created beforehand, what option exists when topic retention was enabled?

### Exercise 7 — Detecting near-retention risk

A subscription has 1-day retention, oldest unacked age is already 21 hours, and ack rate is below publish rate. Design alerts and a runbook prioritizing data preservation; explain why raising retention alone without fixing the worker is insufficient.

### Exercise 8 — Pub/Sub push to Cloud Run

A Cloud Run endpoint has restricted ingress; a Pub/Sub push subscription repeatedly gets 401/403. Distinguish token/audience, service account invoker permissions, routing/ingress, and application errors. If the endpoint returns 2xx before the transaction completes, what can happen?

### Exercise 9 — Cost estimation

A topic receives millions of events/day; three subscriptions each retain acknowledged messages for 31 days, and the topic also has 31-day retention enabled. List the cost components and propose a design that keeps replayability without unnecessary duplicate storage.

## 14. Production checklist and official documentation

| Item | What to verify |
| --- | --- |
| **Retention scope** | Topic retention, subscription retention, and retain-acked are chosen per actual replay need. |
| **Subscription lifetime** | Expiration policy fits low-activity/DR consumers; never confused with message retention. |
| **Ack/retry** | Ack after commit; deadline, lease extensions, exponential backoff, and retry budget are measured. |
| **DLQ** | DLQ topic/subscription, service agent IAM, delivery attempts, redrive, and alerts work. |
| **Backlog** | `num_unacked_messages_by_region`, `oldest_unacked_message_age_by_region`, and SLO/retention alerts exist. |
| **Capacity** | Publisher rate, subscriber ack throughput, flow control, instance scaling, and downstream limits tested. |
| **Replay** | Pre-change snapshot / approved seek procedures exist; idempotency is tested. |
| **Security** | Publisher/subscriber/push service accounts follow least privilege; PII is kept out of logs/DLQ. |
| **Cost** | Estimated retained bytes/age, subscription count, topic retention, DLQ, compute, and monitoring. |
| **Recovery** | Separate backup/archival if >31 days needed; practiced outage and data-loss drills. |

Official sources to verify limits, feature support, and pricing before deployment:

- [Pub/Sub subscription properties](https://cloud.google.com/pubsub/docs/subscription-properties)
- [Subscription message retention](https://cloud.google.com/pubsub/docs/subscription-message-retention)
- [Topic message retention](https://cloud.google.com/pubsub/docs/topic-message-retention)
- [Replay and purge messages with seek](https://cloud.google.com/pubsub/docs/replay-overview)
- [Dead-letter topics](https://cloud.google.com/pubsub/docs/dead-letter-topics)
- [Exactly-once delivery](https://cloud.google.com/pubsub/docs/exactly-once-delivery)
- [Flow control for subscribers](https://cloud.google.com/pubsub/docs/flow-control-messages)
- [Monitor Pub/Sub in Cloud Monitoring](https://cloud.google.com/pubsub/docs/monitoring)
- [Subscription overview and expiration](https://cloud.google.com/pubsub/docs/subscription-overview)
- [Pub/Sub pricing](https://cloud.google.com/pubsub/pricing)
- [gcloud pubsub reference](https://cloud.google.com/sdk/gcloud/reference/pubsub)

**Remember:** **retention** defines the window during which Pub/Sub can keep a message; **ack deadline** governs redelivery pacing; **backlog metrics** show whether consumers are keeping up; **seek/snapshot** enable replay within still-retained data. Good operations is not just getting backlog to 0—it means **messages are processed accurately, within SLO, without hitting retention expiry, and with controlled costs**.
