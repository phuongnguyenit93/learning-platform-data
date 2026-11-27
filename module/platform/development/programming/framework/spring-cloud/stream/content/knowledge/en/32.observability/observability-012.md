# Building Alerts and Dashboards for Stream Health

A Spring Cloud Stream application can remain running with its health endpoint returning UP while data piles up, consumers process slowly, messages continuously enter the DLQ, or a binding stops receiving events. System observability therefore needs to track the application, bindings, and broker together. Dashboards must show how much data the stream is receiving, how fast it is processing, where errors appear, and whether backlogs are growing. Alerts must tie to business impact and concrete remediation steps.

This lesson builds an approach for observing Supplier/Function/Consumer pipelines using Spring Boot Actuator, Micrometer, Prometheus, and Grafana; adding native metrics from Kafka, RabbitMQ, or Pulsar; and using SLIs/SLOs to create alerts and runbooks.

## 1. Three-layer observability

No single metric captures full stream health. Organize observability data into three layers:

| Layer | What to monitor | Operational question |
|---|---|---|
| Application and functions | Events received/processed/failed, processing duration, exceptions, JVM, threads, connections | Are functions processing events properly? |
| Bindings and consumers | Per-binding throughput, consumer group/subscription, retries, redeliveries, pause state, concurrency | Which binding is slow or failing? |
| Broker and infrastructure | Kafka lag/partitions, RabbitMQ queue depth/unacked, Pulsar backlog/subscriptions, broker health, disk/network | Is the broker accepting and distributing data normally? |

A stream can have high input throughput alongside low output throughput. A function can process individual messages quickly while an under-provisioned consumer group still builds lag. A broker can be healthy while one specific queue backs up due to consumer errors. Dashboards must place these numbers side by side to locate bottlenecks.

Overall observability flow:

    Producer / Source
        -> Broker
        -> Spring Cloud Stream binding
        -> Function / Consumer
        -> Output binding
        -> Downstream broker / service

    Application metrics ----+
    Broker exporter ---------+--> Prometheus --> Grafana dashboards
    Alert rules -------------+                 --> Alertmanager / on-call

## 2. Choosing SLIs and SLOs before building dashboards

An SLI (Service Level Indicator) measures actual service quality. An SLO (Service Level Objective) is the quality target over a time window. Adding dozens of charts without defining targets leaves operations teams unsure which numbers require action.

For event streams, commonly useful SLIs include:

- **Processing success ratio:** proportion of valid events processed successfully.
- **End-to-end processing latency:** time from event creation/ingestion until processing completes.
- **Consumer lag or backlog:** amount of data waiting for consumers.
- **Oldest message age:** age of the oldest unprocessed message.
- **DLQ rate:** rate at which messages are diverted to dead-letter destinations.
- **Availability:** ability of bindings/consumers to stay connected and keep processing.
- **Throughput:** inbound and outbound events per second or per minute.

Example targets for an order-processing stream:

| SLI | Illustrative SLO | Interpretation |
|---|---|---|
| Event processing success | 99.9% over 30 days | Valid events processed successfully, excluding contract-rejected messages |
| End-to-end latency | 99% under 30 seconds | 99% of events finish within 30 seconds from the agreed start point |
| Backlog age | Oldest message under 2 minutes | The stream does not leave events waiting too long |
| DLQ rate | Under 0.1% of input events | Unprocessable errors must be rare and investigated |
| Consumer availability | 99.9% of the time | Consumers are available to receive and process data |

These figures are only examples. Each stream must define event types, operating hours, expected traffic, business requirements, and how denominators are counted. For instance, if producers emit no events overnight, you should not alert solely because throughput is 0 during that window.

### 2.1. Defining the denominator and completion state

A success ratio is meaningful only when you define clearly when an event counts as successful. That could be function completion, database transaction commit, confirmed output publish, or downstream business confirmation. These milestones differ.

For a consumer that writes to a database and then publishes downstream, distinguish:
- Message received.
- Processing started.
- Business side effects committed.
- Output published and confirmed per delivery contract.
- Offset/ack committed with the broker.

Do not lump all steps into one `success` counter if steps can fail independently. Use separate metrics for key milestones or define a clear completion boundary for the SLO.

## 3. Adding Actuator and the Prometheus registry

Spring Boot Actuator provides management and observability endpoints. Micrometer is the facade for recording metrics; the registry ships metrics to the target collection system. For Prometheus, applications typically need Actuator and the Micrometer Prometheus registry.

Maven dependencies, letting the Spring Boot BOM manage versions:

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
        <scope>runtime</scope>
    </dependency>

Example configuration:

    management:
      endpoints:
        web:
          exposure:
            include: health,info,prometheus
      endpoint:
        health:
          probes:
            enabled: true
      metrics:
        tags:
          application: order-stream-processor

Prometheus typically scrapes `/actuator/prometheus`. The health endpoint checks application status and readiness/liveness probes. Expose only required endpoints; enforce authentication, network policies, or a reverse proxy. Never expose all Actuator endpoints to the public Internet.

Example Prometheus scrape config:

    scrape_configs:
      - job_name: order-stream-processor
        metrics_path: /actuator/prometheus
        static_configs:
          - targets:
              - order-stream-processor:8080

In Kubernetes, ServiceMonitor/PodMonitor or platform service discovery is usually used instead of static targets. Scrape configs must target the exact port and endpoint exposed by the container.

## 4. Health endpoints do not replace stream metrics

A health indicator answers a question close to: are the application or its dependencies considered UP? It does not tell you whether backlogs are growing, processing latency is breaching SLOs, or DLQ rates are high.

Spring Boot provides the health endpoint and readiness/liveness probes. Specific binders may add health indicators, though displayed components and semantics depend on the binder/version/configuration. Inspect your application's actual health response; do not assume every broker or binding is checked automatically.

A sensible division of responsibilities:

- **Liveness:** the process is alive and does not require a restart to recover. Do not fail liveness merely because the broker temporarily disconnects if that causes Kubernetes to restart pods repeatedly and worsen the outage.
- **Readiness:** whether the instance can accept traffic/take on work. If consumers cannot connect to the broker or are not ready to receive messages, readiness can reflect that according to application policy.
- **Stream health metrics:** lag, backlog, error rate, processing duration, and DLQ rate.
- **Broker health:** broker exporters/management APIs reporting cluster, queue, partition, subscription, and resource state.

If a custom health indicator is needed for a business condition, keep it lightweight and bounded by timeouts. Avoid expensive broker queries inside every health check.

## 5. Recording application metrics with Micrometer

Application metrics answer how functions received and processed messages. A baseline metric set might include:

| Metric | Type | Meaning |
|---|---|---|
| stream.events.received | Counter | Events entering the processing boundary |
| stream.events.processed | Counter | Events completed at the completion boundary |
| stream.events.failed | Counter | Failed processing attempts |
| stream.processing | Timer | Processing duration per event |
| stream.events.retried | Counter | Retries observed by the application |
| stream.dlq.published | Counter | Events routed to the DLQ |
| stream.inflight | Gauge | Events currently processing concurrently |

Counters increase monotonically and have rates computed in Prometheus. Timers record counts and duration distributions, suited for p50/p95/p99. Gauges reflect current values, such as active in-flight work; do not use a Gauge to approximate broker lag when source metrics can be fetched directly from the broker.

Example service recording duration and outcomes:

    @Component
    public class StreamMetrics {
        private final MeterRegistry registry;

        public StreamMetrics(MeterRegistry registry) {
            this.registry = registry;
        }

        public void processed(String binding, Duration duration) {
            registry.counter(
                    "stream.events.processed",
                    "binding", binding
            ).increment();

            registry.timer(
                    "stream.processing",
                    "binding", binding
            ).record(duration);
        }

        public void failed(String binding, String category) {
            registry.counter(
                    "stream.events.failed",
                    "binding", binding,
                    "category", category
            ).increment();
        }
    }

Record metrics at the defined boundary, such as after business changes commit successfully. If a function has multiple steps, record separate metrics for validation, database commit, and output publish to isolate failures.

Example wrapping a service call:

    public void handle(OrderCreated event) {
        Timer.Sample sample = Timer.start(registry);
        try {
            orderService.apply(event);
            sample.stop(registry.timer(
                    "stream.processing",
                    "binding", "orders-in"
            ));
            registry.counter(
                    "stream.events.processed",
                    "binding", "orders-in"
            ).increment();
        } catch (RuntimeException ex) {
            registry.counter(
                    "stream.events.failed",
                    "binding", "orders-in",
                    "category", classify(ex)
            ).increment();
            throw ex;
        }
    }

This snippet is an application-layer instrumentation pattern. If the framework/binder already instruments part of the operation, avoid double-counting the same event. Exceptions are rethrown so Spring Cloud Stream's retry/error handlers run as configured; never swallow exceptions just to make success/failure counters look clean.

## 6. Controlled metric naming and tagging

Metric names should be stable, include units where appropriate, and describe a measurable event. Tags filter and group along dimensions with bounded value sets.

Usually suitable tags:
- application or service.
- environment and region.
- binding name.
- broker type.
- static topic/queue.
- known consumer group or subscription.
- error category from a small enum set.

Keep high-cardinality values out of tags:
- eventId, orderId, customerId.
- traceId, spanId.
- message payloads or exception messages.
- exact timestamps.
- URLs containing IDs or query strings.

Each tag combination can create a separate time series. Attaching eventId to metrics can scale series counts with event volume and consume excessive Prometheus RAM, CPU, and storage. Use logs or traces to locate specific events; use metrics for aggregation.

Errors should be grouped into stable categories such as validation, timeout, dependency, serialization, and unknown. Never use exception messages as tags because their text often varies per request and has unbounded cardinality.

## 7. Histograms and latency percentiles

Average latency can mask a small group of very slow messages. Timer histograms enable computing percentiles and distributions. With Micrometer, configure histograms on timers appropriately for your registry version:

    management:
      metrics:
        distribution:
          percentiles-histogram:
            stream.processing: true

Prometheus can collect timer buckets to compute p95/p99. A p95 query by binding:

    histogram_quantile(
      0.95,
      sum by (le, binding) (
        rate(stream_processing_seconds_bucket[5m])
      )
    )

Prometheus metric names are converted from Micrometer names and the Timer's base unit; the example above assumes a timer named `stream.processing` is exported as `stream_processing_seconds`. Confirm actual names at `/actuator/prometheus` before building dashboards.

Percentile histograms carry storage overhead. Enable them only on key timers, pick sensible buckets, and avoid excessive tag dimensions.

## 8. Monitoring each broker with native metrics

Application metrics cannot replace broker metrics. Install exporters or integrate the monitoring tooling provided by your broker platform.

| Broker | Key metrics | Questions |
|---|---|---|
| Kafka | Consumer group lag, offsets, partitions, under-replicated partitions, ISR, request latency, broker disk | Are consumers keeping up with topics? Are partitions/brokers healthy? |
| RabbitMQ | Ready messages, unacknowledged messages, consumer count, publish/deliver/ack rates, connections/channels, memory/disk alarms | Which queue is backing up? Are consumers acking messages? |
| Pulsar | Subscription backlog, unacked messages, connected consumers, backlog age, topic/partition stats, broker/bookie health | Are subscriptions draining backlog? Are consumers connected? |

Do not use one generic metric name across all three brokers. Kafka lag is typically computed by exporters from log end offset and committed offset; RabbitMQ queue depth splits into ready and unacked; Pulsar backlog follows subscription and acknowledgment semantics. Choose the official exporter/metrics matching your broker version and deployment.

### 8.1. Kafka

For Kafka, group dashboards by topic, partition, and consumer group. Common panels include:
- Current lag per partition and total lag per group.
- Rate of lag increase/decrease.
- Record input rate and consumer processing rate.
- Partitions lacking consumer assignment or consumers currently rebalancing.
- Under-replicated partitions and offline partitions.
- Request latency, broker disk, and network.

High lag that is shrinking may just be a temporary backlog after a traffic spike. Low lag that steadily climbs signals under-provisioned consumers. Watch both lag magnitude and lag trend.

### 8.2. RabbitMQ

For RabbitMQ, distinguish:
- **Ready:** messages waiting to be delivered to a consumer.
- **Unacked:** messages delivered to consumers but not yet acknowledged.
- **Consumers:** number of registered consumers.
- **Publish/deliver/ack rates:** ingress, delivery, and acknowledgment rates.
- **Redelivery:** messages delivered again.
- **Queue age/depth:** depth and age of waiting messages.
- **Broker alarms:** memory/disk watermarks, connection/channel pressure.

Rising ready counts indicate consumers may lack capacity or be inactive. Prolonged rising unacked counts can mean slow consumers, hung consumers, or overly large prefetch. If ack rate stays low while deliver rate is high, inspect processing and acknowledgment handling.

### 8.3. Pulsar

For Pulsar, observe per topic and subscription:
- Subscription backlog.
- Oldest unacked message or backlog age when exposed by the broker/exporter.
- Consumer count and connection state.
- Message rate in/out.
- Redeliveries and acknowledgment timeouts.
- Partition distribution, broker, and BookKeeper/bookie health.
- Storage usage and ledger/managed-ledger metrics.

Backlogs may exist intentionally when subscriptions consume on a schedule. Base alerts on backlog age, growth trends, and processing SLOs rather than a single raw count.

## 9. Overview dashboard for the entire stream

A system-level dashboard should help on-call engineers spot within seconds which stream needs attention. Suggested layout:

| Row | Panel | Displays |
|---|---|---|
| 1 | Overall status | Health, active binding count, critical alert count |
| 1 | Input vs processed rate | Inbound events and completed events over time |
| 1 | Success/error ratio | Error rate per service/binding |
| 2 | Processing latency | p50, p95, p99 |
| 2 | Consumer lag/backlog | Total and top bindings/groups/queues with backlogs |
| 2 | Oldest message age | Age of the longest-waiting message |
| 3 | Retry and DLQ | Retry rate, DLQ rate, and new DLQ messages |
| 3 | Broker health | Kafka/RabbitMQ/Pulsar status and resources |
| 4 | JVM/runtime | Heap, GC pauses, CPU, threads, connection pools |
| 4 | Deployments | Annotations for releases, restarts, and config changes |

The overview dashboard should include filter variables for environment, service, binder, binding, and consumer group. Do not turn individual event IDs into dashboard rows; use logs/traces when investigating a single event.

## 10. Per-binding detail dashboard

Each binding can have its own dashboard or panel row showing:
- Destination and binder type.
- Input rate and output rate.
- Processed/failed/retried counts.
- p95/p99 processing time.
- Lag/backlog and oldest message age.
- Consumer instances/concurrency.
- DLQ destination and DLQ rate.
- Last successful processing timestamp.
- Deployment version.

When a function has multiple inputs/outputs, do not collapse all throughput into one line. For instance, a function joining two inputs must monitor each input's rate separately; one input stopping can stall output even while the other input continues growing.

Across multi-stage pipelines, keep a shared event correlation ID in logs/traces to follow an event across bindings. Dashboards still aggregate by binding; correlation IDs are used strictly for querying logs/traces.

## 11. Building alerts from SLIs

Alerts should fire when there are signs of user impact or risk of breaching SLOs. Do not alert on every metric fluctuation. A solid rule includes:
- Clear measured condition.
- Threshold and sustained duration (`for`).
- Binding/consumer group scope.
- Severity level.
- Recipient or alerting channel.
- Runbook pointing to the first investigation step.

Example initial thresholds:

| Alert | Illustrative condition | Severity |
|---|---|---|
| Processing error ratio high | Error ratio above 2% continuously for 10 minutes with sufficient sample traffic | warning |
| Processing error critical | Error ratio above 10% for 5 minutes | critical |
| Consumer lag rising | Lag climbing continuously and catch-up time exceeds SLO | warning/critical |
| Oldest message too old | Oldest message exceeds 2 minutes | warning |
| DLQ receives messages | New messages entering DLQ on a critical stream | warning |
| No successful processing | Input present with no completed events over expected window | critical |
| Broker unavailable | Prolonged broker/connection unavailability | critical |
| State restore too long | Kafka Streams task restoration exceeds startup/recovery objective | warning |

Tune thresholds to traffic, batch sizes, processing duration, and SLOs. Low-traffic streams may need longer windows or heartbeat/source-activity checks; real-time streams may need shorter windows.

## 12. PromQL for application metrics

Assume the application exports the custom metrics introduced above. 5-minute error ratio:

    sum(rate(stream_events_failed_total[5m]))
    /
    clamp_min(
      sum(rate(stream_events_processed_total[5m])) +
      sum(rate(stream_events_failed_total[5m])),
      1
    )

This query is only an example assuming `processed` and `failed` are mutually exclusive and counted at the same completion boundary. If failed attempts retry and eventually succeed, decide whether the SLI measures attempts or final events; separate metrics may be needed for attempts vs. unique events.

Completed event rate:

    sum by (binding) (
      rate(stream_events_processed_total[5m])
    )

Error rate by binding:

    sum by (binding) (
      rate(stream_events_failed_total[5m])
    )

p95 processing time:

    histogram_quantile(
      0.95,
      sum by (le, binding) (
        rate(stream_processing_seconds_bucket[5m])
      )
    )

DLQ ingress rate:

    sum by (binding) (
      rate(stream_dlq_published_total[5m])
    )

Metric names are examples following Micrometer Prometheus export conventions. Verify actual names, labels, and units before using them in production. Broker exporter lag/backlog metrics vary in name across exporters; substitute the real metrics exposed by your platform.

## 13. Example Prometheus alert rules

Rules can be defined as follows:

    groups:
      - name: spring-cloud-stream
        rules:
          - alert: StreamProcessingErrorRatioHigh
            expr: |
              (
                sum(rate(stream_events_failed_total[5m]))
                /
                clamp_min(
                  sum(rate(stream_events_processed_total[5m])) +
                  sum(rate(stream_events_failed_total[5m])),
                  1
                )
              ) > 0.02
            for: 10m
            labels:
              severity: warning
            annotations:
              summary: Stream processing error ratio is high
              runbook: /runbooks/stream-processing-errors

          - alert: StreamDlqTrafficDetected
            expr: sum(rate(stream_dlq_published_total[5m])) > 0
            for: 2m
            labels:
              severity: warning
            annotations:
              summary: Messages are being sent to a dead-letter destination
              runbook: /runbooks/stream-dlq

These are sample rules for custom metrics. In production, add appropriate service/environment label filters and check traffic denominators. Do not apply a single global error threshold across every binding when criticality and volumes differ.

### 13.1. Alerting on missing traffic

Do not alert merely because processed rate equals 0. There may simply be no new events. Require evidence that the source should have emitted data, such as:
- Producer heartbeat or source event rate greater than 0.
- A clear active schedule for event emission.
- Broker receiving messages while consumers fail to process them.
- Time since last successful processing exceeding the expected window.

For example, alert when input rate is greater than 0 while processed rate remains 0 for 5 consecutive minutes. This condition is far more meaningful than checking `processed == 0` alone.

## 14. Lag alerts and catch-up time

Lag is the number of unprocessed messages/records. A high lag number alone does not reveal exact wait time; combine processing rate and input rate.

If lag is L, processing rate is P, and input rate is I:
- If P <= I, consumers are not catching up; the backlog tends to keep growing.
- If P > I, catch-up time is roughly L / (P - I), assuming relatively steady rates.
- If traffic is bursty, watch trends and age percentiles instead of trusting an instantaneous division.

For Kafka, use lag by consumer group and partition. For RabbitMQ, use ready/unacked and message age. For Pulsar, use subscription backlog and backlog age. Do not compare these figures directly across brokers when semantics differ.

Lag alerts should consider:
- Lag exceeding a threshold over a sustained window.
- Lag rising continuously rather than draining.
- Oldest message age breaching SLO.
- Processing rate remaining below input rate for a prolonged period.
- Consumer count dropping to 0 or repeated rebalances.

## 15. Alertmanager and alert routing rules

Prometheus evaluates alert rules; Alertmanager groups, deduplicates, routes, and delivers alerts to on-call channels. A solid configuration should:
- Group by alert name, environment, service, and binding.
- Inhibit downstream alerts when a larger broker/cluster alert already covers the root cause.
- Set appropriate repeat intervals to avoid noisy repetition.
- Route critical alerts to on-call and warnings to operations channels.
- Apply time-bounded silences for scheduled maintenance.
- Include dashboard links and runbooks in annotations.

Do not send one notification per partition when an outage impacts an entire consumer group. Group by consumer group/topic and keep partition labels in details for investigation.

## 16. Combining metrics, logs, and traces

The three signals complement each other:
- **Metrics** provide trends, rates, latency, and alerting.
- **Logs** explain a specific execution, exception, and metadata.
- **Traces** follow an event's path across multiple services/bindings.

Include helpful fields in structured logs:
- service, environment, binding.
- event type and event ID (in logs, never as metric tags).
- correlation ID/trace ID.
- static destination or consumer group.
- processing outcome and error category.
- retry attempt if applicable.

Never log sensitive payloads, tokens, credentials, or full messages without a protection policy. Trace context can propagate through headers as supported by instrumentation/binders; verify actual propagation as events traverse Kafka, RabbitMQ, and Pulsar. Do not assume trace context survives every converter or broker intact.

## 17. Runbooks when alerts fire

Runbooks must help on-call responders pinpoint root causes before mutating the system.

### 17.1. Processing error ratio rising

1. Identify affected service, environment, and binding.
2. Compare input rate, processed rate, failed rate, and retry rate.
3. Inspect error categories and sample logs/traces to find the root exception.
4. Check recent deployments, schema changes, and external dependencies.
5. Determine whether the error is poison data, schema mismatch, timeout, or broker connectivity.
6. If failing messages are retried, inspect retry budgets and DLQ policies; avoid infinite retries.
7. After fixing the root cause, verify error rate drops and backlogs begin draining.

### 17.2. Consumer lag or backlog rising

1. Identify the topic/queue/subscription and consumer group.
2. Compare input rate against processing/ack rate.
3. Check consumer count, instance restarts, rebalances, and connections.
4. Check downstream database/API latency and thread/connection pools.
5. Check broker resources: disk, memory, network, and partition health.
6. Scale consumers only when partition/queue semantics and downstream capacity permit.
7. Watch backlog age and catch-up time after making changes.

### 17.3. New messages in DLQ

1. Identify the source binding, DLQ destination, and error category.
2. Inspect event schemas, payload versions, and exceptions.
3. Determine whether messages need data fixes or code/config fixes.
4. Preserve event IDs and metadata for reconciliation.
5. Never bulk-replay before consumers are idempotent and the root cause is fixed.
6. Replay in controlled batches while monitoring duplicates and backlogs.
7. Verify messages are processed or remain quarantined with a documented reason.

## 18. Testing dashboards and alerts

Dashboards and alerts are configuration that must be tested too. Recommended checks:
- Verify Prometheus scrape targets are UP and metrics appear after app startup.
- Send successful, failing, and retried events to verify counters/timers increment properly.
- Generate a backlog in a test environment to verify lag and backlog age panels.
- Route a message to the DLQ to confirm alerts trigger.
- Run `promtool check rules` to validate rule syntax.
- Run `promtool test rules` with fixtures to verify thresholds and `for` durations.
- Verify Alertmanager routing, grouping, inhibition, and runbook links.
- Trigger a test alert in staging to verify notifications reach the right team.

Never induce backlogs or disconnect brokers in production just to test alerts. Use staging or scoped, time-boxed failure testing.

## 19. Common observability design mistakes

| Issue | Consequence | Improvement |
|---|---|---|
| Monitoring only CPU and memory | Misses lag or stuck messages | Add input/output rates, backlog age, errors, and DLQ |
| Relying solely on health UP | Process looks healthy while stream makes no progress | Monitor processing progress and broker metrics |
| Alerting whenever throughput is 0 | False alerts when source emits no data | Combine source activity, schedules, and input rate |
| Watching only total lag | One partition/queue may be bottlenecked | Drill down by partition, queue, or subscription |
| Using event ID as a metric label | Cardinality explodes rapidly | Put event ID in logs/traces |
| Watching only average latency | Tail latency is hidden | Track p95/p99 via histograms |
| Alerts without runbooks | On-call wastes time finding first steps | Add dashboards, owners, and investigation steps |
| Scaling consumers immediately on high lag | Can overload databases/downstream | Check bottlenecks and capacity first |
| Uncontrolled DLQ replay | Duplicates or triggers new backlogs | Ensure idempotency, batch replay, and monitoring |
| Exposing Actuator unprotected | Leaks operational details or sensitive endpoints | Restrict endpoints and enforce access control |

## 20. Observability rollout roadmap

Roll out in stages:

1. **Define SLIs/SLOs:** agree on completion boundaries, latency objectives, and backlog age.
2. **Enable Actuator/Micrometer:** expose health and Prometheus endpoints in a controlled manner.
3. **Add application metrics:** received, processed, failed, retry, DLQ, and processing timers.
4. **Collect broker metrics:** Kafka lag, RabbitMQ queue metrics, or Pulsar subscription backlog.
5. **Build overview dashboards:** input/output, errors, latency, backlog, DLQ, and broker health.
6. **Build detail dashboards:** drill down by service, binding, and topic/queue/group.
7. **Create alerts:** error ratio, lag/age, DLQ, broker availability, and no-progress with active input.
8. **Write runbooks:** every alert has an owner, investigation steps, and recovery verification.
9. **Test alerts:** `promtool`, staging traffic, and notification routing.
10. **Review periodically:** adjust thresholds, histogram buckets, retention, and cardinality against live load.

## 21. Pre-production checklist

- [ ] Every stream has clear SLIs/SLOs and completion boundaries.
- [ ] Per-binding metrics exist for received, processed, failed, retry, and DLQ.
- [ ] Timer histograms exist to observe p95/p99 processing latency.
- [ ] Metric tags use only low-cardinality dimensions.
- [ ] Actuator exposes only needed endpoints and is secured.
- [ ] Prometheus scrape targets work and metric names are verified.
- [ ] Broker exporters/native metrics are configured for Kafka, RabbitMQ, or Pulsar.
- [ ] Dashboards display input/output rates, errors, latency, lag/backlog, oldest age, and DLQ.
- [ ] Drill-downs exist per binding, consumer group, queue, or subscription.
- [ ] Alerts are tied to SLOs, have `for` durations, and avoid false alerts when sources are idle.
- [ ] Alerts include severity, owner, dashboard links, and runbooks.
- [ ] Alertmanager grouping/inhibition/silences are configured.
- [ ] Logs include correlation/event IDs without exposing payloads or secrets.
- [ ] Trace propagation is verified across brokers and service boundaries.
- [ ] Dashboards and alerts are tested in staging.
- [ ] Safe procedures exist for scaling consumers, handling DLQs, and replaying.

A well-observed Spring Cloud Stream system shows how data flows through each binding, whether consumers keep up, and whether errors threaten SLOs. Combining application metrics with native broker lag/backlog, per-stream dashboards, and runbook-backed alerts helps operations teams detect bottlenecks early, handle errors safely, and confirm recovery.

## References

- [Spring Boot Actuator — Metrics and Endpoints](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Micrometer — Concepts and Instrumentation](https://docs.micrometer.io/micrometer/reference/concepts.html)
- [Prometheus — Metric Types](https://prometheus.io/docs/concepts/metric_types/)
- [Prometheus — Alerting Rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/)
- [Grafana — Dashboards and Alerting](https://grafana.com/docs/grafana/latest/alerting/)
- [Spring Cloud Stream Reference](https://docs.spring.io/spring-cloud-stream/reference/)
