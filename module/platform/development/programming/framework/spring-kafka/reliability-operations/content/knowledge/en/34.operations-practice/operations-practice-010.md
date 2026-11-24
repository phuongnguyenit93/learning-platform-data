# Setting Up Metrics and Alerts for Spring Kafka Reliability Operations

## 1. Lab Objectives

A Spring Kafka application can have a `Ready` pod, HTTP health `UP`, and zero startup exceptions while still **having stopped processing records**. Common scenarios include climbing consumer group lag, a partition stalled on a poison message, failing producer futures, continuous retries, growing DLT backlogs, or a slow downstream database.

Therefore, **setting up metrics and alerts** means far more than exposing `/actuator/prometheus`. You must track signals across multiple layers, define the right units of measurement, design alerts with sensible thresholds and evaluation windows, and link every alert to concrete remediation steps.

In the **Operations Practice** section of *Spring Kafka Reliability Operations*, we will:

1. Distinguish broker, consumer-group, client, listener, and business metrics.
2. Enable Spring Boot Actuator, Micrometer, and the Prometheus endpoint.
3. Add custom counters to listeners and `KafkaTemplate`.
4. Measure consumer group lag from the right source instead of mistaking a local client metric for cluster-wide lag.
5. Write PromQL queries for dashboards.
6. Configure alert rules, `for` durations, and Alertmanager routing.
7. Separate **zero** from **missing telemetry**.
8. Test counters and alerts using fault injection.
9. Secure metrics endpoints and keep secrets, PII, and event IDs out of labels.
10. Follow runbooks when lag, DLT rates, send failures, or rebalances climb.

Examples assume **Java 17+, Spring Boot 3.x, Spring Kafka 3.x**, a compatible Kafka broker, Micrometer, and Prometheus. Metric names and exporter labels vary across versions; sections below specify which names are created by the application and which must be verified against your monitoring stack.

## 2. Observability Architecture Diagram

~~~text
                     Kafka cluster
                 broker / topic / group
                        |       |
                Broker JMX   Kafka exporter
                        |       | consumer group lag
                        v       v
                       Prometheus
                           ^
                           | scrape
                      /actuator/prometheus
                           |
                  Spring Kafka service
                  /                 \
           Kafka consumer       Kafka producer
             |      |               |
          listener  client       KafkaTemplate
             |    metrics           |
             v                      v
          business DB          send future ACK
             |
       Micrometer counters
                           |
                           v
                  Prometheus rules
                     |         |
                     v         v
                  Grafana   Alertmanager
                               |
                               v
                         On-call + runbook
~~~

| Layer | Signals | Typical Source |
| --- | --- | --- |
| Broker/cluster | Broker availability, request latency, ISR/replication, disk, controller | Kafka JMX exporter or managed Kafka monitoring. |
| Consumer group | Committed offset, log-end offset, lag per topic/partition | Kafka exporter, Burrow, or equivalent service. |
| Kafka client | Consumer fetch/poll, rebalances, producer requests/retries/errors | Native Kafka client metrics via Micrometer/JMX binder. |
| Spring Kafka container | Listener duration, listener errors, consumer events, retry/DLT policy | Spring Kafka Micrometer/Observation and custom instrumentation. |
| Business service | Successful executions, invalid data, idempotency, downstream delay | Application Counters/Timers, audit database. |
| Telemetry | Scrape target up/down, missing series, rule evaluation | Prometheus. |

No single metric can substitute for every layer:

- Lag of `0` **does not prove** the producer emitted every expected event.
- Increasing listener successes **does not prove** offsets committed or business side effects ran once.
- HTTP health `UP` **does not prove** the consumer holds partition assignments.
- High producer request retries **do not mean** multiple business events were emitted.
- Absent error series **do not mean** error count is `0`.

## 3. Choosing Business-Driven SLIs and Alerts

Define SLIs (Service Level Indicators) before picking thresholds:

| SLI | Measurement Method | Interpretation Example |
| --- | --- | --- |
| Consumer lag | Log-end offset minus committed group offset | Number of records the group trails behind log end. |
| Processing delay | Source timestamp to business completion | How long an event takes to finish processing. |
| Consumer error ratio | Errored listener attempts over total attempts | Share of listener invocations throwing errors. |
| Producer send failure | Failed send futures and failure rate | Client failed to obtain delivery per ACK config. |
| DLT rate | Records actually published to the DLT | Volume of records requiring triage/repair. |
| Processing throughput | Successful attempts or committed business ops/s | Current consumption pace. |
| Availability | Scrape targets and group membership | Telemetry is present and consumers are active. |
| Data correctness | Audits, checksums, idempotency | Whether business outcomes are accurate. |

For realtime topics, a 5-minute backlog can breach SLAs; for nightly batch topics, a few minutes of lag may be completely normal. Thus **thresholds like 1,000 or 5,000 records in this guide are illustrative only**, never universal operational standards.

Ask: do producers emit continuously or on schedules, how many partitions exist, what are average/peak throughputs, what is topic retention, are downstreams slow, which messages have hard deadlines, and what warrants paging on-call?

## 4. Enabling Actuator, Micrometer, and Prometheus

### 4.1. Dependencies

Example `build.gradle` in a version-managed Spring Boot 3.x project:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.kafka:spring-kafka'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:kafka'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`starter-web` runs an HTTP server in this demo for Prometheus scraping. If using WebFlux, a separate management port, or a non-HTTP worker, choose a compatible Actuator/exporter setup. Never expose management ports to the public Internet.

### 4.2. Sample Configuration

`application.yml`:

~~~yaml
spring:
  application:
    name: orders-worker
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS}
    consumer:
      group-id: ${KAFKA_CONSUMER_GROUP}
      enable-auto-commit: false
      auto-offset-reset: ${KAFKA_AUTO_OFFSET_RESET:none}
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      properties:
        max.poll.records: ${KAFKA_MAX_POLL_RECORDS:100}
        max.poll.interval.ms: ${KAFKA_MAX_POLL_INTERVAL_MS:300000}
    listener:
      ack-mode: record
      concurrency: ${KAFKA_LISTENER_CONCURRENCY:2}
    producer:
      acks: all
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
      properties:
        enable.idempotence: true

app:
  kafka:
    input-topic: ${KAFKA_INPUT_TOPIC}
    output-topic: ${KAFKA_OUTPUT_TOPIC}

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  metrics:
    tags:
      application: ${spring.application.name}
~~~

Key settings:

- `enable-auto-commit=false`: lets the Spring Kafka container manage offset commits per acknowledgment strategy.
- `ack-mode=record`: container acknowledges after each record listener succeeds per container/error-handler semantics. **Does not create an ACID transaction across Kafka and a database.**
- `auto-offset-reset=none`: fails in this example if the group has no valid committed offset; other apps may choose `earliest` or `latest` per business contract.
- `concurrency=2`: spawns consumer threads per container config, capped practically by assigned partitions.
- `acks=all`, `enable.idempotence=true`: strengthens Kafka publish safety per broker/client guarantees; does not make external side effects exactly-once.

In production, externalize broker/group/topic and SASL/TLS settings via environment variables or a secret manager. Never put raw secrets into ConfigMaps or metric labels.

### 4.3. Querying Endpoints Locally

~~~bash
curl http://localhost:8080/actuator/health
curl http://localhost:8080/actuator/metrics
curl http://localhost:8080/actuator/prometheus
~~~

`/actuator/metrics` reveals exact meter names and available tags. `/actuator/prometheus` outputs Prometheus exposition text for scraping.

**Not every Kafka metric appears immediately at startup.** Many meters register only after a client/producer/consumer initializes or the first event flows. In Spring Kafka 3.x, legacy Micrometer timers vs. Micrometer Observation also depend on version and configuration.

## 5. Distinguishing Built-In Metrics from Application Metrics

### 5.1. JVM / Process / HTTP Metrics

Spring Boot Actuator typically exposes meters such as:

~~~text
jvm.memory.used
jvm.gc.pause
process.cpu.usage
system.cpu.usage
http.server.requests
~~~

In Prometheus, names normalize by convention and meter type, e.g., `jvm_memory_used_bytes`. These reflect application resource capacity, not proof that events were processed.

### 5.2. Kafka Client Metrics

The Kafka Java client exposes metrics by client ID and internal groups such as `records-consumed-rate`, `records-lag-max`, `record-send-rate`, `record-error-rate`, `record-retry-rate`, and `request-latency-avg`.

**Those exact names are not guaranteed to be the Prometheus series names.** JMX, Kafka metrics binders, Spring Kafka Observation, and exporters map names and labels differently. Inspect the live endpoint on your running version before authoring dashboards.

### 5.3. Spring Kafka Listener / Template Metrics

Spring Kafka supports Micrometer timers and Observation. Meters such as `spring.kafka.listener` or `spring.kafka.template` appear when the corresponding instrumentation is enabled. Never assume enabling both Observation and legacy Micrometer timers produces two sets of counts to sum together.

### 5.4. Custom Metrics in This Lesson

We will create:

| Meter Name | Type | When Incremented | Typical Prometheus Name |
| --- | --- | --- | --- |
| `app.kafka.consume.records` | Counter | Each listener callback completion by outcome | `app_kafka_consume_records_total` |
| `app.kafka.produce.results` | Counter | `KafkaTemplate` future success/failure | `app_kafka_produce_results_total` |

Both meters are **created by application code**, not provided automatically by Kafka or Spring Kafka. Exported names depend on registry naming conventions.

## 6. Instrumenting Listener Processing Attempts

Suppose the topic carries `OrderEvent` JSON:

~~~java
package com.example.kafka;

public record OrderEvent(
        String eventId,
        String orderId,
        long amount) {
}
~~~

Business service:

~~~java
package com.example.kafka;

public interface OrderService {
    // Implementation must be idempotent by event ID.
    void apply(OrderEvent event);
}
~~~

Listener:

~~~java
package com.example.kafka;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrdersListener {

    private final ObjectMapper mapper;
    private final OrderService service;
    private final Counter success;
    private final Counter error;

    public OrdersListener(
            ObjectMapper mapper,
            OrderService service,
            MeterRegistry registry) {
        this.mapper = mapper;
        this.service = service;

        this.success = Counter.builder("app.kafka.consume.records")
                .description("Observed listener attempts")
                .tag("listener", "orders")
                .tag("outcome", "success")
                .register(registry);

        this.error = Counter.builder("app.kafka.consume.records")
                .description("Observed listener attempts")
                .tag("listener", "orders")
                .tag("outcome", "error")
                .register(registry);
    }

    @KafkaListener(
        id = "orders-listener",
        topics = "${app.kafka.input-topic}",
        groupId = "${spring.kafka.consumer.group-id}")
    public void onMessage(ConsumerRecord<String, String> record)
            throws Exception {
        try {
            OrderEvent event =
                mapper.readValue(record.value(), OrderEvent.class);

            if (event.eventId() == null || event.eventId().isBlank()) {
                throw new IllegalArgumentException("Missing event ID");
            }

            service.apply(event);
            success.increment();
        } catch (Exception failure) {
            error.increment();
            // Error handler decides retry/DLT. Never swallow exceptions.
            throw failure;
        }
    }
}
~~~

**Unit of measurement:** count of listener callback executions observed by code; **not the count of unique business events**.

For example, if one record fails twice and succeeds on the third attempt:

~~~text
attempt 1 -> error +1
attempt 2 -> error +1
attempt 3 -> success +1
```

Thus `error=2, success=1` does not mean 3 distinct events existed. Even after the listener succeeds, Kafka offset commit is still a separate container step. If the database commits and the process dies before offset commit, the message may be redelivered.

To guarantee zero duplicate side effects, rely on **stable business event idempotency keys**, transaction boundaries, or outboxes—never on Counters.

Never log raw `record.value()` or full exception messages if payloads contain sensitive data. Topic/partition/offset coordinates are fine in retention-controlled investigation logs, but never put event IDs or offsets into metric tags.

## 7. Producer Metrics Based on Send Future Outcomes

A common operational mistake is calling `KafkaTemplate.send()` and immediately incrementing a producer success counter. `send()` returns a `CompletableFuture`, while the broker ACK or failure arrives asynchronously later.

~~~java
package com.example.kafka;

import java.util.concurrent.CompletableFuture;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Component;

@Component
public class OrderPublisher {

    private final KafkaTemplate<String, String> template;
    private final Counter acknowledged;
    private final Counter failed;

    public OrderPublisher(
            KafkaTemplate<String, String> template,
            MeterRegistry registry) {
        this.template = template;

        this.acknowledged = Counter.builder(
                "app.kafka.produce.results")
                .tag("channel", "orders")
                .tag("outcome", "acknowledged")
                .register(registry);

        this.failed = Counter.builder(
                "app.kafka.produce.results")
                .tag("channel", "orders")
                .tag("outcome", "error")
                .register(registry);
    }

    public CompletableFuture<SendResult<String, String>> publish(
            String topic, String key, String payload) {

        CompletableFuture<SendResult<String, String>> future =
                template.send(topic, key, payload);

        future.whenComplete((result, exception) -> {
            if (exception == null) {
                acknowledged.increment();
            } else {
                failed.increment();
            }
        });

        return future;
    }
}
~~~

The `acknowledged` counter indicates the send future succeeded under Kafka client settings (e.g., `acks=all`), **not that a downstream consumer has processed the event**. Callbacks can also miss running if the JVM crashes before completion.

Callers must still handle returned futures and errors per publish contract; recording metrics does not provide durable retries. If an application commits to a database before publishing to Kafka, evaluate a transactional outbox rather than retrying solely in memory.

## 8. Where Does Consumer Group Lag Come From?

Group lag is computed from the broker log-end offset and the group's committed offset:

~~~text
topic-partition log-end offset
          -
consumer-group committed offset
          =
group lag at observation time
~~~

The native client metric `records-lag-max` reflects a local consumer view and **does not replace cluster-wide committed group lag reporting**.

For example, a common Kafka exporter emits series like:

~~~text
kafka_consumergroup_lag{
  consumergroup="orders-worker-prod",
  topic="orders.events",
  partition="0"
}
~~~

**Assumption going forward:** your actual exporter provides `kafka_consumergroup_lag` with `consumergroup`, `topic`, and `partition` labels. Some exporters and managed Kafka platforms use different metric or label names; verify them before writing PromQL.

### 8.1. Total Lag

~~~promql
sum by (consumergroup, topic) (
  kafka_consumergroup_lag{
    consumergroup="orders-worker-prod"
  }
)
~~~

### 8.2. Largest Lagging Partition

~~~promql
max by (consumergroup, topic) (
  kafka_consumergroup_lag{
    consumergroup="orders-worker-prod"
  }
)
~~~

Monitor both **sum** and **max**: a modest total lag can still hide one hot partition delaying an important subset of business keys.

### 8.3. Lag Is Not Delay Time

5,000 records of lag at 100 records/s is completely different from 20,000 records/s. For time-based SLAs, also measure event age or business processing delay using trusted source timestamps while accounting for clock skew.

### 8.4. No Data Is Not Zero Lag

If a group has never committed an offset, the exporter lacks permissions, or scraping broke, the series may not exist at all. **Never blindly append `or vector(0)` to make dashboards look healthy.** Add missing-telemetry and expected-group alerts.

## 9. Configuring Prometheus Scraping

Lab example assuming DNS names `orders-worker` and `kafka-exporter` on the same network:

~~~yaml
global:
  scrape_interval: 30s
  evaluation_interval: 30s

scrape_configs:
  - job_name: orders-worker
    metrics_path: /actuator/prometheus
    static_configs:
      - targets: ["orders-worker:8080"]
        labels:
          environment: lab
          cluster: kafka-lab

  - job_name: kafka-exporter
    static_configs:
      - targets: ["kafka-exporter:9308"]
        labels:
          environment: lab
          cluster: kafka-lab
~~~

These hostnames are **lab placeholders**, not real cluster endpoints. `localhost` works only when the exporter, app, and Prometheus share a network namespace.

**Multi-pod production:** scraping through a single Kubernetes Service hits only one pod per scrape and misses metrics from sibling replicas. Use Kubernetes service discovery or Prometheus Operator `PodMonitor`/`ServiceMonitor` to scrape every pod.

Example `PodMonitor` when pods expose a port named `http`:

~~~yaml
apiVersion: monitoring.coreos.com/v1
kind: PodMonitor
metadata:
  name: orders-worker
  namespace: applications
  labels:
    release: kube-prometheus-stack
spec:
  namespaceSelector:
    matchNames:
      - applications
  selector:
    matchLabels:
      app: orders-worker
  podMetricsEndpoints:
    - port: http
      path: /actuator/prometheus
      interval: 30s
      scrapeTimeout: 10s
~~~

This is a **Prometheus Operator** custom resource requiring matching CRDs, operators, and selectors. `http` must match the exact **container port** name, and network policies must permit Prometheus scrapes. If using a separate management port, update it accordingly.

Protect `/actuator/prometheus` with network policies, proxies, or authentication. Never expose `/actuator/env`, `/actuator/configprops`, or heap dumps to the Internet.

## 10. Essential PromQL Queries

### 10.1. Listener Success Rate

~~~promql
sum by (job, listener) (
  rate(
    app_kafka_consume_records_total{outcome="success"}[5m]
  )
)
~~~

### 10.2. Listener Failed Attempts in 15 Minutes

~~~promql
sum by (job, listener) (
  increase(
    app_kafka_consume_records_total{outcome="error"}[15m]
  )
)
~~~

### 10.3. Produce Errors per Second

~~~promql
sum by (job, channel) (
  rate(
    app_kafka_produce_results_total{outcome="error"}[5m]
  )
)
~~~

### 10.4. Ratio of Failed Listener Attempts

~~~promql
sum by (job, listener) (
  rate(
    app_kafka_consume_records_total{outcome="error"}[5m]
  )
)
/
clamp_min(
  sum by (job, listener) (
    rate(app_kafka_consume_records_total[5m])
  ),
  0.001
)
~~~

`job` here is the **Prometheus scrape job**, not the Kafka consumer group ID. Because custom counters carry `listener` and `outcome` labels while the group-lag exporter carries `consumergroup` and `topic`, they cannot auto-join by topic/group without a mapping. Place panels side by side or attach a controlled, low-cardinality label set via configuration.

### 10.5. Scrape Availability

~~~promql
up{job="orders-worker"}
~~~

`up=1` means only that the HTTP scrape succeeded. `up=0` means the scraper failed to reach the target. If a target **vanishes from discovery**, the `up` series can disappear completely; check for absent/missing targets too.

## 11. Configuring Alert Rules with Evaluation Windows

A Prometheus rule should define:

- A query measuring the right unit.
- Thresholds suited to workload and SLOs.
- A `for` clause to filter brief spikes.
- `severity` reflecting impact.
- Routing labels without blowing up cardinality.
- Helpful descriptions and runbook links.
- Rules covering missing telemetry.

Example `kafka-alerts.yml`:

~~~yaml
groups:
  - name: spring-kafka-reliability
    interval: 30s
    rules:
      - alert: KafkaConsumerGroupLagHigh
        expr: |
          sum by (cluster, environment, consumergroup, topic) (
            kafka_consumergroup_lag{
              consumergroup="orders-worker-prod"
            }
          ) > 5000
        for: 10m
        labels:
          severity: warning
          service: orders-worker
        annotations:
          summary: "Kafka group lag is high"
          description: "Check group membership, input rate, throughput, and DLT"
          runbook_url: "https://runbooks.example.org/kafka/lag"

      - alert: KafkaConsumerPartitionLagHigh
        expr: |
          max by (cluster, environment, consumergroup, topic) (
            kafka_consumergroup_lag{
              consumergroup="orders-worker-prod"
            }
          ) > 2000
        for: 10m
        labels:
          severity: warning
          service: orders-worker
        annotations:
          summary: "A partition has a large backlog"

      - alert: KafkaListenerErrorRatioHigh
        expr: |
          (
            sum by (job, listener) (
              rate(
                app_kafka_consume_records_total{
                  outcome="error"
                }[5m]
              )
            )
            /
            clamp_min(
              sum by (job, listener) (
                rate(app_kafka_consume_records_total[5m])
              ),
              0.001
            )
          ) > 0.05
          and on (job, listener)
          (
            sum by (job, listener) (
              increase(app_kafka_consume_records_total[5m])
            ) > 20
          )
        for: 5m
        labels:
          severity: warning
          service: orders-worker
        annotations:
          summary: "Listener failed attempt ratio is elevated"

      - alert: KafkaProducerSendFailures
        expr: |
          sum by (job, channel) (
            rate(
              app_kafka_produce_results_total{
                outcome="error"
              }[5m]
            )
          ) > 0.1
        for: 5m
        labels:
          severity: critical
          service: orders-worker
        annotations:
          summary: "Sustained KafkaTemplate send failures"

      - alert: KafkaApplicationScrapeDown
        expr: up{job="orders-worker"} == 0
        for: 3m
        labels:
          severity: critical
          service: orders-worker
        annotations:
          summary: "Unable to scrape application"

      - alert: KafkaExporterTargetMissing
        expr: absent(up{job="kafka-exporter"})
        for: 5m
        labels:
          severity: warning
          service: kafka-observability
        annotations:
          summary: "Kafka exporter target is missing"
~~~

**Prerequisites before using these rules:**

1. The Kafka exporter must expose `kafka_consumergroup_lag` with the assumed labels.
2. Listener and producer code must register both `app.kafka.*` metrics.
3. Prometheus scrape config must attach `job`, `cluster`, and `environment` labels as expected.
4. Numeric thresholds are **illustrative**—never copy blindly into production.
5. Runbook URLs are placeholders—replace with real links.
6. When a series disappears completely, error-ratio or lag expressions can return an empty vector; maintain dedicated missing-telemetry alerts.
7. If one Prometheus server scrapes multiple environments, explicitly filter `environment`/`cluster` on critical rules.

### 11.1. Why Does the Error Ratio Alert Gate on Traffic Volume?

A single failure on one event produces a 100% error ratio, which may not warrant paging. The clause:

~~~promql
sum by (job, listener) (
  increase(app_kafka_consume_records_total[5m])
) > 20
~~~

guards ratio alerts until a meaningful sample size exists. For **critical payment events**, a single severe error might still demand immediate alerting via a separate business audit alert. Never apply one traffic gate across every SLO.

### 11.2. Why Does `for` Matter?

If a burst pushes group lag above 5,000 for 30 seconds and then drains quickly, an alert with `for: 10m` will not page. If lag stays above threshold continuously for 10 minutes, the rule transitions to firing on its evaluation schedule.

`for` cannot fix broken queries, missing telemetry, or a 1-minute SLA. Thresholds and durations must come from actual business impact.

## 12. Evaluating Lag Alongside Processing Speed

Lag = 10,000 shrinking by 5,000 records/minute may represent healthy draining. Lag = 1,000 frozen for 30 minutes under steady incoming traffic can be far more serious.

A dashboard should place side by side:

~~~promql
sum by (consumergroup, topic) (
  kafka_consumergroup_lag{
    consumergroup="orders-worker-prod"
  }
)
~~~

and:

~~~promql
sum by (listener) (
  rate(
    app_kafka_consume_records_total{outcome="success"}[5m]
  )
)
~~~

Never add those two numbers together: the first is **group record backlog**, while the second is **successful listener callbacks per second**. Under retries or redeliveries, attempts do not equal unique events.

When SLAs measure end-to-end completion time, track **business event age** or delay from source timestamp to durable outcome. Estimating delay from lag divided by throughput is only roughly accurate under steady load.

## 13. Alertmanager Routing and Noise Reduction

Prometheus evaluates rules; Alertmanager handles grouping, routing, silences, and inhibition.

Simple routing example:

~~~yaml
route:
  receiver: default-ops
  group_by:
    - alertname
    - cluster
    - environment
    - service
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
  routes:
    - matchers:
        - severity="critical"
      receiver: oncall-critical

receivers:
  - name: default-ops
  - name: oncall-critical
~~~

These receivers are placeholder names only and **do not deliver notifications yet**. Integrating email, PagerDuty, chat, or webhooks requires configuring receivers and managing secrets safely without committing tokens to Git.

Consider:

- `warning`: ticket or tracked channel if addressable during business hours.
- `critical`: pages on-call when risking data loss, outages, or SLA breaches.
- Group alerts by service/cluster instead of firing separate pages per partition or pod.
- Use time-bounded maintenance silences during rollouts, but never silence data-corruption alerts.
- When the exporter goes down, lag alerts can vanish; never mistake missing alerts for cleared lag.

## 14. Minimal Grafana Dashboard

| Panel | Source | Question Answered |
| --- | --- | --- |
| Total group lag | Kafka exporter | How large is the backlog? |
| Max partition lag | Kafka exporter | Is one partition stalled? |
| Listener success/error rate | Custom Micrometer | How are consumer callbacks behaving? |
| Producer ACK/failure rate | `KafkaTemplate` completion counters | Are sends succeeding? |
| Listener/business duration | Spring Kafka Timer/Observation or app Timer | Are p95/p99 latencies climbing? |
| Consumer rebalances | Kafka client instrumentation | Is the group churning? |
| DLT backlog/rate | Exporter, DLT audit | How many records need handling? |
| JVM CPU/heap/GC | Actuator | Is the app resource-starved? |
| Broker health/ISR/disk | Broker exporter | Is the cluster under pressure? |
| Business applied count | Database/audit | Are business outputs genuinely accurate? |

For percentiles, configure histogram buckets. If a Timer exports only `_count` and `_sum` without `_bucket`s, `histogram_quantile` cannot compute true p95 from those two series alone.

With `MeterRegistry`, you can add a Timer for custom business work, but avoid double-counting built-in listener duration. When histograms carry many labels, series counts multiply by bucket counts.

## 15. DLT, Retries, and Metric Semantics

Typical fault-tolerant flow:

~~~text
Consumer record
      |
      v
Listener processing
      |
      +-- success -> container ACK/commits per policy
      |
      +-- error
            |
            v
       Error handler
            |
         retry(s)
            |
            +-- success
            |
            +-- exhausted
                    |
                    v
              DLT publisher
                    |
                 send future
                    |
                +---+---+
                |       |
               ACK     error
~~~

Never rename `app.kafka.consume.records{outcome="error"}` to `dlt_total`: a record can fail multiple times and still succeed on retry **without ever entering the DLT**.

| What to Measure | When to Record |
| --- | --- |
| Listener attempts | Listener callback success/error. |
| Retry attempts | Specific retry/error-handler instrumentation. |
| DLT publish requests | When recoverer invokes send. |
| DLT ACK successes | When future/recoverer confirms broker receipt per config. |
| DLT backlog | DLT topic exporter and triage audit state. |
| Business applied unique events | Transactional audit / idempotency store. |

Use `DefaultErrorHandler`, `DeadLetterPublishingRecoverer`, or `@RetryableTopic` matching your Spring Kafka version. Account for cases where the error handler retries/seeks and commits offsets per recovery policy; never assume one exception equals one lost message.

## 16. Testing Custom Counters with `SimpleMeterRegistry`

With `OrdersListener` above, you can unit-test metrics directly without a broker:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class OrdersListenerMetricsTest {

    @Test
    void countsSuccessAndErrorAttempts() throws Exception {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();

        try {
            OrderService service = event -> {
                if ("fail".equals(event.eventId())) {
                    throw new IllegalStateException("test failure");
                }
            };

            OrdersListener listener = new OrdersListener(
                new ObjectMapper(), service, registry);

            listener.onMessage(new ConsumerRecord<>(
                "orders.events", 0, 0L, "k1",
                "{\"eventId\":\"ok\",\"orderId\":\"o1\",\"amount\":100}"
            ));

            assertThrows(IllegalStateException.class, () ->
                listener.onMessage(new ConsumerRecord<>(
                    "orders.events", 0, 1L, "k2",
                    "{\"eventId\":\"fail\",\"orderId\":\"o2\",\"amount\":200}"
                ))
            );

            assertEquals(1.0,
                registry.get("app.kafka.consume.records")
                    .tags("listener", "orders", "outcome", "success")
                    .counter().count());

            assertEquals(1.0,
                registry.get("app.kafka.consume.records")
                    .tags("listener", "orders", "outcome", "error")
                    .counter().count());
        } finally {
            registry.close();
        }
    }
}
~~~

This test verifies only that **Micrometer counters** increment as coded. It does not prove Kafka partition assignment, offset commits, retry/DLT routing, or exporter group lag—those require integration tests against a real broker.

A registry can span multiple tests in the same Spring context, accumulating counts. Use an isolated `SimpleMeterRegistry` or measure before/after deltas rather than assuming counters always start at zero.

## 17. Integration Testing with Kafka and a DB

Use `@EmbeddedKafka` or Testcontainers Kafka for the test broker and a test database for business effects.

~~~text
Kafka test broker
    |
    +-- valid event ------> listener success
    |
    +-- invalid event ----> error handler retry/DLT
    |
    v
Micrometer test registry
    |
    v
Database/business audit
~~~

Test matrix:

| Scenario | Assertion |
| --- | --- |
| Valid event | Listener success counter increments; target data matches. |
| Event causing use-case failure | Error attempts increment; error handler applies policy. |
| Retry succeeds | Error attempts precede success; business effect not duplicated. |
| Poison message goes to DLT | Actual record lands in DLT; ACK/recovery follows policy. |
| Producer broker unreachable | Future fails; producer error counter increments. |
| Consumer restart | Group offsets and redeliveries obey policy; idempotency protects data. |
| Pod restarted | Runtime counters reset; DB audit and Kafka state reconcile accurately. |
| Exporter disconnected | `up`/missing alert fires; never displays fake `lag=0`. |

To test `SASL_SSL`/TLS/ACLs, configure matching security on the test broker; a plain PLAINTEXT `@EmbeddedKafka` does not prove production authentication.

## 18. Testing Alerts with Prometheus Rule Tests

Syntactically valid alerts can still never fire if:

- Metric names or labels do not exist.
- The `job` label differs from expectations.
- The range window is too short for the scrape interval.
- The query yields an empty vector when an exporter is missing.
- The `for` duration has not elapsed long enough.
- Alertmanager silences or misroutes the alert.
- A denominator has zero or too few samples.

Testing workflow:

1. Inspect live series in the Prometheus expression browser.
2. Run each PromQL expression to verify labels and values.
3. Validate syntax with `promtool check rules`.
4. Run `promtool test rules` with time-series fixtures and expected alerts.
5. In staging, inject controlled lag/errors and observe `pending → firing → resolved`.
6. Confirm Alertmanager receives the right severity, service, and environment.
7. Verify notifications link to the right runbook and dashboard.
8. Only then enable production routing.

Timing example:

~~~text
T+00: lag = 100
T+05: lag = 7000
T+10: lag = 7000
T+15: lag = 7000

Rule: lag > 5000, for: 10m

Does not fire immediately at T+05.
May fire after condition holds for a full 10 minutes,
depending on Prometheus's actual evaluation cadence.
~~~

Note: if a rule specifies `for: 10m`, a 30-second fault test will not prove the alert fires.

## 19. Runbook: Rising Consumer Lag

**Symptom:** sustained high sum lag or max partition lag.

### Diagnosis

1. Confirm the exporter and scrapes are healthy and lag series are real.
2. Identify which group, topic, and partitions are climbing.
3. Check group membership and partition assignments.
4. Check incoming producer rate: burst or genuinely slow processing?
5. Check listener attempts, errors, DLT, retries, and poison messages.
6. Check rebalances, poll intervals, and consumer thread CPU/GC.
7. Check downstream DB/API latency and connection pools.
8. Compare backlog drain rate against processing deadlines.
9. Check recent deployments/config changes, especially `group.id`, topics, concurrency, and ack mode.

### Actions

- Fix downstream bottlenecks before increasing concurrency.
- If a poison record blocks a partition, apply DLT/quarantine per policy.
- If processing between polls is too slow, tune batch sizes/latency or poll intervals based on measurements.
- Before scaling, check `replicas × concurrency` against partition counts and DB capacity.
- If lag is draining normally, track SLA progress and refine noisy thresholds.

**Never change group IDs or reset offsets** just to turn lag graphs green. Both actions risk replaying or skipping data.

## 20. Runbook: Producer Send Failures

1. Check bootstrap servers, DNS, advertised listeners, and network connectivity.
2. Check SASL/TLS handshakes, credential rotations, and producer `Write` ACLs.
3. Check broker/topic health, ISR, latency, and availability.
4. Check payload sizes, serialization, and Kafka client timeouts.
5. Inspect returned future exceptions; separate client retries from application retries.
6. Reconcile event IDs / idempotency when the client timed out yet the broker may have persisted the record.
7. For critical data, retry via a durable outbox per policy rather than dropping events.

Never lower `acks=all` to `acks=0` to hide errors. That weakens durability guarantees without fixing the root cause.

## 21. Runbook: Rising DLT Rate or Repeated Failures

- Correlate release or schema-change timestamps with the DLT spike.
- Classify errors: deserialization, validation, transient DB, downstream timeouts, ACLs.
- Check the error handler and retry budget; avoid infinite retries.
- Verify the DLT producer has permissions to publish and receives ACKs.
- Record failing event IDs in an appropriate audit store without putting payloads/PII into metric labels.
- Replay DLT records only after fixing root causes; enforce idempotency because an earlier attempt may have applied side effects.
- Track source-topic lag and DLT backlog separately.

Records in a DLT do not mean data is lost: it is a **controlled recovery path**, though someone and some workflow must still triage and process it.

## 22. Runbook: Prometheus / Grafana Has No Data

~~~text
Application / Kafka exporter
             |
             v
       HTTP metrics endpoint
             |
             v
      Prometheus discovery/scrape
             |
             v
          TSDB/rules
             |
             v
       Grafana/Alertmanager
~~~

Check:

1. Are the app/pods and exporter running?
2. Is `up{job="..."}` `0`, `1`, or completely absent?
3. Does the endpoint return HTTP 200 from Prometheus's network?
4. Do `ServiceMonitor`/`PodMonitor` selectors, namespaces, and port names match?
5. Is the Micrometer Prometheus registry configured?
6. Are counters registered and have listeners/producers actually executed?
7. Did metric names change after upgrading Spring Boot, Micrometer, or the exporter?
8. Are dashboard filters (`job`, `cluster`, `environment`) filtering out all series?
9. Are NetworkPolicies, TLS, or auth blocking scrapes?

**Never convert `No data` to `0` automatically** on critical alerts. Maintain alerts for missing telemetry and missing expected targets.

## 23. Cardinality, Security, and Cost

Creating a new label per `eventId`, `orderId`, `offset`, email, exception message, or request ID can explode into millions of time series and leak sensitive data.

Never use:

~~~text
eventId=evt-123456
userEmail=user@example.org
apiToken=...
offset=123456789
exceptionMessage=Connection failed for password=...
~~~

Prefer bounded label sets:

~~~text
listener=orders
outcome=success|error
channel=orders
errorCategory=validation|timeout|db|other
application=orders-worker
environment=production
~~~

Kafka exporters may require `topic`, `consumergroup`, and `partition` labels, so account for topic/partition/group counts and storage cost.

Protect `/actuator/env`, `/actuator/configprops`, heap dumps, and metrics endpoints with strict access controls. Never dump entire `KafkaProperties` objects, which can contain SASL JAAS credentials. Store Alertmanager webhooks and tokens in a secret manager, never in Git.

## 24. Distinguishing Metrics, Logs, Traces, and Audits

| Tool | Best Suited For | Limitations |
| --- | --- | --- |
| Metrics | Rates, error ratios, latency, lag, SLOs | Lacks per-event details. |
| Logs | Stack traces, topic/partition/offset, error categories | Poor substitute for long-term throughput metrics. |
| Traces | Event flow across Kafka, app, DB, and APIs | Sampling can miss individual events. |
| Audit DB / outbox | Business keys, committed side effects, reconciliation | Does not replace real-time time-series monitoring. |

When an alert fires, dashboards tell you **where and for how long**, logs/traces tell you **why**, and audits verify **whether final business data is correct**.

## 25. Production Rollout Checklist

| Step | Action | Expectation |
| --- | --- | --- |
| 1 | Finalize SLIs/SLOs and owners | Meaningful metrics and grounded thresholds. |
| 2 | Enable Actuator/Micrometer | Protected metrics endpoint available. |
| 3 | Add custom counters | Clear units for listener attempts and futures. |
| 4 | Connect Kafka exporter | Accurate lag per group/topic/partition. |
| 5 | Scrape every pod | No missed replicas from scraping a single Service. |
| 6 | Verify metric names and labels | PromQL matches live runtime output. |
| 7 | Configure rules + Alertmanager | Right severities, routing, and `for` windows. |
| 8 | Verify missing-telemetry alerts | Dead exporters or pods still trigger alerts. |
| 9 | Run staging fault injection | Alerts fire and resolve as expected. |
| 10 | Link runbooks | On-call has clear remediation steps. |
| 11 | Calibrate against live traffic | Avoids false positives and alert fatigue. |
| 12 | Review security and cardinality | Zero leaked secrets/PII and bounded series counts. |

## 26. Practice Exercises

### Exercise 1 — Observing Four Layers

List metrics across broker, consumer group, Kafka client, and business service layers. Explain how `records-lag-max` differs from `kafka_consumergroup_lag` and which metrics reset on pod restarts.

### Exercise 2 — Actuator

Run Spring Boot locally with the Prometheus registry and inspect `/actuator/metrics` and `/actuator/prometheus`. Record actual metric names without exposing sensitive endpoints publicly.

### Exercise 3 — Listener Attempts

Use a fake `OrderService` for one succeeding event and one failing event. Verify counters while ensuring the exception still propagates to the error handler for retry/DLT handling.

### Exercise 4 — Producer Futures

Mock `KafkaTemplate` future successes and failures. Verify counters increment **when the future completes**, not immediately when `send()` returns.

### Exercise 5 — Lag While Consumer Is Paused

On a test broker, run a group with committed offsets, pause the consumer, and publish 100 records. Observe exporter lag across scrapes, then resume and watch lag drain. Never run on production.

### Exercise 6 — Hot Partition

Create a 3-partition topic and send many records with the same key. Compare total lag vs. max partition lag, and explain why adding pods does not unstick a single hot partition.

### Exercise 7 — Error Ratio at Low Traffic

Test the rule with 1/1 errors and 30/100 errors. Verify the traffic gate and `for` clause alert as intended without paging on a single isolated error outside policy.

### Exercise 8 — DLT

Inject a poison message on a test broker and observe listener attempts, retries, DLT publish confirmations, and DLT topic growth. Explain why those four counts differ.

### Exercise 9 — Missing Telemetry

Stop the exporter or break the `PodMonitor` selector in staging; verify `up`/absence alerts fire and dashboards do not treat `No data` as healthy.

### Exercise 10 — Incident Drill

Slow down a test database to induce consumer lag. Follow the diagnostic runbook, fix the bottleneck, and verify business data has zero duplicates once the consumer catches up.

## 27. References

- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Boot — Prometheus Support](https://docs.spring.io/spring-boot/reference/actuator/metrics.html#actuator.metrics.export.prometheus)
- [Spring Kafka — Monitoring and Micrometer](https://docs.spring.io/spring-kafka/reference/kafka/micrometer.html)
- [Spring Kafka — Receiving Messages](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html)
- [Spring Kafka — Error Handling](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)
- [Spring Kafka — Exactly Once Semantics](https://docs.spring.io/spring-kafka/reference/kafka/exactly-once.html)
- [Apache Kafka — Monitoring](https://kafka.apache.org/documentation/#monitoring)
- [Micrometer — Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html)
- [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Prometheus — Querying Functions](https://prometheus.io/docs/prometheus/latest/querying/functions/)
- [Prometheus — Alerting Rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/)
- [Prometheus — Unit Testing Rules](https://prometheus.io/docs/prometheus/latest/configuration/unit_testing_rules/)
- [Alertmanager — Configuration](https://prometheus.io/docs/alerting/latest/configuration/)
- [Prometheus Operator — PodMonitor API](https://prometheus-operator.dev/docs/api-reference/api/#monitoring.coreos.com/v1.PodMonitor)
- [Testcontainers — Kafka Module](https://java.testcontainers.org/modules/kafka/)

