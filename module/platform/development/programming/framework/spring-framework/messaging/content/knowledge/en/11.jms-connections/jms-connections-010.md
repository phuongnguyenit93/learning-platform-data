# Closing Resources, Resetting Connections, and Handling Broker Disconnects

> Objective: properly manage the lifecycle of JMS `Connection`, `Session`, `Producer`, and `Consumer`; close resources safely on shutdown; detect broker connection failures; recover send/receive flows with backoff; and properly handle cases where messages may already have been sent or acknowledged before the connection dropped.

## 1. Why Is the JMS Resource Lifecycle Important?

A JMS application works through multiple resource layers: `ConnectionFactory` creates `Connection`; connection creates `Session`; session creates `MessageProducer` and `MessageConsumer`. These resources typically hold sockets, session state, consumer registrations, and transaction state with the broker.

If resources are not closed on time, the application can leak connections, sessions, consumers, or threads; the broker may keep subscriptions alive; connection pools become exhausted; and deployments/shutdowns turn slow or unstable. Conversely, closing a resource still in use by another component can disrupt in-flight message processing.

Clearly establish **who owns each resource and who is responsible for closing it**:

| Resource | Role | Typical owner |
|---|---|---|
| `ConnectionFactory` | Creates connections to the provider | Application context or infrastructure configuration |
| `Connection` | Client connection to the provider | Component that created the connection, or Spring connection factory/container |
| `Session` | Context for message creation and transactions | Managing thread/consumer or listener container |
| `MessageProducer` | Sends to a destination | `Session` or sending component |
| `MessageConsumer` | Receives from a destination | `Session` or listener container |

In plain JMS code, the component that creates a resource generally must close it. In Spring JMS, `JmsTemplate` and listener containers manage the resources they create; do not manually close connections/sessions managed by Spring.

## 2. Resource Closing Order

When an application creates resources directly using the JMS API, close them in reverse creation order:

1. Stop receiving more messages or stop producers from submitting new work.
2. Close `MessageConsumer` and `MessageProducer`.
3. Close `Session`.
4. Close `Connection`.

Closing a connection also closes its child sessions and objects under the JMS contract. However, closing child resources explicitly first clarifies ownership, avoids holding consumers/producers longer than needed, and enables controlled error handling during close.

`Connection.stop()` only temporarily pauses message delivery to consumers; it does not release the connection. `close()` terminates the connection and releases child resources. If you want to resume after a pause, you can use `stop()` followed by `start()` per lifecycle; never use `stop()` as a substitute for `close()` on shutdown.

### Manual resource management example

```java
import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSException;
import jakarta.jms.MessageConsumer;
import jakarta.jms.Queue;
import jakarta.jms.Session;

void receiveOne(ConnectionFactory connectionFactory) throws JMSException {
    Connection connection = connectionFactory.createConnection();
    try {
        Session session = connection.createSession(
                false, Session.AUTO_ACKNOWLEDGE);
        try {
            Queue queue = session.createQueue("orders.incoming");
            MessageConsumer consumer = session.createConsumer(queue);
            try {
                connection.start();
                consumer.receive(2_000);
            } finally {
                consumer.close();
            }
        } finally {
            // Close the session even if receive or consumer.close fails.
            // Production code should preserve the original exception if close also fails.
            session.close();
        }
    } finally {
        connection.close();
    }
}
```

This example illustrates resource closing order. Production code should use helpers or try-with-resources if the JMS API version in use supports `AutoCloseable`, while ensuring exceptions thrown during closing do not mask the primary exception. The example receives one message and exits; long-running consumers should be managed by a listener container rather than opening/closing connections per receive.

Never share a single `Session`, `MessageProducer`, or `MessageConsumer` across multiple concurrent threads. If parallel processing is needed, create multiple sessions/consumers via a container or suitable pooling mechanism.

## 3. Orderly Shutdown

When an application stops, the goal is to stop accepting new work, let in-flight work finish within an allowed grace period, and then release resources.

A typical shutdown sequence:

1. Mark the application as no longer accepting new work.
2. Stop listener containers or call `Connection.stop()` to pause dispatching new messages.
3. Wait for running handlers to complete within the configured graceful shutdown window.
4. Commit or roll back open transactions based on processing outcomes.
5. Close application-owned consumers/producers, sessions, and connections.
6. Shut down executors, schedulers, and dependent components once no tasks remain using them.

If the process is killed abruptly or the shutdown timeout expires, the broker may redeliver unacknowledged messages. Thus, orderly shutdown reduces disruption but does not replace idempotency and redelivery handling.

In Spring, listener containers have lifecycles managed by the application context. Let Spring start/stop containers according to lifecycle; do not call `close()` on connections or sessions owned by a container. You can configure shutdown wait time and concurrency according to deployment requirements.

## 4. Detecting Broker Disconnects

A broker can lose connectivity due to restarts, network partitions, DNS or TLS issues, expired credentials, connection limits, failovers, timeouts, or infrastructure incidents. Failures can surface at several points:

- When creating a connection or session.
- When sending a message via `send()`.
- While a consumer is waiting on `receive()`.
- Inside a `MessageListener` callback or during acknowledge/commit.
- While a connection is idle, when the provider detects a dead socket.

JMS typically represents errors with `JMSException`. The exception may expose `getErrorCode()` and `getLinkedException()`; providers may also attach root causes in product-specific ways. Preserve the cause chain and provider details for investigation.

### ExceptionListener

JMS `Connection` supports registering an `ExceptionListener`. The provider invokes the listener when it detects a serious connection-related error:

```java
connection.setExceptionListener(exception -> {
    Throwable linked = exception.getLinkedException();
    System.err.println("JMS connection problem: " + exception.getMessage());
    if (linked != null) {
        linked.printStackTrace(System.err);
    }
});
```

This snippet only illustrates the callback. In real applications, emit structured logs and signal a recovery mechanism. Do not perform blocking reconnects or run a lengthy recovery procedure directly on the provider's callback thread; the callback should be fast and safe when multiple errors occur closely together.

`ExceptionListener` is not a catch-all for business errors. A payload parsing error or service exception may not be a connection failure and should go through listener/container error handling. Furthermore, not every provider detects network failures immediately; heartbeats and timeouts depend on provider configuration.

## 5. What Is Uncertain When a Connection Drops?

A tricky aspect of messaging is that a client can lose connectivity right while sending or acknowledging a message. At that point, the client sometimes cannot tell whether the broker already executed the operation.

| Moment of disconnect | What the client knows | Risk to handle |
|---|---|---|
| Before the broker receives the send | The send may not have reached the broker | May need to resend |
| Broker received it, but the send response was lost | The client does not know if the send succeeded | Resending may create duplicates |
| Consumer processed it, but acknowledgement did not reach the broker | The broker may treat the message as unacknowledged | The message may be redelivered |
| Broker acknowledged, but the consumer has not recorded local results | The client lacks application-side proof of completion | Needs reconciliation or idempotency |

Never assume a timeout or exception guarantees the message was definitely not sent. When the outcome is ambiguous, retries must rely on stable message IDs/business keys, and consumers must handle duplicates safely.

## 6. Connection Recovery in Plain JMS Applications

If an application manages long-lived connections itself, recovery needs to recreate the entire group of resources tied to the failed connection. A session, producer, or consumer belonging to a broken connection must not be reused as if still valid.

General recovery procedure:

1. Mark the current connection unavailable and stop new sends/receives on that resource group.
2. Record the error, destination, timestamp, attempt count, and in-flight messages.
3. Close old consumers, producers, sessions, and the connection if the provider still permits; drop references to them if closing fails.
4. Wait using bounded backoff with jitter so many instances do not reconnect simultaneously.
5. Create a new connection from `ConnectionFactory`.
6. Create new sessions, producers/consumers, and listeners; re-register `ExceptionListener` if needed.
7. Call `Connection.start()` once consumers are ready to receive messages.
8. Mark the connection healthy and resume processing; continue monitoring redelivery and duplicates.

Backoff typically grows progressively, such as 1 second, 2 seconds, 4 seconds, 8 seconds, capped at a maximum. Add random jitter so multiple instances do not reconnect at the exact same moment. Cap attempts or transition to a degraded/alert state according to operational requirements.

Do not open new connections in a tight loop while the broker is down. That can cause a connection storm, overload the broker, and slow down recovery.

### Recovery loop pseudocode

```text
while application is running:
    try:
        create connection
        create session and producer/consumer
        start connection when receiving
        process messages
    catch connection failure:
        mark resources unavailable
        close/discard failed resources
        wait using bounded exponential backoff + jitter
        continue
    finally:
        close resources owned by this loop
```

This is pseudocode describing the strategy, not runnable Java code. In Spring applications, prefer the recovery built into listener containers or connection factories rather than writing thread- and session-management loops yourself.

## 7. Spring CachingConnectionFactory and resetConnection()

Spring JMS provides `CachingConnectionFactory`, a `ConnectionFactory` wrapper that can share a connection and cache sessions, producers, and consumers if the corresponding option is enabled. It reduces repeated resource creation overhead, though it must be configured to fit the application model.

Key points to understand:

- `setSessionCacheSize(...)` sets the maximum number of cached sessions per connection.
- Producer caching can reduce repeated producer creation.
- Consumer caching requires careful consideration; not all listener container setups fit external consumer caching.
- `resetConnection()` forces the shared connection and related cached resources to reset so the next usage creates fresh resources.
- Automatic reconnection when the provider emits an exception depends on `ExceptionListener`, the `reconnectOnException` setting, and provider support.

Wrapper configuration example:

```java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.connection.CachingConnectionFactory;

@Configuration
class JmsConnectionConfiguration {
    @Bean
    CachingConnectionFactory cachingConnectionFactory(
            ConnectionFactory targetConnectionFactory) {
        CachingConnectionFactory factory =
                new CachingConnectionFactory(targetConnectionFactory);
        factory.setSessionCacheSize(10);
        factory.setCacheProducers(true);
        factory.setCacheConsumers(false);
        factory.setReconnectOnException(true);
        return factory;
    }
}
```

The example illustrates a common caching strategy, not the optimal setup for every provider. Do not wrap an additional `CachingConnectionFactory` if the application already uses a connection pool or another caching wrapper without understanding how they interact. Measure cache size against actual concurrency and session counts.

When a forced reset is needed after an outage detected by a monitoring layer, you can call `resetConnection()` on an application-owned wrapper. Do not call reset arbitrarily while other threads are actively using the connection; coordinate with producer/consumer lifecycles.

## 8. Self-Recovering Spring Listener Containers

For background consumers, `DefaultMessageListenerContainer` manages connections, sessions, consumers, and listener threads. The container has built-in recovery when the broker or connection encounters an error; it can attempt to re-establish resources according to the configured recovery interval or `BackOff`.

Factory configuration example:

```java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
@EnableJms
class JmsListenerConfiguration {
    @Bean
    DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setConcurrency("2-8");
        factory.setSessionTransacted(true);
        factory.setRecoveryInterval(5_000L);
        return factory;
    }
}
```

In this example, the container uses 2 to 8 consumers, locally transacted sessions, and attempts recovery at 5-second intervals. You can configure a `BackOff` for an escalating retry schedule. Actual values should suit the broker, expected outage duration, and application load.

A listener can use this factory:

```java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
class OrderListener {
    @JmsListener(
            destination = "orders.incoming",
            containerFactory = "jmsListenerContainerFactory"
    )
    public void receive(String json) {
        processOrder(json);
    }
}
```

When a listener throws an exception in a transacted session, the container rolls back the session per configuration and the provider may redeliver the message. Container recovery handles connection/listener infrastructure; it does not fix malformed payloads, guarantee idempotent business operations, or replace dead-letter policies.

## 9. JmsTemplate and Send Failures

`JmsTemplate` manages acquiring and releasing connections/sessions/producers for each send or synchronous receive operation. When backed by `CachingConnectionFactory` or a pool, resources can be reused underneath.

```java
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;

@Service
class OrderPublisher {
    private final JmsTemplate jmsTemplate;

    OrderPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    void publish(String json) {
        jmsTemplate.convertAndSend("orders.incoming", json);
    }
}
```

If the broker is unavailable, the send operation may throw `JmsException` (Spring wraps JMS errors as runtime exceptions). Callers must distinguish transient failures from configuration or data errors, apply bounded retries when safe, and record state when the send outcome is ambiguous.

Do not create a new `JmsTemplate` or a new connection on every retry attempt. Reuse the configured bean, let the connection factory manage resources, and let the retry policy decide when to retry.

## 10. Retries, Redelivery, and Idempotency

When the broker disconnects, unacknowledged messages may be redelivered after the consumer reconnects. When a producer does not receive a send acknowledgment, the producer may retry even though the broker already received the message. Therefore, the system must assume duplicates can occur.

Key safeguards:

- Use a stable message ID or business key to identify messages.
- Design idempotent handlers: processing the same command/event multiple times does not produce duplicate side effects.
- Record processed status and perform business updates within the same appropriate transaction.
- Distinguish retrying transient connection errors from schema, validation, or business rejection errors that cannot self-heal.
- Use backoff, retry limits, and a dead-letter queue/quarantine for unprocessable messages.
- Monitor the redelivery flag, delivery count, or equivalent metadata supplied by the provider.

Never retry infinitely inside a listener thread. If a message fails permanently, retrying just clogs the queue and wastes resources. Route the message to a DLQ after a defined threshold and provide an investigation/replay workflow.

## 11. Transactions During Broker Disconnects

If a session uses local transactions, `commit()` confirms the JMS operations in the transaction and `rollback()` cancels uncommitted operations according to provider semantics. If the connection drops right at commit time, the client may not know whether the broker committed or not. This is an ambiguous outcome requiring deduplication or reconciliation.

A JMS transaction does not automatically encompass database transactions. If a listener writes to a database and loses connection before acknowledgement, the broker may redeliver the message and the database could receive the same effect again. You can use an inbox/deduplication table, unique business keys, or XA/JTA when all resources support it and the cost is acceptable.

Do not catch an exception and return normally if processing is incomplete; the container may treat the listener as successful and acknowledge the message. Let exceptions and transaction semantics accurately reflect processing outcomes.

## 12. Monitoring Connection and Broker Health

Monitor both connection status and backlog health:

- Active connections/sessions and reconnect counts.
- Time from error detection until consumers resume working.
- Failed message sends, receive timeouts, and listener exceptions.
- Queue depth, oldest message age, and publish/consume rates.
- Redelivery counts, rollbacks, retries, and DLQ depth.
- Active consumer count relative to configured concurrency.
- CPU, thread pools, heap, and connection/session wait times.

Logs should include destination, message ID, correlation ID, provider error code, and root cause. Do not log passwords, tokens, or full sensitive payloads. Base alerts on outage duration, reconnect counts, and growing backlogs rather than firing an alert on every normal retry.

## 13. Common Pitfalls

- **Failing to close self-created consumers/sessions/connections:** leaks resources and leaves subscriptions open.
- **Closing a shared connection managed by Spring:** disrupts other components; close only resources owned by the component.
- **Closing parent before child without a plan:** makes close errors and lifecycle hard to track; close consumers/producers, then sessions, then connection.
- **Calling `stop()` and assuming the connection is released:** `stop()` only pauses dispatch; `close()` releases resources.
- **Opening a new connection on every send:** increases overhead and can exhaust broker connection limits.
- **Reusing Session or Consumer after a broken connection:** child resources may already be invalid; recreate the resource group.
- **Reconnecting continuously without backoff:** causes a connection storm while the broker is recovering.
- **Assuming a send timeout means the broker never received the message:** the outcome may be ambiguous; resending can create duplicates.
- **Not handling redelivery:** listeners may execute side effects multiple times after rollbacks or lost acknowledgements.
- **Using retries to handle bad payloads:** permanent data errors need rejection, fixing, or DLQ rather than infinite retries.
- **Managing custom recovery alongside a listener container:** the two mechanisms can fight over creating/closing sessions and consumers.
- **Missing graceful shutdown:** in-flight messages may be interrupted mid-transaction or require redelivery.

## 14. Deployment and Testing Procedure

1. Identify which resources are created by the application and which are owned by Spring/the container.
2. Write clear lifecycle handling: start, stop, close; close resources in order: consumer/producer → session → connection.
3. For plain JMS code, test both happy paths and error paths when creating, sending, receiving, or closing resources.
4. Configure `ExceptionListener` if the application manages connections itself and needs provider error signals.
5. For Spring listeners, configure concurrency, transactions, and recovery/backoff on the listener container.
6. Choose appropriate caching or pooling; avoid overlapping caches/pools without understanding ownership.
7. Simulate broker restarts, network interruptions, send timeouts, listener exceptions, and failures during commit/acknowledge.
8. Verify connections/sessions/consumers are recreated and unacknowledged messages are handled per redelivery policy.
9. Test duplicates to prove handlers are idempotent and side effects do not repeat.
10. Verify graceful shutdown, metrics, logs, and DLQ behavior in an integration environment.

## 15. Conclusion

In plain JMS, the component owning resources must close consumers/producers, sessions, and connections in the proper order; a connection can be paused with `stop()` and terminated with `close()`. When a broker disconnects, sessions and child objects may become unusable, so recovery must recreate the resource group with backoff and status tracking.

In Spring JMS, prefer letting `JmsTemplate`, `CachingConnectionFactory`, and listener containers manage lifecycle/recovery per configuration. Even though the framework can reconnect automatically, send or acknowledge outcomes at the moment of a network drop may remain ambiguous and messages may be redelivered. Idempotent consumers, bounded retries, dead-lettering, and graceful shutdown are essential parts of safe system recovery.