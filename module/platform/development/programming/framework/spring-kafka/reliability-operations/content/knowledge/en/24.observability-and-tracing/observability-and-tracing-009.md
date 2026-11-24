# Tracing across retry topics

In **Spring Kafka Reliability Operations**, retry topics prevent a consumer from holding a failing record on its consumer thread for the entire backoff duration. When processing fails, Spring Kafka can forward the record to a Kafka retry topic; another listener receives it after a delay and retries. Once attempts are exhausted, the record can route to a dead-letter topic (DLT). Consequently, **a single business event** can traverse multiple topics, offsets, listener containers, and application instances.

**Tracing across retry topics** means observing this journey across its asynchronous hops, answering: where did the first attempt fail, which retry attempt succeeded, how much time was spent processing vs. waiting, whether the record was handed off to a DLT, and whether trace context broke across Kafka hops.

Good traceability combines **distributed tracing**, **stable business event IDs**, **structured logs**, **retry/DLT metrics**, and Kafka `topic-partition-offset` coordinates. A clean trace does not prove offsets committed, business databases updated uniquely, or producers wrote durably. Those guarantees must be engineered separately via retry/recovery policies, appropriate Kafka transactions, and idempotency.

## 1. Why do retry topics complicate tracing?

A synchronous HTTP call can yield a seamless chain of spans within a few hundred milliseconds. Retry topics create multiple **independent stages**:

~~~text
Business event: evt-42

orders.events
  -> initial listener: FAILURE
  -> publish to orders.events-retry-2000
  -> record sits in retry topic during backoff
  -> retry listener: FAILURE
  -> publish to orders.events-retry-10000
  -> wait for next retry
  -> retry listener: SUCCESS

Or if retries exhaust:
  -> orders.events-dlt
  -> operator triages and replays later
~~~

Topic names and delays are illustrative; Spring Kafka configures naming, suffixes, and retry-topic reuse depending on version. At each hop, Kafka creates a **new record in the destination topic**. That record may preserve the event ID yet gets a different topic, partition, offset, and timestamp.

Looking only at the initial span shows an exception without telling whether the event later succeeded or moved to a DLT. Looking only at the DLT misses the original exception and intermediate backoff intervals. Distributed tracing must link the hops properly—or at least allow querying them via a stable business ID.

## 2. Distinguishing the identifiers

| Identifier | Meaning | Across retry topics |
|---|---|---|
| `traceId` | A distributed trace managed by a tracer | May carry across hops if propagation works; may differ after replay. |
| `spanId` | An observed operation | Usually changes on each consume, publish, or business operation. |
| Parent/child relationship | Relationship between spans | Requires proper trace context propagation to link. |
| Span link | Causal link not forced into parent/child | Helpful for queues, batches, and replays when supported by instrumentation. |
| `eventId` | Stable identifier of a business event | Should stay unchanged across retries for deduplication and investigation. |
| `correlationId` | Application workflow/request identifier | Can link multiple events or multiple traces. |
| Topic/partition/offset | Physical Kafka record location | Changes across source, retry topics, and DLT. |
| Attempt index | Processing attempt per retry policy | Changes per hop; read from the right metadata. |
| Replay operation ID | Identifier for an operator/system-triggered replay | Usually fresh for each replay campaign. |

One event can have multiple trace IDs if context is lost or a new trace is intentionally started on replay. One trace can also span multiple event IDs if one request emits several messages. **Never use `traceId` as an idempotency key**.

## 3. What should a trace across retry hops look like?

~~~mermaid
sequenceDiagram
    participant P as Source Producer
    participant S as Source Topic
    participant L1 as Source Listener
    participant R1 as Retry Topic 1
    participant L2 as Retry Listener
    participant R2 as Retry Topic 2
    participant L3 as Retry Listener
    participant D as DLT
    P->>S: Publish eventId=evt-42
    S-->>L1: Consumer poll
    Note over L1: Consumer span, attempt 1
    L1->>L1: Business failure
    L1->>R1: Forward retry record, producer span
    Note over R1: Wait asynchronous delay
    R1-->>L2: Consumer poll when eligible
    Note over L2: Consumer span, attempt 2
    L2->>L2: Subsequent failure
    L2->>R2: Forward retry record, producer span
    Note over R2: Wait next backoff
    R2-->>L3: Consumer poll
    alt Retry succeeds
        L3->>L3: Business operation applied
    else Retries exhausted
        L3->>D: Publish DLT, producer span
    end
~~~

A span should reflect **actual execution duration** of that hop, not wrap the entire time the record sits idle in a topic. If a retry runs 10 minutes later, never hold an active span open for 10 minutes just to render an unbroken timeline bar.

Wait time can be measured via event timestamps/headers and metrics, while traces depict separate consume/produce/business spans at distinct timestamps.

## 4. Spring Kafka @RetryableTopic

Example of a record listener using non-blocking retries:

~~~java
@Component
public class OrdersListener {

    private final OrdersService ordersService;

    public OrdersListener(OrdersService ordersService) {
        this.ordersService = ordersService;
    }

    @RetryableTopic(
            attempts = "4",
            backoff = @Backoff(
                    delay = 2_000,
                    multiplier = 2.0,
                    maxDelay = 10_000))
    @KafkaListener(
            id = "orders-listener",
            topics = "orders.events",
            groupId = "orders-service")
    public void handle(ConsumerRecord<String, OrderEvent> record) {
        ordersService.applyIdempotently(record.value());
    }

    @DltHandler
    public void handleDlt(ConsumerRecord<String, OrderEvent> record) {
        // Quarantine/audit per policy; never treat this as business success.
    }
}
~~~

`OrdersService` and `OrderEvent` are application-defined types. Key imports include `RetryableTopic`, `KafkaListener`, `DltHandler`, `Backoff`, `ConsumerRecord`, and `Component`. The example omits Kafka broker settings, serializers, DLT ownership, and testing infrastructure.

In Spring Kafka's common model, `attempts` is **total processing attempts including the first attempt**; do not infer the total number of retry topics solely from topic naming. Spring Kafka may create multiple retry topics or reuse topics depending on backoff policy and version.

**Transaction note:** non-blocking `@RetryableTopic` retries are not supported by Spring Kafka in direct combination with Kafka container transactions under standard architecture. If Kafka EOS is required, redesign the transaction/retry boundary rather than assuming the annotation folds forwarding and source offsets into one transaction.

## 5. Distinct observability layers

| Layer | Primary signal | Strengths | Limitations |
|---|---|---|---|
| Kafka client metrics | Consumer fetch/lag, producer send | Shows whether Kafka clients are healthy | Does not know if business event applied. |
| Spring Kafka listener Observation | Listener operation span/metric | Shows attempt duration and exception | May exclude DLT/retry producer templates. |
| Kafka producer Observation | Send operation/span | Tracks source, retry, and DLT publishes | Send span does not prove source offset committed. |
| Business spans | Database/API/application operations | Isolates slow or failing steps | External side effects are not automatically transactional. |
| Structured logs | Event ID, topic, offset, attempt, error | Exact per-record lookup | Log retention and security constraints. |
| Retry/DLT metrics | Attempts, forwarded, recovered, backlog | System-wide measurement | Does not show one event's full journey. |
| Audit/business state | Durable outcome, idempotency | Reconciles business outcomes | May require dedicated workflow/store. |

Never try to make traces the source of truth for every metric. Traces can be sampled; metrics count volume; business state confirms results.

## 6. Enabling Micrometer Observation for listener containers

In Spring Kafka lines supporting Micrometer Observation:

~~~java
@Configuration
public class OrdersKafkaConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    ordersListenerContainerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory) {

        ConcurrentKafkaListenerContainerFactory<String, OrderEvent> factory =
                new ConcurrentKafkaListenerContainerFactory<>();

        factory.setConsumerFactory(consumerFactory);
        factory.getContainerProperties().setObservationEnabled(true);

        return factory;
    }
}
~~~

`setObservationEnabled(true)` requires a Spring Kafka version supporting Observation; verify the API in your actual dependency. Spring Boot may supply `ObservationRegistry`, yet enabling observation on the container alone does not guarantee exported traces unless a tracing bridge and exporter are configured.

For retries, determine **which container factory the source listener, retry listeners, and DLT listener use**. If the application defines a separate factory for retry endpoints, enable Observation on that factory as well. Do not assume the default bean name covers every endpoint created by custom wiring.

### Legacy timers vs. Observation

Spring Kafka offers legacy Micrometer listener timers and Micrometer Observation depending on version. You may see `setMicrometerEnabled(true)` or `setObservationEnabled(true)`. Metric names, span attributes, and enablement APIs depend on version.

Do not enable both just to "collect more" if doing so creates duplicate telemetry. Inspect actual metrics exposed via Actuator and traces in the backend.

## 7. Enabling Observation for KafkaTemplate

Producer sends must be instrumented to carry context from one Kafka hop to the next:

~~~java
@Bean
KafkaTemplate<String, OrderEvent> ordersKafkaTemplate(
        ProducerFactory<String, OrderEvent> producerFactory) {

    KafkaTemplate<String, OrderEvent> template =
            new KafkaTemplate<>(producerFactory);

    template.setObservationEnabled(true);
    return template;
}
~~~

In supported Spring Kafka versions, when `KafkaTemplate` is instrumented within an active observation/tracing context, producer instrumentation creates a span and injects trace context into Kafka record headers. Consumer instrumentation on the next hop extracts that context.

**Verify which `KafkaTemplate` is actually used by the retry/DLT publisher.** Retry infrastructure may resolve a different template due to bean selection, generic types, serializers, or custom recoverers. Enabling observation on the regular publishing template **does not automatically mean** retry/DLT forwarding is instrumented.

For deserialization errors, DLT records may need to serialize raw bytes rather than DTOs; the template/recoverer must have matching serializers. Proper tracing configuration will not fix a serialization failure when publishing to a DLT.

## 8. Micrometer Tracing and OpenTelemetry

A Spring Boot setup may use Spring Boot Actuator, the Micrometer Tracing bridge for OpenTelemetry, and an appropriate exporter:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-tracing-bridge-otel</artifactId>
</dependency>
<dependency>
    <groupId>io.opentelemetry</groupId>
    <artifactId>opentelemetry-exporter-otlp</artifactId>
</dependency>
~~~

These dependencies illustrate a compatible Spring Boot line; use your project's BOM and avoid accidentally mixing OpenTelemetry and Brave bridges.

Example tracing configuration on Spring Boot lines supporting these properties:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.2
  otlp:
    tracing:
      endpoint: http://otel-collector:4318/v1/traces
~~~

Exporter property paths can vary across Spring Boot versions; confirm against your running system. The endpoint is a placeholder, not an approved production configuration. Collectors require security controls and resource limits.

### Sampling and trace export

A sampling probability of `0.2` does not mean exactly 20% of business events get complete traces. Sampling may be inherited from upstream, context may drop at a retry hop, the exporter may drop spans, or the trace backend may have expired data past retention.

When spans are missing, do not jump to concluding records were lost. Look up the event ID in logs and Kafka offsets to distinguish sampling from delivery errors.

## 9. Trace context in Kafka headers

Distributed tracing metadata usually travels in **Kafka record headers**, not Kafka offsets or message keys. With W3C Trace Context, `traceparent` and `tracestate` are common; another stack may use B3 or another propagation format.

~~~text
Record on source topic:
  topic      = orders.events
  partition  = 2
  offset     = 901

  headers:
    traceparent  = 00-<trace-id>-<span-id>-<flags>
    x-event-id   = evt-42
    x-flow-id    = order-flow-42
~~~

The values above are placeholders; do not copy them as real W3C headers. The tracing library's propagator is responsible for generating and parsing valid formats.

When forwarding to a retry topic, the new record needs **appropriate trace context injection/extraction**. Never blindly copy an old `traceparent` so every retry attempt shares the exact same parent span; that can express a false causal relationship. Let Kafka producer/consumer instrumentation and configured propagators manage it where supported by your version/framework.

### Causes of broken context

- Source producer lacks tracing instrumentation.
- Retry forwarder uses an uninstrumented `KafkaTemplate`.
- Custom recoverer builds a new record and drops/overwrites headers.
- Producer uses W3C while consumer only extracts B3, or vice versa.
- An asynchronous executor drops the active context.
- Propagation headers are duplicated or overwritten out of order.
- Sampling, exporter, or retention hides spans in the UI.
- DLT replay runs a brand-new workflow and intentionally starts a fresh trace ID.

Investigate each hop rather than just tweaking tracing probability.

## 10. Trace ID does not replace event ID

`traceId` is an observability identifier. `eventId` is a business event identifier used to link attempts and enforce idempotency.

One event can yield multiple trace IDs:
- Propagation failed.
- Replay happened days later.
- Operators split recovery workflows.
- Sampling or root-trace policies changed across attempts.

Never generate a fresh event ID on each retry just to start a new trace. Whenever consumers need deduplication, the event ID must remain unchanged for the same business effect.

### Stable event ID header

~~~java
ProducerRecord<String, OrderEvent> record =
        new ProducerRecord<>("orders.events", orderId, event);

record.headers().add(
        "x-event-id",
        event.eventId().getBytes(StandardCharsets.UTF_8));

record.headers().add(
        "x-flow-id",
        event.flowId().getBytes(StandardCharsets.UTF_8));

kafkaTemplate.send(record);
~~~

`event` and `orderId` are application data. Generate `eventId` once when creating the event. Never use trace ID as a business deduplication key.

Reading headers:

~~~java
private String readHeader(
        ConsumerRecord<?, ?> record,
        String headerName) {

    Header header = record.headers().lastHeader(headerName);

    if (header == null || header.value() == null) {
        return "missing";
    }

    return new String(
            header.value(),
            StandardCharsets.UTF_8);
}
~~~

This example uses `org.apache.kafka.common.header.Header`. When receiving headers from untrusted producers, enforce length bounds, validate encoding, and avoid dumping arbitrary content into logs or metric labels.

## 11. What metadata should be logged for an attempt?

A helpful structured log:

~~~text
timestamp       = 2026-11-15T09:00:00Z
service         = orders-service
eventId         = evt-42
flowId          = order-flow-42
traceId         = current-trace-id
spanId          = current-span-id
listener        = orders-listener
topic           = orders.events-retry-2000
partition       = 1
offset          = 783
attempt         = 2
outcome         = failed
errorCategory   = dependency_timeout
nextDestination = orders.events-retry-10000
~~~

Values are illustrative. With Micrometer Tracing logging correlation, `traceId`/`spanId` can populate MDC/structured logs while an observation is active; verify your actual logging pattern.

Never log full Kafka payloads, tokens, passwords, PII, or unbounded repeated stack traces. `errorCategory` should belong to a finite label set. During severe incidents, use correlation IDs and appropriate log sampling rather than leaving every retry attempt at `DEBUG` permanently.

### Distinguish topic offsets at each hop

The record at `orders.events` offset 901 and the record at `orders.events-retry-2000` offset 783 share the same event ID, yet **are not at the same Kafka log position**. Keep topic, partition, and offset per hop in traces/logs; never use a retry offset as a source offset to reset a consumer group.

## 12. Retry attempt metadata vs. delivery attempts

Spring Kafka tracks retry metadata in headers/infrastructure for attempts, timestamps, and destinations. Distinguish:

- Blocking retries can use delivery-attempt metadata per listener/error-handler policy.
- Non-blocking retries via `@RetryableTopic` have their own attempt/retry-topic metadata.
- Exact header naming and counting rules depend on the Spring Kafka version.

Do not assume `KafkaHeaders.DELIVERY_ATTEMPT` is always present or shares identical semantics with attempt counts across retry topics. When logging attempt indices, use the API/header matching your running retry mechanism and clarify whether the initial delivery counts as attempt 1.

**Never infer attempt numbers from topic suffixes**. A retry topic can be reused across multiple attempts or named by delay rather than attempt count.

## 13. Creating observations for business operations

Kafka listener observations normally wrap one listener invocation. To see database calls, computations, or HTTP dependencies clearly, add a business observation:

~~~java
@Service
public class OrdersService {

    private final ObservationRegistry observationRegistry;
    private final OrderRepository repository;

    public OrdersService(
            ObservationRegistry observationRegistry,
            OrderRepository repository) {
        this.observationRegistry = observationRegistry;
        this.repository = repository;
    }

    public void applyIdempotently(OrderEvent event) {
        Observation.createNotStarted(
                "orders.apply",
                observationRegistry)
                .lowCardinalityKeyValue(
                        "operation", "apply-order-event")
                .observe(() -> repository.applyOnce(event));
    }
}
~~~

`OrderRepository.applyOnce` is an assumed business API. Database access, business transactions, and idempotency must be implemented inside real repositories/services.

`lowCardinalityKeyValue` should use bounded values like operation name. Never put event IDs, order IDs, emails, or customer IDs into low-cardinality meter tags. When IDs are needed for lookups, use structured logs or controlled tracing attributes while limiting sensitive data.

For Spring Kafka to retry when a business operation fails, the listener must **throw the exception** to the error handler. Never swallow the exception after tagging a span error and return normally, because the container will treat the record as complete and commit the offset.

## 14. Context when listeners use async executors

Micrometer tracing context normally lives on the active scope/thread. If a listener dispatches work to an `ExecutorService` or `CompletableFuture` without propagating context:

~~~text
Consumer thread:
  active traceId = T1
  submit task

Worker thread:
  no active trace context
  new span becomes root trace T2
~~~

In supported versions, use Micrometer Context Propagation, `ContextSnapshot`, or an instrumented executor to capture/restore context appropriately. Never assume thread-locals cross thread boundaries automatically.

Never pass `KafkaConsumer` to a worker thread to call `poll()`, `seek()`, or `commitSync()`; `KafkaConsumer` is not thread-safe. Async processing must also protect acknowledgments and partition ownership safely across rebalances.

### Never hold a span open during retry waits

If a record waits 15 minutes in a retry topic, the previous attempt's active observation must end once processing/forwarding finishes. When the retry consumer polls the record, instrumentation starts a new observation and extracts context from headers if present. Never keep spans, request scopes, or transactions open across backoff delays.

## 15. Measuring processing latency and retry wait separately

| Interval | Start / end points | Meaning |
|---|---|---|
| Listener processing | Enter → exit listener invocation | Execution time of one attempt. |
| Forwarding | Retry producer send → ack/result | Handoff time back to Kafka. |
| Scheduled backoff | Forward time → eligible retry time | Policy-configured delay. |
| Actual retry wait | Forward time → retry consume time | Includes backoff, backlog, and outages. |
| Extra retry delay | Due time → attempt start | Extra lag from consumer lag, pauses, or rebalances. |
| End-to-end completion | Business event created → final outcome | Workflow completion SLA. |
| DLT unresolved age | DLT publication → resolution | Failed-message triage SLA. |

Kafka record timestamps, source business timestamps, and retry due-time headers have different semantics. Do not assume every retry record timestamp equals when the message was published to the retry topic. Check how your running framework version sets timestamps.

A header like `x-first-seen-at` can retain workflow start time, yet should be set only once and validated against untrusted sources. The tracing backend is not a mandatory SLA store; metrics and audit stores may fit better.

## 16. DLT publication is a distinct trace stage

When retries exhaust, the recoverer can publish to a DLT. In traces, keep these separate:

~~~text
Source listener: FAILED
Retry attempt 2: FAILED
Retry attempt 3: FAILED
DLT publication: SUCCESS
Business outcome: UNRESOLVED
~~~

**DLT publication success is not business success.** The source offset may advance after recovery, yet the order, payment, or business step remains incomplete.

To trace DLT publishing, inspect the template used by `DeadLetterPublishingRecoverer` or retry infrastructure. If a `@DltHandler` listener is instrumented, it produces its own DLT consume stage.

DLT records can carry original topic, partition, offset, exception class, or stack trace headers added by Spring Kafka depending on version/config. Never dump all exception headers into span attributes, as they can be huge or hold sensitive data.

## 17. Long retries and DLT replays: same trace or new trace?

Two strategies exist:

| Scenario | Tracing strategy | Note |
|---|---|---|
| Short retry delay, same workflow | Propagate trace context to form a linked chain of spans | Requires consistent header injection/extraction and sampling. |
| Long retry delay, hours/days | Keep context or start a new trace linked by event ID | Trace backend retention may be shorter than the workflow. |
| Operator DLT replay | Usually sensible to start a new trace for the replay operation | Retain original event ID and replay ID to trace history. |
| Replay issuing a new business command | New trace correlated to the source event | Distinguish semantics of a new command vs. old duplicate. |

OpenTelemetry provides **span links** to express causal relationships that are not strict parent-child links. They fit messaging, batching, and replays well when instrumentation supports them. Do not claim Spring Kafka automatically creates span links for every retry hop; verify library behavior or add custom instrumentation if dedicated links are needed.

Regardless of how trace IDs change, **the event ID for the same business effect must remain stable** to prevent duplicates on replay. Generating a fresh event ID for the same effect defeats inbox/deduplication guards.

## 18. Sampling and trace retention

A trace crossing multiple Kafka hops can miss spans because:

- Upstream sampling dropped the trace.
- One hop lost propagation headers.
- The retry producer lacked instrumentation.
- The exporter/collector overloaded or failed.
- The trace backend only retains data for a few days.
- Retry/DLT replay occurred after the original trace expired.
- The UI query window was too narrow.

Sampling and retention affect **telemetry only**; they do not change retry attempt counts or Kafka logic. To measure full traffic, use counters/metrics; to investigate a single event, use correlation IDs and structured logs.

### Tail sampling

An OpenTelemetry Collector can perform tail sampling to prioritize errors or high latency. However, multi-hour retries can exceed how long the collector buffers spans before making a sampling decision. Never expect a tail-sampling buffer to hold a trace across days; design policies within realistic resource limits.

## 19. Baggage and header security

Tracing baggage can propagate data across multiple services and hops when configured. Use baggage only for tiny, approved, genuinely necessary metadata.

Never arbitrarily put into baggage, trace tags, or Kafka retry headers:

- Passwords, API keys, access tokens, secrets.
- Phone numbers, emails, physical addresses, or payment details.
- Raw payloads or stack traces containing PII.
- User identifiers that inflate metric cardinality.

Kafka retries/DLTs can accumulate exception headers. Large header sizes raise network/storage overhead or even push messages past size limits. Bound trace/correlation fields and follow masking/retention policies.

## 20. Distinguishing trace visibility from delivery guarantees

A trace may show a producer send call occurred, yet that does not prove the broker acknowledged the record and the source offset committed.

| Seen in trace | Valid inference | Invalid assumption |
|---|---|---|
| Retry producer send span started | An attempt was made to forward the record | Broker durably stored the retry record. |
| Producer send span succeeded | Instrumented send operation succeeded | Source transaction/offset committed. |
| Retry consume span | A retry listener received the record | Business effect applied uniquely. |
| DLT publication span | A DLT handoff occurred | DLT ticket was resolved. |
| Listener span succeeded | Listener invocation finished | Kafka transaction definitely committed. |
| No span visible | No trace displayed in the query window | Record was lost from Kafka. |

Verify delivery using producer send results, Kafka topic/partition/offset, committed offsets, and recovery policies. Verify business outcomes via event ID and business audits. Tracing is an **investigation signal**, not a commit, retry, or idempotency mechanism.

## 21. Complementary metrics for retry tracing

A useful logical metric set:

| Metric | Meaning |
|---|---|
| `listener_attempts_total` | Total listener invocations including initial and retries. |
| `listener_failed_attempts_total` | Listener invocations that threw exceptions. |
| `retry_forwarded_total` | Records successfully handed off to retry topics per contract. |
| `retry_success_total` | Retry attempts that completed business processing. |
| `dlt_published_total` | Records confirmed published to DLT. |
| `business_applied_total` | New business events applied (requires idempotency). |
| `retry_wait_seconds` | Latency from forward to retry attempt. |
| `retry_topic_lag` | Backlog of the retry consumer group. |
| `dlt_unresolved_age` | Age of unresolved DLT records. |

The names above are **suggested custom instrumentation**, not built-in Spring Kafka metric names. In Prometheus, Counters export with `_total` and Timers/histograms with `_seconds` per registry naming conventions.

Never use `traceId` or `eventId` as metric labels. Pick bounded dimensions like service, environment, logical pipeline, retry stage, error category, and outcome.

## 22. Prometheus query examples

Assuming custom counters instrumented with `pipeline` and `stage` labels:

~~~promql
sum by (pipeline) (
  rate(app_kafka_listener_failed_attempts_total[5m])
)
~~~

Retry forwarding rate:

~~~promql
sum by (pipeline) (
  rate(app_kafka_retry_forwarded_total[5m])
)
~~~

Records confirmed published to DLT over one hour:

~~~promql
sum by (pipeline) (
  increase(app_kafka_dlt_published_total[1h])
)
~~~

Failed attempt ratio on the retry stage:

~~~promql
sum by (pipeline) (
  rate(app_kafka_listener_failed_attempts_total{stage="retry"}[5m])
)
/
clamp_min(
  sum by (pipeline) (
    rate(app_kafka_listener_attempts_total{stage="retry"}[5m])
  ),
  0.001
)
~~~

These queries are valid only when instrumentation records counters under the same contract. Never sum all attempts across source and retry topics and call that **unique business events**—one event can generate many attempts.

To measure retry backlog, use lag by retry topic/consumer group and record wait age; subtracting forward and consume counters across two time windows does not yield accurate backlog.

## 23. Minimal dashboard

| Dashboard panel | Question answered |
|---|---|
| Source listener failure rate | How many initial attempts are failing? |
| Retry topic forwarded rate | How many records are moving to retries? |
| Retry listener success/failure | Are retries actually recovering records? |
| Retry topic lag | Is backlog building on retry consumers? |
| Expected vs. actual retry delay | Are retries delayed by backoff or congestion? |
| DLT publication count | How many records exhausted retries and entered recovery? |
| Business applied rate | How many unique business events actually applied? |
| Trace exporter errors | Is telemetry lost at exporters/collectors? |
| Consumer rebalance/poll health | Are assignments lost or consumers blocked? |
| DLT unresolved age | How long before failed records must be handled/archived? |

A single-event trace panel is great when launched from a log/error exemplar or event ID link, yet should never be the only way to notice system-wide failures.

## 24. Testing trace propagation across a retry topology

Test against a real integrated Kafka broker or matching test environment with a tracing exporter / in-memory span collector and the same `@RetryableTopic` setup used by the service.

Transient failure then recovery scenario:

1. Enable Observation on source and retry listener containers.
2. Enable Observation on `KafkaTemplate` for both source publisher and retry forwarder.
3. Configure deterministic sampling in tests to avoid random span drops.
4. Publish an event with a fixed `eventId` and valid trace context.
5. Make the first listener invocation throw a controlled exception.
6. Wait for the record to forward to the retry topic.
7. Let the subsequent retry attempt succeed.
8. Assert the record preserves `eventId` and listener attempts match policy.
9. Assert related consume/send spans are captured with parent/link relationships matching your propagation strategy.
10. Reconcile Kafka coordinates, outcomes, and committed offsets per policy.

Terminal DLT scenario:

1. Fail every attempt.
2. Wait for the record to route to the DLT.
3. Verify origin metadata and `eventId` remain usable for tracing.
4. Confirm DLT publishing is instrumented via the right template.
5. Verify the outcome is terminal recovery, not business success.
6. If DLT replay is supported, verify replay trace and `eventId` correlation.

Never test by deliberately breaking ACLs, retry topics, or message headers on production Kafka.

### Testing broken context

In a dedicated test, deliberately use an uninstrumented retry publisher and observe the trace chain splitting. After enabling Observation on the right template, verify context injects/extracts properly. This verifies **the real active producer**, not just that the source listener emits a span.

## 25. Runbook: Trace stops after the first listener

1. Grab `eventId` and source Kafka topic/partition/offset from logs.
2. Check whether the record actually forwarded to the retry topic.
3. Identify which `KafkaTemplate`/recoverer published the retry record.
4. Check Observation on that forwarding template and retry container.
5. Safely inspect propagation headers on the retry record.
6. Compare W3C/B3 formats between producer and consumer.
7. Check sampling, exporter, collector, and backend retention.
8. Check whether the retry consumer has partition assignments, reached due time, or has lag.
9. While traces remain disconnected, trace via `eventId`/logs; never mistake a missing trace for a missing message.

## 26. Runbook: Retry wait exceeds backoff

1. Determine the forward timestamp, due time, and retry listener start time.
2. Check lag on the retry topic/partition.
3. Check consumer group member count, assignments, and pauses.
4. Check `max.poll.interval.ms`, rebalances, and non-responsive consumer events.
5. Measure retry listener processing duration; check for poison pills or dependency timeouts.
6. Check timestamp/retry metadata rules for your Spring Kafka version.
7. Distinguish intentional backoff from extra delay caused by backlog or outages.
8. Resolve the bottleneck, then monitor retry wait and business outcomes.

## 27. Runbook: Same event ID appears in multiple traces

1. Determine whether the event is undergoing automatic retry, DLT replay, or a new command.
2. Compare `eventId` and `correlationId` across topics.
3. Inspect `traceparent` at each Kafka hop and producer/consumer instrumentation linkage.
4. Check whether a custom recoverer strips headers.
5. Check async executors and context propagation.
6. Check sampling, tracer format, and exporter settings.
7. For replays days later, accepting a new trace linked by `eventId` is reasonable.
8. Never alter `eventId` to force traces together; protect idempotency first.

## 28. Runbook: DLT holds the record, but no DLT span appears

1. Confirm the actual DLT topic/partition/offset.
2. Identify which producer template/recoverer performed DLT publishing.
3. Check Observation configuration on that template.
4. Inspect send results and error handling, distinguishing send attempted from send acknowledged.
5. Inspect DLT headers, original Kafka metadata, and `eventId`.
6. Check trace sampling and exporter status.
7. Locate terminal errors in source/retry listener logs.
8. When the DLT record is replayed, preserve correlation to the source event.

## 29. Runbook: Complete trace, yet business logic applied twice

1. Collect `eventId` and all attempts across traces/logs.
2. Reconcile source offsets, crashes/rebalances, and Kafka commits.
3. Check whether the database committed before the Kafka offset committed.
4. Check inbox/unique `eventId` constraints inside the same transaction as business effects.
5. Check whether HTTP/external dependencies use idempotency keys.
6. If a replay generated a new `eventId`, determine whether that broke the deduplication contract.
7. Halt bulk replays if duplicates cause harm; compensate per policy.
8. Fix transaction/idempotency boundaries and retest. Tracing only proves the observed execution path, not exactly-once semantics.

## 30. Control table for tracing across retry topics

| Control point | Question | Evidence |
|---|---|---|
| Source listener | Is Observation enabled on the right container? | Effective container config, consume spans. |
| Retry listener | Do retry/DLT containers enable Observation? | Retry consume spans. |
| Producer forwarder | Does the retry/DLT `KafkaTemplate` enable Observation? | Producer spans and template wiring. |
| Propagation | Are headers injected/extracted in the right format? | Kafka headers, trace relationships. |
| Event identity | Does `eventId` stay stable across retries? | Application headers, structured logs. |
| Retry metadata | Does attempt number match version semantics? | Retry topic API/headers and logs. |
| Timing | Is processing duration separated from retry wait? | Timers, due times, consume timestamps. |
| Failure outcomes | Are failed attempts, forwards, DLT, and business applied separated? | Counters, recoverer results, and business state. |
| Kafka coordinates | Does each hop record its own topic/partition/offset? | Structured logs, broker metadata. |
| Sampling | Could spans drop due to sampler/exporter/retention? | Tracing config and collector metrics. |
| Async context | Do executors propagate context when needed? | Trace integration tests. |
| Security | Do headers/tags/logs avoid tokens, PII, and payloads? | Data policy and redaction. |
| Delivery | Are traces kept separate from offset/send confirmation? | Acks, committed offsets, DLT records. |
| Replay | Do replays preserve correlation and idempotency? | Replay operation ID, inbox/business audits. |
| Diagnosis | When traces break, can records still be found by `eventId`? | Logs, metrics, and Kafka coordinates. |

**Conclusion:** Retry topics introduce multiple **asynchronous Kafka hops** for the same business event. Tracing across these hops requires enabling Micrometer Observation on **listener containers and the exact `KafkaTemplate` instances that publish retries/DLTs**, propagating trace context via Kafka headers, and maintaining a **stable event ID** across retries. Each attempt should have its own span, retry wait times should be measured with timestamps/metrics, and DLT publication must remain distinct from business success. When traces are sampled out or lose context, rely on event IDs, logs, offsets, and retry metrics for truth; even when traces are complete, idempotency and delivery/recovery policies remain essential for business correctness.
