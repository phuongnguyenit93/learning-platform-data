# Declaring NewTopic as a Bean

Kafka organizes data by topic. Before a producer sends records or a consumer reads records, the target topic must exist in the cluster, unless the cluster allows automatic topic creation according to broker configuration. In a Spring Kafka application, you can declare the desired topic as a `NewTopic` bean. Spring Kafka uses this bean together with `KafkaAdmin` to request the Kafka broker to create the topic when the application context starts.

Declaring topics as beans brings the topic structure into configuration that can be managed alongside the source code: topic name, partition count, replication factor, and certain topic-level configurations. It is especially useful when an application owns the topics that it publishes to or consumes from.

This lesson belongs to the **Topic Management** chapter of the **SPRING_KAFKA_MESSAGING** module. The module focuses on building event-driven applications using Spring Kafka, `KafkaTemplate`, and `@KafkaListener`, understanding topics, partitions, offsets, and consumer groups; while also laying the groundwork for serialization, retries, dead-letter handling, transactions, exactly-once semantics, concurrency, and testing.

## 1. The Role of the NewTopic Bean

A topic is a logical data stream in Kafka. A topic is divided into one or more partitions; each partition is its own ordered log. When designing a topic, the application needs to decide at least:

- The topic name following the system's naming convention.
- The number of partitions to meet parallel processing capacity and expected load.
- The replication factor to determine the number of copies of each partition.
- Storage policies such as time/size-based retention or log compaction.
- Topic-level configurations required for data durability and lifecycle.

Spring Kafka provides the `NewTopic` class to represent a topic creation request. When Spring Kafka detects `NewTopic` beans and has an active `KafkaAdmin`, `KafkaAdmin` sends requests to create topics that do not yet exist to the Kafka cluster.

General initialization flow:

~~~mermaid
flowchart TD
    A[Spring ApplicationContext starts] --> B[Detect NewTopic beans]
    B --> C[KafkaAdmin]
    C --> D[AdminClient connects to Kafka]
    D --> E{Topic already exists?}
    E -->|No| F[Send CreateTopics]
    E -->|Yes| G[Keep existing topic]
    F --> H[Broker creates topic]
    H --> I[Producer and consumer use topic]
    G --> I
~~~

A `NewTopic` bean is a declaration of the desired topic. It is not an active topic, nor is it a Kafka producer/consumer. The broker is the component that stores metadata and creates partitions/replicas.

## 2. KafkaAdmin Connects Bean Declarations with the Broker

`KafkaAdmin` is the Spring Kafka component that uses the Kafka Admin API to manage topics. It reads the Kafka connection configuration, finds `NewTopic` beans, and requests the broker to create topics when the application starts.

In Spring Boot, when Spring Kafka is configured via `spring.kafka.bootstrap-servers`, auto-configuration typically creates a `KafkaAdmin` to share the connection details. In that case, the application only needs to declare `NewTopic` beans:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
~~~

If you do not use Spring Boot auto-configuration or want a custom configuration, you can declare `KafkaAdmin` manually:

~~~java
@Configuration
public class KafkaAdminConfiguration {

    @Bean
    public KafkaAdmin kafkaAdmin() {
        Map<String, Object> configs = new HashMap<>();
        configs.put(
            AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
            "localhost:9092"
        );

        return new KafkaAdmin(configs);
    }
}
~~~

In the example, `KafkaAdmin` uses the bootstrap server to initialize an `AdminClient`. `AdminClient` is the Kafka administrative client, capable of creating topics and performing metadata/configuration operations according to granted ACL permissions.

You do not need to create a separate `AdminClient` for each `NewTopic` bean. `KafkaAdmin` manages topic initialization from the declarations discovered by Spring.

### 2.1. Distinguishing KafkaAdmin, AdminClient, and NewTopic

| Component | Role |
| --- | --- |
| `NewTopic` | Describes the desired topic name, partitions, replication factor, and topic configuration. |
| `KafkaAdmin` | Integrates the Spring lifecycle with the Kafka Admin API and processes `NewTopic` beans. |
| `AdminClient` | The Kafka client that executes administrative requests to the broker. |
| Kafka broker | Authenticates requests, creates topics, and stores cluster metadata. |

When dynamic administrative operations are needed at runtime, the application can use the `AdminClient` API directly or an administrative service layer wrapping it. `NewTopic` beans are suitable for topics whose structure is known before the application context starts.

## 3. Declaring a Simple NewTopic Bean

Example creating the `order-events` topic with six partitions and a replication factor of one:

~~~java
@Configuration
public class KafkaTopicConfiguration {

    @Bean
    public NewTopic orderEventsTopic() {
        return new NewTopic("order-events", 6, (short) 1);
    }
}
~~~

The constructor takes three parameters:

- Topic name: `order-events`.
- Number of partitions: `6`.
- Replication factor: `1`.

The replication factor parameter in the constructor has type `short`, so the example uses the cast `(short) 1`. A value of one is suitable for a local environment with only a single broker; it does not provide backup replicas if that broker fails.

In a multi-broker environment, the replication factor is usually chosen to be greater than one, depending on availability requirements and broker count. You cannot create a topic with a replication factor greater than the number of brokers available to store topic replicas.

### 3.1. Declaring with TopicBuilder

Spring Kafka provides `TopicBuilder` to express a topic using a fluent API, which is more readable when there are many properties:

~~~java
@Configuration
public class KafkaTopicConfiguration {

    @Bean
    public NewTopic orderEventsTopic() {
        return TopicBuilder.name("order-events")
            .partitions(6)
            .replicas(3)
            .build();
    }
}
~~~

This example creates a topic with six partitions and a replication factor of three. `TopicBuilder` lets you describe each property on its own line and easily add topic-level configurations.

Both using the `NewTopic` constructor and using `TopicBuilder` produce a `NewTopic` bean. Which approach to choose depends on the topic's complexity; for topics with many configurations, `TopicBuilder` is usually easier to read and maintain.

## 4. Topic-Level Configuration with TopicBuilder

In addition to partitions and replication factor, a topic can have configurations such as retention, cleanup policy, and segment size. `TopicBuilder` supports adding configurations using the `config(name, value)` method.

Example of a topic retaining events for seven days:

~~~java
@Bean
public NewTopic orderEventsTopic() {
    return TopicBuilder.name("order-events")
        .partitions(6)
        .replicas(3)
        .config(TopicConfig.RETENTION_MS_CONFIG, "604800000")
        .build();
}
~~~

`604800000` milliseconds equals seven days. This is an example retention policy; the actual retention period should be based on replay requirements, storage capacity, storage cost, and the system's data regulations.

Some common topic-level configurations:

| Configuration | Meaning |
| --- | --- |
| `retention.ms` | Duration to retain records by data age under the time-based retention mechanism. |
| `retention.bytes` | Maximum log size retained per partition under the applicable policy. |
| `cleanup.policy` | Data cleanup policy: `delete`, `compact`, or a combination depending on supported configuration. |
| `segment.bytes` | Target log segment size before rolling a new segment. |
| `min.insync.replicas` | Minimum number of replicas in the ISR required to accept writes when the producer uses `acks=all`. |
| `max.message.bytes` | Maximum record batch size accepted by the topic per broker/topic configuration. |

Configuration names are strings understood by the Kafka broker. You should use constants from `org.apache.kafka.common.config.TopicConfig` when corresponding constants exist to avoid typos.

Do not set retention or size values merely out of habit. An event topic needing 30-day replay may require a different retention than a topic storing the latest state by key. Configuration must reflect the intended use of the data.

## 5. Choosing the Right Partition Count

A partition is the unit of storage and parallel processing of a topic. A consumer group distributes partitions among consumers; within the same group, each partition at any given time is assigned to at most one active consumer.

The partition count directly affects consumer scalability. If a topic has six partitions, a consumer group can utilize up to six parallel reading threads at the partition level, provided the workload and infrastructure have sufficient capacity. Creating more consumers than partitions does not allow a single partition to be read concurrently by multiple consumers in the same group.

### 5.1. Factors to Consider

When choosing the number of partitions, consider:

- Expected producer throughput and record size.
- Processing throughput of each consumer.
- Maximum number of consumers intended to run concurrently in one group.
- Number of independent groups reading the topic concurrently.
- Per-key ordering requirements and key distribution uniformity.
- Broker resources allocated for partitions, file handles, metadata, and replication.
- Potential need to increase partitions in the future.

There is no single formula that fits every system. You can estimate from target throughput and the measured processing capacity of one consumer, then verify with benchmarks in a near-production environment.

### 5.2. Keys and Ordering Within a Partition

If a producer sends `orderId` as the key, events for the same order are typically routed to the same partition by the default partitioner. Consumers can read in the offset order of that partition.

However, Kafka only guarantees ordering within each individual partition, with no global ordering across all partitions. If the partition count is increased, the key-to-partition mapping can change; you must evaluate the impact on events with the same key and how the system handles old/new data.

Example topic with three partitions:

~~~text
order-events
  Partition 0: Order-A events, Order-D events, ...
  Partition 1: Order-B events, Order-E events, ...
  Partition 2: Order-C events, Order-F events, ...
~~~

This is an illustrative diagram, not how Kafka pins keys alphabetically. The actual partition is chosen by the partitioner and the current partition count.

## 6. Replication Factor and Data Durability

The replication factor determines the number of copies of each partition across different brokers. For example, a replication factor of three means each partition has one leader and two follower replicas according to cluster allocation state.

~~~text
Partition 0, replication factor = 3

Broker 1: Leader
Broker 2: Follower
Broker 3: Follower
~~~

The leader handles read/write requests according to the Kafka protocol; followers replicate data from the leader. If the leader fails, Kafka can elect an eligible replica as the new leader based on ISR state and cluster configuration.

A few points to remember:

- A replication factor of one has no backup replica.
- A replication factor of three requires enough brokers capable of hosting replicas and is commonly used when higher fault tolerance is needed.
- A higher replication factor increases storage cost and replication traffic.
- Replication factor does not replace producer acknowledgement configuration.
- `acks=all` combined with `min.insync.replicas` sets write acknowledgement conditions based on the number of synchronized replicas.

Topic configuration example:

~~~java
@Bean
public NewTopic paymentEventsTopic() {
    return TopicBuilder.name("payment-events")
        .partitions(6)
        .replicas(3)
        .config(TopicConfig.MIN_IN_SYNC_REPLICAS_CONFIG, "2")
        .build();
}
~~~

The example above requires the topic to have a replication factor of three and `min.insync.replicas` equal to two. A producer using `acks=all` may receive an error when the number of replicas in the ISR falls below this threshold, rather than accepting writes with a lower level of protection.

Do not use a replication factor of three in a cluster with only one broker. Kafka will not be able to create a topic with a replication factor exceeding the number of eligible brokers; choose a value matching the actual topology.

## 7. Log Retention and Cleanup Policy

Topics can serve different data purposes. An event topic typically needs to retain history for a period of time so consumers can replay it. A compacted topic typically represents the latest state per key.

### 7.1. Delete Policy

With the `delete` cleanup policy, Kafka deletes old segments when they exceed time-based or size-based retention thresholds. Records are not deleted immediately after consumers finish reading them; retention is managed independently of each consumer group's committed offsets.

Example configuring seven-day retention:

~~~java
@Bean
public NewTopic auditEventsTopic() {
    return TopicBuilder.name("audit-events")
        .partitions(6)
        .replicas(3)
        .config(TopicConfig.CLEANUP_POLICY_CONFIG, "delete")
        .config(TopicConfig.RETENTION_MS_CONFIG, "604800000")
        .build();
}
~~~

If a consumer stops operating for longer than the retention period, some older records may be deleted before the consumer returns. Therefore, retention needs to be greater than the downtime and replay window the system intends to support.

### 7.2. Compact Policy

With the `compact` cleanup policy, Kafka retains the latest value per key in the compacted log after compaction runs. This approach is useful for topics representing current state such as configurations, profiles, or account states by identifier.

~~~java
@Bean
public NewTopic accountStateTopic() {
    return TopicBuilder.name("account-state")
        .partitions(6)
        .replicas(3)
        .compact()
        .build();
}
~~~

Log compaction does not mean older records disappear immediately after a new record is written. Compaction runs in the background according to Kafka's mechanism; for some time, multiple versions of the same key may still coexist. Records with a null key are not treated like a regular key during compaction.

You can use the combined `compact,delete` cleanup policy if you need both compaction and a retention limit. Make sure to read the exact semantics of each policy before applying it to business data.

## 8. Declaring Multiple Topics Using Multiple Beans

An application can own multiple topics. Each topic is declared using its own `NewTopic` bean:

~~~java
@Configuration
public class KafkaTopicConfiguration {

    @Bean
    public NewTopic orderEventsTopic() {
        return TopicBuilder.name("order-events")
            .partitions(6)
            .replicas(3)
            .build();
    }

    @Bean
    public NewTopic paymentEventsTopic() {
        return TopicBuilder.name("payment-events")
            .partitions(3)
            .replicas(3)
            .build();
    }

    @Bean
    public NewTopic accountStateTopic() {
        return TopicBuilder.name("account-state")
            .partitions(6)
            .replicas(3)
            .compact()
            .build();
    }
}
~~~

`KafkaAdmin` detects `NewTopic` beans and sends requests to create topics that do not exist yet. Separating each topic into its own bean method keeps configuration readable, easy to review, and easy to associate with business owners.

The bean name does not have to match the topic name, though it should clearly describe its purpose such as `orderEventsTopic` or `paymentEventsTopic`. The topic name is the value passed into `TopicBuilder`; that is the name the broker will manage.

If an application connects to multiple Kafka clusters, ensure that `NewTopic` beans are processed by the `KafkaAdmin` connected to the correct cluster. Do not assume a `NewTopic` bean automatically knows which cluster it belongs to. With multiple `KafkaAdmin` instances, configure topic management explicitly per cluster and verify behavior against the Spring Kafka version in use.

## 9. Configuring NewTopic via Application Properties or Bean?

Some settings can be declared in application configuration, but `NewTopic` beans provide an explicit way to describe each topic in Java configuration.

| Criterion | NewTopic bean | Creating topics outside the application |
| --- | --- | --- |
| Where described | Spring configuration source code | Scripts, IaC, or operational procedures |
| Timing | When Spring context starts and `KafkaAdmin` initializes | Via pipeline/deployment or administrative action |
| Suitable for | Compact topics owned by the application | Production topics with dedicated governance and lifecycle |
| Change review | Can be reviewed alongside code changes | Reviewed in IaC repository or infrastructure workflow |
| Admin permissions | Application needs ACL to create topics | Pipeline/admin identity performs topic creation |

There is no single choice for every organization. In local environments or small applications, `NewTopic` beans let developers run the application without creating topics manually. In production with strict infrastructure governance, organizations may provision topics using Terraform, Ansible, Helm, or dedicated pipelines and restrict topic-creation permissions of the runtime application.

If topics are created externally, listeners/producers only need the right topic names and access permissions configured. `NewTopic` beans do not have to appear in every Spring Kafka application.

## 10. What Happens When a Topic Already Exists?

`NewTopic` beans are typically used to create missing topics. If a topic with the same name already exists, the `CreateTopics` request may return a `TopicExists` error for that topic; `KafkaAdmin` treats this situation as the topic already being created and does not automatically turn the bean into a general-purpose configuration update for the existing topic.

This has important implications when modifying code:

- Changing the partition count in a `NewTopic` bean is not a reliable way to decrease or adjust partitions of an existing topic.
- Changing the replication factor in the bean does not automatically reassign replicas of an existing topic.
- Changing retention or cleanup policy in the bean should not be treated as a mechanism to update an existing topic's configuration.
- You must use the Admin API or appropriate operational procedures to change an existing topic's configuration.

Kafka supports increasing the partition count via an administrative operation that adds partitions, but does not support decreasing a topic's partition count in a similar way. Increasing partitions can change key-to-partition mapping, so evaluate per-key event ordering before making the change.

For topic configuration, use the appropriate alter configuration operation and verify the state afterward. Do not simply edit values in the bean and assume the broker has applied them.

## 11. KafkaAdmin and Topic Creation Timing at Application Startup

Within the Spring context, `KafkaAdmin` initializes topics declared through `NewTopic` beans. This process depends on broker connectivity and the ACL permissions of the principal used by the application.

If the broker is not ready when the application starts, startup behavior depends on `KafkaAdmin` configuration and the Spring Kafka version. For systems requiring topics to exist before a service receives traffic, design a readiness/startup policy to prevent the application from being considered ready when topic creation fails.

Points to check:

- Whether `KafkaAdmin` is created and enabled in the application context.
- Whether bootstrap servers point to the intended cluster.
- Whether credentials have `Create` permission on the topic or cluster per ACLs.
- Whether the replication factor matches the number of brokers.
- Whether the topic name is valid and follows conventions.
- Whether the broker received the topic creation request.
- Whether the created topic has the expected partitions, replicas, and config.

Do not rely on broker auto-topic creation as a substitute for intentional topic management. If the broker auto-creates a topic when a producer sends to a non-existent name, the topic may be created with default partition/replication settings contrary to the application's needs.

## 12. Combining NewTopic with KafkaTemplate and @KafkaListener

Once a topic is created, producers and consumers can use that topic name. Example:

~~~java
@Configuration
public class KafkaTopicConfiguration {

    @Bean
    public NewTopic orderEventsTopic() {
        return TopicBuilder.name("order-events")
            .partitions(6)
            .replicas(3)
            .build();
    }
}
~~~

Producer:

~~~java
@Service
@RequiredArgsConstructor
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public CompletableFuture<SendResult<String, OrderCreated>> publish(
            OrderCreated event) {
        return kafkaTemplate.send(
            "order-events",
            event.orderId(),
            event
        );
    }
}
~~~

Consumer:

~~~java
@Component
public class OrderEventListener {

    @KafkaListener(
        topics = "order-events",
        groupId = "billing-service"
    )
    public void onOrderCreated(OrderCreated event) {
        billingService.startBilling(event);
    }
}
~~~

The `NewTopic` bean is solely responsible for describing the topic to be created. `KafkaTemplate` is responsible for sending records; `@KafkaListener` is managed by the listener container to receive records. These three components work together in the same messaging flow but have distinct responsibilities.

If the topic is pre-created by an infrastructure pipeline, you can omit the `NewTopic` bean and still use `KafkaTemplate` and `@KafkaListener` normally.

## 13. Verifying Topics After Application Startup

Do not merely observe that the application context started successfully and conclude that the topic was created properly. You must verify topic metadata from the Kafka cluster.

You can use the Kafka CLI:

~~~bash
kafka-topics.sh --bootstrap-server localhost:9092 --list
~~~

Inspect topic details:

~~~bash
kafka-topics.sh --bootstrap-server localhost:9092 --describe --topic order-events
~~~

The topic description output typically shows partitions, leader, replicas, and ISR. This is how you confirm the cluster has received the topic configuration.

You can use `AdminClient` in tests or administrative tools to read topic metadata and configurations. Example inspecting metadata with `AdminClient`:

~~~java
try (AdminClient admin = AdminClient.create(Map.of(
        AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
        "localhost:9092"
))) {
    TopicDescription description = admin.describeTopics(
        List.of("order-events")
    ).allTopicNames().get(10, TimeUnit.SECONDS).get("order-events");

    assertThat(description.partitions()).hasSize(6);
}
~~~

This snippet illustrates how to read metadata; real tests require a running broker and handling for timeouts or missing topics. Checking the partition count can be done via `TopicDescription`; checking topic configuration requires using the appropriate `describeConfigs` API.

## 14. Testing NewTopic Beans

An integration test should verify:

1. The application context creates `KafkaAdmin` and the `NewTopic` beans.
2. The Kafka cluster receives the topic creation request.
3. The topic appears in metadata.
4. The partition count and replication factor match the configuration.
5. Important topic-level configurations are applied.
6. The producer can send records to the topic and the consumer can read records if the test covers an end-to-end flow.

You can use Embedded Kafka or Testcontainers to test against a real broker. Choose a replication factor matching the number of test brokers: a single broker can only create topics with a replication factor of one. If a test configures three replicas on a single broker, topic creation will fail due to insufficient eligible brokers.

For example, a test checking the topic with `AdminClient` can run after the application context initializes and `KafkaAdmin` has created the topic. Avoid fixed sleeps if you can wait using the metadata API with an explicit timeout.

## 15. Common Errors When Declaring NewTopic

| Symptom | Possible Cause | Troubleshooting Direction |
| --- | --- | --- |
| Topic does not appear after startup | `KafkaAdmin` not created, broker unreachable, or `NewTopic` bean not detected | Check application context, bootstrap servers, and `KafkaAdmin` logs |
| Topic creation rejected | ACL missing `Create` permission or invalid topic name | Check principal, ACLs, and topic name |
| Replication factor unavailable | Requested replicas exceed eligible brokers | Check broker count and set appropriate replicas |
| Topic has fewer partitions than expected | Topic already existed with a different configuration | Describe the topic; add partitions via Admin API if needed |
| Retention does not change | Topic already exists and `NewTopic` bean is not an alter config mechanism | Use `describeConfigs` and the appropriate `alterConfigs`/`alterConfigs` API |
| Application starts but producer throws `UnknownTopicOrPartition` | Topic not yet created or producer connects to a different cluster | Check cluster, topic metadata, and initialization timing |
| Works locally but production does not create topics | Production ACL or policy blocks runtime topic creation | Check service account permissions and provisioning workflow |
| Increasing partitions alters per-key ordering | Key-to-partition mapping changes when topology changes | Evaluate partitioning strategy and handling of transitional data |

## 16. NewTopic Bean Design Checklist

Before declaring a topic for a service, answer:

1. Which business domain does the topic belong to, and which service is responsible for it?
2. Does the topic name follow naming conventions and distinguish environments/versions if needed?
3. How is the partition count derived from throughput, consumer concurrency, and broker capacity?
4. Does the replication factor match the broker count and availability requirements?
5. Does the producer use `acks=all` and an appropriate `min.insync.replicas` when high durability is needed?
6. How long must data be retained; should `delete` or `compact` be used?
7. Are limits on message size, segment size, or other topic-level configurations needed?
8. Is the topic pre-created by an infrastructure pipeline, or will the application create it via `KafkaAdmin`?
9. Does the runtime application have permission to create topics in production?
10. Are metadata/configs verified after creation, and is there a procedure for modifying existing topics?

`NewTopic` beans bring topic structure into Spring configuration clearly so it can be reviewed alongside source code. When combined properly with `KafkaAdmin`, they allow development and test environments to create required topics automatically. In operations, you must clearly understand the boundary between declaring new topics and modifying existing ones, and choose partitions, replication, and retention based on the actual needs of the data stream.

