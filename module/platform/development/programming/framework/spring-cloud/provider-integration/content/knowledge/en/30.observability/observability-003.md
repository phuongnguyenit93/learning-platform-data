# Tracking message age, backlog, dead-letter, and processing duration

## 1. Context and objectives

In the **SPRING_CLOUD_PROVIDER_INTEGRATION** module, we practice integrating Spring Boot with managed services from **AWS, Azure, and Google Cloud** using the corresponding Spring Cloud libraries and SDKs. When an application dispatches asynchronous work to a message broker, seeing the producer publish successfully is not enough to conclude the system is healthy. Messages can sit waiting too long, consumers can lack capacity, a group of messages can fail repeatedly, or messages can be routed to a dead-letter queue (DLQ).

For example: an API accepts a submission, saves a document to object storage, and sends a message for a worker to generate a preview. The API still returns HTTP 202 even while the worker is lagging. If you only monitor API requests, operations may think everything is fine even though users wait several minutes for results.

This lesson focuses on four messaging signals:

- **Message age:** how long a message has waited from enqueue/publish time until a consumer begins processing it or until the observation point.
- **Backlog:** the number of messages waiting, in progress, or unacknowledged, depending on state and measurement method.
- **Dead-letter:** the number of messages quarantined after failing processing beyond the retry policy.
- **Processing duration:** how long the consumer takes to execute business logic for a message or batch.

After this lesson, you will be able to:

- Distinguish message age, queue backlog, in-flight count, processing duration, and end-to-end latency.
- Monitor queues/subscriptions and DLQs on Amazon SQS, Azure Service Bus, Azure Queue Storage, and Google Cloud Pub/Sub.
- Instrument consumers using Micrometer Timer/Counter and OpenTelemetry.
- Compute throughput, backlog growth rate, and estimated drain time.
- Design dashboards, SLOs, and alerts based on message age and backlog.
- Operate DLQs, investigate root causes, and perform controlled message redrive/replay.

## 2. Concepts that must not be conflated

A messaging system has multiple timestamps and states. Calling all of them “queue latency” makes it hard for dashboards to pinpoint bottlenecks.

| Signal | Interpretation | Measurement point |
|---|---|---|
| **Message age at processing start** | How long a message waited before the consumer started | consumerStart - enqueuedAt |
| **Backlog** | Number of incomplete messages at the broker | Point-in-time snapshot |
| **In-flight / unacked** | Messages delivered to a consumer but not yet acked/deleted/completed | From receive to settle |
| **Processing duration** | How long the consumer takes to run the handler | handlerFinish - handlerStart |
| **End-to-end latency** | Total time from when the producer creates the message until business completion | businessComplete - publishedAt |
| **DLQ count** | Number of messages currently in the dead-letter area | DLQ snapshot |
| **Retry/delivery attempts** | Number of times a message has been delivered or reprocessed | Per delivery/attempt |

Example:

~~~text
10:00:00  Producer publishes message
10:00:12  Broker delivers message to consumer
10:00:15  Consumer starts handler
10:00:45  Handler finishes
10:00:46  Consumer acks/completes message

Queue wait age       = 15 seconds
Processing duration  = 30 seconds
End-to-end latency   = 45 seconds
Settlement delay     = 1 second
~~~

**Message age is not processing duration.** If age rises while processing duration stays flat, the bottleneck is usually consumer capacity, scheduling, subscription backlog, or producer rate. If age is low while processing duration rises, investigate the handler, database, storage, or downstream APIs.

## 3. State model and message lifecycle

~~~mermaid
flowchart LR
    P[Producer] -->|publish/send| Q[(Queue / Subscription)]
    Q -->|receive| I[In-flight / locked]
    I -->|success + ack/delete/complete| D[Completed]
    I -->|transient failure / nack / abandon| Q
    I -->|delivery limit exceeded| DLQ[(Dead-letter)]
    DLQ --> R[Inspect / repair / replay]
    R --> Q
~~~

States to observe:

- **Available/active/visible:** messages ready for delivery.
- **Delayed/scheduled:** messages that exist but have not reached their delivery time yet.
- **In-flight/locked/unacked:** messages delivered and awaiting processing/settlement.
- **Completed/acknowledged/deleted:** broker has recorded the message as finished.
- **Dead-lettered:** messages moved to quarantine for investigation.
- **Expired:** messages past TTL/retention and no longer eligible for normal processing.

Exact names and semantics differ across providers. For example, SQS uses visibility timeout and delete; Service Bus uses Peek-Lock with complete/abandon/dead-letter; Pub/Sub uses ack deadline and acknowledge/nack. Do not compare counts across providers without normalizing equivalent states.

## 4. Is a growing backlog always an incident?

No. A queue with 100,000 messages can still operate smoothly if producers send 20,000 messages/second and consumers process 25,000 messages/second. Conversely, a queue with only 20 messages where the oldest message has waited 40 minutes can be a serious incident.

Observe these signals together:

1. **Backlog count:** how many messages are waiting?
2. **Oldest message age:** how long has the oldest message waited?
3. **Ingress rate:** at what rate are producers enqueuing messages?
4. **Completion/ack rate:** at what rate are consumers completing messages?
5. **In-flight count:** how many messages are currently held by consumers?
6. **Processing duration:** how long does a message/batch take to process?
7. **DLQ arrival rate and DLQ age:** are failures accumulating and being neglected?

### 4.1. Backlog growth rate

You can estimate:

~~~text
backlog_growth_rate = incoming_rate - completed_rate
~~~

- If persistently positive, the backlog is growing.
- If near 0, the system is processing roughly at the arrival rate.
- If negative, the backlog tends to shrink.

In systems with retries, redelivery, expiration, filters, or fan-out, incoming and completed rates must be defined along the same business boundary. Never mechanically subtract messages received from messages sent and conclude messages were lost.

### 4.2. Estimating backlog drain time

When completion rate exceeds ingress rate:

\[
T_{drain} \approx \frac{Backlog}{CompletionRate - IngressRate}
\]

For example, with a backlog of 120,000 messages, consumers completing 1,000 messages/second, and producers continuing to send 700 messages/second:

\[
T_{drain} \approx \frac{120,000}{1,000-700}=400\text{ seconds}
\]

If completion rate is less than or equal to ingress rate, the backlog cannot drain on its own under current conditions. This is a linear estimate; it does not account for message size distribution, retries, concurrency limits, partitions, bursts, or load-dependent processing duration.

## 5. Monitoring Amazon SQS

Amazon SQS automatically publishes queue metrics to CloudWatch under the **AWS/SQS** namespace. Several metrics are **approximate** due to SQS's distributed architecture; they are suitable for operational monitoring rather than exact transactional accounting.

### 5.1. Key metrics

| CloudWatch metric | Meaning | Purpose |
|---|---|---|
| **ApproximateAgeOfOldestMessage** | Age of the oldest unprocessed message per SQS semantics | Detect messages waiting too long |
| **ApproximateNumberOfMessagesVisible** | Messages available for receipt | Actionable backlog |
| **ApproximateNumberOfMessagesNotVisible** | Messages received but not yet deleted/expired from visibility | In-flight, held by consumers |
| **ApproximateNumberOfMessagesDelayed** | Delayed messages not yet ready for receipt | Track scheduled/delayed work |
| **NumberOfMessagesSent** | Number of messages successfully sent | Ingress volume |
| **NumberOfMessagesReceived** | Number of message receives | Delivery activity, may include redeliveries |
| **NumberOfMessagesDeleted** | Number of messages successfully deleted | Completion activity |
| **NumberOfEmptyReceives** | Receive calls returning no messages | Evaluate polling efficiency |

Queue counts are approximate and may not emit when a queue is idle. NumberOfMessagesReceived counts receive operations, not unique messages; a redelivered message produces multiple receives.

### 5.2. Monitoring SQS DLQs

A DLQ is a separate SQS queue configured as a redrive destination. When a message in the source queue exceeds maxReceiveCount, SQS moves it to the DLQ according to the redrive policy.

For a DLQ, track:

- ApproximateNumberOfMessagesVisible on the DLQ: messages awaiting investigation.
- ApproximateAgeOfOldestMessage on the DLQ: message age per SQS semantics since arriving in the DLQ.
- Rate at which messages are manually processed/redriven.
- Remaining messages and in-flight counts in the source queue.

Do not use NumberOfMessagesSent on the DLQ to count messages automatically moved to the DLQ: SQS does not include automatic redrives in this manual-send metric. Monitor the DLQ's visible count and age metrics instead.

### 5.3. Two common misconceptions about message age

- On a **standard queue**, when a poison message has been received multiple times without deletion, SQS may move it behind other messages; ApproximateAgeOfOldestMessage reflects the next message that has not exceeded the receive threshold, not necessarily the oldest poison message.
- When a message moves to a DLQ, the DLQ age metric reflects when it entered the DLQ. On standard queues, the original enqueue timestamp is preserved for retention; on FIFO queues, the enqueue timestamp resets when moved to the DLQ. Therefore, store a publishedAt/event timestamp in the payload if you need business age from producer creation.

Set DLQ retention longer than the source queue when appropriate so there is enough time to investigate and resolve failed messages.

## 6. Monitoring Azure Service Bus

Azure Service Bus provides a dedicated message broker supporting queues, topics/subscriptions, dead-letter subqueues, and states such as active, scheduled, deferred, completed, or abandoned.

### 6.1. Azure Monitor metrics

| Metric | Meaning | Purpose |
|---|---|---|
| **Active Messages** | Active messages ready for delivery | Deliverable backlog |
| **Dead-lettered messages** | Messages in the dead-letter subqueue | Track accumulating failures |
| **Scheduled messages** | Scheduled messages | Track future-dated work |
| **Messages** | Total messages across states counted by the metric | Overall entity view |
| **Incoming Messages** | Messages entering the entity | Ingress |
| **Outgoing Messages** | Messages received from the entity | Delivery activity |
| **Completed Messages** | Messages completed during the interval | Completion throughput |
| **Abandoned Messages** | Messages abandoned | Retry/redelivery pressure |
| **Size** | Entity size | Storage consumption |

Counts such as Active, Dead-lettered, Scheduled, and Messages are **point-in-time values**. Incoming and Outgoing need not match: duplicate detection, topic filters, TTL, dead-lettering, and auto-forwarding all affect counts. When message-count queries are throttled, some dynamic counts may return empty; never interpret an empty value as a queue truly having 0 messages.

### 6.2. Measuring message age in Service Bus

Azure Monitor provides message counts and throughput metrics, but lacks a direct oldest-message-age metric equivalent to SQS/Pub/Sub in its basic metrics table. Measure age on the consumer from message timestamps:

- EnqueuedTime/EnqueuedTimeUtc: when the broker accepted the message.
- consumerStart: when the handler begins.
- handlerFinish: when processing completes.

Service Bus supports **peek** to inspect a snapshot of messages without deleting them. Peek can return active, locked, deferred, and scheduled messages; dead-lettered messages must be peeked on the separate DLQ. Thus, peek is not a simple exact measure across every queue state. Use bounded peek for diagnostics, while instrumenting continuous age tracking in the consumer or producer/consumer envelope.

### 6.3. Dead-letter subqueue

Service Bus provides a dead-letter subqueue attached to each queue or subscription. Messages can enter the DLQ because:

- The consumer explicitly dead-letters them due to invalid payloads or unprocessable business errors.
- Messages exceed MaxDeliveryCount via abandon/lock expiry and redelivery.
- TTL expires when dead-lettering on message expiration is enabled on the entity.
- Certain forwarding or filter/operation failures depending on configuration.

When investigating, read DeadLetterReason and DeadLetterErrorDescription, correlation ID, message ID, sequence number, and application properties. Never put tokens or sensitive content into error descriptions.

## 7. Monitoring Azure Queue Storage

Azure Queue Storage is a simple queue inside a Storage account. It has different semantics from Service Bus and **no built-in dead-letter subqueue**.

### 7.1. Counting messages

Two common approaches:

- Azure Monitor metric **QueueMessageCount**: unexpired messages in the Storage account's Queue service. This metric refreshes infrequently (potentially daily) and is unsuitable for real-time autoscaling.
- Queue metadata / Get Properties: returns ApproximateMessagesCount for a single queue. This value is an estimate and may exceed the actual count; it is suitable for observing backlog near query time.

Do not compare account-level QueueMessageCount with Service Bus's per-queue active-message count as if they shared the same scope and freshness.

### 7.2. Message age and dequeue count

Azure Queue Storage messages expose metadata such as InsertedOn, NextVisibleOn, and DequeueCount via the corresponding SDK. Consumers can compute:

~~~text
message_age = consumer_start_time - message.InsertedOn
~~~

DequeueCount indicates how many times a message has been dequeued, helping detect repeatedly failing messages. Azure Queue Storage does not provide an automatic DLQ. Applications typically create a dedicated queue, such as `document-jobs-poison`, and move messages there once DequeueCount exceeds a threshold.

### 7.3. Monitoring limitations

Queue metadata count is approximate; Azure Monitor QueueMessageCount is not a real-time signal. When accurate business age is needed, include publishedAt/createdAt in the message envelope and measure at the consumer. You may peek a small batch of messages for investigation, but do not turn scanning the entire queue into a continuous task.

## 8. Monitoring Google Cloud Pub/Sub

Pub/Sub tracks backlog per **subscription**. A single topic can have multiple independent subscriptions, each with its own backlog, acknowledgements, and dead-letter behavior.

### 8.1. Key backlog metrics

| Cloud Monitoring metric | Meaning | Purpose |
|---|---|---|
| **subscription/num_unacked_messages_by_region** | Unacked messages by region | Regional backlog |
| **subscription/oldest_unacked_message_age_by_region** | Age of oldest unacked message by region | Detect consumer lag |
| **subscription/delivery_latency_health_score** | Health score related to delivery latency | Diagnose latency causes |
| **subscription/expired_ack_deadlines_count** | Count of expired ack deadlines | Detect slow consumer processing/acking |
| **subscription/dead_letter_message_count** | Messages forwarded to a dead-letter topic | Track DLQ forwarding |
| **subscription/num_outstanding_messages** | Push messages delivered but unacked | Monitor outstanding push deliveries |

Prefer metrics with the `by_region` suffix for backlog and oldest age. Global metrics can produce data gaps if a region fails to report; regional metrics allow continued visibility into remaining regions. Backlog metrics can also lag by a few minutes, so never rely on a single sample as an instantaneous signal.

### 8.2. Ack deadlines and redelivery

Consumers must acknowledge messages before the deadline. The client library can automatically extend ack deadlines up to a configured limit; if the deadline expires, the message may be redelivered. A high rate of expired ack deadlines typically suggests:

- Consumers lack threads/processes or concurrency.
- Handlers take longer than the maximum ack deadline.
- Consumers crash or messages trigger repeated errors.
- Acks are delayed by networking or improper lease management in the client.

Measure processing duration in the application and monitor expired_ack_deadlines_count in Pub/Sub to separate slow handlers from ack/transport issues.

### 8.3. Dead-letter topic

Pub/Sub supports configuring a dead-letter topic on a subscription. Once a message exceeds the configured delivery attempts, the service can forward it to that topic. The `subscription/dead_letter_message_count` metric counts forwarded messages.

To monitor DLQ backlog, attach a subscription to the dead-letter topic and track its `num_unacked_messages_by_region` and `oldest_unacked_message_age_by_region`. With the Java client, the delivery attempt is typically available in the `googclient_deliveryattempt` message attribute when a dead-letter policy is enabled. Delivery attempt count aids diagnostics, not as a replacement for idempotency.

## 9. Cross-provider comparison

| Need | Amazon SQS | Azure Service Bus | Azure Queue Storage | Google Cloud Pub/Sub |
|---|---|---|---|---|
| Backlog count | Approximate visible messages | Active Messages; count details | ApproximateMessagesCount; account metric QueueMessageCount | num_unacked_messages_by_region |
| In-flight | ApproximateNumberOfMessagesNotVisible | Locked/active state; broker metrics vary by view | Messages invisible during visibility window; instrument if needed | Outstanding/unacked and ack deadline |
| Oldest message age | ApproximateAgeOfOldestMessage | Measure from EnqueuedTime/peek | Measure from InsertedOn or publishedAt | oldest_unacked_message_age_by_region |
| Processing duration | Instrument in consumer | Instrument in consumer | Instrument in consumer | Instrument in subscriber |
| DLQ | Separate DLQ queue | Built-in dead-letter subqueue | Custom poison queue | Dead-letter topic + subscription |
| Delivery attempts | Approximate receive count/system attribute | DeliveryCount | DequeueCount | googclient_deliveryattempt (Java) |
| Count precision | Approximate, distributed | Snapshot/counts with specific semantics | Approximate; account metric refreshes infrequently | Metrics have sampling intervals and latency |

No single identical metric exists across all four services. Build shared dashboards at the application layer by normalizing definitions while keeping native metrics to investigate provider-specific behavior.

## 10. Designing a message envelope for end-to-end age

To measure end-to-end age and investigate DLQs, maintain stable business metadata:

~~~json
{
  "eventId": "evt-2026-0042",
  "jobId": "preview-42",
  "eventType": "DocumentPreviewRequested",
  "schemaVersion": 1,
  "publishedAt": "2026-11-24T09:00:00Z",
  "correlationId": "req-8f12",
  "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
  "payloadRef": {
    "provider": "azure",
    "container": "documents",
    "blobName": "incoming/doc-42.pdf"
  }
}
~~~

Key fields:

- eventId: unique message/event identifier; supports deduplication and idempotency.
- jobId: business key for looking up processing status.
- eventType and schemaVersion: tell the consumer how to interpret the payload.
- publishedAt: UTC timestamp when the business event originated; used for end-to-end age.
- correlationId: links logs across API, producer, and consumer.
- traceparent: propagates trace context per W3C Trace Context when supported.
- payloadRef: reference to large data to avoid embedding files inside messages.

Producer-recorded timestamps and broker-recorded timestamps mean different things. publishedAt reflects when business logic created the event; broker enqueuedAt/publishTime reflects when the broker received the message. Keep both when you need to separate producer delay from queue wait time.

Do not place access tokens, long-lived SAS URLs, account keys, or sensitive content into the envelope. Consumers should fetch payloads using a least-privilege managed identity/workload identity.

## 11. Instrumenting consumers with Micrometer

Provider-native metrics tell you how many messages sit in the queue. Application metrics must measure how long handlers actually run, message age at processing start, and each attempt's outcome.

A standardized metric set can include:

| Application metric | Type | Definition |
|---|---|---|
| messaging.message.age | Timer | From broker enqueue/publish time to when the consumer starts the handler |
| messaging.process.duration | Timer | Time taken by the handler to process the message |
| messaging.messages.processed | Counter | Number of successfully processed messages |
| messaging.messages.failed | Counter | Number of failed processing attempts |
| messaging.messages.dead_lettered | Counter | Number of messages moved by the app to DLQ/poison |
| messaging.consumer.inflight | Gauge | Number of messages currently being handled in the instance |
| messaging.consumer.batch.size | DistributionSummary | Number of messages in a batch |

Metric names follow an illustrative application convention. If adopting OpenTelemetry messaging semantic conventions, metrics include `messaging.process.duration`, `messaging.client.operation.duration`, `messaging.client.consumed.messages`, and `messaging.client.sent.messages`. At the time of writing, several messaging conventions remain in Development status; verify your instrumentation version and emitted conventions before standardizing.

### 11.1. Wrapper for age and processing duration

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.Callable;
import java.util.concurrent.TimeUnit;
import org.springframework.stereotype.Component;

@Component
public class MessageProcessingMetrics {
    private final MeterRegistry registry;

    public MessageProcessingMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public <T> T process(
            String provider,
            String destination,
            Instant enqueuedAt,
            Callable<T> handler) throws Exception {

        Duration messageAge = Duration.between(enqueuedAt, Instant.now());
        if (messageAge.isNegative()) {
            registry.counter(
                    "messaging.message.timestamp_anomalies",
                    "provider", provider,
                    "destination", destination,
                    "reason", "timestamp_in_future")
                .increment();
            messageAge = Duration.ZERO;
        }

        Timer.builder("messaging.message.age")
                .tag("provider", provider)
                .tag("destination", destination)
                .publishPercentileHistogram()
                .register(registry)
                .record(messageAge);

        long started = System.nanoTime();
        String outcome = "success";

        try {
            T result = handler.call();
            registry.counter(
                    "messaging.messages.processed",
                    "provider", provider,
                    "destination", destination)
                .increment();
            return result;
        } catch (Exception ex) {
            outcome = "error";
            registry.counter(
                    "messaging.messages.failed",
                    "provider", provider,
                    "destination", destination,
                    "error_type", classify(ex))
                .increment();
            throw ex;
        } finally {
            Timer.builder("messaging.process.duration")
                    .tag("provider", provider)
                    .tag("destination", destination)
                    .tag("outcome", outcome)
                    .publishPercentileHistogram()
                    .register(registry)
                    .record(System.nanoTime() - started, TimeUnit.NANOSECONDS);
        }
    }

    private String classify(Exception ex) {
        if (ex instanceof java.util.concurrent.TimeoutException) {
            return "timeout";
        }
        if (ex instanceof IllegalArgumentException) {
            return "invalid_message";
        }
        return "other";
    }
}
~~~

Call this wrapper after the consumer receives a message and right before the handler runs. enqueuedAt must come from the corresponding broker timestamp or the envelope's publishedAt. Verify timezone/clock synchronization; if a timestamp appears in the future due to clock skew, record an anomaly rather than reporting a negative age.

This wrapper measures each processing attempt. If a message is redelivered three times, processing duration is recorded three times, matching three handler executions. processed increments only when the handler succeeds; failed increments on each failed attempt. If the application moves the message to a DLQ, increment dead_lettered only in the dead-letter decision branch, not on every retryable failure.

### 11.2. Batch consumers

If a handler processes a batch of 100 messages in 2 seconds, do not record 2 seconds as each individual message's processing duration if the metric semantics represent per-item time. Instead, you can measure:

- messaging.process.batch.duration: duration to process the batch.
- messaging.consumer.batch.size: number of messages in the batch.
- messaging.message.age: individual age of each message when the batch starts.
- Per-message processing duration if the handler can time each item independently.

Document clearly whether metrics reflect batches or individual items so pull and push consumers are not miscompared.

## 12. Measuring message age accurately and safely

### 12.1. Choosing the right timestamp

| Provider | Common broker timestamp | Meaning |
|---|---|---|
| Amazon SQS | SentTimestamp system attribute | When the message was sent to SQS; understand redrive/DLQ semantics |
| Azure Service Bus | EnqueuedTime | When the message was enqueued in the entity |
| Azure Queue Storage | InsertedOn | When the message was inserted into the queue |
| Google Pub/Sub | publishTime | When Pub/Sub received the publish request |

Measure queue age using the broker timestamp when asking “how long did the message wait inside the broker?”. Measure business age using publishedAt when asking “how long has it been since business logic created the event?”. The two values can diverge due to producer buffering, send retries, or forwarding between entities.

### 12.2. Redelivery does not create a new message

A redelivered message increments its delivery count, while its eventId/jobId stays unchanged. Never reset publishedAt on consumer retries; doing so resets age back near 0 and hides messages stuck for a long time.

### 12.3. Age at delivery vs. age of the oldest queued message

Consumer-side age metrics are only recorded when a message is delivered. They do not capture messages still sitting untouched in the backlog. Therefore:

- Use the provider's oldest-message-age metric when available.
- For providers without a native age metric, instrument publishedAt/broker timestamps on consumer receipt and consider bounded peek/periodic sampling for diagnostics.
- Pair backlog count with ingress/completion rates to spot queue growth even before messages are delivered.

Never continuously peek the entire queue to calculate oldest age. Peek is a bounded diagnostic operation that consumes requests and does not accurately cover every state such as locked, deferred, scheduled, or DLQ.

## 13. Dead-letter: observing, investigating, and replaying

A DLQ is a quarantine zone, not a place “for failed messages to quietly disappear”. An unmonitored DLQ turns into a forgotten backlog.

### 13.1. Essential metrics

- Current DLQ count.
- Oldest DLQ message age.
- New messages entering the DLQ per minute/hour.
- Redriven/replayed message count and replay success rate.
- Messages expired by retention or manually purged.
- Root-cause categories: invalid payload, schema mismatch, permission, dependency failure, business rejection, delivery limit.

Separate **DLQ arrival rate** from **DLQ backlog**. Arrival rate reveals newly occurring errors; backlog shows unresolved error volume.

### 13.2. Metadata for investigation

When dead-lettering, retain minimal diagnostic metadata:

- Original message ID and event/job ID.
- Source queue/topic/subscription.
- First published/enqueued timestamp.
- Delivery/dequeue attempt count.
- Dead-letter timestamp.
- Normalized error type/reason.
- Correlation ID/trace ID.
- Schema version and application version.

Avoid logging full sensitive payloads. If retaining the original payload is necessary, store it in a repository with proper access controls and retention policies.

### 13.3. DLQ handling workflow

1. **Alert:** detect DLQ count or arrival rate exceeding thresholds.
2. **Inspect:** sample a small batch, classify reasons, and identify the source.
3. **Fix:** repair code, data, schema, permissions, or the failing dependency.
4. **Validate:** replay a few messages in a test/canary environment.
5. **Redrive:** replay in rate-limited batches while monitoring outcomes.
6. **Reconcile:** verify no duplicate side effects occurred; update business state.

Never bulk-redrive before fixing the root cause. If messages failed due to an old schema, replaying unchanged payloads simply creates another failure loop.

### 13.4. Idempotency and duplicates

A consumer may finish business logic yet crash before ack/delete/complete. The broker will redeliver the message. When replaying from a DLQ, duplicate risk is even higher. Use eventId or jobId as an idempotency key and persist processing state durably before settling the message.

## 14. Dashboards and observability queries

Each queue/subscription dashboard should include four panel groups:

| Group | Panels | Question |
|---|---|---|
| Backlog | Visible/active/unacked count | How many messages are waiting? |
| Age | Oldest age and p50/p95 age-at-start | How old is the oldest message and what is the wait distribution? |
| Consumer | Processing duration p50/p95, success/failure rate, in-flight | Is the consumer slow, failing, or under-provisioned? |
| DLQ | DLQ count, oldest DLQ age, arrival/redrive rate | Are failed messages accumulating and being handled? |

### 14.1. PromQL for application metrics

Assuming Micrometer exports the `messaging_process_duration_seconds_bucket` histogram:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, provider, destination) (
    rate(messaging_process_duration_seconds_bucket[5m])
  )
)
~~~

This query computes p95 processing duration from aggregated histograms. For p95 message age at handler start, query the corresponding histogram:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, provider, destination) (
    rate(messaging_message_age_seconds_bucket[5m])
  )
)
~~~

Processing failure rate by attempt:

~~~promql
sum by (provider, destination) (
  rate(messaging_messages_failed_total[5m])
)
/
sum by (provider, destination) (
  rate(messaging_messages_failed_total[5m])
  +
  rate(messaging_messages_processed_total[5m])
)
~~~

This gives the fraction of handler runs that failed; if you need the final failure rate of unique messages, track logical job/event outcomes using idempotency keys at the business layer. Do not substitute attempt error rate for job failure rate.

### 14.2. Provider-native backlog signals

- **SQS:** chart ApproximateNumberOfMessagesVisible, ApproximateNumberOfMessagesNotVisible, ApproximateAgeOfOldestMessage, and DLQ visible count.
- **Service Bus:** Active Messages, Dead-lettered messages, Incoming/Outgoing, Completed/Abandoned. Add app-side age metrics since there is no equivalent native oldest-age metric.
- **Queue Storage:** ApproximateMessagesCount via queue metadata for near-real-time visibility; use Azure Monitor QueueMessageCount only for long-term account-level trends.
- **Pub/Sub:** `num_unacked_messages_by_region`, `oldest_unacked_message_age_by_region`, `expired_ack_deadlines_count`, `dead_letter_message_count`.

Do not merge all counts into a single `queue_size` panel without specifying whether it represents visible, active, unacked, scheduled, or in-flight messages.

## 15. SLOs and alerting

Set SLOs around business timelines acceptable to users, not solely broker throughput.

Example for a document preview pipeline:

- 99% of messages begin processing within 60 seconds of enqueue.
- 99% of handlers complete within 20 seconds.
- DLQ arrival rate stays below 0.1% of processed messages.
- No critical DLQ message remains uninvestigated for more than 15 minutes.
- Backlog decreases whenever completion rate exceeds ingress rate over a sustained window.

These thresholds are examples; real workloads, priorities, and SLAs may differ.

### 15.1. Suggested alerts

| Condition | Interpretation | Action |
|---|---|---|
| Oldest age persistently exceeds SLO | Consumer lag or stuck messages | Inspect consumer capacity, in-flight count, and dependency latency |
| Backlog growing alongside oldest age | Consumers cannot keep up with producers | Scale carefully, inspect processing duration and throughput |
| High backlog with low age | Short burst or high throughput | Watch trend; not necessarily an immediate page |
| High age with low backlog | A few poison/stuck messages | Locate event ID, delivery count, and handler exceptions |
| High in-flight, low completion | Consumers hold messages too long or acks are slow | Inspect lock/visibility/ack deadlines and thread pools |
| Rising DLQ arrival rate | Data/schema/permission or dependency errors | Classify reasons; pause automatic redrive if needed |
| DLQ oldest age exceeds retention/SLA | Failed messages neglected | Escalate and execute investigation runbook |
| Rising expired ack deadlines | Consumers run too slowly or fail to renew leases | Tune concurrency, deadline/renewal, and handlers |

### 15.2. Autoscaling on backlog

Consumers can scale based on backlog or backlog per worker:

~~~text
backlog_per_worker = visible_or_unacked_backlog / active_workers
~~~

However, scaling only helps when:

- The provider allows additional consumers/partitions/concurrency.
- Downstream databases/storage will not be overwhelmed as consumers scale up.
- Messages can be processed in parallel without violating ordering/session constraints.
- In-flight/lock/ack deadlines are managed properly.

With Pub/Sub, prefer regional backlog metrics and check the delivery latency health score. With SQS FIFO or Service Bus Sessions, throughput may be bounded by the number of active message groups/sessions; adding replicas does not necessarily increase throughput if only one group is active.

## 16. Traces, logs, and cardinality

Metrics answer “what is going wrong broadly”; traces and logs answer “which specific message failed and why”.

When the producer sends a message:

- Generate a stable correlation ID/event ID.
- Propagate W3C traceparent or context per instrumentation support.
- Record a span for send/publish.

When the consumer processes it:

- Create a process/consumer span linked to the producer context.
- Record destination, operation, delivery attempt, and outcome.
- Log exception type and error category; avoid logging secrets or full payloads.
- Use event IDs in logs/traces for investigation; never use event IDs as metric labels.

OpenTelemetry messaging conventions recommend span links between producer and consumer in many messaging patterns, because a single message can fan out to multiple consumers or execute asynchronously. `messaging.process.duration` covers processing duration; `messaging.client.operation.duration` covers client operations such as send/receive/ack. Verify the status/version of semantic conventions and instrumentation in use before standardizing.

Keep metric labels bounded:

- provider: aws, azure, gcp.
- system: sqs, servicebus, storage_queue, pubsub.
- destination: queue/topic/subscription with stable, low-cardinality names.
- outcome: success, error, dead_lettered.
- error_type: invalid_message, timeout, authorization, dependency, other.

Never attach messageId, eventId, correlationId, traceId, customer ID, or blob/object names to metric labels. Those values belong in traces/logs.

## 17. Testing and incident drills

A test suite should verify both consumer and broker metrics:

| Scenario | Expected result |
|---|---|
| Message processed immediately | Low age; processing duration recorded; success increments |
| Producer sends large burst | Backlog grows then drains as consumers catch up |
| Slow handler | Processing duration rises; in-flight/age reflect delay |
| Transient handler error | Message is retried/redelivered per policy |
| Permanent message error | Moved to DLQ/poison per delivery limit |
| Ack/complete fails after processing | Possible redelivery; idempotency prevents duplicate side effects |
| New message enters DLQ | DLQ count and arrival metric rise; alert triggers |
| DLQ replay after fix | Messages process cleanly and business state reconciles |
| Consumer scales out | Throughput increases if partitions/groups/concurrency allow |
| One Pub/Sub region loses metrics | Regional dashboard still displays remaining regions |
| Azure Service Bus count query throttled | Empty dynamic count is not interpreted as zero backlog |
| SQS poison message received repeatedly | ApproximateAgeOfOldestMessage and DLQ semantics interpreted correctly |

### 17.1. Unit testing processing metrics

SimpleMeterRegistry can verify Timers and Counters:

~~~java
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class MessageProcessingMetricsTest {
    @Test
    void recordsSuccessfulProcessing() throws Exception {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        MessageProcessingMetrics metrics =
                new MessageProcessingMetrics(registry);

        String result = metrics.process(
                "azure",
                "document-jobs",
                Instant.now().minusSeconds(2),
                () -> "done");

        assertEquals("done", result);
        assertEquals(
                1.0,
                registry.get("messaging.messages.processed")
                        .tag("provider", "azure")
                        .tag("destination", "document-jobs")
                        .counter()
                        .count());
        assertEquals(
                1L,
                registry.get("messaging.process.duration")
                        .tag("provider", "azure")
                        .tag("destination", "document-jobs")
                        .tag("outcome", "success")
                        .timer()
                        .count());
    }
}
~~~

Add tests for exceptions, age calculation, error tags, and batches. Run integration tests against real brokers or suitable emulators to verify delivery count, visibility/lock/ack deadlines, DLQ routing, and native metrics. Mocks cannot prove managed-service redelivery behavior.

### 17.2. Game day

In staging:

1. Increase producer rate in a controlled way to build backlog.
2. Reduce worker count or increase processing duration to induce consumer lag.
3. Send a malformed message payload to verify DLQ/poison policies.
4. Revoke dependency permissions to confirm permission errors are classified properly.
5. Restore dependency, fix root causes, and replay a small batch of messages.
6. Confirm age, backlog, processing duration, DLQ, and alerts return to normal.

Never run game days by overloading or intentionally breaking production queues.

## 18. Common pitfalls and fixes

| Symptom | Possible cause | Fix |
|---|---|---|
| High backlog count yet users notice no delay | High throughput; backlog is a short burst | Compare oldest age, ingress, and completion rates |
| Low backlog yet very high oldest age | A few stuck or poison messages | Inspect delivery count, message ID, and handler errors |
| Low processing duration yet rising age | Low consumer capacity or insufficient message pulls | Check worker count, polling, subscription, and concurrency |
| In-flight count keeps climbing | Consumers fail to ack/delete/complete or handlers hang | Inspect lease/visibility/ack deadlines and exception paths |
| DLQ count rises while SQS NumberOfMessagesSent stays flat | Automatic redrives are not counted as manual sends | Monitor visible count and age on the DLQ |
| Service Bus message count shows 0 when throttled | Dynamic counts can be empty in responses | Cross-check Azure Monitor metrics, retry queries, and throttle logs |
| Queue Storage metric misses real-time backlog | Account-level QueueMessageCount refreshes infrequently | Use per-queue ApproximateMessagesCount and app-side age |
| Gaps in Pub/Sub backlog metric | Global metrics depend on multiple regions reporting | Use metrics with the `by_region` suffix |
| DLQ replay causes duplicate side effects | Consumer is not idempotent | Use eventId/jobId and durable processing state |
| Negative or jumping message age | Clock skew or timestamp reset on retry | Use UTC, sync clocks, preserve original publishedAt |
| Batch processing duration misread as per-message | Metric records total batch time for each item | Separate batch duration from per-message duration |
| Autoscaling fails to improve throughput | FIFO group/session/partition limits parallelism | Increase active groups/partitions appropriately or redesign processing |

## 19. Hands-on exercises and self-check questions

**Scenario A — SQS backlog:** ApproximateNumberOfMessagesVisible grows steadily, ApproximateAgeOfOldestMessage also rises, and NotVisible stays low. Analyze why consumers may not be receiving enough messages, check polling/worker capacity, and propose a scaling approach.

**Scenario B — SQS DLQ:** A DLQ holds 500 messages while NumberOfMessagesSent is nearly 0. Explain why automatic redrives do not increment the manual send metric and choose the right metrics to monitor the DLQ.

**Scenario C — Service Bus:** Active Messages rise, Dead-lettered Messages rise, and Completed Messages drop. Inspect consumer errors, delivery count, lock expiry, and DeadLetterReason; design a fix-and-replay plan.

**Scenario D — Azure Queue Storage:** Azure Monitor QueueMessageCount stays unchanged while queue metadata count climbs. Explain the freshness/accuracy differences between the two measures and design a consumer-side age metric from InsertedOn.

**Scenario E — Pub/Sub:** `num_unacked_messages_by_region` and `oldest_unacked_message_age_by_region` rise together while `expired_ack_deadlines_count` also climbs. Inspect processing duration, subscriber concurrency, and ack deadline extensions.

**Scenario F — Message age vs. processing duration:** A dashboard shows p95 age at 5 minutes while p95 processing duration is only 2 seconds. Determine whether the bottleneck lies in broker wait time or the handler and propose a fix.

**Scenario G — DLQ replay:** A batch of messages landed in the DLQ because consumers used an outdated schema. After deploying the fix, design canary replay, idempotency, rate limiting, and reconciliation.

### Self-check questions

1. **How does message age differ from processing duration?** Age measures wait time from enqueue/publish until consumer start; processing duration measures how long the handler runs.
2. **Is a high backlog count always an incident?** No; compare it against throughput and oldest age.
3. **Which SQS metric counts messages ready for receipt?** ApproximateNumberOfMessagesVisible.
4. **Which SQS DLQ metric tracks waiting messages?** ApproximateNumberOfMessagesVisible on the DLQ.
5. **Does Azure Service Bus have a native DLQ?** Yes, as a dead-letter subqueue per queue/subscription.
6. **Does Azure Queue Storage have a native DLQ?** No; applications create a poison queue and route messages there by policy.
7. **Is Azure Queue Storage QueueMessageCount suitable for real-time autoscaling?** No; the account-level metric updates infrequently. Use per-queue approximate counts and app metrics.
8. **Which Pub/Sub backlog metrics provide regional resilience?** `num_unacked_messages_by_region` and `oldest_unacked_message_age_by_region`.
9. **Why measure expired ack deadlines?** It shows messages may be redelivered because consumers fail to ack in time.
10. **When should a DLQ be replayed?** After identifying and fixing the root cause, validating a small sample, and ensuring consumers are idempotent.

## 20. Summary

Messaging observability must combine **backlog, oldest message age, in-flight/unacked counts, processing duration, and DLQ tracking**. Backlog shows pending work volume; age shows how long users must wait; processing duration shows handler speed; DLQ shows accumulating unprocessable messages.

AWS SQS provides CloudWatch metrics for oldest age, visible, not-visible, and DLQ queues; Azure Service Bus provides active/dead-letter counts and requires consumer-side age tracking; Azure Queue Storage offers approximate counts with varying freshness and requires custom poison queues; Google Pub/Sub provides regional backlog/oldest-age metrics, ack deadlines, and dead-letter topics. Standardize definitions in the application layer, use Micrometer/OpenTelemetry, preserve original timestamps and idempotency keys, and redrive messages only after fixing the root cause.

### Official references

- [AWS — Available CloudWatch metrics for Amazon SQS](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-available-cloudwatch-metrics.html)
- [AWS — Using dead-letter queues in Amazon SQS](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-dead-letter-queues.html)
- [Azure — Monitoring data reference for Service Bus](https://learn.microsoft.com/azure/service-bus-messaging/monitor-service-bus-reference)
- [Azure — Get message counters for Service Bus](https://learn.microsoft.com/azure/service-bus-messaging/message-counters)
- [Azure — Browse or peek Service Bus messages](https://learn.microsoft.com/azure/service-bus-messaging/message-browsing)
- [Azure — Best practices for monitoring Queue Storage](https://learn.microsoft.com/azure/storage/queues/queues-storage-monitoring-scenarios)
- [Azure — Queue Storage monitoring data reference](https://learn.microsoft.com/azure/storage/queues/monitor-queue-storage-reference)
- [Google Cloud — Monitor Pub/Sub subscriptions](https://docs.cloud.google.com/pubsub/docs/monitoring)
- [Google Cloud — Dead-letter topics](https://docs.cloud.google.com/pubsub/docs/dead-letter-topics)
- [OpenTelemetry — Semantic conventions for messaging metrics](https://opentelemetry.io/docs/specs/semconv/messaging/messaging-metrics/)
- [OpenTelemetry — Semantic conventions for messaging spans](https://opentelemetry.io/docs/specs/semconv/messaging/messaging-spans/)
