# Handling unknown topic or partition

In Kafka producer operations, an **unknown topic or partition** error occurs when the broker cannot identify the topic or partition referenced by a request. The producer may have already connected to the cluster yet still fail to send records because the topic does not exist yet, the topic name is wrong, the specified partition is invalid, or the metadata currently held by the client does not reflect current cluster state.

This error is typically represented by **UnknownTopicOrPartitionException** in the Kafka client. It is a retriable error because sometimes the cause is simply stale metadata or a topic that was just created. However, if the topic genuinely does not exist, the producer is pointing to the wrong cluster, or the application is sending to a non-existent partition, continuous retries will not resolve the root cause.

In the **Producer operations** chapter, handle this error along two fronts: accurately identify the topic/partition and cluster state; then decide whether to let the Kafka client retry automatically, fix configuration, provision the topic via governance workflows, or adjust partition selection logic.

## 1. Understanding the unknown topic or partition error

Kafka stores data in topics, each consisting of one or more partitions. A producer sends records to a specific partition. To do so, the producer needs metadata about the topic, partitions, leader brokers, and related details.

The broker can return **UNKNOWN_TOPIC_OR_PARTITION** when the requested topic or partition is unrecognized at processing time. On the Java client side, the error typically appears as **org.apache.kafka.common.errors.UnknownTopicOrPartitionException**.

The error name combines two cases:

- **Unknown topic**: the topic does not exist in the cluster the client is connected to, or the broker does not yet have valid metadata for that topic.
- **Unknown partition**: the topic may exist, but the partition referenced by the request does not exist or is not yet recognized by the broker at that moment.

This is an error at Kafka's metadata/routing layer. It does not automatically mean the broker lost data, the producer lacks permissions, or a record was written and then lost.

### 1.1 How does the producer need metadata?

Before sending a record, the producer needs to know the target partition and that partition's leader broker. The Kafka client caches metadata in memory and refreshes metadata periodically or when encountering an error that requires a metadata refresh.

High-level flow:

~~~mermaid
sequenceDiagram
    participant App as Spring application
    participant P as Kafka producer
    participant M as Kafka metadata
    participant L as Partition leader

    App->>P: send(topic, key, value)
    P->>M: Fetch topic/partition metadata
    M-->>P: Partition list and leader
    P->>L: Produce request
    alt Valid topic/partition
        L-->>P: ACK or other write error
        P-->>App: Complete future
    else Metadata not yet valid
        L-->>P: UNKNOWN_TOPIC_OR_PARTITION
        P->>M: Refresh metadata
        P->>L: Retry if time remains
        P-->>App: Success or future completes with error
    end
~~~

The producer may not transmit the record immediately upon calling **send()**: the client may have to wait for metadata first. When metadata is unavailable or the broker returns a retriable error, the client can refresh metadata and retry per its retry policy within the send time limit.

Therefore, distinguish:

- Application calls **send()** successfully at the API level: the request entered the asynchronous send pipeline; the broker has not necessarily written the record.
- Producer receives ACK: the broker confirmed the write according to the **acks** configuration.
- Producer receives exception: the send did not complete successfully under the current policy. With timeouts or dropped connections, the outcome may be ambiguous if the broker wrote the record but the ACK never reached the client.

## 2. Common causes

### 2.1 Topic has not been created yet

The application sends records to a new topic that has not yet been created in the cluster. Common situations include:

- The producer service is deployed before the topic provisioning step.
- The topic was created manually in dev but missing in staging or production.
- The application deployment pipeline lacks a dependency on the topic creation step.
- The topic was deleted while the application kept sending.
- A topic name is configured without a corresponding resource in Kafka.

If auto-topic creation is disabled on the cluster, the producer cannot create the topic merely by sending records. The broker returns an error and the producer may retry until the send timeout expires.

**Resolution:** verify the right cluster and topic name, then create the topic through an approved governance workflow. Inspect metadata afterward to ensure the producer can see the topic and its partitions.

### 2.2 Incorrect topic name

Topic names are typically case-sensitive. Configuration mistakes like **order-events**, **order_event**, **Order-Events**, or a differing hyphen/underscore can cause the producer to send to a non-existent name.

Common sources of naming errors include:

- Hard-coding topic names across multiple modules.
- Different Spring profiles across local, staging, and production.
- Missing environment variables or trailing/leading whitespace.
- Topic names assembled from environment or tenant prefixes.
- Producer and consumer using two different naming conventions.

Do not auto-create topics every time a new name is encountered. If a typo occurs while the broker permits auto-create, the cluster may create an unintended topic, causing records to go to the wrong place and the main consumer to miss data.

**Resolution:** log the actual resolved topic name; compare it against the topic list in the right cluster; centralize topic names in shared configuration and validate configuration at startup.

### 2.3 Producer connected to the wrong Kafka cluster

A topic may exist in production yet not exist in the cluster the producer is currently using. This commonly happens when:

- **bootstrap-servers** points to a different cluster.
- An environment's Secret or ConfigMap was mounted incorrectly.
- Service DNS resolves to an old endpoint.
- The application runs with the default profile instead of the deployment profile.
- Multiple clusters exist per region, tenant, or workload.

This cause should be checked early when operations believes the topic "definitely exists". The topic list must be checked on the exact cluster the producer actually connects to.

Do not log credentials or full secrets to prove which cluster is used. You can log the environment name, cluster alias, sanitized bootstrap endpoint, and cluster ID retrieved via admin tools if policy permits.

### 2.4 Specifying a non-existent partition

A producer can explicitly specify a partition instead of letting the partitioner choose:

~~~java
ProducerRecord<String, String> record =
    new ProducerRecord<>(
        "orders",
        7,
        "order-1001",
        "{\"status\":\"CREATED\"}"
    );
~~~

The partition parameter is a **0-based index**. If a topic has 6 partitions, valid indices are **0** through **5**. Index **6** or **7** does not exist in that topic.

The error can happen when:

- Code hard-codes partition IDs.
- The application uses a partition count from an older configuration.
- The topic was created with fewer partitions than expected.
- A service assumes the same partition count across all environments.
- The partition count changed while the producer kept using old logic.

If the producer does not specify a partition, the Kafka partitioner chooses based on metadata, key, and partitioner config. When code explicitly specifies a partition, the application is responsible for ensuring the index is valid.

**Resolution:** describe the topic to get the partition count and list of partition IDs; inspect where **ProducerRecord** is constructed; remove hard-coded partitions unless there is a genuine business routing requirement.

### 2.5 Topic was recently created, deleted, or modified

Immediately after a topic is created, metadata may not yet be consistent across all brokers or updated on the client. A producer holding stale metadata may encounter transient errors when the topic first appears.

Other scenarios:

- The topic was deleted while the producer was actively sending.
- The topic was deleted and recreated with different configuration or partition count.
- A partition leader is being elected or changing.
- The controller/metadata quorum is experiencing issues.
- A broker recently restarted or is recovering metadata.

In these situations, the error may be short-lived. The Kafka client has metadata refresh and retry mechanisms for retriable errors. Still, the application must maintain timeouts and observe final outcomes.

Never delete and recreate a topic to "refresh metadata" as a default fix. Deleting a topic can cause data loss and break contracts with consumers.

### 2.6 Auto-create topics disabled or behaving unexpectedly

Kafka has a broker option **auto.create.topics.enable**. Depending on cluster configuration and request/client type, accessing a non-existent topic may auto-create it or be rejected. Some governed environments disable auto-create to prevent uncontrolled topic sprawl.

Do not rely on auto-create for important business topics because:

- Topics may be created with inappropriate default partition counts or replication factors.
- Retention, cleanup policy, min ISR, and quotas may fail to meet requirements.
- A misspelled topic name can create junk topics.
- Permission to create topics may differ from permission to write to topics.
- Behavior can vary across environments and versions.

Explicitly provision topics using IaC, admin tools, or release workflows. Producers should start sending after topics are created and verified.

## 3. Distinguishing unknown topic/partition from other Kafka errors

Multiple errors appear when a producer fails to send records, but their remedies differ. Never lump all exceptions into "topic does not exist".

| Error | Common meaning | Primary resolution |
|---|---|---|
| **UnknownTopicOrPartitionException** | Broker does not recognize topic or partition at request time | Check cluster, topic, partition, metadata, and provisioning |
| **InvalidTopicException** | Topic name is invalid under Kafka naming rules | Fix topic name; check characters and naming conventions |
| **TopicAuthorizationException** | Principal lacks permission on the topic | Check ACLs and service account |
| **ClusterAuthorizationException** | Principal lacks permission for cluster-level operations | Check appropriate cluster/admin permissions |
| **LeaderNotAvailableException** | Partition has no available leader yet | Check leader election, brokers, and partition state |
| **NotLeaderOrFollowerException** | Request hit a broker that is no longer leader or lacks the proper role | Refresh metadata; check leader and brokers |
| **TimeoutException** | Request did not complete within time limit | Check network, broker latency, retries, and delivery timeout |
| **NetworkException** | Connection to broker was disrupted | Check DNS, routing, TLS, firewall, and brokers |
| **NotEnoughReplicasException** | ISR is below min ISR when writing under durability policy | Restore replicas/ISR and check durability policy |

Several errors may appear sequentially in the same incident. For example, a newly created topic whose leader is not ready yet can yield leader errors; an incorrect ACL can prevent `AdminClient` from describing a topic. Record the original exception and metadata state to identify the first failure.

### 3.1 Do not confuse authorization errors with missing topics

If a principal lacks read/write or describe permissions on a topic, Kafka typically returns the corresponding authorization error. Do not conclude a topic does not exist simply because the application cannot see it via admin tooling.

When inspecting via CLI or `AdminClient`, use the same principal and security configuration as the producer. An admin account seeing a topic does not prove the producer's service account has sufficient permissions.

### 3.2 Do not confuse a leaderless partition with a non-existent partition

A partition can exist while temporarily lacking an available leader. That state differs from a partition ID not existing in the topic. Run describe to view partition IDs, leaders, replicas, and ISRs. If a partition exists but its leader is unavailable, fix the broker/controller rather than creating another topic or increasing partition count.

## 4. Producer-side diagnostic workflow

When seeing **UnknownTopicOrPartitionException**, gather facts before changing configurations.

### Step 1: Capture full error context

At minimum, capture:

- Timestamp of the error.
- Actual resolved topic name.
- Partition ID if explicitly specified by the application or provided by the exception.
- Producer client ID and application instance.
- Sanitized bootstrap endpoint / cluster alias.
- Exception class, root cause, and retry count.
- Key or event ID for business correlation; avoid logging sensitive payloads.
- Final send outcome and total send duration spent.

Do not log only **Failed to send message**. Log enough context to determine which topic on which cluster the producer targeted and at which stage the request failed.

### Step 2: Verify the cluster

Compare the producer's bootstrap servers and environment against the intended cluster. When using multiple profiles, verify effective runtime values rather than just YAML files in the repository.

Check DNS, service discovery, and secret/config injection if the endpoint differs from expectations. Ensure the producer is not accidentally pointed at a dev or staging cluster.

### Step 3: Verify the topic

Use Kafka tools with the right bootstrap endpoint and principal:

~~~bash
kafka-topics.sh \
  --bootstrap-server kafka-1:9092 \
  --list
~~~

To describe the topic:

~~~bash
kafka-topics.sh \
  --bootstrap-server kafka-1:9092 \
  --describe \
  --topic orders
~~~

The describe command reveals partition count, leaders, replicas, and ISRs. If it reports the topic does not exist, re-verify the cluster and topic name before creating anything.

In TLS/SASL-enabled environments, pass the proper client configuration according to your security procedures. Never put passwords or secrets directly into shell history or logs.

### Step 4: Verify the partition

If the topic exists, verify that the partition ID specified in code falls within the topic's partition list.

For example, if a topic has 4 partitions, valid IDs are:

~~~text
0
1
2
3
~~~

If the application specifies partition **4**, fix the logic or configuration. Do not increase partition count merely to mask an index bug if business routing does not require it.

If the partition exists but its leader is unavailable, inspect the leader broker, replicas, ISRs, and controller.

### Step 5: Check recent changes around the error time

Correlate against deployment history:

- Was the topic recently created or deleted?
- Did the partition count change?
- Did bootstrap servers or secrets change?
- Was a new producer version released?
- Were ACLs modified?
- Was there a broker restart, controller failover, or network maintenance?
- Did the auto-create policy change?

Timestamps help distinguish a provisioning race from a persistent configuration mistake.

### Step 6: Decide whether retries remain appropriate

If the topic was just created and metadata is converging, letting the Kafka client refresh metadata and retry within delivery timeout may suffice.

If the topic name is wrong, the cluster is wrong, or the partition index does not exist, retries simply repeat the same error. Fix the configuration/logic cause and handle unsent records according to business policy.

## 5. Handling each scenario

### 5.1 Topic does not exist yet

1. Verify the topic name and cluster.
2. Check whether the topic is declared in manifests/IaC or the environment's resource inventory.
3. Create the topic via the approved governance workflow.
4. Choose partition count, replication factor, retention, cleanup policy, and min ISR per requirements.
5. Describe the topic after creation to confirm leaders/replicas/ISRs.
6. Let the producer re-send pending events via the retry/outbox mechanism.

Do not grant broad create-topic permissions to every producer just to self-heal errors. Topic creation rights can lead to configuration drift and unmanaged topics.

### 5.2 Wrong topic name in configuration

- Log the actual resolved topic name.
- Compare against the environment's canonical topic name.
- Check prefixes/suffixes, delimiters, and casing.
- Centralize topic names into shared configuration or constants.
- Add startup configuration validation.
- Deploy the fix and confirm records land in the intended topic.

If the producer sent records to an unintended topic created via auto-create, evaluate the data in that topic before deleting it. Never delete a topic immediately before verifying whether any consumer or valid data relies on it.

### 5.3 Invalid partition specified

Locate where **ProducerRecord** is constructed or where **KafkaTemplate.send** is called with a partition parameter.

Spring Kafka example sending to an explicit partition:

~~~java
kafkaTemplate.send(
    "orders",
    2,
    "order-1001",
    orderCreated
);
~~~

Partition **2** is the third partition because indexing starts at 0. Only use this send style when business logic truly requires targeting a specific partition, such as managed shard-based routing.

If you want Kafka to choose the partition by key, use the overload without a partition parameter:

~~~java
kafkaTemplate.send(
    "orders",
    "order-1001",
    orderCreated
);
~~~

The default partitioner uses the key and metadata to pick a partition. For non-null keys, records with the same key typically route to the same partition as long as partition count and partitioner remain unchanged. When partition count increases, key mappings can change; never assume a key is permanently bound to one partition ID.

### 5.4 Topic was just created but producer still fails

- Confirm the topic creation command completed successfully.
- Wait for topic/partition metadata to be published by brokers.
- Use topic describe to check partitions and leaders.
- Let the producer refresh metadata and retry for a reasonable duration.
- If the error persists, check controller, brokers, network, and permissions.
- Avoid repeatedly creating/deleting the topic, which complicates metadata state.

For release pipelines, add a readiness wait step after provisioning. Do not only check that the create command returned; verify that the topic has valid partitions and leaders before opening producer traffic.

### 5.5 Partition count changed

Kafka allows increasing a topic's partition count under appropriate conditions, but does not normally support decreasing partition count. When increasing partition count:

- Producers must refresh metadata to see the new partitions.
- The partitioner may distribute records to the new partitions.
- Key-to-partition mappings may change.
- Consumer groups may rebalance to pick up the new partitions.
- Global ordering is not guaranteed; ordering only holds within each partition.

If the producer hard-codes partition IDs, ensure new partitions exist before sending. Even if code only uses keys, confirm whether business logic tolerates mapping changes when partitions increase.

### 5.6 Broker or cluster metadata is recovering

If both topic and partition exist but the error occurs while brokers/controller are recovering:

- Check cluster health and controller/quorum.
- Check whether the partition leader is available.
- Monitor leader elections and ISRs.
- Confirm brokers are serving metadata requests steadily.
- Let clients perform bounded retries; avoid restarting all producers simultaneously unless necessary.

If the error persists, follow the Kafka cluster runbook. Never create duplicate-named topics or alter partition counts in response to transient metadata errors.

## 6. Kafka client retries and metadata refresh

**UnknownTopicOrPartitionException** belongs to the Kafka client's retriable exception group. This allows the producer to retry after refreshing metadata, because the error may stem from a newly created topic, unsynchronized metadata, or changing partition state.

Producer retries are bounded by send configuration. Relevant properties include:

- **delivery.timeout.ms**: maximum total time for the producer to finish sending, including waits and retries.
- **request.timeout.ms**: wait time for a response to a single request.
- **retry.backoff.ms**: wait time between retry attempts.
- **retry.backoff.max.ms**: maximum backoff cap on client versions supporting this property.
- **enable.idempotence**: protects against duplicates caused by producer protocol-level retries when configured properly.

Do not simply increase **delivery.timeout.ms** when a topic does not exist. A longer timeout only prolongs waiting for a cause that cannot self-heal.

Illustrative configuration example:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        enable.idempotence: true
        request.timeout.ms: 30000
        delivery.timeout.ms: 120000
        retry.backoff.ms: 500
~~~

The numbers above are only examples. Tune them based on SLA, cluster latency, and expected recovery times. **delivery.timeout.ms** must be compatible with **request.timeout.ms** and the Kafka client's retry settings.

### 6.1 Kafka client retries vs. application retries

The Kafka producer already has internal retries. If the application also retries the entire **send()** after the future completes with an error, another retry layer is introduced.

Distinguish:

- Producer internal retries for one send call.
- Application re-sending an event after receiving a final error.
- Outbox publisher re-reading the same row not yet marked published.
- Retries at the HTTP/API layer invoking the event-publishing flow.

If multiple layers retry together, total send attempts can multiply exponentially. Maintain one clear retry policy and total time budget.

For fixed topic/partition errors like wrong names or invalid indices, application retries do not help. For timeouts or connection drops, outcomes can be ambiguous; idempotence and event IDs are required to prevent duplicates.

## 7. Spring Kafka: observing send outcomes

### 7.1 KafkaTemplate and futures

**KafkaTemplate.send()** returns **CompletableFuture<SendResult<K, V>>** in modern Spring Kafka versions. You can handle results asynchronously to log errors and metadata upon success.

~~~java
public void publish(OrderCreated event) {
    String topic = "orders";

    kafkaTemplate.send(topic, event.orderId(), event)
        .whenComplete((result, exception) -> {
            if (exception != null) {
                log.error(
                    "Kafka send failed: topic={}, eventId={}",
                    topic,
                    event.eventId(),
                    exception
                );
                return;
            }

            RecordMetadata metadata =
                result.getRecordMetadata();

            log.info(
                "Kafka send succeeded: topic={}, partition={}, offset={}, eventId={}",
                metadata.topic(),
                metadata.partition(),
                metadata.offset(),
                event.eventId()
            );
        });
}
~~~

When the future fails, log the exception class and root cause. If exception classification is needed, unwrap **CompletionException** or walk the cause chain to find the underlying Kafka error.

Do not log sensitive payloads. Event ID, topic, partition, and correlation ID are usually enough for tracing.

### 7.2 Classifying errors before application-level retry

Example helper to detect unknown topic/partition in the cause chain:

~~~java
static boolean isUnknownTopicOrPartition(Throwable error) {
    Throwable current = error;

    while (current != null) {
        if (current instanceof
                UnknownTopicOrPartitionException) {
            return true;
        }
        current = current.getCause();
    }

    return false;
}
~~~

This classification is only one part of error handling. Do not inspect only the outermost exception because Spring or Java futures may wrap errors in other exceptions. Also guard against anomalous cause cycles in custom wrappers; in real applications, use a shared utility to unwrap exceptions.

When an unknown topic/partition error is identified:

- Tag the error by topic and environment.
- Inspect provisioning and metadata.
- Do not retry infinitely if the cause is a static configuration error.
- If the topic is being created, allow a bounded wait or retry per release policy.
- Persist unsent events if the business requires not losing the intent to publish.

### 7.3 Provisioning topics with KafkaAdmin and NewTopic

Spring Kafka supports declaring topics as **NewTopic** beans and using **KafkaAdmin** to manage topic creation when the application initializes its context.

Illustrative example:

~~~java
@Configuration
class KafkaTopicConfiguration {

    @Bean
    NewTopic ordersTopic() {
        return TopicBuilder.name("orders")
            .partitions(6)
            .replicas(3)
            .build();
    }
}
~~~

This approach can be useful in small applications or test environments. For production, topics should generally be managed via IaC or standalone provisioning pipelines so that creation permissions, replication, retention, min ISR, and partition counts remain governed.

If using `KafkaAdmin`, ensure:

- The application has connectivity and required admin permissions.
- Topic names and configs match each environment.
- Startup behavior when brokers are temporarily unavailable is explicitly decided.
- There is a step verifying the topic is actually ready before producers take traffic.
- Topic beans are not used as a way to mask a wrong topic name in code.

Not every application should create topics on its own. Designate one clear provisioning owner to prevent multiple services from altering topic configurations concurrently.

## 8. Inspecting topics and partitions with AdminClient

When programmatic diagnostics are needed, **AdminClient** can describe topics and return their partition lists. Example:

~~~java
Properties properties = new Properties();
properties.put(
    AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
    "kafka-1:9092"
);

try (AdminClient admin = AdminClient.create(properties)) {
    TopicDescription description =
        admin.describeTopics(List.of("orders"))
            .allTopicNames()
            .get(10, TimeUnit.SECONDS)
            .get("orders");

    for (TopicPartitionInfo partition :
            description.partitions()) {
        System.out.printf(
            "topic=%s partition=%d leader=%s replicas=%d isr=%d%n",
            description.name(),
            partition.partition(),
            partition.leader(),
            partition.replicas().size(),
            partition.isr().size()
        );
    }
}
~~~

This snippet focuses on describing a topic. Real applications need security properties, timeouts, exception handling, and proper `AdminClient` lifecycle closure. Exact API details may vary by Kafka client version; match the version your application compiles against.

If the topic does not exist or the principal lacks permissions, the `AdminClient` future will complete with an error. Classify the root cause to distinguish unknown topic from authorization and timeouts.

Do not call **describeTopics()** per record. Metadata/health checks should run at startup, readiness checks, or periodic monitoring tasks at a reasonable cadence; the producer client already maintains its own metadata mechanism.

## 9. Designing provisioning to prevent errors upfront

The best way to handle unknown topic/partition errors is to avoid letting producers send before topics and partitions are ready.

### 9.1 Managing topics as deployment resources

Every business topic should have a clear definition:

- Topic name and environment.
- Owner and associated producers/consumers.
- Partition count.
- Replication factor.
- **min.insync.replicas**.
- Retention and cleanup policy.
- Schema/serialization contract.
- Producer and consumer ACLs.
- Procedure for increasing partitions or changing config.

Store topic definitions in IaC or a governance repository so changes have proper reviews, auditing, and rollback plans.

### 9.2 Ordering releases

A typically safe deployment sequence:

1. Provision topic and ACLs.
2. Describe topic, confirming partitions, leaders, replicas, and ISRs.
3. Verify the producer service account has write permissions.
4. Deploy the producer or open traffic.
5. Deploy/verify consumer groups.
6. Monitor send errors, consumer lag, and initial records.

If producers and topics are released independently, enforce an explicit pipeline dependency or readiness gate. Do not rely on a fixed sleep as the sole guarantee; verify topic state using `AdminClient` or admin tooling.

### 9.3 Validating configuration at startup

An application can validate required topic names before accepting traffic. Validation should balance availability:

- If a topic is a hard dependency, startup/readiness can fail when the topic does not exist.
- If the application can store events in an outbox while Kafka is unavailable, the application can start while the publisher holds off sending.
- If a topic is optional behind a feature flag, only validate when the feature is enabled.

Readiness should reflect real ability to serve business requests. Do not fail liveness merely because Kafka is temporarily unreachable if continuous restarts do not aid recovery and add load to the cluster.

## 10. Partitioning and partition count changes

Unknown partition errors are often tied to how the application routes records.

### 10.1 Zero-based partition indexing

If a topic has N partitions, valid partition IDs are **0** through **N-1**. Example:

| Partition count | Valid partition IDs |
|---:|---|
| 1 | 0 |
| 3 | 0, 1, 2 |
| 6 | 0, 1, 2, 3, 4, 5 |
| 12 | 0 to 11 |

Never confuse partition count with the highest partition ID. A topic with 6 partitions has no partition ID 6.

### 10.2 Choosing partitions by key

When sending a keyed record without specifying a partition, the default partitioner typically hashes the key modulo the partition count to select a partition. Records with the same key usually land in the same partition, preserving per-key ordering under stable configuration.

However, when partition count increases, the hash modulo partition count result can change. Future records with the same key may go to a new partition while older records remain in the previous partition. Thus, increasing partition count can disrupt per-key processing order across historical data.

If the business requires strict ordering for an aggregate/key, evaluate the partitioning strategy and scaling plan before increasing partitions.

### 10.3 Do not hard-code partition counts

If you must route by partition ID, obtain the partition count from metadata or governed configuration and validate before sending. Never copy partition counts from dev to production.

For business sharding requirements, maintain a tested, versioned routing layer. Avoid having individual producer services compute partitions with differing rules.

## 11. Impact on consumers and data

Although the error originates at the producer, mishandling it can affect consumers and data integrity.

### 11.1 Records sent to the wrong topic

If auto-create allows a typo to create a topic, the producer may receive a successful ACK while the primary consumer misses the event because it subscribes to the right topic. This is more dangerous than a send failure because the system may believe the event was published.

Monitor destination topics in successful send metadata and alert on topics outside the governed catalog. Avoid permissive auto-create in production.

### 11.2 Records not sent successfully

If the producer future fails and the application drops the event, the intent to publish can be lost even though the database committed. For critical workflows, a transactional outbox persists the event in the same database transaction so a publisher can resend once Kafka is ready.

The publisher should mark the outbox row as sent after receiving a successful outcome per policy. If the process crashes after the broker writes the record but before updating the outbox, the publisher may resend; consumers should be idempotent by event ID.

### 11.3 Uncertain outcomes

Timeouts do not always prove the broker failed to write. If the producer misses an ACK, the broker may have appended the record. When the application resends later, duplicates can occur without idempotence or deduplication.

With an idempotent producer, internal retries within the same session are protected by protocol. Across application retries, process restarts, or new publishers, stable event IDs and consumer idempotency remain essential.

## 12. Observability and alerting

Combine producer metrics, application logs, and Kafka state.

| Scope | Signals to monitor | Meaning |
|---|---|---|
| Producer | Record send error rate | Rate of failed record sends |
| Producer | Retry rate, request latency | Client is retrying or waiting long |
| Producer | Record queue time, buffer availability | Whether producer is backed up during slow broker/metadata |
| Application | Exceptions by class and topic | Distinguish unknown topic from authorization/timeout |
| Application | Resolved topic name | Detect misconfiguration |
| Kafka metadata | Topic/partition existence | Verify resources are provisioned |
| Partition | Leader, replicas, and ISR | Distinguish non-existent partition from leaderless partition |
| Admin/provisioning | Create/describe topic outcomes | Detect races or pipeline failures |
| Outbox | Backlog and oldest record age | Measure events waiting to be sent |
| Business | Event IDs not yet confirmed by consumers | Detect gaps between publish and processing |

Useful alerts:

- `UnknownTopicOrPartitionException` exceeding a threshold over a time window.
- Sudden spike in producer send failures after deployment.
- Required topic missing in an environment.
- Partition without a leader or degraded ISR.
- Growing outbox backlog or oldest record exceeding SLA.
- Appearance of a topic outside the governed catalog.

Avoid alerting on every transient metadata retry. Alert when errors persist, affect send success rates, or push event age past business thresholds.

## 13. Incident response runbook

When a producer raises unknown topic or partition errors, proceed in order:

1. **Isolate:** identify service, environment, cluster, topic, partition, client ID, and start time.
2. **Read root cause:** confirm the error is truly **UnknownTopicOrPartitionException**, not authorization, invalid topic, leader unavailable, or timeout.
3. **Verify cluster:** check bootstrap endpoints and runtime environment.
4. **Verify topic:** use the proper principal to list/describe the topic.
5. **Verify partition:** check valid partition IDs, leaders, replicas, and ISRs.
6. **Correlate changes:** check releases, topic provisioning, ACLs, broker restarts, controller, and network.
7. **Fix the cause:** correct names, provision topics per workflow, fix partition indices, or recover brokers/metadata.
8. **Handle unsent events:** confirm internal retries finished; drain outbox or pending queues by event ID.
9. **Verify recovery:** producer receives ACKs, metadata shows topic/partition, send errors drop, and consumers receive events.
10. **Post-incident review:** record root cause, impact duration, pending/replayed event counts, and preventive actions.

Never delete or recreate topics, reduce replication, increase partition counts, or enable auto-create merely to make an exception vanish. Every change must tie to a verified root cause with assessed data impact.

## 14. Testing unknown topic/partition errors

Test in a staging environment with production-equivalent configuration:

- Send to a non-existent topic with auto-create disabled; verify the producer receives a final error within timeout limits.
- Create the topic after the producer starts sending; verify metadata refresh and retries recover once the topic is ready.
- Send to an out-of-range partition index; verify the error is classified and does not retry infinitely.
- Point the producer to a cluster lacking the topic; verify startup checks/runbooks detect the environment mismatch.
- Use a principal lacking ACLs; verify authorization errors are distinguished from unknown topic.
- Make a broker/leader unavailable in a test environment; verify leader/metadata errors are handled per runbook.
- Test the outbox while Kafka is unavailable; verify events are retained and published after recovery.
- Test a topic typo in an environment with auto-create; verify controls prevent creating unmanaged topics.

Each test should have dedicated test topics, distinct event IDs, stopping criteria, and cleanup procedures. Never delete production topics or inject test records into live business topics to simulate errors.

## 15. Operations checklist

**Configuration and provisioning**

- [ ] Producer connects to the right cluster for each environment.
- [ ] Topic names are centrally managed with strict case sensitivity.
- [ ] Required topics are provisioned before opening producer traffic.
- [ ] Partition count, replication factor, retention, and min ISR are governed.
- [ ] Auto-create policy is explicitly decided; production does not rely on unmanaged default topics.
- [ ] Producers and diagnostic tools use the proper principal/security configuration.

**Producer and partitioning**

- [ ] Partition IDs are not hard-coded without a business requirement.
- [ ] Partition indices are validated within **0..N-1**.
- [ ] Partition count changes assess impact on key mappings and ordering.
- [ ] Kafka client retries are bounded by delivery timeout.
- [ ] Application retries do not multiply infinitely with internal producer retries.
- [ ] Critical events have event IDs and durable storage/outbox mechanisms.

**Observability and recovery**

- [ ] Logs include topic, partition, client ID, event ID, and root cause.
- [ ] Dashboards cover send errors, retries, request latency, and metadata/partition health.
- [ ] Alerts exist for missing required topics or leaderless partitions.
- [ ] Runbooks distinguish unknown topic, authorization, leader, and timeout errors.
- [ ] Outbox/replay and duplicate-prevention procedures are in place.
- [ ] Missing topics, wrong partition indices, and slow metadata updates have been rehearsed in a suitable environment.

Unknown topic or partition is a routing and metadata error that must be addressed based on actual cluster state. When topics are provisioned under governance, partition indices are valid, producers target the right cluster, and retries are bounded, transient issues self-recover while configuration mistakes surface quickly. For critical events, combine ACK tracking, event IDs, and an outbox so the producer never silently drops publish intent when Kafka is not yet ready.

