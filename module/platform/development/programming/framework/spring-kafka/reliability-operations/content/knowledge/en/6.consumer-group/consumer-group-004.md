# Business-Aligned Stable group.id

In Kafka, a consumer group is a processing unit with its own reading progress. The `group.id` value determines which consumers share reading of a data stream and share committed offsets. Therefore, `group.id` should represent **a stable business processing responsibility**.

A consumer group typically outlives a pod, a JVM, or a single deployment. When an application restarts or scales out with additional replicas, new consumers must join the right group to resume saved progress. If `group.id` changes by pod name, timestamp, or build number, Kafka treats it as a different group and the application may start a new offset history.

This guide explains how to name `group.id` by business purpose, how to choose between sharing and separating groups, how to configure it in Spring Kafka, and the implications of changing identifiers.

## 1. What Does group.id Identify?

Kafka stores offsets per consumer group, topic, and partition. When consumers read records, the group can commit offsets to record the next position to process. Consumers with the same `group.id` join the same coordination group and share that reading progress.

For example, topic `orders` has four partitions. Three instances of the order projection service join the `orders-projection` group. Kafka distributes the partitions across the three consumers. Each partition is assigned to at most one consumer in the group at a time, while one consumer can receive multiple partitions.

    Topic orders
      partition 0 ----+
      partition 1 ----+----> group: orders-projection
      partition 2 ----+          |
      partition 3 ----+          +--> consumer instance A
                                  +--> consumer instance B
                                  +--> consumer instance C

When an instance stops, the group rebalances to redistribute partitions among active members. New instances joining with the same `group.id` can resume from the group's committed offsets, provided those offsets are still valid.

If another service needs to receive all `orders` events to issue invoices, that service must use a separate group. Two independent groups have two separate reading progresses:

    Topic orders
       |
       +----> group: orders-projection
       |          +--> multiple consumers sharing load
       |
       +----> group: invoice-issuer
                  +--> multiple consumers sharing load

Each group receives the record stream at its own pace. Creating a new group does not increase the number of consumers sharing load in an existing group; it creates an independent subscriber reading the topic separately.

### 1.1. Distinguishing group.id from other identifiers

| Identifier | Purpose | Should it change per deployment? |
|---|---|---|
| group.id | Identifies the logical consumer group and offset namespace | No, if the processing responsibility remains the same |
| client.id | Identifies a Kafka client for logs and metrics | Can include instance info if needed |
| member.id | Identifies a member within the group managed by Kafka | Managed by Kafka during group membership |
| group.instance.id | Static member identifier when static membership is enabled | Stable per member, intentionally assigned |
| @KafkaListener id | Identifies the listener container in Spring | Stable and unique within the application context |
| application name | Name of the deployed service or application | May be broader than a single consumer responsibility |

`group.id` is not the name of a pod or an individual Kafka client. It represents the set of consumers collaborating to process the same business stream.

## 2. Naming group.id by Business Responsibility

A group name should help operators answer the question: **What responsibility is this consumer group reading data to fulfill?**

An easy-to-understand naming pattern is:

    <environment>.<business-domain>.<processing-purpose>[.<version>]

Examples:

- `prod.orders.projection.v1`: builds the order read projection for production.
- `prod.billing.invoice-issuer.v1`: issues invoices from business events.
- `prod.risk.fraud-detection.v1`: analyzes events for fraud detection.
- `prod.fulfillment.shipment-planner.v1`: plans shipments.
- `staging.orders.projection.v1`: order projection in the staging environment.

Dots, hyphens, or other naming conventions can be used. What matters is that the name is meaningful, stable, and consistently applied across the organization.

One group can read multiple topics if the records serve the same processing responsibility. Conversely, one topic can have multiple independent groups if multiple systems need to consume the same events at their own pace. Therefore, do not default `group.id` to just the topic name or application name.

### 2.1. One group for one logical workload

If multiple replicas run the same service and produce the same type of business outcome, they typically share `group.id`.

Example: four pods of `orders-projection` all read topic `orders` and update the same read model. They must join the same group so Kafka distributes partitions and shares load.

~~~yaml
spring:
  kafka:
    consumer:
      group-id: prod.orders.projection.v1
~~~

When a rolling deployment replaces old pods with new pods, `group.id` stays unchanged. New members join the existing group and continue from committed progress.

### 2.2. Separating groups for independent responsibilities

If two services need to receive the same events but perform different tasks, they must have separate `group.id` values.

~~~java
@KafkaListener(
    id = "ordersProjectionListener",
    groupId = "prod.orders.projection.v1",
    topics = "orders"
)
public void updateProjection(OrderEvent event) {
    projectionService.apply(event);
}

@KafkaListener(
    id = "invoiceIssuerListener",
    groupId = "prod.billing.invoice-issuer.v1",
    topics = "orders"
)
public void issueInvoice(OrderEvent event) {
    invoiceService.issue(event);
}
~~~

Both listeners above receive records from topic `orders`, yet each listener has its own progress. If they shared `group.id`, they would join the same group and compete for partitions via group assignment. A record is delivered to one member in the group at a time, so you cannot rely on a shared group to guarantee both projection and invoicing receive every record.

This is a core rule when designing event-driven systems:

- Same processing responsibility, needing load sharing: use the same `group.id`.
- Independent processing responsibility, needing the full stream separately: use different `group.id` values.

## 3. Why Does group.id Need to Be Stable?

Kafka stores offsets by `group.id`. When a consumer restarts with the same `group.id`, it can resume from committed offsets. If `group.id` changes, Kafka treats it as a different group and does not automatically transfer offsets from the old group to the new group.

Suppose group `prod.orders.projection.v1` has processed up to offset 850 on partition 0. A deployment changes `group.id` to `orders-projection-20261115`. The new group does not have offset 850. Kafka must apply the `auto.offset.reset` policy since there is no valid offset for the new group.

    old group: prod.orders.projection.v1
       partition 0 -> committed offset 850

    deployment changes group.id

    new group: orders-projection-20261115
       partition 0 -> no committed offset yet
       |
       +--> auto.offset.reset decides the starting position

If `auto.offset.reset=earliest`, the new group may re-read retained records on the topic from the beginning of stored data. If using `latest`, the new group starts at the end of the log and only receives new records after startup. These two choices can lead to drastically different business outcomes.

### 3.1. Impact of auto.offset.reset

`auto.offset.reset` is applied when a group has no valid offset—for example, a brand-new group with no committed offsets or offsets that have fallen outside the retained log range.

| Value | Behavior | Cases to consider |
|---|---|---|
| earliest | Starts from the earliest retained record | Rebuilding a projection or replaying retained data |
| latest | Starts from the end of the log | Only wanting to process new data when creating a new group |
| none | Throws an error if no valid offset is found | Enforcing explicit offset configuration and avoiding automatic positioning |

Configuration example:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: prod.orders.projection.v1
      auto-offset-reset: earliest
~~~

`earliest` cannot recover records that have expired past retention or been removed by compaction. `latest` is also not a fix for lost historical data; it deliberately skips the backlog prior to the new group's starting position.

For a group that already has valid offsets, changing `auto.offset.reset` normally does not move the consumer back to the start of the topic. This policy is not an offset reset command for an active group.

### 3.2. Old offsets are not guaranteed to exist indefinitely

Using a stable `group.id` preserves continuity, but it does not mean offsets live forever. Kafka enforces a retention policy for offsets of inactive consumer groups. Topics also have their own retention or compaction policies. If a group stops for too long, offsets expire, or source records are gone, restarting may not recover the full history.

Define the maximum outage duration the system must tolerate, configure appropriate retention settings, and monitor the last commit timestamps. For rebuildable projections, have a plan to replay from retained source data or snapshots.

## 4. Avoid Generating group.id per Instance or Deployment

Certain naming patterns break group stability:

| Naming pattern | Example | Consequence |
|---|---|---|
| By pod | orders-projection-pod-7c9d | Each pod may create its own group and re-read the entire stream |
| By hostname | orders-projection-node-03 | Scaling or moving nodes changes the group |
| By timestamp | orders-projection-20261115 | Every deployment may create a new group |
| By build number | orders-projection-build-482 | Offset history fragments by build |
| By random UUID | orders-projection-7f3a... | Restarts may create a brand-new group |
| By request or user | orders-projection-user-1042 | Group count grows uncontrollably and offsets fragment |

Example of an incorrect configuration when the goal is a single load-sharing workload:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: orders-projection-pod-7c9d
~~~

Each pod may join a different group. In that case, each group receives the entire topic instead of splitting partitions with the other pods. This increases read volume, inflates offset count, and can duplicate business side effects.

The right configuration is to use a fixed `group.id` tied to the responsibility:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: prod.orders.projection.v1
~~~

Instance names can still appear in `client.id` or logs to distinguish members. There is no need to put the instance name into `group.id` just to tell which consumer is running.

## 5. Configuring group.id in Spring Kafka

Spring Kafka lets you set `group.id` in shared consumer configuration or specify it directly on each `@KafkaListener`.

### 5.1. Default configuration in application.yml

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1:9092,kafka-2:9092
    consumer:
      group-id: prod.orders.projection.v1
      auto-offset-reset: earliest
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.trusted.packages: com.example.events
~~~

`group-id` under `spring.kafka.consumer` is the default value Spring Boot uses when creating consumers. It works well when all listeners in the application truly belong to the same logical workload.

If an application contains multiple listeners with different responsibilities, specify a separate `groupId` on each `@KafkaListener` rather than letting all listeners accidentally share the default group.

### 5.2. Specifying groupId on @KafkaListener

~~~java
@KafkaListener(
    id = "ordersProjectionListener",
    groupId = "prod.orders.projection.v1",
    topics = "orders"
)
public void consume(OrderEvent event) {
    projectionService.apply(event);
}
~~~

The `groupId` attribute on the annotation overrides the `group.id` inherited from the consumer factory for that listener. Explicit declaration makes the listener's responsibility and reading progress immediately clear.

The `id` attribute identifies the listener container in Spring. By Spring Kafka's default behavior, if `id` is set and `groupId` is not declared, `id` can be used as `group.id` when `idIsGroup=true`. An explicit `groupId` overrides this behavior. You can set `idIsGroup=false` if you want `id` to act strictly as a container identifier.

To avoid accidentally using a container id as the offset identifier, declare `groupId` explicitly on important listeners:

~~~java
@KafkaListener(
    id = "invoiceIssuerContainer",
    idIsGroup = false,
    groupId = "prod.billing.invoice-issuer.v1",
    topics = "orders"
)
public void issueInvoice(OrderEvent event) {
    invoiceService.issue(event);
}
~~~

`id` must be unique within the application's application context, whereas `groupId` must be consistent across instances deploying the same workload. The two attributes have different scopes and purposes.

### 5.3. One application with multiple listeners

A Spring Boot application can run multiple listener containers. If they serve independent responsibilities, configure a separate `groupId` for each listener:

~~~java
@KafkaListener(
    id = "paymentProjectionContainer",
    groupId = "prod.payments.projection.v1",
    topics = "payments"
)
public void updatePaymentProjection(PaymentEvent event) {
    paymentProjection.apply(event);
}

@KafkaListener(
    id = "riskScoringContainer",
    groupId = "prod.risk.scoring.v1",
    topics = "payments"
)
public void scorePayment(PaymentEvent event) {
    riskScoring.score(event);
}
~~~

Two listeners can live in the same codebase yet maintain independent reading progress. Being deployed in the same application does not mean they share the same business responsibility.

Conversely, if one listener runs across multiple pods to process a single workload together, all pods must use the same `groupId`. Do not append hostnames or replica identifiers to that value.

## 6. Scaling Consumers Without Changing group.id

When increasing instance count or concurrency, new consumers join the same group. Kafka rebalances and distributes partitions across members. `group.id` does not need to change when the replica count changes.

Example:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: prod.orders.projection.v1
    listener:
      concurrency: 3
~~~

With concurrency set to 3, the listener container can create three consumers in the same group according to configuration. If the application runs three pods and each pod has concurrency 3, the group can have nine consumer members in total.

However, the number of consumers actively processing in parallel is bounded by the assigned partitions. If a topic has four partitions and the group has nine consumers, some consumers will not be assigned any partitions. Increasing concurrency beyond the partition count does not automatically increase throughput.

| Partition count | Consumers in group | Possible outcome |
|---:|---:|---|
| 4 | 1 | One consumer processes all four partitions |
| 4 | 2 | Two consumers split the partitions |
| 4 | 4 | Each consumer can receive one partition |
| 4 | 8 | Up to four consumers receive partitions; the rest remain idle |

Creating a different `group.id` per replica is not how you scale. That creates multiple independent subscribers, each reading the entire stream with its own offsets. To share load, add members within the same group.

## 7. When Should You Create a New group.id?

Changing `group.id` is a decision about processing history and reading progress. Only change it when you genuinely want to create a new logical consumer group.

Valid reasons may include:

- A new business capability needs to read the same topic and produce a different output.
- A new projection needs to replay history to build its own read model.
- A new processing version has incompatible semantics and needs to run in parallel for migration.
- A workload requires independent progress, offset retention, and operational ownership.

Cases that normally do NOT require changing `group.id`:

- Deploying new code when the business responsibility has not changed.
- Restarting a pod or JVM.
- Scaling replica count or changing concurrency.
- Changing hostname, node, container image tag, or build number.
- Updating logging, metrics, or timeout configurations without changing consumption logic.

### 7.1. Version suffixes must be meaningful

You can include a version in the group name when semantic changes require an independent offset history:

    prod.orders.projection.v1
    prod.orders.projection.v2

For example, v2 changes how order state is computed and needs to rebuild the projection from scratch. Group v2 can use `earliest` to re-read retained data while v1 keeps running to compare results.

This is an intentional migration. Before rolling out, determine:

1. Whether v2 will start from `earliest`, `latest`, or an explicitly set offset.
2. Whether the topic still retains enough history to rebuild the projection.
3. Whether v1 and v2 can write to the same table or trigger the same side effects concurrently.
4. How results will be compared and when traffic will switch over.
5. How v1 will be stopped while preserving rollback capability.

Do not add a version to `group.id` on every release. If every build creates a new group, consumers may re-read data, create duplicates, and leave behind hard-to-manage stale groups.

### 7.2. Changing group.id does not automatically migrate offsets

If you need to rename a group while resuming from the previous read position, plan an explicit offset migration. Kafka does not copy committed offsets from an old group to a new group just because their names are similar.

You can use consumer group admin tools to describe or shift offsets under a controlled procedure. Ensure the new consumer is stopped while setting offsets, verify the exact topic-partitions, and inspect the result before starting the workload. Do not run the new group with `auto.offset.reset` expecting it to discover the old group's offsets automatically.

## 8. Environments, Tenants, and Identifier Scope

### 8.1. Distinguishing environments

If dev, staging, and production share a Kafka cluster, include the environment in `group.id`:

    dev.orders.projection.v1
    staging.orders.projection.v1
    prod.orders.projection.v1

This separates offsets and makes groups easy to locate in dashboards. If environments use separate clusters, Kafka already isolates group namespaces at the cluster level, though keeping the environment-prefixed naming convention can still aid operational consistency.

Never share a `group.id` across environments if they might accidentally connect to the same cluster and need independent reading progress.

### 8.2. Per-tenant groups

Some systems need to isolate progress by tenant because each tenant has its own processing schedule, access controls, or recovery requirements. In such cases, a dedicated group per tenant can be considered.

However, do not create groups per user or per request. If tens of thousands of tenants churn continuously, group and offset counts will surge, complicating monitoring and administration.

Before choosing a per-tenant group model, determine:

- Do tenants truly need independent reading progress?
- Are there per-tenant replay, retention, or ACL requirements?
- What is the maximum tenant count and rate of tenant creation/deletion?
- Does the topic use tenant-based partition keys to preserve required ordering?
- Can the platform operationally manage and monitor the expected number of groups?

If tenants can share a single processing stream, use one stable group and carry `tenantId` in the key or payload. The application routes business logic per tenant inside the handler. Only split groups when progress isolation and operational needs genuinely require it.

### 8.3. Do not put sensitive data into group.id

`group.id` can appear in metrics, logs, admin tools, and ACL configurations. Do not put emails, phone numbers, sensitive customer IDs, tokens, or secrets into group names. Use capability names or non-sensitive technical identifiers.

## 9. Static Membership Does Not Replace group.id

Kafka supports static membership through `group.instance.id`. This property provides a stable identity for a member so the group can recognize it when it restarts under certain conditions. Static membership can reduce rebalances caused by brief restarts, especially in deployment environments with stable instance identities.

Distinguish clearly:

- `group.id` identifies the logical group and shared offsets.
- `group.instance.id` identifies a specific member within the group when static membership is enabled.

For example, three instances of a workload can use the same `group.id`, while each instance has its own instance-stable `group.instance.id`:

    group.id = prod.orders.projection.v1
    group.instance.id = orders-projection-member-0

Do not use the same `group.instance.id` for multiple simultaneously active members in the same group; that can trigger member conflicts. If the orchestration platform recreates pods with different names, evaluate how static member identities are assigned and how `session.timeout.ms` is configured.

Static membership optimizes group join behavior. It is not a reason to put pod names into `group.id`, nor does it replace business-aligned group naming.

## 10. group.id and Kafka Access Control

In clusters with authorization enabled, consumer group access can be controlled via ACLs on the `GROUP` resource type. Group names are therefore also part of the operational and security boundary.

When changing `group.id`, consumers may require permissions for the new group. An application authorized to read a topic but lacking permissions for its corresponding group can hit authorization errors when joining or committing offsets.

When designing group names, coordinate with ACL conventions:

- Grant permissions per workload or domain as needed.
- Do not grant overly broad permissions merely to work around inconsistent group names.
- When migrating to a new group, provision ACLs before starting consumers.
- Revoke old group permissions after the migration and rollback window closes.

Stable group names make access control easier to manage and audit.

## 11. Observing and Operating Consumer Groups

A business-meaningful `group.id` helps operators map Kafka metrics directly to service responsibilities. Monitor:

- Consumer lag by group, topic, and partition.
- Active member count and group state.
- Rebalance frequency and rebalance completion duration.
- Committed offsets and last commit timestamps.
- Record processing rate and error rate per group.
- Unexpected new groups appearing after deployments.
- Groups with zero remaining members that still hold offsets or unresolved lag.

If every deployment creates a new group, dashboards can become cluttered with many similarly named groups. That makes it hard to tell which group is the active workload, which holds stale offsets, and which is still consuming data.

Include the group name in logs and traces alongside `topic`, `partition`, `offset`, `eventId`, and `client.id`. Do not use `group.id` in place of `eventId`; the group identifies the workload, while `eventId` identifies a business event.

### 11.1. Inspecting groups with Kafka tools

Consumer group state can be inspected using the Kafka CLI:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --describe \
  --group prod.orders.projection.v1
~~~

This command lets you inspect partition assignments, current offsets, log end offsets, and lag per group. Script names or invocation syntax may vary by Kafka distribution and operating system.

To list groups:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --list
~~~

Before deleting or resetting a group, confirm no workload still depends on that progress and that you have a recovery plan. Deleting groups or resetting offsets are administrative actions that can alter replay behavior and business side effects.

## 12. Testing group.id in Spring Kafka

In tests, avoid letting test runs share production groups or reuse a static group carrying leftover offsets from a previous run if the test expects to read from the beginning.

You can create dedicated groups for tests:

~~~java
@KafkaListener(
    id = "ordersTestListener",
    groupId = "test.orders.projection",
    topics = "orders-test"
)
public void consume(OrderEvent event) {
    testRecorder.record(event);
}
~~~

If tests run in parallel, each test may need its own group so it does not compete for offsets and partition assignments with other tests. In test environments, dynamic group IDs can be useful due to short lifespans and test isolation goals. Never carry that dynamic naming pattern over to production.

An integration test should verify meaningful behaviors:

1. Two consumers in the same group share partitions and do not concurrently receive two copies of the same record delivery under normal conditions.
2. Two different groups can both receive the same records from a topic.
3. Restarting a consumer with the same `group.id` resumes from committed offsets when offsets remain valid.
4. Using a new `group.id` creates a new offset history and obeys `auto.offset.reset`.
5. Scaling consumer count without changing `group.id` maintains a single logical workload.
6. Configuring `groupId` on the annotation overrides the default group as expected.

Tests should assert business outcomes and offsets, not merely that the application starts successfully.

## 13. Common Misconfiguration Scenarios

| Scenario | Consequence | Resolution |
|---|---|---|
| Each pod has its own group.id | Every pod reads the entire topic | Use the same `group.id` across replicas of the same workload |
| Two independent workflows share group.id | They split partitions and neither receives every record | Separate groups by responsibility |
| Changing group.id per build number | New group lacks old offsets; may replay or skip backlog | Keep names stable across deployments |
| Changing group.id while keeping auto.offset.reset=latest | New group starts at log end and misses older backlog | Choose reset policy according to migration goals |
| Creating a new group with earliest after topic retention expired | Cannot rebuild data that was already deleted | Supplement with snapshots or another storage source |
| Using listener id as group unintentionally | Changing container id changes the group | Declare `groupId` explicitly |
| Using one group per user | Group and offset counts grow rapidly | Use one workload group and classify users in payload if appropriate |
| Scaling concurrency by changing group.id | Each group reads the entire stream instead of sharing load | Increase members/concurrency within the same group |
| Changing group but forgetting ACLs | Consumers cannot join or commit offsets | Grant permissions for the new group before deploying |
| Duplicate static member ids | Members can conflict | Assign a unique `group.instance.id` per member |

## 14. Naming Convention Applicable in Projects

A practical convention should contain just enough components to clarify purpose:

    <env>.<domain>.<capability>.<version>

Examples:

| group.id | Responsibility |
|---|---|
| prod.orders.projection.v1 | Builds the order read model |
| prod.orders.search-indexer.v1 | Updates the order search index |
| prod.billing.invoice-issuer.v1 | Issues invoices |
| prod.payments.reconciliation.v1 | Reconciles payments |
| prod.risk.fraud-detection.v1 | Analyzes fraud |
| staging.orders.projection.v1 | Order projection in staging |

The version can be omitted if the organization does not manage versions in group names. If included, increment it only when an independent offset history or intentional migration is needed.

Document this convention in the domain's operational runbook alongside each group's owner, subscribed topics, processing purpose, required retention, and reset/replay procedures. When a workload is renamed or retired, establish a process to clean up old groups after confirming there are no remaining rollback or audit needs.

## 15. Decision Principles

When creating a new consumer or modifying Spring Kafka configuration, start by identifying the processing responsibility:

- If multiple instances perform the same responsibility together, use the same stable `group.id`.
- If two responsibilities need to receive the same events independently, use different `group.id` values.
- If only restarting, scaling, or deploying new code, keep `group.id` unchanged.
- If replaying history or migrating with independent progress, create a new group with an explicit plan for offsets and side effects.
- If splitting by environment or tenant, do so only when independent progress, permissions, or operational boundaries are required.
- If identifying individual clients or members, use `client.id` or `group.instance.id` for its intended purpose; do not change `group.id`.

A well-chosen `group.id` tells operators which business capability a consumer serves and enables Kafka to preserve reading progress across the deployment lifecycle. Treat `group.id` as the long-lived identity of a logical consumer workload, and manage changing it as a change to data processing history.