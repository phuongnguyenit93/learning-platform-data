# Distinguishing the Execution Flows of ChannelInterceptor and ExecutorChannelInterceptor

Spring Messaging has two interceptor types that commonly appear when sending messages through a channel:

- `ChannelInterceptor` observes or adjusts the send/receive lifecycle at the channel level.
- `ExecutorChannelInterceptor` extends `ChannelInterceptor` and adds callbacks that run around a `MessageHandler` processing a message on an executor-dispatched channel.

The key difference is **where the callback sits in the execution flow**. With an `ExecutorSubscribableChannel` backed by an executor, the send callbacks of `ChannelInterceptor` run on the thread calling `send()`; meanwhile, `beforeHandle` and `afterMessageHandled` of `ExecutorChannelInterceptor` run on the thread executing the handler. When the channel runs inline, both groups of callbacks may run on the sending thread.

## 1. The Two Interfaces and Their Scopes

Both interfaces belong to the `org.springframework.messaging.support` package.

### ChannelInterceptor

`ChannelInterceptor` defines channel-level callbacks:

| Callback | Timing | Purpose |
| --- | --- | --- |
| `preSend(message, channel)` | Before the channel sends the message | Inspect, log, or return a modified message |
| `postSend(message, channel, sent)` | After the channel performs the send operation | Observe the `true/false` send outcome |
| `afterSendCompletion(message, channel, sent, ex)` | When the send lifecycle finishes | Clean up resources or record errors |
| `preReceive(channel)` | Before receiving from a receive-capable channel | Allow or prevent the receive operation |
| `postReceive(message, channel)` | After receiving a message | Inspect or modify the received message |
| `afterReceiveCompletion(message, channel, ex)` | When the receive lifecycle finishes | Clean up resources or record errors |

For `send()`, the first three callbacks normally run on the thread calling `channel.send(...)`. This is the thread executing the channel-level send operation, usually the producer thread. If the producer calls `send` from a worker thread, the interceptor also runs on that worker thread.

`preSend` can return a new message to replace the outgoing message. Returning `null` means blocking the send. `postSend` receives the `sent` variable indicating the outcome of the send operation. `afterSendCompletion` receives an exception if the send lifecycle ended with an error.

The three receive callbacks apply only to channels supporting receive operations, such as a `PollableChannel`. `ExecutorSubscribableChannel` dispatches messages to subscribers and does not provide `receive()`.

### ExecutorChannelInterceptor

`ExecutorChannelInterceptor` extends `ChannelInterceptor` and adds two callbacks:

```java
Message<?> beforeHandle(
        Message<?> message,
        MessageChannel channel,
        MessageHandler handler);

void afterMessageHandled(
        Message<?> message,
        MessageChannel channel,
        MessageHandler handler,
        Exception ex);
```

These two callbacks wrap the execution of each `MessageHandler`:

- `beforeHandle` runs before `handler.handleMessage(message)`. It can return a modified message or return `null` to skip the handler.
- `afterMessageHandled` runs after the handler finishes or fails. The `ex` parameter is `null` if the handler completed normally; if an error occurred, it holds the associated exception.

With `ExecutorSubscribableChannel`, these callbacks run on the thread executing the task that delivers to the handler. If the executor actually dispatches to a worker thread, the callbacks run on that worker thread.

Because this interface extends `ChannelInterceptor`, an object implementing `ExecutorChannelInterceptor` can still override `preSend`, `postSend`, `afterSendCompletion`, and other channel-level callbacks. Channel-level callbacks run on the thread invoking send/receive; only the two additional callbacks have handler execution context.

## 2. Thread Flow When Using ExecutorSubscribableChannel

Suppose a producer calls `send()` on an `ExecutorSubscribableChannel` configured with an executor:

```text
Producer thread                         Executor worker
      |                                       |
      |-- ChannelInterceptor.preSend ---------|
      |                                       |
      |-- submit SendTask -------------------->|
      |                                       |-- ExecutorChannelInterceptor.beforeHandle
      |-- ChannelInterceptor.postSend         |-- MessageHandler.handleMessage
      |-- ChannelInterceptor.afterSendCompletion
      |                                       |-- ExecutorChannelInterceptor.afterMessageHandled
      |<-- send() returns                     |
```

These are two callback flows that can run concurrently. The diagram illustrates execution boundaries, not a guarantee that the worker always starts after `afterSendCompletion`. The executor may start the task as soon as the submission arrives, while the producer thread is still finishing post-send callbacks.

Therefore:

- `ChannelInterceptor.postSend` is not a callback indicating the handler has finished processing.
- `ChannelInterceptor.afterSendCompletion` is also not a callback ending asynchronous business processing.
- To observe when a handler starts/ends, use `ExecutorChannelInterceptor.beforeHandle` and `afterMessageHandled`.
- To know whether business results have been persisted, use acknowledgements or application-layer state; interceptors do not provide that guarantee on their own.

### Synchronous Flow Without an Executor

`ExecutorSubscribableChannel()` takes no executor. In this case, the channel executes tasks directly on the thread calling `send()`:

```text
Producer thread
      |
      |-- ChannelInterceptor.preSend
      |-- ExecutorChannelInterceptor.beforeHandle
      |-- MessageHandler.handleMessage
      |-- ExecutorChannelInterceptor.afterMessageHandled
      |-- ChannelInterceptor.postSend
      |-- ChannelInterceptor.afterSendCompletion
      |-- send() returns
```

Therefore, you cannot look at the name `ExecutorChannelInterceptor` alone and conclude that callbacks always run on a thread pool. The actual thread depends on how the channel dispatches tasks.

## 3. Java 17+ Example: Observing the Thread of Each Callback

The example below registers one `ChannelInterceptor` and one `ExecutorChannelInterceptor` on the same `ExecutorSubscribableChannel`. The executor uses a thread named `message-worker`. A `CountDownLatch` holds the handler until the sending thread has received the `send()` result, keeping the output deterministic and easy to observe.

Create `src/main/java/InterceptorThreadDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.support.ChannelInterceptor;
import org.springframework.messaging.support.ExecutorChannelInterceptor;
import org.springframework.messaging.support.ExecutorSubscribableChannel;
import org.springframework.messaging.support.MessageBuilder;

public class InterceptorThreadDemo {

    private static void log(String event) {
        System.out.println(
                event + " [" + Thread.currentThread().getName() + "]");
    }

    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor(task ->
                new Thread(task, "message-worker"));

        CountDownLatch allowHandler = new CountDownLatch(1);
        CountDownLatch handlerFinished = new CountDownLatch(1);

        ExecutorSubscribableChannel asyncChannel =
                new ExecutorSubscribableChannel(executor);

        // Channel-level callbacks: run on the thread calling send().
        asyncChannel.addInterceptor(new ChannelInterceptor() {
            @Override
            public Message<?> preSend(
                    Message<?> message, MessageChannel channel) {
                log("ChannelInterceptor.preSend");
                return message;
            }

            @Override
            public void postSend(
                    Message<?> message,
                    MessageChannel channel,
                    boolean sent) {
                log("ChannelInterceptor.postSend sent=" + sent);
            }

            @Override
            public void afterSendCompletion(
                    Message<?> message,
                    MessageChannel channel,
                    boolean sent,
                    Exception ex) {
                log("ChannelInterceptor.afterSendCompletion ex="
                        + (ex == null ? "null" : ex.getClass().getSimpleName()));
            }
        });

        // Handler-wrapping callbacks: run on the thread executing SendTask.
        asyncChannel.addInterceptor(new ExecutorChannelInterceptor() {
            @Override
            public Message<?> beforeHandle(
                    Message<?> message,
                    MessageChannel channel,
                    MessageHandler handler) {
                try {
                    allowHandler.await(2, TimeUnit.SECONDS);
                }
                catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    return null;
                }

                log("ExecutorChannelInterceptor.beforeHandle");
                return message;
            }

            @Override
            public void afterMessageHandled(
                    Message<?> message,
                    MessageChannel channel,
                    MessageHandler handler,
                    Exception ex) {
                log("ExecutorChannelInterceptor.afterMessageHandled ex="
                        + (ex == null ? "null" : ex.getClass().getSimpleName()));
                handlerFinished.countDown();
            }
        });

        asyncChannel.subscribe(message ->
                log("handler.handleMessage"));

        log("caller.beforeSend");
        boolean sent = asyncChannel.send(
                MessageBuilder.withPayload("order-created").build());

        log("caller.sendReturned sent=" + sent);
        allowHandler.countDown();

        if (!handlerFinished.await(2, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Handler did not finish");
        }

        executor.shutdown();
        executor.awaitTermination(2, TimeUnit.SECONDS);

        // No executor configured: tasks run inline on the thread calling send().
        ExecutorSubscribableChannel inlineChannel =
                new ExecutorSubscribableChannel();

        inlineChannel.addInterceptor(new ExecutorChannelInterceptor() {
            @Override
            public Message<?> beforeHandle(
                    Message<?> message,
                    MessageChannel channel,
                    MessageHandler handler) {
                log("inline.beforeHandle");
                return message;
            }

            @Override
            public void afterMessageHandled(
                    Message<?> message,
                    MessageChannel channel,
                    MessageHandler handler,
                    Exception ex) {
                log("inline.afterMessageHandled");
            }
        });

        inlineChannel.subscribe(message -> log("inline.handler"));
        inlineChannel.send(
                MessageBuilder.withPayload("inline-event").build());
    }
}
```

Create `pom.xml` in the root directory of the Maven project:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>interceptor-thread-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
            <version>7.0.10</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>InterceptorThreadDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Run from the directory containing `pom.xml`:

```bash
mvn -q clean compile exec:java
```

Stdout output:

```text
caller.beforeSend [InterceptorThreadDemo.main()]
ChannelInterceptor.preSend [InterceptorThreadDemo.main()]
ChannelInterceptor.postSend sent=true [InterceptorThreadDemo.main()]
ChannelInterceptor.afterSendCompletion ex=null [InterceptorThreadDemo.main()]
caller.sendReturned sent=true [InterceptorThreadDemo.main()]
ExecutorChannelInterceptor.beforeHandle [message-worker]
handler.handleMessage [message-worker]
ExecutorChannelInterceptor.afterMessageHandled ex=null [message-worker]
inline.beforeHandle [InterceptorThreadDemo.main()]
inline.handler [InterceptorThreadDemo.main()]
inline.afterMessageHandled [InterceptorThreadDemo.main()]
```

In the first part, the three `ChannelInterceptor` callbacks run on the thread calling `send()`; the three handler-related lines run on `message-worker`. The final part uses a channel without an executor, so `beforeHandle`, the handler, and `afterMessageHandled` all run on the main thread.

The latch is used solely to create deterministic output ordering for the example. In real applications, do not block `beforeHandle` like this.

## 4. Callback Ordering and Meaning

### Channel-Level Lifecycle

For a normal send operation:

1. `preSend` runs before the channel performs the send.
2. If the message proceeds to send, the channel invokes internal send logic.
3. `postSend` receives the boolean result of the send logic.
4. `afterSendCompletion` is called when the send lifecycle ends, even if internal send logic throws an exception.

If `preSend` returns `null`, the message is blocked and not forwarded to handlers. Therefore, do not use `postSend` as a sole counter for every message created by the producer; account for the possibility of an interceptor rejecting messages.

### Handler-Wrapping Lifecycle

With `ExecutorSubscribableChannel`, each subscriber receives a processing task. `ExecutorChannelInterceptor` instances are called in registration order during the `beforeHandle` phase. The `afterMessageHandled` callback is called in reverse order to complete the participating interceptors.

`beforeHandle` can return a modified message so the handler receives that message. If it returns `null`, the handler is skipped. `afterMessageHandled` receives the exception if the handler failed, helping measure processing time, log failures, or close context created in `beforeHandle`.

If a channel has multiple subscribers, executor-specific callbacks execute for each handler/task. Thus, a single message sent into the channel can generate multiple `beforeHandle` / `afterMessageHandled` pairs.

## 5. Scenarios That Change the Execution Thread

### Without an Executor

`new ExecutorSubscribableChannel()` runs tasks directly on the thread calling `send()`. Executor-specific callbacks and handlers share the same thread as the producer.

### Executor Running Tasks Asynchronously

With `new ExecutorSubscribableChannel(executor)`, the executor decides the execution thread. If the executor uses a thread pool, handlers and the two executor-specific callbacks usually run on a worker thread from the pool.

### Inline Executor or CallerRunsPolicy

An executor can execute tasks immediately on the thread calling `execute`, such as a direct executor or `ThreadPoolExecutor.CallerRunsPolicy` when the pool is saturated. In that case, executor-specific callbacks and handlers run back on the caller thread.

In Spring Framework 7.0.10's `ExecutorSubscribableChannel` implementation, if there is no executor or submission throws `RejectedExecutionException`, the task is also executed directly on the sending thread. Hence, do not treat the channel name as an absolute guarantee that handlers always run on a worker thread.

### Multiple Handlers and Processing Order

If a channel has multiple subscribers, each handler may be dispatched as a separate task. Do not assume all handlers run sequentially or on the same worker thread. If business ordering matters, design appropriate channels, executors, and synchronization/partitioning mechanisms.

## 6. Handling Errors at the Right Layer

The two interceptor types observe two different error scopes:

- `ChannelInterceptor.afterSendCompletion` observes errors in the channel-level send lifecycle. With asynchronous dispatch, the task may have already been accepted by the executor, so this callback may receive `ex=null` even if the handler fails later.
- `ExecutorChannelInterceptor.afterMessageHandled` observes errors raised while a handler processes a task. The `ex` parameter indicates whether the handler finished normally or failed.

With an asynchronous executor, handler exceptions typically occur on a worker thread after `send()` has already returned. The producer cannot rely solely on try/catch around `channel.send()` to catch all handler errors. Configure logging, error handling, or error reporting flows at the appropriate layer.

Do not throw a new exception from `afterMessageHandled` to replace the original error. This callback is primarily for observation and cleanup; keep error handling clear so the original cause is not masked.

## 7. Thread Safety and Context Propagation

Interceptors can be shared across multiple threads and multiple messages. Therefore:

- Do not store per-message state in mutable interceptor fields without synchronization.
- Put correlation ID, trace ID, or needed metadata into message headers whenever possible.
- If creating context in `beforeHandle` and cleaning it up in `afterMessageHandled`, ensure cleanup always runs even when the handler fails.
- Do not assume `ThreadLocal`, MDC logging context, or security context automatically propagates from producer to executor worker.
- If context must propagate through an executor, configure the executor with an appropriate propagation mechanism, such as `TaskDecorator` with `ThreadPoolTaskExecutor`, and always restore thread state after the task finishes.

Do not retain a transaction or request-scoped object merely because two callbacks share a name referencing the same message. With an asynchronous executor, they may execute on different threads and outside the original transaction/request context.

## 8. Choosing an Interceptor by Need

| Need | What to Use | Reason |
| --- | --- | --- |
| Inspect or modify a message before channel sends | `ChannelInterceptor.preSend` | Runs at the send boundary |
| Record whether channel accepted or rejected a message | `ChannelInterceptor.postSend` | Provides boolean `sent` outcome |
| Clean up context after send operation | `ChannelInterceptor.afterSendCompletion` | Ends the send lifecycle |
| Observe a handler beginning processing | `ExecutorChannelInterceptor.beforeHandle` | Runs right when handler is invoked |
| Measure handler processing duration | `beforeHandle` and `afterMessageHandled` pair | Wraps actual processing |
| Record handler exceptions | `ExecutorChannelInterceptor.afterMessageHandled` | Receives exception from handler execution |
| Control receive operations on a pollable channel | Receive callbacks of `ChannelInterceptor` | Wraps `receive()` |

If you only need to log producer message sends, `ChannelInterceptor` is sufficient. If you need to measure duration or manage context around each handler on `ExecutorSubscribableChannel`, use `ExecutorChannelInterceptor`.

## 9. Common Pitfalls

1. **Assuming `ChannelInterceptor.postSend` runs after handlers complete.** With an asynchronous executor, it runs only after the internal dispatch/send operation.
2. **Assuming `afterSendCompletion` is the message-processing completion callback.** It ends the channel's send lifecycle, not the asynchronous handler lifecycle.
3. **Assuming `ExecutorChannelInterceptor` always runs on a thread pool.** No executor, direct executors, or rejection fallbacks can run inline.
4. **Using `ExecutorChannelInterceptor` on a channel that does not support executor-specific callbacks.** The extra callbacks are invoked only by implementations that integrate this mechanism.
5. **Ignoring the message returned by `beforeHandle`.** Returning a new message replaces the message passed to the handler; returning `null` skips the handler.
6. **Using `preSend` to measure handler time.** The interval from `preSend` to `afterSendCompletion` does not represent asynchronous processing time.
7. **Storing message data in non-thread-safe interceptor fields.** Multiple tasks can access the interceptor concurrently.
8. **Assuming MDC or ThreadLocal propagates automatically to workers.** Configure context propagation and clear state after the task.
9. **Using try/catch around `send()` to catch asynchronous handler errors.** Handler errors can occur after the producer already received the send result.

## 10. Implementation Checklist

- Determine whether the channel being used has an executor or runs inline.
- Use `ChannelInterceptor` for send/receive-level callbacks.
- Use `ExecutorChannelInterceptor` when hooks around each handler are needed.
- Log thread names in test environments to verify threading assumptions.
- Do not treat `postSend` or `afterSendCompletion` as confirmation that handlers completed.
- Handle the `sent` outcome and exceptions at the proper layer.
- Ensure interceptors are thread-safe and hold no per-message state in shared fields.
- Propagate trace/security context across executors using explicit mechanisms.
- Test both asynchronous executor execution and inline channel execution.

## 11. References

- [Spring Framework – ChannelInterceptor Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/ChannelInterceptor.html)
- [Spring Framework – ExecutorChannelInterceptor Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/ExecutorChannelInterceptor.html)
- [Spring Framework – ExecutorSubscribableChannel Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/ExecutorSubscribableChannel.html)
- [Spring Framework – AbstractMessageChannel Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/AbstractMessageChannel.html)
- [Spring Framework – MessageHandler Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageHandler.html)
