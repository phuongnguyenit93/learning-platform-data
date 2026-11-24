# Configuring Dead Letter Topics (DLT) in Spring Kafka

## 1. What Is a DLT and Why Configure It on Deployment?

In **Spring Kafka Reliability Operations**, a **DLT (Dead Letter Topic)** is a Kafka topic used to hold records that a consumer could not process successfully under the application's error policy. A DLT isolates problematic records from the main processing stream, preserves evidence for investigation, and provides a starting point for fixes, replays, or compensation.

Suppose an application consumes order creation events:

~~~text
orders.events
     |
     v
OrderCreatedListener
     |
     +--> Processing succeeds --> Write DB --> Record complete
     |
     +--> Transient error --> Retry per policy
                                   |
                          Retries still fail
                                   |
                                   v
                           orders.events.DLT
                                   |
                       Investigate / fix / replay
~~~

If a consumer retries a corrupt record forever, the partition stalls and consumer lag climbs. If it catches the exception and drops the record, data is lost silently without evidence. A DLT **isolates and preserves failed records**, yet **does not automatically fix data or guarantee end-to-end exactly-once**.

This lesson aims to configure DLTs clearly enough for deployment and operations:

- Distinguish retries, recovery, and dead-letter publishing.
- Prepare Kafka topics, partitions, replication, retention, and access permissions.
- Combine **`DefaultErrorHandler`** with **`DeadLetterPublishingRecoverer`** for record listeners.
- Handle failures when DLT publishing itself fails.
- Handle JSON, validation, database timeout, and deserialization errors.
- Contrast blocking retries with **`@RetryableTopic`**.
- Monitor the DLT, investigate failures, replay safely, and prevent infinite loops.
- Test configurations using Embedded Kafka or Kafka Testcontainers.

Primary examples use **Java 17, Spring Boot 3.x, and Spring Kafka 3.x**. In projects on other versions, verify supported APIs and properties against your actual dependencies.

## 2. Concepts to Distinguish

| Concept | Meaning | Relation to DLT |
| --- | --- | --- |
| **Consumer record** | A record at a specific topic/partition/offset | The original record retried or routed to DLT |
| **Retry** | Re-attempting processing after a failure | May run multiple times before recovery |
| **Backoff** | Wait interval between retry attempts | Reduces load during transient faults |
| **Recoverer** | Component invoked when retries do not resolve the error | Can publish to the DLT |
| **DLT** | Topic storing unprocessable records | Serves auditing, triage, and replay |
| **Poison record** | A record with bad data or one that always fails the consumer | Should not be retried indefinitely |
| **Offset commit** | Persisting the consumer group's progress position | Determines whether the source record is redelivered |
| **Redrive/replay** | Feeding a DLT record back into a processing pipeline | Must guard against duplicates and enforce idempotency |
| **Consumer lag** | Consumption progress delay | Can grow while retries block a partition |

Moving a Kafka record to the DLT does not mean **business processing succeeded**. It only indicates the record traversed a configured recovery branch.

For messages affecting balances, orders, payments, or customer records, establish an end-to-end resolution process for DLT records: owner, deadline, handling outcome, and business state.

## 3. Choose an Error Strategy Before Configuring

Not every exception should be retried the same way.

| Error Group | Examples | Typically Suitable Strategy |
| --- | --- | --- |
| **Transient errors** | Database timeout, HTTP 503 service error, lock timeout | Bounded retries with backoff |
| **Invalid data errors** | Schema-invalid JSON, negative amount, missing required field | Early DLT/quarantine; do not waste retries |
| **Business errors needing intervention** | Unconfigured product code, blocked account | DLT or workflow awaiting data correction |
| **Prolonged infrastructure outage** | Database down, Kafka DLT broker unavailable | Consider stopping/pausing the consumer, alerting, and preserving records |
| **Deployment config/bug errors** | `ClassCastException`, mapping failure across entire batch | Halting/rolling back deployment may beat dumping millions of records into the DLT |
| **Payload/idempotency conflicts** | Same `eventId` with conflicting payload | Isolate, alert, and never overwrite blindly |

A DLT is not the only option. When strict ordering is mandatory, moving a failing record to the DLT and processing subsequent records may violate business contracts. In such cases, prefer **pausing the partition, halting progress, or managing workflow state** rather than treating the DLT as a "quick skip."

## 4. Recommended Architecture for a Consumer

Suppose the system has:

- Source topic: **orders.events**.
- Business consumer group: **order-processor-v1**.
- Error topic: **orders.events.DLT**.
- Order processing service writing to PostgreSQL.
- A dedicated DLT observation workflow that does not blindly replay every record on arrival.

~~~text
                       Kafka broker
                    topic orders.events
                            |
                            v
                  Spring Kafka listener
                            |
                     business service
                            |
                +-----------+------------+
                |                        |
            SUCCESS                  EXCEPTION
                |                        |
      DB transaction commit       DefaultErrorHandler
                |                        |
      Container acks / commits      +----+-------+
      according to policy           |            |
                                Retry OK    Retries exhausted
                                    |            |
                                    v            v
                                Complete    DeadLetterPublishing
                                                Recoverer
                                                    |
                                             publish and verify
                                                    |
                                                    v
                                           orders.events.DLT
                                                    |
                                            Triage / alert /
                                          fix root cause / replay
~~~

**Database commits and Kafka consumer offset commits usually do not share an atomic transaction.** A record can be redelivered if the database committed yet the offset did not commit. Therefore, consumers still need **idempotency keyed by business event ID**; a DLT alone does not solve duplicates.

## 5. Preparing the DLT Topic Before Running the Application

An easy-to-monitor naming convention is:

~~~text
Source topic: orders.events
DLT topic:    orders.events.DLT
~~~

This name is an **application convention**. Spring Kafka uses another default convention in some configurations; if you want a **.DLT** destination, configure the resolver explicitly.

Properties to decide:

| Element | Deployment Example | Reason |
| --- | --- | --- |
| **Partitions** | DLT has at least as many partitions as source if preserving partition index | Avoids publish failures from non-existent partitions |
| **Replication factor** | 3 on a cluster with at least 3 brokers | Tolerates broker faults per cluster policy |
| **Retention** | Aligned with investigation/replay SLA and data retention rules | Prevents records from expiring before handling |
| **Cleanup policy** | Usually time-based delete | DLTs normally need failure history retained |
| **ACLs** | App gets write on DLT; ops gets appropriate read | Protects sensitive data |
| **Message size** | Sized for payload plus error headers | Prevents large failed records from failing to publish |
| **Monitoring** | Alerts on DLT arrivals and error age | Prevents the DLT from becoming an invisible backlog |

For instance, if **orders.events** has three partitions and the resolver preserves the original partition, the DLT must have partitions 0, 1, and 2. **A DLT with fewer partitions than the source will fail** for records from partitions absent at the destination.

### Example: Creating the Topic via Kafka CLI

On a production cluster with enough brokers:

~~~bash
kafka-topics.sh \
  --bootstrap-server kafka-01.example.internal:9092 \
  --create \
  --topic orders.events.DLT \
  --partitions 3 \
  --replication-factor 3
~~~

This is a shell example with an illustrative bootstrap server. On a single-broker local cluster, replication factor 3 is invalid; test setups can use factor 1. Provision and update topics/ACLs via Terraform, Helm, Strimzi, Kafka admin pipelines, or equivalent infra workflows rather than unversioned manual steps.

Verify:

~~~bash
kafka-topics.sh \
  --bootstrap-server kafka-01.example.internal:9092 \
  --describe \
  --topic orders.events.DLT
~~~

For critical data, also verify **`min.insync.replicas`**, producer acknowledgments, retention storage budgets, and organizational evidence-retention/backup policies.

### Creating the Topic with Spring `KafkaAdmin`

In environments permitting application-managed topics, you can declare:

~~~java
import org.apache.kafka.clients.admin.NewTopic;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.TopicBuilder;

@Configuration
public class TopicConfiguration {

    @Bean
    NewTopic ordersDltTopic() {
        return TopicBuilder.name("orders.events.DLT")
                .partitions(3)
                .replicas(3)
                .build();
    }
}
~~~

When running tests on a single broker, override the replication factor/bean per environment. In production, many organizations **do not grant topic CREATE rights** to applications; infrastructure pre-provisions topics and Spring Kafka simply uses them.

## 6. Configuring Consumer and Producer in Spring Boot

Example where the app reads Kafka values as **String** and Jackson parses JSON **inside the listener**. This clarifies how malformed JSON travels through the listener error handler as an application-code exception.

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-01.example.internal:9092
    consumer:
      group-id: order-processor-v1
      enable-auto-commit: false
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
    producer:
      acks: all
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
      properties:
        enable.idempotence: true
    listener:
      ack-mode: record
~~~

Explanation:

- **enable-auto-commit=false:** lets the listener container manage offsets per the configured mechanism rather than auto-committing independently of app processing.
- **ack-mode: record:** for a record listener, the container commits offsets after the listener processes a record successfully or the error handler completes recovery per contract.
- **StringDeserializer:** syntactically invalid JSON payloads still reach the listener as strings, where Jackson throws an exception.
- **acks=all:** requires the producer to receive acknowledgments from in-sync replicas per broker config.
- **enable.idempotence=true:** helps the producer suppress certain Kafka-log duplicates caused by retries within producer idempotence semantics; **does not replace business idempotency**.

**auto-offset-reset=earliest** applies only when the consumer group lacks a valid offset (and in certain out-of-range cases). It is not a retry or DLT mechanism; pick `earliest` or `latest` per deployment policy.

The sample code uses the same `KafkaTemplate` to publish String keys/values to the DLT, so producer serializers must match. If the consumer receives typed JSON objects or raw bytes on deserialization failures, configure serializers differently (see Section 11).

## 7. `DeadLetterPublishingRecoverer` and `DefaultErrorHandler`

Two core components in Spring Kafka's **blocking retry** strategy:

- **`DefaultErrorHandler`:** intercepts listener exceptions, orchestrates retries, and invokes the recoverer when retries exhaust or an exception is non-retryable.
- **`DeadLetterPublishingRecoverer`:** sends failed records to a destination topic using a Kafka producer.

Spring Kafka 3.x example:

~~~java
import org.apache.kafka.common.TopicPartition;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

@Configuration
public class KafkaErrorHandlingConfiguration {

    @Bean
    DefaultErrorHandler errorHandler(
            KafkaTemplate<Object, Object> kafkaTemplate) {

        DeadLetterPublishingRecoverer recoverer =
                new DeadLetterPublishingRecoverer(
                        kafkaTemplate,
                        (record, exception) ->
                                new TopicPartition(
                                        record.topic() + ".DLT",
                                        record.partition()));

        // Do not treat a failed asynchronous send as successful recovery.
        recoverer.setFailIfSendResultIsError(true);

        // After the initial attempt, retry up to 2 more times
        // with a 1,500 ms delay.
        DefaultErrorHandler handler =
                new DefaultErrorHandler(
                        recoverer,
                        new FixedBackOff(1_500L, 2L));

        handler.addNotRetryableExceptions(
                InvalidOrderPayloadException.class);

        return handler;
    }
}
~~~

A domain exception for invalid payloads:

~~~java
public class InvalidOrderPayloadException
        extends RuntimeException {

    public InvalidOrderPayloadException(
            String message, Throwable cause) {
        super(message, cause);
    }

    public InvalidOrderPayloadException(String message) {
        super(message);
    }
}
~~~

**This configuration uses String keys/values matching the YAML example.** For apps with differently typed `KafkaTemplate` beans, create or inject a `KafkaOperations`/`KafkaTemplate` with matching serializers rather than forcing generic casts that hide errors.

### Interpreting Attempt Counts

**`FixedBackOff(1_500L, 2L)`** specifies **two retries after the initial processing attempt**. If all three attempts fail and the recoverer successfully sends to the DLT, the error handler can mark the record recovered under container semantics. If the exception is non-retryable, the handler routes directly to the recoverer per classifier.

In the example, **`InvalidOrderPayloadException`** represents data errors that waiting a few seconds cannot fix. A **database timeout** can be retried; however, during a prolonged database outage, pushing thousands of records to the DLT may be inappropriate. Define policies to stop/pause consumers, apply circuit breakers, or tune backoff for widespread outages.

### Why Set the DLT Partition Equal to the Source Partition?

The resolver uses:

~~~java
new TopicPartition(
        record.topic() + ".DLT",
        record.partition())
~~~

This preserves an easily traceable mapping between source and DLT partitions. It works only when the DLT has matching partition indices. To let Kafka choose partitions by key instead, return a negative partition per the API rather than targeting a non-existent partition—but verify the impact on ordering and partition affinity during replay.

Never assume a DLT strictly preserves source topic ordering, especially under retries, when distinct failed records arrive at different times, or with multiple active consumers.

## 8. Sample Listener and Exception Types

A listener receiving String values and parsing them:

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderEventListener {

    private final ObjectMapper mapper;
    private final OrderService orderService;

    public OrderEventListener(
            ObjectMapper mapper, OrderService orderService) {
        this.mapper = mapper;
        this.orderService = orderService;
    }

    @KafkaListener(
            topics = "orders.events",
            groupId = "order-processor-v1")
    public void onMessage(ConsumerRecord<String, String> record) {
        OrderEvent event;

        try {
            event = mapper.readValue(
                    record.value(), OrderEvent.class);
        } catch (JsonProcessingException ex) {
            throw new InvalidOrderPayloadException(
                    "Invalid order event JSON", ex);
        }

        if (event.eventId() == null
                || event.eventId().isBlank()
                || event.orderId() == null
                || event.orderId().isBlank()) {
            throw new InvalidOrderPayloadException(
                    "Missing required order event fields");
        }

        orderService.apply(event);
    }
}
~~~

Model:

~~~java
import java.math.BigDecimal;

public record OrderEvent(
        String eventId,
        String orderId,
        BigDecimal amount) {
}
~~~

**`OrderService`** is a domain component you implement. This example assumes `OrderService` persists to the database with proper transactions and idempotency; a DLT does not provide that automatically.

Illustrative behavior:

1. Valid JSON and business processing succeeds: the listener returns normally.
2. Invalid JSON syntax: throws **`InvalidOrderPayloadException`** (non-retryable), routed straight to DLT by the handler.
3. Valid JSON missing identifying fields: routed to DLT as a validation failure.
4. Database timeout from `OrderService`: `DefaultErrorHandler` retries with backoff, then invokes the recoverer if still failing.

**Never catch every `RuntimeException` and return normally** inside the listener, as the container may assume the record succeeded and commit progress without DLT/auditing.

## 9. Once DLT Publish Succeeds, What Happens to the Source Offset?

This is a critical decision regarding **record-loss risk**.

~~~text
Source offset 120:
    Listener attempt 1 -> fail
    Listener retry 1   -> fail
    Listener retry 2   -> fail
    Recoverer publish  -> DLT success
    Handler returns    -> record is considered recovered
    Container          -> proceeds per ack/commit policy
~~~

For a record listener with **`AckMode.RECORD`**, the container normally commits progress once the error handler handles the error and returns under Spring Kafka semantics. **`DefaultErrorHandler`** exposes **`ackAfterHandle`** governing whether the container commits recovered offsets; understand this setting before switching to manual ack or transactions.

If the recoverer fails to publish or throws an exception, the record **is not marked successfully recovered** and the error handler/container may retry per error policy. The example sets **`setFailIfSendResultIsError(true)`** to prevent failed producer sends from appearing successful.

Still, **a failure window exists between DLT publishing and offset commit**. The DLT send can succeed right before the process crashes prior to committing the source offset; upon restart, the record reprocesses and can produce **two copies in the DLT**. Therefore:

- DLT consumers/replay tools also require business idempotency.
- Never treat "DLT count equals 1" as an absolute guarantee for a single logical event.
- If stronger Kafka transaction guarantees are needed in a Kafka-to-Kafka pipeline, evaluate transactional listener containers, producers, and compatible error handling; never assume JDBC side effects are atomic with Kafka.
- When switching to **`MANUAL`** or **`MANUAL_IMMEDIATE`** ack mode, re-verify offset semantics; never copy `RECORD` assumptions blindly without testing.

**Never ack offsets early just to avoid duplicates.** Acking before the DLT write is durable risks dropping the source record upon failure with no recoverable error trail.

## 10. What Does a DLT Record Contain?

With **`DeadLetterPublishingRecoverer`**, records sent to the DLT usually preserve the original **key/value** matching the serializer and attach headers describing the source record and exception.

Illustrative description:

~~~text
Destination topic : orders.events.DLT
Destination part. : 1
Value            : {"eventId":"evt-9","orderId":null,"amount":125.00}

Headers (illustrative):
  original topic     : orders.events
  original partition : 1
  original offset    : 120
  exception class    : InvalidOrderPayloadException
  exception message  : Missing required order event fields
  stack trace        : depends on config/version
~~~

Spring Kafka defines DLT-related Kafka header constants in **`KafkaHeaders`**. Exact header types and contents vary across versions and recoverer configs, so verify against your live library version when building DLT consumers.

Keep in mind:

- The **new DLT offset** is not the source offset. Always record original topic/partition/offset for investigation.
- Exception headers—especially stack traces—can be very large, inflating record sizes and bandwidth.
- Exception messages must never leak passwords, tokens, raw PII, or data prohibited in Kafka.
- Duplicate header keys or extra headers can accumulate across multiple re-drives; understand how the recoverer appends/retains headers.
- DLT keys/values may fail parsing under current schemas; DLT dashboards and tools should never blindly deserialize into strict DTOs.

A DLT retains records only until retention/cleanup policies purge them. Never treat a DLT as permanent storage without proper retention, backups, and auditing.

## 11. Deserialization Errors Occurring Before the Listener Runs

A distinct problem compared to the String-payload example occurs when consumers use **`JsonDeserializer`** directly. If a record fails decoding, the exception happens **during Kafka poll/deserialization**, before **`@KafkaListener`** is ever invoked.

A `try/catch` inside the listener cannot catch it because the listener never received the event.

The standard Spring Kafka pattern is **`ErrorHandlingDeserializer`**, which wraps a delegate deserializer and attaches error metadata so container error handling can recover it.

Example config for a specific DTO:

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.value.default.type: com.example.kafka.OrderEvent
        spring.json.trusted.packages: com.example.kafka
~~~

In this snippet, **`com.example.kafka.OrderEvent`** is illustrative only; replace it with your real package/class. Never use a wildcard for trusted packages without explicit justification and safeguards.

### Serializers for Failed Records from `ErrorHandlingDeserializer`

A record rejected by **`JsonDeserializer`** can be passed to the DLT recoverer as **raw original `byte[]`**, whereas valid records failing later are **`OrderEvent`** objects. If the DLT `KafkaTemplate` uses only **`JsonSerializer`** or **`StringSerializer`** for all values, it may fail on one of the two shapes.

One approach configures the DLT producer with a type-delegating serializer:

~~~java
Map<Class<?>, Serializer<?>> serializers = Map.of(
        byte[].class, new ByteArraySerializer(),
        OrderEvent.class, new JsonSerializer<OrderEvent>());

Serializer<Object> valueSerializer =
        new DelegatingByTypeSerializer(serializers, true);
~~~

This illustrates the mechanism; full implementation requires Spring Kafka/Apache Kafka imports, `ProducerFactory`, and `KafkaTemplate` matching your key serializer and actual value types. Test both **valid events that fail business processing** and **unparseable raw bytes**. Never apply the **`StringDeserializer + StringSerializer`** setup verbatim to JSON pipelines without checking payload shapes.

### Distinguishing the Two Processing Paths

| Scenario | Failure Point | What to Verify |
| --- | --- | --- |
| `StringDeserializer`, Jackson parse inside listener | Listener | `DefaultErrorHandler` receives exception from listener |
| `JsonDeserializer` delegate fails | Pre-listener | `ErrorHandlingDeserializer` carries error info for handler recovery |
| Schema Registry / Avro decode fails | Pre-listener | `ErrorHandlingDeserializer` + DLT producer supports raw bytes |
| Valid DTO fails business validation | Listener/service | Handler classifies, retries, or routes to DLT |
| Business DB timeout | Service in listener | Retries/backoff, transaction rollback, idempotency |

## 12. Blocking Retry vs. Non-Blocking Retry Topics?

Two common deployment patterns exist.

### 12.1. Blocking Retry with `DefaultErrorHandler`

Failed records retry inside the listener container thread per error-handler policy. On a single partition, this delays subsequent records.

~~~text
orders.events partition-0
  offset 10: error -> retry -> retry -> DLT
  offset 11: waits behind
~~~

Strengths:

- Configured directly with **`DefaultErrorHandler`** and a recoverer.
- Easy to apply short retries for transient faults.
- No extra retry topics required.

Limitations:

- Retries block partition progress while executing.
- During prolonged outages, many records can stall.
- Unsuitable if retries must wait minutes or hours on the same listener thread.

### 12.2. Non-Blocking Retry with `@RetryableTopic`

Spring Kafka supports **retry topics**, forwarding failed records to retry topics for delayed processing per backoff strategy before eventually reaching the DLT.

~~~text
orders.events
    |
  failure
    v
orders.events-retry-...  (delay)
    |
  failure
    v
orders.events-retry-...  (delay)
    |
  still fails
    v
orders.events.DLT
~~~

Conceptual configuration example using an **alternative strategy** for that listener flow:

~~~java
@RetryableTopic(
        attempts = "4",
        backoff = @Backoff(delay = 1_000, multiplier = 2.0),
        dltTopicSuffix = ".DLT",
        autoCreateTopics = "false")
@KafkaListener(
        topics = "orders.events",
        groupId = "order-processor-v1")
public void onMessage(String payload) {
    orderService.handle(payload);
}
~~~

Required imports include **`org.springframework.kafka.annotation.RetryableTopic`**, **`org.springframework.retry.annotation.Backoff`**, **`KafkaListener`**, and application classes. This illustrates non-blocking retries: send counts, retry topic names, backoff structure, and DLT handling depend on exact configuration. When **`autoCreateTopics=false`**, deployment pipelines must pre-provision all **retry topics and the DLT topic** with the names, partitions, and replication expected by the framework.

Never attach a `DefaultErrorHandler` that directly publishes to **`.DLT`** on the same listener alongside **`@RetryableTopic`** without analyzing the routing path; doing so can bypass retry topics or create overlapping recovery branches.

Strengths:

- Does not stall the source-topic listener waiting on one record.
- Fits long-delay retries while minimizing partition blocking.

Limitations:

- Adds extra topics and consumer groups, increasing deployment/monitoring complexity.
- Records can be processed **out of original order**.
- Unsuitable for flows requiring strict per-entity ordering.
- Requires testing timeouts, retention, DLT handlers, topology, and idempotency.

**Selection rule:** short retries and strict ordering favor blocking retries; long retries and throughput priority favor retry topics. Never pick solely by annotation name without evaluating business requirements.

## 13. DLT Handler: Consume to Investigate, Not Reprocess Infinitely

A DLT may be consumed by:

- Read-only admin tools displaying failure details.
- Audit services persisting failure metadata.
- Data-fix and approved re-drive workflows.
- Consumers executing compensation if business contracts require it.

Never attach a listener to **`orders.events.DLT`** that immediately republishes every message back to **`orders.events`**, or poison records will loop infinitely.

Minimal audit service:

~~~java
@Component
public class OrderDltAuditListener {

    private final DltAuditService auditService;

    public OrderDltAuditListener(DltAuditService auditService) {
        this.auditService = auditService;
    }

    @KafkaListener(
            topics = "orders.events.DLT",
            groupId = "order-dlt-audit-v1")
    public void onDlt(ConsumerRecord<String, String> record) {
        auditService.recordFailure(
                record.topic(),
                record.partition(),
                record.offset(),
                record.key(),
                record.value(),
                record.headers());
    }
}
~~~

**`DltAuditService`** is an application-implemented component. It must guard sensitive data, store only needed fields, and remain idempotent if DLT records are redelivered.

When using **`@RetryableTopic`**, **`@DltHandler`** can also handle DLT records within Spring Kafka's annotation model. Pick one audit/handler path rather than wiring two independent consumers creating uncontrolled side effects.

Never mark a business event **`COMPLETED`** merely because the DLT audit consumer received it. Business status and DLT processing status are distinct concepts.

## 14. DLT Re-Drive / Replay Procedure

Once the underlying issue is fixed, records can return to the pipeline—provided replay is designed to be **idempotent**.

~~~text
orders.events.DLT
       |
       v
Triage: identify root cause
       |
       +--> Truly invalid data: quarantine / close ticket
       |
       +--> Missing configuration: fix reference data
       |
       +--> Software bug: deploy fixed version
       |
       v
Verify replay preconditions
       |
       v
Republish with original eventId + audit metadata
       |
       v
orders.events (or dedicated replay topic)
       |
       v
Idempotent consumer
       |
       v
Reconciliation + close ticket
~~~

Core principles:

1. **Preserve the original `eventId`/`operationId`** for the logical business event. Generating a new `eventId` defeats deduplication.
2. **Never use the DLT offset as business identity**, since it is just the new offset of the failure copy.
3. Attach **`replayAttempt`**, **`original topic/partition/offset`**, and correlation IDs as headers for traceability.
4. Cap replay attempts to avoid infinite source → DLT → source → DLT loops.
5. Enforce access control and approvals, especially for financial events.
6. When ordering matters, replay controlled per aggregate/business key instead of blasting the entire DLT in parallel.
7. **Verify target-system outcomes** and update ticket status; a successful Kafka producer resend does not mean business processing succeeded.
8. If code or schemas changed, decide whether to keep original payloads or run a controlled migration.

### Replay and Duplicate Deliveries

Kafka can deliver a record to the DLT more than once due to the failure window between DLT send and source offset commit. Re-drive tooling may encounter multiple copies sharing the same `eventId`.

A safe business service maintains a **unique constraint on `operationId`/`eventId`** and writes side effects plus deduplication markers in the same transaction. This permits replays without duplicating business effects.

The DLT **records failure evidence**, while idempotency **protects side-effect application**. Critical systems need both.

## 15. Access Control and Data Protection on the DLT

DLTs often hold unsanitized error payloads. Exception headers or payloads can expose:

- Customer identifiers, account numbers, addresses, or phone numbers.
- Internal filesystem paths, class names, and stack traces.
- Unredacted malformed JSON.
- Tokens or sensitive strings from careless exception messages.

Security requirements:

- Business consumers only need **`WRITE`** on the DLT if they do not read it.
- DLT audit/replay services receive scoped **`READ`** rights, separated from production consumers where appropriate.
- Restrict raw payload viewing to authorized personnel; general dashboards should show error category, counts, timestamps, and correlation IDs.
- Connect to Kafka brokers over TLS with proper authentication/ACLs.
- Align retention with data policies and investigation needs—do not retain indefinitely out of convenience.
- Limit sensitive details in exception messages/stack traces and apply redaction where needed.
- Never use a DLT topic as the sole long-term archive for business records.

If a DLT record exceeds message size limits due to oversized payloads/headers, publishing fails. Never resolve this by raising limits endlessly; trim exception headers or store details in a secure audit store linked by correlation ID.

## 16. Retention and Backlog Processing Capacity

Suppose an organization allows up to 14 days to investigate/replay DLT records. A 3-day retention window drops records before operations can act.

Conversely, overly long retention inflates storage costs and data exposure risk. Align on:

| Factor | Question |
| --- | --- |
| **Triage SLA** | How fast must errors be detected and classified? |
| **Replay window** | What is the maximum age allowed for re-drive? |
| **Source retention** | Does the source topic still hold the original record? |
| **DLT retention** | Does the DLT retain long enough to meet triage SLAs? |
| **Compliance** | Do payloads hold sensitive data with retention caps? |
| **Marker retention** | Do deduplication markers survive late replays? |
| **Backup/archive** | Must durable audit reports be exported outside Kafka? |

A common hazard: **the DLT retains records for 30 days, while the idempotency marker table retains only 7 days**. Replaying an already-applied event on day 20 finds the marker purged and causes duplicate side effects. Design both retention windows together.

## 17. Observing the DLT with Metrics and Alerts

Enabling a DLT without monitoring merely moves failures from one log to an unmonitored corner.

Signals to track:

| Metric | Purpose |
| --- | --- |
| **DLT published total** | Count of records sent to the DLT by the recoverer |
| **DLT publish failures total** | Detects inability to persist failed records |
| **DLT backlog/lag** | Records awaiting audit/triage in the corresponding group |
| **Oldest unresolved DLT age** | Detects stalled tickets exceeding SLAs |
| **Consumer retry attempts** | Surfaces recurring transient failures |
| **Source consumer lag** | Shows whether retries are blocking partitions |
| **Processing error categories** | Distinguishes validation, DB timeout, and bugs |
| **Replay success/failure** | Tracks actual remediation outcomes |
| **Partition skew** | One partition accumulating disproportionate poison records |
| **Broker/topic disk usage** | Prevents retention from exhausting storage |

Clarify where each metric is measured: publish callbacks, recoverer, DLT audit consumer, or ticket tracker. Because a record may be published to the DLT multiple times or re-driven, **DLT message counts do not always equal unique logical incidents**.

Never attach `eventId`, `orderId`, UUIDs, or stack traces as long-lived Prometheus metric labels. Keep those in access-controlled structured logs/audits; use low-cardinality tags like topic, group, error category, and outcome on metrics.

### Suggested Alerts

- DLT arrivals become non-zero during periods where zero is normal.
- Sudden spike in DLT volume right after a deployment.
- Consecutive recoverer failures publishing to the DLT.
- Source consumer lag rising alongside retry rates.
- Oldest unresolved DLT record age exceeds SLA.
- Re-driven records bouncing repeatedly back to the DLT for the same `eventId`.
- DLT topic approaching broker quotas or disk limits.

Alerts should never auto-replay the entire DLT. Uncontrolled replays cause duplicates, load spikes, or corrupt writes before underlying bugs are fixed.

## 18. Testing DLTs with Embedded Kafka

A deployment test suite should verify at least:

1. Source and DLT topics have compatible partition counts.
2. Valid records do not enter the DLT.
3. Syntactically invalid JSON arrives on the DLT while the listener applies no business writes.
4. Transient failures retry the expected number of times, then route to the DLT if still failing.
5. When DLT publishing fails, the handler never silently marks the record recovered.
6. Keys/values and source metadata (topic, partition, offset, error) remain intact for investigation.
7. Replaying the same `eventId` does not duplicate side effects.
8. DLT/audit consumers never create infinite loops.

Example using **`@EmbeddedKafka`** with one partition to trace failed-record flow. In tests, topics/`KafkaAdmin` beans must use replication factor 1 rather than production `replicas(3)`.

~~~java
import java.time.Duration;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.kafka.test.utils.KafkaTestUtils;

import static org.assertj.core.api.Assertions.assertThat;

@EmbeddedKafka(
        partitions = 1,
        topics = {"orders.events", "orders.events.DLT"},
        bootstrapServersProperty = "spring.kafka.bootstrap-servers")
@SpringBootTest(properties = {
        "spring.kafka.consumer.enable-auto-commit=false",
        "spring.kafka.consumer.auto-offset-reset=earliest",
        "spring.kafka.consumer.key-deserializer=org.apache.kafka.common.serialization.StringDeserializer",
        "spring.kafka.consumer.value-deserializer=org.apache.kafka.common.serialization.StringDeserializer",
        "spring.kafka.producer.key-serializer=org.apache.kafka.common.serialization.StringSerializer",
        "spring.kafka.producer.value-serializer=org.apache.kafka.common.serialization.StringSerializer",
        "spring.kafka.listener.ack-mode=record"
})
class OrderDltIntegrationTest {

    @Autowired
    EmbeddedKafkaBroker broker;

    @Autowired
    KafkaTemplate<Object, Object> kafkaTemplate;

    @Test
    void invalidJsonIsSentToDlt() throws Exception {
        String payload = "{\"eventId\":";

        Map<String, Object> props = KafkaTestUtils.consumerProps(
                "dlt-observer-" + UUID.randomUUID(),
                "false",
                broker);

        props.put(
                "auto.offset.reset",
                "earliest");

        try (Consumer<String, String> dltConsumer =
                     new DefaultKafkaConsumerFactory<>(
                             props,
                             new StringDeserializer(),
                             new StringDeserializer())
                             .createConsumer()) {

            broker.consumeFromAnEmbeddedTopic(
                    dltConsumer,
                    "orders.events.DLT");

            kafkaTemplate.send(
                    "orders.events",
                    "order-123",
                    payload).get(10, TimeUnit.SECONDS);

            var dltRecord = KafkaTestUtils.getSingleRecord(
                    dltConsumer,
                    "orders.events.DLT",
                    Duration.ofSeconds(30));

            assertThat(dltRecord.value()).isEqualTo(payload);
            assertThat(dltRecord.key()).isEqualTo("order-123");
            assertThat(dltRecord.topic())
                    .isEqualTo("orders.events.DLT");
        }
    }
}
~~~

This example is an **integration test skeleton**:

- The test context must initialize **`OrderEventListener`** and **`DefaultErrorHandler`** from earlier sections.
- `KafkaTemplate` needs matching String serializers.
- Production topic beans must be overridden or disabled in tests to avoid replication-factor or partition conflicts.
- If **`OrderDltAuditListener`** is active, it uses a separate consumer group; the test observer still reads the DLT via its independent group.
- Isolate brokers/topics or fixtures across tests so **`getSingleRecord`** never picks up records from another test.
- Verify the business service **was never invoked**, e.g. via mock/spy or asserting no database side effects.
- Real tests require **`spring-kafka-test`**, JUnit 5, Spring Boot Test, and the project's listener/service beans.

**Never use a fixed `Thread.sleep` and assert the DLT has a record.** Kafka processes asynchronously; await using bounded polling, Awaitility, or `KafkaTestUtils`. Tests should also prove no business side effects occurred for the failed event, not merely that data arrived on the DLT.

## 19. Testing Exhausted Retries Before Entering the DLT

The illustrative **`FixedBackOff(1_500L, 2L)`** config expects a retryable failing record to run once initially plus two retries.

A test scenario:

~~~text
Test event: eventId=evt-test-1

Attempt 1 -> OrderService throws TransientDbException
Attempt 2 -> still TransientDbException
Attempt 3 -> still TransientDbException
             |
             v
       Recoverer publishes to DLT
~~~

How to structure the test:

1. Use a unique `eventId` for the test.
2. Configure an `OrderService` test double / fault injector to throw a retryable exception consistently for that event.
3. Track a counter keyed by `eventId` to count service invocations.
4. Publish the record with `KafkaTemplate`.
5. Wait for the DLT observer to receive the record.
6. Assert the counter matches the expected attempt count per handler config.
7. Assert the DLT preserves key/value and source metadata, with zero committed business writes.
8. Clean up fixture state scoped to `eventId`; never `TRUNCATE` shared tables while other listeners run.

Do not rely on brittle timings like "must take exactly 3 seconds" in CI. Actual backoff reflects schedulers, consumer polls, and broker timing. Assert **invocation counts, DLT state, and reasonable timeouts**.

### Testing Success After One Retry

Configure fault injection to fail **only on the first attempt**, then succeed. Once the test confirms listener completion and expected offsets/side effects, the outcome is:

- Retried once.
- Zero DLT records for that event.
- Business side effect committed strictly once.

Never assert "the DLT has no record right now" before the consumer finishes processing; tests can pass falsely simply because the message hasn't been processed yet. Wait for a reliable completion signal before asserting absence over an appropriate window.

## 20. Testing DLT Publish Failures

If the DLT topic does not exist, ACLs deny `WRITE`, the broker disconnects, or the serializer rejects the value, the recoverer itself can fail.

A failure test must ensure:

- Never reports **recovered** when DLT publishing is not confirmed per policy.
- Does not wrongly commit the source offset merely because the recovery path ran.
- Emits logs/metrics/alerts for DLT publish failures.
- Can retry/recover once infrastructure heals without losing records.
- A widespread DLT outage does not trigger an unbounded retry loop exhausting resources.

Simulate this with a test **`KafkaTemplate` or `ProducerFactory`** returning send errors, or by revoking `WRITE` ACLs in an ACL-enabled Kafka container. When mocking, verify **`setFailIfSendResultIsError(true)`** and container failure paths; to prove real broker behavior, run integration tests against real Kafka.

**Never induce record loss in production to test this.** Use a test broker or controlled fault injection.

## 21. Testing Safe Replay from the DLT

Suppose event **`evt-123`** was already applied to the database, then a crash between DB commit and Kafka offset commit caused redelivery and routing through recovery.

On replay:

~~~text
First processing:
  eventId=evt-123
  inserted marker -> business update -> DB commit

DLT replay:
  eventId=evt-123
  marker already exists
  do not apply business update a second time
~~~

For a service keeping idempotency markers inside the same DB transaction as business updates, tests should assert:

- The **original `eventId`/`operationId`** is preserved.
- The replayed record is consumed and processed/recovered per policy.
- Business tables show exactly one business effect.
- Exactly one deduplication marker row exists.
- DLT/replay tracking reflects the proper outcome.

A DLT does not ensure financial correctness when the service is not idempotent. Therefore, replay tests must **assert final database state**, not just `KafkaTemplate.send` returning success.

## 22. Pre-Production DLT Deployment Checklist

- [ ] Defined **source topic**, DLT name, partition mapping, and consumer group.
- [ ] Provisioned DLT topic with matching partition count and replication factor.
- [ ] Producer serializer supports all payload types sent by the recoverer.
- [ ] Consumer sets **`enable-auto-commit=false`** and an intentional ack mode.
- [ ] Bounded retries/backoff for transient errors; invalid data errors classified separately.
- [ ] `DefaultErrorHandler` and `DeadLetterPublishingRecoverer` wired to the right listener/container.
- [ ] Recoverer fails on DLT send errors rather than swallowing failures.
- [ ] Understood post-recovery offset commits and duplicate-DLT crash windows.
- [ ] Distinguished in-listener errors from pre-listener deserialization errors.
- [ ] If using `ErrorHandlingDeserializer`, DLT producer supports raw bytes as needed.
- [ ] If using `@RetryableTopic`, retry/DLT topics are provisioned and recovery handlers do not overlap.
- [ ] Evaluated ordering implications when skipping records or using retry topics.
- [ ] Configured ACLs, TLS, retention, and sensitive payload/header safeguards on the DLT.
- [ ] Configured metrics/alerts, triage ownership, and resolution SLAs.
- [ ] Documented replay runbook preserving original `eventId`, idempotency, and attempt caps.
- [ ] Tested invalid JSON, retryable errors, DLT publish failures, replays, and duplicates.
- [ ] Verified exact business side effects, not just Kafka record presence.

## 23. Runbook for Handling a DLT Record

When an alert fires on **`orders.events.DLT`**, a safe operational workflow:

~~~text
1. Receive alert:
   DLT topic, consumer group, timestamp, error category.
                 |
                 v
2. Open authorized audit tool:
   original topic/partition/offset, eventId, exception.
                 |
                 v
3. Determine blast radius:
   Single record or whole batch? Any business DB discrepancy?
                 |
                 v
4. Classify root cause:
   Invalid data / missing reference / DB outage / app bug.
                 |
           +-----+------+
           |            |
        Fixable     Unfixable
           |            |
           v            v
  Verify re-drive   Quarantine +
   preconditions    business ticket
           |
           v
5. Replay preserving original business event ID,
   bound attempt count and send rate.
           |
           v
6. Verify business outcome, idempotency,
   Kafka/DLT status, and reconciliation.
           |
           v
7. Close ticket, retain audit history.
~~~

If a deployment bug sends nearly all messages to the DLT, consider **stopping the consumer or rolling back the release**, then fixing the root cause before resuming. A DLT preserves evidence, not infinite storage for a mass-failing bug.

## 24. Conclusion

**Configuring a DLT** in Spring Kafka does not end at creating an extra topic and registering **`DefaultErrorHandler`**. A complete design specifies which records retry, which errors route to the DLT, what serializers the producer uses, whether DLT partitions exist, how publish failures behave, when offsets commit, and who owns triage of backlogged records.

For consumers reading String JSON, **`DefaultErrorHandler` + `DeadLetterPublishingRecoverer` + pre-provisioned DLT topics** is a clear starting point. For errors occurring inside the deserializer, pair **`ErrorHandlingDeserializer`** with a raw-bytes-capable DLT serializer. When long delays are needed, **`@RetryableTopic`** offers an alternative with dedicated retry topics and ordering trade-offs.

Ultimately, a DLT **preserves failed records for recovery**, while **idempotency, auditing, monitoring, and controlled replay** determine whether the system remains genuinely reliable after failures.

