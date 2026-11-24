# Setting the Number of Concurrent Consumers and Tuning Load

## 1. The problem and the goal

A JMS listener receives messages from a queue or topic and invokes business code to process them. When there is only one consumer, the application processes sequentially at that consumer's capacity. When the volume of incoming messages grows, the backlog can build up and the waiting time increases with it.

The Spring JMS listener container manages receiving messages, creating the Session and MessageConsumer, coordinating threads, handing messages to the listener, handling acknowledgement, transactions, and connection recovery. We can increase the number of consumers to process more messages concurrently, or configure a concurrency range so the container increases automatically when load grows and decreases when load drops.

This lesson focuses on DefaultMessageListenerContainer (DMLC), the container commonly used for Spring JMS applications because it supports dynamic concurrency, transactions, and recoverability. After the lesson, the reader can:

- Distinguish SimpleMessageListenerContainer from DefaultMessageListenerContainer.
- Configure a fixed number of consumers or a minimum/maximum consumer range.
- Understand how DMLC increases and decreases consumers according to message-receiving activity.
- Tune the receive timeout, idle consumers, task executor, and recovery.
- Estimate throughput and identify limits at the broker, CPU, database, or external services.
- Understand the effect of concurrency on message ordering, transactions, and redelivery.
- Monitor the number of running consumers and choose a configuration based on data.
- Write a runnable Java 17 example with Spring JMS and ActiveMQ Classic.

## 2. Concurrent consumers in JMS

A consumer is a MessageConsumer attached to one JMS Session and one Destination. When the Spring listener container creates multiple consumers for the same queue, the broker can deliver different messages to those consumers for parallel processing.

~~~mermaid
flowchart TD
    P[Producer] --> Q[(JMS queue)]
    Q --> C1[Consumer 1]
    Q --> C2[Consumer 2]
    Q --> C3[Consumer 3]
    C1 --> L[Listener method]
    C2 --> L
    C3 --> L
    L --> DB[(Database or service)]
~~~

With a queue, the consumers take work from the same queue. Each message is delivered to one consumer in the group in a single delivery. If consumer 1's listener is processing message A, consumer 2 can process message B.

A JMS Session must not be shared so that multiple threads operate on it concurrently. The listener container creates a separate Session for each consumer/invoker. Therefore, increasing concurrency usually increases the number of Sessions, MessageConsumers, and processing threads.

You need to distinguish concurrency from the number of application instances. If an application runs 3 replicas and each replica is configured with 2 to 6 consumers, the total number of consumers can range from 6 to 18. When calculating resources, use the total across all replicas.

## 3. Choosing a listener container

Spring provides two main JMS containers: SimpleMessageListenerContainer (SMLC) and DefaultMessageListenerContainer (DMLC).

| Characteristic | SimpleMessageListenerContainer | DefaultMessageListenerContainer |
|---|---|---|
| How it receives messages | Registers a MessageListener directly with the JMS provider | Polls with a MessageConsumer.receive() loop |
| Concurrency | A fixed number of consumers | A fixed number of consumers or dynamic increase/decrease |
| External transaction manager | Does not support participating in externally managed transactions the way DMLC does | Can participate through PlatformTransactionManager/JtaTransactionManager |
| Native JMS transaction | Yes | Yes |
| Recovery when the broker temporarily loses its connection | Depends on the provider mechanism and the recovery configuration | Has a recovery mechanism and retries connecting |
| Suitable cases | Simple applications that need a fixed number of consumers and a provider callback | Most Spring JMS applications that need transactions, recovery, or dynamic concurrency |

DMLC is usually the default choice for queue-processing systems. SMLC has less runtime logic, but it does not automatically increase/decrease consumers according to load. With SMLC, use setConcurrentConsumers() to set a fixed number of consumers.

Do not increase concurrency for a topic the way you would for a queue unless you have configured a shared subscription or a provider-specific mechanism. With an ordinary topic subscription, each consumer/subscription may receive a copy of the same publication; multiple consumers can cause an application to process the same event repeatedly.

## 4. Configuring a fixed number of consumers

DMLC has the concurrentConsumers property to determine the minimum number of consumers maintained. The default is 1.

Configuring with Java:

~~~java
DefaultJmsListenerContainerFactory factory =
    new DefaultJmsListenerContainerFactory();

factory.setConnectionFactory(connectionFactory);
factory.setConcurrentConsumers(4);
~~~

This configuration creates four consumers for the listener container. When a consumer finishes a message, it continues receiving the next message. The number of consumers does not grow beyond four on its own.

You can configure the number of consumers directly on the endpoint:

~~~java
@JmsListener(
    id = "ordersListener",
    destination = "orders.queue",
    concurrency = "4-4"
)
public void processOrder(String payload) {
    // Process the order
}
~~~

The annotation's concurrency property overrides the concurrency value set on the factory for that endpoint. Use dedicated configuration when one queue needs more resources than another. With `DefaultMessageListenerContainer`, the single value `4` is a range from 1 up to a maximum of 4 consumers; use `4-4` when you truly want to fix four consumers.

Increasing consumers is usually useful for a queue with a large volume of messages and a listener with a significant processing time. For a queue with few messages, one consumer is usually enough and avoids unnecessary Sessions/threads.

## 5. Configuring a concurrency range and dynamic scaling

DMLC supports concurrency in the lower-upper range form. For example, 2-8 means the container keeps at least two consumers and can grow gradually to at most eight consumers when there is load.

~~~java
factory.setConcurrency("2-8");
~~~

You can set it with two separate properties:

~~~java
factory.setConcurrentConsumers(2);
factory.setMaxConcurrentConsumers(8);
~~~

If you pass just a number such as 8, the lower bound is 1 and the upper bound is 8. For an important queue, set both ends explicitly so you know exactly the baseline load level and the scaling limit.

DMLC starts the base number of consumers. When a consumer receives a message and the container sees there is still load while the number of idle consumers is not enough, it can schedule an additional invoker. The increase happens gradually and does not immediately create all the maximum consumers. When load decreases, surplus consumers are marked idle and stopped according to the configured idle thresholds.

Do not interpret dynamic scaling as the container reading a queue depth figure and then computing exactly the number of consumers needed. DMLC observes message receiving and the idle state of the invokers to decide to increase/decrease.

### 5.1. Controlling scale-up

Related properties:

- concurrentConsumers: the base number of consumers always kept.
- maxConcurrentConsumers: the upper bound on the number of consumers.
- idleConsumerLimit: the number of idle consumers allowed to exist before the container schedules an additional invoker. The default value is 1.
- setConcurrency("2-8"): the shorthand way to set min/max.

Increasing maxConcurrentConsumers lets the system handle larger bursts, but each additional consumer uses more Sessions, threads, and downstream resources. Set the upper bound according to the actual resource budget.

### 5.2. Controlling scale-down

DMLC uses idle thresholds to shrink surplus consumers. The important properties include:

- receiveTimeout: how long one receive waits for a message before returning null.
- idleReceivesPerTaskLimit: the number of consecutive receives with no message before a task is considered idle.
- idleTaskExecutionLimit: the number of executions in which a task is considered idle before a surplus task ends.
- maxMessagesPerTask: the maximum number of message-receive attempts within a task; it affects how the task is rescheduled.

The default value of idleTaskExecutionLimit is 1. If consumers increase/decrease continuously when load fluctuates around the threshold, you can raise the idle limit to keep surplus consumers longer. Increasing receiveTimeout or the number of idle receives also makes consumers live longer, but it can lengthen the scale-down time and increase the wait when checking idleness.

Do not set every threshold very high to avoid scaling down. That can keep many idle threads and Sessions for a long time. Tune according to the burst cycle and the time needed to react when load decreases.

## 6. Configuring annotation-driven listeners

@EnableJms enables the @JmsListener infrastructure. Spring creates one listener container for each endpoint declared on a bean.

Example:

~~~java
@Configuration
@EnableJms
public class JmsConfiguration {

    @Bean
    DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
            new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setSessionTransacted(true);
        factory.setConcurrency("2-8");
        factory.setReceiveTimeout(1_000L);
        // Idle task limits belong to DefaultMessageListenerContainer, not this factory.

        return factory;
    }
}
~~~

Listener:

~~~java
@Component
public class OrderListener {

    @JmsListener(
        id = "ordersListener",
        destination = "orders.queue"
    )
    public void processOrder(String payload) {
        // Process the message
    }
}
~~~

If containerFactory is not specified, the annotation infrastructure looks for the bean named jmsListenerContainerFactory. In the example, the default factory is a DMLC and applies concurrency from 2 to 8.

You can set a dedicated concurrency on the annotation:

~~~java
@JmsListener(
    id = "billingListener",
    destination = "billing.queue",
    concurrency = "1-3"
)
public void processBilling(String payload) {
    // Work that needs fewer resources
}
~~~

Set the concurrency level according to the characteristics of the work. A listener that sends email may need higher concurrency than a listener that processes a transaction writing to many tables or calling an API with a low quota.

## 7. Estimating processing capacity

Suppose a message takes on average S seconds to process. A consumer processing sequentially has a theoretical capacity of approximately:

\[
\text{throughput per consumer} \approx \frac{1}{S}
\]

With C concurrent consumers:

\[
\text{throughput ideal} \approx \frac{C}{S}
\]

For example, the average processing time is 250 ms, equivalent to 0.25 seconds:

- One consumer: about 4 messages/second.
- Four consumers: about 16 messages/second under ideal conditions.
- Eight consumers: about 32 messages/second under ideal conditions.

This is an estimated limit, not a throughput commitment. Actual capacity also depends on the broker, network time, CPU, database, locks, connection pools, external APIs, and the error/retry rate.

Call the rate of incoming messages λ and the total processing capacity μ. If λ is greater than μ for a long time, the backlog will grow. Increasing consumers only helps when the bottleneck is the number of listeners processing. If the database has run out of connections or an external API is rate limiting, increasing consumers can cause more errors.

### 7.1. Example of identifying the bottleneck

A system has four consumers, each message takes on average 200 ms to process. The CPU has spare capacity but the database pool only has four connections and each listener holds a connection throughout processing.

If you increase to 12 consumers, at most four listeners can access the database at the same time; the other eight listeners wait for a connection. Latency rises, threads are held for a long time, and the backlog may not decrease significantly.

Check these at the same time:

- The CPU and listener run time.
- The number of database connections in use and the connection wait time.
- The number of requests waiting at the external service.
- The number of Sessions/consumers at the JMS provider.
- The time messages sit in the queue and the actual processing time.

## 8. Impact on message ordering

A queue can deliver messages in the order received, but multiple consumers processing in parallel change the completion order.

Example:

~~~text
Broker sends:   message-1 -> consumer A
                message-2 -> consumer B

Processing:     consumer A takes 2 seconds
                consumer B takes 200 ms

Completion:     message-2 before message-1
~~~

If the business requires strict ordering, keep one consumer or partition the work by a business key. Another option is to use the message group/partition feature supported by the provider so that messages with the same key are processed in an ordered flow.

Do not increase concurrency based only on throughput if the operations updating the same account, order, or business state depend on ordering. You need to clearly define the scope of ordering that must be protected.

## 9. Queue and topic have different semantics

With a queue, multiple consumers usually share the messages. This is a suitable model for a work queue and competing consumers.

With a topic, a publication is sent to the subscriptions. In an ordinary subscription configuration, each subscription receives a copy of the publication. Increasing the number of consumers can cause an application to receive the same event multiple times if they create independent subscriptions.

If you want multiple workers to share messages from a topic, you must configure a shared subscription per JMS/provider and verify the broker's semantics. Do not assume that increasing concurrency on a topic always means load sharing like a queue.

In most cases of background job processing, using a queue with DMLC and dynamic concurrency is easier to control.

## 10. Transactions and redelivery when the listener fails

DMLC uses AUTO_ACKNOWLEDGE by default if no transaction is configured. With DMLC, the default acknowledgement is performed before the listener runs; if the listener throws an exception, the message may not be redelivered.

If you need reliable processing, configure a local JMS transaction:

~~~java
factory.setSessionTransacted(true);
~~~

Or supply an appropriate external transaction manager, for example JtaTransactionManager with an XA-capable ConnectionFactory.

When the Session is transacted, if the listener processes successfully the transaction commits; if the listener throws an exception, the transaction rolls back and the broker can redeliver the message according to the provider's semantics. Configure a redelivery limit, backoff, and dead-letter policy at the broker/provider so that faulty messages do not loop endlessly.

If the listener updates the database and processes JMS within the same local JMS transaction, the database transaction does not participate automatically. You need a coordinating transaction manager, XA if truly needed, or an idempotency/outbox/inbox design to handle the possibility of redelivery and out-of-sync state.

## 11. TaskExecutor and threads

DMLC runs the listener via tasks through the Spring TaskExecutor. By default, the container uses a SimpleAsyncTaskExecutor and creates threads according to the configured number of consumers.

A listener consumer usually occupies a thread for most of its lifecycle because it continuously waits to receive messages. Therefore, an ordinary thread pool does not necessarily reduce the number of threads needed; the pool must have enough threads to run the long-lived consumers.

Only pass an external TaskExecutor when there is a clear reason, such as needing to integrate with threads managed by the application server or using a SchedulingTaskExecutor with short-lived tasks. You need to ensure the executor does not run short of threads, which would prevent consumers from running.

With Java 21 or later, Spring Framework 6.2 supports enabling virtual threads for DMLC's default executor with setVirtualThreads(true). This feature does not apply to Java 17 and does not by itself increase database or broker capacity. Whether using platform threads or virtual threads, you still must limit concurrency and downstream resources.

## 12. Prefetch and provider message distribution

The JMS specification does not define a common prefetch property for every provider. The broker/provider can send ahead some messages to a consumer before the listener has finished processing the current message.

A high prefetch can reduce round trips and increase throughput for short messages. However, a fast consumer can hold many messages already dispatched by the broker while another consumer has little work. This can make the distribution unbalanced and increase the number of messages sitting in the client-side buffer.

A low prefetch usually helps distribute work more evenly and limits the number of messages being delivered to each consumer, but it can increase the cost of exchanges with the broker.

When tuning prefetch:

- Use the JMS provider's own property; do not assume one configuration applies to every broker.
- Measure the number of messages dispatched but not yet fully processed.
- Check redelivery and redistribution when a consumer stops.
- Combine with the listener's processing time and concurrency.
- Load test with short messages, long messages, and uneven processing times.

Do not just increase prefetch and concurrency at the same time. Changing one factor at a time helps identify the cause when latency or throughput changes.

## 13. Session caching and listener resources

DMLC manages the lifecycle of the Connection, Session, and MessageConsumer according to the cache level. With local JMS resources, the container uses CACHE_CONSUMER by default, meaning it keeps the Connection, Session, and Consumer per listener thread.

When there is an external transaction manager, DMLC uses CACHE_NONE by default to obtain fresh resources within the transaction scope, because some Jakarta EE servers only enlist a newly obtained Connection/Session in an XA transaction. Only change the cache level after verifying the requirements of the provider and the transaction manager.

Do not automatically wrap a CachingConnectionFactory outside DMLC. Spring recommends letting the listener container manage caching within its own lifecycle. An external CachingConnectionFactory can cause problems when stopping/starting the container, scaling consumers, or using provider-specific task hints.

If you need separate caching, test the cases of stop/start, broker reconnect, transaction rollback, dynamic scaling, and durable subscription.

## 14. Monitoring consumers and backlog

DMLC provides useful information:

- getConcurrentConsumers(): the configured base number of consumers.
- getMaxConcurrentConsumers(): the maximum consumer limit.
- getScheduledConsumerCount(): the number of consumers that have been scheduled.
- getActiveConsumerCount(): the number of consumers currently active.
- isRunning(): the state of the listener container.

The scheduled count can be higher than the active count when some consumers have been scheduled but are waiting or have not yet executed. Do not treat the two numbers as equivalent.

You can obtain the container from the JmsListenerEndpointRegistry:

~~~java
DefaultMessageListenerContainer container =
    (DefaultMessageListenerContainer)
        registry.getListenerContainer("ordersListener");

int active = container.getActiveConsumerCount();
int scheduled = container.getScheduledConsumerCount();

System.out.println("activeConsumers=" + active);
System.out.println("scheduledConsumers=" + scheduled);
~~~

Besides the consumer count, you need to monitor:

| Metric | Meaning |
|---|---|
| Queue depth | The number of messages waiting |
| Oldest message age | The age of the oldest message in the queue |
| Enqueue/dequeue rate | The rate at which messages arrive at and leave the queue |
| Processing latency | The time the listener takes to process one message |
| Active/scheduled consumers | The number of consumers actually active and scheduled |
| Redelivery count | The number of times a message is redelivered |
| Failure/dead-letter count | The error rate and the messages moved to the DLQ |
| DB/API wait time | The wait time for auxiliary resources |

If queue depth increases but the consumers have already reached max concurrency, check the processing time and downstream bottlenecks before raising the limit. If active consumers stay lower than scheduled consumers for a long time, check the thread executor, the broker state, and consumer initialization errors.

## 15. Recovery when the broker is interrupted

DMLC has a recovery mechanism for when the broker is temporarily unavailable. The default recovery interval is 5 seconds. You can use setRecoveryInterval() or setBackOff() to adjust the interval between connection attempts.

~~~java
factory.setBackOff(new FixedBackOff(5_000L, FixedBackOff.UNLIMITED_ATTEMPTS));
~~~

For the factory, configure `setBackOff(...)`; `setRecoveryInterval(...)` is a setter on `DefaultMessageListenerContainer`, not on `DefaultJmsListenerContainerFactory`. Similarly, `setIdleTaskExecutionLimit(...)` is a DMLC configuration. When you need to control these two values directly, create the container manually:

~~~java
import org.springframework.jms.listener.DefaultMessageListenerContainer;

DefaultMessageListenerContainer container = new DefaultMessageListenerContainer();
container.setIdleTaskExecutionLimit(2);
container.setRecoveryInterval(5_000L);
~~~

If the broker has a long maintenance window or restart, an increasing backoff can reduce the number of continuous connection attempts. When the broker returns, the container re-creates the necessary JMS resources and continues receiving messages.

Recovery does not replace transactions and idempotency. If the connection is lost exactly when a message is being processed or committed, the application needs to accept an uncertain outcome and handle redelivery safely.

## 16. A runnable example with Java 17, Spring JMS, and ActiveMQ Classic

The example uses Spring Framework 6.2.19, Java 17, and Apache ActiveMQ Classic 6.1.5. The ActiveMQ VM transport creates an embedded broker inside the JVM, which is suitable for local practice. The program sends 24 messages to a queue; DMLC starts with two consumers and can grow to six consumers when there is load.

### 16.1. Project structure

~~~text
jms-concurrency-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/example/
                ├── JmsConfig.java
                ├── WorkListener.java
                └── ConcurrencyJmsDemo.java
~~~

### 16.2. Maven dependencies

Create pom.xml:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>jms-concurrency-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jms</artifactId>
            <version>6.2.19</version>
        </dependency>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>activemq-all</artifactId>
            <version>6.1.5</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

ActiveMQ Classic 6.x uses the jakarta.jms namespace, compatible with Spring Framework 6.2. The activemq-all dependency bundles the components needed for the embedded-broker example.

### 16.3. Configuring the JMS listener container

Create src/main/java/com/example/JmsConfig.java:

~~~java
package com.example;

import jakarta.jms.ConnectionFactory;

import org.apache.activemq.ActiveMQConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.util.backoff.FixedBackOff;

@Configuration
@EnableJms
public class JmsConfig {

    @Bean
    ConnectionFactory connectionFactory() {
        return new ActiveMQConnectionFactory(
            "vm://concurrency-demo?broker.persistent=false&broker.useJmx=false"
        );
    }

    @Bean
    DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
            new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setSessionTransacted(true);
        factory.setConcurrency("2-6");
        factory.setReceiveTimeout(1_000L);
        factory.setBackOff(new FixedBackOff(5_000L, FixedBackOff.UNLIMITED_ATTEMPTS));

        return factory;
    }

    @Bean
    JmsTemplate jmsTemplate(ConnectionFactory connectionFactory) {
        return new JmsTemplate(connectionFactory);
    }

    @Bean
    WorkListener workListener() {
        return new WorkListener(24);
    }
}
~~~

The jmsListenerContainerFactory bean is used by the @EnableJms infrastructure as the default factory. The 2-6 configuration keeps at least two consumers and allows scaling up to at most six. Session transactions are enabled so that a listener exception can roll back the JMS transaction and trigger redelivery according to the provider's policy.

### 16.4. The listener that processes messages

Create src/main/java/com/example/WorkListener.java:

~~~java
package com.example;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.jms.annotation.JmsListener;

public class WorkListener {

    private final CountDownLatch completedLatch;
    private final AtomicInteger inFlight = new AtomicInteger();
    private final AtomicInteger peakInFlight = new AtomicInteger();
    private final AtomicInteger completed = new AtomicInteger();

    public WorkListener(int expectedMessages) {
        this.completedLatch = new CountDownLatch(expectedMessages);
    }

    @JmsListener(
        id = "workListener",
        destination = "work.queue"
    )
    public void process(String payload) {
        int current = inFlight.incrementAndGet();
        peakInFlight.accumulateAndGet(current, Math::max);

        boolean success = false;
        try {
            Thread.sleep(150);
            completed.incrementAndGet();
            success = true;
        }
        catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Listener interrupted", ex);
        }
        finally {
            inFlight.decrementAndGet();
            if (success) {
                completedLatch.countDown();
            }
        }
    }

    public boolean await(long timeout, TimeUnit unit)
            throws InterruptedException {
        return completedLatch.await(timeout, unit);
    }

    public int getCompleted() {
        return completed.get();
    }

    public int getPeakInFlight() {
        return peakInFlight.get();
    }
}
~~~

The listener bean is shared among the consumer threads, so the counters use AtomicInteger and CountDownLatch. Each invocation processes a message in 150 ms to simulate work that takes time to execute.

### 16.5. The program that sends messages

Create src/main/java/com/example/ConcurrencyJmsDemo.java:

~~~java
package com.example;

import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.jms.core.JmsTemplate;

public class ConcurrencyJmsDemo {

    public static void main(String[] args) throws InterruptedException {
        try (var context =
                new AnnotationConfigApplicationContext(JmsConfig.class)) {

            JmsTemplate jmsTemplate =
                context.getBean(JmsTemplate.class);

            WorkListener listener =
                context.getBean(WorkListener.class);

            for (int i = 1; i <= 24; i++) {
                jmsTemplate.convertAndSend(
                    "work.queue",
                    "job-" + i
                );
            }

            if (!listener.await(30, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                    "Timed out waiting for all messages"
                );
            }

            System.out.println(
                "completed=" + listener.getCompleted()
            );
            System.out.println(
                "peakInFlight=" + listener.getPeakInFlight()
            );
        }
    }
}
~~~

Run with JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=com.example.ConcurrencyJmsDemo
~~~

Result:

~~~text
completed=24
peakInFlight=N
~~~

completed is always 24 if every message is processed successfully. N is the largest number of concurrent listener invocations observed in that run; the value depends on thread scheduling and the environment, and is not necessarily six. The 2-6 configuration is a limit of the container, not a requirement that there must always be six consumers.

The example uses an embedded broker that does not persist messages durably and is only for learning. When connecting to a real broker, replace the ConnectionFactory and configure the credentials/TLS and queues according to the environment.

## 17. Tuning load by type of work

You should not use one common concurrency for every listener. Classify by processing characteristics:

| Type of work | Characteristic | Configuration direction |
|---|---|---|
| Sending email or calling HTTP | Mostly waiting on I/O | Can increase concurrency up to the quota and connection limits |
| Resizing images or compressing files | Consumes CPU and memory | Limit concurrency according to CPU/RAM |
| Writing database data | Depends on the connection pool and locks | Balance consumers against the DB pool and contention |
| Processing invoices per account | Has a per-key ordering requirement | Partition by accountId or keep processing sequential per key |
| A queue with few messages and no short SLA | Low load | Keep one consumer or low concurrency |
| Batch-wise bursts | Variable load | Use DMLC min/max and appropriate idle thresholds |

If the listener performs a very short operation, the cost of creating a Session, a transaction, and moving the message can take up a large share. In that case, batching or grouping work can be more effective than increasing the number of consumers without limit.

If the listener calls an external service with a quota, set max concurrency according to that quota. For example, if the service allows 20 concurrent requests, you should not create 100 consumers all calling the service without a rate limiter or bulkhead.

## 18. Common mistakes

- **Increasing concurrentConsumers without checking the database**: listeners may wait for connections and make the backlog grow faster.
- **Mistaking concurrency for the thread count of the whole application**: each endpoint has its own container; each replica has its own number of consumers.
- **Setting maxConcurrentConsumers too high**: can overload the broker, CPU, or external services.
- **Using dynamic scaling for an ordinary topic subscription**: the application may receive multiple copies of the same publication.
- **Assuming the completion order is preserved**: multiple consumers processing in parallel can complete a later message before an earlier one.
- **Using SimpleMessageListenerContainer when dynamic scaling is needed**: SMLC keeps the number of consumers fixed.
- **Using AUTO_ACKNOWLEDGE when reliable redelivery is needed**: DMLC acks before the listener invocation; a listener exception can leave the message not redelivered.
- **Using a TaskExecutor that is too small**: not enough threads to run the listener consumers.
- **Increasing receiveTimeout too much**: the time to detect an idle consumer and scale down can drag on.
- **Lowering receiveTimeout too much**: increases the number of polls when the queue is empty and can increase overhead.
- **Ignoring the provider's prefetch**: one consumer can hold many messages waiting to be processed, making the distribution unbalanced.
- **Not observing the active and scheduled consumer counts**: it is hard to know how far the container has scaled or which threads have not yet run.
- **Not testing broker restart and listener shutdown**: bugs often only appear when the JMS resources are re-created.

## 19. Pre-production tuning checklist

- [ ] Choose DMLC if you need dynamic concurrency, transactions, or recovery.
- [ ] Set concurrentConsumers according to the baseline load and maxConcurrentConsumers according to the resource limits.
- [ ] Calculate the total consumers across all application replicas.
- [ ] Determine the ordering requirements and choose the appropriate queue/topic/shared subscription.
- [ ] Enable sessionTransacted or an external transaction manager if you need redelivery when the listener fails.
- [ ] Configure retry, redelivery limit, and dead-letter policy at the broker/provider.
- [ ] Measure the average processing time and p95/p99.
- [ ] Measure queue depth, the age of the oldest message, enqueue/dequeue rate, and active consumers.
- [ ] Check CPU, the database pool, HTTP quota, and lock contention.
- [ ] Choose receiveTimeout and idle thresholds according to the load cycle.
- [ ] Check prefetch per provider and workload type.
- [ ] Ensure the TaskExecutor has enough threads for the configured consumers.
- [ ] Test scale-up, scale-down, broker restart, transaction rollback, and shutdown.
- [ ] Keep the maximum concurrency within the resource budget that has been measured.

## 20. Summary

The Spring JMS listener container manages consumers, Sessions, threads, transactions, and recovery when the broker is interrupted. With DMLC, concurrentConsumers sets the baseline level and maxConcurrentConsumers sets the scaling limit. A configuration of the form 2-8 keeps two consumers when load is low and can grow gradually to eight when the queue has many messages.

The effectiveness of concurrency depends on the entire processing path. Increasing consumers only pays off when the broker, CPU, database, thread executor, and auxiliary services still have capacity to respond. When there are many consumers, the message completion order can change; topic subscriptions have different semantics from queues; and transactions must be configured explicitly if you need redelivery when the listener fails.

Start from real load data, adjust one factor at a time, and monitor both the backlog and downstream resources. This approach helps choose a stable concurrency, avoid over-scaling, and keep processing behavior in line with the business requirements.

## References

- Spring Framework 6.2 — Using Spring JMS: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html
- Spring Framework 6.2 — Annotation-driven Listener Endpoints: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html
- Spring Framework 6.2.19 — DefaultMessageListenerContainer Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html
- Spring Framework 6.2.x — SimpleMessageListenerContainer Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/SimpleMessageListenerContainer.html
- Jakarta Messaging Specification: https://jakarta.ee/specifications/messaging/3.1/