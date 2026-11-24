# DLT publish success and failure

In Spring Kafka, a record that fails processing after exhausting retries can be routed to a **Dead Letter Topic (DLT)** for investigation or reprocessing. However, an error handler deciding to "recover the record" does not mean the record was **successfully written to Kafka**. The DLT may lack partitions, the producer may lack write permissions, the serializer may fail, the broker may be temporarily unresponsive, or the recovery transaction may abort. A system that counts recoverer invocations without measuring DLT send outcomes creates a false sense of security.

The **DLT publish success and failure** lesson in the **Monitoring and metrics** chapter focuses on precisely defining success, instrumenting `DeadLetterPublishingRecoverer` and the Kafka producer, tracking publish/transaction/offset outcomes, designing alerts, diagnosing broken recovery paths, and testing failure windows that can lead to lost or duplicate records.

## 1. Where DLT sits in the Spring Kafka flow

Suppose a service reads `orders.created` and processes orders. On transient errors, the framework can retry. If errors persist past the retry limit, the system uses a recoverer to send the record to the DLT:

~~~text
orders.created
       |
       v
@KafkaListener
       |
       +---- Success -> commit offset per policy
       |
       +---- Failure -> DefaultErrorHandler
                                  |
                                  v
                             Retry / backoff
                                  |
                     +------------+--------------+
                     |                           |
                  Success                 Retries exhausted
                     |                           |
                     v                           v
             Processed OK            DeadLetterPublishingRecoverer
                                                 |
                                  +--------------+--------------+
                                  |                             |
                             DLT publish OK               DLT publish failed
                                  |                             |
                                  v                             v
                         orders.created.DLT             Recovery incomplete
~~~

In a transactional listener model, `DefaultAfterRollbackProcessor` can coordinate recovery after rollback; in non-blocking retries, `@RetryableTopic` routes records through retry topics and the DLT. Common to all is that **publishing to the DLT is a separate Kafka operation** and can fail.

A DLT is a physical topic with partitions, replication, retention, ACLs, producer serializers, and monitoring. It is not an in-memory buffer inside Spring Boot. Therefore, a reliable recovery flow must verify publish outcomes instead of merely confirming that retry logic ran out of attempts.

## 2. Distinguishing five success milestones

The word "success" easily skews metrics when different engineering teams interpret it differently.

~~~text
[1] recoverer invoked
        |
        v
[2] KafkaTemplate.send() accepted
        |
        v
[3] broker ACKs record send
        |
        v
[4] Kafka transaction COMMIT (if any)
        |
        v
[5] DLT consumer receives and processes record
~~~

| Milestone | Suggested metric name | What can be concluded | What cannot yet be concluded |
|---|---|---|---|
| 1 | `recovery_attempt` | Started trying to send failed record to DLT | Whether producer sent or broker received it |
| 2 | `send_submitted` | Producer accepted send request | Whether broker acked |
| 3 | `send_acked` | Send future completed successfully per producer policy | Whether Kafka transaction committed |
| 4 | `tx_committed` | Transaction containing DLT record committed | Whether DLT consumer handled business work |
| 5 | `dlt_processed` | DLT workflow read/processed record | Whether business issue is resolved if only read |

With a **non-transactional producer** and `acks=all`, milestone 3 signals that the broker acknowledged the record per durability config. Yet retention, operations, and infrastructure incidents still affect the record's later lifecycle.

With a **transactional producer**, a send future can complete successfully **before transaction commit**. Consumers using `isolation.level=read_committed` only see data from committed transactions. Therefore, `send_acked` must never be renamed to `tx_committed`.

Reading a DLT record also differs from **business recovery completed**: a record can sit in the DLT for weeks even when the initial publish succeeded.

## 3. Failures are not just a single exception

Failures can arise before, during, or after sending:

| Stage | Example error | Consequence |
|---|---|---|
| Destination resolution | Wrong DLT name, non-existent partition | Recoverer has no valid write destination |
| Serialization | Value is raw bytes while serializer only supports DTO | Record cannot be serialized |
| Authorization | Missing `WRITE` permission on DLT | Broker rejects publish |
| Broker/network | Leader unavailable, disconnect, timeout | Send fails or outcome is unknown |
| Size validation | Payload and headers exceed record limit | Producer/broker rejects |
| Transaction | Producer fenced, commit timeout, coordinator error | Transaction may abort or outcome is unknown |
| Offset bookkeeping | DLT write OK yet source offset uncommitted | Record may redeliver and create DLT duplicates |

Some errors are **permanent**, such as missing ACLs, incompatible serializers, or invalid partitions. Infinite retries will not fix them. Others can be **transient**, such as a broker leader election or brief network interruption.

In particular, a timeout occurring right while the broker processes a request creates an **unknown outcome**. Never assume "app caught an exception" equals "broker definitely did not store the record."

## 4. DeadLetterPublishingRecoverer is the critical junction

`DeadLetterPublishingRecoverer` is commonly used with `DefaultErrorHandler` or an appropriate recovery mechanism. It constructs a producer record for the DLT, attaches error metadata, and invokes Kafka operations to publish.

Example routing to a DLT based on the source topic:

~~~java
@Bean
DeadLetterPublishingRecoverer dltRecoverer(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    return new DeadLetterPublishingRecoverer(
            kafkaTemplate,
            (record, exception) ->
                    new TopicPartition(
                            record.topic() + ".DLT",
                            record.partition()));
}
~~~

Imports:

~~~java
import org.apache.kafka.common.TopicPartition;
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
~~~

Here, a source record on partition `p` is sent to the same partition `p` of `<source>.DLT`. The DLT must exist and have matching partitions; otherwise publishing fails. Depending on design, a different destination resolver can be chosen; keep rules stable so infrastructure and monitoring agree.

### 4.1. Beware of asynchronous producer sends

A Kafka send call can be accepted into the producer buffer before any broker acknowledgment arrives. If recovery logic merely checks "did not throw immediately," it may prematurely conclude the record is safe in the DLT.

Spring Kafka provides options on `DeadLetterPublishingRecoverer` to handle send failures:

- `setFailIfSendResultIsError(true)`: propagates detected send errors into recovery failure.
- `setWaitForSendResultTimeout(Duration)`: bounds how long the recoverer waits for the send result when verifying outcomes.

Example:

~~~java
@Bean
DeadLetterPublishingRecoverer confirmedDltRecoverer(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    var recoverer = new DeadLetterPublishingRecoverer(
            kafkaTemplate,
            (record, exception) ->
                    new TopicPartition(
                            record.topic() + ".DLT",
                            record.partition()));

    recoverer.setFailIfSendResultIsError(true);
    recoverer.setWaitForSendResultTimeout(Duration.ofSeconds(10));

    return recoverer;
}
~~~

Additional import: `java.time.Duration`. Ten seconds is illustrative and should be tuned to client timeouts, real load, and recovery goals.

Default behavior and API details must be verified against your Spring Kafka version. Even if a send is acked, if it runs inside a transaction **never infer final commit** from the send result alone.

### 4.2. When the recoverer fails, never silently ignore it

Suppose the error handler exhausted retries for offset 75. The recoverer attempts to publish to the DLT and hits an authorization failure. If the application swallows the error and treats recovery as complete, the source offset may be committed under an improper configuration, dropping the failed record from the main path **with no copy in the DLT**.

Thus, when "never lose poison records" is a requirement, publish failures must propagate back to error handling/recovery to be handled further: retry at an appropriate time, stop the container, alert, and preserve the ability to re-read from the committed offset.

Do not arbitrarily tweak `ackAfterHandle`, `commitRecovered`, or ack modes without understanding the relationship between recovery success and offset commits.

## 5. Instrumenting DLT with Micrometer

A useful pattern is wrapping `DeadLetterPublishingRecoverer` in a `ConsumerRecordRecoverer` to record actual attempts and outcomes.

Example for a **non-transactional** path:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import org.apache.kafka.common.TopicPartition;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.ConsumerRecordRecoverer;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

import java.time.Duration;

@Bean
DefaultErrorHandler monitoredErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate,
        MeterRegistry registry) {

    var publisher = new DeadLetterPublishingRecoverer(
            kafkaTemplate,
            (record, error) ->
                    new TopicPartition(
                            record.topic() + ".DLT",
                            record.partition()));

    publisher.setFailIfSendResultIsError(true);
    publisher.setWaitForSendResultTimeout(Duration.ofSeconds(10));

    ConsumerRecordRecoverer observedRecoverer = (record, error) -> {
        registry.counter(
                "app.kafka.dlt.publish.attempts",
                "source_topic", record.topic()).increment();

        try {
            publisher.accept(record, error);

            registry.counter(
                    "app.kafka.dlt.publish.results",
                    "outcome", "send_acked",
                    "source_topic", record.topic()).increment();

        } catch (RuntimeException publishError) {
            registry.counter(
                    "app.kafka.dlt.publish.results",
                    "outcome", "failed_or_unknown",
                    "source_topic", record.topic()).increment();

            throw publishError;
        }
    };

    return new DefaultErrorHandler(
            observedRecoverer,
            new FixedBackOff(1_000L, 2L));
}
~~~

Metric semantics here:

1. `attempts` increments when the recoverer is called, **not** on every listener retry.
2. `send_acked` increments after the recoverer returns **with send-result waiting enabled** in this example.
3. `failed_or_unknown` increments when the recoverer throws an exception; timeout cases may leave the true broker state unknown.
4. The exception **is rethrown**, not swallowed.
5. Because this example assumes non-transactional DLT publishing, `send_acked` reflects acknowledgment, not Kafka transaction commit.

The `app.kafka.*` names are application-defined; the framework does not automatically create these exact counters. If producer transactions are used, measure transaction commit where commit results are actually known, not in this wrapper.

### 5.1. Never increment success before sending

Wrong:

~~~java
registry.counter("dlt.publish.success").increment();
publisher.accept(record, error);
~~~

If the publish fails, the metric is already wrong. Even when incrementing after `publisher.accept(...)`, know whether the method waits for the send future or merely enqueues the send.

### 5.2. Do not equate failed with definitely lost

A send timeout may happen after the broker already wrote the record. When only an exception is observed, the outcome may be `unknown`. A system with detailed diagnostics can classify:

| Outcome | Meaning |
|---|---|
| `acked` | Producer received broker acknowledgment for the send |
| `failed_definite` | Error conclusively shows publish failed, such as pre-send serialization error |
| `unknown` | Broker/commit outcome is unconfirmed |
| `tx_committed` | Transaction confirmed committed |

Do not guess commit state solely from a generic exception class or timeout message. Some cases require reconciliation via event ID and inspecting actual records in the DLT.

## 6. Tracking KafkaTemplate futures

If the application has a custom DLT publisher, `KafkaTemplate.send()` lets you observe outcomes at the producer send layer:

~~~java
@Component
public class StringDltPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;
    private final MeterRegistry metrics;

    public StringDltPublisher(
            KafkaTemplate<String, String> kafkaTemplate,
            MeterRegistry metrics) {
        this.kafkaTemplate = kafkaTemplate;
        this.metrics = metrics;
    }

    public void send(String eventId, String payload) {
        metrics.counter("app.kafka.dlt.send.requests").increment();

        kafkaTemplate.send("orders.created.DLT", eventId, payload)
                .whenComplete((result, exception) -> {
                    if (exception == null) {
                        metrics.counter(
                                "app.kafka.dlt.send.responses",
                                "result", "acked").increment();
                    } else {
                        metrics.counter(
                                "app.kafka.dlt.send.responses",
                                "result", "failed").increment();
                    }
                });
    }
}
~~~

This example assumes the DLT uses `StringSerializer` and a non-transactional publisher. The `whenComplete` callback tells when the send future finishes, yet **does not hold back the source offset when publishing fails**. If using code like this as a recoverer, integrate failures back into the error handler or use mechanisms ensuring offsets are not acked/committed before publishing succeeds.

Producer callbacks should stay lightweight: record metrics, emit structured logs, and return. Never make blocking database/HTTP calls in the callback.

Spring Kafka also provides `ProducerListener` for producer success/error callbacks per its API; it can be used for general stats. However, if `KafkaTemplate` sends to multiple topics, filter by DLT destination before computing DLT success/failure.

## 7. DLT inside Kafka transactions

With a listener using Kafka transactions, recovery may run in a new transaction after the main processing transaction rolls back.

~~~text
Transaction listener:
  process record -> exception -> ROLLBACK
                         |
                         v
AfterRollbackProcessor / recoverer
                         |
                         v
Recovery transaction (if supported by config)
   +---- publish DLT record
   +---- send recovered source offset
                         |
                         v
                COMMIT or ABORT
~~~

In suitable Spring Kafka setups, `DefaultAfterRollbackProcessor` can use `commitRecovered` and `KafkaTemplate` to include the recovered offset in a **new recovery transaction** alongside the DLT output.

A critical distinction:

- `KafkaTemplate.send()` succeeded: producer received broker ack for the record.
- `Recovery transaction commit` succeeded: DLT output and input offset committed together in the transaction.
- `Commit failed or aborted`: recovery must not be considered complete; redelivery/reconciliation may be needed.

If a metric increments as soon as `DeadLetterPublishingRecoverer.accept()` returns, **do not label that metric as transactional publish committed** when final commit occurs in a later step. To measure commit success, instrument transaction completion or verify with `read_committed` outputs and committed offsets in tests.

### 7.1. Producer fencing

`ProducerFencedException` can occur when a transactional producer session loses ownership of its `transactional.id` because a newer session took over a valid epoch. This is a severe producer/transaction-level error, not a transient HTTP timeout you can retry on the same session.

When fencing occurs, investigate instance ownership and transactional ID prefixes rather than mistaking DLT send-stage acks for transaction commits. The container/transaction manager must recover with a valid session.

## 8. Two failure windows involving source offsets

### 8.1. DLT write fails yet source offset commits

~~~text
Source record offset 101 fails
       |
       v
DLT publish fails
       |
       v
Error swallowed / recovery treated as success
       |
       v
Source offset 102 commits
       |
       v
Record 101 risks disappearing from processing path
~~~

This is unacceptable when the requirement is "every failed record must leave a trace in the DLT or another durable store."

Check `DefaultErrorHandler`, recoverer, ack mode, `ackAfterHandle`, `commitRecovered`, and transaction boundaries. Propagating a DLT publish exception usually allows error handling to keep the record unrecovered, though exact behavior must be tested on your version/config.

### 8.2. DLT written yet source offset uncommitted

~~~text
Source record 101 -> DLT publish succeeds
                            |
                            v
                       Process crashes
                            |
                            v
                   Source offset uncommitted
                            |
                            v
                   Record 101 redelivered
                            |
                            v
                   DLT may receive another copy
~~~

This is **at-least-once recovery**: the record is preserved, possibly with duplicates. DLT consumers/replay tooling should use event IDs or stable correlation keys to prevent duplicate business side effects.

A Kafka transaction spanning DLT output and input offset reduces this gap within Kafka. With non-transactional publishers, accept redelivery possibility and design deduplication.

### 8.3. Proper reconciliation keys

When investigating duplicates or missing records, combine multiple fields:

~~~text
business_event_id
source_topic
source_partition
source_offset
pipeline_owner
dlt_topic
~~~

`source_topic + partition + offset` identifies a record in the source topic, while `business_event_id` tracks the same event when published to another topic with a new offset. If multiple consumer groups process one main topic, include `pipeline_owner` to distinguish each service's valid recoveries.

## 9. How blocking retry and non-blocking retry differ

| Model | Path to DLT | Metrics to separate |
|---|---|---|
| `DefaultErrorHandler` blocking retry | Retries processing before recoverer routes record to DLT | Listener attempts, recoverer attempts, DLT send outcome |
| Transactional + after-rollback | Rollback, retries, then recovery to DLT | Transaction rollback, send ack, recovery transaction commit |
| `@RetryableTopic` non-blocking retry | Main -> retry topics -> DLT | Retry topic publish failures, DLT publish outcome, DLT handler status |

Never confuse two failure types:

1. **DLT publish failure**: inability to get a record into the DLT under chosen guarantees.
2. **DLT handler/consumer failure**: the record reached the DLT, yet triage, repair, or replay logic failed.

These are two distinct pipelines with separate counters and runbooks. With non-blocking retries, also watch publishing to **retry topics** before the DLT; if that stage fails, the record may never reach the DLT step.

## 10. Metadata linking DLT records and original errors

`DeadLetterPublishingRecoverer` can attach Spring Kafka headers such as:

| Header | Meaning |
|---|---|
| `KafkaHeaders.DLT_ORIGINAL_TOPIC` | Recorded source topic |
| `KafkaHeaders.DLT_ORIGINAL_PARTITION` | Source partition |
| `KafkaHeaders.DLT_ORIGINAL_OFFSET` | Source offset |
| `KafkaHeaders.DLT_EXCEPTION_FQCN` | Fully qualified exception class name |
| `KafkaHeaders.DLT_EXCEPTION_CAUSE_FQCN` | Root cause class if present |
| `KafkaHeaders.DLT_EXCEPTION_MESSAGE` | Error message |
| `KafkaHeaders.DLT_EXCEPTION_STACKTRACE` | Stack trace per framework config/behavior |

Not every record contains all headers. Numeric headers may be encoded as binary bytes; do not blindly decode all headers as UTF-8.

Kafka headers permit **multiple values per header name**. When a record traverses multiple retries or recovery hops, accumulated metadata may appear. Use `headers(name)` or `lastHeader(name)` purposefully rather than assuming a single-value map shows full history.

Ideally, every event carries a stable `eventId` from the original producer. While metrics carry only low-cardinality labels, logs/traces can include event ID and source topic-partition-offset for detailed reconciliation.

## 11. Application metrics design

A system can define:

| Suggested metric | Type | Definition |
|---|---|---|
| `app.kafka.dlt.publish.attempts` | Counter | Recoverer invoked to attempt publish |
| `app.kafka.dlt.publish.results{outcome="acked"}` | Counter | Send acknowledged by broker |
| `app.kafka.dlt.publish.results{outcome="failed"}` | Counter | Observed publish failure |
| `app.kafka.dlt.publish.results{outcome="unknown"}` | Counter | Timeout/uncertain outcome |
| `app.kafka.dlt.publish.latency` | Timer | Duration from attempt to send outcome |
| `app.kafka.dlt.recovery.tx.commits` | Counter | Successful recovery transaction commits if instrumented |
| `app.kafka.dlt.recovery.tx.failures` | Counter | Failed/aborted recovery transaction commits |
| `app.kafka.dlt.records.consumed` | Counter | DLT consumer received/processed record per definition |
| `app.kafka.dlt.records.resolved` | Counter | DLT record terminally resolved/replayed |
| `app.kafka.dlt.unresolved.age` | Gauge/Timer | Age of unresolved backlog |

These metrics are **custom conventions**. Do not claim the framework supplies these exact names out of the box.

Labels should stay limited to finite groups:

- `service` or `pipeline`;
- `source_topic` and `dlt_topic`;
- `outcome`;
- `error_category` such as `authorization`, `serialization`, `timeout`, `too_large`;
- `environment`.

Avoid event IDs, record keys, offsets, stack traces, full exception messages, or transactional IDs with dynamic suffixes as Prometheus labels. Those values have high cardinality or may contain sensitive data; they belong in structured logs and traces.

### 11.1. Choosing a failure rate

Conceptual ratio:

~~~text
observed_failure_rate =
  DLT publish attempts classified as failed
  /
  total DLT publish attempts with determined outcomes
~~~

When DLT attempts are zero or volume is tiny, percentages are unhelpful. One failure out of one attempt is very different from thousands of failures per minute.

Combine absolute failure count, failure rate, duration, backlog, and source consumer lag. Having zero DLT attempts for hours can simply mean no business errors occurred—it is **not automatically a broken exporter**.

## 12. Complementary Kafka producer and broker metrics

Kafka client/Spring Kafka/Micrometer can provide producer metrics such as:

- Record send/error/retry rates.
- Request latency, buffer pool wait, record size.
- Transaction commit/abort behavior depending on instrumentation.
- Consumer lag, poll duration, and rebalance activity.
- Broker topic records-in/bytes-in.
- `KafkaTemplate` observation/tracing if enabled.

Do not confuse **overall producer record error rate** with DLT publish error rate: a single `KafkaTemplate` might send to main topics, retry topics, and DLTs. Instrument per destination or attach clear context.

Broker metrics can prove the DLT topic receives traffic, yet cannot tell you the original exception, whether the source offset committed, or whether replay workflows succeeded.

## 13. DLT reliability dashboard

A useful dashboard offers multiple perspectives:

~~~text
DLT Reliability Dashboard
  |
  +-- Publish
  |      attempts/sec, acked/sec, failed/sec, unknown/sec
  |      send latency p50 / p95 / p99
  |
  +-- Producer / infrastructure
  |      request errors, retries, broker availability
  |      Kafka transaction commit / abort / fencing
  |
  +-- Source consumer
  |      consumer lag by partition, error rate, retries
  |
  +-- DLT inventory
         DLT records in, oldest unresolved age
         DLT consumer lag, replay success/failure
~~~

If DLT acknowledgments surge while publish failures remain zero, **the DLT path may be working fine while the business application is failing en masse**. Alert on DLT inflow volume, not just publish failures.

If DLT attempts rise, DLT failures rise, topic records-in stays flat, and source lag climbs, the recovery path may be broken. This is high priority because consumers may stall or records risk being skipped if the error handler is misconfigured.

## 14. Alerting on the right root cause

| Signal | Suggested response |
|---|---|
| Brief send failure then recovery | Log warning, watch retries |
| Continuous send failures and rising source lag | Urgent alert on DLT publish path |
| Repeated authorization/serializer failures | Actionable configuration incident |
| Recovery transaction commit failure | Investigate transactions and offset commits |
| DLT records-in spikes while publish success stays high | Investigate listener errors or input data |
| DLT unresolved age breaches SLO | Alert on triage/replay backlog |
| Unknown outcomes rising | Reconcile and deduplicate by event ID |

PromQL example when the exporter normalizes metric names as configured by the app:

~~~promql
sum by (service, pipeline) (
  rate(app_kafka_dlt_publish_results_total{outcome="failed"}[5m])
)
~~~

This is an illustrative example. Verify exported metric names and labels in your monitoring backend; do not copy expressions without confirming how Micrometer exports them.

Good alerts combine failure count, failure ratio, sustained duration, and real lag impact. Do not fire an incident for every single business-error DLT record, nor ignore a completely broken DLT publish path just because "DLT traffic is low."

## 15. Common causes of publish failures

### 15.1. DLT topic does not exist

When clusters disable auto-create and topics are provisioned via Terraform/GitOps, it is easy to forget creating the DLT. Verify suffixes, partitions, replication, and ACLs. If an error handler relies on a missing DLT, the outage only surfaces when the first poison record arrives.

### 15.2. DLT lacks partitions

A destination resolver preserves the source partition, yet main has eight partitions while DLT has only four. A source record on partition 6 cannot be published to partition 6 of the DLT. Plan partition counts or intentionally use a different resolver.

### 15.3. Serializer does not support failed data

A record that failed deserialization may need recovery as raw `byte[]`. If the DLT `KafkaTemplate` only configures a Java DTO serializer, publishing fails. Verify serializers handle both normal records and deserialization failures; consider `DelegatingByTypeSerializer` or a dedicated template.

### 15.4. Record too large

Exception stack traces and metadata headers can bloat record size across retries/recoveries. If payload + headers exceed producer/broker/topic limits, publishing is rejected. Control header history, payload size, and message limits rather than blindly raising limits.

### 15.5. Broker/authorization and Kafka transactions

Missing `WRITE` permissions, unavailable partition leaders, timeouts, or producer fencing can all block DLT publishing. When using Kafka transactions, monitor the transaction coordinator and commit outcomes—a broker ack on a send does not guarantee the transaction committed.

## 16. Runbook when DLT publish fails

When a recovery failure is detected, follow this investigation sequence:

1. Identify service, pipeline, source topic, partition, offset, DLT topic, and instance.
2. Retrieve the exception at the **DLT publish stage**, not just the business listener exception.
3. Verify the DLT topic exists, has the exact name, enough partitions, and healthy leader/replication.
4. Check producer ACLs, credentials, serializers, and schema registry if used.
5. Check value/key/header sizes; inspect raw bytes of records that failed deserialization.
6. Inspect producer send futures, timeouts, and retry metrics.
7. If transactional, check transaction commit/abort or producer fencing.
8. Verify **source committed offset**: can the record still be redelivered?
9. For timeouts, separate `unknown outcome`: the DLT may have received the record.
10. Fix the root cause before controlled retries/replays.
11. Watch DLT publish success, source lag, and DLT consumer state after recovery.
12. Reconcile duplicate/missing records using event ID and source metadata.

Never manually commit offsets just to lower lag while DLT publishing is still broken. Doing so can wipe poison records from both the source stream and the DLT.

When multiple partitions stall on a shared ACL or serializer bug, scaling more consumers will not fix the common cause. Prioritize restoring the recovery path and protecting source data.

## 17. Structured logs for a DLT publish

An illustrative structured log:

~~~text
event_type=dlt_publish_result
service=orders-worker
pipeline=order-validation
source_topic=orders.created
source_partition=2
source_offset=481
dlt_topic=orders.created.DLT
event_id=evt-7aa2
outcome=failed_or_unknown
error_category=authorization
duration_ms=123
instance_id=orders-worker-4
~~~

These fields are added by the application; not all are built-in Spring Kafka event properties. Use event ID and source offset for traceability, but **never use them as metric labels**.

Stack traces can contain internal URIs, payloads, or personal data. Enforce redaction/log sampling policies and access controls. If an error retries repeatedly, avoid logging full stack traces on every loop; instead log counts, correlation IDs, and last failure summaries.

## 18. Testing DLT publish success

Unit tests calling `recoverer.accept(...)` with a mocked producer only prove the recoverer code was invoked. To verify broker acknowledgments and DLT topic contents, use Embedded Kafka or Kafka Testcontainers.

Basic scenario:

1. Create main topic and DLT with matching partition policies.
2. Configure listener, error handler, and recoverer.
3. Send a record that forces the listener to throw an exception consistently.
4. Wait for retries to exhaust and the recoverer to publish.
5. Read from the DLT with a test consumer.
6. Verify key/value, event ID, source headers, and exception metadata.
7. Verify the source group's committed offset after recovery.
8. Verify application attempt and send-success counters match defined semantics.
9. If using Kafka transactions, read the DLT with `read_committed` so aborted outputs are not mistaken for committed outputs.

Test consumer configuration example:

~~~java
Map<String, Object> config = new HashMap<>();
config.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
config.put(ConsumerConfig.GROUP_ID_CONFIG, "dlt-observer-it");
config.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
config.put(ConsumerConfig.ISOLATION_LEVEL_CONFIG, "read_committed");
config.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class);
config.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
        ByteArrayDeserializer.class);
~~~

This snippet assumes DLT values are written as bytes. If JSON/Avro serializers are used in practice, select the matching deserializer. Test consumers need unique group IDs and topics cleaned/isolated from other tests.

## 19. Testing DLT publish failure

A strong failure suite should cover:

| Scenario | How to inject fault | Assertion |
|---|---|---|
| Missing DLT | Disable auto-create, omit topic | Recoverer reports failure, recovery not treated as success |
| Invalid partition | Main has more partitions than DLT; preserve partition number | Publish fails cleanly without writing to wrong destination |
| ACL denied | Producer lacks `WRITE` permission | Failure metric increments, source offset obeys policy |
| Serializer mismatch | Raw bytes with DTO-only serializer | Error caught, no record silently dropped |
| Oversized record | Payload/headers exceed limit | Clear error and alert fired |
| Broker outage | Controlled network cut/broker stop | Retry/failure/unknown outcome matches actual path |
| Transaction abort | Force recovery transaction rollback | `read_committed` sees no aborted record |
| Producer fenced | Replace transactional producer identity | Old session cannot commit |
| Crash after ack | Kill before source offset commit | Record redeliverable; DLT consumer deduplicates |
| Unknown outcome | Drop response at ack/commit boundary | Reconciliation avoids duplicate side effects |

Never stop testing at:

~~~java
assertThrows(Exception.class,
        () -> recoverer.accept(record, exception));
~~~

Verify **actual data in the DLT**, **input offsets**, **error metrics**, **recoverability**, and duplicate semantics. Throwing an exception does not prove the broker never stored the record; receiving a send ack does not prove the source offset committed.

### 19.1. Testing send vs. transaction commit

Distinguish milestones:

~~~text
T0: send submitted
T1: send future completed
T2: Kafka transaction commit completed
~~~

If T1 acks successfully yet T2 aborts, a `read_uncommitted` consumer can observe the record while `read_committed` does not treat it as committed data. Therefore, transaction integration tests must verify under the proper isolation level.

### 19.2. Never rely on fixed sleeps for assertions

Kafka publishing, rebalances, leader elections, and retries are asynchronous. Use latches, bounded-timeout consumer polls, or Awaitility conditions; avoid assuming every send finishes within a fixed millisecond delay on CI.

Keep test topics, consumer groups, and transactional IDs isolated, clean up producers/containers afterward, and never run destructive fault injection against shared production clusters.

## 20. DLT publish success is not business resolution

A record successfully written to the DLT still needs triage, repair, or replay.

~~~text
orders.created.DLT
       |
       v
DLT triage / handler / recovery worker
       |
       +---- analyze error
       +---- fix data or downstream dependency
       +---- controlled replay
       +---- confirm business processing succeeded
~~~

Keep separate:

- **Publication reliability**: are failed records reliably placed in the DLT?
- **DLT backlog**: how many records remain unhandled?
- **Triage latency**: how long does evaluation take?
- **Replay success**: do reprocessed records succeed?
- **Duplicate suppression**: do replays and redeliveries avoid duplicate side effects?
- **Final resolution**: was business state repaired, incident closed, and audited?

A service with `DLT publish success = 100%` and millions of unresolved records cannot be considered healthy from a business perspective.

## 21. Common mistakes

- **Counting recoverer invocation as publish success** before the future gets a broker ack.
- **Counting send ack as Kafka transaction committed** when transactions can still abort.
- **Treating every timeout as definitely unwritten** despite unknown outcomes.
- **Swallowing publish exceptions** and letting source offsets commit.
- **Monitoring only DLT records-in**, missing attempts that fail before reaching the broker.
- **Lumping all producer errors into DLT publish failures** when one template serves multiple topics.
- **Failing to check DLT partitions/ACLs/serializers** before rollout.
- **Not supporting raw bytes from deserialization errors** when publishing to DLT.
- **Not reconciling source offsets**, leaving operators unsure whether records were lost or duplicated.
- **Incrementing error counters without measuring unresolved DLT backlog**.
- **Using offsets and stack traces as metric labels**, causing cardinality bloat and data leaks.
- **Retrying permanent errors infinitely**, such as ACL denied or invalid partition.
- **Equating publish success with DLT handler success**.
- **Never testing broker outages, timeouts, post-ack crashes, and transaction rollbacks**.
- **Scaling consumers to fix a DLT ACL error** instead of fixing the root cause.
- **Lacking a DLT publisher failure runbook**, leaving recovery incidents unowned and prolonged.

## 22. Production implementation checklist

Before marking your recovery path production-ready, answer:

1. Does "DLT publish success" mean send submitted, broker acked, or transaction committed?
2. Does `DeadLetterPublishingRecoverer` detect send failures and propagate them back to the handler?
3. Are timeouts/unknown outcomes recorded separately for reconciliation?
4. Are source offsets committed only after recovery succeeds per contract?
5. Does the DLT topic exist with proper partition count, replication, and ACLs?
6. Do producer serializers handle both normal values and raw bytes from deserialization failures?
7. Can recovery transactions encounter producer fencing or commit failures?
8. Do metrics separate attempts, acked, failed, unknown, and transaction committed?
9. Do labels limit cardinality and exclude sensitive payloads?
10. Do dashboards link DLT publish failures with source lag and DLT backlog?
11. Do alerts distinguish publish-path failures from DLT spikes caused by business errors?
12. Do you have event IDs or source topic-partition-offsets for reconciliation?
13. Is the DLT consumer/replay idempotent?
14. Have missing topics, invalid partitions, ACLs, serializers, broker outages, and crashes been tested?
15. Is a person or system accountable for triaging and resolving DLT backlogs?

**DLT publish success and failure** are foundational reliability signals in Spring Kafka systems. To keep failed records safe, measure outcomes at the **exact producer acknowledgment or transaction commit boundary**, never swallow recovery failures, protect source offsets, and reconcile unknown outcomes or duplicates. Combining metrics, structured logs, broker/client telemetry, dashboards, alerts, and integration tests lets operations spot immediately when **the error-handling path itself is broken**, rather than discovering it after data is lost or consumers stall.
