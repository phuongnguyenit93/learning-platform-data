# ExecutorSubscribableChannel with Direct or Executor-Based Dispatch

## Objectives

After this lesson, you will be able to:

- Explain the role of `ExecutorSubscribableChannel` in Spring Messaging.
- Distinguish direct dispatch on the sending thread from dispatch through an `Executor`.
- Understand why a message is delivered to all registered subscribers.
- Correctly interpret the `send()` result, processing order, and exceptions in both modes.
- Configure a bounded executor using `ThreadPoolTaskExecutor`.
- Use `ChannelInterceptor` and `ExecutorChannelInterceptor` with the proper lifecycle.
- Recognize the limits around transactions, context, back-pressure, and durability when processing on an executor.

## 1. What Is ExecutorSubscribableChannel?

`ExecutorSubscribableChannel` resides in the package:

~~~java
org.springframework.messaging.support.ExecutorSubscribableChannel
~~~

It is an implementation of `SubscribableChannel`. A `SubscribableChannel` maintains a list of registered `MessageHandler`s; when the channel receives a message, it invokes those handlers.

The defining characteristic of `ExecutorSubscribableChannel` is that it **delivers the message to each subscriber**. The channel has two dispatch modes:

- Without an executor configured: invokes handlers directly on the thread calling `send()`.
- With an executor configured: creates one task per subscriber and submits the task through the provided executor.

~~~text
Producer
   |
   | send(message)
   v
ExecutorSubscribableChannel
   |
   +---- Subscriber A
   |
   +---- Subscriber B
   |
   +---- Subscriber C

Without Executor:
  A -> B -> C invoked on the sending thread

With Executor:
  task A -> Executor
  task B -> Executor
  task C -> Executor
~~~

Because it sends to all subscribers, a single message can trigger multiple handlers. Keep this in mind when comparing with channels that select a single consumer.

## 2. Direct Mode: Processing on the Sending Thread

Use the no-argument constructor:

~~~java
ExecutorSubscribableChannel channel =
        new ExecutorSubscribableChannel();
~~~

Or pass `null` as the executor:

~~~java
ExecutorSubscribableChannel channel =
        new ExecutorSubscribableChannel(null);
~~~

When the producer calls `send(message)`, the channel iterates through the subscribers and runs each subscriber's task directly on the calling thread. Therefore:

1. Handlers begin before `send()` returns.
2. Handlers are invoked sequentially on the same thread.
3. The execution time of all handlers adds to the duration of the `send()` call.
4. Exceptions from a handler can propagate back to the producer through `send()`.
5. If one handler throws an exception, the synchronous dispatch pass may stop at that handler and subsequent subscribers will not be invoked during that send pass.

Example:

~~~java
ExecutorSubscribableChannel channel =
        new ExecutorSubscribableChannel();

channel.subscribe(message ->
        System.out.println("Audit: " + message.getPayload()));

channel.subscribe(message ->
        System.out.println("Metrics: " + message.getPayload()));

channel.send(MessageBuilder.withPayload("ORD-1001").build());
~~~

Output:

~~~text
Audit: ORD-1001
Metrics: ORD-1001
~~~

Both subscribers receive the same message. They run synchronously on the sending thread; the producer continues only after the handlers finish or an exception interrupts the dispatch pass.

### When to Use Direct Mode?

This mode fits when:

- Handlers are lightweight and need to complete within the current flow.
- You want exceptions from handlers to be observed immediately at the `send()` call site.
- You need a simple execution flow that is easy to debug.
- You do not want to add an executor and thread-switching overhead.

Do not use it when handlers perform slow I/O, call external APIs, or do heavy CPU work that prolongs the request thread. A slow handler will slow down the producer and any handlers invoked after it.

## 3. Executor-Based Mode

Pass an object implementing `java.util.concurrent.Executor`:

~~~java
Executor executor = Executors.newFixedThreadPool(4);

ExecutorSubscribableChannel channel =
        new ExecutorSubscribableChannel(executor);
~~~

When `send(message)` is called, the channel creates a task for each subscriber and calls `executor.execute(task)`. The executor decides which thread runs the task and when.

With a multi-worker thread pool:

- Subscribers can process concurrently.
- The producer generally does not wait for handlers to finish.
- Completion order is not guaranteed.
- The executor can queue tasks, spawn new threads, or reject tasks according to its configuration.

Distinguish `Executor` from a specific thread pool. The `Executor` interface does not guarantee asynchronous execution: an implementation may run tasks immediately on the calling thread. For example, `Runnable::run` is a synchronous executor:

~~~java
Executor directExecutor = Runnable::run;

ExecutorSubscribableChannel channel =
        new ExecutorSubscribableChannel(directExecutor);
~~~

Thus, threading behavior depends on the actual executor implementation, not merely on whether the constructor accepts an argument.

### Meaning of send() When Using an Executor

With an asynchronous executor, `send()` usually returns after the tasks have been submitted to the executor, before the handlers finish.

`send()` does not return a `Future` for each subscriber and does not provide an aggregated result indicating all handlers succeeded. A `true` value is not business confirmation that all subscribers finished processing.

If the producer needs to know the outcome of asynchronous work, design a separate feedback mechanism such as a callback, an application-managed future, a reply message, or a status persisted in the business system.

## 4. Comparing the Two Modes

| Criterion | Without Executor | With Asynchronous Executor |
|---|---|---|
| Thread running handler | Thread calling `send()` | Thread decided by the executor |
| Execution timing | Immediately during the send call | After the task is accepted by the executor; may run immediately or later |
| Relationship to `send()` | `send()` waits for handlers to finish | `send()` typically does not wait for handlers to complete |
| Subscribers | Delivers to each subscriber | Creates a separate task for each subscriber |
| Concurrency | Handlers run sequentially | Can run in parallel if the executor has multiple workers |
| Completion order | Follows sequential invocation order | Not guaranteed under parallel execution |
| Handler exceptions | Can propagate back to the `send()` caller | Usually occur inside the executor task/thread |
| Resources | Uses the current thread | Uses the executor's threads, queue, and resources |
| Back-pressure | Slow handlers directly slow down the producer | Depends on queue, pool, and task rejection policy |

Configuring a single-thread executor still dispatches through the executor, but tasks are processed sequentially on one worker. A multi-thread executor allows parallel processing, at the cost of having to account for race conditions and completion order.

## 5. Configuring via Java Configuration

In a Spring application, you can register the channel and executor as beans. `ThreadPoolTaskExecutor` is Spring's implementation that lets you configure the thread pool, queue, and shutdown lifecycle.

~~~java
package demo.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.support.ExecutorSubscribableChannel;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class MessagingConfiguration {

    @Bean
    public ExecutorSubscribableChannel directOrdersChannel() {
        return new ExecutorSubscribableChannel();
    }

    @Bean
    public ThreadPoolTaskExecutor messagingExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("messaging-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(10);
        return executor;
    }

    @Bean
    public ExecutorSubscribableChannel asyncOrdersChannel(
            ThreadPoolTaskExecutor messagingExecutor) {
        return new ExecutorSubscribableChannel(messagingExecutor);
    }
}
~~~

Points to understand:

- `directOrdersChannel` uses the sending thread.
- `asyncOrdersChannel` uses `messagingExecutor`.
- `corePoolSize` is the core thread count.
- `maxPoolSize` is the maximum thread limit.
- `queueCapacity` bounds the number of tasks waiting in the queue.
- `threadNamePrefix` helps identify workers in logs and thread dumps.
- `waitForTasksToCompleteOnShutdown` and `awaitTerminationSeconds` support an orderly shutdown.

Spring manages the lifecycle of the `ThreadPoolTaskExecutor` bean; you do not need to call `initialize()` manually inside the `@Bean` method. When injecting a channel by type, the application has two beans of type `ExecutorSubscribableChannel`; use `@Qualifier` or the bean name to select the right channel.

Example:

~~~java
@Component
public class OrderPublisher {

    private final ExecutorSubscribableChannel channel;

    public OrderPublisher(
            @Qualifier("asyncOrdersChannel")
            ExecutorSubscribableChannel channel) {
        this.channel = channel;
    }

    public void publish(String orderId) {
        channel.send(MessageBuilder.withPayload(orderId).build());
    }
}
~~~

This configuration does not require `@EnableAsync`. `@Async` is a separate method-invocation proxy mechanism; `ExecutorSubscribableChannel` dispatches subscribed `MessageHandler`s through the executor passed to its constructor.

## 6. Complete Java 17 Example: Observing Threads and When send() Returns

The example uses Spring Framework 6.2.18 and JDK 17. The program creates a direct channel and a channel backed by a single-thread executor. A latch holds the asynchronous handler in a waiting state so you can observe that `send()` can return before the handler finishes.

Directory structure:

~~~text
executor-subscribable-channel-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ExecutorSubscribableChannelDemo.java
~~~

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>executor-subscribable-channel-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
            <version>6.2.18</version>
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

File `src/main/java/demo/ExecutorSubscribableChannelDemo.java`:

~~~java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.ExecutorSubscribableChannel;
import org.springframework.messaging.support.MessageBuilder;

public class ExecutorSubscribableChannelDemo {

    public static void main(String[] args) throws InterruptedException {
        Thread caller = Thread.currentThread();
        Message<String> message =
                MessageBuilder.withPayload("ORD-1001").build();

        // Direct mode: handler runs on the thread calling send().
        ExecutorSubscribableChannel directChannel =
                new ExecutorSubscribableChannel();

        directChannel.subscribe(incoming ->
                System.out.printf(
                        "direct handler on caller=%s, payload=%s%n",
                        Thread.currentThread() == caller,
                        incoming.getPayload()
                ));

        boolean directSent = directChannel.send(message);
        System.out.println("direct send returned=" + directSent);

        // Executor mode: handler runs on a worker thread.
        ExecutorService executor = Executors.newSingleThreadExecutor(
                task -> new Thread(task, "message-worker")
        );

        CountDownLatch handlerStarted = new CountDownLatch(1);
        CountDownLatch allowHandlerToFinish = new CountDownLatch(1);
        CountDownLatch handlerFinished = new CountDownLatch(1);

        try {
            ExecutorSubscribableChannel executorChannel =
                    new ExecutorSubscribableChannel(executor);

            executorChannel.subscribe(incoming -> {
                System.out.printf(
                        "executor handler on caller=%s, payload=%s%n",
                        Thread.currentThread() == caller,
                        incoming.getPayload()
                );

                handlerStarted.countDown();

                try {
                    if (!allowHandlerToFinish.await(5, TimeUnit.SECONDS)) {
                        throw new IllegalStateException(
                                "Timed out waiting for the main thread"
                        );
                    }
                    System.out.println("executor handler completed");
                }
                catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException(ex);
                }
                finally {
                    handlerFinished.countDown();
                }
            });

            boolean executorSent = executorChannel.send(message);

            if (!handlerStarted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Handler did not start");
            }

            System.out.println(
                    "executor send returned before handler completed="
                            + executorSent
            );

            allowHandlerToFinish.countDown();

            if (!handlerFinished.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Handler did not finish");
            }
        }
        finally {
            allowHandlerToFinish.countDown();
            executor.shutdown();

            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
~~~

Run from the directory containing `pom.xml`:

~~~bash
mvn -q compile org.codehaus.mojo:exec-maven-plugin:3.5.0:java -Dexec.mainClass=demo.ExecutorSubscribableChannelDemo
~~~

Stdout output:

~~~text
direct handler on caller=true, payload=ORD-1001
direct send returned=true
executor handler on caller=false, payload=ORD-1001
executor send returned before handler completed=true
executor handler completed
~~~

How to read the output:

1. The direct handler runs on the same thread as `main`.
2. The executor handler runs on the `message-worker` thread.
3. The asynchronous handler signals that it started, then waits on the latch.
4. The main thread observes that `send()` has already returned while the handler is still waiting.
5. The main thread releases the latch, and only then does the handler finish.

This example intentionally uses `CountDownLatch` to demonstrate the timing relationship. In a real application, do not use latches to coordinate message production/consumption unless there is an explicit synchronization need.

## 7. A Single Message Sent to Multiple Subscribers

`ExecutorSubscribableChannel` is a broadcast channel across the subscriber list. Every subscriber receives the same input message. When an executor is present, the channel creates a separate task for each subscriber.

~~~java
ExecutorSubscribableChannel channel =
        new ExecutorSubscribableChannel(executor);

MessageHandler auditHandler = message ->
        audit(message.getPayload());

MessageHandler metricsHandler = message ->
        recordMetric(message.getPayload());

channel.subscribe(auditHandler);
channel.subscribe(metricsHandler);

channel.send(MessageBuilder.withPayload("ORD-1001").build());
~~~

Both handlers are invoked. If the executor has multiple workers, they may run concurrently. Therefore:

- Do not rely on completion order to establish business dependencies between subscribers.
- Do not let multiple subscribers concurrently mutate the same mutable object inside the payload.
- If handler B must run after handler A's result, build a flow or orchestration that makes that dependency explicit.
- If a message should be received by only one consumer in a group, choose a channel with appropriate point-to-point semantics.

### Comparison with Easily Confused Channels

| Channel | Module | Message delivery | Executor support |
|---|---|---|---|
| `ExecutorSubscribableChannel` | Spring Messaging | All subscribers | Yes, via constructor |
| `DirectChannel` | Spring Integration | Selects one subscriber per message | Not the channel's default executor mechanism |
| `PublishSubscribeChannel` | Spring Integration | All subscribers | Can configure a TaskExecutor |
| `ExecutorChannel` | Spring Integration | Selects one subscriber per message | Has a TaskExecutor |

The names `ExecutorSubscribableChannel` and `ExecutorChannel` sound similar, but their delivery semantics differ. Read the exact package and channel contract before swapping implementations.

## 8. Exceptions and Error Handling

### Without Executor

In direct mode, handlers are invoked on the sending thread. If a handler throws a `MessagingException`, the exception can propagate back to the caller. Other exceptions may be wrapped by Spring in a `MessageDeliveryException`.

This lets the producer see errors immediately, but it also means a failing handler can cause the send call to fail and prevent subsequent subscribers from being invoked during that dispatch pass.

~~~java
try {
    channel.send(message);
}
catch (MessageDeliveryException ex) {
    // Log, forward the error, or handle at the call site.
}
~~~

### With Executor

With an asynchronous executor, handler exceptions occur in a task running on a worker thread. The caller of `send()` normally does not receive that exception because `send()` already returned before the task finished.

An appropriate observation and error-handling strategy is required:

- Catch exceptions inside the handler when you need to record a business error or emit an error event.
- Use logging and metrics with a correlation ID to trace each message.
- Configure the executor and an appropriate uncaught exception policy.
- If retries are needed, implement bounded retries with idempotency at the business layer.
- If the producer needs feedback on processing results, use a reply/callback or a separate processing status.

Do not treat the executor accepting a task as proof that the handler succeeded.

### When the Executor Rejects a Task

An executor can reject a task when it has shut down or exhausted capacity according to its rejection policy. Understand the behavior of the Spring implementation in use: in the current source, `ExecutorSubscribableChannel` catches `RejectedExecutionException` and runs that task directly on the sending thread as a fallback. Thus, when the pool is overloaded or shutting down, the handler can unexpectedly execute on the producer thread and prolong `send()`.

The executor may also be configured with `CallerRunsPolicy`, which runs the task on the sending thread upon rejection. Test the actual policy of your chosen version and executor; do not assume every handler always runs on a worker thread.

## 9. ChannelInterceptor and ExecutorChannelInterceptor

Spring Messaging provides two interceptor levels with different lifecycles.

### ChannelInterceptor

`ChannelInterceptor` observes or modifies messages at the channel level, with callbacks such as:

- `preSend`: before the channel sends the message.
- `postSend`: right after the channel performs send.
- `afterSendCompletion`: after the entire send operation completes or fails.

With an executor-backed channel, callbacks around `send()` belong to the sending flow. Therefore `postSend` and `afterSendCompletion` can run before subscribers finish asynchronous processing.

### ExecutorChannelInterceptor

`ExecutorChannelInterceptor` extends `ChannelInterceptor` and adds per-subscriber callbacks:

- `beforeHandle`: runs inside the task, right before invoking the handler.
- `afterMessageHandled`: runs inside the task after the handler finishes, even if the handler throws an exception.

You can use this interceptor to set up and clean up context bound to the worker thread, such as MDC or a custom context:

~~~java
public class WorkerContextInterceptor
        implements ExecutorChannelInterceptor {

    @Override
    public Message<?> beforeHandle(
            Message<?> message,
            MessageChannel channel,
            MessageHandler handler) {
        // Set up context for the current subscriber.
        return message;
    }

    @Override
    public void afterMessageHandled(
            Message<?> message,
            MessageChannel channel,
            MessageHandler handler,
            Exception ex) {
        // Clean up the worker thread's context.
    }
}
~~~

If `beforeHandle` returns `null`, the corresponding handler will not be invoked. If resource cleanup is needed, put the logic in `afterMessageHandled` and ensure context state is restored even when an exception occurs.

## 10. Thread Context and Transactions

Offloading processing to an executor means handlers may run on a different thread. Do not assume data bound to the producer thread automatically appears on the worker:

- `ThreadLocal` and MDC are not copied automatically.
- Security context needs an appropriate context propagation mechanism if required by the application.
- Transactions bound to the current thread do not automatically transfer to the worker thread.
- Request-scoped state or framework context may no longer be available.

If a handler needs a database transaction, start the transaction at the handler's processing boundary, for example by calling a Spring-managed service with `@Transactional`. Do not rely on the transaction of the thread that called `send()`.

You can use `TaskDecorator` on `ThreadPoolTaskExecutor` to copy and restore certain contexts such as MDC. For security context, use Spring Security's built-in integration rather than arbitrarily copying security objects yourself.

## 11. Back-Pressure, Ordering, and Durability Limits

### Queue and Pool Capacity

An executor typically uses a queue to hold waiting tasks. If producers create tasks faster than workers process them, the queue grows.

Configure explicitly:

- Core pool size and maximum pool size.
- Finite queue capacity.
- Rejection policy.
- Thread naming and metrics.
- Shutdown timeout and how remaining tasks are handled.

An unbounded queue can accumulate tasks until the heap is exhausted. Too small a queue can cause frequent task rejections. Choose values based on processing duration, producer rate, subscriber count, and actual resources.

### Ordering

Without an executor, handlers are invoked sequentially on the sending thread. With a multi-worker executor, completion order may differ from submission order.

If the business requires ordering:

- Use a single-thread executor for flows that must be sequential.
- Use locking or partitioning by business key when parallelism across groups is needed while keeping order within each group.
- Design idempotent handlers and check versions/sequences if messages can arrive out of order.

Do not use a shared multi-thread executor and assume messages for the same order will always complete in send order.

### Not Durable Messaging

`ExecutorSubscribableChannel` and the executor's internal queue live in the current process. They do not provide:

- Persistent message storage across restarts.
- Redelivery from a broker.
- Dead-letter queues.
- Event replay.
- Communication across JVMs or services.

If the application stops while tasks remain in the executor queue, tasks may be lost depending on the shutdown policy. When durable delivery, broker-level retries, or cross-process communication are required, use RabbitMQ, Kafka, JMS, or an appropriate transport. An executor only determines how handlers run within the application.

## 12. Common Mistakes

1. **Assuming the Executor constructor always creates new threads.** An executor can run synchronously; check the implementation passed in.
2. **Assuming `send()` waits for handlers to finish in all cases.** With an asynchronous executor, `send` usually only waits for task submission.
3. **Assuming a message goes to only one subscriber.** `ExecutorSubscribableChannel` invokes every registered subscriber.
4. **Confusing it with Spring Integration `ExecutorChannel`.** `ExecutorChannel` picks one subscriber per message; `ExecutorSubscribableChannel` sends to all subscribers.
5. **Using an unbounded pool.** Task backlogs can grow heap and latency; configure a finite queue capacity.
6. **Relying on completion order with multiple workers.** Handlers can run concurrently and finish out of order.
7. **Expecting asynchronous exceptions at the caller.** Exceptions can occur on a worker thread after `send` has returned.
8. **Not handling rejection or shutdown.** Tasks may fall back to running on the caller thread or be subject to the executor's rejection policy.
9. **Assuming transactions and `ThreadLocal` propagate to workers.** They are thread-bound and require explicit context propagation mechanisms.
10. **Using the channel as a durable broker.** The executor queue lives in process memory; there is no durability or replay.
11. **Having interdependent subscribers while dispatching concurrently.** Build a sequential flow or explicit orchestration if ordering is a business requirement.
12. **Skipping cleanup in interceptors.** Context or resources bound to a worker must be restored even when a handler fails.

## 13. Selection and Operations Checklist

- [ ] Determine whether all subscribers need to receive the same message.
- [ ] Choose direct handling if handlers are lightweight and the caller needs to wait for the outcome.
- [ ] Choose an executor if processing time must be decoupled from the sending thread.
- [ ] Verify whether the executor is genuinely asynchronous or may run tasks inline.
- [ ] Set finite core pool size, max pool size, and queue capacity.
- [ ] Choose a rejection policy and check the fallback behavior of the Spring version in use.
- [ ] Define how exceptions from workers are logged and handled.
- [ ] Use `ExecutorChannelInterceptor` for per-subscriber context when needed.
- [ ] Design processing order and idempotency for concurrent handlers.
- [ ] Start transactions in the worker's processing service if needed.
- [ ] Monitor active threads, queue depth, rejected tasks, processing time, and handler errors.
- [ ] Choose a broker if durability, replay, persistent retries, or inter-process communication is required.

## 14. Conclusion

`ExecutorSubscribableChannel` is a `SubscribableChannel` in Spring Messaging that delivers each message to all registered subscribers. The no-argument constructor runs handlers on the sending thread; the constructor taking an `Executor` delegates dispatch to the executor. Direct mode makes errors and ordering easy to observe, but makes the producer wait for handlers. Executor mode decouples processing from the producer, but requires managing pools, queues, exceptions, ordering, and context. Keep in mind this is in-process dispatch; when durable storage or inter-service communication is needed, an appropriate transport must be used.

## Official References

- [Spring Framework 6.2.18 Javadoc: ExecutorSubscribableChannel](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/support/ExecutorSubscribableChannel.html) — delivery semantics to all subscribers and the two constructors.
- [Spring Framework 6.2.18 Javadoc: SubscribableChannel](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/SubscribableChannel.html) — registering and unregistering `MessageHandler`s.
- [Spring Framework 6.2.18 Javadoc: ExecutorChannelInterceptor](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/support/ExecutorChannelInterceptor.html) — callbacks before and after each subscriber processes a message inside an executor task.
- [Spring Framework Reference 6.2: Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html) — `TaskExecutor`, `ThreadPoolTaskExecutor`, queue capacity, and rejection policies.
- [Spring Framework Javadoc: ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html) — thread pool configuration and management.
- [Spring Framework source: ExecutorSubscribableChannel](https://github.com/spring-projects/spring-framework/blob/main/spring-messaging/src/main/java/org/springframework/messaging/support/ExecutorSubscribableChannel.java) — how tasks are submitted per subscriber and fallback on executor rejection.
