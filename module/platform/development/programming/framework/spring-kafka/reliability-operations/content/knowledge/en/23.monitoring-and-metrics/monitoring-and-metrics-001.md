# Micrometer consumer timers

In a Spring Kafka system, consumers must not only read records but also process them **on time, with an acceptable error rate**. A Kafka consumer group may have low lag while the listener processes each record unusually slowly; conversely, the listener may execute very fast yet still have high lag due to insufficient partition concurrency, slow broker fetches, or a producer sending too quickly. Therefore, monitoring must distinguish **listener processing time** from **consumer lag, poll rate, retry wait time, and end-to-end latency**.

Spring Kafka's **Micrometer consumer timers** measure business listener invocation duration through `Timer` instances named `spring.kafka.listener`. The framework provides this capability automatically when Micrometer integration conditions are met. Timers are split by **success** and **failure** outcomes, helping operations teams observe processing duration, listener invocation counts, and error trends.

This lesson guides how to enable, disable, and attach tags to timers; integrate Spring Boot Actuator/Prometheus; write queries; identify measurement limitations; distinguish Micrometer timers from Observation/Tracing and Kafka client metrics; and build runbooks when metrics behave abnormally.

## 1. What exactly does the timer measure?

A basic pipeline:

~~~text
Kafka broker
    |
    v
KafkaConsumer.poll() ------> Fetched records
                                  |
                                  v
                         Spring listener container
                                  |
                                  v
                       @KafkaListener invocation
                                  |
                         +--------+--------+
                         |                 |
                       Success           Exception
                         |                 |
                         v                 v
                 success Timer        failure Timer
                                  |
                                  v
                        Error handler / retry / DLT
~~~

`spring.kafka.listener` records **the duration of each listener invocation** within the scope wrapped by Spring Kafka instrumentation. It is not a measurement of the total time a record spends in Kafka, does not automatically count wait time in retry topics, and does not replace Kafka client `poll()`/fetch instrumentation.

An operational perspective:

| Question | Does the Micrometer listener timer answer it? |
|---|---|
| How long does the listener typically take to run? | Yes |
| Did each listener invocation succeed or throw an exception? | Yes, via the `result` tag |
| How many times was the listener invoked over a time range? | Can be derived from `count` |
| How many backlogged records does the consumer have? | No; requires consumer lag |
| How long has a record waited since the producer sent it? | No; requires end-to-end latency |
| Is `poll()` stuck? | Not directly; requires consumer/client metrics and monitor events |
| How many retries has a record gone through? | Not directly; requires retry metrics/headers |
| Did the database commit safely? | No; the timer only reflects the listener invocation outcome observed by the framework |

A listener that returns normally after silently swallowing a business error may be recorded in the **success** group. Therefore, the listener's success metric **does not automatically equal** the success rate of the entire business workflow.

## 2. Conditions for creating Micrometer timers

According to the Spring Kafka Reference, the listener timer feature has been supported since **Spring Kafka 2.3**. The container automatically creates and updates a `Timer` when:

1. Micrometer is present on the classpath.
2. A suitable `MeterRegistry` exists in the Spring application context; the documentation describes the single-registry condition.
3. The container property `micrometerEnabled` is enabled.
4. The application has not switched to Observation mode replacing traditional timers for the corresponding listener.

In many current versions, `ContainerProperties.micrometerEnabled` defaults to `true`, while `observationEnabled` defaults to `false`. However, "default true" **does not guarantee the timer will appear**, if the registry is not ready or the container is not created by the factory you think it is.

Dependency example:

~~~text
Micrometer API on classpath
            +
MeterRegistry able to record metrics
            +
ContainerProperties.micrometerEnabled = true
            +
Listener actually invoked
            |
            v
Spring Kafka registers/updates spring.kafka.listener Timer
~~~

If the listener is completely idle, the series may not yet appear as a metric sample depending on when the container creates the meter and the registry/exporter behavior. Do not jump to the conclusion that monitoring is broken just because a newly started topic has no traffic yet.

## 3. Timer name and default tags

Spring Kafka's listener timer is named:

~~~text
spring.kafka.listener
~~~

The framework documentation describes the default tags:

| Tag | Example | Meaning |
|---|---|---|
| `name` | `orders-consumer-0` | Container/child consumer name |
| `result` | `success` or `failure` | Listener invocation outcome |
| `exception` | `none` or `ListenerExecutionFailedException` | Exception label at the listener layer |

Two groups of timers are maintained for `success` and `failure` outcomes. In many Spring Kafka versions, the failure timer's `exception` tag reflects the `ListenerExecutionFailedException` wrapper, **not necessarily the deepest business exception class**.

Conceptual data example:

~~~text
spring.kafka.listener{
    name="orders-consumer-0",
    result="success",
    exception="none"
}

spring.kafka.listener{
    name="orders-consumer-0",
    result="failure",
    exception="ListenerExecutionFailedException"
}
~~~

If you want to track `DatabaseUnavailableException` and `InvalidOrderEventException` separately, supplement with error-handler metrics, application logs, tracing, or counters with intentional exception classification. Do not assume the `exception` tag on the timer always contains the root cause.

## 4. Concurrent container creates timers per consumer thread

With `ConcurrentMessageListenerContainer`, Spring Kafka maintains timers for each child consumer. The documentation states that the `name` tag gets a `-n` suffix appended, with `n` from 0 to `concurrency - 1`.

~~~text
@KafkaListener(id="orders-consumer", concurrency="3")
              |
              v
Concurrent container
   +-- orders-consumer-0 -> success/failure timers
   +-- orders-consumer-1 -> success/failure timers
   +-- orders-consumer-2 -> success/failure timers
~~~

This helps pinpoint a consumer thread with higher latency than the other threads. However, when calculating the error rate **across the entire listener**, you must aggregate across all child names rather than picking only `orders-consumer-0`.

These metrics can change when scaling concurrency, changing listener ID configuration, or restarting. Choose stable logical listener names so dashboards do not depend on a single child index.

Listener example:

~~~java
@KafkaListener(
    id = "orders-consumer",
    topics = "orders",
    groupId = "order-projection",
    concurrency = "3")
public void handle(OrderEvent event) {
    orderProjectionService.apply(event);
}
~~~

The listener ID and timer `name` are related, though not necessarily identical across every container/bean name configuration. Verify the actual series emitted in the registry.

## 5. Enabling and disabling timers in ContainerProperties

When using Spring Java configuration:

~~~java
@Configuration
public class OrderConsumerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    ordersListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

        factory.setConsumerFactory(consumerFactory);
        factory.getContainerProperties().setMicrometerEnabled(true);

        return factory;
    }
}
~~~

`setMicrometerEnabled(true)` makes the intent explicit even though the default in current Spring Kafka versions is `true`.

To disable legacy listener timers when there is a clear reason:

~~~java
factory.getContainerProperties().setMicrometerEnabled(false);
~~~

Notes:

- This configuration affects containers created by that factory, and does not automatically change every Kafka listener in the application.
- If there are multiple `ConcurrentKafkaListenerContainerFactory` beans, check which factory each listener is bound to.
- Enabling timers incurs instrumentation and meter series overhead, which is usually small compared to business work but still needs to be measured on large systems.
- Do not disable metrics just to silence alerts; if an alert is wrong, fix the alert/query/cardinality.
- If `observationEnabled=true`, Micrometer Observation replaces legacy timer recording; you must identify which telemetry path is actively in use.

## 6. Wiring the listener factory properly with @KafkaListener

Example listener using the factory declared above:

~~~java
@Component
public class OrdersConsumer {

    private final OrderProjectionService projection;

    public OrdersConsumer(OrderProjectionService projection) {
        this.projection = projection;
    }

    @KafkaListener(
        id = "orders-consumer",
        topics = "orders",
        groupId = "order-projection",
        containerFactory = "ordersListenerFactory")
    public void onOrder(OrderEvent event) {
        projection.apply(event);
    }
}
~~~

Merely having a factory bean in the Spring context does not mean a listener will use it; if `containerFactory` is unspecified, Spring Kafka may choose the default factory named `kafkaListenerContainerFactory` or follow application configuration.

When some listeners have timers and others do not, the first thing to check is **factory wiring**, `micrometerEnabled`, `observationEnabled`, and the active `MeterRegistry` for each path.

## 7. What statistics does a Micrometer Timer provide?

A `Timer` in Micrometer stores the measurement count and total time, along with distribution statistics depending on the registry/configuration.

| Statistic | Interpretation |
|---|---|
| `count` | Number of listener invocations recorded into the timer |
| `totalTime` / `sum` | Total duration of all invocations |
| `max` | Maximum value according to the appropriate backend window/statistics |
| Histogram buckets | Latency distribution across buckets, if enabled/supported by the exporter |
| Percentile | p50/p95/p99 percentiles if configured and supported by the backend |

If a Timer records 100 invocations with a total time of 12.5 seconds, the **average processing duration** is:

~~~text
Average invocation duration
= totalTime / count
= 12.5 seconds / 100
= 125 milliseconds
~~~

This is the average invocation duration, **not** the total latency from Kafka publish to database projection commit. A record might sit on the broker for 10 minutes and then be processed by the listener in 20 ms; the timer records about 20 ms for that invocation.

For a batch listener, one invocation can process multiple records. The Timer's `count` may represent **the number of batch listener invocations**, not the number of records. To measure record throughput in a batch, supplement with a record counter or Kafka client metrics.

## 8. Integrating Spring Boot Actuator and Prometheus

In Spring Boot, you can use Actuator together with the Micrometer Prometheus registry to export timer data.

Gradle Kotlin DSL example:

~~~kotlin
dependencies {
    implementation("org.springframework.kafka:spring-kafka")
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
}
~~~

With Maven, equivalent dependencies can be declared. There is no need to build a separate Kafka event producer to send timer data; `MeterRegistry` integrates with the exporter.

An illustrative endpoint configuration:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  metrics:
    tags:
      application: order-projection
    distribution:
      percentiles-histogram:
        spring.kafka.listener: true
~~~

In this configuration:

- `management.endpoints.web.exposure.include` determines which Actuator endpoints are accessible over the web.
- `management.metrics.tags.application` attaches a common application tag.
- `percentiles-histogram.spring.kafka.listener` requests exporting histograms for the timer of that name according to Micrometer registry capabilities.
- The Prometheus endpoint is typically `/actuator/prometheus` when properly set up.

**Security:** metrics endpoints can expose internal details about services, listener names, and exception labels. Restrict access using appropriate network policies, authentication, or scrape infrastructure; do not leave them publicly exposed without control.

Do not configure histograms for thousands of tag combinations without calculating cardinality and storage cost.

## 9. How are timers exported to Prometheus?

When the Prometheus registry exports the Micrometer Timer `spring.kafka.listener`, the metric name is typically converted to snake_case with seconds as the unit. For example:

~~~text
spring_kafka_listener_seconds_count
spring_kafka_listener_seconds_sum
spring_kafka_listener_seconds_max
~~~

If histograms are enabled and supported by the backend, there may also be:

~~~text
spring_kafka_listener_seconds_bucket
~~~

Illustrative series example:

~~~text
spring_kafka_listener_seconds_count{
  name="orders-consumer-0",
  result="success",
  exception="none",
  application="order-projection"
} 12430
~~~

Actual series depend on the Micrometer/Prometheus registry version, tag keys, custom tags, Observation mode, and scrape configuration. Do not assume meters appear before the listener runs and the registry creates corresponding samples.

`_count` is a counter incremented each time the timer records an event; use `rate(...)` to compute the rate over a time window. `_sum` is total seconds and allows calculating average duration.

## 10. Querying throughput from listener timers

PromQL example estimating invocations per second by listener child:

~~~promql
sum by (name) (
  rate(spring_kafka_listener_seconds_count[5m])
)
~~~

If you want to combine success and failure for the same logical listener, you need to know the child names and naming convention. One approach is to add a static `pipeline` tag and aggregate by that tag instead of merging names with regex when configuring multiple listeners.

For a batch listener, invocation rate **does not equal record throughput**. For example, if one batch invocation processes 200 records, the timer count increases only once for the invocation; to get records/second, measure record counts or client fetch/consumer counters.

For a standard record listener, invocation count is usually close to how many times the listener was called; during retries, invocation count can exceed the number of unique business events. Timer count does not automatically deduplicate events.

## 11. Querying error rate from the result tag

PromQL query illustrating the ratio of failed listener invocations over 5 minutes:

~~~promql
sum by (name) (
  rate(spring_kafka_listener_seconds_count{result="failure"}[5m])
)
/
clamp_min(
  sum by (name) (
    rate(spring_kafka_listener_seconds_count[5m])
  ),
  0.000000001
)
~~~

Meaning:

- Numerator: invocation rate tagged with `result="failure"`.
- Denominator: rate of all invocations for the same `name`.
- `clamp_min` prevents division by zero when samples are tiny or there has not been traffic for long enough.

When no failure series exists in the window, the division may return no sample instead of 0. Dashboards/alerts may need appropriate missing-series handling. Do not infer "no failure metric" = "no errors" if all instrumentation is disabled.

Additional note: the framework records a failure when a listener invocation throws an error in a way it observes. If the listener catches the exception and returns normally, the outcome may be tagged as success. An intentionally handled business rejection may be treated as a success at the Kafka listener level, even though the order was rejected from a business perspective.

## 12. Querying average latency

From Timer `_sum` and `_count`, average processing duration can be calculated:

~~~promql
sum by (name) (
  rate(spring_kafka_listener_seconds_sum[5m])
)
/
clamp_min(
  sum by (name) (
    rate(spring_kafka_listener_seconds_count[5m])
  ),
  0.000000001
)
~~~

The result is in **seconds**. Multiply by 1000 if the dashboard displays milliseconds.

Example:

~~~text
Timer count increase: 2,000 invocations in 5 minutes
Timer sum increase:   100 seconds

Average = 100 / 2,000 = 0.05 seconds = 50 ms
~~~

This metric shows the average of invocations already recorded by the Timer in the window, and does not reflect records still hanging before an invocation finishes.

If a single request takes 30 seconds while 99 other requests take only 10 ms, the average may be pulled up without clearly explaining tail latency. When tail latency SLOs are needed, consider p95/p99 histograms.

## 13. p95/p99 from histograms

Once histograms are enabled and Prometheus receives the buckets, p95 can be calculated as follows:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, name) (
    rate(spring_kafka_listener_seconds_bucket[5m])
  )
)
~~~

To measure p99, replace `0.95` with `0.99`. Histogram queries on a Micrometer Timer are only valid if:

1. Histograms are actually enabled and the registry exports `_bucket`.
2. The tags being aggregated have consistent definitions.
3. The window has enough samples for percentiles to be meaningful.
4. The number of buckets and tag combinations fits within the cardinality budget.

Do not use a single `_max` in place of p99. Maximum is affected by outliers and window semantics, whereas p99 is a percentile based on the data distribution.

In low-traffic systems, a one-minute p99 can fluctuate wildly; carefully choose the measurement window and alert threshold.

## 14. Separating success latency and failure latency

The two Timer groups, success and failure, help detect different problems.

A failure can be **very fast** if the listener detects invalid data at the very beginning of the method. Conversely, a failure can be **very slow** if the listener calls a database or HTTP API until it times out.

Hypothetical example:

| Result | Count/5m | Average duration | Possible interpretation |
|---|---:|---:|---|
| success | 8,000 | 25 ms | Most records complete normally |
| failure | 60 | 1,800 ms | Dependency timeout or retries before throwing exception |
| failure | 900 | 3 ms | Mass data validation failures, failing fast |

Both show "high failure rate" yet require different runbooks. Metrics must be correlated with exception logs, DLT, dependency latency, and release changes.

PromQL for average failure latency:

~~~promql
sum by (name) (
  rate(spring_kafka_listener_seconds_sum{result="failure"}[5m])
)
/
clamp_min(
  sum by (name) (
    rate(spring_kafka_listener_seconds_count{result="failure"}[5m])
  ),
  0.000000001
)
~~~

If the listener fails due to a schema mismatch, increasing retry/backoff will not help; you need to classify permanent errors, handle DLT, and fix the contract.

## 15. Static Micrometer tags

Spring Kafka allows attaching static tags to listener timers via `ContainerProperties.micrometerTags`.

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
ordersListenerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties().setMicrometerEnabled(true);
    factory.getContainerProperties().setMicrometerTags(Map.of(
        "pipeline", "order-projection",
        "domain", "orders",
        "environment", "production"
    ));

    return factory;
}
~~~

Suitable tags are **low-churn** attributes:

- `pipeline` or `service`: processing stream name.
- `domain`: business group.
- `environment`: dev/staging/production.
- `region`: deployment region if applicable.
- `team`: bounded ownership identifier.

Do not use event ID, order ID, UUID, offset, request URLs containing IDs, or raw Kafka keys as tags. Each new tag value can create a new meter/time series. In high-traffic systems, excessive cardinality increases `MeterRegistry` memory usage, Prometheus series count, and storage cost.

## 16. Dynamic tags from ConsumerRecord

Starting with Spring Kafka versions **2.9.8 and 3.0.6**, Spring Kafka supports `ContainerProperties.micrometerTagsProvider`. This is a function taking `ConsumerRecord<?, ?>` to return a map of dynamic tags, merged with the static tags.

Example classifying only a small set of event types:

~~~java
private static String eventKind(ConsumerRecord<?, ?> record) {
    Header header = record.headers().lastHeader("event-type");

    if (header == null || header.value() == null) {
        return "unknown";
    }

    String raw = new String(
        header.value(),
        StandardCharsets.UTF_8
    );

    return switch (raw) {
        case "OrderCreated" -> "order_created";
        case "OrderPaid" -> "order_paid";
        case "OrderCancelled" -> "order_cancelled";
        default -> "other";
    };
}
~~~

Attach the function to the factory:

~~~java
factory.getContainerProperties().setMicrometerTagsProvider(
    record -> Map.of("event_kind", eventKind(record))
);
~~~

Additional imports may include:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Map;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.header.Header;
~~~

**Important:** this function is designed around `ConsumerRecord`, making it suitable for record listeners; support in batch listeners is limited. Check your exact Spring Kafka version if using batch mode.

Use an enum/whitelist as shown in the example to bound the number of tag values. Do not put a raw `trace-id` or `event-id` header directly into a dynamic tag. If you need to trace a specific event, use tracing/logging with a correlation ID rather than a separate metric series per event.

## 17. Static tags and dynamic tags can conflict

When combining `micrometerTags` with `micrometerTagsProvider`, the framework merges tags according to the mechanism of the version in use. If both the static map and the dynamic function produce a `domain` or `pipeline` key, overriding issues or confusing semantics can arise.

Example of a design to avoid:

~~~text
Static:  domain=orders
Dynamic: domain=untrusted-header-value
~~~

Define a tag contract:

| Tag | Kind | Allowed values |
|---|---|---|
| `pipeline` | Static | `order-projection`, `payment-projection` |
| `environment` | Static | `production`, `staging` |
| `event_kind` | Dynamic, whitelist | `order_created`, `order_paid`, `other` |
| `name` | Framework | Container/child name |
| `result` | Framework | `success`, `failure` |
| `exception` | Framework | Framework-determined exception labels |

Do not set custom tags that collide with framework keys such as `name`, `result`, or `exception`. Doing so can cause conflicts or cause dashboards to read the wrong series.

## 18. Micrometer Timer vs. Observation differences

Spring Kafka supports **Micrometer Observation** starting in version 3.0. When enabled:

~~~java
factory.getContainerProperties().setObservationEnabled(true);
~~~

Spring Kafka switches to the Observation mechanism, providing metrics and tracing integration capabilities via Observation instrumentation. The documentation notes that enabling Observation **disables legacy Micrometer Timers** for the observed listener, because Observation manages the corresponding timer itself.

Comparison table:

| Aspect | Legacy Micrometer Timers | Micrometer Observation |
|---|---|---|
| Enabled via | `micrometerEnabled=true` | `observationEnabled=true` |
| Primary goal | Listener invocation duration and outcome | Unified metrics/tracing instrumentation |
| Timer name | `spring.kafka.listener` | May also be `spring.kafka.listener` per convention |
| Default tags | `name`, `result`, `exception` | Observation low-cardinality keys per convention/version |
| Custom tags | `micrometerTags`, `micrometerTagsProvider` | `KafkaListenerObservationConvention`/context |
| Tracing | Does not create spans from Timer alone | Can integrate with Micrometer Tracing |
| Batch listener | Traditional timer measures invocation | Observation support for batch depends on version/configuration |

**Version note:** Some early Spring Kafka 3.x releases did not yet support Observation for batch listeners and fell back to Timers instead; documentation for newer releases adds batch-level Observation. When upgrading, check the specific release and batch configuration rather than applying a fixed assumption across all versions.

A dashboard filtering `result="failure"` from legacy timers can break when migrating to Observation because **tag names and conventions are not completely identical**. Migration must include verifying Prometheus series and updating alert rules.

## 19. Customizing Observation tags differs from micrometerTagsProvider

With Observation, Spring Kafka provides `KafkaListenerObservationConvention` and a corresponding default convention. Tag customization uses conventions/context rather than continuing to process `micrometerTagsProvider` by default like legacy Timers.

Concept:

~~~text
Legacy timers:
  ContainerProperties.micrometerTags
  ContainerProperties.micrometerTagsProvider

Observation:
  ContainerProperties.observationEnabled = true
  ContainerProperties.observationConvention
  KafkaListenerObservationConvention
~~~

In the Observation model, you must separate:

- **Low-cardinality tags:** bounded value sets suitable for metrics.
- **High-cardinality attributes:** event ID, key, offset, or request ID; only suitable for tracing/logging with proper access control and data governance.

If you put an event ID into low-cardinality observation tags, the cardinality consequences are the same as with Timer tags.

Do not enable a custom hand-rolled Timer alongside Observation for the same invocation without a specific reason, as metrics may be double-recorded under different metric names and mislead dashboards.

## 20. Micrometer consumer timers vs. Kafka client metrics

Spring Kafka also supports integrating **Micrometer Kafka client metrics** to observe metrics of the underlying KafkaConsumer/producer clients themselves.

| Metric group | What does it measure? |
|---|---|
| `spring.kafka.listener` Timer | Listener invocation duration, success/failure result |
| Kafka consumer fetch metrics | Fetch latency, fetch rate, records consumption |
| Kafka consumer group/coordinator metrics | Rebalance, commit, heartbeat per client metrics |
| Consumer lag | Difference between processed position and log-end offsets |
| `spring.kafka.template` Timer | Record sending activity via KafkaTemplate |
| Retry/DLT application metrics | Retry attempts, recoveries, DLT volume |
| Business metrics | Number of orders applied, number of successful payments |

Spring Kafka provides `MicrometerConsumerListener` and `MicrometerProducerListener` for producer/consumer factories, binding Kafka client metrics into `MeterRegistry` according to client lifecycles.

Example configuring a consumer factory with a dedicated metrics listener:

~~~java
@Bean
ConsumerFactory<String, OrderEvent> consumerFactory(
        KafkaProperties kafkaProperties,
        MeterRegistry registry) {

    Map<String, Object> config =
            kafkaProperties.buildConsumerProperties();

    var factory =
        new DefaultKafkaConsumerFactory<String, OrderEvent>(config);

    factory.addListener(
        new MicrometerConsumerListener<String, OrderEvent>(registry)
    );

    return factory;
}
~~~

This example illustrates wiring with Spring Boot; `buildConsumerProperties`/constructor overloads may vary by Boot/Spring Kafka version. In a real application, if Boot has already configured the consumer factory and listeners, reuse the existing factory rather than creating a new one that drops custom SerDe, auth, or error-handling settings.

**Listener timers do not replace Kafka client metrics.** A listener running in 20 ms while poll/fetch stalls for 10 seconds will look fast in the Timer yet the pipeline will still suffer from low throughput.

## 21. Timers do not measure end-to-end latency

Example timeline for an event:

~~~text
12:00:00 Producer publishes event
12:00:01 Kafka broker stores record
12:02:31 Consumer receives record due to backlog
12:02:31.020 Listener finishes processing
12:02:31.040 Offset commit completes
~~~

The listener timer may record about **20 ms**, while the latency from publish to business completion is about **151 seconds**.

To monitor end-to-end latency:

1. Producer attaches an event timestamp or business `occurredAt` with clear semantics.
2. Consumer measures the elapsed time from that timestamp until business work completes.
3. Distinguish event timestamp from Kafka `CreateTime` and `LogAppendTime`.
4. Watch for clock skew and untrusted upstream timestamps.
5. If a record goes through a retry topic, preserve the original event timestamp and event ID.
6. Do not use this end-to-end latency to replace the listener Timer; the two measurements serve different diagnostic purposes.

If a listener launches a downstream async task and returns before the task finishes, the Timer may reflect only the invocation duration rather than the full side effect. Async listener instrumentation behavior must be verified against the version and APIs in use.

## 22. Timers with DefaultErrorHandler and retries

A failing record can trigger the listener multiple times:

~~~text
Record A, attempt 1 -> listener throws -> failure timer +1
        |
        v
Backoff
        |
Record A, attempt 2 -> listener throws -> failure timer +1
        |
        v
Backoff
        |
Record A, attempt 3 -> listener success -> success timer +1
~~~

In this case, the Timer count records **3 listener invocations** for **one business event**. The success/failure ratio here is per invocation, not the rate of events that ultimately succeed after retries.

If a record is sent to the DLT after exhausting attempts, the failed invocations still increment the failure Timer; a successful DLT publish does not turn invocations that threw exceptions into success timer entries.

To measure retries accurately, also track:

- Retry attempt count by exception class.
- Number of unique events recovered successfully.
- Number of events routed to the DLT.
- Total time to completion from original event to terminal outcome.
- Number of duplicates/re-deliveries detected by idempotency.
- Delay and backlog of retry topics when using non-blocking retries.

With `DefaultErrorHandler`, some backoff wait time happens **outside** the listener method invocation, so do not add up Timer durations as if they covered the entire retry delay.

## 23. Timers in non-blocking retry topics

When using `@RetryableTopic`, records are forwarded across the original topic and retry topics. Each retry listener/container can create its own timers.

~~~text
orders (original listener timer)
    |
    +-- failure --> orders-retry-1000 (retry listener timer)
                       |
                       +-- failure --> orders-retry-2000 (retry listener timer)
                                          |
                                          +-- DLT
~~~

A business event passing through multiple topics will have multiple listener invocations at different stages. The Timer metric measures each invocation without linking those records into an end-to-end workflow.

Consequences:

- A dashboard looking only at the original topic's timer may miss a failing retry stage.
- A retry listener's timer may be fast while backlog is high because the scheduled delay has not elapsed yet.
- A retried record may execute after a newer record, affecting ordering; Timers cannot detect business ordering violations.
- A DLT consumer has its own timers if a listener container is registered for it.
- If multiple child containers share a logical listener ID, determine the exact tag names so you do not misaggregate.

You can add a static `stage` tag or separate dashboards by container name, provided you understand how Spring Kafka creates retry topic listeners in your deployed version.

## 24. Timers in batch listeners

With a batch listener:

~~~java
@KafkaListener(
    id = "batch-importer",
    topics = "import-events",
    containerFactory = "batchListenerFactory")
public void onBatch(List<ConsumerRecord<String, ImportEvent>> records) {
    importService.applyBatch(records);
}
~~~

A single invocation can contain tens to hundreds of Kafka records. Therefore:

~~~text
10 batch invocations x 200 records/batch
= 2,000 records delivered to listener

Timer count increases by about 10, not 2,000
(when the timer records per batch listener invocation).
~~~

Do not directly compare the `spring.kafka.listener` invocation rate of a record listener with a batch listener and treat it as records/second. Measure `batch.size`, batch processing duration, and record throughput at the application level.

If a batch has only one failing record and the entire method throws an exception, the failure Timer reflects a **failed batch invocation**; it does not indicate how many records in the batch already applied side effects. Diagnosis requires `BatchListenerFailedException`, proper transaction design, and per-record metrics.

## 25. Choosing tags without exploding cardinality

A common observability mistake is putting every ID into Timer tags:

~~~java
// DO NOT DO THIS: every orderId creates a new tag value.
factory.getContainerProperties().setMicrometerTagsProvider(
    record -> Map.of("order_id", String.valueOf(record.key()))
);
~~~

Suppose the service processes one million order IDs, each creating a distinct `order_id` tag. When multiplied by result, exception, listener name, pod, and histogram buckets, the number of time series can explode.

Instead:

~~~java
// Tag with a controlled set of values.
factory.getContainerProperties().setMicrometerTagsProvider(
    record -> Map.of("event_kind", eventKind(record))
);
~~~

Recommended tag policy:

| Category | Example | Should it be used as a metric tag? |
|---|---|---|
| Stable | `environment=prod` | Yes |
| Small group | `event_kind=order_paid` | Yes |
| Listener | `name=orders-consumer-0` | Yes, framework-managed |
| Exception label | `exception=ListenerExecutionFailedException` | Yes, framework-managed |
| Kafka key | `order-912838` | No |
| Event ID | Unique UUID per event | No |
| Offset | `topic-1@12345` | No |
| Correlation ID | Unique ID per request | No |
| Raw exception message | Free-form, may contain PII | No |

For information needed to trace a single record, use logs/tracing with a correlation ID and access controls, not high-cardinality metrics.

## 26. Reasons why spring.kafka.listener is missing

When the metric does not show up in Prometheus or Actuator:

1. **No suitable Micrometer registry** in the application context.
2. `micrometerEnabled=false` on the container factory actually in use.
3. `observationEnabled=true`, switching instrumentation to Observation with different tag conventions.
4. The listener has not been invoked yet or the topic has no data.
5. `@KafkaListener` is using a different factory due to `containerFactory`/bean name.
6. Prometheus registry dependency or Actuator endpoint is not configured.
7. The `/actuator/prometheus` endpoint is blocked/requires authentication or Prometheus scraping fails.
8. Meter filters denied the metric or renamed tags.
9. The metric name changed after naming conversion, e.g. `spring_kafka_listener_seconds_count`.
10. `MeterRegistry` is not created by the app or multiple registries do not match auto-instrumentation conditions.
11. The app is running under a different profile where metrics export is disabled.
12. A child consumer's timer has a `name` tag that does not match the expected query.

Do not immediately create a manual Timer with the same name before identifying the root cause; doing so can cause two sources to record the metric or produce incompatible tag sets.

## 27. Distinguishing listener timer latency from CPU/GC latency

Higher listener latency does not always mean the Kafka broker is slow. A listener includes Java code and service/DB calls, so cross-check:

| Observation | Possible cause |
|---|---|
| Timer p99 rises, DB latency rises | Slow database connections/queries |
| Timer p99 rises, CPU 100% | CPU saturation or heavy algorithm |
| Timer p99 rises, GC pauses rise | Memory pressure/GC |
| Timer failure rate rises, very short latency | Fail-fast validation/schema bug |
| Timer failure rate rises, latency near timeout | API/DB timeout |
| Timer steady but lag increases | Insufficient consumer concurrency/fetch/throughput |
| Timer low, record e2e latency high | Large backlog, retry delay, or pause |
| Timer has no samples, containers stopped | Lifecycle/startup problem |
| Timer shows success but DB data is missing | Swallowed exception or unfinished async processing |

Never rely on a single metric to conclude root cause. The Timer is one piece of the reliability picture.

## 28. Practical dashboard example

A dashboard for `order-projection` might include:

| Panel | Data |
|---|---|
| Listener invocations/sec | `spring_kafka_listener_seconds_count` rate |
| Listener success/failure rate | Filter `result` |
| Average listener duration | `_sum / _count` |
| p95/p99 latency | `histogram_quantile` if histogram enabled |
| Consumer lag per partition | Client/exporter lag metric |
| Error handler retry count | Application metric/observability |
| DLT volume | DLT producer/consumer counter |
| DB pool utilization | Hikari/DB metrics |
| Consumer rebalance count | Kafka client metrics |
| Idle/non-responsive events | Spring Kafka application event counters |
| End-to-end processing latency | Timestamp-based custom metric |

Panels need appropriate observation windows and dimensionality. A listener with low p99 but rapidly rising consumer lag may still need more concurrency/partition capacity. A listener with low lag but a high failure rate may be sending records to the DLT, making the original topic look "processed" even though business processing did not complete.

## 29. Alerting on latency and failure rate

An alert can be based on **multiple conditions together**:

- Failure rate rises above a significant threshold.
- Minimum number of invocations within a sufficiently large window.
- p95/p99 latency exceeds the SLO.
- Consumer lag or oldest-record age increases.
- DLT volume spikes abnormally.

Conceptual rule logic example:

~~~text
IF listener failure ratio > 5%
AND invocation rate >= 10 invocations/s
FOR 5 minutes
THEN alert order-projection owner
~~~

Thresholds of 5%, 10/s, and 5 minutes are illustrative only and must be chosen based on real SLOs and traffic.

Avoid alerting when traffic is too low: one error out of two invocations produces a 50% failure ratio without necessarily indicating a widespread incident. At the same time, do not ignore a single critical event such as a payment; in that case, use a dedicated business alert or DLT alarm.

For histogram percentiles, check sample sizes and bucket configuration before setting p99 thresholds.

## 30. Runbook: timer failures increase after a deploy

1. Identify `name`, `result`, version/pod, and the time window when errors increased.
2. Compare child consumers, topics, and partition assignments.
3. Inspect exception logs/cause chains because the timer `exception` tag may only be a wrapper.
4. Check schema/serde, DB/API latency, auth, and release changes.
5. Check retry attempts, DLT publishing, and the count of unfinished unique events.
6. Verify whether the listener catches exceptions and alters success/failure semantics.
7. If failures are transient, confirm backoff/circuit breakers are relieving dependency load.
8. If payloads have permanent errors, apply non-retryable classification and route to DLT per policy.
9. Check whether consumer lag is rising or dropping abnormally.
10. After rollback/fix, monitor failure rate, end-to-end latency, and DLT recovery.

Do not simply reduce timer instrumentation or remove the exception tag to make the dashboard green; identify the real business root cause.

## 31. Runbook: timer latency rises while lag stays low

1. Confirm whether duration increased on the success or failure timer.
2. Compare p95, p99, and average; are there many slow invocations or just a few outliers?
3. Check DB pool, slow queries, lock waits, and transaction duration.
4. Check HTTP client timeouts, internal retries, and rate limits.
5. Check CPU, GC, memory, and thread pool saturation.
6. Check whether batch size or record size changed.
7. Check whether metrics changed tag/Observation conventions after a deploy.
8. If lag is low due to low traffic, do not conclude throughput capacity is healthy.
9. Check business end-to-end latency to spot broker waits or other retry delays.
10. Tune concurrency, timeouts, or code according to the identified root cause.

Distinguish "slow listener invocation" from "Kafka broker delivering records slowly." The Timer only covers one segment of the pipeline.

## 32. Runbook: lag rises while timers look healthy

1. Determine producer ingress rate and consumer record throughput.
2. Check partition count and listener concurrency.
3. Measure poll/fetch latency and Kafka client metrics.
4. Check whether any partition has a hot key/skew.
5. Check for paused consumers or long error-handler backoffs.
6. Check whether retry topics/DLT have separate backlogs.
7. Verify whether listener timer count reflects record invocations or batch invocations.
8. Check offset commit latency and rebalance count.
9. Check oldest record age and retention budget.
10. Increase capacity or adjust partitioning in a controlled manner instead of only optimizing an already-fast listener method.

Example: a listener processes 2 ms/record, yet there is only one partition and ingress is very high; a good timer p99 will not allow the consumer to exceed a single partition's sequential processing limit.

## 33. Measuring individual business steps when detail is needed

The listener timer shows the duration covering an invocation; if you need to know which step is slow, you can add a custom Timer for database/API calls:

~~~java
@Service
public class OrderProjectionService {

    private final Timer databaseWriteTimer;
    private final OrderRepository repository;

    public OrderProjectionService(
            MeterRegistry registry,
            OrderRepository repository) {

        this.repository = repository;
        this.databaseWriteTimer = Timer.builder("business.order.db.write")
                .description("Duration of order projection DB writes")
                .tag("operation", "upsert")
                .register(registry);
    }

    public void apply(OrderEvent event) {
        databaseWriteTimer.record(() -> repository.apply(event));
    }
}
~~~

Example measuring database writes separately. It **does not replace** `spring.kafka.listener`:

- The listener timer measures the entire event-handling method.
- The custom Timer measures one step inside the method.
- The sum of steps does not necessarily equal the listener duration because serialization, validation, business logic, and orchestration also take time.
- If the method calls an async operation without awaiting the result, the timer may measure only task submission time.
- Custom Timer tags must also stay low cardinality.

If an important measurement involves a database transaction, decide whether the Timer should measure up to transaction commit or only repository method execution; proxy transaction boundaries can affect the result.

## 34. Differences between Timer, Counter, and LongTaskTimer

| Instrument | When to use? | Example |
|---|---|---|
| `Timer` | Count invocations and measure duration for completed tasks | `spring.kafka.listener` |
| `Counter` | Count events without measuring duration | Number of records sent to DLT |
| `Gauge` | State at scrape time | Queue depth, consumer lag |
| `LongTaskTimer` | Observe long-running tasks even before completion | Long-running workflow/Observation active timer |
| `DistributionSummary` | Measure distribution of non-time values | Batch size or payload size |

A Micrometer Timer only records duration when the sample completes. If a listener hangs indefinitely, that invocation may not yet appear in the Timer; in that case, thread/health/long-task monitoring is more important.

Do not use a Timer to measure consumer lag by recording "offset difference" in seconds; use the proper tool/instrument type to avoid misleading reports.

## 35. Operating metrics with multiple pods and consumer groups

In a multi-replica deployment:

~~~text
order-projection pod-A: orders-consumer-0, orders-consumer-1
order-projection pod-B: orders-consumer-0, orders-consumer-1
order-projection pod-C: orders-consumer-0, orders-consumer-1
~~~

Pods may share the same `name` tag, while Prometheus adds target labels like `instance`, `job`, `pod`. When aggregating, define your goal clearly:

- Per pod: detect one instance running slower than others.
- Per logical listener: measure total invocations/failures across replicas.
- Per consumer child: detect a hot partition/thread.
- Per business domain: compare pipelines with different SLOs.

Do not strip `instance` too early when investigating a single pod. Conversely, when building a service-level error ratio, aggregate instances and tags properly so you do not misleadingly average ratios.

If pod counts change within a Prometheus window, `rate` must be computed on each individual counter series before summing. Do not sum raw counters first and then take `rate` when replicas restart at different times.

## 36. Security and cost of metrics

Although Timers do not carry business payloads, tag names can reveal domain, service, listener, and exception names. Therefore:

- Protect Actuator/Prometheus endpoints with network policies and access controls.
- Never put PII, event IDs, order IDs, auth tokens, or raw exception messages into tags.
- Control histogram buckets, series count, and Prometheus retention.
- Use sampling or appropriate aggregation when detailed tracing is needed.
- Monitor overhead when increasing the number of dynamic tag values.
- Manage dashboards and alert rules as reviewed code/config.
- When migrating to Observation, verify tag names instead of comparing only metric names.

A monitoring setup with too many series can consume the consumer's own memory and put pressure on the metrics backend, working against reliability goals.

## 37. Micrometer consumer timers implementation checklist

- [ ] Micrometer and an appropriate `MeterRegistry` are present in the application context.
- [ ] Container has `micrometerEnabled=true` or an explicit Observation mode chosen.
- [ ] Know the timer name `spring.kafka.listener` and tags `name`, `result`, `exception`.
- [ ] Understand that a concurrent listener has timers per child thread.
- [ ] Distinguish listener invocation count from unique business events and batch record count.
- [ ] Static tags are stable; dynamic tags only come from a whitelisted set of values.
- [ ] Event IDs, offsets, Kafka keys, or message text are never used as metric labels.
- [ ] Actuator/Prometheus has the registry/exporter and secured scrape endpoint.
- [ ] Histograms are enabled only when p95/p99 is needed and cardinality cost is accounted for.
- [ ] Dashboard includes invocation rate, failure rate, average, and tail latency.
- [ ] Supplemented with consumer lag, Kafka client metrics, retry/DLT, and business success metrics.
- [ ] Never refer to Timer duration as end-to-end latency.
- [ ] Never treat timer success as proof that DB/HTTP side effects committed.
- [ ] If using Observation, verify conventions and version support for batch listeners.
- [ ] Alerts include minimum traffic, duration windows, and corresponding runbooks.
- [ ] Have a process to verify metrics when upgrading Spring Kafka or Micrometer.

## 38. References

- [Spring Kafka Reference — Monitoring](https://docs.spring.io/spring-kafka/reference/kafka/micrometer.html)
- [Spring Kafka Reference — Listener Container Properties](https://docs.spring.io/spring-kafka/reference/kafka/container-props.html)
- [Spring Kafka Reference — Micrometer Observation Documentation](https://docs.spring.io/spring-kafka/reference/appendix/micrometer.html)
- [Micrometer Reference — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Spring Boot Reference — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)

**Conclusion:** Spring Kafka's Micrometer consumer timers provide a standard, reasonably low-overhead measurement of **the duration and outcome of each listener invocation**. Use `spring.kafka.listener` along with the `name`, `result`, and `exception` tags to observe success/failure and latency; add controlled static/dynamic tags when grouping is needed. However, timers do not measure consumer lag, retry wait time, exactly-once effectiveness, or end-to-end business latency. For a reliable system, combine listener timers with Kafka client metrics, retry/DLT, consumer group state, dependency health, and business telemetry, while aligning your choice between legacy timers and Micrometer Observation with your deployed Spring Kafka version.
