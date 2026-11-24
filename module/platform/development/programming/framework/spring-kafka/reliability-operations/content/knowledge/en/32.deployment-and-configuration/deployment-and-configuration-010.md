# Configuring Metrics and Observation in Spring Kafka

## 1. What Problems Do Metrics and Observation Solve?

In a Kafka system, a service can stay running with zero exceptions in logs while **consumer lag** climbs steadily, producers send slowly, or listeners keep repeating the same message via retries. Looking solely at `"message received"` logs or an HTTP health status of `UP` makes it hard to identify the root cause and blast radius.

Within **Spring Kafka Reliability Operations**, configuring metrics and observation helps answer core operational questions:

- Are producers successfully delivering records to brokers? Are acknowledgment latencies or error rates rising?
- Are consumers reading data, receiving partition assignments, and committing offsets properly?
- Are Kafka brokers, networks, or clients creating a bottleneck?
- How long does a listener take to process a record? How many records fail, retry, or move to a dead-letter topic?
- Which step along HTTP/API → Kafka → database → downstream Kafka consumes the most time?
- When the application redeploys, do consumers experience long rebalances, abnormal lag spikes, or stalled processing?
- When a metric degrades, how do you jump from a dashboard to the exact trace and log without creating high-cardinality labels?

A practical observability stack combines **metrics, traces, and logs**, each serving a distinct purpose:

| Signal | Examples | Purpose |
|---|---|---|
| **Metrics** | Record rates, consumer lag, error counts, processing latency | Trends, alerting, capacity planning |
| **Traces** | Spans across Kafka publish → Kafka consume → database call | Following one execution flow across services |
| **Logs** | Event ID, exception type, topic/partition/offset | Investigating specific incidents |
| **Audit/business outcomes** | Payment committed, event written to outbox, duplicate counts | Proving actual business outcomes |

**Observation does not equal business success.** A completed span does not prove the database committed, the Kafka offset was persisted, or an event executed strictly once. Confirming those facts requires inspecting transaction state, offsets, outbox/inbox tables, and business counters.

### Technical Scope

Examples primarily target **Spring Boot 3.x, Spring Kafka 3.x, Java 17+, and Micrometer 1.x**. Spring Boot and Spring Kafka evolve continuously; verify exact property, metric, and tag names against your **actual version**. Examples use `String` producers and consumers to focus on instrumentation rather than serialization.

## 2. Three Measurement Layers to Separate

Three distinct sources are often lumped together as "Kafka metrics":

| Layer | Where Data Originates | Examples | Strengths and Limits |
|---|---|---|---|
| **Kafka client metrics** | `KafkaProducer` and `KafkaConsumer` | Bytes sent, request latency, records consumed rate, fetch/poll, retry rate | Shows client/network health; cannot tell whether business transactions succeeded |
| **Spring Kafka listener/template observations** | `KafkaTemplate` and listener containers | Template send duration, listener callback duration, trace context | Connects Kafka with app processing; does not replace broker-level lag |
| **Kafka cluster/group metrics** | Brokers, exporters, Kafka admin/consumer group tooling | Consumer-group lag, under-replicated partitions, request queues, ISR, broker errors | Shows accurate cluster health and backlog; does not show how individual items fared in business logic |

Alongside these, define **application business metrics**, for example:

```text
payment_event_received_total
payment_event_processed_total
payment_event_duplicate_total
payment_event_failed_total
payment_outbox_pending
payment_dlq_published_total
```

These names are **illustrative application metrics**, not built-in metrics emitted by Spring Kafka.

Diagram:

```text
        Producer Service                     Consumer Service
  +-------------------------+          +------------------------------+
  | business method         |          | @KafkaListener               |
  |      |                  |          |       |                      |
  |      v                  |          |       v                      |
  | KafkaTemplate.send()    |          | validation / DB / outbox     |
  |      |                  |          |       |                      |
  |  Producer client        |          |   Consumer client            |
  +------+------------------+          +-------+----------------------+
         |                                     ^
         v                                     |
  +------+-------------------------------------+---------+
  |                       Kafka cluster                 |
  | Broker metrics / partitions / offsets / ISR / quota |
  +-----------------------------------------------------+

      Micrometer meters + observations + trace context
                         |
                         v
               Actuator / Prometheus
                         |
                    Grafana/Alerts
                         |
                   OTLP tracing
                         |
                 Jaeger/Tempo/other
```

**Important:** When consumer lag rises, the cause may lie in consumer processing, partition count, downstream databases, brokers/networks, or a sudden producer spike. No single metric pinpoints the root cause alone.

## 3. How Do Micrometer Metrics Differ from Micrometer Observation?

**Micrometer Metrics** provides APIs such as `Counter`, `Timer`, `Gauge`, and registries exporting numbers to Prometheus, Datadog, OTLP, or other backends.

**Micrometer Observation** provides a unified abstraction for **an operation with a start and end**, carrying context, key-values, and handlers. Depending on configured handlers/bridges, one observation can produce:

- A Timer/metric measuring duration.
- A Span for distributed tracing.
- Trace/span IDs correlating logs.
- Context propagation across supported execution steps.

Keep several distinctions in mind:

1. **Having a Micrometer registry** does not mean distributed tracing works automatically.
2. **Enabling Observation on `KafkaTemplate`** does not enrich Kafka broker metrics if client/broker instrumentation is missing.
3. **Enabling a tracing exporter** does not automatically measure consumer-group lag.
4. An observation can be created yet never reach the backend if sampling, handlers, or exporters are misconfigured.
5. Metrics are aggregated measurements, whereas traces capture sampled or policy-selected individual requests/events.

### 3.1. Which Metric Type Should You Use?

| Type | Data | Best Fit |
|---|---|---|
| `Counter` | Monotonically increasing total | Retry counts, DLT publishes, business failures |
| `Timer` | Invocation count and execution duration | Listener/processing duration, publish latency |
| `Gauge` | Current instantaneous value | Queue size, pending outbox rows, consumer lag from measured source |
| `DistributionSummary` | Distribution of sizes/quantities | Payload bytes, batch record counts |
| `LongTaskTimer` | In-flight long-running operation | Very slow tasks needing observation before completion |

Using `Counter` for error counts and `Timer` for durations is far easier to analyze than maintaining a fluctuating `Gauge` just for error totals. Conversely, backlogs or pending outbox counts fit gauges or authoritative external metrics.

## 4. Required Dependencies in Spring Boot

A Spring Kafka app exporting metrics and traces typically needs the following dependencies.

### 4.1. Gradle Example

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.kafka:spring-kafka'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    // Registry for /actuator/prometheus endpoint.
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'

    // Choose a tracing bridge matching your observability stack.
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    runtimeOnly 'io.opentelemetry:opentelemetry-exporter-otlp'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
}
```

Dependency versions are normally managed by **Spring Boot dependency management/BOM**; avoid forcing incompatible Micrometer/OTel versions just to copy a snippet.

If your project only needs metrics without distributed tracing yet, omit the tracing bridge and exporter. When adding tracing, pick the bridge matching your backend (such as OpenTelemetry). Never install multiple competing bridges simultaneously unless required.

**Note:** Kafka client metrics can be auto-configured by Spring Boot Actuator/Micrometer when compatible beans and dependencies are present. However, custom beans, multiple client factories, or framework version changes can alter automatic registration. Always verify active meters after producers/consumers initialize.

### 4.2. Maven Example (Core Dependencies)

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.kafka</groupId>
        <artifactId>spring-kafka</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>

    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
        <scope>runtime</scope>
    </dependency>

    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-tracing-bridge-otel</artifactId>
    </dependency>

    <dependency>
        <groupId>io.opentelemetry</groupId>
        <artifactId>opentelemetry-exporter-otlp</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

This skeleton assumes a Spring Boot parent/BOM; add HTTP, serialization, JDBC, and domain dependencies per your environment.

## 5. Enabling Metrics Endpoints and Tracing Exporters

Example configuration for an observed environment:

```yaml
spring:
  application:
    name: payment-worker

  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}

    consumer:
      group-id: payment-worker-v1
      enable-auto-commit: false
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer

    producer:
      acks: all
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer

    listener:
      ack-mode: record
      concurrency: 3
      observation-enabled: true

    template:
      observation-enabled: true

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus

  metrics:
    tags:
      application: ${spring.application.name}

  tracing:
    sampling:
      probability: 0.10

  otlp:
    tracing:
      endpoint: ${OTEL_TRACES_ENDPOINT:http://localhost:4318/v1/traces}
```

Explanation:

- `management.endpoints.web.exposure.include` exposes endpoints needed for monitoring. Exposing an endpoint does not secure it; enforce authentication and network policies.
- `management.metrics.tags.application` attaches a stable application tag to metrics where configured.
- `spring.kafka.listener.observation-enabled=true` tells Spring Boot to enable observation on auto-configured listener containers.
- `spring.kafka.template.observation-enabled=true` enables observation on the Boot-configured template.
- `management.tracing.sampling.probability=0.10` samples roughly 10% of traces via the active sampler—not 10% of Kafka records processed.
- `management.otlp.tracing.endpoint` illustrates an OTLP/HTTP exporter on Spring Boot stacks supporting that property. With a Collector, match endpoint and protocol to your actual deployment.

**Very important note:** Both `observation-enabled` properties apply through Spring Boot's auto-configuration path. If your app declares custom `KafkaTemplate` or `ConcurrentKafkaListenerContainerFactory` beans without letting Boot configure them, enable observation and attach the registry on **those custom beans directly**. YAML alone never guarantees custom beans are instrumented.

### 5.1. Checking Actuator After Startup

Examples:

```text
GET /actuator/health
GET /actuator/metrics
GET /actuator/metrics/spring.kafka.listener
GET /actuator/prometheus
```

`/actuator/metrics` lists meters registered in the process. Until a listener processes at least one record, certain meters may not appear yet. If a consumer bean exists without connecting/polling, Kafka client metrics may also be absent.

**Never build dashboards purely from guessed Prometheus metric names.** Names shown in `/actuator/metrics` differ from Prometheus series names after registry conversion: dots become underscores, and Timers gain `_seconds_count`, `_seconds_sum`, and optional bucket series.

## 6. Enabling Observation on `KafkaTemplate`

In Spring Kafka 3.x, `KafkaTemplate` supports observation for send operations. When constructing a template manually, enable it directly:

```java
import org.apache.kafka.common.serialization.StringSerializer;

import io.micrometer.observation.ObservationRegistry;

import java.util.HashMap;
import java.util.Map;

import org.apache.kafka.clients.producer.ProducerConfig;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;

@Configuration
class ObservedProducerConfiguration {

    @Bean
    ProducerFactory<String, String> paymentProducerFactory() {
        Map<String, Object> config = new HashMap<>();

        config.put(
                ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
                "localhost:9092");
        config.put(
                ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
                StringSerializer.class);
        config.put(
                ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
                StringSerializer.class);
        config.put(ProducerConfig.ACKS_CONFIG, "all");
        config.put(
                ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);

        return new DefaultKafkaProducerFactory<>(config);
    }

    @Bean
    KafkaTemplate<String, String> paymentKafkaTemplate(
            ProducerFactory<String, String> paymentProducerFactory,
            ObservationRegistry observationRegistry) {

        KafkaTemplate<String, String> template =
                new KafkaTemplate<>(paymentProducerFactory);

        template.setObservationRegistry(observationRegistry);
        template.setObservationEnabled(true);

        return template;
    }
}
```

**Illustrative code:** `localhost:9092` is for local setups. In production, read bootstrap servers from validated config. Declaring a custom `KafkaTemplate` may cause Spring Boot's default template bean to back off. Verify which bean is injected into your publisher.

Creating observations requires a **registry with matching handlers**. An `ObservationRegistry` without registered metrics/tracing handlers will not export data to backends. Spring Boot Actuator/tracing auto-configuration usually wires handlers when dependencies match.

### 6.1. Observing Asynchronous Send Outcomes

`KafkaTemplate.send(...)` returns a `CompletableFuture` in Spring Kafka 3.x:

```java
import java.util.concurrent.CompletableFuture;

import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;

public final class PaymentPublisher {

    private final KafkaTemplate<String, String> template;

    public PaymentPublisher(
            KafkaTemplate<String, String> template) {
        this.template = template;
    }

    public CompletableFuture<SendResult<String, String>> send(
            String paymentId,
            String eventJson) {

        return template.send(
                "payments-out.v1",
                paymentId,
                eventJson
        );
    }
}
```

Template observation measures the publish operation within Spring Kafka instrumentation. However, **method return** is not when the broker confirms durability. Business logic must track future completion and failure/retry/outbox policies.

Callback example:

```java
publisher.send(paymentId, eventJson)
        .whenComplete((result, error) -> {
            if (error != null) {
                // Report error or mark outbox for retry.
                reportSendFailure(paymentId, error);
            } else {
                // Broker acknowledged per the configured acks policy.
                recordAcknowledged(result.getRecordMetadata());
            }
        });
```

`reportSendFailure(...)` and `recordAcknowledged(...)` are illustrative domain functions, not built-in Spring Kafka APIs.

**Never conclude exactly-once simply because template metrics show success.** Producer idempotence, application retries, and consumer processing are distinct layers.

## 7. Enabling Observation on the Listener Container

With `@KafkaListener`, polling and callback invocation are managed by the listener container. When using a custom `ConcurrentKafkaListenerContainerFactory`, enable observation on `ContainerProperties`:

```java
import io.micrometer.observation.ObservationRegistry;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.ContainerProperties;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

@Configuration
class ObservedConsumerConfiguration {

    @Bean("observedListenerFactory")
    ConcurrentKafkaListenerContainerFactory<String, String>
    observedListenerFactory(
            ConsumerFactory<String, String> consumerFactory,
            ObservationRegistry observationRegistry) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<
                        String, String>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);

        factory.getContainerProperties().setAckMode(
                ContainerProperties.AckMode.RECORD);

        factory.getContainerProperties()
                .setObservationRegistry(observationRegistry);

        factory.getContainerProperties()
                .setObservationEnabled(true);

        factory.setCommonErrorHandler(
                new DefaultErrorHandler(
                        new FixedBackOff(1_000L, 2L)
                )
        );

        return factory;
    }
}
```

`FixedBackOff(1_000L, 2L)` is only a sample policy; it does not create a DLT or guarantee final errors are resolved by business rules. When a final error is recovered by the handler, monitor the **recovery outcome**, not just listener exceptions.

### 7.1. Binding the Right Container Factory

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public final class PaymentEventListener {

    private final PaymentService service;

    public PaymentEventListener(PaymentService service) {
        this.service = service;
    }

    @KafkaListener(
            topics = "payments-in.v1",
            groupId = "payment-worker-v1",
            containerFactory = "observedListenerFactory")
    public void handle(String payload) {
        service.process(payload);
    }
}
```

`PaymentService` is an application-defined business service.

If the application has multiple listener factories and omits `containerFactory`, a listener may bind to an unobserved default factory or point to the wrong cluster. In multi-cluster deployments, name factories clearly and test bean wiring.

### 7.2. What Does the Listener Timer Measure?

Listener observation wraps callback execution under Spring Kafka semantics—not the full time an event sat in Kafka **before** the consumer started processing it. Thus:

```text
Producer publishes at 10:00:00
Message waits in topic 2 minutes
Consumer starts callback at 10:02:00
Listener processing takes 100 ms

Listener duration ≈ 100 ms
End-to-end event age ≈ 2 minutes + 100 ms + other delays
```

To measure how long events waited, combine Kafka timestamps, consumer lag/lag-time, and contractually consistent clocks. Never treat listener duration alone as end-to-end event latency.

### 7.3. Record vs. Batch Listener Observation Differences

For a **record** listener, observations wrap each callback invocation. For a **batch** listener, one callback processes many records, and framework observation/tagging behavior can differ. Never treat batch-listener observation counts as total Kafka records processed.

When exact record counts are needed, use Kafka client records-consumed metrics, a clear business counter, or per-record instrumentation inside the loop.

## 8. Traditional Metrics and Observation May Share Names

Before Observation integration, Spring Kafka already instrumented listeners and templates using Micrometer Timers. Once observation is enabled, the framework may switch to the Observation path instead of legacy Timers in applicable paths.

Upgrading can therefore cause:

- Similar meter names with **different tag sets**, breaking existing dashboards.
- Double-counting the same operation if an app adds manual Timers alongside enabled observations without checking.
- Observation enabled without creating spans if no tracing bridge/handler exists.
- Disappearing metrics after switching to a custom factory/template unless instrumentation is enabled on that custom bean.
- Counting one event multiple times in business counters if instrumentation is inconsistent.

**Never delete legacy metrics from dashboards immediately when rolling out new configs.** Run side-by-side comparisons or verify target series and alerts before retiring old queries, especially for critical SLAs and error rates.

## 9. Kafka Client Metrics: Producer and Consumer

Kafka clients emit internal statistics on requests, I/O, buffers, fetches, polls, records, and more. Spring Boot/Micrometer can bind them to the registry when factories/clients are created and listener instrumentation is wired properly.

Key groups to observe:

| Side | Kafka Client Metric Group | Signal |
|---|---|---|
| Producer | Record send rate / error rate / retry rate | Send throughput and failure status |
| Producer | Request latency, response rate | Network/broker latency |
| Producer | Buffer available/exhausted, batch size, compression | Memory pressure and batching |
| Producer | Record size max/avg | Abnormal payload growth |
| Consumer | Records consumed rate | Consumption volume |
| Consumer | Fetch rate/latency | Pulling batches from brokers |
| Consumer | Records lag max | Client-observed offset lag |
| Consumer | Poll idle ratio, poll rate | Consumer poll behavior |
| Consumer | Commit latency/rate | Offset commit health |
| Consumer | Assigned partitions/rebalances | Consumer group stability |

**Metric names after Micrometer/Prometheus translation do not necessarily match raw Kafka client JMX names.** Kafka client metric groups/names often become `kafka.producer.*` or `kafka.consumer.*` meters, then underscored Prometheus series. Inspect the live `/actuator/prometheus` endpoint before hardcoding PromQL expressions.

### 9.1. When Auto-Config Shows No Client Metrics

Common reasons:

1. No Kafka producer or consumer has actually been instantiated yet.
2. Using custom `ProducerFactory`/`ConsumerFactory` beans without registering Micrometer listeners.
3. Missing `MeterRegistry` or Actuator configuration.
4. Measuring only listeners while assuming broker metrics are also collected by Spring Boot.
5. Kafka clients closed, causing gauges/metrics to disappear at scrape time.
6. Tag/metric naming changed after an upgrade.

Spring Kafka provides factory listeners for Micrometer integration—typically `MicrometerProducerListener` and `MicrometerConsumerListener`. On custom factories, register them as supported by your version:

```java
import io.micrometer.core.instrument.MeterRegistry;

import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.MicrometerConsumerListener;
import org.springframework.kafka.core.MicrometerProducerListener;

// Illustrative after creating factories with proper configs.
producerFactory.addListener(
        new MicrometerProducerListener<>(meterRegistry));

consumerFactory.addListener(
        new MicrometerConsumerListener<>(meterRegistry));
```

This is **illustrative wiring**: `producerFactory` and `consumerFactory` here represent `DefaultKafkaProducerFactory`/`DefaultKafkaConsumerFactory` instances built from your config maps, not pre-existing globals. Check whether Boot already registered instrumentation before adding listeners manually to avoid duplicate meters.

### 9.2. Kafka Client Metrics Do Not Equal Business Outcomes

A high producer `record-send-rate` only proves the client sends records well, not that consumers processed them. A high consumer `records-consumed-rate` does not prove database commits or outbox publishes succeeded.

Example:

```text
Kafka producer:  1,000 messages/s
Kafka consumer:  1,000 records/s
Business commit:   650 events/s
DLT/retry/duplicate: the remainder
```

Looking solely at network rates makes the system appear healthy. Business metrics are essential to see true event outcomes.

## 10. Consumer Lag Must Be Measured from the Right Source

**Consumer lag** measures how many records remain for a consumer group to process in a topic/partition.

In simplified form:

```text
lag ≈ log-end-offset - committed-offset
```

In Kafka, committed offset normally represents the **next position to read** (next offset), not necessarily the last processed offset. For groups lacking committed offsets, lag calculation depends on `auto.offset.reset` and retention rules.

Example:

```text
Partition 0:
  End offset (next) = 15,000
  Group committed offset = 14,200

  Lag = 15,000 - 14,200 = 800 records
```

This simplified formula omits details of isolation levels, transaction LSOs, compaction, retention, and how specific exporters define end offsets. Pick an exporter and understand its exact semantics.

### 10.1. Client Lag and Group Lag Are Not Identical

- A `KafkaConsumer` reports **`records-lag-max`** only for partitions **assigned** to that client.
- A consumer-group lag monitor reads broker offsets and committed offsets across the **entire group**, including partitions no live client currently holds.
- If a consumer dies and stops emitting client metrics, dashboards relying solely on client metrics **go dark right when an incident strikes**.
- When a consumer group does not exist yet or has no committed offsets, tools display lag differently.

Therefore, for service-level SLOs, combine:

1. Consumer client metrics.
2. Cluster-level group lag via an exporter/monitoring platform (e.g., broker/Admin-API exporter).
3. Listener liveness and partition assignments.
4. Business processing throughput and outbox/DB state.

### 10.2. High Lag Is Not Always a Bug

A scheduled downstream job may intentionally let Kafka accumulate backlog and process in batches. For a real-time system, 10,000 lagging records may already breach SLAs.

Document **SLOs by record count and/or event age**, for instance:

```text
payment-commands consumer group:
- Consumer lag < 5,000 records under normal conditions.
- Event processing age p95 < 30 seconds.
- If lag rises continuously for more than 15 minutes: alert.
```

Numbers are illustrative. 5,000 lagging records at 100,000/s is tens of milliseconds of work; at 10/s it is many minutes. **Evaluate record lag and event age together.**

## 11. Kafka Broker Metrics Do Not Come from Spring Actuator Automatically

Spring Kafka runs **inside the application**, whereas Kafka brokers are a separate system. Enabling `spring-boot-starter-actuator` alone does not collect:

- Under-replicated partitions.
- Offline partitions.
- Broker request queues.
- ISR shrink/expand events.
- Controller health.
- Disk utilization and disk latency.
- Network processor idle ratios.
- Broker-side quotas/throttling.

These come from broker JMX/exporters, managed Kafka platform telemetry, or dedicated cluster monitoring.

Illustrative deployment architecture:

```text
Spring Boot application             Kafka brokers
        |                                 |
 /actuator/prometheus                 JMX / exporter
        |                                 |
        +------------+--------------------+
                     |
                 Prometheus
                     |
                   Grafana
                     |
                 Alertmanager

Traces from app -> OpenTelemetry Collector -> Tempo/Jaeger
Logs from app   -> Log pipeline            -> Search UI
```

If producer client latency rises alongside broker `under-replicated-partitions`, investigate the cluster. If brokers are healthy while listener duration spikes on DB calls, investigate downstream.

## 12. Propagating Trace Context Through Kafka Headers

Distributed tracing follows a flow across services:

```text
HTTP POST /payments
    |
    v
payment-api
    |  Span: HTTP request
    |
    +--> KafkaTemplate.send("payments-in.v1")
                   | Span: Kafka produce
                   |
                Kafka topic
                   |
                   v
             payment-worker
                   | Span: Kafka listener
                   |
                   +--> JDBC transaction
                   |
                   +--> KafkaTemplate.send("payments-out.v1")
                                  |
                                  v
                             next-service
```

With Micrometer Observation, a tracing bridge, and Spring Kafka instrumentation, trace context is **injected** into Kafka record headers on send and **extracted** at the receiving listener.

### 12.1. Conditions for End-to-End Trace Linking

- Producers and consumers agree on trace propagation header formats, typically W3C Trace Context.
- Both services have properly configured `ObservationRegistry` and tracing handlers.
- Middleware, proxies, or transformers do not strip record headers.
- Instrumentation is enabled on the actual template and listener containers in use.
- Context is not lost when offloading work onto executors or background threads without propagation.
- Sampling policies do not drop the traces you expect to inspect.

If two services use incompatible propagation formats or one enables metrics only, traces break even while Kafka delivers messages normally.

### 12.2. Never Blindly Trust External Headers

Headers like `traceparent`, `baggage`, or custom correlation IDs may be set by external producers. Treat them as **untrusted input**, not proof of authorization or identity.

Never place tokens, emails, account numbers, or sensitive payloads in baggage just to "carry them along the trace"; baggage propagates across services and telemetry backends.

A span or correlation ID never replaces `eventId` as a business idempotency key.

### 12.3. When Processing Threads Change

If a listener hands off to a `CompletableFuture` or executor, the active span/context can be lost without explicit context propagation. Spring Boot offers Micrometer Context Propagation support depending on your stack, though you must test actual executors and async boundaries.

Never store a trace ID from a listener thread in a static field for another thread; that is neither thread-safe nor trace-accurate.

## 13. Custom Observations for Business Logic

Not all listener latency comes from Kafka. You may want a nested observation around payment validation or database updates.

Example:

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

public final class PaymentProcessingService {

    private final ObservationRegistry registry;
    private final PaymentRepository repository;

    public PaymentProcessingService(
            ObservationRegistry registry,
            PaymentRepository repository) {

        this.registry = registry;
        this.repository = repository;
    }

    public void process(PaymentEvent event) {
        Observation observation = Observation.createNotStarted(
                "payment.process",
                registry
        );

        observation.lowCardinalityKeyValue(
                "operation", "apply-payment");

        observation.lowCardinalityKeyValue(
                "source", event.sourceSystem());

        observation.observe(() ->
                repository.applyIdempotently(event)
        );
    }
}
```

`PaymentEvent` and `PaymentRepository` are hypothetical domain types. `applyIdempotently(...)` must enforce proper transactions and business keys.

**Note on the `source` tag:** the example assumes `event.sourceSystem()` comes from a **small, bounded allowlist**. If it is a dynamic partner ID or free-form payload string, do not use it as a low-cardinality key. Map it to bounded source groups or place it in high-cardinality trace context/logs per policy.

### 13.1. Low Cardinality vs. High Cardinality

A core Observation distinction:

- **Low-cardinality key-values** fit metric tags: `operation=apply-payment`, `outcome=success/failed`, `source=partner-a/partner-b`.
- **High-cardinality key-values** belong only on trace/span attributes when needed, subject to security/retention limits: `eventId`, `paymentId`, `orderId`. Never make them metric labels.
- **Baggage** propagates across services; never treat it as secure storage for sensitive data.

Avoid:

```java
// Avoid: every event creates a separate metric time series.
observation.lowCardinalityKeyValue(
        "eventId", event.eventId());
```

Even if the backend accepts it initially, hundreds of thousands of event IDs explode cardinality linearly with message volume and overload monitoring.

### 13.2. Observations Do Not Roll Back Side Effects

`observation.observe(...)` records exceptions and closes spans when code throws, yet **does not open a business transaction**. For proper DB behavior, apply a transaction manager or `@Transactional` at the exact business boundary.

For producers/outboxes, an observation does not prove the broker received an event if code only queues an async send and returns.

## 14. Custom Business Counters: Counting One Thing Accurately

Built-in metrics do not always answer business questions. Define custom counters as needed:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

public final class PaymentOutcomeMetrics {

    private final Counter accepted;
    private final Counter duplicate;
    private final Counter rejected;

    public PaymentOutcomeMetrics(MeterRegistry registry) {
        accepted = Counter.builder("payment.event.outcome")
                .tag("outcome", "accepted")
                .register(registry);

        duplicate = Counter.builder("payment.event.outcome")
                .tag("outcome", "duplicate")
                .register(registry);

        rejected = Counter.builder("payment.event.outcome")
                .tag("outcome", "rejected")
                .register(registry);
    }

    public void accepted() {
        accepted.increment();
    }

    public void duplicate() {
        duplicate.increment();
    }

    public void rejected() {
        rejected.increment();
    }
}
```

Define **exactly where each count increments**:

- `received`: listener starts handling a record; increments again on Kafka redeliveries.
- `attempted`: one business execution attempt; increments on retries.
- `accepted`: business operation completed—by DB commit or merely validation?
- `duplicate`: event ID already exists in inbox, or is it truly an exact duplicate?
- `rejected`: business validation categorized the event as unprocessable.

When **exact** committed transaction counts are required, in-memory counters are not authoritative because the JVM can crash after DB commit before incrementing, or increment before a transaction rolls back. Use DB audit/inbox/outbox tables for financial reconciliation and metrics for operational trends.

### 14.1. Do Not Count Transient Retries the Same as Final Failures

Suppose a record hits two transient errors before succeeding:

```text
Attempt 1: DB timeout
Attempt 2: DB timeout
Attempt 3: commit succeeds

Retry attempts = 2
Final failed events = 0
Business accepted = 1
```

Incrementing `payment_event_failed_total` in every `catch` makes dashboards report 2 failed events even though zero events were lost. Separate `processing_attempt_errors_total` from `final_processing_failures_total` and DLT recoveries.

## 15. Error Handling, Retries, and DLT Need Dedicated Telemetry

Spring Kafka uses `DefaultErrorHandler` and recoverers to handle listener exceptions. Observability must expose **retry progress**, **recovery decisions**, and **DLT send outcomes**.

Diagram:

```text
Kafka record
   |
   v
@KafkaListener
   |
   +-- success -------------> offset/transaction per policy
   |
   +-- exception
          |
          v
   DefaultErrorHandler
          |
          +-- retry with backoff
          |
          +-- exhausted
                 |
                 +-- DLT publish (must observe outcome)
                 +-- stop/fail (per policy)
```

A `KafkaTemplate` observation showing a successful DLT send only confirms broker acceptance under producer policy; downstream DLT triage still needs an owner, retention, and runbooks.

### 15.1. What DLT Metrics Should Exist?

| Metric | Meaning |
|---|---|
| Records recovered into DLT | Failures removed from the main path |
| DLT publish failure count | Risk of losing the recovery path |
| Oldest unresolved DLT record age | Aging unaddressed incidents |
| Pre-recovery error classification | Invalid payload, transient DB, schema mismatch |
| Records replayed from DLT | Remediation progress |
| Replay failures | Unresolved root causes |

These metrics usually require application/recoverer instrumentation and monitoring tooling; never assume Spring Kafka emits all of them out of the box.

### 15.2. Example Error Handler and DLT Recoverer Configuration

```java
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.util.backoff.FixedBackOff;

@Bean
DefaultErrorHandler paymentErrorHandler(
        KafkaTemplate<Object, Object> dltTemplate) {

    var recoverer =
            new DeadLetterPublishingRecoverer(dltTemplate);

    var handler = new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 2L)
    );

    handler.addNotRetryableExceptions(
            InvalidPaymentEventException.class
    );

    return handler;
}
```

`InvalidPaymentEventException` is a hypothetical domain exception; `dltTemplate` must target the right cluster, serializers, topics, and ACLs. This snippet illustrates classification only—it does **not yet include custom metrics or DLT send verification across all failure modes**.

If the consumer reads cluster A while the business producer writes cluster B, the DLT template must point to the cluster **intended to host the DLT**, usually A. An observed template sending to the wrong cluster is still a functional bug.

## 16. View Consumer Lag and Listener Duration Together

Example time-series view:

| Time | Group Lag | Listener p95 | DB p95 | Producer Send p95 | Initial Interpretation |
|---|---:|---:|---:|---:|---|
| 10:00 | 200 | 50 ms | 20 ms | 15 ms | Healthy |
| 10:05 | 2,000 | 55 ms | 20 ms | 15 ms | Producer load spike or insufficient partitions |
| 10:10 | 8,000 | 800 ms | 700 ms | 15 ms | DB may be the bottleneck |
| 10:15 | 15,000 | 850 ms | 730 ms | 16 ms | Consumers falling behind |
| 10:20 | 12,000 | 70 ms | 25 ms | 16 ms | Recovering, backlog draining |

Numbers are **illustrative** and do not prove root cause alone. Correlate logs, DB connection pools, query latencies, partition assignments, and producer rates before concluding.

### 16.1. Three Questions When Lag Rises

1. **Did input volume spike?** Check producer rate/bytes and topic ingress.
2. **Are consumers slowing down?** Check listener duration, retries/DLT, DB/API latency, and `max.poll.interval.ms`.
3. **Are active consumers/partitions insufficient?** Check group assignments/rebalances, partition count, pod/thread counts, and concurrency config.

Lag can briefly tick up right after deploys due to rebalances. Never alert on a single sample without a time window or deployment context.

## 17. Prometheus: Metric Names and Writing Queries

The Prometheus registry converts meter names to its naming convention. For example, a Micrometer Timer named `spring.kafka.listener` may export series such as:

```text
spring_kafka_listener_seconds_count
spring_kafka_listener_seconds_sum
spring_kafka_listener_seconds_max
```

Exact names, series types, and tags must be **verified on `/actuator/prometheus`**, as they depend on Micrometer version, registry, and instrumentation.

### 17.1. Counting Observed Listener Invocations

If the Timer metric exists, you can query:

```promql
sum(
  rate(spring_kafka_listener_seconds_count[5m])
)
```

This represents **completed listener operations per second** over the window. With batch listeners, one operation handles multiple records; with retries, one record runs multiple times. It is **not necessarily unique events/s**.

### 17.2. Average Listener Duration

```promql
sum(
  rate(spring_kafka_listener_seconds_sum[5m])
)
/
sum(
  rate(spring_kafka_listener_seconds_count[5m])
)
```

Yields seconds per operation when samples exist and both series are present.

For low-traffic jobs or listeners handling rare messages, a 5-minute window may hold too few samples. Widen the range, inspect weekly histograms, or check execution logs.

### 17.3. P95 with Histograms

When histograms are enabled and `_bucket` series exist:

```promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(spring_kafka_listener_seconds_bucket[10m])
  )
)
```

Use only when histograms are actually exported with sufficient samples. Percentiles on a topic receiving a handful of records per hour are misleading.

To enable histograms for specific Timers, configure Micrometer distribution on matching meter names:

```yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        "[spring.kafka.listener]": true
        "[spring.kafka.template]": true
```

Meter names here are examples for compatible stacks. Histograms consume memory and multiply time series; enable selectively for SLO needs rather than across high-cardinality tags.

### 17.4. Splitting Queries by Topic or Listener ID

Some meters carry tags for listener ID, topic, result, or exception. Because tag names vary by instrument and version, inspect live Prometheus labels first:

```text
# Illustrative example, not a guaranteed tag across all versions:
spring_kafka_listener_seconds_count{spring_kafka_listener_id="..."}
```

Never hardcode `name`, `listener`, `topic`, or specific tag keys without verifying. Once confirmed, group by stable labels so consumers with different SLAs are not blended together.

## 18. Dashboards for Spring Kafka Reliability Operations

Effective dashboards organize panels by role and outcome rather than cramming hundreds of raw metrics onto one screen.

### 18.1. Overview

| Panel | Measurement Source | Question |
|---|---|---|
| Applications alive/readiness | Spring Actuator / orchestrator | Are services and listeners healthy? |
| Group lag and lag trend | Kafka group exporter | Are consumers keeping up? |
| Incoming/outgoing rates | Kafka clients or brokers | Is traffic spiking or dropping abnormally? |
| Listener processing p95 | Micrometer Observation Timer | Is application code slowing down? |
| Business accepted/failed/duplicate | Business metrics/DB | How many events reached real outcomes? |
| DLT pending | DLT topic + audit | How much unresolved failure backlog exists? |
| Producer error/retry rate | Kafka client metrics + future callbacks | Is the send path unstable? |
| DB/API latency | Dependency instrumentation | Where is the downstream bottleneck? |

### 18.2. Producer Detail

Track:

- Sends/sec, bytes/sec, record error/retry rates.
- Request latency and record-size distributions.
- Available buffer memory / exhaustion.
- Broker ACK latency from client metrics.
- Events created in outbox but not yet published.
- Oldest pending outbox age and publish failure counts.
- End-to-end traces from business request to Kafka send as sampling allows.

If producer client metrics look fine while outbox pending grows, the fault likely sits in the **publisher scheduler, DB query, or outbox polling logic**, not Kafka.

### 18.3. Consumer Detail

Track:

- Group lag and per-partition lag distribution.
- Records consumed/sec.
- Listener Timer p50/p95/p99 where sample counts suffice.
- Error handler attempts and final outcome breakdowns.
- DLT records/age and replays.
- Commit latency/failures.
- Rebalance count/duration and assigned partition count.
- DB connection pool waits, transaction durations, and timeouts.
- Idempotently processed events and duplicate counts.

A group with low total lag yet **huge lag on one partition** often suffers from data skew or a poison message. Never graph total lag alone.

## 19. Alerting: Measure Impact Before Paging

Example alert rules distinguishing **symptoms** from **causes**:

| Illustrative Alert | Condition | Action |
|---|---|---|
| Sustained consumer lag growth | Group lag climbs continuously for 15 minutes past SLA | Check load, partitions, retries, DB |
| Zero consumption progress | Lag > 0 while processed rate = 0 for 10 minutes | Check assignments, pauses, auth, poison records |
| Producer send errors | Error rate exceeds baseline for 5 minutes | Check brokers/network/ACLs/quotas |
| DLT surge | DLT recoveries spike abnormally | Check schema errors / poison data |
| High listener duration | p95 breaches SLO across enough samples | Check DB/API/CPU/GC |
| Aging outbox | Oldest pending age exceeds SLA | Check publisher and Kafka cluster B |
| Continuous rebalances | Rebalance rate rises and lag stops recovering | Check pods, poll interval, static membership |
| Lost telemetry | Prometheus scrape target `up=0` | Check instrumentation/endpoint/network |

Thresholds are illustrative. Alerting on "zero messages processed" when no messages are arriving produces false positives; condition alerts on lag/backlog and pipeline schedules.

### 19.1. Writing Actionable Alerts

Good alerts include:

- Clear group/topic or service name.
- Business SLA impact severity.
- Evaluation window avoiding single-spike noise.
- Direct links to dashboards and relevant logs/traces.
- Runbook: owner, diagnostic steps, conditions to pause/resume/restart.
- Recovery verification criteria, e.g. falling lag and restored business throughput.

Never auto-kill consumers or reset offsets solely because lag is high. Without idempotency and replay workflows, those actions amplify duplicates or drop data.

## 20. Sampling, Performance, and Telemetry Cost

Aggregated metrics are far cheaper than storing full traces for **every message**. At 100,000 records/sec, exporting full traces with heavy attributes incurs substantial cost.

Illustrative policy:

```yaml
management:
  tracing:
    sampling:
      probability: 0.10
```

This controls **tracing sampling**. It does **not** mean the listener is instrumented only 10% logically or processes only 10% of records. Metrics still record via active handlers/registries while spans export according to sampling.

### 20.1. Choosing Sampling by Need

- Low traffic, critical transactions: higher trace sampling may be affordable.
- Very high traffic: lower baseline sampling, rely on metrics for trends, and boost sampling conditionally during incidents.
- Rare failures: use controlled logging/audits or error-tail sampling if your tracing backend supports it.
- Sensitive data: strip attributes, redact, and limit retention.

**Never rely on trace sampling to count exact business events.** An unsampled trace does not mean an event wasn't processed; a trace showing multiple attempts does not mean multiple unique business events.

### 20.2. Instrumentation Overhead

Enabling metrics/tracing adds CPU, memory, allocations, exporter network I/O, and time-series overhead. Benchmark before and after enabling under representative load, measuring:

- Throughput, listener p95/p99, GC pauses.
- Registry and exporter CPU/memory.
- OTLP export latency when the collector fails.
- Prometheus series count from tags and histograms.
- Telemetry pipeline buffers and rate limits.

Observability exists to support reliability—it must never destabilize the app if an exporter stalls. Use async exporters, bounded buffers, and finite timeouts per your stack design.

## 21. Cardinality: The Mistake That Breaks Monitoring

Prometheus stores a separate time series per unique **metric name + label set**. Kafka carries many identifiers, not all of which belong in metric labels.

### 21.1. Typically Appropriate Labels

- `application`: service name from a bounded set.
- `cluster`: small set of cluster IDs/aliases.
- `topic`: within a managed topic inventory.
- `consumer_group`: lifecycle-controlled group names.
- `listener_id`: statically configured IDs.
- `outcome`: `success`, `failed`, `recovered`.
- `exception_class`: normalized into a bounded category set.

Even `topic`/`group` becomes high-cardinality if an app spawns per-customer or per-session topics/groups. Evaluate **actual value cardinality**, not just field names.

### 21.2. Labels to Avoid

- `eventId`, `messageId`, `paymentId`, `orderId`.
- Raw payloads or raw exception messages.
- Per-record timestamps.
- Per-record Kafka offsets.
- Unique per-request/per-event trace IDs.
- Randomly generated `client.id` on every reconnect without bounds.
- `tenantId` when tens of thousands of tenants exist.

These belong in **structured logs or trace attributes** under proper access controls.

Wrong example:

```java
Counter.builder("payment.processed")
        .tag("eventId", event.eventId())
        .register(registry)
        .increment();
```

Every new event registers a new meter. Fix it to:

```java
Counter.builder("payment.processed")
        .tag("outcome", "accepted")
        .register(registry)
        .increment();
```

Better yet, construct and cache the `Counter` once instead of looking it up on every invocation, especially for fixed tags.

### 21.3. Never Put Personal Data in Trace Attributes Casually

Traces and logs are stored and queried too. Never attach card numbers, full names, email addresses, or secrets to spans for "easier debugging." Use pseudonymized reference IDs, bounded retention, and strict access control.

## 22. Distinguishing Observation, Offset Commits, and Transactions

A listener observation may finish while the container is still performing the offset commit per policy. A `KafkaTemplate` observation may record a send while the application's DB transaction has not committed yet. Therefore, maintain a **boundary table**:

| Activity | What It Actually Proves | What Cannot Be Inferred |
|---|---|---|
| Listener callback finished | Method returned along the execution path | External business data definitely committed |
| Producer future succeeded | Broker acknowledged record per `acks` | Consumer processed the event |
| Kafka offset commit succeeded | Group advanced its read position | Non-Kafka side effects were not duplicated |
| DB transaction committed | Data persisted in DB | Kafka output also reached the broker |
| DLT publish succeeded | Record reached DLT per producer semantics | Someone triaged or recovered the record |
| Trace finished | Instrumented operation completed | End-to-end exactly-once |

### 22.1. DB + Kafka Outbox

When a service writes to a DB and publishes to Kafka, a more reliable flow is:

```text
Kafka consumer receives E-101
          |
          v
DB transaction:
  insert inbox(eventId=E-101) if absent
  update business tables
  insert outbox(eventId=E-101)
  COMMIT
          |
          v
Consumer ack/offset commit per policy
          |
          v
Outbox publisher
   |
   +-- send to Kafka
   +-- observe future success/failure
   +-- mark delivered
          |
          v
Downstream idempotent consumer
```

Track `inbox_duplicate_total`, `outbox_pending`, `outbox_publish_failed_total`, and Kafka producer metrics separately. A fast producer Timer never replaces measuring outbox age.

### 22.2. Kafka Transactions

Spring Kafka supports Kafka transactions and certain Kafka-to-Kafka exactly-once patterns when properly configured. Yet Kafka transactions **do not cover PostgreSQL**, nor do they span two independent Kafka clusters in one atomic transaction.

A Kafka "transaction committed" metric never proves external database updates committed alongside it. When business consistency is the goal, test crash/recovery paths and reconcile state.

## 23. Multi-Cluster Deployments and Observation

In systems where producers and consumers connect to different clusters:

```text
Kafka Cluster A                          Kafka Cluster B
   inbound topic                            outbound topic
       |                                         ^
       v                                         |
 ConsumerFactory A                       ProducerFactory B
       |                                         |
 ListenerContainerFactory A               KafkaTemplate B
       |                                         |
       +------------- Application ---------------+
                             |
                      ObservationRegistry
                             |
                      Metrics + Tracing
```

You can share **one `ObservationRegistry`** inside the JVM across client roles while adding stable low-cardinality tags distinguishing inbound/outbound/cluster where component conventions support them.

However:

- A shared registry does not ensure clients connect to the right clusters.
- Listener factory A must enable observation on its exact `ContainerProperties`.
- `KafkaTemplate` B must enable observation on the exact bean used by the publisher.
- Custom client factories may need explicit Kafka client metrics listeners registered.
- A DLT producer targeting A may need a separate `KafkaTemplate`; instrument it too if you want visibility.
- Additional Kafka admin/clients may hit separate clusters; verify metrics and health per role.

A common mistake is enabling `spring.kafka.template.observation-enabled` for Boot's default template while the business service injects a custom `outboundKafkaTemplate` lacking observation. Traces then break at outbound Kafka even though publishing works.

## 24. Application Profiles and Environment Configuration

Separating configuration across profiles keeps operations clean.

Local example:

```yaml
# application-local.yml
spring:
  kafka:
    bootstrap-servers: localhost:9092

management:
  tracing:
    sampling:
      probability: 1.0

  otlp:
    tracing:
      endpoint: http://localhost:4318/v1/traces
```

Production example:

```yaml
# application-prod.yml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS}

management:
  tracing:
    sampling:
      probability: 0.05

  otlp:
    tracing:
      endpoint: ${OTEL_TRACES_ENDPOINT}
```

Sampling values are illustrative. For metric scraping, production must also configure Prometheus targets, service discovery, and network policies so scrapers reach endpoints without exposing them to the public internet.

### 24.1. Never Let Localhost Defaults Leak into Production

A pattern like:

```yaml
bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}
```

is handy locally, but if the env var is omitted in production, the app may try connecting to the wrong place. Make production properties mandatory, fail fast on validation, and keep fallbacks strictly in local profiles.

### 24.2. Manage Configuration as a Contract

Document:

| Config Item | Owner | Value / Source | Verification |
|---|---|---|---|
| Kafka bootstrap | Kafka Platform | Env/config per cluster | Connectivity/metadata test |
| Topic/group | Service Team | Versioned config | Contract/wiring test |
| Observation enabled | Service Team | Boot properties/custom beans | Endpoints and test spans |
| Prometheus endpoint | Observability | Actuator + network policy | Scrape `up` |
| OTLP endpoint | Observability | Secret/config | Collector receives spans |
| Sampling | SRE + Service Team | Per-env policy | Trace volume/coverage |
| Metric tags | Observability | Stable allowlist | Cardinality review |
| Alert thresholds | Service Owner | Per-workload SLOs | Incident simulations |

A line reading `metrics enabled=true` in documentation does not prove the **telemetry pipeline works**. Verify end-to-end from app through scraper/collector to dashboard.

## 25. Securing Actuator, Telemetry, and Collection Pipelines

The `/actuator/prometheus` endpoint can expose topic names, group IDs, broker aliases, app versions, and internal operational details. Never expose it publicly just so Prometheus can scrape it.

Appropriate safeguards:

- Restrict endpoint access to the monitoring network only.
- Enforce authentication/authorization or service-mesh policies per infrastructure.
- Use TLS when metrics cross trust boundaries.
- Never emit secrets in tags, logs, span attributes, or exception messages.
- Protect exporter endpoints and credentials; never commit passwords/tokens in YAML.
- Bound retention and access controls on traces and logs.
- Avoid writing raw Kafka payloads into tracing or logging pipelines.
- Control cardinality to prevent backend overload.

**Tracing headers are not authentication credentials.** A record carrying an "internal-looking" trace ID must still pass business validation and authorization.

## 26. Testing Metrics: Unit Tests Without a Kafka Broker

For custom `MeterRegistry` counters, use `SimpleMeterRegistry` in unit tests for deterministic assertions.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import org.junit.jupiter.api.Test;

class PaymentOutcomeMetricsTest {

    @Test
    void acceptedCounterIncrementsOnce() {
        try (SimpleMeterRegistry registry =
                     new SimpleMeterRegistry()) {

            PaymentOutcomeMetrics metrics =
                    new PaymentOutcomeMetrics(registry);

            metrics.accepted();

            Counter counter = registry.find("payment.event.outcome")
                    .tag("outcome", "accepted")
                    .counter();

            assertEquals(1.0, counter.count(), 0.000001);
        }
    }
}
```

This proves the code increments the Counter accurately, not that Kafka committed messages or metrics reached Prometheus. In-memory counters reset on JVM restarts; use them for operational trends, not durable audit tables.

### 26.1. Testing Tag Policies

Write tests or static checks prohibiting business IDs in metric tags. Suppose `PaymentOutcomeMetrics` allows only `outcome` in `{accepted, duplicate, rejected}`.

Verify that processing many events with distinct IDs does not grow meter count with ID count. If meter count scales linearly with records, custom instrumentation is likely emitting dynamic tags.

### 26.2. Testing `ObservationRegistry`

For custom observations, use `TestObservationRegistry` from Micrometer Observation's test module or a fake `ObservationHandler` to verify operation names, low-cardinality keys, errors, and lifecycle.

Assertions to include:

- Exact observation name, e.g. `payment.process`.
- `operation` belongs to the defined value set.
- Exceptions are reported to the handler when business logic throws.
- `eventId` is absent from low-cardinality keys.
- Observation stops cleanly even on failure.

Remember that a bare registry without handlers emits no spans/metrics. To assert Timers, attach a metrics handler/registry or use a configured Spring Boot test context.

## 27. Testing Spring Boot Wiring: Observation Must Be Enabled on Real Beans

With custom `KafkaTemplate` and listener factories, verify observation is enabled and registries are wired properly.

Spring context test example:

```java
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.KafkaTemplate;

@SpringBootTest
class KafkaObservationWiringTest {

    @Autowired
    @Qualifier("paymentKafkaTemplate")
    KafkaTemplate<String, String> template;

    @Autowired
    @Qualifier("observedListenerFactory")
    ConcurrentKafkaListenerContainerFactory<String, String> factory;

    @Test
    void customComponentsHaveObservationEnabled() {
        // Check factory/container properties per your version's API.
        assertTrue(
                factory.getContainerProperties().isObservationEnabled()
        );

        // Beyond checking bean existence, integration tests must
        // trigger a send and verify a real observation.
        assertTrue(template != null);
    }
}
```

This is a **basic wiring check**. When using multiple custom factories, confirm listeners use the tested factory and templates actually have observation enabled. Spring test contexts need full dependencies, configs, and producer/consumer beans; tests can use a dummy bootstrap if not connecting to a broker, though that does not verify network connectivity.

### 27.1. End-to-End Kafka Testing with a Test Broker

`spring-kafka-test` and `@EmbeddedKafka` let you test record sending and receiving. Structural example:

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.test.context.EmbeddedKafka;

@SpringBootTest(properties = {
        "spring.kafka.listener.observation-enabled=true",
        "spring.kafka.template.observation-enabled=true"
})
@EmbeddedKafka(
        partitions = 2,
        topics = {
                "test-payments-in",
                "test-payments-out"
        },
        bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
class KafkaObservationIntegrationTest {

    @Test
    void producerAndListenerAreObserved() {
        // Arrange: create message/test listener and test registry.
        // Act: send record to embedded topic.
        // Assert:
        //   1. Listener receives record within bounded timeout.
        //   2. Matching observations/spans exist for send and receive.
        //   3. Timer metrics record samples per active version.
        //   4. No unintended records are processed.
    }
}
```

This is a **test skeleton**, omitting listener, template, registry, and assertion implementations. Using `@EmbeddedKafka` alone does not prove traces reach an external exporter. To test export, use an integration test with an in-memory span exporter or inspectable test collector.

### 27.2. Testcontainers for Production-Like Environments

Testcontainers Kafka simulates real brokers more faithfully and lets you run two Kafka containers to validate multi-cluster configs.

Key scenarios:

1. Consumer reads cluster A; producer writes to cluster B.
2. Both sides emit metrics/observations from their respective factories.
3. Tracing context follows events as the service relays messages.
4. Producer broker B unavailable: future fails; pending outbox grows without losing events.
5. Consumer DB timeout: retries are recorded without inflating business accepted counts.
6. Invalid message: listener error handler routes to DLT per policy with final-recovery metrics.
7. Consumer rebalance/restart: offset commits follow semantics; events stay idempotent.
8. Schema/deserialization failure: error signal fires even when the listener method is never reached.
9. Collector outage: business processing continues per design while telemetry buffers/retries boundedly.
10. Prometheus endpoint blocked from unauthorized networks while authorized scrapers succeed.

Never replace a two-cluster test with two topics on **one broker** and claim credentials, routing, and cross-cluster failures were tested.

## 28. Common Operational Issues

### 28.1. Metrics Exist, No Traces Appear

Check:

- Is a compatible Micrometer Tracing bridge present?
- Is observation actually enabled on the template/listener in use?
- Are `ObservationRegistry` and tracing handlers active?
- Is sampling probability too low for test traffic to show spans?
- Are collector endpoints and credentials correct?
- Are trace headers propagating through Kafka?
- Is context lost across async executors?

**Never leave sampling at 100% long-term in production just to debug one incident** without assessing traffic and cost. Raise it temporarily per runbook.

### 28.2. Traces Exist, No Kafka Client Metrics

Check factory/client Micrometer instrumentation, registry, Boot auto-config beans, active topic traffic, and endpoints. `KafkaTemplate`/listener traces do not replace Kafka client metrics for fetch, buffers, and retries.

### 28.3. Consumer Lag Vanishes When Pods Crash

If dashboards read gauges solely from live `KafkaConsumer` instances, pod crashes stop the series and make lag look like zero. Use cluster-side group lag exporters and scrape-target availability alerts to catch this.

### 28.4. Duplicate Metrics After Adding Instrumentation

If a manual Timer wraps a listener alongside enabled Observation Timers, the same operation gets recorded twice under near-identical names. Clarify each panel's metric source, remove redundant instrumentation, or name explicitly.

### 28.5. DLT Grows While Listener Failure Rate Looks Low

The error handler may recover records with listener instrumentation reporting result/exception tags differently from your business metric definition. Monitor recoverer outcomes and DLT publishers directly, not just listener Timer error tags.

### 28.6. Traces Break Between Producer and Consumer

Common causes: stripped type/trace headers, incompatible formats, unobserved producer, unobserved custom listener factory, lost async context, or sampling. Inspect record headers in a safe test environment rather than logging full production payloads.

### 28.7. Slow Consumer Processing Despite Normal Kafka Client Metrics

The bottleneck may be DB connection pools, downstream HTTP calls, thread contention, or GC. Nested operation traces and DB metrics reveal more than Kafka network stats alone.

### 28.8. Missing Meters on Quiet Topics

Some meters instantiate lazily on first operation. Missing series do not prove healthy processing. Alerts must distinguish `missing telemetry` from `zero traffic` using `up`, Kafka group assignments, and business schedules.

## 29. End-to-End Monitoring Setup Procedure

Follow this rollout sequence:

1. **Finalize SLOs and event semantics:** consumer lag, event age, delivery success, DLT recovery, and business commits.
2. **Add Actuator/registry:** verify `/actuator/metrics` and `/actuator/prometheus` in the app.
3. **Enable Observation on the actual `KafkaTemplate` and listener factories:** via Boot properties or custom Java beans.
4. **Configure tracing bridge/exporter:** verify spans reach the backend in test environments.
5. **Collect Kafka client metrics:** watch producer retries/buffers and consumer polls/commits.
6. **Collect independent broker and group lag metrics:** never rely solely on client gauges.
7. **Add clearly defined business metrics:** attempted, accepted, duplicate, final failure, outbox pending.
8. **Enforce tag governance:** low-cardinality labels only, never payloads or event IDs.
9. **Build dashboards:** overview, producer, consumer, DLT, and dependencies.
10. **Define SLO-based alerts:** include evaluation windows, runbooks, and owners.
11. **Test failure modes:** broker/DB/collector outages, rebalances, redeliveries, and DLT publish failures.
12. **Roll out with verification:** reconcile old vs. new telemetry when upgrading instrumentation or renaming metrics.
13. **Watch telemetry costs:** cardinality, traces/sec, storage retention, and exporter CPU/memory.
14. **Maintain the contract:** update metric queries and runbooks whenever Kafka versions, serializers, group IDs, partitions, or concurrency change.

## 30. Deployment and Configuration Checklist

| Check | Why Does It Matter? |
|---|---|
| `spring-boot-starter-actuator` and matching registry exporter present | Metrics have an export path |
| Observation enabled on the right `KafkaTemplate` | Publish flow is instrumented |
| Observation enabled on the right listener container factory | Receive callbacks are instrumented |
| Tracing bridge/exporter configured if traces are needed | Spans export beyond JVM memory |
| Kafka client metrics appear once clients become active | Network/poll/buffer visibility exists |
| Independent source exists for broker and group lag | Detects dead consumers and backlogs |
| Topic/group/client ID cardinality is bounded | Prevents backend series explosions |
| Payloads and event IDs excluded from metric tags | Prevents cardinality spikes and data leaks |
| Micrometer Timers/histograms are not double-counted | Keeps SLOs/p95 trustworthy |
| Retry metrics separate attempts from final failures | Prevents inflated failure counts |
| DLT publishing is observed with a runbook | Preserves a data-recovery path |
| Outbox pending/age measured if using an outbox | Detects unsent events |
| Actuator endpoints are not exposed unintentionally | Protects operational internals |
| Collector outages do not hang business flows | Telemetry never becomes a single point of failure |
| Alerts use SLA-aligned thresholds and windows | Reduces false positives |
| Restart/rebalance/offset-commit paths tested | Prevents false exactly-once assumptions |
| Multi-cluster routing tested | Prevents metrics/debug traffic going to the wrong place |
| Production profile has no casual localhost fallback | Fails fast on missing config |
| Config and metric names are versioned | Upgrades do not blind dashboards |

## 31. Hands-On Exercises

Build `payment-worker` with a consumer reading `payment-commands.v1`, a producer writing `payment-results.v1`, and a database storing payment state.

### Requirement 1: Core Metrics

1. Add Actuator and the Prometheus registry.
2. Expose `/actuator/metrics` and `/actuator/prometheus` on a controlled test network.
3. Enable listener and template observation via Spring Boot properties.
4. Send 20 records to the test topic and confirm Timer/metrics record samples.
5. Contrast callback invocation metrics against unique deduplicated business events.

### Requirement 2: Tracing

6. Add Micrometer Tracing bridge and OTLP exporter targeting a test Collector.
7. Confirm traces link Kafka producer and consumer spans properly.
8. Add a nested `payment.process` observation around the business operation.
9. Test offloading to an async executor and verify context propagation.
10. Verify zero payloads, tokens, or account numbers appear in spans or baggage.

### Requirement 3: Reliability Metrics

11. Add `accepted`, `duplicate`, and `rejected` business counters with bounded outcome labels.
12. Simulate two DB timeouts followed by success; distinguish retry attempts from final failures.
13. Configure a DLT recoverer; track records sent to the DLT and DLT send failures.
14. Use an external consumer-group lag source to detect a killed consumer pod.
15. Simulate slow broker ACKs on the producer and observe producer future errors/latency.

### Requirement 4: Dashboards and Alerts

16. Build a dashboard covering group lag, records/s, listener p95, producer retries/errors, DLT count, and outbox age.
17. Alert on 15-minute rising lag and event processing age breaching SLO; explain why single-sample alerts fail.
18. Verify dashboards never label by dynamic `eventId` or payload.
19. Load-test with 1%, 10%, and 100% sampling; compare throughput, CPU, and trace volume in test.
20. Simulate a Collector outage and verify business processing continues per design.
21. With consumer on cluster A and producer on cluster B, configure separate factories/templates, enable observation on each bean, and prove traces/metrics never mix clusters.
22. Write runbooks for three scenarios: high lag, rising DLT, and lost traces post-deploy.

**Review Question 1:** `spring.kafka.listener.observation-enabled=true` is set and the listener Timer appears. Does that prove messages processed strictly once and the DB committed?

**Answer:** **No.** The Timer reflects instrumented operations per listener semantics; offset commits, database transactions, retries/rebalances, and idempotency are separate concerns requiring business instrumentation and consistency testing.

**Review Question 2:** A consumer pod dies and its `records-lag-max` metric disappears. Can you conclude the group has zero lag?

**Answer:** **No.** Client metrics stopped emitting because the client is gone. Measure group lag from the Kafka cluster/offsets and monitor pod and scrape-target availability.

**Review Question 3:** If `spring_kafka_listener_seconds_count` increases by 1,000, were exactly 1,000 unique events processed successfully?

**Answer:** **Not necessarily.** Timer counts reflect callback attempts, batch listeners, retries, or other framework outcomes. Counting unique business events requires keys, transactions, and dedicated business metrics/audits.

## 32. References

- [Spring Boot Reference — Apache Kafka Support](https://docs.spring.io/spring-boot/reference/messaging/kafka.html): Boot Kafka properties, `KafkaTemplate`, listener containers, and observation configuration.
- [Spring Boot Reference — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): `MeterRegistry`, Actuator metrics endpoint, Prometheus exporter, and distribution settings.
- [Spring Boot Reference — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): Micrometer Tracing, bridges, tracing exporters, and sampling.
- [Spring Kafka Reference — Micrometer](https://docs.spring.io/spring-kafka/reference/kafka/micrometer.html): Micrometer metrics, observation, and monitoring for `KafkaTemplate`/listeners.
- [Spring Kafka Reference — Observability](https://docs.spring.io/spring-kafka/reference/kafka/micrometer.html): listener/template observation and conventions on supported versions.
- [Spring Kafka Reference — Receiving Messages](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages.html): listener containers, ack modes, and concurrency.
- [Spring Kafka Reference — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html): `DefaultErrorHandler`, retries/recovery, and DLT.
- [Spring Kafka Reference — Exactly Once Semantics](https://docs.spring.io/spring-kafka/reference/kafka/exactly-once.html): Kafka transactions and guarantee boundaries.
- [Spring Kafka Reference — Testing](https://docs.spring.io/spring-kafka/reference/testing.html): `EmbeddedKafka` and integration tests.
- [Micrometer Documentation — Observation](https://docs.micrometer.io/micrometer/reference/observation.html): observation lifecycle, conventions, and key-values.
- [Micrometer Documentation — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html): Timers and duration measurement.
- [OpenTelemetry — Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/): cross-process tracing context.
- [Prometheus Documentation — Histograms and Summaries](https://prometheus.io/docs/practices/histograms/): rates, buckets, and percentiles.
- [Apache Kafka — Monitoring](https://kafka.apache.org/documentation/#monitoring): Kafka broker/client metrics.
- [Apache Kafka — Consumer Configuration](https://kafka.apache.org/documentation/#consumerconfigs): offsets, polling, fetching, and group semantics.
