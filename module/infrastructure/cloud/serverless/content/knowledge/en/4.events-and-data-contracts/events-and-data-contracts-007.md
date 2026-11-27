# Event Time, Processing Time, and Late Events

In a serverless architecture, an event may be generated at one moment, travel across a network or sit in a queue for some time, and only then trigger a Java function. Consequently, the time a business fact occurred and the time a function processes the event rarely match. Confusing these two timestamps can cause daily revenue reports to be misattributed, aggregation windows to close prematurely, or valid transactions to be dropped simply because messages arrived late.

This lesson explains how to distinguish event time, processing time, and ingestion time; how to understand late and out-of-order events; and how to design data contracts, time windows, and appropriate handling policies.

## Learning Objectives

After this lesson, you will be able to:

- Distinguish event time, ingestion/arrival time, and processing time.
- Explain why events can arrive late or out of occurrence order.
- Understand time windows and watermarks in stream processing.
- Choose a late-event handling policy aligned with business requirements.
- Design event contracts that preserve business occurrence time and processing metadata.
- Write a Java function that measures latency without mutating the event's original timestamp.

## 1. Three Timestamps in an Event Flow

When an event is created and processed across multiple services, at least three timestamps must be distinguished.

| Timestamp | Meaning | Who Usually Records It? |
|---|---|---|
| **Event time** | When the business fact actually occurred | System or device originating the event |
| **Ingestion / arrival time** | When the broker, gateway, or platform received the event | Queue, event bus, API gateway, or adapter |
| **Processing time** | When the consumer began or executed processing of the event | Java function or stream processor |

Some systems also track **publication time**: when the producer dispatched the event. Publication time may differ from event time if the application recorded the fact earlier and only published the event later. Never treat a broker-assigned timestamp as event time; these timestamps serve different purposes.

### Example: Order Created While Device Is Offline

A sales associate creates an order at 10:02 while a tablet is disconnected. The application saves the order locally and syncs to the cloud at 10:17. The queue receives the message at 10:17:01, and the function begins processing at 10:17:02.

| Milestone | Timestamp |
|---|---|
| Event time — order created | 10:02:00 |
| Publication time — application sends event | 10:17:00 |
| Ingestion time — queue receives message | 10:17:01 |
| Processing time — function starts | 10:17:02 |

If an hourly revenue report uses processing time, the order is counted in the 10:15–10:30 window even though the business event occurred at 10:02. Conversely, for a dashboard monitoring function load, processing time is the right metric because it shows when the platform actually performed work.

**Rule of thumb:** use event time for business questions ("what happened when"); use processing time for operational questions ("when did the system process it"); use ingestion time to measure queue wait time from platform receipt to consumer processing.

## 2. Event Time and Processing Time Provide Two Different Views

Consider a stream of transaction events. There are two ways to aggregate transaction counts in five-minute intervals.

- **By event time:** transactions are placed into the window containing when the transaction actually occurred. This suits business reporting, store activity statistics, or behavioral analytics.
- **By processing time:** transactions are placed into the window when the function or stream processor handled them. This suits measuring throughput, consumption load, processing capacity, and operational latency.

The two results can diverge substantially when producers go offline, networks slow down, queues build backlogs, or systems undergo heavy retries.

For example, 100 events have event times between 10:00 and 10:05 but reach the queue between 10:10 and 10:15. A business report by event time records 100 transactions in the first window. A processing-time dashboard shows 100 executions in the later window. Both are accurate because they answer different questions.

### Never Replace Event Time with Function Execution Time

A common mistake is having a function receive an old event and overwrite its timestamp with the current time. The system then loses information about when the business event actually occurred. This corrupts reports, hampers incident investigation, and prevents data replays from reproducing original results.

Keep the original timestamp immutable inside the event. Consumers can record supplemental metadata such as receivedAt, processingStartedAt, and processedAt in logs or separate processing records.

## 3. Why Do Events Arrive Late or Out of Order?

In distributed systems, the order in which events are generated is not guaranteed to match the order in which consumers receive them. Common causes include:

1. **Offline devices or applications:** events are buffered locally and uploaded once connectivity returns.
2. **Network latency:** events traverse geographic regions, gateways, or intermediaries with varying transit times.
3. **Queues and partitions:** messages are partitioned or processed in parallel; consumers finish at different speeds.
4. **Batching and backpressure:** platforms batch multiple events or slow down under high load, keeping events waiting before processing.
5. **Retries and redelivery:** a failed message or expired acknowledgment may be redelivered behind newer messages.
6. **Replays and backfills:** operations teams intentionally replay historical data to fix bugs or regenerate reports.
7. **Clock skew:** clocks on producer devices or servers may run fast, slow, or unsynchronized.

Three phenomena must be distinguished:

- **Out-of-order event:** an event arrives in a different order from its event time. For example, an event from 10:04 is processed before an event from 10:03.
- **Late event:** an event arrives after the processor considers a time range relatively complete, typically determined by a watermark and an allowed lateness policy.
- **Duplicate event:** the same event is delivered or processed multiple times. Duplicates may arrive on time or late; this is orthogonal to ordering.

An event arriving behind another event is not necessarily late under the processing policy. If the watermark has not yet passed the relevant window, the processor can still accept the out-of-order event and update the result normally.

### Timestamps Can Also Be Wrong

Producer-supplied event time is trustworthy only when the producer follows strict recording rules. A device with a skewed clock can emit an event time in the future or far in the past. Therefore, the data contract must specify:

- Which business moment the timestamp represents.
- Who generates the timestamp and how clocks are synchronized.
- Format, timezone, and precision.
- Acceptable skew bounds and how invalid timestamps are handled.

For cloud systems, exchange timestamps in UTC—such as ISO 8601 with the Z suffix—or epoch values with an explicitly defined unit. In Java, Instant is the appropriate type to represent an unambiguous point in time. Avoid using a bare LocalDateTime for cross-region events because it carries no offset or timezone. When reporting by business day in a specific country, convert Instant to the business ZoneId at the reporting layer; never replace the original timestamp with local time. This rule also ensures correct handling on daylight saving transition days.

## 4. Time Windows in Event Processing

When summing, counting, or computing statistics over time intervals, processors typically group events into **time windows**.

| Window Type | How It Works | Example |
|---|---|---|
| Tumbling window | Fixed-size, contiguous, non-overlapping windows | 10:00–10:05, 10:05–10:10 |
| Sliding window | Fixed-length window advancing by a smaller step, so windows can overlap | 10-minute window updated every minute |
| Session window | Groups events into activity sessions; a session closes after an inactivity gap | A shopping session ending after 30 minutes of inactivity |

Event-time windows group by the event's timestamp. Processing-time windows group by when the processor observes or handles the event. Choosing the wrong window basis causes results to diverge from the measurement goal.

### Example of an Event-Time Tumbling Window

Suppose the system counts orders in five-minute windows:

- Window A: 10:00 up to (excluding) 10:05.
- Window B: 10:05 up to (excluding) 10:10.
- An order with event time 10:04:30 belongs to Window A, even if the function receives it at 10:12.

Define window boundary conventions explicitly, such as start-inclusive and end-exclusive. This prevents an event at exactly 10:05 from being double-counted in both windows or omitted from both.

## 5. Watermarks and Allowed Lateness

An event-time processing system needs a way to estimate when data for a time interval is reasonably complete. A **watermark** is a progress signal estimating event-time completeness: the processor assumes most events with timestamps below a threshold have likely arrived.

A watermark is not proof that no older event will ever arrive. A device may sync after hours offline, a queue may backlog, or operations may replay historical data. A watermark is a computational coordination mechanism built on latency assumptions, not an absolute guarantee from the event source.

**Allowed lateness** is the grace period during which the system continues accepting late events and updating window results after the watermark has passed the window's end according to processor rules.

Illustrative example:

- The business window ends at 10:05.
- The watermark passes 10:05, so the processor emits an initial result.
- Policy allows an additional 10 minutes of lateness.
- An event with event time 10:04 arriving at 10:09 can still update Window A's result.
- After the grace period expires, the event may be dropped, routed to a side stream, or trigger a correction record depending on policy.

Exact details of window closing, state retention, and expired-event handling differ across stream processors and cloud services. Always consult the semantics of your specific platform. A typical queue-triggered function does not provide watermarks or event-time windows out of the box; if those mechanisms are required, the application must use a stream processing service or manage state and progress explicitly.

### Illustrating Watermark Progression

~~~mermaid
flowchart LR
    A["Data event time"] --> B["Group events into windows"]
    B --> C["Watermark passes window end"]
    C --> D["Emit initial result"]
    D --> E["Receive late event within allowed lateness"]
    E --> F["Update or emit correction"]
    D --> G["Grace period expires"]
    G --> H["Close state / route expired events"]
~~~

Do not choose allowed lateness merely to make numbers look complete. Base it on observed latency distributions, response-time SLAs, and state storage costs. Holding windows open longer requires more memory or storage and delays when results are considered final.

## 6. Choosing a Late-Event Handling Policy

No single late-event policy fits every domain. Determine required accuracy, acceptable waiting time, and whether previously emitted results can be revised.

| Policy | Implementation | Best Fit When | Risks or Costs |
|---|---|---|---|
| Accept and update | Keep window state open longer; update sums or counts | Reports need accuracy and delays are typically short | Published results may change after initial display |
| Emit corrections | Keep emitted result and emit a correction/retraction on late events | Downstream systems must observe result revisions | Consumers must understand versioning or compensating actions |
| Route to a separate stream | Write expired events to a DLQ or late-event topic for later handling | Investigation, reconciliation, or backfill is needed | Requires operational and replay workflows |
| Drop expired events | Leave results unchanged; record only metrics and logs | Near-real-time dashboards prioritize low latency and approximate counts | Business results may be incomplete |
| Recompute historical data | Run batch jobs or backfills to regenerate results | Financial reporting or high-accuracy datasets | Resource-intensive and requires result versioning |

### Choosing by Business Requirement

- **Operational dashboards:** can tolerate approximate counts for a few minutes as long as last-updated time and lag alerts are shown.
- **Revenue reporting:** requires reconciliation rules and correction mechanisms; never silently discard valid transactions just because they arrived late.
- **Fraud detection:** balances alert speed against incorporating late-arriving evidence. An initial decision can be updated when additional events arrive.
- **Customer notifications:** must avoid resending notifications or repeating side effects when historical events are replayed.

A practical choice is emitting preliminary results early, then allowing updates within a defined allowed lateness window. For domains needing finalized figures, run reconciliation or batch backfills after the cutoff time.

## 7. Designing Event Contracts to Preserve Time Semantics

The event contract should specify which timestamp is the business occurrence time, which timestamps infrastructure adds, and how consumers must interpret them.

An order event might contain:

~~~json
{
  "eventId": "evt-8f31",
  "eventType": "OrderPlaced",
  "occurredAt": "2026-11-17T03:02:00Z",
  "publishedAt": "2026-11-17T03:17:00Z",
  "data": {
    "orderId": "ORD-1042",
    "total": 1250000,
    "currency": "VND"
  }
}
~~~

In this example, occurredAt is event time; publishedAt is when the producer dispatched the event. Ingestion time and processing time are typically recorded by the broker or consumer and do not need to be embedded in the producer's payload. If multiple consumers share the event, each consumer has its own processing time.

Design principles:

1. **Keep eventId stable:** retries and replays must preserve the original event's identifier so consumers can deduplicate.
2. **Keep occurredAt immutable:** never replace it with publish, enqueue, or function execution timestamps.
3. **Define timestamps explicitly:** field names must convey meaning; avoid a generic timestamp field without a contract definition.
4. **Use UTC and a uniform format:** specify ISO 8601 or epoch milliseconds/seconds explicitly; never mix units.
5. **Record timestamp source when needed:** for device-originated events, store source or clock metadata to assess trustworthiness.
6. **Separate delivery metadata:** deliveryAttempt, receivedAt, and processedAt belong to processing context; never mutate the original business event.
7. **Define invalid-timestamp handling:** events too far in the future or overly stale should be quarantined, alerted, or verified per business rules.

For auditable data, store the immutable raw event separately from processing outcomes or correction records. This preserves source lineage and explains why current figures differ from earlier published results.

## 8. Java Example: Measuring Latency Without Overwriting Event Time

The following example illustrates an event contract and how a function records processing time. Event time comes from the producer; processing time comes from the consumer's Clock. The 10-minute threshold is merely an operational delay alert threshold, not a watermark or full stream-processor late-event definition.

Example uses Java records (Java 16 and above).

~~~java
import java.math.BigDecimal;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

public record OrderPlaced(
        String eventId,
        String orderId,
        Instant occurredAt,
        Instant publishedAt,
        BigDecimal total,
        String currency) {
}

public record ProcessingObservation(
        Instant processingTime,
        Duration eventAge,
        boolean exceedsOperationalDelay,
        boolean producerClockAhead) {
}

public final class OrderEventHandler {
    private static final Duration MAX_OPERATIONAL_DELAY =
            Duration.ofMinutes(10);
    private static final Duration MAX_FUTURE_SKEW =
            Duration.ofSeconds(30);

    private final Clock clock;

    public OrderEventHandler(Clock clock) {
        this.clock = clock;
    }

    public ProcessingObservation handle(OrderPlaced event) {
        Instant processingTime = clock.instant();

        if (event.occurredAt() == null) {
            throw new IllegalArgumentException("occurredAt is required");
        }

        if (event.occurredAt().isAfter(
                processingTime.plus(MAX_FUTURE_SKEW))) {
            throw new IllegalArgumentException(
                    "occurredAt is too far in the future");
        }

        Duration rawEventAge =
                Duration.between(event.occurredAt(), processingTime);
        boolean producerClockAhead = rawEventAge.isNegative();
        Duration eventAge = producerClockAhead
                ? Duration.ZERO
                : rawEventAge;

        boolean delayed =
                eventAge.compareTo(MAX_OPERATIONAL_DELAY) > 0;

        // Log/metric the observation; do not modify event.occurredAt().
        return new ProcessingObservation(
                processingTime, eventAge, delayed, producerClockAhead);
    }
}
~~~

In production, the function adapter maps the event from HTTP, queue, or event source into OrderPlaced. Clock should be injected so unit tests can fix time. When event time is slightly ahead of the processing clock within the allowed skew bound in the example above, the observation flags producerClockAhead and clamps measured eventAge to 0 while leaving the original timestamp untouched. Events exceeding the future skew bound should be classified as data errors and routed to an appropriate handling stream. Throwing exceptions that trigger infinite retries from the source creates load without fixing bad data.

### Which Latencies Should Be Measured?

The following intervals can be tracked when timestamps are reliably recorded:

- **Event age:** processingTime minus occurredAt. Shows how old the event is when the consumer processes it.
- **Producer delay:** publishedAt minus occurredAt. Shows how long the producer took between the business occurrence and event emission.
- **Queue wait:** processingStartedAt minus receivedAt/enqueuedAt. Shows how long the event waited before the consumer started.
- **Execution duration:** processedAt minus processingStartedAt. Shows how long the function spent processing.

Do not subtract or compare timestamps from unsynchronized clocks without accounting for clock skew. For measuring duration within a single process, a monotonic clock or dedicated duration timer is more reliable than subtracting two wall-clock timestamps that may jump.

## 9. Retry, Replay, and Idempotency with Late Events

Late events and retries often occur together, yet they must be handled separately.

- **Retry:** the same message is redelivered because the previous attempt failed or did not acknowledge in time.
- **Replay:** historical events are intentionally re-emitted to recover state or regenerate results.
- **Late arrival:** an event arrives at the consumer for the first time after the watermark has passed its event time under window and lateness rules.

In all three cases, preserve the original event time and eventId. Consumers can record deliveryAttempt, replayRunId, or receivedAt in separate metadata. Overwriting occurredAt with the current time on every retry turns an old event into a brand-new event in time and corrupts aggregations.

To process safely:

1. Use eventId or a business key as the idempotency key.
2. Persist processed status alongside business results in an atomic operation whenever possible.
3. Separate permanent data errors from retryable infrastructure errors.
4. Determine whether a replay should update live results or only run for verification.
5. If results were already published downstream, use versions or correction events to represent updates.
6. Record dropped, DLQ-routed, or expired events for reconciliation.

Idempotency protects side effects from duplicate execution, but it does not solve window-update semantics by itself. An event can be processed strictly once and still arrive after a report has closed; a dedicated late-event policy is needed for that case.

## 10. Testing Time-Based Scenarios

Unit tests that only feed in-order events matching processing time miss many bugs. Create test cases with fixed clocks to reproduce these scenarios:

| Scenario | Test Data | What to Verify |
|---|---|---|
| On-time event | occurredAt close to processingTime | Assigned to the correct window |
| Late event | occurredAt significantly older than processingTime | Event age measured accurately and late policy applied |
| Out-of-order event | Receive 10:04 event before 10:03 event | Event-time windows update accurately |
| Duplicate | Resend same eventId | No repeated side effects |
| Future timestamp | occurredAt exceeds allowed clock skew | Quarantined or handled as a data error |
| Historical replay | Old event intentionally re-emitted | Not mistaken for a new event; results versioned/corrected properly |
| Window boundary | occurredAt exactly at window end | Follows published boundary convention |
| Timezones and DST transitions | Events across multiple timezones | UTC and local reporting remain consistent |

In Java, use Clock.fixed in unit tests to freeze processing time. Integration tests must verify the real semantics of your queue or stream processor: retries, ordering, watermarks, state retention, and DLQ behavior can differ from local emulators.

## 11. Time Design Checklist for Event-Driven Functions

- [ ] Event contract clearly defines occurredAt and its business semantics.
- [ ] Timestamps use UTC or an explicitly specified offset/timezone.
- [ ] Timestamp unit and precision are standardized.
- [ ] EventId remains unchanged across retries and replays.
- [ ] Ingestion time and processing time are recorded separately.
- [ ] Metrics exist for event age, queue wait, and execution duration.
- [ ] Criteria defining when an event is considered late and the deciding cutoff are documented.
- [ ] If using stream windows, window type, watermark, and allowed lateness are chosen.
- [ ] A policy exists for updating, correcting, quarantining, dropping, or backfilling late events.
- [ ] Consumers enforce idempotency to prevent side effects on redelivery.
- [ ] Future, overly stale, or invalid timestamps have explicit handling.
- [ ] Tests cover out-of-order, late events, duplicates, replays, and window boundaries.

## Self-Check Questions

1. Why can an order's event time be 10:02 while the function's processing time is 10:17?
2. When measuring function throughput, should you use event time or processing time? Why?
3. Is an out-of-order event always a late event? What role does the watermark play in distinguishing them?
4. How does allowed lateness help systems handle late-arriving data, and what is the trade-off?
5. Why must retries or replays never overwrite occurredAt with the current timestamp?
6. Does idempotency solve the problem of an event arriving after a reporting window has closed? What additional mechanism is needed?

In serverless systems, events can traverse multiple layers before reaching a Java function. Keeping business occurrence time, ingestion time, and processing time distinct ensures reports reflect reality, operations measure true latency, and consumers handle delayed data under explicit policies. Combining stable event contracts, well-chosen watermarks, idempotency, and correction workflows enables systems to stay responsive while preserving data accuracy.
