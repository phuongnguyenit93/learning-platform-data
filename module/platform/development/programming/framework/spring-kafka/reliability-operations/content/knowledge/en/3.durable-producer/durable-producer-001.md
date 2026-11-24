# KafkaTemplate and the Send Path

## 1. Role of KafkaTemplate in Spring Kafka

`KafkaTemplate<K, V>` is the application-layer API for sending records to Kafka. It hides most low-level Kafka producer operations while integrating with the Spring ecosystem such as message conversion, transactions, producer factory, and asynchronous callbacks.

In a Spring Kafka application, the common path is:

1. Business code calls a `KafkaTemplate.send(...)` method.
2. KafkaTemplate creates or receives a `ProducerRecord`, then obtains a producer from `ProducerFactory`.
3. The Kafka producer serializes key/value, determines the partition, and places the record into the send buffer.
4. Kafka's sender thread groups records into batches and sends a Produce request to the partition's broker leader.
5. The broker processes the record and responds according to the `acks` configuration.
6. The producer callback completes the `CompletableFuture<SendResult<K, V>>` returned by KafkaTemplate.
7. The application receives the result or error and records the send status.

This diagram illustrates the path at a high level:

~~~mermaid
sequenceDiagram
    participant S as Business Service
    participant T as KafkaTemplate
    participant F as ProducerFactory
    participant P as KafkaProducer
    participant A as Record accumulator
    participant B as Broker leader

    S->>T: send(topic, key, value)
    T->>F: get producer
    F-->>T: KafkaProducer
    T->>P: send(ProducerRecord, callback)
    P->>P: serialize key/value
    P->>P: select partition
    P->>A: append record to batch
    A->>B: Produce request
    B-->>A: Produce response
    A-->>P: callback metadata or exception
    P-->>T: complete callback
    T-->>S: CompletableFuture completes
~~~

KafkaTemplate is responsible for connecting the Spring API with the Kafka producer. Network transmission, batching, producer-layer retries, and the broker protocol are handled by the Kafka client. The broker does not call back into the sending application's listener; consumers on the receiving side read records independently afterward.

## 2. ProducerFactory and KafkaProducer

### 2.1. ProducerFactory

`ProducerFactory<K, V>` is the Spring Kafka abstraction used to create and provide Kafka producers. `DefaultKafkaProducerFactory` is the common implementation, taking producer configurations such as bootstrap servers, serializers, acks, retries, compression, and other client settings.

KafkaTemplate uses ProducerFactory to obtain an appropriate producer for a send operation. The factory also manages the producer lifecycle and supports binding a producer to a transaction when the application enables Kafka transactions. Therefore, when configuring multiple KafkaTemplates or multiple producer factories, you must clearly specify which template sends to which Kafka cluster and which serializers/transactions it uses.

Java configuration example:

~~~java
@Configuration
public class KafkaProducerConfiguration {

    @Bean
    public ProducerFactory<String, OrderCreated> orderProducerFactory(
        KafkaProperties kafkaProperties
    ) {
        Map<String, Object> properties = new HashMap<>(
            kafkaProperties.buildProducerProperties()
        );

        properties.put(ProducerConfig.ACKS_CONFIG, "all");
        properties.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);

        return new DefaultKafkaProducerFactory<>(properties);
    }

    @Bean
    public KafkaTemplate<String, OrderCreated> orderKafkaTemplate(
        ProducerFactory<String, OrderCreated> orderProducerFactory
    ) {
        return new KafkaTemplate<>(orderProducerFactory);
    }
}
~~~

This is an illustrative example; how properties are retrieved from `KafkaProperties` may differ across Spring Boot versions. In real projects, use a unified configuration source and avoid creating multiple duplicate producer factories unless there is a specific requirement.

### 2.2. KafkaProducer

`KafkaProducer<K, V>` is the Apache Kafka client. The producer receives records, performs serialization, selects partitions, manages buffers, and sends requests asynchronously. KafkaTemplate calls the producer API and translates results into Spring's abstraction.

Normally, business code does not need to instantiate KafkaProducer directly. Using KafkaTemplate integrates the application with Spring configuration, resource management, and framework transactions. When low-level operations or a Kafka client API not wrapped by KafkaTemplate are needed, you can use a callback to access the producer via the template's execute APIs, but limit logic there so client details do not leak into services.

## 3. Ways to Call KafkaTemplate.send

KafkaTemplate provides multiple overloads to describe a record at varying levels of detail. Commonly used overloads include:

| Call | When to use |
|---|---|
| `send(topic, data)` | Send a value to a topic, letting the partitioner decide the partition |
| `send(topic, key, data)` | Send a record with a key for routing and per-key ordering |
| `send(topic, partition, key, data)` | Specify a concrete partition |
| `send(topic, partition, timestamp, key, data)` | Specify both partition and timestamp |
| `send(ProducerRecord)` | Full control over topic, partition, timestamp, key, value, and headers |
| `send(Message<?>)` | Send a Spring Message, leveraging payload and message headers |
| `sendDefault(...)` | Send to the default topic configured for KafkaTemplate |

Exact overload signatures may vary by Spring Kafka version. When upgrading dependencies, verify against the API of the version in use.

### 3.1. Sending a Simple Value

~~~java
@Service
@RequiredArgsConstructor
public class OrderPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public CompletableFuture<SendResult<String, OrderCreated>> publish(
        OrderCreated event
    ) {
        return kafkaTemplate.send("orders", event.orderId(), event);
    }
}
~~~

In this example, `orderId` is the key. Events with the same key are normally sent to the same partition by the default partitioner, allowing Kafka to preserve the order of those records within the partition. If no key is provided, the producer can still choose a partition according to the client's partitioner mechanism and batching policy.

### 3.2. Creating a ProducerRecord to Control Metadata

When you need to set a timestamp, partition, or headers, create a `ProducerRecord` before calling send:

~~~java
public CompletableFuture<SendResult<String, OrderCreated>> publish(
    OrderCreated event,
    String correlationId
) {
    ProducerRecord<String, OrderCreated> record =
        new ProducerRecord<>("orders", null, event.orderId(), event);

    record.headers().add(
        "correlation-id",
        correlationId.getBytes(StandardCharsets.UTF_8)
    );

    return kafkaTemplate.send(record);
}
~~~

`ProducerRecord` makes the record's metadata explicit in sending code. Ensure header values are encoded under a consistent convention between producer and consumer. Avoid placing secret data or large payloads in headers.

If a partition is explicitly specified, that partition is used instead of the result calculated by the partitioner. The application must ensure the partition exists and that manual assignment does not break load distribution strategies.

### 3.3. Sending a Spring Message

`send(Message<?>)` is useful when the application already works with Spring Messaging's `Message<?>` abstraction. The payload becomes the value and certain headers can be mapped to Kafka metadata via a message converter.

~~~java
Message<OrderCreated> message = MessageBuilder
    .withPayload(event)
    .setHeader(KafkaHeaders.TOPIC, "orders")
    .setHeader(KafkaHeaders.KEY, event.orderId())
    .setHeader("correlation-id", correlationId)
    .build();

kafkaTemplate.send(message);
~~~

Header mapping behavior depends on the message converter and Spring Kafka configuration. If explicit control over partition, timestamp, or Kafka headers is needed, `ProducerRecord` is usually easier to read and less dependent on conversion conventions.

## 4. Internal Path Inside a send Call

### 4.1. From Service to KafkaTemplate

When a service calls `send()`, KafkaTemplate builds a record from the parameters or accepts the record provided by the application. For `send(Message<?>)`, the template uses a message converter to convert the Spring Message into a ProducerRecord.

Next, the template obtains a producer from ProducerFactory. If the template is configured to use transactions, the producer may bind to the active transaction. In the normal case, the factory provides a producer for the send and manages reusing or closing the producer according to the factory's mechanism.

Key point to remember: KafkaTemplate does not persist records to the broker itself. It is the orchestration layer calling the Kafka client; the final send outcome depends on the producer, the network, and the broker's response.

### 4.2. Serializing Key and Value

The Kafka producer must convert key and value into byte arrays before sending. Serializers are configured separately for key and value, for example:

- `StringSerializer` converts strings into bytes.
- Spring Kafka's `JsonSerializer` converts objects into JSON.
- Avro or Protobuf serializers can be used when the system manages schemas in those respective formats.

If serialization fails, the producer may raise an error immediately during the send call or complete the future exceptionally, depending on when and what kind of error occurs. This is a client-side failure; the record has not been acknowledged by the broker.

Producer and consumer must agree on the data format. With JSON, event structure, type headers, or target type configuration on the consumer must be aligned. A successful serialization only proves the object was converted to bytes, not that the consumer can deserialize or correctly understand the schema.

### 4.3. Selecting a Partition

The producer determines the partition in this general priority order:

1. If `ProducerRecord` specifies a partition, the producer uses that partition.
2. If there is a key, the partitioner uses the key and topic metadata to choose a partition.
3. If there is no key, the partitioner chooses a partition according to client policy, which may balance load and leverage batching.

A partition is Kafka's unit of ordering. Two records in the same partition are read in offset order; two records in different partitions have no guaranteed global order.

If the business logic requires ordering per order, account, or aggregate, use a stable identifier of the entity as the key. When changing the partition count, the mapping from key to partition can change; increasing partitions can affect ordering for a key between old and new records. Therefore, changing the partition count is an operational decision that must be evaluated beforehand.

### 4.4. Buffering and Batching

After serializing and determining the partition, the producer places the record into the send buffer. The Kafka client groups records for the same partition into batches to reduce request count and increase throughput. The sender thread transmits ready batches to the broker.

Configurations with direct impact:

| Configuration | Role |
|---|---|
| `batch.size` | Target batch size for a single partition |
| `linger.ms` | Time the producer can wait for additional records to fill a batch |
| `buffer.memory` | Producer buffer capacity used for records waiting to be sent |
| `compression.type` | Batch compression algorithm |
| `max.request.size` | Size limit of a request sent by the producer |

Large batches and high linger can increase throughput, but also increase wait time before sending. Too small a buffer or a slow broker can cause the producer to wait for buffer space or hit timeout errors. Measure actual load to balance latency and throughput.

### 4.5. Sending Requests and Receiving Broker Responses

The sender thread sends a Produce request to the partition's broker leader. The broker checks write permissions, partition state, ISR conditions, and other constraints; then it processes the record according to the Kafka protocol.

The producer waits for a response according to the `acks` configuration:

- `acks=0`: do not wait for broker acknowledgement.
- `acks=1`: wait for the leader to acknowledge after writing.
- `acks=all`: wait for replicas in the ISR to satisfy the acknowledgement condition according to cluster configuration.

After receiving the response, the Kafka client invokes the callback for the corresponding record or batch. KafkaTemplate translates that result into a `SendResult` or completes the future with an exception.

A successful response indicates the producer received acknowledgement according to the acks policy. It does not mean a consumer has read the record or that downstream business processing has completed.

## 5. Handling Asynchronous Results

### 5.1. CompletableFuture in Spring Kafka 3.x

Starting with Spring Kafka 3.0, send methods return `CompletableFuture<SendResult<K, V>>`. Applications can register callbacks using `whenComplete`, `thenAccept`, or `exceptionally`.

~~~java
public void publish(OrderCreated event) {
    kafkaTemplate.send("orders", event.orderId(), event)
        .whenComplete((result, error) -> {
            if (error != null) {
                log.error("Publish failed for order {}", event.orderId(), error);
                return;
            }

            RecordMetadata metadata = result.getRecordMetadata();
            log.info(
                "Published order {} to {}-{} offset {}",
                event.orderId(),
                metadata.topic(),
                metadata.partition(),
                metadata.offset()
            );
        });
}
~~~

`SendResult<K, V>` contains the sent record and the `RecordMetadata` returned by the Kafka client. Metadata typically provides topic, partition, offset, timestamp, and record size. This data is useful for logging, tracing, and incident investigation.

Before Spring Kafka 3.0, the send API typically returned `ListenableFuture`. When reading old examples or upgrading applications, pay attention to this difference so you do not misuse the future type or callback.

### 5.2. Combining Multiple Asynchronous Operations

If you need to send multiple events without blocking the thread, you can combine futures:

~~~java
public CompletableFuture<Void> publishAll(List<OrderCreated> events) {
    List<CompletableFuture<SendResult<String, OrderCreated>>> sends =
        events.stream()
            .map(event -> kafkaTemplate.send(
                "orders",
                event.orderId(),
                event
            ))
            .toList();

    return CompletableFuture.allOf(
        sends.toArray(CompletableFuture[]::new)
    );
}
~~~

`allOf` completes when all futures complete. If one future fails, the combined future also completes exceptionally. If you need detailed results for each event, keep the list of futures and collect individual results/errors instead of relying solely on the combined future.

Do not create an unbounded number of futures for a large batch send. Limit concurrency or batch size at the application layer to avoid filling the producer buffer, increasing heap usage, and putting pressure on the broker.

### 5.3. Synchronous Sending by Waiting on the Future

There are cases where business logic must know the send result before proceeding. You can wait on the future with a timeout:

~~~java
public SendResult<String, OrderCreated> publishAndWait(
    OrderCreated event
) throws InterruptedException, ExecutionException, TimeoutException {
    return kafkaTemplate
        .send("orders", event.orderId(), event)
        .get(5, TimeUnit.SECONDS);
}
~~~

This approach blocks the calling thread until a result arrives or the timeout expires. Use it only when there is a clear reason and an appropriately designed timeout. If called on a high-traffic web server request thread, synchronous waiting can exhaust the thread pool and increase system-wide latency.

A timeout while waiting on the future does not prove the record was not written. The broker may have written the record, while the response was lost or delayed. If the application resends after a timeout, duplicate records may occur; a stable event ID and consumer idempotency help handle that case.

### 5.4. What Should a Callback Do?

Callbacks should perform short work: logging, incrementing metrics, completing a business future, or forwarding the result to a controlled processing mechanism. Kafka producer callbacks may run on the producer's I/O processing thread. Avoid executing slow database queries, synchronous HTTP calls, or heavy CPU processing directly in the callback because it can slow down sending other records.

If post-send processing is needed, use a dedicated executor or internal event mechanism. The executor must have a bounded queue and a clear rejection policy; otherwise, offloading work to another thread merely moves the overload problem elsewhere.

## 6. Types of Errors on the Send Path

Send errors can occur at multiple stages:

| Stage | Error example | Meaning |
|---|---|---|
| Record creation | Invalid topic or parameters | The application constructed an invalid record |
| Serialization | Serializer cannot convert object | Data or format error |
| Metadata/buffer fetch | Timed out waiting for metadata or buffer | The client could not prepare the send in time |
| Sending to broker | Network exception, broker unavailable | Unreachable or connection interrupted |
| Broker processing | Authorization, record too large, not enough replicas | Broker rejected due to permissions or policy |
| Waiting for ack | Request timeout or delivery timeout | Final result not received within deadline |

### 6.1. Synchronous vs. Asynchronous Errors

Not all errors appear after the future is returned. Some configuration errors, record creation errors, or client errors can happen immediately when calling send. Errors occurring after the record enters the send pipeline are typically reported via the callback/future.

Therefore, for complete error handling, wrap the send call in a try/catch block and also register a callback on the future:

~~~java
public void publish(OrderCreated event) {
    try {
        kafkaTemplate.send("orders", event.orderId(), event)
            .whenComplete((result, error) -> {
                if (error != null) {
                    recordSendFailure(event, error);
                } else {
                    recordSendSuccess(event, result.getRecordMetadata());
                }
            });
    } catch (RuntimeException immediateFailure) {
        recordSendFailure(event, immediateFailure);
    }
}
~~~

Do not record success merely because the send method returned a future. Only a successfully completed callback/future indicates the producer received a success result according to the acknowledgement configuration.

### 6.2. Timeouts and the Meaning of Ambiguous Outcomes

Several timeouts must be distinguished:

- `max.block.ms` limits how long producer APIs can wait for metadata or buffer space before throwing an error.
- `request.timeout.ms` limits how long to wait for a response to a single request.
- `delivery.timeout.ms` limits the total time from calling send until reporting success or failure, including batch wait, request, and retry time.

Configuration names and defaults may vary by Kafka client version. Check the documentation for the exact running version.

When a delivery timeout occurs, the producer cannot always conclude the broker did not write the record. For example, the broker wrote the record but the response was lost on the network. The application must treat an ambiguous outcome as a potential duplicate if retried.

### 6.3. Producer Retries vs. Application Retries

The Kafka producer has internal retries for transient errors based on client configuration. With an idempotent producer, Kafka uses a producer ID and sequence number to prevent duplicates caused by internal retries within the idempotence mechanism's scope.

Application-level retry is a new send call, typically occurring when a service retries a request, restarts, or resends an event after being uncertain about a previous outcome. Producer idempotence does not automatically recognize every application-level resend as the same business operation. Therefore, events should have a stable ID and consumers should implement idempotency.

## 7. Producer Configurations Related to Send

An illustrative configuration in Spring Boot:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      acks: all
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      properties:
        enable.idempotence: true
        delivery.timeout.ms: 120000
        request.timeout.ms: 30000
        linger.ms: 5
        batch.size: 32768
        compression.type: snappy
~~~

Operational meaning:

- `bootstrap-servers` provides bootstrap addresses for the client to discover the broker cluster.
- `acks: all` requires acknowledgement from the ISR, and must be paired with replication factor and `min.insync.replicas` on the broker/topic.
- `enable.idempotence: true` reduces the risk of duplicates from internal producer retries.
- `delivery.timeout.ms` limits total delivery time; do not set it too low if the system experiences network latency or broker instability.
- `request.timeout.ms` limits the wait time for a single request.
- `linger.ms` and `batch.size` affect batching and latency.
- `compression.type` reduces transmission size in exchange for CPU spent on compression/decompression.

Do not copy this exact set of values into every environment. Choose timeouts according to SLA, measure throughput and latency, check broker limits, and monitor retry rates. If configuring idempotence explicitly, compatibility constraints between acks, retries, and max in flight must be satisfied as required by the Kafka client version.

## 8. KafkaTemplate with Transactions

KafkaTemplate can participate in Kafka transactions when configured with a transactional ProducerFactory. Transactions are useful when a flow needs to send multiple records atomically, or when a consumer reads a record, processes it, and sends output records within the same Kafka transaction.

Example using a transaction at the template layer:

~~~java
kafkaTemplate.executeInTransaction(operations -> {
    operations.send("order-events", orderId, orderCreated);
    operations.send("audit-events", orderId, auditEvent);
    return true;
});
~~~

Both records are sent in the same Kafka transaction. If the callback completes normally, the transaction is committed; if an exception occurs, the transaction can be aborted according to the template's mechanism. Verify exception handling and transaction configuration in the specific Spring Kafka version.

A Kafka transaction does not include a database or HTTP service. If an application updates a database and then publishes an event, a state can occur where the database committed but the Kafka transaction failed, or vice versa depending on operation order. When consistency between a database and Kafka is required, transactional outbox is usually the appropriate design: write business data and an outbox row in the same database transaction, then have a publisher read the outbox and send to Kafka.

## 9. Flush, Close, and Producer Lifecycle

### 9.1. Flush

`flush()` tells the producer to push pending buffered records immediately and wait for sending to complete according to Kafka client behavior. KafkaTemplate also exposes a flush method.

Do not call flush after every record in a high-throughput flow because it degrades batching efficiency. Only enable auto flush or call flush when specifically required, such as forcing buffered records to be sent before a synchronization point.

### 9.2. Producer Lifecycle

A producer is a resource holding network connections, buffers, and background threads. Spring Kafka manages producers through ProducerFactory and the bean/container lifecycle. Normal application code should not manually close the producer obtained from the template after each send.

If using the execute callback for low-level producer operations, adhere to that API's resource management contract. Do not retain a producer outside the factory's management scope, do not manually close a factory-managed producer, and do not create a new producer for every record.

## 10. Observing the Send Path

For stable operations, observe both application-level outcomes and Kafka producer metrics.

| Observation point | Useful information | Purpose |
|---|---|---|
| Before send | Event ID, topic, key, correlation ID | Know which event the application intends to send |
| Future/callback | Success, exception, completion time | Know what outcome the producer received |
| SendResult | Topic, partition, offset, timestamp | Trace where the record was written |
| Producer metrics | Request latency, record retry, error rate, buffer available bytes, batch size | Detect slow brokers or a congested producer |
| Broker metrics | Request handler, network processor, ISR, partition health | Identify issues in the Kafka cluster |

When logging success, include topic, partition, offset, and event ID. When logging errors, include exception class, topic, and event ID to aid investigation. Avoid logging full payloads if they contain personal information or sensitive data.

Producer metrics can be collected via Kafka client metrics or application monitoring integrations. Exact metric names depend on the Kafka client version and metrics system. Key metric groups to monitor include request latency, record send rate, retry rate, error rate, buffer utilization, batch size, and compression rate.

## 11. Common Design Mistakes

**Ignoring the future:** The service calls send and discards the result. Asynchronous errors go unrecorded at the business layer, making the application assume events were sent successfully.

**Waiting synchronously on every send:** Calling `get()` or `join()` right after every send loses asynchronous benefits, increases latency, and can exhaust thread pools.

**Blind retries after timeouts:** A timeout does not prove the record was not written. Resending without a stable event ID can create duplicate side effects on the consumer.

**Sending oversized payloads:** Large records put pressure on the producer buffer, network, and broker. Limit event size, send only necessary data, and use object storage/references for large payloads.

**Omitting the key:** The producer may distribute records without preserving order per business entity. If per-key ordering is required, choose a key with business meaning.

**Calling flush continuously:** Flushing every record hurts batching and throughput.

**Heavy processing inside callbacks:** Callbacks run on the producer's processing path; slow operations can affect other sends.

**Confusing send acknowledgement with business processing:** A successful future only confirms the producer received a send result per acks. It does not prove the consumer processed it or the database committed.

## 12. Diagnostic Procedure When Send Fails

When an event does not appear on the consumer side, trace sequentially:

1. Confirm the service called send with the right topic, key, and event ID.
2. Check for synchronous exceptions right at the send call.
3. Check whether the future/callback completed successfully or failed.
4. If successful, use topic, partition, and offset in SendResult to locate the record on Kafka.
5. If a timeout or network exception occurred, inspect producer retries, delivery timeout, broker availability, and partition state.
6. If the record already exists, shift investigation to consumer group, offsets, lag, deserialization, and listeners.

This layered approach avoids fixing the consumer when the producer has not sent the record, or retrying the producer when the broker has already written the record and the real issue lies in the consumer.

## 13. Principles for Using KafkaTemplate in Applications

- Inject KafkaTemplate via constructor so services are easy to test and dependencies are explicit.
- Use simple overloads for normal cases; use ProducerRecord when metadata control is needed.
- Choose keys according to the business entity that requires ordering.
- Track futures/callbacks and record both synchronous and asynchronous errors.
- Do not block threads unless there is an explicit synchronous requirement; if waiting is necessary, always set a timeout.
- Set limits for concurrent sends and batch sizes at the application layer.
- Choose compatible serializers/deserializers and schemas between producer and consumer.
- Configure acks, idempotence, retries, and timeouts according to SLA and cluster capability.
- Use transactions when atomicity within Kafka is needed; use outbox/inbox for database boundaries.
- Log event ID, topic, partition, offset, and correlation ID for traceability.

By clearly understanding the path from KafkaTemplate to the producer buffer, broker response, and future callback, operations teams can pinpoint exactly which step a send is failing at, distinguish client errors from broker errors, and handle timeouts without creating unintended duplicates.
