# Acknowledgment deadlines and redelivery handling in Pub/Sub

> **Chapter:** Pub/Sub and Messaging  
> **Lesson:** Acknowledgment deadlines and redelivery handling  
> **Module:** CLOUD_PROVIDERS_GCP

In the **CLOUD_PROVIDERS_GCP** module, learners study Google Cloud from project organization, IAM, and VPC to Compute Engine, GKE, Cloud Run, storage, and databases. For Java systems communicating via **Pub/Sub**, reliability does not end when the publisher sends successfully: subscribers must know **when to acknowledge processing, when to let a message be redelivered, and how to protect business logic from duplicate side effects**.

Pub/Sub defaults to an **at-least-once delivery** model. After a message is delivered to a subscription, Pub/Sub waits for an **acknowledgment** within the **acknowledgment deadline**. If the subscriber **nacks**, or the deadline expires without a valid acknowledgment, the message may **redeliver**. This behavior helps systems recover when workers fail, yet can cause orders or payments to be updated **twice** if code lacks **idempotency**.

**Core principle:** **persist results durably first, then ack**, use lease extension for long work, use retry/backoff and dead-letter topics for prolonged failures, and build idempotency even when exactly-once delivery is enabled. Examples use hypothetical sandbox projects; resource creation/deletion commands can incur costs and must not be run in production without approval.

## 1. Learning objectives

After this lesson, you will be able to:

1. Distinguish `messageId`, `ackId`, ack, nack, ack deadline, and message retention.
2. Explain when and why **redelivery** happens in pull/StreamingPull and push.
3. Choose an initial deadline: default **10 seconds**, range **10–600 seconds**; know when to use `ModifyAckDeadline`.
4. Use automatic **lease management** and flow control in a Java subscriber.
5. Distinguish **retry immediately**, **exponential backoff**, and **push backoff**.
6. Design a **dead-letter topic (DLQ)**, IAM for the Pub/Sub service agent, and safe replay procedures.
7. Understand the boundary between **exactly-once delivery** and **exactly-once business effects**.
8. Write and test a Java subscriber that acks/nacks in the right transactional order.
9. Monitor backlog, expired ack deadlines, push failures, DLQ, and cost.
10. Handle worker crashes, poison messages, ordering keys, and downstream failures.

## 2. Messages, subscriptions, and acknowledgment state

~~~mermaid
sequenceDiagram
    participant P as Publisher
    participant T as Pub/Sub Topic
    participant S as Subscription
    participant W as Java Worker
    P->>T: Publish(orderId=OD-42)
    T->>S: Message arrives at subscription
    S-->>W: Deliver(messageId=M, ackId=A1)
    Note over W: Ack deadline starts
    W->>W: Process and commit durably
    W->>S: Acknowledge(A1)
    Note over S: Record completion for subscription
~~~

| Term | Meaning |
|---|---|
| **Topic** | Endpoint where publishers send messages |
| **Subscription** | A receiving stream with its own ack state; two subscriptions on the same topic receive messages independently |
| **Message ID** | Identifier assigned by Pub/Sub on publish; useful for tracking a message |
| **Ack ID** | Token for the **current delivery attempt**, used to ack/nack/extend; can **change after redelivery** |
| **Outstanding** | Message that has been delivered but not yet fully acknowledged |
| **Ack deadline** | Wait window for acknowledgment of a delivery attempt |
| **Nack** | Signal that processing has not succeeded so the message can be retried |
| **Redelivery** | The same Pub/Sub message is delivered again |
| **Backlog** | Unacknowledged messages in a subscription |
| **Retention** | Duration messages are stored, **different from** ack deadline |

**Do not confuse fan-out with duplicates:** the same message arriving at two subscriptions `billing-sub` and `shipping-sub` is normal behavior. Receiving the **same messageId twice on the same subscription** typically indicates redelivery/duplicate delivery.

### 2.1. What happens when a worker crashes?

~~~text
t=0s   Worker A receives message M, ackId=A1; deadline 10s
t=2s   Worker A commits result to Cloud SQL
t=3s   Worker A crashes before ack
t>=10s Lease expires; M may be redelivered
t=12s  Worker B receives same messageId M, ackId=B2
t=13s  Worker B sees business event already processed in DB
t=14s  Worker B skips side effect and acks B2
~~~

Redelivery **is not guaranteed to happen at the exact 10-second mark**; timing also depends on retry policy, flow control, networking, and availability. Under at-least-once, your system must still tolerate duplicates even when a previous ack was sent.

## 3. Acknowledgment deadline and ack operations

### 3.1. Subscription-level parameters

| Property | Value |
|---|---|
| Default ack deadline | **10 seconds** |
| Minimum / maximum | **10 / 600 seconds** |
| Scope | Initial deadline after each delivery |
| Pull/StreamingPull | Can extend per message using `ModifyAckDeadline` |
| Push | Deadline also determines the HTTP request timeout; **cannot extend a single message individually** |
| Default message retention | **7 days**, with separate configurable limits; not processing time |

A subscription with a 60-second ack deadline **does not delete messages after 60 seconds**. While unacknowledged, a message remains within the retention window and can be redelivered.

### 3.2. Actions and consequences

| Action | How Pub/Sub interprets it | Consequence |
|---|---|---|
| `ack(ackId)` | Message processed | No further delivery needed under current semantics |
| `nack()` | Processing incomplete | Retry per policy |
| `ModifyAckDeadline(ackId, 120)` | Grant additional processing time | Extends deadline of current delivery |
| `ModifyAckDeadline(ackId, 0)` | Equivalent to nack for pull | Message becomes eligible for retry |
| Neither ack nor nack sent | No result yet | Expiry may trigger redelivery |

**Do not pass `messageId` instead of `ackId`** to Acknowledge/ModifyAckDeadline APIs. An old ack ID after redelivery may no longer be valid, especially on subscriptions with exactly-once enabled.

### 3.3. Trade-offs of too-low vs. too-high deadlines

- **Too low:** worker takes 45 seconds, deadline is 10 seconds; message may reach another worker while the first is still working.
- **Too high:** worker fails after 1 second, deadline is 600 seconds; message may not be retried promptly without another signal.
- **Balanced:** based on p95/p99 processing time and lease extension, balancing duplicate risk against recovery latency.

Do not set `600` on every subscription just to "be sure there are no duplicates." Measure processing duration, bound job timeouts, and monitor ack expirations.

## 4. How do Pull, StreamingPull, and Push differ?

| Property | Pull / StreamingPull | Push |
|---|---|---|
| Who fetches messages? | Subscriber actively connects | Pub/Sub sends an HTTPS request |
| How ack works | `Acknowledge(ackId)` or client `ack()` | HTTP success status |
| Nack | `nack()`/deadline 0 | HTTP error or timeout |
| Extend individual deliveries | **Yes** | **No** |
| Exactly-once delivery | **Yes**, under supported conditions | **No** |
| Suitable application types | Java workers on GKE/VMs, variable processing times | Cloud Run HTTP endpoints, short tasks |

### 4.1. Push: returning an HTTP status is an ack

Pub/Sub treats HTTP status codes `102`, `200`, `201`, `202`, and `204` as successful acknowledgment. Other responses or timeouts can cause Pub/Sub to redeliver.

~~~text
Pub/Sub push → Cloud Run /pubsub
  1. Cloud Run verifies OIDC push identity and Invoker IAM
  2. Java handler decodes/validates message
  3. Commit DB or write task to a durable queue
  4. Return HTTP 204
~~~

**Common mistake:** returning `202 Accepted` immediately while only holding the message in an in-memory variable to process on a background thread. If the instance is terminated, Pub/Sub already considers the message acked and will not redeliver it. For asynchronous tasks, write to a **durable queue/store before returning 2xx**.

For private Cloud Run, use authenticated push and grant `roles/run.invoker` to the proper push service account. Do not enable unauthenticated access just to fix a 403.

### 4.2. Push backoff is independent of retry policy

When a push endpoint returns repeated errors/timeouts, Pub/Sub applies automatic **push backoff** (roughly **100 ms–60 seconds**), which can slow down **the entire subscription**. Retry exponential backoff is a separate mechanism; when both apply, retry timing uses the larger delay per service semantics. Consequently, one poison message or widespread endpoint errors can throttle push delivery even for valid messages.

## 5. Lease management for long-running Java work

With the **high-level Java StreamingPull client**, the library automatically calls `ModifyAckDeadline` while a message remains unacked. It can choose lease durations based on historical acknowledgment latency (e.g., p99) and renew multiple times.

~~~mermaid
sequenceDiagram
    participant S as Pub/Sub
    participant J as Java Subscriber
    S-->>J: Message M (initial 10s)
    Note over J: Work takes 90s
    J->>S: ModifyAckDeadline(M, 45s)
    J->>S: ModifyAckDeadline(M, 45s)
    J->>J: Commit succeeded
    J->>S: Ack(M)
~~~

**Practical notes:**

- High-level libraries by default can extend for **about one hour total**; total lease period and per-extension duration have separate options.
- If the subscriber crashes, loses network, or exhausts the total lease period, the message can redeliver.
- **Lease extension does not equal a permanent exclusive lock** under at-least-once; idempotency is still required.
- If a job runs for hours, consider **splitting tasks, durable checkpointing, Cloud Tasks/Workflows, or a dedicated job pipeline**.
- **Flow control** caps outstanding messages/bytes. Letting an 8-thread worker pull 10,000 messages can leave thousands of deliveries waiting and expiring their leases before being processed.

## 6. Java pull subscriber: ack on success, nack on error

### 6.1. Minimal Maven POM

JDK 17 example; uses Google Cloud Libraries BOM to manage dependency versions:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example.messaging</groupId>
  <artifactId>orders-subscriber</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
  </properties>
  <dependencyManagement>
    <dependencies>
      <dependency>
        <groupId>com.google.cloud</groupId>
        <artifactId>libraries-bom</artifactId>
        <version>26.90.0</version>
        <type>pom</type>
        <scope>import</scope>
      </dependency>
    </dependencies>
  </dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>com.google.cloud</groupId>
      <artifactId>google-cloud-pubsub</artifactId>
    </dependency>
  </dependencies>
</project>
~~~

BOM `26.90.0` is a reference version from Google Cloud Java documentation at the time of writing; for real projects, pin and evaluate appropriate versions, dependency scans, and compatibility.

### 6.2. Java code for StreamingPull

~~~java
package com.example.messaging;

import com.google.cloud.pubsub.v1.AckReplyConsumer;
import com.google.cloud.pubsub.v1.MessageReceiver;
import com.google.cloud.pubsub.v1.Subscriber;
import com.google.pubsub.v1.ProjectSubscriptionName;
import com.google.pubsub.v1.PubsubMessage;

public final class OrdersSubscriber {
    public static void main(String[] args) {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                "Usage: OrdersSubscriber PROJECT_ID SUBSCRIPTION_ID");
        }
        ProjectSubscriptionName name =
            ProjectSubscriptionName.of(args[0], args[1]);

        MessageReceiver receiver =
            (PubsubMessage msg, AckReplyConsumer consumer) -> {
                String data = msg.getData().toStringUtf8();
                try {
                    // DEMO: production must use DB commit + idempotency.
                    if (data.startsWith("FAIL")) {
                        throw new IllegalStateException("Simulated error");
                    }
                    System.out.println("Processed " + msg.getMessageId()
                        + " data=" + data);
                    consumer.ack(); // ACK only when actually successful.
                } catch (Exception error) {
                    System.err.println("Failed " + msg.getMessageId()
                        + ": " + error.getMessage());
                    consumer.nack(); // Retry per subscription policy.
                }
            };

        Subscriber subscriber = Subscriber.newBuilder(name, receiver).build();
        Runtime.getRuntime().addShutdownHook(
            new Thread(() -> subscriber.stopAsync()));
        subscriber.startAsync().awaitRunning();
        System.out.println("Listening on " + name);
        subscriber.awaitTerminated();
    }
}
~~~

Save at `src/main/java/com/example/messaging/OrdersSubscriber.java`. Build with Maven/IDE and run with full dependencies; this program is an **example pull worker**, not a production-ready database processor.

**Limitations:** `System.out.println` is not a durable side effect. In production, **commit the DB or durable downstream operation before `consumer.ack()`**. Every exception calls nack in this demo; real systems must distinguish transient errors from poison messages and use a DLQ to avoid infinite loops.

### 6.3. IAM and authentication

| Identity | Appropriate role |
|---|---|
| Publisher service account | `roles/pubsub.publisher` on the topic |
| Java subscriber runtime identity | `roles/pubsub.subscriber` on the subscription |
| Deployer/CI | Separate Compute Engine/GKE deployment permissions |
| Pub/Sub service agent | Additional DLQ IAM only when forwarding is needed |

Use Application Default Credentials (ADC) with a VM-attached service account, Workload Identity Federation for GKE, or the appropriate service identity. On developer workstations, use `gcloud auth application-default login` per internal policy. **Never commit JSON keys or access tokens to Git or logs**.

## 7. Redelivery and durable idempotency

### 7.1. The "DB committed, ack not finished" window

~~~mermaid
sequenceDiagram
    participant S as Pub/Sub
    participant A as Worker A
    participant DB as Cloud SQL
    participant B as Worker B
    S-->>A: M (eventId=e-42)
    A->>DB: COMMIT business update
    Note over A: Crash before ACK
    S-->>B: Redeliver M
    B->>DB: Check unique eventId
    DB-->>B: Event already processed
    B->>S: ACK, create no new side effect
~~~

Pub/Sub acknowledgment and a Cloud SQL transaction are **two separate transactions**. Exactly-once delivery does not make two distinct systems commit atomically either. The safe approach is **durable deduplication**.

### 7.2. Reference SQL with a unique constraint

~~~sql
CREATE TABLE processed_events (
    consumer_name TEXT NOT NULL,
    event_key     TEXT NOT NULL,
    processed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_key)
);

CREATE TABLE order_status (
    order_id      TEXT PRIMARY KEY,
    status        TEXT NOT NULL,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

Within **a single transaction**, Java executes:

1. `INSERT INTO processed_events ... ON CONFLICT DO NOTHING`.
2. **If affected rows = 0:** message already processed → commit transaction and ack, **do not re-run the business effect**.
3. **If affected rows = 1:** update `order_status`, commit, then ack.
4. If DB commit fails, **nack**; if ack fails due to network error, the message may redeliver, and the marker prevents repeating work.

~~~sql
BEGIN;

INSERT INTO processed_events (consumer_name, event_key)
VALUES ('orders-worker', 'ORDER_CONFIRMED:OD-42')
ON CONFLICT DO NOTHING;

-- Java checks the INSERT row count above.
-- ONLY when the INSERT actually added a new row:
INSERT INTO order_status (order_id, status)
VALUES ('OD-42', 'CONFIRMED')
ON CONFLICT (order_id)
DO UPDATE SET status = EXCLUDED.status, updated_at = now();

COMMIT;
~~~

This SQL snippet is an **illustrative workflow**: the UPDATE step is not automatically skipped when INSERT returns 0; Java code must check affected rows and branch accordingly.

### 7.3. Choosing the right idempotency key for each duplicate source

| Duplicate type | Appropriate key |
|---|---|
| Pub/Sub redelivery of the same message | `subscriptionId + messageId` if deduplicating only at the subscription level |
| Publisher publishes the same business event multiple times | **Stable business eventId** |
| Charge request | `paymentId + operationType`, plus the payment provider's idempotency |
| Replay/seek or consumer rebuild | Business eventId + version, per replay policy |

**Do not use an in-memory `HashSet` as your sole deduplication store**: restarts or scaling across multiple Pods lose state. For side effects outside the DB (email, payment, HTTP), use a **transactional outbox** or downstream idempotency; a DB unique marker cannot automatically roll back an already-completed HTTP call.

## 8. Retry immediately and exponential backoff

| Subscription policy | Meaning | Impact |
|---|---|---|
| **Retry immediately** (default) | Redelivers promptly after nack/timeout | Fast recovery but prone to tight error loops |
| **Exponential backoff** | Waits increasingly between min and max | Useful when downstream is overloaded |
| **Push backoff** (automatic) | Throttles push when many requests fail | Can slow down the entire subscription |

**Distinguish the three timers:** ack deadline = time allowed for the current delivery; retry backoff = wait interval before the next delivery; retention = how long a message is retained. For example, if Java needs 50 seconds to process with a 10-second ack deadline, increasing retry backoff to 60 seconds **does not solve lease expiration**.

### 8.1. Handling errors by category

| Error | Strategy |
|---|---|
| Cloud SQL timeout/HTTP 503 | Short local retry, then nack; exponential backoff |
| Publisher sends permanently invalid JSON | Validate schema; send failures to DLQ, do not hot-retry forever |
| Event ID already in `processed_events` | Ack, do not call downstream again |
| 403 due to misconfigured IAM | Alert operations; retries only help after fixing the policy |
| GKE worker OOM | Reduce outstanding/concurrency, fix JVM/resources and DB pool |
| Downstream 429 quota | Bounded backoff, respect retry hints |

Do not hold deliveries outstanding with hours-long `sleep` calls just to delay retries: that holds leases, inflates backlog, and increases costs.

## 9. Dead-letter topics and poison messages

~~~mermaid
flowchart LR
    T["orders-topic"] --> S["orders-sub"]
    S --> J["Java worker"]
    J -->|"ACK"| OK["Completed"]
    J -. "NACK / deadline expired" .-> S
    S -->|"Best-effort after max attempts"| DLQ["orders-dlq topic"]
    DLQ --> DLS["orders-dlq-sub"]
    DLS --> OPS["Investigate / replay"]
~~~

- DLQ is configured on the **subscription**, not on the source topic.
- `maxDeliveryAttempts` ranges from **5–100**; if enabled and left blank, the default is **5**.
- Delivery count before forwarding to DLQ is **best effort**, **not** strictly exact on attempt N; counts can reset.
- The Pub/Sub **service agent of the project containing the source subscription** needs `roles/pubsub.publisher` on the DLQ topic and `roles/pubsub.subscriber` on the source subscription.
- **Create a separate subscription on the DLQ topic** to inspect forwarded messages.
- A DLQ message carries attributes describing the source subscription and attempt count; use them for investigation, as DLQ does not auto-fix schemas.

**Java delivery attempts:** documentation describes the `googclient_deliveryattempt` attribute in the Java client when DLQ is configured appropriately. The counter is approximate; do not rely on it as the sole source of business truth.

### 9.1. DLQ runbook

1. Read source, event ID, schema version, and error logs; avoid printing PII/credentials.
2. Classify as permanent poison error, transient error, or bad deployment.
3. Fix data/schema/permissions and verify idempotency.
4. Replay a few selected events in sandbox.
5. Perform controlled replay to the topic or a dedicated processor, measuring duplicate effects.
6. Monitor backlog/DLQ after changes; update alerts and runbooks.

## 10. Exactly-once delivery: exact scope

Pub/Sub supports **exactly-once delivery** for **pull/StreamingPull subscriptions**, **not push**. Per service conditions:

- Subscribers can **receive server confirmation of ACK results**.
- A message whose **ACK is confirmed successful** will not redeliver within the guarantee scope.
- While a message remains outstanding, it will not redeliver before the deadline expires.
- If multiple deliveries occurred due to deadline expiry/nack, only the **latest delivery's ack ID** is valid.
- The guarantee has **regional boundaries**, so use an appropriate regional endpoint if subscribers are distributed across regions.
- Exactly-once adds quota usage and overhead; benchmark before enabling broadly.

| Scenario | Does exactly-once delivery prevent it automatically? |
|---|---|
| Redelivery after a **confirmed successful** ack | **Yes**, within guarantee scope |
| Worker commits DB then crashes before ack | **No** |
| Publisher publishes the same event twice with **two message IDs** | **No** |
| Subscription intentionally calls `seek`/replays old messages | **No**, replay is intentional |
| External API charges twice before ack | **No**, requires downstream idempotency |
| Push/HTTP subscription | **Not supported** |
| Subscribers across multiple regions without consistent locational endpoints | Not fully guaranteed by default |

**Exactly-once delivery ≠ exactly-once business effect.** Always keep required unique constraints, transactions, and outboxes.

### 10.1. Java example of confirmed ack

Using `MessageReceiverWithAckResponse` and `AckReplyConsumerWithResponse`:

~~~java
MessageReceiverWithAckResponse receiver = (message, consumer) -> {
    // ONLY AFTER durable business commit.
    try {
        AckResponse response = consumer.ack().get();
        if (response == AckResponse.SUCCESSFUL) {
            System.out.println("ACK confirmed " + message.getMessageId());
        } else {
            System.err.println("ACK not confirmed: " + response);
        }
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        System.err.println("Interrupted while waiting for ACK");
    } catch (ExecutionException e) {
        System.err.println("ACK result unknown: " + e.getCause());
    }
};
~~~

This snippet is an **illustrative receiver fragment** requiring imports and `Subscriber.newBuilder(subscription, receiver)` on an exactly-once-enabled subscription. Blocking on the future is easy to understand but can hurt throughput; in production handle completion asynchronously and plan for failed/unknown ack results.

### 10.2. Message ordering

When ordering is enabled and the publisher sets the same ordering key:

- Pub/Sub delivers messages for the **same key** in order under supported conditions.
- When a message redelivers, subsequent messages **for the same key** may also redeliver, even if already acked, to maintain order.
- With **exactly-once + ordering**, ACKs must follow order; out-of-order ACKs can transiently fail and trigger redelivery.
- DLQ + ordering has best-effort exceptions when messages are forwarded.

Do not enable ordering for every message if the application does not need per-key order; it can reduce throughput and allow one poison message to stall later messages.

## 11. Hands-on A — Observing ack deadlines with gcloud

**Create and run only in a sandbox project**; never use a shared topic with production consumers.

### 11.1. Create topic and pull subscription

~~~bash
gcloud auth list
gcloud config get-value project

gcloud pubsub topics create orders-ack-lab \
  --project=PROJECT_ID

gcloud pubsub subscriptions create orders-ack-sub \
  --project=PROJECT_ID \
  --topic=orders-ack-lab \
  --ack-deadline=30

gcloud pubsub subscriptions describe orders-ack-sub \
  --project=PROJECT_ID
~~~

Verify the resulting `ackDeadlineSeconds`. If the name already exists, verify ownership; do not delete someone else's resources for a lab.

### 11.2. Publish and pull without auto-ack

~~~bash
gcloud pubsub topics publish orders-ack-lab \
  --project=PROJECT_ID \
  --message='{"eventId":"evt-001","orderId":"OD-42"}'

gcloud pubsub subscriptions pull orders-ack-sub \
  --project=PROJECT_ID \
  --limit=1
~~~

Note `MESSAGE_ID` and `ACK_ID` from the output. Subsequent commands use the **actual ACK_ID of the delivery** before it expires if you want to act on the current delivery.

**Manual ack:**

~~~bash
gcloud pubsub subscriptions ack orders-ack-sub \
  --project=PROJECT_ID \
  --ack-ids=ACK_ID
~~~

**Extend delivery by 120 seconds:**

~~~bash
gcloud pubsub subscriptions modify-message-ack-deadline orders-ack-sub \
  --project=PROJECT_ID \
  --ack-ids=ACK_ID \
  --ack-deadline=120
~~~

**Nack / request retry:**

~~~bash
gcloud pubsub subscriptions modify-message-ack-deadline orders-ack-sub \
  --project=PROJECT_ID \
  --ack-ids=ACK_ID \
  --ack-deadline=0
~~~

Try four runs with **separate messages**: ack promptly; let the deadline expire; extend first then ack; nack immediately. Track `messageId`, each `ackId`, and redelivery timing. Do not use `--auto-ack` when observing retries because it acks immediately on pull.

## 12. Hands-on B — Retry backoff and dead-lettering

### 12.1. Configure exponential backoff

~~~bash
gcloud pubsub subscriptions update orders-ack-sub \
  --project=PROJECT_ID \
  --min-retry-delay=10s \
  --max-retry-delay=60s

gcloud pubsub subscriptions describe orders-ack-sub \
  --project=PROJECT_ID
~~~

When nacked, Pub/Sub can apply backoff within the configured bounds. Do not write tests expecting redelivery at an exact fixed second.

### 12.2. Create a DLQ and a subscription for the DLQ

~~~bash
gcloud pubsub topics create orders-ack-dlq \
  --project=PROJECT_ID

gcloud pubsub subscriptions create orders-ack-dlq-sub \
  --project=PROJECT_ID \
  --topic=orders-ack-dlq

gcloud pubsub subscriptions update orders-ack-sub \
  --project=PROJECT_ID \
  --dead-letter-topic=projects/PROJECT_ID/topics/orders-ack-dlq \
  --max-delivery-attempts=5
~~~

Retrieve the **project number**:

~~~bash
gcloud projects describe PROJECT_ID \
  --format="value(projectNumber)"
~~~

Grant roles to the Pub/Sub **service agent of the source subscription's project**; substitute the actual `PROJECT_NUMBER` (not the Java runtime service account):

~~~bash
gcloud pubsub topics add-iam-policy-binding orders-ack-dlq \
  --project=PROJECT_ID \
  --member="serviceAccount:service-PROJECT_NUMBER@gcp-sa-pubsub.iam.gserviceaccount.com" \
  --role="roles/pubsub.publisher"

gcloud pubsub subscriptions add-iam-policy-binding orders-ack-sub \
  --project=PROJECT_ID \
  --member="serviceAccount:service-PROJECT_NUMBER@gcp-sa-pubsub.iam.gserviceaccount.com" \
  --role="roles/pubsub.subscriber"
~~~

Once IAM takes effect, test a **poison message** with the demo subscriber to observe nacks, attempts, and eventual DLQ forwarding. **The count of 5 attempts is a best-effort threshold**, not guaranteed to always be exactly five.

### 12.3. Cleanup after lab

**Delete only lab resources you created that have no active consumers:**

~~~bash
gcloud pubsub subscriptions delete orders-ack-sub --project=PROJECT_ID
gcloud pubsub subscriptions delete orders-ack-dlq-sub --project=PROJECT_ID
gcloud pubsub topics delete orders-ack-lab --project=PROJECT_ID
gcloud pubsub topics delete orders-ack-dlq --project=PROJECT_ID
~~~

Deleting a subscription can discard backlog that cannot be recovered via normal paths; confirm before cleaning up.

## 13. Monitoring and diagnosing redelivery

| Signal | Metric / source | Interpretation |
|---|---|---|
| Backlog by region | `subscription/num_unacked_messages_by_region` | Processing cannot keep up with publish rate, or workers are failing |
| Oldest message age | `subscription/oldest_unacked_message_age_by_region` | Possible stuck poison message/insufficient capacity |
| Pull ack deadline expired | `subscription/expired_ack_deadlines_count` | Deadline/lease/flow-control settings are poorly tuned |
| Push HTTP errors | `subscription/push_request_count` by response code | Timeout, 401/403, 429, or 5xx |
| Delivery latency health | `subscription/delivery_latency_health_score` | Overall delivery health overview |
| DLQ forwarding | `subscription/dead_letter_message_count` | Failing messages moved off the main subscription |
| Java processing time | p50/p95/p99 via app metrics | Basis for choosing deadline/lease |
| DB errors and dedup hits | Logs/tracing/DB metrics | Find downstream bottlenecks and business duplicates |
| Cost and storage | Cloud Billing | Retries, backlog, retention, and compute |

Prefer metrics with the **`_by_region`** suffix when building dashboards resilient to single-region outages. Backlog rising together with oldest age → processing throughput is usually insufficient; small backlog with rising oldest age → suspect a poison message.

### 13.1. Troubleshooting table

| Symptom | Possible cause | Check |
|---|---|---|
| Same `messageId` received multiple times | Lease expired, nack, or ack failure | Expired deadlines, subscriber logs |
| Identical payload with different `messageId` | Publisher published duplicates | Business event ID, publisher retries |
| Java OOM | Too many outstanding messages | Flow control, heap, GC, thread pool |
| Duplicate DB writes | Committed before ack without idempotency | Unique constraint, DB transaction/outbox |
| Exactly-once ack returns `INVALID_ARGUMENT` | Stale/expired ack ID | Lease and ack response, newer delivery |
| Push 403 | Push auth service account missing Invoker/wrong audience | Cloud Run IAM and OIDC token |
| Push slow despite healthy Cloud Run | Push backoff or quota | Push error count, retry config |
| DLQ empty despite many nacks | Missing agent IAM or threshold not yet reached | Pub/Sub service agent, DLQ config |
| Ordering key stuck | Earlier event with same key unacked | Delivery attempts, DLQ, key-specific logs |
| Backlog lost after a long period | Retention expired/seek/delete | Subscription policy, backup/replay plan |

### 13.2. Short runbook

1. Identify **subscription, messageId/eventId, delivery type, region**.
2. Inspect expired ack deadlines (pull) or push HTTP response classes.
3. Check worker health, CPU/RAM, restarts, processing p99, and DB latency.
4. Compare initial deadline against **lease manager max extension** and **flow control**.
5. Check retry policy, DLQ IAM, and poison messages.
6. Verify/protect durable idempotency **before** replaying backlog.
7. Fix one root cause, test worker crash/DB failure in sandbox, and measure results.
8. Tune capacity/concurrency to downstream limits; update alerts and runbooks.

**Do not "fix" issues by acking before commit, setting a 600-second deadline for every job, or deleting a subscription holding real data.**

## 14. Case study: Orders Worker on GKE and Cloud SQL

**Hypothetical scenario:** A Java worker receives `ORDER_CONFIRMED`, writes to Cloud SQL PostgreSQL, and signals warehouse fulfillment. Normal processing takes 1–4 seconds, but during peak hours p99 climbs to 50–70 seconds. The subscription has a 10-second ack deadline; GKE Pods OOM when pulling too many outstanding messages.

**Why did the failure cascade?** Insufficient lease or overloaded client → redelivery → two workers process the same event → duplicate DB writes due to missing unique constraint → higher DB load → even slower processing → growing backlog and Pub/Sub costs.

**Ordered remediation plan:**

1. Add a stable `eventId`; create a unique constraint on consumer + event.
2. Transactionally write the marker and state, then **commit before ack**; route external side effects via outbox.
3. Enable/configure high-level lease management tuned to p99, with a max processing timeout.
4. Cap outstanding messages, Java concurrency, and the Cloud SQL connection pool.
5. Use exponential backoff retries for transient errors; DLQ for malformed schemas.
6. Verify Pub/Sub service agent IAM for the DLQ; enable metrics/alerts.
7. Run a chaos drill for **crash after DB commit before ack**, verifying redelivery **does not create another order**.
8. If exactly-once is desired, verify regional endpoints/ack responses; keep idempotency.

This is a **system correctness problem**, not something solved merely by adding CPU or raising the ack limit.

## 15. Exercises and self-assessment

### Exercise 1 — Deadline expiration

Subscription deadline is 10 seconds, Java worker runs for 45 seconds without extending; another worker receives the same message. **Is this a Pub/Sub bug?** Name two ways to reduce this occurrence.

**Hint:** No; use automatic lease extension or right-size the deadline and flow control.

### Exercise 2 — Ack ID differs from message ID

Worker A receives `messageId=M42, ackId=A1`; after deadline expiration, Worker B receives `messageId=M42, ackId=B2`. **Which value does B use to ack?** Which key should be logged to identify redelivery?

**Hint:** `B2` is the new ack token; `M42` tracks deliveries of the same message.

### Exercise 3 — Ack before DB commit

Java calls `ack()` before INSERTing the order. The worker crashes after ack but before INSERT. **Can work be lost?** How should the order be changed?

**Hint:** Yes; commit durably before acking.

### Exercise 4 — Nack and hot retry

A message has permanently invalid JSON; the subscriber always nacks, with immediate retry and no DLQ. **What happens to throughput and billing?** Propose guardrails.

**Hint:** A poison loop causes repeated redeliveries and cost; use validation, DLQ, retry backoff, and alerts.

### Exercise 5 — Push and 202 Accepted

A Cloud Run push handler returns `202` and stores data only in RAM for later processing. **Does Pub/Sub consider it acked?** What if the instance is terminated?

**Hint:** Already acked; data can be lost. Return 2xx only after durable enqueue/commit.

### Exercise 6 — Exactly-once

A pull subscription has exactly-once enabled. The worker commits to the DB and crashes before ack; the publisher also sends an equivalent business event with a different message ID. **Can a double charge occur?**

**Hint:** Yes; exactly-once does not guarantee cross-system business transactions—idempotency is required.

### Exercise 7 — Best-effort DLQ

`maxDeliveryAttempts=5`, yet a message appears 6 times before going to DLQ. **Is this a guarantee violation?** Which IAM permissions should be checked if no messages reach the DLQ?

**Hint:** Best effort; the Pub/Sub service agent needs Publisher on the DLQ topic and Subscriber on the source subscription.

### Exercise 8 — Ordering key

A1, A2, A3 share an ordering key. A2 redelivers. **Can A3 redeliver even if already acked?** When is ordering overkill?

### Exercise 9 — Optimizing the worker

A Java worker has 8 threads but pulls 10,000 outstanding messages; p99 processing is 35 seconds, and ack expirations are rising. Recommend **flow control, lease settings, DB tuning, DLQ, idempotency, and metrics**.

### Exercise 10 — Designing a test scenario

Design a test proving an order is processed **business-wise only once** during: (a) worker OOM, (b) ack network failure, (c) duplicate publisher publish, and (d) DLQ replay. List the evidence to collect.

## 16. Pre-production checklist

- [ ] Decided between pull/StreamingPull vs. push based on latency and message volume requirements.
- [ ] Distinguished **ack deadline, retention, and retry backoff**.
- [ ] Initial deadline matches p95/p99, with the high-level lease manager configured/monitored.
- [ ] **Ack after DB commit/durable processing**, never early.
- [ ] Durable idempotency handles both **redelivery and publisher duplication**.
- [ ] Max outstanding messages/bytes, concurrency limits, and DB connection pool limits are set.
- [ ] Retry backoff and push backoff are understood separately, with error alerts.
- [ ] DLQ has a topic, subscriber, service agent IAM, and replay runbook.
- [ ] Delivery attempts are understood as **best effort**, not an absolute N.
- [ ] Exactly-once is applied only to pull, with ack confirmation and regional constraints tested.
- [ ] If ordering is enabled, tested redelivery of subsequent messages sharing a key.
- [ ] Push endpoint has authentication and returns success **after durable enqueue**.
- [ ] Dashboards cover regional backlog, oldest age, expired ack deadlines, push errors, and DLQ.
- [ ] Practiced worker crash, downstream timeout, poison message, duplicate, and replay drills.
- [ ] Estimated costs for Pub/Sub traffic, retention, compute, logs, and redeliveries.
- [ ] Sandbox cleanup targets only lab resources without deleting subscriptions holding needed data.

## 17. Official documentation

Verify current limits, flags, and client versions before deployment:

- [Pub/Sub — Subscription properties](https://docs.cloud.google.com/pubsub/docs/subscription-properties)
- [Pub/Sub — Lease management](https://docs.cloud.google.com/pubsub/docs/lease-management)
- [Pub/Sub — Pull subscriptions](https://docs.cloud.google.com/pubsub/docs/pull-messages)
- [Pub/Sub — Push subscriptions](https://docs.cloud.google.com/pubsub/docs/push)
- [Pub/Sub — Retry policy](https://docs.cloud.google.com/pubsub/docs/subscription-retry-policy)
- [Pub/Sub — Dead-letter topics](https://docs.cloud.google.com/pubsub/docs/dead-letter-topics)
- [Pub/Sub — Exactly-once delivery](https://docs.cloud.google.com/pubsub/docs/exactly-once-delivery)
- [Pub/Sub — Message ordering](https://docs.cloud.google.com/pubsub/docs/ordering)
- [Pub/Sub — Monitoring](https://docs.cloud.google.com/pubsub/docs/monitoring)
- [Pub/Sub — Troubleshooting pull](https://docs.cloud.google.com/pubsub/docs/pull-troubleshooting)
- [Pub/Sub — Troubleshooting push](https://docs.cloud.google.com/pubsub/docs/push-troubleshooting)
- [Google Cloud Pub/Sub Java client library](https://docs.cloud.google.com/java/docs/reference/google-cloud-pubsub/latest/overview)
- [gcloud pubsub subscriptions](https://docs.cloud.google.com/sdk/gcloud/reference/pubsub/subscriptions)
- [Pub/Sub pricing](https://cloud.google.com/pubsub/pricing)

**Key takeaways:** The **ack deadline** is the wait window for acknowledging **one delivery**, not retention. Pull workers can extend leases; push must return HTTP success within the deadline. Unacked/nacked messages can **redeliver**; retry backoff and DLQ help manage failures but **do not replace durable idempotency**. For Java applications processing critical data, the safe order is **durable commit → ack**, monitoring backlog/ack expirations, and rehearsing worker crashes/replays—even when exactly-once delivery is enabled.
