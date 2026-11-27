# Distinguishing Event Time, Processing Time, and Configuring TimestampExtractor

In event stream processing, a record may be created at one moment, received by Kafka at another, and only processed by the application later. These three timestamps are not synonymous. Using the wrong kind of time can cause statistical windows, time-based joins, and latency reports to produce incorrect results, especially when data arrives late or is replayed.

Kafka Streams assigns a timestamp to each record before executing time-dependent operations. The component that determines that timestamp is **TimestampExtractor**. The Spring Cloud Stream Kafka Streams Binder lets you register extractors as Spring beans and select a bean per input binding. Thus, an application can use a business timestamp in the payload as event time, use broker-assigned metadata timestamps as ingestion time, or use the system clock when processing-time semantics are genuinely required.

## 1. Three Timestamps in an Event Stream

Suppose a sensor records a temperature at 10:00:00, the device sends the record at 10:00:03, the Kafka broker writes the record to the topic at 10:00:04, and the application only processes it at 10:00:12. An event has at least three notable milestones:

| Concept | Meaning | Example |
|---|---|---|
| Event time | When the event actually occurred at the source | Sensor measures temperature at 10:00:00 |
| Ingestion time | When the broker appends the record to a topic partition | Kafka appends record at 10:00:04 |
| Processing time | When the stream application actually processes the record | Kafka Streams processes at 10:00:12 |

Event time answers "what happened when?". Ingestion time answers "when did Kafka receive and persist the event?". Processing time answers "when did the application process the event?".

Latency can be computed across pairs of milestones:

- Publish delay: ingestion time minus event time.
- Processing delay: processing time minus ingestion time.
- End-to-end delay: processing time minus event time.

These calculations are only reliable when clocks across producers, brokers, and applications are reasonably synchronized. If a source device's clock drifts by several minutes, event time still reflects the timestamp sent by the device rather than necessarily the exact real-world moment.

## 2. How Do Event Time and Processing Time Differ?

**Event time** is tied to the business content of the event. For example, an order is paid at 09:58, but due to an unstable network it only reaches Kafka at 10:04. If the system aggregates revenue per minute, that payment still belongs to minute 09:58.

**Processing time** is tied to when the application processes the record. In the example above, the application processes it at 10:04. Under processing time, the revenue is recorded in minute 10:04.

This difference stands out when data arrives late or out of order:

- Event-time windowing groups events by when they occurred, even if they arrive late.
- Processing-time windowing groups events by when the application receives and processes them.
- When replaying a topic from older offsets, processing time changes with each run; event time stored inside the data can stay unchanged.
- When historical business analysis is needed, event time is usually the better anchor.
- When measuring actual load, queuing time in the system, or operational responsiveness, processing time can be more useful.

No single time type fits every use case. Choose based on the meaning of the calculation, then ensure producers and consumers agree on how timestamps are interpreted.

## 3. Kafka Also Has Broker-Recorded Timestamps

Kafka stores a timestamp in record metadata. This timestamp can be the time supplied by the producer or the time the broker appends the record, depending on topic/broker configuration.

Kafka supports two main types:

| Kafka timestamp type | Stored timestamp | Meaning when read by Kafka Streams |
|---|---|---|
| CreateTime | Timestamp in `ProducerRecord` sent by the producer | Can represent event time if the producer sets it to the event occurrence time |
| LogAppendTime | Timestamp assigned by the broker upon appending to the partition | Represents ingestion time |

The topic property is **message.timestamp.type**; the broker default is typically controlled by **log.message.timestamp.type**. The common default is **CreateTime**. With CreateTime, Kafka preserves the producer-supplied timestamp, within timestamp validation bounds configured on the broker. With LogAppendTime, the broker overwrites the timestamp with the append time.

Important point: CreateTime does not automatically guarantee the timestamp is the business occurrence time. If the producer does not explicitly set the timestamp to the event time, the Kafka client typically uses the current time when constructing the record. In that case, CreateTime is closer to when the producer sent the record than when the event actually happened.

For example, the producer needs to set the timestamp from the event's **occurredAt** field if you want Kafka metadata to carry event time:

~~~java
Instant occurredAt = event.occurredAt();

ProducerRecord<String, OrderEvent> record =
    new ProducerRecord<>(
        "orders.created",
        null,
        occurredAt.toEpochMilli(),
        event.customerId(),
        event
    );

kafkaProducer.send(record);
~~~

This example uses the Kafka producer directly to illustrate the `ProducerRecord` timestamp field. When using the Spring Cloud Stream Kafka Streams Binder, producer bindings and serialization configuration may be managed separately; do not assume having an `occurredAt` field in the payload automatically populates Kafka record metadata with that value.

If producers cannot populate metadata with event time, Kafka Streams can read the timestamp field from the payload using a custom `TimestampExtractor`. This separates business semantics from the default timestamp assigned by the producer or broker.

## 4. How Does Kafka Streams Use Timestamps?

Kafka Streams invokes `TimestampExtractor` to obtain a timestamp for each input record. That timestamp is used in time-dependent operations such as:

- Tumbling, hopping, and sliding windows.
- Session windows.
- Time-bounded stream-stream joins.
- Stream-time progression and handling out-of-order records.
- Stream-time punctuations.

`TimestampExtractor` assigns a timestamp to the record, but does not reorder the Kafka log. Within a partition, records are still read in offset order. Event time may rise, fall, or arrive out of order. Kafka Streams uses the timestamp and operator semantics to determine windows or joins rather than turning the topic into an event-time-sorted log.

For example, the same partition may contain:

~~~text
Offset 100: eventTime = 10:00:10
Offset 101: eventTime = 10:00:35
Offset 102: eventTime = 10:00:20
~~~

The record at offset 102 arrives later yet has an earlier event time than offset 101. This is an out-of-order event. If the application uses event time, it can still update the 10:00:00–10:01:00 window as long as the window's grace period has not expired.

## 5. Stream-Time Is Data-Driven Time Progression

Kafka Streams uses the concept of **stream-time** to track time progression for a task. Stream-time is updated based on the timestamps of processed records; essentially, it is the highest timestamp the task has observed so far. It is data-driven time, not wall-clock time.

For instance, a task processes a record with timestamp 10:00:10, then 10:00:35, and then receives an older record with timestamp 10:00:20. Stream-time remains 10:00:35. An older record does not move the task's clock backward.

Stream-time has an important operational characteristic: if no new records arrive, stream-time does not advance merely because the system clock keeps ticking. Consequently, an event-time window may not yet be considered past its grace period if traffic stops arriving, even though several minutes of real time have passed.

Processing-time based on the system clock behaves differently. Kafka Streams also supports wall-clock-time punctuations, which can run on a schedule even without new records. These two notions of time serve different purposes:

| Mechanism | Time Used | Advances Without New Records? |
|---|---|---|
| Event-time / stream-time | Timestamp extracted from records | No |
| Processing-time / wall-clock-time | System clock | Yes, for tasks scheduled by wall-clock |

## 6. What Is TimestampExtractor?

**TimestampExtractor** is the Kafka Streams interface used to extract a timestamp from a `ConsumerRecord`. Its primary method looks like:

~~~java
long extract(ConsumerRecord<Object, Object> record, long partitionTime);
~~~

Two parameters:

- **record**: current Kafka record, including topic, partition, offset, key, value, headers, and timestamp metadata.
- **partitionTime**: highest valid timestamp extracted from a prior record in the same topic partition; may be **-1** if no prior reference timestamp exists.

The return value must be milliseconds since the Unix epoch (00:00:00 UTC on 1970-01-01). Kafka Streams requires a positive timestamp; zero or negative timestamps are considered invalid in current APIs. An extractor should be stateless: do not store mutable state in fields to infer timestamps across records. If you need the previous timestamp, Kafka Streams provides `partitionTime`.

Do not use a timezone-less `LocalDateTime` as a timestamp. Convert an explicit instant with timezone semantics such as `Instant` to epoch milliseconds:

~~~java
long timestamp = event.occurredAt().toEpochMilli();
~~~

Do not return seconds when Kafka Streams expects milliseconds. For example, timestamp 1,700,000,000 in milliseconds falls in 1970, whereas the same number interpreted as seconds falls around 2023. The wrong unit places records into completely wrong windows.

## 7. Default and Built-In Extractors

By default, Kafka Streams uses **FailOnInvalidTimestamp**. This extractor reads the Kafka record's timestamp metadata. If the timestamp is invalid (negative), it throws an exception instead of silently skipping the record.

Built-in implementations include:

| Extractor | Behavior | Use Case |
|---|---|---|
| FailOnInvalidTimestamp | Reads metadata timestamp; fails on negative timestamp | Default when you want to detect records missing timestamps |
| LogAndSkipOnInvalidTimestamp | Logs a warning and returns an invalid timestamp so the record is skipped | Only when policy permits dropping bad records |
| UsePartitionTimeOnInvalidTimestamp | Uses valid metadata timestamp; if invalid, estimates using prior `partitionTime`, fails if no prior value exists | Legacy data missing timestamps where partition-based estimation is acceptable |
| WallclockTimestampExtractor | Returns current processing machine time | When processing-time semantics are desired |

Be cautious with **LogAndSkipOnInvalidTimestamp**. Records with negative timestamps will not be processed; logging a warning does not mean the record was routed to a DLQ. If data loss is unacceptable, choose an intentional strategy, such as failing to halt the pipeline for investigation or routing invalid records to a separate quarantine stream.

**UsePartitionTimeOnInvalidTimestamp** does not recover the true original event time. It simply uses the latest valid timestamp observed in the same partition as an estimate for records missing timestamps. If the partition has not yet seen a valid timestamp, the extractor cannot estimate.

**WallclockTimestampExtractor** reads neither payload timestamps nor metadata timestamps. It returns system time when the record is processed. Replaying the same record on another day yields a different timestamp, and processing-time windowing results may differ.

## 8. Writing a TimestampExtractor Reading Business Time From Payload

Suppose order events have this structure:

~~~java
import java.math.BigDecimal;
import java.time.Instant;

public record OrderEvent(
    String eventId,
    String customerId,
    Instant occurredAt,
    BigDecimal amount
) {}
~~~

The application needs to count orders per customer in five-minute windows. The **occurredAt** field is the business timestamp to use as event time.

Custom extractor:

~~~java
import java.time.Instant;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.streams.errors.StreamsException;
import org.apache.kafka.streams.processor.TimestampExtractor;

public final class OrderEventTimestampExtractor
        implements TimestampExtractor {

    @Override
    public long extract(
            ConsumerRecord<Object, Object> record,
            long partitionTime) {

        Object value = record.value();

        if (!(value instanceof OrderEvent event)) {
            throw new StreamsException(
                "Expected OrderEvent in topic " + record.topic()
            );
        }

        Instant occurredAt = event.occurredAt();

        if (occurredAt == null) {
            throw new StreamsException(
                "Missing occurredAt for event " + event.eventId()
            );
        }

        long timestamp = occurredAt.toEpochMilli();

        if (timestamp <= 0) {
            throw new StreamsException(
                "Invalid event timestamp for event " + event.eventId()
            );
        }

        return timestamp;
    }
}
~~~

Key characteristics of this extractor:

- Extracts the timestamp from the business field `occurredAt`, independent of producer or broker timestamps.
- Converts `Instant` into epoch milliseconds.
- Holds no mutable state and does not depend on invocation order.
- Does not substitute invalid timestamps with current system time.
- Throws `StreamsException` if the payload or business timestamp is invalid so errors are caught and handled per application policy.

In production, define a clear strategy for records missing `occurredAt`: fail to fix the upstream source, route to a quarantine topic via an appropriate error handler, or use an estimated timestamp if business rules permit. Avoid silently falling back to processing time because that mixes two semantics within the same stream.

## 9. Registering the Extractor in the Spring Cloud Stream Kafka Streams Binder

The Kafka Streams Binder lets you register a `TimestampExtractor` as a Spring bean, then reference that bean by name on each consumer input binding.

Example bean:

~~~java
import org.apache.kafka.streams.processor.TimestampExtractor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class StreamTimeConfiguration {

    @Bean
    TimestampExtractor orderEventTimestampExtractor() {
        return new OrderEventTimestampExtractor();
    }
}
~~~

Example event-processing function:

~~~java
import java.time.Duration;
import java.util.function.Function;

import org.apache.kafka.common.utils.Bytes;
import org.apache.kafka.streams.kstream.KStream;
import org.apache.kafka.streams.kstream.KTable;
import org.apache.kafka.streams.kstream.Materialized;
import org.apache.kafka.streams.kstream.TimeWindows;
import org.apache.kafka.streams.kstream.Windowed;
import org.springframework.context.annotation.Bean;

@Bean
Function<KStream<String, OrderEvent>,
        KTable<Windowed<String>, Long>> countOrders() {

    return orders -> orders
        .filter((customerId, event) -> customerId != null && event != null)
        .groupByKey()
        .windowedBy(
            TimeWindows.ofSizeAndGrace(
                Duration.ofMinutes(5),
                Duration.ofMinutes(1)
            )
        )
        .count(
            Materialized
                .<String, Long, org.apache.kafka.streams.state.WindowStore<Bytes, byte[]>>
                    as("orders-by-customer-window")
        );
}
~~~

Binding configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: countOrders
    stream:
      bindings:
        countOrders-in-0:
          destination: orders.created
      kafka:
        streams:
          bindings:
            countOrders-in-0:
              consumer:
                timestampExtractorBeanName: orderEventTimestampExtractor
~~~

The input binding name derived from the function name is **countOrders-in-0**. The **timestampExtractorBeanName** property points to the Spring bean name. If a function has multiple inputs, you can assign different extractors per input binding. Any input without a custom extractor uses Kafka Streams' default configuration.

The DSL example above uses event time from `occurredAt` to group events into five-minute windows with a one-minute grace period. Key/value Serdes and `Materialized` configuration should be set appropriately for your project's dependencies and Kafka Streams version. The snippet focuses on illustrating how the extractor supplies timestamps to windowing operations.

## 10. Event-Time Windows and Late-Arriving Events

An event may arrive after the event-time window it belongs to has already started or even nearly ended. Kafka Streams uses stream-time and the grace period to decide whether late records are still accepted.

Suppose a five-minute window starts at 10:00 and ends at 10:05, with a one-minute grace period:

- Event with `occurredAt` 10:02 arrives at 10:03: processed in window 10:00–10:05.
- Event with `occurredAt` 10:01 arrives at 10:05:20: can still be accepted if stream-time has not passed 10:06.
- Once stream-time exceeds 10:06, records belonging to this window are deemed too late and excluded from the window's computation.

The grace period is not a fixed timer measured from broker arrival. It is evaluated against the task's stream-time. Without new records, stream-time does not advance with the system clock.

Illustrative diagram:

~~~text
Event time:
10:00                 10:05          10:06
  |--------------------|--------------|
  <--- 5-min window ---> < 1-min grace >

Late record with event time 10:02:
  - Before stream-time passes 10:06: can be accepted
  - After stream-time passes 10:06: too late for this window
~~~

A larger grace period lets the system accept late data longer, but window state must be retained longer and final outputs are delayed. Too small a grace period can drop valid records delayed by slow networks or source devices. Choose based on real producer lateness distributions.

## 11. Processing Time with WallclockTimestampExtractor

When the goal is processing based on when the application actually receives records, you can use **WallclockTimestampExtractor**:

~~~java
import org.apache.kafka.streams.processor.TimestampExtractor;
import org.apache.kafka.streams.processor.WallclockTimestampExtractor;

@Bean
TimestampExtractor processingTimeExtractor() {
    return new WallclockTimestampExtractor();
}
~~~

Configuration on the input binding:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          bindings:
            liveMetrics-in-0:
              consumer:
                timestampExtractorBeanName: processingTimeExtractor
~~~

Each record gets the system clock timestamp when the extractor runs. This is useful for certain operational measurements, such as grouping records by when the consumer processes them.

However, there are trade-offs:

- Replaying the same record at a different time gives a different timestamp.
- Windowing may yield different results between the initial run and a replay.
- Two instances with skewed clocks can produce inconsistent timestamps.
- When the application pauses and no new records arrive, stream-time still does not advance; the extractor is only invoked when a record is processed.
- `WallclockTimestampExtractor` does not replace a wall-clock task scheduler.

If the goal is running a periodic task even with no incoming messages, use a scheduler or Processor API punctuation with **WALL_CLOCK_TIME**. If the goal is running as stream-time advances, use punctuation with **STREAM_TIME**. These two mechanisms differ:

~~~java
context.schedule(
    Duration.ofSeconds(30),
    PunctuationType.STREAM_TIME,
    timestamp -> {
        // Runs when stream-time advances far enough to the next interval.
    }
);

context.schedule(
    Duration.ofSeconds(30),
    PunctuationType.WALL_CLOCK_TIME,
    timestamp -> {
        // Runs according to the system clock, even when the stream has no new records.
    }
);
~~~

The punctuation example belongs to the Processor API; exact APIs and `ProcessorContext` setup depend on the Kafka Streams version. Do not use wall-clock punctuation to simulate event-time windowing.

## 12. Handling Invalid Timestamps

Invalid timestamps (zero or negative per current API requirements) can occur when:

- Legacy producers omit timestamp metadata.
- Producers send negative values or use the wrong unit.
- Payloads lack `occurredAt`.
- Source data uses ambiguous timezones.
- Timestamps break during schema or data-type conversions.
- Source device clocks experience severe skew.

Options must be decided based on business rules:

| Policy | Behavior | Risk |
|---|---|---|
| Fail fast | Throws exception and stops/lets the task handle the error | Can halt pipeline progress, but prevents silent metric corruption |
| Log and skip | Drops invalid-timestamp record and logs a warning | Loses data from computations |
| Use partition time | Estimates using latest valid timestamp in the partition | No longer exact event time |
| Quarantine | Routes invalid records to a separate investigation stream | Requires extra topology, permissions, and operational workflow |
| Wall-clock fallback | Uses consumer processing time | Mixes event time and processing time; non-deterministic replays |

Never return a negative timestamp to represent "unknown". Kafka Streams may drop the record without processing it. If a timestamp cannot be determined and data loss is unacceptable, throw an error or route the record to quarantine by explicit design.

If using `partitionTime` as a fallback, emit a metric counting fallback occurrences. Do not treat estimated values as exact business timestamps. If the partition has never seen a valid timestamp, `partitionTime` can be `-1` and cannot serve as a fallback.

## 13. Clocks, Timezones, and Timestamp Skew

`TimestampExtractor` returns epoch milliseconds, meaning milliseconds since the Unix epoch in UTC. In payloads, use representations with explicit timezones such as ISO-8601 with offset or UTC:

~~~json
{
  "eventId": "evt-9001",
  "customerId": "customer-42",
  "occurredAt": "2026-11-24T03:15:30Z",
  "amount": 125000
}
~~~

If a source sends local time without a timezone, the application cannot tell whether it is UTC or a local timezone. Standardize schemas and timezone conventions across producers.

Synchronize clocks using NTP or an equivalent mechanism. If producers use CreateTime, Kafka brokers may enforce timestamp-difference limits relative to broker time and reject records too far off. If using LogAppendTime, the broker replaces the timestamp with append time, so metadata no longer reflects event time.

Validate the following conditions:

- Timestamp is not too far in the future.
- Timestamp is not older than business rules allow.
- Units are always milliseconds entering Kafka Streams.
- Never use timezone-less `LocalDateTime` for cross-system data.
- Retain the source's original timestamp if auditing is needed.
- Track clock skew and fallback/quarantine record rates.

## 14. Timestamp Propagation Through Kafka Streams Operations

Timestamps affect more than source records. Kafka Streams also determines output record timestamps depending on the operation:

- Stateless transformations generally preserve the input record's timestamp.
- Operations producing multiple records from one input typically propagate the input's timestamp.
- Aggregation results may carry the maximum timestamp among contributing records.
- Stream-stream or table-table join outputs typically use the greater timestamp of the two input records.
- Outputs emitted from punctuation may use the task's internal time at the moment of punctuation.

This matters when chaining multiple topologies or topics. If an operator alters the timestamp, downstream windowing uses the new timestamp. When you need to preserve the original business timestamp, verify operator semantics and consider keeping `occurredAt` in the payload for auditing.

Do not equate output record metadata timestamps with every timestamp in the payload. An event may hold multiple milestones: `occurredAt`, `receivedAt`, `processedAt`. Kafka metadata carries only one timestamp per record; the payload can retain the rest for latency measurement and investigation.

## 15. TimestampExtractor and Multiple Input Bindings

A Kafka Streams function can have multiple input bindings, for example:

- **process-in-0** receives `OrderEvent` from the orders topic.
- **process-in-1** receives `PaymentEvent` from the payments topic.
- **process-in-2** receives `CustomerSnapshot` from the customers topic.

Each input may require different timestamp semantics. `OrderEvent` might use `occurredAt`, `PaymentEvent` might use `settledAt`, while `CustomerSnapshot` might use Kafka's metadata timestamp.

The Spring Cloud Stream Kafka Streams Binder lets you select a `TimestampExtractor` per binding. The full prefix is **spring.cloud.stream.kafka.streams.bindings.<binding-name>.consumer**:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          bindings:
            process-in-0:
              consumer:
                timestampExtractorBeanName: orderTimestampExtractor
            process-in-1:
              consumer:
                timestampExtractorBeanName: paymentTimestampExtractor
~~~

Both beans must be declared in the Spring context. If a binding omits this setting, the binder uses the default timestamp extractor for that binding.

When joining two streams, timestamp semantics must be aligned or at least clearly understood. If one stream uses event time while the other uses ingestion time, records may miss join windows unexpectedly. Before joining, establish which timestamp represents the shared business concept.

## 16. Testing Timestamps and Windowing

Do not stop at unit testing that an extractor returns a positive number. Test how the topology behaves with out-of-order and late records too.

Use Kafka Streams **TopologyTestDriver** to test topology logic without a real broker. Example creating an input topic and piping records with specific timestamps:

~~~java
inputTopic.pipeInput(
    "customer-42",
    new OrderEvent(
        "evt-1001",
        "customer-42",
        Instant.parse("2026-11-24T03:00:10Z"),
        new BigDecimal("100000")
    ),
    Instant.parse("2026-11-24T03:00:10Z")
);
~~~

If the topology uses a custom extractor reading `occurredAt` from the payload, the timestamp passed to `TestInputTopic` does not override the `occurredAt` value chosen by the extractor. Tests should explicitly verify which timestamp is actually used for windowing.

Cases to test:

1. Valid event time producing accurate epoch milliseconds.
2. Timestamp prior to Unix epoch or null `occurredAt` field.
3. Wrong payload type or unsupported schema version.
4. Two records in the same partition arriving in ascending event-time order.
5. Record with an older event time arriving after a newer record.
6. Record arriving within the grace period updating the window.
7. Record arriving after stream-time passes `end + grace` being excluded from the window.
8. `WallclockTimestampExtractor` assigning timestamps at test execution time.
9. Replaying the same data with event time yielding stable results.
10. Multiple input bindings using separate extractors and joining under aligned semantics.

`TopologyTestDriver` is ideal for testing time and window logic. Integration tests with a real Kafka broker are still necessary to verify whether the topic timestamp type is `CreateTime` or `LogAppendTime`, whether producers set metadata properly, and whether binder configuration actually wires the intended extractor bean.

## 17. Monitoring Latency and Timestamp Quality

A production pipeline should monitor both latency and timestamp quality:

| Metric | Meaning |
|---|---|
| Event-to-ingestion delay | Gap between event time and ingestion time |
| Ingestion-to-processing delay | Time a record waits before processing |
| Event-to-processing delay | End-to-end business delay |
| Invalid timestamp count | Records lacking a valid timestamp |
| Timestamp fallback count | Occurrences of `partitionTime` or other fallbacks |
| Late record count | Records dropped due to exceeding grace period |
| Stream-time lag | Difference between wall-clock time and observed stream-time |
| Window update latency | Time from event occurrence until aggregate updates |

When logging invalid records, include topic, partition, offset, `eventId`, metadata timestamp, and payload timestamp if present. Do not log full sensitive payloads.

Distinguish late records from records delayed by a processing backlog. Old event time may be valid late-arriving data; high processing-time lag may mean consumers cannot keep up. Both issues require different remedies.

## 18. Choosing Semantics by Use Case

| Use Case | Recommended Timestamp | Reason |
|---|---|---|
| Computing revenue by payment time | Event time from `settledAt` | Late-arriving transactions still fall into the right business interval |
| Counting sensor readings by measurement time | Event time from sensor timestamp | Preserves device measurement timing |
| Measuring message dwell time in broker | Ingestion time and processing time | Measures backlog and consumption delay |
| Current processing-rate dashboard | Processing time | Reflects live consumer activity |
| Replaying history for recomputation | Stable event time in payload | Windowing results are reproducible |
| Receiving records from producers with uncontrolled timestamps | `LogAppendTime` or gateway-normalized timestamp | Reduces dependence on source clocks |

If business logic requires historical analysis and tolerates late events, event time is usually the primary choice. If the system needs operational statistics by receipt or processing time, ingestion/processing time fits better. All three milestones can be stored simultaneously in payloads or telemetry for auditing and analysis.

## 19. Common Errors

| Symptom | Cause | Resolution |
|---|---|---|
| Windows contain data shifted by minutes/hours | Timestamp uses wrong timezone or seconds instead of milliseconds | Standardize on `Instant`/UTC and verify epoch milliseconds |
| Late events get dropped | Stream-time already passed `end + grace` | Tune grace based on late-arrival distribution and verify timestamp extractor |
| Replays produce different results from initial run | Using processing-time extractor or clock-dependent timestamps | Use stable event time when reproducibility is needed |
| Records silently disappear without output | Extractor returns negative timestamp or uses `LogAndSkipOnInvalidTimestamp` | Choose fail/quarantine policy and monitor invalid timestamps |
| Joins miss windows | Two inputs use different timestamp semantics | Align the event-time contract across inputs |
| Default timestamp is not event time | Producer lets Kafka auto-assign `CreateTime` from send clock | Set `ProducerRecord` timestamp or use a custom extractor |
| Stream-time stalls when topic goes quiet | Stream-time only advances on new records | Use wall-clock punctuation for clock-driven tasks |
| Event time lies in the future | Source clock skew or bad data | Check clock skew, enforce timestamp bounds, and quarantine |
| One binding uses the wrong extractor | Wrong bean name or wrong binding name | Check function definition and `timestampExtractorBeanName` |

## 20. Production Deployment Checklist

- Clearly define whether business logic requires event time, ingestion time, or processing time.
- Specify timestamps in schemas using UTC/`Instant` or epoch milliseconds.
- If using `CreateTime`, ensure producers set timestamps with the intended semantics.
- If using `LogAppendTime`, account for the Kafka broker replacing timestamps with append time.
- Keep `TimestampExtractor` stateless and return valid epoch milliseconds.
- Choose an invalid-timestamp policy: fail, skip, estimate, or quarantine.
- Never silently mix event time with processing time.
- Register extractor beans and map them accurately to each input binding.
- Align timestamp semantics before joining multiple streams.
- Choose grace periods based on real late-arrival distributions.
- Monitor stream-time, late records, timestamp fallbacks, and end-to-end latency.
- Test replay, out-of-order events, invalid timestamps, and window closing.
- Use integration tests to verify topic timestamp types and real Kafka metadata.
- Synchronize clocks across producers, brokers, and consumers; guard against future or overly stale timestamps.

## 21. References

- [Spring Cloud Stream — Timestamp Extractor](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/timestamp-extractor.html), registering `TimestampExtractor` beans and configuring per input binding.
- [Spring Cloud Stream Kafka Streams Binder — Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/configuration-options.html), Kafka Streams Binder consumer properties.
- [Apache Kafka Streams — Core Concepts](https://kafka.apache.org/44/streams/core-concepts/), event time, processing time, ingestion time, stream-time, and windowing.
- [Apache Kafka Streams — Configuring a Streams Application](https://kafka.apache.org/44/streams/developer-guide/config-streams/), `default.timestamp.extractor` and built-in extractors.
- [Apache Kafka — TimestampExtractor API](https://kafka.apache.org/44/javadoc/org/apache/kafka/streams/processor/TimestampExtractor.html), `extract` signature, `partitionTime`, and timestamp requirements.
- [Apache Kafka — Topic Configs](https://kafka.apache.org/44/configuration/topic-configs/), `message.timestamp.type` and timestamp limits.

Event time captures when business events occur, ingestion time captures when brokers store records, and processing time captures when applications process them. Kafka Streams uses `TimestampExtractor` to feed one of those semantics into stream-time and time-dependent operations. When timestamps are standardized, extractors are properly configured per input binding, grace periods reflect real latency, and invalid-timestamp policies are explicitly defined, windows and joins produce far more consistent results under late, out-of-order, or replayed data.
