# Testing Channel Send and Receive with a Controlled Executor

In Spring Messaging, a message is sent through a MessageChannel and delivered to one or more MessageHandlers. When a channel uses an executor, sending the message and the handler actually processing the message happen at two different times. Therefore, a test that only calls send() and immediately checks the handler result can suffer from a race condition: the test runs before the worker thread finishes processing.

A controlled executor enables testing asynchronous flows deterministically. Instead of spawning threads that run at arbitrary times, the test uses an executor that holds Runnables in a queue. The test decides when to run each task, thereby clearly verifying that the message is scheduled, the handler receives the expected payload/headers, and the reply is forwarded as expected.

## 1. Distinguishing Channel Types and How Messages Are Received

Core abstractions in Spring Messaging:

- **MessageChannel:** contract for sending Messages. The send() method returns a boolean indicating whether the send was accepted.
- **SubscribableChannel:** a channel that maintains a list of subscribers as MessageHandlers. When a message arrives, the channel invokes the registered handlers.
- **ExecutorSubscribableChannel:** a SubscribableChannel that can delegate handler invocation to a java.util.concurrent.Executor.
- **PollableChannel:** a channel with a receive() API so consumers can actively pull messages. QueueChannel is a common example in Spring Integration.

Distinguish how the two groups receive messages:

| Channel Type | How Consumers Receive Messages | How to Test |
|---|---|---|
| SubscribableChannel | MessageHandler registered via subscribe(handler) | Record messages in the handler and control when the executor runs tasks |
| PollableChannel | Consumer calls receive() or receive(timeout) | Send a message and call receive with a bounded timeout |
| ExecutorSubscribableChannel | MessageHandler runs via Executor | Use a fake executor to schedule and run tasks under test control |

ExecutorSubscribableChannel belongs to the org.springframework.messaging.support package of Spring Framework. QueueChannel is commonly used from Spring Integration; do not confuse Spring Integration implementations with channels built into the spring-messaging module.

## 2. What Happens When Calling send() on ExecutorSubscribableChannel?

For an ExecutorSubscribableChannel created with an executor:

1. Caller invokes channel.send(message).
2. The channel runs interceptors in the send phase.
3. For each subscriber, the channel creates a task to process the message.
4. The channel hands the task to the executor via execute(task).
5. send() returns after sending/scheduling completes.
6. The executor runs the task; the task calls MessageHandler.handleMessage(message).
7. Post-handling callbacks of ExecutorChannelInterceptor are invoked after the handler completes or throws an error.

Therefore, send() returning true does not mean the handler has finished running. It usually only indicates that the channel accepted the send and handed the task to the executor. With an asynchronous executor, the handler may not have been invoked yet when send() returns.

Another important point: ExecutorSubscribableChannel has no receive() method. The receiving side is the subscribed MessageHandler. If a test needs to inspect messages arriving at the consumer, record the message directly inside the handler or use a PollableChannel as the handler's output.

### 2.1. Default Executor vs. Supplied Executor

- new ExecutorSubscribableChannel() creates a channel that runs handlers on the thread calling send().
- new ExecutorSubscribableChannel(executor) delegates tasks to the provided executor.
- Passing null also means executing on the thread calling send().

If the goal is to test asynchronous scheduling, do not use the default constructor or a synchronous executor. Pass an executor controlled by the test.

### 2.2. send() Does Not Wait for Handler Completion

Do not write a test like the following for an asynchronous channel:

~~~java
assertTrue(channel.send(message));
assertEquals("hello", received.getPayload());
~~~

The snippet above may pass sometimes and fail other times depending on worker thread timing. Do not fix race conditions with Thread.sleep(100), because sleeping only slows tests down and still does not guarantee the task has finished.

Instead, the test needs a deterministic signal: run tasks manually in a fake executor, or wait on a CountDownLatch/CompletableFuture with a timeout when testing a real executor.

## 3. Building a Fake Executor to Control Each Task

A minimal fake executor can hold Runnables in a queue. The test calls runNext() to execute exactly one task, or runAll() if it wants to drain all pending tasks.

~~~java
import java.util.ArrayDeque;
import java.util.Queue;
import java.util.concurrent.Executor;

final class ManualExecutor implements Executor {

    private final Queue<Runnable> tasks = new ArrayDeque<>();

    @Override
    public void execute(Runnable task) {
        this.tasks.add(task);
    }

    int pendingTasks() {
        return this.tasks.size();
    }

    void runNext() {
        Runnable task = this.tasks.poll();
        if (task == null) {
            throw new IllegalStateException("No task is pending");
        }
        task.run();
    }

    void runAll() {
        while (!this.tasks.isEmpty()) {
            runNext();
        }
    }
}
~~~

Characteristics of ManualExecutor:

- execute() only adds the task to the queue without running it immediately.
- pendingTasks() reports the number of queued tasks.
- runNext() runs exactly one task and returns control to the test.
- runAll() runs all pending tasks, including new tasks enqueued during processing.

This executor is only for single-threaded tests. It does not simulate thread scheduling, race conditions, or true thread-pool concurrency. In return, it allows verifying processing order and timing without depending on machine speed or sleep.

## 4. Testing Request Sending and Reply Receiving Step by Step

The example below uses two ExecutorSubscribableChannels: one channel receives requests and one channel emits replies. Both share the same ManualExecutor. The test explicitly runs the request task first, and only then runs the reply task.

~~~java
import java.util.concurrent.Executor;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.ExecutorSubscribableChannel;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.*;

class ExecutorSubscribableChannelTest {

    @Test
    void sendsRequestAndReceivesReplyDeterministically() {
        ManualExecutor executor = new ManualExecutor();

        ExecutorSubscribableChannel inbound =
                new ExecutorSubscribableChannel(executor);
        ExecutorSubscribableChannel outbound =
                new ExecutorSubscribableChannel(executor);

        AtomicReference<Message<?>> requestReceived = new AtomicReference<>();
        AtomicReference<Message<?>> replyReceived = new AtomicReference<>();

        inbound.subscribe(request -> {
            requestReceived.set(request);

            Message<String> reply = MessageBuilder.withPayload("pong")
                    .setHeader(
                            "correlationId",
                            request.getHeaders().get("correlationId"))
                    .build();

            assertTrue(outbound.send(reply));
        });

        outbound.subscribe(replyReceived::set);

        Message<String> request = MessageBuilder.withPayload("ping")
                .setHeader("correlationId", "corr-42")
                .build();

        // Send only queues the task; the handler has not run yet.
        assertTrue(inbound.send(request));
        assertNull(requestReceived.get());
        assertNull(replyReceived.get());
        assertEquals(1, executor.pendingTasks());

        // Run the inbound channel task.
        executor.runNext();
        assertEquals("ping", requestReceived.get().getPayload());
        assertNull(replyReceived.get());

        // The inbound handler sent a reply, so an outbound task is pending.
        assertEquals(1, executor.pendingTasks());

        // Run the outbound channel task.
        executor.runNext();
        assertEquals("pong", replyReceived.get().getPayload());
        assertEquals(
                "corr-42",
                replyReceived.get().getHeaders().get("correlationId"));
        assertEquals(0, executor.pendingTasks());
    }

    static final class ManualExecutor implements Executor {

        private final java.util.Queue<Runnable> tasks =
                new java.util.ArrayDeque<>();

        @Override
        public void execute(Runnable task) {
            this.tasks.add(task);
        }

        int pendingTasks() {
            return this.tasks.size();
        }

        void runNext() {
            Runnable task = this.tasks.poll();
            if (task == null) {
                throw new IllegalStateException("No task is pending");
            }
            task.run();
        }
    }
}
~~~

This is a complete JUnit 5 test class. The test uses MessageBuilder to create a message with a payload and correlationId, then verifies that both the request and reply preserve the expected data.

Execution flow:

~~~text
Test
 |
 | inbound.send(request)
 v
ManualExecutor: [request task]
 |
 | runNext()
 v
Inbound MessageHandler receives "ping"
 |
 | outbound.send(reply)
 v
ManualExecutor: [reply task]
 |
 | runNext()
 v
Outbound MessageHandler receives "pong"
 |
 v
Test verifies payload + correlationId
~~~

The key point to observe is that after the first runNext(), the request handler has received the message, yet the reply handler still has not run. The reply is only received after the second runNext(). The test thus proves the asynchronous boundary between the two channels.

## 5. Testing Multiple Subscribers

ExecutorSubscribableChannel delivers messages to each subscriber. For each handler, the channel creates a separate task and submits it to the executor.

Example with two subscribers:

~~~java
ManualExecutor executor = new ManualExecutor();
ExecutorSubscribableChannel channel =
        new ExecutorSubscribableChannel(executor);

List<String> received = new ArrayList<>();

channel.subscribe(message -> received.add("handler-A"));
channel.subscribe(message -> received.add("handler-B"));

assertTrue(channel.send(
        MessageBuilder.withPayload("event").build()));

assertEquals(2, executor.pendingTasks());
assertTrue(received.isEmpty());

executor.runNext();
assertEquals(1, received.size());

executor.runNext();
assertEquals(2, received.size());
~~~

This example illustrates one task per subscriber. Do not assume completion order across multiple subscribers when using a real thread pool. With a FIFO ManualExecutor, the test can control task execution order, but that order is an artifact of the fake executor rather than a general guarantee for all executors.

If business logic requires processing order, check the preserve-order configuration or appropriate serialization mechanism of the real system. Do not infer processing order from the order of subscribe() calls when tasks can run concurrently.

## 6. Testing Errors in MessageHandler

With an asynchronous executor, exceptions thrown inside a handler typically surface when the executor runs the task. The caller already received the result from send() earlier, so assertThrows cannot be placed around send() to catch asynchronous processing failures.

For a handler throwing IllegalStateException, ExecutorSubscribableChannel wraps the processing error in MessageDeliveryException. ManualExecutor lets the test catch the exception at the exact moment the task executes:

~~~java
import org.springframework.messaging.MessageDeliveryException;

@Test
void handlerFailureIsObservedWhenExecutorRunsTask() {
    ManualExecutor executor = new ManualExecutor();
    ExecutorSubscribableChannel channel =
            new ExecutorSubscribableChannel(executor);

    channel.subscribe(message -> {
        throw new IllegalStateException("invalid state");
    });

    Message<String> message =
            MessageBuilder.withPayload("bad-event").build();

    assertTrue(channel.send(message));

    assertEquals(1, executor.pendingTasks());

    assertThrows(
            MessageDeliveryException.class,
            executor::runNext);
}
~~~

In cases where a handler throws a MessagingException, the implementation may propagate that exception directly instead of wrapping it in MessageDeliveryException. Tests should verify the exact exception contract provided by the application's handlers and adapters.

Do not treat send() returning true as proof that the message was processed successfully. When you need to verify processing results, inspect the output channel, completion signal, business state, or appropriate callbacks.

## 7. Distinguishing ChannelInterceptor and ExecutorChannelInterceptor

The two interceptor types operate at different stages.

### ChannelInterceptor

ChannelInterceptor observes the send/receive lifecycle at the channel level:

- preSend(): before the channel sends the message; can modify the message or return null to block sending.
- postSend(): immediately after the send call completes; receives a boolean indicating whether sending succeeded.
- afterSendCompletion(): runs after the send cycle finishes, even if an exception occurred.

With ExecutorSubscribableChannel, postSend() may run before subscribers process the message because send only queued tasks to the executor.

### ExecutorChannelInterceptor

ExecutorChannelInterceptor extends ChannelInterceptor and provides per-subscriber callbacks inside the executor task:

- beforeHandle(): right before invoking the MessageHandler.
- afterMessageHandled(): after the handler completes, even if the handler throws an exception.

If the test goal is to verify when a handler started or finished processing, ExecutorChannelInterceptor callbacks are more appropriate than postSend().

Example of recording processing outcome:

~~~java
AtomicReference<Exception> handlingError = new AtomicReference<>();

channel.addInterceptor(new ExecutorChannelInterceptor() {

    @Override
    public void afterMessageHandled(
            Message<?> message,
            MessageChannel channel,
            MessageHandler handler,
            Exception ex) {

        handlingError.set(ex);
    }
});
~~~

In a test using ManualExecutor, you can assert that handlingError is still null before runNext(), then check its value after the task runs. If the handler succeeds, ex is null; if the handler fails, the callback receives the corresponding exception.

## 8. When You Need to Test a Real Executor

ManualExecutor is well-suited for unit tests of scheduling and ordering. When you need to verify integration with ThreadPoolTaskExecutor or multithreaded behavior, use a real executor and a synchronization signal.

Example using CountDownLatch:

~~~java
CountDownLatch handled = new CountDownLatch(1);
AtomicReference<Message<?>> received = new AtomicReference<>();

ExecutorSubscribableChannel channel =
        new ExecutorSubscribableChannel(threadPoolTaskExecutor);

channel.subscribe(message -> {
    received.set(message);
    handled.countDown();
});

assertTrue(channel.send(
        MessageBuilder.withPayload("async-event").build()));

assertTrue(handled.await(2, TimeUnit.SECONDS));
assertEquals("async-event", received.get().getPayload());
~~~

In this example, threadPoolTaskExecutor is a ThreadPoolTaskExecutor whose initialization and lifecycle are managed by the Spring context. The test must shut down the context or executor after completion.

CountDownLatch.await(timeout) has a time bound so the test never hangs indefinitely. If using CompletableFuture, use get(timeout, unit) or an equivalent deadline-bounded await API. Do not use Thread.sleep to guess when a handler finishes.

ManualExecutor and a real executor test two different classes of properties:

| Goal | Appropriate Tool |
|---|---|
| Verify send only enqueues tasks | ManualExecutor |
| Run individual handlers under test control | ManualExecutor |
| Verify request/reply step by step | ManualExecutor |
| Verify exceptions when a task executes | ManualExecutor |
| Verify real threads, concurrency, shutdown | ThreadPoolTaskExecutor + latch/future |
| Verify race conditions and thread safety | Real executor, barrier/latch, and controlled repeated testing |

## 9. Caveats When Using Executors in Tests

### 9.1. Executor Rejecting Tasks

In the current implementation of ExecutorSubscribableChannel, if the executor throws RejectedExecutionException, the channel executes the task directly on the sending thread as a fallback treated as an executor-shutdown scenario. Therefore, do not assume that an executor rejecting a task will cause send() to return false or prevent the handler from being invoked.

This fallback behavior can cause handlers to run synchronously on the caller thread and alter latency. If the application needs a different task rejection policy, verify the Spring version in use and configure the executor accordingly.

### 9.2. Do Not Leak Tasks Between Tests

A ManualExecutor must be created fresh for each test or cleared after every test. If tasks remain in the queue from a previous test, a later test may execute the wrong message and produce hard-to-explain failures.

With a real executor, close the ApplicationContext or call shutdown properly according to its lifecycle. Do not share a global thread pool across tests without a clear reason.

### 9.3. Avoid Asserting State Before Synchronization

Reading an AtomicReference immediately after send() only proves the handler had not updated the value at the moment of the read. With a real executor, the value could change immediately afterward. Only assert final state after a latch/future or equivalent synchronization mechanism.

### 9.4. Do Not Assume send Timeout Bounds Handler Execution Time

MessageChannel.send(message, timeout) describes the wait time to send/be accepted by the channel depending on the implementation. It is not an overall deadline for the handler's total execution time. With ExecutorSubscribableChannel, the task may keep running after send() has returned. To bound processing time, manage deadlines in the handler, executor, or application layer.

### 9.5. Channel Tests Do Not Replace Broker Integration Tests

An ExecutorSubscribableChannel test verifies in-process sending, scheduling, and handler invocation logic. It does not verify that an external broker received the message, ACK, persistence, redelivery, routing, or delivery guarantees.

With a real broker, separate integration tests are needed to verify adapters, connections, serialization, acknowledgments, and retries. Keep unit tests fast and deterministic; only involve a broker in tests when verifying integration behavior.

## 10. Checklist for a Reliable Send/Receive Test

- [ ] Use the right channel type for the goal: SubscribableChannel or PollableChannel.
- [ ] When testing asynchronous behavior, pass an executor controlled by the test.
- [ ] Verify send() returns true and the task was queued.
- [ ] Verify the handler has not run before the executor executes the task.
- [ ] Explicitly run tasks and verify received payload/headers.
- [ ] If the handler sends a reply, verify the reply is received only after the corresponding task.
- [ ] Verify correlationId or message ID is preserved.
- [ ] Verify exceptions when the task runs, not just around send().
- [ ] Use ExecutorChannelInterceptor if you need to verify when the handler finishes.
- [ ] Do not use Thread.sleep or unbounded timeouts.
- [ ] Clean up queues, subscriptions, ApplicationContext, and executors after tests.
- [ ] Have separate integration tests for a real broker when delivery/ACK guarantees need verification.

## References

- Spring Framework Javadoc — ExecutorSubscribableChannel: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/ExecutorSubscribableChannel.html
- Spring Framework Javadoc — SubscribableChannel: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/SubscribableChannel.html
- Spring Framework Javadoc — MessageChannel: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageChannel.html
- Spring Framework Javadoc — ChannelInterceptor: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/ChannelInterceptor.html
- Spring Framework Javadoc — ExecutorChannelInterceptor: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/ExecutorChannelInterceptor.html
- Spring Framework source — ExecutorSubscribableChannel implementation: https://github.com/spring-projects/spring-framework/blob/main/spring-messaging/src/main/java/org/springframework/messaging/support/ExecutorSubscribableChannel.java
- Spring Framework tests — MessageBrokerConfigurationTests: https://github.com/spring-projects/spring-framework/blob/main/spring-messaging/src/test/java/org/springframework/messaging/simp/config/MessageBrokerConfigurationTests.java
