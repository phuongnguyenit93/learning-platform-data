# Configuring Retry Topics in Spring Kafka

When a consumer fails to process a Kafka message due to downstream API timeouts, transient database disconnects, or rate-limited targets, two common options exist: **retrying immediately on the consumer thread** or **forwarding the message to a retry topic for later reprocessing**. The second option avoids blocking the consumer thread for too long, but requires proper topic provisioning, consumer setup, DLT, Kafka permissions, and operational policies.

This lesson **"Configuring Retry Topics"** belongs to **Spring Kafka Reliability Operations → Deployment and Configuration**. It is more than adding `@RetryableTopic`: a production system must know **how many retries to allow, how long to delay, which exceptions are retryable, where retry and DLT topics are created, who holds publish/consume rights, how to monitor backlogs, and what to do when message forwarding fails**.

```text
Producer
   |
   v
orders.events  ----> main listener
                          |
                     processing fails
                          |
                   retryable exception?
                     /            \
                   Yes             No
                    |               |
                    v               v
 orders.events-retry-0              DLT
        |                             ^
   wait backoff                       |
        v                           |
   retry listener                   |
        |                           |
   still failing? -------- Yes --> next retry topic
        |                           |
        No                          +-- attempts exhausted --> DLT
        |
        v
  processing succeeded
```

Topic names in the diagram illustrate suffixing by **attempt index**. Actual topic names may carry delay-based suffixes or reuse a single topic across multiple retry intervals depending on policy and Spring Kafka version.

## 1. Distinguishing Blocking Retry, Retry Topics, and DLT

| Concept | How It Works | Best Suited When |
| --- | --- | --- |
| **Blocking retry** | The same consumer container retries the record with a `BackOff`, holding or pausing progress on the current partition | Brief faults, few attempts, stricter ordering required |
| **Non-blocking retry topic** | On failure, the record is **published to another topic** with eligibility timestamps; retry listeners consume after the delay | Downstreams recover in seconds/minutes and you must not block the main consumer |
| **Dead Letter Topic (DLT)** | Holds records unprocessable after exhausting the retry policy or hitting a non-retryable error | Investigation, alerting, evidence retention, and controlled reprocessing needed |
| **Application quarantine** | Dedicated business error store such as a database or object storage | Data triage workflows, review status, error codes, and auditing needed |
| **Replay/reprocess** | Deliberately rerunning from the DLT or source after fixing the fault | A distinct operational workflow requiring duplicate protection |

In Spring Kafka, `@RetryableTopic` and `RetryTopicConfiguration` support the **non-blocking retry** model. Spring Kafka typically creates/registers listeners for retry topics and the DLT, using a `KafkaTemplate` to forward records across topics.

**A retry topic is not an in-JVM queue.** Messages are written to Kafka, so they survive process restarts when brokers, replication, and retention are properly operated. In-JVM callbacks or `AtomicInteger` counters are not durable.

### 1.1. Limits You Must Know Upfront

- **Original topic ordering is not preserved.** A record sent to a retry topic can be processed after later records that stayed on the main topic.
- **Non-blocking retry topics do not support batch listeners** (`List<ConsumerRecord<...>>`); use a record listener to apply `@RetryableTopic` directly.
- **Do not combine non-blocking retries with Kafka container transactions.** If using transactional containers / EOS, evaluate another suitable retry strategy.
- Retries do not provide **exactly-once side effects** for databases, HTTP APIs, or payment systems. Consumers can reprocess events; business handlers must be idempotent.
- Messages can be forwarded multiple times; a DLT is not a deduplication mechanism and does not fix malformed payloads automatically.

In particular, when business rules require A to finish before B on the same partition, moving A to a retry topic while continuing to process B on the main topic can corrupt logic. Consider short blocking retries, coordinated partition pausing, or an out-of-order-tolerant state machine instead.

## 2. How Non-Blocking Retries Work

Suppose a listener consumes `orders.events` with `attempts=4` and exponential backoff `2s, 4s, 8s`:

```text
T0              orders.events: order-123
                attempt 1 -> RemoteTemporaryException
                      |
                      v
T0 + approx. 2s  orders.events-retry-0
                attempt 2 -> still failing
                      |
                      v
T0 + approx. 6s  orders.events-retry-1
                attempt 3 -> still failing
                      |
                      v
T0 + approx. 14s orders.events-retry-2
                attempt 4 -> still failing
                      |
                      v
                orders.events-dlt
```

Timestamps are **cumulative delay illustrations**, not exact timing SLAs. Broker I/O, consumer lag, paused partitions awaiting due records, scheduling, and downtime can extend actual wall-clock delays. Non-blocking retries use timestamps/backoff to decide when a record becomes eligible; while waiting, the retry topic consumer may **pause the partition** and continue polling to keep group membership alive.

`attempts` typically includes the **initial processing attempt**. With `attempts="4"` in the example, a record is tried by the listener up to four times under the non-blocking policy: once on the main topic and three times across retry topics, barring timeouts, exclusions, or fatal classifications that route to the DLT early.

### 2.1. Committing Offsets on the Main Topic Does Not Mean Business Success

Once a record is successfully forwarded from the main topic to a retry topic, the container can complete error handling on the main topic and advance to subsequent records. That **does not mean the business request succeeded**; it merely transitioned into a pending-retry state.

```text
orders.events offset 20
    |
    +-- publish orders.events-retry-0 succeeded
    |
    +-- main consumer continues offsets 21, 22, ...

order-123 has not completed business processing yet
```

Therefore, during reconciliation, distinguish **processed successfully**, **scheduled for retry**, **pending in DLT**, and **reprocessed after manual review**. Watching only main-topic consumer lag can mislead dashboards into reporting "zero backlog" while thousands of records sit in retry topics.

## 3. Preparing Project and Dependencies

The snippets below target **Java 17+, Spring Boot 3.x, and Spring Kafka 3.3.x** as a reference baseline. Retry topic support exists in newer versions, though default topic reuse, APIs, or packages can change across major/minor releases. Always align with the Spring Kafka version managed by your project's Spring Boot BOM.

In `build.gradle`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.kafka:spring-kafka'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
    testImplementation 'org.awaitility:awaitility'
}
```

Never force an unrelated `spring-kafka` version overriding Spring Boot's dependency management solely to use a newer annotation. Spring Retry supports backoff mechanics; depending on your version/setup it may need to be present as a dependency—consult the BOM and docs for your exact release.

### 3.1. Kafka Connection Configuration

`application.yml` for string payloads:

```yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}

    consumer:
      group-id: orders-service
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer

    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
      acks: all
      properties:
        enable.idempotence: true

    listener:
      ack-mode: record
```

`acks: all` and producer idempotence strengthen publishing within the Kafka producer boundary, yet **do not guarantee a business transaction executes only once** or join an external database in a shared transaction.

`auto-offset-reset=earliest` helps when a group has no committed offset yet; it does not force full replay on every restart once offsets exist. In production, align `earliest`/`latest` with your bootstrap and backfill policies.

`ack-mode: record` is commonly recommended for the retry topic model. If using manual acknowledgment or `asyncAcks`, review version-specific error handler settings and test actual commits/replays.

## 4. Simplest Approach: `@RetryableTopic`

Suppose the app receives order IDs as strings, calls a downstream service, and encounters two error categories:

- `RemoteTemporaryException`: timeouts, 503s, or transient dependency outages—**retryable**.
- `InvalidOrderException`: malformed business messages—**pointless to retry without fixing the payload**.

Business exceptions:

```java
package com.example.kafka;

public class RemoteTemporaryException extends RuntimeException {
    public RemoteTemporaryException(String message, Throwable cause) {
        super(message, cause);
    }
}
```

```java
package com.example.kafka;

public class InvalidOrderException extends RuntimeException {
    public InvalidOrderException(String message) {
        super(message);
    }
}
```

In `OrderService`, the app explicitly maps HTTP/validation errors into these exceptions. Avoid `catch (Exception ex) { throw new RemoteTemporaryException(...); }` globally: that turns programming bugs or bad payloads into retryable errors and triggers needless retry loops.

Illustrative listener:

```java
package com.example.kafka;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.annotation.DltHandler;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.annotation.RetryableTopic;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.retry.annotation.Backoff;
import org.springframework.stereotype.Component;

@Component
public class OrderConsumer {

    private static final Logger log =
        LoggerFactory.getLogger(OrderConsumer.class);

    private final OrderService orderService;
    private final OrderDeadLetterService deadLetterService;

    public OrderConsumer(
            OrderService orderService,
            OrderDeadLetterService deadLetterService) {
        this.orderService = orderService;
        this.deadLetterService = deadLetterService;
    }

    @RetryableTopic(
        attempts = "4",
        backoff = @Backoff(delay = 2000, multiplier = 2.0, maxDelay = 8000),
        include = {RemoteTemporaryException.class},
        exclude = {InvalidOrderException.class},
        retryTopicSuffix = "-retry",
        dltTopicSuffix = "-dlt",
        topicSuffixingStrategy =
            org.springframework.kafka.retrytopic.TopicSuffixingStrategy
                .SUFFIX_WITH_INDEX_VALUE,
        autoCreateTopics = "false",
        kafkaTemplate = "kafkaTemplate"
    )
    @KafkaListener(
        id = "ordersConsumer",
        topics = "orders.events",
        groupId = "orders-service"
    )
    public void consume(
            String orderId,
            @Header(KafkaHeaders.RECEIVED_TOPIC) String receivedTopic) {
        log.info("event=order.consume topic={} orderId={}",
            receivedTopic, orderId);

        orderService.processIdempotently(orderId);
    }

    @DltHandler
    public void onDlt(
            String orderId,
            @Header(KafkaHeaders.RECEIVED_TOPIC) String dltTopic) {
        deadLetterService.recordForReview(orderId, dltTopic);
    }
}
```

`OrderService` and `OrderDeadLetterService` are **application services you implement**. `processIdempotently` must persist outcomes keyed by business key (such as a unique constraint or processed-state check); it is not a built-in Spring Kafka API. `recordForReview` should store DLT records in an access-controlled audit/quarantine store with duplicate-write protection.

Here, `autoCreateTopics="false"` means **topics must be provisioned by the platform before the app runs**. That fits production environments restricting topic-creation rights. For local learning/demos, you can set `"true"` and configure partitions/replication for your test broker.

### 4.1. `attempts` and `@Backoff`

| Property | Example | Meaning |
| --- | --- | --- |
| `attempts` | `"4"` | Total attempts under the non-blocking policy, including the initial attempt |
| `backoff.delay` | `2000` | Initial delay in milliseconds |
| `backoff.multiplier` | `2.0` | Delay multiplier for exponential backoff |
| `backoff.maxDelay` | `8000` | Maximum delay cap |
| `include` | `RemoteTemporaryException` | Exception types eligible for retry |
| `exclude` | `InvalidOrderException` | Exception types skipped by retry and sent to terminal strategy |
| `retryTopicSuffix` | `"-retry"` | Prefix of the retry topic suffix |
| `dltTopicSuffix` | `"-dlt"` | DLT topic suffix |
| `topicSuffixingStrategy` | `SUFFIX_WITH_INDEX_VALUE` | Names retry topics by attempt index |
| `autoCreateTopics` | `"false"` | Prevents framework startup topic creation via admin |
| `kafkaTemplate` | `"kafkaTemplate"` | Bean used to publish to retry topics and DLT |

`@RetryableTopic` supports placeholders like `attempts = "${app.kafka.retry.attempts}"` to externalize policy from code to deployment config. Even so, changing values that alter **topic counts/names and listener topology** requires updating topic provisioning and planning for old backlogs during rollout.

### 4.2. Why Do You Need a Compatible `KafkaTemplate`?

The retry infrastructure needs a **producer** to forward records to retry/DLT topics. In a standard Spring Boot setup with string serializers, a default `KafkaTemplate<String, String>` is registered under `kafkaTemplate`.

When using JSON/Avro/Protobuf, ensure the retry producer's serializer supports forwarded records. Specifically with `ErrorHandlingDeserializer`, a deserialization-failed record's payload may be **raw `byte[]`**; a `KafkaTemplate` expecting only domain DTOs will fail to send it to the DLT. Configure a multi-type serializer such as `DelegatingByTypeSerializer` and test it thoroughly.

Do not expect `@RetryableTopic` to fix a misconfigured producer serializer. Forwarding can also fail due to ACLs, timeouts, broker unavailability, or messages exceeding size limits.

## 5. Determining Which Retry Topics Must Be Provisioned

With:

```java
@RetryableTopic(
    attempts = "4",
    backoff = @Backoff(delay = 2000, multiplier = 2.0, maxDelay = 8000),
    topicSuffixingStrategy =
        TopicSuffixingStrategy.SUFFIX_WITH_INDEX_VALUE,
    retryTopicSuffix = "-retry",
    dltTopicSuffix = "-dlt",
    autoCreateTopics = "false"
)
```

Under a **one-topic-per-retry-attempt** model, the expected topic list is:

```text
orders.events
orders.events-retry-0
orders.events-retry-1
orders.events-retry-2
orders.events-dlt
```

Three retry attempts follow the initial attempt, requiring three retry destinations. Switching to delay-based suffixes can embed `2000`, `4000`, `8000`; enabling **topic reuse** for equal delays changes the topic count. **Never hardcode the list above without pinning `topicSuffixingStrategy`, reuse strategy, and Spring Kafka version.**

### 5.1. Versions Affect Retry Topic Counts

Topic reuse across attempts sharing the same delay has evolved across releases. For instance, Spring Kafka **4.1** changed defaults toward **reusing a single retry topic per interval**, whereas 3.x lines had different defaults/strategies. Therefore, when upgrading:

- Inspect the actual topic graph inferred by the framework.
- Provision any new topics prior to deployment.
- Never delete old retry topics while backlogs remain.
- Keep consumers running on old-topology topics during migration windows if needed.
- Verify records emitted by the prior version still process/triage cleanly post-rollout.

Even with the same backoff policy, **changing topic reuse strategy changes topic naming and routing**—it is a deployment change, not just an annotation refactor.

## 6. Creating Retry Topics and DLT in Production

In production clusters, platform teams normally manage Kafka topics via IaC or reviewed workflows because topic creation touches **partition counts, replication factors, retention, ACLs, quotas, monitoring, and data ownership**.

Illustrative Kafka CLI script (run from a host with Kafka CLI and cluster connectivity):

```bash
KAFKA_BOOTSTRAP=broker1:9092

for topic in \
  orders.events \
  orders.events-retry-0 \
  orders.events-retry-1 \
  orders.events-retry-2 \
  orders.events-dlt
do
  kafka-topics.sh \
    --bootstrap-server "$KAFKA_BOOTSTRAP" \
    --create \
    --if-not-exists \
    --topic "$topic" \
    --partitions 3 \
    --replication-factor 3
done
```

This illustrative command assumes **at least three brokers** supporting replication factor 3 and no extra CLI auth config. On a single-broker local setup, `--replication-factor 3` fails; lower it to what the broker supports. For `SASL_SSL`/mTLS, pass `--command-config` appropriately and avoid recording passwords/tokens in shell history.

**Never lower replication factor in production just to make a topic-creation script succeed.** Match the cluster's durability capabilities and SLAs.

### 6.1. Must `partitions` Match the Main Topic?

Retry topics hold records carrying the original key and source metadata. If the recoverer preserves the original partition when forwarding, **the target partition must exist**. A practical rule is giving retry/DLT topics **at least as many partitions as the main topic**, or establishing an explicit partition-mapping strategy.

If the main topic has 12 partitions while a retry topic has only 1, forwarding from partition 7 can fail with *invalid partition*, depending on recoverer config. Never assume an auto-create default of `numPartitions="1"` fits production.

Increasing main-topic partitions after deployment may also require expanding partitions across all retry/DLT topics, updating monitoring, and reviewing ordering/idempotency. Kafka does not allow shrinking partitions easily; plan partition topology for the long term.

### 6.2. Distinct Retention for Retry and DLT

| Topic Type | Purpose | Retention Considerations |
| --- | --- | --- |
| Main | Primary message stream | Source replay SLA and storage capacity |
| Retry | Holds records waiting out backoff or downstream recovery | Must exceed max total delay **plus outage duration and drain time** |
| DLT | Holds failed records awaiting triage/reprocessing | Aligned with incident process, review SLA, and compliance retention |

Never set retry-topic retention equal to `maxDelay`. A record arriving at a retry topic may wait much longer if consumers are paused, lag builds, clusters fail over, or deploys roll back. On the DLT, overly short retention can purge failure evidence before anyone reviews it.

Avoid enabling log compaction on retry/DLT topics just to "save disk" when operations need **every failed event preserved**. Compaction can discard earlier records with the same key; use it only if data semantics and retention rules explicitly allow it.

### 6.3. Auto-Create in Dev/Test vs. Pre-Provision in Production

| Approach | Advantage | Risk |
| --- | --- | --- |
| `autoCreateTopics="true"` | Simple for demos and integration tests | App needs topic-create rights; easy to misconfigure partitions/replication/retention |
| `autoCreateTopics="false"` + IaC/CLI | Explicit config/ACL control and change review | Topics must exist before rollout |
| Spring `NewTopic` beans + `KafkaAdmin` | Managed in Java config | Still requires Create/Alter rights; avoid conflicting with IaC |

Do not confuse `@RetryableTopic.autoCreateTopics` with Kafka client `allow.auto.create.topics`: they control two separate mechanisms. When platform teams manage production topics, never rely on implicit broker auto-creation to provision retry/DLT topics.

## 7. ACL/IAM Permissions for Retry Topics

When a record fails, Spring Kafka uses a Kafka producer to **publish to the retry topic or DLT**, and spins up separate consumer containers to read them. Thus, `READ` on the main topic alone is insufficient.

| Principal | Typical Permissions Needed | Scope |
| --- | --- | --- |
| Application consumer | `READ` main topic and retry/DLT topics per policy | `orders.events`, `orders.events-retry-*`, `orders.events-dlt` |
| Consumer groups | `READ`/group management per Kafka ACLs | Main group plus generated groups for retry/DLT |
| Retry forwarding producer | `WRITE` on retry/DLT topics | Only the corresponding destinations |
| Kafka admin/provisioning | `CREATE`, `DESCRIBE`, `ALTER` when needed | Cluster/topic resources per policy |
| DLT review/reprocess service | `READ` DLT, `WRITE` approved target topics | Only error-workflow topics |

Exact actions depend on the Kafka broker/provider and cloud platform (MSK, Confluent Cloud, etc.). Some environments require `DESCRIBE`, `CREATE`, `WRITE`, `READ`, transactional ID rights, or Schema Registry permissions. Verify real cluster policies instead of copying one ACL template everywhere.

### 7.1. Symptoms of Missing ACLs

```text
Main listener receives order-123.
Handler throws RemoteTemporaryException.
Forwarder attempts to publish to orders.events-retry-0.
Broker rejects: TopicAuthorizationException.

=> Message is not guaranteed to have moved to the retry topic.
=> Error-handling container may continue failing.
=> Do not record order-123 as "safely in retry".
```

During deployment verification, do not test only happy-path publishing to the main topic. **Intentionally inject failures to exercise the forwarding path** to retry and DLT topics using a production-like application principal.

## 8. Choosing Backoff Matching the Failure Nature

Retry policies should derive from **downstream recovery characteristics** and **processing SLAs**, not picking huge numbers "just in case."

### 8.1. Fixed Backoff

```java
@RetryableTopic(
    attempts = "4",
    backoff = @Backoff(delay = 5000)
)
```

Uses a constant ~5-second delay between attempts. Fits fast-recovering targets or simple rate limits. If millions of messages fail simultaneously, fixed backoff can cause them all to return together and create repeated load spikes.

### 8.2. Exponential Backoff

```java
@RetryableTopic(
    attempts = "5",
    backoff = @Backoff(
        delay = 1000,
        multiplier = 2.0,
        maxDelay = 16000
    )
)
```

Delays grow progressively (e.g., 1, 2, 4, 8 seconds across four retry attempts). Useful when downstreams need recovery breathing room and immediate hammering worsens outages. Never grow exponents unboundedly; enforce a total duration cap and terminate at a DLT with alerting.

### 8.3. Random/Jitter Backoff

When many consumers retry together after an outage, jitter dampens **retry storms**. Spring Kafka supports varied backoff policies, including random exponential or custom backoff via config. Exact APIs depend on version; for specialized policies, consult `RetryTopicConfigurationBuilder` or extended configuration in your release docs.

Avoid aggressive retry schedules against hard rate-limited targets. With HTTP 429/`Retry-After`, account for response contracts and permitted retry windows; never assume the annotation automatically honors downstream headers.

### 8.4. Total Timeout and Attempt Limits

Beyond attempt counts, you can cap the **overall retry chain timeout**:

```java
@RetryableTopic(
    attempts = "10",
    timeout = "60000",
    backoff = @Backoff(delay = 1000, multiplier = 2.0, maxDelay = 10000)
)
```

In Spring Kafka, `timeout` bounds elapsed time since retry processing began when deciding whether to keep retrying after a failure or route to the DLT. It is not a guarantee that the record finishes within 60 seconds, nor is it a physical Kafka message TTL. Backlogs or consumer outages can push actual execution far later.

Align `attempts` and `timeout` with SLAs, downstream speed, DLT operations, and retention. For errors that can never heal without changing the payload, never stretch out retries just to delay hitting the DLT.

## 9. Exception Classification: Retryable or Not?

This is the most critical retry-topic decision. An arbitrary `RuntimeException` does not automatically warrant retrying.

| Error Category | Examples | Typical Policy |
| --- | --- | --- |
| Transient | HTTP 503, connection timeout, recoverable rate limiting | Bounded retries with backoff |
| Brief contention | Deadlock/optimistic lock conflict in specific cases | Safe to retry if handler is idempotent |
| Bad data | Invalid schema, missing required field, negative amount | Early DLT/quarantine; fix payload or upstream |
| Misconfiguration | Missing topic, bad credentials, Schema Registry error | Alert and fix deployment; retrying records rarely helps |
| Serialization/deserialization | Unreadable payload, unknown schema | Inspect serializer, error handler/DLT with raw payload |
| Programming bug | `NullPointerException`, invalid state transition | Fail/alert and fix code; avoid blind retries |
| Uncertain outcome | API timeout after server already committed | Retry **only with** idempotency or target state check |

Use application-layer exceptions in code to classify cleanly:

```java
try {
    downstreamClient.reserve(orderId);
} catch (DownstreamUnavailableException ex) {
    throw new RemoteTemporaryException(
        "Temporary downstream failure", ex);
}
```

This snippet assumes project-supplied `DownstreamUnavailableException` and `downstreamClient`. If a timed-out request could already have taken effect, `reserve` should pass a **stable idempotency key** so retries do not double-reserve inventory or charge twice.

### 9.1. Nested Exceptions and `traversingCauses`

Sometimes a retryable exception is wrapped:

```text
ListenerExecutionFailedException
    └── ApplicationException
          └── RemoteTemporaryException
```

Spring Kafka supports `traversingCauses` so the classifier inspects the cause chain per policy. When needed:

```java
@RetryableTopic(
    include = {RemoteTemporaryException.class},
    traversingCauses = "true"
)
```

Do not enable it blindly if wrapper exceptions carry distinct business meaning. Test both direct and nested exceptions to verify records do not jump to the DLT unexpectedly.

### 9.2. Default Fatal Exceptions

Spring Kafka treats certain exceptions as **fatal** for non-blocking retries—such as specific deserialization, conversion, or argument-resolution errors. Because those do not heal in a few seconds, they can bypass retry topics straight to the DLT. The exact list and customization hooks vary by version; never claim `include` overrides every fatal classification in all setups.

For specialized needs, extend `RetryTopicConfigurationSupport` to tailor fatal exceptions per your API version, and prove actual routing with integration tests.

## 10. DLT: An Investigation Queue, Not a Trash Bin

Once attempts exhaust or a non-retryable error occurs, the record moves to the **Dead Letter Topic** per policy.

```text
orders.events
    |
    +--> 503 timeout -> retry -> retry -> success
    |
    +--> invalid currency -> orders.events-dlt
    |
    +--> 503 timeout -> retries exhausted -> orders.events-dlt
```

Choose one of two explicit DLT policies:

1. **Active DLT consumer** persists records into an error-management store, fires alerts, or opens tickets.
2. **Manual-start DLT consumer** (`autoStartDltHandler="false"`); a separate review/reprocess workflow reads and acts after approval.

Example handler:

```java
@DltHandler
public void handleDlt(
        String payload,
        @Header(KafkaHeaders.RECEIVED_TOPIC) String topic) {
    quarantineStore.saveIfAbsent(
        payload,
        topic
    );
}
```

`quarantineStore.saveIfAbsent` is an application abstraction that must derive a business key/event ID and capture full source metadata. In production, also record original topic, partition, offset, key, exception class/reason code, timestamps, retry attempts, and correlation ID; never dump sensitive raw payloads into logs.

### 10.1. What If the DLT Handler Fails Too?

A DLT handler can fail if the quarantine database is unavailable. Spring Kafka provides DLT failure-handling strategies, including **retrying on the DLT** or **failing** depending on config/version. Never assume `@DltHandler` runs strictly once.

If a DLT consumer stores a record and sends an email alert, decouple durable persistence from notifications so an email outage does not re-execute the handler repeatedly. The quarantine store itself needs idempotency.

### 10.2. Disabling Automatic DLT Consumption

Spring Kafka provides `autoStartDltHandler`:

```java
@RetryableTopic(
    attempts = "4",
    autoStartDltHandler = "false"
)
@KafkaListener(topics = "orders.events")
public void process(String payload) {
    // ...
}
```

When the DLT handler does not auto-start, failed records still publish to the DLT if routing and permissions succeed, while the app leaves the DLT container stopped at startup. Pair this with monitoring/alerts and a runbook to start/review; never use this flag and forget an unread DLT.

### 10.3. Separate DLTs by Exception Type

In supporting Spring Kafka versions, different error groups can route to dedicated DLTs—for example, schema errors to `orders.events-schema-dlt` and business errors to `orders.events-business-dlt`. Exception-based DLT routing arrived in 3.2; use version-appropriate annotations/configs and pre-provision every custom DLT topic.

Avoid spawning dozens of DLT topics per Java exception class: excessive topics multiply operational overhead and fragment triage. Routing DLTs by **owning triage team** is usually far more practical than per-class topics.

## 11. Configuring with `RetryTopicConfigurationBuilder`

`@RetryableTopic` fits when each listener has a relatively simple policy. When applying policies across sets of topics or building selectable policy beans, Spring Kafka provides `RetryTopicConfiguration` and its builder.

Spring Kafka 3.x example:

```java
package com.example.kafka;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.retrytopic.RetryTopicConfiguration;
import org.springframework.kafka.retrytopic.RetryTopicConfigurationBuilder;

@Configuration
public class RetryTopicPolicyConfiguration {

    @Bean
    RetryTopicConfiguration paymentRetries(
            KafkaTemplate<String, String> kafkaTemplate) {
        return RetryTopicConfigurationBuilder
            .newInstance()
            .exponentialBackoff(1000, 2, 8000)
            .maxAttempts(4)
            .concurrency(2)
            .includeTopics(List.of("payments.events"))
            .retryOn(RemoteTemporaryException.class)
            .notRetryOn(InvalidOrderException.class)
            .create(kafkaTemplate);
    }
}
```

**Pick one configuration mechanism per listener/topic policy** so it is never ambiguous whether annotations or beans govern topology. When multiple `RetryTopicConfiguration` beans match a topic, never assume their properties merge automatically. Establish one policy owner and test the generated topic/listener names.

In production, if topics are pre-provisioned and custom naming/auto-create flags are needed, configure the corresponding builder methods for your version or use property-controlled annotations. Never copy `attempts` alone while ignoring partitions/replicas and Kafka permissions.

### 11.1. Advanced Global Configuration

Spring Kafka offers two ways to customize infrastructure globally:

- `@EnableKafkaRetryTopic` to import infrastructure beans and customize them as needed.
- Extending `RetryTopicConfigurationSupport` in a `@Configuration` class to override global configuration hooks.

**Do not mix both global approaches arbitrarily**, and never declare multiple subclasses of `RetryTopicConfigurationSupport` expecting them to merge. For most apps, `@RetryableTopic` alone suffices to bootstrap default retry topics.

Global support becomes useful when combining **short blocking retries** for certain exceptions with longer non-blocking retries for others, or customizing fatal exceptions and error handlers. Because details vary across versions, consult the exact release docs you run.

## 12. How Much Concurrency Do Retry Topics Need?

With non-blocking retries, retry/DLT consumer containers can use different concurrency from the main listener. In 3.x releases, you can set `concurrency` on retry containers.

Example:

```java
@RetryableTopic(
    attempts = "4",
    concurrency = "2"
)
@KafkaListener(
    topics = "orders.events",
    concurrency = "6"
)
public void handle(String payload) {
    // ...
}
```

Meaning: the main listener runs more consumer threads, while retry/DLT consumers use their own concurrency when supported. Actual assigned consumers still depend on **partitions, group IDs, and replica count**.

Never raise retry concurrency unboundedly: during a downstream outage, too many retry workers keep hammering the recovering target. Measure backlogs, recovery rates, rate limits, and writer idempotency.

### 12.1. Consumer Groups of Retry Topics

Spring Kafka typically derives consumer group IDs for retry topics from the main listener's group ID plus the topic suffix, avoiding unnecessary cross-rebalances between retry and main listeners. When provisioning ACLs, grant permissions **for all generated group IDs**, not only `orders-service`.

A common pitfall: the app connects and reads the main topic fine, yet retry listeners fail to join their groups because the principal lacks group permissions on generated retry groups. Check assignment logs for every retry/DLT container during smoke tests.

## 13. Ordering Loss: A Business Bug Example

Suppose a partition holds two ordered events:

```text
offset 50: order-123 CREATED
offset 51: order-123 CANCELLED
```

The listener hits a 503 processing `CREATED` and forwards it to a retry topic. Meanwhile, `CANCELLED` on the main topic succeeds before `CREATED` is retried.

```text
Main: CREATED (failed) -> forward to retry
Main: CANCELLED (succeeded)
Retry: CREATED (succeeded late)

Wrong outcome if late CREATED overwrites CANCELLED state.
```

Prevention strategies:

- Make consumers **idempotent and version-aware**: store `eventVersion` and update only on newer versions.
- Enforce state-machine transitions so a late `CREATED` is rejected when current state is already `CANCELLED`.
- For strict per-key ordering flows, use blocking retries or partition pausing instead of moving records to another topic.
- For event sourcing, apply sequence numbers and controlled hold/reorder mechanisms if business rules demand them.

Never assume identical Kafka keys preserve ordering **across separate topics**. Ordering holds only within a single topic's partition; a retry topic is a separate log.

## 14. Publishing to Retry/DLT Can Fail Too

Critical deployment truth: **the failure path itself can fail**.

```text
Main consumer receives order-123
          |
     processing fails
          |
     publish to retry
          |
      +---+---+
      |       |
  succeeds  publish fails
      |       |
      |       +-- ACL denied / broker timeout /
      v           serializer mismatch / invalid partition
  wait for retry
```

Never claim "the record is safely in the retry topic" simply because the handler threw an exception or logged `retry scheduled`. Confirm the forwarding send actually succeeded under framework error handling and broker ACKs.

Failure cases to test:

1. Forwarding producer lacks `WRITE` permission on the retry topic.
2. Retry topic is missing/deleted or lacks sufficient partitions.
3. Forwarding `KafkaTemplate` serializer rejects the payload.
4. Broker becomes temporarily unavailable during forwarding.
5. Message exceeds `max.message.bytes` or producer request size limits.
6. Schema Registry is unreachable during serialization.

In these scenarios, verify error handler and offset commit behavior for your version/config. Never manually `acknowledge()` a failing record before confirming it was forwarded to Kafka, or you create a data gap.

### 14.1. Transactions and Outboxes

Non-blocking retries **do not combine with Kafka container transactions**. If a handler updates a DB and publishes another event, DB and Kafka do not become atomic merely through `@RetryableTopic`.

For critical side effects, consider:

- Unique business keys in the database.
- A transactional outbox to publish events after DB commits.
- Consumer deduplication/inbox tables to handle redeliveries.
- Reconciling pending/retry/DLT records by business key.

If Kafka-transaction EOS is mandatory, choose a transaction-compatible retry/error-handling architecture rather than forcing `@RetryableTopic` onto a transactional batch listener.

## 15. Controlled Rollout Across Multiple Environments

Minimal operational matrix:

| Aspect | Dev/Test | Staging | Production |
| --- | --- | --- | --- |
| Main topic | May auto-create | Provisioned via IaC | Approved provisioning |
| Retry/DLT topics | Auto-created for tests | Pre-provisioned + ACLs | Pre-provisioned + ACLs/retention |
| Replication factor | Matches test broker count | Matches cluster | Matches SLA/cluster |
| Retry attempts/backoff | Short for fast tests | Production-like | Tuned to downstream SLA and retry budget |
| DLT | Queue/test probe | Dry-run triage | Review workflow, alerts, retention |
| Permissions | Test principals | Production-like service principal | Least privilege |
| Monitoring | Logs + test assertions | Consumer lag and error alerts | Lag, retry age, DLT size, SLOs |
| Idempotency | Tested via business keys | Failure injection | Constraints/outbox/reconciliation |

### 15.1. Rolling Out Changes to Retry Attempts or Delays

Suppose production runs three retries (`-retry-0`, `-retry-1`, `-retry-2`), and a new release switches to a single shared retry topic or delay-based suffixes.

If you simply deploy new code and drop old listeners:

```text
Old retry topic still holds 50,000 records
              |
              v
Deploy new version without listeners for the old topic
              |
              v
Backlog is orphaned, even while main consumer keeps running
```

Safe change procedure:

1. Inventory the exact topic graph and current lag.
2. Provision new topics with matching partitions/retention/ACLs.
3. Define a **drain or migration plan** for old retry backlogs.
4. Deploy compatibly or keep consumers on old topics until pending records drain to zero.
5. Verify DLT handlers, serializers, consumer groups, and key idempotency across both versions.
6. Monitor lag, age, and success counts; delete old topics only after confirming no needed records remain.

Never change multiple dimensions (attempts, naming, serializers, groupId) simultaneously without a transition plan, as tracing lost messages across versions becomes nearly impossible.

### 15.2. Never Share Retry Suffixes Across Independent Listeners on One Topic

If two independent `@KafkaListener`s consume the same main topic with different retry policies, give them **isolated retry/DLT topic names**. Leaving uncontrolled defaults can cause one listener's config to collide with the other or create indistinguishable consumers.

Spring Kafka 3.x supports multiple listeners on the same topic, provided suffix/topic naming and policy ownership are explicit. Include listener ID/purpose in suffixes when needed—e.g. `-billing-retry` and `-reporting-retry`—with separate DLTs if error policies differ.

## 16. Integration Testing Retry Topics with `@EmbeddedKafka`

An integration test should prove:

1. The listener fails initially with a retryable exception.
2. The record moves to a retry topic and is reprocessed.
3. Succeeding after retries **keeps it out of the DLT**.
4. Exhausting attempts delivers the message to the DLT.
5. Non-retryable exceptions route to the DLT per policy **without traversing all retry topics**.
6. When `KafkaTemplate` fails to forward a retry, the test detects failure instead of passing falsely.

The example below is a **Spring Boot 3.x/Spring Kafka 3.x fixture** for integration testing record listeners and DLTs. Isolate topics/groups between test cases and await producer ACKs for stability.

### 16.1. Test Listener with Failure Injection

```java
package com.example.kafka;

import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.kafka.annotation.DltHandler;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.annotation.RetryableTopic;
import org.springframework.retry.annotation.Backoff;

public class RetryProbeListener {

    final AtomicInteger deliveryCount = new AtomicInteger();
    final BlockingQueue<String> successes = new LinkedBlockingQueue<>();
    final BlockingQueue<String> deadLetters = new LinkedBlockingQueue<>();

    @RetryableTopic(
        attempts = "3",
        backoff = @Backoff(delay = 250),
        autoCreateTopics = "true",
        numPartitions = "1",
        replicationFactor = "1"
    )
    @KafkaListener(
        id = "retryProbeListener",
        topics = "payments.retry.test",
        groupId = "payments-retry-test-group"
    )
    public void handle(String payload) {
        int attempt = deliveryCount.incrementAndGet();

        if (payload.equals("always-fail")) {
            throw new RemoteTemporaryException(
                "Injected failure", null);
        }
        if (payload.equals("fail-once") && attempt == 1) {
            throw new RemoteTemporaryException(
                "Injected transient failure", null);
        }
        successes.add(payload);
    }

    @DltHandler
    public void onDlt(String payload) {
        deadLetters.add(payload);
    }
}
```

This fixture targets **two isolated scenarios**: "fail once" and "always fail." `AtomicInteger` counts **all callbacks**, so sending multiple test messages concurrently to one listener bean mixes attempt counts. In real suites, key counts by message ID or isolate each scenario with its own topic/group/context and controlled state resets.

### 16.2. Testing Message Delivery to the DLT

```java
@SpringBootTest(
    classes = RetryTopicIntegrationTest.TestApplication.class,
    properties = {
        "spring.kafka.consumer.auto-offset-reset=earliest",
        "spring.kafka.consumer.key-deserializer="
            + "org.apache.kafka.common.serialization.StringDeserializer",
        "spring.kafka.consumer.value-deserializer="
            + "org.apache.kafka.common.serialization.StringDeserializer",
        "spring.kafka.producer.key-serializer="
            + "org.apache.kafka.common.serialization.StringSerializer",
        "spring.kafka.producer.value-serializer="
            + "org.apache.kafka.common.serialization.StringSerializer"
    }
)
@EmbeddedKafka(
    partitions = 1,
    topics = "payments.retry.test",
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
class RetryTopicIntegrationTest {

    @Autowired KafkaTemplate<String, String> template;
    @Autowired RetryProbeListener listener;
    @Autowired KafkaListenerEndpointRegistry registry;

    @Test
    void sendsToDltAfterRetriesAreExhausted() throws Exception {
        MessageListenerContainer container =
            registry.getListenerContainer("retryProbeListener");
        assertThat(container).isNotNull();

        ContainerTestUtils.waitForAssignment(container, 1);
        template.send("payments.retry.test", "always-fail")
            .get(10, TimeUnit.SECONDS);

        assertThat(listener.deadLetters.poll(15, TimeUnit.SECONDS))
            .isEqualTo("always-fail");
        assertThat(listener.successes).isEmpty();
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableKafka
    static class TestApplication {
        @Bean
        RetryProbeListener retryProbeListener() {
            return new RetryProbeListener();
        }
    }
}
```

Common imports: JUnit Jupiter `@Test`, Spring Boot Test `@SpringBootTest`, `@SpringBootConfiguration`, `@EnableAutoConfiguration`, Spring Kafka `@EmbeddedKafka`, `KafkaTemplate`, `KafkaListenerEndpointRegistry`, `MessageListenerContainer`, `ContainerTestUtils`; Java `TimeUnit`; AssertJ `assertThat`. Imports are **omitted for brevity** to keep focus on the test flow.

`@EmbeddedKafka` creates only the main topic declared in the annotation. With `autoCreateTopics="true"`, retry/DLT infrastructure needs Kafka admin and topic-creation rights on the embedded broker; Spring Kafka provisions them per policy. Never copy `replicationFactor="1"` into a multi-broker production cluster requiring high replication.

In real suites, use `@DirtiesContext`, isolated groups/topics per test, and explicit message IDs. Sharing `deliveryCount` across tests can cause test ordering to break attempt assertions even when the retry framework works properly.

### 16.3. Testing Transient Failure Followed by Success

Additional scenario using **a fresh instance/probe**:

```java
template.send("payments.retry.test", "fail-once")
    .get(10, TimeUnit.SECONDS);

assertThat(listener.successes.poll(10, TimeUnit.SECONDS))
    .isEqualTo("fail-once");
assertThat(listener.deadLetters).isEmpty();
```

To prove a retry actually happened, assert callback counts per **message ID** or inspect `KafkaHeaders.RECEIVED_TOPIC` on the succeeding invocation. Never assert success alone: if exception injection fails to trigger, the test still passes without touching the retry topic.

### 16.4. Additional Deployment Tests Needed

| Test | Setup | Expected Outcome |
| --- | --- | --- |
| Retryable exception | Listener fails twice, succeeds on third attempt | No DLT; business output happens once |
| Non-retryable exception | `InvalidOrderException` | Early DLT per classifier |
| Exhausted attempts | Always throws transient error | DLT receives record and source metadata |
| Producer lacks `WRITE` on retry | Revoke permission in test cluster | Forward reports error; never silently commits as success |
| Retry topic has fewer partitions | Main has more partitions than retry | Routing/publish failure detected |
| Deserialization failure | Malformed value bytes with `ErrorHandlingDeserializer` | DLT forwarding serializer handles raw bytes cleanly |
| Service restart | Backlog in retry topic, restart app | Backlog finishes per Kafka offsets/retention |
| Rebalance | Scale consumers while retry topic holds backlog | Zero lost records; idempotent on replay |
| Upgrade retry naming | Backlog in old topics during rollout | Drain/migration plan executes cleanly |
| DLT handler fails | Quarantine store unavailable | DLT failure policy triggers with alert |
| Multiple messages, same key | Earlier record enters retry, later runs on main | Verify business logic handles out-of-order execution |

## 17. Observability: Do Not Watch Only Main Consumer Lag

A useful dashboard answers: how many records succeeded, how many await retry, how many sit in the DLT, and how long has the **oldest pending record** waited?

| Signal | Meaning |
| --- | --- |
| Main consumer lag | Progress on the source topic; excludes work sitting in retries |
| Retry topic lag per destination | Records pending across retry stages |
| Retry age/backoff delay | Elapsed time since first failure |
| Failure count by exception category | Is a downstream down or is input data invalid? |
| DLT arrival rate | Records exceeding retry policy or hitting non-retryable errors |
| DLT unreviewed count | Backlog awaiting operations/data triage |
| Forward failures | Failures sending records to retry/DLT topics |
| Consumer rebalance rate | Detects unstable consumer groups |
| Retry recovery rate | Share of failing messages that recover on later attempts |
| Duplicate/idempotency conflicts | Redeliveries causing repeat attempts or duplicate inputs |

While messages wait in retry topics, **main consumer lag can read 0**. Never use main lag alone to declare "all orders for the day finished processing." Business reporting should reconcile input business keys against **success state + pending retries + DLT/quarantine** under a clear contract.

### 17.1. Structured Logging

Example:

```text
event=kafka.retry.scheduled
messageId=order-123-v4
originalTopic=orders.events
originalPartition=2
originalOffset=17621
retryTopic=orders.events-retry-1
exceptionCategory=DOWNSTREAM_TIMEOUT
retryAttempt=2
correlationId=order-123-v4
```

These fields are instrumentation suggestions, **not guaranteed out-of-the-box from one annotation**. Spring Kafka forwards several headers carrying origin, exception, and retry metadata; check exact header names for your version. Never log payloads containing PII, access tokens, presigned URLs, or payment details.

For Prometheus/Micrometer metrics, use only low-cardinality labels like `topicGroup`, `exceptionCategory`, and `result`. Never put `orderId`, `messageId`, or per-message `originalOffset` into metric labels. Detailed identifiers belong in access-controlled log/audit stores.

### 17.2. Alerts and SLOs

Consider alerting on:

- Retry lag growing steadily even after the downstream recovered.
- Sudden spikes in DLT arrival rate by reason code.
- Records stuck in retry past SLA; oldest pending age nearing retention.
- Forwarding producer hitting `TopicAuthorizationException`/serialization errors.
- DLT handler down or no consumer/workflow reviewing the DLT.
- A new deployment failing to consume old retry topics.

During prolonged downstream outages, **coordinated pausing of the main listener** can prevent unbounded retry queues, though pausing grows main lag. Base that trade-off on storage/retention/capacity and ingestion requirements.

## 18. Common Configuration Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| No retry topics appear | `@RetryableTopic` not bootstrapped, policy mismatch, auto-create off | Check annotations/config beans, topic provisioning, and logs |
| Startup fails with missing topic | `autoCreateTopics=false`, missing retry/DLT topics, or admin policy | Pre-provision all topics before deploy |
| Retry producer hits `TopicAuthorizationException` | Missing `WRITE` on retry/DLT | Grant scoped ACLs to the forwarding principal |
| Retry consumer fails to join | Missing group/topic `READ` or wrong group ID | Check generated groups and ACLs |
| `SerializationException` on forward | `KafkaTemplate` serializer rejects payload/raw bytes | Use a compatible serializer and test deserialization paths |
| Message jumps straight to DLT from main | Non-retryable/fatal exception or timeout | Check classifier and cause chain |
| Message retries too many times | `attempts`, stacked blocking+non-blocking retries, or changing policy | Distinguish total attempts and retry layers |
| Backoff not exact to the millisecond | Backlog, poll scheduling, paused partitions, or clock drift | Measure real timestamps; do not expect hard real-time timers |
| Main lag is zero yet business incomplete | Records sit in retry/DLT | Monitor full topology and business state |
| Retry topic backlog stops draining post-deploy | Topic naming changed, old listener removed | Drain/migrate old topics |
| DLT holds records nobody handles | DLT handler not started or workflow missing | Assign owner, alerts, and review/reprocess workflow |
| Duplicate writes after retries | DB/API side effect happened before offset commit | Idempotency keys, unique constraints, outbox |
| Messages processed out of order | Non-blocking retry moved record to another topic | Use version-aware consumers or choose another mechanism |
| `@RetryableTopic` placed on batch listener | Unsupported on batch listeners | Switch to record listener or different error handling |
| Non-blocking retry on transactional container | Incompatible configuration | Choose a transaction-compatible retry architecture |
| Retry/DLT has fewer partitions than main | Partition-preserving forward exceeds target partitions | Align topic partition counts or define custom routing |
| Multiple listeners on one main topic share retry naming | Overlapping policies/topics | Isolate suffixes and establish clear ownership |

### 18.1. Do Not "Fix" Everything by Retrying Every Exception

A configuration like:

```java
@RetryableTopic(attempts = "100")
```

does not inherently improve reliability. If a schema-invalid payload can never heal, 100 attempts just waste load, inflate topic counts or lag, and delay triage. Even for genuine transient 503s/timeouts, high attempt counts must fit within retry budgets, retention, rate limits, and SLAs.

A sound configuration has **error classification, bounded attempts, a clear terminal destination, and a DLT owner**.

## 19. Safe Deployment Procedure

Execute a retry-topic rollout in order:

1. **Lock down the business contract:** message keys/idempotency, event versions, ordering rules, and error policy.
2. **Pin the Spring Kafka version:** confirm APIs, naming, default topic reuse, and batch/transaction limits.
3. **Size the retry budget:** attempts, backoff, timeout, and DLT behavior aligned with downstream SLAs.
4. **Map the topic graph:** main, retry, and DLT names, partitions/replicas, and consumer groups.
5. **Provision infrastructure:** topics, ACL/IAM, serializers/Schema Registry, retention, quotas, and monitoring.
6. **Deploy listeners:** `@RetryableTopic` or builder config, DLT handler, and idempotent business service.
7. **Run failure-injection smoke tests:** transient fail-then-recover, non-retryable, exhausted attempts, and forward failure.
8. **Check backlogs and rollback plan:** keep reading old topics or run a controlled drain when naming changes.
9. **Observe post-deploy:** retry lag, DLT arrivals, downstream load, duplicate conflicts, and oldest pending age.
10. **Rehearse reprocessing:** re-inject an approved DLT record into processing without duplicating side effects.

Never roll back code by deleting all retry/DLT topics: they may hold unprocessed records. Topic cleanup must be a deliberate data-management action with reconciliation.

## 20. Environment-Specific Configuration Pattern

One way to manage retry parameters in `application.yml`:

```yaml
app:
  kafka:
    retry:
      attempts: ${KAFKA_RETRY_ATTEMPTS:4}
      initial-delay-ms: ${KAFKA_RETRY_INITIAL_DELAY_MS:2000}
      max-delay-ms: ${KAFKA_RETRY_MAX_DELAY_MS:8000}
      auto-create-topics: ${KAFKA_RETRY_AUTO_CREATE_TOPICS:false}
```

Consuming those properties in the annotation:

```java
@RetryableTopic(
    attempts = "${app.kafka.retry.attempts}",
    backoff = @Backoff(
        delayExpression = "${app.kafka.retry.initial-delay-ms}",
        multiplier = 2.0,
        maxDelayExpression = "${app.kafka.retry.max-delay-ms}"
    ),
    autoCreateTopics = "${app.kafka.retry.auto-create-topics}"
)
@KafkaListener(topics = "orders.events")
public void consume(String orderId) {
    // ...
}
```

`@Backoff.delayExpression`/`maxDelayExpression` are Spring Retry annotation attributes; verify placeholder resolution on your active version. If deployment configs keep `attempts` equal while changing backoff/delay, topic names can shift when using delay-based suffixes. **Never externalize properties without keeping IaC topology in sync.**

In production, allow retry budget changes only through reviewed rollouts. Never let an environment variable silently alter the number of retry topics unknown to the Kafka platform team.

## 21. Pre-Go-Live Checklist

| Question | Pass Criteria |
| --- | --- |
| Is the listener a record listener? | Non-blocking retry is not used on batch listeners |
| Does the container use Kafka transactions? | No unsupported combination is configured |
| Is ordering loss acceptable when records retry? | Business tolerates it or enforces version/state checks |
| Does `attempts` include the first try? | Policy clearly tracks attempts vs. retry stages |
| Do backoff/timeout match SLAs? | Bounded retry budget and measurements exist |
| Are exceptions classified? | Retryable, non-retryable, and fatal paths are tested |
| Are retry/DLT topic names/versions locked? | Topic graph is finalized and fully provisioned |
| Do partitions/replicas fit the cluster? | No missing destination partitions; matches SLA |
| Is retention enough for outages/backlogs? | Headroom covers downtime plus triage |
| Does the principal hold rights on retry/DLT too? | Smoke-tested with a production-like identity |
| Does `KafkaTemplate` serialize forwards cleanly? | Tested on normal payloads and raw bytes where needed |
| Does the DLT have an owner and workflow? | Clear alerts, review, reprocessing, and retention |
| Is the business handler idempotent? | Retries/replays create no duplicate side effects |
| Can you see where pending messages live? | Dashboard covers main + retries + DLT |
| Is there a migration plan for naming changes? | Old retry backlogs are not orphaned |
| Were forward and broker failures tested? | Never marks success before durable forwarding |

## Conclusion

**Configuring retry topics** in Spring Kafka is a decision about **topology, latency, and operational ownership**, not just adding `@RetryableTopic`. Non-blocking retries protect the main consumer from stalling on failing records, in exchange for **losing cross-topic ordering**, adding topics/consumer groups, and requiring strict forwarding controls.

A reliable deployment ensures: **topics and ACLs are provisioned properly, backoff is bounded, exceptions are classified, DLTs have active owners, messages are never orphaned across rollouts, and side effects are idempotent**. Finally, validate with real-fault integration tests—covering retry recovery, exhausted attempts, and failed retry/DLT forwarding—and monitor main, retry, and DLT topics together in production.

## References

- [Spring Kafka Reference — Non-Blocking Retries](https://docs.spring.io/spring-kafka/reference/retrytopic.html): overview, limits with batch listeners and container transactions.
- [Spring Kafka Reference — How the Pattern Works](https://docs.spring.io/spring-kafka/reference/retrytopic/how-the-pattern-works.html): forwarding, timestamps/backoff, retry partitions, and DLT.
- [Spring Kafka Reference — Configuration](https://docs.spring.io/spring-kafka/reference/retrytopic/retry-config.html): `@RetryableTopic`, `RetryTopicConfigurationBuilder`, and global config.
- [Spring Kafka Reference — Features](https://docs.spring.io/spring-kafka/reference/retrytopic/features.html): backoff, classifiers, timeouts, and exception routing.
- [Spring Kafka Reference — Topic Naming](https://docs.spring.io/spring-kafka/reference/retrytopic/topic-naming.html): suffixes, topic reuse, and version differences.
- [Spring Kafka Reference — DLT Strategies](https://docs.spring.io/spring-kafka/reference/retrytopic/dlt-strategies.html): DLT handlers, failure strategies, and auto-start.
- [Spring Kafka Reference — Combining Blocking and Non-Blocking Retries](https://docs.spring.io/spring-kafka/reference/retrytopic/retry-topic-combine-blocking.html): combining both retry types.
- [Spring Kafka Reference — Testing Applications](https://docs.spring.io/spring-kafka/reference/testing.html): `@EmbeddedKafka`, `ContainerTestUtils`, and integration tests.
- [Apache Kafka Documentation](https://kafka.apache.org/documentation/): topics, partitions, retention, ACLs, consumer groups, and delivery semantics.
