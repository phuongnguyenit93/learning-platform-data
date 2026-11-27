# Producing Periodic Messages with Supplier

Not every message appears after a user request or after another service emits an event. Many systems need to emit messages periodically: heartbeats to report that a process is still alive, inventory snapshots every few minutes, aggregated metrics over a time interval, or device status pulled from a data source on a schedule. In Spring Cloud Stream, a `Supplier<T>` function can produce a payload and let the framework invoke the function on a polling schedule, then send the result through the output binding.

`Supplier` is the starting point of a message flow created by the application itself. It has no input binding; each time it is invoked, the function provides a value to the output binding. The poller controls the invocation cadence. The binder connects the binding to a broker such as Kafka, RabbitMQ, or Pulsar. To use this model properly, you need to distinguish when the message is created, the polling cadence, and when the broker acknowledges delivery.

This lesson belongs to the **Message Producers** chapter of the `SPRING_CLOUD_STREAM` module, where applications use the `Supplier`/`Function`/`Consumer` functional model, bindings, and binders to process events. The content focuses on producing periodic messages with a synchronous supplier, configuring the poller, creating payloads with identifiers, and operating safely when the application runs multiple instances.

## 1. What Does Supplier Do in a Message Flow?

In Java, `Supplier<T>` is a functional interface with a `get()` method that returns a value of type `T` and takes no input parameters. Spring Cloud Stream can use a supplier bean as a message producer. For a synchronous supplier, the framework invokes `get()` using a polling mechanism; the returned value is converted into a message and sent to the output binding.

```text
Spring's Poller
      |
      | invokes periodically
      v
Supplier<T>.get()
      |
      | returns payload T
      v
Message conversion / output binding
      |
      v
Binder
      |
      v
Kafka / RabbitMQ / Pulsar
```

For example, a monitoring service wants to emit a heartbeat every 5 seconds. The supplier creates a `Heartbeat` object containing the service name, creation timestamp, and a local sequence number. Spring Cloud Stream serializes the payload according to the binding's content type and passes it to the binder to send to the configured destination.

`Supplier` fits well when the application proactively generates data at a regular cadence. If a message should only be emitted when a business action occurs—such as an order just being created—emit the message from the business processing flow or use an event-driven emission mechanism instead of unnecessary polling.

## 2. Declaring a Supplier as a Bean

A supplier is typically declared using `@Bean` in a Spring configuration class. For example:

```java
import java.time.Instant;
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.Supplier;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record Heartbeat(
    String service,
    long sequence,
    Instant generatedAt
) {}

@Configuration
class HeartbeatProducer {

    @Bean
    Supplier<Heartbeat> heartbeatSupplier() {
        AtomicLong sequence = new AtomicLong();

        return () -> new Heartbeat(
            "order-service",
            sequence.incrementAndGet(),
            Instant.now()
        );
    }
}
```

Spring Cloud Stream recognizes the `heartbeatSupplier` bean as a producer. The default output binding is named by convention:

```text
heartbeatSupplier-out-0
```

The `out-0` suffix denotes the first output of the function. A supplier has no `in-0` binding because it does not receive messages from a broker. Each time the poller calls `get()`, the example above creates a new heartbeat with the current time and increments the sequence in the instance's memory.

`AtomicLong` protects the increment operation in case the bean is invoked from multiple threads. However, this sequence is only meaningful within the lifecycle of a single instance: it resets to its initial value when the application restarts, and each replica has its own counter. Do not use an in-memory counter as a system-wide unique identifier. If you need a stable event identifier, use a UUID or an ID issued from an appropriate durable source.

## 3. Configuring the Output Binding

A supplier requires an output binding connected to a destination. Example configuration for emitting heartbeats as JSON:

```yaml
spring:
  cloud:
    function:
      definition: heartbeatSupplier
    stream:
      bindings:
        heartbeatSupplier-out-0:
          destination: system.heartbeat
          content-type: application/json
```

Configuration elements:

- `spring.cloud.function.definition` selects the function bean to activate.
- `heartbeatSupplier-out-0` is the supplier's default output binding.
- `destination` is the logical target name that the binder maps to a broker resource.
- `content-type: application/json` specifies that the payload is serialized to JSON.

With Kafka, the destination is usually a topic. With RabbitMQ, an output binding typically publishes to an exchange and the routing topology determines which queue receives the message. With Pulsar, the destination is a topic. The payload creation logic inside the supplier can remain unchanged when switching binders, while physical resources, permissions, and connection settings still need to match the broker.

You do not need to create a `MessageChannel` manually for standard function cases. Spring Cloud Stream derives the binding from the bean name and function role. Always verify the actual binding name when renaming a bean because old configuration may no longer match.

## 4. Controlling Emission Cadence with the Poller

A synchronous supplier is invoked by a poller. You can configure the wait interval and initial delay under `spring.cloud.stream.poller`:

```yaml
spring:
  cloud:
    function:
      definition: heartbeatSupplier
    stream:
      poller:
        initial-delay: 1000
        fixed-delay: 5000
      bindings:
        heartbeatSupplier-out-0:
          destination: system.heartbeat
          content-type: application/json
```

In this example:

- `initial-delay: 1000` delays the first poll by approximately 1,000 milliseconds after the poller starts.
- `fixed-delay: 5000` sets a 5,000-millisecond interval between configured poll executions.

The unit for these poller properties is milliseconds. Default values when unconfigured depend on the version and Spring Integration/Spring Cloud Stream configuration; declare them explicitly when the emission cadence is a business or operational requirement.

`fixed-delay` does not mean wall-clock emissions at exact 00, 05, 10, 15 second marks. With fixed delay, the wait interval is measured between executions; the duration of the previous poll also affects when the next message is created. If you need a wall-clock schedule—for example, exactly 09:00 every day in a specific time zone—use a dedicated scheduling mechanism such as Spring Scheduling or Quartz and then proactively emit messages through the appropriate output binding.

### Choosing a Polling Interval

| Need | Reference Polling Interval | Notes |
|---|---|---|
| Monitoring heartbeat | A few seconds to tens of seconds | Balance failure-detection sensitivity against message volume |
| Metric snapshot | A few minutes | Account for query cost and data latency |
| Periodic status aggregation | A few minutes or longer | Emit only on change if business logic allows |
| Reading an external data source | Based on API or source system limits | Avoid polling faster than the source's capacity |

There is no single interval that fits every application. Polling too frequently increases load on the producer, broker, and consumer. Polling too infrequently causes data to arrive late or monitoring to detect failures slowly.

## 5. Supplier Creating a Fresh Payload on Each Invocation

A supplier should return a payload representing a single emission. Example inventory snapshot:

```java
import java.time.Instant;
import java.util.List;
import java.util.function.Supplier;

import org.springframework.context.annotation.Bean;

record StockItem(String sku, int available) {}

record StockSnapshot(
    Instant capturedAt,
    List<StockItem> items
) {}

@Bean
Supplier<StockSnapshot> stockSnapshotSupplier(InventoryReader inventory) {
    return () -> new StockSnapshot(
        Instant.now(),
        inventory.readCurrentStock()
    );
}
```

Each time the supplier is invoked, the application reads the current data and builds a new snapshot. In a real implementation, `InventoryReader` is a business bean provided by the application. Consider query duration, payload size, read transactions, and the possibility of the data source changing while capturing the snapshot.

If reading the source takes longer than the polling interval, executions may be delayed depending on the scheduler and configuration. Do not spawn new threads manually on every supplier call. Use bounded execution mechanisms, timeouts, and appropriate backpressure if the data source has unstable latency.

## 6. How to Handle No New Data?

A supplier can return `null` to indicate that the current poll produces no message. For example, emit a snapshot only when changes exist:

```java
@Bean
Supplier<StockSnapshot> changedStockSupplier(InventoryReader inventory) {
    return () -> inventory.readChangedStockSnapshot()
        .orElse(null);
}
```

Here `readChangedStockSnapshot()` returns `Optional<StockSnapshot>`. If there is no new data, the supplier returns `null` and that poll emits no payload. Verify this behavior against the supplier type and framework version in use; do not return an empty object if consumers might misinterpret it as a valid snapshot.

If you need to emit a "no changes" status message, represent that explicitly in the schema—such as `changeCount: 0` and `capturedAt`—instead of using `null`. If you do not want to emit a message when the source has not changed, `null` is more appropriate.

## 7. Sending a Message with Headers

A supplier can return `Message<T>` when you need to set headers such as event type, correlation ID, or event ID:

```java
import java.time.Instant;
import java.util.UUID;
import java.util.function.Supplier;

import org.springframework.context.annotation.Bean;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

record Heartbeat(String service, Instant generatedAt) {}

@Bean
Supplier<Message<Heartbeat>> heartbeatMessageSupplier() {
    return () -> MessageBuilder
        .withPayload(new Heartbeat("order-service", Instant.now()))
        .setHeader("eventId", UUID.randomUUID().toString())
        .setHeader("eventType", "ServiceHeartbeat")
        .build();
}
```

The payload holds business data; headers carry metadata for routing, tracing, or processing. Do not place all metadata into the JSON payload if consumers only need them as transport attributes. Also check which headers are supported by the binder and how headers are mapped across the broker, because not every broker preserves every header in the same way.

When using `Message<T>`, you still need to configure the content type for the output binding. Payload format and message metadata are two separate concerns. Do not put sensitive data in headers, because headers can also be logged or passed through intermediate systems.

## 8. Multi-Instance Suppliers and Duplicate Emission Risk

When an application is deployed across multiple replicas, each instance typically has its own supplier bean and poller. If there are 3 replicas, all 3 may invoke the supplier on schedule and emit heartbeats or snapshots. This may be intentional if each instance should report its own status, or it may be a bug if you only want a single system-wide snapshot per interval.

```text
Replica A -- Supplier + poller --+
Replica B -- Supplier + poller --+--> destination: system.heartbeat
Replica C -- Supplier + poller --+
```

Define the emission unit clearly:

- **Per instance:** each replica emits its own heartbeat, with `instanceId` in the payload to distinguish them.
- **Per application:** only one designated instance emits the shared snapshot.
- **Per data partition:** each instance emits data for a specific region or key set.

If only one instance is allowed to emit, you can use leader election, a distributed lock, or a dedicated scheduler running a single replica. Handle leader changes and lease expiration carefully to avoid two instances emitting concurrently during handoff.

Consumers should also be idempotent in case a message can be resent. A unique `eventId` helps identify each emission; for periodic snapshots, you can use a `(sourceId, capturedAt)` pair or a stable `snapshotId` per period. Do not rely on a timestamp alone as a unique key if clock precision or synchronization across machines is not guaranteed.

## 9. Time, Identifiers, and Replayability

A periodic message should carry enough context for consumers to understand which point in time it represents:

```json
{
  "eventId": "e7a2d1f2-5b93-4c51-9a2a-9c15b4c1c1e2",
  "eventType": "StockSnapshotCreated",
  "source": "warehouse-service",
  "capturedAt": "2026-11-24T08:30:00Z",
  "schemaVersion": 1,
  "items": [
    { "sku": "COFFEE-01", "available": 42 },
    { "sku": "TEA-03", "available": 18 }
  ]
}
```

Distinguish between:

- `capturedAt`: when the data was read or the snapshot was created.
- Publish time: when the producer sent the message to the broker; this may differ from capture time.
- Processing time: when the consumer received and processed the message; this may be later due to backlog.

If a consumer uses snapshots to update current state, it must avoid applying an older snapshot after a newer one. You can compare `capturedAt`, a per-source sequence, or a snapshot version. If data is split across multiple partitions or instances, define ordering within the scope of each source or aggregate.

Polling does not automatically maintain durable history. When the application stops, polls scheduled during the downtime are not automatically backfilled when the application restarts. If business requirements demand recording every due period, store the execution schedule or periods to emit in a database and design an explicit catch-up process.

## 10. Errors When Supplier Creates or Sends Messages

Errors can occur at multiple stages:

| Stage | Example | How to Handle |
|---|---|---|
| Data retrieval | Database timeout, unresponsive source API | Timeouts, bounded retries, circuit breakers, and source error metrics |
| Payload creation | Missing data or schema violation | Validate before returning the message; log with event ID if available |
| Serialization | Data type unsupported by converter | Check content type, Java types, and converters |
| Publish | Broker disconnected or rejected publish | Rely on binder/client retries and producer error policy; do not assume the message was persisted |
| Consumer processing | Valid JSON payload but invalid business logic | Consumer validation, bounded retries, and an appropriate DLQ |

Do not catch every exception inside the supplier and silently return `null`. Doing so turns a data-source failure into a "no message" poll, hiding the incident from the system. Distinguish between having no new data and failing to retrieve data.

For transient errors, you can use retry with backoff at the data-source access layer. However, factor retry duration into the polling cycle and deployment timeouts. If the supplier blocks for too long, the poller may fail to keep its expected cadence. For permanent errors such as misconfiguration or invalid schema, log clearly and raise an alert.

## 11. Do Not Confuse Polling with Exact Business Schedules

Polling is how the framework asks the supplier at an interval. It fits tasks like "check whether data is ready to emit" or "generate heartbeats at an approximate cadence." Polling is not a durable scheduler that guarantees exactly one emission at an exact wall-clock time.

| Requirement | Approach |
|---|---|
| Emit a heartbeat every few seconds | Synchronous supplier with a fixed-delay poller |
| Read new rows from a table periodically | Supplier calls a service/repository with a bounded query |
| Emit a report at 08:00 every day | Cron-based scheduler or Quartz with an explicit time zone and catch-up policy |
| Guarantee one emission per business period | Store emission periods and state in a database, using a unique key/outbox |
| Emit immediately when a business action completes | Emit an event from the business flow or a Function's output |

If the emission schedule has financial or legal significance, do not rely solely on an in-memory poller. Persist the schedule, execution records, and emission results so they can be reconciled after a restart.

## 12. Testing a Periodic Supplier

Test suppliers at both the function level and the integration level:

| Scenario | How to Test | Expected Result |
|---|---|---|
| Supplier creates payload | Call `get()` directly in a unit test | Payload has the expected fields, timestamp, and identifier |
| Poller runs per configuration | Start the context with the poller and output test binding | Invocation count matches the test time window |
| No new data | Supplier returns `null` | No unintended empty message is emitted |
| Data source failure | Have the repository throw an exception | Error is recorded and observable, not treated as no data |
| Broker unavailable | Stop the broker or block connectivity | Publish failure is detected via binder/client mechanisms |
| Multiple replicas | Run multiple test instances | Confirm producer count matches design, with no unintended duplicates |
| Restart | Stop and restart the application | Understand whether sequence, polling schedule, and data periods are reset or missed |

Example unit test for the supplier:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import org.junit.jupiter.api.Test;

class HeartbeatProducerTest {

    @Test
    void createsHeartbeatWithIncreasingSequence() {
        var supplier = new HeartbeatProducer().heartbeatSupplier();

        Heartbeat first = supplier.get();
        Heartbeat second = supplier.get();

        assertEquals(1, first.sequence());
        assertEquals(2, second.sequence());
        assertNotNull(first.generatedAt());
    }
}
```

The unit test above checks payload creation logic; it does not verify that the poller actually runs on schedule or that the binder sends messages to the broker. Integration tests need to verify the `heartbeatSupplier-out-0` binding, destination, and content type using a test binder or an appropriate broker.

## 13. Observability and Operations

A periodic supplier should expose metrics and logs sufficient to answer these questions:

- When did the most recent poll start and finish?
- How many polls produced a message, and how many had no new data?
- What are the average and maximum data-retrieval durations?
- How many data-source read, serialization, or publish errors occurred?
- How old is a produced message when the consumer processes it?
- How many messages does each instance emit over a given time window?
- Were any scheduled periods missed after an application restart?

Logs should include `eventId`, `source`, `capturedAt`, and `instanceId` whenever possible. Avoid logging full payloads if they contain sensitive data. Metrics should use bounded-cardinality labels; do not put UUIDs or order IDs in metric labels.

For heartbeats, the monitoring consumer should evaluate the time since the last heartbeat per `instanceId`. Do not rely solely on total message rate across the entire destination, because one instance may stop emitting while others remain active.

## 14. Recommended Implementation Workflow

When building a periodic producer with `Supplier`:

1. Identify the data to emit and why it needs to be emitted periodically.
2. Choose the payload type and schema; add an event ID, source ID, and appropriate creation timestamp.
3. Declare a `Supplier<T>` bean whose logic produces one message per invocation.
4. Choose the output binding named `<functionName>-out-0` and configure its destination and content type.
5. Set `initial-delay` and `fixed-delay` based on acceptable latency, query cost, and broker capacity.
6. Determine whether the application runs a single replica or multiple replicas; choose per-instance, per-application, or partitioned emission.
7. Design idempotency, sequence/versioning, and a catch-up policy if missed periods are unacceptable.
8. Handle the no-data case separately from data-source errors.
9. Test the poller, binder, broker, restarts, and multi-instance deployments.
10. Monitor poll frequency, payload creation duration, publish failures, and consumer lag.

## 15. Self-Check

- [ ] Can explain why `Supplier<T>` is suitable for messages that the application proactively emits.
- [ ] Can identify the default output binding `<functionName>-out-0`.
- [ ] Can configure `initial-delay` and `fixed-delay` for the poller.
- [ ] Can distinguish fixed-delay polling from wall-clock or cron schedules.
- [ ] Know how to return a new payload, a `Message<T>` with headers, or `null` when there is no data.
- [ ] Recognize the risk of multiple replicas emitting duplicate messages.
- [ ] Can design event ID, source ID, and timestamps to handle duplicates or stale data.
- [ ] Can distinguish data-retrieval errors, serialization errors, and publish errors.
- [ ] Know how to test the supplier in isolation versus testing poller/binding integration.

## Conclusion

`Supplier<T>` lets an application proactively produce messages without needing an input binding. For a synchronous supplier, the poller invokes the function periodically; the result is serialized according to the content type and sent via the `<functionName>-out-0` output binding. Configuring `initial-delay` and `fixed-delay` controls startup delay and polling cadence. In production, you must account for data-retrieval duration, publish failures, multiple replicas, event identifiers, and application stops or restarts. If the requirement calls for an exact business schedule or zero missed periods, add a durable scheduler and persist execution state rather than relying solely on an in-memory poller.
