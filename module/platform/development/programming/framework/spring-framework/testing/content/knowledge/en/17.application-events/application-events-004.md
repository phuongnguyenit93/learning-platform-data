# Synchronous Events vs. Execution on an Executor

In Spring, publishing an application event and running listeners are two related operations, not the same thing. By default, Spring invokes listeners directly on the thread publishing the event. If a listener performs slow work, the publish call must also wait. A listener can be moved to an executor to run on a thread pool, but doing so changes completion timing, ordering, error handling, and transaction context.

Understanding this difference helps choose the right approach for each kind of work: tasks that must finish within the current business flow usually fit synchronous listeners; auxiliary tasks that can run independently usually fit an executor; and work that must guarantee zero data loss requires a durable storage and delivery mechanism.

## 1. Publishing Events and Executing Listeners

Spring allows a bean to publish an event via **ApplicationEventPublisher**. Another bean subscribes to the event using **@EventListener**. Since Spring Framework 4.2, an event can be any plain object; extending **ApplicationEvent** is not required.

For example, declaring an event when an order is created:

~~~java
import java.time.Instant;
import java.util.UUID;

public record OrderPlaced(UUID orderId, Instant occurredAt) {
}
~~~

Service publishing the event:

~~~java
import java.time.Instant;
import java.util.UUID;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final ApplicationEventPublisher eventPublisher;

    public OrderService(ApplicationEventPublisher eventPublisher) {
        this.eventPublisher = eventPublisher;
    }

    public void placeOrder(UUID orderId) {
        // Save the order and perform required business steps.
        eventPublisher.publishEvent(
                new OrderPlaced(orderId, Instant.now())
        );
    }
}
~~~

Listener receiving the event:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class OrderAuditListener {

    @EventListener
    public void onOrderPlaced(OrderPlaced event) {
        System.out.println(
                "Audit order " + event.orderId()
                        + " on " + Thread.currentThread().getName()
        );
    }
}
~~~

**publishEvent(...)** sends the event into the ApplicationContext. The ApplicationContext uses **ApplicationEventMulticaster** to find and invoke matching listeners. Under the default configuration, the multicaster is **SimpleApplicationEventMulticaster** and has no asynchronous executor attached to it.

Therefore, the default execution flow looks like this:

~~~text
Thread calling OrderService.placeOrder()
    |
    |-- eventPublisher.publishEvent(event)
            |
            |-- ApplicationEventMulticaster
                    |
                    |-- OrderAuditListener.onOrderPlaced(event)
                    |       (same thread that published the event)
                    |
                    |-- other synchronous listeners
    |
    |-- publishEvent() returns
    |
    |-- placeOrder() continues
~~~

If the listener takes 500 ms to complete, the **publishEvent(...)** call must also wait for roughly that duration. If there are multiple synchronous listeners, the wait time can approach the sum of their execution times.

## 2. Synchronous Execution by Default

Synchronous means the caller only continues after the listener invocation finishes. It does not mean the entire application has only one thread; it only describes the waiting relationship between the event publish call and the listener.

For example:

~~~java
public void placeOrder(UUID orderId) {
    System.out.println("Before publish");

    eventPublisher.publishEvent(
            new OrderPlaced(orderId, Instant.now())
    );

    System.out.println("After publish");
}
~~~

If the listener also logs when it starts and finishes, the observable order is:

~~~text
Before publish
Listener started
Listener finished
After publish
~~~

Key characteristics:

- The listener runs on the thread calling **publishEvent(...)**.
- When **publishEvent(...)** returns, synchronous listeners have already finished executing.
- Listeners are invoked in the order Spring determines; **@Order** or **Ordered** can be used to specify invocation order.
- If a listener throws an exception and the multicaster has no **ErrorHandler**, the exception can propagate back to the **publishEvent(...)** caller; dispatching may also stop before subsequent listeners.
- The listener can use context bound to the current thread, such as a thread-bound transaction.

Synchronous execution usually fits when the listener's result is part of the current processing flow, the listener must finish before the service returns, or the work is short and has predictable execution time. For example: updating internal state, checking simple rules, or recording a change that must be confirmed immediately.

The trade-off is that a slow listener can prolong the request or background job publishing the event. A failing listener can also cause the calling flow to fail if errors are not handled separately.

## 3. Moving Listeners to an Executor

An executor is a mechanism that accepts a task and decides how to run it. An executor may run the task directly on the calling thread, spawn a new thread, or submit the task to a thread pool. Hence, simply passing an executor into configuration is not enough to conclude a task definitely runs on a different thread; actual behavior depends on the chosen executor.

In Spring, there are two common ways to run event listeners on an executor:

1. Use **@Async** on individual listeners that need to run asynchronously.
2. Configure an executor on **SimpleApplicationEventMulticaster** so the multicaster dispatches eligible listeners to the executor.

These two approaches take effect at different points. Choose the one that matches the scope you want to make asynchronous.

### 3.1. Using @Async on Individual Listeners

Declare an executor and enable asynchronous processing support:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class AsyncConfiguration {

    @Bean("applicationEventExecutor")
    public ThreadPoolTaskExecutor applicationEventExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("app-event-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(10);
        return executor;
    }
}
~~~

Annotate the listener you want to offload to the executor with **@Async**:

~~~java
import org.springframework.scheduling.annotation.Async;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class OrderNotificationListener {

    @Async("applicationEventExecutor")
    @EventListener
    public void onOrderPlaced(OrderPlaced event) {
        // Send a notification or perform a time-consuming auxiliary task.
        System.out.println(
                "Notify order " + event.orderId()
                        + " on " + Thread.currentThread().getName()
        );
    }
}
~~~

In this example, the default multicaster still invokes the listener on the publishing thread. However, the call passes through a proxy created by Spring for **@Async**; the proxy submits the method body to **applicationEventExecutor**. Once the task is accepted, the listener call returns and the publishing flow can continue.

**@EnableAsync** enables **@Async** processing. The call must pass through a Spring bean proxy; calling an **@Async** method from another method on the same instance (self-invocation) normally bypasses the proxy and does not produce the expected asynchronous execution. Place the listener in a separate Spring bean and let the ApplicationContext invoke that bean.

The advantage of this approach is that only listeners annotated with **@Async** are sent to the executor. Other listeners continue running synchronously.

### 3.2. Configuring an Executor for SimpleApplicationEventMulticaster

If you want the multicaster to dispatch eligible listeners to an executor, you can declare a bean named **applicationEventMulticaster**:

~~~java
import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.event.SimpleApplicationEventMulticaster;
import org.springframework.core.task.TaskExecutor;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class EventMulticasterConfiguration {

    @Bean(name = "applicationEventMulticaster")
    public SimpleApplicationEventMulticaster applicationEventMulticaster(
            ConfigurableBeanFactory beanFactory,
            @Qualifier("applicationEventExecutor") TaskExecutor executor) {

        SimpleApplicationEventMulticaster multicaster =
                new SimpleApplicationEventMulticaster(beanFactory);
        multicaster.setTaskExecutor(executor);
        return multicaster;
    }
}
~~~

This bean replaces the ApplicationContext's default multicaster. When an event is published, the multicaster submits eligible listener invocations to the configured executor. Listeners that do not support asynchronous execution are still invoked synchronously. In Spring Framework 6.1, transactional event listeners are an important example: they require thread-bound transaction synchronization and are not automatically dispatched to the multicaster's executor.

This approach has a broader impact than **@Async**: other listeners in the same ApplicationContext may also end up running on the executor. Therefore, inspect existing listeners before applying a global configuration.

Do not simultaneously configure an asynchronous multicaster and put **@Async** on the same listener without a deliberate reason. Otherwise, the multicaster may submit the proxy call to the executor a first time, and then the proxy submits the method body to the executor a second time. Two-level dispatching makes execution flow and completion timing harder to follow.

## 4. Comparing Synchronous Flow and Executor-Based Flow

| Aspect | Default Synchronous Listener | Executor-Based Listener |
|---|---|---|
| Execution thread | The thread calling **publishEvent(...)** | Usually an executor thread; depends on the executor type and task rejection policy |
| Return timing | Waits until synchronous listeners finish | Usually returns after the task is submitted or accepted |
| Request duration | Includes listener execution time | Can reduce request wait time |
| Exception in listener | Can propagate to the caller if no **ErrorHandler** is configured | Does not propagate to the publishing thread the same way; requires an executor/listener error-handling mechanism |
| Ordering | Invocation order can be controlled with **@Order** | Task submission order does not guarantee completion order |
| Current transaction | Can participate in the thread-bound transaction | Another thread does not automatically join the publishing thread's transaction |
| Thread-local context | Uses the current thread's context | Does not automatically inherit thread-local values |
| Task lifecycle | Completes before the caller continues | Depends on queue, thread pool, and shutdown process |

An executor is not the same as a durable queue. Tasks in a thread pool usually exist only in the process's memory. If the application stops abruptly, pending tasks can be lost. If the queue is full, the executor may reject tasks or apply another policy such as running the task on the calling thread.

## 5. Differences to Handle in Production Applications

### 5.1. Exceptions and Processing Outcomes

With synchronous listeners, the caller can receive exceptions directly from **publishEvent(...)** if a listener fails and the multicaster has no **ErrorHandler** configured. This can be appropriate when the listener is a mandatory part of the business operation.

With **@Async** listeners, exceptions occur after the task has been submitted, so they cannot propagate back to the publishing thread like a synchronous call. For **void** methods, configure **AsyncUncaughtExceptionHandler** when centralized handling is needed. For a multicaster with an executor, an **ErrorHandler** can be configured on the multicaster to handle errors when listeners are invoked.

Beyond errors inside the listener, consider the case where the executor rejects a task. For example, the queue is full and the rejection policy throws an exception. In that case, task submission can fail immediately when publishing the event. A caller-runs rejection policy can cause some event publications to fall back to synchronous waiting behavior.

Do not just log and ignore errors if the task carries business significance. Explicitly decide whether to retry, persist a failure state, alert operations, or allow the user to try again.

### 5.2. Listener Ordering and Completion Ordering

**@Order** can specify the order in which Spring invokes or submits listeners. When listeners run synchronously, a listener with a lower order value is invoked first and must finish before the calling thread moves to the next listener.

When listeners are submitted to a thread pool, submitting in order does not mean they finish in that order. A fast listener may finish before a listener submitted earlier. If business rules require strict processing order, design a sequential processing flow or a partition/queue mechanism with appropriate ordering guarantees.

### 5.3. Transactions and Commit Timing

Spring transactions are typically bound to the current thread. A synchronous listener invoked on the service's thread can participate in the current transaction, depending on the transaction manager and propagation configuration.

When a listener runs on a thread pool, the publishing thread's transaction is not automatically propagated to the new thread. Several situations can arise:

- The listener runs before the service's transaction commits.
- The listener cannot see uncommitted data from the original transaction.
- The original transaction rolls back, yet the asynchronous listener already performed an external side effect.
- A listener that needs to write data must open its own transaction if required by business rules.

If you only want to handle an event after the transaction commits, use **@TransactionalEventListener**:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderAfterCommitListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderPlaced(OrderPlaced event) {
        // Process only when the transaction that published the event has committed.
    }
}
~~~

By default, a transactional event listener is only invoked when a suitable transaction is active at the time the event is published. If there is no transaction, the listener will not be invoked unless **fallbackExecution** is enabled.

If asynchronous processing after commit is needed, a transaction-bound listener can be deliberately combined with **@Async**. The handler body runs on a different thread and does not inherit the committed transaction; if it needs to write data, open a new appropriate transaction. In particular, do not expect a global executor configuration on the multicaster to automatically move transactional event listeners to a thread pool.

### 5.4. Thread-Local Context

Thread-bound data such as logging MDC, **SecurityContext**, request context, or transaction state does not automatically appear on executor threads. If a listener needs this data, pass the necessary business data directly in the event or configure an appropriate context propagation mechanism, such as a **TaskDecorator** for the executor.

Avoid passing the entire request object or short-lived objects into tasks that run after the request if they were not designed for use outside the request. Events should contain the necessary data and have a clear lifecycle.

### 5.5. Queues, Resource Limits, and Shutdown

Thread pools need bounded thread counts and queue capacities. An unbounded queue can cause memory to grow continuously when the event publication rate exceeds the processing rate. An overly large pool can cause contention for CPU, database connections, or shared resources.

When designing an executor, specify:

- Concurrency level appropriate to the task type.
- Maximum queue capacity.
- Policy when the queue is full.
- Wait time during application shutdown.
- How to monitor active tasks, queue size, rejected tasks, and processing duration.

**setWaitForTasksToCompleteOnShutdown(true)** and **setAwaitTerminationSeconds(...)** help Spring wait for a period of time so running tasks can finish on shutdown. They do not turn a thread pool into durable storage and do not guarantee tasks survive process or host crashes.

## 6. Testing Synchronous and Asynchronous Listeners

When testing, verify both functional behavior and how the listener is executed. Do not use **Thread.sleep(...)** to wait for asynchronous tasks because fixed wait times can make tests slow and flaky. Use **CountDownLatch**, **CompletableFuture**, or Awaitility to synchronize the test with the task.

For synchronous listeners, you can capture the thread name and assert immediately after publishing the event:

~~~java
String publishingThread = Thread.currentThread().getName();

eventPublisher.publishEvent(
        new OrderPlaced(orderId, Instant.now())
);

assertEquals(publishingThread, listenerThreadName.get());
~~~

For an **@Async** listener, the listener can record the thread name and count down a latch:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.scheduling.annotation.Async;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class AsyncOrderProbe {

    private final CountDownLatch completed = new CountDownLatch(1);
    private final AtomicReference<String> threadName = new AtomicReference<>();

    @Async("applicationEventExecutor")
    @EventListener
    public void onOrderPlaced(OrderPlaced event) {
        threadName.set(Thread.currentThread().getName());
        completed.countDown();
    }

    public CountDownLatch completed() {
        return completed;
    }

    public String threadName() {
        return threadName.get();
    }
}
~~~

The test can wait for the listener to complete and then compare threads:

~~~java
String publishingThread = Thread.currentThread().getName();

eventPublisher.publishEvent(
        new OrderPlaced(orderId, Instant.now())
);

assertTrue(asyncOrderProbe.completed().await(2, TimeUnit.SECONDS));
assertNotEquals(publishingThread, asyncOrderProbe.threadName());
~~~

The example above illustrates the verification technique; in a real test suite, reset the latch and probe state for each test run so state from an earlier test does not affect later tests. The wait timeout should be generous enough for CI environments while remaining finite so tests do not hang.

Scenarios to test:

1. Synchronous listeners complete before the service continues.
2. **@Async** listeners are invoked on the expected executor.
3. Listener exceptions are handled according to the chosen configuration.
4. Full queues or executor task rejections are handled explicitly.
5. Transaction-dependent listeners run in the right phase.
6. Tests with **@Transactional** do not accidentally roll back and prevent **AFTER_COMMIT** listeners from firing. Default transactional tests typically roll back at the end; if you need to test post-commit behavior, explicitly commit the transaction in the test.

Do not only check that the listener was called. For asynchronous listeners, also verify the execution thread, completion timing, and behavior when errors occur.

## 7. Choosing the Right Approach

| Requirement | Appropriate Approach |
|---|---|
| Short listener that must finish before the service returns | Default synchronous **@EventListener** |
| Only a few auxiliary listeners allowed to run in the background | **@Async** on individual listeners |
| Most listeners in an ApplicationContext need an executor | Configure an executor on **SimpleApplicationEventMulticaster**, after checking special listeners |
| Process only after transaction commit | **@TransactionalEventListener(phase = AFTER_COMMIT)** |
| Process after commit without slowing down the commit thread | Transactional listener combined with an explicitly configured and tested async mechanism |
| Task must be redelivered after application restart | Durable queue, message broker, or Transactional Outbox |
| Processing order required per business key | Partitioned queue or sequential worker per key |

Spring application events primarily serve communication within the same ApplicationContext and the same process. Using an executor only changes execution within that process; it does not provide durable persistence, post-restart retries, delivery acknowledgments, or cross-service communication.

If an event represents a business obligation that must not be lost, such as sending an invoice, charging payment, or syncing order status to another system, consider Transactional Outbox or a message broker. With Outbox, the application writes business data and the outbound record in the same transaction; a separate process reads that record and sends it, with retry and status-tracking mechanisms.

## 8. Common Misconceptions

- **Calling publishEvent(...) does not mean asynchronous.** By default, listeners are called synchronously on the publishing thread.
- **@EventListener does not create a new thread on its own.** To run a listener on an executor, use **@Async** and enable **@EnableAsync**, or configure the multicaster.
- **Having an executor does not guarantee execution on a different thread.** An executor may run directly on the calling thread; a rejection policy may also run tasks on the calling thread.
- **@Order does not guarantee completion order when running concurrently.** It only helps determine the order in which listeners are invoked or submitted.
- **Transactions do not automatically propagate across a thread pool.** New worker threads need their own transaction if transactional operations are required.
- **A thread pool is not a message broker.** An in-memory queue does not guarantee tasks survive process termination.
- **@Async does not propagate exceptions back to the event publisher.** Design an appropriate error receiver and handler.
- **Do not make every listener asynchronous by default.** Choose async scope based on processing duration, dependencies, transaction requirements, and task criticality.

## 9. Conclusion

Spring application events run synchronously by default: the publishing thread invokes listeners and waits for them to finish. **@Async** moves specifically annotated listeners to an executor; an executor on **SimpleApplicationEventMulticaster** changes dispatching for eligible listeners.

When moving from synchronous execution to an executor, redesign how you observe errors, completion ordering, transactions, thread-local context, queue bounds, and shutdown. Keep synchronous execution for work whose result is needed immediately in the current flow, use an executor for decoupled auxiliary tasks, and use a durable delivery mechanism when business rules require zero event loss.
