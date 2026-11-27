# IoT Data Ingestion and Time-Window Aggregation

In the **Real-World Application Patterns** chapter, an IoT system typically ingests telemetry from thousands of devices with uneven data rates and connectivity quality. Devices may transmit data periodically, backfill after network outages, send duplicates on retry, or deliver old events after reconnecting. A serverless application must ingest the data stream, authenticate sources, validate schemas, deduplicate events, and aggregate metrics over time windows without losing data or creating traffic spikes.

This lesson belongs to the **CLOUD_SERVERLESS** module, focusing on developing and deploying applications using the serverless model—especially Java functions triggered by HTTP, messages, or events. Learners work through triggers, state, access permissions, retries, idempotency, cold starts, scaling, and cost to determine when FaaS is the right choice. The IoT problem brings these topics together in a real-world pipeline: ingest, validate, buffer, aggregate, store results, and serve queries.

## 1. The IoT Telemetry Problem

An IoT device may send measurements such as:

- Temperature, humidity, and pressure.
- Voltage, current, and power.
- Location or motion state.
- Energy consumption.
- On/off cycle counts or operational status.
- Threshold-breach alerts.

For example, a temperature sensor sends one message every 10 seconds. With 20,000 devices, the system receives an average of about 2,000 events per second. When cellular networks or gateways recover, many devices may backfill buffered data simultaneously, causing sudden traffic bursts.

Applications typically do not need to query every raw measurement to render a dashboard. Instead, they need aggregations by minute, device, or region, such as:

- Average, minimum, and maximum temperature per minute.
- Total energy consumption per hour.
- Number of alerts emitted by a device within a time range.
- Percentage of active devices by region.
- Latency between measurement time and server ingestion time.

A well-designed pipeline retains raw data long enough per policy, produces fast-to-query aggregates, and supports detecting or correcting values when events arrive late.

## 2. Overall Architecture

A reference architecture:

~~~mermaid
flowchart TD
    DEV["IoT devices / gateways"] --> ING["IoT ingestion endpoint"]
    ING --> AUTH["Authenticate device and validate envelope"]
    AUTH --> STREAM["Durable stream or queue"]
    STREAM --> PROC["Java Lambda / stream processor"]
    PROC --> DEDUP["Deduplication and event-time window"]
    DEDUP --> RAW["Raw telemetry storage"]
    DEDUP --> AGG["Window aggregate store"]
    AGG --> API["Query API / dashboard"]
    STREAM --> DLQ["DLQ / quarantine"]
    PROC --> OBS["Metrics, logs and traces"]
    RAW --> LAKE["Data lake / offline analysis"]
~~~

Each component has a distinct responsibility:

- **Device/gateway:** measures and emits telemetry, including device identity and sequence numbers if available.
- **Ingestion endpoint:** authenticates devices, enforces rate limits, and checks payload sizes.
- **Stream or queue:** absorbs bursts, persists events durably, and decouples producers from consumers.
- **Processor:** parses, validates, deduplicates, and computes aggregates.
- **Raw storage:** retains raw telemetry for auditing, analysis, or rebuilding.
- **Aggregate store:** stores results keyed by device, metric, and window.
- **Query API:** serves dashboards and downstream applications.
- **DLQ/quarantine:** holds unprocessable events.
- **Observability:** tracks ingest rate, lag, late events, errors, and cost.

Not every system needs all components. For a small prototype, an HTTP endpoint and a database may suffice. For a large fleet, a durable stream and a stateful processor are usually more appropriate.

## 3. Choosing Protocols and Ingestion Endpoints

IoT devices can send data over MQTT, HTTP, or proprietary protocols via a gateway. The choice depends on connectivity, power budget, payload size, latency requirements, and device capabilities.

| Ingestion Method | Suitable When | Control Points |
|---|---|---|
| MQTT | Devices maintain long-lived connections with small, frequent telemetry | Device identity, topic authorization, QoS, reconnects |
| HTTP | Devices/gateways can send independent requests | Authentication, rate limits, request size, retries |
| Gateway protocol adapter | Devices use industrial protocols or private networks | Gateway identity, buffering, schema mapping |
| Stream producer | Gateways or backends already batch records | Partition key, throughput, backpressure |

MQTT QoS 1 typically provides at-least-once delivery semantics, so duplicates can occur. HTTP clients may also retry after timeouts even when the server already received the request. Never assume the transport protocol guarantees each measurement appears only once.

### 3.1. Device Authentication

Each device or gateway needs its own identity. Depending on the platform, this may use certificates, short-lived tokens, or the IoT broker's native authentication mechanism.

Requirements:

- Bind the device identity to a tenant/owner.
- Allow a device to publish only to its own topics or resources.
- Maintain processes for issuing, rotating, and revoking credentials.
- Avoid sharing a single secret across the entire fleet whenever possible.
- Enforce payload size and request rate limits.
- Block revoked devices before accepting new data.
- Audit changes to identities or permissions.

Never trust a `deviceId` inside the payload as proof of identity. The server must verify that the authenticated device identity matches the `deviceId` declared in the event.

## 4. Telemetry Event Envelope

An event should carry sufficient metadata to identify source, timing, and order:

~~~json
{
  "eventId": "evt-thermo-8a71",
  "eventType": "TelemetryMeasured",
  "schemaVersion": 2,
  "tenantId": "tenant-17",
  "deviceId": "sensor-204",
  "sequence": 9182,
  "eventTime": "2026-11-17T10:20:30.250Z",
  "sentAt": "2026-11-17T10:20:31.010Z",
  "metric": "temperature",
  "value": 28.45,
  "unit": "Cel",
  "firmwareVersion": "3.8.1"
}
~~~

Field meanings:

- eventId: stable identifier for the measurement or event.
- tenantId/deviceId: device scope.
- sequence: monotonically increasing number assigned by the device or gateway.
- eventTime: timestamp when the measurement occurred.
- sentAt: timestamp when the device sent the event.
- metric/value/unit: measurement type, value, and unit.
- schemaVersion: contract version.

If a device lacks a reliable clock, `eventTime` may be skewed. You can add `receivedAt` generated by the ingestion service. Never overwrite the original `eventTime`; keep both to distinguish measurement time from ingestion time.

### 4.1. Unit Normalization

Never sum or average values with different units. For instance, Celsius and Fahrenheit temperatures must be normalized before aggregation. Energy (kWh) and power (kW) are different physical quantities and cannot be summed directly.

Schemas should specify:

- Stable metric names.
- Canonical units.
- Data types and precision.
- Valid value ranges.
- Unit conversion rules.
- Precision and rounding policies.

For billing or energy calculations requiring exact precision, use `BigDecimal` or scaled integers in the smallest unit rather than arbitrary floating-point numbers. For example, store millidegrees or milliamperes when the resolution is fixed.

## 5. Event Time vs. Processing Time

These concepts are distinct:

- **Event time:** when the device took the measurement or the event occurred.
- **Processing time:** when the processor executes the computation.
- **Ingestion time:** when the system received the event.

For example, a device loses connectivity from 10:00 to 10:05 and backfills a 10:01 measurement at 10:06. Its event time is 10:01, while its ingestion/processing time is around 10:06.

If you aggregate by processing time, the data is placed into the 10:06 window even though it reflects the state at 10:01. For dashboards organized by measurement time, use event time with an explicit late-arrival policy.

Processing time remains useful for operational monitoring—for example, measuring latency from server receipt to completion. Never overload a single timestamp for both purposes.

## 6. Types of Time Windows

Windows define which events are grouped together for computation. Three common types:

### 6.1. Tumbling Window

Tumbling windows have a fixed length and do not overlap. For example, 1-minute windows:

- 10:00:00 to just before 10:01:00.
- 10:01:00 to just before 10:02:00.
- 10:02:00 to just before 10:03:00.

Each event belongs to exactly one window per metric/key. This type suits per-minute/per-hour metrics and periodic reports.

### 6.2. Sliding Window

Sliding windows have separate length and slide intervals. For example, a 5-minute window updated every 1 minute. Consecutive windows overlap.

This type suits rolling averages, trend detection, or alerts requiring frequent updates. A single event may belong to multiple windows, increasing computation and state size.

### 6.3. Session Window

Session windows group events into a session separated by inactivity gaps. For example, if a device emits no data for 15 minutes, the telemetry session is considered closed.

Session windows fit usage-session analysis or bursty activity. You must define the gap timeout and how late events that bridge a previously closed session are handled.

~~~mermaid
flowchart LR
    subgraph T["Tumbling: 1-minute windows"]
      T1["10:00-10:01"] --> T2["10:01-10:02"] --> T3["10:02-10:03"]
    end
    subgraph S["Sliding: 5-minute window, 1-minute step"]
      S1["10:00-10:05"]
      S2["10:01-10:06"]
      S3["10:02-10:07"]
    end
    subgraph E["Session: 15-minute inactivity gap"]
      E1["Events"] --> E2["Quiet gap"] --> E3["Session closes"]
    end
~~~

## 7. Defining Window Keys and Boundaries

An aggregate key typically includes:

- Tenant ID.
- Device ID or group ID.
- Metric name.
- Window start time.
- Window definition/version.

Example: tenant-17 / sensor-204 / temperature / 10:20 UTC / 1-minute.

Window keys must be deterministic so retries and replays update the exact same aggregate. If window size changes, never silently reuse the same key format; include a window specification/version.

For a tumbling window of size W milliseconds, window start is calculated as:

\[
start = \left\lfloor \frac{eventTimeMillis}{W} \right\rfloor \times W
\]

Windows are half-open intervals: start inclusive, end exclusive. An event at exactly 10:21:00 belongs to the window starting at 10:21, not the window ending at 10:21.

Use UTC when computing window keys and storing timestamps. Convert to local timezones only in the presentation layer to prevent daylight saving transitions from duplicating or skipping an hour.

### 7.1. Java Example for Computing a Tumbling Window

~~~java
import java.time.Duration;
import java.time.Instant;

public record TimeWindow(Instant start, Instant end) {
    public static TimeWindow tumbling(
            Instant eventTime,
            Duration windowSize) {

        long sizeMillis = windowSize.toMillis();
        if (sizeMillis <= 0) {
            throw new IllegalArgumentException(
                    "windowSize must be positive");
        }

        long eventMillis = eventTime.toEpochMilli();
        long startMillis =
                Math.floorDiv(eventMillis, sizeMillis) * sizeMillis;

        Instant start = Instant.ofEpochMilli(startMillis);
        return new TimeWindow(start, start.plusMillis(sizeMillis));
    }
}
~~~

Use `Math.floorDiv` to handle timestamps prior to the Unix epoch properly. This example assumes whole-millisecond window sizes; if higher resolution is needed, use appropriate time units and arithmetic.

## 8. Watermarks and Late Events

In stream processing, a watermark estimates event-time progress. It indicates the processor believes most events prior to that timestamp have already been observed. A watermark is not an absolute guarantee that no older event will arrive.

For example, the watermark is at 10:10, and an event with `eventTime` 10:07 arrives afterward. That is a late event relative to the watermark.

A processor may allow 5 minutes of lateness. Depending on the engine, the 10:05–10:10 window may emit initial results when the watermark reaches the window end, while retaining state for late arrivals; the window only stops accepting updates once the watermark passes 10:15. Allowed lateness should reflect connectivity patterns, device buffering, and product latency requirements.

Late-event policies can include:

- **Accept and update:** update the aggregate if the window is still within allowed lateness.
- **Emit correction:** publish a correction or new revision for an already-emitted aggregate.
- **Side output/quarantine:** route overly late events to an investigation stream.
- **Drop with audit:** drop only if policy permits and record a metric.

Never silently drop late events if they affect reporting or business obligations.

### 8.1. Watermarks in Lambda

An isolated Lambda invocation has no global watermark on its own. If each invocation processes only one batch, it does not know whether other devices still have unarrived older events.

There are two approaches:

1. Use a stream processing engine with native event-time state and watermarks.
2. Manage watermarks explicitly in durable storage, with clear rules per partition/key and progress source.

Never store watermarks in a static field of a Java Lambda. Execution environments can be recycled, and scaling out creates multiple instances with diverging in-memory state.

## 9. Handling Duplicates and Sequence Gaps

Devices may retry after losing an ACK, gateways may resend batches, and stream consumers may retry records. A stable `eventId` is needed for deduplication.

If devices emit monotonically increasing sequences, processors can detect:

- Sequence less than or equal to a previously seen sequence: likely a duplicate or old event.
- Sequence equal to the next expected value: normal next event.
- Sequence jumps with a gap: potential lost event or an earlier event arriving late.
- Sequence reset after reboot: requires a boot/session identifier or epoch to avoid confusion.

Do not rely solely on `deviceId + sequence` if sequences can reset. Construct an identity from `deviceId + bootId + sequence`, or a stable device-generated `eventId`.

Deduplication retention must be at least as long as the retry/replay window supported by the system. Deleting dedup records too early allows replayed events to be counted twice.

## 10. Partitioning and Hot Keys

Streams typically shard data by partition key. A good key keeps events from the same device together and preserves ordering within a partition. However, if one device emits excessive data or all devices share a key, a partition can become a hot key.

Options:

- Partition by `deviceId` when per-device ordering is needed.
- Partition by `tenantId` when grouping by tenant, though large tenants may cause hot partitions.
- Add a shard suffix for ultra-high-throughput devices when parallel processing and subsequent merging are acceptable.
- Distribute via a hash of `deviceId` for balanced load.
- Split telemetry and alerts into separate streams when priority requirements differ.

Do not choose a partition key solely by device count. Consider event rate distribution, payload sizes, and ordering requirements.

## 11. Storing Raw Telemetry and Aggregates

It is usually best to separate raw data from aggregated results:

| Store | Data | Purpose |
|---|---|---|
| Stream/queue | Events awaiting processing | Buffering, retries, and distribution |
| Raw object storage | Original telemetry partitioned by batch/time | Auditing, replay, offline analytics |
| Aggregate database | Sum/count/min/max per window | Dashboards and fast queries |
| Metadata store | Device registry, calibration, schemas | Validation and device management |
| DLQ/quarantine | Failed events | Investigation and recovery |

At high volume, you do not need to keep every raw event in the API-serving database. Object storage or a data lake fits high-volume historical data; an aggregate database serves lookups by key and time range.

Retention policies for raw data and aggregates can differ. Aggregates can often be kept longer if sensitive details have been stripped and policies permit.

## 12. Basic Aggregate Formulas

For each window and metric, common metrics include:

- count: number of valid events.
- sum: sum of values.
- average: sum divided by count.
- min/max: minimum/maximum value.
- last: value with the latest event time or sequence.
- rate: number of events or total quantity per unit of time.

Do not directly average per-batch averages when batches have different event counts. Accumulate `sum` and `count`, then compute the final average:

\[
average = \frac{\sum value_i}{count}
\]

For example, batch A has 10 samples averaging 20°C and batch B has 2 samples averaging 30°C. The true overall average is (10×20 + 2×30)/12 = 21.67°C, not (20+30)/2 = 25°C.

For energy, if each event represents instantaneous power, you cannot sum power values and call the result energy. You must integrate over time or use cumulative meter readings.

### 12.1. Precision and Outliers

Do not use `double` for calculations requiring strict decimal precision. Use `BigDecimal` or fixed-scale integers, and define output rounding rules.

Define how outliers are handled:

- Values outside physical bounds.
- Sensors reporting fault codes or invalid calibration.
- Suspicious repeated values.
- Noise spikes.
- Sensor drift.

Do not silently delete outliers if auditing is required. Attach a quality flag, retain the raw value, and exclude from aggregates according to a versioned rule.

## 13. Java Model and Validation Example

A telemetry model can be represented as:

~~~java
import java.math.BigDecimal;
import java.time.Instant;

public record TelemetryEvent(
        String eventId,
        String tenantId,
        String deviceId,
        String bootId,
        long sequence,
        Instant eventTime,
        Instant receivedAt,
        String metric,
        BigDecimal value,
        String unit,
        int schemaVersion) {
}
~~~

Validation should verify:

- Device is registered and not revoked.
- Tenant in the event matches the authenticated identity.
- Event type and schema version are supported.
- Metric/unit belong to the permitted registry.
- Value falls within valid bounds.
- `eventTime` is neither too far in the future nor older than allowed by policy.
- Payload size and sequence are valid.

Example:

~~~java
import java.math.BigDecimal;
import java.time.Duration;
import java.time.Instant;

public final class TelemetryValidator {
    private static final Duration MAX_FUTURE_SKEW =
            Duration.ofMinutes(2);

    private TelemetryValidator() {
    }

    public static void validate(
            TelemetryEvent event,
            Instant serverNow) {

        if (event.eventId() == null || event.eventId().isBlank()) {
            throw new IllegalArgumentException("Missing eventId");
        }
        if (event.deviceId() == null || event.deviceId().isBlank()) {
            throw new IllegalArgumentException("Missing deviceId");
        }
        if (event.value() == null) {
            throw new IllegalArgumentException("Missing value");
        }
        if (event.eventTime() == null) {
            throw new IllegalArgumentException("Missing eventTime");
        }
        if (event.eventTime().isAfter(
                serverNow.plus(MAX_FUTURE_SKEW))) {
            throw new IllegalArgumentException("Event time is in future");
        }
        if (event.value().compareTo(new BigDecimal("-80")) < 0
                || event.value().compareTo(new BigDecimal("150")) > 0) {
            throw new IllegalArgumentException(
                    "Temperature outside configured range");
        }
    }
}
~~~

The range `-80` to `150` is only an example for one specific sensor type. Each metric needs its own range and calibration policy. Do not apply this temperature check to all telemetry types.

## 14. Safely Updating Aggregates in DynamoDB

For simple tumbling windows, Lambda can maintain state in DynamoDB. An aggregate item key can combine tenant, device, metric, and `windowStart`.

To prevent duplicates, use `TransactWriteItems` containing:

1. Put a dedup item with condition `attribute_not_exists`.
2. Update the aggregate item to increment `count` and `sum`.
3. Both operations commit or roll back atomically.

Conceptual update expression example:

~~~text
SET #sum = if_not_exists(#sum, :zero) + :value,
    #updatedAt = :now
ADD #count :one
~~~

The dedup item and the aggregate item must be two distinct items in the transaction. If the dedup condition fails, the transaction does not update the aggregate; after verifying the expected conditional failure type, the consumer treats the event as a duplicate.

Use `BigDecimal`/DynamoDB `Number` at your chosen precision, avoiding unnecessary conversion to binary floating point. Min/max values require conditional update logic or a stateful stream processor; they cannot be replaced by simple addition.

### 14.1. State Expiry and Finalization

Aggregate state should not be deleted immediately when a window ends if late events are still allowed. Retain state through the allowed lateness period, then have a finalizer transition the status to `FINALIZED` via a conditional update.

DynamoDB TTL can clean up items after retention expires, but TTL deletion is asynchronous. Never rely on TTL events to precisely trigger final result emission. Finalizers should be driven by watermarks or conditional scheduled sweeps.

If a late event arrives after finalization, policy may emit a correction revision, route to a side output, or reject with an audit log. Never silently mutate a finalized aggregate if downstream consumers have already relied on the earlier result.

## 15. When to Use a Stateful Stream Processor?

When you need event-time windows, watermarks, allowed lateness, session windows, or large state, a stream processing engine is usually better suited than building all state management manually in Lambda.

A stream processor can provide:

- Event-time timestamp assignment.
- Watermark generation.
- Tumbling/sliding/session windows.
- Stateful aggregation.
- Checkpointing and recovery.
- Late-event side outputs.
- Exactly-once or at-least-once state semantics depending on connectors/configuration.

Example architecture:

- IoT broker feeds telemetry into Kinesis Data Streams or Kafka.
- A managed stream processor consumes partitions.
- The processor assigns event time, applies watermarks, and computes windows.
- Aggregates are written to a database or data lake.
- Dashboards query the aggregate store.

Always verify actual sink semantics. A processor with exactly-once checkpoints does not automatically guarantee external HTTP side effects execute once unless the sink participates in the corresponding protocol.

## 16. Stateless Lambda vs. Stateful Aggregation

Lambda excels at independent event processing, validation, enrichment, routing, or updating external durable state. However, a single Lambda invocation is not a global stateful stream processor.

Do not:

- Keep sums/counts in a static map and treat them as reliable aggregates.
- Assume the next invocation runs in the same execution environment.
- Use one instance's memory to coordinate across devices.
- Finalize a window simply because one invocation saw no new events.
- Infer event ordering from Lambda completion order.

When using Lambda, state must live in DynamoDB, Redis, or another durable store, with atomic dedup and aggregate updates. If complex event-time semantics are needed, use a stream engine rather than simulating watermarks with a global variable.

## 17. Batch Size, Concurrency, and Backpressure

Batching reduces invocation counts but increases the data each invocation handles. Overly large batches can:

- Increase memory usage and duration.
- Cause timeouts when a single record is slow.
- Widen the blast radius when a batch fails.
- Reprocess already-completed records on retry if partial failure reporting is disabled.
- Make hot aggregate keys even hotter.

High concurrency reduces stream lag but can overwhelm the database. Cap event source mapping concurrency or reserved concurrency according to the aggregate store's capacity.

Monitor:

- Incoming records per second.
- Iterator age or queue age.
- Concurrent executions.
- p95/p99 duration.
- Throttles and retries.
- Database write throttles/latency.
- DLQ count and oldest event age.

Backpressure can be applied by lowering consumer concurrency, throttling producers, buffering in queues, or using rate limiters. Never raise concurrency while the database is throttling; that only worsens the problem.

## 18. Hot Devices and Skewed Traffic

Some devices may emit far more events than others due to firmware bugs or overly aggressive sampling rates. If the partition key is just `deviceId`, a single device can create a hot partition.

Mitigations:

- Rate-limit per device and per tenant.
- Enforce a maximum sampling rate.
- Detect abnormal sequence jumps or duplicate bursts.
- Enforce per-tenant quotas.
- Separate alert streams from regular telemetry.
- Consider shard suffixes for high-rate devices and merge aggregates downstream.
- Alert when a single device accounts for an anomalous share of traffic.

Never let one malfunctioning device exhaust concurrency or write capacity for the entire fleet.

## 19. Handling Bad Data and Quarantine

Some events cannot be folded into aggregates:

- Unsupported schema versions.
- Disallowed metrics or units.
- Revoked devices.
- `eventTime` too far in the future.
- Conflicting sequences.
- Corrupted payloads.
- Out-of-range values.
- Tenant/device mismatches.

Error classification:

| Error Type | Action |
|---|---|
| Network error or throttling | Retry with backoff |
| Unsupported schema | Quarantine and upgrade consumer/transform |
| Unauthorized device | Reject, audit, and alert |
| Malformed payload | DLQ/quarantine |
| Duplicate event | Ignore idempotently, increment metric |
| Late event within allowance | Update/emit correction |
| Event too old | Side output or drop per policy |
| Anomalous sensor value | Flag quality or quarantine |

Do not send every error to retries. Unauthorized or malformed events will not fix themselves after repeated redeliveries.

## 20. Raw Data, Replay, and Rebuilding Aggregates

Aggregates may need recomputation when:

- Formulas are fixed.
- Calibration factors are updated.
- Failed events are recovered.
- Window definitions change.
- A batch of events was missing or duplicated.
- An audit is requested.

Retaining raw events according to policy enables rebuilds. During a replay:

1. Select the target time range and devices/tenants.
2. Select the aggregation logic version.
3. Write outputs to a new namespace/version.
4. Run reconciliation checks.
5. Compare against existing aggregates.
6. Promote the new results once verified.

Never replay directly onto production aggregates without versioning or a deduplication strategy. Replaying the same events will inflate counts/sums again unless state is reset or isolated by generation key.

An aggregate key can include `aggregationVersion` so new logic can run alongside legacy results.

## 21. Detecting Silent Devices and Missing Data

A device that stops sending telemetry is not necessarily broken. It may have lost connectivity, depleted its battery, entered maintenance, or only report on state change.

You can define heartbeats or expected reporting intervals:

- `expectedInterval`: expected reporting cadence.
- `gracePeriod`: allowed delay before alerting.
- `lastSeenAt`: timestamp of the last valid event received.
- `status`: `ONLINE`, `STALE`, `OFFLINE`, or `UNKNOWN`.

A scheduled function can detect devices past their grace period and emit alerts. Avoid scanning the entire device registry on every invocation; use an index on `lastSeenAt` or a state-tracking stream.

Never treat missing events as a zero measurement. If no readings arrived, aggregates should record `count=0` or a missing-data status—never inject zeros into averages.

## 22. Serving Queries and Dashboards

Dashboards commonly query by:

- Tenant.
- Device or device group.
- Metric.
- Time range.
- Granularity (minute, hour, day).

The aggregate store needs keys/indexes aligned with query access patterns—for example, a partition key of tenant/device/metric and a sort key of window start. For tenant-wide queries, maintain a tenant-level or region-level rollup projection; avoid full table scans.

Query APIs should cap time ranges and maximum returned data points. If a user requests 1 year of data at 1-second granularity, the API should select coarser aggregates or downsample rather than returning tens of millions of points.

You can retain multiple aggregate tiers:

- 1-minute resolution for several days.
- 1-hour resolution for several months.
- 1-day resolution for longer retention.

Exact retention periods should be driven by policy and storage costs.

## 23. Security and Privacy of IoT Data

Telemetry can reveal locations, daily routines, factory operational states, or user behavior. Ensure:

- Per-device/gateway authentication.
- Least-privilege IAM for ingestion and processors.
- Encryption in transit and at rest.
- Never logging raw payloads containing sensitive data.
- Tenant isolation via keys/partitions and authorization checks.
- Certificate/token rotation and revocation management.
- Bounded retention for raw telemetry.
- Access and export auditing.
- Never embedding device secrets inside events.
- Isolating the command channel from telemetry ingestion.

Telemetry ingestion and device commands are separate authorization boundaries. A device permitted to publish measurements is not implicitly authorized to receive control commands.

## 24. Cost Drivers in an IoT Pipeline

Cost components:

- MQTT/API ingestion requests.
- Stream shard/throughput or queue requests.
- Lambda invocations and GB-seconds.
- Stateful stream processing capacity.
- DynamoDB writes/reads and storage.
- Object storage for raw telemetry.
- Logs, metrics, and traces.
- Data transfer.
- DLQs, archives, and replays.
- Query APIs and dashboards.

Costs scale with device count, sampling frequency, payload size, retention, and retry volume. Lowering sampling rates reduces cost but also reduces visibility into short-lived events; balance product requirements against budget.

Optimization levers:

- Batch telemetry at gateways when appropriate.
- Compress payloads if devices and backend support it.
- Strip unnecessary fields.
- Right-size stream/queue throughput.
- Log only essential metadata.
- Pre-aggregate early while retaining raw data per policy.
- Separate hot and cold data tiers.
- Bound replays and retries.
- Sample traces at high traffic volumes.

Never cut costs by discarding raw events if the business requires audits or rebuilds. Define retention and recomputation requirements before trimming stored data.

## 25. Testing an IoT System

Key test cases:

- Valid events from authenticated devices.
- Revoked devices attempting to publish.
- Legacy and new payload schemas.
- Duplicate events sharing the same `eventId`.
- Out-of-order event sequences.
- Clock-skewed `eventTime` values.
- Events arriving past allowed lateness.
- Traffic bursts when multiple gateways reconnect.
- A single device creating a hot key.
- Database throttling or stream lag.
- Lambda timeouts between deduplication and aggregate updates.
- Replaying the same raw dataset.
- Window boundaries right at window start/end.
- Display timezone conversions while computing windows in UTC.
- Devices stopping heartbeats.
- DLQ redrives after consumer fixes.

Aggregation tests must verify sums, counts, averages, and window membership. For example, an event at exactly 10:01:00 must fall into `[10:01, 10:02)`, not `[10:00, 10:01)`.

For large systems, run load tests with realistic traffic distributions, including skewed high-rate devices. Measure throughput, lag, p95/p99 latency, throttling, database write capacity, and cost.

## 26. Step-by-Step Implementation Rollout

A practical rollout sequence:

1. Define metrics, units, schemas, and event identities.
2. Register device identities and authorization policies.
3. Choose the ingestion protocol and durable buffer.
4. Select partition keys based on ordering and throughput.
5. Persist raw telemetry per policy.
6. Choose window types and event-time semantics.
7. Select a stream processor or Lambda + durable state store.
8. Design deduplication and late-event policies.
9. Build the aggregate store and query access patterns.
10. Configure retries, DLQs, and replay workflows.
11. Set up dashboards, alerts, and cost metrics.
12. Run load tests, chaos tests, and data correctness checks.
13. Canary with a small group of devices.
14. Expand across the fleet while monitoring lag and hot keys.
15. Document aggregation versions and rebuild procedures.

Do not onboard the entire fleet before validating capacity. Canarying a small device cohort measures real event rates, payload distributions, and failure modes prior to full rollout.

## 27. Common Mistakes

**Using processing time instead of event time:** Backfilled events land in the wrong windows. Keep measurement and receipt timestamps separate.

**Using a static map in Lambda as an aggregate store:** State is not shared across execution environments and can be lost. Use a durable database or stateful stream processor.

**Skipping deduplication:** Retries inflate sums and counts multiple times. Use `eventId` with atomic dedup and aggregate updates.

**Inferring order from timestamps:** Device clocks drift. Use sequences or versions whenever available.

**Using a single partition key for all traffic:** Hot devices/tenants bottleneck the partition. Analyze traffic skew and shard appropriately.

**Closing windows too early:** Late events get dropped. Use watermarks with allowed lateness or correction policies.

**Using TTL for finalization:** TTL cleanup is asynchronous. Use watermarks or conditional finalizer jobs.

**Averaging averages:** Produces incorrect results when batch sizes differ. Accumulate sums and counts, then divide.

**Summing power as energy:** Physically invalid units. Integrate over time or use cumulative meter readings.

**Replaying directly onto live aggregates:** Doubles counts and sums. Use an `aggregationVersion` or isolated rebuild namespace.

**Conflating missing data with zero:** Misleads dashboards. Store explicit counts and data-quality status.

**Increasing concurrency during database throttling:** Adds load and worsens lag. Throttle workers to match downstream capacity.

**Logging entire telemetry payloads:** Leaks data and inflates costs. Log filtered metadata only.

## 28. Production Checklist

- [ ] Device identities are authenticated and bound to the correct tenant.
- [ ] Devices can publish only to authorized topics/resources.
- [ ] Event envelopes include `eventId`, `eventTime`, `receivedAt`, `schemaVersion`, and `unit`.
- [ ] Sequence/boot IDs are included where gap and reset detection are needed.
- [ ] Metrics and units are normalized.
- [ ] Event time and processing time are kept distinct.
- [ ] Window types, sizes, steps, and UTC alignment are defined.
- [ ] Watermarks/allowed lateness or late-event policies are explicit.
- [ ] Deduplication and aggregate updates execute atomically.
- [ ] Aggregate state resides in durable storage.
- [ ] Partition keys are evaluated against hot keys and traffic skew.
- [ ] Raw telemetry has retention and encryption policies.
- [ ] DLQs/quarantine have owners and redrive runbooks.
- [ ] Batch sizes and concurrency match downstream capacity.
- [ ] Metrics cover ingest rate, lag, late events, duplicates, and window completion.
- [ ] Tests verify window boundaries and replays.
- [ ] Versioned aggregate rebuild procedures exist.
- [ ] Dashboards distinguish missing data from zero values.
- [ ] Logs contain no credentials or sensitive payloads.
- [ ] Load tests and canaries run before full fleet rollout.
- [ ] Cost metrics are tracked per device, event, and aggregate window.

## Conclusion

A serverless IoT pipeline must authenticate devices, standardize event envelopes, buffer data durably, and process events by measurement time. Tumbling, sliding, and session windows serve different aggregation needs; event-time watermarks and allowed lateness handle backfilled or delayed arrivals. Duplicates must be controlled through stable event identities and atomic aggregate updates.

Java Lambda is well suited for validation, routing, and simple aggregations backed by external state. For high-volume streams or complex windowing, a stateful stream processor is usually a better fit. Never use execution environment memory as a source of state; monitor lag, hot keys, late events, retries, DLQs, and cost. When raw data retention, aggregate versioning, and replay policies are designed upfront, the system can scale to larger fleets while preserving accurate, verifiable results.
