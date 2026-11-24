# Designing a Reliability Dashboard for Spring Kafka

## 1. Purpose of a Reliability Dashboard

When operating a Spring Kafka system, the primary question is not simply **"Is Kafka still up?"**, but rather:

> **Are business events being received, processed, completed, and recovered within their deadlines?**

A Kafka cluster can be healthy, topics can still accept messages, and consumer processes can report `UP`, yet a batch of messages may be stuck on a poison pill, consumer lag may be climbing, retries may be looping, or records may be piling up in a dead-letter topic (DLT) with no one handling them.

Order-ingestion architecture example:

```text
Order API
   |
   | produce order.created
   v
Kafka: orders.created
   |
   | consumer group = order-processors
   v
Spring Kafka @KafkaListener
   |
   +-- success --> update/order projection --> business completion
   |
   +-- transient failure --> retry / backoff --> success
   |
   +-- non-recoverable --> orders.created.DLT --> investigation/re-drive
```

An operational dashboard must show **current service availability**, **end-to-end latency**, **processing rate**, **backlogs**, and **failures and recovery**, while giving on-call engineers enough context to pick the next step.

After completing this lesson, learners will be able to:

1. Translate reliability requirements into measurable SLIs and SLOs.
2. Select metrics across producer, Kafka broker, consumer group, Spring listener, retry, and DLT layers.
3. Structure a Grafana/Prometheus dashboard from high-level overview to drill-down views.
4. Distinguish lag, throughput, processing latency, event age, and success ratios.
5. Add instrumentation with Spring Boot Actuator and Micrometer.
6. Write PromQL queries for panels and alerts while recognizing metric limitations.
7. Build investigation runbooks for rising lag, listener errors, growing DLTs, or producer fencing.
8. Validate the dashboard via failure injection before relying on it in production.

Illustrative scope: **Java 17+, Spring Boot 3.x, Spring Kafka 3.x, Micrometer, Prometheus, and Grafana**. Application-defined metric names in this guide are *illustrative conventions*, not a promise that Spring Kafka exports all of them out of the box. Systems running Spring Kafka 4.x or different exporters must verify exact metric names and APIs per version.

## 2. Data Flow Map and Where Signals Originate

```text
       [Producer API / Outbox publisher]
         |  acks, send failures, send latency
         |  retries, throughput, transaction outcome
         v
       [Kafka Broker + Topic]
         |  broker health, partitions, replication
         |  throughput, request latency, ISR
         v
       [Consumer Group]
         |  committed offsets, log end offsets
         |  group lag, rebalance, assignment
         v
       [Spring @KafkaListener]
         |  handled records, processing latency
         |  exceptions, retries, acknowledgements
         v
       [Database / External API / Kafka output]
         |  business completion, idempotency
         |  E2E age, correctness, publish outcome
         |
         +-- failed / exhausted retry
                      |
                      v
                  [DLT / Quarantine]
                      |
                      +-- oldest unresolved, re-drive
                      +-- recovery outcome and age

 Observability plane:
  Spring Boot Actuator/Micrometer
  Kafka client metrics/JMX
  Broker JMX metrics
  Consumer group offset exporter
  Logs/traces/audit and deployment annotations
                      |
                      v
              Prometheus / TSDB
                      |
                      v
             Grafana dashboards + alerts
```

**Core principle:** no single metric layer captures the entire journey. Consumer lag comes from committed vs. log-end offsets; handler executions come from the app; broker replication health comes from Kafka; and business correctness usually has to be measured in the database or downstream system.

A "Kafka OK" dashboard showing only broker counts and CPU will miss business outages. Conversely, a dashboard showing only listener exceptions can miss unreachable brokers, under-replicated partitions, or a consumer group holding zero partition assignments.

## 3. Identifying Dashboard Users and Questions to Answer

Design panels around operational questions rather than pulling every available metric onto Grafana.

| Audience | Primary Question | Information Needed |
| --- | --- | --- |
| Application on-call | Are messages processing on time? | SLOs, backlogs, event age, error/retry/DLT rates, consumer state |
| Kafka platform team | Can brokers handle the traffic? | ISR, under-replicated partitions, request latency, broker/network/disk |
| Business owner | Which orders are delayed or failing? | Business completion, pending counts, DLT/quarantine, reconciliation |
| Release team | Did a new rollout degrade reliability? | Deploy annotations, before/after errors & lag, rebalances, versions |
| Incident commander | What is the blast radius and timeline? | Cluster, environment, service, topic, consumer group, and start time |

Maintain **one overview dashboard** for end-user/business health alongside component drill-down dashboards. Avoid cramming hundreds of panels onto one screen; more charts do not automatically speed up incident response.

### Minimum Filter Dimensions

The sample dashboard exposes template variables:

```text
environment: dev | staging | prod
cluster: kafka-cluster-a | kafka-cluster-b
service: orders-producer | orders-consumer
topic: orders.created | orders.validated | orders.created.DLT
consumer_group: order-processors
listener: orderCreatedListener
```

These values must come from a reliable inventory or label policy rather than letting dashboards guess which topics belong to which business flow. Enforce naming and labeling conventions so production and staging never mix and metrics across two Kafka clusters are never summed together.

## 4. Reliability Is Not Equivalent to Throughput

A system can process 50,000 events/second while silently dropping a critical record category. Group signals by reliability goal:

| Goal | SLI or Signal | Meaning |
| --- | --- | --- |
| Availability | Share of eligible events completed | Messages do not vanish silently |
| Timeliness | Share completed within deadline, p95/p99 event-to-completion | Stronger than merely "eventually processed" |
| Integrity | Duplicate/missing/inconsistent business effects | No double payments or dropped orders |
| Recoverability | Retry success, DLT recovery time, unresolved backlog | Ability to bring failed records to valid state |
| Capacity | Lag, ingress/egress rates, consumer saturation | Sufficient capacity to keep up with ingress |
| Infrastructure | Broker availability, ISR, replication, storage | Underlying platform stability |

**Listener success is not necessarily business success.** If a listener simply pushes messages into an internal queue and returns, a listener success metric measures *intake and forwarding*, not orders safely persisted to the database.

Before naming any metric `success`, document **which boundary it measures**: deserialization, handler invocation, DB persistence, offset commit, or end-to-end business completion.

## 5. Designing SLIs and SLOs Before Picking Charts

Suppose the product commits to: **99.9% of valid order events completed within 5 minutes, measured over a rolling 30-day window**.

Definitions:

- *Eligible event*: an event with a valid business ID conforming to the accepted contract and outside explicitly documented exclusion policies.
- *Completed event*: the business outcome persisted durably at the defined boundary, not merely the listener returning.
- *Latency*: elapsed time from event acceptance (or contracted business event time) until the outcome commits.
- *Denominator*: count of **unique business events**, not total listener invocations.
- *Window*: rolling 30 days in UTC or contracted timezone.

Illustrative SLI:

\[
\text{TimelyCompletionSLI}
=\frac{\#\{\text{eligible events completed within 5 minutes}\}}
{\#\{\text{eligible events past evaluation deadline}\}}
\]

If an event arrived 10 seconds ago against a 5-minute deadline, it should not yet count as missing the deadline in a "past evaluation deadline" denominator unless the SLO explicitly defines it differently. Publish cutoff rules to prevent artificial dashboard swings during traffic spikes.

Example SLO:

```text
SLI: timely business completion, per unique eligible event
SLO: >= 99.9% over rolling 30 days
Deadline: 5 minutes
Exclusions: explicitly documented invalid-source cases only
Owner: orders-processing team
Error budget: 0.1% of eligible events in window
```

### Why Not Use Listener Error Rate as the Sole SLO?

One event might invoke the handler three times:

```text
Attempt 1: timeout   -> failure
Attempt 2: timeout   -> failure
Attempt 3: success   -> completed business effect
```

Measured by **attempts**, the success rate is 1/3. Measured by **unique eligible business events**, that event completed successfully. Both metrics are valuable, yet they measure different things:

- **Attempt failure rate**: diagnostic signal for dependency health and wasted capacity.
- **Business completion SLI**: customer-facing reliability of the business flow.

Computing an exact unique completion SLI requires event IDs and a durable ledger/state machine or trusted source records; `rate(listener_success_total) / rate(listener_total)` alone is rarely enough.

## 6. The First Four Signal Groups Every Dashboard Needs

To make a dashboard immediately actionable, prioritize:

1. **Traffic and progress:** successful producer send rate, consumer processing rate, and completed business events.
2. **Lag and freshness:** consumer group backlog, event age at processing, and time since last durable completion.
3. **Errors and recovery:** handler errors, retries, DLTs, transaction aborts, and unresolved items awaiting replay.
4. **Saturation and infrastructure:** CPU/heap, connection pools, thread concurrency, broker request latency, and replication health.

These map to the four golden signals (**traffic, errors, latency, saturation**). For Kafka, add **offsets, lag, rebalances, and DLTs** because it is an asynchronous pipeline rather than a simple HTTP request/response service.

## 7. Consumer Lag: Essential Yet Easily Misunderstood

For a topic-partition, a common lag model is:

\[
\text{lag}_{p}
=\text{logEndOffset}_{p}-\text{committedOffset}_{p}
\]

In practice, exporters and Kafka client metrics may compute lag using either **fetch position** or **committed group offset**. Know which definition your datasource uses.

Example consumer group across four partitions:

| Partition | Group Lag (records) |
| --- | ---: |
| 0 | 1,200 |
| 1 | 1,100 |
| 2 | 40 |
| 3 | 60 |
| **Total** | **2,400** |

If the group sustains **100 records/second** with no new arrivals, `2,400 / 100 = 24 seconds` serves only as a **very rough backlog estimate**, not true "event age" or an SLA metric. While producers keep writing, partitions skew, per-record times vary, or consumers pause, that estimate diverges widely.

### Valid Uses of Lag

- Total lag by **consumer group + topic + cluster**: overall backlog size.
- Max lag across partitions: catches hot partitions or unbalanced assignments.
- Lag rate of change: whether the backlog is growing, draining, or stalled.
- Lag alongside input rate and processing throughput: pinpoints why the group falls behind.
- Retry-topic and DLT lag (when consumers exist): pending backlogs on recovery streams.

### What Lag Cannot Tell You

- Does not directly reveal **the age of the oldest unread record**.
- Does not prove events produced accurate business outcomes.
- Does not measure how long handlers spend per record.
- Does not explain why consumers failed to commit offsets.
- Does not fully capture events successfully sent to a DLT yet still awaiting replay.

**Special note on offset commits:** with manual acks, transactions, and async processing, fetch position, processing position, and committed offset can diverge. A group may have fetched many records without committing yet; depending on the exporter, lag reflects "uncommitted" or "unfetched." Never treat an ambiguous lag metric as proof that business work finished.

## 8. Distinguishing Processing Latency, Event Age, and Backlog Age

Several distinct durations are loosely called "Kafka latency," yet mean very different things:

| Metric | Starts At | Ends At | Meaning |
| --- | --- | --- | --- |
| Producer send latency | Send call start | Broker ACK / future completes | Publishing and acknowledgment time |
| Kafka broker request latency | Broker receives request | Broker sends response | Broker/network performance |
| Listener processing duration | Handler entry | Handler returns/throws | Application processing time |
| Event age at processing | Chosen event timestamp | Processing start or finish | How stale incoming data is when handled |
| Business end-to-end latency | Event accepted | Business result durable | True end-to-end business experience |
| Oldest unresolved backlog age | Oldest unfinished event | Current time | Age of the oldest pending work |
| DLT unresolved age | Oldest DLT/quarantine event waiting | Current time | Risk of breaching recovery windows |

### Event Timestamps Can Be Unreliable

`ConsumerRecord.timestamp()` reflects either `CREATE_TIME` or `LOG_APPEND_TIME` depending on topic, broker, and producer configuration. It does not necessarily match when the business event occurred.

To measure SLA "from order acceptance," carry a trusted `acceptedAt` timestamp from the business boundary and preserve it across retries and DLTs. Using the Kafka record timestamp from a retry topic **resets event age** every time the record is republished.

Additionally, producer and consumer clocks can drift. Standardize on UTC with NTP and define how negative durations from clock skew are handled rather than silently clamping invalid timestamps to "0 latency."

## 9. Recommended Dashboard Metric Contract

To keep PromQL examples consistent, this lesson defines an **illustrative metric contract**. These metrics exist only if your application or exporter emits those exact names and labels:

| Illustrative Prometheus Metric | Type | Key Labels | Source |
| --- | --- | --- | --- |
| `app_kafka_listener_records_total` | Counter | `service`, `listener`, `result` | Application instrumentation |
| `app_kafka_listener_processing_seconds_bucket` | Histogram | `service`, `listener`, `le` | Micrometer Timer configured with histogram |
| `app_kafka_business_events_total` | Counter | `service`, `flow`, `outcome` | Business completion ledger/instrumentation |
| `app_kafka_retry_attempts_total` | Counter | `service`, `listener`, `reason` | Error handler / retry instrumentation |
| `app_kafka_dlt_published_total` | Counter | `service`, `source_topic`, `result` | DLT producer callback / recoverer |
| `app_kafka_dlt_unresolved_records` | Gauge | `service`, `dlt_topic` | Quarantine / DLT audit system |
| `app_kafka_dlt_oldest_unresolved_age_seconds` | Gauge | `service`, `dlt_topic` | Recovery state store |
| `app_kafka_consumer_group_lag_records` | Gauge | `cluster`, `consumer_group`, `topic`, `partition` | Kafka exporter / group offsets |
| `app_kafka_producer_sends_total` | Counter | `service`, `result`, `destination` | Producer instrumentation |
| `app_kafka_transaction_outcomes_total` | Counter | `service`, `outcome` | Transaction lifecycle instrumentation |
| `app_kafka_last_business_success_timestamp_seconds` | Gauge | `service`, `flow` | Application durable success checkpoint |
| `app_kafka_event_to_completion_seconds_bucket` | Histogram | `service`, `flow`, `le` | End-to-end business instrumentation |

Do not reimplement metrics as custom meters if Micrometer or an exporter already provides them. **Inventory existing metrics first**, then standardize names, definitions, and units to avoid double-counting.

### Metric Labels and Units Must Be Consistent

- Counters increase monotonically per attempt or event; never reset mid-run except on process restarts, which `rate`/`increase` handle.
- Gauges move up and down, fitting backlog sizes and last-success timestamps.
- Histogram buckets measure seconds for latency—never mix milliseconds and seconds in the same metric.
- `topic`, `service`, `listener`, and `cluster` are useful filter dimensions, though total cardinality must be bounded.
- Never put `eventId`, `orderId`, `correlationId`, `offset`, stack traces, or exception messages into labels; their cardinality is unbounded.

## 10. What Metrics Does Spring Kafka Provide Out of the Box?

Spring Kafka and Kafka clients emit many signals via Micrometer, Observation, and Kafka client metrics; brokers expose JMX metrics. However, **final Prometheus names vary across versions, binders, exporters, and naming conventions**.

By layer:

| Source | Observable Signals | Not Provided Automatically |
| --- | --- | --- |
| Spring Kafka listener metrics/Observation | Listener invocation duration, result, configured tags | Unique business completion SLO |
| Spring Kafka template metrics/Observation | Send/template operation duration | End-to-end business flow commit |
| Kafka producer metrics | Record send rate, error/retry rates, request latency, buffer wait | Business orders persisted in DB |
| Kafka consumer metrics | Consume rate, poll/fetch, client lag, rebalances | Full cluster-wide consumer group backlog without a committed-offset exporter |
| Kafka broker JMX | Request throughput, ISR, under-replicated partitions, controller, disk | Business-layer message outcomes |
| Consumer group exporter | Committed group offsets and log-end offsets/lag | Handler failures or DLT recovery |
| Application custom instrumentation | Retry/DLT decisions, business completion, idempotency conflicts | Infrastructure health unless integrated with exporters |

In Spring Kafka 3.x, built-in Micrometer metrics appear as names like `spring.kafka.listener` or `spring.kafka.template`, exported to Prometheus with underscores and time suffixes. **Inspect `/actuator/metrics` or `/actuator/prometheus` on your actual deployed build** instead of copying metric names from the web and mistaking "No data" for an inactive system.

All PromQL examples below follow **the custom metric contract from section 9** rather than tying to one specific Kafka exporter's naming.

## 11. Enabling Actuator and the Prometheus Endpoint

### 11.1. Dependencies

Example `pom.xml` with Spring Boot dependency management:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-kafka</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
    </dependency>
</dependencies>
```

In standard Spring Boot projects, Spring Kafka is commonly brought in via `org.springframework.kafka:spring-kafka`, as not every Boot release includes a `spring-boot-starter-kafka` artifact. If your build lacks that starter, use the official dependency:

```xml
<dependency>
    <groupId>org.springframework.kafka</groupId>
    <artifactId>spring-kafka</artifactId>
</dependency>
```

For Spring Boot 3.x and Spring Kafka 3.x, **`spring-kafka`** is the safe official dependency managed by Boot's BOM. In real projects, keep whichever dependency your build supports rather than listing both a nonexistent starter and its replacement. The `pom.xml` snippet above simply illustrates needing Kafka + Actuator + Prometheus.

### 11.2. `application.yml`

```yaml
spring:
  application:
    name: orders-consumer
  kafka:
    bootstrap-servers: kafka-1:9092,kafka-2:9092,kafka-3:9092
    consumer:
      group-id: order-processors
      auto-offset-reset: earliest

management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
  endpoint:
    health:
      probes:
        enabled: true

logging:
  level:
    org.springframework.kafka: INFO
```

Boot Actuator exposes `/actuator/prometheus` when the registry and endpoints are configured. In Kubernetes production:

- Expose metrics endpoints only on internal networks or a restricted management port.
- Never expose all actuator endpoints to the public Internet.
- Enforce NetworkPolicies, auth/TLS, or a metrics sidecar per platform standards.
- Never place secrets inside metric tags or custom metric names.

### 11.3. Example Prometheus Scrape Config

```yaml
scrape_configs:
  - job_name: spring-kafka-orders
    metrics_path: /actuator/prometheus
    scrape_interval: 15s
    static_configs:
      - targets:
          - orders-consumer-1:8080
          - orders-consumer-2:8080
```

This illustrates fixed hostnames; Kubernetes typically uses `ServiceMonitor`/`PodMonitor` or service discovery instead of hardcoding pod IPs. When aggregating across replicas, use `sum by (...)` or `max by (...)` matching each metric's semantics—never sum gauges that an exporter already reports redundantly across pods.

## 12. Combining Observation with Custom Business Metrics

Spring Kafka 3.x supports Micrometer Observation on listeners and templates when enabled on the container or template. Example listener factory configuration:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;

@Configuration
public class KafkaObservationConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, String>
    kafkaListenerContainerFactory(
            ConsumerFactory<String, String> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, String>();
        factory.setConsumerFactory(consumerFactory);
        factory.getContainerProperties().setObservationEnabled(true);
        return factory;
    }
}
```

This matches Spring Kafka 3.x APIs; if Spring Boot auto-configures the container factory or your project defines multiple factories, verify which bean `@KafkaListener` actually uses. Other Boot/Kafka versions may provide properties to enable Observation; avoid registering duplicate metric streams unintentionally.

To enable Observation on a template:

```java
KafkaTemplate<String, String> template =
        new KafkaTemplate<>(producerFactory);
template.setObservationEnabled(true);
```

`producerFactory` above is an application-configured bean. Observation captures framework timing and tracing, whereas reliability dashboards still need application-defined **business outcomes, retries, DLTs, and freshness**.

### Why Are Custom Metrics Needed?

The framework sees when a listener method returns, yet it has no idea whether "the order was paid," "the invoice was emitted downstream," "the DLT record was repaired," or "a customer received duplicate payments." Only the business layer knows those boundaries.

## 13. Instrumenting Spring Listeners with Micrometer

Example helper measuring listener **attempts**—never treat it as unique business events:

```java
package com.example.orders.metrics;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.time.Duration;
import org.springframework.stereotype.Component;

@Component
public class OrderListenerMetrics {

    private final Counter success;
    private final Counter failure;
    private final Timer duration;

    public OrderListenerMetrics(MeterRegistry registry) {
        this.success = Counter.builder("app.kafka.listener.records")
                .description("Handler attempts that completed normally")
                .tag("service", "orders-consumer")
                .tag("listener", "orderCreated")
                .tag("result", "success")
                .register(registry);

        this.failure = Counter.builder("app.kafka.listener.records")
                .description("Handler attempts that threw an exception")
                .tag("service", "orders-consumer")
                .tag("listener", "orderCreated")
                .tag("result", "failure")
                .register(registry);

        this.duration =
                Timer.builder("app.kafka.listener.processing")
                        .description("Handler attempt duration")
                        .tag("service", "orders-consumer")
                        .tag("listener", "orderCreated")
                        .publishPercentileHistogram()
                        .register(registry);
    }

    public void recordSuccess(Duration elapsed) {
        success.increment();
        duration.record(elapsed);
    }

    public void recordFailure(Duration elapsed) {
        failure.increment();
        duration.record(elapsed);
    }
}
```

Listener using the helper:

```java
import java.time.Duration;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    private final OrderService orderService;
    private final OrderListenerMetrics metrics;

    public OrderListener(
            OrderService orderService,
            OrderListenerMetrics metrics) {
        this.orderService = orderService;
        this.metrics = metrics;
    }

    @KafkaListener(
            id = "orderCreated",
            topics = "orders.created",
            groupId = "order-processors")
    public void onOrder(ConsumerRecord<String, String> record) {

        long start = System.nanoTime();
        try {
            orderService.process(record.key(), record.value());
            metrics.recordSuccess(
                    Duration.ofNanos(System.nanoTime() - start));
        } catch (RuntimeException ex) {
            metrics.recordFailure(
                    Duration.ofNanos(System.nanoTime() - start));
            throw ex;
        }
    }
}
```

`OrderService` is an application-defined business service responsible for side effects and idempotency under your transaction strategy.

**Limitations of this measurement:**

- `success` means **the `orderService.process` method returned normally**.
- It does not prove the consumer offset committed or a distributed business flow committed.
- When the listener retries, each attempt increments a counter. This is an *attempt-level* metric, not a unique-event SLO.
- If an `Error` is thrown or a failure happens after the callback returns (e.g., during transaction commit), this listener metric will miss the failure.
- If Micrometer Observation is also enabled, another framework timer exists; dashboards must distinguish sources and never sum duplicate counters or timers.

Measuring duration with `System.nanoTime()` avoids wall-clock jumps. Still, event-to-completion latency requires business timestamps and durable outcome timestamps.

## 14. Custom Metrics for Business Outcomes

Suppose business completion is persisted in a table:

```sql
CREATE TABLE order_processing_result (
    event_id       VARCHAR(100) PRIMARY KEY,
    order_id       VARCHAR(100) NOT NULL,
    status         VARCHAR(30) NOT NULL,
    accepted_at    TIMESTAMP NOT NULL,
    completed_at   TIMESTAMP,
    last_error     VARCHAR(100)
);
```

Reprocessed events share the same `event_id`. The primary key prevents writing multiple completion rows for one event. The app updates states:

```text
ACCEPTED -> PROCESSING -> COMPLETED
                       \-> RETRYING
                       \-> QUARANTINED
```

**Design the ledger around business rules.** Never treat routing to a DLT as completed success; a DLT entry is a *recoverable failure* that can still breach an order's completion SLO.

### Atomicity Note Between Metrics and the Database

Suppose the DB commits and the process crashes **before incrementing the counter**. Prometheus misses the increment even though the business event succeeded. Conversely, incrementing before commit can count rolled-back transactions.

Therefore:

- Micrometer counters fit **health and operational trends**.
- High-precision SLOs should be computed from **durable records** or reconciled ledgers.
- If using counters to approximate SLOs, document drift and double-counting risks.
- Incrementing metrics after commit reduces risk, yet never creates an atomic transaction between the TSDB and database.

### Designing Business Outcome Metrics

```text
app_kafka_business_events_total{flow="orderImport", outcome="completed"}
app_kafka_business_events_total{flow="orderImport", outcome="quarantined"}
app_kafka_business_events_total{flow="orderImport", outcome="expired"}
app_kafka_last_business_success_timestamp_seconds{flow="orderImport"}
```

When an event moves `RETRYING -> COMPLETED`, decide whether counters track **state transitions** or **final outcomes**—never sum transitions into unique event counts. For exact SLOs, query ledger state snapshots.

## 15. Producer Instrumentation

For producers, monitor:

- Whether sends succeeded or failed at the Kafka send future level.
- Latency from send invocation until future completion.
- Kafka client error/retry rates and pre-network serialization failures.
- Transaction commits/aborts and producer fencing when using Kafka transactions.
- Outbox pending size and age when using an outbox publisher.

Example recording send outcomes via Spring Kafka 3.x `CompletableFuture`:

```java
import io.micrometer.core.instrument.MeterRegistry;
import java.util.concurrent.CompletableFuture;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

@Service
public class InstrumentedOrderPublisher {

    private final KafkaTemplate<String, String> template;
    private final MeterRegistry registry;

    public InstrumentedOrderPublisher(
            KafkaTemplate<String, String> template,
            MeterRegistry registry) {
        this.template = template;
        this.registry = registry;
    }

    public CompletableFuture<SendResult<String, String>>
    publish(String orderId, String jsonPayload) {

        long start = System.nanoTime();

        CompletableFuture<SendResult<String, String>> future =
                template.send("orders.created", orderId, jsonPayload);

        future.whenComplete((result, exception) -> {
            String outcome = exception == null ? "success" : "failure";
            registry.counter(
                    "app.kafka.producer.sends",
                    "service", "orders-producer",
                    "destination", "orders.created",
                    "result", outcome).increment();

            registry.timer(
                    "app.kafka.producer.send.duration",
                    "service", "orders-producer",
                    "destination", "orders.created")
                    .record(System.nanoTime() - start,
                            java.util.concurrent.TimeUnit.NANOSECONDS);
        });
        return future;
    }
}
```

This assumes `template` and topics are configured. Never put exception messages into metric labels; if error categories are needed, map exceptions to a bounded enum such as `SERIALIZATION`, `TIMEOUT`, `AUTHORIZATION`, or `BROKER`.

**For Kafka transactions:** a completed send future does not prove the overall transaction **committed**. Emit transaction outcome metrics at the transaction boundary while maintaining external idempotency for databases and APIs. Never treat `ProducerFencedException` as a transient network error: close and replace fenced producers per lifecycle rules.

## 16. Retries and DLT: Recoverability Signals

Spring Kafka supports multiple error-handling mechanisms:

- Blocking retries with `DefaultErrorHandler` and `BackOff`.
- Non-blocking retry topics with `@RetryableTopic` / retry-topic infrastructure where appropriate.
- `DeadLetterPublishingRecoverer` and DLTs.
- Recovery jobs or replay tools to fix and re-drive records.

Dashboards must distinguish:

```text
attempt failure
     |
     +-- retry -> eventual success
     |
     +-- retries exhausted -> published to DLT
                                |
                                +-- waiting investigation
                                +-- re-drive success
                                +-- permanent rejection
```

### Essential Recovery Metrics

| Signal | Core Definition | Notes |
| --- | --- | --- |
| Retry attempts | Total retry executions | One event can contribute multiple attempts |
| Retried event count | Distinct events that retried at least once | Requires `eventId` or audit store |
| Retry exhaustion | Events exhausting retry budget | Does not automatically confirm DLT publish succeeded |
| DLT publish success | Records broker-ACKed on the DLT | Does not mean the underlying error is fixed |
| DLT publish failure | System failed to persist failed record to DLT | High risk of lost visibility or stalled offsets |
| Unresolved DLT backlog | Events still awaiting resolution | Requires a state store or tracking table |
| Oldest unresolved DLT age | Age of the oldest pending DLT case | Measures recoverability SLO |
| Re-drive outcome | Replay success/failure | Must prevent duplicate side effects |

If a system has a DLT topic with no consumer group reading it, **Kafka consumer lag on the DLT is meaningless**. Measuring unresolved DLT backlogs requires an audit/quarantine workflow tracking investigated, fixed, and re-driven statuses.

### Never Count DLT Offset Deltas and Call Them "Unresolved"

The record count stored in a DLT topic reflects **all published records within retention**, not whether they were re-driven. A record can be replayed successfully while remaining on the DLT until retention expires. Thus broker DLT size differs from unresolved business cases.

## 17. Rebalances, Listener Liveness, and Assignments

A consumer group can be unhealthy even when processes report `UP`:

- Consumers hold zero assigned partitions.
- Continuous rebalances interrupt processing.
- `max.poll.interval.ms` expires due to slow handlers.
- Consumers are paused by error handlers or backoff policies.
- Listener threads hang on downstream dependencies.
- Containers are stopped or failing authentication.

Signals to observe:

```text
assigned_partitions_count
consumer_poll_frequency
poll_idle_time
rebalance_count / rebalance_rate
last_successful_business_event_time
listener_container_running
consumer_group_lag
```

Not all of these exist verbatim out of the box; pull some from Kafka client metrics and Spring Kafka container events, and instrument custom metrics for the rest.

### When Is `assignment = 0` an Error?

A consumer instance holding zero partitions **can be completely normal** if replica count exceeds partition count. Never alert per pod on `assigned_partitions=0`. Alert when:

- The entire consumer group makes zero progress while **work is expected**.
- Positive lag persists alongside zero processing progress.
- A rebalance storm visibly degrades throughput.

Tie metrics to the **consumer group and workload**, not merely one pod's state.

## 18. Infrastructure Panels: Brokers and Clients

Application reliability cannot be separated from Kafka infrastructure. At minimum, pull data from Kafka broker exporters/JMX or platform teams:

| Group | Signals | Analysis |
| --- | --- | --- |
| Broker health | Broker up, active controller / metadata quorum health | Have cluster nodes dropped out? |
| Replication | Under-replicated/offline partitions, ISR shrink | Durability risk or rejected produces |
| Request serving | Produce/fetch request latency, errors, request queues | Are brokers serving slowly? |
| Storage/network | Disk utilization, I/O, throughput, page cache | Saturation or disk-full risk |
| Producer client | Send errors/retries, record size, buffer pool waits | Is bottleneck client-side or broker-side? |
| Consumer client | Fetch rate/latency, poll activity, rebalances | Falling behind source or coordinator churn? |
| Security | Auth/authorization failures | SASL/ACL/cert misconfig or expired creds |
| Transactions | Aborts/fences, transaction coordinator pressure | Exactly-once / transaction lifecycle issues |

**How to gather names:** JMX MBean names and metrics exposed by JMX Exporter vary by exporter config and Kafka version. Never hardcode metric names in operational docs without checking live endpoints. If the Kafka platform team maintains a cluster dashboard, link directly from your broker health panel to theirs.

## 19. How Should the Dashboard Be Laid Out?

A single large-screen dashboard can be organized into five rows:

```text
┌───────────────────────────────────────────────────────────────┐
│ FILTERS: env | cluster | service | group | topic | version     │
├───────────────────────────────────────────────────────────────┤
│ SLO 30d        Last success     Lag total      Oldest DLT     │
│ 99.93%         28 sec ago       2,400 records  12 min        │
├───────────────────────────────────────────────────────────────┤
│ Incoming rate (records/s)  | Processing success rate (records/s)│
│ Total lag by group/topic   | Max partition lag                 │
├───────────────────────────────────────────────────────────────┤
│ p95/p99 processing        | Event-to-completion age p95/p99    │
│ Failure/retry rate        | DLT publish + unresolved backlog   │
├───────────────────────────────────────────────────────────────┤
│ Producer send errors      | Consumer rebalance / assignments  │
│ Transaction abort/fence   | Broker health / under-replication  │
├───────────────────────────────────────────────────────────────┤
│ Deploy / incident annotation | Logs/traces/runbooks            │
└───────────────────────────────────────────────────────────────┘
```

Sample values in this wireframe are **not real system measurements**.

### Row 1 — Overall Status

Displays:

- 30-day SLO compliance with clear numerator/denominator sources.
- Time since last **durable business success**.
- Total consumer group lag and max partition lag.
- Unresolved DLT case count and oldest age.

This gives on-call engineers a 10-second answer on whether the pipeline meets its commitments.

### Row 2 — Traffic and Progress

Place incoming rate beside processing rate. If input is 2,000 records/s and processing is 1,000 records/s, lag will grow unless another consumer or special offset semantics apply. If both drop to 0, check whether traffic naturally subsided, upstream broke, or telemetry stalled.

### Row 3 — Latency and Failures

Show p95/p99 processing duration histograms separately from event-to-completion age. Add retry attempts, listener exceptions, and DLT outcomes. High DLT publishing paired with shrinking unresolved counts suggests recovery is working; climbing unresolved DLT counts demand action.

### Row 4 — Capacity and Infrastructure

Pair producer errors, Kafka client rebalances, assigned partitions, and broker request latency/ISR with CPU/memory charts to separate application bugs from infrastructure saturation.

### Row 5 — Deployment Context

Add annotations whenever:

- A new application version deploys.
- Replicas or concurrency scale.
- Consumer group settings change.
- Retry or DLT policies change.
- Brokers upgrade or partitions reassign.

Reliability incidents frequently follow changes. Annotations help correlate quickly, though **temporal correlation alone does not prove causation**.

## 20. PromQL: Listener Throughput

Suppose the application exports:

```text
app_kafka_listener_records_total{
  service="orders-consumer",
  listener="orderCreated",
  result="success"
}
```

Successful handler attempts rate over 5 minutes:

```promql
sum by (service, listener) (
  rate(app_kafka_listener_records_total{result="success"}[5m])
)
```

Failed handler attempts rate:

```promql
sum by (service, listener) (
  rate(app_kafka_listener_records_total{result="failure"}[5m])
)
```

Total attempts:

```promql
sum by (service, listener) (
  rate(app_kafka_listener_records_total[5m])
)
```

These queries **aggregate across replicas** via `sum by`. For multi-instance listeners, never pick a single pod's series to infer service-wide throughput.

**Limitation:** an event retried three times contributes three attempts to this counter. For **unique completed business events**, query the separate `app_kafka_business_events_total` metric/ledger.

## 21. PromQL: Error Rate and Handling Sparse Data

Handler failed attempt ratio:

```promql
sum by (service, listener) (
  rate(app_kafka_listener_records_total{result="failure"}[5m])
)
/
clamp_min(
  sum by (service, listener) (
    rate(app_kafka_listener_records_total[5m])
  ),
  0.000001
)
```

This yields a ratio, e.g., `0.05` for 5%. At low traffic, one failure spikes the ratio sharply. Combine alerts with **minimum traffic**, **duration**, and business impact:

```promql
(
  sum by (service, listener) (
    rate(app_kafka_listener_records_total{result="failure"}[10m])
  )
  /
  clamp_min(
    sum by (service, listener) (
      rate(app_kafka_listener_records_total[10m])
    ),
    0.000001
  )
) > 0.05
and on(service, listener)
sum by (service, listener) (
  increase(app_kafka_listener_records_total[10m])
) > 100
```

This is a reference guard; neither 5% nor 100 attempts fits every workload. A low-volume topic carrying critical financial events may need an immediate alert on **a single unrecoverable failure**.

### Never Turn "No Data" Into "OK"

When processes die or Prometheus fails to scrape, rates disappear. If dashboards display "0 errors" when **time series are absent**, on-call gets misled. Monitor scrape `up` and alert on missing metrics separately.

## 22. PromQL: Group-Wide Lag and Hot Partitions

Suppose the exporter emits:

```text
app_kafka_consumer_group_lag_records{
  cluster="kafka-prod-a",
  consumer_group="order-processors",
  topic="orders.created",
  partition="0"
}
```

Total lag:

```promql
sum by (cluster, consumer_group, topic) (
  app_kafka_consumer_group_lag_records
)
```

Highest lagging partition:

```promql
max by (cluster, consumer_group, topic) (
  app_kafka_consumer_group_lag_records
)
```

Top partitions to investigate:

```promql
topk(10, app_kafka_consumer_group_lag_records)
```

**Important:** the metric must emit **one unique series per partition/group/topic/cluster**, or queries must deduplicate if multiple exporters scrape the same cluster. Summing duplicated series across `instance` labels overcounts backlogs.

### Does Rising Lag Always Mean the Consumer Is Failing?

Not necessarily. Lag rises due to:

- Sudden upstream traffic spikes.
- Consumer throughput below producer rate requiring capacity.
- One partition receiving more records than peers.
- Slow message processing from a degraded database.
- Continuous consumer group rebalances.
- Paused consumers or blocked error handlers.
- Stale/delayed group offset metadata.

Read **ingress rate, processing rate, max partition lag, and error rate together** before blindly adding replicas.

## 23. PromQL: p95 / p99 Processing Duration

When the `Timer` in section 13 enables `publishPercentileHistogram()` and Prometheus scrapes:

```text
app_kafka_listener_processing_seconds_bucket{le="0.1",...}
app_kafka_listener_processing_seconds_count{...}
app_kafka_listener_processing_seconds_sum{...}
```

p95:

```promql
histogram_quantile(
  0.95,
  sum by (le, service, listener) (
    rate(app_kafka_listener_processing_seconds_bucket[5m])
  )
)
```

p99:

```promql
histogram_quantile(
  0.99,
  sum by (le, service, listener) (
    rate(app_kafka_listener_processing_seconds_bucket[5m])
  )
)
```

If only `_count` and `_sum` exist **without buckets**, `histogram_quantile` returns nothing. Enable histograms via Micrometer config or code and verify exported metrics.

### Why Can't You Add Pod p95 Values Together?

Percentiles **are not additive**. Pod A's p95 plus Pod B's p95 is not the service-wide p95. For classic histograms, sum bucket counts with `sum by (le, ...)` first, then compute quantiles. With native histograms or trace backends, aggregation syntax varies by datasource.

### Bucket Boundaries Affect Accuracy

If SLAs require completion under 5 seconds, choose fine-grained buckets around 0.1 s, 0.5 s, 1 s, 2 s, 5 s, and 10 s. Histograms create one series per bucket × label combination, so balance resolution against storage budget.

## 24. PromQL: Retries, DLT, and Unrecovered Age

Total retries over 5 minutes:

```promql
sum by (service, listener, reason) (
  rate(app_kafka_retry_attempts_total[5m])
)
```

Successful DLT publishes in 15 minutes:

```promql
sum by (service, source_topic) (
  increase(app_kafka_dlt_published_total{result="success"}[15m])
)
```

Current unresolved DLT count:

```promql
sum by (service, dlt_topic) (
  app_kafka_dlt_unresolved_records
)
```

Oldest unresolved age:

```promql
max by (service, dlt_topic) (
  app_kafka_dlt_oldest_unresolved_age_seconds
)
```

**Warning on DLT gauges:** the application must explicitly track whether a DLT case is resolved or unresolved. Without a recovery store, never publish an "unresolved" gauge simply by counting raw Kafka records sitting in the DLT topic.

### Detecting a Stalled Pipeline

If the app maintains `app_kafka_last_business_success_timestamp_seconds` as Unix epoch seconds:

```promql
time() - max by (service, flow) (
  app_kafka_last_business_success_timestamp_seconds
)
```

This returns seconds elapsed since the last durable success, ideal for continuous streams. For nightly batch workloads, do not fire "no progress in 10 minutes" 24/7; compare against expected schedules or input activity.

If the series is missing (app processed nothing yet or scrape failed), `time() - gauge` produces no output. Pair it with no-data rules and scrape health checks.

## 25. PromQL: Business-Layer Event-to-Completion SLI

Suppose the application exports a histogram **for completed events**:

```promql
histogram_quantile(
  0.99,
  sum by (le, service, flow) (
    rate(app_kafka_event_to_completion_seconds_bucket[10m])
  )
)
```

This measures p99 latency **only across completed events**, so stalled events that never finish stay invisible. If the whole pipeline hangs, the histogram stops recording samples and p99 stops rising while users wait.

To truly measure a "99.9% within 5 minutes" SLO:

1. Track eligible events and their SLA start timestamps.
2. Track durable outcomes per unique event ID.
3. Identify events already past the deadline without completing.
4. Apply documented contract exclusions/adjustments.
5. Compute numerator/denominator over sufficiently aged windows.

A completion-only histogram supports a chart of "duration of finished events," **never replacing a ledger-based timely completion ratio**.

### Error Budget

For a 99.9% 30-day SLO, the allowed bad-event ratio is `0.001`. Error budget burn compares **bad eligible events** divided by total eligible events in the window against `0.001`:

\[
\text{BudgetUsedFraction}
=\frac{\text{BadEligibleEvents}/\text{EligibleEvents}}{0.001}
\]

`BudgetUsedFraction = 0.4` means 40% of the window's error budget is consumed. At low volumes, handle small sample sizes and critical single events carefully, and guard against dividing by zero.

## 26. Alert Design: From Panels to Action

Panels merely visualize issues; alerts must trigger **clear, actionable responses**. Every alert should include:

- User/business impact description.
- Owner and severity.
- Condition and evaluation duration.
- Dashboard link pre-filtered to service/group/topic.
- Runbook link.
- Guidance distinguishing missing telemetry from real incidents.
- Clear resolution / auto-resolve conditions.

### Core Alerts

| Alert | Suggested Condition | First Response |
| --- | --- | --- |
| **Business SLO burn** | Error budget burning rapidly over short/long windows | Identify overdue events; halt rollouts if correlated |
| **Consumer lag sustained** | Lag stays above threshold for minutes without draining | Compare ingress vs. throughput and partition skew |
| **No processing progress** | Positive lag with near-zero success throughput | Inspect listener container, errors, rebalances, dependencies |
| **DLT publish failures** | Failed attempts writing to DLT | High priority because failure evidence is at risk |
| **DLT unresolved age breach** | Unresolved cases past handling deadline | Open incident / quarantine triage workflow |
| **Producer error spike** | Send failures rising under sufficient traffic | Check auth, brokers, serialization, timeouts |
| **Transaction fencing** | Unexpected `ProducerFencedException` | Inspect `transactionIdPrefix` per instance |
| **Broker replication risk** | Persistent under-replicated or offline partitions | Escalate to Kafka platform team |
| **Telemetry missing** | Scrape target down or metrics absent | Verify app/metrics endpoint before assuming healthy |

Never send a Slack alert for every transient retry; that guarantees alert fatigue. Start with **SLO impact, unrecovering backlogs, and broken recovery paths**, using other signals for diagnosis.

## 27. Example Prometheus Alert Rules

Assuming the custom metrics from section 9 exist, an illustrative rule group:

```yaml
groups:
  - name: spring-kafka-orders-reliability
    rules:
      - alert: KafkaConsumerLagSustained
        expr: |
          sum by (cluster, consumer_group, topic) (
            app_kafka_consumer_group_lag_records
          ) > 10000
        for: 15m
        labels:
          severity: warning
        annotations:
          summary: "Kafka consumer lag sustained"
          description: "Review ingress, processing rate and partition skew."

      - alert: KafkaDltPublishFailure
        expr: |
          sum by (service, source_topic) (
            increase(app_kafka_dlt_published_total{result="failure"}[10m])
          ) > 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Failed record could not be published to DLT"

      - alert: KafkaBusinessNoProgress
        expr: |
          time() - max by (service, flow) (
            app_kafka_last_business_success_timestamp_seconds
          ) > 600
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "No durable business completion in 10 minutes"
```

**Not production-ready as-is:** thresholds like 10,000 records, 10 minutes, and 15 minutes are illustrative only. Tune them to peak traffic, deadlines, source rates, partition counts, and severity.

`KafkaBusinessNoProgress` does not fit scheduled sparse workloads or planned pauses. In production, pair it with expected schedule checks and no-data alerts. For DLT publish failures, ensure the metric increments specifically on **failed DLT publish attempts**, never on handler errors prior to attempting DLT routing.

### Severity by Impact

- **Critical:** business events missing deadlines, DLT unable to persist errors, offline partitions threatening data, or transactional pipelines unable to commit.
- **Warning:** rising backlogs still within error budget, elevated retries, DLT items needing triage, or emerging skew.
- **Info:** deployments, single rebalances, or brief spikes without SLO impact.

Assign severity by *impact + urgency*, never purely by CPU usage or raw counter magnitude.

## 28. Separating Retry Effects from Duplicate Data

Spring Kafka can invoke a listener multiple times for the same record after exceptions or rollbacks. Kafka transactions make Kafka-to-Kafka flows atomic within scope, yet **do not prevent duplicate side effects in external databases or APIs**.

Example:

```text
Consumer reads order.created event E-1001
  -> billing API call succeeds
  -> consumer transaction rolls back before offset commit
Consumer rereads E-1001
  -> billing API called again
```

The "listener attempts" metric increments twice while business event `E-1001` must count once if idempotency works.

Add these dashboard metrics:

```text
app_kafka_idempotency_conflicts_total
app_kafka_duplicate_events_suppressed_total
app_kafka_business_events_total{outcome="completed"}
app_kafka_business_events_total{outcome="rejected"}
```

These are application-designed metrics. **Do not automatically treat high `duplicate_events_suppressed` counts as failures:** if producer retries or upstream at-least-once resends are normal under contract, suppressions are healthy. What matters is preventing duplicate business side effects and wrong unique completions.

## 29. Runbook: Continuously Rising Lag

### Symptoms

```text
consumer_group=order-processors
lag total: 2,000 -> 10,000 -> 40,000
incoming rate: 1,500/s
processing success: 700/s
listener error rate: 0.1%
```

These are illustrative numbers.

### Diagnosis

1. Check whether input rate spiked or processing rate dropped first.
2. Check max partition lag: one "hot" partition or all partitions slow?
3. Check listener p95/p99 duration; if elevated, check dependencies, DB pools, API rate limits.
4. Check consumer assignments and rebalances; any churn or idle consumers?
5. Check CPU/heap/GC and thread concurrency.
6. Check broker fetch latency, under-replicated partitions, and network health.
7. Check recent deployments or traffic events.

### Actions

- If valid traffic spiked and consumers are healthy: scale **within partition count** and downstream capacity.
- If one partition is hot: adding replicas **cannot help that partition**; inspect key distribution and partitioning.
- If DB slows processing: fix queries, indexes, or pools, or shed load—adding consumers can overload the DB further.
- If rebalances loop: inspect poll intervals, listener duration, and group membership.
- If a poison pill stalls progress: fix retry/DLT handling rather than skipping all exceptions to zero out lag.

Never seek offsets to end just to "fix lag" without explicit business approval to drop data; that causes silent business data loss.

## 30. Runbook: Lag Near Zero Yet Orders Still Delayed

### Symptoms

```text
consumer lag: near 0
listener success: high
business completion: dropping
end-to-end p99: 12 minutes (SLO 5 minutes)
```

Likely causes:

- Listener only pushes events to an internal queue whose downstream workers are wedged.
- Database accepted calls yet transaction commits stall.
- Outbox publisher falls behind after listener finishes.
- External non-Kafka retry loops are waiting.
- Listener success metric counts handler returns rather than durable business completions.

Actions:

1. Inspect stages after the listener: DB, outbox, external APIs.
2. Query event status in the business ledger, not offsets alone.
3. Measure duration per stage to pinpoint the bottleneck.
4. Reconcile `eventId`s against final outcomes.

This proves why dashboards need business SLAs and cannot rely purely on consumer lag.

## 31. Runbook: Retries and DLT Spiking After Deploy

### Symptoms

```text
Deployment v42 -> v43
handler errors rising
retry attempts rising
DLT published rising
lag fluctuating
```

Check:

- Payload, schema, and header compatibility between existing producers and the new consumer.
- Changes to serializers/deserializers, error handlers, or trusted packages.
- Changes to topics, keys, partitions, timeouts, or transaction boundaries.
- Clusters of validation errors vs. timeouts.
- Records stuck in infinite retries instead of routing to DLT.
- DLT records missing origin headers needed for investigation.

Actions:

1. Correlate deployment annotations with metric inflection points.
2. Group errors using a **bounded** exception class/category tag.
3. If caused by the new release, roll back or halt canary per change policy.
4. Preserve DLT/quarantine records to repair and re-drive; never delete failing data.
5. After fixing, verify unresolved backlogs shrink and unique business outcomes reconcile.

Never treat "DLT publish succeeded" as incident resolution. It only confirms failing events were safely captured for follow-up.

## 32. Runbook: Transaction Aborts or `ProducerFencedException`

For Kafka-to-Kafka transactional pipelines:

```text
transaction abort spike
producer fenced exceptions
consumer retry / listener restarts
throughput decrease
```

Causes to distinguish:

- Multiple replicas/factories sharing `transactionIdPrefix` causing `transactional.id` collisions.
- Legitimate replacement of a stable producer identity where fencing is protective.
- Producer idle/transactional ID expiration or producer cache lifecycle issues.
- Transaction timeouts or unavailable broker/coordinator.
- Slow listener triggering poll timeouts/rebalances and transaction failures.

Dashboards should link to:

- Logs with `instanceId`, `transactionIdPrefix`, exception class, and deployment version.
- Kafka client producer and transaction metrics.
- Listener rebalance, commit, and abort signals.
- Business data audits verifying duplicate prevention.

Never turn off transactions just to silence errors without assessing exactly-once impacts; fencing may be protecting data integrity.

## 33. Capacity Planning and Partition Skew

A consumer group reading 24 partitions cannot parallelize across 100 consumers **in the same group** on that topic with one partition per consumer; 76 consumers sit idle. Useful concurrency is bounded by partition count and topology, and actual throughput still depends on I/O and downstreams.

Capacity dashboards should show:

```text
partition count
assigned partitions per active consumer
max partition lag / median lag
processing records per second per consumer
listener processing p95 and p99
CPU, heap, GC, DB connection pool utilization
downstream requests/sec and error rate
```

### When Adding Replicas Helps

- Unassigned or under-utilized partitions remain.
- Bottlenecks sit in per-instance CPU or listener execution rather than shared DBs/APIs.
- Key distribution is reasonably balanced.
- Rebalance overhead and startup times are acceptable.

### When Adding Replicas Does Not Help

- One hot partition carries most of the traffic.
- DB pools or third-party APIs are already saturated.
- Error handlers are pausing partitions.
- Producer throughput is broker-limited.
- Business work serializes on locks for the same order key.

Showing "total lag" beside "max partition lag" and "throughput per consumer" prevents misguided scaling decisions.

## 34. Cardinality and Metric Storage Cost

Prometheus stores one time series per **unique label combination**. With:

```text
service=10
topic=50
consumer_group=20
partition=24
instance=100
```

Emitting all dimensions simultaneously produces a theoretical ceiling of:

\[
10 \times 50 \times 20 \times 24 \times 100 = 24{,}000{,}000
\]

This represents **the product of maximum cardinalities**, not that every combination exists simultaneously—yet it shows why careless labels explode storage.

### Labels to Allow vs. Forbid

| Data | Metric Label? | Reason |
| --- | --- | --- |
| `service`, `environment`, `cluster` | Yes, bounded set | Filtering and ownership |
| `listenerId`, `topic`, `consumer_group` | Yes, when cardinality is governed | Flow analysis |
| `partition` | Only when drill-down is needed and exporter supports it | Multiplies series counts |
| `result`, `errorCategory` | Yes, bounded enum | Outcome ratios |
| `exceptionClass` | Consider normalized groups, never dynamic strings | Can grow high-cardinality |
| `orderId`, `eventId`, `correlationId` | No | Nearly unique per event |
| `offset`, `message timestamp` | No | Changes every record |
| Full exception message / stacktrace | No | Unbounded and may leak secrets |
| Dynamic UUID-based retry topic names | No if unbounded | Exhausts cardinality budgets |

Store individual event IDs in logs and traces for investigation under strict retention, privacy, and access controls.

## 35. Ownership and Metric Documentation

Every metric and panel needs an explicit contract:

```yaml
metric: app_kafka_listener_records_total
owner: orders-processing
type: counter
unit: attempts
source: Spring Kafka listener application code
labels:
  - service
  - listener
  - result
semantics:
  success: handler returned without RuntimeException
  failure: handler threw RuntimeException
limitations:
  - retries produce multiple attempts
  - does not guarantee offset commit
  - does not represent unique business completion
dashboard_panel: "Listener attempt throughput"
```

This is a **metric documentation example**, not an auto-parsed Micrometer config. Whenever teams change retry logic or adopt non-blocking retries, update semantic docs alongside dashboards.

Establish clear ownership:

- Application team owns handler/business metrics, DLT recovery metrics, and runbooks.
- Kafka platform team owns broker JMX, cluster alerts, and partition/replication health.
- SRE/observability team owns Prometheus/Grafana availability, retention, label budgets, and alert routing.
- Data/business owners define SLOs, eligible event scope, and completion criteria.

## 36. Testing Dashboards Before Go-Live

A dashboard validated only on happy-path traffic cannot be trusted. Test against simulated failures:

| Scenario | Expected Signal | What Dashboard / Runbook Should Do |
| --- | --- | --- |
| Producer doubles send rate | Ingress climbs; lag may climb | Clearly reveals current consumer capacity |
| Consumer stopped for 5 min | Success throughput drops to 0; group lag climbs | No-progress alert fires while source has traffic |
| One hot partition | Max partition lag jumps above peer partitions | Drill-down to partition and key distribution |
| Slow DB | Listener p95/p99 climbs; throughput drops | Links directly to DB dashboard |
| Invalid payload | Processing errors, retries/DLT rise | Groups into proper error category |
| DLT producer permission denied | DLT publish failures | Critical alert; never treated as DLT publish success |
| DLT record re-driven successfully | Unresolved backlog/age drops | Re-drive outcome and audit match |
| Kafka producer transaction fenced | Abort/fence errors | Correlates instance prefix and rollout |
| Frequent group rebalances | Rebalance count climbs; throughput fluctuates | Inspect poll intervals and membership |
| Application pod restarts | Counters reset; scrape targets rotate | `rate` avoids false spikes |
| Metrics endpoint unscrapeable | `up=0` or series absent | No-data alert fires instead of showing 0 as healthy |
| Business completion stalls while listener returns | Business SLO degrades; handler success looks normal | Exposes downstream stall |
| Message retried multiple times | Attempt counter > unique event count | SLO does not miscount unique events |
| Header/schema skew during rolling upgrade | Conversion/DLT errors spike | Canary/rollback per runbook |

### Automated Testing Scenario

With Testcontainers Kafka or `@EmbeddedKafka` (per compatible version), write a producer/consumer test:

1. Publish N records with unique `eventId`s.
2. Force selected records to throw in the listener.
3. Configure retry policy followed by DLT after exhausting attempts.
4. Wait for processing to converge; assert attempt counts differ from unique completed counts.
5. Read Prometheus exposition or `MeterRegistry` in the test to assert metrics emitted.
6. Run re-drive and verify unresolved DLT age/count drops.

To test alert rules, run `promtool test rules` with crafted time-series inputs during QA and deployment verification rather than during initial doc authoring.

## 37. Sample Micrometer Test with `SimpleMeterRegistry`

Metric recording logic can be unit-tested without running a Kafka broker:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.time.Duration;
import org.junit.jupiter.api.Test;

class OrderListenerMetricsTest {

    @Test
    void recordsOneSuccessAndOneFailureAttempt() {
        try (SimpleMeterRegistry registry = new SimpleMeterRegistry()) {
            OrderListenerMetrics metrics =
                    new OrderListenerMetrics(registry);

            metrics.recordSuccess(Duration.ofMillis(50));
            metrics.recordFailure(Duration.ofMillis(100));

            double successes = registry
                    .get("app.kafka.listener.records")
                    .tag("listener", "orderCreated")
                    .tag("result", "success")
                    .counter().count();

            double failures = registry
                    .get("app.kafka.listener.records")
                    .tag("listener", "orderCreated")
                    .tag("result", "failure")
                    .counter().count();

            long durationCount = registry
                    .get("app.kafka.listener.processing")
                    .tag("listener", "orderCreated")
                    .timer().count();

            assertEquals(1.0, successes);
            assertEquals(1.0, failures);
            assertEquals(2, durationCount);
        }
    }
}
```

This verifies **instrumentation**, not that Kafka records committed or Prometheus scraped successfully. End-to-end reliability requires integration tests with a broker, database, and event IDs.

## 38. From Dashboards to On-Call Workflows

An operational dashboard is valuable only when it drives action:

```text
ALERT
  |
  v
Open dashboard filtered to service + group + topic
  |
  v
Check business SLO and active impact
  |
  +-- no traffic expected? -> verify schedule / upstream
  |
  +-- lag growing? -> inspect processing rate and partition skew
  |
  +-- processing failing? -> inspect error categories + retry/DLT
  |
  +-- broker/client failing? -> inspect infrastructure
  |
  v
Follow runbook and apply bounded mitigation
  |
  v
Verify recovery:
    lag decreases
    completion rate recovers
    oldest unresolved age decreases
    error budget burn stabilizes
    no duplicate business effects
  |
  v
Document incident and improve thresholds/tests
```

Never close an incident merely because lag hit `0` if DLT backlogs, missing data, or business completion SLAs remain unrecovered. Conversely, a brief lag spike that drains rapidly without breaching deadlines may not require an incident.

## 39. Practice Lab: Building a Reliability Dashboard

**Exercise 1 — Choose an SLO.** For `orders.created`, define "eligible," "durable completion," a 5-minute deadline, and a 30-day window. Explain why listener success rate does not equal timely completion SLI.

**Exercise 2 — Inventory metrics.** Run Spring Boot Actuator Prometheus in a test environment and list real metrics from Spring Kafka listeners/templates and the Kafka client. Compare against section 9's custom contract, noting sources and units.

**Exercise 3 — Consumer lag.** Add a 4-partition topic to a dashboard plotting total lag and max partition lag. Create a hot partition to observe why both charts belong side by side.

**Exercise 4 — Throughput.** Build records/second panels for producer and consumer. Induce a traffic spike, watch backlogs grow, and identify the equilibrium throughput.

**Exercise 5 — Processing latency.** Enable histograms on Micrometer Timers and plot p95/p99. Inject random database call latency and observe the impact.

**Exercise 6 — Business freshness.** Record `acceptedAt` on events and `completedAt` in a ledger. Measure event-to-completion latency, compare it with listener duration, and design an oldest-unresolved-event metric.

**Exercise 7 — Retries and DLT.** Inject one transient failure and one permanent failure. Build panels distinguishing retry attempts, DLT published, unresolved DLT items, and DLT publish failures.

**Exercise 8 — No-progress alert.** Run a consumer with steady input, then stop the listener. Write a rule combining positive lag + low processing progress, and test behavior during scheduled idle periods.

**Exercise 9 — Broker infrastructure.** Link the application team's dashboard to the broker health/replication dashboard. Document exact escalation criteria to the Kafka platform team.

**Exercise 10 — Transaction fencing.** Run two Spring Kafka instances with colliding `transactionIdPrefix` values in a test environment. Observe fenced producers, aborted transactions, and stalled consumer progress; fix prefixes and watch recovery.

**Exercise 11 — Metric cardinality.** Temporarily add an event ID label in an isolated test environment and observe series explosion. Move event IDs to logs/tracing and keep metric labels bounded.

**Exercise 12 — Canary deployment.** Roll out a controlled handler or schema change. Annotate the version on the dashboard and define rollback thresholds tied to SLOs and error/DLT rates.

**Exercise 13 — DLT re-drive.** Build a DLT case state table with source event IDs, statuses, and timestamps. Display unresolved counts and oldest age on the dashboard; after a successful re-drive, verify gauges drop.

**Exercise 14 — Alert testing.** Write tests for Prometheus recording/alert rules using simulated time series for rising lag, missing metrics, and DLT failures. Verify alerts do not spam during scheduled zero-traffic windows.

**Exercise 15 — Incident drill.** Simulate "consumer lag low yet business completion stopped." Document step-by-step investigation across listener, outbox/DB, and ledger until locating the stalled stage.

## 40. Dashboard Handover Checklist

Before declaring a dashboard production-ready, answer with concrete evidence:

| Question | Required Evidence |
| --- | --- |
| Were SLIs/SLOs defined with business owners? | Document specifying denominators, deadlines, and exclusions |
| Does the dashboard isolate environment and cluster? | Governed filters and metric labels |
| Can you tell if listeners are still processing? | Throughput, last success, lag, and scrape status |
| Is committed-offset lag distinguished from fetch lag? | Documentation of the lag exporter datasource |
| Can you tell whether DLT records were resolved? | Recovery/audit state, not just Kafka topic size |
| Do histograms have matching buckets? | Prometheus exposition and p95/p99 panels |
| Are error/attempt counts kept distinct from unique events? | Explicit metric contracts |
| Do alerts have owners and runbooks? | Links and routing in alert annotations |
| Are no-data alerts configured? | Scrape `up`/absent tests |
| Was the dashboard tested under failures? | Failure-injection results and incident drills |
| Do migrations verify metric names and labels? | Version-aware compatibility tests |
| Are high-cardinality labels and secrets avoided? | Label inventory and retention policies |

This checklist is meant for teams to apply in real operational workflows; at the STEP 4 documentation stage, there is no requirement to run Kafka, Prometheus, Gradle, or evaluate lesson content.

## 41. Conclusion

A reliability dashboard for Spring Kafka must answer **whether business data arrives on time and recovers safely**, rather than merely showing the Kafka cluster is up.

An effective design combines:

- **Business SLOs/SLIs** anchored on explicit event IDs and durable outcomes.
- **Producer and consumer telemetry** covering traffic, progress, errors, transactions, and rebalances.
- **Lag + freshness + latency** with exact semantics—never carelessly converting "records behind" into "seconds late."
- **Retry/DLT/recovery metrics** showing whether failed data is actually resolved rather than forgotten in a DLT.
- **Broker and downstream health** to locate bottlenecks at the right layer.
- **PromQL, Grafana, alerts, runbooks, and failure tests** turning telemetry into operational action.

With all these layers connected, dashboards not only show that a consumer is slow, but answer **who is affected, since when, how much error budget remains, where to fix it, and how to prove full recovery**.

### References

- [Spring Kafka Reference — Micrometer Observations and Metrics](https://docs.spring.io/spring-kafka/reference/kafka/micrometer.html)
- [Spring Kafka Reference — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)
- [Spring Kafka Reference — Non-blocking Retries](https://docs.spring.io/spring-kafka/reference/retrytopic.html)
- [Spring Kafka Reference — Kafka Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html)
- [Spring Boot Reference — Metrics and Actuator](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Micrometer Reference — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Prometheus — Query Functions](https://prometheus.io/docs/prometheus/latest/querying/functions/)
- [Prometheus — Alerting Rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/)
- [Apache Kafka — Monitoring](https://kafka.apache.org/documentation/#monitoring)
- [Grafana — Dashboard Best Practices](https://grafana.com/docs/grafana/latest/dashboards/build-dashboards/best-practices/)
