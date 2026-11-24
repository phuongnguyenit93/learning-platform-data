# Per-Thread `ProducerFactory` and `ConsumerFactory`

In Spring Kafka, `ProducerFactory` and `ConsumerFactory` are typically declared as shared beans in the Spring `ApplicationContext`. A factory can be used by multiple services or listeners, but the Kafka client objects created by the factory follow different sharing rules: `KafkaProducer` is thread-safe, whereas `KafkaConsumer` is not thread-safe and must be owned by a single thread.

Therefore, "per-thread factory" should not be understood as creating a new Spring factory for each thread. Distinguish between the factory that manages configuration and client lifecycles versus the actual producer/consumer instances. Spring Kafka provides appropriate mechanisms for both client types, ranging from shared producers to per-thread producers and dedicated consumers for each listener container.

## 1. Factories and Kafka Clients Are Two Different Layers

A factory describes how to create clients: bootstrap servers, serializers/deserializers, security, group ID, client ID, and other Kafka properties. A factory can be a singleton bean, while the number of created clients depends on how the factory and application use it.

| Component | Role | Threading Rule |
|---|---|---|
| `ProducerFactory<K, V>` | Creates and manages producers | Usually shared across threads |
| `KafkaProducer<K, V>` | Sends records to brokers | Thread-safe; multiple threads can call `send()` |
| `ConsumerFactory<K, V>` | Creates consumers | Can be shared to create multiple consumers |
| `KafkaConsumer<K, V>` | Polls and reads records | Not thread-safe; a consumer may only be accessed by its owning thread |
| `KafkaTemplate<K, V>` | Spring Kafka record-sending abstraction | Can be used as a singleton bean from multiple threads |
| Listener container | Manages consumers, polling, acknowledgement, and lifecycle | Each consumer runs on a dedicated thread managed by the container |

The typical pattern is one `ProducerFactory` and one `KafkaTemplate` shared by many services; one `ConsumerFactory` shared by many listener containers; and each child listener container owning its own consumer.

## 2. Default Producer Can Be Shared Across Multiple Threads

Kafka producers are designed to be thread-safe. Multiple threads can call `send()` on the same producer without external locking around each call. The producer internally manages buffers, batching, network I/O, and callbacks.

Spring Kafka's `DefaultKafkaProducerFactory` by default can share a single non-transactional producer among clients using the factory. `KafkaTemplate` obtains the producer from the factory when sending and releases it according to the factory's management mechanism.

Example factory and template configuration:

```java
import java.util.HashMap;
import java.util.Map;

import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.StringSerializer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.kafka.support.serializer.JsonSerializer;

@Configuration
class ProducerConfiguration {

    @Bean
    ProducerFactory<String, OrderEvent> orderProducerFactory() {
        Map<String, Object> properties = new HashMap<>();

        properties.put(
                ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
                "localhost:9092"
        );
        properties.put(
                ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
                StringSerializer.class
        );
        properties.put(
                ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
                JsonSerializer.class
        );
        properties.put(ProducerConfig.ACKS_CONFIG, "all");

        return new DefaultKafkaProducerFactory<>(properties);
    }

    @Bean
    KafkaTemplate<String, OrderEvent> orderKafkaTemplate(
            ProducerFactory<String, OrderEvent> producerFactory) {
        return new KafkaTemplate<>(producerFactory);
    }
}
```

Services can inject the same `KafkaTemplate`:

```java
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
class OrderPublisher {

    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;

    OrderPublisher(KafkaTemplate<String, OrderEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    void publish(OrderEvent event) {
        kafkaTemplate.send("orders", event.orderId(), event);
    }
}
```

There is no need to create a new `KafkaTemplate` or `ProducerFactory` per request or per thread. Sharing the default producer is usually the simplest and most efficient choice because the producer already supports concurrent calls.

## 3. When Is a Dedicated Producer Per Thread Needed?

For non-transactional factories, Spring Kafka provides the `producerPerThread` option on `DefaultKafkaProducerFactory`. When enabled, the factory creates a separate producer for each thread calling the factory for the first time; the producer is stored per thread so subsequent calls on the same thread can reuse it. This option is useful in certain cases where `flush()` on a shared template might cause other threads to wait on the shared producer.

```java
DefaultKafkaProducerFactory<String, OrderEvent> producerFactory =
        new DefaultKafkaProducerFactory<>(properties);

producerFactory.setProducerPerThread(true);
```

This mechanism can be helpful when per-thread producer isolation is needed or when each worker should have its own producer instance. However, a per-thread producer does not by itself increase throughput. The default producer is already thread-safe and capable of asynchronous sending, batching, and background I/O.

Only consider enabling `producerPerThread` when backed by measurement or specific isolation requirements. This option is intended for non-transactional producer usage; when Kafka transactions are needed, use Spring Kafka's transactional producer cache and transaction manager. Each separate producer has its own buffers, connections, metadata cache, and background resources; as thread counts grow, producer counts and resource consumption grow accordingly.

### Cleaning Up Thread-Bound Producers

Producers stored in `ThreadLocal` are not closed automatically simply because a task in a thread pool finishes. When a thread no longer needs its producer, you must call `closeThreadBoundProducer()` on the exact thread that created and used that producer. `reset()` and `destroy()` on the factory do not automatically clean up these thread-bound producers.

Example with a worker that has a clear lifecycle:

```java
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.TimeUnit;

import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.KafkaTemplate;

class OrderPublishingWorker implements Runnable {

    private final BlockingQueue<OrderEvent> queue;
    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;
    private final DefaultKafkaProducerFactory<String, OrderEvent> producerFactory;

    OrderPublishingWorker(
            BlockingQueue<OrderEvent> queue,
            KafkaTemplate<String, OrderEvent> kafkaTemplate,
            DefaultKafkaProducerFactory<String, OrderEvent> producerFactory) {
        this.queue = queue;
        this.kafkaTemplate = kafkaTemplate;
        this.producerFactory = producerFactory;
    }

    @Override
    public void run() {
        try {
            while (!Thread.currentThread().isInterrupted()) {
                OrderEvent event = queue.take();

                kafkaTemplate.send(
                        "orders",
                        event.orderId(),
                        event
                ).get(10, TimeUnit.SECONDS);
            }
        }
        catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
        }
        catch (Exception exception) {
            throw new IllegalStateException("Publishing failed", exception);
        }
        finally {
            producerFactory.closeThreadBoundProducer();
        }
    }
}
```

This snippet illustrates a dedicated worker: it waits for events, waits for send results to finish, and then exits; the `finally` block closes the thread-bound producer. In a production application, decide how to route send failures to a retry or error queue rather than dropping events when a worker stops.

If using a long-lived thread pool, do not call `closeThreadBoundProducer()` after every task if the goal is to reuse the producer across tasks. Call it when the worker thread terminates or when the thread will no longer use the producer. The method must run on the exact thread owning the producer; calling it from a pool-management thread will not close another worker's producer.

## 4. What Is the Cost of Per-Thread Producers?

Each producer is a full Kafka client, not merely a wrapper object. When `producerPerThread` is enabled, the number of producers can approach the number of threads actually using the factory.

| Resource | Impact When Producer Count Grows |
|---|---|
| Network connections | Additional connections to brokers |
| Buffers and batches | Each producer has its own buffer and batch memory |
| Metadata | Each producer manages its own client metadata |
| Background I/O | Each producer has its own network/I/O resources |
| Metrics | Additional client metrics; each thread does not get a distinct `client.id` by default |
| Shutdown | Thread-bound producers must be closed per thread |

For example, if a worker pool has 20 threads and each producer is configured with `buffer.memory` up to 32 MiB, the theoretical total buffer budget can reach roughly 640 MiB if all producers allocate up to the limit. Actual figures depend on allocation and load, but must be accounted for when scaling worker counts.

Do not enable producer-per-thread merely to avoid self-written locking. The Kafka producer is already thread-safe. Measure throughput, latency, buffer availability, request latency, and CPU first to verify whether a real bottleneck exists.

## 5. `ConsumerFactory` Is Shared, but `Consumer` Must Be Dedicated

Unlike producers, Kafka consumers are not thread-safe. A single `KafkaConsumer` must not be used concurrently from multiple threads. Operations like `subscribe()`, `poll()`, `commitSync()`, `pause()`, and `close()` must be invoked on the thread owning the consumer. `wakeup()` is the supported Kafka exception for waking a consumer from another thread.

`DefaultKafkaConsumerFactory` can be a singleton bean. Each call to `createConsumer()` creates a new consumer with the factory's configuration. Thus, multiple workers can share the factory, while each worker must own its own consumer instance.

Example factory configuration:

```java
import java.util.HashMap;
import java.util.Map;

import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.support.serializer.JsonDeserializer;

@Configuration
class ConsumerConfiguration {

    @Bean
    ConsumerFactory<String, OrderEvent> orderConsumerFactory() {
        Map<String, Object> properties = new HashMap<>();

        properties.put(
                ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
                "localhost:9092"
        );
        properties.put(
                ConsumerConfig.GROUP_ID_CONFIG,
                "orders-service"
        );
        properties.put(
                ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG,
                false
        );
        properties.put(
                ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
                StringDeserializer.class
        );
        properties.put(
                ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
                JsonDeserializer.class
        );
        properties.put(
                JsonDeserializer.TRUSTED_PACKAGES,
                "com.example.orders"
        );

        return new DefaultKafkaConsumerFactory<>(properties);
    }
}
```

The factory above can be shared by multiple listener containers. Each container/consumer thread requests a new consumer. Never store a singleton `KafkaConsumer` and inject it into multiple services or workers.

## 6. Creating the Consumer Inside Its Owning Thread

If managing a Kafka consumer manually instead of using `@KafkaListener`, call `consumerFactory.createConsumer()` inside the worker thread. That worker performs subscribing, polling, and closing within the same lifecycle.

```java
import java.time.Duration;
import java.util.List;

import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.springframework.kafka.core.ConsumerFactory;

class OrderConsumerWorker implements Runnable {

    private final ConsumerFactory<String, OrderEvent> consumerFactory;

    OrderConsumerWorker(
            ConsumerFactory<String, OrderEvent> consumerFactory) {
        this.consumerFactory = consumerFactory;
    }

    @Override
    public void run() {
        try (Consumer<String, OrderEvent> consumer =
                     consumerFactory.createConsumer()) {

            consumer.subscribe(List.of("orders"));

            while (!Thread.currentThread().isInterrupted()) {
                ConsumerRecords<String, OrderEvent> records =
                        consumer.poll(Duration.ofSeconds(1));

                records.forEach(record ->
                        process(record.key(), record.value())
                );

                if (!records.isEmpty()) {
                    // Commit only after every record in this poll was processed successfully.
                    consumer.commitSync();
                }
            }
        }
    }
}
```

The example uses try-with-resources to close the consumer when the worker exits. `process()` represents business processing; a production application must define commit strategies, retries, and worker shutdown behavior. Do not call `poll()` or `commitSync()` on this consumer from another thread.

If you need to stop the worker externally, retain a reference to the consumer and call `wakeup()` per the Kafka API to wake the poll loop; then let the consumer's owning thread exit the loop and close it. Do not call `close()` from a control thread in place of a controlled shutdown sequence.

## 7. Listener Container Automatically Creates Consumers by Concurrency

With `@KafkaListener`, you normally do not need to create threads manually or call `ConsumerFactory.createConsumer()`. Spring Kafka listener containers manage consumers and their lifecycles.

When concurrency is set to 3, `ConcurrentMessageListenerContainer` creates three child containers; each child has its own consumer running on its own consumer thread. All three share the same `ConsumerFactory` bean.

```java
import org.springframework.boot.autoconfigure.kafka.ConcurrentKafkaListenerContainerFactoryConfigurer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;

@Configuration
class ListenerContainerConfiguration {

    @Bean("ordersListenerFactory")
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    ordersListenerFactory(
            ConcurrentKafkaListenerContainerFactoryConfigurer configurer,
            ConsumerFactory<String, OrderEvent> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

        configurer.configure(factory, consumerFactory);
        factory.setConcurrency(3);

        return factory;
    }
}
```

Listener selecting the factory:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
class OrderListener {

    @KafkaListener(
            id = "ordersListener",
            topics = "orders",
            groupId = "orders-service",
            containerFactory = "ordersListenerFactory"
    )
    public void onOrder(OrderEvent event) {
        orderService.process(event);
    }
}
```

Spring Kafka manages consumer creation, subscribing, polling, committing, rebalancing, and closing consumers when the container stops. Do not manually close consumers owned by the container and do not share consumer instances across listener threads.

## 8. Concurrency Is Limited by Partitions

Concurrency is the number of consumer threads the container can run for the listener. The number of consumers that actually receive partitions within the same group is limited by the number of assigned partitions.

Example topic with 4 partitions:

| Concurrency | Consumer Count | Consequence |
|---:|---:|---|
| 1 | 1 | One consumer reads all four partitions |
| 2 | 2 | Two consumers split four partitions |
| 4 | 4 | Potentially one partition per consumer |
| 6 | 6 | At least two consumers may not be assigned partitions |

Increasing concurrency does not increase partition count and does not automatically increase throughput if the bottleneck is a database or downstream service. Each consumer also carries its own connection, fetch buffers, and management overhead.

Choose concurrency based on partition count, record processing duration, downstream capacity, and consumer lag. If each partition requires sequential processing, do not offload records to an uncontrolled executor, as side effects could finish out of order.

## 9. Distinguishing `producerPerThread` from Consumer Concurrency

Both concepts involve threads, but they solve different problems:

| Setting/Mechanism | Effect |
|---|---|
| `DefaultKafkaProducerFactory.setProducerPerThread(true)` | Creates and caches a dedicated producer per thread using the factory |
| Default thread-safe producer | Multiple threads share a producer per the factory mechanism |
| `ConcurrentMessageListenerContainer` concurrency | Creates multiple child consumers and listener processing threads |
| `ConsumerFactory.createConsumer()` | Creates a new consumer instance; application must manage the owning thread |
| `@KafkaListener(concurrency = "3")` | Requests the listener container to run up to three consumer threads |

There is no need to enable `producerPerThread` simply because a listener container has concurrency 3. Producers and consumers are independent client pipelines; a listener can publish output using the same thread-safe `KafkaTemplate` while the container manages a separate consumer for each child.

## 10. Threads and Transactions in Spring Kafka

When using Kafka transactions, Spring Kafka binds a transactional producer to the transaction context on the current thread. `KafkaTransactionManager` and `KafkaTemplate` coordinate to obtain a producer participating in the transaction; the producer is committed or aborted according to the transaction lifecycle.

This means transactions are bound to the executing thread. Do not start a transaction on one thread, offload the Kafka send to another thread, and expect the transaction context to follow automatically. Mechanisms like `@Async`, executors, or callbacks running on different threads do not automatically inherit an open transaction.

Example of sending inside a transaction with `KafkaTemplate`:

```java
kafkaTemplate.executeInTransaction(operations -> {
    operations.send("orders", orderId, orderCreated);
    operations.send("order-audit", orderId, auditEvent);
    return true;
});
```

This example requires the producer factory to be configured as transactional, typically with a unique `transactionIdPrefix` per application instance. Sends inside the callback participate in the transaction opened by the template on the current thread. When the callback completes normally, the transaction commits; if an exception occurs, the transaction aborts per the API semantics.

If using `KafkaTransactionManager` with `@Transactional`, configure the transaction manager and producer factory according to your Spring Kafka version's guidance. `producerPerThread` is designed for non-transactional producers; when a factory uses transactions, let the transactional producer cache and transaction manager manage producers. Never call `closeThreadBoundProducer()` while a producer is still in use.

## 11. Lifecycle and Shutdown

Each client type must be closed in its proper owner:

| Object | Who Closes It? | When |
|---|---|---|
| Shared producer managed by `DefaultKafkaProducerFactory` | Factory/Spring lifecycle | When the factory is destroyed or reset |
| Thread-bound producer when `producerPerThread` is enabled | The owning thread itself, via `closeThreadBoundProducer()` | When the thread no longer needs the producer |
| Manually created consumer via `ConsumerFactory` | The worker that created and uses the consumer | When the worker exits |
| Consumer created by a listener container | Spring Kafka container | When the container stops |
| `KafkaTemplate` | Normally no separate close needed | The factory manages the underlying producer |

During application shutdown, stop listener containers before closing resources that listeners depend on. For manually managed workers, signal the worker to stop its poll loop, complete or handle in-flight work, and close consumers/producers on the proper threads.

Do not use `ThreadLocal` to retain clients without a cleanup strategy. Thread pools commonly reuse threads for long periods; failing to release thread-bound producers can keep resources alive longer than expected.

## 12. When Should You Split Factories?

Create separate factories for configuration or cluster boundaries, not simply because there are more threads.

| Requirement | Design Approach |
|---|---|
| Multiple services sending to one cluster with the same serializers | Share `ProducerFactory` and `KafkaTemplate` |
| Need per-thread producer after measuring | Use `producerPerThread` with proper per-thread cleanup |
| Sending to a different cluster | Create a separate `ProducerFactory`, inject with `@Qualifier` |
| Different serializers or security settings | Create a separate factory with matching configuration |
| Multiple listeners on the same cluster | Share `ConsumerFactory`, use appropriate factory/container concurrency |
| Listeners needing different concurrency | Create separate listener container factories or configure concurrency on endpoints |
| Manual consumer for a dedicated task | Share `ConsumerFactory`, create one dedicated consumer inside each worker |

For example, if two producer factories serve two clusters, use explicit bean names and `@Qualifier` where templates are created. Do not rely on bean ordering or `@Primary` to route business traffic when multiple clusters have different meanings.

## 13. Common Pitfalls

| Symptom | Cause | Resolution |
|---|---|---|
| Multiple threads calling a producer raise thread-safety concerns | Confusing producer with consumer | Producers are thread-safe; sharing the default factory/template is usually appropriate |
| Producer remains open after worker finishes | Enabled `producerPerThread` without cleanup | Call `closeThreadBoundProducer()` on the proper thread |
| Cleanup called yet another worker's producer remains | Called `closeThreadBoundProducer()` from a manager thread | Cleanup must run on the thread owning the producer |
| Consumer throws concurrent access errors | Sharing one `KafkaConsumer` across multiple threads | Each thread/container must have its own consumer instance |
| Concurrency increased yet throughput stays flat | Low partition count or downstream already saturated | Inspect assignments, lag, and bottlenecks |
| Creating a factory per request | Confusing factory with client instance | Use stable factory beans and reuse clients via appropriate mechanisms |
| Transactions fail across executors | Transaction context is thread-bound | Execute transactional operations on the same thread or redesign transaction boundaries |
| Resource usage spikes when `producerPerThread` is enabled | Each thread creates extra producers, connections, and buffers | Measure thread count, buffers, and network; enable only with clear benefit |
| Listener consumer closed manually | Interfering with container-managed clients | Let the listener container manage consumer lifecycles |

## 14. Checklist for Designing Per-Thread Factories

1. Use `ProducerFactory` and `ConsumerFactory` as shared beans when client configuration is identical.
2. Prefer the default thread-safe producer; enable `producerPerThread` only with measured reasons or specific isolation needs.
3. When `producerPerThread` is enabled, call `closeThreadBoundProducer()` on the owning thread when it finishes using the producer.
4. Never share one `KafkaConsumer` across multiple threads.
5. With `@KafkaListener`, let the container create and manage dedicated consumers per concurrency setting.
6. Choose concurrency based on partition count and downstream processing capacity.
7. Never create a new factory per request or per task.
8. Split factories when clusters, serializers, security, or producer roles differ.
9. Keep transactions within the same thread; do not assume context propagates across executors.
10. Verify shutdown and cleanup so producers, consumers, or connections do not leak.

`ProducerFactory` and `ConsumerFactory` are typically shared as singleton factory beans. The difference lies in the created clients: producers can be shared because they are thread-safe or isolated per thread when needed; consumers must have a dedicated instance for each owning thread. Following this model lets Spring Kafka leverage concurrency while safely managing client lifecycles and broker resources.
