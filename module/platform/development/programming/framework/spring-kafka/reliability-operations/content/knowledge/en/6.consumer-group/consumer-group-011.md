# Preventing Unintended group.id Changes

In Kafka, **`group.id`** defines the identity of a consumer group. Kafka uses this value to coordinate consumers sharing partitions and to store committed offsets. Therefore, the group ID is part of data-processing identity: changing it can cause an application to start a new reading stream, re-read old data, or skip a backlog depending on offset configuration.

In Spring Kafka, the group ID can come from Spring Boot consumer configuration, `ConsumerFactory`, listener attributes, or environment variables. An unintended override can cause every pod to join a different group, two independent services to share a single group, or a deployment to spawn a brand-new group. These mistakes rarely make application startup fail; instead, they alter record distribution and can introduce duplicates or missed business processing.

The operational goal is to keep the group ID stable for the same logical consumer subscription, changing it only when there is an explicit offset migration and data-handling plan.

## 1. What Does group.id Represent?

A consumer group is a set of consumers collaborating to read one or more topics. For a multi-partition topic, Kafka assigns partitions to consumers in the group to share load. Consumers in the same group share an offset namespace per topic-partition.

For example, topic **orders** has six partitions and the group ID is **billing-service**. If the service runs three consumers in the same group, Kafka can assign two partitions to each consumer. When scaled to six consumers, each consumer can receive one partition. If scaled to eight consumers, two consumers may receive no partitions because active consumers exceed available partitions.

~~~mermaid
flowchart TD
    T["Topic: orders (6 partitions)"] --> G["Consumer group: billing-service"]
    G --> C1["Consumer 1: P0, P1"]
    G --> C2["Consumer 2: P2, P3"]
    G --> C3["Consumer 3: P4, P5"]
~~~

A group ID ties three things together:

- **Membership**: which consumers participate in the same group and coordinate assignments.
- **Partition assignment**: how partitions are distributed among group members.
- **Offset state**: the group's committed position for each topic-partition.

A new consumer group has its own offset state, even when reading the same topic as an existing group. Kafka does not automatically treat two groups with the same code, application name, or database as one consumer group. Group identity is based strictly on the group ID string itself.

### 1.1 Same group ID means sharing load

Suppose two pods run listeners reading topic `orders` with group ID `billing-service`. They are two members of the same group. Kafka splits partitions between them; normally, each partition is assigned to at most one member in the group at a time.

As a result, each record in a partition is processed by one member of the group. The two pods are not two independent replicas each receiving every record. This is how a logical consumer service scales out.

If two different applications accidentally share the same group ID, they compete for partitions. One application may receive some partitions while the other receives the rest. Each application therefore sees only part of the stream. This is a common mistake when copying configuration from another service without changing the group ID.

### 1.2 Different group IDs mean two independent subscriptions

If two applications use different group IDs, Kafka treats them as two independent subscribers. Each group has its own assignments and offsets, so both can read all partitions of the topic.

Example:

- `billing-service` reads `orders` to update payments.
- `analytics-service` reads `orders` to build reports.

These two services normally need separate group IDs. If they shared one group, Kafka would divide partitions between them and each service would process only a subset of records, violating business intent.

~~~mermaid
flowchart TD
    T["Topic: orders"] --> G1["Group: billing-service"]
    T --> G2["Group: analytics-service"]
    G1 --> B1["Billing consumers"]
    G2 --> A1["Analytics consumers"]
    B1 --> DB1["Billing database"]
    A1 --> DB2["Analytics store"]
~~~

There is no single "correct group ID for a topic." A group ID must represent one logical subscription or processing stream sharing a common goal and offset progression.

## 2. What Happens When the group.id Changes?

Kafka stores offsets by group ID, topic, and partition. When the group ID changes, the new consumer does not automatically inherit offsets from the old group.

Suppose a service runs with group ID **orders-projection-v1**, having processed up to offset 500 on partition 0. A deployment changes the group ID to **orders-projection-v2**.

Kafka sees a new group. Because the new group lacks committed offsets from the old group, its starting behavior depends on **auto.offset.reset**.

| auto.offset.reset | Behavior when the new group has no valid offset |
|---|---|
| earliest | Starts from the earliest offset still retained in the partition |
| latest | Starts from the end of the log when the read position is established; existing backlog may be skipped |
| none | Throws an error if no valid offset is available to use |

This can lead to two drastically different outcomes:

- With **earliest**, the service may re-read many records already processed by the old group. Databases or downstreams may receive duplicates if logic is not idempotent.
- With **latest**, the service may start after an existing backlog. Records never processed by the new group may be skipped.
- With **none**, the consumer refuses to pick a starting position automatically and raises an error so operators decide the offset.

**auto.offset.reset does not reset existing offsets.** It applies only when the group has no valid committed offset for a partition or the stored offset is no longer valid—such as falling outside log retention. Therefore, changing group ID typically triggers reset behavior; changing `auto.offset.reset` alone on a group that already has valid offsets normally does not jump the group back to `earliest`/`latest`.

### 2.1 Old offsets do not move to the new group

The old group's offsets continue belonging to the old group. Changing the group ID configuration neither deletes nor migrates those offsets.

Old offsets may remain stored for a period according to Kafka's offset retention policy, yet they should not be treated as a permanent backup. Offset metadata can expire once a group stays inactive long enough or be deleted by administrative actions.

If the goal is renaming a group while resuming from the exact processing position, an explicit offset migration plan is required. You cannot just change the group ID string and expect Kafka to stitch progress together.

### 2.2 The new group can produce duplicate side effects

If the new group uses `earliest`, it can re-read records already processed by the old group. For example:

1. The old `billing-service` already recorded an invoice for order 1001.
2. A deployment changes the group ID.
3. The new group starts from `earliest`.
4. The order 1001 record is processed again.
5. The application records the invoice a second time unless protected by idempotency or a unique business key.

Kafka does not know two executions belong to the same business action. Consumers must use event IDs, order IDs, or idempotency keys to prevent duplicate side effects.

### 2.3 The new group can skip backlog

If the new group uses `latest`, it may set its starting position at the end of the log when no offset exists. Records waiting to be processed at that moment are not read by the new group.

This is an application-level processing gap even though the records remain in Kafka. Data was not deleted; the consumer simply began reading after it. Recovery is possible through controlled offset adjustment if the data is still within retention.

## 3. How group.id Changes Unintentionally

Unintended group ID changes usually stem from configurations assembled across multiple sources or from using an unstable value.

### 3.1 Using pod name, hostname, or UUID as group.id

Dangerous configuration example:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: ${HOSTNAME}
~~~

In Kubernetes, each pod normally has its own hostname. When every pod has its own group ID, Kafka creates a separate consumer group per pod. Instead of splitting partitions across replicas, each pod becomes an independent subscriber and may receive the entire stream.

Consequences can include:

- Every pod processes the same records and creates duplicate side effects.
- Consumer group counts climb with every scale or restart event.
- Each group tracks separate offsets, complicating lag observability and offset administration.
- Read load and downstream load multiply by pod count.
- New pods create brand-new groups that may replay from `earliest` or start at `latest`.

Never use instance-lifecycle-bound values as group ID: pod name, container ID, hostname, random UUID, timestamp, process ID, or deployment revision. Those values belong in `client.id` or observability metadata, depending on purpose.

### 3.2 Sharing the same group ID across environments

If development, staging, and production connect to the same Kafka cluster and share the same group ID, consumers across environments can compete for partitions. Production records might get processed by staging, or members from different environments can trigger continuous group rebalances.

Include the environment name in the group ID whenever multiple environments share a cluster, for example:

- `orders-projection-dev`
- `orders-projection-staging`
- `orders-projection-prod`

Even when each environment has its own Kafka cluster, keeping a clear naming convention helps make logs, dashboards, and runbooks readable while preventing accidents if environments ever share a cluster.

### 3.3 Embedding application version in group.id

Example:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: orders-projection-${APP_VERSION}
~~~

When `APP_VERSION` changes on every build or release, each version can create a new group. During a rolling deployment, old and new versions run concurrently under two different groups. Both groups read the full stream, duplicating side effects.

Normally, the group ID represents a logical subscription stable across application versions. Do not embed version, build number, Git SHA, or release timestamp in `group.id` if the goal is continuing existing offsets.

There are intentional migration cases requiring two groups in parallel, such as validating a new read model. In those cases, a version suffix can be useful, provided it is treated as an independent subscription with a replay plan, isolated target data, and clear sunset criteria.

### 3.4 Overridden placeholders or profiles

A configuration that looks stable can still change across environments:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: ${APP_KAFKA_GROUP:orders-projection}
~~~

The actual value depends on the `APP_KAFKA_GROUP` environment variable. If a ConfigMap, Secret, Helm values file, or CI pipeline sets a different value, the application will use a different group ID.

Spring Boot has many property sources. Profiles, environment variables, command-line arguments, system properties, and external config can all override values in `application.yml`. When investigating, inspect the effective runtime configuration rather than reading only one YAML file.

Relaxed-binding environment variables can override properties like:

~~~text
SPRING_KAFKA_CONSUMER_GROUP_ID
~~~

If a deployment template accidentally injects a release name, pod name, or namespace into this variable, the group ID can change on every deployment.

### 3.5 Annotation overriding ConsumerFactory

Spring Kafka allows setting group ID at the listener level. Thus, the global Spring Boot consumer group ID may not be the final value used by a listener.

Example:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "orders-projection"
)
public void handle(OrderCreated event) {
    // Process the event.
}
~~~

The **groupId** attribute on the listener overrides `group.id` inherited from the consumer factory for that listener. If `groupId` is hard-coded in the annotation, changing `application.yml` may not affect the listener as operators expect.

Also pay attention to **id** and **idIsGroup**:

- **id** identifies the listener container.
- By default, when no explicit `groupId` is given, Spring Kafka can use `id` as the group ID if `idIsGroup` is enabled.
- **groupId** explicitly specifies the group ID for the listener.
- Set **idIsGroup=false** when you want `id` to act strictly as a container ID and never be used as the group ID when `groupId` is omitted.

Example declaring both identifiers explicitly:

~~~java
@KafkaListener(
    id = "ordersProjectionListener",
    idIsGroup = false,
    groupId = "${app.kafka.consumer.group-id}",
    topics = "orders"
)
public void handle(OrderCreated event) {
    // Process the event.
}
~~~

Syntax and configuration options can depend on the Spring Kafka version. Check the annotation definition for your project's version. The key is never confusing container ID with group ID, and knowing exactly where the listener obtains its value.

### 3.6 Custom ConsumerFactory or container factories

An application can define multiple `ConsumerFactory` or `ConcurrentKafkaListenerContainerFactory` beans. Each factory can have its own group ID configuration. A listener using a custom factory may not pick up `spring.kafka.consumer.group-id`.

When a project has multiple listeners, map out:

- Which listener uses which factory.
- Which property supplies the factory's group ID.
- Whether the annotation defines its own `groupId`.
- Whether the listener relies on default `idIsGroup` behavior.
- Whether any bean post-processor or customizer mutates consumer properties.

Do not assume every listener in an application uses the same group simply because they live alongside one `application.yml`.

## 4. Stable group.id Naming Conventions

A good group ID expresses the logical consumer subscription, environment, and processing purpose. It should not depend on a specific instance.

A usable convention:

~~~text
<service>-<subscription>-<environment>
~~~

Examples:

~~~text
billing-service-orders-prod
orders-projection-prod
analytics-orders-staging
inventory-reservation-dev
~~~

You can choose another convention, provided it preserves these properties:

- Stable across restarts, scaling, and rolling deployments.
- Identical across replicas belonging to the same logical consumer group.
- Distinct across logical subscriptions needing the full stream independently.
- Distinct across environments if they share a Kafka cluster.
- Free of pod names, random values, build numbers, or versions unless part of an intentional migration.
- Centrally governed with clear ownership.

### 4.1 One group per logical subscription

Start with the question: "What single workload is this set of consumers collaborating to perform?"

For example, an e-commerce application might have:

| Logical subscription | Topic | Group id |
|---|---|---|
| Update order read model | orders | orders-projection-prod |
| Process payments | orders | billing-service-prod |
| Reserve inventory | orders | inventory-reservation-prod |
| Behavioral analytics | orders | analytics-orders-prod |

These groups read the same topic with independent offsets and assignments. Each logical subscription can scale its replicas independently.

### 4.2 Replicas must use the same group ID

If a service has four pods, all four pods must use the same group ID so Kafka distributes partitions among them.

~~~mermaid
flowchart TD
    T["Topic: orders"] --> G["Group: billing-service-prod"]
    G --> P1["Pod 1"]
    G --> P2["Pod 2"]
    G --> P3["Pod 3"]
    G --> P4["Pod 4"]
    P1 --> D["Shared billing database"]
    P2 --> D
    P3 --> D
    P4 --> D
~~~

Partition count limits parallelism within a group. If a topic has 8 partitions, running 20 consumers in the same group does not create 20 independent partition-processing streams. Surplus consumers stay idle. Never give each pod a distinct group ID just to keep every instance busy; that turns each pod into an independent subscriber and multiplies processing.

### 4.3 Distinguishing group.id from client.id and group.instance.id

Three commonly confused properties:

| Property | Purpose | Should it vary by instance? |
|---|---|---|
| group.id | Logical consumer group identity and offset namespace | No; replicas in the same group share it |
| client.id | Client identifier for observability, logs, metrics, and quotas | Yes, often includes service/pod name |
| group.instance.id | Specific member identity when static membership is enabled | Yes, unique and stable per member |

**client.id** does not replace `group.id`. Changing `client.id` does not create a new consumer group or a new offset namespace.

**group.instance.id** enables static membership in supported Kafka versions. It helps brokers recognize a stable member across brief restarts, cutting unnecessary rebalances. Every member in the same group must have a unique `group.instance.id`. If two consumers simultaneously use the same static member ID, one may be fenced or removed from the group.

Never set `group.instance.id` equal to `group.id` across all pods. Nor should you use `group.instance.id` as a workaround to give each pod its own group ID. They address two different identity layers.

## 5. Configuring group.id in Spring Boot and Spring Kafka

Pick one intentional configuration source per listener and avoid declaring conflicting values.

### 5.1 Default configuration via application.yml

For an application with a single primary logical consumer group, set the group ID in consumer properties:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: orders-projection-prod
      enable-auto-commit: false
      auto-offset-reset: earliest
~~~

Listeners using the default `ConsumerFactory` can inherit this group ID if annotations do not override it. This is straightforward when all listeners belong to one subscription or processing group.

If the application has multiple listeners with distinct purposes, do not force them into one group ID. Declare separate group IDs per listener or use corresponding factories.

### 5.2 Using a dedicated property per logical subscription

A cleaner approach is naming properties by application purpose:

~~~yaml
app:
  kafka:
    consumer:
      group-id: orders-projection-prod

spring:
  kafka:
    consumer:
      enable-auto-commit: false
      auto-offset-reset: earliest
~~~

The listener references the property:

~~~java
@KafkaListener(
    id = "ordersProjectionListener",
    idIsGroup = false,
    groupId = "${app.kafka.consumer.group-id}",
    topics = "orders"
)
public void handle(OrderCreated event) {
    projectionService.apply(event);
}
~~~

The benefit is managing the group ID by business purpose while the container `id` serves Spring Kafka's internal lifecycle and observability. With multiple listeners, define separate properties for each subscription.

### 5.3 Controlled per-environment overrides

Keep the same property structure while setting environment-specific values in profiles:

`application.yml`:

~~~yaml
app:
  kafka:
    consumer:
      group-id: orders-projection-dev
~~~

`application-prod.yml`:

~~~yaml
app:
  kafka:
    consumer:
      group-id: orders-projection-prod
~~~

Or inject via an environment variable:

~~~yaml
app:
  kafka:
    consumer:
      group-id: ${APP_KAFKA_GROUP_ID:orders-projection-dev}
~~~

The environment variable must hold a stable value for the logical subscription, such as **orders-projection-prod**. Never bind it to a pod name or build ID.

### 5.4 Configuration in Java

If building `ConsumerFactory` manually:

~~~java
@Bean
ConsumerFactory<String, OrderCreated> ordersConsumerFactory(
        @Value("${app.kafka.consumer.group-id}") String groupId) {

    Map<String, Object> props = new HashMap<>();
    props.put(
        ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
        "kafka-1:9092,kafka-2:9092,kafka-3:9092"
    );
    props.put(ConsumerConfig.GROUP_ID_CONFIG, groupId);
    props.put(
        ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class
    );
    props.put(
        ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
        JsonDeserializer.class
    );
    props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);

    return new DefaultKafkaConsumerFactory<>(props);
}
~~~

If the annotation specifies its own `groupId`, the annotation value can override the factory's group ID. Verify the final value on the listener container rather than inspecting the factory bean alone.

### 5.5 Avoiding multiple sources with unclear precedence

Common sources that can affect `group.id`:

- `application.yml` and `application-{profile}.yml`.
- Environment variables.
- Java system properties and command-line arguments.
- Helm values, ConfigMaps, or deployment manifests.
- Manually constructed `ConsumerFactory` beans.
- `@KafkaListener` annotations.
- Property placeholders or SpEL expressions.
- Customizers, bean post-processors, or internal libraries.

Establish a single authoritative place to manage the value for each logical subscription. If per-environment overrides are needed, document precedence rules and inspect runtime values. Never leave a YAML property and a literal `groupId` in an annotation coexisting unintentionally.

## 6. Designing group.id for Deployment Scenarios

### 6.1 Scaling replica count

When scaling from 2 to 5 pods, `group.id` must stay unchanged. Kafka rebalances partitions to redistribute them across the new members. Group offsets resume from committed positions.

Example:

- Before scaling: 2 pods, group `orders-projection-prod`.
- After scaling: 5 pods, still group `orders-projection-prod`.
- Kafka rebalances and redistributes partitions.
- Consumers continue reading from the group's offsets.

Scaling is not a reason to change `group.id`.

### 6.2 Rolling deployments

During a rolling deployment, old and new pod versions can run concurrently for a period. If both use the same group ID, they join the same group and share partitions. This is normally the desired behavior when the new version is compatible with the old version in payload, schema, and side effects.

If `group.id` is tied to version, both versions belong to different groups. Both may process the entire stream concurrently, causing business duplicates or two read models writing to the same target.

Use a separate group ID for the new version only during an intentional migration with isolated target storage or controlled side-effect handling.

### 6.3 Blue/green deployments

Blue/green may run two consumer fleets side by side. Clarify the intent:

- If blue and green are simply two alternating replica sets for the same subscription, use the same group ID and control when traffic/assignments shift.
- If green needs to read independently to validate data before cutover, use a separate group ID while preventing duplicate side effects and defining how outputs are compared.
- At cutover, decide where the new group's offsets will continue from and how any backlog is handled.

Do not let both groups write to the same business table for an extended period without idempotency or side-effect isolation.

### 6.4 Running multiple instances for tenants

Some systems create consumer groups per tenant. This can be valid when each tenant needs independent offsets and processing progress. However, dynamic group IDs must be governed:

- Naming rules must be stable and free of sensitive data.
- Group counts must be bounded or paired with cleanup mechanisms.
- Idle groups and offset retention must be monitored.
- Tenant creation/deletion lifecycles must tie into group lifecycles.
- Never create a new group per request or per restart.

If tenants are merely partition keys and can share processing progress, a single shared group may fit better. The choice depends on business isolation and scaling requirements.

### 6.5 Separating environments and clusters

When dev, staging, and production share a Kafka cluster, group IDs must differ so partitions are not split across environments. Even if environments have independent clusters—where the same group ID does not share offsets because offsets live inside each cluster—including the environment name still keeps operations unambiguous.

## 7. Intentional group.id Changes: Migration Procedure

Sometimes changing a group ID is genuinely necessary, such as renaming a subscription, splitting a service, or building a new consumer. Treat this as an offset migration, not a simple string swap.

### 7.1 Define the goal before changing

Three distinct goals exist:

1. **Rename while continuing from the current position**: migrate offsets from the old group to the new group or perform an equivalent step.
2. **Create an independent subscriber from scratch**: the new group maintains its own offsets and must decide whether to replay history or start with new data only.
3. **Replay data to rebuild a read model**: the new group typically starts from retained `earliest` or a chosen timestamp/offset; outputs must be isolated or safely overwritten.

Do not use the same procedure for all three cases.

### 7.2 Capture the old group's state

Before stopping the old group:

- Record the group ID, topics, partitions, and committed offsets.
- Record lag and log end offsets at snapshot time.
- Identify which partitions are assigned to consumers.
- Check retention to verify whether historical data is still readable.
- Confirm consumers have no in-flight work or uncommitted side effects remaining.

Use Kafka tools to inspect group state:

~~~bash
kafka-consumer-groups.sh   --bootstrap-server kafka.example:9092   --describe   --group orders-projection-prod
~~~

The `describe` command displays committed offsets, log end offsets, lag, and member info depending on Kafka version. Target the right cluster and group before taking action.

### 7.3 Choose the starting position for the new group

If renaming while continuing from the old position, transfer committed offsets per topic-partition. Use Kafka `AdminClient` or an appropriate admin tool to write offsets for the new group.

A committed offset represents the next position a consumer will read, not the last processed offset with arbitrary additions. When copying offsets, preserve exact committed-offset semantics and partition mappings.

If replaying, pick `earliest`, a timestamp, or specific offsets per plan. Verify the data remains within retention and confirm whether side effects can safely re-execute.

### 7.4 Stop consumers and execute migration

A careful procedure:

1. Freeze group ID configuration changes during the migration.
2. Stop the old consumer group or ensure it stops processing when offset tools require an inactive group.
3. Snapshot committed offsets and partition state.
4. Configure the new group ID.
5. Migrate offsets per partition if continuing from the old position.
6. Verify the new offsets were written accurately.
7. Start a single canary consumer with the new group.
8. Verify assignments, first records read, lag, and side effects.
9. Scale out replicas after the canary stabilizes.
10. Delete or decommission the old group only after the rollback window passes and zero consumers remain on it.

When using offset reset tools, inspect dry-run output carefully and execute only after verifying group, topic, and partitions. Never reset offsets on an active group without understanding rebalance behavior and tool preconditions.

### 7.5 Migration rollback

If the new group misbehaves, reverting to the old group can reprocess records because the old group has its own offsets stopped at an earlier position. Compare offsets between both groups, identify executed side effects, and rely on idempotency or reconciliation to avoid duplicates.

Do not delete the old group immediately after cutover. Keep the rollback runbook and offset snapshots until migration success is verified.

## 8. Observing group.id and Detecting Anomalous Changes

Group ID changes may not throw exceptions. Monitor group identities alongside lag and assignments.

### 8.1 Monitor the group inventory

Track consumer group counts per cluster and application namespace. A sudden spike in group count can indicate:

- Group IDs contain pod names or UUIDs.
- A new release spawned a new group ID.
- A profile or environment variable was overridden.
- A service restarted with altered configuration.
- A consumer migration created a group without a cleanup plan.

Not every new group is an error. Reconcile against the managed registry of subscriptions and group owners.

### 8.2 Monitor offsets and lag per group

Consumer lag must be viewed by group ID. When the group ID changes, existing dashboards may keep displaying the old group while the new group appears with empty offsets or different lag.

Monitor:

- Expected vs. actual group IDs.
- Member counts per group.
- Partition assignments.
- Committed offsets per topic-partition.
- Log end offsets and lag.
- Consumer restarts and rebalance counts.
- Processed record counts and side effects per business key.
- Groups with zero members that still hold offsets or lag.

Alert whenever a service creates an unlisted group ID or an active group ID changes across deployments without a migration ticket.

### 8.3 Log the group.id at startup

Explicitly log the effective group ID alongside service name, environment, and client ID at startup. Never log secrets or sensitive data on the same line.

Easy-to-investigate log example:

~~~text
service=orders-projection
environment=prod
consumerGroup=orders-projection-prod
clientId=orders-projection-pod-7f8c
topics=orders
~~~

During deployment, compare this output against expected configuration. If an annotation overrides the group ID, inspecting YAML files is insufficient; verify the effective consumer config built for the actual listener.

### 8.4 Inspect runtime configuration

When suspecting an unexpected group ID change:

1. Read resolved property values after Spring Boot loads profiles and external config.
2. Inspect `ConsumerFactory` properties.
3. Inspect `@KafkaListener` annotations, especially `groupId`, `id`, and `idIsGroup`.
4. Verify which factory the listener container uses.
5. Inspect consumer config logged at startup.
6. Use Kafka tools to list and describe groups on the target cluster.
7. Cross-check deployment revisions and pod environment variables.

Never edit YAML and assume the issue is resolved. If an annotation or factory overrides it, the runtime value will not change.

## 9. Misconfiguration Scenarios and Resolutions

| Scenario | Symptom | Cause | Resolution |
|---|---|---|---|
| Group ID contains pod name | Each pod has its own group; every pod processes the whole stream | Using `HOSTNAME` or pod UID as group ID | Use a shared stable group ID across replicas |
| Group ID contains version | A new group appears after every release | Embedding `APP_VERSION`/build number in group ID | Use a stable logical subscription ID; version only for intentional migrations |
| Two services share a group | Each service receives only a subset of partitions | Accidentally copied group ID | Split groups by logical subscription |
| Dev and prod share a group on one cluster | Cross-environment members, abnormal rebalances | Missing environment in group ID | Separate group IDs by environment |
| Annotation overrides YAML | Changing `application.yml` leaves runtime group unchanged | `@KafkaListener` sets `groupId` or `idIsGroup` | Inspect listener metadata and annotation settings |
| New group with `earliest` | Old records get reprocessed | New group has no committed offsets | Migrate offsets cleanly or prepare replay/idempotency |
| New group with `latest` | Existing backlog is not read | `auto.offset.reset=latest` | Set offsets per business requirement before starting |
| Multiple `ConsumerFactory` beans | One listener joins an unexpected group | Factory sets its own `group.id` | Map factories to listeners explicitly |
| Duplicate static member IDs | Members fenced or evicted from group | Multiple instances share `group.instance.id` | Issue a unique member ID per instance |

## 10. Anti-Patterns to Avoid and How to Fix Them

### 10.1 Do not use hostname as group.id

Unsuitable configuration:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: ${HOSTNAME}
~~~

More stable configuration:

~~~yaml
app:
  kafka:
    consumer:
      group-id: orders-projection-prod
~~~

Every `orders-projection` replica in production uses the same value. Pod identity can go into `client.id` if metrics need per-pod distinction.

### 10.2 Do not embed build version in group.id

Unsuitable configuration:

~~~yaml
app:
  kafka:
    consumer:
      group-id: orders-projection-${BUILD_NUMBER}
~~~

Stable configuration:

~~~yaml
app:
  kafka:
    consumer:
      group-id: orders-projection-prod
~~~

If a new consumer must run alongside for validation, create a distinct group ID with a clear migration name, isolated output, and an end date.

### 10.3 Explicitly declare listener id and groupId

Explicit configuration:

~~~java
@KafkaListener(
    id = "ordersProjectionContainer",
    idIsGroup = false,
    groupId = "${app.kafka.consumer.group-id}",
    topics = "${app.kafka.consumer.topic}"
)
public void handle(OrderCreated event) {
    projectionService.apply(event);
}
~~~

This separates container identity from consumer group identity. Ensure the placeholder resolves to the exact same value across every replica in an environment.

## 11. Misconceptions to Avoid

**"Each pod needs its own group ID so Kafka can tell consumers apart."** False. Kafka distinguishes members within a group via member identity; group ID must be identical across replicas intended to share partitions and offsets.

**"Changing group ID only changes the display name."** False. It creates a different consumer group with an independent offset state.

**"The new group automatically inherits old offsets."** False. Kafka never copies committed offsets between two group IDs automatically.

**"`auto.offset.reset=earliest` always reads the entire history."** False. `earliest` is only the earliest offset still readable in the log under retention/compaction; deleted records cannot be replayed from Kafka.

**"`auto.offset.reset=latest` jumps an existing group to the end."** False. It applies when a group lacks valid offsets, not to reset existing valid offsets.

**"`client.id` and `group.id` are interchangeable."** False. `client.id` identifies clients for metrics/logs; `group.id` governs membership and offsets.

**"Sharing a group ID across services saves resources."** False if services need the entire stream independently. They will split partitions and each service will receive only part of the data.

**"Putting versions in group ID makes deployments safe."** Not automatically. It creates a new subscription, which can cause both versions to process all data and generate duplicates.

**"Reading `application.yml` tells you the runtime group ID."** False. Environment variables, profiles, `ConsumerFactory`, and annotations can override the value.

## 12. Incident Response When Unexpected group.id Changes Are Detected

When dashboards show a new group or consumers start replaying/skipping records, respond in order:

1. Record the active group ID running in each pod and when the change began.
2. Determine whether pods belong to the same service, environment, and release.
3. Compare actual group IDs against application properties and deployment environment settings.
4. Check `@KafkaListener` `groupId`, `idIsGroup`, container `id`, and `ConsumerFactory`.
5. Use Kafka tools to describe both old and new groups: members, partitions, committed offsets, log end offsets, and lag.
6. Determine whether the new group used `earliest`, `latest`, or `none` when lacking offsets.
7. Audit executed side effects: which records were replayed, which may have been skipped, and which downstreams were affected.
8. If caused by misconfiguration, halt the rollout or fix the config source to restore the intended group ID.
9. If the new group already processed data, reconcile by event ID/business key before switching back to prevent duplicates.
10. Verify after recovery that only expected groups remain, assignments are healthy, and lag progresses normally.

Do not delete the new group immediately upon discovery. First determine which records it processed and how far its offsets advanced. Deleting groups or resetting offsets without snapshots destroys forensic evidence and increases replay risk.

## 13. Testing group.id Stability

Verify configuration in integration or staging environments:

- Start two replicas of the same service and verify they join the same group ID.
- Scale replicas up and down; verify the group ID stays unchanged and offsets continue advancing.
- Restart a pod; verify the new member rejoins the same group instead of creating a new one.
- Perform a rolling deployment; verify old and new versions join the expected group together.
- Switch profiles or test environment variables; verify the effective group ID matches the approved value.
- Create two logical subscriptions needing independent reads; verify they have distinct group IDs and each receives the full stream.
- Practice a group ID migration in staging; verify offsets transfer accurately or replay starts at the chosen point.
- Verify side-effect idempotency when a new group replays records.

Success criteria should be concrete: expected group count does not grow after restarts/scaling; every replica of the same subscription uses the same group; committed offsets keep advancing; no unallowed duplicate side effects occur; and new groups appear only alongside documented migrations.

## 14. Design and Operations Checklist

**Group identity**

- [ ] Every group ID represents an owned logical subscription.
- [ ] Replicas of the same subscription share the same group ID.
- [ ] Services needing independent reads use separate group IDs.
- [ ] Environments are separated when sharing a Kafka cluster.
- [ ] Group IDs contain no pod names, hostnames, UUIDs, timestamps, build numbers, or versions outside migration plans.

**Spring configuration**

- [ ] Primary source of group ID is clearly defined.
- [ ] `application.yml`/profiles/environment variables do not override unexpectedly.
- [ ] `@KafkaListener` `groupId` values are audited.
- [ ] `id` and `idIsGroup` behavior is understood for the Spring Kafka version.
- [ ] `ConsumerFactory` and listener container factories are explicitly mapped.
- [ ] Runtime group ID is logged at startup and checked against expected values.

**Offsets and migration**

- [ ] `auto.offset.reset` behavior is understood for groups without valid offsets.
- [ ] Changing group ID includes a per-partition offset migration or replay plan.
- [ ] Old offsets are snapshotted prior to migration.
- [ ] Old groups are retained long enough for rollback.
- [ ] Consumer side effects have idempotency or reconciliation for replays.

**Observability and testing**

- [ ] An allowlist of expected group IDs exists per service/environment.
- [ ] Group counts, members, assignments, committed offsets, and lag are monitored.
- [ ] Alerts fire when unexpected group IDs appear.
- [ ] Restarts, scaling, rolling deploys, and group migrations have been tested in staging.
- [ ] Runbooks exist for investigating replays, skipped backlogs, and duplicate side effects.

Group ID is part of a consumer's operational state because it governs membership, partition assignment, and the offset namespace. Keeping group IDs stable across restarts, scaling, and releases lets consumers resume smoothly from committed progress. Whenever a group ID must change, treat it as a data migration: define the read position, preserve offsets, control side effects, and validate the new group before shifting full load.

