# Exactly-once support scope and business-processing idempotency

## Lesson Objectives

The **SPRING_CLOUD_PROVIDER_INTEGRATION** module practices integrating Spring Boot with managed services from **AWS, Azure, and Google Cloud** using the corresponding Spring Cloud libraries. In messaging systems, a message can be redelivered when a subscriber nacks, misses an ack deadline, or loses connectivity. Applications must distinguish broker delivery guarantees from ensuring a business operation produces side effects strictly once.

Google Cloud Pub/Sub provides **exactly-once delivery** for pull subscriptions. This feature tells the subscriber whether Pub/Sub successfully processed an acknowledgment and prevents redelivery after a confirmed acknowledgment within its supported scope. However, it does not create a distributed transaction across Pub/Sub, databases, and external APIs.

After this lesson, you will be able to:

1. Explain the exact scope of Pub/Sub's exactly-once delivery guarantee.
2. Distinguish redelivery, duplicate delivery, and publishing the same business event twice.
3. Create a pull subscription with exactly-once delivery enabled.
4. Understand regional affinity, ack responses, and latest ack ID requirements.
5. Receive acknowledgment responses using the Java Pub/Sub client.
6. Contrast `PubSubTemplate`'s ack API with the Java client API returning `AckResponse`.
7. Design inbox/idempotency keys to protect side effects in databases and external systems.
8. Test successful acks, uncertain acks, redeliveries, and duplicate publishes.

## 1. What does exactly-once delivery mean?

### 1.1. Guarantees at the Pub/Sub layer

When exactly-once delivery is enabled on a pull subscription, Pub/Sub provides these core semantics:

- Subscribers can determine whether an acknowledgment request succeeded or failed.
- Once Pub/Sub confirms a successful ACK, that message will not be redelivered to the subscription within the supported regional scope.
- While a message remains outstanding and its ack deadline has not expired, Pub/Sub does not redeliver it under exactly-once semantics.
- If a message is redelivered due to a NACK or an expired ack deadline, only the acknowledgment ID from the most recent delivery remains valid for ACKing.

Crucially, **exactly-once delivery is tied to a Pub/Sub message ID on a subscription**, not to the JSON content or business ID your application puts inside the payload.

### 1.2. Types of "duplicates" to distinguish

| Scenario | Message ID | Handled by exactly-once delivery? |
| --- | --- | --- |
| Subscriber NACKs and receives the same message again | Preserves same message ID | Valid redelivery; feature does not suppress NACK retries |
| Ack deadline expires, message is redelivered | Preserves same message ID | Valid redelivery; subscriber must reprocess |
| Pub/Sub redelivers after an ACK was confirmed successful | Same message ID | Prevented within exactly-once and single-region scope |
| Publisher sends the same logical event twice | Two publish operations can get distinct message IDs | Not deduplicated by exactly-once delivery alone |
| Producer retries publish and creates an extra message | Can get a different message ID | Not considered a duplicate delivery; application must deduplicate by event ID |

For example, a producer emits `OrderPaid` with `eventId=evt-1001`, hits an application-layer timeout, and resends it as a new publish request. Pub/Sub treats these as two separate messages. A subscription with exactly-once enabled can still receive both messages because each carries its own message ID.

Therefore, use two layers of defense:

1. Exactly-once delivery to curb redeliveries of the same Pub/Sub message within supported boundaries.
2. Business-layer idempotency to guard against distinct messages representing the same logical event.

## 2. What does exactly-once delivery NOT guarantee?

This feature does not:

- Automatically deduplicate multiple publishes with the same payload on the publisher side.
- Make a database transaction and a Pub/Sub ACK commit atomically together.
- Guarantee an external HTTP API is called only once.
- Prevent retries after a NACK or an expired ack deadline.
- Guarantee exactly-once across multiple regions.
- Support push subscriptions or export subscriptions writing directly to BigQuery/Cloud Storage.
- Replace event IDs, inbox tables, idempotency keys, or transactional outboxes.

For instance, a consumer updates an account balance in a database and then sends an ACK. If the database commits successfully but the ACK hits a network failure, the message can be redelivered. Exactly-once cannot roll back an already-committed database transaction. The consumer must recognize that the event was already applied and avoid deducting funds a second time.

## 3. Supported scope and regional limits

### 3.1. Pull subscriptions only

Exactly-once delivery supports:

- Pull API.
- StreamingPull API.
- High-level subscriber client libraries using Pull/StreamingPull.

Not supported:

- Push subscriptions.
- BigQuery export subscriptions.
- Cloud Storage export subscriptions.
- Other export subscriptions where Pub/Sub pushes data directly to destination services.

The reason is that pull subscribers actively send ACK requests to Pub/Sub and receive responses confirming whether the ACK was processed. With push, a subscriber returns an HTTP response without knowing for sure whether Pub/Sub received and persisted that acknowledgment.

### 3.2. Guarantee applies within a single region only

Pub/Sub's exactly-once guarantee holds only when subscribers connect to Pub/Sub within the **same region**. If consumers for the same subscription run across multiple regions, duplicate deliveries can occur even when the feature is enabled.

When running on Google Cloud within one region, clients normally connect to that region's endpoint. For workloads outside Google Cloud or multi-region deployments, use a locational endpoint to pin subscribers to one specific region.

Example endpoint:

```text
asia-southeast1-pubsub.googleapis.com:443
```

This is an illustrative endpoint for the Singapore region. All subscribers for the subscription must route consistently to the same region if you rely on the exactly-once guarantee.

Publishers may publish from other regions; the regional affinity requirement applies to subscriber connections.

### 3.3. Pull subscriptions and ACK responses

Exactly-once delivery relies on receiving ACK outcomes:

```mermaid
sequenceDiagram
    participant S as Subscriber
    participant P as Pub/Sub
    S->>P: Pull / StreamingPull
    P-->>S: Message + ack ID
    S->>S: Execute business logic
    S->>P: Acknowledge(ack ID)
    P-->>S: ACK response
    alt ACK succeeds
        S->>S: Record completion
        Note over S,P: No redelivery of same message within region
    else ACK fails or outcome unknown
        S->>S: Keep processing state and await outcome/redelivery
        Note over S,P: May redeliver; consumer must be idempotent
    end
```

Do not treat merely invoking `ack()` as proof that Pub/Sub confirmed the ACK. Applications must observe the response/future appropriate to the API in use.

## 4. Enabling exactly-once delivery on a subscription

### 4.1. Creating a pull subscription

Create a new subscription with exactly-once enabled:

```bash
gcloud pubsub subscriptions create orders-exactly-once-sub \
  --topic=orders \
  --enable-exactly-once-delivery
```

To set an explicit initial ack deadline:

```bash
gcloud pubsub subscriptions create orders-exactly-once-sub \
  --topic=orders \
  --enable-exactly-once-delivery \
  --ack-deadline=60
```

When exactly-once is enabled and no ack deadline is specified at creation, the subscription defaults to 60 seconds. High-level clients can automatically extend the deadline during processing; the subscription value is the initial deadline.

### 4.2. Verifying the configuration

```bash
gcloud pubsub subscriptions describe orders-exactly-once-sub
```

Verify `enableExactlyOnceDelivery` is `true`, the subscription uses pull delivery, and it points to the right topic. Grant only the IAM permissions needed to create/manage subscriptions; runtime subscribers need permission to consume from the subscription.

### 4.3. Configuring via Java `SubscriptionAdminClient`

If provisioning resources in Java:

```java
import com.google.cloud.pubsub.v1.SubscriptionAdminClient;
import com.google.pubsub.v1.ProjectSubscriptionName;
import com.google.pubsub.v1.ProjectTopicName;
import com.google.pubsub.v1.Subscription;
import java.io.IOException;

public Subscription createExactlyOnceSubscription(
        String projectId,
        String topicId,
        String subscriptionId) throws IOException {

    ProjectTopicName topicName =
            ProjectTopicName.of(projectId, topicId);
    ProjectSubscriptionName subscriptionName =
            ProjectSubscriptionName.of(projectId, subscriptionId);

    Subscription subscription = Subscription.newBuilder()
            .setName(subscriptionName.toString())
            .setTopic(topicName.toString())
            .setEnableExactlyOnceDelivery(true)
            .setAckDeadlineSeconds(60)
            .build();

    try (SubscriptionAdminClient adminClient =
                 SubscriptionAdminClient.create()) {
        return adminClient.createSubscription(subscription);
    }
}
```

This example uses the runtime environment's Application Default Credentials. In production, subscriptions are usually provisioned with Terraform or infrastructure pipelines so IAM, retention, retry policies, and exactly-once settings live in one configuration.

## 5. Receiving ACK responses with the Java Pub/Sub client

### 5.1. Why are acknowledgment responses needed?

When exactly-once is enabled, the subscriber needs to know whether the server processed an ACK request successfully:

- `SUCCESSFUL`: ACK confirmed; the same message will not be redelivered within guarantee bounds.
- `INVALID`: ack ID is invalid or expired; do not retry the old ack ID.
- `PERMISSION_DENIED`: principal lacks ACK permission.
- `FAILED_PRECONDITION`: subscription state or request fails preconditions.
- `OTHER`: another error; inspect the cause and client retry policy.

The Java client provides:

- `MessageReceiverWithAckResponse`
- `AckReplyConsumerWithResponse`
- `AckResponse`

`AckReplyConsumerWithResponse.ack()` returns `Future<AckResponse>` so the application can read the outcome from Pub/Sub.

`AckReplyConsumerWithResponse` is currently marked **Beta/Pre-GA** in the Java API reference. Review support terms and library versions before making it a hard dependency in production systems.

Current Pub/Sub documentation recommends Java client library version `1.139.0` or higher for best exactly-once performance and support. With Spring Boot, verify the actual `google-cloud-pubsub` version resolved by your BOM; do not bump a single dependency manually if doing so breaks alignment with the versions tested by Spring Framework on Google Cloud.

### 5.2. Example subscriber reading ACK responses

```java
import com.google.cloud.pubsub.v1.AckReplyConsumerWithResponse;
import com.google.cloud.pubsub.v1.AckResponse;
import com.google.cloud.pubsub.v1.MessageReceiverWithAckResponse;
import com.google.cloud.pubsub.v1.Subscriber;
import com.google.pubsub.v1.ProjectSubscriptionName;
import com.google.pubsub.v1.PubsubMessage;
import java.time.Duration;
import java.util.concurrent.Future;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class ExactlyOnceSubscriber {
    private final OrderProcessor orderProcessor;
    private final ProcessingRegistry processingRegistry;

    public ExactlyOnceSubscriber(
            OrderProcessor orderProcessor,
            ProcessingRegistry processingRegistry) {
        this.orderProcessor = orderProcessor;
        this.processingRegistry = processingRegistry;
    }

    public Subscriber start(String projectId, String subscriptionId) {
        ProjectSubscriptionName subscriptionName =
                ProjectSubscriptionName.of(projectId, subscriptionId);

        MessageReceiverWithAckResponse receiver =
                (PubsubMessage message,
                 AckReplyConsumerWithResponse ackConsumer) -> {
                    String eventId = message.getAttributesOrDefault(
                            "eventId", "missing-event-id");

                    try {
                        orderProcessor.processIdempotently(message);
                    } catch (Exception processingError) {
                        // Only NACK when business processing fails before sending ACK.
                        try {
                            AckResponse nackResponse = ackConsumer.nack()
                                    .get(15, TimeUnit.SECONDS);
                            processingRegistry.markProcessingFailed(
                                    eventId,
                                    processingError.getClass().getSimpleName()
                                            + ":" + nackResponse.name());
                        } catch (InterruptedException interrupted) {
                            Thread.currentThread().interrupt();
                            processingRegistry.markProcessingFailed(
                                    eventId, "NACK_UNCERTAIN");
                        } catch (ExecutionException | TimeoutException nackError) {
                            processingRegistry.markProcessingFailed(
                                    eventId, "NACK_UNCERTAIN");
                        }
                        return;
                    }

                    // Send ACK only after the business transaction commits.
                    Future<AckResponse> ackFuture = ackConsumer.ack();
                    try {
                        AckResponse response =
                                ackFuture.get(15, TimeUnit.SECONDS);
                        if (response == AckResponse.SUCCESSFUL) {
                            processingRegistry.markAckConfirmed(eventId);
                        } else {
                            processingRegistry.markAckUnconfirmed(
                                    eventId, response.name());
                        }
                    } catch (InterruptedException interrupted) {
                        Thread.currentThread().interrupt();
                        processingRegistry.markAckUncertain(eventId);
                    } catch (ExecutionException | TimeoutException ackError) {
                        // Server may have processed ACK; never send NACK after ACK.
                        // If redelivered, inbox/idempotency prevents duplicate side effects.
                        processingRegistry.markAckUncertain(eventId);
                    }
                };

        Subscriber subscriber = Subscriber.newBuilder(
                        subscriptionName, receiver)
                .setEndpoint("asia-southeast1-pubsub.googleapis.com:443")
                .setMinDurationPerAckExtensionDuration(
                        Duration.ofSeconds(60))
                .setMaxDurationPerAckExtensionDuration(
                        Duration.ofSeconds(120))
                .setMaxAckExtensionPeriodDuration(
                        Duration.ofMinutes(10))
                .build();

        subscriber.startAsync().awaitRunning();
        return subscriber;
    }
}
```

`OrderProcessor` and `ProcessingRegistry` are business services you implement. This example uses the direct subscriber client to obtain `AckResponse`; it is not a standard `PubSubTemplate.subscribe()` callback.

`OrderProcessor.processIdempotently()` must deserialize the message, write the inbox record, and commit side effects in a single transaction before returning. `ProcessingRegistry` in this example only tracks operational/ACK status for observability; it does not replace the inbox transaction. `Subscriber` callbacks can execute concurrently on multiple threads, so services and registries must be thread-safe.

In production code:

- Do not block callbacks indefinitely; set an appropriate timeout on the ACK future.
- If the ACK outcome is unknown, keep processing state durable and rely on idempotency upon redelivery.
- Never send a NACK after already sending an ACK just because the ACK future timed out; the original request may have succeeded.
- NACK only when business processing fails prior to sending the ACK.
- Stop `Subscriber` gracefully when the Spring context shuts down.

Hold the `Subscriber` instance in a bean/component and call `stopAsync()` when the Spring context closes. Never spin up a new subscriber per message or per HTTP request.

### 5.3. Lease extensions and ack IDs

The Java high-level subscriber automatically extends ack deadlines while callbacks are running. With exactly-once, avoid letting ack IDs expire due to network hiccups or missed client extensions:

```java
Subscriber subscriber = Subscriber.newBuilder(subscriptionName, receiver)
        .setEndpoint("asia-southeast1-pubsub.googleapis.com:443")
        .setMinDurationPerAckExtensionDuration(Duration.ofSeconds(60))
        .setMaxDurationPerAckExtensionDuration(Duration.ofSeconds(120))
        .setMaxAckExtensionPeriodDuration(Duration.ofMinutes(10))
        .build();
```

These values are examples. `minDurationPerAckExtension` and `maxDurationPerAckExtension` range from 0 to 600 seconds. Pick values large enough to tolerate network jitter without expiring, yet avoid setting them arbitrarily high, which delays redelivery if a worker dies.

When exactly-once is enabled, an ACK or `ModifyAckDeadline` using an expired ack ID can return `INVALID_ARGUMENT`. If a message has been redelivered, only the ack ID from the latest delivery is valid.

## 6. Using exactly-once in Spring Boot applications

### 6.1. Provision subscriptions via infrastructure, process messages with Spring

The Spring Boot starter provides `PubSubTemplate` for publish, subscribe, and pull:

```xml
<dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>spring-cloud-gcp-starter-pubsub</artifactId>
</dependency>
```

Use a Spring Framework on Google Cloud BOM compatible with your Spring Boot version. Do not pin `google-cloud-pubsub` independently when the BOM already manages it.

An exactly-once subscription is a Pub/Sub resource setting, not an annotation on `@Service`. Create the subscription with Terraform, `gcloud`, or `SubscriptionAdminClient`, then connect the Spring consumer to it.

### 6.2. `PubSubTemplate` and acknowledgment futures

`PubSubTemplate.subscribe()` delivers messages to callbacks as `BasicAcknowledgeablePubsubMessage`. The Spring wrapper's `ack()` and `nack()` methods return `CompletableFuture<Void>`. This lets applications observe asynchronous completion, though the return type does not expose `AckResponse` enum values like `SUCCESSFUL`, `INVALID`, or `PERMISSION_DENIED`.

If your application must classify the exact server ACK response, use the Java client with `MessageReceiverWithAckResponse` and `AckReplyConsumerWithResponse` as shown earlier. Never assume every `message.ack()` call was confirmed by Pub/Sub merely because execution passed that line.

Typical Spring handler example:

```java
pubSubTemplate.subscribe("orders-exactly-once-sub", message -> {
    String payload = message.getPubsubMessage()
            .getData()
            .toStringUtf8();

    try {
        orderService.processIdempotently(payload);
        message.ack().whenComplete((unused, error) -> {
            if (error != null) {
                // Record ACK failure/uncertain; do not repeat side effects.
            }
        });
    } catch (Exception error) {
        message.nack();
    }
});
```

`PubSubTemplate` remains suitable for most Spring integrations. When operational requirements strictly demand persisting `AckResponse.SUCCESSFUL` or distinguishing expired ack IDs, drop down to the lower-level subscriber API and verify library version compatibility.

### 6.3. Connecting subscribers to a single region

When using the Java `Subscriber` directly, set a locational endpoint on the builder:

```java
Subscriber subscriber = Subscriber.newBuilder(
                subscriptionName, receiverWithResponse)
        .setEndpoint("asia-southeast1-pubsub.googleapis.com:443")
        .build();
```

If deploying Spring Boot across multiple zones/regions, ensure every instance consuming the same subscription targets the same regional endpoint. An autoscaling group spanning two regions does not satisfy regional affinity merely because the subscription has exactly-once enabled.

### 6.4. Watch out for Spring Integration ack modes

If using `PubSubInboundChannelAdapter`, the `AUTO`, `AUTO_ACK`, and `MANUAL` modes govern when Spring Integration invokes ack/nack. They do not replace checking the server ACK response.

For business flows requiring tight control:

- Choose manual acknowledgment so messages are not acked before transactions commit.
- Retrieve `BasicAcknowledgeablePubsubMessage` from `GcpPubSubHeaders.ORIGINAL_MESSAGE`.
- Persist business outcomes before acking.
- Observe Spring's ack future; if a specific `AckResponse` is required, use the native Java subscriber API.

## 7. Idempotency with an inbox/idempotency table

### 7.1. Use a business event ID

Producers should generate a stable `eventId` before publishing:

```json
{
  "eventId": "evt-01J9A7K2",
  "eventType": "OrderPaid",
  "orderId": "ord-1001",
  "schemaVersion": 1
}
```

If a publisher retries the same event, it must reuse the exact same `eventId`. Never use Pub/Sub's `messageId` as a business deduplication key because two publish operations for the same logical event can receive two distinct message IDs.

An idempotency key typically combines `consumerName + eventId`, because two different consumers may legitimately process the same event for separate purposes.

### 7.2. Creating an inbox table

PostgreSQL example:

```sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(120) NOT NULL,
    event_id VARCHAR(160) NOT NULL,
    pubsub_message_id VARCHAR(160),
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (consumer_name, event_id)
);
```

`processed_events` serves as the inbox/deduplication registry. Its unique key prevents the same consumer from applying the same logical event more than once, whether caused by Pub/Sub redelivery or duplicate producer publishes.

### 7.3. Writing the inbox record and side effects in one transaction

Example:

```java
@Transactional
public void processIdempotently(OrderPaid event, String pubsubMessageId) {
    int inserted = jdbcTemplate.update("""
            INSERT INTO processed_events(
                consumer_name, event_id, pubsub_message_id
            )
            VALUES (?, ?, ?)
            ON CONFLICT DO NOTHING
            """,
            "billing-projection",
            event.eventId(),
            pubsubMessageId
    );

    if (inserted == 0) {
        // Event already applied; skip repeating side effects.
        return;
    }

    orderRepository.markPaid(event.orderId());
    accountRepository.recordPayment(event.orderId(), event.amount());
}
```

The inbox insert and business updates must belong to the same database transaction:

- If the transaction rolls back, both the inbox row and side effects roll back; the message can be retried.
- If the transaction commits, the event is recorded as processed alongside its side effects.
- If the subsequent ACK fails and the message redelivers, the next attempt sees the inbox row and skips side effects.

Never insert the inbox row in a separate transaction before side effects. If the process crashes between the two transactions, the event can appear completed even though business state was never updated.

### 7.4. Processing sequence

Recommended flow:

```text
Receive message
    ↓
Read eventId and validate
    ↓
Transaction:
  insert inbox if absent
  update business state
  commit
    ↓
Send ACK and inspect outcome
    ↓
If ACK uncertain: wait for redelivery, inbox blocks duplicate side effects
```

If the event already exists in the inbox, skip reapplying updates. Still send an ACK for the current delivery so the message stops retrying.

### 7.5. Storing status for multi-step workflows

For multi-step workflows, a single `processed_at` timestamp may not suffice. Use explicit states such as:

| Status | Meaning |
| --- | --- |
| `RECEIVED` | Event recorded |
| `PROCESSING` | Workflow in progress |
| `COMPLETED` | All required side effects completed |
| `RETRYABLE_FAILED` | Transient failure, eligible to resume |
| `PERMANENT_FAILED` | Error requiring intervention or quarantine |

If a workflow runs for a long time, do not hold a Pub/Sub message outstanding for many minutes or hours. Persist durable job state, ack the initiating event once the job is saved, and let a dedicated worker/workflow continue.

## 8. Exactly-once with external APIs and services

### 8.1. Database transactions do not span HTTP APIs

Suppose a consumer must:

1. Update an order in PostgreSQL.
2. Call a payment provider to capture funds.
3. Send a confirmation email.
4. ACK Pub/Sub.

No single ACID transaction covers PostgreSQL, an HTTP payment API, an email provider, and Pub/Sub together. If the payment API succeeds but the response times out, the consumer cannot tell whether funds were captured. Blindly retrying risks capturing twice.

Exactly-once delivery cannot bridge this transaction boundary.

### 8.2. Use idempotency keys on downstream APIs

When a downstream API supports idempotency, send the exact same key on every retry of the same event:

```http
POST /payments/capture
Idempotency-Key: evt-01J9A7K2
Content-Type: application/json
```

The downstream service must persist the key and result in the same transaction as its side effect. When receiving the same key again, it returns the prior result instead of capturing funds a second time.

Never generate a fresh key on each retry. Use the stable event ID created by the producer.

### 8.3. Use a transactional outbox for follow-up events

If a consumer updates a database and must emit a subsequent event, write an outbox row in the same transaction:

```sql
CREATE TABLE outbox_events (
    event_id VARCHAR(160) PRIMARY KEY,
    event_type VARCHAR(120) NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at TIMESTAMPTZ
);
```

Business transaction:

```java
@Transactional
public void markOrderPaid(OrderPaid event) {
    orderRepository.markPaid(event.orderId());
    outboxRepository.insert(
            event.eventId(),
            "OrderPaymentRecorded",
            serialize(event)
    );
}
```

An outbox worker publishes unsent rows to Pub/Sub and marks them sent. If the worker crashes after publishing but before updating `published_at`, the event may be republished. Downstream consumers still require an inbox/idempotency check on `eventId`.

An outbox makes database updates and publish intent atomic; it does not make publishing strictly once-only. Pairing an outbox with idempotent consumers produces a resilient end-to-end flow.

### 8.4. When downstream systems lack idempotency support

If an external API has no idempotency key, there is no universal way to guarantee a single side effect across an ambiguous network timeout. Options include:

- Build an internal adapter layer with request IDs and a deduplication registry.
- Use workflow state to reconcile outcomes before retrying.
- Query transaction status via a lookup API before reissuing commands.
- Apply compensation/reconciliation when outcomes cannot be confirmed.
- Accept at-least-once semantics and design repairable/reconcilable side effects.

Never claim exactly-once business effects if the target system cannot identify or deduplicate repeated requests.

## 9. Failure matrix: when can a message be reprocessed?

| Failure point | Business state | ACK state | What to do |
| --- | --- | --- | --- |
| Crash before transaction | Uncommitted | Unacked | Pub/Sub redelivers; process normally |
| Transaction rollback | Uncommitted | Unacked/un-nacked | Retry per policy |
| Commit succeeds, crash before ACK | Committed | Unacked | Redelivery may occur; inbox skips side effects and ACKs |
| ACK sent but response times out | Committed | Unknown | Keep state; skip repeating side effects; if redelivered, deduplicate and ACK |
| ACK response `SUCCESSFUL` | Committed | Confirmed | Pub/Sub does not redeliver the same message within region |
| ACK response `INVALID` | Possibly committed | Ack ID expired/invalid | Do not retry old ack ID; process new delivery idempotently |
| Producer publishes same event twice | Same event ID, two publishes | Separate delivery states | Inbox deduplicates by event ID |
| Consumer runs in another region | Possibly committed | Regional guarantee inapplicable | Pin subscribers to one region or enforce strong deduplication |
| Seek/replay subscription | Event may already be processed | Intentionally redelivered | Keep inbox records across the replay window |

### 9.1. How long should inbox records be kept?

Idempotency record retention must exceed the longest window in which a message could reappear:

- Subscription retention.
- Dead-letter retention and operational investigation time.
- Manual re-drive turnaround.
- Snapshot/seek replay window.
- Publisher retry or replay horizon.

If inbox rows are purged too early, a replayed message can re-trigger side effects. For financial events or irreversible state transitions, retain business keys long-term or maintain a ledger per data retention policies.

### 9.2. Event IDs must originate at the producer

An Event ID should be:

- Unique within the business domain.
- Stable across publish retries of the same event.
- Independent of Pub/Sub's message ID.
- Namespaced by producer/event type if multiple systems emit events.
- Free of sensitive data or PII.

Never generate a fresh UUID in the subscriber for each delivery; doing so destroys deduplication.

## 10. Combining ordering with exactly-once

Pub/Sub supports message ordering alongside exactly-once delivery. However, when combining both:

- ACKs must be sent in message order within the same ordering key.
- Out-of-order ACKs may be rejected with transient errors.
- If the deadline expires before a valid ordered ACK arrives, messages can redeliver.
- Throughput per ordering key is capped in the thousands of messages per second.

When ordering is required, design callbacks so later messages for a key are never ACKed ahead of earlier ones. Never dispatch messages to an unbounded executor and ACK in arbitrary completion order.

Seek/replay intentionally resets acknowledgment states. Messages redelivered after a seek are valid redeliveries even on exactly-once subscriptions. Therefore, inbox/idempotency remains essential for replay flows.

## 11. Metrics, quotas, and troubleshooting

### 11.1. Key metrics

| Metric | Meaning | How to use |
| --- | --- | --- |
| `subscription/exactly_once_warning_count` | Events that may trigger redelivery due to failed ACK/ModifyAckDeadline | Spot expired ack IDs, request errors, or service persistence issues |
| `subscription/expired_ack_deadlines_count` | Count of ack deadline expirations | Inspect slow subscribers or lease extensions |
| `service.serviceruntime.googleapis.com/api/request_count` | API requests and response codes | Diagnose ACK/ModifyAckDeadline API errors |
| `subscription/num_unacked_messages_by_region` | Unacknowledged message count | Track backlog |
| `subscription/oldest_unacked_message_age_by_region` | Age of oldest unacknowledged message | Spot lagging subscribers |

`exactly_once_warning_count` can rise from either client or server issues and can be noisy. Repeatedly sending an invalid ack ID increments the metric multiple times even if not every error causes an actual redelivery.

### 11.2. Quotas and latency

Exactly-once subscriptions carry additional regional quotas, including:

- Messages consumed from exactly-once subscriptions.
- Messages ACKed or deadline-extended on those subscriptions.

Exactly-once also adds higher publish-to-subscribe latency than standard subscriptions. If high throughput is a primary requirement, use StreamingPull and benchmark realistically before enabling it across all workloads.

### 11.3. Diagnosing ACK errors

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| `INVALID_ARGUMENT` on ACK | Ack ID expired or not the latest delivery ID | Stop retrying old ID; wait for new delivery and use new ID |
| `PERMISSION_DENIED` | Subscriber lacks `roles/pubsub.subscriber` | Check principal and IAM bindings on the subscription |
| `exactly_once_warning_count` rising | Failed ACK/ModifyAckDeadline calls or invalid ack IDs | Cross-check response codes, expired deadlines, and client logs |
| Redelivery after ACK timeout | Server may have missed ACK or response was lost | Rely on inbox; never repeat side effects |
| Duplicates with different message IDs | Producer published the same event multiple times | Deduplicate by event ID |
| Duplicates when subscribers span regions | Regional guarantee does not apply | Route all subscribers to one region |
| Throughput drops after enabling exactly-once | Higher latency/quotas, ACK ordering, or flow control | Use StreamingPull, check quotas, and measure ack latency |
| Out-of-order ACKs with ordering keys | Callbacks finish out of order | Serialize processing/ACKs per key |

### 11.4. Do not retry permanent errors

The Java client automatically retries some transient errors. Errors caused by an invalid ack ID cannot be fixed by resending the same ID. Classify failures:

- Transient errors: let the client retry per policy.
- Expired/invalid ack ID: stop retrying the old ID; await redelivery.
- Permission denied: fix IAM bindings.
- Failed precondition: check subscription state and request parameters.
- Uncertain timeout: record uncertain state and rely on idempotency.

## 12. Testing exactly-once and idempotency

### 12.1. Unit testing the inbox

Test the business handler and inbox independently:

1. A new event inserts into the inbox and updates business state.
2. Reprocessing the same `eventId` skips repeating the business update.
3. Mid-transaction errors roll back both the inbox row and business update.
4. Two concurrent workers processing the same event let the unique constraint allow only one transaction to apply side effects.
5. Distinct event IDs with identical payloads are treated as separate events unless business rules dictate otherwise.

Use a real database or Testcontainers to verify unique constraints and transaction isolation. Mocking repositories alone does not prove concurrency or deduplication works properly.

### 12.2. Integration testing with the Pub/Sub emulator

The emulator is helpful for core flows:

- Creating topics/subscriptions and publishing messages.
- Reading payloads, attributes, and message IDs.
- Testing ack/nack and callback behavior.
- Testing application inbox/idempotency logic.

Never treat emulator results as proof that production exactly-once server guarantees, regional affinity, quotas, or ACK responses are verified. Test those semantics against real Pub/Sub in a sandbox project.

### 12.3. Cloud sandbox tests

Create a pull subscription with exactly-once enabled:

```bash
gcloud pubsub topics create exactly-once-lab

gcloud pubsub subscriptions create exactly-once-lab-sub \
  --topic=exactly-once-lab \
  --enable-exactly-once-delivery \
  --ack-deadline=60
```

Test cases:

| Test case | How to run | What to verify |
| --- | --- | --- |
| ACK succeeds | Receive message and wait for `AckResponse.SUCCESSFUL` | Same message ID is not redelivered |
| NACK | Receive message, then NACK | Message may redeliver; message ID stays the same |
| ACK response timeout | Process business logic, send ACK, then drop/timeout response in test client | Uncertain state recorded; inbox prevents duplicate side effects |
| Expired ack ID | Let deadline expire, receive new delivery, then attempt ACK with old ID | Old request rejected; use new ID from current delivery |
| Duplicate event publish | Publish twice with same `eventId` in two publish calls | May receive two Pub/Sub message IDs; business side effect occurs once |
| Cross-region subscriber | Connect subscribers to endpoints in different regions | Do not rely on cross-region exactly-once guarantees |
| Ordering + exactly-once | Send multiple messages with same key, ACK out of order | Observe transient ACK errors/redeliveries; fix consumer to ACK sequentially |
| Seek/replay | Seek subscription to a snapshot or timestamp | Messages intentionally replay; inbox blocks duplicate side effects |

### 12.4. Verifying permissions and configuration

- Subscriber holds `roles/pubsub.subscriber` on the subscription.
- Subscription has `enableExactlyOnceDelivery=true`.
- All subscribers use the same locational endpoint.
- Subscription is pull, not push/export.
- Client library is managed by a compatible BOM; for Java, use a client library version recommended in current Google documentation.
- Monitor `exactly_once_warning_count`, `expired_ack_deadlines_count`, and ACK/ModifyAckDeadline response codes.

## 13. Hands-on exercise

An e-commerce system receives `PaymentCaptured` events on topic `payments`. The `ledger-service` consumer writes transactions to PostgreSQL and emits `LedgerEntryCreated` events for a reporting service.

### Requirements

1. Create pull subscription `ledger-exactly-once-sub` with exactly-once delivery enabled.
2. Configure the consumer to run in a single region using the matching locational endpoint.
3. Create a `PaymentCaptured` record with `eventId`, `paymentId`, `orderId`, `amount`, `currency`, and `occurredAt`.
4. Define an inbox table with a unique key on `(consumer_name, event_id)`.
5. Write both the inbox record and ledger entry in the same database transaction.
6. Use Java `MessageReceiverWithAckResponse` to receive `AckResponse`.
7. Mark ACK confirmed only when the response is `SUCCESSFUL`.
8. If ACK times out or the outcome is uncertain, never repeat the ledger entry; await redelivery and rely on the inbox.
9. Write the `LedgerEntryCreated` outbox event in the same transaction as the ledger entry.
10. Implement an outbox publisher with retries that preserves the event ID.
11. Test duplicate event publishes, ACK timeouts, redeliveries, expired ack IDs, and cross-region subscribers.
12. Build a dashboard for exactly-once warnings, expired deadlines, backlog, and business processing.

### Evaluation matrix

| Scenario | Expected result |
| --- | --- |
| New event | One ledger entry and one inbox record |
| Same event ID redelivered | No second ledger entry created |
| Producer publishes same event twice | Two messages may arrive; only one side effect occurs |
| ACK succeeds | Server confirms; message does not redeliver within region |
| Uncertain ACK response | Redelivery may occur; inbox prevents duplicate side effects |
| Database transaction rolls back | No partial inbox record or ledger entry |
| Outbox worker republishes | Reporting consumer deduplicates by event ID |
| Subscriber in another region | Does not rely on the exactly-once guarantee |
| Seek replay | Event replays at delivery layer without duplicating side effects |

### Completion criteria

- Explains the pull-only and single-region scope of Pub/Sub exactly-once.
- Distinguishes Pub/Sub message IDs from business event IDs.
- Reads and classifies ACK responses.
- Implements an atomic inbox/idempotency transaction.
- Implements an outbox for downstream follow-up events.
- Includes sandbox tests for redelivery, duplicate publish, and ack uncertainty.

## 14. Comparison with AWS and Azure

| Aspect | Google Cloud Pub/Sub | AWS | Azure |
| --- | --- | --- | --- |
| Delivery guarantee | Exactly-once delivery for pull subscriptions within one region | SQS FIFO offers deduplication and ordering; Standard is at-least-once | Service Bus offers MessageId-based duplicate detection within a configured window |
| Confirmation | ACK response via pull client | DeleteMessage/visibility timeout; FIFO dedup does not replace business transactions | Complete/Abandon and message locks |
| Business event deduplication | Inbox/idempotency by event ID | Consumer idempotency by MessageDeduplicationId/business key | MessageId duplicate detection plus consumer idempotency |
| Ordering | Ordering keys; ACKs must follow order when combined with exactly-once | FIFO MessageGroupId | Service Bus SessionId |
| Replay | Snapshots/seek; seek can trigger intentional redelivery | DLQ redrive or event archive | DLQ resubmit or event archive |
| Scope | Subscribers must share one region | Per queue/region and FIFO semantics | Per entity/namespace and service configuration |

Never map Pub/Sub's exactly-once into a generic cross-cloud property for all messaging services. SQS FIFO deduplication and Service Bus duplicate detection have their own windows and scopes; none of them create an exactly-once transaction between the broker and your application database.

## Summary

Google Cloud Pub/Sub exactly-once delivery prevents redelivery of the same Pub/Sub message after a confirmed ACK, within a single region and strictly for pull/StreamingPull subscriptions. NACKs, expired ack deadlines, and seeks can still cause redeliveries. Two separate publish calls for the same business event can also yield distinct message IDs, which exactly-once does not deduplicate.

Consequently, Spring Boot consumers still need stable event IDs, an inbox/idempotency table, and transactions covering both processing markers and database side effects. For external APIs, use target-side idempotency keys or reconcilable workflows/outboxes. When exact server ACK confirmation is needed, Java's `MessageReceiverWithAckResponse` exposes `AckResponse`, whereas `PubSubTemplate`'s standard API returns a `Void` future without that enum.

Exactly-once is a useful delivery safeguard, while business-layer idempotency and transactions ultimately protect data integrity across process crashes, uncertain ACK responses, publisher retries, and event replays.

## References

- [Google Cloud Pub/Sub — Exactly-once delivery](https://docs.cloud.google.com/pubsub/docs/exactly-once-delivery) — pull/region scope, ACK responses, ack IDs, quotas, and ordering limits.
- [Google Cloud Pub/Sub — Subscribe with exactly-once delivery](https://docs.cloud.google.com/pubsub/docs/samples/pubsub-subscriber-exactly-once) — Java examples for `MessageReceiverWithAckResponse` and `AckReplyConsumerWithResponse`.
- [Java AckReplyConsumerWithResponse API](https://docs.cloud.google.com/java/docs/reference/google-cloud-pubsub/latest/com.google.pubsub.v1.AckReplyConsumerWithResponse) — ACK/NACK futures and server responses.
- [Java MessageReceiverWithAckResponse API](https://docs.cloud.google.com/java/docs/reference/google-cloud-pubsub/latest/com.google.pubsub.v1.MessageReceiverWithAckResponse) — message callback with acknowledgment response.
- [Java Subscriber.Builder API](https://docs.cloud.google.com/java/docs/reference/google-cloud-pubsub/latest/com.google.pubsub.v1.Subscriber.Builder) — endpoints, lease extensions, and subscriber settings.
- [Spring Framework on Google Cloud — Pub/Sub](https://googlecloudplatform.github.io/spring-cloud-gcp/reference/html/pubsub.html) — `PubSubTemplate`, acknowledgment futures, and subscriber integration.
- [Google Cloud Pub/Sub — Pull subscriptions](https://docs.cloud.google.com/pubsub/docs/pull) — Pull/StreamingPull and high-level clients.
- [Google Cloud Pub/Sub — Troubleshoot pull subscriptions](https://docs.cloud.google.com/pubsub/docs/pull-troubleshooting) — redeliveries, duplicate publishes, seek, and ordering.
