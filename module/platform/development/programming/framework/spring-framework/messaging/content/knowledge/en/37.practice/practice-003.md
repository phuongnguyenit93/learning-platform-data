# Building a JMS Work Queue with Acknowledgement and Rollback

A JMS work queue receives jobs from a producer, stores messages in a broker, and delivers them to consumers. When processing succeeds, the consumer acknowledges the message so the broker removes it from the queue. When processing fails, the consumer needs to roll back or recover so the broker can redeliver the message. Acknowledgement determines what happens when a listener throws an exception, a process stops, or the broker loses its connection.

In Spring, JmsTemplate sends messages; DefaultMessageListenerContainer receives messages and invokes the listener; `@JmsListener` declares endpoints via annotations. For work requiring reliability, use a transacted JMS Session so that message receipt and acknowledgement belong to a local transaction. The listener commits only when processing completes; an exception rolls back the transaction and the provider can redeliver the message.

This lesson uses Spring Framework 7.0.8, Jakarta JMS, ActiveMQ Classic 6.1.5, and Java 17. ActiveMQ is the provider for the embedded test; the transaction model belongs to JMS/Spring, while delay, retry limit, and DLQ are broker-specific policies.

## 1. Queue Workflow

A JMS queue supports competing consumers: multiple consumers listen to the same destination and the broker distributes one message to one consumer at a time. Each consumer typically uses its own JMS Session.

~~~text
Producer
   | send(jobId, payload)
   v
JMS Queue
   | deliver
   v
Listener Container
   | begin local JMS transaction
   v
Business Handler
   | success   -> commit Session   -> broker removes message
   | exception -> rollback Session -> broker redelivers
                                      |
                                      +-> retry limit exceeded -> DLQ
~~~

Three operations must be distinguished:

- Send: the producer sends a message to the destination.
- Receive: the broker delivers the message to the consumer.
- Acknowledge/commit: the consumer confirms the message has been processed according to the session's semantics.

A delivered message does not mean business logic has completed. A message read into memory does not mean the broker has deleted it. With a transacted session, commit is the point confirming receipt and the JMS operations within the same session transaction.

A queue is suitable when each job needs to be processed by one consumer. A topic is suitable when multiple subscribers need to receive the same event. Do not use a topic instead of a queue just to increase the number of consumers; delivery and subscription semantics differ.

## 2. JMS Acknowledgement Modes

| Mode | How it acknowledges | Behavior and limitations |
|---|---|---|
| AUTO_ACKNOWLEDGE | Provider acknowledges automatically per listener/receive semantics | Spring warns this default mode does not guarantee reliability for many message listeners; a listener error can lose messages |
| CLIENT_ACKNOWLEDGE | Client calls Message.acknowledge() | Acknowledge confirms all consumed messages on the Session, not just the current message |
| DUPS_OK_ACKNOWLEDGE | Provider is permitted to acknowledge lazily | Duplicates may appear; suitable when throughput matters more than avoiding duplicates |
| SESSION_TRANSACTED | Client commits or rolls back the Session | Rollback causes the message to be redelivered per provider policy; suitable for critical work queues |

With CLIENT_ACKNOWLEDGE, calling message.acknowledge() has Session-wide scope. If a listener processes multiple messages on the same session, the acknowledgement scope may be broader than expected.

With a transacted session, do not call Message.acknowledge(). The listener container manages Session.commit() when the listener completes successfully and Session.rollback() when the listener throws an exception. Let a single place own the transaction boundary.

## 3. Enabling Transactions for Listeners

When the listener container sets sessionTransacted=true, each listener invocation runs inside a local JMS transaction:

1. The container receives the message in a transacted Session.
2. The listener executes business logic.
3. The listener finishes normally: the container commits the Session.
4. The listener throws an exception: the container rolls back the Session.
5. The broker can redeliver the message according to provider policy.

Rollback protects a message from being acknowledged before the listener finishes processing. However, rollback does not automatically undo side effects outside JMS such as database writes, HTTP calls, or file creation.

For example: the listener writes to the database successfully, then the JMS commit fails. The broker redelivers the message and the listener may write the record again. Therefore, transacted JMS usually provides at-least-once semantics; the application still needs idempotency and duplicate detection.

### 3.1. Configuring DefaultMessageListenerContainer

DefaultMessageListenerContainer is a common choice because it supports dynamic concurrency, recovery, and external transactions when configured. Basic Java configuration:

~~~java
@Bean
DefaultMessageListenerContainer jobsContainer(
        ConnectionFactory connectionFactory,
        MessageListener jobsListener) {

    DefaultMessageListenerContainer container =
            new DefaultMessageListenerContainer();
    container.setConnectionFactory(connectionFactory);
    container.setDestinationName("jobs.queue");
    container.setMessageListener(jobsListener);
    container.setSessionTransacted(true);
    container.setConcurrentConsumers(2);
    container.setMaxConcurrentConsumers(8);
    return container;
}
~~~

sessionTransacted=true is the key point. When the listener throws a runtime exception, the container rolls back the session. The provider determines delay, redelivery count, and DLQ.

### 3.2. Configuring @JmsListener

For annotation-driven listener endpoints, configure DefaultJmsListenerContainerFactory:

~~~java
@Configuration
@EnableJms
class JmsWorkQueueConfig {

    @Bean
    DefaultJmsListenerContainerFactory workQueueFactory(
            ConnectionFactory connectionFactory) {
        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setSessionTransacted(true);
        factory.setConcurrency("2-8");
        return factory;
    }
}

@Component
class JobListener {
    private final JobProcessor processor;

    JobListener(JobProcessor processor) {
        this.processor = processor;
    }

    @JmsListener(destination = "jobs.queue",
            containerFactory = "workQueueFactory")
    public void handle(Job job) {
        processor.process(job);
    }
}
~~~

If processor.process(job) throws an exception, the exception must propagate out of the listener for the container to roll back. If you catch the exception and only log it without rethrowing, the container considers the listener finished normally and commits the message. For retryable errors, throw an exception; for non-retryable errors, route the message to an error flow/DLQ per your designed policy.

## 4. Sending Jobs with JmsTemplate

JmsTemplate manages message creation, sending to a destination, and releasing JMS resources. Example sending a job with a stable ID:

~~~java
jmsTemplate.convertAndSend("jobs.queue", job, message -> {
    message.setStringProperty("jobId", job.id());
    message.setJMSCorrelationID(job.correlationId());
    return message;
});
~~~

jobId is the business key used for idempotency. JMSCorrelationID is useful for correlating request/reply or logs; it does not create idempotency by itself and does not replace a database unique constraint.

If jobs must survive a broker restart, persistent delivery mode and properly configured broker persistence are required. Persistent delivery mode does not guarantee durable storage on its own if the broker runs non-persistently or storage is not safely operated.

You can configure the delivery mode explicitly:

~~~java
jmsTemplate.setDeliveryMode(DeliveryMode.PERSISTENT);
jmsTemplate.setExplicitQosEnabled(true);
~~~

JmsTemplate is thread-safe once configured. Reuse the template bean rather than creating a new template for each job.

## 5. Rollback, Redelivery, and Retry Policy

When a listener throws an exception in a transacted session, the container rolls back. The broker detects the uncommitted delivery and redelivers the message. Common indicators:

- JMSRedelivered indicates the message was delivered previously.
- JMSXDeliveryCount represents how many times the message has been delivered if the provider supports this property.
- The provider may apply redelivery delay, exponential backoff, and maximum redeliveries.
- When exceeding the retry limit, the broker can move the message to a Dead Letter Queue (DLQ).

Not all providers use the same property, delay, or DLQ name. Check the documentation of the deployed broker. ActiveMQ Classic has RedeliveryPolicy with initial delay, exponential backoff, and maximum redeliveries.

Example ActiveMQ Classic configuration:

~~~java
RedeliveryPolicy policy = new RedeliveryPolicy();
policy.setInitialRedeliveryDelay(1_000);
policy.setUseExponentialBackOff(true);
policy.setBackOffMultiplier(2.0);
policy.setMaximumRedeliveries(5);
connectionFactory.setRedeliveryPolicy(policy);
~~~

maximumRedeliveries=5 allows up to five redeliveries after the initial delivery per ActiveMQ semantics. The total number of times the listener is invoked may exceed the retry count. Verify with tests on the actual provider and version.

Do not let failing messages loop immediately and infinitely. Delay/backoff avoids hot loops and reduces load when a dependency is down. You can add jitter if supported by the provider to prevent many messages from retrying simultaneously.

## 6. Poison Messages and Dead Letter Queues

A poison message is a message that always fails due to bad data, incompatible schema, missing configuration, or a bug that cannot self-heal with retries. If the broker redelivers infinitely, the message can occupy consumers and stall queue progress.

A DLQ is where the broker moves a message after exceeding the redelivery policy or when delivery fails. A DLQ needs an operational process:

1. Monitor message count and age in the DLQ.
2. Record the last cause, delivery count, job ID, and original destination.
3. Classify transient errors, data errors, and code bugs.
4. Fix the root cause before replaying.
5. Replay in a controlled manner and ensure consumers are idempotent.
6. Keep an audit trail for replaying or discarding messages.

ActiveMQ Classic can use ActiveMQ.DLQ by default; an individual dead-letter strategy gives each queue its own DLQ. Example XML for the ActiveMQ Classic broker:

~~~xml
<destinationPolicy>
    <policyMap>
        <policyEntries>
            <policyEntry queue=">">
                <deadLetterStrategy>
                    <individualDeadLetterStrategy
                            queuePrefix="DLQ."
                            useQueueForQueueMessages="true"/>
                </deadLetterStrategy>
            </policyEntry>
        </policyEntries>
    </policyMap>
</destinationPolicy>
~~~

This XML snippet belongs to ActiveMQ Classic broker configuration, not Spring configuration. Other providers may use different DLQ names and routing policies.

## 7. JMS and Database Transactions

sessionTransacted=true only protects operations within the JMS Session. If the listener also updates a database, the two resources do not automatically become a single atomic transaction.

Common failure window:

~~~text
JMS message delivered
       |
       v
DB transaction commits
       |
       X JVM stops before JMS commit
       |
       v
Broker redelivers the message
       |
       v
DB operation runs again
~~~

If the DB commits before the JMS commit and the process stops in between, the message will be redelivered. This is duplicate delivery, not an abnormal broker failure.

Approaches to handle this:

- Idempotent consumer: use jobId/messageId as a unique key in the DB; if already processed, do not repeat side effects.
- Inbox table: record processed messages in the same DB transaction as business updates. A unique constraint on the message ID enables safe duplicate handling.
- Outbox pattern: producer writes business data and an outbox row in the same DB transaction; a relay sends outbox messages to the broker. The relay may publish duplicates, so consumers still need idempotency.
- XA/JTA: coordinate JMS and database in a distributed transaction if both resource managers support XA and operations accept XA's complexity, latency, and recovery overhead.

Do not assume `@Transactional` on a listener automatically creates a distributed transaction. It uses the configured transaction manager. If that is a database transaction manager while the listener container uses a local JMS transaction, the two transactions can still commit independently.

Example inbox consumer:

~~~java
@Transactional
public void process(Job job) {
    if (!inboxRepository.insertIfAbsent(job.id())) {
        return; // Message already processed; this is a redelivery/duplicate.
    }

    orderService.apply(job);
}
~~~

insertIfAbsent must be protected by a unique constraint or a database-appropriate upsert. Checking existence then inserting in two steps can hit a race condition when two consumers process the same ID. The inbox record and business update must commit in the same DB transaction. Only afterward does the listener container commit the JMS Session. If the message is redelivered, the consumer sees the inbox record and does not repeat side effects.

## 8. Retry or Terminate?

Not every exception should trigger redelivery:

| Error type | Example | Recommended policy |
|---|---|---|
| Transient dependency | Database timeout, HTTP 503, broker dependency temporarily unavailable | Roll back and retry with backoff |
| Resolvable business conflict | Resource currently locked, version out of sync | Limited retry or retry queue |
| Validation/permanent | Missing required field, invalid enum | Do not retry for long; move to DLQ/quarantine |
| Schema incompatibility | Consumer cannot read payload version | DLQ and fix compatibility |
| Code bug | Repeated NullPointerException | Limit retries, alert, and DLQ |

The listener should throw an exception when rollback is desired. If you want to skip a job for business reasons, persist that decision durably and let the listener complete normally. Do not catch and swallow exceptions just to avoid red logs; that behavior can cause the broker to commit a message even though the work did not succeed.

Local retry keeps the message within a single listener invocation; broker redelivery rolls back the transaction and creates a new delivery attempt. Do not stack multiple retry layers without calculating the total attempt count and maximum duration.

## 9. Concurrency, Ordering, and Queue Throughput

Increasing consumer count allows processing more jobs in parallel. With DefaultMessageListenerContainer, concurrentConsumers is the initial consumer count; maxConcurrentConsumers is the upper limit when the container scales dynamically. With an annotation factory, setConcurrency("2-8") declares the concurrency range.

High concurrency is not always better:

- The database connection pool may be smaller than the consumer count.
- Downstream APIs have rate limits.
- Long jobs can hold sessions/consumers for a long time.
- Redelivery and multiple consumers can alter processing order.
- If multiple jobs update the same aggregate, locking or optimistic concurrency is needed at the business layer.

A queue typically distributes one message to one consumer, but you should not assume business completion order always matches send order when multiple consumers, retries, or priorities exist. If per-key ordering is required, consider provider-supported message groups/partitioning or sequential processing by aggregate key.

Set concurrency limits based on downstream capacity, not just CPU. Observe queue depth, oldest message age, processing latency, consumer count, and redelivery rate before adding workers.

## 10. Java 17 Example: Testing Real Rollback and Redelivery

The test below uses an ActiveMQ Classic embedded broker over VM transport. The listener intentionally throws an exception on the first attempt; because the listener container uses a transacted session, the message is rolled back and redelivered by the broker. On the second attempt the listener completes, the session commits, and the message is acknowledged.

The test verifies transaction/redelivery within a single JVM. The broker is configured as non-persistent for fast testing; it does not prove message survival across broker restarts. Production requires persistent broker storage and proper delivery configuration.

### 10.1. Maven Dependencies

Minimal POM for Java 17:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>jms-rollback-redelivery-test</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <spring.version>7.0.8</spring.version>
    <activemq.version>6.1.5</activemq.version>
    <junit.version>5.12.2</junit.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-jms</artifactId>
      <version>${spring.version}</version>
    </dependency>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>${spring.version}</version>
    </dependency>
    <dependency>
      <groupId>org.apache.activemq</groupId>
      <artifactId>activemq-broker</artifactId>
      <version>${activemq.version}</version>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.apache.activemq</groupId>
      <artifactId>activemq-client</artifactId>
      <version>${activemq.version}</version>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.apache.activemq</groupId>
      <artifactId>activemq-kahadb-store</artifactId>
      <version>${activemq.version}</version>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.junit.jupiter</groupId>
      <artifactId>junit-jupiter</artifactId>
      <version>${junit.version}</version>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.14.0</version>
        <configuration><release>17</release></configuration>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.5.3</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

### 10.2. Complete Test

Save as src/test/java/example/JmsRollbackRedeliveryTest.java:

~~~java
package example;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import jakarta.jms.MessageListener;
import org.apache.activemq.ActiveMQConnectionFactory;
import org.apache.activemq.RedeliveryPolicy;
import org.apache.activemq.broker.BrokerService;
import org.junit.jupiter.api.Test;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.listener.DefaultMessageListenerContainer;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class JmsRollbackRedeliveryTest {

    @Test
    void listenerFailureRollsBackAndBrokerRedelivers() throws Exception {
        BrokerService broker = new BrokerService();
        broker.setBrokerName("jms-rollback-test");
        broker.setPersistent(false);
        broker.setUseJmx(false);
        broker.addConnector("vm://jms-rollback-test");
        broker.start();
        broker.waitUntilStarted();

        ActiveMQConnectionFactory connectionFactory =
                new ActiveMQConnectionFactory("vm://jms-rollback-test?create=false");
        RedeliveryPolicy redelivery = new RedeliveryPolicy();
        redelivery.setInitialRedeliveryDelay(100);
        redelivery.setUseExponentialBackOff(false);
        redelivery.setMaximumRedeliveries(2);
        connectionFactory.setRedeliveryPolicy(redelivery);

        CountDownLatch completed = new CountDownLatch(1);
        AtomicInteger attempts = new AtomicInteger();
        AtomicInteger deliveryCount = new AtomicInteger();
        AtomicReference<String> completedJob = new AtomicReference<>();

        DefaultMessageListenerContainer container =
                new DefaultMessageListenerContainer();
        container.setConnectionFactory(connectionFactory);
        container.setDestinationName("jobs.queue");
        container.setSessionTransacted(true);
        container.setConcurrentConsumers(1);
        container.setMaxConcurrentConsumers(1);
        container.setMessageListener((MessageListener) message -> {
            int attempt = attempts.incrementAndGet();
            try {
                deliveryCount.set(message.getIntProperty("JMSXDeliveryCount"));
                String jobId = message.getStringProperty("jobId");
                if (attempt == 1) {
                    throw new IllegalStateException("simulated transient failure");
                }
                completedJob.set(jobId);
                completed.countDown();
            }
            catch (jakarta.jms.JMSException ex) {
                throw new IllegalStateException(ex);
            }
        });
        container.afterPropertiesSet();
        container.start();

        try {
            JmsTemplate template = new JmsTemplate(connectionFactory);
            template.convertAndSend("jobs.queue", "generate-report", message -> {
                message.setStringProperty("jobId", "job-42");
                return message;
            });

            assertTrue(completed.await(10, TimeUnit.SECONDS),
                    "job should be redelivered and processed");
            assertEquals("job-42", completedJob.get());
            assertEquals(2, attempts.get());
            assertEquals(2, deliveryCount.get());
        }
        finally {
            container.stop();
            container.destroy();
            broker.stop();
            broker.waitUntilStopped();
        }
    }
}
~~~

The test uses ActiveMQ's JMSXDeliveryCount to verify the message was delivered a second time. Assertions also check the job ID and how many times the listener was actually invoked. CountDownLatch waits for completion with a timeout; do not use Thread.sleep() to guess redelivery timing.

Run:

~~~bash
mvn test
~~~

Expected Surefire output:

~~~text
Tests run: 1, Failures: 0, Errors: 0, Skipped: 0
~~~

SLF4J logs may warn that no provider is present in this minimal test; that simply means logging falls back to NOP and does not affect the transaction/redelivery assertions. Real applications should select a compatible logging provider.

## 11. Monitoring Queues and Redeliveries in Production

Monitor the following metrics:

- Queue depth: number of waiting messages.
- Oldest message age: age of the oldest message.
- Enqueue/dequeue rate: rate at which producers send and consumers receive.
- In-flight/delivering count: messages currently delivered but not yet committed.
- Consumer count and consumer utilization.
- Processing duration p50/p95/p99.
- Redelivery count/rate and number of messages with JMSRedelivered=true.
- DLQ depth, message age, and rate of messages moved to DLQ.
- Transaction rollback/commit rate and broker connection errors.

Log each job with jobId, JMSMessageID, JMSCorrelationID, destination, JMSRedelivered, JMSXDeliveryCount, consumer instance, start/end timestamps, and outcome. Do not log sensitive payloads or credentials. Avoid using jobId as a metric tag due to unbounded cardinality; keep IDs in logs/traces.

A useful queue alert typically combines queue depth and oldest message age. High depth while dequeue rate remains high may just be a burst; continuously rising oldest age while dequeue rate is near zero signals consumers are not making progress. Rapidly growing DLQ or sudden spikes in redelivery rate require separate alerts.

## 12. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Using AUTO_ACKNOWLEDGE for critical jobs | Messages may be acknowledged despite processing errors | Use a transacted listener session |
| Catching exceptions without rethrowing | Container commits the message | Rethrow when rollback is needed |
| Calling Message.acknowledge() in a transacted session | Mixes two acknowledgement models | Let the container commit/roll back the session |
| Assuming CLIENT_ACKNOWLEDGE acknowledges one message | May acknowledge multiple messages on the same session | Understand session scope or use a transacted session |
| Infinite retries | Poison message occupies the queue and workers | Limit retries, add backoff, and use a DLQ |
| Moving messages to DLQ without monitoring | Failed jobs are forgotten | Dashboards, alerts, and a replay process |
| DB commits while JMS rolls back | Redelivery repeats side effects | Inbox/idempotency or XA/JTA when truly required |
| Spawning an async task and returning from the listener | JMS transaction commits before the task finishes | Process inside the listener or hand off to another queue |
| Increasing concurrency without measurement | DB/API overload, higher latency | Bound by downstream capacity |
| Using a non-persistent broker in production | Messages may be lost when the broker stops | Persistent delivery and persistent broker store |

## 13. Implementation Checklist

- Use a queue for competing consumers and define destinations clearly.
- Producers send persistent messages if durability is required and the broker has persistent storage.
- Listener container enables sessionTransacted=true or uses an appropriate transaction manager.
- Listener throws an exception when rollback is desired; never swallow errors.
- Redelivery policy includes delay, backoff, and attempt limits.
- Poison messages have a DLQ/quarantine and an investigation/replay procedure.
- Consumers are idempotent using job IDs or an inbox table.
- Boundaries between JMS transactions and database transactions are clearly defined.
- Concurrency is chosen based on DB pool, API quotas, and processing duration.
- Monitor queue depth, oldest age, in-flight, redelivery, rollback, and DLQ.
- Test the failure path: listener throws an exception, broker redelivers, subsequent attempt commits.
- Test broker restarts and persistence separately in an appropriate integration environment.
- Close listener containers and broker/client resources during tests/shutdown.

## References

- [Spring Framework — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html)
- [Spring Framework — Receiving JMS Messages](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html)
- [Spring Framework API — DefaultMessageListenerContainer](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html)
- [ActiveMQ Classic — Redelivery Policy](https://activemq.apache.org/components/classic/documentation/redelivery-policy)
- [ActiveMQ Classic — Message Redelivery and DLQ Handling](https://activemq.apache.org/components/classic/documentation/message-redelivery-and-dlq-handling)
- [ActiveMQ Classic — VM Transport](https://activemq.apache.org/components/classic/documentation/vm-transport-reference)
