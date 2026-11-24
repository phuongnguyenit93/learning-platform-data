# Producer interceptor

In Spring Kafka, a **Producer interceptor** is an extension point of the Kafka producer client for observing or modifying records at send time and when receiving acknowledgement results. The interceptor runs inside the producer process before the record is sent over the network to the broker. It is useful for shared cross-cutting concerns such as adding correlation headers, standardizing technical metadata, or collecting send metrics.

The producer interceptor belongs to the Kafka client API (`org.apache.kafka.clients.producer.ProducerInterceptor`). Because Spring Kafka uses the Kafka producer underneath, a Spring Boot application can configure interceptors via producer properties. This interceptor is not a broker-side interceptor, nor is it Spring Kafka's consumer-side `RecordInterceptor`.

## 1. Position of the interceptor in the send pipeline

When the application calls `KafkaTemplate.send()`, Spring Kafka hands the record to the Kafka producer. The Kafka producer invokes the interceptors before serializing and sending the record. Next, the producer determines the partition, serializes the key/value, places the record into a batch, and sends the request to the broker. When an acknowledgement or send error arrives, the producer invokes the interceptor's callback.

```text
Spring Application
      |
      | KafkaTemplate.send(record)
      v
Kafka producer
      |
      v
ProducerInterceptor.onSend(record)
      |
      v
Serialize key/value and choose partition
      |
      v
Batch and send request to broker
      |
      v
Broker processes record
      |
      v
ProducerInterceptor.onAcknowledgement(metadata, exception)
      |
      v
Send callback / future
```

`onSend()` runs on the thread calling send and may return a new `ProducerRecord`. The returned record continues through subsequent interceptors and the producer's send pipeline. `onAcknowledgement()` is called when the producer receives an acknowledgement or determines the send failed. This callback may run on the producer's I/O thread, so it must execute quickly and avoid blocking.

If multiple interceptors are configured, Kafka calls `onSend()` in the order of the configured list. Acknowledgement callbacks are called in reverse order. Therefore, interceptor ordering can affect the metadata seen by later interceptors and how interceptors observe results.

## 2. Methods of ProducerInterceptor

The Kafka interface defines four main methods:

| Method | When called | Responsibility |
|---|---|---|
| `configure(Map<String, ?> configs)` | When Kafka instantiates the interceptor | Read producer configs and initialize needed resources |
| `onSend(ProducerRecord<K, V> record)` | Before the producer serializes and sends the record | Observe or return a modified record |
| `onAcknowledgement(RecordMetadata metadata, Exception exception)` | When the send completes with success or failure | Record send outcome and technical metrics |
| `close()` | When the producer closes the interceptor | Release resources owned by the interceptor |

### 2.1. `configure()`

Kafka calls `configure()` when initializing the interceptor. The method receives the producer configuration map. You can read interceptor-specific parameters or prepare internal objects. Avoid opening network connections, loading large datasets, or performing long-running work here because producer initialization may be delayed.

The Kafka client typically instantiates interceptors from class names declared in `interceptor.classes`. Therefore, standard configuration requires a no-argument constructor and you should not assume the interceptor is automatically a Spring bean capable of `@Autowired` dependency injection.

### 2.2. `onSend()`

`onSend()` receives the record before serialization. This is a suitable place to add technical headers, such as a correlation ID if the record does not have one yet. The method can return the original record or construct a new record with adjusted metadata.

Keep `onSend()` lightweight, deterministic, and free of external side effects. Do not make synchronous calls to databases, REST APIs, identity services, or remote logging systems inside this method. Every send passes through this path, so any slow operation directly increases send latency and reduces throughput.

Modifying the key or partition can change where the record is stored and the observable business ordering. Modify those fields only when there is an explicit routing rule. Do not use an interceptor to silently alter business payloads.

### 2.3. `onAcknowledgement()`

This method receives `RecordMetadata` when the send succeeds and `Exception` when the send fails. On success, the metadata can provide the record's topic, partition, offset, and timestamp. On failure, metadata may be null; check `exception` before reading metadata.

This is a good place to update counters or record lightweight technical outcomes. Do not perform manual retries inside this callback. Producer retries are already governed by Kafka producer settings such as `retries` and `delivery.timeout.ms`; re-sending inside the callback can create loops or amplify load.

For transactional producers, a record's acknowledgement callback does not mean the transaction containing that record has committed. A record may be acknowledged by the broker at the produce-request level while the transaction is later aborted. If you need to know the transaction commit outcome, track transaction results at the application's transaction management layer.

### 2.4. `close()`

Kafka calls `close()` when the producer shuts down. If the interceptor owns resources such as a dedicated executor or registry, release them here. Avoid creating separate threads or clients unless truly necessary; shared resources should generally be managed by the application and Spring lifecycle.

## 3. Example: adding a correlation ID to headers

Suppose events flow across multiple services and operations teams need to find logs belonging to the same processing flow. A producer interceptor can add an `x-correlation-id` header when the record does not already carry it. If the application already propagated a correlation ID from an incoming request or upstream service, the interceptor preserves that value.

```java
package com.example.kafka;

import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.UUID;

import org.apache.kafka.clients.producer.ProducerInterceptor;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.clients.producer.RecordMetadata;
import org.apache.kafka.common.header.Headers;
import org.apache.kafka.common.header.internals.RecordHeaders;

public class CorrelationIdProducerInterceptor
        implements ProducerInterceptor<String, String> {

    private static final String HEADER_NAME = "x-correlation-id";

    @Override
    public ProducerRecord<String, String> onSend(
            ProducerRecord<String, String> record) {

        Headers headers = new RecordHeaders(record.headers());

        if (headers.lastHeader(HEADER_NAME) == null) {
            String correlationId = UUID.randomUUID().toString();
            headers.add(
                    HEADER_NAME,
                    correlationId.getBytes(StandardCharsets.UTF_8));
        }

        return new ProducerRecord<>(
                record.topic(),
                record.partition(),
                record.timestamp(),
                record.key(),
                record.value(),
                headers);
    }

    @Override
    public void onAcknowledgement(
            RecordMetadata metadata,
            Exception exception) {

        if (exception != null) {
            // Update error counter using a thread-safe, non-blocking operation.
            return;
        }

        if (metadata != null) {
            // Optionally record topic/partition/offset into a lightweight metric.
        }
    }

    @Override
    public void configure(Map<String, ?> configs) {
        // No additional configuration needed in this example.
    }

    @Override
    public void close() {
        // Release owned resources if the interceptor holds any.
    }
}
```

The example copies headers into a new `RecordHeaders` instance to add metadata without mutating the input record's header collection directly. The `ProducerRecord` constructor preserves the original topic, partition, timestamp, key, and value. If a correlation ID already exists, the interceptor does not overwrite it.

In production, clearly define how correlation IDs are generated. If multiple records originate from the same business request, the ID should be created at the request or event layer and propagated across services. Generating a UUID inside the interceptor is only a fallback when no ID is present. If every record in a batch receives its own generated UUID, they will not share the same correlation ID even though they came from the same business operation.

## 4. Registering the interceptor in Spring Boot

Declare the interceptor class in Spring Boot's producer configuration. The example below uses string serializers for illustration:

```properties
spring.kafka.producer.key-serializer=org.apache.kafka.common.serialization.StringSerializer
spring.kafka.producer.value-serializer=org.apache.kafka.common.serialization.StringSerializer
spring.kafka.producer.properties[interceptor.classes]=com.example.kafka.CorrelationIdProducerInterceptor
```

The `interceptor.classes` property is a Kafka producer configuration. Multiple classes can be declared as a comma-separated list of class names. Each interceptor must be compatible with the key/value types used by the producer and must be instantiable by the Kafka client.

In applications with multiple `ProducerFactory` or `KafkaTemplate` beans, verify that the interceptor configuration is applied to the intended producer factory. A producer created by a different factory may not use this interceptor. Declaring it in one producer configuration does not automatically affect every Kafka producer in the JVM.

After configuring, you can verify by sending a record without `x-correlation-id` and confirming the header appears at the consumer or in a Kafka inspection tool. Then send a record that already carries the header to confirm the interceptor preserves the existing value. Also test the failure path to ensure the error callback does not cause secondary exceptions or block the producer.

## 5. Producer interceptor, ProducerListener, and RecordInterceptor

Spring Kafka provides several similarly named extension points that run at different stages. Choosing the right mechanism avoids putting logic in the wrong layer.

| Mechanism | Location | Suitable use cases |
|---|---|---|
| Kafka `ProducerInterceptor` | Inside the Kafka producer client, before sending and upon send result | Adding technical headers, observing the producer at the client level |
| Spring Kafka `ProducerListener` | `KafkaTemplate` callback on send success or failure | Handling send results in a Spring application, using Spring-managed dependencies |
| Spring Kafka `RecordInterceptor` | Consumer listener container side, before invoking the listener | Observing or modifying records before the listener processes them |
| `KafkaTemplate` callback / `CompletableFuture` | At each application send call | Handling the result specifically for one send operation |

### 5.1. When Spring-managed dependencies are needed

The Kafka client instantiates `ProducerInterceptor` from producer configuration. Therefore, do not place logic inside an interceptor that depends on Spring repositories, services, or beans and assume Spring will auto-inject them. If you need Spring-managed dependencies to handle send results, `ProducerListener` is usually a better fit.

Listener example:

```java
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.clients.producer.RecordMetadata;
import org.springframework.kafka.support.ProducerListener;

public class OrderProducerListener
        implements ProducerListener<String, OrderCreated> {

    @Override
    public void onSuccess(
            ProducerRecord<String, OrderCreated> record,
            RecordMetadata metadata) {
        // Record send success using application beans
        // after the listener is registered with KafkaTemplate.
    }

    @Override
    public void onError(
            ProducerRecord<String, OrderCreated> record,
            RecordMetadata metadata,
            Exception exception) {
        // Record send error and trigger appropriate application-level handling.
    }
}
```

Register the listener on the active `KafkaTemplate`. Explicit configuration example:

```java
@Configuration
class OrderKafkaConfiguration {

    @Bean
    ProducerListener<String, OrderCreated> orderProducerListener() {
        return new OrderProducerListener();
    }

    @Bean
    KafkaTemplate<String, OrderCreated> orderKafkaTemplate(
            ProducerFactory<String, OrderCreated> producerFactory,
            ProducerListener<String, OrderCreated> producerListener) {
        KafkaTemplate<String, OrderCreated> template =
                new KafkaTemplate<>(producerFactory);
        template.setProducerListener(producerListener);
        return template;
    }
}
```

This example creates an explicit `KafkaTemplate` from `ProducerFactory` and attaches the listener to it. In an application using Spring Boot's auto-configured `KafkaTemplate`, attach the listener to the existing template or customize the bean according to your application structure. Do not create an unintended extra `KafkaTemplate` just to register a listener. Callbacks should still remain brief because they execute on the producer's send-completion path.

### 5.2. When record processing is needed on the consumer side

Spring Kafka's `RecordInterceptor` is attached to the listener container and runs before the listener method. It can be used to enrich consumption context or skip records according to designed rules. It does not intercept records being sent by a producer. Do not confuse `RecordInterceptor` with Kafka `ProducerInterceptor` simply because both have interceptor in their names.

## 6. Limitations to understand clearly

### 6.1. Interceptors do not replace send acknowledgement

`onSend()` is called before broker acknowledgement. The interceptor finishing only means the record passed through the client-side hook; it does not prove the broker stored the record. The application must still handle the future/callback from `KafkaTemplate.send()` or `ProducerListener` to learn the send outcome.

Similarly, `onAcknowledgement()` only provides the result at the record produce-request level. When Kafka transactions are enabled, a success callback for a record is not proof that the transaction committed. Transaction outcomes must be tracked separately.

### 6.2. Do not use exceptions to reject records

The Kafka producer catches and logs exceptions thrown by interceptor methods to prevent an interceptor from breaking the client's send pipeline. Consequently, throwing an exception inside `onSend()` is not a reliable way to reject a record or enforce mandatory validation. If data is invalid, validate at the service/domain layer before calling `KafkaTemplate.send()` and return a clear error to the caller.

### 6.3. No exactly-once guarantee for side effects

Interceptors do not make sending, writing to a database, or calling external services outside Kafka an atomic transaction. Adding an event ID or correlation ID to headers also does not automatically deduplicate events. If a consumer receives the same event again, the target system still needs idempotency or a suitable deduplication mechanism.

If you need exactly-once semantics in a Kafka-to-Kafka flow, you must properly configure and use Kafka transactions alongside consumers reading with `read_committed`. If there are side effects outside Kafka, design an outbox/inbox or equivalent consistency mechanism at the business layer.

### 6.4. Do not block the producer thread

`onSend()` sits on the client's synchronous send path; slow processing slows down sends. `onAcknowledgement()` may run on the I/O thread; blocking this thread can delay handling of other responses. Do not perform the following inside an interceptor:

- Synchronous calls to REST APIs, databases, or external services.
- Long lock waits, sleeps, or waiting on futures to complete.
- Re-serializing large payloads without an explicit requirement.
- Logging entire payloads for every record at high throughput.
- Implementing custom retries or sending new records inside the acknowledgement callback.

If asynchronous processing is needed, consider a bounded internal queue with a full-queue policy. Do not create an unbounded executor inside an interceptor because executor backlog can become a new source of memory exhaustion.

### 6.5. Protecting metadata and sensitive data

Kafka headers are transmitted with the record and can be read by multiple consumers, observability tools, or storage systems. Do not put access tokens, passwords, session secrets, or unnecessary personal data into headers. Correlation IDs should be technical identifiers containing no secret information.

When modifying headers, preserve existing headers and avoid appending duplicate values if your system conventions require uniqueness. Also standardize encoding, header names, and how invalid values sent by upstream services are handled.

## 7. Observability and error handling

Interceptors can provide additional signals about send outcomes, but they should work alongside Kafka producer metrics and business metrics. Metrics worth observing include:

- Successful and failed send counts.
- Error rate by topic and exception type.
- Producer-side send duration or acknowledgement time.
- Retry counts and timeout errors.
- Count of records receiving a fallback correlation header.

Do not use event IDs, correlation IDs, or high-cardinality keys as metric labels because they create huge cardinality. Use metrics with bounded labels such as application, cluster, topic, and outcome; store detailed IDs in controlled logs or traces.

Common troubleshooting scenarios:

| Symptom | Possible cause | Resolution |
|---|---|---|
| Header does not appear | Producer is using a different factory; interceptor is not registered; record was sent by another producer | Check `interceptor.classes` configuration on the right producer factory and inspect records at the consumer |
| Header is overwritten or duplicated | Interceptor does not check existing headers; multiple interceptors modify the same header | Standardize header ownership rules, check before adding, and verify interceptor order |
| Slow record sends after adding interceptor | `onSend()` performs heavy work or waits on I/O | Remove blocking operations, measure hook duration, and move business logic to another layer |
| Exception in interceptor but record is still sent | Kafka client catches interceptor exceptions to protect the send pipeline | Perform mandatory validation before `KafkaTemplate.send()`; do not use interceptor exceptions as a rejection mechanism |
| Metric shows success but transaction aborted | Record acknowledgement callback does not reflect final transaction commit outcome | Track transaction outcomes separately and only publish business completion after transaction commit |
| Unable to inject Spring beans | Kafka client instantiates the interceptor from the class config | Keep interceptors lightweight without Spring dependencies, or use Spring-managed `ProducerListener`/callbacks |

When investigating, distinguish errors in the interceptor hook from serialization errors, connection errors, broker errors, and business errors. An interceptor cannot fix broker errors from the client side; metrics and exceptions must retain enough context to pinpoint the failing layer.

## 8. Testing interceptors

Testing should focus on the behavior the interceptor is responsible for, while keeping integration tests for Kafka producer configuration.

### 8.1. Unit testing `onSend()`

Cases to test:

1. Record without correlation ID: result contains a valid header.
2. Record already having correlation ID: existing value is preserved.
3. Record with other headers: those headers still exist after the interceptor runs.
4. Topic, partition, timestamp, key, and value: unchanged except per designed rules.
5. Header encoding: value is encoded and decoded using the same standard, such as UTF-8.

Conceptual JUnit test example:

```java
@Test
void addsCorrelationIdWhenMissing() {
    CorrelationIdProducerInterceptor interceptor =
            new CorrelationIdProducerInterceptor();

    ProducerRecord<String, String> input =
            new ProducerRecord<>("orders", "order-42", "created");

    ProducerRecord<String, String> output = interceptor.onSend(input);

    Header header = output.headers().lastHeader("x-correlation-id");
    assertNotNull(header);
    assertFalse(new String(header.value(), StandardCharsets.UTF_8).isBlank());
    assertEquals("orders", output.topic());
    assertEquals("order-42", output.key());
    assertEquals("created", output.value());
}
```

If your project's Java version does not support `String.isBlank()`, you can use `trim().isEmpty()` in the assertion. Unit tests do not require a Kafka connection because they only verify record transformation inside the interceptor.

### 8.2. Integration testing

Initialize the producer with `interceptor.classes` configured in a test Kafka environment. Send a record via `KafkaTemplate`, read the record from the topic, and verify the header is stored by the broker with the record. Test records with pre-existing headers, records without headers, and the send-failure path.

If the application has multiple producer factories, test each relevant factory. A test on the default factory does not prove that a producer for another stream has registered the interceptor. With transactions, include commit and abort cases to ensure application metrics or logs do not confuse record acknowledgement with transaction outcome.

## 9. Design principles for production

A production interceptor should be small in scope, predictable in behavior, and low in execution overhead. Before deploying, align on the following principles:

1. Use interceptors only for technical metadata or general producer observability.
2. Generate correlation IDs at the request/event layer whenever possible; the interceptor only supplies a fallback value.
3. Do not depend on Spring dependency injection in interceptors instantiated by the Kafka client.
4. Do not use interceptor exceptions for validation or record rejection.
5. Do not perform blocking I/O in `onSend()` or `onAcknowledgement()`.
6. Do not treat record acknowledgement callbacks as transaction commit results.
7. Preserve existing keys, partitions, timestamps, payloads, and headers unless an approved rule dictates otherwise.
8. Monitor producer performance before and after enabling an interceptor; keep the ability to disable the interceptor config to isolate incidents if needed.
9. Verify every `ProducerFactory` that actually sends data to the target topics.
10. Do not put secrets or sensitive data into headers or metric labels.

A producer interceptor is a small hook in the Kafka client's send lifecycle. When used within its proper scope, it helps standardize metadata and improve observability for Spring Kafka streams. Requirements around business validation, retries, idempotency, transactions, and send-result handling still need to be addressed at the layers responsible for them.
