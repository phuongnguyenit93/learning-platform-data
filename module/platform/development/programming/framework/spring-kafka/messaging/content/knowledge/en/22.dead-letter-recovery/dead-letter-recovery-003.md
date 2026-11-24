# Determining the Dead-Letter Topic Name

## 1. What Is a Dead-Letter Topic Used For?

In Spring Kafka, when a listener fails to process a record and retries are exhausted, the application can move the record to a separate topic for later investigation or recovery. This topic is commonly called a dead-letter topic (DLT), and sometimes a dead-letter queue (DLQ).

For example, the `order-projection` consumer group reads from the `orders` topic. A record has a valid payload at the Kafka level but cannot be transformed or persisted to the database. After the configured number of retries, `DeadLetterPublishingRecoverer` can send the record to `orders.DLT`. The main-stream consumer continues with the next record according to the recovery policy.

A DLT isolates records that require investigation from the normal processing flow. It does not automatically fix data, guarantee that the record will be reprocessed, or replace logging, alerting, or operational procedures.

## 2. Spring Kafka's Default DLT Name

`DeadLetterPublishingRecoverer` lets you specify a function to determine the destination topic and partition. When using the default constructor that only takes a Kafka template, Spring Kafka applies the following convention:

- The destination topic is the original topic name plus the `.DLT` suffix.
- The destination partition is the original record's partition.

Example:

| Source topic | Source partition | Default DLT | DLT partition |
|---|---:|---|---:|
| `orders` | 0 | `orders.DLT` | 0 |
| `orders` | 3 | `orders.DLT` | 3 |
| `payments` | 1 | `payments.DLT` | 1 |
| `inventory.events` | 2 | `inventory.events.DLT` | 2 |

This convention is predictable: looking at the DLT name tells you which topic the record came from. When preserving the partition, the DLT needs enough partitions to accept every source partition. If `orders` has 6 partitions, `orders.DLT` needs at least 6 partitions to map partitions 0 through 5.

Do not confuse a DLT name with a retry topic name. A retry topic typically holds records to be retried after a delay; a DLT stores records that have exhausted the retry policy or are determined to be unprocessable in the current flow.

~~~mermaid
flowchart TD
    A["Topic orders"] --> B["Consumer group order-projection"]
    B --> C{"Listener processing succeeded?"}
    C -->|Yes| D["Commit offset per AckMode"]
    C -->|No| E["DefaultErrorHandler"]
    E --> F{"Retries remaining?"}
    F -->|Yes| G["Backoff then invoke listener again"]
    G --> C
    F -->|No| H["DeadLetterPublishingRecoverer"]
    H --> I["Topic orders.DLT"]
    I --> J["Investigate / fix data / controlled replay"]
~~~

## 3. Configuring the Destination Topic and Partition with DeadLetterPublishingRecoverer

When you want to explicitly specify naming rules, use the constructor that takes a destination resolver. The resolver receives the original record and exception, then returns a `TopicPartition` containing the target topic name and partition.

~~~java
import org.apache.kafka.common.TopicPartition;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;

@Configuration
public class DeadLetterConfiguration {

    @Bean
    DeadLetterPublishingRecoverer deadLetterPublishingRecoverer(
            KafkaTemplate<Object, Object> dltKafkaTemplate) {

        var recoverer = new DeadLetterPublishingRecoverer(
            dltKafkaTemplate,
            (record, exception) -> new TopicPartition(
                record.topic() + ".DLT",
                record.partition()
            )
        );

        // Do not treat recovery as successful if sending to DLT fails.
        recoverer.setFailIfSendResultIsError(true);

        return recoverer;
    }
}
~~~

The resolver in this example explicitly expresses the default rule: take the original topic, append `.DLT`, and preserve the partition. Explicit declaration is helpful when you later need to change the naming convention or add routing by error type.

`setFailIfSendResultIsError(true)` instructs the recoverer to raise an error if publishing to the DLT fails. If DLT publishing fails, the record has not been safely recovered; the error handler should continue treating it as a recovery failure rather than silently ignoring it. Verify the API against your Spring Kafka version.

## 4. Attaching the Recoverer to DefaultErrorHandler

The recoverer is typically invoked after listener retries are exhausted. The `DefaultErrorHandler` bean must be attached to the listener container factory used by the listener:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

@Bean
DefaultErrorHandler kafkaErrorHandler(
        DeadLetterPublishingRecoverer deadLetterPublishingRecoverer) {

    return new DefaultErrorHandler(
        deadLetterPublishingRecoverer,
        new FixedBackOff(1000L, 2L)
    );
}

@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>
        orderKafkaListenerContainerFactory(
                ConsumerFactory<String, OrderCreatedEvent> consumerFactory,
                DefaultErrorHandler kafkaErrorHandler) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(kafkaErrorHandler);
    return factory;
}
~~~

Listener referencing this factory:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "order-projection",
    containerFactory = "orderKafkaListenerContainerFactory"
)
public void handle(OrderCreatedEvent event) {
    orderProjectionService.apply(event);
}
~~~

`FixedBackOff(1000L, 2L)` illustrates waiting one second between retries, with at most two additional retry attempts after the initial invocation. Once retries are exhausted, the error handler calls the recoverer to publish to the DLT.

If a listener uses a different factory, configure the error handler on that exact factory. Merely declaring a recoverer bean without attaching the error handler to the container will not automatically move failed records to the DLT.

## 5. Common DLT Naming Conventions

There is no single mandatory suffix for every system. What matters is that topic names are stable, predictable, and agreed upon by producers, consumers, and operations.

| Convention | Example for topic `orders` | When suitable |
|---|---|---|
| By source topic | `orders.DLT` | Simple default; consumer groups can share a single DLT for errors |
| By topic and consumer group | `orders.order-projection.DLT` | Each subscriber needs its own error queue and replay permissions |
| By topic and error category | `orders.invalid.DLT`, `orders.dependency.DLT` | Different handling workflows exist for stable error categories |
| With environment namespace | `prod.orders.DLT` | Multiple environments share a single Kafka cluster |
| By domain then topic | `commerce.orders.DLT` | Topics are organized by domain or bounded context |

### Using one shared DLT per source topic

`orders.DLT` is a simple choice when failed records need centralized investigation. If multiple consumer groups read from `orders`, their failed records can all be sent to this shared DLT.

The advantage is fewer topics and easier lookup of failed records. However, the DLT operations consumer needs to know which group failed on the record; original metadata added by the recoverer can help with this. Teams also need to agree on access permissions and replay procedures.

Spring Kafka adds dead-letter headers to store original record info and the recovery cause, such as original topic, partition, offset, and exception type. The DLT consumer can read this metadata to identify the record's origin; the DLT topic name and source headers complement each other.

### Separating DLTs by consumer group

If `order-projection` and `fraud-monitor` have different owners, SLAs, and recovery processes, you can split them:

- `orders.order-projection.DLT`
- `orders.fraud-monitor.DLT`

This reduces the risk of one team accidentally replaying records belonging to another team. However, Kafka group IDs may contain characters unsuitable for topic naming rules or be overly long. If embedding the group in the DLT name, use a short, stable, explicitly configured identifier rather than arbitrarily concatenating raw group IDs.

The resolver needs to know which subscriber it serves. Typically, you create a separate recoverer per container or pass a stable subscriber identifier into the recoverer configuration.

~~~java
@Bean
DeadLetterPublishingRecoverer orderProjectionRecoverer(
        KafkaTemplate<Object, Object> dltKafkaTemplate) {

    String subscriber = "order-projection";

    return new DeadLetterPublishingRecoverer(
        dltKafkaTemplate,
        (record, exception) -> new TopicPartition(
            record.topic() + "." + subscriber + ".DLT",
            record.partition()
        )
    );
}
~~~

In this example, `subscriber` is a static configuration of the recoverer. Do not infer the consumer group from untrusted payload fields or headers.

### Separating DLTs by error category

You can route errors that have different recovery paths:

- `orders.invalid.DLT` stores invalid payloads or contract violations.
- `orders.dependency.DLT` stores records that exhausted retries due to downstream dependencies.
- `orders.processing.DLT` stores remaining processing errors requiring investigation.

Only create a small, stable set of error categories with clear owners and workflows. Do not create topics per exception name, event ID, or individual request; that inflates topic counts, ACLs, configurations, and operational overhead.

## 6. Resolver Routing by Error Type

A destination resolver can inspect the exception to choose a DLT. The following example demonstrates two error categories: invalid data and remaining processing errors.

~~~java
import org.apache.kafka.common.TopicPartition;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;

@Bean
DeadLetterPublishingRecoverer categorizedRecoverer(
        KafkaTemplate<Object, Object> dltKafkaTemplate) {

    return new DeadLetterPublishingRecoverer(
        dltKafkaTemplate,
        (record, exception) -> {
            String suffix =
                exception instanceof InvalidOrderEventException
                    ? ".invalid.DLT"
                    : ".failed.DLT";

            return new TopicPartition(
                record.topic() + suffix,
                record.partition()
            );
        }
    );
}
~~~

This is a minimal example. In real applications, exceptions may be wrapped by listener adapter or framework exceptions. If you need to classify by root cause, traverse the cause chain with a bound and use distinct business exceptions. Do not rely on exception message strings because messages can change across versions or locales.

If a transient error is recoverable, retry with backoff or use delayed retry topics instead of sending it straight to the DLT. A DLT is intended for records that have exhausted the retry policy or errors that cannot be resolved automatically.

## 7. Keep or Change Partition When Moving to DLT?

There are two primary strategies.

| Strategy | What the resolver returns | Result |
|---|---|---|
| Keep source partition | `new TopicPartition(dltTopic, record.partition())` | Record in source partition Pn goes to DLT partition Pn |
| Let producer choose partition | `new TopicPartition(dltTopic, -1)` | Kafka producer selects partition by key/partitioner |

Keeping the source partition is useful when you want easy correlation and to preserve partition alignment between the main topic and the DLT. With this approach, the DLT must have a matching partition for every source partition.

Returning partition `-1` lets the producer choose the partition using its partitioner mechanism. This can be useful when the DLT has a different partition count from the source topic, though records are no longer mapped to the same partition index. Do not rely on this if operational workflows require 1:1 partition correlation or ordering by source partition.

Even when preserving the partition, the DLT is still a separate topic. There is no global ordering between the source topic and the DLT. If business ordering is required, design around keys, partitions, and an appropriate replay procedure.

## 8. Creating the DLT Topic and Operational Settings

Naming a topic in the resolver does not automatically ensure the topic exists. You must create the DLT before failed records are published or configure a controlled topic creation mechanism.

You can declare a `NewTopic` bean in Spring Kafka:

~~~java
import org.apache.kafka.clients.admin.NewTopic;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class DeadLetterTopicConfiguration {

    @Bean
    NewTopic ordersDltTopic() {
        // Example: source topic has 6 partitions.
        return new NewTopic("orders.DLT", 6, (short) 3);
    }
}
~~~

Spring Boot normally configures `KafkaAdmin` to create `NewTopic` beans on application startup. Partition counts and replication factors in the example are illustrative: a DLT preserving source partitions needs enough matching partitions, and the replication factor must not exceed the number of eligible brokers in the cluster.

In production, many organizations manage topics via Infrastructure as Code or Kafka administration workflows rather than letting every application auto-create topics. Whichever approach you use, verify the topic exists before enabling a consumer that may publish to the DLT.

Operational properties to define upfront:

- **Partitions:** enough to map source partitions if the resolver preserves partitions.
- **Replication factor:** aligned with broker count and durability requirements.
- **Retention:** long enough to allow detection, investigation, and replay.
- **Cleanup policy:** usually `delete` to retain individual failed records over time; use compaction only when intentionally keeping only the latest state per key.
- **ACL:** the main consumer group needs write access to the DLT; the investigation team needs read access; the replay process needs read access to the DLT and write access to the target topic.
- **Monitoring:** track new record counts, growth rate, oldest record age, and DLT publish failures.

Do not set retention too short such that failed records expire before the responsible team investigates. Nor should you retain them indefinitely without a capacity, triage, and data deletion policy.

## 9. DLT Naming and Deployment Environments

If multiple environments share a cluster, add an environment namespace to topic names so producers or consumers in one environment do not accidentally read data from another.

Example:

| Environment | Source topic | DLT |
|---|---|---|
| Local | `local.orders` | `local.orders.DLT` |
| Test | `test.orders` | `test.orders.DLT` |
| Staging | `staging.orders` | `staging.orders.DLT` |
| Production | `prod.orders` | `prod.orders.DLT` |

Another option is using separate clusters per environment and keeping topic names short such as `orders`/`orders.DLT`. Pick one consistent convention across the entire platform.

Do not embed profiles, pod IDs, or build numbers into DLT names. Topic names must remain stable across deployments so operations teams can still find older failed records.

## 10. Kafka Topic Name Validity Rules and Limits

Topic names must comply with Kafka broker rules. Key points to remember:

- Topic names have a maximum length of 249 characters.
- ASCII alphanumeric characters, period `.`, underscore `_`, and hyphen `-` are the standard supported characters.
- Do not use exact names `.` or `..`.
- Topic names are case-sensitive; `orders.DLT` and `orders.dlt` are two distinct names.
- Avoid names starting with `__` because that prefix is normally reserved for Kafka internal topics.

When combining a source name with a suffix, check the final length. A source topic already near the limit can cause the DLT name to exceed 249 characters. Impose a length limit on source topic names or use a shorter suffix per contract.

Do not normalize topic names differently between producer and consumer. Changing from `.DLT` to `.dlt` must be treated as a configuration/contract change with a corresponding plan for data migration, ACLs, consumers, and retention.

## 11. Testing DLT Name Resolution Rules

Unit-test the destination resolver independently to ensure the target topic name and partition match the contract.

Example testing an application-defined resolver function. Extracting the destination rule into a method lets you unit-test the output directly:

~~~java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.TopicPartition;

final class DeadLetterDestination {

    private DeadLetterDestination() {
    }

    static TopicPartition defaultDltDestination(
            ConsumerRecord<?, ?> record) {
        return new TopicPartition(
            record.topic() + ".DLT",
            record.partition()
        );
    }
}
~~~

Unit test for the rule above:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.junit.jupiter.api.Test;

class DeadLetterDestinationTest {

    @Test
    void appendsDltSuffixAndKeepsOriginalPartition() {
        var record = new ConsumerRecord<String, String>(
            "orders",
            2,
            100L,
            "ORD-1001",
            "{\"orderId\":\"ORD-1001\"}"
        );

        var destination = DeadLetterDestination.defaultDltDestination(record);

        assertThat(destination.topic()).isEqualTo("orders.DLT");
        assertThat(destination.partition()).isEqualTo(2);
    }
}
~~~

If using a custom resolver, extract it into a bean or standalone method to unit-test cases such as:

- Different source topics.
- Source partitions at the start, middle, and end of the partition range.
- DLT names by consumer group or error category.
- Both retryable and non-retryable exception types.
- Resulting names staying within Kafka topic length limits.
- Partition `-1` when you want the producer to choose the partition.

Integration tests should create source and DLT topics on Embedded Kafka or Testcontainers, make the listener fail in a controlled way, and verify that the record actually lands on the expected topic/partition. Verify key, value, original headers, and exception metadata.

In particular, test cases where the DLT does not exist, lacks partitions, or the producer lacks write permission. Recovery should only be considered complete once the record has been published according to the application's acknowledgement policy.

## 12. Common Mistakes When Naming DLTs

| Symptom | Cause | Fix |
|---|---|---|
| `InvalidTopicException` | Name contains invalid characters or exceeds length limit | Check Kafka naming rules and length after appending suffix |
| Target partition not found | DLT has fewer partitions than source topic while resolver keeps original partition | Create enough partitions or pick a partitioner intentionally |
| DLT publish fails | Topic does not exist, ACL missing, or broker error | Create the topic beforehand, grant permissions, and monitor send results |
| Teams overwrite/mix errors | Multiple consumer groups share `<topic>.DLT` | Separate DLT by subscriber if independent ownership is needed |
| Too many DLT topics | Topics created per exception, event ID, or tenant | Use a small set of stable, owned error categories |
| Cannot trace record origin | Topic name does not indicate original topic and metadata is missing | Keep clear naming conventions and verify DLT headers |
| Failed records deleted before handling | Retention is too short | Set retention based on investigation and replay SLAs |

## 13. Dead-Letter Topic Naming Checklist

- [ ] Choose one stable naming convention across the entire system.
- [ ] If using Spring Kafka defaults, understand the `<source-topic>.DLT` convention.
- [ ] Decide whether DLTs are shared per topic or separated by consumer group.
- [ ] Only split by error category when clear workflows and owners exist.
- [ ] Decide whether to keep the source partition or let the producer choose the partition.
- [ ] If keeping the partition, create the DLT with at least as many partitions as the source topic.
- [ ] Pre-create the topic and verify replication factor, ACLs, and retention.
- [ ] Verify the topic name after appending the suffix remains valid and within length limits.
- [ ] Distinguish DLTs from delayed retry topics.
- [ ] Enable failure handling when DLT publishing fails and test recovery.
- [ ] Monitor DLT count, record age, and growth rate.
- [ ] Establish a controlled investigation, data-fix, and replay workflow.

A DLT name should reveal which topic the record came from and which error-handling flow it belongs to. The `<source-topic>.DLT` convention is an easy-to-operate starting point; when isolation by consumer group or error category is needed, use a destination resolver with stable names and ensure proper partitions and topic configuration. Naming is only valuable when paired with clear access controls, retention, monitoring, and recovery procedures.
