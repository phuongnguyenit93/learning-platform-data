# Testing a Successful Producer Send

In Spring Kafka, successfully calling **KafkaTemplate.send()** does not mean the message has been recorded by the broker. The producer sends data asynchronously: the initial call usually only places the record into the client's send path. The final result is returned after the broker responds or when the send attempt fails.

Therefore, a successful producer test needs to clearly define what it is proving:

- The application builds the right topic, key, value, and headers for the record.
- The broker receives the record and returns an acknowledgement according to the **acks** configuration.
- The record has valid metadata such as topic, partition, and offset.
- When deeper verification is needed, a consumer can read back the exact key and payload from the topic.

These verification levels complement each other. Unit tests check message construction logic; integration tests with a Kafka broker confirm that the actual send path works.

## 1. What counts as a successful send?

### 1.1 send() is an asynchronous operation

**KafkaTemplate.send()** sends a record through the Kafka producer. In Spring Kafka 3.x, the overloads of this method return **CompletableFuture<SendResult<K, V>>**. The future completes when the producer receives either a successful or failed send result.

For example:

~~~java
CompletableFuture<SendResult<String, String>> future =
        kafkaTemplate.send("orders", "order-42", "ORDER_CREATED");
~~~

Immediately after the line above, the record may still be sitting in the producer buffer or in flight to the broker. Returning a future should not be treated as proof that the broker has written the record.

In a test, you can wait for the result:

~~~java
SendResult<String, String> result =
        kafkaTemplate.send("orders", "order-42", "ORDER_CREATED")
                .get(10, TimeUnit.SECONDS);
~~~

If the send succeeds, get() returns SendResult. If the producer encounters an error, the future completes exceptionally and get() throws ExecutionException. If the test's wait deadline is exceeded, get() throws TimeoutException. The 10-second deadline here is the test's wait limit; it is not synonymous with the producer's delivery.timeout.ms configuration.

You should not use Thread.sleep() to wait for a send to finish. Sleep merely delays the test by a guessed duration, whereas the future directly represents the result of the send.

### 1.2 Meaning of broker acknowledgement

The acknowledgement level depends on the producer acks configuration:

| Value | Meaning | What the test can conclude |
|---|---|---|
| 0 | The producer does not wait for a broker acknowledgement | The future does not prove that the broker received the record |
| 1 | The partition leader acknowledges that it has written the record | The leader has acknowledged; data can still be lost if the leader fails before other replicas receive the record |
| all or -1 | The broker waits for replicas currently in the ISR to acknowledge according to the Kafka protocol | The record is acknowledged according to the ISR set and replication configuration at write time |

If the application's requirement is to report send success only after broker acknowledgement, the test must run with acks=1 or acks=all; for high durability requirements, acks=all is typically chosen along with an appropriate min.insync.replicas configuration on the broker/topic.

acks=all does not mean every broker in the cluster must acknowledge. It applies to the replicas currently in the in-sync replica set (ISR). Therefore, durability also depends on the replication factor, ISR, and min.insync.replicas.

### 1.3 Reading send result metadata

SendResult contains the record the producer sent and the RecordMetadata returned by the broker:

~~~java
RecordMetadata metadata = result.getRecordMetadata();

String topic = metadata.topic();
int partition = metadata.partition();
long offset = metadata.offset();
long timestamp = metadata.timestamp();
~~~

In tests, commonly useful assertions include:

- The topic matches the expected topic.
- The partition is non-negative.
- The offset is non-negative.
- The key and value of the producer record match the input data.

Metadata proves that the producer received an acknowledgement for the record under the current configuration. It does not yet prove that a downstream consumer has processed the record or that business side effects have completed.

## 2. Choosing the right type of test

| Test type | How it is implemented | What it proves |
|---|---|---|
| Unit test | Mock KafkaTemplate | The service calls the right topic, key, payload, and headers |
| Integration test | Use @EmbeddedKafka | Producer, serializer, broker, and send path work together |
| Integration test with broker container | Use Kafka in Testcontainers | Tests a configuration closer to the deployment environment |
| System test | Send to a real test cluster | Verifies ACLs, TLS, replication, broker policies, and environment configuration |

If the goal is to verify a successful producer send, a unit test only confirms the call to a mock. A mock can return a completed future even when no broker exists. Therefore, at least one integration test connected to a broker is needed to confirm actual acknowledgement.

## 3. Testing with Embedded Kafka

Spring Kafka provides spring-kafka-test with @EmbeddedKafka, EmbeddedKafkaBroker, and KafkaTestUtils. An embedded broker is well suited for fast integration tests that run alongside the test suite without needing a shared Kafka cluster.

### 3.1 Declaring the dependency

With Spring Boot, add the test dependency matching the Spring Kafka version managed by Spring Boot:

~~~xml
<dependency>
    <groupId>org.springframework.kafka</groupId>
    <artifactId>spring-kafka-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Usually you do not need to specify the version manually if the project uses Spring Boot dependency management. If managing versions manually, make sure spring-kafka-test is compatible with the spring-kafka version in the application.

### 3.2 Configuring a test with a single topic

The example below uses KafkaTemplate<String, String> to focus on send behavior. In a real application, the serializer must match the data types used by the producer.

~~~java
import java.util.Map;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.kafka.test.utils.KafkaTestUtils;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(properties = {
    "spring.kafka.producer.acks=all",
    "spring.kafka.producer.key-serializer=org.apache.kafka.common.serialization.StringSerializer",
    "spring.kafka.producer.value-serializer=org.apache.kafka.common.serialization.StringSerializer"
})
@EmbeddedKafka(
    partitions = 1,
    topics = "orders",
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
class OrderProducerIntegrationTest {

    @Autowired
    private KafkaTemplate<String, String> kafkaTemplate;

    @Autowired
    private EmbeddedKafkaBroker embeddedKafka;

    @Test
    void shouldSendRecordAndReceiveBrokerAcknowledgement() throws Exception {
        Map<String, Object> consumerProps =
                KafkaTestUtils.consumerProps(
                        "producer-send-test",
                        "false",
                        embeddedKafka
                );

        try (Consumer<String, String> consumer =
                     new DefaultKafkaConsumerFactory<String, String>(
                             consumerProps
                     ).createConsumer()) {

            // Create the subscription before the producer sends the record.
            embeddedKafka.consumeFromAnEmbeddedTopic(consumer, "orders");

            SendResult<String, String> result =
                    kafkaTemplate.send(
                            "orders",
                            "order-42",
                            "ORDER_CREATED"
                    ).get(10, TimeUnit.SECONDS);

            assertEquals(
                    "orders",
                    result.getRecordMetadata().topic()
            );
            assertTrue(result.getRecordMetadata().partition() >= 0);
            assertTrue(result.getRecordMetadata().offset() >= 0);
            assertEquals(
                    "order-42",
                    result.getProducerRecord().key()
            );
            assertEquals(
                    "ORDER_CREATED",
                    result.getProducerRecord().value()
            );

            ConsumerRecord<String, String> received =
                    KafkaTestUtils.getSingleRecord(consumer, "orders");

            assertEquals("order-42", received.key());
            assertEquals("ORDER_CREATED", received.value());
        }
    }
}
~~~

A few points to note:

1. @EmbeddedKafka initializes the broker and the orders topic for the test.
2. bootstrapServersProperty injects the embedded broker address into the configuration Spring Boot uses to create KafkaTemplate.
3. The test creates the consumer and subscribes to the topic before sending. This prevents the consumer from missing the record by starting to read after publish time.
4. get(10, TimeUnit.SECONDS) waits for the acknowledgement and fails the test if the future completes with an exception or times out.
5. Assertions on RecordMetadata check the result returned by the broker; assertions on the consumer check that the record can be read from the topic.

KafkaTestUtils.getSingleRecord() waits for one record and checks the read result. If the test needs to handle multiple records, use getRecords() or poll the consumer and assert the count, keys, and values as required.

### 3.3 Why assert both the future and the consumer?

The two assertions answer two different questions:

- A successful future with metadata confirms that the producer received an acknowledgement from the broker according to the acks configuration.
- A consumer reading the record confirms that the record is present on the topic and can be consumed by a consumer group in the test.

If you only need to verify the send contract and acknowledgement, assertions on the future and metadata are usually enough. If you need to verify serializers, topic routing, key, payload, or readability, add consumer assertions.

The consumer in the example is an independent test consumer. It does not represent all of the application's business listener logic. To test a listener, a separate test is needed to verify that the listener receives the record and completes its corresponding side effects.

## 4. Testing a producer service instead of only testing KafkaTemplate

In applications, producers are often wrapped in a service to keep event-creation logic in one place:

~~~java
@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreated>> publish(
            OrderCreated event) {
        return kafkaTemplate.send(
                "orders",
                event.orderId(),
                event
        );
    }
}
~~~

Testing can be split into two parts:

- Unit tests for OrderEventPublisher using mocks to confirm the right topic, key, and event are sent. These tests are fast and focus on the service's logic.
- Integration tests using Embedded Kafka to call the real publisher, wait for the future to complete, and verify metadata or the record received by the consumer.

A mocked unit test should not be treated as proof that a producer successfully sends to Kafka. It only proves that the code asked the template to send a record.

## 5. Handling asynchronous results in application code

In production code, you normally should not block a thread with get() just to wait for the broker. Handle the future with a callback:

~~~java
public void publish(OrderCreated event) {
    kafkaTemplate.send("orders", event.orderId(), event)
            .whenComplete((result, exception) -> {
                if (exception != null) {
                    log.error(
                            "Cannot publish order event, orderId={}",
                            event.orderId(),
                            exception
                    );
                    return;
                }

                RecordMetadata metadata = result.getRecordMetadata();
                log.info(
                        "Published order event, orderId={}, partition={}, offset={}",
                        event.orderId(),
                        metadata.partition(),
                        metadata.offset()
                );
            });
}
~~~

Callbacks let the application observe send results without holding a waiting thread. For production systems, add metrics for send success/failure counts, retries, send latency, and errors by type. Avoid logging entire payloads or sensitive data.

If the calling layer needs to know that publishing succeeded before completing a workflow, return the future to that layer or design an appropriate business state. Do not swallow exceptions in the callback and report success to the caller when the record has not been acknowledged by the broker.

In Spring Kafka 2.x, the send API typically returned ListenableFuture and used addCallback(). Starting in Spring Kafka 3.0, the API moved to CompletableFuture; write tests against the project's actual dependency version.

## 6. Testing multiple records and send batches

When a producer sends multiple records, you should not wait only for the future of the last record. Each send() call has an independent result; one record succeeding does not prove that earlier records succeeded.

With Spring Kafka 3.x and Java 17 or higher, you can collect the futures:

~~~java
List<CompletableFuture<SendResult<String, String>>> futures =
        events.stream()
                .map(event -> kafkaTemplate.send(
                        "orders",
                        event.orderId(),
                        event.payload()
                ))
                .toList();

CompletableFuture.allOf(
        futures.toArray(new CompletableFuture<?>[0])
).get(10, TimeUnit.SECONDS);

for (CompletableFuture<SendResult<String, String>> future : futures) {
    SendResult<String, String> result = future.join();
    assertTrue(result.getRecordMetadata().offset() >= 0);
}
~~~

allOf() completes normally only when all input futures complete normally. If one future fails, waiting throws an error; when you need to report exactly which record failed, iterate over each future and record the corresponding result.

When testing consumer batch consumption, do not assume ordering across partitions. Kafka only guarantees ordering within a single partition. If a test needs business ordering, send records with the same key so they are routed to the same partition, then verify ordering within that partition.

## 7. Common mistakes when testing producers

| Symptom | Possible cause | How to check |
|---|---|---|
| Test passes even though the broker is not running | The test only mocks KafkaTemplate or does not wait for the future | Use Embedded Kafka and wait for the send result |
| get() throws ExecutionException | Broker error, topic does not exist under policy, serializer error, ACL rejection, or send timeout | Inspect getCause() and the root exception |
| Test times out | Broker is not ready yet, consumer setup is wrong, producer is retrying, or timeout configuration is too short | Check bootstrap servers, broker logs, and delivery timeout |
| Future succeeds but consumer does not see the record | Consumer started reading at the wrong time, improper offset reset, reading the wrong topic/partition, or record filtered by read configuration | Create the consumer before sending and check topic, group, and offset |
| Read key/value differs from expected | Incompatible serializer/deserializer or incorrect schema mapping | Check serializer configuration on both sides and actual payload |
| Test passes in isolation but fails when running the full suite | Reusing group ID, topic, or context; leftover test data | Use separate group IDs, separate topics, or isolate the context |

When a future fails, report the root cause instead of printing only the ExecutionException message. Common errors include SerializationException, TimeoutException, TopicAuthorizationException, RecordTooLargeException, and NotEnoughReplicasException.

Distinguish between two types of timeout:

- The timeout passed to future.get(timeout, unit) only limits how long the test waits for the result.
- delivery.timeout.ms limits how long the producer attempts to complete the send, including retries and waiting for acknowledgement.

These two limits can differ. If the test waits for less time than the producer is allowed to retry, the test may time out even while the producer is still sending. Set the test wait deadline large enough relative to the producer configuration and broker startup time.

## 8. Limitations of Embedded Kafka and when a real broker is needed

Embedded Kafka is useful for testing the send path, serializers, topics, and consumer record reading. However, a single-broker setup does not fully simulate a production cluster:

- Cannot test fault tolerance when a partition leader stops and another replica is elected leader.
- Cannot prove acks=all behavior with multiple replicas or min.insync.replicas policies.
- Does not fully represent ACLs, TLS, SASL, quotas, network policies, and real environment broker configurations.
- Does not replace compatibility testing for Kafka versions, schema registries, or production monitoring systems.

If producer requirements involve replication or failover, use a multi-broker Kafka test cluster, such as a properly configured Testcontainers environment or a dedicated integration cluster. If ACLs/TLS need to be verified, tests must run with the corresponding authentication mechanism and permissions.

Do not infer production durability from a passing Embedded Kafka test alone. Test results are only meaningful within the scope of the broker and configuration the test actually uses.

## 9. Test design checklist

Before concluding that a producer send succeeded, verify:

1. Does the test connect to a real broker or only mock KafkaTemplate?
2. What level is acks configured to, and does that level match the requirement?
3. Does the test wait for the future to complete and handle exceptional completion?
4. Does it check metadata such as topic, partition, and offset?
5. Does a consumer need to read back the record to check the key, payload, headers, or serializer?
6. Did the consumer subscribe to the topic before sending and use a dedicated group ID for the test?
7. Is the test timeout appropriate for the send timeout and broker startup time?
8. If requirements involve replication, ACLs, or TLS, does the test run on a cluster reflecting those configurations?

A reliable producer test does more than confirm that code called send(). It waits for the asynchronous result, checks the acknowledgement according to the acks configuration, and verifies the metadata returned by the broker. When the application contract also covers record contents, read the record back with a test consumer to verify the actual key and payload. This verification approach helps catch serializer bugs, broker configuration issues, and send-path failures before they surface in business processing flows.
