# Managing Sessions When Multiple Threads Send or Receive Concurrently

In JMS, a `Session` is the working context for creating messages, sending messages, receiving messages, and managing transactions. One `Connection` can create multiple `Session` instances, but a `Session` is defined as a single-threaded context: operations on the same `Session` must not be performed concurrently from multiple threads. A `Session` also serializes invocations of any `MessageListener` attached to it.

This is critical when an application needs to increase throughput using multiple threads. Do not create a single `Session` and share it across all producers or consumers running in parallel. Give each concurrent processing thread its own `Session` and JMS resources, or delegate `Session` management to Spring's JMS listener container and `JmsTemplate`.

This lesson focuses on the `Session` lifecycle, concurrent sending and receiving, transaction and acknowledgement management, message ordering, concurrency configuration in Spring, and common pitfalls when sharing a `Session`.

## 1. Connection, Session, Producer, and Consumer

A JMS application typically has the following components:

- **ConnectionFactory:** creates connections to the JMS provider, such as ActiveMQ Artemis, IBM MQ, or another JMS broker.
- **Connection:** physical or logical connection to the provider. One `Connection` can create multiple `Session` instances.
- **Session:** single-threaded context used to create messages, producers, and consumers, and manage acknowledgement or transactions.
- **MessageProducer:** sends messages to a destination such as a `Queue` or `Topic`.
- **MessageConsumer:** receives messages from a destination via `receive` or a `MessageListener`.
- **Destination:** the send/receive target, usually a `Queue` or `Topic`.

Typical relationship:

~~~mermaid
flowchart TD
    F["ConnectionFactory"] --> C["Connection"]
    C --> S1["Session 1"]
    C --> S2["Session 2"]
    C --> S3["Session 3"]
    S1 --> P1["Producer / Consumer"]
    S2 --> P2["Producer / Consumer"]
    S3 --> P3["Producer / Consumer"]
~~~

A `Connection` can serve multiple `Session` instances. Each `Session` manages its own producers, consumers, and transaction state. Multiple `Session` instances on the same `Connection` allow an application to run multiple independent send/receive threads without opening a physical `Connection` for every message.

Do not confuse `Connection` with `Session`. That a provider allows multiple `Session` instances on one `Connection` does not mean one `Session` can be used concurrently by multiple threads.

## 2. Why Must a Session Not Be Shared Concurrently?

JMS specifies `Session` as a single-threaded context for sending and receiving messages. A `Session` manages ordered state such as:

- `MessageProducer` and `MessageConsumer` created from the `Session`.
- Transaction state of the `Session` if using a transacted session.
- Acknowledgement of messages received in the `Session`.
- Serialized dispatching of `MessageListener` callbacks on that `Session`.

If two threads use the same `Session` at the same time, operations can interleave and cause unintended behavior. For instance, one thread commits a transaction while another thread is sending a message; one thread closes a consumer while another is calling `receive`; or two threads use the same producer and session state in an order the application does not expect.

Follow these principles:

1. Never use one `Session` concurrently from multiple threads.
2. Never share a `Session`'s `MessageProducer` or `MessageConsumer` across threads as if they were thread-safe.
3. Use multiple `Session` instances to achieve parallel processing streams.
4. Close producers, consumers, and `Session` instances according to the application or container lifecycle.
5. If pooling/caching is needed, use mechanisms supported by the JMS provider or Spring instead of holding a global `Session` yourself.

A `Session` can be used sequentially in ways permitted by the API/provider, but the safest and most controllable design binds a `Session` to one processing thread or one consumer worker at a time.

## 3. The One-Session-Per-Worker Model

Suppose an application has three workers sending messages in parallel. It can use one shared `Connection` and three separate `Session` instances:

~~~java
Connection connection = connectionFactory.createConnection();

Session session1 =
        connection.createSession(false, Session.AUTO_ACKNOWLEDGE);
Session session2 =
        connection.createSession(false, Session.AUTO_ACKNOWLEDGE);
Session session3 =
        connection.createSession(false, Session.AUTO_ACKNOWLEDGE);
~~~

Each worker uses its own `Session`:

~~~text
Worker 1 -> Session 1 -> Producer 1
Worker 2 -> Session 2 -> Producer 2
Worker 3 -> Session 3 -> Producer 3
~~~

When receiving messages asynchronously, each consumer should also have its own `Session`. JMS providers and listener containers usually manage this relationship. One `Session` does not become multiple consumer threads merely because multiple `MessageConsumer` instances can be created from it; listener callbacks on the same `Session` are serialized.

To process multiple messages concurrently, increase the number of consumers/sessions. Balance concurrency against broker capacity, database, downstream services, and the provider's connection/session limits.

## 4. Concurrent Sending: Using JmsTemplate or Separate Sessions

### 4.1. Sharing JmsTemplate across threads

In Spring applications, `JmsTemplate` is designed to be reused after configuration. Multiple threads can invoke `send`/`convertAndSend` methods on the same `JmsTemplate`. The template acquires or participates in an appropriate `Session` via the `ConnectionFactory` and active transaction mechanism; it manages resource usage within the scope of the call.

Example:

~~~java
@Service
public class OrderPublisher {

    private final JmsTemplate jmsTemplate;

    public OrderPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    public void publish(OrderCreated event) {
        jmsTemplate.convertAndSend("orders.queue", event);
    }
}
~~~

The publisher service can be a singleton and called by multiple threads. What to avoid is creating a `Session` in a field of the service and reusing it in every call. `JmsTemplate` manages `Session` through Spring JMS's mechanisms; there is no need to hold a `Session` in a singleton.

Configure the template and `ConnectionFactory` before the application starts handling traffic. Do not mutate shared configuration while threads are sending messages.

### 4.2. When using the JMS API directly

If not using `JmsTemplate`, each worker should obtain its own `Session` from the `Connection`. Illustrative example:

~~~java
Session session = connection.createSession(
        false,
        Session.AUTO_ACKNOWLEDGE
);

MessageProducer producer = session.createProducer(queue);

try {
    TextMessage message = session.createTextMessage("Order ORD-42");
    producer.send(message);
}
finally {
    producer.close();
    session.close();
}
~~~

The snippet requires the corresponding imports and JMS resources. In a real application, creating/closing `Connection` and `Session` should reside in an appropriate lifecycle manager, pool, or container; avoid opening a new physical `Connection` per message without reason.

If a worker sends many messages, it can keep its `Session` and producer for the lifetime of the worker and close them when the worker stops. Never share them concurrently with another worker.

### 4.3. CachingConnectionFactory

Spring JMS provides `CachingConnectionFactory` to reuse a `Connection` and cache `Session`, `MessageProducer`, or consumer instances per configuration. When the application closes a `Session` proxy, the resource can be returned to the cache rather than immediately closing the physical `Session`.

Caching reduces resource creation cost, but it does not make `Session` thread-safe. A `Session` currently borrowed by one thread must not be used concurrently by another thread. Once returned to the cache, the `Session` can be reused for another borrow according to the factory's management mechanism.

Configure the session cache size based on actual concurrency. If the number of workers exceeds the cached `Session` count, the factory may need to create more `Session` instances; cache size must not be mistaken for a limit on the number of threads allowed to send.

## 5. Concurrent Receiving with Spring's Listener Container

For asynchronous consumers, let Spring manage `Connection`, `Session`, and `MessageConsumer` through a listener container. One container can create multiple consumers; each consumer has its own `Session` to receive messages and invoke the listener.

Configuration example:

~~~java
@Configuration
@EnableJms
public class JmsConfiguration {

    @Bean
    public DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setConcurrency("3-8");
        factory.setSessionTransacted(true);

        return factory;
    }
}
~~~

Listener:

~~~java
@Component
public class OrderListener {

    @JmsListener(
            destination = "orders.queue",
            concurrency = "3-8"
    )
    public void receive(OrderCreated event) {
        processOrder(event);
    }

    private void processOrder(OrderCreated event) {
        // Business processing.
    }
}
~~~

Depending on the configuration style, concurrency is set on the factory or the annotation. There is no need to set both without reason; the annotation can override the factory's setting for that listener.

With concurrency `3-8`, the container can maintain a minimum of three consumers and scale up to a maximum of eight consumers according to the container's scheduling capability. Each consumer has its own `Session`. Listener invocations can run concurrently across multiple threads.

An important note: the `OrderListener` bean is usually a singleton. The `receive` method can be invoked concurrently on the same instance. Therefore, do not store per-message mutable state in ordinary fields; use local variables, immutable objects, or thread-safe structures if state truly must be shared.

## 6. Session, Transactions, and Acknowledgement

`Session` does not only manage resources; it is also the scope of JMS transactions and acknowledgement. Increasing the number of `Session` instances means the application also increases the number of independent units of work.

### 6.1. Non-transacted Session

Example:

~~~java
Session session = connection.createSession(
        false,
        Session.AUTO_ACKNOWLEDGE
);
~~~

The first argument `false` means the `Session` does not use a JMS transaction. The second argument specifies the acknowledgement mode.

Common modes:

- **AUTO_ACKNOWLEDGE:** the provider automatically acknowledges messages according to this mode's rules. For synchronous `receive`, acknowledgement occurs when `receive` returns successfully; for a listener, after the callback completes normally.
- **CLIENT_ACKNOWLEDGE:** the application calls `acknowledge` on the message. Acknowledgement is `Session`-scoped: acknowledging one message can acknowledge all messages previously consumed by that `Session`.
- **DUPS_OK_ACKNOWLEDGE:** the provider may defer acknowledgement to improve performance; the consumer must tolerate possible duplicate deliveries.
- **SESSION_TRANSACTED:** used only when creating a transacted `Session`; ordinary acknowledgement modes are no longer applied in the same way.

Because `CLIENT_ACKNOWLEDGE` is `Session`-scoped, do not share one `Session` across multiple consumer threads expecting each thread to acknowledge its own messages independently.

### 6.2. Transacted Session

You can create a transacted `Session`:

~~~java
Session session = connection.createSession(
        true,
        Session.SESSION_TRANSACTED
);

MessageProducer producer = session.createProducer(queue);

try {
    producer.send(session.createTextMessage("Order ORD-42"));
    session.commit();
}
catch (JMSException ex) {
    session.rollback();
    throw ex;
}
finally {
    producer.close();
    session.close();
}
~~~

A JMS transaction is bound to a single `Session`. `commit` confirms the send and receive operations belonging to that transaction; `rollback` discards messages sent in the transaction and causes received messages to be redelivered according to provider semantics.

If multiple workers use separate `Session` instances, each worker has its own transaction. Committing `Session 1` does not commit work underway in `Session 2`. This is an important boundary when designing batching or parallel processing.

### 6.3. JMS transactions and database transactions

A JMS transaction does not automatically merge into a single transaction with a database. If a listener updates a database and then acknowledges a message, the process can fail between the two operations and leave divergent state.

You can use JTA/XA when both the database and JMS provider support XA and the system is configured with an appropriate transaction coordinator. This approach carries higher operational and performance overhead.

Another option is the Transactional Outbox: write business data and an outbox record within the same database transaction, then have a relay send the message to the JMS destination. Consumers still need idempotency because the relay or broker can produce duplicate deliveries in certain failure scenarios.

## 7. Ordering with Multiple Sessions and Consumers

One `Session` serializes its listener callbacks, but with multiple `Session`/consumer instances, messages can be processed in parallel. Consequently, the order in which processing starts and completes across the system may differ from send order.

For example, message A is received by consumer 1 before message B on consumer 2, yet consumer 2 finishes faster so B completes before A. If business rules require ordering per order or customer, design the ordering scope explicitly.

Common approaches:

- Use only a single consumer when queue-wide processing order is required and throughput permits.
- Group work by a business key so messages in the same group go through the same consumer if supported by the provider.
- Use a sequence number or version so the consumer detects out-of-order messages.
- Design idempotent handlers capable of handling late-arriving events.
- Avoid increasing concurrency before identifying which ordering guarantees truly must be preserved.

Some JMS providers support message grouping, often via the `JMSXGroupID` property. When using it, read the provider documentation to learn how groups are distributed and how failover behaves. Do not assume all providers implement it the same way.

With multiple producer `Session` instances, ordering across producers also does not automatically form a global order. If ordering per aggregate is required, serialize event emission for that aggregate or use an appropriate partitioning/grouping mechanism.

## 8. Lifecycle Management and Resource Limits

Each `Session` typically creates additional producers/consumers and may allocate broker-side resources. Raising concurrency too high can exhaust connection, session, consumer, or thread limits.

Several principles:

- Reuse `Connection` through an appropriate `ConnectionFactory`, pool, or caching factory.
- Do not create a physical `Connection` per message.
- Close `Session`, producer, and consumer when the worker/container lifecycle ends.
- Do not close a shared `Connection` while other workers are still using it.
- Cap concurrency according to the capacity of the broker, database, and downstream services.
- Monitor active `Session` counts, consumer counts, backlog, processing time, and error rates.
- Use graceful shutdown to stop receiving messages, finish or roll back in-flight work, and then close resources.
- Do not store a `Session` in a static field or singleton service for multiple threads to call concurrently.

`ConnectionFactory` can be a singleton; `JmsTemplate` and listener containers are also commonly managed as shared beans. `Session` has a narrower usage scope and must be managed per thread/consumer or per transaction.

## 9. Common Pitfalls When Multiple Threads Send or Receive Concurrently

### 9.1. Sharing one Session across multiple threads

Symptoms can include provider errors, intermingled transactions, messages processed out of expected application order, or intermittent failures hard to reproduce under load.

Fix: create a dedicated `Session` per concurrent worker/consumer or use `JmsTemplate`/listener containers to manage `Session`.

### 9.2. Mistaking JmsTemplate for a Session

`JmsTemplate` is a high-level convenience abstraction, not a `Session`. A configured template can be shared across threads; never extract a `Session` from a callback and store it in a field for later reuse.

### 9.3. Adding threads without adding Sessions/consumers

One `Session` does not execute multiple listener callbacks in parallel by itself. To increase concurrent receiving capacity, configure the listener container with multiple consumers so the container creates a separate `Session` per consumer.

### 9.4. Sharing MessageProducer or MessageConsumer

Producers/consumers are created from a `Session` and depend on the `Session` lifecycle. Do not share them concurrently across threads. Let each worker use the resources of its own `Session`.

### 9.5. Treating CLIENT_ACKNOWLEDGE as per-thread acknowledgement

Acknowledgement is `Session`-scoped, not an independent acknowledgement per thread sharing a `Session`. Using a dedicated `Session` per consumer makes acknowledgement scope clear and controllable.

### 9.6. Concurrency altering processing order

Multiple consumers can complete messages in different orders. If business logic requires ordering, choose an appropriate concurrency level and grouping/sequencing strategy.

### 9.7. Session or consumer closed while still in use

Closing shared resources can fail in-flight operations. Containers should manage lifecycles; with direct JMS API usage, the worker owning a resource is responsible for closing it after stopping work.

### 9.8. Retries causing duplicate side effects

A message can be redelivered after a rollback, disconnect, or acknowledgement failure. Use a message ID or business key to make handlers idempotent; never rely on an assumption that a message is processed strictly once.

## 10. Java 17 Example: Each Worker Uses Its Own Session

The following example uses plain JDK classes to simulate the principle of a separate `Session` per concurrent task. `DemoSession` is an illustrative class defined by the program itself, not `javax.jms.Session` or `jakarta.jms.Session`.

Create file **JmsSessionConcurrencyDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class JmsSessionConcurrencyDemo {

    record OrderMessage(String id, String payload) {}

    record DemoSession(String sessionId) {
        String send(OrderMessage message) {
            return sessionId + " sent " + message.id();
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService workers = Executors.newFixedThreadPool(3);

        try {
            List<Callable<String>> tasks = new ArrayList<>();

            for (int i = 1; i <= 3; i++) {
                int workerNumber = i;

                tasks.add(() -> {
                    DemoSession session =
                            new DemoSession("session-" + workerNumber);

                    OrderMessage message = new OrderMessage(
                            "msg-" + workerNumber,
                            "OrderCreated"
                    );

                    return session.send(message);
                });
            }

            List<Future<String>> results = workers.invokeAll(tasks);

            // invokeAll preserves Future order matching the input task order.
            for (Future<String> result : results) {
                System.out.println(result.get());
            }
        }
        finally {
            workers.shutdown();
        }
    }
}
~~~

Compile and run with Java 17 or later:

~~~bash
javac JmsSessionConcurrencyDemo.java
java JmsSessionConcurrencyDemo
~~~

Output:

~~~text
session-1 sent msg-1
session-2 sent msg-2
session-3 sent msg-3
~~~

The example creates a `DemoSession` inside each task. The three tasks can execute concurrently without sharing the same `Session` object. This is strictly an ownership illustration; it does not connect to a JMS broker and does not test the semantics of a JMS provider.

## 11. How to Test Concurrency and Transactions

In real deployments, test against the JMS provider the application uses:

- **Session isolation:** verify each consumer/worker has its own `Session` and no `Session` is called concurrently.
- **Concurrent sending:** send from multiple workers and verify message count, payload, and message IDs are accurate.
- **Concurrent receiving:** increase concurrency and verify messages are distributed and processed appropriately under the configuration's delivery guarantees.
- **Transaction rollback:** make a handler throw an exception inside a transacted `Session`, and verify rollback and redelivery per provider behavior.
- **Acknowledgement:** test `AUTO_ACKNOWLEDGE`, `CLIENT_ACKNOWLEDGE`, or transacted mode according to `Session` scope.
- **Ordering:** send a sequence of numbered messages and observe receive/completion order as consumer count increases.
- **Shutdown:** stop the container while processing is underway to verify resources are closed and uncommitted messages are recovered as configured.
- **Load test:** raise concurrency incrementally, monitoring `Session` count, threads, consumers, throughput, latency, and backlog.

Do not merely check that the program throws no exceptions. Verify zero message loss, no duplicate side effects, proper transaction rollbacks, and resource limits kept within operational bounds.

## 12. Concurrency Selection Checklist

Before increasing thread count, answer:

1. Does each worker have its own `Session`?
2. Are producers using `JmsTemplate` or lifecycle-managed resources properly?
3. Are consumers created by the listener container with appropriate concurrency?
4. Is the listener bean safe when multiple invocations run concurrently?
5. Are transactions and acknowledgement clearly scoped per `Session`?
6. Does ordering need to be preserved queue-wide, per destination, or by business key?
7. Do the broker and downstream services have enough capacity for the planned consumer count?
8. Have retries, redelivery, and idempotency been designed?

A JMS `Session` is the unit managing send/receive state, acknowledgement, and transactions. When multiple threads operate concurrently, use multiple independent `Session` instances or let Spring manage `Session` via `JmsTemplate` and listener containers. Increasing concurrency by scaling consumers/sessions enables controlled parallel processing; sharing a single `Session` concurrently only introduces race conditions, entangled transactions, and hard-to-diagnose failures.