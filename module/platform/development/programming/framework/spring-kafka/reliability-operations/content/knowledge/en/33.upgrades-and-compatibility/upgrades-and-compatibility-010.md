# Post-Upgrade Smoke Testing in Spring Kafka

## 1. What Is a Post-Upgrade Smoke Test?

When upgrading **Spring Kafka**, **Spring Boot**, **Kafka Java clients**, the Java runtime, or Kafka brokers, an application may still start up while part of its processing pipeline no longer behaves properly: producers write the wrong format, listeners fail to join the consumer group, deserializers cannot read old events, error handlers alter retries, the DLT fails to receive bad records, or offsets are not committed as expected.

A **post-upgrade smoke test** is a **short, repeatable check suite with clear PASS/FAIL criteria** designed to confirm that the newly deployed version still performs its most critical capabilities.

Example order-event processing system:

~~~text
Before upgrade
    Spring Boot / Spring Kafka / Kafka clients (old version)
                               |
                               v
                      Upgrade and deploy
                               |
                               v
                          New version
                               |
                   +-----------+----------+
                   |           |          |
              Producer      Consumer   Error handler
                   |           |          |
                   v           v          v
               Kafka ack   DB side effect  Retry/DLT
                   |           |          |
                   +-----------+----------+
                               |
                     Metrics and offsets
                               |
                       PASS / FAIL / UNKNOWN
                               |
                 Continue rollout / Halt
~~~

Smoke testing answers the question: **"Does the new build in the target deployment environment minimally satisfy the application's contract?"**

It **does not prove** that throughput meets long-term SLAs, every crash/recovery case is safe, or the pipeline provides end-to-end exactly-once semantics. Those require dedicated integration, recovery, load/soak, or chaos testing.

This article belongs to **Spring Kafka Reliability Operations → Upgrades and Compatibility**, using examples with **Java 17, Spring Boot 3.x, Spring Kafka 3.x, Spring JDBC, and PostgreSQL**. When upgrading to other versions, consult the compatibility matrix, migration notes, and actual APIs of your chosen version set; never infer compatibility from illustrative examples.

## 2. Distinguishing Smoke Tests from Other Test Layers

| Test Type | Question Answered | When Run |
| --- | --- | --- |
| **Unit test** | Are parsing, mapping, validation, and business rules right? | CI on every code change |
| **Integration test** | Do Kafka, Spring listeners, serializers, database, and handlers work together? | CI/staging |
| **Contract test** | Can producers and consumers read pre/post-upgrade schemas? | Before rollout on schema or library changes |
| **Post-upgrade smoke test** | Can the deployed build send, receive, process, and handle errors properly? | Right after deploy/canary |
| **Recovery test** | Is crashing after DB commit before offset commit safe? | Dedicated CI/staging |
| **Load/soak test** | Does the system sustain real load long-term without abnormal lag/GC growth? | Before major rollouts or on schedule |
| **Chaos/failover test** | Do broker outages, network partitions, and node restarts recover cleanly? | Controlled environments |

A smoke suite that is too narrow—merely calling an HTTP health endpoint—easily yields false PASS results. A smoke suite that is too broad—pushing tens of thousands of records or killing brokers—introduces risk and slows rollout decisions.

The goal is selecting **the fewest tests that still cover the technical paths most likely to break after an upgrade**.

## 3. Listing What Can Change Due to an Upgrade

A Spring Kafka application spans multiple layers:

~~~text
Business listener / processor
           |
     Spring Kafka
           |
    Spring Framework
           |
    Kafka Java client
           |
  TLS / SASL / network
           |
      Kafka broker
           |
 Schema registry if used
~~~

Prepare a **version inventory**:

| Component | What to Record |
| --- | --- |
| Spring Boot | Before/after versions, BOM managing dependencies |
| Spring Kafka | Before/after versions, listener/error handler/retry APIs |
| Kafka clients | Actual version inside the artifact, not only declared version |
| Java runtime | JVM vendor/version, TLS, and truststore |
| Kafka broker | Version, rolling upgrade plan if any |
| Schema registry | Avro/Protobuf/JSON schemas, subjects, and auth |
| Database | JDBC driver, transaction manager, connection pool |
| Observability | Actuator, Micrometer, logging/tracing |
| Deployment | Image digest, ConfigMaps, Secrets, ACLs, topics/groups |

Changes to watch closely:

- Default consumer/producer configuration values.
- Listener acknowledgment and offset commit behavior.
- Deserializers, trusted packages, type headers, and schema compatibility.
- `DefaultErrorHandler`, retry classifiers, and dead-letter publishing.
- **`@RetryableTopic`** and retry topic/DLT names.
- Kafka transactions, producer fencing, and `transactional.id`.
- Listener concurrency, rebalances, and assignments.
- Changed metrics/health indicators or tag names.
- Compatibility between the new client and Kafka brokers in the target environment.

Never force a `kafka-clients` version outside the Spring Boot–managed dependency set without evaluating compatibility first. Record **exact build artifacts/versions**, never "latest" as verification evidence.

## 4. Choosing Smoke Cases Along Real Execution Paths

Suppose the application uses **`orders.events`** as its main topic, **`orders.events.DLT`** for failed records, and PostgreSQL to store results.

| ID | Smoke Case | What Must Be Proven |
| --- | --- | --- |
| S1 | Startup/connection | Beans, TLS/SASL, broker metadata, and ACLs work |
| S2 | Producer send | `KafkaTemplate` sends a record and receives broker ack |
| S3 | Consumer/DB | New-build listener receives record and commits business side effect |
| S4 | Offset progress | Consumer group advances past record per ack/commit policy |
| S5 | Duplicate | Same `eventId` received twice produces only one business effect |
| S6 | Error handler/DLT | Failed record is retried/recovered and reaches DLT properly |
| S7 | Serialization compatibility | Old/new events are read per contract |
| S8 | Kafka transactions | If pipeline uses transactions, commit/abort works properly |
| S9 | Observability | Metrics, logs, traces, and alerts retain sufficient signal |
| S10 | Canary health | No abnormal spikes in lag, rebalances, errors, or pod restarts |

Not every application needs S8. Yet if a pipeline uses **consume-transform-produce with Kafka transactions**, skipping transaction smoke testing after an upgrade skips an essential path.

Include at least **one event going through the business processing path** and one **failure branch** whenever the app uses retry/DLT. A dummy listener that only logs can miss regressions in production transactions or serializers.

## 5. PASS, FAIL, and UNKNOWN Rules

Smoke gates must be agreed upon before rollout.

**PASS**: sufficient evidence that mandatory conditions succeeded within a reasonable window.

**FAIL**: evidence of broken functionality—for example, producer serializer error, listener not processing, wrong DB write, duplicate side effect, or DLT publish failure.

**UNKNOWN / INCONCLUSIVE**: insufficient evidence collected—for instance, lacking permissions to read consumer groups or observability tooling losing connection.

Example contract for case S3:

~~~text
Input:
  topic = smoke.orders.events
  eventId = smoke-{unique-id}
  payload = valid OrderCreated

Expected:
  producer ack success
  consumer from upgraded build actually receives event
  DB has exactly one result for eventId
  no matching DLT record
  consumer progress matches ack policy

Timeout:
  30 seconds in illustrative staging environment

Outcome:
  PASS / FAIL / UNKNOWN
~~~

**UNKNOWN must never silently become PASS.** When evidence is insufficient, the gate should hold rollout at the current stage for investigation.

The 30-second threshold is illustrative only; pick timeouts based on baselines, resources, and infrastructure requirements rather than one absolute constant across all clusters.

## 6. Isolating Smoke Tests from Production Business Data

A trustworthy smoke test must be repeatable without causing unintended side effects.

Principles:

1. Use a **dedicated smoke topic** or an authorized test namespace/canary.
2. Use a distinct **`eventId`** per test run, never customer transaction IDs.
3. Use an isolated test database/tenant/account to verify side effects.
4. Never inject poison records into production business topics without an approved procedure.
5. Never reset production consumer group offsets for testing.
6. Never delete shared DLT or deduplication tables during fixture cleanup.
7. Grant only necessary ACLs to the smoke runner.
8. Use trace/correlation IDs to separate test traffic from real traffic.
9. Preserve failure evidence before cleaning up fixtures.
10. Never run smoke tests with thousands of records as a substitute for load testing.

Example topology:

~~~text
Staging / canary namespace
       |
       +--> smoke.orders.events
       |          |
       |          v
       |       Listener configured like business listener
       |          |
       |          v
       |       smoke_processed_event (isolated DB)
       |
       +--> smoke.orders.events.DLT
                   |
                   v
                DLT observer
~~~

**Coverage note:** a smoke listener writing only a marker is a safe probe, yet does not prove the entire business pipeline. It should reuse the production Spring Kafka listener container/error handler/serializer/transaction configuration and be paired with real business integration tests. Where production logic differs completely, add suitable canary events or contract tests while still guaranteeing zero unintended impact on real data.

## 7. Pre-Upgrade Baseline

Before deploying, record:

| Group | Baseline |
| --- | --- |
| Consumer | Lag, assigned partitions, rebalance rate |
| Producer | Error rate, acks, request latency, retry rate |
| Listener | Throughput, processing time, exception rate |
| Retry/DLT | Retry attempts, DLT ingress, publish failures |
| Database | Commits/rollbacks, connection pool saturation |
| JVM | CPU, memory, GC, thread count |
| Pods | Readiness, restarts, resource throttling |
| Business | Applied events, duplicates, reconciliation mismatches |

Sample record:

~~~text
service: order-consumer
environment: staging
release-candidate: <build-digest>
old-spring-boot: <actual-version>
new-spring-boot: <actual-version>
old-spring-kafka: <actual-version>
new-spring-kafka: <actual-version>
kafka-clients: <actual-version>
broker: <actual-version>
java: <actual-runtime>

baseline-window: 30 minutes before deploy
consumer-lag: <measured-range>
retry-rate: <measured-range>
DLT-ingress: <measured-range>
p95-processing-time: <measured-value>
~~~

Compare across similar traffic windows. A smoke run sending a few messages cannot prove unchanged performance, yet baselines reveal clear regressions during canary rollouts.

## 8. Startup Smoke: Check More Than HTTP Health

An application can return **HTTP 200** while its consumer has not joined the group or broker credentials are invalid.

Confirm:

- Container runs the exact target image digest/release.
- Spring context and Kafka listener beans initialize cleanly.
- TLS/SASL authentication and Kafka ACLs succeed.
- `AdminClient` can read topic metadata.
- Topics exist with the expected partition counts.
- Listener containers are actually **running**.
- Consumer groups have active members and assigned partitions.
- Zero authorization/serializer/deserializer errors.
- No continuous rebalances or crash loops.
- Readiness reflects genuinely critical dependencies by design.

Common exceptions:

~~~text
SaslAuthenticationException
TopicAuthorizationException
GroupAuthorizationException
UnknownTopicOrPartitionException
SerializationException
InvalidTopicException
NoClassDefFoundError
NoSuchMethodError
CertificateException
~~~

On **`NoSuchMethodError`/`NoClassDefFoundError`**, inspect dependency compatibility/classpath. On TLS or ACL errors, verify truststores, secrets, and service-account permissions on topics/groups.

**`AdminClient.describeCluster` succeeding does not prove listeners process records.** That only confirms connectivity.

## 9. Producer Smoke: Send, Wait for Ack, Record Metadata

Spring Kafka 3.x provides **`KafkaTemplate.send`** returning **`CompletableFuture<SendResult<K,V>>`**. Smoke tests must await broker acknowledgment instead of calling send and assuming success.

~~~java
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.producer.RecordMetadata;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
public class SmokeProducer {

    private final KafkaTemplate<String, String> kafka;

    public SmokeProducer(KafkaTemplate<String, String> kafka) {
        this.kafka = kafka;
    }

    public RecordMetadata send(
            String topic,
            String eventId,
            String payload) throws Exception {

        return kafka.send(topic, eventId, payload)
                .get(10, TimeUnit.SECONDS)
                .getRecordMetadata();
    }
}
~~~

After sending, record evidence:

~~~text
eventId: smoke-...
topic: smoke.orders.events
partition: 1
offset: 208
producer-ack: success
~~~

**A producer ack proves only that Kafka wrote/acknowledged the record per producer settings.** It does not prove the listener actually received it or the database committed.

If production uses Avro/Protobuf/JSON serializers and a schema registry, send a message through **the same serializer/converter/schema contract**, not just a String serializer for convenience. Serialization is one of the biggest upgrade risks.

## 10. Consumer Smoke Must Observe Side Effects

An isolated test `KafkaConsumer` reading a topic proves only that **the test's own consumer** works. To verify the new deployment actually processes messages, check outputs produced by the production/canary listener:

- Business row/marker committed in the DB.
- Output event emitted by a consume-transform-produce flow.
- An application acknowledgment carrying a correlation ID.
- A durable audit record stamped with the consumer's build/version.
- Or a properly instrumented listener probe that does not alter business behavior.

Example test table setup:

~~~sql
CREATE TABLE smoke_processed_event (
    event_id VARCHAR(100) PRIMARY KEY,
    event_type VARCHAR(40) NOT NULL,
    processed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Event:

~~~java
public record SmokeOrderEvent(
        String eventId,
        String orderId,
        String action) {
}
~~~

Service:

~~~java
@Service
public class SmokeOrderService {

    private final JdbcTemplate jdbc;

    public SmokeOrderService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void apply(SmokeOrderEvent event) {
        jdbc.update("""
            INSERT INTO smoke_processed_event(
                event_id, event_type
            ) VALUES (?, ?)
            ON CONFLICT (event_id) DO NOTHING
            """,
            event.eventId(),
            event.action());
    }
}
~~~

This is PostgreSQL SQL. **`ON CONFLICT`** prevents the `eventId` marker from inserting twice on duplicates. To prove idempotency for a balance-credit or order-creation operation, assert the **actual business side effect** in the fixture too, not just this marker.

## 11. Test Listener Sharing the Same Error Mechanism

Example listener reading JSON Strings:

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class SmokeOrderListener {

    private final ObjectMapper mapper;
    private final SmokeOrderService service;

    public SmokeOrderListener(
            ObjectMapper mapper, SmokeOrderService service) {
        this.mapper = mapper;
        this.service = service;
    }

    @KafkaListener(
            topics = "smoke.orders.events",
            groupId = "smoke-order-processor-v1")
    public void consume(ConsumerRecord<String, String> record) {
        SmokeOrderEvent event;

        try {
            event = mapper.readValue(
                    record.value(), SmokeOrderEvent.class);
        } catch (JsonProcessingException ex) {
            throw new InvalidSmokePayloadException(
                    "Invalid smoke event JSON", ex);
        }

        if (event.eventId() == null
                || event.eventId().isBlank()
                || event.orderId() == null
                || event.orderId().isBlank()) {
            throw new InvalidSmokePayloadException(
                    "Missing mandatory smoke event fields");
        }

        service.apply(event);
    }
}
~~~

Exception:

~~~java
public class InvalidSmokePayloadException
        extends RuntimeException {

    public InvalidSmokePayloadException(
            String message, Throwable cause) {
        super(message, cause);
    }

    public InvalidSmokePayloadException(String message) {
        super(message);
    }
}
~~~

The sample setup requires **`ObjectMapper`, Spring JDBC, `KafkaTemplate`, the topic**, and a transaction manager. In staging, wire the same **`ConsumerFactory`, `ListenerContainerFactory`, `CommonErrorHandler`, and serializers** as production counterparts.

Do not attach a probe listener to a production business consumer group without a plan; it can steal partitions from real consumers.

## 12. Integration Smoke Test with Spring Boot Test

Once the smoke listener is in place, a test can publish an event and wait for the DB to reflect the result:

~~~java
import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.kafka.core.KafkaTemplate;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

@SpringBootTest(properties = {
        "spring.kafka.consumer.enable-auto-commit=false",
        "spring.kafka.listener.ack-mode=record"
})
class KafkaSmokeAfterUpgradeTest {

    @Autowired
    KafkaTemplate<String, String> kafkaTemplate;

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void producerAndListenerProcessSmokeEvent() throws Exception {
        String eventId = "smoke-" + UUID.randomUUID();

        String payload = """
            {"eventId":"%s","orderId":"SMOKE-001","action":"PROBE"}
            """.formatted(eventId);

        kafkaTemplate.send(
                "smoke.orders.events",
                eventId,
                payload).get(10, TimeUnit.SECONDS);

        await().atMost(Duration.ofSeconds(30))
                .untilAsserted(() -> {
                    Integer count = jdbc.queryForObject("""
                            SELECT COUNT(*)
                            FROM smoke_processed_event
                            WHERE event_id = ?
                            """,
                            Integer.class, eventId);

                    assertThat(count).isEqualTo(1);
                });
    }
}
~~~

Prerequisites:

- Test broker/topic, listener, and `DataSource` are ready.
- Table **`smoke_processed_event`** exists and is writable.
- Spring Boot Test, JUnit 5, AssertJ, Awaitility, and Kafka dependencies are present.
- Tests use unique **`eventId`**s; never `TRUNCATE` shared tables while other tests may run.
- If the consumer group has no committed offsets and uses **`auto-offset-reset=latest`**, wait for partition assignment **before sending** to avoid missing the first message.
- Test cases launch a Spring context pointed at staging infrastructure; never let tests accidentally connect to production databases.

### Distinguishing CI Tests from Post-Deploy Smoke

**`@SpringBootTest`** normally boots a fresh application context inside the test process. It proves the test process's code/config works, yet **does not prove a newly deployed pod is actually consuming**.

For a real post-deploy smoke test, an external runner should:

1. Confirm the new service is deployed and its listeners have partition assignments.
2. Publish an event to the smoke topic.
3. Query the DB/audit/output generated by **the running service itself**.
4. Verify the build/version of the instance that processed the record.
5. Never spin up a test listener in the same group that might intercept the record instead of the canary.

## 13. Wait for Real Conditions, Not Arbitrary Sleeps

Kafka and Spring listeners operate asynchronously. Example:

~~~java
kafkaTemplate.send(topic, key, payload);
Thread.sleep(1_000L);
assertThat(resultCount).isEqualTo(1);
~~~

This test can fail randomly when CI slows down, or pass before subsequent steps run.

Use **Awaitility**, a `CountDownLatch`/identifiable test probe, or bounded-timeout consumer group offset polling. Conditions must tie directly to the test record, not merely "consumer lag is 0" on a topic carrying other traffic.

An **unobservable timeout** must yield `UNKNOWN` or `FAIL` per contract; never default to `PASS` simply because no error surfaced.

## 14. Offset Smoke: Did the Consumer Group Advance Past the Record?

With record listeners and offset commit policies, verify **after processing** that the group advanced past the probe record.

Producers return **`RecordMetadata`** containing topic, partition, and offset. For Kafka committed offsets, the committed offset is normally the **next position to consume**, so it should exceed the processed record's offset.

Example using `AdminClient`:

~~~java
import java.util.Map;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.AdminClientConfig;
import org.apache.kafka.common.TopicPartition;

public boolean hasCommittedPast(
        String bootstrap,
        String groupId,
        TopicPartition partition,
        long recordOffset) throws Exception {

    try (AdminClient admin = AdminClient.create(
            Map.of(
                AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
                bootstrap))) {

        var committed = admin
                .listConsumerGroupOffsets(groupId)
                .partitionsToOffsetAndMetadata()
                .get(10, TimeUnit.SECONDS)
                .get(partition);

        return committed != null
                && committed.offset() > recordOffset;
    }
}
~~~

This is an illustrative method to place in an appropriate class. It requires consumer group read permissions and a reasonable wait for commit. **Never assume `partition=0`** when producers send keyed messages; use the topic/partition/offset from `RecordMetadata`.

Warnings:

- **Advancing offsets does not prove the business side effect succeeded.** Error handlers can recover/skip records and advance offsets.
- With manual ack, async processing, or Kafka transactions, commit semantics and timing can differ.
- On topics with concurrent traffic, an advancing offset does not guarantee the exact probe `eventId` was processed.
- Combine **business marker/`eventId` and offset progress** to prove both aspects independently.
- Never reset production group offsets in smoke tests.

## 15. Post-Upgrade Duplicate Smoke

Upgrades can affect commit timing, container concurrency, or retry behavior, exposing idempotency bugs.

A simple smoke case:

~~~text
Kafka offset 200: eventId=smoke-a
Kafka offset 201: eventId=smoke-a

Expected:
  listener receives/completes both attempts
  business marker has one record
  side effect applies only once
~~~

**Wait for the second record to actually finish processing** before asserting final data. Checking `marker count=1` right after offset 200 yields a false pass while offset 201 has not even been consumed yet.

Ways to verify:

- Consumer group committed offset surpasses the second offset.
- Test probe at listener completion.
- Business acknowledgment emitted as each attempt finishes.

Note that **`marker count=1` alone does not prove business idempotency** if code deduplicates the marker while still applying the side effect twice. Tests should assert the **business result** too—for example, a simulated balance incremented exactly once.

Producer idempotence and Kafka transactions reduce duplicates within Kafka scope, yet do not automatically protect all JDBC/HTTP/email side effects. A duplicate smoke check is a fast gate; the **DB commit before offset commit** crash gap needs deeper integration/failure tests.

## 16. Retry and Dead Letter Topic Smoke

If the app uses **`DefaultErrorHandler`** and **`DeadLetterPublishingRecoverer`**, verify post-upgrade:

- The error handler remains attached to the listener container.
- The exception classifier still distinguishes retryable vs. non-retryable errors.
- Backoff and attempt counts match contract.
- The DLT topic, partition mapping, and ACLs exist.
- The DLT producer serializer handles real failed payloads.
- DLT records carry keys/values and sufficient source metadata for investigation.
- When DLT sending fails, the original record is not falsely marked recovered.
- Post-recovery offset commits follow the ack mode.

Example configuration:

~~~java
@Configuration
public class SmokeKafkaErrorConfiguration {

    @Bean
    DefaultErrorHandler smokeErrorHandler(
            KafkaTemplate<String, String> kafkaTemplate) {

        DeadLetterPublishingRecoverer recoverer =
                new DeadLetterPublishingRecoverer(
                    kafkaTemplate,
                    (record, exception) -> new TopicPartition(
                        record.topic() + ".DLT",
                        record.partition()));

        recoverer.setFailIfSendResultIsError(true);

        DefaultErrorHandler handler =
                new DefaultErrorHandler(
                    recoverer,
                    new FixedBackOff(200L, 1L));

        handler.addNotRetryableExceptions(
                InvalidSmokePayloadException.class);

        return handler;
    }
}
~~~

Import Spring Kafka classes, **`org.apache.kafka.common.TopicPartition`**, **`FixedBackOff`**, and Spring `@Configuration`. The bean must be wired into the listener container factory properly; when an app has multiple container factories, do not assume every listener picks up this handler automatically.

With **`FixedBackOff(200L, 1L)`**, retryable errors are attempted **once initially plus one retry**. `InvalidSmokePayloadException` is classified as non-retryable.

### Safe Poison JSON Test

Publish to **`smoke.orders.events`**:

~~~text
Malformed payload:
  {"eventId":

Expected:
  smoke.orders.events.DLT receives record
  DB has no business side effect
  DLT record carries original topic/partition/offset
  correct error category
~~~

Never inject poison JSON into production business topics just for smoke testing. The DLT should have matching partition counts with the source topic if the recoverer preserves the original partition index.

If the app uses **`@RetryableTopic`**, check the retry topics and DLT of the non-blocking topology; a `DefaultErrorHandler` routing straight to a DLT does not exercise the retry-topic pipeline.

## 17. Deserialization Smoke: Errors Can Occur Before the Listener

Two distinct cases:

~~~text
A. StringDeserializer
      |
      v
   Listener + Jackson parse
      |
   Can throw exception from listener
~~~

~~~text
B. JsonDeserializer / AvroDeserializer
      |
      +--> Parse fails during KafkaConsumer.poll()
                 |
           Listener never invoked
~~~

When using a typed deserializer directly and wanting decode failures routed to a DLT, Spring Kafka typically needs **`ErrorHandlingDeserializer`** wrapping the delegate so container error handling can process the error details.

Example:

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.value.default.type: com.example.events.OrderEvent
        spring.json.trusted.packages: com.example.events
~~~

Replace **`com.example.events.OrderEvent`** with the real class. Never widen trusted packages unboundedly just to make a test pass.

A record failing to decode may be forwarded by the DLT recoverer as **raw `byte[]`**, whereas valid records are POJOs. The DLT producer serializer must handle both shapes if the pipeline can send them. After upgrading, smoke tests should include **both valid payloads and undeserializable payloads** matching the real factory.

### When Using Schema Registry

Verify:

1. The new client connects to the registry with existing auth/TLS.
2. Subject name strategies and schema IDs did not shift unexpectedly.
3. New consumers can read events written by the old producer version.
4. During rolling rollouts, old consumers can read events written by the new producer.
5. Required headers or content types are preserved.
6. DLT/replay tools can store and read records with invalid schemas.

Do not send events only from new producers to new consumers; that can PASS while a mixed-version rollout still breaks.

## 18. Transaction Smoke When Using Kafka EOS

Some systems use **Kafka transactions** in consume-transform-produce pipelines. In those cases, smoke-test the transactional path itself rather than only a plain producer.

~~~text
Input topic
     |
     v
Transactional listener
     |
     v
Transform + KafkaTemplate.send(output)
     |
     v
Kafka transaction commit
     |
     v
read_committed consumer observes output
~~~

Smoke tests should verify:

- The transactional producer initializes cleanly.
- No `ProducerFencedException` from misconfigured `transactional.id`.
- Committed outputs appear to a consumer with **`isolation.level=read_committed`**.
- Under controlled fault injection, aborted transactions hide uncommitted outputs.
- Offset/transaction semantics match listener container settings.

**Kafka exactly-once semantics do not automatically cover PostgreSQL or external APIs.** If a listener writes via JDBC while a Kafka transaction runs, understand transaction boundaries and apply idempotency or an outbox where needed.

Do not enable transactions just for smoke tests; test the exact contract the application runs.

## 19. Consumer Groups, Rebalances, and Concurrency

After an upgrade, a group may alter assignment behavior or suffer abnormal rebalances.

Check:

- Consumer group member count.
- Partitions assigned to each member.
- Zero unprocessed partitions due to wrong subscriptions.
- Listener concurrency matches partition counts and database connection pools.
- No continuous rebalances under steady traffic.
- `max.poll.interval` and slow record processing do not trigger evictions.
- Rolling deployments keep old/new consumers in the group as designed.
- Group IDs did not change unintentionally.

**Lag equal to 0 is not sufficient proof of health.** The topic may have no data, the group name may be wrong, or the error handler may be skipping records. Send a fresh event through the exact group running the upgraded build.

In a shared-group canary, records may be picked up by an **old pod**. The test would see DB output without knowing whether the new build processed it. Attach build identity/tracing to acknowledgments, or use a dedicated smoke topic/group for the canary.

## 20. Observability Gate

After upgrading, watch:

| Signal | Criterion |
| --- | --- |
| Deployed build/image | Matches new version |
| Listener lifecycle | Running, partitions assigned |
| Producer errors | No new send/serialization errors |
| Consumer errors | No abnormal increase |
| Offsets/lag | Advancing with traffic, not growing unboundedly |
| Retry attempts | Matches baseline and policy |
| DLT ingress | Only intentional smoke-failure records or known real errors |
| DLT publish errors | Zero publish errors |
| DB commits/rollbacks | Commits cleanly, no abnormal rollback spike |
| Processing latency | Within threshold vs. baseline |
| JVM GC/CPU/memory | No clear regressions |
| Pod restarts/readiness | No crash loops, no flapping |
| Rebalances | Not continuous outside the deploy window |

Metric names and tags can change across Spring Kafka/Micrometer/Actuator versions. If dashboards go blank after an upgrade, determine whether instrumentation changed or traffic is absent; **missing mandatory metrics is still a rollout issue**.

Never use `eventId`, `orderId`, or UUIDs as long-lived Prometheus tags. Those belong in structured logs/traces and access-controlled audits.

## 21. Rolling Upgrades and Cross-Version Compatibility

During a rolling deployment:

~~~text
orders.events
     |
     +--> old consumer
     |
     +--> new consumer
~~~

Verify:

- **New producer -> old consumer** can still read messages?
- **Old producer -> new consumer** can still read messages?
- Schema evolution maintains backward/forward compatibility per contract?
- Exception headers/DLT records remain readable by old replay tools?
- Did retry topic naming change after upgrading Spring Kafka?
- Are database migrations backward-compatible with old/new code running concurrently?
- Do idempotency keys and consumer scopes retain the same meaning?
- Does `transactional.id` prefixing cause producer fencing?
- Are both old/new versions visible on the same dashboards/alert rules?

Example contract fixtures:

~~~text
old writer payload -> new reader
new writer payload -> old reader
new writer payload -> new reader
~~~

If old consumers cannot read the new schema, the rollout needs a dedicated strategy: versioned topics, expand-contract, feature flags, or a proven safe deploy order. Never use a happy-path smoke test on the new build as an excuse to skip old/new compatibility.

## 22. Canary Rollouts and Expansion Criteria

Workflow:

~~~text
Inventory + migration review
             |
             v
        CI / Staging
             |
      Integration tests
             |
             v
       Staging smoke
             |
          PASS?
        /       \
      No        Yes
      |          |
     Fix       Canary deploy
                 |
              Canary smoke
                 |
          PASS + healthy metrics?
             /           \
            No           Yes
            |             |
       Halt/rollback   Gradual rollout
                           |
                    Monitor errors/lag
                           |
                        Full rollout
                           |
                     Post-rollout smoke
~~~

Gates should be written beforehand, e.g.:

| Gate | Condition |
| --- | --- |
| G1: readiness | Correct build; auth/topics/assignments succeed |
| G2: produce | Test record acked with partition/offset |
| G3: business | New-build listener produces right result |
| G4: progress | Consumer group advances past record per ack mode |
| G5: duplicate | Same `eventId` does not duplicate side effects |
| G6: failure path | Invalid input goes to DLT without business side effects |
| G7: observability | Metrics/logs/traces suffice to verify outcome |
| G8: canary | No out-of-bounds spikes in lag/rebalances/errors |

G8 is measured over an **agreed observation window**, not just one minute post-deploy. A smoke PASS should lead to **gradual expansion**, never skipping canary monitoring.

## 23. Prepare Rollback Before Running Smoke Tests

Smoke tests are only useful if a FAIL triggers controlled action.

Prepare prior to rollout:

- Image digest and configuration of the old version.
- **Backward-compatible** DB migration plan or roll-forward plan when irreversible.
- Event schema versioning and mixed-version strategy.
- Topics, retry topics, DLTs, ACLs, and consumer group ownership.
- Listener pause/drain procedure to prevent extra side effects during remediation.
- Rollout halt criteria for lag, retries, DLT, errors, and business reconciliation.
- Authorized owner to execute rollback or expand rollout.
- Steps to re-verify outputs and idempotency after recovery.

**Rolling back an image does not delete Kafka records already published.** If a new producer emitted a schema that old consumers cannot parse, reverting to the old image can worsen the outage. Likewise, committed offsets, DLT records, and committed DB side effects do not reverse automatically.

For irreversible changes, you may need to **roll forward** with a controlled fix. Document this before deploying rather than improvising mid-incident.

## 24. Diagnosing Smoke Failures

| Symptom | Possible Cause | Where to Check |
| --- | --- | --- |
| App fails to start | Version mismatch, broken classpath | Dependency tree, stack traces |
| Producer timeout | Kafka broker, ACLs, DNS/TLS, ISR | Producer logs, broker health |
| Ack OK yet DB unchanged | Wrong listener/group, deserialization failure | Assignments, consumer logs |
| Listener processes yet offset stalls | Ack mode, commit/transaction error | Committed offsets, handlers |
| Offset advances yet business DB wrong | Recover/skip, transaction rollback, bug | DLT, DB, audit logs |
| Poison record blocks consumer | Misconfigured deserializer/error handler | `ErrorHandlingDeserializer` |
| DLT has no record | Wrong topic/partition/serializer/ACL | Recoverer logs, topic metadata |
| More retries than expected | Backoff/exception classification changed | Handler config, attempt counts |
| DLT spikes after rollout | Incompatible schema, buggy deploy | Exception categories, release markers |
| Duplicate business effects | Gap in marker/unique constraint/idempotency | DB transactions, `operationId` |
| Continuous rebalances | Poll interval, group config, rollout churn | Kafka group metrics/logs |
| Smoke PASS yet production fails | Probe uses different path or old build handled it | Trace build identity, contract coverage |

Never raise concurrency or tweak ack modes recklessly just to "make the test pass." Those settings can alter ordering, retries, duplicates, and memory pressure.

## 25. Automating Smoke Tests in Deployment Pipelines

A smoke runner can accept:

~~~text
environment
deployedImageDigest
expectedSpringKafkaVersion
bootstrapServersSecretReference
smokeTopic
smokeConsumerGroup
smokeDltTopic
smokeDbNamespace
timeouts
smokeRunId
~~~

Standard steps:

~~~text
1. Confirm build/deployment identity
2. Confirm Kafka connectivity/topic metadata
3. Confirm consumer assignment
4. Send valid event with unique eventId
5. Wait for business effect from deployed listener
6. Verify offset/processing progress
7. Send duplicate event, verify one effect
8. Send invalid event to isolated smoke topic
9. Verify retry/DLT and no bad side effect
10. Read metrics, logs, rebalance and readiness
11. Emit PASS/FAIL/UNKNOWN with evidence
12. Clean only fixtures owned by smokeRunId
~~~

Illustrative report:

~~~text
smokeRunId: smoke-20261116-01
environment: staging
build: <actual-image-digest>
topic: smoke.orders.events
group: smoke-order-processor-v1

startup-auth:      PASS
producer-ack:      PASS  (partition=1, offset=208)
business-effect:   PASS  (eventId=smoke-...)
offset-progress:   PASS
duplicate:         PASS
retry-DLT:         PASS
metrics:           PASS
overall:           PASS
~~~

Every PASS must include concrete evidence: `RecordMetadata`, DB queries, committed offsets, DLT records, metric windows, or traces. On FAIL, reports should record **phase, error class, build digest, `eventId`, timestamp, and environment** per data policy.

Never convert an unobservable mandatory step to PASS. `UNKNOWN` should keep the canary from expanding.

## 26. DLT Smoke Tests Must Not Become Real Incidents

Testing the DLT requires intentionally sending bad records. This generates backlog items that may trigger alerts or retry multiple times.

Best practices:

- Use a dedicated smoke DLT with agreed retention.
- Tag `eventId`/`testRunId` to distinguish from real production failures.
- Never use real customer payloads.
- Never delete records belonging to other groups/topics.
- Never auto-replay all smoke DLT records back into source topics.
- Never let smoke tests congest production partitions.
- Rate-limit throughput and attempt counts.
- Save evidence and clean up only fixtures belonging to that specific run.
- Never set infinite max retries just to avoid failing tests.

DLT records are operational data with their own lifecycle, owner, and access permissions. If a team ignores the DLT after an upgrade, a system can look healthy over HTTP while silently accumulating poison messages.

## 27. A Complete Smoke Scenario

### Preconditions

~~~text
- Upgraded build deployed in staging/canary.
- Topic smoke.orders.events exists with expected partition count.
- DLT smoke.orders.events.DLT exists.
- Consumer group smoke-order-processor-v1 has assignments.
- PostgreSQL has table smoke_processed_event.
- KafkaTemplate and listener use production-equivalent config.
- Each test uses a unique eventId.
~~~

### Happy Path

~~~text
1. Publish valid JSON.
2. Wait for producer ack.
3. Wait for DB marker/business effect.
4. Assert one record, correct value.
5. Verify consumer progress.
6. Verify no error/DLT for eventId.
~~~

### Duplicate Path

~~~text
1. Publish same eventId/payload again.
2. Wait for second record to be processed.
3. Verify exactly one business effect.
4. Verify no unintended retry storm.
~~~

### Error Path

~~~text
1. Publish invalid JSON to isolated smoke topic.
2. Wait for expected DLT record.
3. Verify original topic/partition/offset metadata.
4. Verify no business side effect.
5. Verify recovered progress and no DLT send error.
~~~

### Post-Smoke Observation

~~~text
1. Verify build version of processing instance.
2. Observe lag/rebalance/producer errors for agreed window.
3. Compare with pre-upgrade baseline.
4. Decide PASS / FAIL / UNKNOWN.
5. Continue rollout only when gate allows it.
~~~

If a step times out, report FAIL/UNKNOWN with evidence; never use `Thread.sleep` and assume success.

## 28. Common Mistakes

### Checking Only `/health`

HTTP healthy does not prove listeners hold partition assignments or process Kafka records.

### Checking Only `KafkaTemplate.send`

Producer acks do not prove consumers executed business logic.

### Using a Test Consumer Different from the Production Listener

An ad-hoc `KafkaConsumer` reading successfully does not prove the real Spring listener/transaction/error handler works.

### Not Knowing Which Pod Processed the Record

When old and new pods share a group, the old build may handle the smoke event. Verify build identity or use a dedicated canary group/topic.

### Asserting Duplicates Too Early

After the first record, the DB already holds one marker; the second record may not have arrived yet. Wait for full attempts/progress before concluding.

### Using Fixed Sleeps

Sleeps make tests flaky. Wait on observable conditions with bounded timeouts.

### Skipping Deserialization Failures

Valid JSON passes while malformed records stall before the listener. Test both in-listener parsing and delegate deserializers matching your architecture.

### Skipping DLT and Retries

The happy path passes while poison messages block partitions or the DLT producer lacks write permissions.

### Testing Only New Producer -> New Consumer

Mixed-version rollouts can fail when old consumers read new payloads. Run bidirectional contract checks.

### Running Smoke Tests on Real Production Data

Causes unwanted side effects, fake DLT entries, and operational alerts. Use isolated test data/canary namespaces.

### Rolling Back Without Accounting for Schemas/Offsets

Old images do not automatically undo new event schemas, DB migrations, committed offsets, or applied side effects.

### Treating Smoke PASS as Proof for Production Load

A handful of smoke messages cannot measure long-term throughput, GC, backpressure, or rebalances under load. Pair with canary monitoring and performance tests.

## 29. Post-Upgrade Checklist

- [ ] Exact artifacts/versions recorded before and after upgrade.
- [ ] Compatibility/migration notes cross-checked for the actual library set.
- [ ] Baselines captured for lag, retries, DLT, errors, latency, GC, and rebalances.
- [ ] Topics/partitions/replication/ACLs/retention verified.
- [ ] TLS/SASL and schema registry still operational.
- [ ] Smoke events isolated from real business data.
- [ ] Producer receives broker acks.
- [ ] **New-build** listener processes and commits business effects.
- [ ] Consumer group progress follows contract.
- [ ] Duplicates do not apply side effects a second time.
- [ ] Retry/DLT verified with invalid input on an isolated topic.
- [ ] Deserialization error path tested when used.
- [ ] Kafka transactions smoke-tested if pipeline uses them.
- [ ] Old/new producer/consumer schema compatibility evaluated.
- [ ] Monitoring, logs, traces, and alerts reporting properly.
- [ ] Canary shows no abnormal spikes in lag/rebalances/errors.
- [ ] PASS/FAIL/UNKNOWN gate enforced with saved evidence.
- [ ] Executable rollback or roll-forward plan ready.
- [ ] Test fixtures have clear ownership and isolated cleanup.

## 30. Conclusion

A Spring Kafka **post-upgrade smoke test** does not end when the Spring context boots and a producer sends one record. Reliable smoke testing must prove the **new build** actually **reads, decodes, processes, commits results, advances offsets, and recovers from errors** according to contract.

Keep smoke suites small, automated, safe with test data, and backed by concrete evidence. When PASS, expand rollout gradually while watching the canary. When FAIL or UNKNOWN, hold the rollout, investigate across Kafka/client/listener/DB/DLT layers, and roll back only after assessing schema compatibility and already-written data.

Combining smoke gates with **contract tests, idempotency, recovery tests, and monitoring** turns upgrades from "deploy and hope" into a **verifiable, risk-controlled, and safely recoverable process**.

