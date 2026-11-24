# Distinguishing metrics, logs, and traces

In a Spring Kafka system, a listener may still be running while consumer lag rises, a record may be retried multiple times before landing in a Dead Letter Topic (DLT), or processing may slow down because of the database even when the Kafka broker is healthy. To understand those situations, reading a single log line or a throughput chart is usually not enough.

The three foundational observability signals are **metrics**, **logs**, and **traces**. They describe the system from three distinct perspectives:

- **Metrics**: How many events occurred, how fast or at what rate are things changing, and how is latency distributed?
- **Logs**: At a specific point in time, which component did what, to which record, and with what outcome?
- **Traces**: Which components did an operation pass through, which step was slow or failed, and how are the steps related?

In the **Observability and Tracing** chapter of the **Spring Kafka Reliability Operations** module, the focus is distinguishing these three signals by **purpose, scope, conclusion accuracy, and cost**, then combining them to investigate retries, rebalances, consumer lag, DLTs, Kafka transactions, and database side effects.

**Guiding principle:** metrics, logs, and traces provide visibility and diagnostics; they never replace broker committed offsets, Kafka transaction outcomes, or database state when proving data was durably processed.

## 1. A Kafka incident seen through the three signals

Suppose the `payment-worker` service consumes `payments.authorized`, updates PostgreSQL, and publishes `payments.settled`:

~~~text
Payment API
     |
     v
payments.authorized (Kafka)
     |
     v
Spring Kafka payment-worker
     |
     +---- PostgreSQL
     |
     +---- payments.settled (Kafka)
~~~

After deploying a new version, consumer lag climbs. Operations teams want to answer:

1. When did lag start rising, and on which partitions?
2. Which records are retrying, and are exceptions coming from the database?
3. Is processing time spent in Kafka poll, validation, waiting for the connection pool, SQL, or producer sends?
4. Have Kafka outputs and input offsets committed?
5. Did any records reach the DLT, and did any DLT publishes fail?

| Question | Best-suited signal | Supporting signal |
|---|---|---|
| When did lag start rising and by how much? | **Metric** | Deployment/rebalance milestone logs |
| Which partition is slow? | **Metric** (lag/throughput per partition) | `topic-partition-offset` logs |
| Which exact record threw an exception? | **Structured log** | Trace if sampled |
| Is the DB or Kafka send slow? | **Trace** with per-step spans | Timer metrics, duration logs |
| How much did the error rate jump? | **Metric** (counter/rate) | Logs grouped by error |
| Did recovery pick retry or DLT? | **Log** recording the decision | Retry/DLT counters |
| Did the Kafka transaction commit? | Actual Kafka state and commit result | Commit log/metric/trace at the right boundary |

An effective investigation workflow typically begins with **a metric detecting the issue**, moves to **logs to locate specific records and exceptions**, and uses **traces to see the path and latency causes**.

## 2. Metrics: measurements aggregatable over time

**Metrics** are numeric measurements or distributions, usually appearing as time series with labels such as `service`, `topic`, `listener`, `outcome`, and `error_category`.

Common metric types:

| Type | Meaning | Spring Kafka examples |
|---|---|---|
| **Counter** | Cumulative event count, monotonically increasing over the meter's lifetime | Listener attempts, errors, retries, DLT publish failures |
| **Gauge** | Point-in-time observed value that can rise or fall | Outbox pending count, active connection pool |
| **Timer** | Execution durations and sample counts; can emit histograms | Listener processing duration, DB call duration |
| **Distribution summary** | Distribution of magnitudes, not necessarily time | Payload size, batch size |
| **Long-task timer** | Count and elapsed time of long operations still in flight | Separately instrumented long-running tasks |

Illustrative example (not mandatory default Spring Kafka metric names):

~~~text
app_kafka_listener_attempts_total{
  service="payment-worker",
  listener="payment-authorized",
  outcome="failed"
}

app_kafka_listener_duration_seconds_bucket{
  service="payment-worker",
  listener="payment-authorized",
  le="0.25"
}
~~~

Metrics suit dashboards, alerting, capacity planning, and Service Level Objectives (SLOs) because they aggregate cleanly across many instances over long periods.

### 2.1. Metrics detect trends; they do not explain every cause

`consumer_lag=50000` shows a large backlog under the active metric definition, yet does not explain why on its own. Possibilities include:

- Sudden producer throughput spike.
- Slow database queries or an exhausted connection pool.
- Listener endlessly retrying a poison record.
- Paused container.
- Continuous consumer group rebalances.
- Repeated deserializer exceptions.
- Failed offset commits or a fenced transactional producer.

Finding the root cause requires cross-checking processing latency, producer rates, error metrics, logs, and traces.

### 2.2. Counters and rates are two ways of reading data

A counter is cumulative within a process lifetime; after a restart it resets to zero. In Prometheus, you normally query `rate()` or `increase()` over a time window rather than comparing raw counter values across pods.

Conceptual PromQL example:

~~~promql
sum by (service, listener) (
  rate(app_kafka_listener_attempts_total{outcome="failed"}[5m])
)
~~~

Actual metric names depend on the exporter and meter setup. A sample with 1 failure out of 1 attempt has very different operational meaning from 10,000 failures out of 10,000 attempts; combine **rate, volume, and duration**.

### 2.3. Metric tags must control cardinality

A time series normally corresponds to a unique combination of label values. Putting `eventId`, `orderId`, `offset`, full exception messages, or trace IDs into tags can spawn millions of series.

**Good to use:**

~~~text
service=payment-worker
topic=payments.authorized
outcome=failed
error_category=database_timeout
environment=production
~~~

**Never use as metric tags:**

~~~text
payment_id=P-92837283
event_id=c8f6...
offset=98126812
trace_id=24ac...
exception_message="account 1234 unavailable..."
~~~

Per-event identifiers belong in logs or controlled trace attributes. Even labels like `partition` require weighing total partition count: helpful for drill-down, yet capable of inflating series counts on clusters with many topics and partitions.

## 3. Logs: evidence of specific events

**Logs** are records of specific events or decisions occurring during program execution. Logs normally include timestamp, severity, message, exception details, and contextual fields.

Example structured log emitted by an application:

~~~json
{
  "timestamp": "2026-11-15T10:14:23.551Z",
  "level": "ERROR",
  "service": "payment-worker",
  "listener": "payments-authorized",
  "eventId": "evt-58f3",
  "topic": "payments.authorized",
  "partition": 4,
  "offset": 18233,
  "attempt": 3,
  "errorCategory": "database_timeout",
  "action": "retry",
  "traceId": "7d4e3f3f988b45b7b768b729e73be102",
  "message": "Payment processing failed; retry scheduled"
}
~~~

A log like this tells you exactly **which record, where, what failed, and what decision the application made**. If operators see only `ERROR Failed!`, isolating causes and distinguishing records becomes very hard.

### 3.1. Logs should state facts, not unconfirmed outcomes

Compare:

~~~text
Wrong: "Kafka publish SUCCESS"
       immediately after KafkaTemplate.send() before the future completes

Clearer:
  kafka.send.submitted
  kafka.send.acknowledged
  kafka.transaction.committed
~~~

A completed send future does not mean the Kafka transaction committed; inside a transaction, an output can be acknowledged and still abort later. Likewise, `repository.save()` or an SQL `UPDATE` does not prove the database committed.

Event names should reflect **exact commit boundaries**. When using both a database and Kafka, logs should distinguish `db.tx.committed`, `kafka.tx.committed`, `kafka.tx.failed`, and `commit.outcome.unknown` if confirmation is lost at any step.

### 3.2. Structured logs support correlation

Useful fields for a Kafka listener:

- `service`, `instance`, `listenerId`, `consumerGroup`.
- `topic`, `partition`, `offset`.
- `eventId`, `correlationId`, and business key when non-sensitive.
- `traceId`, `spanId` when tracing context is present.
- `retryAttempt`, `retryTopic`, `dltTopic`.
- `errorCategory`, `action`, `durationMs`.

Never log full payloads by default—especially personal data, secrets, payment cards, or authentication tokens. Enforce masking/redaction and retention policies.

### 3.3. Multiple log entries do not mean multiple business events processed

A record can be executed multiple times by a listener due to retries, rollbacks, or redeliveries. A `"received event E"` log may appear five times even though the final business effect committed only once.

Therefore, read `listener.attempts` metrics, logs keyed by `eventId + attempt`, and durable business state evidence together. Never count `received` log lines as completed payments.

## 4. Traces: execution paths and relationships across steps

A **distributed trace** describes one operation across multiple components and services. Traces consist of **spans**, each having start/end timestamps, an operation name, attributes, status, and optional events or links.

Conceptual diagram:

~~~text
HTTP POST /payments
   |
   +-- validate request                        5ms
   +-- DB insert                              18ms
   +-- Kafka produce payments.authorized      12ms

Kafka consume payments.authorized
   |
   +-- decode/validate                         4ms
   +-- paymentService.apply                    8ms
   +-- PostgreSQL update                     620ms
   +-- Kafka produce payments.settled          20ms
~~~

Traces answer "which step took 620ms?" and "did the error happen before or after the DB call?" They are especially valuable for workflows crossing producers, Kafka topics, consumers, HTTP dependencies, databases, and multiple services.

Kafka is an **asynchronous boundary**. Producer and consumer can live in different processes and execute far apart in time. Depending on instrumentation and propagation, a consumer span may be a child of propagated context, a new trace connected via span links, or uncorrelated if propagation failed. Never assume every record forms a complete single span tree.

### 4.1. Trace ID, span ID, event ID, and offset are not identical

| Identifier | Role | Across retries/replays |
|---|---|---|
| `traceId` | Groups spans of one trace | Can change across attempts or after replays |
| `spanId` | Identifies a specific operation inside a trace | Changes on every span |
| `eventId` | Application-assigned business event ID | Should stay stable across retries/DLT/replays |
| `correlationId` | Links multiple units of work in one workflow | Can outlive a single trace |
| `topic-partition-offset` | Record location within a Kafka topic | Changes when moved to a new topic |

**Never use trace ID as an idempotency key**. The same business event can be reprocessed a day later under a fresh trace. Use `eventId` / a stable business key for deduplication, and trace ID to investigate a single execution.

### 4.2. Traces can be sampled

Systems rarely retain traces for 100% of Kafka records at high throughput. When traces are sampled, failing to find a trace for a given event does not prove that event never ran.

To count error rates or compute exact traffic-wide SLOs, rely on metrics. To audit every sensitive operation, maintain a dedicated durable audit log/ledger; trace backends apply sampling and retention and cannot serve as a default substitute.

## 5. Comparison table: metrics, logs, and traces

| Criterion | Metric | Log | Trace |
|---|---|---|---|
| Unit | Numeric value / distribution over time | Single event / decision | Operation made of spans |
| Strongest at | Trends, SLOs, alerting | Forensics and record detail | Path and latency breakdown |
| Typical cost | Low if labels are bounded | Scales with log volume/indexing | Scales with span volume/sampling |
| Identifying a single record | Unsuitable as a label | Ideal | When the trace is recorded |
| Finding specific errors | Directional, grouped | Exact exception and context | Links root cause and failing step |
| Measuring throughput | Ideal | Hard and expensive to aggregate | Incomplete when sampled |
| Measuring p95 latency | Timer histograms | Duration logs can assist | Explains why a few executions were slow |
| Guarantees durability | No | No | No |

Never put any of these three telemetry signals in place of a transaction log or database. They are **observability**, not the system of record for final business truth.

## 6. Combining the three signals across a Kafka workflow

A correlation model:

~~~text
HTTP request
     |
     v
KafkaTemplate producer
     |
     +---- eventId, correlationId
     +---- tracing propagation headers (if enabled)
     v
Kafka topic
     |
     v
@KafkaListener
     |
     +---- metric: invocation, duration, outcome
     +---- log: eventId, topic, partition, offset, exception
     +---- trace: consumer span and business spans
     |
     +---- DB / HTTP dependency
     |
     +---- Kafka output or retry/DLT
~~~

Designs should distinguish two metadata groups:

1. **Business correlation:** `eventId` and `correlationId`, managed to survive retries and replays.
2. **Execution correlation:** `traceId`, `spanId`, and span links, describing a single execution or chain of executions.

Kafka headers can carry context across services. Still, automatic injection/extraction requires proper instrumentation; using `KafkaTemplate` and `@KafkaListener` alone does not automatically produce queryable distributed traces.

## 7. Micrometer Metrics and Micrometer Observation

In Spring Boot / Spring Kafka, **Micrometer Metrics** provides `Counter`, `Timer`, `Gauge`, and meter registries. **Micrometer Observation** instruments an operation via `ObservationRegistry`; configured handlers turn observations into metrics and tracing spans.

~~~text
Spring Kafka listener / KafkaTemplate
              |
              v
       Micrometer Observation
              |
        +-----+------+
        |            |
        v            v
  Metrics handler  Tracing handler
        |            |
        v            v
  MeterRegistry    Tracer/exporter
        |            |
        v            v
  Prometheus       OTLP/Zipkin/etc.
~~~

**Observation is an instrumentation API**, not a fourth storage type. Having an `ObservationRegistry` without a tracer/bridge means the application can emit metrics without exported traces. Conversely, configuring tracing does not automatically export all Kafka client metrics.

Micrometer Observation also distinguishes:

- **Low-cardinality key-values:** suitable as metric labels, requiring a bounded value set.
- **High-cardinality key-values:** suited for tracing metadata, while still requiring sensitivity and cost controls.

Never attach `eventId`, payloads, or exception messages as low-cardinality tags.

## 8. Enabling Observation for listeners and KafkaTemplate

Spring Kafka versions supporting observation on listener containers:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, PaymentEvent>
        paymentListenerFactory(
                ConsumerFactory<String, PaymentEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, PaymentEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties().setObservationEnabled(true);

    return factory;
}
~~~

For `KafkaTemplate` on supported versions:

~~~java
@Bean
KafkaTemplate<String, PaymentEvent> paymentTemplate(
        ProducerFactory<String, PaymentEvent> producerFactory) {

    var template = new KafkaTemplate<>(producerFactory);
    template.setObservationEnabled(true);
    return template;
}
~~~

To achieve **distributed tracing**, the application also needs a Micrometer Tracing bridge (e.g., OpenTelemetry or Brave), propagation configuration, and an appropriate exporter/backend.

Operational checks:

- Identify which custom listener factory `@KafkaListener` actually uses.
- Identify which `KafkaTemplate` publishes to main, retry, and DLT topics.
- Verify both producer and consumer enable propagation when linking traces across Kafka.
- Do not assume auto-configuration from one Spring Boot version applies identically to custom beans.
- Test headers and spans explicitly rather than merely seeing a tracing dependency in the build.

### 8.1. Observation does not mean transaction commit

A `KafkaTemplate` send observation may end as soon as the producer send finishes; inside a Kafka transaction, the transaction can commit or abort afterward. A listener observation may likewise finish before the container commits offsets.

If you need metrics/logs reflecting **Kafka transaction committed**, instrument transaction completion directly. If you need **database committed**, observe the corresponding database transaction. Never rename listener method success as `"exactly once achieved"`.

## 9. Creating custom Timers for business logic

Kafka client metrics do not inherently know whether "the payment was accurately applied in the database." Applications can instrument business operations:

~~~java
@Component
public class PaymentProcessor {

    private final PaymentService service;
    private final MeterRegistry registry;

    public PaymentProcessor(
            PaymentService service,
            MeterRegistry registry) {
        this.service = service;
        this.registry = registry;
    }

    public void process(PaymentEvent event) {
        Timer.Sample sample = Timer.start(registry);
        String outcome = "success";

        try {
            service.apply(event);
        } catch (RuntimeException exception) {
            outcome = "failure";
            throw exception;
        } finally {
            sample.stop(registry.timer(
                    "app.payment.processing.duration",
                    "outcome", outcome));
            registry.counter(
                    "app.payment.processing.attempts",
                    "outcome", outcome).increment();
        }
    }
}
~~~

This snippet measures **the method attempt**. If the database transaction commits after the method returns, or the Kafka transaction commits in the outer container, an attempt marked `"success"` does not prove every resource committed.

When metrics must reflect durable business success, place measurement points at business commit boundaries and use distinct names such as `processing.attempt.success`, `db.commit.success`, and `kafka.transaction.commit.success`.

### 9.1. Avoid double counting when the framework already instruments

When the listener container already enables observation, wrapping the entire listener method in a custom `Timer` duplicates the framework timer's meaning. Prefer:

- Framework observation for listener invocations and `KafkaTemplate` sends.
- Custom observations for distinct business steps (validation, DB updates, HTTP calls).
- Custom counters for business outcomes/reconciliation unknown to the framework.
- Kafka client/broker metrics for fetches, polls, retry requests, and throughput.

## 10. Creating a custom Observation for a processing step

Example instrumenting validation:

~~~java
@Component
public class PaymentValidator {

    private final ObservationRegistry registry;

    public PaymentValidator(ObservationRegistry registry) {
        this.registry = registry;
    }

    public void validate(PaymentEvent event) {
        Observation observation =
                Observation.start("payment.validate", registry);

        observation.lowCardinalityKeyValue(
                "operation", "payment-validation");

        try (Observation.Scope scope = observation.openScope()) {
            validateFields(event);
        } catch (RuntimeException exception) {
            observation.error(exception);
            throw exception;
        } finally {
            observation.stop();
        }
    }
}
~~~

Imports:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
~~~

With matching handlers, this operation emits a duration metric and a validation span. If you want the trace to carry an event-related attribute, use a controlled, PII-free high-cardinality attribute—**never** turn event IDs into metric tags.

## 11. Structured logging inside @KafkaListener

A record listener can safely log context:

~~~java
@KafkaListener(
        id = "payment-listener",
        topics = "payments.authorized",
        groupId = "payment-worker")
public void handle(ConsumerRecord<String, PaymentEvent> record) {
    PaymentEvent event = record.value();

    log.info(
            "Payment received eventId={} topic={} partition={} offset={}",
            event.eventId(),
            record.topic(),
            record.partition(),
            record.offset());

    paymentService.apply(event);
}
~~~

With structured JSON logging, these fields become keys rather than strings requiring regex parsing. If your tracing stack populates `traceId` and `spanId` into MDC, logs link directly to traces.

However, MDC typically relies on thread-local context. If a listener delegates work to an executor, future, or callback on another thread, use proper context propagation; otherwise, logs **lose their trace ID** or even pick up stale context from thread reuse.

Never invoke `KafkaConsumer` methods from worker threads solely to enrich logs or traces. `KafkaConsumer` is not thread-safe for normal operations; acks and commits must follow framework semantics.

## 12. Correlation via Kafka headers

A producer can attach tracing context in Kafka headers per the configured propagator (e.g., W3C Trace Context). The consumer extracts context when receiving the record:

~~~text
HTTP request / Producer span
            |
            v
Kafka record headers:
   traceparent / tracestate (if enabled)
   business eventId
            |
            v
Kafka consumer:
   extract context
   create consumer observation/span
   business log carries eventId and traceId
~~~

Do not assume tracing headers always survive custom producers, retry topics, or DLTs. Test every publisher and recoverer type.

Also distinguish:

- **Tracing propagation headers** may change per operation/attempt.
- **Business correlation headers** should be preserved across retries/replays per contract.
- **DLT error headers** can grow record size across multiple hops.
- **Sensitive headers** must never be blindly copied or exported to telemetry.

A Kafka record may sit in a topic for hours. Tracing spans represent instrumented execution; queue dwell time does not appear automatically as a synchronous child span lasting hours.

## 13. Retries and DLT: what should the three signals describe?

A poison record might go through:

~~~text
orders.created offset 481
      |
      +---- listener attempt 1 -> DB timeout
      |
      +---- listener attempt 2 -> DB timeout
      |
      +---- listener attempt 3 -> validation failure
      |
      v
DeadLetterPublishingRecoverer
      |
      +---- DLT publish ack / failure / unknown
      |
      v
orders.created.DLT
~~~

| Stage | Metric | Log | Trace |
|---|---|---|---|
| Listener attempts | Retry/error counters | Event ID, attempt, exception | Attempt span if sampled |
| Backoff | Retry duration/count | Backoff decision | Span/event if instrumented |
| DLT publishing | Attempts, acked, failed, unknown | Source offset, destination, publish error | Producer span if sampled |
| Recovery transaction | Commit/abort metrics | Commit outcome, fencing details | Transaction span if present |
| DLT triage/replay | Unresolved age, replay count | Event ID, action, operator | New trace or linked trace |

**DLT publish success is not business success.** A record sent to a DLT still has not been processed by business logic. Metrics should separate `dlt.publish.acked`, `dlt.tx.committed`, `dlt.consumed`, and `dlt.resolved` when workflows include those stages.

### 13.1. Avoiding confusion when retries create multiple traces

A business event may retry inside the same container and then route to a retry topic minutes later. The tracing backend may store multiple traces or drop the original trace due to retention.

Therefore, for long-lived incident lookups, use **event ID** plus **original topic-partition-offset** as the primary correlation keys. Trace IDs explain an instrumented execution path, not a business record's unique key.

## 14. Transactional listeners and boundaries to measure

In a Kafka transactional listener:

~~~text
Kafka consumer receives record
       |
       v
Kafka transaction begins
       |
       +---- listener processing
       +---- KafkaTemplate.send(output)
       +---- input offset added to transaction
       |
       v
Kafka transaction COMMIT or ABORT
~~~

Distinguish:

1. **Method duration**: how long the listener method ran.
2. **Send acknowledgment**: broker ack for the output record.
3. **Kafka transaction commit**: outputs and input offsets committed in the Kafka transaction.
4. **Database transaction commit**: separate DB state commit, if the listener writes to a DB.

If the method returns cleanly yet the Kafka transaction commit fails, `listener_method_success` must never be interpreted as `kafka_tx_commit_success`. If the DB commits and Kafka rolls back, the input may redeliver and the business DB requires idempotency.

Logs and traces assist investigations, yet **never** turn a Kafka transaction and a database transaction into an XA transaction. When zero DB/event loss is required, consider transactional outbox/inbox patterns and reconciliation.

## 15. Consumer lag and latency: measuring the right target

Lag typically relates to the gap between log end offset and committed group offset or consumer position depending on the metric source.

~~~text
Partition p0:
  log end offset:          30,000
  committed group offset:  27,000
  lag by committed:         3,000 records
~~~

Lag is not absolute latency and does not explain why records are piling up. To find the cause, combine:

- Incoming records/sec vs. consumed records/sec.
- Processing p95/p99.
- Database connection wait and query latency.
- Listener error/retry rates.
- Rebalance count/duration.
- Pause state and offset commit errors.

Also separate four kinds of latency:

| Latency type | From what to what? | Role |
|---|---|---|
| Producer send latency | Submit send → broker ack | Producer/broker performance |
| Queueing delay | Record published/created → consume starts | Time waiting inside Kafka |
| Listener processing | Listener start → return/throw | Listener logic performance |
| End-to-end business | Event created → durable business state | Real SLO |

A 200ms listener trace does not mean the event took only 200ms from producer emission; it may have sat in the topic for 15 minutes beforehand. Measuring end-to-end requires trustworthy source timestamps and synchronized clocks.

## 16. Trace sampling and retention

Recording 100% of traces at 100,000 messages/second is expensive to store. Common strategies:

- **Head sampling:** decides when a trace starts.
- **Tail sampling:** collector selects traces after observing outcomes such as errors or duration.
- **Priority sampling:** prioritizes keeping error/slow traces if supported by the stack.
- **Per-service sampling:** tunes rates per service throughput and budget.

Consequences:

- Having logs without a trace is normal when tracing is sampled.
- Never use total sampled spans to compute system-wide error rates.
- Producer and consumer may sample differently, leaving traces missing spans.
- A DLT record replayed days later may no longer have its original trace.
- Trace attributes containing PII remain a risk even at low sampling rates.

Metrics cover SLO statistics and alerts, while logs and sampled traces support deep dives during incidents.

## 17. Storage cost and telemetry security

| Signal | Primary cost driver | Risks to control |
|---|---|---|
| Metric | Time series count from tags | Cardinality explosion, sensitive labels |
| Log | Storage volume and indexing | Payload/headers/PII, log storms, retention |
| Trace | Span and attribute volume | High-cardinality data, SQL/URL secrets, sampling |

Production rules:

1. Never log raw record payloads by default.
2. Never place access tokens, passwords, or personal data into tracing baggage.
3. Never use event IDs as low-cardinality metric tags.
4. Bound Kafka tracing/baggage header sizes.
5. Log exceptions only to the necessary level with redaction.
6. Set retention and access permissions by telemetry sensitivity.
7. Use structured logs to query event IDs; use metrics for aggregate statistics.
8. Tracing exporters must never block listeners indefinitely when the observability backend fails.

A failing observability system must never make Kafka processing unsafe or turn a telemetry endpoint into a mandatory dependency for committing records.

## 18. A dashboard combining all three signals

Suggested dashboard layout:

~~~text
Spring Kafka Reliability Dashboard
|
+-- Metrics: health and SLOs
|     consumer lag by topic/partition
|     records/sec, processing errors/sec
|     listener processing p50/p95/p99
|     retry/DLT rates and transaction aborts
|     DB/HTTP latency
|
+-- Logs: event investigation
|     filter by service/topic/error category
|     search event ID or source offset
|
+-- Traces: paths and bottlenecks
      slow/error traces
      producer/consumer spans
      DB/HTTP child spans
~~~

If your observability backend supports **exemplars**, metric points can link to a representative trace. Exemplars remain samples, however; not every record or metric point has a complete trace.

Never build a dashboard with just one `"Kafka healthy"` indicator. A running container does not guarantee the consumer is making progress, and high DLT publish success does not mean business errors are low.

## 19. Incident walkthrough: DLT publish failure

Suppose an operator sees:

~~~text
Metrics:
  listener.errors/sec          rising
  dlt.publish.attempts/sec     rising
  dlt.publish.failures/sec     rising
  consumer_lag{partition="2"}  rising
~~~

Metrics show the recovery path is failing, yet cannot pinpoint why. Structured log:

~~~text
ERROR service=orders-worker
      event_id=evt-7aa2
      source_topic=orders.created
      partition=2 offset=481
      dlt_topic=orders.created.DLT
      action=publish_dlt
      error_category=authorization
      message="DLT write unauthorized"
~~~

If a trace was retained:

~~~text
consume orders.created
   |
   +-- business validation -> error
   |
   +-- recoverer publish DLT -> authorization error
~~~

Next steps: check the DLT topic, partitions, and producer ACLs; after fixing, watch DLT publish acks / transaction commits, source committed offsets, and falling lag. Never manually commit source offsets just to make lag drop before the record is safely preserved in the DLT.

## 20. Incident walkthrough: slow database causing lag

Metrics:

~~~text
consumer_lag rising sharply
listener_processing_p95 rising
kafka_fetch_latency stable
db_pool_active near limit
~~~

Log:

~~~text
WARN event_id=evt-58f3 topic=payments.authorized
     partition=4 offset=18233
     error_category=db_connection_timeout
     action=retry
~~~

Trace:

~~~text
consume payments.authorized
   |
   +-- validation                    5ms
   +-- DB connection acquisition  1800ms
   +-- SQL update                    40ms
~~~

Reasonable conclusion: the bottleneck lies in the database pool or dependency, not Kafka broker fetching. Changing `pollTimeout` usually will not fix the root cause. Investigate pool capacity, connection leaks, query plans, lock contention, and retry policies.

After remediation, metrics confirm latency/lag recovery; logs show which failing records retried or went to the DLT; traces confirm DB wait times dropped on sampled executions.

## 21. Testing instrumentation

Tests must prove **signals are recorded at the right boundaries**, not merely that an observer method ran.

### 21.1. Metric test

With `SimpleMeterRegistry` or a matching test registry:

~~~java
SimpleMeterRegistry registry = new SimpleMeterRegistry();

// processor and service test double initialized in setup.
processor.process(event);

double attempts = registry
        .find("app.payment.processing.attempts")
        .tag("outcome", "success")
        .counter()
        .count();

assertThat(attempts).isEqualTo(1.0);
~~~

This is an illustrative fragment: `processor` and `event` are prepared in test setup. Also test error paths, `Timer` durations, and confirm no tags contain event IDs.

### 21.2. Log test

Use a test appender or log capture to verify:

- Logs contain event ID and source `topic-partition-offset`.
- Retry/DLT stages are classified accurately.
- Error categories are clear.
- No sensitive payloads leak.
- `traceId`/`spanId` appear when a tracing scope is active.
- Repeated retries do not emit unbounded full stack traces.

Avoid brittle byte-for-byte assertions on full stack traces unless needed; versions and exception wrapping can vary.

### 21.3. Tracing test

With an in-memory tracing exporter / test backend:

1. Enable observation on `KafkaTemplate` and listener containers.
2. Produce a record with context propagation.
3. Have the consumer receive the record and create a business span.
4. Assert producer/consumer observations appear per contract.
5. Assert correlation propagation or span links match actual configuration.
6. Throw an exception and assert matching span error events/status.
7. Ensure event IDs never leak into low-cardinality metric tags.
8. If an executor is used, verify context is neither lost nor leaked to another record.

Do not hardcode a strict parent-child tree if your tracing stack uses span links or sampling. Tests should verify the chosen correlation semantics.

### 21.4. Kafka + database integration test

Use Kafka Testcontainers / Embedded Kafka and a real database to verify requirements such as:

- Logs and metrics accurately reflect record retries.
- DLT publish failures are observed when ACLs/topics are missing or serializers fail.
- Kafka transactional send acks are not mislogged as transaction commits.
- DB commits and Kafka commits are measured/logged separately.
- Redelivery of the same event ID produces no duplicate business side effects.
- When the tracing backend is unavailable, Kafka listeners continue operating per policy.
- After rebalances/restarts, MDC from a previous record does not leak into a new record.

These tests validate observability at real boundaries rather than merely mocking listener method calls.

## 22. Mistakes to avoid

- **Counting log lines as business events:** one record can retry many times.
- **Putting event IDs in metric tags:** causes cardinality explosion.
- **Treating lag metrics as root causes:** lag is only a symptom with many possible sources.
- **Treating traces as complete audits:** traces undergo sampling and retention.
- **Treating trace ID as an idempotency key:** replays can change traces.
- **Enabling tracing on producers without consumers:** propagation breaks.
- **Assuming every thread gets MDC automatically:** async executors need context propagation.
- **Treating `KafkaTemplate` send spans as committed Kafka transactions:** sending and committing differ.
- **Treating listener method success as durable DB success:** transactions may commit after the method.
- **Watching only the main topic and forgetting retry/DLT:** records change topics.
- **Ignoring queueing delay:** fast listener processing can still miss end-to-end SLAs.
- **Logging raw payloads/headers:** security risks and storage costs.
- **Creating spans for every trivial helper:** adds overhead and obscures real signals.
- **Never testing metric tags:** applications can silently generate millions of time series.
- **Using telemetry instead of transactional outbox/idempotency:** observing does not create data guarantees.

## 23. Choosing signals by need

| What do you need to know? | Primary choice |
|---|---|
| How many records fail per minute? | Metric Counter/Rate |
| What is p95 listener processing time? | Metric Timer/Histogram |
| Why did the record at offset 481 fail? | Structured Log |
| Did the service choose retry or DLT? | Log + recovery counter |
| Which HTTP request originated this Kafka command? | Trace + business correlation |
| Which DB query slowed processing down? | Trace + DB latency metric |
| Which partition holds the consumer group lag? | Kafka lag metric |
| Was the DLT record committed by Kafka? | Kafka commit result / committed state + boundary log/metric |
| Was the payment applied exactly once? | Database/inbox/ledger state; telemetry assists |
| Is the SLO being breached? | Metric measuring the right end-to-end boundary |
| Why is the SLO being breached? | Logs + representative traces |

**Conclusion:** Metrics answer *magnitude and trends*; logs answer *specific events and decisions*; traces answer *paths and per-step costs*. In Spring Kafka, all three signals should connect through event ID, source `topic-partition-offset`, and trace context, while durable processing outcomes still require verification against Kafka commits/offsets and database state. Using each tool at its proper boundary catches failures earlier, shortens investigations, and prevents false conclusions like "listener succeeded means the transaction committed" or "DLT publish was called means the record is safe."

