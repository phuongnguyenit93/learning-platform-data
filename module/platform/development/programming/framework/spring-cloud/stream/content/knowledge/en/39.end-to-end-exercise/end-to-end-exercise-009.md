# Windowed Device Telemetry Aggregation with Kafka Streams Binder

An IoT system can receive thousands of temperature and humidity measurements per second from many devices. If an application merely stores raw messages, analytics consumers have to manually group records, compute averages, and determine time intervals. Kafka Streams can perform this directly on the event stream: routing records by device, grouping them into time windows, maintaining aggregate state, and emitting summaries to another topic.

This exercise builds a Spring Cloud Stream pipeline using the Kafka Streams Binder. Each event carries a device ID, measurement timestamp, temperature, and humidity. The application groups by device ID, aggregates over one-minute tumbling windows with a 15-second grace period for late events, and outputs a summary per device and window.

The material combines the `Supplier`/`Function`/`Consumer` functional model, binders, Kafka Streams DSL, event-time, Serdes, state stores, testing, and operations. Examples target Java 17+ and a Kafka Streams version providing `TimeWindows.ofSizeAndGrace`; use a Spring Boot, Spring Cloud release train, and Kafka Streams Binder version aligned via your project BOM.

## 1. Expected Outcome and Architecture

The data source emits records like:

| deviceId | eventTime | temperatureC | humidityPercent |
|---|---|---:|---:|
| `sensor-101` | 10:00:05 | 26.2 | 61.0 |
| `sensor-101` | 10:00:18 | 26.8 | 60.5 |
| `sensor-205` | 10:00:21 | 24.1 | 55.0 |
| `sensor-101` | 10:00:54 | 27.0 | 60.0 |
| `sensor-205` | 10:01:02 | 24.4 | 54.5 |

For the one-minute window starting at 10:00:00, the result for `sensor-101` can include reading count, average, minimum, and maximum temperature, and average humidity. `sensor-205` receives its own summary. Subsequent windows do not overwrite earlier window results because the output key includes both the device ID and the window start timestamp.

Overall architecture:

    IoT devices
        |
        v
    telemetry producer
        |
        v
    Kafka topic: device-readings
        |
        v
    Kafka Streams Binder
        |
        v
    Function<KStream, KStream>
        |
        +--> validate event
        +--> key by deviceId
        +--> repartition if required
        +--> group by key
        +--> event-time window
        +--> aggregate into state store
        |
        v
    Kafka topic: device-window-summaries
        |
        v
    dashboard / alerting / downstream consumers

The binder manages connecting Spring Cloud Stream input/output bindings to the Kafka Streams runtime. The Kafka Streams DSL executes grouping, windowing, aggregation, and state management, while business transformation logic stays inside the function bean.

## 2. Project Setup and Dependencies

The application requires the Kafka Streams Binder. Use the dependency managed by the Spring Cloud BOM:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-stream-binder-kafka-streams</artifactId>
</dependency>
~~~

If the application also defines functions using the Kafka `MessageChannel` Binder, add the standard Kafka Binder only when genuinely needed. The Kafka Streams Binder is an integration tailored for the Kafka Streams API with its own configuration, lifecycle, and topology.

Dependencies typically managed by the Spring Boot/Spring Cloud BOM:
- Spring Boot starter and Spring Cloud Stream.
- Kafka Streams API compatible with the binder.
- Spring Kafka for `JsonSerde`.
- Jackson Java Time module if the application deserializes `java.time.Instant` in JSON.

Do not arbitrarily pin individual versions of Spring Cloud Stream, Kafka Streams, and Spring Kafka. Use a compatible release train/BOM, then inspect the dependency tree if incompatible class or method errors appear.

## 3. Designing the Event and Output Contract

The input event represents a single measurement:

~~~java
import java.time.Instant;

public record DeviceReading(
        String deviceId,
        Instant eventTime,
        double temperatureC,
        double humidityPercent) {
}
~~~

The output represents an aggregated summary for one device in one window:

~~~java
public record DeviceWindowSummary(
        String deviceId,
        long windowStartEpochMs,
        long windowEndEpochMs,
        long readingCount,
        double averageTemperatureC,
        double minTemperatureC,
        double maxTemperatureC,
        double averageHumidityPercent) {
}
~~~

Field meanings are straightforward:
- `deviceId` identifies the device and acts as the grouping key.
- `eventTime` is when the measurement occurred on the device, not necessarily when Kafka received the record.
- `readingCount` counts valid samples included in the summary.
- `windowStartEpochMs` and `windowEndEpochMs` bound the window.
- Average/min/max values are computed from valid samples.

Standardize timezones and units across systems—for example, Celsius for temperature, percentage 0 to 100 for humidity, and UTC epoch milliseconds for timestamps. If producers send ambiguous timezones or seconds instead of milliseconds, windows will classify events incorrectly.

## 4. Distinguishing the Record Key from `deviceId` in the Payload

Kafka Streams `groupByKey` groups by the Kafka record key. It does not inspect `deviceId` inside the JSON payload automatically to infer the key.

If the producer already writes `deviceId` as the record key, you can call `groupByKey` directly. If the producer sends a null key or a different key, re-key from the payload:

~~~java
.selectKey((oldKey, reading) -> reading.deviceId())
.groupByKey(Grouped.with(Serdes.String(), readingSerde))
~~~

`selectKey` changes the record key. When a subsequent operation requires key-based partitioning, Kafka Streams may create an internal repartition topic to route records to their matching partitions. Repartitioning ensures all records with the same `deviceId` reach the same task/partition, at the cost of extra network, serialization, disk, and latency overhead.

If producers can set the right key upfront, doing so at the producer avoids an extra repartition hop. Still, the topology should enforce key semantics rather than relying solely on topic conventions.

## 5. Choosing a Time Window

Kafka Streams provides several window types:

| Type | Behavior | Example use case |
|---|---|---|
| Tumbling | Fixed-size, non-overlapping windows | Per-minute or hourly averages |
| Hopping | Fixed-size windows advancing by smaller steps, overlapping | 5-minute average updated every 1 minute |
| Sliding | Windows based on time differences between records | Analyzing events occurring close together |
| Session | Windows extending with activity and closing after an idle gap | Device or user activity sessions |

This exercise chooses a one-minute tumbling window. Intervals are half-open: the start instant is inclusive, while the exact end instant belongs to the next window. For example, the 10:00:00 to 10:01:00 window includes events from 10:00:00 up to strictly before 10:01:00.

Window size and grace period are distinct concepts:
- Window size defines the time range being aggregated.
- Grace period allows late-arriving events to update a window after its end timestamp.
- Events arriving after stream time advances past window end plus grace are considered too late and excluded from that window's aggregation.

With a one-minute window size and 15-second grace, events belonging to the 10:00 window are accepted during the grace interval past 10:01 depending on partition/task stream time. Do not interpret grace as an independent wall-clock timer; Kafka Streams advances stream time based on timestamps of processed records.

## 6. Event Time vs. Processing Time

This is the most critical design choice in this exercise.

- Event time: when the device took the measurement.
- Ingestion time: when the broker received the record.
- Processing time: when the application processes the record.

By default, window aggregations use the timestamp Kafka Streams extracts via `TimestampExtractor`. If the producer sets the Kafka record timestamp to event creation time, the default may work. However, if `eventTime` only lives inside the JSON payload while the Kafka record timestamp reflects publish time, windows will follow ingestion timestamps rather than `eventTime`.

In IoT workloads, devices can lose connectivity and backfill buffered readings later. In those cases, event-time is usually far more accurate than processing-time. Configure a `TimestampExtractor` reading `eventTime` from the payload, or populate record timestamps directly at the producer.

Example `TimestampExtractor`:

~~~java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.streams.processor.TimestampExtractor;

public class DeviceEventTimestampExtractor implements TimestampExtractor {

    @Override
    public long extract(ConsumerRecord<Object, Object> record,
                        long partitionTime) {
        Object value = record.value();

        if (value instanceof DeviceReading reading
                && reading.eventTime() != null) {
            return reading.eventTime().toEpochMilli();
        }

        // Fallback should only be used if permitted by the data contract.
        return record.timestamp();
    }
}
~~~

If `eventTime` is missing or malformed, never silently substitute current wall-clock time, as that places bad events into the wrong window. Reject the record, emit alerts, or route malformed payloads to quarantine. Falling back to `record.timestamp()` is acceptable only when explicitly agreed in the contract.

## 7. Configuring `TimestampExtractor` on the Input Binding

Declare the extractor as a Spring bean with a stable name:

~~~java
import org.apache.kafka.streams.processor.TimestampExtractor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class DeviceStreamConfiguration {

    @Bean
    TimestampExtractor deviceEventTimestampExtractor() {
        return new DeviceEventTimestampExtractor();
    }
}
~~~

With the Kafka Streams Binder, the consumer binding provides `timestampExtractorBeanName` to reference the bean. Match the exact property name and syntax to your binder release.

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          bindings:
            aggregateDeviceWindows-in-0:
              consumer:
                timestampExtractorBeanName: deviceEventTimestampExtractor
~~~

If you do not configure an extractor, verify that producers set Kafka record timestamps to the event-time expected by the topology. Write tests with late events and mismatched record timestamps to prove the extractor is active.

## 8. Creating Serdes for Payloads and State

Kafka stores byte arrays; Kafka Streams needs Serializer/Deserializers (Serdes) to convert keys and values. In this example:
- Key is `String`.
- Input value is `DeviceReading`.
- State store value is `DeviceAggregate`.
- Output value is `DeviceWindowSummary`.

Spring Kafka provides `JsonSerde` for JSON. You can create concrete Serde subclasses with public no-argument constructors so the binder can instantiate them by class name:

~~~java
import org.springframework.kafka.support.serializer.JsonSerde;

public class DeviceReadingSerde extends JsonSerde<DeviceReading> {
    public DeviceReadingSerde() {
        super(DeviceReading.class);
    }
}

public class DeviceAggregateSerde extends JsonSerde<DeviceAggregate> {
    public DeviceAggregateSerde() {
        super(DeviceAggregate.class);
    }
}

public class DeviceWindowSummarySerde extends JsonSerde<DeviceWindowSummary> {
    public DeviceWindowSummarySerde() {
        super(DeviceWindowSummary.class);
    }
}
~~~

Place each public class in its own Java file matching the package referenced in binder configuration. Serde classes must expose a public no-argument constructor so the binder can instantiate them by class name.

For Java records containing `Instant`, verify the Jackson Java Time module and the `ObjectMapper` used by `JsonSerde`. Do not treat plain JSON as a schema registry: if you require schema versioning, compatibility checks, and schema IDs, use Serdes integrated with your chosen registry.

## 9. Building the Aggregate State Object

The aggregate holds just enough state to update metrics without storing every raw reading:

~~~java
public record DeviceAggregate(
        long count,
        double temperatureSum,
        double humiditySum,
        double minTemperatureC,
        double maxTemperatureC) {

    public static DeviceAggregate empty() {
        return new DeviceAggregate(
                0,
                0,
                0,
                0,
                0);
    }

    public DeviceAggregate add(DeviceReading reading) {
        double min = count == 0
                ? reading.temperatureC()
                : Math.min(minTemperatureC, reading.temperatureC());

        double max = count == 0
                ? reading.temperatureC()
                : Math.max(maxTemperatureC, reading.temperatureC());

        return new DeviceAggregate(
                count + 1,
                temperatureSum + reading.temperatureC(),
                humiditySum + reading.humidityPercent(),
                min,
                max);
    }

    public double averageTemperatureC() {
        return count == 0 ? 0 : temperatureSum / count;
    }

    public double averageHumidityPercent() {
        return count == 0 ? 0 : humiditySum / count;
    }
}
~~~

The aggregate stores only count, sums, min, and max. Each incoming event updates these fields in constant time. Never retain a `List` of all readings inside the window, as memory grows linearly with event count and high-volume windows can bloat state stores.

For percentiles or medians, sum/count is insufficient. You can use streaming algorithms like t-digest or histograms, choosing bounded-size state structures and matching Serdes.

## 10. Writing the Windowed Aggregation Function

The function takes a `KStream` keyed by `String` with `DeviceReading` values and returns a `KStream` keyed by `String` with `DeviceWindowSummary` values.

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
import org.apache.kafka.streams.kstream.TimeWindows;
import org.apache.kafka.streams.kstream.Windowed;
import org.apache.kafka.streams.state.WindowStore;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class DeviceWindowFunctions {

    @Bean
    Function<KStream<String, DeviceReading>,
             KStream<String, DeviceWindowSummary>> aggregateDeviceWindows() {

        Serde<String> stringSerde = Serdes.String();
        Serde<DeviceReading> readingSerde = new DeviceReadingSerde();
        Serde<DeviceAggregate> aggregateSerde = new DeviceAggregateSerde();

        return input -> input
                .filter((key, reading) -> isValid(reading))
                .selectKey((oldKey, reading) -> reading.deviceId())
                .groupByKey(Grouped.with(stringSerde, readingSerde))
                .windowedBy(TimeWindows.ofSizeAndGrace(
                        Duration.ofMinutes(1),
                        Duration.ofSeconds(15)))
                .aggregate(
                        DeviceAggregate::empty,
                        (deviceId, reading, aggregate) ->
                                aggregate.add(reading),
                        Materialized
                                .<String, DeviceAggregate,
                                        WindowStore<Bytes, byte[]>>as(
                                                "device-window-aggregate")
                                .withKeySerde(stringSerde)
                                .withValueSerde(aggregateSerde))
                .toStream()
                .map((windowedKey, aggregate) -> toSummary(
                        windowedKey,
                        aggregate));
    }

    private static boolean isValid(DeviceReading reading) {
        return reading != null
                && reading.deviceId() != null
                && !reading.deviceId().isBlank()
                && reading.eventTime() != null
                && Double.isFinite(reading.temperatureC())
                && Double.isFinite(reading.humidityPercent())
                && reading.humidityPercent() >= 0
                && reading.humidityPercent() <= 100;
    }

    private static KeyValue<String, DeviceWindowSummary> toSummary(
            Windowed<String> windowedKey,
            DeviceAggregate aggregate) {

        long start = windowedKey.window().start();
        long end = windowedKey.window().end();

        String outputKey = windowedKey.key() + "|" + start;

        DeviceWindowSummary summary = new DeviceWindowSummary(
                windowedKey.key(),
                start,
                end,
                aggregate.count(),
                aggregate.averageTemperatureC(),
                aggregate.minTemperatureC(),
                aggregate.maxTemperatureC(),
                aggregate.averageHumidityPercent());

        return KeyValue.pair(outputKey, summary);
    }
}
~~~

Topology steps:

1. `filter` discards records failing basic contract validation.
2. `selectKey` sets `deviceId` as the Kafka record key.
3. `groupByKey` groups records belonging to the same device.
4. `windowedBy` assigns records to time windows.
5. `aggregate` updates state for each device/window pair.
6. `toStream` converts the resulting `KTable` into a stream of updates.
7. `map` builds a unique output key per device and window start.

This example filters invalid events simply to keep the topology clear. In production, never drop silently: increment invalid metrics, log at bounded rates, and route malformed payloads to a DLQ/quarantine per business rules.

## 11. Why Must the Output Key Include the Window Start?

If the output key were only `deviceId`, every new window would write to the same key. If downstream reads into a `KTable` or the output topic uses log compaction, newer summaries would overwrite older summaries for that device.

In this exercise, the output key is:

    deviceId|windowStartEpochMs

For example:

    sensor-101|1795514400000
    sensor-101|1795514460000

Each window gets its own distinct identity. If a late event inside the grace period updates the same window, the output key stays identical for that window, updating the summary under the same key.

An alternative is a structured composite key with an explicit schema instead of string concatenation. If downstream requires partitioning by `deviceId`, you can use `deviceId` as the Kafka key and put `windowStart` in the value, noting that compacted topics will retain only the latest update per key. Choose keys according to downstream consumer contracts.

## 12. Configuring the Kafka Streams Binder

Select the function bean and declare input/output bindings:

~~~yaml
spring:
  cloud:
    function:
      definition: aggregateDeviceWindows
    stream:
      bindings:
        aggregateDeviceWindows-in-0:
          destination: device-readings
        aggregateDeviceWindows-out-0:
          destination: device-window-summaries
      kafka:
        streams:
          binder:
            brokers: localhost:9092
            applicationId: device-window-aggregator-local
          bindings:
            aggregateDeviceWindows-in-0:
              consumer:
                keySerde: org.apache.kafka.common.serialization.Serdes$StringSerde
                valueSerde: com.example.telemetry.DeviceReadingSerde
                timestampExtractorBeanName: deviceEventTimestampExtractor
            aggregateDeviceWindows-out-0:
              producer:
                keySerde: org.apache.kafka.common.serialization.Serdes$StringSerde
                valueSerde: com.example.telemetry.DeviceWindowSummarySerde
~~~

Adjust broker endpoints, Serde package names, and `applicationId` for your project. Kafka Streams Binder properties live under the `kafka.streams` prefix, distinct from the Kafka `MessageChannel` Binder. Never copy properties from `spring.cloud.stream.kafka.bindings` into `kafka.streams.bindings`, as the two binders expose different extended properties.

`applicationId` identifies the Kafka Streams application and its internal consumer group. Replicas of the same application must share the same `applicationId` to divide tasks and state; dev, staging, and production must use separate `applicationId` values so they never share consumer groups or state accidentally.

Pre-provision input and output destinations in production. The input topic needs enough partitions for desired parallelism. The output topic and internal repartition/changelog topics need adequate permissions and storage.

### 12.1. Serdes on Bindings vs. Inside the Topology

Configuring `keySerde`/`valueSerde` on the input binding tells the binder how to deserialize incoming records. Inside the topology, `Grouped.with` specifies Serdes for grouping/repartitioning, and `Materialized.with` specifies Serdes for the state store. Output binding producer Serdes control how summaries are serialized.

Serde classes must be instantiable via the binder's supported mechanism. Custom classes need public constructors and runtime classpath availability. Never declare Serdes solely on the input binding and assume output or state stores inherit the same types automatically.

## 13. Running End-to-End Locally

A practical walkthrough:

1. Start local Kafka or a dedicated test environment.
2. Create topic `device-readings` with an appropriate partition count.
3. Create topic `device-window-summaries`.
4. Start the application with the local profile and a dedicated `applicationId`.
5. Send events with `deviceId`, `eventTime`, and measurement values.
6. Read the output topic and inspect summaries by device and window.
7. Send a late event still within the grace period.
8. Send an event past the grace period and confirm the old window is not updated.
9. Stop/restart the application and verify state restoration.
10. Inspect consumer lag, processing rates, state/changelog topics, and logs.

Example JSON input:

~~~json
{
  "deviceId": "sensor-101",
  "eventTime": "2026-11-24T10:00:05Z",
  "temperatureC": 26.2,
  "humidityPercent": 61.0
}
~~~

Example summary output:

~~~json
{
  "deviceId": "sensor-101",
  "windowStartEpochMs": 1795514400000,
  "windowEndEpochMs": 1795514460000,
  "readingCount": 3,
  "averageTemperatureC": 26.6667,
  "minTemperatureC": 26.2,
  "maxTemperatureC": 27.0,
  "averageHumidityPercent": 60.5
}
~~~

Output values illustrate three samples in the same window; epoch timestamps in tests should be computed from actual event times. Never hard-code illustrative timestamps into production logic.

## 14. When Are Aggregation Results Emitted?

The aggregate output in this topology is represented as a `KTable`. Whenever a valid event modifies a window's state, the `KTable` can emit an update via `toStream`. Therefore, downstream consumers may receive multiple summary updates for the same output key while the window remains open or within its grace period.

This works well for near-real-time dashboards where averages update with each reading. However, if downstream wants only a single final result after the window closes, add `Suppressed.untilWindowCloses` in the topology:

~~~java
.suppress(Suppressed.untilWindowCloses(
        Suppressed.BufferConfig
                .maxBytes(50_000_000L)
                .shutDownWhenFull()))
.toStream()
~~~

Suppression buffers results until the window closes based on stream time and grace. The buffer requires a size limit; when full, the policy shown shuts down the Kafka Streams task/application rather than silently breaking the final-only guarantee. Size the buffer, monitor it, and plan recovery appropriately. If emitting early when the buffer fills is acceptable, choose the corresponding policy while understanding outputs may no longer be strictly final-only.

Never enable suppression just to reduce message counts without sizing memory. Device count, open windows, grace period, and event rate dictate buffer size.

## 15. State Stores and Changelog Topics

Windowed aggregation must retain intermediate state. Kafka Streams creates a state store named `device-window-aggregate`; local state is stored on each instance and restored from a changelog topic when a task moves to another instance or a process restarts.

Understand these three components:

- Local state store: state actively used by tasks on the instance.
- Changelog topic: Kafka log backing state store recovery.
- Repartition topic: created when the topology changes keys and must redistribute records.

State stores are not disposable caches to delete arbitrarily. Deleting local state slows down restoration; deleting changelog/internal topics destroys state recovery. Never manually delete internal topics while the application is running.

Keep `applicationId` and store names stable. Changing `applicationId` makes Kafka Streams treat it as a brand-new application with a fresh consumer group and state identity, causing it to re-read inputs per offset policy and rebuild state from scratch. Changing topologies or store names requires a state and internal-topic migration plan.

## 16. Partitions, Tasks, and Scalability

Kafka Streams creates tasks based on input topic partitions and topology structure. Within an `applicationId`, instances coordinate to share tasks. Useful active instances are capped by the number of parallel tasks; adding Pods beyond that limit will not raise throughput.

Checklist:
- Does the input topic have enough partitions for target parallelism?
- Is key distribution balanced, or is one device excessively hot?
- Do repartition topics have adequate partitions and throughput?
- Do brokers have enough disk, network, and replication capacity?
- Does state store restoration prolong rebalances?
- Can downstream outputs sustain the publish rate?

Because this topology groups by `deviceId`, events for the same device must hit the same partition for accurate aggregation. With skewed keys, one task processes far more load than peers. Adding partitions will not split a hot key across multiple partitions because the same key must stay on one partition to maintain aggregate ordering and state.

## 17. Choosing a Processing Guarantee

Kafka Streams supports multiple processing guarantees. At-least-once can reprocess records across certain failure windows; downstream should be idempotent on the output key. Exactly-once v2 provides atomic Kafka read/write transactions when brokers and configurations meet requirements.

Exactly-once inside Kafka Streams does not automatically cover side effects to external databases, HTTP APIs, emails, or other brokers. If a function writes to an external database outside Kafka, add outbox/inbox or separate idempotency/transactional safeguards.

When enabling `exactly_once_v2`, verify:
- Kafka broker version and transaction support.
- Transactional ID/producer permissions and transaction coordinator availability.
- Replication factor and `min.insync.replicas` on involved topics.
- Transaction timeouts and commit intervals.
- How the binder passes `processing.guarantee` down to Kafka Streams config in your version.

Never claim end-to-end exactly-once solely because `processing.guarantee` is set to `exactly_once_v2`.

## 18. Unit Testing Aggregation Logic

Separating aggregate calculations from the topology keeps unit tests clean. Verify:
- Empty aggregate receiving its first event.
- Accurate count increments.
- Accurate sums and averages.
- Accurate min/max updates.
- Multiple devices never mix state.
- Invalid readings excluded from results.
- Output keys distinguish windows.

Example unit test for the aggregate:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import org.junit.jupiter.api.Test;

class DeviceAggregateTest {

    @Test
    void calculatesCountAverageAndRange() {
        DeviceAggregate aggregate = DeviceAggregate.empty();

        aggregate = aggregate.add(new DeviceReading(
                "sensor-101",
                Instant.parse("2026-11-24T10:00:05Z"),
                26.0,
                60.0));

        aggregate = aggregate.add(new DeviceReading(
                "sensor-101",
                Instant.parse("2026-11-24T10:00:20Z"),
                28.0,
                64.0));

        assertThat(aggregate.count()).isEqualTo(2);
        assertThat(aggregate.averageTemperatureC()).isEqualTo(27.0);
        assertThat(aggregate.minTemperatureC()).isEqualTo(26.0);
        assertThat(aggregate.maxTemperatureC()).isEqualTo(28.0);
        assertThat(aggregate.averageHumidityPercent()).isEqualTo(62.0);
    }
}
~~~

This unit test verifies pure Java arithmetic; it does not test Kafka Streams window semantics, Serdes, or the binder.

## 19. Testing the Topology with `TopologyTestDriver`

`TopologyTestDriver` runs a Kafka Streams topology inside the JVM without a real broker. Use test input/output topics to verify keys, timestamps, windows, and aggregates.

A test suite should cover:

| Scenario | Input data | Expected outcome |
|---|---|---|
| One device, one window | Multiple readings with same `deviceId` | One output key, accurate count and average |
| Two devices | Two distinct `deviceId` values | Independent state |
| Two windows | Events before and after minute boundary | Two distinct summary keys |
| Late event within grace | Timestamp in older window, processed inside grace | Older window aggregate updates |
| Event past grace | Timestamp older than grace boundary | Expired window does not update |
| Invalid timestamp | Null or negative/invalid timestamp | Rejected or handled per policy |
| Key mismatch | Input key differs from `deviceId` | Repartition/grouping still groups accurately |
| Restart/state restore | Restore from changelog in integration test | Aggregate resumes from committed state |

When testing event-time, set timestamps explicitly on `TestInputTopic` or use the production `TimestampExtractor`. If tests emit payloads with inaccurate record timestamps, window outcomes will diverge from expectations.

`TopologyTestDriver` tests topology logic and state stores in a test harness. It does not replace integration tests for broker rebalances, ACLs, TLS, transactions, network partitions, or state restoration across real instances.

## 20. Integration Testing with Real Kafka

Use Kafka Testcontainers or an equivalent test cluster to verify the binder and runtime:

1. Start a Kafka container.
2. Create input/output topics with explicit partition counts.
3. Start the Spring context with the Kafka Streams Binder.
4. Send events via a producer with proper keys and timestamps.
5. Read the output topic and verify summaries.
6. Send late events inside and beyond the grace period.
7. Stop/restart the application or migrate tasks to verify state restoration.
8. Inspect consumer groups, `applicationId`, and internal topics.
9. Verify access permissions and serialization with real artifacts.

Integration tests should use a unique `applicationId` per test run to avoid colliding with state/offsets from other environments. Clean up topics/containers after tests without deleting internal topics of shared running apps.

## 21. Monitoring and Operations

An aggregation pipeline must monitor both the application and Kafka:

| Metric/Signal | Meaning |
|---|---|
| Input records/sec | Rate of readings entering topology |
| Output updates/sec | Rate of summaries emitted |
| Processing latency | Per-record processing duration |
| Consumer lag | How far behind the Kafka Streams app is |
| Rebalance count/time | Frequency and duration of assignment churn |
| State restore duration | Time spent restoring state stores |
| RocksDB/local state size | Local state storage footprint per instance |
| Changelog/repartition traffic | Internal topology traffic |
| Dropped late records | Records arriving past grace period |
| Invalid reading count | Data failing schema/domain validation |
| Broker disk and request latency | Kafka cluster health |

Never use output rate alone as a health indicator. With continuous `KTable` updates, one input triggers an output update; with suppression, output rate tracks closed windows instead. Dashboards must reflect the deployed semantics.

Logs should include `deviceId`, event type, `applicationId`, partition/task, and error category at controlled levels. Avoid putting high-cardinality event IDs or device IDs into metric labels; use structured logs and traces to inspect individual events.

## 22. Common Issues

| Symptom | Possible cause | Resolution |
|---|---|---|
| All devices merged together | Missing re-key by `deviceId` or wrong producer key | Call `selectKey` then `groupByKey`; verify key Serde |
| Summaries land in wrong windows | Kafka record timestamp differs from `eventTime` | Configure `TimestampExtractor` and test timestamps |
| Late events do not update window | Grace period expired per stream time | Check grace, partition time, and clock/source delays |
| Valid-looking schema fails deserialization | Serde or JSON type mismatch | Check input `valueSerde`, `JavaTimeModule`, and contract |
| State store fails to restore | Changelog/internal topic or `applicationId` changed | Verify internal topics, ACLs, and app identity |
| Repartition topic creation fails | Insufficient permissions or provisioning config | Check ACLs, broker policy, and topic provisioning |
| Output cannot be read | Wrong output producer Serde | Configure output `keySerde`/`valueSerde` |
| One task overloaded | Key skew / hot device | Analyze key distribution and shard if domain allows |
| Multiple Pods yield no throughput gain | Too few input partitions/tasks | Increase partitions per capacity plan and check task assignments |
| Output emits multiple updates | `KTable.toStream()` emits on every aggregate update | Use suppression if only final results are desired |
| App stops when suppression buffer fills | Bounded buffer with `shutDownWhenFull` | Tune capacity carefully, reduce cardinality/window, or adjust policy |
| Tests pass but production fails | Binder, broker security, or real state restore untested | Add integration tests against equivalent Kafka |

## 23. End-to-End Implementation Workflow

1. Create a project with a BOM-compatible Kafka Streams Binder dependency.
2. Define `DeviceReading` and `DeviceWindowSummary`.
3. Standardize on event-time and UTC timestamps.
4. Implement a `TimestampExtractor` reading `eventTime` from payloads or ensure accurate producer timestamps.
5. Create Serdes for input, aggregate state, and output.
6. Write a `Function` taking `KStream` and validating payloads.
7. Key by `deviceId`, call `groupByKey`, and check repartitioning.
8. Configure a one-minute tumbling window with 15-second grace.
9. Implement count/sum/min/max aggregation.
10. Materialize the state store with a stable name.
11. Convert `KTable` to `KStream` and construct output keys by `deviceId` and window start.
12. Configure input/output bindings, `applicationId`, and Serdes in the Kafka Streams Binder.
13. Run locally, emit events, and inspect summaries.
14. Test multiple devices, multiple windows, late events, and invalid payloads.
15. Test the topology with `TopologyTestDriver`.
16. Run integration tests covering binder, broker, state restore, and security.
17. Monitor lag, restores, dropped late events, state size, and output rates.
18. Deploy with pre-provisioned topics/partitions/ACLs and environment-specific `applicationId`s.

## 24. Production Checklist

- [ ] Events carry stable `deviceId` and valid `eventTime`.
- [ ] Producer keys or topology re-keys by `deviceId`.
- [ ] `TimestampExtractor` enforces proper event-time semantics.
- [ ] Window size, grace period, and late-event policies are agreed upon.
- [ ] Input, aggregate state, and output Serdes are compatible.
- [ ] State store names stay stable and changelogs are protected.
- [ ] Output keys distinguish both device and window.
- [ ] Decision is documented between emitting incremental updates vs. final-only results.
- [ ] Suppression buffers are bounded with alerts approaching capacity.
- [ ] `applicationId` is isolated across local/dev/staging/prod and shared across replicas of the same app.
- [ ] Input partitions support target parallelism and key distribution is verified.
- [ ] Broker ACLs cover input, output, repartition, and changelog topics.
- [ ] Processing guarantees accurately reflect Kafka transaction boundaries.
- [ ] Unit tests, `TopologyTestDriver` tests, and Kafka integration tests exist.
- [ ] Dashboards track lag, restores, state, late records, and throughput.
- [ ] Runbooks cover prolonged rebalances, slow state restores, backlogs, and schema errors.

This exercise built a complete pipeline: ingesting telemetry, keying by `deviceId`, grouping into tumbling event-time windows, updating aggregate state, and emitting summaries per device and window. The Kafka Streams Binder connects the function to the Kafka Streams runtime, while the Kafka Streams DSL handles windowing and stateful computation. In real deployments, decisions around timestamps, grace periods, Serdes, partitions, state stores, `applicationId`, and delivery guarantees must be verified against a real broker and representative data.

## References

- [Spring Cloud Stream — Kafka Streams Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/overview.html)
- [Spring Cloud Stream — Kafka Streams Programming Model](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/programming-model.html)
- [Spring Cloud Stream — Kafka Streams Binder Configuration](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/configuration-options.html)
- [Apache Kafka Streams — Developer Guide](https://kafka.apache.org/documentation/streams/)
- [Apache Kafka Streams — Windowing](https://kafka.apache.org/documentation/streams/developer-guide/dsl-api.html#windowing)
- [Spring Kafka — Serialization, Deserialization and Serdes](https://docs.spring.io/spring-kafka/reference/kafka/serdes.html)
