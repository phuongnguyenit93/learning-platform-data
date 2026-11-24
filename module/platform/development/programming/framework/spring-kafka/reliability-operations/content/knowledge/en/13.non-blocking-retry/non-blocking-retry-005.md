# Topic Naming

In Spring Kafka, **non-blocking retry** routes a failed record to one or more retry topics, delays processing, and retries on corresponding listeners. Once attempts are exhausted, the record is usually moved to a **dead-letter topic (DLT)**. Because each step can correspond to a physical Kafka topic, topic naming is part of operational design: names must reflect the data flow, avoid colliding with other applications, remain easy to observe, and be manageable via automated infrastructure.

Spring Kafka provides default naming conventions along with options to customize suffixes, strategies for appending delays or indexes to names, and deeper customization when needed. This topic focuses on **topic naming** in non-blocking retry, from how names are formed to production deployment decisions.

## 1. Where Do Topic Names Sit in the Non-Blocking Retry Flow?

Suppose a system reads order events from topic `orders.created`. When processing fails because a dependent service is unavailable, Spring Kafka can forward the record to a delayed retry topic. If it still fails after all attempts, the record is moved to the DLT:

```text
orders.created
     |
     | listener fails
     v
orders.created-retry-1000
     |
     | retry after ~1 second, still failing
     v
orders.created-retry-2000
     |
     | retry after ~2 seconds, still failing
     v
orders.created-retry-4000
     |
     | retry after ~4 seconds, still failing
     v
orders.created-dlt
```

The names and wait times in the diagram are **illustrative examples** for a multi-delay configuration. The actual list of physical topics depends on `attempts`, backoff policy, suffix strategy, same-delay topic reuse behavior, and Spring Kafka version.

Components to distinguish:

| Component | Role | Example name |
|---|---|---|
| Main topic | Source receiving initial events | `orders.created` |
| Retry topic | Holds records for reprocessing after a delay | `orders.created-retry-1000` |
| Another retry topic | Another wait level or retry stage | `orders.created-retry-2000` |
| DLT | Quarantines records not recovered after exhausting retries | `orders.created-dlt` |

Retry topics and DLTs are real Kafka topics. They have their own partitions, replication factors, retention, ACLs, metrics, and storage costs. Changing naming can create new topics, affecting active topologies and how applications observe or replay records.

## 2. Spring Kafka's Default Naming Convention

When configuring `@RetryableTopic`, Spring Kafka typically takes the **main topic name** as the base and appends suffixes for auxiliary topics:

- Retry topics use the default `-retry` suffix.
- Dead-letter topics use the default `-dlt` suffix.
- Retry topics can have a delay value or index appended to distinguish different retry destinations.

For a main topic `payments.requested`, a set of names might be:

```text
payments.requested
payments.requested-retry-1000
payments.requested-retry-2000
payments.requested-retry-4000
payments.requested-dlt
```

The base name helps operators quickly recognize topics belonging to the same flow. The `-retry` portion indicates records have not yet succeeded and are being retried; `-dlt` shows records have entered the final error-handling path.

Importantly, **do not predict the topology from suffixes alone**. When configuration changes, there may be fewer retry topics than attempts, especially when multiple attempts share the same delay and are combined into one topic. To know exact names, check the Spring Kafka configuration and the actual topics present in the cluster.

## 3. Setting Suffixes via @RetryableTopic

`@RetryableTopic` lets you customize the retry topic and DLT suffixes using `retryTopicSuffix` and `dltTopicSuffix`.

Example:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.annotation.RetryableTopic;
import org.springframework.retry.annotation.Backoff;

@RetryableTopic(
        attempts = "4",
        backoff = @Backoff(
                delay = 1_000,
                multiplier = 2.0,
                maxDelay = 4_000),
        retryTopicSuffix = "-processing-retry",
        dltTopicSuffix = "-processing-dlt")
@KafkaListener(
        topics = "orders.created",
        groupId = "order-processor")
public void handle(OrderCreated event) {
    orderService.process(event);
}
```

In this example, the base name remains `orders.created`, while retry topics use the suffix `-processing-retry` and the DLT is `orders.created-processing-dlt`. If delay-based suffixing is used, a retry topic may be named `orders.created-processing-retry-1000`.

`attempts = "4"` means **at most four processing attempts, including the first**; when all attempts fail, the record is moved to the DLT according to the configured strategy. Growing delays can produce distinct wait levels for the three retries.

Types `OrderCreated` and `orderService` are illustrative business components. A real application needs matching deserializers, serializers, Kafka listener containers, and topic infrastructure.

### When Should You Change the Suffix?

Consider custom suffixes when multiple independent pipelines consume the same main topic, when an organization enforces topic naming standards, or when avoiding collisions with existing operational topics.

For example, two consumer groups read `orders.created` but execute two different business workflows:

```text
orders.created
    |
    +-- inventory-service
    |     orders.created-inventory-retry-1000
    |     orders.created-inventory-dlt
    |
    +-- billing-service
          orders.created-billing-retry-1000
          orders.created-billing-dlt
```

If both pipelines use identical retry/DLT names, they risk unintentionally sharing physical topics. Different consumer groups have separate offsets yet still read data from the same topic; thus one pipeline could see the other pipeline's retry records. Separate suffixes clarify data ownership and reduce misprocessing risk.

## 4. TopicSuffixingStrategy: Suffix by Delay or by Index?

When multiple retry destinations are created, an additional naming segment is needed to tell them apart. Spring Kafka provides `TopicSuffixingStrategy` to choose whether to append suffixes by **delay value** or **index**.

| Strategy | Meaning | Illustrative names |
|---|---|---|
| `SUFFIX_WITH_DELAY_VALUE` | Uses delay duration to distinguish retry destinations | `orders-retry-1000`, `orders-retry-2000` |
| `SUFFIX_WITH_INDEX_VALUE` | Uses an index for retry destinations | `orders-retry-0`, `orders-retry-1` |

Actual index numbers and topic sets also depend on how Spring Kafka constructs the retry topology for your version and topic reuse policy; names in the table only illustrate shape.

### 4.1. Suffix by Delay Value

Names like `orders-retry-1000` let operators immediately see the configured delay in milliseconds. This is convenient when each retry tier has a different wait interval.

Advantages:

- Topic names reflect the retry wait interval.
- Easy to correlate backoff configuration with topics in dashboards.
- Fits exponential backoff with distinct wait levels.

Limitations:

- Changing delays can change physical topic names.
- Multiple retries with the same delay require appropriate reuse or naming differentiation rules.
- The topic name reflects configured delay, not a guarantee the record will execute at that exact millisecond; actual timing depends on consumer scheduling, polling, and system load.

### 4.2. Suffix by Index

Names like `orders-retry-0` or `orders-retry-1` express destination order instead of exposing delay values.

Advantages:

- Shorter names when delays are long or configurations have many tiers.
- Decouples topic identity from numeric delay values in the name.
- Convenient when operational policy only needs to distinguish retry tiers.

Limitations:

- Requires checking configuration to know which delay corresponds to an index.
- Changing retry tier count or reuse strategy can alter the meaning of indexes.
- Cannot assume the index equals the number of listener invocations if multiple attempts are consolidated into one retry topic.

Depending on the Spring Kafka version, this strategy is configured via annotation attributes or the retry topic configuration builder. When operating a specific version, check the supported `TopicSuffixingStrategy` API before changing topology.

## 5. Relationship Between Backoff and Number of Retry Topics

Retry topic names depend not only on `retryTopicSuffix`. They also depend on attempt count, delays, and topic reuse strategy.

For example, with an initial retry after 1 second, the next after 2 seconds, and the next after 4 seconds, Spring Kafka may create three distinct retry destinations. With **fixed backoff** where every retry waits 1 second, some configurations/versions allow **reusing the same retry topic** for attempts with identical delays.

Conceptual comparison:

```text
Exponential backoff:
main -> retry-1000 -> retry-2000 -> retry-4000 -> dlt

Fixed backoff, separate retry destinations:
main -> retry-0 -> retry-1 -> retry-2 -> dlt

Fixed backoff, reusing topic with same delay:
main -> retry-1000 -> retry-1000 -> retry-1000 -> dlt
                    (same physical topic)
```

The final diagram depicts logical flow returning to the same retry topic; Kafka does not create three copies of a topic just because the topic appears three times in the diagram.

Policies for reusing retry topics with the same delay can vary across Spring Kafka versions. Therefore, do not commit to a topic count based solely on attempts. When documenting infrastructure, use the **actually created topic names or actual topic definitions** as the source of truth.

## 6. Naming DLTs and Routing by Exception Type

DLTs commonly carry the `-dlt` suffix. They hold records the application failed to process successfully through normal retries. DLT names should make the main topic and owning business flow clear.

Example:

```text
invoices.issued                  # main
invoices.issued-retry-1000       # retry
invoices.issued-retry-5000       # retry
invoices.issued-dlt              # dead letter
```

In some designs, DLTs need to be routed by error type:

```text
invoices.issued-dlt-validation
invoices.issued-dlt-downstream
invoices.issued-dlt
```

Those names are design conventions, **not automatically created by Spring Kafka simply because an exception belongs to that category**. Routing to multiple DLTs requires configuring routing rules or destination resolvers matching your Spring Kafka version. Without such configuration, treat `-dlt` as the default destination.

When designing multiple DLTs, clearly decide where each error category is stored, retention duration, who owns remediation, and how replay works. Splitting DLTs can help with permissions and triage, but also increases the number of topics, ACLs, dashboards, and runbooks to manage.

## 7. Naming and Consumer Group ID Are Two Separate Layers

Topic names are physical resources on the Kafka cluster. Consumer group IDs determine offsets and partition distribution among consumers in the same group.

Example:

```text
Topic: orders.created-processing-retry-1000
  group A: has its own offsets
  group B: has its own offsets
```

If two listeners use different consumer group IDs yet subscribe to the same retry topic, **both groups can receive that record**. Changing the group ID does not make a retry topic private to one pipeline.

Spring Kafka typically creates retry topic and DLT containers from the original listener and applies group ID rules to those related containers. However, that is group membership mechanics; it does not replace assigning unique topic names between pipelines.

In multi-service architectures or architectures with multiple consumer groups on the same main topic, include a service or business identifier in retry/DLT suffixes. Avoid letting two independent pipelines accidentally share a physical retry path.

## 8. Topic Names and Kafka Limits

Kafka topic names have length and character restrictions. Safe, common characters include Latin letters, digits, periods (`.`), hyphens (`-`), and underscores (`_`). Kafka typically caps topic names at 249 characters.

Because Spring Kafka **appends suffixes** to the main topic, a main topic name near the limit can become invalid once `-retry-<delay>` or `-dlt` is added.

Example:

```text
Original name:
  commerce.orders.fulfillment.events.v2

Retry name:
  commerce.orders.fulfillment.events.v2-retry-16000

DLT name:
  commerce.orders.fulfillment.events.v2-dlt
```

Keep essential identifiers in the name, but avoid overly long names just to cram all metadata into the topic name. Frequently changing info such as deploy timestamps, build numbers, or pod IDs belongs in configuration, labels, metrics, or headers rather than in retry topic names.

Because periods and underscores can produce identical normalized metric names in Kafka, follow one consistent convention cluster-wide to avoid monitoring confusion.

## 9. Naming by Environment and Ownership

In shared clusters, topics may need an environment or domain prefix to prevent collisions:

```text
dev.orders.created
dev.orders.created-retry-1000
dev.orders.created-dlt

staging.orders.created
staging.orders.created-retry-1000
staging.orders.created-dlt

prod.orders.created
prod.orders.created-retry-1000
prod.orders.created-dlt
```

If each environment uses a separate cluster, embedding the environment name in topics may be unnecessary. What matters is a single convention consistent with deployment architecture, ACL grants, IaC, and dashboards.

Topic naming should answer:

- Which domain/service owns the topic?
- Is the topic main, retry, or DLT?
- Which pipeline/consumer group owns the retry topic if multiple pipelines share a main topic?
- Should the suffix reflect delay or index?
- Who has permission to create topics, publish, consume, and replay?

Never embed the application version into the suffix on every deploy. If each release creates a new set of retry topics, records left in the old topic set risk going unwatched by new consumers. When versioning a topology is necessary, have a clear migration and draining plan.

## 10. Auto-Creating Topics vs. Pre-Existing Topics

In local or test environments, Spring Kafka can assist with creating retry/DLT topics based on configuration. In production, many systems require topics to be created via Terraform, GitOps, a Kafka operator, or cluster governance pipelines.

Example disabling auto-creation on the annotation:

```java
@RetryableTopic(
        attempts = "4",
        retryTopicSuffix = "-retry",
        dltTopicSuffix = "-dlt",
        autoCreateTopics = "false")
@KafkaListener(topics = "orders.created")
public void onOrder(OrderCreated event) {
    orderService.process(event);
}
```

When `autoCreateTopics = "false"`, the application **must not assume** all retry/DLT topics already exist. The topic set must be provisioned beforehand with appropriate partition count, replication factor, retention, and ACLs; otherwise, retry publishing can fail or consumers may not receive expected partitions.

Items to declare when provisioning topics via infrastructure:

| Attribute | Why attention is needed |
|---|---|
| Topic name | Must match the exact name Spring Kafka constructs. |
| Partition count | Sufficient for routing/recovery and retry listener parallelism. |
| Replication factor | Aligned with durability targets and broker count. |
| Retention | Long enough to retain records during retry waits, investigation, and replay. |
| ACL | Producer can write retry/DLT; consumer can read corresponding topics. |
| Quota/monitoring | Makes write volume, lag, and retry/DLT errors visible. |

In recovery configurations that preserve the source record's partition, retry/DLT topics need matching target partitions. If a target partition does not exist, publishing can fail. Plan retry/DLT partition counts to be compatible with the main topic and with how `DeadLetterPublishingRecoverer` selects partitions.

## 11. Changing Topic Naming in a Running System

Changing `retryTopicSuffix`, `dltTopicSuffix`, `TopicSuffixingStrategy`, or the number of delay levels can **change physical topic names**. This is a topology change that must be rolled out with a plan.

Initial example:

```text
orders.created-retry-1000
orders.created-retry-2000
orders.created-dlt
```

After switching to a service-specific suffix:

```text
orders.created-fulfillment-retry-1000
orders.created-fulfillment-retry-2000
orders.created-fulfillment-dlt
```

Records in the old retry topic set do not automatically move to the new set. If the new application only subscribes to the new names, records waiting in old topics may be stranded until a consumer processes them or a replay workflow runs.

When renaming, you should:

1. Inventory existing main/retry/DLT topics and remaining records/lag.
2. Pre-declare new topics with proper partitions, ACLs, retention, and monitoring.
3. Decide how to handle records in old topics: drain them, keep old listeners running during transition, or run controlled replay.
4. Deploy listeners with the new configuration via an observable rollout process.
5. Verify failed records are published to the right new retry topics and DLT.
6. Delete old topics only after remaining records are handled and retention policies are met.

If a release is rolled back, the old application may not consume retry topics just created by the new version. Build rollback capability into the renaming plan from the start.

## 12. How Topic Naming Affects Metrics and Runbooks

Consistent naming helps spot failures quickly on dashboards:

```text
Topic                                Records in    Lag
orders.created                       high          low
orders.created-retry-1000            rising        low
orders.created-retry-2000            rising        rising
orders.created-dlt                   rising        depends on DLT consumer
```

Values in the diagram indicate trends only. Rapidly rising records-in on retry topics or continuous arrivals in the DLT can signal a failing dependency, invalid data, or a regression from a deploy.

An operational dashboard should group:

- Main topic, retry topics, and DLT of the same pipeline.
- Records/bytes entering each retry topic over time.
- Consumer lag of retry and DLT listeners per partition.
- Rate of records returning to success vs. entering DLT.
- Retry/DLT publish failures, deserialization errors, and authorization errors.
- Time records spend in retry state before succeeding or being quarantined.

Do not infer actual retry timing solely from suffixes `1000` or `2000`. The suffix shows the **configured delay value**, whereas actual completion time can be longer when consumers are busy, topics have lag, or brokers experience issues.

Runbooks should list the exact retry/DLT names the system owns, explain why each tier exists, where to look up errors, and the replay procedure. When multiple applications share a Kafka cluster, naming conventions also help scope ACLs and avoid operating on the wrong topic.

## 13. Testing to Verify Topic Names

You can use Embedded Kafka or Kafka Testcontainers to verify the topology `@RetryableTopic` builds. Tests should focus on **records landing in the right topics** rather than merely asserting names predicted from annotations.

Recommended integration scenario:

1. Start the application with `@RetryableTopic` and the expected topic set.
2. List actual topics via Kafka AdminClient or cluster admin tools.
3. Send a record for which the listener intentionally throws a retryable exception.
4. Confirm the record appears in the configured retry destination.
5. Let subsequent retries fail and confirm the record reaches the expected DLT.
6. Verify key, value, headers, and required source metadata are preserved.
7. If multiple pipelines share the main topic, confirm failed records from one pipeline do not appear in another pipeline's retry/DLT topics.
8. If auto-create is disabled, run a test with a missing retry topic to observe failure behavior and ensure infrastructure provisioning catches gaps.

With Kafka command-line tools on a cluster, you can list topics:

```bash
kafka-topics.sh --bootstrap-server localhost:9092 --list
```

Do not hard-code the list of retry topics independently across source code, tests, and IaC and let them drift apart. Maintain a verifiable naming convention synchronized between application config and infrastructure.

## 14. Common Mistakes

- **Two pipelines sharing retry topics unintentionally:** different consumer groups do not isolate data at the physical topic level.
- **Assuming there is always one topic per retry:** reusing topics with the same delay can result in fewer topics than attempts.
- **Reading a delay suffix and assuming exact execution timing:** actual retry schedules also depend on consumer scheduling, lag, and resources.
- **Changing suffixes on rollout without handling old topics:** records waiting for retry may be left behind.
- **Creating only the main topic in IaC:** the application still needs retry/DLT topics with exact names and permissions.
- **Creating retry topics with fewer partitions than routing requires:** publishing to a non-existent partition can fail.
- **Using overly long names:** adding delay/index and DLT suffixes can exceed Kafka limits.
- **Embedding pod IDs or build IDs in names:** each deploy creates new topics and makes stranded retry flows hard to manage.
- **Sharing a single DLT for all errors without ownership:** makes it unclear who investigates and replays failures.
- **Confusing retry topic names with group IDs:** topic names define where records are stored, while group IDs define offsets and consumer assignments.

## 15. Choosing a Naming Convention for Production

A practical convention uses the main topic as the root, adds a pipeline identifier if multiple independent flows exist, and applies consistent suffixes for retry and DLT:

```text
<main-topic>[-<pipeline>]-retry[-<delay-or-index>]
<main-topic>[-<pipeline>]-dlt
```

This is a **design convention**, not mandatory Kafka syntax. The `<pipeline>` segment can be omitted if each main topic has only one retry pipeline and the organization has clear ownership.

| Context | Naming direction |
|---|---|
One service handling one main topic | Keep default `-retry` / `-dlt` for simplicity. |
Multiple services subscribing to one main topic | Add a service or business identifier suffix for retry/DLT. |
Exponential backoff with different delays | Delay-based suffixes make wait tiers clear on dashboards. |
Wanting to decouple topic names from delay values | Consider index-based suffix strategy, verifying version compatibility. |
Cluster managing topics via IaC | Disable auto-create if policy requires; define all retry/DLT topics before rollout. |
Changing retry config on a system with live data | Plan draining/migration and rollback for old topics. |

When designing **topic naming** for non-blocking retry, treat topic names as part of the operational contract. Good names make it clear which stage a record is in, which pipeline owns it, and where to investigate. When suffixes, delay/index strategies, topic provisioning, and migration plans align, a Spring Kafka system can retry cleanly, stay easy to monitor, and minimize lost records during configuration changes.
