# DefaultMessageListenerContainer and the Message Receive Loop

In Spring JMS, **DefaultMessageListenerContainer (DMLC)** is the container that manages receiving messages from a Queue or Topic and invoking the listener on its own worker threads. Its defining characteristic is that it uses the JMS API in a polling fashion: each worker repeatedly calls **MessageConsumer.receive()**, waits for a message to arrive, and then hands the message to the listener for processing.

DMLC manages the Connection, Session, MessageConsumer, threads, transactions, acknowledgement, cache, and the ability to recover when the broker temporarily loses its connection. As a result, the application does not have to write the receive loop itself, create a consumer for each worker itself, or handle the entire resource lifecycle itself.

## 1. Where does DMLC fit in Spring JMS?

Spring JMS provides abstractions for the application to work with a JMS provider:

- **ConnectionFactory:** creates a Connection to the broker or JMS provider.
- **Connection:** represents the connection to the provider.
- **Session:** a single-threaded context for creating messages, producers, and consumers, and for managing transactions/acknowledgement.
- **MessageConsumer:** receives messages from a Queue or Topic.
- **MessageListener:** the callback that processes one message.
- **MessageListenerContainer:** manages the listener and the resources needed to receive messages.

DMLC belongs to the package **org.springframework.jms.listener** and extends **AbstractPollingMessageListenerContainer**. The container uses ordinary JMS client calls, specifically a loop of **receive()** calls on the MessageConsumer. This approach does not require the JMS provider to supply a ServerSessionPool.

DMLC suits both standalone JMS environments and Jakarta EE environments. It supports concurrency, Spring-managed transactions, and automatic recovery when the broker is temporarily unavailable, and it also allows start, stop, and changing some configuration at runtime.

### 1.1. How does DMLC differ from SimpleMessageListenerContainer?

Spring has two common JMS containers:

| Criterion | DefaultMessageListenerContainer | SimpleMessageListenerContainer |
|---|---|---|
| Receiving method | Polling with a MessageConsumer.receive() loop | Registers a MessageListener directly with the JMS provider |
| Execution thread | Invoker tasks managed by the Spring TaskExecutor | The provider coordinates callbacks according to the JMS mechanism |
| Concurrency | Can increase/decrease dynamically according to configuration | Mainly creates a fixed number of consumers at startup |
| Transaction | Supports local JMS transactions and an external transaction manager | A more limited scope of transaction support |
| Broker recovery | Has automatic recovery and retries setting up the consumer | A simpler recovery mechanism |
| Use case | Most applications that need tunability and recovery | Simple flows, a fixed number of consumers, and a suitable provider |

DMLC is usually the default choice when you need control over concurrency, transactions, or recoverability. SimpleMessageListenerContainer can still be suitable when the requirements are very simple and you want to rely more on provider-managed callbacks.

## 2. How does the receive loop work?

When the container starts, DMLC creates the initial number of consumers according to the configuration. Each consumer has one JMS Session and one corresponding MessageConsumer. The container creates invoker tasks and hands the tasks to the Spring TaskExecutor.

Each invoker performs this cycle:

1. Obtain or set up the Connection, Session, and MessageConsumer according to the cache level.
2. Call MessageConsumer.receive() with the configured receive timeout.
3. If a message is received, pass the message to the listener.
4. Perform commit, rollback, or acknowledgement according to the transaction/acknowledgement mode.
5. Continue the loop to receive the next message.
6. If no message is received within the timeout, mark that receive attempt as idle and apply the consumer coordination policy.
7. When the container stops or a resource hits an error, close or re-establish the resources according to the lifecycle.

~~~mermaid
flowchart TD
    A["Container start"] --> B["Create consumer invoker"]
    B --> C["Obtain Connection / Session / Consumer"]
    C --> D["MessageConsumer.receive(timeout)"]
    D --> E{"Received message?"}
    E -->|Yes| F["Invoke MessageListener"]
    F --> G["Commit / acknowledge or rollback"]
    G --> D
    E -->|No, timeout| H["Mark receive as idle"]
    H --> I{"Scale or reschedule?"}
    I -->|Continue| D
    I -->|Release surplus worker| J["Close worker resources"]
    J --> K["Wait for new scheduling"]
    C -. "Connection failure" .-> R["Recovery / reconnect"]
    R --> C
~~~

The receive loop belongs to the container. The listener only processes the message that is passed to it; it does not need to call receive() itself or create its own while loop to poll the destination.

### 2.1. The role of the receive timeout

DMLC uses the receive timeout to limit how long one receive() call waits for a message. With the commonly used default configuration, the timeout is about 1,000 ms. You can change it with:

~~~java
container.setReceiveTimeout(1_000);
~~~

The value is in milliseconds. When the time runs out without a message, receive() returns null; the invoker then has a chance to evaluate the idle state and adjust its scheduling.

The receive timeout is not the maximum time the listener may take to process a message. If the listener takes 20 seconds to process, the receive timeout does not interrupt the listener after 1 second. This timeout controls the time spent waiting to receive a message.

A timeout that is too long can make detecting the idle state and releasing surplus consumers slow. A timeout that is too short can make the loop check more often and increase the number of receives that return null. Choose according to the workload, response requirements, and scaling policy.

## 3. Each invoker manages its own JMS resources

A JMS Session is a single-threaded context. DMLC organizes the consumer workers so that each processing thread has a corresponding Session and MessageConsumer according to the cache policy.

Example when there are three consumers:

~~~text
Invoker 1 -> Session 1 -> Consumer 1 -> Listener
Invoker 2 -> Session 2 -> Consumer 2 -> Listener
Invoker 3 -> Session 3 -> Consumer 3 -> Listener
~~~

Each invoker can receive and process messages independently. DMLC manages creating, caching, closing, and re-establishing resources when needed. Do not take the container's Session and store it in a singleton field to share with other threads.

A listener bean is usually a singleton. When the container has multiple consumers, the listener method can be invoked concurrently on the same instance. Therefore:

- Use local variables to hold the data of each processing run.
- Use immutable objects for shared data.
- If you need shared state, choose a thread-safe structure and define atomicity clearly.
- Do not store the Message, Session, or transaction state of one processing run in a field and use it in another invocation.

## 4. Basic DMLC configuration

DMLC can be declared directly as a Spring bean. The following example illustrates a Queue listener with two initial consumers and the ability to grow to at most eight consumers:

~~~java
@Configuration
public class JmsListenerConfiguration {

    @Bean
    public DefaultMessageListenerContainer orderListenerContainer(
            ConnectionFactory connectionFactory,
            MessageListener orderMessageListener) {

        DefaultMessageListenerContainer container =
                new DefaultMessageListenerContainer();

        container.setConnectionFactory(connectionFactory);
        container.setDestinationName("orders.queue");
        container.setMessageListener(orderMessageListener);

        container.setConcurrentConsumers(2);
        container.setMaxConcurrentConsumers(8);

        container.setReceiveTimeout(1_000);
        container.setSessionTransacted(true);
        container.setRecoveryInterval(5_000);

        return container;
    }
}
~~~

The MessageListener bean can be implemented separately:

~~~java
@Component
public class OrderMessageListener implements MessageListener {

    private final OrderService orderService;

    public OrderMessageListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @Override
    public void onMessage(Message message) {
        orderService.process(message);
    }
}
~~~

The example uses the JMS types of the corresponding Spring version. Spring Framework 6 and later uses the Jakarta Messaging API with the package jakarta.jms; older Spring applications may use javax.jms. The package needs to be consistent with the Spring version and the JMS provider.

Some important configuration:

- **setConnectionFactory:** supplies the ConnectionFactory configured by the provider.
- **setDestinationName:** sets the name of the Queue or Topic; destination resolution is based on the DestinationResolver.
- **setMessageListener:** registers the listener that receives messages.
- **setConcurrentConsumers:** the base number of consumers maintained.
- **setMaxConcurrentConsumers:** the upper bound when the container needs to scale up.
- **setReceiveTimeout:** the maximum wait time for a single receive.
- **setSessionTransacted:** enables a local JMS transaction for the Session.
- **setRecoveryInterval:** the pause between recovery attempts under a fixed configuration.

When you need to use an external transaction manager, you can configure the transactionManager property instead of relying only on a local transacted Session. How to configure it depends on the transaction manager and the JMS provider.

## 5. Concurrency and dynamic scaling

DMLC has two main properties to control the number of consumers:

- **concurrentConsumers:** the base number of consumers. The default value is 1.
- **maxConcurrentConsumers:** the maximum number of consumers. The default value is 1.

If maxConcurrentConsumers is greater than concurrentConsumers, DMLC can create additional invokers when it notices the message load increasing. When the load decreases, surplus consumers can be scaled back down to the base level.

Example:

~~~java
container.setConcurrentConsumers(2);
container.setMaxConcurrentConsumers(8);
~~~

The container always maintains the base consumer level according to the configuration and can grow to eight consumers when the coordination conditions allow. Scaling is based on message-receiving activity and the idle state, not an instantaneous autoscaler based on CPU.

### 5.1. Properties related to scaling

DMLC has several advanced properties:

| Property | Role |
|---|---|
| idleConsumerLimit | The limit on the number of idle consumers the container accepts when deciding to create additional invokers |
| idleTaskExecutionLimit | The number of times a task is marked idle before a surplus task is stopped |
| idleReceivesPerTaskLimit | The number of consecutive receives that return null to mark a task as idle |
| maxMessagesPerTask | The maximum number of receive attempts within one task before the task is rescheduled |
| taskExecutor | The executor that runs the listener invokers |

These properties help balance the ability to scale up against the cost of creating threads and JMS resources. If scaling up/down happens too often, you can adjust the idle limits or the receive timeout so that surplus consumers are kept longer. If you need to release resources quickly when the queue is empty, you can lower the idle thresholds appropriately.

### 5.2. TaskExecutor and the thread lifecycle

If you do not configure a dedicated executor, DMLC uses a SimpleAsyncTaskExecutor to create the threads for the invokers. These threads usually live for a long time because each invoker loops on receive continuously.

An ordinary thread pool does not necessarily bring a benefit if each task occupies a thread for almost the entire lifetime of the container. A dedicated executor is useful when you need to integrate with Jakarta EE's thread management mechanism or an execution environment with its own policy.

With Spring Framework 6.2 and Java 21 or later, DMLC also supports a virtual threads option for the default executor through setVirtualThreads(true). This option only applies when the container uses the default executor; if you pass in a dedicated executor, the application must configure virtual threads on that executor.

## 6. Queue and Topic have different concurrency behavior

With a Queue, multiple consumers usually compete to receive messages. A message is delivered to one consumer at a time according to queue semantics. Increasing the number of consumers can increase throughput if the listener and the downstream systems can handle parallel processing.

However, when multiple consumers are active together, the order in which processing completes can differ from the order in which messages were sent or received. For example, consumer 1 receives message A before consumer 2 receives B, but B is processed faster and completes before A.

With a Topic, each independent subscription usually receives a copy of the published message. If you increase the number of consumers in the usual way on the same Topic, multiple consumers may receive the same publication, leading to repeated processing. Only increase concurrency for a Topic when the provider and the shared subscription configuration or an equivalent mechanism support the desired semantics correctly.

If the business requires ordering:

- Keep one consumer for the destination when you need simple processing order and throughput allows.
- Group messages by a business key if the provider supports message grouping.
- Use a sequence number or version to detect events that arrive late or out of order.
- Design the handler to be idempotent and able to handle duplicates.
- Test the receive order and completion order on the actual provider.

## 7. Transactions and acknowledgement in the receive loop

DMLC does not only receive messages but also coordinates when to commit or acknowledge after the listener has processed.

### 7.1. Default AUTO_ACKNOWLEDGE

With AUTO_ACKNOWLEDGE, DMLC performs the acknowledgement before invoking the listener, according to the container's semantics. If the listener throws an exception, the message has already been acknowledged and is not redelivered just because of that exception.

This means a listener can fail after the broker/provider has already considered the message acknowledged. If the application needs redelivery when processing fails, do not rely on the default AUTO_ACKNOWLEDGE.

### 7.2. Local transacted Session

You can enable a local JMS transaction:

~~~java
container.setSessionTransacted(true);
~~~

In that case, receiving the message and processing the listener fall within the Session's transaction. If the listener completes normally, the container commits the transaction. If the listener throws an exception, the container rolls back according to the transaction policy and the provider can redeliver the message.

The specific redelivery behavior depends on the JMS provider, the delivery count, the redelivery delay, and the dead-letter policy. If a message always causes an error, it can be redelivered many times; you need to limit retries and configure an appropriate poison-message/DLQ policy.

### 7.3. External transaction manager

DMLC can participate in an external transaction through the transactionManager property, typically a JtaTransactionManager in a Jakarta EE environment with a ConnectionFactory that supports XA/JTA.

When using an external transaction manager, DMLC by default does not cache resources at the Connection/Session/Consumer level, to ensure that fresh resources are obtained within the transaction scope as required by some application servers. You can adjust cacheLevel if the provider/server allows it and it has been tested.

Do not assume that a local JMS transaction and a database transaction are automatically a single atomic transaction. If you need to commit the database and JMS together, you need to configure an appropriate XA/JTA or use a Transactional Outbox according to the application architecture.

## 8. DMLC cache levels

DMLC has its own resource caching mechanism. The main cache levels:

| Cache level | Resources held |
|---|---|
| CACHE_NONE | No JMS resources are cached |
| CACHE_CONNECTION | Cache Connection |
| CACHE_SESSION | Caches the Connection and Session |
| CACHE_CONSUMER | Caches the Connection, Session, and MessageConsumer |
| CACHE_AUTO | Lets the container choose according to the transaction strategy |

With local JMS resources, the default is usually CACHE_CONSUMER. When there is an external transaction manager, the default is CACHE_NONE so that fresh resources are obtained within the transaction scope.

Example of setting the cache level explicitly:

~~~java
container.setCacheLevel(
        DefaultMessageListenerContainer.CACHE_CONSUMER
);
~~~

Only choose a cache level after understanding the transaction manager and the provider's rules. Some Jakarta EE servers require a new Connection and Session to register resources into an XA transaction. Forcing caching in that case can cause the transaction not to be enlisted correctly.

### 8.1. Combining with CachingConnectionFactory

DMLC already manages caching according to the listener worker's lifecycle. Spring recommends letting the listener container manage the appropriate cache level itself in many cases.

If you also use CachingConnectionFactory, pay attention to:

- There may be two cache layers holding the Connection, Session, or Consumer at the same time.
- Stopping and then restarting the container requires the Connection to be cached independently at the container scope; an externally cached Connection can make the lifecycle restart not work as expected.
- Dynamic scaling with provider-specific hints and a cached consumer can cause messages to be delivered to a consumer that is no longer attached to the listener container.
- You need to test reconnect, shutdown, durable subscription, and redelivery with the exact JMS provider.

Do not enable caching at every layer just because you want to improve performance. Measure the cost of creating resources and choose one cache strategy that is easy to manage.

## 9. Recovery when the broker is temporarily down

DMLC can recover on its own when the broker is temporarily down. When setting up the Connection or Consumer fails, the container schedules another recovery attempt instead of stopping permanently.

The default recovery interval is 5 seconds. You can configure:

~~~java
container.setRecoveryInterval(5_000);
~~~

Or supply a BackOff to adjust the wait time between attempts:

~~~java
container.setBackOff(new ExponentialBackOff(1_000, 2.0));
~~~

The BackOff example shown needs the imports and a configuration limit that suits the Spring version in use. If the BackOff ends with a STOP state, the container stops further attempts according to the BackOff's contract.

The container's recovery helps re-establish the connection and consumers. It does not replace retry for business errors inside the listener. You need to distinguish:

- **Connection/setup failure:** the broker is unavailable, an authentication error occurs, or the consumer cannot be created. DMLC performs recovery.
- **Listener processing failure:** the listener throws an exception while processing a message. The transaction, error handler, redelivery, and DLQ decide how it is handled.
- **Application shutdown:** the container is stopped/destroyed and closes resources according to the lifecycle; this is not a broker error that needs recovery.

## 10. Lifecycle: start, stop, and shutdown

DMLC implements Spring's lifecycle interfaces, including SmartLifecycle. In an ApplicationContext, the container can start automatically according to the autoStartup configuration and stop when the context closes.

Some common operations:

~~~java
container.start();
container.stop();
container.destroy();
~~~

In a Spring application, it is usually better to let the ApplicationContext manage the lifecycle rather than calling it manually in a business service.

When stopping, the container stops the listener invokers and closes the managed Sessions/Consumers. With a stop callback, the application can know when listener processing has actually stopped. You need to design a graceful shutdown so that in-flight transactions have a chance to complete or roll back properly before the application terminates.

Do not close the shared ConnectionFactory from within a listener worker. Resources owned by the container or the factory need to be closed according to the corresponding lifecycle.

## 11. Error handling and monitoring

A listener can throw an exception due to bad data, a business error, a temporarily unreachable database, or a programming error. DMLC can be configured with an ErrorHandler to handle listener errors according to the application's policy.

Example:

~~~java
container.setErrorHandler(error ->
        logger.error("JMS listener failed", error)
);
~~~

The ErrorHandler helps write logs or raise alerts, but does not decide on its own whether the message is redelivered. Redelivery depends on the transaction/acknowledgement and the provider. Do not swallow the exception in the listener if you need to roll back a transacted Session.

Metrics worth monitoring:

- The number of active consumers and the number of consumers that have been scheduled.
- The number of messages waiting in the queue or the subscription backlog.
- The message receive and processing rate.
- The average processing time and high percentiles.
- The number of listener errors, rollbacks, and redeliveries.
- The number of recoveries/reconnects.
- The number of messages moved to the DLQ.
- The running threads and the time the listener is blocked.

DMLC provides information such as activeConsumerCount and scheduledConsumerCount to observe the concurrency state. Combined with the broker's metrics, this helps distinguish a queue backlog caused by too few consumers from slow listener processing or a congested downstream service.

## 12. Common mistakes

### 12.1. Writing your own while loop and receive in parallel with DMLC

DMLC already manages the receive loop. Creating an additional receive loop on the same Session/Consumer can cause contention and break the lifecycle.

How to handle it: hand message receiving over to the container; the listener only processes the message passed in.

### 12.2. Thinking a listener exception always causes the message to be resent

With DMLC's default AUTO_ACKNOWLEDGE, acknowledgement happens before listener execution, so an exception does not by itself create redelivery.

How to handle it: use sessionTransacted or an external transaction manager when you need rollback/redelivery; check the broker's policy.

### 12.3. Increasing concurrency but ignoring ordering

Multiple consumers processing in parallel can complete messages in different orders.

How to handle it: determine which ordering must be preserved, and consider a single consumer or business-level grouping/sequencing.

### 12.4. Increasing consumers on a Topic as on a Queue

Multiple independent subscription consumers can receive the same publication.

How to handle it: check shared subscription and the provider's semantics; do not increase concurrency if the topic configuration does not support that model.

### 12.5. Using an external transaction manager but forcing an unsuitable cache

Some application servers need fresh resources in the transaction to enlist XA.

How to handle it: understand the default CACHE_NONE, check the provider's rules, and only change cacheLevel after testing XA in practice.

### 12.6. Scaling up/down too often

The receive timeout and idle limits can cause surplus consumers to be created and then stopped continuously when load fluctuates.

How to handle it: adjust idleTaskExecutionLimit, idleReceivesPerTaskLimit, maxMessagesPerTask, and receiveTimeout according to the workload.

### 12.7. A singleton listener holding unsafe mutable state

Multiple consumers can call the listener on the same bean instance.

How to handle it: use local variables, immutable objects, or thread-safe structures; avoid keeping an invocation's Session/Message in a field.

### 12.8. Confusing recovery with business retry

DMLC recovery restores the Connection/Consumer when the broker has a problem. It does not replace a retry policy for payload processing errors.

How to handle it: configure recovery for the infrastructure and transaction/retry/DLQ for message processing separately.

## 13. Java 17 example: simulating the polling loop with two consumers

The following example uses the JDK's BlockingQueue and ExecutorService to simulate the core idea of DMLC: multiple workers run a poll loop, each worker has its own Session and processes the messages it receives. This is an illustrative program using pure JDK, not a Spring JMS implementation, and it does not connect to a broker.

Create the file **PollingListenerLoopDemo.java**:

~~~java
import java.util.Set;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class PollingListenerLoopDemo {

    record DemoMessage(String id) {}

    record ProcessedMessage(String messageId, String sessionId) {}

    record DemoSession(String id) {}

    public static void main(String[] args) throws Exception {
        BlockingQueue<DemoMessage> queue =
                new ArrayBlockingQueue<>(10);

        queue.add(new DemoMessage("M-1"));
        queue.add(new DemoMessage("M-2"));

        Set<String> sessionIds = ConcurrentHashMap.newKeySet();
        ConcurrentLinkedQueue<ProcessedMessage> processed =
                new ConcurrentLinkedQueue<>();

        CountDownLatch workersStarted = new CountDownLatch(2);
        CountDownLatch firstMessagesReceived = new CountDownLatch(2);
        CountDownLatch continuePolling = new CountDownLatch(1);

        ExecutorService executor = Executors.newFixedThreadPool(2);

        try {
            Future<?> first = executor.submit(() ->
                    runConsumer(
                            "consumer-1",
                            queue,
                            sessionIds,
                            processed,
                            workersStarted,
                            firstMessagesReceived,
                            continuePolling
                    )
            );

            Future<?> second = executor.submit(() ->
                    runConsumer(
                            "consumer-2",
                            queue,
                            sessionIds,
                            processed,
                            workersStarted,
                            firstMessagesReceived,
                            continuePolling
                    )
            );

            if (!workersStarted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Consumers did not start");
            }

            if (!firstMessagesReceived.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Both consumers did not receive a first message");
            }

            queue.add(new DemoMessage("M-3"));
            queue.add(new DemoMessage("M-4"));
            continuePolling.countDown();

            first.get();
            second.get();

            System.out.println("Consumers started: " + sessionIds.size());
            System.out.println("Messages processed: " + processed.size());
            System.out.println(
                    "Distinct worker sessions: " + sessionIds.size());
        }
        finally {
            continuePolling.countDown();
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }

    private static void runConsumer(
            String consumerId,
            BlockingQueue<DemoMessage> queue,
            Set<String> sessionIds,
            ConcurrentLinkedQueue<ProcessedMessage> processed,
            CountDownLatch workersStarted,
            CountDownLatch firstMessagesReceived,
            CountDownLatch continuePolling) {

        DemoSession session = new DemoSession("session-" + consumerId);
        sessionIds.add(session.id());
        workersStarted.countDown();

        try {
            DemoMessage first = queue.poll(5, TimeUnit.SECONDS);

            if (first != null) {
                processed.add(new ProcessedMessage(first.id(), session.id()));
                firstMessagesReceived.countDown();
                continuePolling.await();
            }

            DemoMessage next;
            while ((next = queue.poll(200, TimeUnit.MILLISECONDS)) != null) {
                processed.add(new ProcessedMessage(next.id(), session.id()));
            }
        }
        catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
        }
    }
}
~~~

Compile and run with Java 17 or later:

~~~bash
javac PollingListenerLoopDemo.java
java PollingListenerLoopDemo
~~~

Result:

~~~text
Consumers started: 2
Messages processed: 4
Distinct worker sessions: 2
~~~

The two consumers receive the first two messages while each worker owns its own Session. After both have received a message, the program adds two more messages and lets the polling loop continue. The result only prints the count to avoid depending on which worker receives M-3 or M-4.

The example illustrates how to organize workers and the polling loop. The real DMLC also manages the Connection, MessageConsumer, transactions, acknowledgement, timeouts, scaling, recovery, and lifecycle.

## 14. Deployment and testing process

When deploying DMLC, you should proceed in this order:

1. Choose Queue or Topic and determine the message-receiving semantics.
2. Configure the ConnectionFactory, destination, and listener.
3. Start with one consumer, then increase concurrency once you have measured throughput and the ordering you need.
4. Configure receiveTimeout to balance polling and detecting the idle state.
5. Choose sessionTransacted or an external transaction manager according to the processing requirements.
6. Choose a cacheLevel compatible with the transaction manager and provider.
7. Configure a recovery interval or BackOff for connection errors.
8. Define an ErrorHandler, retry, redelivery, and DLQ for listener errors.
9. Verify that the listener bean is safe when invoked concurrently.
10. Test start/stop, broker restart, transaction rollback, queue backlog, ordering, and graceful shutdown.

Test scenarios that should be covered:

- Send a message while the container is running and confirm the listener receives the correct payload.
- Increase concurrency to confirm multiple consumers actually process in parallel.
- Make the listener throw an exception in a transacted Session and confirm rollback/redelivery.
- Check AUTO_ACKNOWLEDGE to understand the behavior when the listener fails.
- Stop the broker temporarily and then restart it, and confirm DMLC recovers on its own.
- Create increasing/decreasing load to observe dynamic scaling and idle consumer cleanup.
- Stop the ApplicationContext while a listener is processing to verify that resources and transactions are terminated correctly.
- With a Topic, confirm that subscription and concurrency do not cause unintended multiple processing.

DefaultMessageListenerContainer manages the receive loop, workers, Sessions, Consumers, and transactions so that the application can focus on the listener logic. Understanding how polling, the receive timeout, concurrency, cache level, and acknowledgement work together helps configure things correctly for the Queue/Topic and the JMS provider. When combined with an appropriate transaction, recovery with backoff, backlog monitoring, and a thread-safe listener, DMLC can receive messages stably even when the load changes or the broker is temporarily interrupted.

## References

- [Spring Framework 6.2: DefaultMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html)
- [Spring Framework: JMS integration reference](https://docs.spring.io/spring-framework/reference/integration/jms.html)