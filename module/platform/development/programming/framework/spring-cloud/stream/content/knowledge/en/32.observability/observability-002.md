# Distinguishing Connection Health from Business Processing Capability

In a Spring Cloud Stream application, the connection status to Kafka, RabbitMQ, or Pulsar only indicates that the application can communicate with the broker at the time of the check. It does not prove that messages are being consumed, that functions are completing their work, that data is being written to the target system, or that business outcomes are meeting deadlines.

A consumer may keep its broker connection in the UP state while being stuck in a database call. A producer may connect successfully while messages are continuously routed to the DLQ. Conversely, an application may receive no messages for several minutes because upstream is not emitting events; this is not necessarily a failure.

Therefore, at least four layers should be observed separately: process health, binder/broker connection health, message transport flow, and business processing outcomes. Only by combining these signals can you tell whether the service is actually getting its work done.

## 1. Four health layers to observe

| Layer | Question to answer | Example signals |
|---|---|---|
| Process | Is the application alive and able to accept work? | Liveness, readiness, thread pool, memory |
| Connection | Can the binder communicate with the broker? | Binder health indicator, connection, authentication, metadata request |
| Transport | Are messages being received, sent, and forwarded? | Consumer assignment, publish ack, consumer lag, queue depth, redelivery |
| Business | Are messages producing the right outcomes on time? | Success rate, processing latency, oldest backlog age, business failure, DLQ |

These layers are related but do not substitute for one another. The broker can be UP while business processing is DOWN; a function can process successfully while the output broker fails to receive it; or the broker can be temporarily DOWN while the application still holds completed business state for earlier messages.

~~~mermaid
flowchart TD
    A["Process<br/>Liveness / Readiness"] --> B["Binder and broker<br/>Connection, authentication"]
    B --> C["Message transport<br/>Consume / Publish / Lag"]
    C --> D["Business processing<br/>Validation / Database / Side effect"]
    D --> E["Output result<br/>ACK / Output / DLQ"]
    F["Metrics, logs, traces"] -. observes .-> A
    F -. observes .-> B
    F -. observes .-> C
    F -. observes .-> D
    F -. observes .-> E
~~~

When designing dashboards and alerts, ask questions per layer rather than using a single UP/DOWN status for everything.

## 2. Process health: liveness and readiness

Liveness answers whether the process is still running or has entered an unrecoverable state, such as a deadlock or loop that halts progress. Readiness indicates whether the instance is ready to serve according to the application's operational conditions.

Spring Boot Actuator provides the health endpoint and health groups for Kubernetes:

- Liveness: the process is alive; if it fails continuously, the platform may restart the container.
- Readiness: whether the instance should receive traffic or be considered ready during a rollout.
- Overall health: combines all configured HealthContributors.

For message-processing applications, you should not include every broker connection failure in liveness. An external broker interruption does not mean the Java process is broken. If liveness depends on the broker, Kubernetes may continuously restart instances while the broker is recovering, creating extra connections and unnecessary load.

Readiness can include broker connection conditions if the deployment workflow needs to wait for the binder to be ready before marking an instance healthy. However, HTTP service readiness does not automatically stop message consumers. A Kafka consumer group or Rabbit listener has its own lifecycle managed by the binder; understand the binder's behavior when readiness turns DOWN.

Example enabling probes and observability endpoints:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
  endpoint:
    health:
      probes:
        enabled: true
      show-details: when-authorized
  health:
    binders:
      enabled: true
~~~

To export Prometheus metrics, add the corresponding registry, such as micrometer-registry-prometheus, to the application dependencies. Only expose the endpoints you need and protect health/metrics details via authentication, internal networks, or platform policies.

## 3. Binder and broker connection health

Spring Cloud Stream provides a health indicator for binders. Overall health can show whether the binder can check the connection status to the middleware according to the binder implementation's mechanism. The management.health.binders.enabled property controls this health indicator; check the defaults and implementation against the Spring Cloud Stream version in your application's BOM.

A binder health indicator is useful for detecting:

- An unreachable broker or closed connection.
- Invalid credentials or authorization errors when establishing a connection.
- Inability to perform the required broker health check operation.
- One binder failing in a multi-binder application while another continues working.

However, the health indicator is not an end-to-end test. An UP status does not guarantee that a consumer group has been assigned partitions, that a queue has consumers, that a function is not stalled, or that output has been processed by the target system.

For example, RabbitMQ can accept a TCP connection and AMQP channel while a queue has zero consumers. A Kafka bootstrap broker can respond to metadata requests while the consumer group has no assigned partitions. A Pulsar broker can accept connections while subscription backlog keeps growing.

### 3.1. A successful connection does not mean messages are processed

| Scenario | Connection health | Processing capability |
|---|---|---|
| Broker reachable, consumer has no assigned partitions | May be UP | Not yet consuming messages |
| Rabbit connection open, queue has no consumers | May be UP | Messages accumulate in the queue |
| Producer connected to broker but publish rejected due to ACL/topic policy | May be UP | Output is not written as expected |
| Function receives message but database call times out | UP | Business processing fails |
| Function finishes but message is retried due to ack/commit error | UP | Possible duplicate processing |
| Broker temporarily interrupted while application serves independent requests | DOWN at connection layer | Other capabilities may still work |

Therefore, display binder status separately from consumer, producer, and business metrics. Do not interpret a single UP indicator on a dashboard as meaning the entire pipeline is healthy.

## 4. Message transport health

The transport layer answers whether messages are flowing through the system at the expected pace. At minimum, observe both input and output:

- Number of messages published.
- Number of messages consumed or dispatched.
- Number of messages acknowledged/committed.
- Number of redeliveries or retries.
- Consumer lag or queue backlog.
- Age of the oldest waiting message.
- Number of messages sent to the DLQ or parking-lot queue.

High throughput is not necessarily good: the system might be processing a large volume of failing messages and retrying them. Low throughput is not necessarily bad: upstream might have no new events. Compare inbound rate, outbound rate, backlog, and message age together.

### 4.1. Metrics by broker

| Broker | Transport metrics to monitor |
|---|---|
| Kafka | Consumer lag per group/partition, records consumed, fetch rate, rebalance, commit rate, producer send/error rate |
| RabbitMQ | Ready messages, unacked messages, consumer count, publish/ack/nack rate, redelivery, connection/channel, DLQ depth |
| Pulsar | Subscription backlog, unacked messages, redelivery, ack rate, publish/dispatch rate, consumer count, and topic backlog |

Exact metric names depend on the binder, client, and version. Do not assume all binders emit the same metric names or share the same semantics. Inspect the actual metrics list through Actuator/Micrometer, broker dashboards, and documentation for your deployed version.

### 4.2. Distinguishing lag from business errors

Kafka consumer lag is the difference between the latest record position and the offset processed/committed by the consumer group. Growing lag can result from a publish rate higher than the consumption rate, inactive consumers, prolonged rebalances, or slow handlers.

RabbitMQ queue depth is the number of ready or unacked messages depending on the metric. Ready messages growing while consumer count is 0 usually indicates the queue is not being consumed. High unacked counts may reflect consumers holding many deliveries or processing slowly.

Pulsar subscription backlog shows the number of pending messages per subscription. Continuously growing backlog should be examined alongside ack rate, redelivery, and consumer status.

Lag/backlog is a transport signal. It does not pinpoint the business cause. To learn why processing is slow, correlate it with processing duration, dependency errors, traces, and output status.

## 5. Business processing health

Business health focuses on the outcomes the service is responsible for producing. For example, with an order-processing consumer:

- How many orders were processed successfully?
- What is the failure rate due to validation, database, or payment service issues?
- How long does it take from event emission until the order is updated?
- How long has the oldest incomplete message been waiting?
- Have any messages been sent to the DLQ?
- Was an event ID processed repeatedly or did it produce duplicate side effects?

A recommended set of business metrics:

| Metric/SLI | Meaning |
|---|---|
| Business events received | Number of events that entered the handler |
| Business events succeeded | Number of events that completed the business flow |
| Business events failed | Number of failed processing attempts, categorized by cause |
| Processing duration | Execution time of the handler or use case |
| End-to-end latency | Time from event timestamp to completed outcome |
| Oldest pending age | Age of the oldest incomplete message or job |
| Retry count | Number of retry attempts |
| DLQ/parking-lot count | Number of events requiring intervention or investigation |
| Duplicate/idempotency hit | Number of times a previously processed event was detected |

Measure business duration from a meaningful boundary. A timer around a handler measures handler execution time; it does not necessarily include time the message spent in the broker, retry wait time, or asynchronous downstream completion time.

End-to-end latency should use the event timestamp or the timestamp recorded when the system received the event, compared against the business completion time. Account for clock skew and late-arriving events when computing it.

## 6. Instrumenting Spring Cloud Stream functions with metrics

The example below uses a Consumer to process side effects. The service only returns after the business transaction has committed successfully. The success metric therefore represents the use-case outcome, not merely that the function was invoked.

Data type:

~~~java
public record OrderAccepted(
    String eventId,
    String orderId,
    String customerId
) {}
~~~

Tracking latest progress:

~~~java
import java.time.Instant;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.stereotype.Component;

@Component
class ProcessingProgress {

    private final AtomicReference<Instant> lastReceived =
        new AtomicReference<>();

    private final AtomicReference<Instant> lastSucceeded =
        new AtomicReference<>();

    void received() {
        lastReceived.set(Instant.now());
    }

    void succeeded() {
        lastSucceeded.set(Instant.now());
    }

    Instant lastReceived() {
        return lastReceived.get();
    }

    Instant lastSucceeded() {
        return lastSucceeded.get();
    }
}
~~~

Measuring processing counts and duration:

~~~java
import java.util.function.Consumer;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderConsumerConfiguration {

    @Bean
    Consumer<OrderAccepted> processOrder(
            OrderService orderService,
            ProcessingProgress progress,
            MeterRegistry registry) {

        Counter succeeded = Counter.builder("orders.processing")
            .tag("outcome", "success")
            .register(registry);

        Counter failed = Counter.builder("orders.processing")
            .tag("outcome", "failure")
            .register(registry);

        Timer duration = Timer.builder("orders.processing.duration")
            .description("Order business processing duration")
            .register(registry);

        return event -> {
            progress.received();
            Timer.Sample sample = Timer.start(registry);
            try {
                orderService.processAndCommit(event);
                progress.succeeded();
                succeeded.increment();
            }
            catch (RuntimeException exception) {
                failed.increment();
                throw exception;
            }
            finally {
                sample.stop(duration);
            }
        };
    }
}
~~~

The processAndCommit method should represent the business completion boundary, such as updating the database inside a transaction and committing before returning. When an exception is rethrown, the binder can apply retries or error handling according to its configuration.

The metric above counts successful/failed handler invocations. If the binder retries a message three times, one logical event can record multiple failures before succeeding. Therefore, do not directly interpret handler invocation counts as unique business events. If you need to count the final outcome per event, record it by event ID at the final processing boundary or also aggregate messages routed to the DLQ.

Do not attach eventId, orderId, customerId, email, or payload values as metric tags. High-cardinality values increase memory usage and metric storage costs. Use structured logs and trace attributes to look up individual events.

## 7. Business health indicators must have clear semantics

You can create a custom HealthIndicator to represent processing progress. The following example marks the status DOWN when the handler recently received messages but recorded no successes within the allowed window:

~~~java
import java.time.Duration;
import java.time.Instant;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("businessProcessing")
class BusinessProcessingHealthIndicator implements HealthIndicator {

    private static final Duration STALE_AFTER = Duration.ofMinutes(5);

    private final ProcessingProgress progress;

    BusinessProcessingHealthIndicator(ProcessingProgress progress) {
        this.progress = progress;
    }

    @Override
    public Health health() {
        Instant received = progress.lastReceived();
        Instant succeeded = progress.lastSucceeded();
        Instant now = Instant.now();

        if (received == null) {
            return Health.unknown()
                .withDetail("state", "NO_MESSAGE_OBSERVED")
                .build();
        }

        boolean recentInput =
            Duration.between(received, now).compareTo(STALE_AFTER) <= 0;

        boolean successIsStale = succeeded == null
            || Duration.between(succeeded, now).compareTo(STALE_AFTER) > 0;

        if (recentInput && successIsStale) {
            return Health.down()
                .withDetail("state", "INPUT_WITHOUT_RECENT_SUCCESS")
                .withDetail("lastReceived", received)
                .withDetail("lastSucceeded", succeeded)
                .build();
        }

        return Health.up()
            .withDetail("lastReceived", received)
            .withDetail("lastSucceeded", succeeded)
            .build();
    }
}
~~~

This is a simple policy example, not a universal definition for all applications. In production, configure thresholds based on SLOs, message volume, normal processing time, and traffic patterns.

If there is no traffic, the indicator returns UNKNOWN instead of concluding DOWN merely because there is no recent success. If inputs keep arriving without successes, the indicator detects a stall. However, it only observes handlers that were actually invoked; messages sitting in the broker without being delivered to a handler must be detected via lag or queue backlog.

For batch workloads or very sparse traffic, avoid using a fixed five-minute threshold. Combine:

- Input rate or number of pending messages.
- Consumer lag/queue depth.
- Oldest message age.
- Most recent successful processing time when input is present.
- Expected processing schedule if it only runs in batches.

Do not put every business error into liveness. A malformed record or a failed transaction may turn business health DOWN while the process is still healthy and capable of processing other records.

## 8. Distinguishing handler success from output delivery success

With a Consumer, the service can update the database and return; in that case, handler success measures use-case completion within the service boundary. With a Function returning a message, the function finishes when it creates the output object, while the binder still has to publish that object to the destination broker.

Therefore, two signals should be separated:

1. Function transformation success: the input data has been transformed into output.
2. Output delivery success: the binder/client published it and received confirmation according to the broker's semantics.

If output goes through a second broker, the function returning does not prove the second broker received it or the downstream consumer processed it. Monitor producer errors/acks/returns and downstream consumer status.

In an application using both Kafka and RabbitMQ simultaneously, there is no automatic distributed transaction spanning both binders. One side can complete while the other fails. Use an outbox, idempotency, bounded retries, or compensating workflows according to your delivery requirements.

## 9. Observing backlog and message age

Backlog count tells you how much work is waiting. Backlog age tells you how long the oldest item has been waiting. The two metrics complement each other:

- A queue with 100,000 messages but high throughput and low message age may be keeping up with load.
- A queue with only 20 messages where the oldest has waited 45 minutes may represent a severe SLO violation.
- Continuously rising consumer lag indicates processing speed is not keeping up with publish rate.
- Zero lag accompanied by a growing DLQ indicates messages left the main flow while business processing still failed.

Monitor oldest pending age or end-to-end latency percentiles alongside backlog. With Kafka, per-partition lag helps detect a hot partition even when total lag looks fine. With RabbitMQ, separate ready and unacked counts. With Pulsar, monitor backlog and redeliveries per subscription.

Some useful dashboards:

| Dashboard | Key charts |
|---|---|
| Broker connectivity | Binder health, connection errors, authentication failures |
| Message transport | Input/output rate, lag/backlog, consumer count, redelivery |
| Business processing | Success/failure, processing duration, end-to-end latency |
| Error handling | Retry rate, DLQ ingress, parking-lot depth, exception category |
| Dependency health | Database latency, downstream API error rate, connection pool |

## 10. Classifying errors by where they occur

If you only have a single counter named errors, operators cannot tell whether to investigate the broker, serialization, or business logic. Classify errors by boundary:

| Error type | Examples | Signals to monitor |
|---|---|---|
| Connectivity | Timeout, connection refused, TLS/authentication | Binder health, connection error |
| Provisioning/permission | Missing topic/exchange, missing ACL | Provisioning error, producer error |
| Serialization | Unable to deserialize payload or incompatible schema | Deserialization error, invalid message |
| Delivery | Publish nack/return, consumer redelivery | Producer error, redelivery, unacked |
| Business validation | Missing field, invalid order state | Validation failure, DLQ reason |
| Dependency | Database/API timeout or unavailable | Dependency latency/error |
| Business rule | Insufficient credit limit, transaction declined | Business outcome by reason code |

Do not retry every error the same way. Connectivity timeouts may be transient; schema-invalid payloads usually need quarantine or DLQ; business rule rejections may be valid outcomes rather than system errors. Metrics and logs should preserve this classification.

## 11. Logging, correlation IDs, and distributed tracing

Metrics show trends and magnitude. Logs help investigate a specific execution. Traces show timing and relationships across steps in the pipeline.

Each event should have a stable identifier, such as eventId, along with a correlationId or trace context. Record these fields in structured logs to correlate:

- Consumer receiving the record.
- Function or service starting processing.
- Database or downstream API calls.
- Commit result.
- Producer sending output.
- Next consumer completing.

Do not log full sensitive payloads. Log only necessary metadata, event type, eventId, correlationId, destination, partition/offset or queue, outcome, and normalized error codes.

Distributed tracing can create spans for receiving a message, running the function, and making downstream calls. When trace context is propagated via message headers, services can link traces across brokers. Configure propagation compatible with your Micrometer Tracing/OpenTelemetry version and the binder in use.

During retries or redeliveries, distinguish the same logical event from each attempt. You can keep eventId stable and create separate span/attempt attributes for each delivery. This makes it possible to see how many times an event was attempted without creating high-cardinality metric tags.

## 12. Alerting on business symptoms, not only broker state

A good alert is tied to concrete actions. For example:

| Observed condition | Interpretation | Investigation action |
|---|---|---|
| Binder DOWN and publish/consume failing | Possible connection or authentication loss | Check broker, DNS, network, TLS, credentials, and ACLs |
| Binder UP but consumer lag rising continuously | Consumers not keeping up or not processing | Check assignment, concurrency, handler latency, and dependencies |
| High input rate, low success rate, growing DLQ | Pipeline receiving messages but failing business logic | Classify exceptions, schemas, database, and validation rules |
| Ready queue growing, consumer count is 0 | Queue has no active consumers | Check listener lifecycle, bindings, and deployment |
| Unacked rising and processing duration high | Consumers holding deliveries too long | Check thread pools, downstream timeouts, and prefetch |
| Low lag but high end-to-end latency | Messages not backlogged but each takes long to process | Check dependency wait times and synchronous steps |
| No input and no backlog | May be normal idle state | Cross-check upstream schedule and traffic before alerting |
| Broker UP, recent successes, but one partition has high lag | Possible hot partition or skewed key distribution | Check per-partition lag and key skew |

Set alerts based on sustained duration and impact severity. A brief few-second flicker in broker health does not necessarily require paging. Conversely, oldest pending age breaching the SLO or a steadily rising failure rate demands attention even while the broker remains UP.

Illustrative PromQL expression:

~~~promql
sum(rate(orders_processing_total{outcome="failure"}[5m]))
/
clamp_min(sum(rate(orders_processing_total[5m])), 1)
~~~

This expression assumes the registry exports a Micrometer metric named orders_processing_total with an outcome label. Final metric names may be normalized differently depending on the registry. Verify the actual metrics before using alert rules.

## 13. Canary events and end-to-end checks

Connection health indicators and internal metrics do not prove the entire processing route is working. You can add a periodic canary event:

1. A probe publisher sends a test event along a dedicated route.
2. Consumers execute steps matching the pipeline under observation.
3. A final confirmation point records the eventId and completion time.
4. Monitoring measures the elapsed time from emission to confirmation.

Canaries should use a dedicated event type or tenant so they do not trigger real business side effects. If they must traverse the same production topic, handlers should recognize the canary and handle it idempotently while avoiding creating real orders, payments, or notifications.

Canaries measure end-to-end latency and catch failures in segments that per-component health checks miss. They should complement metrics, not replace backlog and business outcome checks.

## 14. Example scenario: broker UP but orders stalled

Suppose a dashboard shows the following signals:

| Signal | Value |
|---|---:|
| Kafka binder health | UP |
| Input rate | 120 events/s |
| Consumer lag | Rising from 500 to 40,000 |
| Processing success | Dropping to 5 events/s |
| Processing duration p95 | 8 seconds |
| Database timeout | Spiking |
| DLQ ingress | Rising |

The right conclusion is that the broker connection is still working, but the business pipeline cannot keep up with input. Investigation should focus on the database pool, timeouts, concurrency, and retry policy. Restarting the consumer is unlikely to fix the root cause if the database remains overloaded.

Another scenario:

| Signal | Value |
|---|---:|
| Rabbit binder health | UP |
| Ready queue | 15,000 |
| Consumer count | 0 |
| Business success | 0 |
| DLQ ingress | 0 |

The broker connection may be open, yet the queue has no consumers. Check binding names, function definitions, listener lifecycle, groups, and consumer startup logs.

Finally, if the broker is UP, input rate is 0, ready queue is 0, lag is 0, and no event emission is scheduled during that window, the service may simply be normally idle. Do not alert solely because there are no recent successes when there is no work to process.

## 15. Designing SLIs and SLOs for a pipeline

SLIs should measure the experience or outcomes the system delivers. An event pipeline might choose:

- Processing success ratio: proportion of valid events completing business processing.
- End-to-end latency: time from event creation to completed outcome.
- Oldest pending age: age of unprocessed work.
- DLQ rate: proportion of events diverted from the main flow.
- Data freshness: how current downstream state is compared to the source.

Illustrative SLO examples:

| SLI | Example target | Evaluation window |
|---|---:|---|
| Valid events completing successfully | 99.9% | 30 days |
| End-to-end latency p95 | Under 30 seconds | 7 days |
| Oldest pending age | Under 2 minutes | Continuous |
| Events routed to DLQ due to technical errors | Under 0.1% | 7 days |

These numbers are only examples. Real targets must be based on business requirements, load, dependencies, and resilience. Do not base SLOs solely on broker availability; high broker uptime does not guarantee order status is updated on time.

When computing the success ratio, decide whether the unit is a delivery attempt or a unique logical event. Retries can generate multiple handler invocations for one event; if the numerator and denominator use different units, the ratio will be misleading. You can use eventId to deduplicate business outcomes where completion state is stored.

## 16. Observability implementation checklist

- [ ] Enable Actuator health and appropriate probes.
- [ ] Observe binder health separately for each broker/binder.
- [ ] Do not put broker availability into liveness if doing so could cause restart loops.
- [ ] Monitor consumer count, assignment, lag, or queue/subscription backlog.
- [ ] Monitor input rate and output rate.
- [ ] Measure processing success, failure, and duration at business boundaries.
- [ ] Monitor oldest pending age and end-to-end latency.
- [ ] Monitor retries, redeliveries, DLQ, and parking-lot queues.
- [ ] Categorize errors into connectivity, delivery, serialization, dependency, and business rule errors.
- [ ] Use correlation IDs, event IDs, and trace context in logs/tracing.
- [ ] Avoid high-cardinality metric tags.
- [ ] Configure alerts that distinguish normal idle periods from stalled backlogs.
- [ ] Add canary events if full-route verification is needed.
- [ ] Define SLIs/SLOs around business outcomes and processing deadlines.
- [ ] Test dashboards/alerts by simulating broker downtime, stopped consumers, slow dependencies, and malformed messages.

## Official References

- [Spring Cloud Stream - Health Indicator](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/health-indicator.html): binder health indicator and status.
- [Spring Boot Actuator - Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): health, metrics, and how to expose endpoints.
- [Spring Boot Actuator - Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes): liveness and readiness for Kubernetes.
- [Micrometer Documentation](https://docs.micrometer.io/micrometer/reference/): metrics, Timer, Counter, registries, and application instrumentation guidelines.
- [Apache Kafka Monitoring](https://kafka.apache.org/documentation/#monitoring): consumer lag, producer/consumer metrics, and broker monitoring.
- [RabbitMQ Monitoring](https://www.rabbitmq.com/docs/monitoring): queue, connection, consumer, and broker metrics.
- [Apache Pulsar Monitoring](https://pulsar.apache.org/docs/next/administration-metrics/): broker, topic, subscription, and backlog metrics.
