# KafkaTemplate metrics

In Spring Kafka, `KafkaTemplate` is the commonly used API for sending records to Kafka. When operating a producer, simply knowing whether the application called `send()` successfully is not enough. It is necessary to measure the time spent sending and waiting for broker acknowledgement, the number of send failures, the retry rate, batch sizes, buffer utilization, and signals indicating that the broker or network is slowing the producer down.

KafkaTemplate metrics provide visibility into send operations at the application level. When combined with native Kafka producer metrics, broker metrics, and consumer lag, operations teams can distinguish whether an error lies in the sending code, the producer client, the broker, or downstream processing. These metrics also help evaluate the impact of changes to `acks`, batching, compression, timeouts, and partition counts.

## 1. Metric layers to distinguish

A Spring Kafka system has multiple observability layers. You should not lump everything into a single "Kafka latency" metric because each layer measures a different time span.

| Observability layer | Source | Question answered |
|---|---|---|
| KafkaTemplate timer/observation | Spring Kafka and Micrometer | How long does a single send call from the application take to complete or fail? |
| Kafka producer client metrics | Kafka client used inside the template | To what extent is the producer waiting on the broker, retrying, batching, or running out of buffer? |
| Broker metrics | Kafka broker/JMX or exporter | Is the broker overloaded, losing replicas, throttling, or experiencing slow I/O? |
| Consumer metrics | Listener container, Kafka consumer client | Are records being consumed in time, and is consumer lag increasing? |
| Business metrics | Business code | Does the published event lead to a business outcome within SLA? |

For example, the KafkaTemplate timer may increase because the producer has to wait for broker acknowledgement. However, it can also increase due to producer buffer pressure or slow networking. Conversely, a low send timer does not prove the event has been processed by a consumer; the record may sit in the topic for a long time.

## 2. What do KafkaTemplate metrics measure?

KafkaTemplate sends records asynchronously and receives results via callbacks/futures. Template-level metrics typically record the duration of the send operation from start until the send result completes, along with the success or failure status.

In traditional Spring Kafka Micrometer timer configurations, the meter is typically named `spring.kafka.template` with tags describing the template, result, and exception. Common tags include:

- `name`: the name or identifier of the KafkaTemplate.
- `result`: the outcome of the send, typically distinguishing success and failure.
- `exception`: the exception type or a value indicating no exception.

Exact meter names, tags, and representations may vary by Spring Kafka version and how instrumentation is enabled. Check the actual meters in the registry rather than relying on a dashboard copied from another version.

Timers report count, total time, and max time; when histograms are enabled, the backend can compute percentiles such as p95 or p99. These measurements are useful for answering:

- How long is sending a record taking at p50, p95, and p99?
- Did the send failure rate increase after a deployment?
- Is a specific KafkaTemplate behaving differently from the other templates?
- Is send duration increasing concurrently with retries or producer buffer waits?

The timer does not measure consumer processing time, does not confirm that business side effects have committed, and does not replace Kafka broker metrics.

## 3. Enabling traditional Micrometer metrics

Spring Kafka supports Micrometer timers for KafkaTemplate. When the application has a suitable Micrometer registry, the template can record send duration and result tags. You can enable it and add stable tags when configuring the template manually:

~~~java
@Bean
KafkaTemplate<String, OrderEvent> orderKafkaTemplate(
        ProducerFactory<String, OrderEvent> producerFactory) {

    KafkaTemplate<String, OrderEvent> template =
            new KafkaTemplate<>(producerFactory);

    template.setMicrometerEnabled(true);
    template.setMicrometerTags(Map.of(
            "producer", "orders"));

    return template;
}
~~~

The example above illustrates template configuration according to the API of Spring Kafka versions that support Micrometer timers. Check the API of the version you are using; some newer versions prefer Micrometer Observation and may differ in configuration.

Additional tags should have a bounded set of values, such as the producer stream name or business category. Do not add `orderId`, `customerId`, event id, correlation id, or message key as metric tags. Each new tag value can create a separate time series and cause cardinality to explode quickly.

If the application uses multiple KafkaTemplates, assign meaningful bean names or identifying tags to distinguish producers. Do not create a new template per request or per tenant; doing so increases the number of producer clients, connections, resources, and meters to manage.

## 4. Micrometer Observation and tracing

Starting with Spring Kafka 3.0, KafkaTemplate supports Micrometer Observation. Observation provides a unified model for recording metrics and creating traces when the application has corresponding tracing configuration. This is often the right choice for modern Spring applications because a send operation can be linked to the trace of the incoming request or processing flow that produced the event.

Observation can be enabled via Spring Boot configuration:

~~~yaml
spring:
  kafka:
    template:
      observation-enabled: true
~~~

When creating a template manually, it can be configured directly:

~~~java
@Bean
KafkaTemplate<String, OrderEvent> orderKafkaTemplate(
        ProducerFactory<String, OrderEvent> producerFactory,
        ObservationRegistry observationRegistry) {

    KafkaTemplate<String, OrderEvent> template =
            new KafkaTemplate<>(producerFactory);
    template.setObservationEnabled(true);
    template.setObservationRegistry(observationRegistry);
    return template;
}
~~~

If Spring Boot already auto-configures KafkaTemplate and ObservationRegistry, prefer configuring via properties rather than creating an unnecessary second template. Exact property names and APIs may differ across Spring Boot/Spring Kafka versions; verify the actual dependency version.

Observation can produce timers and spans depending on the connected registries/handlers. Enabling Observation does not mean traces will automatically appear in your backend if the application has not configured a tracing exporter. Metrics and tracing also serve two different purposes:

- Metrics aggregate trends and rates across many sends.
- Traces help follow a specific request across components and points in time.

Do not turn event id or customer id into metric labels just to look up a single event. Keep detailed identifiers in traces or controlled logs, while metrics should use low-cardinality tags.

### 4.1. Choosing between traditional timers and Observation

Traditional timers focus on send duration and outcome. Observation provides a broader integration point for metrics and tracing. Within an application, choose the configuration based on your Spring Kafka version and observability requirements to avoid creating two duplicate measurement sets.

If Observation is enabled, Spring Kafka may use Observation instead of the traditional Micrometer timer for that operation. Do not assume both sets of meters will appear. Verify the actual meter names, tags, and traces after starting the application.

## 5. Native Kafka producer metrics

KafkaTemplate uses the Kafka producer client underneath. The producer client exposes many metrics describing internal performance. This layer is critical when the template-level timer increases without an obvious cause.

Commonly observed metrics include:

| Kafka client metric | Meaning | How to interpret |
|---|---|---|
| `record-send-rate` / `record-send-total` | Rate and total count of records sent | Determines whether the producer is emitting data and how throughput changes |
| `record-error-rate` / `record-error-total` | Rate and total count of send errors | Detects broker, serialization, or request errors |
| `record-retry-rate` / `record-retry-total` | Rate and total count of retries | Rising retries may signal an unstable broker or network |
| `request-latency-avg` / `request-latency-max` | Request latency at the producer client | Reflects how long requests take the broker to process/respond from the client's view |
| `request-rate` / `request-total` | Rate and total count of requests | Combine with batch size to evaluate batching efficiency |
| `batch-size-avg` / `batch-size-max` | Average and maximum batch size | Small batches can increase request overhead when traffic is low or spread across many partitions |
| `compression-rate-avg` | Observed compression ratio | Evaluates compression effectiveness for the workload |
| `bufferpool-wait-ratio` | Ratio of time the producer waits on the buffer pool | Rising values may indicate buffer pressure |
| `bufferpool-wait-time-total` | Total buffer wait time | Used to detect the producer blocking when buffer space is exhausted |
| `buffer-available-bytes` | Available buffer capacity | Helps determine whether the producer is close to exhausting its buffer |
| `outgoing-byte-rate` | Outgoing byte rate | Tracks network bandwidth generated by the producer |
| `produce-throttle-time-avg` | Average throttling time | May indicate broker quotas are throttling the producer |

Metric names and the available metric set can vary by Kafka client version. Metrics are also typically scoped by client, node, or connection. Preserve the dimensions provided by Kafka to identify the relevant broker/producer, but do not add arbitrary high-cardinality tags.

### 5.1. Reading metrics by group

**Send and error group:** `record-send-rate`, `record-error-rate`, and `record-retry-rate` show how fast the producer is sending and whether it is encountering errors or retries. Retries rising before errors rise can be a sign that the broker is starting to slow down or requests are frequently timing out before eventually succeeding.

**Latency group:** `request-latency-avg` and `request-latency-max` describe request timing at the Kafka client. Averages can hide very slow requests, so combine max, latency distributions if collected, and the template-level timer.

**Batching and compression group:** `batch-size-avg` together with `compression-rate-avg` help evaluate whether the producer is accumulating enough data and whether compression is effective. Small batches are not automatically a problem; on low-traffic streams, small batches may be normal.

**Buffer group:** `bufferpool-wait-ratio`, `bufferpool-wait-time-total`, and `buffer-available-bytes` help detect when the producer cannot push data out as fast as the application produces it. When buffer waits rise, check broker latency, network, in-flight requests, and send rate before simply increasing `buffer.memory`.

## 6. Accessing metrics from KafkaTemplate

KafkaTemplate provides access to the producer client's metrics via the `metrics()` API in supported versions:

~~~java
Map<MetricName, ? extends Metric> producerMetrics =
        kafkaTemplate.metrics();

producerMetrics.forEach((name, metric) -> {
    Object value = metric.metricValue();
    log.debug("Kafka producer metric: name={}, value={}",
            name.name(), value);
});
~~~

This snippet only illustrates how to read metrics. In a production application, you should not log all metrics on every request or create a new meter per metric on every call. Use Micrometer, JMX, or your existing metrics collection system to scrape periodically. Reading `metrics()` is useful for diagnostics or internal tooling, but does not replace a standard metrics pipeline.

ProducerFactory may manage or share a producer depending on configuration and usage. Therefore, when reading metrics, understand which producer client a metric belongs to and its scope. If multiple KafkaTemplates share a factory, some client metrics may reflect the aggregate activity of the shared producer rather than a single template bean.

## 7. Exposing metrics via Spring Boot Actuator

In a Spring Boot application, Actuator provides endpoints for health checks and exposing metrics. To export metrics to Prometheus, the application typically needs Actuator and the Prometheus registry:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
~~~

Example configuration to expose endpoints:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
~~~

After startup, the Prometheus endpoint is typically at `/actuator/prometheus`. Verify that the endpoint is exposed in the deployment environment and protected with appropriate authentication, network policy, or reverse proxy. Never expose all Actuator endpoints publicly to the Internet.

Metrics can be exported to Prometheus, OTLP, or another backend depending on the registry and observability infrastructure. You do not have to force every application to use the same backend; what matters is keeping metric names, tags, and dashboard conventions consistent.

### 7.1. Verifying that meters are created

Once KafkaTemplate sends a record, check `/actuator/metrics` or the registry to confirm the timer/observation has appeared. For example, you can check the `spring.kafka.template` meter if the application uses traditional Micrometer timers. With Observation, the meter name and tags may differ according to its conventions.

If the meter is missing:

1. Verify that the Micrometer and registry dependencies are on the classpath.
2. Verify that the active template has instrumentation configured.
3. Send a test record and wait for the callback/future to complete.
4. Check the Observation or Micrometer timer configuration for your Spring Kafka version.
5. Check whether any meter filter or export configuration is excluding the meter.
6. Verify you are checking the right application instance and the right registry/endpoint.

Do not conclude that metrics are broken just because you looked up the wrong meter name or queried the wrong tag. Inspect the application's actual list of meters.

## 8. Tags and cardinality

Tags allow slicing metrics by meaningful attributes. For example, `producer=orders` or `result=failure` can help identify which sending flow is failing. However, each tag combination can create a separate time series.

Usually appropriate tags:

- Template names with a small set of values defined at application startup.
- Stable service or producer stream names.
- Send result (success/failure).
- Exception type by class name if the set of exception types is bounded.
- Topics with a finite set of names that are not dynamically generated without bound.

Inappropriate tags:

- `orderId`, `customerId`, `userId`, or event id.
- Message keys that can have millions of values.
- Correlation id or trace id.
- Exception messages containing dynamic content.
- Full URLs or arbitrary tenant names when tenant count is large.

For example, if a service processes 500,000 orders per day and adds `orderId` as a tag, the registry can create hundreds of thousands of series. This increases memory usage, scrape load, storage cost, and query latency. Use logs or traces to look up a specific order.

If you need to distinguish business types, use a categorizing attribute with a small value set such as `event_type=order_created` or `event_type=order_cancelled`, after considering the number of tag combinations. Never pull arbitrary values from the payload to create labels.

## 9. Histograms and percentiles

Default timers may provide count, total time, and max. To observe p95 or p99, the backend needs suitable distribution data, typically via histograms or percentile configuration.

Histograms are useful when comparing tail latency across instances and querying percentiles in Prometheus. In return, each bucket and tag combination increases the number of series. Enable histograms only for important meters and keep tags limited.

For example, you can configure histograms for the KafkaTemplate send meter via Micrometer/Spring Boot distribution configuration. Exact property syntax depends on the Spring Boot version and actual meter name; verify the meter name after enabling the timer or Observation before configuring.

Do not look only at average latency. If the average is 10 ms while p99 is 2 seconds, a small subset of requests still suffers a very bad experience. Tracking p50, p95, and p99 alongside request rate and error rate helps determine whether a change improved most requests or only shifted the mean.

## 10. Building a KafkaTemplate dashboard

A producer dashboard should answer three questions: can the producer send, how long does sending take, and what is slowing it down?

A useful dashboard may include:

| Panel | Metrics | Purpose |
|---|---|---|
| Send rate | Successful sends over time | Track publish throughput |
| Send duration | p50/p95/p99 of the KafkaTemplate timer | Observe application-level latency |
| Error rate | Send error count and error rate | Detect producer send failures |
| Retry rate | Kafka client retry rate | Detect requests being retried |
| Request latency | Kafka producer request latency | Distinguish client vs. broker slowness |
| Batch size | Average batch size | Check batching efficiency |
| Compression | Compression rate | Track compression effectiveness |
| Buffer pressure | Buffer wait ratio/time and available bytes | Detect producer buffer bottlenecks |
| Throttling | Produce throttle time | Detect quota throttling |

If there are multiple templates, allow filtering by template name or stable producer tag. Keep the same time range when comparing latency, errors, and retries to see correlations.

### 10.1. Prometheus query examples

Prometheus metric names are usually normalized from Micrometer meters; for example, a timer may be exported as `spring_kafka_template_seconds_*`. The final name depends on instrumentation and registry, so check `/actuator/prometheus` before using queries.

With a histogram timer, a percentile query looks like:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(spring_kafka_template_seconds_bucket[5m])
  )
)
~~~

The timer recording rate can be estimated with:

~~~promql
sum(rate(spring_kafka_template_seconds_count[5m]))
~~~

The queries above are illustrative examples. If the actual meter has a different name or tags distinguishing template/result, adjust the queries to preserve the necessary dimensions and avoid aggregating producers with different behaviors together.

## 11. Alerting on producer metrics

Alerts should focus on signals that affect event publishing capability or SLAs, rather than paging simply because a metric fluctuated for a few seconds.

Conditions worth alerting on:

- Send error rate rising above baseline for a sustained period.
- p95 or p99 send duration exceeding the latency budget.
- Sustained increase in retry rate alongside rising request latency.
- Rising buffer wait ratio and dropping available buffer bytes.
- Rising produce throttle time due to quotas.
- Send rate dropping abnormally while application input traffic remains high.
- Under-replicated partitions or ISR shrinks appearing on the cluster.

An alert based solely on `record-error-rate` can miss scenarios where the producer retries and succeeds, yet latency has spiked sharply. Combining retries, request latency, and the template timer helps detect issues earlier.

Alert thresholds should be derived from the system's SLOs and baselines. Do not apply a single threshold across all topics, environments, or times of day. Use a sustained condition duration (`for` duration) to avoid flaky alerts caused by brief spikes.

## 12. Diagnosing common scenarios

### 12.1. KafkaTemplate send duration increases

Check in order:

1. Are `request-latency-avg/max` increasing at the same time?
2. Are `record-retry-rate` or `record-error-rate` increasing?
3. Is buffer wait ratio rising while buffer available is dropping?
4. Is the broker experiencing produce request latency, disk/network pressure, or throttling?
5. Are ISRs shrinking or are partition leaders changing repeatedly?
6. Did traffic spike or did key distribution create a hot partition?

If request latency and retries rise together, prioritize checking the broker, network, and ISR. If request latency is normal but buffer wait rises, the producer may be generating data faster than it can send; check in-flight requests, batching, and publish rate.

### 12.2. Send errors increase without an increase in request latency

Errors may fail fast due to authorization, missing topics, serialization failures, or invalid producer configuration. Check the exception class and logs containing correlation/event ids. Do not infinitely retry configuration or data errors because retries cannot fix the root cause.

### 12.3. Retries increase while most sends still succeed

This can be an early warning sign: the broker or network is experiencing slow or flaky requests, though the producer is still recovering. Compare retry rate against request latency, broker throttling, ISR, and network errors. If retries remain elevated, end-to-end latency may breach SLA even while the final error rate stays low.

### 12.4. Producer metrics are normal but events reach consumers slowly

The KafkaTemplate timer only measures the send operation. Check consumer lag, poll rate, listener processing time, downstream latency, and assigned partitions. Also check whether records are waiting in retry topics or being processed out of order due to non-blocking retries.

### 12.5. Metrics disappear after an upgrade

Check version changes for Spring Boot, Spring Kafka, Micrometer, and the Kafka client. Switching from Micrometer timers to Observation can change meter names or tags. Check `observation-enabled`, registry, meter filter, and dashboard queries. Do not immediately create replacement meters before determining the cause of the rename or instrumentation change.

## 13. Correlating metrics with logs and traces

Metrics show problems broadly; logs and traces help locate a specific send. When publishing events, include an event id and correlation id in the log context or message headers if the architecture supports it.

Do not put these identifiers into metric tags. Use them in structured logs or traces to look up an event. Enforce access controls and avoid logging sensitive payloads.

With Observation/tracing, a trace can connect the incoming request, the Kafka send operation, and subsequent steps if context is propagated via message headers and consumer instrumentation is configured compatibly. Do not assume trace context automatically passes through every custom serializer or intermediary system; test propagation in a realistic environment.

## 14. Testing instrumentation

Before deploying dashboards and alerts, test the instrumentation:

1. Send a valid record and verify the timer/observation is recorded.
2. Send a record to a non-existent topic or trigger an error appropriate for the test environment to verify failure metrics.
3. Simulate a slow or disconnected broker to observe retries and latency.
4. Verify that producer client metrics carry the required dimensions.
5. Verify that the Prometheus endpoint or corresponding backend scrapes the meters.
6. Verify that tags do not contain event ids, message keys, or personal data.
7. Verify that histograms and percentiles appear if the dashboard requires p95/p99.
8. Test alerts by creating controlled test conditions.

Tests should verify both sides: that metrics appear and that the send operation actually achieved the expected business outcome. A recorded timer metric does not mean the record has been processed by a consumer.

## 15. KafkaTemplate metrics operations checklist

### Instrumentation

- [ ] Spring Kafka version and Micrometer/Observation configuration approach are identified.
- [ ] The active KafkaTemplate is properly instrumented.
- [ ] Timer/observation metrics and Kafka producer client metrics are clearly distinguished.
- [ ] Both success and failure outcomes are recorded.
- [ ] Observation/tracing is enabled when needed and the registry/exporter is configured.

### Metric quality

- [ ] Send rate, duration, errors, and retries are covered.
- [ ] Request latency, batch size, compression, and buffer metrics are covered.
- [ ] Histograms are enabled if p95/p99 is needed.
- [ ] Tags use only low-cardinality values.
- [ ] Event id, customer id, order id, message key, or trace id are not used as metric tags.

### Dashboards and alerts

- [ ] Dashboards distinguish template, producer client, and broker metrics.
- [ ] Producer latency can be correlated with consumer lag.
- [ ] Alerts are based on SLOs/baselines with appropriate sustained durations.
- [ ] Metrics endpoints are secured and only necessary endpoints are exposed.
- [ ] Dashboards/queries have been verified after dependency upgrades.

## Conclusion

KafkaTemplate metrics tell you how long application-level send operations take and how they finish. Native Kafka producer metrics further explain retries, request latency, batching, compression, and buffer pressure. Micrometer timers or Observation provide the export path to Actuator and monitoring backends; tracing and logs help investigate individual events. When these layers are combined with broker metrics, consumer lag, and business metrics, operations teams can spot slow producers, distinguish broker issues from application errors, and evaluate configuration changes without confusing send duration with end-to-end business completion time.
