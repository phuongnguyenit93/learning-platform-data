# Retry Topic Infrastructure Changes in Spring Kafka: Safe Upgrades and Compatibility

When upgrading Spring Kafka or modifying `@RetryableTopic` configuration, an application may still start normally while **retry topics, consumer groups, backoff, DLT routing, or serializers** have silently changed. The dangerous scenario is unprocessed data sitting in old retry topics while the new release subscribes only to the new retry topic. Dashboards may report zero lag for the new consumer even though critical records remain stranded on the broker.

**Retry topic infrastructure** encompasses the entire system enabling Spring Kafka *non-blocking retries*: `@RetryableTopic` or `RetryTopicConfiguration` settings, bootstrap mechanism, destination resolvers, topic naming, retry/DLT topics, retry listener containers, consumer groups, `KafkaTemplate`/producer serializers, backoff timestamps/headers, exception classifiers, and DLT handlers. **Changing the infrastructure** is therefore a change in *data topology and operational contracts*, not merely refactoring an annotation.

Within **Spring Kafka Reliability Operations → Upgrades and Compatibility**, this guide covers identifying changes across Spring Kafka 2.9, 3.x, and 4.1; inventorying current topology; configuring explicitly; upgrading without stranding retry backlogs; controlling ordering, idempotency, partitions, and serialization; and deploying, testing, monitoring, and rolling back with evidence.

Examples use Java 17+, Spring Boot 3.x, and Spring Kafka 3.x/4.x as context. APIs and default values can vary between releases; when applying them, pin your project's exact release and check release notes/documentation for that version.

## 1. Non-Blocking Retries: Where Does Data Flow?

When the main listener throws a retryable exception, Spring Kafka can **publish the record to a retry topic** along with next-attempt timing metadata. The retry-topic consumer checks the due timestamp, pauses the partition if waiting is still needed, and resumes to reprocess. Once attempts are exhausted or a non-retryable error occurs, the event can be forwarded to a Dead Letter Topic (DLT).

~~~mermaid
flowchart TD
    A["orders.events / main listener"] --> B{"Processing succeeded?"}
    B -->|Yes| C["Complete business effect"]
    B -->|Retryable error| D["Forward to retry topic"]
    D --> E["Retry listener\npause until due timestamp"]
    E --> F["Reprocess"]
    F -->|Succeeded| C
    F -->|Attempts remaining| D
    F -->|Attempts exhausted or fatal| G["orders.events-dlt"]
    G --> H["DLT handler / quarantine / replay"]
~~~

Difference from **blocking retry**: instead of blocking the source processing thread inside the same container, non-blocking retry sends the record to **another topic** for deferred processing. Because additional broker topics and consumer groups are involved, topology can change between versions even when business processing code does not change.

### Components to Inventory

| Component | Role | Upgrade Risk |
|---|---|---|
| `@RetryableTopic` | Declares attempts, backoff, suffixes, DLT, and retryable errors. | New defaults alter topology or semantics. |
| `RetryTopicConfiguration` | Centralized retry policy via bean/builder. | Conflicts with annotations targeting the same topic. |
| `@EnableKafkaRetryTopic` / `RetryTopicConfigurationSupport` | Bootstrap and global customization. | Duplicate infrastructure or lost customizers. |
| Retry topic names | Identifies destinations by delay/index/reuse. | Old topics orphaned, unread by new consumers. |
| Retry listener containers | Wait for and consume retry records. | Concurrency/group ID shifts. |
| `KafkaTemplate` and serializers | Forwards DTOs/raw bytes to retry/DLT. | Producer publishing failures. |
| Backoff/attempt headers | Stores due timestamps and retry history. | Wrong delay/attempt tracking or observability. |
| Exception classifier | Classifies retry, fatal, and DLT routing. | Infinite retries or premature DLT routing. |
| DLT handler | Handles records that do not recover automatically. | Growing DLT backlog or consumed without remediation. |
| Kafka consumer group offsets | Tracks reading progress per topic. | Duplicates, offset resets, or invisible backlogs. |

**Important:** Kafka does not automatically move a record from `orders.events-retry-1` to `orders.events-retry` when an application changes configuration. Those topics are independent logs on the broker.

## 2. Lock Down Invariants Before Making Changes

A safe retry infrastructure migration must prove:

1. **No retry records are stranded** in either the old or new topology.
2. Successfully processed events do not create duplicate business side effects on replay/restart.
3. Attempts, backoff, and fatal/non-retryable exceptions match the business contract.
4. The DLT has a topic, owner, retention, consumer/remediation path, and replay procedure.
5. Backoff does not let retention expire retry records before they become due.
6. Consumer groups/partitions and ACLs align with every active destination.
7. Data republished by the old release can still be decoded by the new release or has a migration path.
8. Rolling deployments and rollbacks can both handle **in-flight backlogs**.
9. Every source record can be proven to have eventually succeeded, reached the DLT, or followed an approved disposition.

If a job writes to a database, inspect business keys and committed data. Kafka retries can fire multiple times; listener callback count does **not** equal unique business effect count.

## 3. Spring Kafka Milestones to Watch

| Milestone | Notable Change | Migration Action Required |
|---|---|---|
| **Spring Kafka 2.7** | Added non-blocking retry via `@RetryableTopic` and `RetryTopicConfiguration`. | Inventory if the app previously built custom retry topics. |
| **Spring Kafka 2.9** | Changed bootstrap and infrastructure bean customization mechanisms. | Check enablement, support subclasses, and legacy overrides. |
| **Spring Kafka 3.0** | Allowed separate retry-container concurrency; changed some topic-creation defaults. | Cross-check consumer task counts, topics, and broker settings. |
| **Spring Kafka 3.2** | Supported `@RetryableTopic` on class-level `@KafkaListener`; refined backoff reuse. | Verify annotation discovery and topic topology. |
| **Spring Kafka 4.1** | Defaults to reusing **one retry topic for equal delay intervals**. | Inspect fixed-delay/multiple-attempt topologies and handle old retry topics. |

These are feature milestones, not a complete compatibility matrix. In a real project, confirm the Spring Boot BOM, Java, Kafka clients, broker version, serializer types, and deprecated/removed APIs. Never copy a Spring Kafka 4.x snippet to compile directly in a 3.x project where the API does not yet exist.

### Especially Important Default Change in 4.1

Suppose a fixed backoff policy of 1 second, 4 total attempts:

~~~text
Attempt 1: orders.events
Attempt 2: retry delay 1000 ms
Attempt 3: retry delay 1000 ms
Attempt 4: retry delay 1000 ms
Then:      DLT if still failing
~~~

With the **multi-topic strategy**, it may create:

~~~text
orders.events-retry-0
orders.events-retry-1
orders.events-retry-2
orders.events-dlt
~~~

With the **single-topic reuse strategy**, it may create only:

~~~text
orders.events-retry
orders.events-dlt
~~~

Starting in Spring Kafka 4.1, equal retry delay intervals are **reused by default**. To keep separate retry topics per attempt in supported versions, explicitly select a strategy such as `SameIntervalTopicReuseStrategy.MULTIPLE_TOPICS`. Exact names also depend on suffixing policy, index/delay settings, and custom config: do not treat the illustrative list above as guaranteed names for every deployment.

A similar risk arises when exponential backoff hits `maxInterval`: later attempts share **the same maximum delay**, so reuse can alter the retry topic count compared to the previous strategy. Calculate and verify the full effective topology, not just `retryTopicSuffix`.

## 4. Inventory Old and New Topologies

Before changing dependencies, record completely:

| Attribute | Old | Planned New |
|---|---|---|
| Spring Kafka / Spring Boot version | Fill in running release | Fill in target release |
| Source topic | `orders.events` | `orders.events` |
| Main consumer group | `orders-processor` | `orders-processor` |
| Attempts | 4 total | 4 total |
| Backoff | Fixed 1000 ms | Fixed 1000 ms |
| Retry topic names | `orders.events-retry-0/1/2` | `orders.events-retry` or keep old |
| Retry consumer groups | Measure on broker | Verify from context/broker |
| DLT topic/handler | `orders.events-dlt` | Keep or change intentionally |
| Partition count | 6 | 6 or designed mapping |
| Topic retention | Actual value | Covers max delay + outage window |
| Consumer concurrency | Actual main/retry values | Set targets and load-test |
| Serializer/deserializer | Including type headers | Including compatibility plan |
| Old retry backlog | May be non-empty | Must drain/bridge/keep reading |

Do not fill out the table by guessing from annotation names. Inspect live topics, partition counts, consumer-group offsets, and running app configuration. If 3.x already configured reuse earlier, moving to 4.1 **might not change topology**, so rely on evidence rather than assuming a change.

### Inspect Both Topics and Consumer Groups

~~~text
Main group: orders-processor
  subscribes: orders.events

Retry group(s): group ID combining main group + suffix
  subscribes: orders.events-retry-0
              orders.events-retry-1
              ...

DLT consumer:
  subscribes: orders.events-dlt
~~~

Retry containers typically derive group IDs from the main group and topic suffix. If suffixes/group IDs change, previous offsets **do not carry over**. A new group applies `auto.offset.reset` and consumes from `earliest` or `latest` when no committed offset exists. Both options carry risk if misaligned with migration: `earliest` can replay, while `latest` can drop data needing processing.

## 5. Bootstrap Infrastructure: Modern Configuration Approaches

There are three common configuration levels:

1. **`@RetryableTopic` on the listener:** simplest; the framework bootstraps required retry/DLT infrastructure automatically.
2. **`RetryTopicConfiguration` bean:** centralizes policy via builder for selected topics.
3. **Global configuration:** use either `@EnableKafkaRetryTopic` **or** extend `RetryTopicConfigurationSupport` when global behavior customization is needed.

### Using `@EnableKafkaRetryTopic`

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.annotation.EnableKafkaRetryTopic;

@Configuration
@EnableKafkaRetryTopic
public class RetryInfrastructureConfig {
    // RetryTopicConfiguration beans if needed.
}
~~~

`@EnableKafkaRetryTopic` is already meta-annotated with `@EnableKafka`. It is the route to enable/import infrastructure beans, not a requirement to add on every listener already using `@RetryableTopic`.

### Using `RetryTopicConfigurationSupport`

When advanced/global customization is required:

~~~java
import java.util.List;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.annotation.EnableKafka;
import org.springframework.kafka.retrytopic.RetryTopicConfigurationSupport;

@EnableKafka
@Configuration
public class CustomRetryInfrastructure
        extends RetryTopicConfigurationSupport {

    @Override
    protected void manageNonBlockingFatalExceptions(
            List<Class<? extends Throwable>> fatalExceptions) {
        fatalExceptions.add(UnsupportedEventSchemaException.class);
    }
}
~~~

`UnsupportedEventSchemaException` is an application-defined exception. This marks incompatible schema errors as fatal instead of retrying the same payload repeatedly.

**Never combine `@EnableKafkaRetryTopic` and a `@Configuration` extending `RetryTopicConfigurationSupport`.** Also ensure **at most one** configuration class extends support in the context. Spring Kafka 2.9 changed how infrastructure is bootstrapped/customized, so very old internal bean overrides must migrate to supported hooks rather than merely renaming imports and classes.

Places to audit during migration:

~~~text
@RetryableTopic
@EnableKafkaRetryTopic
@EnableKafka
RetryTopicConfigurationSupport
RetryTopicConfigurationBuilder
RetryTopicConfiguration
DeadLetterPublishingRecoverer
DefaultErrorHandler / CommonErrorHandler
@DltHandler
KafkaTemplate bean names
ConsumerFactory / KafkaListenerContainerFactory
~~~

This is a scope-identification checklist, **not** a list of classes that must be deleted. What matters is knowing which component builds the topology and which customizers actually execute after upgrading.

## 6. Configuring `@RetryableTopic` Explicitly

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.annotation.RetryableTopic;
import org.springframework.retry.annotation.Backoff;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    @RetryableTopic(
        attempts = "4",
        backoff = @Backoff(delay = 1_000, multiplier = 2.0),
        retryTopicSuffix = "-retry",
        dltTopicSuffix = "-dlt",
        autoCreateTopics = "false"
    )
    @KafkaListener(
        topics = "orders.events",
        groupId = "orders-processor"
    )
    public void handle(String eventId) {
        orderService.processIdempotently(eventId);
    }
}
~~~

`orderService` is an application dependency whose field/injection is omitted in the snippet; the focus is annotation configuration. In a real application, supply the service bean, serializers/deserializers, `KafkaTemplate`, and supporting infrastructure.

Explanation:

- `attempts="4"` normally includes the initial attempt on the main topic, meaning up to three non-blocking retry attempts before DLT unless a timeout or fatal policy intervenes.
- Exponential backoff can produce retry topics for different delays. Never assume exactly three retry topics if a reuse strategy applies.
- Suffixes are declared explicitly, yet **how index/delay appending and reuse work** must still be controlled.
- `autoCreateTopics="false"` prevents automatic topic creation; DevOps must provision the exact retry/DLT topic names and ACLs prior to publishing.
- Group ID is specified explicitly so reconciling offsets/groups during migration is unambiguous.

### Keeping Multi-Topic Strategy on 4.1

On versions supporting `SameIntervalTopicReuseStrategy`:

~~~java
import org.springframework.kafka.retrytopic.SameIntervalTopicReuseStrategy;

@RetryableTopic(
    attempts = "4",
    backoff = @Backoff(delay = 1_000),
    sameIntervalTopicReuseStrategy =
        SameIntervalTopicReuseStrategy.MULTIPLE_TOPICS
)
@KafkaListener(topics = "orders.events", groupId = "orders-processor")
public void handle(String value) {
    // Business processing.
}
~~~

This fragment illustrates **intentionally selecting topology**; do not copy it verbatim into older Spring Kafka versions lacking that attribute/enum. Consult documentation for your exact release. On older releases with different/deprecated strategy APIs, migrate to the supported API and test actual topic names.

## 7. `RetryTopicConfigurationBuilder` for Centralized Management

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.retrytopic.RetryTopicConfiguration;
import org.springframework.kafka.retrytopic.RetryTopicConfigurationBuilder;

@Configuration
public class OrdersRetryConfig {

    @Bean
    RetryTopicConfiguration ordersRetryPolicy(
            KafkaTemplate<String, String> template) {

        return RetryTopicConfigurationBuilder.newInstance()
            .exponentialBackoff(1_000, 2.0, 8_000)
            .maxAttempts(4)
            .includeTopics(List.of("orders.events"))
            .create(template);
    }
}
~~~

With the builder, policies can be centralized across multiple topics. Still avoid **multiple distinct configurations matching the same source topic**. Multiple `@KafkaListener`s on one topic are not guaranteed to give each annotation an independent topology: the framework may apply one retry configuration across listeners on the same source topic. If two listeners have conflicting retry policies, do not rely on bean scanning order or expect per-listener automatic resolution; design a unified configuration or separate the architecture.

### Checklist for Multiple Listeners on the Same Topic

- How many `@KafkaListener`s consume the same topic?
- Do those listeners share a consumer group or use different ones?
- How many `@RetryableTopic`/`RetryTopicConfiguration` definitions target that topic?
- Do retry/DLT suffixes or naming strategies overlap?
- Could two retry publishers be created with conflicting configurations?
- Could a retry record from the old version be interpreted under a different policy by the new version?

If an app switches from method-level annotations to class-level `@KafkaListener` in Spring Kafka 3.2+, also verify `@KafkaHandler` dispatch, DLT handler selection, and per-event-type policies. Avoid refactoring annotation placement at the same time as changing topic naming unless necessary.

## 8. Naming Rules: Suffixes Are Not the Whole Name

Retry topics are typically named from the source topic, retry suffix, and **delay or attempt index**. For example:

~~~text
orders.events-retry-1000
orders.events-retry-2000
orders.events-retry-4000
orders.events-dlt
~~~

Or:

~~~text
orders.events-retry-0
orders.events-retry-1
orders.events-retry-2
orders.events-dlt
~~~

In fixed-delay and reuse cases:

~~~text
orders.events-retry
orders.events-dlt
~~~

Beyond suffixes, consider:

| Option | Consequence |
|---|---|
| Suffix by **delay** | Names may reflect 1000/2000/4000 ms. |
| Suffix by **index** | Names reflect retry stage sequence. |
| Single topic for same intervals | Multiple attempts with equal delay share one topic. |
| Multiple topics | Separate topic per attempt. |
| Exponential max-interval reuse | Later attempts sharing max delay share a topic. |
| Custom `RetryTopicNamesProviderFactory` | Names may differ completely from default conventions. |
| Custom DLT exception routing | May add per-exception DLTs with custom suffixes. |

When upgrading, snapshots must record the **exact created/subscribed topic names**, not only the retry suffix. When infrastructure requires pre-created topics with `autoCreateTopics=false`, even a single character mismatch stops publishers/consumers from working.

## 9. Changing Topic Naming While Backlog Remains: Classic Scenario

Suppose before rollout:

~~~text
orders.events-retry-0: 12 unfinished records
orders.events-retry-1:  5 unfinished records
orders.events-retry-2:  3 unfinished records
orders.events-dlt:      7 records needing remediation
~~~

The new release switches to:

~~~text
orders.events-retry
orders.events-dlt
~~~

**The twenty old retry records will not magically appear in the new topic.** If the new release subscribes only to `orders.events-retry`, old records can sit on Kafka until retention expires with nobody processing them.

### Migration Options

| Option | Idea | When Suitable | Risk |
|---|---|---|---|
| **Keep old topology** | Pin naming/reuse so the new release still reads old retry topics. | New version has compatible APIs. | Headers/deserializers/offsets still need verification. |
| **Drain before cutover** | Stop emitting new retries to old topics and let old consumers finish backlog. | Short retry delays, bounded pending volume. | Must wait out the max backoff/outage window. |
| **Bridge consumer** | Read old topics and forward records onto the new path in a controlled way. | New topology change is mandatory and backlog is hard to drain. | Attempt headers, idempotency, duplicates. |
| **Parallel old/new** | Keep old retry consumers running while new publishers are active. | Planned zero-downtime rollout. | Risk of processing the same event on two paths. |
| **Approved replay** | Reprocess from source or DLT with keys and audit trail. | Cannot drain/bridge directly. | Can duplicate business effects if non-idempotent. |

**Draining** is not merely `lag=0` at one instant. Confirm all old producers have stopped creating new retries, due retry events have been processed, related groups have no pending items, and the DLT has its own disposition. If max backoff spans hours, a few quiet minutes are inconclusive.

### Mixed-Version Deployment

~~~text
Pod A: Spring Kafka 3.x -> multiple retry topics
Pod B: Spring Kafka 4.1 -> single retry topic
~~~

During a rolling deploy, both pods can share the main consumer group yet on failure forward to **two different topologies**. Some retries land in old topics while others land in the new topic. Without a compatibility plan:

- Old retry consumers might be scaled to 0 prematurely.
- New retry consumers do not read old topics.
- DLT handlers or serializers differ between versions.
- Rebalances cause an event to be redelivered.
- Business effects in DB/APIs can be duplicated.

Do not judge rollout success merely by "pod Ready." Trace test events through main, old/new retry destinations, DLT, and downstream under a **unique business key**.

## 10. Provisioning Kafka Topics to Match Topology

A retry infrastructure needs real topics with proper partitions, replication, retention, cleanup policy, ACLs, and quotas.

### Testing: Allowing Auto-Creation

~~~java
@RetryableTopic(
    attempts = "3",
    backoff = @Backoff(delay = 500),
    autoCreateTopics = "true",
    numPartitions = "1",
    replicationFactor = "1"
)
@KafkaListener(topics = "orders.events")
void handle(String value) {
    // Test demo.
}
~~~

Replication factor 1 fits a single-node test broker, **not** production defaults. Auto-creation requires `KafkaAdmin` and sufficient permissions; lacking rights or enough broker replicas causes topic creation to fail.

### Production: Pre-Provision, Disable Auto-Create

~~~java
@RetryableTopic(
    attempts = "4",
    autoCreateTopics = "false",
    retryTopicSuffix = "-retry",
    dltTopicSuffix = "-dlt"
)
@KafkaListener(topics = "orders.events", groupId = "orders-processor")
void handle(String eventId) {
    // Business processing.
}
~~~

Before rollout, infrastructure must create **all topics with verified exact names**. Example inventory:

~~~yaml
# Illustrative inventory declaration, NOT a full Kafka CRD.
sourceTopic: orders.events
sourcePartitions: 6
retryPolicy:
  maxAttempts: 4
  backoff: exponential
  initialDelayMs: 1000
  multiplier: 2
topics:
  - name: orders.events-retry-1000
    partitions: 6
  - name: orders.events-retry-2000
    partitions: 6
  - name: orders.events-retry-4000
    partitions: 6
  - name: orders.events-dlt
    partitions: 6
owner: kafka-platform
~~~

The list above holds only for **one chosen topology**; fixed backoff, reuse strategies, or custom naming yield different names. Infrastructure and code must share **a single source of truth for destination names**.

### Partition Routing

Retry/DLT publishers usually try to preserve the original partition. If the source has 6 partitions while the retry topic has 3, forwarding a record from partition 5 can fail because the destination lacks that partition. A partition resolver returning `null` lets the producer pick a partition in architectures that allow it, though that alters key affinity and ordering.

Verify:

- Partition counts and producer routing for every retry/DLT topic.
- Replication factor compatible with broker count.
- Retention **longer than max backoff plus incident remediation windows**.
- Producer has WRITE permission on retry/DLT; consumers have READ/group permissions.
- Message size/header growth and compression settings.
- Whether topic quotas or throttling could time out the retry publisher.

Some provisioning defaults change across releases—for example, replication factor may fall back to the broker default. Never let an upgrade unexpectedly create topics with durability or partition counts differing from infrastructure standards.

## 11. Consumer Groups, Offsets, and Concurrency

Retry topics have their own listener containers and consumer groups. Group IDs usually combine the main group ID with the retry destination suffix. Changing topic names or listener group settings means previous offsets **do not automatically carry over** to the new group.

| What Changed | Possible Consequence |
|---|---|
| Different group ID | Different offset reset behavior; replay or skipped old data. |
| Increased retry container concurrency | Higher throughput, but downstream DB/APIs may overload. |
| Decreased concurrency | Higher retry backlog/latency; SLO adjustment needed. |
| Increased partition count | More partition assignments, does not guarantee end-to-end ordering. |
| Pod count changes and group rebalance | Records can redeliver at commit boundaries. |

Starting in Spring Kafka 3.0, retry container concurrency can be tuned independently from the main container via supported APIs. Settings such as main concurrency 6 and retry concurrency 1 help when a downstream API is overloaded, provided backlog drain time is measured. Never raise retry concurrency just to "make jobs finish faster" if that overwhelms the target system.

**Never treat `lag=0` on the new group as proof that all retries are finished.** Old groups may still have pending work, and old topics may no longer have any active subscriber group.

## 12. Backoff Timestamps, Attempts, and Timeouts

Example:

~~~text
T0           original attempt
T0 + ~1000ms retry attempt 2
After fail + ~2000ms retry attempt 3
After fail + ~4000ms retry attempt 4
After fail   DLT
~~~

These are **target** times, not exact real-time schedules. Scheduling, consumer pause/resume, broker lag, rebalances, and downstream load can delay delivery further.

Common points of confusion:

- `maxAttempts=4` typically includes the original attempt.
- Topic count does **not** always equal attempts minus one when reuse is active.
- A chain-wide retry timeout can route a record to the DLT before exhausting all attempts.
- Blocking retries, if combined, can add extra listener invocations.
- Attempt/timestamp headers are part of semantics; changing how headers are written/read can affect custom monitoring and compatibility.

Across versions, Spring Kafka offers options to retain multiple values or only a single value for certain retry headers to limit header growth. If operational code reads internal headers directly, inventory header names, multi-value cases, and retain/strip policies before upgrading.

## 13. Exception Policies Can Make Topology Look Right While Business Behavior Is Wrong

A transiently failing record should be retried boundedly. A permanently corrupt record rarely becomes valid simply by sending the same bytes through retry topics.

~~~java
@RetryableTopic(
    attempts = "4",
    backoff = @Backoff(delay = 1_000, multiplier = 2.0),
    include = {TransientPartnerException.class},
    exclude = {InvalidOrderException.class}
)
@KafkaListener(topics = "orders.events", groupId = "orders-processor")
void handle(String eventId) {
    // Service processes event and may throw exceptions.
}
~~~

`TransientPartnerException` and `InvalidOrderException` are custom exceptions. Confirm include/exclude APIs and cause traversal for your exact release.

| Error | Suggested Policy |
|---|---|
| HTTP 503/429 on idempotent API | Retry with backoff, timeouts, and limits. |
| Transient database deadlock | Retry when transaction/replay is safe. |
| Permanently malformed JSON | Usually DLT/stop; do not retry identical bytes indefinitely. |
| Incompatible schema version | DLT/stop and fix producer/consumer. |
| Authorization/ACL error writing retry topic | Fix infrastructure; do not treat as item data error. |
| Permanent business validation failure | Do not retry blindly. |
| Code bug such as NPE | Fail/escalate; avoid masking bugs with long retries. |
| Schema registry temporarily unavailable | Classify based on real client recoverability. |

Spring Kafka maintains lists of **fatal exceptions** in non-blocking retry, along with global APIs to add or remove entries. After upgrading, verify that specific exceptions route through retry stages or straight to the DLT as expected; checking topic counts alone will not catch classifier regressions.

## 14. Serialization and `ErrorHandlingDeserializer` Are Sensitive Migration Points

A retry/DLT record may contain:

- A successfully deserialized DTO or String where the listener later threw an exception.
- **Raw `byte[]`** when value deserialization failed and `ErrorHandlingDeserializer` preserved the original bytes for recovery.
- Raw key bytes when **key deserialization** failed.
- Headers from an older producer/consumer carrying different schema/type metadata.

Hence the retry/DLT `KafkaTemplate` may need a serializer supporting multiple runtime types.

~~~java
import java.util.LinkedHashMap;
import java.util.Map;
import org.apache.kafka.common.serialization.ByteArraySerializer;
import org.apache.kafka.common.serialization.Serializer;
import org.springframework.kafka.support.serializer.DelegatingByTypeSerializer;
import org.springframework.kafka.support.serializer.JsonSerializer;

Map<Class<?>, Serializer<?>> serializers = new LinkedHashMap<>();
serializers.put(byte[].class, new ByteArraySerializer());
serializers.put(OrderEvent.class, new JsonSerializer<>());

var retryValueSerializer = new DelegatingByTypeSerializer(serializers);
~~~

`OrderEvent` is an application DTO; this is an illustrative fragment, not a complete `ProducerFactory`. For Spring Kafka 4.x, check the target version's JSON/Jackson serializer APIs rather than copying 3.x imports unchecked. If keys can also be raw bytes, the key serializer must support them too; a lone `StringSerializer` cannot handle every case.

### Compatibility of Old Retry Backlogs

If an old-version producer sent a serialized DTO to a retry topic, the new-version consumer must:

1. Read the old byte format properly.
2. Handle type headers/target packages per security policy.
3. Preserve the event ID and business semantics.
4. Ensure exception metadata remains intact for classification/recovery.
5. Never deserialize untrusted classes just to push migration through.

When changing JSON serializers, schema registries, or event classes, run a **compatibility integration test** where the old app produces the record and the new app consumes it. Testing only new-app-to-new-app is insufficient.

## 15. DLT Infrastructure Must Be Migrated Too

The Dead Letter Topic isolates records that exhausted retries or were classified fatal. It has its own topic, producer, consumer group/handler, retention, and remediation workflow.

~~~java
@DltHandler
public void handleDlt(String payload) {
    quarantineService.storeForReview(payload);
}
~~~

This is a fragment: `quarantineService` belongs to the application and needs safe handling of sensitive data, idempotency, and appropriate transactions.

Checklist:

- Is the DLT name still right? Are there custom per-exception DLTs?
- Is the DLT topic provisioned with the right ACLs?
- When no `@DltHandler` exists, is the default logging handler/consumer acceptable for business needs?
- If another service handles the DLT, must auto-starting the DLT handler be disabled in this app?
- When the DLT handler fails, is `ALWAYS_RETRY_ON_ERROR` or `FAIL_ON_ERROR` used?
- Can the new handler read schemas of older DLT records?
- Is retention long enough for investigation and replay?

A DLT consumer that merely **reads and logs** does not mean the business event was fixed or approved to drop. Maintain remediation states and clear ownership.

## 16. Feature Limitations You Cannot Ignore

Spring Kafka's non-blocking retries have important official limitations:

- **Non-blocking retries are not supported with batch listeners** under this feature.
- **Non-blocking retries do not combine with container transactions** under supported semantics.

If during the same upgrade you convert a record-level `@KafkaListener` to batch-level or enable container transactions, you must redesign the recovery path. Do not keep the annotation and assume the framework behaves the same way.

Alternatives include blocking retries, transaction rollback/after-rollback handling, or a dedicated durable-intent architecture depending on Kafka offset and business transaction needs. Test the chosen design on the exact container type and broker.

## 17. Non-Blocking Retries Alter Ordering

Example on a single partition:

~~~text
offset 100: OrderUpdated(order-A, version=1) -> fails -> retry topic
offset 101: OrderUpdated(order-A, version=2) -> succeeds on main topic

Later:
retry consumer processes version=1
~~~

Kafka guarantees order **within one partition of one topic**, yet once `v1` moves to a retry topic, the handler can apply `v2` first and `v1` afterward. If the database writer performs "last write wins" without checking versions, state regresses.

Therefore, if switching from blocking to non-blocking retries:

- Design `aggregateVersion`/sequence checks and optimistic locking.
- Ensure consumers are idempotent by event ID.
- Define a policy for late or out-of-order events.
- Where strict ordering is mandatory, consider keeping blocking retries or another model.

This is a **business semantic change**, not just a throughput optimization.

## 18. Safe Two-Phase Migration

### Phase A — Upgrade Libraries, Preserve Current Topology

1. Lock down current versions and topology from broker/config.
2. Migrate global bootstrap config to compatible APIs if needed.
3. Explicitly pin attempts, suffixing, reuse, timeouts, fatal exceptions, and DLT strategy.
4. Preserve old topic names and consumer groups where possible.
5. Test payloads from the old app on the new consumer.
6. Verify pending retry topics continue being consumed and the DLT still works.
7. Deploy canary/rolling and monitor both old and new retries.

### Phase B — Intentionally Change Topic Reuse/Naming

1. Choose the new topology and rationale (fewer topics, easier management, lower broker load, etc.).
2. Provision topics, partitions, replication, and ACLs.
3. Drain/bridge backlogs on the old topology.
4. Switch publishers/listeners per cutover plan.
5. Verify business idempotency and DLT behavior.
6. Decommission old topics only after zero actionable records remain.

If both phases must combine into one deployment, test cross-version bridging/rollback far more rigorously; it cannot be treated as a routine dependency bump.

## 19. Retry Topology Cutover Runbook

### Pre-Cutover

| Task | Expected Evidence |
|---|---|
| Snapshot old names/partitions/groups | Inventory stored by deployment ID. |
| Calculate max backoff + retention window | Sufficient time to drain and investigate. |
| Identify who still writes to old retries | Producer list and stop schedule. |
| Provision new retry/DLT topics | Verified topic settings and ACLs. |
| Verify rollback plan | Consumer/bridge ready to read new topics if reverting. |
| Test idempotency | Replaying one event twice produces one business effect. |
| DLT remediation owner | Person/channel accountable for failed records. |

### During Cutover

1. Record exact timestamp with timezone, versions, and config changes.
2. Restrict old producers from creating new retry destinations per plan.
3. Keep old retry consumers or bridges running until drain evidence is complete.
4. Start new consumers and inspect partition assignments/group IDs.
5. Inject probe events with unique business IDs to trigger transient and permanent failures.
6. Verify retry delays, attempts, suffixes, DLT routing, and publish acknowledgments.
7. Monitor **old topics and new topics simultaneously**.

### Post-Cutover

Close the migration only when old retry backlogs have no orphaned records, no producer writes to old topics, DLT items have proper dispositions, and business outputs reconcile. Do not delete old topics immediately if retention/audit or rollback remains possible.

## 20. An Integration Test Verifying the Retry Chain

Unit tests invoking listener methods directly **do not verify** topic names, broker forwarding, consumer groups, or delays. Include a Kafka broker in tests: Embedded Kafka or Testcontainers/cluster tests.

### Test Probe Listener

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.annotation.RetryableTopic;
import org.springframework.retry.annotation.Backoff;
import org.springframework.stereotype.Component;

@Component
public class RetryProbeListener {

    private final ConcurrentHashMap<String, AtomicInteger> counts =
        new ConcurrentHashMap<>();
    private final CountDownLatch completed = new CountDownLatch(1);

    @RetryableTopic(
        attempts = "4",
        backoff = @Backoff(delay = 500),
        autoCreateTopics = "true",
        numPartitions = "1",
        replicationFactor = "1"
    )
    @KafkaListener(topics = "upgrade.orders", groupId = "upgrade-probe")
    public void onMessage(String id) {
        int attempt = counts.computeIfAbsent(
            id, ignored -> new AtomicInteger()).incrementAndGet();

        if (attempt <= 2) {
            throw new TestTransientException("TEST_TRANSIENT");
        }

        completed.countDown();
    }

    public boolean awaitCompletion() throws InterruptedException {
        return completed.await(20, TimeUnit.SECONDS);
    }

    public int attempts(String id) {
        AtomicInteger n = counts.get(id);
        return n == null ? 0 : n.get();
    }
}
~~~

`TestTransientException` is a custom test exception. The probe uses in-memory state solely for observation in an isolated test, never as a durable counter for production or multi-node runs.

### Embedded Kafka Test Harness

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.test.context.EmbeddedKafka;

@SpringBootTest
@EmbeddedKafka(
    partitions = 1,
    topics = {"upgrade.orders"},
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
class RetryUpgradeIntegrationTest {

    @Autowired
    KafkaTemplate<String, String> kafkaTemplate;

    @Autowired
    RetryProbeListener probe;

    @Test
    void transientFailureIsRetriedThenSucceeds() throws Exception {
        String eventId = "upgrade-test-001";

        kafkaTemplate.send("upgrade.orders", eventId, eventId)
            .get(10, TimeUnit.SECONDS);

        assertThat(probe.awaitCompletion()).isTrue();
        assertThat(probe.attempts(eventId)).isEqualTo(3);
    }
}
~~~

**Assumptions:** the context configures `KafkaTemplate` and `RetryProbeListener`; `KafkaAdmin`/`@RetryableTopic` creates topics per test policy, and the container has time to receive partition assignments. The test must not collide with another suite sharing the same group/topic/state. Provide the test exception class, producer config, and suitable test Kafka broker.

The test above proves the listener is retried and completes, yet is **not enough** to prove migration safety. Extend assertions to cover retry topic names, actual consumer groups, DLT delivery, and old backlogs.

## 21. Testing Old Topology to New Topology

To verify compatibility, construct a scenario:

~~~text
T0: old app sends record R to orders.events-retry-1
T1: old app stops
T2: new app starts with orders.events-retry
T3: who processes R?
~~~

Valid answers depend on your strategy:

- **Keep old topics:** the new consumer actually subscribes to the old topic and processes R.
- **Drain:** old consumers stay running until R reaches a final outcome.
- **Bridge:** a component moves R onto the new path while preserving event IDs and approved retry semantics.
- **Reprocess:** an audit record and idempotency ensure replay creates no duplicates.

**Never accept "new consumer lag=0" as a passing test result.** It does not measure lag on old topics. Where feasible, use both real app versions: have the old app produce retry records/headers, then have the new app consume them. That is far more trustworthy than synthesizing internal headers by guesswork.

### DLT Test

Send a record designed to fail permanently and verify:

1. Exact attempt count matching the chosen policy.
2. Event arrives on the exact DLT topic.
3. Source metadata/exception headers are sufficient for tracing.
4. DLT producer serializer handles both DTOs and raw bytes if used.
5. DLT consumer/quarantine produces a clear outcome rather than just logging.

If DLT publishing fails, test offset/recovery semantics: the source record must never be silently treated as recovered under contracts prohibiting data loss.

## 22. Testing Rollback and Duplicates During Rolling Deploy

With non-blocking retries, an event can be seen by the handler multiple times. If the handler writes to a DB:

~~~sql
-- Anti-pattern when events can replay.
UPDATE account
SET balance = balance + :amount
WHERE account_id = :accountId;
~~~

If that statement commits and a failure happens before the Kafka ack/offset commit, a retry can credit the balance a second time. Risk increases when two versions run concurrently.

Instead you need:

- A durable event ID from the producer.
- A unique processed-event marker in the same DB transaction as the business update.
- Idempotency keys/status checks on remote APIs.
- Version guards if aggregate ordering matters.
- Final data reconciliation by event ID rather than counting callbacks.

Fault-injection test:

~~~text
Attempt 1: business DB commits -> crash before Kafka ack
Attempt 2: record redelivered -> business effect DOES NOT increment a second time
~~~

Also test a record republished by the old version and processed by the new version, and vice versa for rollback. **Kafka producer idempotence does not replace business idempotency** when multiple application attempts emit the same event.

## 23. Upgrade Test Matrix

| ID | Scenario | Result to Verify |
|---|---|---|
| U-01 | Valid event. | Main listener processes properly, no retry. |
| U-02 | Transient exception a few times then success. | Retry attempts/routing accurate. |
| U-03 | Permanent exception. | DLT/stop per policy, no infinite retries. |
| U-04 | Max attempts exhausted. | DLT holds record and source metadata. |
| U-05 | Fixed-delay reuse differs across versions. | Topic names/consumer groups match design. |
| U-06 | Exponential reaches max interval. | Reuse or multiple-topic strategy behaves as intended. |
| U-07 | Old retry topic has remaining backlog. | Records drained/bridged/processed, never orphaned. |
| U-08 | Mixed-version rolling deploy. | No lost/duplicated business effects. |
| U-09 | Retry destination missing partitions. | Publish error reported, no silent loss. |
| U-10 | Topic not provisioned / missing ACL. | Startup/publish monitored with rollback readiness. |
| U-11 | DLT producer wrong serializer for raw bytes. | Recovery failure detected. |
| U-12 | Key deserialization fails. | Raw key handled via appropriate publisher. |
| U-13 | Consumer group ID changes. | Offset reset/replay follows plan. |
| U-14 | Retry consumer rebalance. | Backoff/progression/duplicate tolerance hold. |
| U-15 | App crashes after retry publish ACK. | No duplicate business effects. |
| U-16 | DLT handler fails. | DLT failure strategy/alert works. |
| U-17 | JSON/type headers from old version. | New consumer decodes or routes safely. |
| U-18 | Two listeners on the same source topic. | No hidden policy conflicts. |
| U-19 | Retry concurrency changed. | Does not overload downstream. |
| U-20 | Retention shorter than recovery window. | Risk caught before dropping records. |
| U-21 | Rollback from new to old deployment. | New retry backlog still has a recovery path. |
| U-22 | Reprocessing from DLT. | Event ID preserved, audit/idempotency intact. |

Prioritize U-05, U-07, U-08, and U-21 because these are classic **retry infrastructure migration failures** that never surface in ordinary listener happy-path tests.

## 24. Observability During Migration

A dashboard watching only the source topic is insufficient. Collect metrics from **both old and new topologies**:

| Area | Signals |
|---|---|
| Main topic | Processing rate, failures, lag, rebalances, consumer groups. |
| Old retry topics | Lag by old groups, pending record counts, last publisher timestamp. |
| New retry topics | Publish success/failure, retry rate, lag, oldest pending age. |
| DLT | Arrival rate, unremediated backlog, failed DLT handlers. |
| Producer forwarding | Serialization errors, Kafka ACK failures, ACL/quota errors. |
| Retry containers | Active containers, assigned partitions, pause/resume, concurrency. |
| Business output | Dedup counts, version mismatches, missing/duplicate event IDs. |
| End-to-end | Source event → completed/DLT/replayed/quarantined outcome. |

Example structured log (application-defined):

~~~json
{
  "event": "kafka.retry.forwarded",
  "deploymentVersion": "orders-vNext",
  "sourceTopic": "orders.events",
  "destinationTopic": "orders.events-retry",
  "consumerGroup": "orders-processor",
  "attempt": 2,
  "errorCategory": "PARTNER_TEMPORARY_FAILURE",
  "result": "PUBLISHED"
}
~~~

Never log raw payloads, credentials, or unredacted full headers containing exception stack traces. Never use event IDs/offsets as high-cardinality metric labels; detailed IDs belong in protected audit logs/traces.

### Why `lag=0` Does Not Prove Drained

Zero lag on one consumer group reflects only that group's progress on its assigned partitions. It does not prove no older producer is still sending, no other old group remains, no DLT items sit unhandled, or downstream DB state is accurate. Decommissioning must rely on **an inventory of producers + groups + pending records + business outcomes**.

## 25. Rolling Back When the New Deployment Misbehaves

Rolling back the application image to the old version **is not enough** if the new version already published records to new retry topics that the old version does not subscribe to.

Procedure:

1. Lock down timestamps, versions, and destination topics written by the new release.
2. Freeze further topology changes per approval.
3. Inventory backlogs in **new retry topics and DLT**.
4. Determine whether the old version can read the new destinations or needs a bridge/compatibility consumer.
5. Restore the old app and inspect main/retry groups.
6. Process records across both old and new topologies, reconciling by event ID.
7. Check serializer/schema compatibility for payloads produced by the new app.
8. Clean up new topics only after proving every record has a final disposition and no retention/audit need remains.

**Do not delete new topics just to make dashboards look green.** That can destroy unresolved events. Likewise, do not reset consumer group offsets merely to keep consumers moving without a replay/idempotency plan.

## 26. Post-Upgrade Investigation Runbook

When failed records stop retrying or events go missing from the DLT:

**A. Identify the Record and State**

~~~text
springKafkaVersion / deploymentVersion
sourceTopic / partition / offset
consumerGroup / listenerId
businessEventId
expected exception category
expected attempts / backoff
last observed destination
~~~

**B. Check Configuration**

- Was `@RetryableTopic` discovered?
- Are two global bootstrap paths active simultaneously?
- Does another `RetryTopicConfiguration` bean match the same source topic?
- Did retry naming/reuse/index/delay strategies change?
- Can `KafkaTemplate` producer serializers read/write old records?
- Did the fatal exception list or DLT routing change?

**C. Check the Broker**

- Do the actual topics exist with sufficient partitions/replication?
- Does the publisher have WRITE permission and receive ACKs from retry/DLT?
- Do retry consumer groups have assigned partitions and proper committed offsets?
- Do old retry topics hold orphaned backlogs?
- Is the DLT consumer/handler running per policy?

**D. Decide Recovery**

- Did any record already execute business side effects?
- Are retry records in the old or new topology?
- Is drain, bridge, rollback, or replay needed?
- Are there duplicate/out-of-order events needing reconciliation?
- Who approves data/topic/offset interventions?

**E. Closure Criteria**

Close the incident only once actionable events reach outcomes, old/new backlogs have zero orphans, the DLT is managed, and business data has no out-of-contract errors or duplicates. "Pod Running" is never the sole closure condition.

## 27. Common Anti-Patterns

**"Just bumping the dependency; retry infrastructure surely stays the same."** Default naming/reuse, global bootstrapping, and hooks may have changed.

**"Suffix is still `-retry`, so names must be identical."** Appending delay/index or reuse changes the full name.

**"Spring Kafka automatically migrates records to the new topic."** No; Kafka topics are separate logs.

**"Using both `@EnableKafkaRetryTopic` and extending `RetryTopicConfigurationSupport` to be extra safe."** Causes duplicate beans and context failures.

**"Each `@RetryableTopic` on the same source topic gets an isolated config."** Not always; avoid policy conflicts.

**"`maxAttempts=4` means there must be four retry topics."** No; it usually includes the original attempt, and topic count depends on reuse.

**"Backoff=1000ms is an exact real-time deadline."** Scheduling, consumer lag, and rebalances delay actual execution.

**"A new Group ID does not affect data."** Offsets belong to the group; changing it risks replays or skips.

**"A record landing in the DLT means business handling is done."** The DLT is quarantine requiring remediation.

**"Non-blocking retries preserve per-key ordering with the source topic."** Not across topics; later events can overtake earlier ones.

**"Non-blocking retries support all batch listeners and container transactions."** False per feature limitations.

**"`JsonSerializer` alone handles all retry/DLT records."** Deserialization errors may require a raw `byte[]` producer.

**"Old retry lag hitting 0 right at deploy is enough to delete the topic."** Producers may still be publishing, or DLT/other groups remain active.

**"Rollback is just swapping the app image."** Records already published by the new version must still be handled.

**"Keeping topic retention short saves disk."** Retry backoff plus outages can exceed retention and drop records before due time.

## 28. Retry Topic Infrastructure Change Checklist

### Before the Change

- [ ] Pin old/new versions of Spring Boot, Spring Kafka, Kafka clients, and brokers.
- [ ] Inventory `@RetryableTopic`, beans, support classes, and listeners sharing source topics.
- [ ] Lock down attempts, backoff, timeouts, fatal exceptions, DLT, and topic suffix/index/delay/reuse.
- [ ] Record exact old retry/DLT topics, partitions, ACLs, retention, and consumer groups.
- [ ] Identify old backlogs and every producer still writing to old topics.
- [ ] Verify serializers for DTOs, raw `byte[]`, and old-version payloads.
- [ ] Choose keep-topology, drain, or bridge with an assigned owner.
- [ ] Check compatibility with batch listeners/container transactions.
- [ ] Prepare a rollback plan covering **Kafka data**, not only application binaries.

### During Testing and Rollout

- [ ] Provision destinations matching the target topology.
- [ ] Test transient/permanent errors, attempts, DLT, and retry timestamps.
- [ ] Test records sitting in old retry topics after upgrade.
- [ ] Test Kafka group/offset progression and mixed-version deploys.
- [ ] Test DLT publish failures, serializer mismatches, and partitions.
- [ ] Test business idempotency, duplicates, and ordering guards.
- [ ] Monitor old/new retry lag and consumers concurrently.

### After Rollout

- [ ] Zero actionable records orphaned in old topics.
- [ ] No unexpected publishers still sending to old retry destinations.
- [ ] DLT has an owner and events have proper dispositions/replays.
- [ ] Business outputs reconciled by event IDs/versions.
- [ ] Recovery/rollback remains executable if an incident emerges.
- [ ] Decommission old topics only with approval and evidence.
- [ ] Update runbooks, topic manifests, dashboards, and topology docs.

## 29. Official Documentation and Version Discipline

To verify differences in your project, consult documentation for the **exact version of Spring Kafka running or being deployed**:

- [Non-Blocking Retries](https://docs.spring.io/spring-kafka/reference/retrytopic.html) — mechanics and limitations.
- [Retry Topic Configuration](https://docs.spring.io/spring-kafka/reference/retrytopic/retry-config.html) — annotations, builders, and global bootstrap.
- [Topic Naming](https://docs.spring.io/spring-kafka/reference/retrytopic/topic-naming.html) — suffixes, delay/index, single/multiple topic reuse.
- [Retry Topic Features](https://docs.spring.io/spring-kafka/reference/retrytopic/features.html) — backoff, classifiers, timeouts, headers, and DLT routing.
- [DLT Strategies](https://docs.spring.io/spring-kafka/reference/retrytopic/dlt-strategies.html) — DLT handlers and failure policies.
- [Kafka Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html) — transaction semantics and limits with non-blocking retries.

Unversioned reference pages usually show the current stable release. Use the version selector / 3.x docs if your project is on 3.x; do not copy attributes introduced only in 4.1 into older source code and assume a compatible migration.

## Conclusion

**Changing retry topic infrastructure** directly impacts **failed-record routing, consumer-group offsets, and business result consistency**. Spring Kafka 2.9 changed infrastructure bootstrapping/customization; 3.x releases expanded APIs and reuse strategies; Spring Kafka 4.1 changed the default to reuse equal retry intervals. Consequently, the same attempts/backoff policy is not guaranteed to produce the same topic names across every release.

To upgrade reliably, **lock down the old topology before editing code**, explicitly configure defaults prone to change, check pending records in old retry topics, drain/bridge or retain a compatible topology, and test failures and rollbacks against a real Kafka broker. After deployment, watch both old and new topics, the DLT, offsets, serialization, and business idempotency. Only when every record has a verifiable outcome and no backlog is stranded is the migration truly complete.
