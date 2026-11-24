# Recovering Connections with recoveryInterval or BackOff in Spring JMS

## 1. Why does a listener need a recovery mechanism?

A JMS listener usually runs for a long time. The listener container holds resources such as the Connection, Session, and MessageConsumer to receive messages continuously. When the broker restarts, the network is interrupted, or the provider temporarily cannot create a consumer, these resources can become invalid.

The application needs a mechanism to try to re-establish the connection after an infrastructure error occurs. Spring JMS provides a recovery mechanism in `DefaultMessageListenerContainer`. The container can re-create the connection and the message-receiving resources after the listener setup fails.

Two main options to control the wait between attempts:

- **recoveryInterval:** a fixed wait, measured in milliseconds.
- **BackOff:** a strategy that computes the wait for each attempt, for example fixed delay or exponential backoff.

By default, `DefaultMessageListenerContainer` attempts recovery at a 5-second interval. You can keep the default, replace it with a different fixed interval, or configure a BackOff depending on the broker's characteristics and operational requirements.

After the lesson, you should be able to:

- Explain why the listener container must recover the connection and consumer.
- Distinguish recoveryInterval from BackOff.
- Configure recovery for a listener declared with @JmsListener.
- Use FixedBackOff or ExponentialBackOff to control the retry delay.
- Understand the meaning of BackOffExecution.STOP.
- Distinguish connection recovery from message-processing retry.
- Observe the recovering state and test a broker restart.

## 2. How does DefaultMessageListenerContainer recover on its own?

`DefaultMessageListenerContainer` is Spring JMS's listener container, commonly used for message-driven POJOs and `@JmsListener` endpoints. The container uses the JMS client API to create sessions/consumers and receive messages in tasks managed by an executor.

When listener setup fails, for example when it cannot create the connection or consumer, the container can:

1. Record the setup error.
2. Wait according to the configured recovery strategy.
3. Try to re-establish the necessary connection or destination resource.
4. Re-create the session and consumer.
5. Continue receiving messages once the broker and resources are ready.

General flow:

~~~text
Listener container is receiving messages
              |
              v
Connection / consumer hits an error
              |
              v
Record listener setup failure
              |
              v
Wait for recoveryInterval or BackOff
              |
              v
Try to re-create JMS resources
          /           \
      Failed          Succeeded
         |                |
         v                v
    Wait for next     Continue receiving
~~~

This mechanism is useful when the broker is only temporarily unavailable. For example, a broker restart during a deployment or a short network interruption. The container can re-establish the message-receiving resources by itself when the infrastructure is working again.

The container's recovery cannot fix a misconfiguration. If the username/password is wrong, the destination does not exist, or the account does not have permission to consume, continued retries will keep failing until the configuration or permissions are fixed.

## 3. recoveryInterval: a fixed wait

### 3.1 Meaning and default value

`DefaultMessageListenerContainer.setRecoveryInterval(long)` accepts the wait between recovery attempts, in milliseconds.

The default value is:

~~~text
5000 milliseconds = 5 seconds
~~~

If you want the container to wait 10 seconds between attempts, configure:

~~~java
container.setRecoveryInterval(10_000L);
~~~

`recoveryInterval` is a simple choice when you want a predictable retry cycle. The wait does not grow with the number of failures.

This method is a convenient way to configure a `FixedBackOff` with the corresponding wait. In an ordinary configuration, the container keeps attempting recovery while it is still running.

### 3.2 Configuring DefaultMessageListenerContainer directly

Example of creating the container with Java configuration:

~~~java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.Destination;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.listener.DefaultMessageListenerContainer;

@Configuration
public class ManualJmsContainerConfiguration {

    @Bean
    public DefaultMessageListenerContainer ordersContainer(
            ConnectionFactory connectionFactory,
            Destination ordersQueue,
            OrderMessageListener listener) {

        DefaultMessageListenerContainer container =
                new DefaultMessageListenerContainer();

        container.setConnectionFactory(connectionFactory);
        container.setDestination(ordersQueue);
        container.setMessageListener(listener);
        container.setRecoveryInterval(10_000L);

        return container;
    }
}
~~~

`ConnectionFactory`, `Destination`, and `OrderMessageListener` are beans supplied by the application or the JMS provider. The example illustrates configuring a container manually; the Spring application context manages the bean's lifecycle.

### 3.3 When should you use recoveryInterval?

Use a fixed interval when:

- The broker's expected restart time is short.
- You want the listener to retry regularly and predictably.
- The system has only a few listeners or instances.
- You do not yet need to bound the recovery time with a complex strategy.

A wait that is too short can create many failed connection attempts, dense logs, and additional load on a broker that is already having problems. A wait that is too long makes the consumer recover slowly after the broker is already ready.

Choose the value based on the broker's typical recovery time, the number of instances connecting at the same time, and the level of message delay the system accepts.

## 4. BackOff: controlling the wait per attempt

### 4.1 BackOff and BackOffExecution

Spring Core provides the abstraction `org.springframework.util.backoff.BackOff` to describe how to compute the wait between attempts.

Two main components:

- `BackOff`: a strategy that creates a new backoff execution.
- `BackOffExecution`: tracks the sequence of waits for one recovery; each call to `nextBackOff()` returns the next wait time.

If `nextBackOff()` returns `BackOffExecution.STOP`, the listener container makes no further recovery attempts under that strategy.

`BackOff` is a general Spring Core abstraction. It is not specific to JMS and is also not a Spring Retry retry policy. `DefaultMessageListenerContainer` uses this abstraction to compute the wait time for recovery.

### 4.2 FixedBackOff

`FixedBackOff` keeps the wait between attempts constant. It suits cases where you want to use the BackOff abstraction but still need a fixed schedule.

Example:

~~~java
import org.springframework.util.backoff.FixedBackOff;

FixedBackOff backOff = new FixedBackOff(
        5_000L,
        FixedBackOff.UNLIMITED_ATTEMPTS
);
~~~

The code creates a strategy that waits 5 seconds between attempts with an unlimited number of attempts. You can use a finite number of attempts when you want automatic recovery to stop after a certain number of attempts.

The practical difference between `setRecoveryInterval(5_000L)` and `setBackOff(new FixedBackOff(...))` lies in the level of control. recoveryInterval is a convenient API for a fixed delay; BackOff lets you choose the algorithm and set clear retry limits.

### 4.3 ExponentialBackOff

`ExponentialBackOff` increases the wait after each attempt. The wait is multiplied by the multiplier until it reaches the max interval.

For example, if it starts at 1 second, the multiplier is 2, and the cap is 30 seconds, the illustrative wait schedule is:

| Next recovery attempt | Wait |
|---|---:|
| 1 | 1 second |
| 2 | 2 seconds |
| 3 | 4 seconds |
| 4 | 8 seconds |
| 5 | 16 seconds |
| Subsequent attempts | At most 30 seconds |

Gradual increase helps reduce the frequency of connection attempts when the broker is down for a long time. When the broker recovers, the listener still retries according to the computed schedule.

Spring Framework's ExponentialBackOff has these main properties:

- `initialInterval`: the initial wait.
- `multiplier`: the factor by which the wait grows.
- `maxInterval`: the maximum wait.
- `maxElapsedTime`: the maximum accumulated total time before the retry sequence stops.
- `maxAttempts`: the maximum number of attempts; this API has been available since Spring Framework 6.1.

If no elapsed time or attempts limit is configured, ExponentialBackOff by default can continue for a very long time. For production recovery, decide clearly whether you need unlimited retry or need to stop to raise an alarm and intervene.

## 5. Configuring BackOff for @JmsListener

When using annotation-driven listeners, configure recovery on `DefaultJmsListenerContainerFactory`. The factory passes these settings into the `DefaultMessageListenerContainer` it creates.

### 5.1 Using recoveryInterval

~~~java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
@EnableJms
public class JmsListenerConfiguration {

    @Bean
    public DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setRecoveryInterval(10_000L);
        factory.setConcurrency("2-6");

        return factory;
    }
}
~~~

A listener using the factory:

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    @JmsListener(
            destination = "orders.queue",
            containerFactory = "jmsListenerContainerFactory")
    public void receive(String payload) {
        // Pass the payload to the business service.
    }
}
~~~

This factory configures a fixed recovery delay of 10 seconds. When the container cannot set up the listener because of a connection error, it retries at the configured wait.

### 5.2 Using ExponentialBackOff

When you need to increase the wait with the number of failures, you can configure `BackOff` directly:

~~~java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.util.backoff.ExponentialBackOff;

@Configuration
@EnableJms
public class JmsRecoveryConfiguration {

    @Bean
    public DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);

        ExponentialBackOff backOff =
                new ExponentialBackOff(1_000L, 2.0);

        backOff.setMaxInterval(30_000L);
        backOff.setMaxElapsedTime(5 * 60_000L);

        factory.setBackOff(backOff);

        return factory;
    }
}
~~~

In the example:

- The first wait is 1 second.
- Each subsequent wait grows by a factor of 2.
- The wait does not exceed 30 seconds.
- When the accumulated total time reaches the 5-minute limit, the BackOff can return `BackOffExecution.STOP` and the container stops further recovery attempts under this strategy.

This is a Spring bean configuration, not a standalone Java program. It needs a valid `ConnectionFactory` bean and the corresponding Spring JMS dependency.

### 5.3 Choose one strategy per factory

`setRecoveryInterval` is a convenient way to create a fixed backoff. `setBackOff` lets you use a custom strategy. If you configure both, the recovery interval setting may replace the configured BackOff; therefore choose one clear mechanism for each listener factory.

There is no need to set both just to “increase safety”. That makes it hard to determine the actual retry schedule.

## 6. BackOffExecution.STOP and recovery limits

### 6.1 The meaning of STOP

A finite BackOff can decide that it should not continue attempting after a threshold. When `BackOffExecution.nextBackOff()` returns `BackOffExecution.STOP`, `DefaultMessageListenerContainer` does not schedule any further recovery attempts under that execution.

For example, if you configure an elapsed time limit of 5 minutes, once the backoff sequence reaches the threshold, the container does not keep attempting indefinitely.

This is useful when:

- The configuration may be permanently wrong, such as the credentials or the destination.
- The organization wants to switch the state to an alert and intervene.
- You need to bound the period during which a listener is allowed to recover on its own.
- You want to avoid prolonged retries that no operator knows about.

### 6.2 STOP does not mean the broker has been deleted or messages have been lost

STOP only controls the listener container's scheduling of recovery. It does not delete the queue/topic, does not delete messages in the broker, and does not by itself change the ConnectionFactory configuration.

Once recovery has stopped, the system needs an observation mechanism and appropriate action, for example an alert, investigating the cause, and then restarting the container or application after fixing the configuration.

If you need the listener to recover on its own throughout a broker outage of unknown duration, use an unlimited retry strategy or the default fixed recovery interval. In exchange, you need monitoring to detect a prolonged outage.

## 7. Connection recovery differs from message-processing retry

This is a point that needs to be clearly distinguished.

### 7.1 Connection recovery and listener setup

The `recoveryInterval` and `BackOff` of `DefaultMessageListenerContainer` control the wait between attempts to re-establish listener resources after a setup or connection error.

Examples:

- The broker is temporarily unavailable.
- The connection is closed or lost.
- The consumer cannot be created.
- The destination resource needs to be re-resolved after a setup error.

The goal is to restore the container's ability to receive messages.

### 7.2 Business processing retry

If the listener has received a message but the business method throws an exception, this is a message-processing error. Whether the message is redelivered depends on the acknowledgement, the transaction, and the broker policy.

The related settings include:

- JMS session transaction, for example `setSessionTransacted(true)`.
- The transaction manager configured for the listener container.
- Acknowledge mode.
- The broker redelivery policy, delivery count, and dead-letter queue.
- The ErrorHandler or the application's error flow.

Example of a factory using a transaction for the listener:

~~~java
factory.setSessionTransacted(true);
~~~

When processing fails in a session transaction, the container can roll back according to the transaction semantics; the broker/provider can redeliver the message. You need to check the broker's actual redelivery policy.

### 7.3 Do not use recoveryInterval to retry business logic

If a message contains bad data that makes the listener fail continually, increasing recoveryInterval is not the right fix. The container may still be connected normally; the error lies in the payload or the business service.

Classify them:

| Symptom | Mechanism to consider |
|---|---|
| The broker is temporarily down or the connection is lost | recoveryInterval / BackOff |
| Cannot create a session or consumer | Listener container recovery |
| The listener method throws an exception | Transaction, acknowledgement, redelivery, error handling |
| Sending a message fails at the publisher | Retry on the producer side or the provider client |
| The message TTL expires | The broker's expiration policy |
| The broker moves a faulty message to the DLQ | Redelivery and dead-letter policy |

A system may need both connection recovery and message redelivery, but the two mechanisms solve two different kinds of errors.

## 8. Combining with the JMS provider's failover and reconnect

The JMS provider may offer a failover URI, reconnect, heartbeat, or its own connection retry. Spring DMLC has the container's recovery mechanism. These two layers can both take part when the broker loses its connection.

Example:

~~~text
Spring listener container
        |
        v
Provider ConnectionFactory
        |
        v
JMS client / failover transport
        |
        v
Broker cluster
~~~

You need to determine which layer is responsible for each situation:

- The provider can switch on its own to another broker node in the same cluster.
- The ConnectionFactory can try to reconnect according to the provider configuration.
- DefaultMessageListenerContainer can re-create the connection/session/consumer when the listener setup fails.
- Spring's BackOff controls the wait between the container's recovery attempts.

Do not assume provider failover and Spring recovery have the same retry schedule. If both retry too quickly, the system can create many failed connection attempts. If both wait too long, the overall recovery time increases.

Check the provider documentation and test a real broker restart or failover. Avoid creating multiple retry layers that have no limit or no metrics.

## 9. Choosing a recovery strategy by scenario

| Scenario | Suggested configuration |
|---|---|
| A short broker restart, few listeners | A fixed recoveryInterval |
| A prolonged broker outage, many attempts | ExponentialBackOff with maxInterval |
| Need to keep retrying until the broker is up | An unlimited FixedBackOff or recoveryInterval |
| Need to bound the automatic recovery time | A BackOff with maxElapsedTime or maxAttempts |
| The provider already has a failover cluster | Coordinate provider reconnect and Spring BackOff |
| Credential or destination errors may be configuration errors | Limit retries, raise alerts, and fix the configuration |

There is no single wait that suits every application. Consider:

- The time the broker typically takes to recover.
- The number of listeners and application instances.
- The load when all instances reconnect at the same time.
- The acceptable message delay.
- The maximum time the system retries on its own before intervention is needed.
- Whether the provider has its own retry or failover.

ExponentialBackOff by default adds no random jitter. If many instances start together and hit the same error, their retry schedules can be similar. For large systems, you can use a custom BackOff with jitter to reduce many clients reconnecting at the same moment.

## 10. Observing the recovery state

Automatic recovery is only useful when the operations team knows whether the listener is active or is trying to recover.

You should observe:

- The listener container's logs when the connection or consumer setup fails.
- The number of recoveries and the time since the most recent successful connection.
- The number of active consumers and the number of scheduled consumers.
- Queue depth or subscription backlog.
- The connection state and errors reported by the provider.
- The time the listener spends in the recovering state.
- The number of messages redelivered after the connection recovers.

`DefaultMessageListenerContainer` provides state such as `isRecovering()` and information about active consumers through the corresponding APIs. You can expose the information via JMX, actuator/custom metrics, or the application's monitoring system depending on the implementation.

Do not log passwords, tokens, or connection strings that contain secrets. When recording errors, keep enough information to identify the provider, destination, container, and cause without exposing credentials.

A useful alert can fire when a listener has been recovering longer than the operational threshold, or when there are no active consumers while the queue still has a backlog.

## 11. Testing recovery

You should test with a real JMS provider/broker or Testcontainers with an appropriate image.

The scenarios to verify:

1. The broker works normally and the listener receives messages.
2. The broker stops after the listener has been running.
3. The container records the error and retries at the configured recoveryInterval.
4. The broker restarts, and the container re-creates the connection/session/consumer.
5. The listener continues receiving new messages after recovery.
6. The BackOff increases the delay according to the configuration.
7. A finite BackOff returns STOP and no longer attempts recovery.
8. The container stops while waiting for recovery.
9. Provider failover and Spring recovery coordinate correctly.
10. A listener method that throws an exception is handled according to the separate transaction/redelivery policy.

For tests with wait times, use Awaitility, a latch, or a synchronization mechanism with a clear timeout instead of long arbitrary sleeps. Do not only check that the log has a line “reconnecting”; verify that the listener actually receives a message after the broker recovers.

You should separate the connection recovery test from the redelivery test. One test stops the broker to check that DMLC reconnects; another test deliberately makes the listener fail in a transaction to check whether the message is redelivered per the broker policy.

## 12. Common mistakes

- **Setting recoveryInterval too short:** creates many failed connection attempts and additional load on the broker.
- **Setting recoveryInterval too long:** the listener recovers slowly even though the broker is ready.
- **Thinking recoveryInterval is a message-processing timeout:** it only controls the wait between recovery attempts.
- **Using a finite BackOff without monitoring:** when it returns STOP, the container does not continue attempting under that execution.
- **Configuring both setRecoveryInterval and setBackOff at the same time:** the recovery interval setting may override the BackOff depending on the configuration order.
- **Confusing Spring BackOff with Spring Retry:** the two APIs and configuration purposes are different.
- **Assuming recovery can fix wrong credentials:** you need to fix the authentication or access-permission cause.
- **Assuming a broker restart will not cause message redelivery:** messages not yet acknowledged can be redelivered according to the broker's semantics.
- **Using recoveryInterval to handle a poison message:** business errors need error handling, retry/redelivery, and a DLQ.
- **Not considering provider reconnect:** retries at both the provider and Spring can overlap.
- **Not monitoring the listener state:** the application may be running while the consumers are not active.
- **Not testing broker restart:** a successful startup configuration does not prove runtime recovery works.

## 13. Configuration checklist

Before putting a JMS listener into production, check:

- Does the listener use DefaultMessageListenerContainer or which other container implementation?
- Is recovery a fixed interval or a custom BackOff?
- Is the recoveryInterval value in milliseconds appropriate?
- If using ExponentialBackOff, are initialInterval, multiplier, and maxInterval reasonable?
- Is maxElapsedTime or maxAttempts needed to stop recovery?
- When the BackOff returns STOP, who receives the alert and restarts the listener?
- Does the provider have its own failover/reconnect?
- Does recovery overlap with the provider's retry?
- Has a setup error been distinguished from a message-processing error?
- Are the transaction and redelivery policy configured separately?
- Are there metrics for recovery, active consumers, and queue backlog?
- Has the integration test stopped/restarted the broker and verified that the listener receives messages again?

When recoveryInterval or BackOff is configured correctly, DefaultMessageListenerContainer can recover the listener on its own after a transient connection failure with an appropriate retry schedule. Separating infrastructure recovery from business redelivery helps the application keep its ability to receive messages and handle errors according to each layer's responsibility.

## 14. References

- [DefaultMessageListenerContainer — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html)
- [DefaultJmsListenerContainerFactory — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/config/DefaultJmsListenerContainerFactory.html)
- [ExponentialBackOff — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/util/backoff/ExponentialBackOff.html)
- [FixedBackOff — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/util/backoff/FixedBackOff.html)
- [Receiving a Message — Spring Framework Reference](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html)