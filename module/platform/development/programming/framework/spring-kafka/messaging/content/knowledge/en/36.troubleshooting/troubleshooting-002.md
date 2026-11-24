# Topic Does Not Exist

A missing-topic error occurs when a producer, consumer, or listener container references a Kafka topic that has not been created on the cluster the application is connected to. Common causes include a misspelled topic name, incomplete topic creation, bootstrap servers pointing to the wrong environment, or a cluster that disallows auto-creating topics. Other issues such as missing permissions, a partition lacking a leader, or an unready broker can look like a missing-topic error yet require different remediation.

In the `SPRING_KAFKA_MESSAGING` module, the producer sends events with `KafkaTemplate` and the consumer receives events with `@KafkaListener`. A topic is a resource managed on the Kafka cluster; the name in code is only a reference. Therefore, verify the topic on the right cluster with the right name and partitions before changing retries or modifying listeners.

~~~mermaid
flowchart TD
    A[Producer / Consumer reports topic error] --> B{Does topic exist on the right cluster?}
    B -->|No| C[Check name and bootstrap server]
    C --> D[Provision topic]
    B -->|Yes| E{Does partition have a leader?}
    E -->|No| F[Check broker/controller]
    E -->|Yes| G{Is there an authorization error?}
    G -->|Yes| H[Check principal and ACLs]
    G -->|No| I[Check metadata, timeouts, and client config]
    D --> J[Try sending/receiving record]
    F --> J
    H --> J
    I --> J
~~~

The event/listener examples in this article use the following simple contract:

~~~java
public record OrderCreatedEvent(
        String eventId,
        String orderId
) {}

public interface OrderApplicationService {
    void handle(OrderCreatedEvent event);
}
~~~

## 1. Recognizing Missing-Topic Errors

Common exceptions/logs include:

| Symptom | Common meaning | What to check |
|---|---|---|
| `UnknownTopicOrPartitionException` | Broker cannot find the topic/partition in current metadata | Check name, topic existence, and metadata refresh |
| `LEADER_NOT_AVAILABLE` / `LeaderNotAvailableException` | Partition has no available leader yet, common during topic creation or leader election | Check partition and broker status |
| `TopicAuthorizationException` | Principal lacks permission to operate on the topic | Check ACLs and application identity |
| `InvalidTopicException` | Invalid topic name | Check characters, length, and naming conventions |
| `TimeoutException` | Request did not complete within the allowed time | Check broker, network, metadata, and timeouts |
| `InvalidReplicationFactorException` | Requested replication factor exceeds available broker capacity | Check broker count and replica configuration |

`UnknownTopicOrPartitionException` does not always prove the topic has never existed. It can also occur with stale metadata, an invalid partition, or a newly created topic whose metadata has not propagated to the client yet. Cross-check with AdminClient/CLI output and broker status before drawing conclusions.

## 2. Distinguishing a Missing Topic from an Unready Leader

A newly created topic may already appear in metadata before its partitions have stable leaders. During that window, producers/consumers may temporarily hit leader or metadata errors.

| State | How to tell | Action |
|---|---|---|
| Topic missing from list | `--list` does not show the topic name on the target cluster | Check the name and create/provision the topic |
| Topic exists but partition lacks leader | `--describe` shows leader `-1` or an abnormal state | Check broker/controller and wait for election to finish |
| Topic exists, leader is healthy, but rejected | Authorization exception | Grant appropriate ACLs |
| Topic exists on a different cluster | Wrong cluster ID/bootstrap servers | Fix environment configuration |

Do not handle `TopicAuthorizationException` by recreating the topic. Nor should you raise retries indefinitely when the broker rejects due to ACLs; retrying cannot grant permissions.

## 3. Checking the Topic Name in the Application

Topic names must match exactly across the producer, listener, configuration, and infrastructure. Kafka is case-sensitive, so `orders.created` and `Orders.Created` are two different names.

Common mistakes:

- Typos or mismatched letter casing.
- Producer uses an environment suffix while the listener uses a hardcoded name.
- A Spring Boot profile is not activated, loading the wrong topic name.
- Topic name in `@KafkaListener` differs from the one provisioned in the environment.
- Retry or DLT topics have a different suffix than expected.
- Configuration placeholders are empty or fail to resolve.

Centralize topic names in configuration:

~~~yaml
app:
  kafka:
    topics:
      orders-created: orders.created
      shipments-requested: shipments.requested
~~~

Inject that configuration into publishers/listeners or use property placeholders directly in the annotation:

~~~java
@KafkaListener(
        topics = "orders.created",
        groupId = "orders-service"
)
public void listen(OrderCreatedEvent event) {
    orderService.handle(event);
}
~~~

Avoid hardcoding the same name across multiple classes. If the topic name depends on the environment, verify the resolved value at startup and compare it against the name created on the cluster.

## 4. Verifying the Application Connects to the Right Kafka Cluster

A topic might exist in development but not in staging/production. Before creating a topic, verify which `bootstrap.servers` the application is using.

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
    consumer:
      group-id: orders-service
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.value.default.type: com.acme.orders.OrderCreatedEvent
        spring.json.trusted.packages: com.acme.orders
~~~

Check the following:

- Is the `KAFKA_BOOTSTRAP_SERVERS` variable passed into the process/container?
- Which Spring profile is active?
- Are the producer and consumer using the same cluster?
- Are CLI/AdminClient tools using the same bootstrap servers as the application?
- Is the application connecting through the broker's right listener address in Docker/Kubernetes?
- Could DNS, TLS, SASL, or network policies cause the client to hit the wrong endpoint?

Do not only test `localhost:9092` on the host machine if the application runs inside a container. Inside a container, `localhost` points to that container itself; use service DNS or a broker address reachable from the container.

## 5. Checking Topics with Kafka CLI

Kafka CLI lets you verify topic status directly on the cluster:

~~~bash
# List topics
kafka-topics.sh --bootstrap-server localhost:9092 --list

# Inspect partitions, leaders, and replicas
kafka-topics.sh --bootstrap-server localhost:9092 --describe --topic orders.created

# Create topic if it does not exist
kafka-topics.sh --bootstrap-server localhost:9092 --create --topic orders.created --partitions 3 --replication-factor 1
~~~

On Windows distributions, the script name may be `kafka-topics.bat`. Use the exact same bootstrap server, security config, and environment as the application to avoid inspecting the wrong cluster.

If the topic is listed, read the `--describe` output: verify partition count, leaders, and replicas. If the topic is absent, double-check spelling and the cluster before creating it.

## 6. Creating Topics with Spring Kafka KafkaAdmin

Spring Kafka can create topics on application startup via `NewTopic` beans and `KafkaAdmin`. This approach suits development/test environments or systems that choose to provision topics from application configuration.

~~~java
import org.apache.kafka.clients.admin.NewTopic;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.TopicBuilder;

@Configuration
public class KafkaTopicConfiguration {

    @Bean
    public NewTopic ordersCreatedTopic() {
        return TopicBuilder.name("orders.created")
                .partitions(3)
                .replicas(1)
                .build();
    }
}
~~~

When Spring Kafka has a `KafkaAdmin` and an appropriate broker connection, `NewTopic` beans are used to request topic creation. If a topic already exists, creating the bean does not mean the existing topic automatically changes its partitions/replication for every property in the bean. Modifying an existing topic's configuration requires a dedicated administration process and awareness of Kafka's alteration limits.

The replication factor must fit the number of available brokers. For example, `replicas(3)` cannot succeed on a single-broker cluster. Choose partition counts based on throughput, ordering, and consumer group concurrency; do not pick an arbitrary partition count just to clear an error.

## 7. When Should Topics Be Provisioned Outside the Application?

In production, many organizations manage topics via Terraform, Ansible, Helm, a Kafka operator, or infrastructure pipelines. This separates topic-creation privileges from runtime service privileges and governs partitions, replicas, retention, cleanup policy, quotas, and ACLs.

| Topic creation method | Best suited when | Notes |
|---|---|---|
| `KafkaAdmin` + `NewTopic` | Local, integration tests, small services with clear ownership | Runtime identity needs topic-creation permissions |
| Kafka CLI/AdminClient | Manual operations or administrative scripts | Must target the right cluster and audit changes |
| IaC/Kafka operator | Production across many services/environments | Topic lifecycle is reviewed and versioned |
| Broker auto-create | Sandboxes or controlled experimental environments | May create topics with unsuitable default partitions/replicas |

Do not rely on broker auto-create for production when topics require specific partition counts, replication factors, or retention settings.

## 8. Auto-Create Topic Configuration

The Kafka broker has `auto.create.topics.enable`, which decides whether the broker creates a topic automatically upon receiving a request referencing a nonexistent topic. The Kafka consumer also has `allow.auto.create.topics` to control whether the consumer allows the broker to auto-create a topic when subscribing/fetching.

These two settings live on opposite sides:

- `auto.create.topics.enable`: broker configuration.
- `allow.auto.create.topics`: consumer configuration.

If the broker disables auto-create, a producer or consumer referencing a nonexistent topic cannot create it automatically. This is usually easier to control in production. When auto-create is enabled, topics can be created with broker defaults; the application should not assume a newly created topic has the desired partitions, replicas, or retention.

Auto-create does not replace a provisioning process. Even if auto-create is used locally, declare topics explicitly so tests reflect real configurations.

## 9. Distinguishing Topic Creation Permissions from Topic Usage Permissions

An application may have permission to write/read a topic without permission to create topics. If the topic does not exist and the broker does not auto-create, the producer cannot self-heal via retries.

Permissions to check depending on the security model:

- Create topic: for administrative/provisioning identities.
- Describe topic: to inspect metadata.
- Write: for producers.
- Read: for consumers.
- Group access: for consumer groups.

`TopicAuthorizationException` or `ClusterAuthorizationException` must be resolved with appropriate ACLs/roles. Do not grant broad `Create` permissions to every service just to avoid missing-topic errors. Keep runtime service identities limited to required permissions while provisioning identities hold topic-creation and configuration rights.

## 10. Checking Listener Startup When a Topic Does Not Yet Exist

`@KafkaListener` subscribes to the declared topics. If a topic does not exist yet, startup behavior depends on container configuration, broker auto-create, and Kafka client metadata.

Spring Kafka provides `missingTopicsFatal` to choose whether the container fails startup when a declared topic does not exist. You can enable fail-fast on the container factory:

~~~java
factory.getContainerProperties().setMissingTopicsFatal(true);
~~~

When enabled, the application catches misconfigured topic names earlier rather than running with a listener waiting for the topic to appear. When `false`, the container may keep waiting for metadata/topics depending on configuration and version. `missingTopicsFatal` does not create topics; it only controls how the listener container reacts.

If topics are created via `KafkaAdmin`, ensure the broker is ready and topic creation completes before expecting listeners to process records. For environments requiring fail-fast behavior, configure it explicitly and check startup logs.

## 11. Checking Producer Send When a Topic Does Not Exist

In Spring Kafka 3.x and later, `KafkaTemplate.send()` is asynchronous and returns `CompletableFuture<SendResult<K,V>>`. Older Spring Kafka versions used `ListenableFuture`. Metadata or broker errors can surface in the future, so do not just check that invoking the method throws no synchronous exception.

~~~java
import java.util.concurrent.CompletableFuture;

import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreatedEvent>> publish(
            OrderCreatedEvent event) {

        return kafkaTemplate.send(
                "orders.created",
                event.orderId(),
                event
        );
    }
}
~~~

At the call site, observe the future to capture the result:

~~~java
publisher.publish(event).whenComplete((result, exception) -> {
    if (exception != null) {
        log.error("Cannot publish order event: orderId={}",
                event.orderId(), exception);
        return;
    }

    log.debug("Published order event: topic={} partition={} offset={}",
            result.getRecordMetadata().topic(),
            result.getRecordMetadata().partition(),
            result.getRecordMetadata().offset());
});
~~~

Never ignore future exceptions. If publishing is a mandatory business step, propagate the failure to retry/outbox or an appropriate handling mechanism; merely logging and treating the business step as successful can lose events.

## 12. Checking Retry Topics and Dead-Letter Topics

A “topic does not exist” error can also happen with a retry topic or DLT, not just business topics. For example, `DeadLetterPublishingRecoverer` routes to `orders.created.DLT`, yet that topic has not been provisioned.

Checklist for retry/DLT:

- Verify topic names after applying `retryTopicSuffix` and `dltTopicSuffix`.
- Create all retry topics and DLTs before starting listeners if broker auto-create is disabled.
- Partition counts must be compatible with how the recoverer routes partitions.
- The DLT producer's serializer supports the actual payload, including raw `byte[]` on deserialization failures.
- The runtime identity has write permissions on the DLT; DLT listeners have read and group access permissions.
- Monitor recovery publish failure logs without confusing them with business listener errors.

With `@RetryableTopic`, the topology can create retry/DLT destinations according to configuration. Check your Spring Kafka version's documentation and `KafkaAdmin` setup; do not assume the annotation automatically creates topics in every production setup.

## 13. Ordered Diagnostic Workflow

When hitting a missing-topic error, work through these steps in sequence:

1. Record the exact topic name from the exception/log.
2. Verify the active Spring profile and resolved property inside the process.
3. Verify the bootstrap servers/cluster the application connects to.
4. Run Kafka CLI `--list` and `--describe` against the right cluster.
5. If the topic is missing, check ownership and the provisioning workflow.
6. If the topic exists but lacks a leader, check brokers/controllers and partition status.
7. If rejected by authorization, check principal/ACLs instead of creating the topic.
8. If producer send fails, read the underlying exception from `CompletableFuture`.
9. If the listener receives no records, check subscription patterns, group, assignment, and offsets once the topic exists.
10. After fixing, send a test record and verify both listener and producer work.

This workflow prevents changing multiple settings at once and creating stray topics on the wrong cluster.

## 14. Testing Topic Provisioning

Integration tests should verify that topics actually exist and listeners can process records:

- Start the test broker with explicitly declared topics.
- When testing `KafkaAdmin`, start the Spring context with `NewTopic` beans and verify the topics are created.
- When testing missing topics, disable broker auto-create or use an uncreated topic name.
- Verify listener behavior with `missingTopicsFatal` enabled and disabled according to configuration.
- Send a record with `KafkaTemplate`, await the send future, and verify metadata.
- Verify the listener receives the expected payload.
- Test that DLT/retry topics exist and have compatible partition counts.
- Include dedicated ACL tests if the application uses SASL/ACLs.

With Embedded Kafka, declare topics via `@EmbeddedKafka(topics = ...)` for clear fixtures. With Testcontainers, create topics using `AdminClient` during setup. Do not let tests rely on implicit auto-create because that behavior can differ from production.

## 15. Common Pitfalls

- **Wrong topic name or letter case:** compare the actual resolved name against the name on the broker.
- **Wrong bootstrap servers:** the topic may exist on a different cluster.
- **Assuming retries create topics:** retries only repeat the operation; they do not replace provisioning.
- **Confusing an unready leader with a missing topic:** inspect partition leaders with `--describe`.
- **Confusing authorization with a missing topic:** grant proper ACLs rather than recreating the topic.
- **Leaving auto-create enabled in production with uncontrolled defaults:** topics may end up with unsuitable partitions/replicas.
- **Uncreated DLT/retry topics:** recovery publishing fails after a listener error.
- **Not awaiting the producer future:** asynchronous send errors go unnoticed.
- **Listener waits for topic without failing startup:** configure `missingTopicsFatal` per operational requirements.
- **Creating a topic with a replication factor larger than the broker count:** `AdminClient` fails topic creation.
- **Misusing localhost inside a container:** the broker address is unreachable from the application's network namespace.

## 16. Troubleshooting Checklist

- [ ] Captured the exact topic name from logs/exceptions.
- [ ] Verified active Spring profile and resolved property values.
- [ ] Verified bootstrap servers and the right Kafka cluster.
- [ ] Checked the topic with `kafka-topics --list` and `--describe`.
- [ ] Distinguished missing topic, leader unavailable, invalid topic, and authorization failure.
- [ ] Provisioned the topic with appropriate partitions, replicas, and retention.
- [ ] Decided explicitly between `KafkaAdmin`, CLI/IaC, or auto-create.
- [ ] `missingTopicsFatal` matches startup requirements.
- [ ] Producer observes `KafkaTemplate.send()` future outcomes.
- [ ] Retry topics and DLT are created, authorized, and checked for partitions.
- [ ] Integration tests verify topic provisioning and listener execution.
- [ ] Broad `Create` permissions are not granted to runtime services just to dodge errors.

Missing-topic errors must be addressed starting from metadata and cluster state before adjusting listeners. Verify the right name, right bootstrap servers, partition state, and ACLs; then provision topics through a controlled mechanism. When main topics, retry topics, and DLTs are properly configured, `KafkaTemplate` and `@KafkaListener` operate reliably across deployment environments.
