# Configuring fixedDelay, initialDelay, cron, and maxMessagesPerPoll

In Spring Cloud Stream, `Supplier<T>` is a data producer. Unlike `Function` and `Consumer`, which are triggered when an input message arrives, a supplier has no input destination to trigger it. The framework needs another mechanism to invoke `get()` and obtain data to send to the output binding. The default mechanism is the **poller**: a scheduler that invokes the supplier periodically, converts the result into a message, and sends it through the binder to Kafka, RabbitMQ, or Pulsar.

The poller lets you control startup timing, the interval between invocations, cron schedules, and the maximum number of messages per poll. Proper configuration keeps the producer emitting at the right cadence, avoids overly aggressive source queries, limits load, and controls how much data enters the broker.

## 1. How Do Supplier and Poller Work?

A simple supplier can be declared as follows:

```java
import java.time.Instant;
import java.util.function.Supplier;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderEventSource {

    @Bean
    Supplier<OrderSnapshot> orderSnapshot(OrderService orderService) {
        return () -> orderService.nextSnapshot()
            .orElse(null);
    }
}

record OrderSnapshot(String orderId, Instant capturedAt) {}
```

The supplier returns an `OrderSnapshot` whenever it is invoked. Spring Cloud Stream sets up the output binding `orderSnapshot-out-0`. By default, the poller invokes the supplier every second; if the supplier returns data, the framework converts the result into a message and sends it to the configured destination. If the source has no data yet and returns `null`, no message payload is emitted for that invocation.

```yaml
spring:
  cloud:
    function:
      definition: orderSnapshot
    stream:
      bindings:
        orderSnapshot-out-0:
          destination: orders.snapshots
          content-type: application/json
```

The poller is an application-side trigger mechanism for the supplier. It is neither the consumer polling configuration of Kafka, RabbitMQ, or Pulsar, nor the schedule of an application-authored `@Scheduled` method. Once the supplier is triggered, the binder remains responsible for sending the message to the broker.

## 2. Four Properties to Understand

| Property | Meaning | Default Value in Default Poller |
|---|---|---|
| `fixedDelay` | Wait interval between periodic polls, measured in the configured time unit. | 1000 ms |
| `initialDelay` | Wait time before the first poll of the periodic schedule. | 0 |
| `cron` | Schedule expression specifying when the poller is triggered. | Not configured |
| `maxMessagesPerPoll` | Maximum number of messages a single poll event can fetch/emit. | 1 |

In YAML configuration, Spring Boot uses kebab-case: `fixed-delay`, `initial-delay`, `max-messages-per-poll`, `time-unit`. Java property names in API documentation are typically written in camelCase; both forms map to the same configuration.

In current Spring Cloud Stream configurations, default poller properties are exposed under the `spring.integration.poller` prefix. Older versions of Spring Cloud Stream used `spring.cloud.stream.poller`; the old prefix was deprecated as of Spring Cloud Stream 3.2. When upgrading applications, check the Spring Cloud Stream/Spring Boot version and use the corresponding prefix, avoiding mixing old and new configuration.

## 3. fixedDelay: Wait Interval Between Invocations

`fixedDelay` specifies how long the poller waits after one poll completes before starting the next one. For the default poller, the default value is 1000 milliseconds, equivalent to one second.

For example, set a 5-second wait interval:

```yaml
spring:
  integration:
    poller:
      fixed-delay: 5000
      time-unit: MILLISECONDS
```

If invoking the supplier and sending the message takes 400 milliseconds, the next poll will begin about 5 seconds after the previous one completes. The time between two poll starts is therefore approximately 5.4 seconds in this example, excluding scheduler jitter and system load.

You can change the time unit to make configuration easier to read:

```yaml
spring:
  integration:
    poller:
      fixed-delay: 5
      time-unit: SECONDS
```

Do not set `fixedDelay` too small if the supplier queries a database, calls an external API, or performs expensive work. A short interval can hammer the data source continuously, increase database load, and produce messages faster than consumers can process them.

## 4. initialDelay: Delaying the First Poll

`initialDelay` defines the wait time from when the poller starts until the first periodic poll. The default value is 0, meaning the poller can start immediately once the schedule is activated.

For example, wait 10 seconds after application startup before polling, with subsequent polls spaced 5 seconds apart:

```yaml
spring:
  integration:
    poller:
      initial-delay: 10000
      fixed-delay: 5000
      time-unit: MILLISECONDS
```

`initialDelay` is useful when the application needs time to finish initialization, wait for database connections, warm caches, or wait for a dependent service to become ready. It does not replace a readiness check and does not guarantee that dependencies are operational; if true readiness is required, the application must still verify connectivity and handle errors appropriately.

`initialDelay` applies to periodic schedules using delay/rate. When using `cron`, the schedule is determined by the timestamps of the cron expression; do not expect `initialDelay` to shift cron timestamps.

## 5. cron: Running on a Calendar Schedule

`cron` uses a cron expression to specify when the poller is invoked. This approach fits data sources that need to run at fixed wall-clock points, such as the top of each hour, every 15 minutes, or during a specific time window.

Spring uses a six-field cron expression consisting of second, minute, hour, day of month, month, and day of week. Examples:

| Expression | Schedule |
|---|---|
| `0 * * * * *` | Every minute, at second 0. |
| `0 */5 * * * *` | Every 5 minutes, at second 0. |
| `0 0 * * * *` | Every hour, at minute 0 and second 0. |
| `0 30 2 * * *` | Daily at 02:30:00. |
| `0 0 9 * * MON-FRI` | Weekdays at 09:00:00. |

Example poller configuration running every 15 minutes:

```yaml
spring:
  integration:
    poller:
      cron: "0 */15 * * * *"
      max-messages-per-poll: 10
```

When using cron, do not simultaneously configure `fixed-delay` on the same poller. The two properties represent different scheduling mechanisms: fixed delay measures a wait after the previous poll, while cron specifies points on the calendar. `initialDelay` is not used to offset cron timestamps.

Cron is appropriate when business logic ties to wall-clock times, such as aggregating data at the end of every hour or emitting start-of-day reports. If you only need to run again after a wait interval once the previous execution finishes, `fixedDelay` is more predictable.

## 6. maxMessagesPerPoll: Limiting Messages per Poll

`maxMessagesPerPoll` sets the maximum number of messages fetched/emitted during a single poll event. The default is 1. With an imperative supplier, one call to `get()` typically produces one message; if you set a limit greater than 1, the poller can invoke the supplier multiple times within the same poll cycle to fetch more messages until reaching the limit or until the source has no more data.

Example:

```yaml
spring:
  integration:
    poller:
      fixed-delay: 2000
      max-messages-per-poll: 20
```

With this configuration, the poller waits 2 seconds between poll cycles and can fetch up to 20 messages per cycle. If the supplier only has 3 pending records, the poll cycle can finish after fetching those 3 records; a limit of 20 does not mean the application must always produce 20 messages.

`maxMessagesPerPoll` does not mean batch size inside a single payload. It limits how many source messages are processed in one poll cycle. If the application wants to send a single message containing a list of multiple records, that is a separate payload type and serialization decision.

Increasing the limit can improve throughput and reduce poller trigger overhead, but it can also cause message bursts, put pressure on the broker and consumers, prolong a single poll cycle, and delay other scheduled tasks. Choose a value based on source data rate, producer send capacity, broker capacity, and downstream processing capacity.

## 7. Configuring the Default Poller

Properties under `spring.integration.poller` create a default poller configuration shared by bindings that require polling. Full example:

```yaml
spring:
  cloud:
    function:
      definition: orderSnapshot
    stream:
      bindings:
        orderSnapshot-out-0:
          destination: orders.snapshots
          content-type: application/json
  integration:
    poller:
      fixed-delay: 3000
      initial-delay: 5000
      max-messages-per-poll: 5
      time-unit: MILLISECONDS
```

The application begins polling after about 5 seconds, then waits 3 seconds after each poll completes before starting the next. Each cycle can emit at most 5 messages. The default poller is convenient when the application has only one polled source or multiple sources sharing the same schedule.

If multiple suppliers in the same application need different schedules, global configuration may not suffice. In that case, consider configuring a dedicated poller per output binding.

## 8. Configuring a Dedicated Poller per Binding

Spring Cloud Stream supports configuring a poller per output binding. For example, an application has two suppliers: one emitting snapshots every 5 seconds and one emitting daily reports. You can assign a separate schedule to each binding instead of forcing both onto the default poller.

Example separate configuration for `orderSnapshot-out-0` and `dailyReport-out-0`:

```yaml
spring:
  cloud:
    function:
      definition: orderSnapshot;dailyReport
    stream:
      bindings:
        orderSnapshot-out-0:
          destination: orders.snapshots
          producer:
            poller:
              fixed-delay: 5000
              initial-delay: 1000
              max-messages-per-poll: 10
        dailyReport-out-0:
          destination: reports.daily
          producer:
            poller:
              cron: "0 0 2 * * *"
```

The per-binding configuration path takes the form `spring.cloud.stream.bindings.<binding>.producer.poller.*`. Per-binding configuration is helpful when each source has a different emission cadence. Verify which properties are supported by your Spring Cloud Stream version; avoid assuming every binder version supports the exact same poller options.

## 9. fixedDelay vs. cron: Choosing Based on Business Requirements

| Need | Suitable Configuration | Reason |
|---|---|---|
| Read a source periodically, waiting a fixed interval after the last run finishes | `fixed-delay` | Intervals do not overlap when processing duration varies. |
| Run at exact fixed wall-clock times | `cron` | Schedule aligns with wall-clock time. |
| Wait for application startup to stabilize before running | `initial-delay` combined with fixed delay | Delays the first poll. |
| Fetch multiple records per cycle from a source with backlog | `max-messages-per-poll` greater than 1 | Increases the maximum message count per cycle. |
| Each supplier needs a different cadence | Per-binding poller | Avoids applying one global schedule to different sources. |

For example, an outbox-checking source might use a short fixed delay because events need to be emitted relatively quickly. An end-of-day report aggregation source should use cron to run at a scheduled time. A historical data ingestion source might increase `max-messages-per-poll` during a backfill phase and lower it again once caught up.

## 10. Suppliers Returning Reactive Data

Not all suppliers are polled the same way. An imperative supplier like `Supplier<OrderEvent>` is normally polled periodically, producing one result per invocation. A reactive supplier like `Supplier<Flux<OrderEvent>>` can represent a continuous stream; in that case, the framework typically invokes the supplier once to obtain the publisher rather than calling it again on every cycle.

If you need to poll a data source periodically while having the supplier return a finite `Flux` for each query, you can use `@PollableBean` to tell the framework that this reactive supplier still needs to be polled:

```java
import java.util.function.Supplier;

import org.springframework.cloud.function.context.PollableBean;
import reactor.core.publisher.Flux;

@PollableBean
Supplier<Flux<OrderEvent>> pendingOrderEvents(OrderService orderService) {
    return () -> Flux.fromIterable(orderService.findPendingEvents());
}
```

With `@PollableBean`, the framework can poll a finite reactive supplier on a schedule and split each element into a separate message according to the default `splittable` configuration. If you want to keep the entire `Flux` as a single result instead of splitting elements, review the `splittable` attribute and payload contract. Do not use a periodic poller for an infinite `Flux` that already emits data continuously; doing so can create unwanted multiple subscriptions.

## 11. Considerations for Source Processing and Duplicate-Emission Safety

The poller invokes the supplier on a schedule, but it does not guarantee that a source record is emitted only once. If the supplier queries a database for pending records, the application needs a safe mechanism to mark or claim records.

For example, if the supplier reads 10 pending records without marking them as processed, the next poll may re-emit the same data. If the application marks records as sent before publishing succeeds, a broker failure can lose events. Patterns like transactional outbox, `NEW/IN_PROGRESS/SENT` status transitions, claim locks, leases, and idempotency help manage this boundary.

When `max-messages-per-poll` is greater than 1, ensure each supplier invocation fetches the next slice of data rather than repeatedly returning the same record. Claiming data must be safe when the application runs multiple instances or when an instance restarts mid-poll.

The poller also does not replace retries and error handling. If the supplier throws an exception, the poll can fail and be recorded according to Spring Integration/Spring Cloud Stream mechanisms. Define how source errors, broker send failures, and retries are handled; do not assume a failed poll will automatically ensure all records are emitted later.

## 12. Common Configuration Mistakes

1. **Using an outdated version prefix.** Configuring `spring.cloud.stream.poller` on newer versions may no longer bind as expected; check your version and use `spring.integration.poller` where appropriate.
2. **Configuring both fixed delay and cron together.** These are two distinct triggers; choose one mechanism per poller.
3. **Assuming initialDelay shifts the cron schedule.** Initial delay applies to periodic triggers; cron still fires at the expression's calendar points.
4. **Setting maxMessagesPerPoll too high.** A single poll cycle can create a large burst, increasing pressure on the broker and consumers.
5. **Assuming the poller controls the broker consumer.** Here the poller triggers the supplier; consumers receive messages via binder/broker mechanisms.
6. **Using a poller for a continuous reactive supplier.** A supplier returning an infinite `Flux` generally only needs to be invoked once; use `@PollableBean` for finite `Flux` cases that require polling.
7. **Failing to mark source data after emission.** The supplier may re-emit records on the next poll or miss records if status is updated at the wrong time.
8. **Scheduling without accounting for processing time.** With fixed delay, the wait interval starts after the previous poll finishes; the actual start-to-start cycle is longer than configured if processing takes time.

## 13. Testing and Observing the Poller

Test timing behavior and message counts at the application level:

| Case | What to Verify |
|---|---|
| fixed delay | Time between polls matches the configured wait after the previous poll completes. |
| initial delay | No emissions occur before the initial wait elapses. |
| cron | The poller runs only at the points specified by the expression. |
| max messages | A cycle does not exceed the configured limit and stops when the source is exhausted. |
| Per-binding poller | Two suppliers can run on independent schedules. |
| Supplier error | Exceptions are observed and the source can recover per the designed policy. |
| Multiple instances | No unintended duplicate emissions occur when accessing a shared data source. |

Avoid long `Thread.sleep()` calls in unit tests to wait for schedules. You can test supplier logic separately, test bindings with the Spring Cloud Stream Test Binder, and use a controllable scheduler/clock if the architecture permits. Integration tests should verify that messages are actually sent to the binder and measure emission timing within a reasonable tolerance.

Metrics to monitor include poll count, supplier execution duration, messages created per cycle, cycles with no data, source query errors, publish errors, and latency from data readiness to message dispatch. If backlog grows steadily, consider increasing the limit or poll frequency while confirming that the broker and consumers have enough capacity.

## 14. Configuration Selection Checklist

Before setting up a poller for a supplier, answer these questions:

1. Does the data source need to emit at a relative interval or at fixed wall-clock times?
2. Is a delay needed after application startup?
3. How long does one supplier invocation take, and what load might it place on databases/APIs?
4. How many messages at most should each cycle emit to achieve throughput without causing bursts?
5. Do multiple instances access the source concurrently, and how is data claimed/marked?
6. Is the supplier imperative, continuous reactive, or finite reactive requiring polling?
7. Does the application use the default poller or require separate per-output-binding configuration?
8. Are metrics and alerts in place to detect slow pollers, source errors, or growing backlogs?

For sources that should run steadily after each processing cycle, start with a moderate `fixed-delay` and a small `max-messages-per-poll`. Use `initial-delay` when startup warm-up time is needed. Choose `cron` when business rules require a fixed wall-clock schedule. Increase the message limit only when the source, broker, and consumers have sufficient capacity. A sound poller configuration must align with actual data velocity and source state management so message emission stays stable under both high load and application failures.

## References

- [Spring Cloud Stream Reference – Producing and Consuming Messages, Polling Configuration Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
