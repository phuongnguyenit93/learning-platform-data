# Separating Producer and Consumer Configuration in Spring Kafka

## 1. Why Separate Producer and Consumer Configuration?

A **Spring Kafka** application can act as both a **producer** (sending records to Kafka) and a **consumer** (receiving records from Kafka). Both roles operate on the same platform, yet their reliability, performance, security, and operational requirements differ.

Consider a payment processing service:

```text
                                  payment-service
                   +-------------------------------------+
                   |                                     |
Payment commands   |  Consumer                          |
Kafka topic ------>|  @KafkaListener                     |
                   |        |                            |
                   |        v                            |
                   |  Validate + DB transaction          |
                   |        |                            |
                   |        v                            |
                   |  Producer                          |-----> payment-results
                   |  KafkaTemplate                      |       Kafka topic
                   |                                     |
                   +-------------------------------------+
```

Putting everything into one shared block and applying the same parameters to both sides leads to easy misconceptions:

- `acks`, `linger.ms`, `delivery.timeout.ms`, and `enable.idempotence` apply only to the **producer**.
- `group.id`, `auto.offset.reset`, `enable.auto.commit`, and `max.poll.records` apply only to the **consumer**.
- `concurrency` is a **listener container** setting, not a producer thread count.
- Kafka producer `retries` is not the same as business-level retries inside a listener or HTTP/DB retries.
- Shared properties like `bootstrap.servers` and `security.protocol` may match when both sides use the same cluster, but need not match when connecting to different clusters or principals.

**Separated configuration** means placing each parameter on the right component with clear ownership and operational policy. Separation **does not imply** you must always split into two applications or two Kafka clusters.

### After This Lesson, You Will Be Able To

1. Separate `spring.kafka.producer.*`, `spring.kafka.consumer.*`, and `spring.kafka.listener.*` in Spring Boot.
2. Decide when auto-configuration suffices and when dedicated `ProducerFactory`, `ConsumerFactory`, `KafkaTemplate`, and `ConcurrentKafkaListenerContainerFactory` beans are needed.
3. Build an application consuming from cluster A and producing to cluster B without mixing up credentials, offsets, or topics.
4. Understand the boundaries among producer delivery, listener processing, offset commits, retries, DLT, and Kafka transactions.
5. Design profiles, secrets, config validation, readiness, telemetry, and independent testing for both sides.

**Example scope:** Java 17+, Spring Boot 3.x, and Spring Kafka 3.x. Exact property names and APIs should be checked against your stack's minor version; the examples do not represent every released version of Spring Kafka.

## 2. Four Configuration Layers to Distinguish

Kafka configuration in a Spring application typically spans multiple layers:

| Layer | Components | Purpose |
|---|---|---|
| **Common Kafka client** | `bootstrap.servers`, TLS/SASL, DNS, client ID | How to connect and authenticate |
| **Producer client** | `ProducerConfig`, `ProducerFactory`, `KafkaTemplate` | Sending records, serializers, acks, retries, transactions |
| **Consumer client** | `ConsumerConfig`, `ConsumerFactory` | Reading records, deserializers, group, fetch/poll, isolation |
| **Spring listener container** | `ConcurrentKafkaListenerContainerFactory`, `@KafkaListener` | Concurrency, ack mode, error handler, DLT/recovery |

Relationship:

```text
Spring Boot application
  |
  +-- Kafka configuration (common)
  |      bootstrap, common security
  |
  +-- Producer-specific config
  |      |
  |      +-- ProducerFactory
  |              |
  |              +-- KafkaTemplate
  |                      |
  |                      +-- send(...) -> Kafka broker
  |
  +-- Consumer-specific config
         |
         +-- ConsumerFactory
                 |
                 +-- ListenerContainerFactory
                         |
                         +-- @KafkaListener -> Kafka broker
```

When using Spring Boot auto-configuration, Boot can create most of these beans from `spring.kafka.*`. If the application declares a custom bean of the same type, certain auto-configured beans may **back off**. Always verify actual bean wiring rather than assuming a custom `ProducerFactory` automatically runs alongside every default bean.

## 3. Common Case: Same Cluster, Role-Specific Configuration

Suppose both producer and consumer connect to a shared Kafka cluster. Use hierarchical configuration instead of mixing every property into an undifferentiated map.

```yaml
spring:
  application:
    name: payment-service

  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}

    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
      acks: all
      properties:
        "[enable.idempotence]": true
        "[max.in.flight.requests.per.connection]": 5
        "[linger.ms]": 5
        "[delivery.timeout.ms]": 120000
        "[request.timeout.ms]": 30000

    consumer:
      group-id: payment-commands-v1
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      enable-auto-commit: false
      auto-offset-reset: earliest
      properties:
        "[max.poll.records]": 200
        "[max.poll.interval.ms]": 300000

    listener:
      ack-mode: record
      concurrency: 3
```

This is an **illustrative** configuration, not optimal defaults for every system. `${...}` placeholders follow Spring Boot environment syntax, such as `${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}`.

Meaning:

- `spring.kafka.bootstrap-servers`: shared endpoint when producer and consumer use the same cluster.
- `spring.kafka.producer.*`: policies for the **sending** client.
- `spring.kafka.consumer.*`: policies for the **reading** client.
- `spring.kafka.listener.*`: behavior of the container managing `@KafkaListener`.
- `properties`: passes advanced Kafka client properties down to the Kafka library; bracketed keys help Spring Boot bind map keys containing dots.

We have not placed business retries or DLT settings in YAML here because they typically require a separately configured **error handler/recoverer**. Kafka producer retries and listener retries are not the same mechanism.

### 3.1. Shared Properties and Role-Specific Overrides

Example:

```yaml
spring:
  kafka:
    bootstrap-servers: kafka-common:9092

    producer:
      bootstrap-servers: kafka-producer:9092

    consumer:
      bootstrap-servers: kafka-consumer:9092
```

In Spring Boot versions supporting per-role bootstrap properties, specific producer/consumer configs can override the shared value. That **does not mean** swapping two addresses completes a multi-cluster setup: credentials, truststores, ACLs, topic admin, DLT, and transactions must also target the right cluster.

When sharing a cluster and credentials, placing addresses and security at the common level reduces duplication. When there are **two independent security domains**, never rely on shared properties being accidentally inherited; design separate factories and control each config map explicitly.

### 3.2. Do Not Misplace Kafka Properties

| Property | Right Place | What Happens If Misused? |
|---|---|---|
| `acks=all` | Producer | Putting it on the consumer does not change send acknowledgment policy |
| `enable.idempotence=true` | Producer | Does not make the listener process messages "exactly once" |
| `group.id` | Consumer | Producers do not belong to consumer groups to commit offsets |
| `max.poll.records` | Consumer | Does not control the batch size sent by the producer |
| `auto.offset.reset` | Consumer | Does not reset an existing committed offset |
| `ack-mode=record` | Listener container | Not equivalent to Kafka producer `acks=all` |
| `concurrency=3` | Listener container | Does not create 3 producers or 3 partitions |
| `transaction-id-prefix` | Producer/Spring transaction setup | Does not automatically create transactions across DB and two clusters |

**Rule:** if you cannot explain whether a parameter affects the **send side, read side, or callback processing side**, do not put it in shared configuration yet.

## 4. Producer: Configuration Focused on Durable Delivery

The producer serializes keys/values, determines partitions, and sends records. A successful Java send call **does not mean** the broker has acknowledged the record.

Key properties:

| Property | Meaning | Things to Note |
|---|---|---|
| `bootstrap.servers` | Initial brokers for fetching metadata | Must point to the right cluster |
| `key.serializer` | Converts keys to bytes | Keys influence partitioning |
| `value.serializer` | Converts values to bytes | Must match consumer contract |
| `acks` | Broker acknowledgment level | `all` favors durability over `0` |
| `enable.idempotence` | Limits duplicates from producer retries under Kafka-supported conditions | Does not deduplicate fresh business send calls |
| `retries` | Kafka client retries for retryable errors | Bounded by delivery timeout/policy |
| `delivery.timeout.ms` | Upper bound for client record delivery | Must coordinate with request timeout and linger |
| `request.timeout.ms` | Timeout waiting for a broker response | Should not be confused with a job timeout |
| `linger.ms` | Delay to batch records before sending when applicable | Throughput vs. latency trade-off |
| `batch.size` | Max per-partition send buffer size in bytes | **Not Kafka record count or Spring Batch chunk size** |
| `compression.type` | Payload compression | Trades CPU for network/disk savings |
| `max.in.flight.requests.per.connection` | Unacknowledged requests per connection | Must align with idempotence/ordering |

### 4.1. `acks=all` Is Not Application-Wide Exactly-Once

`acks=all` requires the partition leader to wait for acknowledgments per the ISR policy, offering stronger durability than `acks=0` under proper conditions. However, actual durability still depends on replication factor, `min.insync.replicas`, ISR health, and cluster operations.

`enable.idempotence=true` helps the producer avoid certain duplicates generated by **internal Kafka producer retries** via producer ID/sequence tracking. It **does not** guarantee that:

- The application never calls `KafkaTemplate.send(...)` twice for the same event.
- The database committed or did not commit.
- The consumer processes only once.
- No duplicates occur across an application restart triggering a fresh business send.
- A transaction spans two Kafka clusters simultaneously.

If the application producer can re-emit an event after a crash, you need an **event ID/idempotency key** and durable state storage, typically paired with a transactional outbox.

### 4.2. Optimizing Throughput Without Sacrificing Stability

For instance, a high-volume audit producer may experiment with higher `linger.ms` or compression, while a real-time payment command producer may prioritize low latency.

Benchmark settings against payload size, partition count, network latency, broker quotas, and SLAs. Never copy the same `batch.size` across every topic without knowing message sizes and latency targets.

## 5. Consumer: Configuration Focused on Safe Processing and Offsets

Consumers read records within a consumer group; Kafka stores committed offsets per group/topic/partition.

Key properties:

| Property | Meaning | Things to Note |
|---|---|---|
| `group.id` | Consumer group identifier | Governs partition assignment and committed offsets |
| `key.deserializer` | Converts bytes to keys | Must match producer |
| `value.deserializer` | Converts bytes to values | Deserialization errors can happen before the listener |
| `enable.auto.commit` | Kafka client commits offsets on a timer | Usually set to `false` when listeners commit based on processing outcomes |
| `auto.offset.reset` | Starting position **when no valid offset exists** | Not a replay button for every run |
| `max.poll.records` | Maximum records returned per poll | Not equal to thread count or partition count |
| `max.poll.interval.ms` | Max gap between polls for poll-loop processing | Slow listeners can trigger group rebalances |
| `fetch.min.bytes` / `fetch.max.wait.ms` | Fetch batching vs. latency trade-off | Workload dependent |
| `isolation.level` | `read_uncommitted` or `read_committed` | `read_committed` skips records from aborted Kafka transactions |
| `client.id` | Identifier for client observability | Separate by role when metrics/diagnostics need clarity |

`enable-auto-commit=false` is standard when using a Spring Kafka listener container with an explicit ack mode. In that mode, the **container** coordinates offset commits according to the ack mode and error handler. Never conclude that offset commits are completely disabled just because this client property is `false`.

### 5.1. `auto.offset.reset=earliest` Does Not Reset Committed Offsets

Example:

```text
Topic: payment-commands, partition 0

Kafka offsets:
0 1 2 3 4 5 6 7 8 9

Consumer group payment-service-v1 has committed offset 7
(meaning next position = 7).

Restart consumer in the same group:
  -> resumes at committed position, does not revert to offset 0.

Brand new consumer group, no committed offset yet:
  auto.offset.reset=earliest -> starts from the earliest retained offset.
```

To replay an existing group, follow a controlled seek/reset-offset procedure and account for duplicate side effects. Switching `earliest` to `latest` is not a deduplication fix.

### 5.2. Committing Offsets After Processing Yields At-Least-Once, Not DB Exactly-Once

When a listener processes a record and commits the offset **after** business logic completes, a failure window exists:

```text
Consumer receives event E-101
          |
          v
Database update succeeds
          |
          v
JVM crashes before offset commit
          |
          v
Kafka redelivers E-101 after restart/rebalance
```

This is why **at-least-once delivery** requires idempotent business processing. An inbox table or unique business event ID prevents updating the DB twice even when the consumer re-reads a record.

Committing offsets **before** side effects finish creates the opposite risk: losing events if the process dies. Always document the commit point in your design and test failure scenarios.

## 6. Listener Container: Where Consumer Retry/Ack/Concurrency Live

In Spring Kafka, `KafkaConsumer` merely polls messages and participates in the group. `@KafkaListener` is driven by a **listener container**; choices like ack mode, concurrency, and error handlers apply at this layer.

For a single cluster, Spring Boot can configure the container from:

```yaml
spring:
  kafka:
    listener:
      ack-mode: record
      concurrency: 3
```

`record` typically corresponds to committing after each record is processed successfully per container semantics; when a listener throws an exception, the error handler governs retries, seeking/recovery, or DLT routing.

Other modes include `batch`, `manual`, and `manual_immediate`, each with specific behavior. Never change `ack-mode` just to cut commit calls without understanding error, rebalance, and duplicate consequences.

### 6.1. Concurrency Cannot Exceed Partition Count Benefits

Suppose a topic has 3 partitions and a consumer group runs a listener container with `concurrency=8`. Within that group, each partition is assigned to at most one consumer at a time, so 8 consumers cannot simultaneously read from 3 partitions. Extra consumers sit idle.

Conversely, increasing partition count affects ordering because Kafka preserves record order **within a partition**, not across the entire topic. If the key is `paymentId` and per-payment update ordering matters, the producer must use a stable key so records for the same payment route consistently, assuming partitioning and partition counts do not change in ways that alter distribution.

Configuration docs should record partition counts and the rationale for concurrency rather than assuming more threads are always better.

## 7. Minimal Java Example with Spring Boot Auto-Configuration

When producer and consumer share one cluster, you do not have to manually declare every factory bean. Spring Boot can build `KafkaTemplate` and the default listener container from YAML.

### 7.1. Producer Calling `KafkaTemplate`

```java
import java.util.concurrent.CompletableFuture;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

@Service
public final class PaymentResultPublisher {

    private static final Logger log =
            LoggerFactory.getLogger(PaymentResultPublisher.class);

    private final KafkaTemplate<String, String> kafkaTemplate;

    public PaymentResultPublisher(
            KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, String>> publish(
            String paymentId,
            String jsonPayload) {

        CompletableFuture<SendResult<String, String>> future =
                kafkaTemplate.send(
                        "payment-results.v1",
                        paymentId,
                        jsonPayload
                );

        future.whenComplete((result, error) -> {
            if (error != null) {
                log.error(
                        "Kafka send failed for paymentId={}",
                        paymentId,
                        error
                );
            } else {
                log.info(
                        "Kafka record acknowledged: topic={}, "
                                + "partition={}, offset={}",
                        result.getRecordMetadata().topic(),
                        result.getRecordMetadata().partition(),
                        result.getRecordMetadata().offset()
                );
            }
        });

        return future;
    }
}
```

In Spring Kafka 3.x, `KafkaTemplate.send(...)` returns `CompletableFuture<SendResult<K,V>>`. Calling `send` only **initiates an asynchronous send**; business code needing confirmed delivery must observe the future or use an outbox when durability across crashes is required.

**Do not place a long blocking `send(...).get()` inside every listener** just to "be sure Kafka sent it," as that slows the consumer, risks exceeding `max.poll.interval.ms`, and hurts throughput. When a flow must wait boundedly, design explicit timeouts, error paths, and load limits.

### 7.2. Consumer Using `@KafkaListener`

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public final class PaymentCommandListener {

    private final PaymentCommandService service;

    public PaymentCommandListener(PaymentCommandService service) {
        this.service = service;
    }

    @KafkaListener(topics = "payment-commands.v1")
    public void onMessage(String jsonPayload) {
        service.handle(jsonPayload);
    }
}
```

`PaymentCommandService` is a hypothetical business service. If `service.handle(...)` throws an exception, the configured error handler/container decides the outcome. **Never catch all exceptions and return normally** if business processing failed, because the container may consider the record succeeded and commit the offset.

If manual acknowledgment is needed, configure `AckMode.MANUAL` or `MANUAL_IMMEDIATE` and accept `Acknowledgment` in the listener. Explicitly manage when `acknowledge()` is called as well as retry/recovery conditions.

## 8. When Should You Create Separate Beans?

Auto-configuration is enough for many apps with **one Kafka connection profile**. Explicit beans become valuable when:

- Consuming from cluster **A** and producing to cluster **B**.
- Both sides use **different SASL credentials/truststores**.
- Two producers send different payload types with different serializers, timeouts, or transaction policies.
- Two consumer groups/topics require distinct container factories or error handlers.
- The DLT resides on the source cluster while business outputs go to a target cluster.
- You want to prevent a global setting from inadvertently altering both sides' behavior.

Bean-level separation makes explicit **which factory belongs to which cluster**, though you must verify qualifiers, wiring, and where Spring Boot auto-configuration backs off.

## 9. Configuring Two Independent Clusters

Suppose:

- `inbound Kafka`: cluster A, holding `payment-commands.v1`.
- `outbound Kafka`: cluster B, receiving `payment-results.v1`.
- Consumer uses `inbound-consumer-group`.
- Producer sends to cluster B and uses no group ID.
- Both sides may need separate authentication credentials.

### 9.1. Application YAML Keeping Config Regions Separate

```yaml
app:
  kafka:
    inbound:
      bootstrap-servers: ${KAFKA_INBOUND_BOOTSTRAP}
      group-id: payment-commands-processor-v1
      topic: payment-commands.v1
      concurrency: 3

    outbound:
      bootstrap-servers: ${KAFKA_OUTBOUND_BOOTSTRAP}
      topic: payment-results.v1
```

The names `app.kafka.inbound.*` and `app.kafka.outbound.*` are **application-defined configuration**, not Spring Boot Kafka properties that auto-create factories. Your code must read and pass them into `ProducerFactory` and `ConsumerFactory`.

To keep focus on role separation, the Java snippets below use `String` serializers/deserializers. Authentication configs are added to each map in the security section.

### 9.2. Dedicated `ProducerFactory` and `KafkaTemplate` for Outbound

```java
import java.util.HashMap;
import java.util.Map;

import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.StringSerializer;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;

@Configuration
public class OutboundKafkaConfiguration {

    @Bean("outboundProducerFactory")
    ProducerFactory<String, String> outboundProducerFactory(
            @Value("${app.kafka.outbound.bootstrap-servers}")
            String bootstrapServers) {

        Map<String, Object> properties = new HashMap<>();

        properties.put(
                ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
                bootstrapServers);
        properties.put(
                ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
                StringSerializer.class);
        properties.put(
                ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
                StringSerializer.class);
        properties.put(ProducerConfig.ACKS_CONFIG, "all");
        properties.put(
                ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);
        properties.put(
                ProducerConfig.MAX_IN_FLIGHT_REQUESTS_PER_CONNECTION, 5);
        properties.put(
                ProducerConfig.DELIVERY_TIMEOUT_MS_CONFIG, 120_000);
        properties.put(
                ProducerConfig.REQUEST_TIMEOUT_MS_CONFIG, 30_000);

        return new DefaultKafkaProducerFactory<>(properties);
    }

    @Bean("outboundKafkaTemplate")
    KafkaTemplate<String, String> outboundKafkaTemplate(
            @Qualifier("outboundProducerFactory")
            ProducerFactory<String, String> producerFactory) {

        return new KafkaTemplate<>(producerFactory);
    }
}
```

In this example, `outboundKafkaTemplate` is bound to `outboundProducerFactory` via `@Qualifier`. Do not rely on a default `kafkaTemplate` bean, because a default bean might point to another cluster or not exist once custom `ProducerFactory` beans are declared.

### 9.3. Dedicated `ConsumerFactory` and Listener Container for Inbound

```java
import java.util.HashMap;
import java.util.Map;

import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.common.serialization.StringDeserializer;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import org.springframework.kafka.annotation.EnableKafka;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.listener.ContainerProperties;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

@Configuration
@EnableKafka
public class InboundKafkaConfiguration {

    @Bean("inboundConsumerFactory")
    ConsumerFactory<String, String> inboundConsumerFactory(
            @Value("${app.kafka.inbound.bootstrap-servers}")
            String bootstrapServers,
            @Value("${app.kafka.inbound.group-id}")
            String groupId) {

        Map<String, Object> properties = new HashMap<>();

        properties.put(
                ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
                bootstrapServers);
        properties.put(
                ConsumerConfig.GROUP_ID_CONFIG,
                groupId);
        properties.put(
                ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
                StringDeserializer.class);
        properties.put(
                ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
                StringDeserializer.class);
        properties.put(
                ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
        properties.put(
                ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
        properties.put(
                ConsumerConfig.MAX_POLL_RECORDS_CONFIG, 200);

        return new DefaultKafkaConsumerFactory<>(properties);
    }

    @Bean("inboundListenerFactory")
    ConcurrentKafkaListenerContainerFactory<String, String>
    inboundListenerFactory(
            @Qualifier("inboundConsumerFactory")
            ConsumerFactory<String, String> consumerFactory,
            @Value("${app.kafka.inbound.concurrency:3}")
            int concurrency) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<
                        String, String>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(concurrency);
        factory.getContainerProperties().setAckMode(
                ContainerProperties.AckMode.RECORD);

        // After errors are handled per policy, DefaultErrorHandler
        // has a default recover/log mechanism; does not create a DLT automatically.
        factory.setCommonErrorHandler(
                new DefaultErrorHandler(
                        new FixedBackOff(1_000L, 2L)));

        return factory;
    }
}
```

`FixedBackOff(1_000L, 2L)` illustrates two retry attempts after the initial failed processing attempt, with a 1-second wait between attempts per policy. This is not a universal standard for all failures. Certain exceptions can be classified as non-retryable by the error handler; once retries are exhausted, the default recoverer logs and treats the error as recovered under its semantics. **No DLT is configured automatically** merely by creating `DefaultErrorHandler` as shown above.

If a business error must route to a DLT or stop processing, configure the appropriate recoverer/classification and test offset behavior after recovery.

### 9.4. Wiring the Right Template and Listener Factory

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;

@Service
public final class OutboundEventPublisher {

    private final KafkaTemplate<String, String> template;

    public OutboundEventPublisher(
            @Qualifier("outboundKafkaTemplate")
            KafkaTemplate<String, String> template) {
        this.template = template;
    }

    public void sendPaymentResult(
            String paymentId, String jsonPayload) {

        template.send(
                "payment-results.v1",
                paymentId,
                jsonPayload
        ).whenComplete((result, failure) -> {
            if (failure != null) {
                // Log + application recovery mechanism.
                // Do not treat the event as successfully delivered.
                reportPublicationFailure(paymentId, failure);
            }
        });
    }
}

@Component
public final class InboundPaymentListener {

    private final PaymentProcessingService service;

    public InboundPaymentListener(PaymentProcessingService service) {
        this.service = service;
    }

    @KafkaListener(
            topics = "payment-commands.v1",
            containerFactory = "inboundListenerFactory")
    public void handle(String payload) {
        service.process(payload);
    }
}
```

`PaymentProcessingService` and `reportPublicationFailure(...)` are illustrative business components to be implemented by the application. The snippet highlights the core point: the producer **uses no consumer group**, the consumer **uses no producer acknowledgments**, and each side receives its dedicated factory.

In a reliable system, `sendPaymentResult(...)` returning `void` without observing the future is only suitable for best-effort paths or when a durable outbox/reconciliation exists at another layer. If send outcome affects a business decision, the contract should reflect asynchronous delivery or persist an outbound event before acknowledging processing.

## 10. Avoiding Default Configurations That Connect to the Wrong Cluster

When an application has multiple Kafka beans of the same type, never rely on default bean names or autowiring solely by type without verifying wiring.

For example:

```java
@Autowired
private KafkaTemplate<String, String> kafkaTemplate;
```

With multiple templates present, Spring may fail with an ambiguous dependency error or select a bean according to its resolution rules; never rely on implicit resolution to distinguish clusters.

Name beans to express their role:

```text
inboundConsumerFactory
inboundListenerFactory
inboundDlqProducerFactory    (if writing DLT to the source cluster)
inboundDlqKafkaTemplate

outboundProducerFactory
outboundKafkaTemplate
```

With multiple listeners:

```java
@KafkaListener(
    topics = "payment-commands.v1",
    containerFactory = "inboundListenerFactory")
public void onCommand(String value) {
    // ...
}
```

**Never reuse a single `KafkaTemplate` for both cluster B outbound events and cluster A DLT** merely because both invoke `send`. If the DLT lives on source cluster A while `outboundKafkaTemplate` targets cluster B, the recoverer can route errors to the wrong infrastructure or hit unknown-topic/ACL failures.

### 10.1. Why Should You Have Role-Specific Connectivity Checks?

When pointed at the wrong cluster, an app can still start up because Kafka clients connect asynchronously. A `UP` health endpoint does not automatically prove every topic, credential, and read/write permission is valid.

Verify:

- Can the consumer join the right group on cluster A?
- Does the inbound topic exist with the expected partition count?
- Can the producer publish to the outbound topic on cluster B?
- Does the DLT (if used) have write permissions on the cluster that actually hosts it?
- Does the Kafka admin/metadata client use the right bootstrap servers and credentials?
- Is readiness aligned with an appropriate connectivity policy rather than marking the entire service `DOWN` during brief broker blips if queuing/outbox allows read APIs to stay available?

### 10.2. Do Not Confuse `KafkaAdmin` with Client Factories

`KafkaAdmin` performs cluster-level topic/config management operations. In a multi-cluster architecture, declaring a `NewTopic` against an uncontrolled default `KafkaAdmin` can provision topics on the **wrong cluster**.

In production, many organizations manage topics via IaC/platform teams rather than letting every service auto-create them. Whichever model you choose, document each topic's ownership, cluster, retention, partition count, replication, min ISR, and ACLs.

## 11. Separating Security Protocols, Credentials, and ACLs

Two Kafka clients can use the same broker yet **different principals**—for instance, a producer with `WRITE` only and a consumer with `READ` only on their respective topics. This limits blast radius if a credential leaks.

Illustrative permission design:

| Role | Cluster | Principal | Illustrative Least-Privilege Permissions |
|---|---|---|---|
| Inbound consumer | A | `payment-reader` | Read topic `payment-commands.v1`, read/join matching group |
| Outbound producer | B | `payment-writer` | Write/describe topic `payment-results.v1` |
| Inbound DLT producer | A | `payment-dlt-writer` | Write topic `payment-commands.v1-dlt` |
| Topic operator | A/B | `kafka-admin` | Separate admin permissions; exclude from app unless required |

Exact Kafka ACLs and permissions depend on the broker, auth mechanism, and managed Kafka platform. Never grant a producer read access to all topics or a consumer cluster-admin permissions just to silence permission errors.

### 11.1. Illustrative `SASL_SSL` Configuration

Some Kafka clients require:

```java
import org.apache.kafka.clients.CommonClientConfigs;
import org.apache.kafka.common.config.SaslConfigs;

properties.put(
        CommonClientConfigs.SECURITY_PROTOCOL_CONFIG,
        "SASL_SSL");

properties.put(
        SaslConfigs.SASL_MECHANISM,
        "SCRAM-SHA-512");

properties.put(
        SaslConfigs.SASL_JAAS_CONFIG,
        jaasConfigurationFromSecretProvider);
```

`jaasConfigurationFromSecretProvider` represents a config string retrieved from the application's secure secret/config provider, not a Kafka API variable name. Each producer/consumer factory must carry its **exact authentication profile**. For mTLS or managed identity/OAuth, the required properties differ.

Pay close attention to:

- Never put passwords/tokens in `JobParameters`, logs, or Git.
- Never log an entire `properties` map at debug level if it holds a JAAS password.
- Configure bootstrap/truststores per environment and cluster.
- Maintain a credential rotation policy without requiring code redeploys if infrastructure permits.
- Ensure TLS certificate SAN/hostname verification matches the target brokers.
- Apply network egress allowlists and least-privilege Kubernetes/service account permissions.

**Avoid sharing a single `KAFKA_PASSWORD` variable across two principals** when the goal is security isolation. Use separate secret references per role instead.

## 12. Serialization Must Be Separated per Topic Contract

The producer decides how data is encoded into bytes. The consumer must know how to decode compatibly. This is a **topic data contract**, not a setting to change arbitrarily inside a profile.

For example, a producer sends a plain JSON string; the consumer uses `StringDeserializer` and parses JSON inside the service. This is easy to implement but requires explicit validation/schema enforcement.

With Spring Kafka JSON serializer/deserializer:

```yaml
spring:
  kafka:
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer

    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        "[spring.deserializer.value.delegate.class]": org.springframework.kafka.support.serializer.JsonDeserializer
        "[spring.json.value.default.type]": com.example.kafka.events.PaymentCommand
        "[spring.json.trusted.packages]": com.example.kafka.events
        "[spring.json.use.type.headers]": false
```

This is an **alternative single-cluster example**, not a config meant to be mixed verbatim with the `String` factories in the multi-cluster section. `PaymentCommand` is a hypothetical DTO in the application package.

Points to understand:

- `JsonSerializer` can add type headers when configured to do so.
- `JsonDeserializer` needs to know the target type or receive valid type metadata.
- Setting `trusted.packages=*` without security review widens the set of classes eligible during deserialization.
- `ErrorHandlingDeserializer` routes certain deserialization failures into Spring Kafka's error-handling path rather than failing before the listener without recovery metadata.
- A consumer need not trust externally supplied type headers; it can specify a fixed target type and ignore headers when a topic has a uniform schema.
- If producers/consumers use Avro, Protobuf, or Schema Registry, both sides must share schema evolution contracts, credentials, and registry configs.

### 12.1. Data Contracts Independent of Java Classes

Never assume every service shares the same version of Java class `com.example.PaymentCommand`. In distributed systems, producers and consumers deploy independently. Document:

```text
Topic: payment-commands.v1
Key: paymentId (String, nonblank)
Value: PaymentCommand version 1
Required fields: eventId, paymentId, amount, currency
Compatibility: backward-compatible schema evolution
Maximum payload size: 256 KiB (example)
PII: must not contain full card number
```

These values are illustrative. Enforce them with validation and schema rules, not just comments.

## 13. Producer Retries and Consumer Retries Are Two Different Things

A very common operational question: "We turned retries on—why are messages still lost or duplicated?"

Because retries exist at multiple layers:

| Retry | Where Is It Triggered? | Purpose | Risk |
|---|---|---|---|
| **Producer client retry** | `KafkaProducer` on retryable errors | Deliver record to broker | Timeouts/unknown outcomes; app resends can create duplicates |
| **Application publish retry** | Service after send future fails | Reissue business publish request | If prior send reached the broker without ACK returning, duplicates occur |
| **Listener processing retry** | `DefaultErrorHandler` or listener retry mechanism | Reprocess a failed record | Same record runs business code multiple times |
| **DLT recovery** | Recoverer when retries are exhausted | Route failed record for separate handling | DLT send itself can fail |
| **Database retry** | Transaction/business service | Recover transient DB errors | External non-DB side effects may repeat |
| **Message broker redelivery** | Rebalance, uncommitted offsets | Redeliver record | Consumer must be idempotent |

Consequently, a reliable policy usually has two distinct layers:

- **Producer:** idempotence, `acks=all`, proper timeouts, send future observation, and an outbox if events must be published after business commits.
- **Consumer:** commit offsets after processing per defined semantics, bounded retries, DLT or stop on unprocessable errors, and idempotent business actions.

### 13.1. Example: Consumer Validation Errors Should Not Retry

Suppose a record lacks `paymentId`. Retrying 10 more times will not fix the payload. Classify that exception as non-retryable and route it to the DLT/quarantine.

Conversely, transient database connection errors can retry with backoff. **Do not configure retries for every `Exception`** if that allows a poison message to block a partition too long or repeat side effects.

### 13.2. DLT Needs a Producer Targeting the Right Cluster

If the consumer reads cluster A and business output goes to cluster B, while DLT `payment-commands.v1-dlt` lives on cluster A:

```text
Cluster A                         Cluster B
----------                        ----------
payment-commands                 payment-results
       |                                 ^
       v                                 |
 inbound consumer                  outbound producer
       |
       +-- recover failed record
                   |
                   v
          inbound DLT producer
            -> Cluster A
```

You need a second `KafkaTemplate` pointing to cluster A for the DLT, or an explicitly designed routing setup. **Never** pass `outboundKafkaTemplate` (cluster B) into `DeadLetterPublishingRecoverer` if the DLT resides on cluster A.

Skeleton example:

```java
// Wiring illustration only: inboundDltTemplate must target cluster A.
DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(inboundDltTemplate);

DefaultErrorHandler handler =
        new DefaultErrorHandler(
                recoverer,
                new FixedBackOff(1_000L, 2L));
```

Beyond code, verify target topic, partition mapping, ACLs, serialized error handling, retention, and behavior when DLT publishing fails. Recovery may count as having handled the record under container semantics; if DLT sending fails and the recoverer does not report/throw appropriately, you risk losing the failure-handling path.

## 14. Offset Commits: Specify the Mode Instead of Relying on One Boolean

`enable-auto-commit=false` by itself does not answer "when is the offset committed?" Listener containers provide explicit options.

### 14.1. `AckMode.RECORD`

For a record listener, the container commits offsets appropriately after each record succeeds per container semantics. Suitable when you want straightforward progress tracking without manual ack calls.

### 14.2. `AckMode.BATCH`

The container commits by groups of records returned from a `poll` after processing under its mechanism. This can reduce commit overhead, though the replay window after a crash/rebalance is wider.

### 14.3. `AckMode.MANUAL` and `MANUAL_IMMEDIATE`

The listener receives `Acknowledgment` and invokes `acknowledge()` at an application-controlled moment. Example:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.Acknowledgment;

@KafkaListener(
        topics = "payment-commands.v1",
        containerFactory = "manualAckListenerFactory")
public void onMessage(
        String payload,
        Acknowledgment acknowledgment) {

    paymentService.processIdempotently(payload);
    acknowledgment.acknowledge();
}
```

You must configure `manualAckListenerFactory` with the corresponding ack mode; the snippet above cannot be used unchanged with the earlier factory configured for `AckMode.RECORD`.

**Never put `acknowledge()` in a `finally` block** unless business success is confirmed. Calling acknowledge also does not prevent redelivery across every crash scenario; combine it with idempotency.

### 14.4. At-Least-Once Still Produces Duplicates

When the DB commits successfully but the offset has not yet committed, the record can be redelivered. That is normal in at-least-once architectures. Store `eventId` in an inbox table within the same transaction as business state changes to detect replays.

If the business action calls a non-idempotent external API, switching ack modes alone is usually **not enough** for correctness.

## 15. Kafka Transactions and Exactly-Once Boundaries

A Kafka producer can participate in Kafka transactions under appropriate configs; a consumer with `isolation.level=read_committed` returns only committed records from transactional producers while still reading non-transactional records normally.

Spring Kafka supports transactional read-process-write patterns and sends consumer offsets into the Kafka transaction when properly configured. This pattern can achieve **Kafka-to-Kafka exactly-once processing semantics** within the preconditions of Kafka transactions.

However, distinguish carefully:

- Producer idempotence ≠ business exactly-once.
- Kafka transaction ≠ an automatic atomic transaction with PostgreSQL.
- A Kafka transaction on cluster B **does not** span consumer offset reads from cluster A.
- Consumer `read_committed` does not merge database writes and offset commits into one transaction.
- When sending emails or HTTP requests, Kafka transactions do not roll back those side effects.

### 15.1. Why Does Cross-Cluster Require a Different Design?

Suppose a consumer reads cluster A and a producer writes to cluster B:

```text
Cluster A: consumed offset X
           |
           v
Application processes
           |
           v
Cluster B: produced record Y
```

Kafka does not provide a single transaction covering both cluster A's offset and cluster B's produced record. If the application crashes between the two actions, it must tolerate replay or missing acknowledgments per policy. Typically this uses **transactional inbox/outbox**, idempotent keys, and application-layer reconciliation.

Never turn on `transaction-id-prefix` and claim cross-cluster exactly-once. Across distinct transaction managers, analyze commit ordering, crash windows, and specific recovery paths.

### 15.2. When Should You Use an Outbox?

For business processing that must update a DB and publish an event:

```text
Consumer from cluster A
          |
          v
DB transaction:
  upsert business state
  insert inbox eventId (dedup)
  insert outbox eventId + payload
  COMMIT
          |
          v
Outbox publisher -> cluster B
          |
          v
Downstream consumer dedups eventId
```

If the publisher crashes after Kafka B receives the event but before marking the outbox row delivered, the event can be sent again. This is **at-least-once delivery with an idempotent consumer**, not automatic end-to-end exactly-once.

## 16. Environment Profiles: Never Copy Configs Uncontrolled

An application may deploy to `local`, `staging`, and `production`. Distinguish:

- **Invariant in code:** client roles, topic contracts, serializer types, retry classification logic.
- **Varies by environment:** bootstrap servers, credentials, pools/quotas, concurrency, topic prefixes if used.
- **Varies by workload:** fetch, linger, compression, timeouts, concurrency, once measured and approved.
- **Varies by operations:** readiness/pausing, traffic-shifting feature flags, without breaking contracts.

Example:

```yaml
# application.yml (shared defaults, do not store secrets)
app:
  kafka:
    inbound:
      group-id: payment-commands-processor-v1
      topic: payment-commands.v1
      concurrency: 2
    outbound:
      topic: payment-results.v1
```

```yaml
# application-prod.yml (production-specific configuration)
app:
  kafka:
    inbound:
      bootstrap-servers: ${KAFKA_INBOUND_BOOTSTRAP}
      concurrency: 4
    outbound:
      bootstrap-servers: ${KAFKA_OUTBOUND_BOOTSTRAP}
```

These are application-defined properties; Java factories must read them. Never commit real usernames/passwords or JAAS contents into profiles.

### 16.1. Never Use Local Defaults for Critical Endpoints in Production

A configuration like:

```yaml
app:
  kafka:
    outbound:
      bootstrap-servers: ${KAFKA_OUTBOUND_BOOTSTRAP:localhost:9092}
```

is convenient for development, but if the env var is missing in production, the producer may silently try to connect to a local broker or the wrong environment.

For critical endpoints, have **no localhost fallback in production**; missing configuration must fail startup or fail readiness clearly. Local defaults belong strictly in development profiles.

### 16.2. Declare Topic Ownership Clearly

Topic names may be separated by environment (`dev.payment-results.v1`) or each environment may run a dedicated cluster (`payment-results.v1`). Either way, the contract must record the actual topic and cluster. Never assemble prefixes via unchecked string concatenation and create topics in the wrong environment.

## 17. Managing Properties with `@ConfigurationProperties`

In large applications, dozens of `@Value` annotations become hard to maintain. Bind application properties like `app.kafka.inbound.*` and `app.kafka.outbound.*` into typed configuration objects.

Example using Java records and Spring Boot configuration properties:

```java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.kafka")
public record KafkaRolesProperties(
        Inbound inbound,
        Outbound outbound
) {
    public record Inbound(
            String bootstrapServers,
            String groupId,
            String topic,
            int concurrency
    ) {
    }

    public record Outbound(
            String bootstrapServers,
            String topic
    ) {
    }
}
```

Registration:

```java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(KafkaRolesProperties.class)
public class KafkaRolesPropertiesConfiguration {
}
```

Factory beans can then inject `KafkaRolesProperties` and read:

```java
String inboundServers =
        properties.inbound().bootstrapServers();

String outboundServers =
        properties.outbound().bootstrapServers();
```

This introduces typed binding. In production, add validation:

- `inbound` and `outbound` must not be null.
- Bootstrap servers must be non-blank, and topics must have valid names.
- `concurrency` > 0 and within operational limits.
- `groupId` is non-blank and stable across deploys unless intentionally migrating groups.
- If distinct clusters A/B are required, verify that by contract rather than merely comparing broker strings.
- Security profiles reference the proper principal per role.

Use Jakarta Bean Validation (`@NotBlank`, `@NotNull`, `@Min(1)`) with `@Validated` and the validation starter. Spring Boot 3 uses the `jakarta.validation` namespace. Early validation helps because Kafka client misconfigurations sometimes surface only after listeners open.

## 18. Separating Timeouts, Quotas, and Performance for Both Sides

Producer and consumer process load in opposite directions, so their operational thresholds differ.

### 18.1. Producer Throughput

Influencing factors:

- `linger.ms`, `batch.size` (bytes), compression.
- Partition count and key distribution.
- Broker quotas and request latency.
- Payload size and message size limits.
- Network and TLS overhead.
- Pending futures and buffer memory.

A producer pushing 10,000 events/sec needs a different batching policy than a producer emitting 10 events/sec with low-latency requirements.

### 18.2. Consumer Throughput

Influencing factors:

- Partition count relative to active consumers.
- `max.poll.records` and per-record processing time.
- Listener concurrency.
- Downstream database/API speed.
- Retries/backoff and DLT overhead.
- Rebalances and offset commit duration.
- Executor/thread pools and memory pressure.

Suppose average record processing takes 200 ms and one consumer executes sequentially: theoretical throughput is around 5 records/s (ignoring overhead). Increasing `max.poll.records` will not make each record process faster. Evaluate whether parallelism is safe per business key or optimize I/O.

### 18.3. Role-Specific Thresholds

| Dimension | Producer | Consumer |
|---|---|---|
| Latency | End-to-end time from publish request to broker ACK | Time from record availability to business commit |
| Backlog | Outstanding sends / pending outbox | Consumer lag / processing queue |
| Retry | Send attempts, delivery timeout | Error handler retries, redelivery, DLT |
| Capacity | Records/s, bytes/s, buffer pressure | Records/s, poll interval, DB throughput |
| Error | Serialization, authorization, broker unavailable | Deserialization, poison records, DB failures, rebalances |
| Security | Write ACL, serializer/registry access | Read ACL, group authorization, deserializer/registry access |

Seeing high producer throughput while consumer lag climbs steadily does not mean end-to-end processing is healthy. Build dashboards linking both roles via the same business event ID or correlation ID.

## 19. Role-Separated Monitoring and Logging

Kafka client metrics typically distinguish producers and consumers by client ID, though exact metric names depend on client version and registry. Spring Boot Actuator + Micrometer can expose Kafka client metrics to your observability stack.

Groups to watch:

**Producer:**

- Send rate, record size, request latency.
- Record error/retry rate.
- Available buffer / exhaustion, wait time.
- Delivery timeouts and send future failures.
- Pending outbox age if using an outbox.

**Consumer:**

- Consumer lag per group/topic/partition.
- Poll rate and records consumed rate.
- Commit latency/failures.
- Partition assignments/rebalances.
- Listener processing duration and errors.
- DLT record count and pending DLT age.
- DB latency and business outcomes.

Useful structured logs:

```text
event=kafka.producer.send_failed
role=outbound
topic=payment-results.v1
eventId=evt-101
errorCategory=TIMEOUT

event=kafka.consumer.processing_failed
role=inbound
topic=payment-commands.v1
group=payment-commands-processor-v1
partition=2
offset=152001
errorCategory=DATABASE_TRANSIENT
```

Never place `eventId`, per-record partition offsets, or payloads into **high-cardinality Prometheus tags**. Keep them in structured logs/traces with proper retention and access control. Avoid logging raw messages containing PII or secrets.

### 19.1. Health Does Not Replace Business Readiness

An app can report process `UP` while:

- The producer lacks write permission on the outbound topic.
- The consumer cannot join its group.
- The listener is paused.
- The inbound topic has not been created.
- The DLT producer points to the wrong cluster.
- Consumer lag grows unboundedly.

Readiness policies should reflect genuinely required capabilities. At the same time, do not automatically mark the entire service `DOWN` on a brief broker disconnect if the architecture uses queues/outboxes and read APIs must remain available. Choose policies according to application responsibilities and deployment model.

## 20. Testing Producer and Consumer Configuration

There are at least three testing levels, each answering a different question.

### 20.1. Unit Testing Property Binding

Verify `KafkaRolesProperties` binds valid values and rejects invalid configs. Example test cases:

| Case | Expected |
|---|---|
| Valid inbound A, outbound B, valid group | Binds successfully |
| Missing outbound bootstrap | Fails validation |
| Concurrency equals 0 | Fails validation |
| Blank group ID | Fails validation |
| Security configured only on inbound, missing on outbound | Fails startup or validation per policy |
| Topic name contains unsupported values | Fails validation |

Unit tests do not prove Kafka clients can connect, yet they catch profile mistakes before deployment.

### 20.2. Single-Cluster Integration Testing with EmbeddedKafka

For testing serialization, listener wiring, and ack/error handling, `spring-kafka-test` provides utilities such as `@EmbeddedKafka` or `EmbeddedKafkaBroker`.

Conceptual example:

```java
@SpringBootTest
@EmbeddedKafka(
        partitions = 2,
        topics = {
                "test-payment-commands",
                "test-payment-results"
        })
class PaymentKafkaIntegrationTest {

    @Test
    void sendsAndConsumesEvent() {
        // Send a test event using a KafkaTemplate configured for the embedded broker.
        // Wait with Awaitility/latch using a bounded timeout.
        // Assert the listener receives the event once on the happy path.
        // Verify topic and key match the contract.
    }
}
```

This is a **test skeleton**, omitting dynamic bootstrap wiring for the embedded broker and test fixture beans. Real tests must point clients to the embedded broker's bootstrap address, isolate consumer groups, and clean state between runs.

Embedded Kafka is useful for core flows. However, one embedded broker does not prove **two independent clusters**, real TLS/SASL, ACLs, broker replication, quotas, or production failover.

### 20.3. Two-Cluster Integration Testing with Testcontainers

To test inbound A → outbound B, run **two separate test Kafka brokers/clusters** via Testcontainers or an equivalent integration setup.

```text
Test container Kafka A             Test container Kafka B
    payment-commands                   payment-results
            |                                 ^
            v                                 |
     inboundListenerFactory            outboundKafkaTemplate
            |                                 |
            +------------ app ----------------+
```

Tests should verify:

1. The listener connects to cluster A, joins the right group, and consumes messages from A.
2. Once the business service finishes, the producer writes the record to cluster B.
3. The message appears on B and does **not** leak onto A.
4. Failures publishing to B are recorded/retried via outbox or the chosen policy.
5. The error handler routes DLT messages back to cluster A if required by design.
6. Missing ACL credentials do not fall back to the other cluster's producer factory.
7. Consumer redelivery after a crash does not create duplicate DB rows.
8. Topic prefixes and security settings match the test profile.

These steps require sufficient test environment resources; never treat a test using two topics on **one cluster** as proof that multi-cluster configuration works.

### 20.4. Verifying Explicit Bean Wiring

You can assert the right bean is wired by name/qualifier:

```java
import static org.junit.jupiter.api.Assertions.assertNotSame;
import static org.junit.jupiter.api.Assertions.assertSame;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;

class KafkaWiringTest {

    @Autowired
    @Qualifier("outboundKafkaTemplate")
    KafkaTemplate<String, String> outbound;

    @Autowired
    @Qualifier("outboundProducerFactory")
    ProducerFactory<String, String> outboundFactory;

    @Test
    void templateUsesExpectedProducerFactory() {
        assertSame(outboundFactory, outbound.getProducerFactory());
    }
}
```

This is an illustrative assertion snippet meant to live inside a Spring test context containing the corresponding beans. It checks in-JVM wiring, not the actual target broker. Separate tests must inspect effective `bootstrap.servers` and verify with live messages.

### 20.5. Failure-Injection Tests for Semantics

| Scenario | What to Prove |
|---|---|
| Kafka broker A unavailable | Consumer signals error/does not misprocess, recovers when broker returns |
| Kafka broker B unavailable | Producer future fails within timeout; outbound event is not lost if durable delivery is contracted |
| DLT producer on wrong cluster | Test detects topic/ACL mismatch |
| Listener throws transient exception | Bounded retries; does not ack before processing |
| Listener throws poison payload | Recovers/routes to DLT per policy; no infinite retry |
| DB committed, offset uncommitted | Message is handled idempotently on redelivery |
| Producer ACK uncertain due to timeout | App-level resend causes no duplicate business effect |
| Schema changes | Consumer handles compatibly or routes error to quarantine |
| Rebalance mid-processing | No duplicate or missing business writes |
| App restart | Consumer resumes committed offsets, does not reset due to `earliest` |

## 21. Operations, Rollouts, and Safe Configuration Changes

Separating config makes deployments safer only when changes are managed per role.

### 21.1. Before Deployment

Record an effective configuration matrix:

| Field | Inbound Consumer | Outbound Producer |
|---|---|---|
| Cluster | Kafka A | Kafka B |
| Bootstrap | Secret/config reference A | Secret/config reference B |
| Principal | reader principal | writer principal |
| Topic | `payment-commands.v1` | `payment-results.v1` |
| Group | `payment-commands-processor-v1` | Not applicable |
| Serializer/Deserializer | StringDeserializer | StringSerializer |
| Retry policy | Listener + DLT | Kafka producer + outbox |
| Delivery/commit | Record commit after processing | ACK via future |
| SLA | Consumer lag and processing latency | Publish ACK latency |
| Rollback plan | Controlled consumer pause/restart | Outbox replay/config downgrade |

To verify, check effective properties, bean status, and cluster permissions. Never print secrets when recording config.

### 21.2. Changing `group.id` Changes Replay Semantics

Changing `payment-commands-processor-v1` to `payment-commands-processor-v2` typically creates a **new consumer group** with no old committed offsets. With `auto.offset.reset=earliest`, the new group can replay retained records; with `latest`, it can skip records already present before the group was created.

This is a **business** change, not a cosmetic rename for tidiness. It requires a replay and idempotency plan.

### 21.3. Changing Serializers Requires Contract Migration

If the producer switches from JSON String to binary Avro while the consumer still uses `StringDeserializer`, messages fail decoding or produce invalid payloads. Safe rollouts require schema versioning, bidirectional compatibility or a new topic version, and compatibility tests between old and new producer/consumer versions.

### 21.4. Changing Concurrency

Increasing `concurrency` adds consumers to the group, triggers rebalances, increases DB load, or exposes race conditions if listeners are not thread-safe. Benchmark, watch lag and DB pools, and verify key ordering rather than scaling purely by application CPU.

### 21.5. Toggling Consumers While Keeping Producers Active

Some systems must pause inbound processing during downstream outages while still letting producers emit certain events. Because the roles are independent, use listener registry/container controls or `autoStartup` configuration with a clear runbook rather than shutting down the entire Kafka subsystem.

Distinguish **pause** from **stop** and understand their impacts on consumer groups, offsets, rebalances, and readiness. While paused, backlog grows; ensure capacity exists to catch up once resumed.

## 22. Common Anti-Patterns

| Anti-Pattern | Consequence | Fix |
|---|---|---|
| Putting every property under one shared map | Easy to misplace parameters | Split `producer`/`consumer`/`listener` |
| Assuming `acks=all` makes consumers process once | Duplicates can still occur | Idempotent consumer + transaction boundaries |
| Treating `auto.offset.reset=earliest` as a replay command for an existing group | Does not alter committed offsets | Dedicated reset/replay procedure |
| Enabling `enable-auto-commit=true` while expecting business-aligned container acks | Offsets drift from processing completion | Define explicit ack mode/commit policy |
| Catching exceptions in listener and returning | Container may commit offsets despite business failure | Propagate errors or recover intentionally |
| Producer ignoring `CompletableFuture` | Send failures go unnoticed | Observe future/use outbox |
| Sharing one `KafkaTemplate` for cluster B output and cluster A DLT | DLT routes to wrong cluster | Separate template/factory per destination |
| Annotating `@KafkaListener` without `containerFactory` when multiple exist | May bind to unintended default factory | Specify listener factory explicitly |
| Two factories of the same type without `@Qualifier` | Ambiguous wiring | Bean names, qualifiers, tests |
| Sharing credentials across producer/consumer despite least privilege | Over-broad access, hard to rotate | Role-based principals/ACLs |
| Putting JAAS passwords in Git-committed YAML | Secret exposure | Secret manager/secure env injection |
| `concurrency=8` on a 3-partition topic expecting 8x throughput | Idle consumers, unexpected DB load | Tune to partitions/processing time |
| Sharing one client ID uncontrollably across roles | Hard-to-read metrics/diagnostics | Role- and instance-specific client IDs |
| Letting `JsonDeserializer` trust all packages | Expands attack surface | Schema/type allowlist |
| Treating `read_committed` as a cross-cluster DB/Kafka transaction | Broken consistency assumptions | Inbox/outbox and reconciliation |
| Testing multi-cluster using two topics on one broker | Misses wrong-cluster wiring bugs | Two independent test brokers/clusters |
| Changing `group.id` during deploys without a plan | Unintended replays or skips | Review offset/consumer group semantics |
| Auto-creating topics on uncontrolled clusters | Wrong environment/ACLs | IaC or isolated `KafkaAdmin` |
| Using localhost defaults in production | Connects to wrong endpoint when env missing | Fail fast on missing config |
| Putting payloads/event IDs in every metric label | High cardinality, potential data leaks | Stable labels + structured logs |

## 23. Hands-On Exercise: Consumer A, Producer B Application

Build `invoice-relay-service`. It reads `invoice-approved.v1` events from cluster A, writes audit/inbox state in PostgreSQL, and publishes `invoice-settlement-requested.v1` to cluster B.

**Functional Requirements:**

1. Define `app.kafka.inbound.*` and `app.kafka.outbound.*` with distinct bootstrap servers, topics, and settings.
2. Create `inboundConsumerFactory` using `StringDeserializer`, `group.id=invoice-relay-v1`, auto-commit disabled, and `auto.offset.reset=earliest` for a new group.
3. Create `inboundListenerFactory` with `AckMode.RECORD`, `concurrency=2`, and an error handler with bounded retries.
4. Create `outboundProducerFactory` using `StringSerializer`, `acks=all`, idempotence, and a finite delivery timeout.
5. Create `outboundKafkaTemplate`, inject it with `@Qualifier` into the publisher, and prove the listener uses the inbound factory.
6. Design and implement inbox/outbox tables so the DB never processes the same `eventId` twice and outbound events can be resent after a crash.
7. Add `inboundDlqKafkaTemplate` targeting cluster A if the DLT must reside on the source cluster.
8. Separate credentials: the reader principal can only read topic A/group, and the writer principal can only write topic B.
9. Add validation for application properties: non-empty bootstrap/topic/group and `concurrency > 0`.
10. Write a two-cluster integration test: send to A, receive on B, with no cross-cluster message leaks.
11. Simulate producer B failure while consumer A keeps receiving: explain how the outbox prevents event loss.
12. Simulate DB commit succeeded while offset A did not commit: prove replay creates no duplicate audit records.
13. Simulate a poison payload: the message must route to DLT/quarantine per policy rather than retrying infinitely.
14. Change the consumer group ID to `invoice-relay-v2` in a test environment and verify offset behavior.
15. Increase concurrency from 2 to 6 on a 3-partition topic; measure active consumers and throughput.
16. Design separate dashboard panels for producer ACK latency/pending outbox and consumer lag/rebalances/DLT.

**Review Question:** If a consumer reads Kafka A, a producer writes Kafka B, and both `enable.idempotence=true` and `acks=all` are enabled, can the whole pipeline be called exactly-once?

**Answer:** **No.** Those two properties improve producer reliability within Kafka client/broker boundaries; they do not form an atomic transaction spanning consumed offsets on A, PostgreSQL updates, and records produced to B. Explicit transaction boundaries, inbox/outbox, idempotency, and reconciliation are required for reliable business outcomes under retries and crashes.

## 24. References

- [Spring Boot Reference — Apache Kafka Support](https://docs.spring.io/spring-boot/reference/messaging/kafka.html): `spring.kafka` configuration, producer/consumer/listener, KafkaTemplate, and KafkaListener.
- [Spring Kafka Reference — Sending Messages](https://docs.spring.io/spring-kafka/reference/kafka/sending-messages.html): `KafkaTemplate` and send futures.
- [Spring Kafka Reference — Receiving Messages](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages.html): containers, `@KafkaListener`, ack modes, and concurrency.
- [Spring Kafka Reference — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html): `DefaultErrorHandler`, retries, and DLT.
- [Spring Kafka Reference — Exactly Once Semantics](https://docs.spring.io/spring-kafka/reference/kafka/exactly-once.html): Kafka transactional processing and its limits.
- [Spring Kafka Reference — SerDes](https://docs.spring.io/spring-kafka/reference/kafka/serdes.html): `JsonSerializer`, `JsonDeserializer`, and error-handling deserializer.
- [Spring Kafka Reference — Testing](https://docs.spring.io/spring-kafka/reference/testing.html): `spring-kafka-test`, Embedded Kafka, and integration tests.
- [Apache Kafka Producer Configs](https://kafka.apache.org/documentation/#producerconfigs): `acks`, idempotence, retries, linger, batch size, and timeouts.
- [Apache Kafka Consumer Configs](https://kafka.apache.org/documentation/#consumerconfigs): `group.id`, offset reset, polling, fetching, and isolation.
- [Apache Kafka Security](https://kafka.apache.org/documentation/#security): TLS, SASL, ACLs, and client authentication.
