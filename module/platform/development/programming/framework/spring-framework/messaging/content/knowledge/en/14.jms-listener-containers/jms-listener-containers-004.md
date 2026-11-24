# Criteria for Choosing a Container by Transactions and Scalability

> Goal: choose the right JMS listener container according to transaction, reliability, throughput, and scalability requirements; understand the differences between `SimpleMessageListenerContainer` and `DefaultMessageListenerContainer`; configure concurrency, acknowledgement, and recovery, and test behavior when the listener fails.

## 1. What does a listener container solve?

A JMS listener container is the intermediary component between the JMS provider and the application's listener. The container creates and manages the `Connection`, `Session`, `MessageConsumer`, the message-receiving threads, transactions, acknowledgement, and the listener lifecycle. As a result, the business code only needs to process the payload when it is invoked.

In Spring, the two standard implementations usually considered are:

- `SimpleMessageListenerContainer` (SMLC).
- `DefaultMessageListenerContainer` (DMLC).

Both receive messages asynchronously and invoke the listener. The main differences are in how messages are received, which transactions are supported, the ability to adjust the number of consumers automatically, and how recovery works when the broker has a problem.

## 2. SimpleMessageListenerContainer

`SimpleMessageListenerContainer` creates a fixed number of sessions and consumers when the container starts. It registers the listener with the standard JMS API `MessageConsumer.setMessageListener()` and lets the JMS provider invoke the `onMessage()` callback when a message arrives.

Characteristics:

- The number of consumers is determined at startup; the container does not increase/decrease it according to load.
- Relies on the JMS provider's asynchronous callback mechanism.
- Supports local JMS transactions through `sessionTransacted=true`.
- Does not participate in externally managed transactions such as JTA.
- Has compatibility requirements with Jakarta EE environments that restrict JMS resources; you need to check the provider/container before choosing.

SMLC suits cases with stable load, a fixed number of consumers, an application running in an appropriate standalone JMS environment, and no need for an external transaction manager. It has simple configuration, but the application must determine the appropriate concurrency from the start.

### SMLC configuration example

```java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.listener.SimpleMessageListenerContainer;

@Configuration
class SimpleJmsConfiguration {

    @Bean
    SimpleMessageListenerContainer simpleOrdersContainer(
            ConnectionFactory connectionFactory,
            OrderMessageListener listener) {
        var container = new SimpleMessageListenerContainer();
        container.setConnectionFactory(connectionFactory);
        container.setDestinationName("orders.incoming");
        container.setMessageListener(listener);
        container.setConcurrentConsumers(2);
        container.setSessionTransacted(true);
        return container;
    }
}
```

The example creates two fixed consumers and uses a local JMS transaction for each processing run. `OrderMessageListener` is a listener supplied by the application. If the listener throws an exception within the transaction, the session is rolled back and the broker can redeliver the message according to the provider's policy.

SMLC also supports `CLIENT_ACKNOWLEDGE`, but this mode only acknowledges the message and does not group other JMS operations in the same session into a transaction. When you need to send a reply or coordinate multiple JMS operations, a transacted session is usually clearer.

## 3. DefaultMessageListenerContainer

`DefaultMessageListenerContainer` is the common choice for most Spring JMS applications. The container uses a `MessageConsumer.receive()` loop on Spring-managed tasks, instead of handing the entire job of invoking the listener to the provider's callback thread.

Characteristics:

- Supports a minimum and maximum number of consumers, which can grow with load and then shrink back to the base level.
- Supports local JMS transactions with `sessionTransacted=true`.
- Can participate in externally managed transactions, typically JTA with an XA-capable `ConnectionFactory`.
- Has a recovery mechanism when the broker is temporarily unavailable.
- Allows configuring the cache level, receive timeout, executor, recovery interval, or `BackOff`.

DMLC suits cases where you need to scale consumers with load, need to participate in JTA/XA, or want the container to recover on its own after the broker is interrupted. It has more options, so concurrency, cache, and transactions need to be configured deliberately.

## 4. Comparing the two containers

| Criterion | `SimpleMessageListenerContainer` | `DefaultMessageListenerContainer` |
|---|---|---|
| Receiving method | The provider invokes the `MessageListener` | The container polls with `MessageConsumer.receive()` |
| Consumers | Fixed from startup | Fixed or increasing/decreasing within the configured limits |
| Local JMS transaction | Yes, via `sessionTransacted` | Yes, via `sessionTransacted` |
| External transaction/JTA | Not supported | Supported |
| Broker recovery | Depends on the provider and the container lifecycle | Has integrated recovery, with configurable backoff |
| Operational configuration | Simpler | More options |
| Suitable cases | Stable load, fixed concurrency | Variable load, need for scaling or an external transaction |

If you have no special reason to use SMLC, DMLC is usually the practical choice for production applications because of its richer transaction and recovery capabilities. Even so, the container cannot replace the application's design for idempotency, dead-letter handling, and resource limits.

## 5. Choosing a container by transaction requirements

Before choosing a container, you need to determine which operations the transaction must protect: only receiving the message, receiving and sending a reply, or the message together with a database update.

### 5.1. No transaction

If the listener only performs work that can be repeated and accepts the default delivery risks, you can use the default acknowledgement mode. However, `AUTO_ACKNOWLEDGE` does not guarantee redelivery when the listener fails. Spring warns that a message can be lost if the listener throws an exception or the container stops during processing.

With DMLC, the default acknowledgement can be performed before the listener runs; an exception from the listener therefore does not cause the message to roll back automatically. Do not use throwing an exception as a retry mechanism if the container has not been configured with a transaction.

### 5.2. Local JMS transaction

Set `sessionTransacted=true` on the listener container so that each listener invocation runs in a local JMS transaction:

1. The container receives the message in a transacted session.
2. The listener performs the processing and the JMS operations belonging to that session.
3. If the listener completes normally, the transaction is committed.
4. If the listener throws an exception, the transaction rolls back; the broker can redeliver the message.

This is usually the appropriate choice when you need reliable delivery between the broker and the listener. If you use `SessionAwareMessageListener` to send a reply using the very session that received the message, the reply-sending operation can be in the same JMS transaction.

Example of DMLC with a local JMS transaction:

```java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
class JmsListenerConfiguration {

    @Bean
    DefaultJmsListenerContainerFactory ordersListenerFactory(
            ConnectionFactory connectionFactory) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setSessionTransacted(true);
        factory.setConcurrency("2-8");
        factory.setRecoveryInterval(5_000L);
        return factory;
    }
}
```

`DefaultJmsListenerContainerFactory` creates a DMLC for the endpoints that use this factory. The configuration sets a minimum of two consumers, allows growing to at most eight consumers, uses a local JMS transaction, and attempts recovery at a five-second interval.

Attach the factory to the listener:

```java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
class OrderListener {
    private final OrderService orderService;

    OrderListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @JmsListener(
            destination = "orders.incoming",
            containerFactory = "ordersListenerFactory"
    )
    public void receive(OrderCreated event) {
        orderService.process(event);
    }
}
```

The application needs to enable annotation listeners with `@EnableJms` if the infrastructure is not auto-configured by Spring Boot. `OrderCreated` is the message DTO and `OrderService` contains the business logic. If processing fails, the exception needs to propagate out of the listener so the container knows the transaction must roll back.

### 5.3. Transactions with a database

A local JMS transaction only manages the JMS operations in the session. It does not automatically include a JDBC/JPA transaction. For example, if the listener writes to the database successfully but the broker has an error before commit/acknowledge, the message can be redelivered and the database may receive the same effect again.

There are two common approaches:

- **JMS local transaction + idempotency/inbox:** the JMS transaction manages receiving the message; the database records the result and the message ID/business key in a way that prevents duplicates. This approach is usually easier to operate and less costly than XA.
- **JTA/XA transaction:** combines JMS receiving and the database update in one distributed transaction if both the JMS provider and the database support XA and are registered correctly with the transaction coordinator.

Do not assume that `@Transactional` on the listener method automatically merges the database transaction into the container's JMS transaction. You need to determine which transaction manager the container is using and which resources participate in that transaction.

### 5.4. Distributed JTA/XA transactions

When the business requirement needs an atomic commit or rollback between JMS and the database, DMLC can participate in an external transaction through `JtaTransactionManager`. The JMS `ConnectionFactory` must support XA; the database also needs an XA resource if the database operation must take part in the same transaction.

Example configuration of a factory participating in JTA:

```java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.transaction.jta.JtaTransactionManager;

@Configuration
class XaJmsListenerConfiguration {

    @Bean
    DefaultJmsListenerContainerFactory xaOrdersListenerFactory(
            ConnectionFactory xaConnectionFactory,
            JtaTransactionManager transactionManager) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(xaConnectionFactory);
        factory.setTransactionManager(transactionManager);
        factory.setConcurrency("2-8");
        return factory;
    }
}
```

This is the Spring-side configuration. For XA to actually work, `xaConnectionFactory` must be an XA factory supplied by the provider and configured in the transaction coordinator; the datasource must also be XA if the database needs to participate. Merely setting `JtaTransactionManager` in Spring while using an ordinary connection factory will not produce a distributed transaction.

XA increases complexity, the cost of transaction logging, and the operational requirement of recovering the coordinator. If the system accepts controlled duplicates, a local transaction combined with inbox/outbox and idempotency is usually a lighter option.

## 6. Choosing a container by scalability

Concurrency is the number of listener consumers that can process messages at the same time. With DMLC, `concurrentConsumers` is the base level and `maxConcurrentConsumers` is the upper bound. You can declare it with a string such as `2-8`: the container maintains at least two consumers and can grow to eight when load increases.

Increasing consumers usually helps the queue process more messages in parallel, but does not guarantee that throughput grows linearly. Each consumer may need a session, a transaction, a thread, and a connection to the database or a downstream service. If you increase concurrency beyond the capacity of those resources, latency and timeout errors can increase.

### Choosing concurrency

Things to consider:

- The average processing time and the variability of the handler.
- The CPU, heap, and number of threads that can be allocated to the listener.
- The database connection pool size and the concurrency limits of downstream APIs.
- The parallel-processing capacity of the broker and destination.
- Transaction duration; the longer the transaction, the longer it holds resources.
- The number of backlogged messages, the publish rate, and the target processing latency.

Start with a small concurrency, measure throughput/latency, and increase gradually. Set the upper limit based on the capacity of the database and downstream; do not rely only on the number of CPU cores.

### Queue and Topic have different concurrency behavior

**Queue:** multiple consumers usually compete to receive messages; each message is delivered to one consumer in the group according to the broker's policy. Increasing consumers can increase throughput, but the completion order of processing is no longer guaranteed. A message that takes a long time to process can complete after a message that arrived later.

**Topic:** each subscription normally receives a copy of the publication. Adding many independent consumers on the same topic can cause each consumer to receive the same message, creating repeated processing in the application. Only increase concurrency for a topic when the provider supports shared subscription and the corresponding Spring/JMS configuration has been verified.

If the business requires strict ordering, you usually need a sequential consumer or partitioning by a business key so that related messages go through the same processing thread. If you only need ordering per aggregate, you can partition by `orderId` instead of locking the whole queue.

## 7. Recovery, cache, and resource limits

DMLC has a mechanism to retry connecting when the broker is temporarily unavailable. By default, recovery is retried at a fixed interval; you can configure `recoveryInterval` or a `BackOff` to space out retries. When the broker recovers, the container re-creates the message-receiving resources according to its lifecycle.

The container also manages the connection/session/consumer cache. When there is no caching, the container may have to create connections/sessions frequently; when using an external transaction manager, obtaining fresh resources may be necessary for the resources to take part correctly in the JTA transaction. Only change the cache level after understanding the provider, the transaction manager, and the lifecycle requirements.

Do not increase concurrency without limit. Set limits and monitor the actual number of consumers, thread pool, sessions, queue depth, the age of the oldest message, and the rollback rate.

## 8. Acknowledgement, redelivery, and dead-letter

With both SMLC and DMLC, the default `AUTO_ACKNOWLEDGE` does not provide a reliable guarantee for redelivery when the listener fails. When you need reliable message processing, Spring recommends using a transacted session or an appropriate external transaction manager.

When the listener throws an exception within a local JMS transaction, the container rolls back. The broker can redeliver the message; the number of redeliveries and the policy for moving to dead-letter depend on the provider. A malicious or wrongly-schemed message can cause a retry loop and clog the queue.

There should be a policy for:

1. Bounded retry for transient errors such as database/network timeouts.
2. A delay or backoff between retries if the broker/provider supports it.
3. A dead-letter queue or quarantine after a defined number of failures.
4. Recording the message ID, correlation ID, destination, exception, and delivery count.
5. A process for investigating and replaying messages after fixing the cause.

The listener must be idempotent because duplicates can appear after a rollback, redelivery, or an incident during commit. For database updates, you can use an inbox table/unique key to record messages that have been processed within the same business transaction.

## 9. Examples of choosing by scenario

| Scenario | Suggested choice | Reason |
|---|---|---|
| A queue with few messages, stable load, needing simple configuration | SMLC + local transaction | Fixed consumers, no need for dynamic scaling/JTA |
| A queue whose load varies by hour | DMLC with `concurrency="2-12"` | Increase/decrease consumers with load within limits |
| A listener needing a JMS transaction and sending a reply on the same session | SMLC or DMLC with `sessionTransacted=true` | The JMS operations in the session are in the same local transaction |
| A listener that updates the DB and needs an atomic commit with JMS | DMLC + JTA/XA | Supports an external transaction manager when all XA resources are configured correctly |
| A topic with many independent subscribers | One consumer per subscription normally | Avoids creating multiple subscriptions that receive the same publication unintentionally |
| A queue needing strict processing order | One consumer or partition/serialize by key | Avoids multiple consumers completing out of order |
| A broker that may restart and needs automatic recovery | DMLC | Has integrated recovery/backoff |

## 10. Common mistakes when choosing a container

- **Choosing SMLC and then expecting it to scale itself:** SMLC creates a fixed number of consumers at startup.
- **Using SMLC when JTA is needed:** this container does not participate in externally managed transactions.
- **Using DMLC but keeping AUTO_ACKNOWLEDGE:** a listener throwing an exception is not enough to guarantee the message is redelivered.
- **Enabling many consumers for an ordinary topic:** can cause multiple consumers to receive the same publication.
- **Increasing concurrency beyond the database pool:** listeners wait for connections, transactions drag on, and the queue backlog grows.
- **Using XA only to avoid writing idempotency:** XA increases complexity and operational cost; weigh it against outbox/inbox.
- **Assuming a local JMS transaction includes the database:** the two resources can commit independently.
- **Assuming rollback with endless retry is always safe:** a poison message can repeat and clog the queue.
- **Not checking ordering when scaling:** send order does not guarantee processing completion order across multiple consumers.
- **Not measuring recovery and cache:** the container may create too many resources or recover slowly when the broker returns.

## 11. Testing and operations

Before deploying to production, you should test the following scenarios:

- Successful listener: the message is committed/acknowledged exactly once according to the configuration.
- Listener throws an exception: the local transaction rolls back and the broker redelivers according to the policy.
- Transient database failure: the retry does not create duplicate side effects.
- Broker restart or network loss: DMLC recovers and the consumers work again.
- A sudden load spike: concurrency increases without exhausting the database pool or thread pool.
- Load decrease: the number of consumers returns to the base level if dynamic scaling is enabled.
- Multiple consumers on a queue: check ordering, duplicates, and load distribution.
- Topic subscription: confirm each subscriber receives the expected number of messages.
- Poison message: bounded retry and then move to DLQ/quarantine.
- Shutdown: the container stops in an orderly way and uncommitted messages are safely reprocessed.

Monitor at least queue depth, the age of the oldest message, publish/consume rate, listener duration, the number of active consumers, transaction rollbacks, redeliveries, DLQ depth, reconnect count, and the connection pool status.

## 12. Decision process

1. Determine whether the destination is a queue or a topic and the ordering requirements.
2. Determine which transaction needs protection: JMS alone, JMS with a reply, or JMS with a database.
3. If you need JTA/XA or dynamic scaling, choose DMLC.
4. If the load is fixed and you only need a local JMS transaction in a suitable environment, consider SMLC.
5. For reliable delivery requirements, enable `sessionTransacted=true` or configure an appropriate transaction manager; do not rely on AUTO_ACKNOWLEDGE.
6. Set the min/max concurrency according to the capacity of the broker, database, and downstream.
7. Design retry, redelivery, DLQ, and idempotency.
8. Test listener failures, broker restart, duplicates, ordering, and peak load.
9. Monitor metrics and adjust based on production data.

## 13. Conclusion

`SimpleMessageListenerContainer` suits a receive flow with fixed concurrency and a local JMS transaction. `DefaultMessageListenerContainer` suits most applications that need dynamic scaling, recovery, or participation in externally managed transactions such as JTA/XA.

With both containers, use a transacted session when you need reliable redelivery. Choose concurrency according to the real limits of the broker, database, and downstream; consider the differences between queue/topic and the processing order. If the transaction includes a database, decide clearly between a local JMS transaction combined with idempotency/inbox-outbox and JTA/XA, and then test rollback, redelivery, recovery, and concurrent load.

## References

- [Spring Framework Reference — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html)
- [Spring Framework Reference — Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html)
- [Spring Framework Reference — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html)