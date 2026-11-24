# KafkaAdmin and Kafka Resource Management

In Spring Kafka architecture, an application does not only send and receive records. It also needs appropriate Kafka resources for event streams to operate: topics, partitions, replication, retention, cleanup policies, and access permissions. **KafkaAdmin** is the Spring Kafka component that helps declare and create topics from application configuration; **AdminClient** is Apache Kafka's administrative API for performing more granular administrative operations.

This lesson places KafkaAdmin in its proper role within the **SPRING_KAFKA_MESSAGING** module: supporting applications that send and receive events with KafkaTemplate and @KafkaListener, while managing topics and configurations so messaging flows can scale, recover, and run reliably. Examples focus on topics because those are the resources Spring Kafka applications most frequently need to declare directly.

## Desired Outcomes

After this lesson, you will be able to:

- Explain KafkaAdmin, the KafkaAdmin bean, NewTopic, TopicBuilder, and their relationship with AdminClient.
- Declare topics via Spring configuration and understand when topics are created.
- Choose partition counts, replication factors, and topic configurations based on processing requirements.
- Distinguish between creating new topics and modifying configurations of existing topics.
- Use AdminClient to list, describe, and manage topics in an administrative task.
- Design resource management strategies that differ across local, test, staging, and production environments.
- Test topic creation, handling existing topics, and detecting misconfigurations.
- Operate topics safely via ACLs, monitoring, change workflows, and data lifecycle policies.

## 1. Why Does an Application Need to Manage Kafka Resources?

Kafka stores records in topics. Producers send records to topics; consumer groups read topic partitions by offset. If a topic does not exist yet, has too few partitions, lacks appropriate replication, or has wrong retention settings, the application may fail to meet requirements for load, ordering, durability, and storage.

Common scenarios:

- A new event stream such as orders.created needs a dedicated topic shared by producers and consumer groups.
- Consumers need more partitions for parallel processing, yet the existing topic only has a single partition.
- Events must be retained for seven days to support reprocessing and incident investigation.
- A topic holding the latest state by key needs a compaction cleanup policy.
- Production environments need replication and min.insync.replicas to improve fault tolerance.
- An application needs to inspect an existing topic and detect when actual configuration diverges from desired configuration.

The components can be visualized as follows:

~~~mermaid
flowchart TD
    APP[Spring Boot application] --> KA[KafkaAdmin]
    CONF[NewTopic beans] --> KA
    KA --> AC[Kafka Admin API]
    AC --> CL[Kafka cluster]
    CL --> TOPIC[Topics and partitions]
    PRODUCER[KafkaTemplate] --> TOPIC
    TOPIC --> CONSUMER["@KafkaListener"]
    OPS[AdminClient / Operations job] --> AC
~~~

KafkaAdmin manages topics declared in the Spring context. KafkaTemplate and @KafkaListener use those topics to exchange records. AdminClient provides fine-grained administrative operations when applications or operational workflows need to query or modify resources on demand. In production, proactively provision topics to avoid auto-created topics with unsuitable default partition counts and settings when brokers allow auto-creation.

Remember that KafkaAdmin is neither a Kafka broker nor a record store. It sends administrative requests to the cluster through the Kafka Admin API.

## 2. Distinguishing KafkaAdmin and AdminClient

These two components are related but serve two different kinds of tasks.

| Component | Role | Typical usage |
|---|---|---|
| KafkaAdmin | Integrates topic administration into the Spring application context | Declare NewTopic beans so topics are created during application startup. |
| AdminClient | Low-level administrative API of Apache Kafka | List, describe, create, and delete topics; read or modify configs and perform broker-supported administrative actions. |
| KafkaTemplate | Sends records to topics | Producers emit OrderCreatedEvent or other business events. |
| @KafkaListener | Receives records from topics | Consumers process events by consumer group. |

With Spring Boot and the spring-kafka dependency, Spring Boot typically configures KafkaAdmin based on the application's Kafka properties. When the application declares NewTopic beans, KafkaAdmin uses those beans to send topic creation requests to the cluster.

If a dynamic administrative task is required—such as auditing a list of managed topics or creating a topic for an approved request—AdminClient allows calling administrative APIs directly. Do not create a new AdminClient for every business request; this client needs lifecycle management, proper closing, and is usually used as a shared component in administrative tasks.

## 3. Configuring Administrative Connections

KafkaAdmin needs bootstrap server addresses and necessary security details to connect to the cluster. In Spring Boot, basic configuration typically resides in application.yml:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
~~~

When using Spring Boot auto-configuration, the bootstrap-servers property configures Kafka components, including KafkaAdmin. If the application needs separate settings for the admin connection, you can declare a KafkaAdmin bean with its own configuration map.

Manual configuration example:

~~~java
@Configuration
public class KafkaAdminConfiguration {

    @Bean
    KafkaAdmin kafkaAdmin() {
        Map<String, Object> configs = new HashMap<>();
        configs.put(
                AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
                "localhost:9092"
        );
        return new KafkaAdmin(configs);
    }
}
~~~

The code above illustrates creating KafkaAdmin when an application needs to manage admin configuration itself. In a Spring Boot application that already has an auto-configured KafkaAdmin, avoid declaring duplicate beans unless there is a clear need to replace or customize it.

For clusters secured with SASL or TLS, the admin client also needs security protocol, authentication mechanism, truststore, and related infrastructure properties. Administrative permissions must be granted via ACLs or the corresponding authorization mechanism. An application that only sends and receives records generally does not need full cluster admin privileges.

Configuration principles:

- Use environment variables or a secret manager for credentials; do not commit passwords or private keys to the repository.
- Separate configurations by environment and avoid using local broker addresses in production.
- Grant only the necessary permissions to the topic administration account.
- Set reasonable timeouts for administrative operations and handle connection failures.
- Explicitly decide whether the application is allowed to continue starting when the broker is temporarily unavailable.

## 4. Declaring Topics with NewTopic and TopicBuilder

The most common way to integrate topic creation with Spring Kafka is to declare a NewTopic bean. NewTopic models the desired topic; TopicBuilder makes constructing this model easier to read.

Example of an order events topic:

~~~java
@Configuration
public class KafkaTopicConfiguration {

    @Bean
    NewTopic ordersCreatedTopic() {
        return TopicBuilder.name("orders.created")
                .partitions(6)
                .replicas(3)
                .build();
    }
}
~~~

When the Spring context initializes, KafkaAdmin detects the NewTopic bean and asks Kafka to create the topic if it does not yet exist. With the configuration above, the topic has six partitions and a replication factor of three. The cluster must have enough suitable brokers to satisfy the replication factor.

For Kafka running on a local machine with only one broker, use replicas(1). Do not configure three replicas on a single-broker cluster because the broker cannot fulfill that requirement.

Additional topic properties can be configured:

~~~java
@Bean
NewTopic ordersCreatedTopic() {
    return TopicBuilder.name("orders.created")
            .partitions(6)
            .replicas(3)
            .config(TopicConfig.RETENTION_MS_CONFIG, "604800000")
            .config(TopicConfig.MIN_IN_SYNC_REPLICAS_CONFIG, "2")
            .build();
}
~~~

This is another configuration example for the orders.created topic, illustrating a seven-day retention period and min.insync.replicas of two; within a single configuration class, define one bean per topic. This example targets a cluster with replication factor three and producers using suitable acknowledgements, such as acks=all. Actual values should be based on acceptable data loss requirements, broker count, storage capacity, and record throughput.

TopicBuilder also supports declaring a compaction cleanup policy:

~~~java
@Bean
NewTopic customerStateTopic() {
    return TopicBuilder.name("customer.state")
            .partitions(6)
            .replicas(3)
            .compact()
            .build();
}
~~~

Compaction retains the latest value per key in the log via Kafka's asynchronous compaction mechanism; older records do not necessarily disappear immediately when new records are written. It fits topics representing current state by key, such as configuration state or customer state. Producers need to send stable keys; records with null values can be used as tombstones to mark keys for deletion according to compaction rules and the configured tombstone retention time.

Common topic configurations:

| Configuration | Purpose | Considerations |
|---|---|---|
| retention.ms | Duration to retain records under retention policy | Align with storage, replay needs, and capacity. |
| retention.bytes | Log size limit per partition | Account for total storage across all partitions and replicas. |
| cleanup.policy | Selects delete, compact, or combined depending on broker version/config | Compaction requires suitable keys and data models. |
| min.insync.replicas | Minimum replicas that must be in ISR to satisfy writes with acks=all | Must be compatible with replication factor and availability goals. |
| segment.bytes | Log segment size | Affects segment management and retention behavior. |
| max.message.bytes | Maximum record batch size accepted by the topic | Must match producer, broker, and consumer limits. |

Do not add every property to every topic out of habit. Determine data requirements, recovery needs, and storage costs before choosing configurations.

## 5. Choosing Partitions and Replication Factor

Partitions and replication factor determine many critical properties of a topic.

**Partitions** split a topic into independent logs, enabling parallel processing. A consumer group can have at most as many actively assigned consumers as the topic's partition count. If a topic has six partitions, the group cannot effectively use ten consumers simultaneously to read only that topic.

Partition count should be chosen based on:

- Expected record traffic and processing speed per consumer.
- Required concurrency of consumer groups.
- Key-based ordering requirements.
- Overhead of managing partitions, log files, metadata, and broker resources.
- Future traffic growth plans.

Do not pick too few partitions and limit scalability, but also do not create excessive partitions without need. Every partition adds overhead for brokers, controllers, consumers, and monitoring systems.

**Replication factor** is the number of copies of each partition across brokers. Replication lets a topic remain available when a broker fails, within the limits of surviving replicas and ISR policies.

Example of a three-broker cluster and a topic with replication factor three:

~~~mermaid
flowchart LR
    P0[Partition 0] --> B1[Broker 1: Leader]
    P0 --> B2[Broker 2: Follower]
    P0 --> B3[Broker 3: Follower]
~~~

In practice, different partitions distribute leaders and replicas differently to balance load. Kafka manages the ISR (in-sync replicas), the set of replicas keeping up with the leader according to cluster conditions.

Combining replication factor three, min.insync.replicas two, and producer acks=all means a write is acknowledged only when the required ISR conditions are met. If ISR drops below the threshold, the producer may receive an error instead of writing with weaker durability. This is a trade-off between write availability and data durability.

An important note: increasing the partition count of an existing topic cannot be undone by reducing partitions. Increasing partitions can also change key routing under the default partitioner, because partitioning math depends on partition count. If ordering of events sharing a key is a business requirement, plan partition changes carefully.

## 6. Topic Lifecycle During Spring Application Startup

A typical initialization flow:

1. Spring Boot reads Kafka configuration and creates required beans.
2. Configuration classes declare NewTopic beans.
3. KafkaAdmin discovers declared topics.
4. KafkaAdmin connects to the broker via the Admin API and sends topic creation requests.
5. The Kafka broker validates topic names, partitions, replication, and configuration.
6. Topics become ready for producers and consumers once the broker finishes the operation.

~~~mermaid
sequenceDiagram
    participant App as Spring Application
    participant KA as KafkaAdmin
    participant Broker as Kafka Broker
    participant Producer as KafkaTemplate
    participant Consumer as Listener Container
    App->>KA: Initialize context and NewTopic beans
    KA->>Broker: CreateTopics
    Broker-->>KA: Topic creation result
    KA-->>App: Admin initialization complete
    Producer->>Broker: Send record
    Broker-->>Producer: Send result
    Consumer->>Broker: Poll records
    Broker-->>Consumer: Records
~~~

Creating topics at startup keeps resource definitions next to application configuration. This is convenient locally, in integration tests, and in small services with clear topic ownership.

However, behavior when the broker is unavailable must be designed. An application might need to fail fast if it cannot run without Kafka; another application might need to start up to serve non-Kafka features and reconnect later. Spring Kafka provides options to configure KafkaAdmin behavior when brokers are unavailable, such as fatalIfBrokerNotAvailable. Choose behavior based on service startup and readiness requirements.

Do not assume that merely because the context started, all topics were created exactly as intended. Log administrative results, inspect topics in the target environment, and align health/readiness checks with application architecture.

## 7. Existing Topics and Configuration Changes

Creating a new topic and modifying an existing topic are two distinct situations.

When a topic does not exist yet, KafkaAdmin can create it from the NewTopic bean. When a topic already exists, the application should verify actual configuration and decide whether changes are permitted. Specific KafkaAdmin behavior regarding partitions and topic configs depends on the Spring Kafka version and enabled administrative options.

Principles to remember:

- Kafka does not support decreasing the partition count of an existing topic.
- Increasing partitions must be treated as an architectural change since it can affect key-based partitioning.
- Topic configs can be altered via the Admin API if broker and permissions allow.
- Changing retention or cleanup policy can alter how data is retained and deleted.
- Changing replication factor typically involves replica allocation and reassignment procedures, not merely changing a number in a bean.
- Do not let multiple applications independently manage the configuration of the same topic without clear ownership.

In Spring Kafka, KafkaAdmin provides options controlling whether existing topic configs are modified. Before enabling config modification behavior, read the documentation for your exact version and understand precisely which properties will change. Unexpected changes can affect consumer groups or storage retention policies.

Treat topic changes like migrations:

1. Record the current configuration of the topic.
2. Define the target configuration and rationale for the change.
3. Assess impact on partitions, key ordering, retention, replication, and consumers.
4. Test on staging with representative data.
5. Apply changes using an account with appropriate permissions.
6. Re-read configuration after changes and monitor metrics.
7. Update operational documentation and ownership records.

## 8. Using AdminClient for Active Administrative Tasks

When operations are needed outside the Spring context lifecycle, AdminClient can be used. AdminClient is Apache Kafka's API; it supports listing topics, describing topics, creating or deleting topics, and reading and modifying configurations subject to permissions and broker version.

Example administrative task that creates a topic and reads its description:

~~~java
public void ensureAuditTopic(
        String bootstrapServers) throws Exception {

    Map<String, Object> configs = new HashMap<>();
    configs.put(
            AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
            bootstrapServers
    );

    NewTopic topic = new NewTopic(
            "audit.events",
            3,
            (short) 1
    );

    try (AdminClient admin = AdminClient.create(configs)) {
        admin.createTopics(List.of(topic))
                .all()
                .get(10, TimeUnit.SECONDS);

        Map<String, TopicDescription> descriptions =
                admin.describeTopics(List.of("audit.events"))
                        .all()
                        .get(10, TimeUnit.SECONDS);

        TopicDescription description =
                descriptions.get("audit.events");

        System.out.println(
                "Topic=" + description.name()
                + ", partitions=" + description.partitions().size()
        );
    }
}
~~~

This example is suitable for illustrating a standalone task. In a real application, handle cases where the topic already exists, timeouts, authentication failures, and broker errors separately. Do not treat TopicExistsException as a fatal error if the goal is ensuring the topic is present; inspect the current state and verify its configuration.

AdminClient returns results asynchronously via KafkaFuture. Calling get with a timeout gives administrative tasks a bounded wait. If an operation runs inside a long-lived workflow, record errors, bound retries, and avoid repeating non-idempotent modifications.

Common AdminClient operations:

| Need | API group |
|---|---|
| List topics | listTopics |
| Read partitions, leaders, replicas, and ISR | describeTopics |
| Create topics | createTopics |
| Delete topics | deleteTopics |
| Read topic or broker configs | describeConfigs |
| Modify configs | alterConfigs or incrementalAlterConfigs depending on API and version |
| Increase partition count | createPartitions |
| Manage ACLs | describeAcls, createAcls, deleteAcls |
| Monitor consumer groups | describeConsumerGroups, listConsumerGroups |

API names and data types may change across Kafka client versions. When writing code, use the exact kafka-clients version managed by Spring Boot dependency management and consult the corresponding documentation.

Deleting a topic is an operation that can cause data loss and disrupt active producers and consumers. Only execute it through a controlled administrative process after confirming the exact environment, topic name, and ownership.

## 9. Managing Topics by Environment

A topic may require different settings across local, test, staging, and production. For instance, local uses a single broker, few partitions, and one replica; production uses multiple brokers, more partitions, higher replication factor, and retention sized to real storage capacity.

Spring profiles or environment variables can separate configuration. Example:

~~~yaml
spring:
  config:
    activate:
      on-profile: local

  kafka:
    bootstrap-servers: localhost:9092
~~~

The example only shows selecting a profile for local configuration. In real projects, partition, replica, and retention values can be placed in dedicated properties or supplied by deployment infrastructure. Do not replicate production configuration verbatim into local if the local environment lacks enough brokers.

A common organization pattern:

| Environment | Partitions | Replication | Goal |
|---|---:|---:|---|
| Local | 1-3 | 1 | Fast development, easy environment setup. |
| Integration test | Per test scenario | 1 or per test broker | Verify producer, consumer, and admin behavior. |
| Staging | Near production | Near production | Validate configuration and load prior to release. |
| Production | By load and parallelism | By availability needs | Stable operations with fault recovery. |

Numbers in the table are directional guidelines, not universal defaults for every system.

For larger systems, manage topics via dedicated infrastructure pipelines or migrations. Business applications may only need read/write permissions; a deployment job or dedicated admin account handles creating and updating topics. This avoids having multiple service replicas concurrently attempt unnecessary administrative changes.

## 10. Permissions and Security When Managing Resources

Topic administration requires higher privileges than sending and receiving records. In ACL-enabled clusters, operations may require CREATE, DESCRIBE, ALTER, or DELETE permissions depending on the task. Consumer and producer accounts should only hold permissions needed on relevant topics and consumer groups.

Separate roles clearly:

- **Producer applications:** write permission to assigned topics.
- **Consumer applications:** read permission on topics and access to corresponding consumer groups.
- **Administrative tasks:** permission to create or alter topics within approved scope.
- **Monitoring tasks:** permission to read required metadata and metrics.

Do not grant cluster-wide admin privileges to every service just so KafkaAdmin can create topics at startup. Provisioning can be separated from runtime services, or permissions can be scoped per environment and ownership.

With SASL/TLS, protect credentials, restrict secret read access, rotate credentials, and inspect logs to avoid printing passwords or sensitive payloads. When running AdminClient inside an application, ensure the client uses the security configuration of the target cluster.

## 11. Testing KafkaAdmin and Topic Resources

Topic administration tests should verify real broker behavior, not merely check that a NewTopic bean exists in the Spring context.

Test layers can include:

| Test type | What to verify |
|---|---|
| Config unit tests | Topic name, partition count, replication factor, and configs are properly declared. |
| Integration tests | KafkaAdmin successfully creates the topic on a test broker. |
| Existing-topic tests | Restarting the application does not break an existing topic. |
| AdminClient tests | Can describe topics and read partitions/replicas/ISR. |
| Permission tests | Accounts lacking permission receive expected errors; authorized accounts succeed. |
| Failure tests | Broker unavailability or timeouts are handled per policy. |

EmbeddedKafka or Testcontainers can run a broker in tests. Testcontainers is helpful when you need an environment closer to an actual Kafka broker. When using EmbeddedKafka, isolate test topics and consumer groups between tests so results do not depend on execution order.

An example test verifying a topic was created using AdminClient:

~~~java
@Test
void shouldCreateOrdersTopic() throws Exception {
    try (AdminClient admin = AdminClient.create(adminConfigs)) {
        Set<String> topics = admin.listTopics()
                .names()
                .get(10, TimeUnit.SECONDS);

        assertThat(topics).contains("orders.created");

        Map<String, TopicDescription> descriptions =
                admin.describeTopics(List.of("orders.created"))
                        .all()
                        .get(10, TimeUnit.SECONDS);

        assertThat(
                descriptions.get("orders.created").partitions()
        ).hasSize(6);
    }
}
~~~

This is an illustrative example; adminConfigs and the broker must be supplied by the test context. If tests run in parallel, use unique topic names or appropriate resource isolation mechanisms.

Do not let tests automatically delete shared topics or topics holding persistent data. Each test needs an explicit resource creation and cleanup strategy.

## 12. Monitoring and Troubleshooting Administration Issues

After topics are created, cluster and resource health must still be monitored. Indicators to watch:

- Number of topics and partitions per broker.
- Offline partitions and under-replicated partitions.
- Number of replicas in ISR and ISR shrink events.
- Leader distribution and load across brokers.
- Log size, data growth rate, and disk utilization.
- AdminClient error rates or timeouts.
- Consumer lag across groups using the topic.
- Retention and compaction status relative to data goals.

Common troubleshooting scenarios:

| Symptom | Possible cause | Investigation steps |
|---|---|---|
| Cannot create topic | Broker unreachable, missing CREATE permission, replication factor exceeds broker count | Check connectivity, ACLs, broker count, and Admin API errors. |
| Topic exists with different config | Topic created earlier or modified outside the application | Describe topic and actual config; compare against target config. |
| Producer receives NotEnoughReplicas | ISR below min.insync.replicas when using strict acks | Check brokers, replica lag, and ISR. |
| Consumer lacks expected parallelism | Fewer partitions than consumers or unexpected partition assignment | Check partition count, consumer group, and rebalances. |
| Storage grows rapidly | Long retention, rising traffic, high replication, or compaction falling behind | Check log sizes, retention, segments, and disk. |
| Config changes do not take effect | KafkaAdmin not configured to alter existing configs or change unsupported by broker | Check versions, modify options, and Admin API responses. |

When troubleshooting, retrieve actual state from the broker. Do not assume a topic has the right configuration merely because the source code contains a NewTopic bean.

## 13. Comprehensive Exercise: Managing Topics for an Order System

Build a topic configuration for an order event flow consisting of:

- orders.created: newly created order event.
- inventory.reserved: inventory reservation outcome.
- payment.authorized: payment authorization outcome.
- orders.failed: business event requiring follow-up or reconciliation.

Practice requirements:

1. Declare NewTopic beans for the topics using TopicBuilder.
2. Choose partition counts and replication factors for local and production environments.
3. Configure retention for event topics; explain why retention must align with replay windows and storage capacity.
4. Experiment with compact cleanup policy for a keyed state topic and compare it with delete.
5. Restart the application to verify how KafkaAdmin handles existing topics.
6. Use AdminClient to read topic descriptions, partitions, replicas, and ISR.
7. Simulate a missing administrative permission scenario to observe ACL errors.
8. Write an integration test verifying the topic exists with the expected partition count.
9. Document a procedure for changing partitions or retention without unexpected disruption.
10. Connect KafkaTemplate and @KafkaListener to the topics to verify the complete event flow.

Upon completion, produce a resource inventory listing topic name, owner, producer, consumer group, key, partition count, replication factor, retention, cleanup policy, and operational contact.

## 14. Learning Sequence and Completion Criteria

| Stage | Content | Self-check criteria |
|---|---|---|
| 1. Admin roles | KafkaAdmin and AdminClient | Can explain the difference between declarative startup management and active administration. |
| 2. Connection setup | bootstrap servers, security, ACLs | KafkaAdmin connects to the right cluster using appropriate credentials. |
| 3. Topic declaration | NewTopic, TopicBuilder | Application creates topics according to configuration. |
| 4. Resource design | partitions, replication, retention, compaction | Can explain the impact of each property on load and data durability. |
| 5. Topic lifecycle | create, describe, alter, delete | Can distinguish creating, inspecting, and altering existing topics. |
| 6. Automation | profiles, migrations, ownership | Each environment has clear configuration and controlled changes. |
| 7. Testing | EmbeddedKafka, Testcontainers, AdminClient | Tests cover new topics, existing topics, and admin failures. |
| 8. Operations | ACLs, metrics, ISR, disk, consumer lag | Can inspect topic health and diagnose common issues. |

The lesson is complete when you can declare topics with KafkaAdmin, explain how topics are created in the Spring lifecycle, use AdminClient to inspect broker state, make grounded choices for partitions/replication/retention, and build a safe resource change process.

KafkaAdmin brings topic declarations into Spring Kafka configuration; AdminClient expands administrative capabilities when active operations are needed. Messaging reliability also depends on how partitions, replicas, retention, access permissions, testing, and monitoring are designed. Mastering these areas helps producers and consumers operate on a predictable, operable resource foundation.

