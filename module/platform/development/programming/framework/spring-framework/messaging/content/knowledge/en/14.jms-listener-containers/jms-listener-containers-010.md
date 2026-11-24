# Starting, Stopping, Waiting for Processing, and Receiving Messages While Stopping

In Spring JMS, **DefaultMessageListenerContainer (DMLC)** manages the lifecycle of consumers receiving messages from a Queue or Topic. The container supports starting, pausing, restarting, and releasing resources when the application closes. When stopping, an important question is whether a listener currently processing a message is allowed to finish, whether new messages arriving during stopping are received, and when the application knows it can close other dependencies.

Three operations must be distinguished: **stop** pauses message receiving and lets listener invokers stop; **stop(Runnable)** provides a callback when all listener processing has actually stopped; **shutdown/destroy** releases the Session, Consumer, and Connection managed by the container. Understanding these operations properly helps implement graceful shutdown, avoid closing the database or dependencies too early, and control messages received during the stopping phase.

## 1. Lifecycle of DefaultMessageListenerContainer

DMLC implements Spring's lifecycle interfaces, including **Lifecycle**, **SmartLifecycle**, and **DisposableBean**. Therefore, it can be automatically started and stopped by the Spring ApplicationContext according to the application lifecycle.

States to distinguish:

- **Initialized/active:** the container has been configured and has created the necessary infrastructure.
- **Running:** the container is allowing invokers to receive messages and invoke the listener.
- **Stopped:** the container has received a stop request; it can be started again if it has not been shut down.
- **Shutdown/destroyed:** the container has closed the resources it manages and ended its lifecycle.

Some key methods:

| Method | Meaning |
|---|---|
| start() | Starts or resumes receiving messages |
| stop() | Asks the container to stop receiving messages and stop the invokers |
| stop(Runnable callback) | Stops the container and invokes the callback after listener processing has actually stopped |
| shutdown() | Stops the shared Connection, destroys Sessions/Consumers, and closes the container |
| destroy() | Spring hook to call shutdown() when the bean is destroyed |
| isRunning() | Indicates whether the container is in the running state |
| isActive() | Indicates whether the container has been initialized and has not yet shut down |

**stop() can be followed by start()** to continue using the container. shutdown() and destroy() are for ending the lifecycle and releasing resources. Do not use shutdown() as an ordinary pause operation if you still intend to restart the container.

### 1.1. Auto-startup and lifecycle ordering

DMLC has **autoStartup=true** by default, meaning the Spring LifecycleProcessor starts the container automatically when the ApplicationContext refresh completes. You can disable it to start proactively after the application is ready:

~~~java
container.setAutoStartup(false);
~~~

DMLC also has a lifecycle phase. Spring starts components in ascending phase order and stops them in reverse order. By default DMLC uses SmartLifecycle.DEFAULT_PHASE, meaning it starts late and stops early in the lifecycle chain. You can adjust the phase to control the relationship between the listener and other dependencies.

For example, if the listener needs a database and auxiliary services, those dependencies must be ready before the listener starts. On shutdown, the listener should stop before the database connection pool or dependencies the listener needs are closed.

## 2. What happens when stop() is called?

DMLC uses invokers running a message-receiving loop with MessageConsumer.receive(). When stop() is called:

1. The container sets the running state to false.
2. The container wakes up invokers waiting on the lifecycle condition.
3. The shared Connection is stopped if the container's cache strategy uses a shared Connection.
4. The invokers stop receiving new messages according to the stop rules.
5. A currently running listener is allowed to reach the end of processing; the container tracks when all listener processing stops.

stop() does not mean deleting messages remaining in the Queue or waiting for the whole destination to empty. Unreceived messages still belong to the broker/destination and can be processed after the container restarts or by another consumer.

You should also not use isRunning()==false alone to conclude that all listener invocations have finished. The running state reflects the lifecycle request; to know that stopping the listener has completed, use stop(Runnable callback).

## 3. Waiting for an in-flight listener to complete with stop(Runnable)

DMLC provides the overload:

~~~java
container.stop(() -> {
    // Listener processing has actually stopped.
    stoppedLatch.countDown();
});
~~~

The callback is only invoked after all listener processing in the container has stopped. This is the right signal for the application to proceed to the next shutdown step, such as closing the services that the listener uses.

You can use a CountDownLatch to wait for the callback with an application-defined timeout:

~~~java
CountDownLatch stopped = new CountDownLatch(1);

container.stop(stopped::countDown);

boolean completed = stopped.await(30, TimeUnit.SECONDS);

if (!completed) {
    throw new IllegalStateException(
            "JMS listener container did not stop in time"
    );
}
~~~

In the example, 30 seconds is the wait limit set by the application. DMLC does not provide a separate awaitTermination() method. If the timeout expires, you must not consider the container completely stopped; record that listeners are still running and apply the application's shutdown policy.

Some notes on the callback:

- The callback is invoked after listener processing actually stops, not merely after the stop request is sent.
- If stop(callback) is called multiple times while the previous stop has not yet finished, the newest callback replaces the previous one.
- If start() is called to restart the container before the stop process completes, the waiting callback may not be invoked.
- The callback should be short. If many shutdown steps need to be performed, the callback can signal a separate coordinator to continue the work.

## 4. Receiving messages while the container is stopping

DMLC has the **acceptMessagesWhileStopping** property to decide how to handle a message that receive() returns during the time the container is stopping.

Configuration:

~~~java
container.setAcceptMessagesWhileStopping(false);
~~~

The default value is **false**.

### 4.1. acceptMessagesWhileStopping=false

When the container is stopping, a message returned from a receive attempt may be rejected by aborting the receive attempt. This helps the container exit the receive loop and finish faster.

This behavior does not mean DMLC actively deletes all waiting messages. A message whose receive attempt is aborted is handled according to the semantics of the JMS provider and the acknowledgement/transaction in use.

Spring's Javadoc notes that aborting a receive attempt can cause the provider's retry counter to decrease for the message involved. If there are multiple concurrent consumers, check the provider's retry/redelivery policy and ensure the retry count is large enough relative to the number of consumers in shutdown situations.

### 4.2. acceptMessagesWhileStopping=true

You can enable it:

~~~java
container.setAcceptMessagesWhileStopping(true);
~~~

When enabled, DMLC continues processing messages that pending receive attempts return during the stopping phase. This can help finish a few more messages that the broker had already delivered to the consumer when shutdown began.

However, receive timeouts that have not yet expired can still receive new messages sent after the moment stop began. Therefore, the container can continue processing new messages while stopping. If producers keep sending messages continuously, the wait time for the callback can drag on.

This flag is not a mode to drain the entire Queue. It only decides how to handle messages received by receive attempts still in progress during the stopping phase. To drain a backlog in a controlled way, you need to coordinate stopping producers, observing the backlog, and managing shutdown time at the application level.

### 4.3. Comparing the two options

| Configuration | Behavior during stopping | Impact |
|---|---|---|
| false (default) | Aborts receive attempts for messages arriving during the stopping phase | Stops receiving faster; need to check the provider's redelivery/retry |
| true | Processes messages returned by receive during the stopping phase | Can complete additional messages, but can also receive new messages and prolong shutdown |

Choose according to business requirements. If the priority is to stop receiving quickly to deploy a new version, false is usually suitable. If you want to finish messages consumers are waiting to receive and accept a longer shutdown time, you can consider true after testing.

## 5. In-flight messages, acknowledgement, and transactions

How messages are handled when stopping is directly tied to the Session's acknowledgement and transaction.

### 5.1. AUTO_ACKNOWLEDGE

With DMLC, the default AUTO_ACKNOWLEDGE mode performs acknowledgement before invoking the listener. If the listener throws an exception or the application stops at an unfortunate moment, the message may already be acknowledged and will not be redelivered.

Therefore, AUTO_ACKNOWLEDGE does not provide a reliable guarantee for flows where messages must not be lost. Do not treat the stop callback as a mechanism to recover already-acknowledged messages.

### 5.2. Local transacted Session

You can enable a local JMS transaction:

~~~java
container.setSessionTransacted(true);
~~~

In that case, receiving the message and processing the listener are inside the Session's transaction:

- The listener completes normally: the container commits the transaction.
- The listener throws an exception: the container rolls back the transaction according to the error-handling mechanism.
- The container stops while the message has not yet been committed: the unfinished transaction can be rolled back when resources are terminated, so the provider handles redelivery according to configuration.

For a message currently being processed by the listener, the stop callback only completes after listener processing has stopped. If the listener completes normally and the transaction commits, the message has been processed. If the listener fails and rolls back, the provider can redeliver the message.

Redelivery count, delay, dead-letter policy, and attempt limits depend on the JMS provider. Configure a limit for poison messages so that a faulty message is not redelivered endlessly.

### 5.3. External transaction manager

DMLC can also participate in an external transaction through the transactionManager property, usually JtaTransactionManager in an environment supporting XA/JTA.

On shutdown, the transaction manager needs to finish or roll back active transactions before closing related resources. Stopping beans in lifecycle phase order helps ensure the listener finishes before the transaction/database dependencies it needs.

JMS and database transactions do not automatically become one atomic transaction if only a local transacted Session is used. If you need to guarantee consistency between the database and messages, configure an appropriate XA/JTA or use a Transactional Outbox.

## 6. stop(), shutdown(), and closing the ApplicationContext

These three operations have different purposes:

| Operation | Purpose | Can start again? |
|---|---|---|
| stop() | Pauses the listener container | Yes, call start() |
| stop(Runnable) | Pauses and receives a callback when listener processing has stopped | Yes, call start() after stopping completes |
| shutdown() | Stops the Connection, destroys Sessions/Consumers, and closes the container | Used for ending the lifecycle; requires re-initialization if you want to reuse |
| destroy() | Bean release hook, calls shutdown() | Do not use for pause/restart |

In a Spring application, the ApplicationContext manages SmartLifecycle and DisposableBean. When the context closes, the lifecycle processor asks SmartLifecycle components to stop according to phase; afterward beans are destroyed to release resources.

If you need to coordinate shutdown manually, you can call stop(callback), wait for the callback to complete, and then close other dependencies. Avoid calling destroy() or closing the ConnectionFactory while the listener is still using the Session, database, or auxiliary services.

## 7. Graceful shutdown process for a JMS application

A controlled shutdown process usually consists of:

1. Stop accepting new work from HTTP/API or internal producers.
2. If business requires, pause producers publishing new messages to the destination.
3. Call stop(Runnable) on DMLC.
4. Choose acceptMessagesWhileStopping according to the policy for handling messages during stop.
5. Wait for the callback confirming listener processing has stopped, with an application-defined timeout.
6. After the callback, close the database pool, auxiliary services, and resources the listener needs.
7. Close the ApplicationContext so Spring destroys the container and remaining beans.
8. When starting again, start the container after dependencies and the broker are ready.

If the queue still has a backlog after the container stops, messages can remain on the broker and be processed by consumers later. That is usually better than trying to process the entire backlog within an unbounded shutdown window.

### 7.1. Bounding the shutdown time

The wait timeout for the callback must be chosen according to the listener's maximum processing time and the shutdown time allowed by the deployment platform.

Example:

~~~java
CountDownLatch stopped = new CountDownLatch(1);

container.stop(stopped::countDown);

if (!stopped.await(45, TimeUnit.SECONDS)) {
    // Log/emit metrics and apply the application's shutdown policy.
}
~~~

If a listener can run longer than 45 seconds, the application needs to decide whether to wait longer, report an incomplete shutdown, or switch to an emergency stop mechanism. Do not assume the CountDownLatch timeout stops the listener thread on its own.

The listener should have timeouts for HTTP, database, and external service calls. If a listener can hang indefinitely, the stop callback may also never complete.

## 8. Sample configuration for DMLC

Example of configuring the container with a local JMS transaction and not receiving messages during the stopping phase:

~~~java
@Configuration
public class JmsListenerConfiguration {

    @Bean
    public DefaultMessageListenerContainer orderContainer(
            ConnectionFactory connectionFactory,
            MessageListener orderListener) {

        DefaultMessageListenerContainer container =
                new DefaultMessageListenerContainer();

        container.setConnectionFactory(connectionFactory);
        container.setDestinationName("orders.queue");
        container.setMessageListener(orderListener);

        container.setConcurrentConsumers(2);
        container.setMaxConcurrentConsumers(8);

        container.setSessionTransacted(true);
        container.setAcceptMessagesWhileStopping(false);
        container.setReceiveTimeout(1_000);

        container.setAutoStartup(false);

        return container;
    }
}
~~~

The application can start after dependencies are ready:

~~~java
container.start();
~~~

And stop while waiting for the callback:

~~~java
CountDownLatch stopped = new CountDownLatch(1);

container.stop(stopped::countDown);

if (!stopped.await(45, TimeUnit.SECONDS)) {
    throw new IllegalStateException(
            "Order listener did not stop before the deadline"
    );
}
~~~

This is an illustrative configuration. With Spring Framework 6 and later, the JMS API uses the jakarta.jms package; older Spring applications may use javax.jms. Synchronize the package with the framework version and provider.

If using an external transaction manager, configure an appropriate transactionManager and check cacheLevel according to the application server's XA rules. Do not force caching of Sessions/Consumers if the provider requires obtaining fresh resources within the transaction scope.

## 9. Scenarios to test

Lifecycle testing should confirm actual behavior rather than just checking isRunning():

- **Start:** the container starts receiving messages after dependencies are ready.
- **Stop when idle:** invokers exit the receive loop and the callback is invoked.
- **Stop while listener is processing:** the callback is only invoked after listener processing finishes.
- **Stop with a message waiting to be received:** test acceptMessagesWhileStopping=false and true on a real provider.
- **Backlog:** unreceived messages remain on the destination after stop and are processed when started again.
- **Transaction rollback:** the listener throws an exception in a transacted Session; confirm redelivery per the provider.
- **Shutdown timeout:** the listener processes longer than the deadline; confirm the application reports an incomplete shutdown.
- **Restart:** stop and then start the container again; confirm the Connection, Session, and Consumer are re-created according to the lifecycle.
- **ApplicationContext close:** verify the listener stops before the database pool and other dependencies.
- **Concurrent stop/start:** avoid restarting the container before the stop callback completes if the application relies on the callback signal.

Also monitor activeConsumerCount, scheduledConsumerCount, message processing time, rollback/redelivery counts, number of messages in the backlog, and time from the stop request to the callback.

## 10. Java 17 example: waiting for an in-flight message to finish before stopping a worker

The following example uses BlockingQueue, ExecutorService, and CountDownLatch to simulate a worker currently processing a message when a stop request arrives. The worker completes the current message, then exits the loop; the remaining message in the queue keeps waiting.

This is a pure JDK program to illustrate lifecycle and waiting for the callback. It does not replace DMLC, does not connect to a JMS broker, and does not simulate the provider's acknowledgement/redelivery.

Create the file **ListenerStopLifecycleDemo.java**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class ListenerStopLifecycleDemo {

    record DemoMessage(String id) {}

    public static void main(String[] args) throws Exception {
        BlockingQueue<DemoMessage> queue =
                new ArrayBlockingQueue<>(4);

        queue.add(new DemoMessage("M-1"));
        queue.add(new DemoMessage("M-2"));

        AtomicBoolean running = new AtomicBoolean(true);
        CountDownLatch processingStarted = new CountDownLatch(1);
        CountDownLatch finishCurrentMessage = new CountDownLatch(1);
        CountDownLatch stoppedCallback = new CountDownLatch(1);

        ExecutorService executor = Executors.newSingleThreadExecutor();

        Future<?> worker = executor.submit(() -> {
            try {
                while (running.get()) {
                    DemoMessage message =
                            queue.poll(5, TimeUnit.SECONDS);

                    if (message == null) {
                        continue;
                    }

                    System.out.println("Processing " + message.id());
                    processingStarted.countDown();

                    // Simulate the listener performing business logic.
                    finishCurrentMessage.await();

                    System.out.println("Processed " + message.id());
                }
            }
            catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
            finally {
                // Simulate the stop(Runnable) callback.
                stoppedCallback.countDown();
            }
        });

        try {
            if (!processingStarted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Listener did not start processing");
            }

            running.set(false);
            System.out.println(
                    "Stop requested; in-flight message is finishing");

            finishCurrentMessage.countDown();

            if (!stoppedCallback.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Listener did not stop before timeout");
            }

            worker.get();

            System.out.println("Stop callback invoked");
            System.out.println("Pending messages: " + queue.size());
        }
        finally {
            finishCurrentMessage.countDown();
            executor.shutdown();

            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
~~~

Compile and run with Java 17 or later:

~~~bash
javac ListenerStopLifecycleDemo.java
java ListenerStopLifecycleDemo
~~~

Result:

~~~text
Processing M-1
Stop requested; in-flight message is finishing
Processed M-1
Stop callback invoked
Pending messages: 1
~~~

The worker receives M-1 and starts processing. The main thread sends a stop request while the message is still being processed. The worker finishes M-1 and exits; the simulated callback is only emitted after the worker stops. M-2 remains in the queue.

In the real DMLC, stop(Runnable) provides a similar callback after listener processing actually stops. How remaining messages are kept, redelivered, or acknowledged depends on the JMS provider and the transaction/acknowledgement mode.

## 11. Common mistakes when managing lifecycle

### 11.1. Thinking stop() waits for the whole queue to empty

stop() stops the listener container. It does not drain the entire backlog on the broker on its own.

How to handle it: if you need to drain, stop the producer, monitor the backlog, and set a clear deadline; use the stop callback to know when listener processing has ended.

### 11.2. Using isRunning() as the signal that shutdown is complete

isRunning() reflects the lifecycle state. When stop is requested, it can turn false before the last listener invocation finishes.

How to handle it: use the stop(Runnable) callback or the ApplicationContext lifecycle coordination mechanism.

### 11.3. Closing the database before the listener stops

A running listener may still need the database or auxiliary services. Closing dependencies too early causes ongoing processing to fail.

How to handle it: wait for the stop callback to complete before closing dependencies that the listener uses.

### 11.4. Enabling acceptMessagesWhileStopping and expecting shutdown to always be fast

When enabled, pending receive attempts can continue receiving messages, including newly arriving ones. If producers are still active, shutdown can drag on.

How to handle it: stop producers first or keep false if stopping quickly is the priority.

### 11.5. Using AUTO_ACKNOWLEDGE for business operations that must not lose messages

DMLC acknowledges before invoking the listener in the default mode. A listener failure does not automatically guarantee redelivery.

How to handle it: use sessionTransacted or an external transaction manager, and also check the provider's retry and DLQ.

### 11.6. Restarting before the stop callback completes

DMLC may not invoke the stop callback if the container is started again before the previous stopping process completes.

How to handle it: wait for the callback before restarting when the application needs to use the callback as a lifecycle milestone.

### 11.7. Calling shutdown() when you only want to pause

shutdown() releases the Session/Consumer and closes the container. This is an operation that ends the resource lifecycle.

How to handle it: use stop() to pause and start() to resume; let Spring call destroy() when the bean is actually destroyed.

## 12. Design rules

- Use start/stop for pausing and restarting within the container lifecycle.
- Use stop(Runnable) to know when listener processing has actually stopped.
- Use shutdown/destroy when you need to release resources.
- Decide acceptMessagesWhileStopping clearly based on the policy for receiving messages while stopping.
- Use a transacted Session or external transaction manager if you need reliability when a listener fails or the application shuts down.
- Stop producers and new work sources before stopping consumers if you need to control the volume of messages generated.
- Wait for the callback before closing the database, HTTP clients, or dependencies the listener needs.
- Set an application-level shutdown timeout and have a policy for when it times out.
- Monitor the backlog, active consumers, rollbacks, redeliveries, and stop time.
- Test stop/start, broker restart, and ApplicationContext close on a real JMS provider.

DMLC supports Spring-standard lifecycle so the application can control when to receive messages, when to stop listeners, and when to release JMS resources. stop(Runnable) is a reliable signal to coordinate graceful shutdown because the callback is only invoked when listener processing has ended. acceptMessagesWhileStopping decides how messages received during the stopping phase are handled; this choice must go together with the application's transaction, acknowledgement, retry, and backlog policies.

## References

- [Spring Framework 6.2: DefaultMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html)
- [Spring Framework 6.2: AbstractMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/AbstractMessageListenerContainer.html)
- [Spring Framework: JMS integration reference](https://docs.spring.io/spring-framework/reference/integration/jms.html)