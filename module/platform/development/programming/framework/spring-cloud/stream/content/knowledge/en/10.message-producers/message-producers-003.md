# Configuring a Dedicated Poller for Each Output Binding

In Spring Cloud Stream, an imperative `Supplier` provides data when the framework invokes its `get()` method. Because a `Supplier` receives no input messages, the framework needs a trigger mechanism to know when to fetch new data. The poller performs that job: it invokes the `Supplier` on a schedule, receives the returned value, and converts it into a message sent through the output binding to the broker.

By default, the shared poller produces one message per second for a standard `Supplier`. The default configuration works for a simple producer, but an application can have multiple sources with different emission cadences. For example, order events may need to be emitted nearly continuously, while metric snapshots only need to be emitted once per minute. Spring Cloud Stream lets you configure a separate poller directly on each output binding so each source has a cadence, start time, and maximum messages per poll suited to its load.

## 1. How Does the Poller Trigger a Supplier?

`Function` and `Consumer` are typically invoked when a message arrives on an input binding. Because a `Supplier` is a producer, it has no input binding to trigger it. For an imperative `Supplier`, Spring Cloud Stream uses a poller to call `get()` periodically.

~~~java
import java.time.Instant;
import java.util.UUID;
import java.util.function.Supplier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public record OrderEvent(String orderId, Instant createdAt) {}

@Configuration
class OrderSourceConfiguration {

    @Bean
    Supplier<OrderEvent> orderEvents() {
        return () -> new OrderEvent(
            UUID.randomUUID().toString(),
            Instant.now()
        );
    }
}
~~~

The `orderEvents` bean creates an `OrderEvent` each time `get()` is called. Spring Cloud Stream emits that value through the output binding with the default name `orderEvents-out-0`. If the binding's destination is `orders.created`, the binder sends the message to the corresponding destination on Kafka, RabbitMQ, or Pulsar.

~~~mermaid
flowchart LR
    P["Poller"] -->|"Calls get() on schedule"| S["Supplier<OrderEvent>"]
    S -->|"OrderEvent"| O["orderEvents-out-0"]
    O --> B[("Binder")]
    B --> D[("orders.created")]
~~~

The poller controls when the `Supplier` is invoked inside the application. It is not the consumer mechanism that reads a topic or queue from the broker. Sending messages to the broker is still handled by the output binding and binder.

## 2. Output Binding Name to Configure

For a `Supplier` bean named `orderEvents`, the default output binding name is `orderEvents-out-0`. This convention derives from the bean name and data direction:

| Component | Example Name | Meaning |
|---|---|---|
| Supplier bean | orderEvents | Producer function detected by Spring Cloud Function |
| Output binding | orderEvents-out-0 | First output port of the Supplier |
| Destination | orders.created | Topic, queue, or logical target on the broker |
| Poller | orderEvents-out-0.producer.poller | Dedicated schedule configuration for this output binding |

The binding name is the configuration key inside the application. The destination is the resource to which the binder connects. Do not substitute the destination name for the binding name under `producer.poller`.

For example, if the binding name has been explicitly mapped via `spring.cloud.stream.function.bindings`, use the mapped binding name when declaring `producer` properties. If no mapping exists, keep the default name derived from the `Supplier` bean.

## 3. Configuring the Shared Poller

If all `Supplier` beans in an application share the same emission cadence, you can configure the default poller once. In current Spring Cloud Stream versions, the default poller property group uses the `spring.integration.poller` prefix:

~~~yaml
spring:
  integration:
    poller:
      fixed-delay: 1000
      initial-delay: 0
      max-messages-per-poll: 1
~~~

Commonly used properties:

| Property | Meaning | Default |
|---|---|---|
| fixed-delay | Wait interval between periodic poller runs, in milliseconds | 1000 |
| initial-delay | Wait time before the first poll | 0 |
| max-messages-per-poll | Maximum number of messages produced in a single poll | 1 |
| cron | Schedule expression using a Cron Trigger | Not set |
| time-unit | Time unit applied to delay values | MILLISECONDS |

For example, `fixed-delay` set to `2000` means the shared poller waits on a two-second cadence. This configuration affects imperative `Supplier` beans that rely on the default poller. If each source needs a different schedule, configure it at the output binding level instead of changing the shared poller.

In older versions, documentation used the `spring.cloud.stream.poller` prefix. That property was deprecated in Spring Cloud Stream 3.2 in favor of configuring the Spring Integration poller via `spring.integration.poller`. For projects being upgraded, check your specific Stream version and migration guide rather than copying old configuration.

## 4. Configuring a Dedicated Poller for an Output Binding

To configure a dedicated poller, place `poller` under the binding's `producer` branch:

~~~yaml
spring:
  cloud:
    function:
      definition: orderEvents
    stream:
      bindings:
        orderEvents-out-0:
          destination: orders.created
          producer:
            poller:
              fixed-delay: 2000
              initial-delay: 500
              max-messages-per-poll: 1
~~~

In this example:

- `orderEvents` is the activated `Supplier` bean name.
- `orderEvents-out-0` is the output binding created by the `Supplier`.
- `orders.created` is the destination on the broker.
- `producer.poller.fixed-delay` sets a dedicated interval of 2000 milliseconds.
- `producer.poller.initial-delay` delays the first poll by 500 milliseconds after initialization.
- `producer.poller.max-messages-per-poll` limits each poll to producing at most one message.

The key configuration path is:

~~~text
spring.cloud.stream.bindings.orderEvents-out-0.producer.poller.fixed-delay
~~~

Dedicated poller properties are declared under `producer.poller` of the output binding. Do not place them under `consumer`, because a `Supplier` emits data outbound. Also do not place them under `spring.cloud.stream.kafka.bindings` or `spring.cloud.stream.rabbit.bindings`: the poller is a framework trigger mechanism, not a broker-specific connection option.

## 5. Using Multiple Suppliers with Different Cadences

An application can register multiple functional beans. When there are multiple `Supplier`/`Function`/`Consumer` beans, explicitly declare which beans to activate using `spring.cloud.function.definition`. Use a semicolon to list multiple independent functions; do not use a pipe character, because that represents function composition.

Example application with two sources:

~~~java
import java.time.Instant;
import java.util.UUID;
import java.util.function.Supplier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public record OrderCreated(String orderId, Instant createdAt) {}

public record MetricSnapshot(Instant capturedAt, long activeOrders) {}

@Configuration
class EventSources {

    @Bean
    Supplier<OrderCreated> orderEvents() {
        return () -> new OrderCreated(
            UUID.randomUUID().toString(),
            Instant.now()
        );
    }

    @Bean
    Supplier<MetricSnapshot> metricSnapshots() {
        return () -> new MetricSnapshot(Instant.now(), 42L);
    }
}
~~~

Declare configuration for each output:

~~~yaml
spring:
  cloud:
    function:
      definition: "orderEvents;metricSnapshots"
    stream:
      bindings:
        orderEvents-out-0:
          destination: orders.created
          content-type: application/json
          producer:
            poller:
              fixed-delay: 500
              initial-delay: 0
              max-messages-per-poll: 1
        metricSnapshots-out-0:
          destination: metrics.snapshots
          content-type: application/json
          producer:
            poller:
              fixed-delay: 30000
              initial-delay: 5000
              max-messages-per-poll: 1
~~~

The two sources have different schedules:

| Supplier | Output binding | Destination | Fixed delay | Initial delay |
|---|---|---|---:|---:|
| orderEvents | orderEvents-out-0 | orders.created | 500 ms | 0 ms |
| metricSnapshots | metricSnapshots-out-0 | metrics.snapshots | 30000 ms | 5000 ms |

With per-binding configuration, changing the metric snapshot interval does not affect the order event emission rate. Each output binding can have its own destination, content type, and poll schedule.

The examples above illustrate schedule configuration; in a real application, the `Supplier` should read from a business source. Do not emit a dummy record every cycle if the goal is to read pending records waiting to be processed.

## 6. Choosing fixed-delay or cron

The poller supports periodic scheduling via `fixed-delay` or a Cron Trigger. Choose the one that matches the timing semantics of the task:

| Scheduling Mode | Suitable When | Example |
|---|---|---|
| fixed-delay | You want to wait a duration between polls | Check a job queue every 2 seconds |
| cron | You want to run at specific calendar times | Emit a report at the top of each hour |

Example using `cron` on an output binding:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        hourlyReport-out-0:
          destination: reports.hourly
          producer:
            poller:
              cron: "0 0 * * * *"
              max-messages-per-poll: 1
~~~

Spring Cron expressions have a seconds field at the beginning. The expression `0 0 * * * *` means running at second 0, minute 0 of every hour. When using `cron`, do not simultaneously set `fixed-delay` on the same poller; choose one schedule type to avoid confusing configuration.

`fixed-delay` fits continuous polling, whereas `cron` fits tasks on a fixed wall-clock schedule. Neither guarantees exact delivery timing when the application is busy, the JVM pauses, the host is overloaded, or the broker is unavailable.

## 7. Understanding max-messages-per-poll

`max-messages-per-poll` limits how many messages the poller can produce in a single trigger. The default value is 1. For a `Supplier` reading one record at a time from a data source, a value greater than 1 can allow a single poll to fetch multiple consecutive records until reaching the limit or until the source has no more data.

Example:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        pendingOrders-out-0:
          destination: orders.pending
          producer:
            poller:
              fixed-delay: 5000
              max-messages-per-poll: 20
~~~

The poller can fetch at most 20 messages in one poll. That does not mean the system will always emit 20 messages; the actual count depends on available data and how the `Supplier` indicates there is no more data.

Increasing `max-messages-per-poll` can raise throughput when the source has many records, but it also makes each poll last longer and creates burst load on the broker. Weigh batch size, processing duration, query limits, memory, and target system capacity.

Do not confuse `max-messages-per-poll` with Kafka consumer batch mode. This property controls how many messages are produced by the producer-side poller; batch consumption is a consumer-side reading mechanism with separate configuration.

## 8. Imperative Supplier vs. Reactive Supplier

The default poller fits an imperative `Supplier` of the form `Supplier<T>`. Each time `get()` returns a value, the framework can send that value as a message.

A reactive `Supplier` of the form `Supplier<Flux<T>>` is typically invoked once to provide a continuous stream. The framework does not repeatedly call `get()` on a schedule as it does with an imperative `Supplier`, because `Flux` already represents a stream that will keep emitting data.

If `Supplier<Flux<T>>` represents a finite dataset that needs periodic querying, you can use the `PollableBean` annotation to tell the framework that this reactive source still needs to be polled. Example:

~~~java
import org.springframework.cloud.function.context.PollableBean;
import reactor.core.publisher.Flux;
import java.util.function.Supplier;

@PollableBean
public Supplier<Flux<String>> pendingBatch() {
    return () -> Flux.just("order-A", "order-B");
}
~~~

The pollable behavior of a reactive `Supplier` can depend on how the stream is split into individual messages and on `splittable` configuration. Check the documentation for your version before applying it. Do not add `PollableBean` just because a `Supplier` returns a `Flux`; only use it when a finite stream needs to be re-polled on a schedule.

## 9. Poller vs. External Triggers

Not every output binding needs a `Supplier`. If data arrives from an HTTP endpoint, a callback, or a system with its own trigger mechanism, the application can use `StreamBridge` to send messages when an event occurs.

Example:

~~~java
import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final StreamBridge streamBridge;

    public OrderEventPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public boolean publish(OrderCreated event) {
        return streamBridge.send("ordersOutput-out-0", event);
    }
}
~~~

In this case, `StreamBridge` sends when `publish` is called. No poller is needed for that output binding. If you both create a scheduled `Supplier` poller and use `StreamBridge` to emit the same kind of data, clearly define each source's responsibility to avoid duplicate emissions.

## 10. Threads, Processing Time, and Data Source Load

The `Supplier` is polled by the framework's scheduling mechanism. Do not assume `get()` executes on an HTTP request thread or on a fixed application thread. This matters when the `Supplier` uses `ThreadLocal`, tracing context, or libraries requiring thread affinity.

Operational principles:

- Keep `get()` execution time bounded and set timeouts on dependent calls.
- Avoid letting a slow query tie up the poller for too long.
- Bound the number of records fetched in each poll.
- Monitor poll duration, emitted message counts, and data-source access errors.
- Choose a cadence suited to the broker's and consumer's ingestion capacity.
- Avoid using multiple `Supplier` beans to poll the same record set without a data-claiming partition mechanism.

If a poll takes a long time, the effective cadence can stretch out. A poller is a scheduling mechanism, not a throughput guarantee. When you need thread control or need to send from an existing callback, `StreamBridge` is usually a better fit.

## 11. The Poller Does Not Replace Delivery Guarantees

The poller decides when to call the `Supplier`. It does not guarantee that a record is written to the broker exactly once or never lost. If the `Supplier` reads a database row and marks it as processed before the broker confirms delivery, a network failure can leave the data unsent while the source considers it complete.

For business data requiring high reliability, you can use the Transactional Outbox pattern:

1. The business transaction writes business data and an outbox record in the same database transaction.
2. The `Supplier` reads unpublished outbox records.
3. The application sends the records via the output binding.
4. Once an appropriate confirmation strategy succeeds, mark the record as sent or update delivery status.
5. Consumers process idempotently to tolerate redelivered messages.

Completion marking must be designed carefully around the binder's and broker's confirmation capabilities. Do not delete or mark records before having evidence of a successful send. The poller can run again after errors or application restarts; therefore, unique keys and duplicate-handling capability are essential.

## 12. Testing Poller Configuration

Verify both `Supplier` logic and binding behavior:

| Test Level | What to Verify |
|---|---|
| Supplier unit test | `get()` returns expected data and handles empty sources and dependency failures |
| Test Binder | Values from `Supplier` are sent to the right output binding and payloads are converted properly |
| Integration test | Scheduled poller, destination, and binder work against a real broker |
| Load test | Cadence and `max-messages-per-poll` do not overload the source or broker |

Do not use long `Thread.sleep` calls in unit tests just to wait for the poller to run. Test the `Supplier` directly in unit tests; reserve schedule and binding tests for integration tests with controlled wait bounds.

When verifying multiple pollers, confirm each bean has the right binding name and each binding has the right `fixed-delay` or `cron`. Observe startup logs, emission timestamps, and message counts at the destination. If two producers have different configured schedules yet run at the same effective rate, check whether the per-binding settings are placed correctly under `producer.poller` or are being overridden by shared configuration.

## 13. Common Configuration Errors

| Symptom | Cause | Resolution |
|---|---|---|
| Supplier still emits every second | Changed a property with the wrong prefix or wrong binding name | Check `spring.cloud.stream.bindings.<binding>.producer.poller` |
| All Suppliers changed cadence together | Set `spring.integration.poller` instead of per-binding configuration | Move properties under each output's `producer.poller` |
| Poller does not run | Bean not selected in function definition or not discovered | Check bean name and `spring.cloud.function.definition` |
| Poller runs but produces no messages | `Supplier` returns `null`, source has no data, or an error occurred | Inspect `get()`, logs, and data-source state |
| Cron schedule fires at the wrong time | Cron expression or time zone differs from expectations | Check Spring Cron syntax and environment timezone |
| Reactive Supplier called only once | `Flux` is treated as a continuous stream | Use an imperative `Supplier` or `PollableBean` for a finite stream requiring polling |
| Duplicate data emitted after restart | Source does not store checkpoints or sending is not idempotent | Use an outbox, delivery state, and deduplication keys |

Incorrect example: placing `poller` under `consumer`:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orderEvents-out-0:
          consumer:
            poller:
              fixed-delay: 5000
~~~

Output bindings must be configured under `producer`:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orderEvents-out-0:
          producer:
            poller:
              fixed-delay: 5000
~~~

When configuration appears to have no effect, check in order: bean name, binding name, function definition, the `producer.poller` level, and configuration sources that might override it. Do not change the destination or binder if the issue is only the poll schedule.

## 14. Configuration Workflow per Producer

When adding a new `Supplier`, follow these steps in order:

1. Identify the data source and required business emission frequency.
2. Register the `Supplier` bean with a clear name.
3. Determine the default output binding from the bean name.
4. Choose the destination and content type for the binding.
5. Set `fixed-delay` or `cron` in the binding's `producer.poller`.
6. Choose `initial-delay` and `max-messages-per-poll` based on data-source characteristics.
7. Test the `Supplier` directly and test output with the Test Binder.
8. Run integration tests with the target broker.
9. Monitor emission rate, latency, errors, and source data health.
10. Design checkpoints, an outbox, or idempotency if delivery guarantees are required.

Separating pollers per output binding lets each producer run on a schedule matched to its data and load. The `Supplier` focuses on creating data; the poller decides when to invoke it; the output binding and binder handle sending messages to the broker.

## Official References

- [Spring Cloud Stream - Producing and Consuming Messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html): `Supplier`, default poller, poller properties, and per-output-binding configuration.
- [Spring Cloud Function - Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html): functional beans, imperative/reactive `Supplier`, and function definitions.
- [Spring Boot - Integration Properties](https://docs.spring.io/spring-boot/appendix/application-properties/index.html): Spring Integration poller properties provided by Spring Boot.
