# Topic Does Not Exist in Kafka

In a Spring Kafka application, a **non-existent topic** means the broker does not return metadata for a topic that the application needs. This situation typically occurs when `@KafkaListener` subscribes to a topic that has not been created yet, the topic name is misspelled, the application connects to the wrong cluster, or the topic has not been provisioned in the current environment.

Three states must be distinguished:

| State | Common Symptoms | Meaning |
|---|---|---|
| Topic does not exist | `UnknownTopicOrPartitionException`, code `UNKNOWN_TOPIC_OR_PARTITION` | The broker responded, but the requested topic was not found |
| Broker unreachable | Timeout, disconnect, `BrokerNotAvailableException` | The application could not verify the topic because it could not communicate with the cluster |
| Insufficient permissions | `TopicAuthorizationException`, `TOPIC_AUTHORIZATION_FAILED` | The topic may exist, but the application's principal is not allowed to view or use it |

Do not lump all three cases together as "missing topic." The remediation and the information that need to be reported to operations differ.

## 1. Why does a topic not exist?

Common causes:

- The topic has not been created in the cluster of the running environment.
- The topic name in `@KafkaListener`, the producer, or the configuration is misspelled, has the wrong casing, or uses the wrong name across environments.
- The application starts before the topic provisioning step. This is a common deployment ordering error when multiple services start together.
- `bootstrap.servers` points to a different cluster than the one where the operations team created the topic.
- The broker disables automatic topic creation, or the client is not authorized to trigger that mechanism.
- The topic has been deleted, or topic creation has not completed yet when the listener checks metadata.

A topic may exist in a local environment but not in staging or production. Therefore, when investigating, verify the exact broker addresses, credentials, and topic name used by the running process.

## 2. Impact on a Spring Kafka listener

Example listener subscribing to the `orders` topic:

```java
@KafkaListener(topics = "orders", groupId = "order-service")
public void consume(OrderEvent event) {
    // Handle order event
}
```

When the container starts, Spring Kafka needs the topic's metadata to determine which partitions the consumer can read. If the topic does not exist yet, startup behavior depends on the listener container's `missingTopicsFatal` property.

- When `missingTopicsFatal=true`, the container throws an error and fails to start if a declared topic does not exist yet. Depending on application lifecycle configuration, this error can cause application context startup to fail.
- When `missingTopicsFatal=false`, the container can start and continue waiting for metadata/partitions to appear. Once the topic is created and the broker updates metadata, the consumer can begin receiving partitions.

Since Spring Kafka 2.3, the default value of this property is `false`; older versions had different default behavior. Configure it explicitly so behavior does not depend on library upgrades.

With Spring Boot, you can keep the consumer configuration provided by Boot and set the property on the factory:

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent> kafkaListenerContainerFactory(
        ConcurrentKafkaListenerContainerFactoryConfigurer configurer,
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory = new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
    configurer.configure(factory, consumerFactory);

    // Allow the container to wait for the topic to be created after the application starts.
    factory.getContainerProperties().setMissingTopicsFatal(false);
    return factory;
}
```

If not using Spring Boot, set the same property on the `ConcurrentKafkaListenerContainerFactory` that the application configures itself.

`missingTopicsFatal=false` only changes how the listener handles a topic that is missing at startup. It **does not create the topic**, does not fix the topic name, and does not resolve connectivity or authorization errors. If the topic is a mandatory requirement for business processing, readiness still needs to reflect the missing-topic state.

## 3. Creating topics in a controlled way

Topics should be created before the application needs to use them. Provisioning can be managed with infrastructure tools such as Terraform, Helm, a Kafka operator, or cluster administration processes. This ensures partition counts, replication factors, and topic configs are reviewed alongside the deployment environment.

In a Spring Kafka application, a `NewTopic` bean can be declared so `KafkaAdmin` creates the topic during initialization:

```java
@Configuration
class KafkaTopicsConfiguration {

    @Bean
    NewTopic ordersTopic() {
        return TopicBuilder.name("orders")
                .partitions(6)
                .replicas(3)
                .build();
    }
}
```

Spring Boot usually auto-configures `KafkaAdmin` when appropriate Kafka configuration is present. For Spring applications not using Boot, you must register `KafkaAdmin` and provide the broker connection configuration. The administrative account used by the application must have permission to create topics.

Choose the partition count and replication factor based on load, broker count, and availability requirements. The example above requires a cluster with enough brokers to satisfy a replication factor of 3; a single-broker local environment typically needs a replication factor of 1.

A few points to note:

- Declaring `NewTopic` does not replace infrastructure configuration management. Check the behavior of the Spring Kafka version in use when a topic already exists and configuration changes are needed.
- Do not rely on the broker's `auto.create.topics.enable` to create topics automatically in production. Topics may be created with inappropriate default partition counts or replication factors; a typo in a topic name can also create unintended topics.
- `auto.offset.reset=earliest` or `latest` only determines where to start reading when no suitable offset exists. This property does not create topics.
- Do not delete and recreate a topic as a quick troubleshooting step. Doing so can cause data loss and confusion over consumer group offsets.

## 4. Verifying the topic on the right cluster

Use the exact broker address the application is connecting to when checking:

```bash
# Check whether a topic exists and inspect partitions/replicas
kafka-topics.sh \
  --bootstrap-server kafka.example.internal:9092 \
  --describe \
  --topic orders

# List topics returned by the broker
kafka-topics.sh \
  --bootstrap-server kafka.example.internal:9092 \
  --list
```

If `--describe` reports that the topic does not exist, compare the topic name against the application configuration and check the provisioning step. If the command cannot connect, investigate DNS, network, TLS/SASL, and broker status before concluding the topic is missing.

When the topic exists but the listener still does not process messages, proceed to inspect the consumer group:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka.example.internal:9092 \
  --describe \
  --group order-service
```

This command helps inspect partition assignment, committed offsets, and lag. The fact that a topic exists does not mean the consumer has been assigned partitions or is reading successfully.

## 5. Integrating topic status into health and readiness

Broker health and the existence of a specific topic are two different checks. The Kafka health indicator provided by Spring Boot (if enabled in the version and configuration in use) is useful for detecting cluster connectivity issues. However, brokers can be operating normally while the `orders` topic has not yet been created.

If one or more topics are mandatory for the service to operate, add a health indicator that checks the metadata of those exact topics. Kafka's `AdminClient` provides the `describeTopics` API for this purpose.

Create an `AdminClient` using the same Kafka administration configuration as the application:

```java
@Configuration
class KafkaHealthConfiguration {

    @Bean(destroyMethod = "close")
    AdminClient topicHealthAdminClient(KafkaAdmin kafkaAdmin) {
        return AdminClient.create(kafkaAdmin.getConfigurationProperties());
    }
}
```

Then create the health indicator. The example below checks two required topics, limits the total wait time to about two seconds, and distinguishes a missing topic from other errors:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.TopicDescription;
import org.apache.kafka.common.KafkaFuture;
import org.apache.kafka.common.errors.UnknownTopicOrPartitionException;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("kafkaTopics")
final class KafkaTopicsHealthIndicator implements HealthIndicator {

    private static final Set<String> REQUIRED_TOPICS =
            Set.of("orders", "payments");

    private static final long TIMEOUT_NANOS =
            TimeUnit.SECONDS.toNanos(2);

    private final AdminClient admin;

    KafkaTopicsHealthIndicator(AdminClient admin) {
        this.admin = admin;
    }

    @Override
    public Health health() {
        final Map<String, KafkaFuture<TopicDescription>> descriptions;

        try {
            descriptions = admin.describeTopics(REQUIRED_TOPICS).topicNameValues();
        } catch (RuntimeException ex) {
            // For example: the client cannot connect yet or the AdminClient configuration is invalid.
            return Health.down(ex).build();
        }

        List<String> available = new ArrayList<>();
        List<String> missing = new ArrayList<>();
        long deadline = System.nanoTime() + TIMEOUT_NANOS;

        for (var entry : descriptions.entrySet()) {
            long remaining = deadline - System.nanoTime();
            if (remaining <= 0) {
                return Health.down()
                        .withDetail("reason", "Timed out while checking required topics")
                        .build();
            }

            try {
                entry.getValue().get(remaining, TimeUnit.NANOSECONDS);
                available.add(entry.getKey());
            } catch (ExecutionException ex) {
                Throwable cause = ex.getCause();

                if (cause instanceof UnknownTopicOrPartitionException) {
                    missing.add(entry.getKey());
                } else {
                    // For example: an ACL error or other metadata error must not be treated as a missing topic.
                    return Health.down(cause)
                            .withDetail("topic", entry.getKey())
                            .build();
                }
            } catch (TimeoutException ex) {
                return Health.down(ex)
                        .withDetail("topic", entry.getKey())
                        .build();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return Health.down(ex).build();
            }
        }

        if (!missing.isEmpty()) {
            return Health.down()
                    .withDetail("missingTopics", missing)
                    .withDetail("availableTopics", available)
                    .build();
        }

        return Health.up()
                .withDetail("topics", available)
                .build();
    }
}
```

This is a baseline example; in a real application, the topic list should come from environment-specific configuration rather than being hard-coded. If the Kafka client version in use throws a different exception type for a non-existent topic, handle it according to that actual exception. Do not turn `TopicAuthorizationException`, timeouts, or broker errors into a "topic does not exist" result.

`AdminClient` is an administrative client with network connections. Create a reusable bean and close it when the application context stops, as in the example above; do not create a new client on every health endpoint call. Keep the list of checked topics short and timeouts finite so probes do not hang when the cluster experiences issues.

### Attaching the health indicator to Spring Boot readiness

With Spring Boot Actuator, enable health probes and add the `kafkaTopics` indicator to the readiness group:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,kafkaTopics
      show-details: when_authorized
```

Kubernetes can call:

- `/actuator/health/readiness`: only receives a ready status when `readinessState` and all mandatory checks in the group pass.
- `/actuator/health/liveness`: checks whether the process is still alive.

Do not add Kafka to the liveness group just because a broker or topic is failing. If liveness depends on Kafka, an external outage can cause Kubernetes to repeatedly restart an otherwise healthy application. Readiness is designed to stop routing traffic or new work to an instance while a dependency is not ready.

If a topic only serves an optional feature, do not include it in the overall service readiness. Check only the topics truly required for core functionality, or expose a separate degraded status for that feature.

## 6. Understanding the meaning of readiness results

When `kafkaTopics` returns `UP`, it only confirms that the application was able to query metadata and that the listed topics exist under the permissions `AdminClient` has. It does not prove:

- That the consumer has joined the group and been assigned partitions.
- That the application has `READ`, `WRITE`, or other permissions required for each business workflow.
- That partitions have a stable leader, replicas are in sync, or durability configuration meets requirements.
- That the producer can write messages and the consumer can process messages end-to-end.

If the service should only be considered ready after the listener receives partitions, add a separate check based on listener/container state or partition assignment events. Do not infer consumer state from `describeTopics` alone.

The health endpoint can also be called frequently by multiple probes. For large clusters or long topic lists, consider caching the result for a short period and tracking health check response times. Do not allow a single probe to generate a large volume of administrative requests to Kafka.

## 7. Procedure when readiness reports a non-existent topic

1. Read the health indicator details to identify which topic is missing.
2. Obtain the exact `bootstrap.servers`, topic name, and principal from the failing instance's configuration.
3. Run `kafka-topics.sh --describe` against that exact cluster to verify metadata.
4. If the topic truly does not exist, inspect the manifest or provisioning workflow: name, partitions, replication factor, and topic config.
5. If the topic exists but the application cannot see it, check the `DESCRIBE` ACL and required `READ`/`WRITE` permissions; also check TLS/SASL if authentication errors occur.
6. After provisioning or fixing configuration, verify that readiness transitions to `UP`, the listener receives partition assignments, and the consumer group begins operating.

You can use the following table to guide investigation steps:

| Observed Result | Remediation Direction |
|---|---|
| `UnknownTopicOrPartitionException` | Check topic name, cluster, and topic creation step |
| `TopicAuthorizationException` | Check principal and ACLs for the topic |
| Timeout or disconnect | Check broker, network, DNS, TLS/SASL, and timeout |
| `LeaderNotAvailableException` | Check partition status, leader election, and broker |
| Topic exists but consumer receives no messages | Check group, assignment, offsets, read permissions, and listener logic |

A stable deployment workflow typically provisions topics first, then starts the service and uses readiness to confirm required dependencies are ready. If the service is allowed to start before its topics exist, set `missingTopicsFatal` according to that policy and let readiness continue reporting unready until the topics appear.
