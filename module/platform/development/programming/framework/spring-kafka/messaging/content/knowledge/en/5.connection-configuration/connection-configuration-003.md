# Basic producer configuration

A producer is the component that sends records from an application to Kafka. In Spring Kafka, applications typically use `KafkaTemplate` to send data; producer configuration determines which brokers the client connects to, how keys/values are converted to bytes, what level of broker acknowledgment is required, how send errors are handled, and how buffering, batching, and compression are used.

A good producer configuration needs to satisfy three goals simultaneously: sending the right data to the right cluster, providing reliability appropriate to the business requirements, and using resources reasonably. There is no single optimal parameter set for every system. Configuration should start from business requirements, and only then tune latency, throughput, and durability.

This lesson belongs to the **Connection Configuration** chapter of the **SPRING_KAFKA_MESSAGING** module. The module focuses on building event-driven applications with Spring Kafka, understanding topics, partitions, offsets, and consumer groups, and learning serialization, retries, dead-letter handling, transactions, exactly-once semantics, concurrency, and testing to operate messaging flows reliably.

## 1. Where does the producer fit in the send flow?

Sending an event with Spring Kafka goes through the following main components:

1. The business service creates the event and selects the topic, key, and payload.
2. `KafkaTemplate` builds the record and delegates the send request to a producer provided by `ProducerFactory`.
3. The serializer converts the key/value into bytes.
4. The partitioner determines the target partition based on the specified partition, key, or default strategy.
5. The Kafka producer sends the record to the partition's leader broker.
6. The broker processes the record and responds according to the acknowledgment configuration.
7. The send operation's future completes with success or failure; the application can observe this result.

~~~mermaid
flowchart LR
    A[Service creates event] --> B[KafkaTemplate]
    B --> C[ProducerFactory]
    C --> D[Kafka Producer]
    D --> E[Serializer]
    E --> F[Partitioner]
    F --> G[Broker leader]
    G --> H[ACK or error]
    H --> I[SendResult / Exception]
~~~

The producer is only responsible for sending records and receiving results according to the producer-broker protocol. Consumer reading, business processing, and offset commits are separate steps. Therefore, a successful send result does not mean a consumer has already processed the event.

## 2. Minimal configuration in Spring Boot

If the application uses Spring Boot and Spring Kafka, you can declare the cluster address and serializers in `application.yml`. Spring Boot uses these properties to configure the default producer factory and KafkaTemplate when auto-configuration is active.

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
~~~

These properties mean:

- `bootstrap-servers`: broker address that the client uses for initial connection and cluster metadata discovery.
- `key-serializer`: converts the key from a Java type to bytes.
- `value-serializer`: converts the payload from a Java type to bytes.
- `StringSerializer`: suitable when the key is a string.
- `JsonSerializer`: Spring Kafka's serializer for converting objects to JSON.

The declared serializers must match the key/value types that the application sends. For example, `KafkaTemplate<String, OrderCreated>` requires serializers capable of handling String for the key and OrderCreated for the value. If the generic types and serializers are incompatible, errors may occur when sending or serializing records.

With a minimal configuration, the producer may use the Kafka client's default values for acknowledgments, retries, batching, and timeouts. When taking the application to a real environment, proactively review the important properties in the following sections rather than relying completely on library version defaults.

## 3. Connecting to a Kafka cluster with bootstrap servers

### 3.1. Bootstrap servers are initial addresses

`bootstrap.servers` is the list of broker addresses the producer uses to establish the initial connection and fetch metadata. You can declare one or more brokers:

~~~yaml
spring:
  kafka:
    bootstrap-servers:
      - kafka-1.internal:9092
      - kafka-2.internal:9092
      - kafka-3.internal:9092
~~~

Declaring multiple addresses gives the client additional options if one bootstrap broker is unavailable. After fetching metadata, the Kafka client connects to the broker currently serving as the leader of the target partition. Therefore, the bootstrap list is not a fixed list of brokers through which every record is sequentially routed.

### 3.2. Broker advertised addresses must also be reachable

A common situation is that the application connects to the bootstrap broker successfully but then fails to send records. The cause may be that the broker advertises addresses in `advertised.listeners` that the application's host cannot reach.

For example, the broker might advertise `localhost:9092`. This address is only suitable when the producer runs in the same network environment as the broker. If the producer runs in a container or on another machine, `localhost` may point to the application container/machine itself rather than the Kafka broker.

When investigating connectivity, check:

- Whether DNS resolves the broker hostnames.
- Whether the ports are open from the application's runtime environment.
- Whether firewalls, network policies, or security groups block the connection.
- Whether `advertised.listeners` returns a hostname and port reachable by the producer.
- Whether the application uses the right listener intended for internal, external, or container clients.

Do not troubleshoot connection errors by randomly changing bootstrap servers. Identify the addresses that the Kafka cluster advertises to clients and ensure those addresses are reachable from the exact deployment environment.

### 3.3. Environment-specific configuration

Cluster addresses usually differ across local, test, staging, and production environments. Do not hard-code production addresses in Java code.

You can set a default configuration in YAML and override it via environment variables:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
~~~

During deployment, environment configuration can provide `SPRING_KAFKA_BOOTSTRAP_SERVERS` or equivalent configuration via the deployment management system. This allows a single application artifact to run in multiple environments without rebuilding just to change broker addresses.

## 4. Serializers for keys and values

Kafka stores records as bytes. Producer serializers are responsible for converting Java types to bytes before sending them to the broker.

### 4.1. Choosing a serializer by data type

| Serializer | Suitable Data | Notes |
| --- | --- | --- |
| `StringSerializer` | String | Commonly used for string keys or text payloads. |
| `ByteArraySerializer` | byte[] | Used when the application already encodes the payload itself. |
| `IntegerSerializer` | Integer | Used when the key/value is an integer. |
| Spring Kafka `JsonSerializer` | Java Object | Converts objects to JSON and can add type information to headers as configured. |
| Avro/Protobuf Serializer | Schema-based payload | Commonly used when the system has a schema registry or a dedicated schema management mechanism. |

Example event:

~~~java
public record OrderCreated(
    String eventId,
    String orderId,
    BigDecimal total,
    Instant occurredAt
) {}
~~~

The producer can send the event using orderId as the key:

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

In this example, the key is String and the value is OrderCreated. Spring Kafka uses the configured serializers to convert them into bytes.

### 4.2. Keys affect partitioning

A key is not just metadata for the consumer to read. It is also used by the producer when choosing a partition. With the default partitioner and a non-null key, records with the same key are normally routed to the same partition within the same partition topology.

Choosing `orderId` as the key gives events belonging to the same order a chance to be processed in order within a single partition. Choosing a poor key, such as an identical value for every record, can concentrate load onto a single partition and reduce parallelism.

If there is no ordering requirement per entity, you can send records without a key so the partitioner distributes them using the default strategy. Key decisions should be based on business semantics and how consumers process the data.

### 4.3. Producers and consumers must agree on a contract

Successful producer serialization does not guarantee every consumer can decode the payload. Both sides must agree on:

- Payload format, such as JSON, Avro, or Protobuf.
- Field naming rules and data types.
- How to handle new fields, missing fields, or null values.
- Type headers or schema identifiers if the format uses type/schema metadata.
- Compatibility rules when producers and consumers are released at different times.

With JSON, Spring Kafka's JsonSerializer can add type headers. Consumers can use type headers, mappings, or a default type to determine the target type. Do not let one service's internal Java package become a mandatory contract for all other services if services need to be released independently. When needed, define a stable schema or type mapping.

## 5. Send confirmation level with acks

`acks` determines what level of acknowledgment from the broker the producer waits for before considering a send successful.

| Value | Behavior | Trade-off |
| --- | --- | --- |
| `0` | Producer does not wait for the broker to confirm the record was written. | Lower latency, but the producer cannot easily detect send failures and records may be lost. |
| `1` | Leader acknowledges after appending the record to its local log. | Records may be lost if the leader fails before other replicas replicate the data. |
| `all` | Leader waits for replicas in the ISR to acknowledge according to the replication protocol. | Increases data protection, but depends on ISR health and replication configuration. |

For important business events, `acks=all` is usually the option to consider. However, `acks=all` does not automatically mean every replica in the cluster has written the record. It relates to the set of replicas currently in the ISR. Replication factor and `min.insync.replicas` must be coordinated to establish appropriate durability guarantees.

Example configuration:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
~~~

When the send future completes successfully, the producer has received acknowledgment according to the chosen configuration. This result does not indicate whether the consumer group has read the record yet.

## 6. Retries and idempotence on the producer

### 6.1. Retries handle transient send errors

A producer can encounter transient errors such as broker leader changes, request timeouts, or brief network glitches. The Kafka client can resend the request when the error is retriable and within the send time limit.

Do not simply set `retries` very high and assume data is safe. Total send time is also bounded by `delivery.timeout.ms`. When this timeout expires, the send operation can fail even if the client still has configured retry attempts remaining.

Related properties:

| Property | Role |
| --- | --- |
| `retries` | Number of times the client can retry sending when encountering a retriable error. |
| `delivery.timeout.ms` | Upper bound on total time for a send to complete, including waiting and producer retries. |
| `request.timeout.ms` | Wait time for a response to a single request to the broker. |
| `retry.backoff.ms` | Pause interval between retry attempts where applicable. |

Think of `delivery.timeout.ms` as the overall limit for a single send. `request.timeout.ms` applies only to a single request. If timeouts are configured inconsistently, the producer may run out of overall time before its retry budget is exhausted.

### 6.2. Idempotent producer limits duplicates from retries

If a producer sends a record but the acknowledgment is lost on the return path, the client may not know whether the broker already appended the record. When retrying, there is a risk of creating duplicate records without a deduplication mechanism at the producer layer.

Kafka supports idempotent producers. When `enable.idempotence` is enabled, the producer uses a producer ID and sequence numbers so the broker can recognize retries belonging to the same producer stream, thereby avoiding duplicate appends caused by retries within the guarantees of this mechanism.

Commonly used configuration:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        "enable.idempotence": true
~~~

Idempotence must be used alongside compatible Kafka client configuration conditions, including acknowledgments, retries, and maximum in-flight requests per connection. Modern Kafka client versions automatically validate several of these conditions; if you override related properties, consult documentation for the exact version to avoid conflicts.

An idempotent producer does not eliminate all application-level duplicates. For example, a service might call send twice for the same event because business logic re-ran; those are two new sends from the application, not internal retries that an idempotent producer can recognize as the same operation. To prevent business-level duplicates, you need event IDs and proper consumer idempotency.

## 7. Batching, linger, and compression

A producer does not necessarily send each record as a separate request. The Kafka client groups records into batches per partition to reduce request count and improve network efficiency.

Commonly tuned properties:

| Property | Meaning |
| --- | --- |
| `batch.size` | Target batch size per partition. |
| `linger.ms` | Time the producer can wait for additional records to fill a batch before sending. |
| `buffer.memory` | Memory the producer uses to buffer records waiting to be sent. |
| `compression.type` | Compression type for record batches, such as none, gzip, snappy, lz4, or zstd depending on client/broker support. |

Example:

~~~yaml
spring:
  kafka:
    producer:
      batch-size: 32768
      buffer-memory: 67108864
      properties:
        "linger.ms": 5
        "compression.type": zstd
~~~

The numbers above are only examples to illustrate configuration syntax, not optimal values for every system. Increasing `linger.ms` can allow larger batches and improve throughput, but it also increases waiting latency for records during low traffic. Increasing `batch.size` or `buffer.memory` can increase memory usage.

Compression can reduce network bandwidth and transmission size, at the cost of CPU usage on the producer and broker/consumer for compression/decompression. Choose compression based on payload size, CPU, bandwidth, and actual latency.

Batches are organized per partition. If keys are unevenly distributed, one partition may receive most records and form large batches while other partitions have sparse data. Therefore, batch tuning cannot replace proper key design and partitioning.

## 8. Key timeouts and backpressure

A producer has several points where it can wait: initializing connections, fetching metadata, waiting for buffer space, sending requests, and waiting for acknowledgments. Different timeouts control different stages.

| Property | When It Takes Effect |
| --- | --- |
| `max.block.ms` | Bounds how long certain synchronous producer calls wait for metadata or available buffer space; KafkaTemplate.send can block during metadata fetch/buffer allocation. |
| `request.timeout.ms` | Bounds the wait time for a response to a single request. |
| `delivery.timeout.ms` | Bounds the total time to complete a send. |
| `linger.ms` | Wait time to accumulate a batch before sending under applicable conditions. |
| `metadata.max.age.ms` | Maximum interval before the client refreshes metadata via the Kafka client mechanism. |

When a producer sends faster than brokers can accept, the buffer can fill up. At that point, send calls may wait up to `max.block.ms`, after which a timeout occurs if required buffer space or metadata is unavailable. This is a form of backpressure: the application feels that the infrastructure is not keeping up with the data generation rate.

Do not set timeouts excessively high to mask overloaded brokers. Monitor buffer availability, request latency, record queue time, retry rate, and error rate. If the producer's buffer is constantly full, look for root causes such as slow brokers, network congestion, unbalanced partitions, or an event emission rate exceeding cluster capacity.

## 9. Complete producer configuration in Spring Boot

A baseline configuration balancing reliability and performance might look like this:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      acks: all
      batch-size: 32768
      buffer-memory: 67108864
      properties:
        "enable.idempotence": true
        "delivery.timeout.ms": 120000
        "request.timeout.ms": 30000
        "linger.ms": 5
        "compression.type": zstd
~~~

This configuration reflects the following decisions:

- Use StringSerializer for keys and JsonSerializer for payloads.
- Require acknowledgments at level all.
- Enable the idempotent producer.
- Set total time for a single send and timeout per request.
- Allow the producer to accumulate batches over a brief window.
- Use compression to reduce bytes transmitted.

Values must be validated against the Kafka client, broker, Spring Boot versions, and real operational requirements. Without load metrics, start from a simple configuration, measure latency and throughput, and then adjust each group of properties.

## 10. Java configuration when manually creating ProducerFactory

Spring Boot auto-configuration is usually sufficient for applications using a single cluster and a single set of serializers. If you need to manage factories yourself, you can declare ProducerFactory and KafkaTemplate using Java configuration.

~~~java
@Configuration
public class KafkaProducerConfiguration {

    @Bean
    public ProducerFactory<String, OrderCreated> orderProducerFactory() {
        Map<String, Object> props = new HashMap<>();

        props.put(
            ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
            "localhost:9092"
        );
        props.put(
            ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class
        );
        props.put(
            ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
            JsonSerializer.class
        );
        props.put(ProducerConfig.ACKS_CONFIG, "all");
        props.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);
        props.put(ProducerConfig.DELIVERY_TIMEOUT_MS_CONFIG, 120_000);
        props.put(ProducerConfig.REQUEST_TIMEOUT_MS_CONFIG, 30_000);
        props.put(ProducerConfig.LINGER_MS_CONFIG, 5);

        return new DefaultKafkaProducerFactory<>(props);
    }

    @Bean
    public KafkaTemplate<String, OrderCreated> orderKafkaTemplate(
            ProducerFactory<String, OrderCreated> orderProducerFactory) {
        return new KafkaTemplate<>(orderProducerFactory);
    }
}
~~~

This example illustrates passing producer properties to DefaultKafkaProducerFactory. Imports are omitted to focus on the configuration.

Do not create a custom ProducerFactory just to change a single property if Spring Boot already supports the corresponding property. Using application.yml keeps configuration easy to override per environment and minimizes infrastructure boilerplate. Manual factories are appropriate when multiple clusters, multiple serializers, or independent producer configurations are needed.

When declaring beans manually, verify which KafkaTemplate bean is injected into services. If there are multiple ProducerFactory or KafkaTemplate beans with the same generic types, use bean names and `@Qualifier` to avoid injecting the wrong one.

## 11. Sending records and observing results

KafkaTemplate provides an asynchronous send API. Example:

~~~java
public void publish(OrderCreated event) {
    kafkaTemplate.send("order-events", event.orderId(), event)
        .whenComplete((result, exception) -> {
            if (exception != null) {
                log.error(
                    "Failed to send event orderId={}",
                    event.orderId(),
                    exception
                );
                return;
            }

            RecordMetadata metadata = result.getRecordMetadata();
            log.info(
                "Sent topic={} partition={} offset={}",
                metadata.topic(),
                metadata.partition(),
                metadata.offset()
            );
        });
}
~~~

When sending succeeds, `SendResult` provides `RecordMetadata` with the topic, partition, offset, and timestamp. This information is useful for correlating records with consumer logs and investigating incidents.

In Spring Kafka 3.x, the send method returns a `CompletableFuture`. In older versions, the API may return a `ListenableFuture`. Use the appropriate future type for the project's dependency version.

If business logic needs to be sure the broker has acknowledged before returning a response to the caller, you can wait on the future within a chosen timeout. However, do not block threads arbitrarily on every send because it reduces concurrency. With an asynchronous API, observe callbacks/futures and establish a clear error-handling policy.

Do not log the entire payload by default. Usually only event ID, business key, topic, partition, offset, and correlation ID are needed; payloads may contain personal data or sensitive information.

## 12. Securing producer connections

In production environments, producers may require TLS and SASL to authenticate and encrypt connections to the Kafka cluster. Security properties can be configured at the `spring.kafka.properties` level for shared use or under the producer properties branch if separation is needed.

Illustrative example of SASL_SSL with SCRAM:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka.example.internal:9093
    properties:
      security.protocol: SASL_SSL
      sasl.mechanism: SCRAM-SHA-512
      sasl.jaas.config: org.apache.kafka.common.security.scram.ScramLoginModule required username="producer-user" password="injected-secret";
~~~

The snippet above only illustrates property names and mechanisms. Do not commit real usernames/passwords to source control. In deployment, retrieve credentials from a secret manager, Kubernetes Secret, or protected environment variables. Also configure truststores/certificates according to the cluster's TLS requirements and verify that hostname verification is not arbitrarily disabled.

If the producer and consumer use different credentials, place configurations under each respective client instead of sharing all properties at the root level. The ACL permissions of the producer principal should only be sufficient to write to the required topics.

## 13. Testing producer configuration

Producer configuration should be tested at multiple levels:

### 13.1. Initialization configuration test

Verify that the application context creates ProducerFactory and KafkaTemplate with the right key/value types, bootstrap servers, and serializers. This step catches binding errors or missing dependencies, though it does not prove the producer can actually send records.

### 13.2. Integration testing with Kafka

Use Embedded Kafka or Testcontainers to run a broker in tests. Send records with KafkaTemplate and then read them from a test consumer or inspect listener results. You should verify:

- The topic receives the expected record.
- The key and payload are serialized properly.
- Returned metadata has valid topic, partition, and offset values.
- Consumers can deserialize the payload according to the contract.
- When the broker is unavailable or misconfigured, the application receives an observable send error.

Testcontainers is suitable when testing against a real broker close to the deployment environment. Embedded Kafka can be suitable for faster Spring Kafka tests. The choice depends on the project's version and test infrastructure.

### 13.3. Do not only check that the send call throws no exception

Because sending is asynchronous, returning from KafkaTemplate.send without throwing a synchronous exception does not prove the broker acknowledged the record. Tests must wait for the future to complete and verify the result or error within a bounded time.

An illustrative integration test:

~~~java
@Test
void shouldPublishOrderCreated() throws Exception {
    OrderCreated event = new OrderCreated(
        "evt-100",
        "order-100",
        new BigDecimal("125.50"),
        Instant.now()
    );

    SendResult<String, OrderCreated> result =
        kafkaTemplate.send("order-events", event.orderId(), event)
            .get(10, TimeUnit.SECONDS);

    assertThat(result.getRecordMetadata().topic())
        .isEqualTo("order-events");
    assertThat(result.getRecordMetadata().partition())
        .isGreaterThanOrEqualTo(0);
    assertThat(result.getRecordMetadata().offset())
        .isGreaterThanOrEqualTo(0);
}
~~~

This is an illustrative example; tests require the corresponding broker, topic, and KafkaTemplate bean. Do not rely on fixed offsets because offsets depend on topic state and data from other tests.

## 14. Monitoring producers in operations

A producer may still be running while send quality is degrading. Monitor these signals:

- **Record send rate:** number of records sent per second.
- **Request latency:** time for a request to reach the broker and receive a response.
- **Record queue time:** time a record stays in the producer buffer before being sent.
- **Retry rate:** number of times requests are retried.
- **Error rate:** send failures by exception type.
- **Buffer availability:** remaining available buffer capacity.
- **Batch size and compression rate:** batching and compression efficiency.
- **Metadata refresh and connection errors:** connection status and broker metadata.

If the retry rate rises, check broker leaders, network, and request timeouts. If queue time rises, the producer may be lingering too long for batches or the broker/network is falling behind. If buffer availability is frequently low, the producer is experiencing backpressure or buffer/send-rate settings are mismatched.

Do not simply increase buffer memory to mask slow brokers. A larger buffer delays when the application feels backpressure and increases memory usage, without increasing broker processing capacity.

## 15. Common configuration errors

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| Cannot connect to broker | Wrong bootstrap servers, DNS, port, or advertised.listeners | Check addresses from the application's exact runtime environment and broker metadata |
| Connects to bootstrap but sends time out | Leader broker address is unreachable or network is unstable | Check advertised.listeners, routes, firewalls, and broker leaders |
| SerializationException | Serializer does not support key/value types or payload is malformed | Check KafkaTemplate generics and configured serializers |
| Broker rejects send | ACLs, topic authorization, insufficient ISR, or quota | Check exception, principal, topic ACLs, and ISR state |
| Send succeeds but event appears multiple times | Application resends the same event or retries at business layer | Check event ID, callbacks, application retries, and idempotency |
| Producer buffer full | Broker is slow or send rate exceeds cluster capacity | Monitor buffer availability, queue time, request latency, and record rate |
| Latency increases during low traffic | linger.ms or batching waits too long | Measure queue time and adjust linger to match latency targets |
| High CPU usage | CPU-heavy compression or serializing large payloads | Compare compression types, payload sizes, and CPU profiles |
| Future fails after service has already returned | Asynchronous send; error only surfaces upon acknowledgment | Observe future/callback and decide whether waiting on the result is necessary |

## 16. Pre-production producer checklist

Before releasing, confirm:

1. Bootstrap servers point to the right cluster and broker advertised addresses are reachable from the runtime environment.
2. Key/value serializers are compatible with data types and consumer contracts.
3. Keys are chosen appropriately for business partitioning and ordering requirements.
4. Acknowledgments (`acks`) match the criticality of the events.
5. Idempotence and retries are configured consistently with reliability requirements.
6. Delivery timeout, request timeout, and max block timeout have appropriate values.
7. Batching, linger, buffer, and compression have been evaluated for latency, throughput, and memory.
8. TLS/SASL and ACLs are properly configured if the cluster requires authentication.
9. Send futures/callbacks are observed; send errors are not ignored.
10. Integration tests and metrics exist to detect connection errors, retries, buffer pressure, and latency.

Basic producer configuration is not merely declaring a broker address and serializers. It is a set of decisions about connectivity, data formats, durability, timeouts, and resource usage. When these decisions are clearly documented and tested, KafkaTemplate provides a reliable event-publishing path for business services.

