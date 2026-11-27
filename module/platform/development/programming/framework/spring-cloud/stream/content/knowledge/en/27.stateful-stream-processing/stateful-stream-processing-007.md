# Grace Periods, Late Data, and Window Results

In stream processing, events do not always arrive in Kafka in exact business chronological order. A transaction that occurred at 10:02 may arrive after a transaction from 10:04 due to network delays, offline devices, retries, or producers emitting from multiple sources. If the system finalizes window results as soon as it sees the end timestamp, late-arriving events can be ignored or skew metrics.

Kafka Streams solves this problem using **event time**, **stream time**, windows, and **grace periods**. A window defines which events belong to the same time group; the grace period bounds how long after a window ends the system continues accepting out-of-order records. Window results can be emitted continuously as state changes or emitted once after the window closes.

In the Spring Cloud Stream Kafka Streams binder, these concepts are used directly via the Kafka Streams DSL inside function beans. This lesson focuses on choosing timestamps, configuring grace periods, distinguishing late events from dropped events, managing state retention, and testing final results.

## 1. Why Do Events Arrive Late?

Suppose a store aggregates order counts per customer in 5-minute windows. An order's business time is recorded when it occurs, but producers may send records several minutes later.

~~~text
Business time (event time)               Time record reaches Kafka
10:01:00  order A --------------------> 10:01:02
10:02:00  order B -------------------------------> 10:05:30
10:04:00  order C --------------------> 10:04:03
10:03:00  order D --------------------------------------> 10:08:00
~~~

If the system relied only on arrival time, it could place order B and order D into the wrong windows. With event time, they are assigned to windows by when they occurred, but you must decide how long the system still waits for late-arriving records.

Common causes:

- Mobile or IoT devices go offline and flush buffered data later.
- Producers retry or batch multiple events before sending.
- Multiple producers experience differing network latencies.
- Consumers or brokers face temporary congestion.
- Events originate at an upstream system and pass through multiple services before hitting the topic.
- Source machine clocks drift or timestamps are generated improperly.
- Replays/backfills inject older records into the topic after windows have already been processed.

Event time is the business instant the event represents. Processing time is when the application executes processing for the record. Kafka Streams also uses stream time to determine a task's time progress. These three milestones can differ.

## 2. Event Time, Processing Time, and Stream Time

| Concept | Meaning | Example |
|---|---|---|
| Event time | When the event actually occurred according to source data | Order created at 10:02 |
| Processing time | When the application is currently processing the record | Consumer processes at 10:06 |
| Stream time | Time milestone advancing based on record timestamps observed by the task | Task has received records timestamped up to 10:08 |

Kafka records carry timestamp metadata. By default, Kafka Streams uses the timestamp in `ConsumerRecord`. That timestamp may reflect `CreateTime` sent by the producer or `LogAppendTime` assigned by the broker, depending on topic/broker configuration.

If you need to use an `occurredAt` field inside the payload as event time, you must provide a `TimestampExtractor`. Do not assume Kafka timestamps always represent business occurrence time.

Stream time is tracked per task by Kafka Streams and advances when the task processes a record with a timestamp higher than the current mark. Out-of-order records with smaller timestamps do not push stream time backward. It is not a continuously ticking system clock. When no new records arrive, stream time can stand still even as wall-clock time moves ahead by many minutes.

This point is critical: grace periods and window closing are driven by stream time. Without new records pushing stream time forward, a window may remain unclosed and its final result unemitted even when wall-clock time has passed window end plus grace.

~~~text
Record event times          10:01  10:02  10:04  10:08
                                |     |     |     |
Task stream time            10:01 -> 10:02 -> 10:04 -> 10:08

Wall clock keeps running even with no records.
Stream time advances only with the timestamps of processed data.
~~~

Do not confuse stream time with a global watermark from another stream processing engine. Kafka Streams uses per-task stream-time semantics to manage windows, grace periods, and suppression.

## 3. Windows Define Time-Based Grouping Scopes

Windowing partitions records with the same key into time-based groups for `count`, `reduce`, `aggregate`, or `join`.

Kafka Streams supports four main window shapes:

| Window Type | Characteristics | Use Case Example |
|---|---|---|
| Tumbling time window | Fixed size, non-overlapping, no gaps | Total orders every 5 minutes |
| Hopping time window | Fixed size, potentially overlapping; has size and advance interval | Total orders over 5 minutes, updated every minute |
| Sliding window | Continuously sliding window by timestamp difference between records | Detecting two behaviors within 10 minutes of each other |
| Session window | Dynamic size, separated by an inactivity gap | Grouping a user's sequence of actions |

### Tumbling Window

Non-overlapping 5-minute windows have boundaries:

~~~text
[10:00, 10:05) [10:05, 10:10) [10:10, 10:15)
     5 min           5 min           5 min
~~~

The interval is left-inclusive and right-exclusive. A record timestamped exactly 10:05 belongs to the window starting at 10:05, not the window ending at 10:05.

Kafka Streams `TimeWindows` are epoch-aligned. With a 5-minute tumbling window, boundaries align on multiples of 5 minutes since the epoch rather than aligning to when the application started.

### Hopping Window

A window with size 5 minutes and advance 1 minute:

~~~text
[10:00, 10:05)
   [10:01, 10:06)
      [10:02, 10:07)
         [10:03, 10:08)
~~~

One event can belong to multiple windows. Hopping suits dashboards computing rolling lookback totals with frequent updates. State costs and output counts are typically higher than tumbling.

### Sliding Window

A sliding window differs from a hopping window. It builds snapshots based on timestamp differences between records; boundaries are not simply fixed epoch-aligned steps. Kafka Streams provides `SlidingWindows` for windowed aggregations and `JoinWindows` for stream-stream joins. Do not refer to every overlapping window as the same window type.

### Session Window

A session window groups records by key as long as the gap between events does not exceed the inactivity gap. When a new event bridges two sessions, Kafka Streams can merge the sessions and update the result. Session windows fit user sessions, interaction journeys, or action sequences whose duration depends on real activity.

## 4. What Is a Grace Period?

The grace period is the duration after a window's end during which Kafka Streams still accepts out-of-order records for that window.

Example window `[10:00, 10:05)` with a 2-minute grace period:

~~~text
Window end:       10:05
Grace period:     10:05 ---------------- 10:07
                  |<------ 2 min ------>|

Stream time has not passed the window-close threshold:
  a late record with event-time 10:04 can still update the window.

Stream time has passed 10:07:
  the window is closed; later records belonging to this window are dropped.
~~~

Grace does not change a record's event timestamp. Nor does it shift the record into the next window. Grace solely defines how long the window stays open to accept out-of-order data.

Points to remember:

- Grace is measured from window end, not from when the first record arrived.
- Records are assigned to windows by event timestamp, whereas whether a window has closed depends on the task's stream time.
- Records arriving after the window closes are dropped from that window's calculation.
- Larger grace accepts later data, but delays final results and holds state longer.
- A grace of 0 means no waiting period for out-of-order records once the window ends.
- Grace is neither a consumer retry delay nor Kafka topic retention.

Modern Kafka Streams requires choosing grace explicitly via factory methods like `ofSizeAndGrace` or `ofSizeWithNoGrace`. Older APIs used to default to a 24-hour grace period; Kafka removed that default to prevent inadvertently holding unfinalized results for a full day. Therefore, avoid relying on legacy window constructors or assuming every version shares the same default.

## 5. Timeline Example: Is a Record Accepted or Dropped?

Suppose tumbling window `[10:00, 10:05)` with 2-minute grace. The close threshold is 10:07 in stream time.

| Arrival Order | Event Timestamp | Stream Time Before Arrival | Outcome |
|---|---:|---:|---|
| 1 | 10:01 | 10:00 | Accepted, updates window |
| 2 | 10:04 | 10:01 | Accepted, updates window |
| 3 | 10:02 | 10:04 | Accepted; out-of-order record, but window still within grace |
| 4 | 10:08 | 10:04 | Stream time advances to 10:08; the 10:00 window is now closed |
| 5 | 10:03 | 10:08 | Dropped from window `[10:00, 10:05)` because grace has passed |

A common pitfall: record #3 has a timestamp smaller than current stream time yet is still accepted because the window has not closed. Record #5 has an event timestamp inside the old window, but arrives after stream time has passed `end + grace`, so it cannot modify that window's result.

A record with an abnormally futuristic timestamp can push stream time far ahead, closing many older windows prematurely. Always check for future timestamps, clock skew, and replayed data before feeding records into the topology.

## 6. Configuring a Tumbling Window with Grace in the Kafka Streams DSL

Example counting orders per customer ID in 5-minute windows, accepting late records up to 2 minutes:

~~~java
import java.time.Duration;

import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.common.utils.Bytes;
import org.apache.kafka.streams.kstream.Grouped;
import org.apache.kafka.streams.kstream.KTable;
import org.apache.kafka.streams.kstream.Materialized;
import org.apache.kafka.streams.kstream.TimeWindows;
import org.apache.kafka.streams.kstream.Windowed;
import org.apache.kafka.streams.state.WindowStore;

KTable<Windowed<String>, Long> counts = orders
    .groupByKey(Grouped.with(
        Serdes.String(),
        Serdes.String()
    ))
    .windowedBy(
        TimeWindows.ofSizeAndGrace(
            Duration.ofMinutes(5),
            Duration.ofMinutes(2)
        )
    )
    .count(
        Materialized
            .<String, Long, WindowStore<Bytes, byte[]>>as(
                "orders-per-customer-5m"
            )
            .withKeySerde(Serdes.String())
            .withValueSerde(Serdes.Long())
            .withRetention(Duration.ofHours(1))
    );
~~~

Explanation:

- `groupByKey` groups records by Kafka key; here the key is customer ID.
- `TimeWindows.ofSizeAndGrace` creates fixed 5-minute windows with a 2-minute grace period.
- `count` maintains record counts per key and window.
- `Materialized.as` names the state store for monitoring and recovery.
- `withRetention` keeps window state at least long enough for window plus grace; here 1 hour exceeds the required 7 minutes.

If changing the key before grouping, use `groupBy` with `Grouped.with` to supply Serdes for the new key and value. Kafka Streams may create a repartition topic to route identical keys to the same partition.

The output is a `KTable` keyed by `Windowed<String>`, not a plain `String`. The key carries both customer ID and window bounds to distinguish the same customer across multiple windows.

## 7. Continuously Changing Window Results

After aggregation, the `KTable` emits updates as new records or accepted late records arrive.

Example for window `[10:00, 10:05)`:

~~~text
Event A arrives: count = 1
Event B arrives: count = 2
Event C arrives late within grace: count = 3
~~~

If you immediately convert the `KTable` into a `KStream`, downstream may receive three updates: `1`, `2`, and `3`. These are successive latest values for the same windowed key, not three independent numbers to sum together.

Downstream consumers must understand update semantics:

- When writing to a state table, upsert by customer + window.
- When sending to a system that expects only final results, do not forward intermediate updates.
- When aggregating across updates, handle changelog semantics rather than summing every emitted value.
- When using a compacted topic, ensure unique keys per customer/window and a serializer for the windowed key.

### Converting KTable to KStream

~~~java
KStream<Windowed<String>, Long> updates = counts.toStream();
~~~

This `KStream` contains update records. It does not turn multiple updates into a single business event on its own. If the output topic uses windowed keys, configure a matching `TimeWindowedSerde` for the key and window size. If you do not want windowed keys at the Kafka layer, map to a `String` key and embed window start/end in the value.

Example producing a readable output format:

~~~java
KStream<String, String> summaries = counts.toStream()
    .map((windowedKey, count) -> {
        String customerId = windowedKey.key();
        long start = windowedKey.window().start();
        long end = windowedKey.window().end();

        String value = start + "|" + end + "|" + count;
        return KeyValue.pair(customerId, value);
    });
~~~

In this example, the output key is customer ID and the value contains window start, end, and count. If the same customer spans multiple windows, this simple `String` key collides and newer records can overwrite older ones in a compacted topic. When retaining multiple windows, use a windowed key or a composite key like `customerId + windowStart`.

## 8. Emitting Only Final Results with Suppressed.untilWindowCloses

Some business workflows must wait until grace expires before sending results, such as:

- Finalizing revenue per 5-minute interval.
- Raising an alert when hourly transaction counts fall below a threshold.
- Sending end-of-period reports to a system that does not support updates.
- Generating invoices or snapshots once a window closes.

Kafka Streams provides `Suppressed.untilWindowCloses` to buffer intermediate updates and emit only the final value once the window closes.

~~~java
import static org.apache.kafka.streams.kstream.Suppressed.BufferConfig.unbounded;

import org.apache.kafka.streams.kstream.Suppressed;

KTable<Windowed<String>, Long> finalCounts = counts.suppress(
    Suppressed.untilWindowCloses(unbounded())
);
~~~

With window 10:00–10:05 and 2-minute grace, the final result emits only once the task's stream time crosses the 10:07 close mark. If 10 valid events fell in the window, downstream receives a single final output with count 10 instead of updates 1, 2, 3...10.

Grace and suppression play distinct roles:

| Component | Governs |
|---|---|
| Window size | Which time bucket an event belongs to |
| Grace period | How long the window accepts out-of-order records |
| `Suppressed.untilWindowCloses` | When to emit final results instead of every update |
| State retention | How long state remains stored before cleanup |

Without suppression, results keep updating continuously. Grace still determines whether late records are accepted.

### Suppression Buffers

`unbounded()` is easy to demonstrate, but has no memory limit. In production, bound the buffer by bytes or record count and choose an overflow policy.

- `emitEarlyWhenFull()` frees memory by emitting some results before the window closes; this can break "final-only" requirements.
- `shutDownWhenFull()` preserves strict final-only semantics, but can halt the processor if the buffer hits its limit.
- Size the limit based on concurrent open windows, active keys, grace length, event rate, and allocated application memory.

Do not use an unbounded buffer in production without estimating concurrent windows and keys. The longer the grace and the higher the traffic, the more pending results the buffer must hold.

## 9. Choosing a Grace Period Based on Real Latency

Too short a grace period loses late events. Too long a grace period delays finalized results and inflates state retention and suppression buffers.

Measure the arrival latency distribution:

`event arrival delay = record arrival timestamp - event time`

For example, if 99.5% of events arrive within 45 seconds and business rules tolerate dropping a tiny tail of later data, a 1-minute grace period is a reasonable starting point to test. If sources can go offline for 20 minutes and flush backlogs later, a 1-minute grace will not suffice.

Workflow for choosing grace:

1. Collect business timestamps and record arrival timestamps.
2. Compute latency percentiles (p50, p95, p99) and extreme outliers.
3. Segment sources with different latency profiles; do not look solely at a system-wide average.
4. Determine result finalization SLAs.
5. Choose a grace period covering most acceptable latency.
6. Size state stores and suppression buffers accordingly.
7. Replay real production-like traffic to measure dropped late-record rates.
8. Monitor metrics post-deployment and adjust when traffic patterns shift.

Do not pick grace by adding an arbitrary number. Balance data completeness, output latency, and state storage costs.

## 10. Grace Period Is Not State Store Retention

These two settings are often confused:

- Grace defines how long a window accepts late-arriving records.
- Retention defines how long the state store keeps window data before purging it.

For example, with a 5-minute window size and 2-minute grace, the state store must keep window data long enough to process through the end of grace; retention cannot be smaller than `window size + grace`. You may keep it longer for queries or operational reasons.

~~~java
.count(
    Materialized
        .as("orders-per-customer-5m")
        .withKeySerde(Serdes.String())
        .withValueSerde(Serdes.Long())
        .withRetention(Duration.ofHours(1))
);
~~~

Notes to keep in mind:

- Longer retention does not automatically extend grace. Records arriving after the window closes are still dropped.
- Longer grace does not automatically guarantee state is retained long enough if retention is misconfigured.
- Too short a retention can purge window state prematurely.
- Too long a retention increases disk usage, changelog size, and restore times.
- Kafka Streams has a default window store retention; production workloads should set it explicitly when control is needed.

For session windows, retention must cover the inactivity gap plus grace. For joins, verify retention on both state stores along with join window and grace settings.

## 11. TimestampExtractor: Selecting the Right Timestamp

By default, Kafka Streams reads metadata timestamps from Kafka `ConsumerRecord`. If producers already stamp metadata with accurate event times, that may suffice.

If business timestamps reside inside the payload, create a `TimestampExtractor` bean:

Declare the `Purchase` DTO once in a shared package so producers, Serdes, extractors, and functions all use it:

~~~java
import java.time.Instant;

public record Purchase(
    String customerId,
    long amount,
    Instant occurredAt
) {}
~~~

Place this record in `Purchase.java` inside a shared application package. The extractor and topology examples below use this DTO.

~~~java
import java.time.Instant;

import org.apache.kafka.streams.errors.StreamsException;
import org.apache.kafka.streams.processor.TimestampExtractor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class EventTimestampConfiguration {

    @Bean
    TimestampExtractor purchaseTimestampExtractor() {
        return (record, partitionTime) -> {
            Object value = record.value();

            if (!(value instanceof Purchase purchase)
                    || purchase.occurredAt() == null) {
                throw new StreamsException(
                    "Purchase event is missing occurredAt"
                );
            }

            Instant occurredAt = purchase.occurredAt();
            long timestamp = occurredAt.toEpochMilli();

            if (timestamp < 0) {
                throw new StreamsException(
                    "Purchase event has an invalid timestamp"
                );
            }

            return timestamp;
        };
    }

}
~~~

This example assumes the value has already been deserialized into `Purchase` before the timestamp extractor inspects the record. If values arrive as raw JSON bytes or `String`, the extractor must parse the actual format and handle parse errors intentionally.

Attach the extractor to the right input binding:

~~~yaml
spring:
  cloud:
    function:
      definition: purchaseWindowCounts

    stream:
      kafka:
        streams:
          bindings:
            purchaseWindowCounts-in-0:
              consumer:
                timestampExtractorBeanName: purchaseTimestampExtractor
~~~

The Spring Cloud Stream Kafka Streams binder lets you attach a `TimestampExtractor` bean per consumer binding. For multi-input functions, each binding may need a different timestamp extractor if sources follow different timestamp conventions.

Do not configure `WallclockTimestampExtractor` when event-time windows are intended. The wall-clock extractor uses current time at processing, losing the ability to organize records by original business occurrence time.

## 12. Timestamp Validation and Clock Skew

Timestamps are the single most critical input to windowing. One corrupt timestamp can invalidate results across many windows.

Check the following:

- Timezones and time formats; store absolute instants in UTC.
- Whether timestamps fall within reasonable past/future bounds.
- Whether producers synchronize clocks via NTP or an equivalent mechanism.
- Whether timestamps come from untrusted client devices.
- Whether replayed events retain their original event time.
- Whether brokers use `CreateTime` or `LogAppendTime`.
- Whether `TimestampExtractor` returns consistent timestamps across all records from the same source.

A record with a far-future timestamp can jump stream time ahead, closing older windows and causing subsequent events to look overly late. Reject, quarantine, or normalize anomalous timestamps before feeding them into the topology.

If a timestamp is invalid, do not silently replace it with current time unless that is an explicit business policy. Replacing timestamps can drop events into the wrong window without any audit trail.

## 13. Hopping Windows with Grace

A hopping window has both a size and an advance interval. Example computing 5-minute transaction totals updated every minute with a 90-second grace period:

~~~java
import java.time.Duration;

import org.apache.kafka.streams.kstream.TimeWindows;

TimeWindows windows = TimeWindows
    .ofSizeAndGrace(
        Duration.ofMinutes(5),
        Duration.ofSeconds(90)
    )
    .advanceBy(Duration.ofMinutes(1));
~~~

One event can update multiple open windows. With suppression enabled, each window emits its final result only when stream time passes that specific window's `end + grace`.

Account for the overhead:

- One event can belong to multiple windows.
- State store entries multiply according to overlap.
- The suppression buffer must hold pending results for multiple windows.
- Grace applies per window, so final emissions happen at staggered times.
- Downstream must identify both the key and window boundaries.

Hopping fits rolling-metric dashboards, but uses more state than tumbling. Do not make the advance interval tiny relative to window size unless frequent updates are genuinely required.

## 14. Session Windows with Grace

A session window is defined by an inactivity gap. Events with the same key are grouped into one session if gaps between them stay within the gap. A late-arriving event can extend or merge sessions, altering start/end bounds and the aggregate value.

Example with a 5-minute gap:

~~~text
Event A 10:00
Event B 10:03      -> same session
Event C 10:11      -> new session

Event D 10:07 arrives late
If sessions are still within grace and D bridges the two active regions,
Kafka Streams can merge the sessions by timestamp.
~~~

Configuration:

~~~java
SessionWindows sessions = SessionWindows
    .ofInactivityGapAndGrace(
        Duration.ofMinutes(5),
        Duration.ofMinutes(2)
    );
~~~

With session windows, boundaries can shift as late events are accepted. Downstream should not assume a session key/window that emitted an intermediate result will stay immutable. If final results are needed, use suppression for session windows and design keys/state stores appropriately.

Session windows are useful for login sessions, playback sessions, interaction sequences, or continuous device activity. Choose the inactivity gap based on domain semantics rather than merely network latency.

## 15. Grace in Stream-Stream Joins

Grace is equally critical in stream-stream joins. Two events with the same key may arrive asynchronously. The join window defines the allowed timestamp difference for pairing; grace lets out-of-order records keep participating for a window after the join window ends.

Example pairing `OrderPlaced` and `PaymentReceived` when timestamps differ by at most 10 minutes, with a 2-minute grace:

~~~java
import java.time.Duration;

import org.apache.kafka.streams.kstream.JoinWindows;

JoinWindows joinWindows = JoinWindows
    .ofTimeDifferenceAndGrace(
        Duration.ofMinutes(10),
        Duration.ofMinutes(2)
    );
~~~

Grace does not widen the join's time difference. Time difference defines whether two records are close enough to pair; grace defines how long the system still accepts out-of-order records for joining.

Clarify the following:

- Do both streams share the same key and partitioning?
- Do both sources' timestamp extractors share compatible semantics?
- Is the time difference symmetric or asymmetric (`before`/`after`)?
- How are records arriving after grace handled/dropped?
- Is state store retention sufficient for the join window plus grace?
- Can one record match multiple records on the opposite side?

If one side lags longer than grace, join outputs may be incomplete. Measure each source's latency independently; never size grace solely from the faster source.

## 16. Handling Records Dropped After Grace

Kafka Streams does not automatically send every late record to a DLQ. Once a record is past grace for a window operation, it is ignored for that window's computation. This differs from deserialization exceptions or exceptions thrown by a business processor.

To avoid losing visibility for investigation:

1. Track metrics for dropped records and event latency.
2. Selectively log key, topic, partition, offset, timestamp, and relevant window.
3. Keep raw topics long enough to allow replays/backfills.
4. Route excessively late records to a quarantine topic if business rules require separate handling.
5. Maintain a backfill or correction process when events arrive after grace.
6. Distinguish late records dropped from windows from deserialization failures or processing exceptions.

One strategy is branching a lateness check before window aggregation using the Processor API or timestamp-aware logic. That branch can forward metadata of overly stale records to a dedicated topic. However, classification must follow the same window and stream-time rules as the main topology—do not merely compare timestamps against `System.currentTimeMillis`.

Even without a quarantine branch, raw input topics and replay capability remain a safety net for investigation. However, replaying with the same application ID continues from committed offsets and existing state; you need a reset procedure or a separate backfill application ID while isolating outputs to avoid duplicate writes.

## 17. Complete Example with the Spring Cloud Stream Kafka Streams Binder

A function consuming `Purchase`, grouping by customer ID, counting orders in 5-minute windows, accepting 2-minute late records, and emitting only final results.

Because the `Serde<Purchase>` bean's generic type matches the function input, the Kafka Streams binder can infer the Serde for input values. The binder also infers `String` Serde for keys and output strings; if your application uses custom Serdes or inference fails, declare `keySerde`/`valueSerde` per binding.

~~~java
import java.time.Duration;

import java.util.function.Function;

import org.apache.kafka.common.serialization.Serde;
import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.common.utils.Bytes;
import org.apache.kafka.streams.KeyValue;
import org.apache.kafka.streams.kstream.Grouped;
import org.apache.kafka.streams.kstream.KStream;
import org.apache.kafka.streams.kstream.Materialized;
import org.apache.kafka.streams.kstream.Suppressed;
import org.apache.kafka.streams.kstream.TimeWindows;
import org.apache.kafka.streams.state.WindowStore;
import org.springframework.kafka.support.serializer.JsonSerde;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class PurchaseWindowTopology {

    @Bean
    Serde<Purchase> purchaseSerde() {
        return new JsonSerde<>(Purchase.class);
    }

    @Bean
    Function<KStream<String, Purchase>, KStream<String, String>>
            purchaseWindowCounts(Serde<Purchase> purchaseSerde) {

        return purchases -> purchases
            .filter((key, purchase) ->
                purchase != null && purchase.customerId() != null
            )
            .groupBy(
                (key, purchase) -> purchase.customerId(),
                Grouped.with(Serdes.String(), purchaseSerde)
            )
            .windowedBy(
                TimeWindows.ofSizeAndGrace(
                    Duration.ofMinutes(5),
                    Duration.ofMinutes(2)
                )
            )
            .count(
                Materialized
                    .<String, Long, WindowStore<Bytes, byte[]>>as(
                        "purchase-count-by-customer-5m"
                    )
                    .withKeySerde(Serdes.String())
                    .withValueSerde(Serdes.Long())
                    .withRetention(Duration.ofHours(1))
            )
            .suppress(
                Suppressed.untilWindowCloses(
                    Suppressed.BufferConfig.unbounded()
                )
            )
            .toStream()
            .map((windowedKey, count) -> {
                String customerId = windowedKey.key();
                long start = windowedKey.window().start();
                long end = windowedKey.window().end();

                String summary = start + "|" + end + "|" + count;
                return KeyValue.pair(customerId, summary);
            });
    }

}
~~~

In production, replace `unbounded()` with a bounded buffer and an appropriate full-buffer policy. If the output topic is compacted and holds multiple windows for the same customer, the output key must include the window start so each window gets a distinct key, e.g., `customerId + "|" + start`.

Binding configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: purchaseWindowCounts

    stream:
      bindings:
        purchaseWindowCounts-in-0:
          destination: purchases.events

        purchaseWindowCounts-out-0:
          destination: purchases.window-counts

      kafka:
        streams:
          binder:
            applicationId: purchase-window-counter-v1
~~~

If event timestamps live inside payloads, register a `TimestampExtractor` bean and configure its bean name on the input binding as shown earlier. If Kafka record timestamps already represent event time, the default extractor can be used.

## 18. Testing Windows and Late Events with TopologyTestDriver

`TopologyTestDriver` lets you pipe input records with explicit timestamps, inspect window boundaries, and verify whether late events are accepted or dropped.

Example scenario to test. The snippet below assumes `testDriver`, matching serializers/deserializers, and the topology have already been initialized in test setup:

- Window `[10:00, 10:05)`, 2-minute grace.
- Events timestamped 10:01 and 10:04 are counted.
- Event timestamped 10:03 arriving later before stream time passes 10:07 is still counted.
- A record timestamped 10:08 advances stream time past grace.
- Event timestamped 10:04 arriving afterward is excluded from the old window.
- Suppression emits only the final result once the window closes.

~~~java
import java.time.Instant;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.apache.kafka.streams.KeyValue;
import org.apache.kafka.streams.TestInputTopic;
import org.apache.kafka.streams.TestOutputTopic;

// Create input/output topics from TopologyTestDriver with matching Serdes.
TestInputTopic<String, Purchase> input = testDriver.createInputTopic(
    "purchases.events",
    stringSerializer,
    purchaseSerializer
);
TestOutputTopic<String, String> output = testDriver.createOutputTopic(
    "purchases.window-counts",
    stringDeserializer,
    stringDeserializer
);

input.pipeInput(
    "customer-42",
    new Purchase("customer-42", 100, Instant.parse("2026-11-24T10:01:00Z")),
    Instant.parse("2026-11-24T10:01:00Z")
);

input.pipeInput(
    "customer-42",
    new Purchase("customer-42", 200, Instant.parse("2026-11-24T10:04:00Z")),
    Instant.parse("2026-11-24T10:04:00Z")
);

// Out-of-order record, but window is still within grace.
input.pipeInput(
    "customer-42",
    new Purchase("customer-42", 150, Instant.parse("2026-11-24T10:03:00Z")),
    Instant.parse("2026-11-24T10:03:00Z")
);

// Send a record timestamped past 10:07 to advance stream time and close the old window.
input.pipeInput(
    "customer-99",
    new Purchase("customer-99", 50, Instant.parse("2026-11-24T10:08:00Z")),
    Instant.parse("2026-11-24T10:08:00Z")
);

// Record belonging to the old window, but arriving after the window closed.
input.pipeInput(
    "customer-42",
    new Purchase("customer-42", 75, Instant.parse("2026-11-24T10:04:30Z")),
    Instant.parse("2026-11-24T10:04:30Z")
);

List<KeyValue<String, String>> finalResults = output.readKeyValuesToList();
assertEquals(1, finalResults.size());
assertEquals("customer-42", finalResults.get(0).key);
assertTrue(finalResults.get(0).value.endsWith("|3"));
~~~

The test reads outputs by the designed key/window and verifies that `customer-42`'s final count is 3, not 4. With suppression enabled, output for the old window only appears after the 10:08 record pushes stream time past the close mark.

Notes:

- `advanceWallClockTime` is not a substitute for advancing stream time with record timestamps.
- To test late records, control input record timestamps directly.
- Test records right on window boundaries, e.g., timestamp 10:05 belongs to the next window.
- Test abnormally futuristic event timestamps.
- Test with no new records to confirm suppression does not emit merely because wall-clock time elapses.
- Test hopping/session windows separately since their window semantics differ from tumbling.

## 19. Integration Testing with Real Kafka

Unit tests verify DSL logic, while integration tests must verify the binder, timestamp extractors, Serdes, and broker.

Use Testcontainers Kafka or a test Kafka environment to verify:

1. The function bean activates and input/output bindings point to the right topics.
2. Kafka record timestamps or custom `TimestampExtractor`s are used properly.
3. Payloads whose event time differs from Kafka timestamps land in the right window.
4. Out-of-order events within grace update the aggregate.
5. Events after grace do not alter the final aggregate.
6. Suppression emits a single final result once stream time passes `end + grace`.
7. Restarting the application restores the state store without losing aggregates.
8. Output keys retain both customer ID and window identity.
9. Window retention and changelogs function under production-like settings.
10. Metrics/logs for dropped records are observable.

Do not simply sleep for 2 minutes in tests. Drive stream time using record timestamps. Tests will run fast, deterministically, and independently of CI runner clocks.

## 20. Observability and Production Operations

A windowed topology needs visibility into both data latency and processing progress.

Monitor:

- Processing lag of input partitions.
- Event arrival delay relative to event time.
- Task stream time and its gap behind latest event time.
- Records dropped due to exceeding grace or invalid timestamps.
- Open window counts and data volume in state stores.
- Suppression buffer usage and buffer-limit hit counts.
- State store restoration duration after restarts.
- Rebalances, task migrations, and consumer errors.
- Rates of anomalous event timestamps or clock skew.
- Replay/backfill frequency and reprocessed record counts.

Exact metric names depend on the Kafka Streams, binder, and exporter versions. Discover available metrics in your actual runtime instead of hard-coding metric names from another version. Investigation logs should include topic, partition, offset, key, record timestamp, window start/end, and application ID.

If grace is increased in production, check its impact on suppression buffers and output emission timing. If grace is reduced, determine whether older records may be dropped more often and require backfilling.

## 21. Common Mistakes

| Symptom | Cause | Resolution |
|---|---|---|
| Late events fall into the wrong window | Using processing time instead of event time | Check Kafka timestamps and `TimestampExtractor` |
| Out-of-order events are dropped too early | Grace is too short or stream time jumped ahead | Measure real latency and pick an appropriate grace period |
| Final results never appear | Stream time has not passed `end + grace` | Check timestamps of new records and suppression settings |
| Wall clock passed the window yet no output emits | Stream time does not advance without records | Understand stream-time semantics; do not rely on sleep |
| Results emit multiple times | `KTable` converted to `KStream` without suppression | Accept upsert semantics or use `untilWindowCloses` |
| Downstream double-counts totals | Treating `KTable` updates as independent events | Upsert by key/window or consume final-only outputs |
| State store grows excessively | Window/hopping/grace/retention too large | Measure key cardinality and narrow scopes appropriately |
| Suppression buffer fills up | Many open windows or long grace | Bound the buffer, monitor it, and choose an overflow policy |
| Windows close prematurely | Future timestamps or clock skew | Validate event times and source clocks |
| Joins miss data | Join grace insufficient or sources have asymmetric latency | Measure each source independently; tune time difference and grace |
| Replaying fails to fix results | Replayed data is still too late relative to current stream time/state | Use a backfill/reset workflow with isolated outputs |
| Tests hang waiting for results | Test only advances wall clock | Pipe records with newer timestamps to advance stream time |

## 22. Pre-Implementation Design Checklist

| Item | Question to Answer |
|---|---|
| Event time | Do timestamps come from the producer, broker, or payload? |
| Timestamp extractor | Is a custom extractor needed per input binding? |
| Clocks | Do sources synchronize to UTC and enforce future-timestamp bounds? |
| Window type | Does the domain fit tumbling, hopping, sliding, or session? |
| Window boundaries | Do start/end bounds match desired semantics? |
| Grace | What is the source's p99 latency? |
| Stream time | Is everyone clear that stream time only advances as tasks process records? |
| Late events | Are post-grace records dropped, quarantined, or backfilled? |
| Output | Emit intermediate updates or final-only results? |
| Suppression | Is the buffer bounded with an explicit overflow policy? |
| Retention | Does the state store retain at least `window size + grace`? |
| Keys | Do output keys preserve window identity? |
| Recovery | Can changelogs and local state recover across restarts? |
| Testing | Are boundaries, out-of-order, post-grace, and idle streams tested? |
| Monitoring | Are latency, dropped records, state size, and restore duration tracked? |

## 23. Hands-On Exercise and Completion Criteria

Build a topology counting orders per customer in 5-minute windows:

1. Create topic `purchases.events` keyed by customer ID.
2. Define event time as `occurredAt` in the payload.
3. Write a `TimestampExtractor` and attach it to the input binding.
4. Create a `KStream` and group by customer ID.
5. Use a 5-minute tumbling window with a 2-minute grace period.
6. Materialize the state store with a clear name and retention of at least 7 minutes.
7. Run a sequence of records in chronological order and verify counts.
8. Send an out-of-order event before stream time passes `end + grace`; verify the count increases.
9. Advance stream time past `end + grace`, then send an event belonging to the old window; verify the count stays unchanged.
10. Compare continuous outputs against outputs using `Suppressed.untilWindowCloses`.
11. Test records landing exactly on window boundaries.
12. Test abnormally futuristic timestamps and event replays.
13. Write `TopologyTestDriver` tests for late events and suppression.
14. Run integration tests with the Kafka binder and a real broker.
15. Document choices for grace, retention, output semantics, and handling excessively late records.

You have completed the exercise when you can explain event time, processing time, and stream time; calculate window and grace boundaries; predict which records are accepted or dropped; distinguish grace from retention; choose between intermediate and final emissions; and test topology behavior under late-arriving data.

## 24. Official References

- [Apache Kafka Streams — Streams DSL: Windowing and Grace](https://kafka.apache.org/41/streams/developer-guide/dsl-api/) — tumbling, hopping, sliding, session windows, grace periods, late records, and final window results.
- [Apache Kafka Streams — Upgrade Guide](https://kafka.apache.org/41/streams/upgrade-guide/) — grace API changes and removal of the 24-hour default grace period.
- [Apache Kafka Streams — Configuring a Streams Application](https://kafka.apache.org/41/streams/developer-guide/config-streams/) — timestamps, state stores, and runtime configuration.
- [Apache Kafka Streams — Application Reset Tool](https://kafka.apache.org/41/streams/developer-guide/app-reset-tool/) — reset/replay workflow when rebuilding state.
- [Spring Cloud Stream — Kafka Streams Binder: Timestamp Extractor](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/timestamp-extractor.html) — declaring `TimestampExtractor` beans and configuring them per input binding.
- [Spring Cloud Stream — Kafka Streams Binder Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/configuration-options.html) — binder configuration and Kafka Streams properties.
- [Apache Kafka — TimeWindows API](https://kafka.apache.org/41/javadoc/org/apache/kafka/streams/kstream/TimeWindows.html) — configuring size, advance interval, and grace.
- [Apache Kafka — Suppressed API](https://kafka.apache.org/41/javadoc/org/apache/kafka/streams/kstream/Suppressed.html) — buffers, `untilWindowCloses`, and full-buffer policies.
