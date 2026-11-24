# Errors in Spring Application Events Async Listeners: Mechanics, Rollback, and Safe Handling

## 1. Why Are Errors in Async Listeners a Separate Problem?

Spring Application Events enable a component to publish an event and interested listeners to react to it. With standard synchronous dispatch, the publisher calls `publishEvent(...)` and listeners execute on the same thread. When a listener throws an unhandled exception, that exception can propagate back to the publisher. If the publisher is inside an appropriate transaction, the error can affect the commit or rollback decision.

When a listener runs **asynchronously** via `@Async` or an executor configured on the multicaster, that relationship changes: the publisher can return **before** the listener's work finishes. An error raised later inside the worker no longer automatically propagates back onto the caller's stack. A system that merely puts `try/catch` around `publishEvent(...)` can easily assume it caught every error while the listener task actually failed on another thread.

Business example:

~~~text
OrderService.placeOrder()
        |
        | save order in transaction
        | publish(OrderPlaced)
        v
  Async notification listener ------------> Email provider
        |                                       |
        | returns control                       +-- timeout / 503
        v
  OrderService may have already returned
  and transaction may have committed
~~~

If sending the email is only an auxiliary task, not rolling back the order may be desirable. However, if the email is a result that must be delivered reliably, merely adding `@Async` and ignoring exceptions **lacks a recovery mechanism**. You must distinguish launch failures, execution failures, rollback, retries, and message durability.

**Lesson objectives:** pinpoint where each error occurs; choose the right `AsyncUncaughtExceptionHandler`, multicaster `ErrorHandler`, or `Future` monitoring; understand why async exceptions do not automatically roll back the publisher; and design retry/outbox/idempotency for work that must not be lost.

## 2. Three Concepts You Must Keep Separate

### 2.1. Publishing Does Not Mean Completion

`ApplicationEventPublisher.publishEvent(Object)` submits an event into the `ApplicationContext`'s dispatch mechanism. It is not an API confirming that business tasks have finished, let alone a promise of durable event persistence. The publish call returning **is not sufficient** to conclude that an async listener succeeded.

### 2.2. @Async Differs from a Multicaster With a TaskExecutor

There are two common ways to process events off the publishing thread:

1. **`@Async` on an `@EventListener` method:** annotation-driven async support creates a proxy and hands the method invocation off to the selected executor. For `void` methods, errors inside the body are handled via Spring's async exception mechanism.
2. **`SimpleApplicationEventMulticaster.setTaskExecutor(...)`:** the multicaster itself can delegate listener invocations to an executor. In that case, the error-handling path is tied to the multicaster, the executor, and the multicaster's `ErrorHandler`. Not every listener is permitted to run async this way; some listeners require running on the publisher thread.

Both mechanisms can coexist, though doing so complicates thread and error boundaries. Do not configure both simultaneously thinking "double async is faster."

### 2.3. Worker Exceptions Differ from Task Submission Errors

Distinguish:

- **Errors before/around publish time:** e.g., event construction code throws; this happens immediately at the publisher.
- **Errors when submitting the task:** the executor is shutting down or the queue is full; `TaskRejectedException`/`RejectedExecutionException` can appear on the scheduling path depending on the executor and configuration. Some implementations have fallback strategies when rejecting tasks; do not assume every rejection is always thrown in the same way.
- **Errors inside the already running listener body:** e.g., the email gateway returns 503; with `@Async void`, this error does not automatically return to a `try/catch` around publish.
- **Errors during post-processing/error recording:** even an error handler can encounter errors. Thus logging an exception alone does not mean the work was recovered.

Comparison table:

| Execution path | Exception in handler body | Typical impact on publisher |
| --- | --- | --- |
| Synchronous listener, no swallowing `ErrorHandler` | Can propagate through multicaster | Caller can catch it; transaction can roll back per rules |
| `@Async void` listener, task actually started | `AsyncUncaughtExceptionHandler` handles uncaught exceptions in method | Publisher has usually already returned; does not receive the same exception |
| Listener run by multicaster's executor | Exception belongs to task/executor or handled by multicaster `ErrorHandler` | Usually does not propagate from worker back to publisher |
| Task submission fails before task runs | Per executor/implementation policy | Can surface immediately during publish or hit fallback |
| Synchronous listener with suppressing `ErrorHandler` | Handler may log and not rethrow | Publisher may see no error even though listener failed |

**The word "typical" is intentional:** an executor might use `CallerRunsPolicy` or a multicaster might have a fallback; that is no longer the same behavior as successfully offloading the task to another thread.

## 3. How Does @Async @EventListener Actually Work?

Minimal configuration in a Spring application requires a listener bean, async support enabled, and an explicit executor:

~~~java
@Configuration
@EnableAsync
public class EventsConfiguration {
    @Bean("eventExecutor")
    ThreadPoolTaskExecutor eventExecutor() {
        ThreadPoolTaskExecutor executor =
            new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("event-");
        executor.initialize();
        return executor;
    }
}
~~~

The example above is a **configuration fragment inside a Spring application**, not a standalone Java file; imports for `Configuration`, `EnableAsync`, `Bean`, and `ThreadPoolTaskExecutor` are required. The name `eventExecutor` matches `@Async("eventExecutor")`.

~~~java
@Component
public class EmailListener {
    @Async("eventExecutor")
    @EventListener
    public void onOrderPlaced(OrderPlaced event) {
        emailService.sendOrderConfirmation(event.orderId());
    }
}
~~~

This is also **illustrative code**: the application must define `OrderPlaced`, `emailService`, imports, and DI configuration. When the async proxy works properly, the `onOrderPlaced` body runs on the executor and the publisher does not wait for the result.

### Conditions for @Async to Apply Properly

- `@EnableAsync` or equivalent configuration is present.
- The listener method is registered by Spring on a container-managed bean; instantiating `new EmailListener()` manually without bean registration will not activate the listener mechanism.
- Proxy configuration must allow intercepting the method; avoid `final` classes/methods that block subclass proxying, private methods, or proxy-incompatible setups.
- The executor name `eventExecutor` must match the configured bean.
- When an async method is called **internally from another method on the same object** via `this.someAsyncMethod()`, standard self-invocation bypasses the Spring proxy. `@EventListener` is dispatched by Spring through the listener bean, though other self-invocation calls still require attention.
- If the listener also needs `@Transactional`, separate the transactional service and check interceptor order, thread, and actual transaction.

**Do not use thread name as the sole proof of async.** Thread names aid debugging, but correctness must be verified via behavior, executor, and tests.

## 4. Handling Exceptions from @Async void

For an `@Async` method returning `void`, the caller has no `Future` to inspect errors. Spring provides the `AsyncUncaughtExceptionHandler` interface:

~~~java
public interface AsyncUncaughtExceptionHandler {
    void handleUncaughtException(
        Throwable ex,
        Method method,
        Object... params
    );
}
~~~

This is the main signature, not a full interface definition to copy verbatim. The handler receives:

- `ex`: exception or throwable from the async method body.
- `method`: metadata for the failing method.
- `params`: call arguments, requiring care as they may contain sensitive data.

A handler can be supplied via `AsyncConfigurer#getAsyncUncaughtExceptionHandler()`. If you do not supply one, Spring has a default mechanism to log errors per logging configuration; **do not rely solely on default logging as a retry policy**.

Example handler in a project:

~~~java
@Override
public AsyncUncaughtExceptionHandler
        getAsyncUncaughtExceptionHandler() {
    return (ex, method, params) -> {
        logger.error(
            "Async listener failed at {}",
            method.getName(), ex
        );
        metrics.counter("event_listener_failure").increment();
    };
}
~~~

This is **illustrative code**; `logger` and `metrics` must be configured. The handler here observes errors but **does not automatically retry, mark the task failed in durable storage, or forward the error back to the publisher**.

If the task has critical business significance, design additional retry, dead-letter, status tracking, or a durable delivery system rather than assuming "handler logged it = error handled."

## 5. Complete Java 17+ Example: Async Error Caught at Worker, Not Publisher

This example uses Java 17+, Maven, and Spring Framework **6.2.8**. It does not require Spring Boot, a database, or a real email provider.

Idea:

1. Main publishes `OrderPlaced`.
2. The `@Async` listener is handed off to `ThreadPoolTaskExecutor`.
3. The listener waits on a `CountDownLatch` so main can print `PUBLISH_RETURNED` first, keeping output deterministic.
4. Main opens the latch; the listener prints `LISTENER...` and then intentionally throws `IllegalStateException`.
5. Custom `AsyncUncaughtExceptionHandler` prints the error and signals completion.
6. Main observes the handler completing and prints `MAIN_CONTINUES`, without catching that exception via a publisher `try/catch`.

### 5.1. Directory Structure

~~~text
async-event-failure-demo/
├── pom.xml
└── src/main/java/AsyncEventFailureDemo.java
~~~

### 5.2. File pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>async-event-failure-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
                <configuration>
                    <mainClass>AsyncEventFailureDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 5.3. File src/main/java/AsyncEventFailureDemo.java

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.aop.interceptor.AsyncUncaughtExceptionHandler;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.AsyncConfigurer;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public final class AsyncEventFailureDemo {

    // Two latches help confirm exact ordering without using Thread.sleep.
    private static final CountDownLatch ALLOW_WORKER =
        new CountDownLatch(1);
    private static final CountDownLatch ERROR_HANDLED =
        new CountDownLatch(1);

    public record OrderPlaced(long orderId) { }

    // Do not use final on the listener class so the proxy can intercept it.
    public static class FailingListener {

        @Async("eventsExecutor")
        @EventListener
        public void onOrderPlaced(OrderPlaced event) {
            try {
                if (!ALLOW_WORKER.await(10, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("gate timeout");
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("interrupted", ex);
            }

            System.out.println(
                "LISTENER order=" + event.orderId()
            );

            // Simulate an error occurring AFTER the task actually started running.
            throw new IllegalStateException("mail service down");
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class Config implements AsyncConfigurer {

        @Bean("eventsExecutor")
        ThreadPoolTaskExecutor eventsExecutor() {
            ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(10);
            executor.setThreadNamePrefix("events-");
            executor.initialize();
            return executor;
        }

        @Bean
        FailingListener failingListener() {
            return new FailingListener();
        }

        @Override
        public AsyncUncaughtExceptionHandler
                getAsyncUncaughtExceptionHandler() {
            return (ex, method, params) -> {
                System.out.println(
                    "ASYNC_ERROR "
                    + ex.getClass().getSimpleName()
                    + " " + ex.getMessage()
                    + " method=" + method.getName()
                );
                ERROR_HANDLED.countDown();
            };
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(Config.class)) {

            System.out.println("PUBLISH");
            context.publishEvent(new OrderPlaced(42L));
            System.out.println("PUBLISH_RETURNED");

            // Open the gate after publish has returned.
            ALLOW_WORKER.countDown();

            if (!ERROR_HANDLED.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                    "Async error was not observed"
                );
            }
            System.out.println("MAIN_CONTINUES");
        }
    }
}
~~~

Run in the project directory with JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java
~~~

Lines printed by **the program itself**, in order under the example configuration:

~~~text
PUBLISH
PUBLISH_RETURNED
LISTENER order=42
ASYNC_ERROR IllegalStateException mail service down method=onOrderPlaced
MAIN_CONTINUES
~~~

### 5.4. Line-by-Line Analysis

- `PUBLISH`: main is about to publish the event.
- `PUBLISH_RETURNED`: the `publishEvent` call returns after scheduling succeeded. The listener may already have entered the worker but is blocked on `ALLOW_WORKER.await(...)`, so it has not printed logs or thrown an error yet.
- `LISTENER order=42`: after main opens the latch, the worker executes its body.
- `ASYNC_ERROR ...`: `IllegalStateException` from the `@Async void` body is routed to the custom `AsyncUncaughtExceptionHandler`. The handler prints the method name and signals `ERROR_HANDLED`.
- `MAIN_CONTINUES`: main waits on **a signal designed by the example**, not an exception automatically propagated back. That latch is how we know the error was recorded before exiting the program.

**Limitations of the example:** there is no transaction, no real email sent, and no proof of durable event delivery. `CountDownLatch` only serves ordering verification, not a retry mechanism to use directly in production. If the executor rejects the task at submission time, the program may take a different error path before reaching the output above; the example assumes the executor initialized normally and has capacity to accept the task.

Do not write `Thread.sleep(100)` and conclude the error was handled. For async tests, use a latch, future, status queue, or verify an outcome with a timeout.

## 6. Which Exception Handler Handles Which Type of Error?

### 6.1. AsyncUncaughtExceptionHandler

Intended for uncaught exceptions from `@Async` invocations with a `void` return type. When the async proxy accepts the task successfully, the method body runs off the publisher thread and exceptions are handled by the async invocation path.

It can log, emit metrics, send alerts, or record failure state. By itself, however, it does not "rethrow to the caller" and does not automatically roll back the publisher.

### 6.2. SimpleApplicationEventMulticaster.setErrorHandler

If configuring the multicaster directly, an `ErrorHandler` can be set:

~~~java
@Bean(name = "applicationEventMulticaster")
SimpleApplicationEventMulticaster applicationEventMulticaster() {
    SimpleApplicationEventMulticaster multicaster =
        new SimpleApplicationEventMulticaster();
    multicaster.setErrorHandler(ex -> {
        // Log/metrics; decide whether to suppress or propagate.
        System.err.println("EVENT_ERROR: " + ex);
    });
    return multicaster;
}
~~~

This is an **illustrative** configuration example requiring imports for `Bean` and `SimpleApplicationEventMulticaster`. Naming the bean specifically `applicationEventMulticaster` replaces the multicaster used by the context in appropriate configurations.

`ErrorHandler` wraps the **multicaster's invocation of the listener**. If the listener is executed synchronously by the multicaster, the handler can suppress or rethrow depending on its logic. If the multicaster uses an executor, an exception in the worker can be caught by this handler on the worker. However, when the listener method is an `@Async` proxy that has scheduled a `void` task, errors raised afterward may already be handled by `AsyncUncaughtExceptionHandler` **inside the proxy**, never returning to the multicaster. In that case, merely adding `setErrorHandler` does not replace a custom async handler.

One more point: in Spring 6.1+, `ApplicationListener.supportsAsyncExecution()` can cause certain listeners such as transaction-synchronized listeners **not to be offloaded to an executor by the multicaster**. Do not treat a global executor as a guarantee that every listener runs asynchronously.

### 6.3. When You Want to Collect Results and Exceptions via Future

Spring `@Async` on a **service method** can return `CompletableFuture<T>`. The caller receives the future and observes exceptions via `join()`, `get()`, or `whenComplete(...)`:

~~~java
// Outline: a service Spring-proxied with @Async.
@Async("eventsExecutor")
public CompletableFuture<Void> sendEmail(long orderId) {
    emailClient.send(orderId);
    return CompletableFuture.completedFuture(null);
}
~~~

The orchestrator can monitor it:

~~~java
CompletableFuture<Void> future = emailService.sendEmail(42L);
future.whenComplete((value, error) -> {
    if (error != null) {
        // Record error, retry, or transition to failed state.
    }
});
~~~

Both snippets above are illustrative code in an application with `emailClient`, `emailService`, and appropriate imports. **Do not assume that changing an `@EventListener @Async` method to return `CompletableFuture` gives the caller a publish result returned by Spring**: event dispatch does not expose an API aggregating futures from all listeners. If you need an explicit outcome, an async orchestration/service with a future contract or a stateful job is usually easier to control.

## 7. Rollback: Which Transaction Does an Async Exception Affect?

This is the most important difference between synchronous and asynchronous errors.

### 7.1. Synchronous Listener in the Same Transaction

Example of a use case:

~~~java
@Transactional
public void createOrder(CreateOrder command) {
    orderRepository.save(createEntity(command));
    publisher.publishEvent(new OrderCreated(command.id()));
}
~~~

This is sketch code, requiring repository, models, and transaction configuration. If a synchronous listener joins the same transaction on this thread and throws an unhandled `RuntimeException`, the exception can propagate back, causing the transaction to be marked for rollback per rules.

However, that **is not true for every listener**: `@Transactional(propagation = REQUIRES_NEW)`, remote services, executors, and exception handlers can alter the boundaries.

### 7.2. Async Listener Runs on Another Thread

With `@Async`, the listener body usually runs on a different thread, **not inheriting the publisher's thread-bound imperative transaction**. If the publisher has already committed or is committing, an email error in the worker cannot automatically roll back the source transaction.

~~~text
Publisher thread (T1)                 Worker thread (no T1)
-------------------------             --------------------------
BEGIN T1
save order
publish(OrderCreated)
  -> schedule async task ------------> await executor
COMMIT T1                             send email -> failure
return                                async exception handler logs
~~~

Do not confuse "publisher and listener run in the same JVM" with "they share the same transaction." JDBC/JPA transactions are bound to managed resources and threads/contexts; Spring does not automatically transfer an open imperative transaction onto an executor.

### 7.3. @Transactional on an Async Worker

A listener or service running on a worker can have `@Transactional` and its own properly configured transaction manager. When invoked through a proxy inside the worker, it can open **a new transaction** for the worker's own DB operations.

Conceptual example:

~~~java
@Service
public class ProjectionWriter {

    @Transactional
    public void updateFor(OrderCreated event) {
        // Write projection in the worker's transaction.
        // Does not share the publisher's T1 transaction.
    }
}
~~~

An `@Async` listener can call `projectionWriter.updateFor(event)` through the bean proxy. The projection's transaction can roll back when projection processing fails, **without rolling back the previously committed order**. Separating the service this way avoids self-invocation and hard-to-verify interceptor ordering.

### 7.4. @TransactionalEventListener and @Async

`@TransactionalEventListener` allows binding work to a transaction phase, commonly `AFTER_COMMIT`. When combined:

~~~java
@Async("eventsExecutor")
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterOrderCommit(OrderCreated event) {
    notificationService.send(event);
}
~~~

This is illustrative code inside a Spring bean, requiring imports, executor, `OrderCreated`, and `notificationService`. **Transaction synchronization is registered for the event/transaction in the publisher context**, while the method body can be handed off to the executor **after the transaction commits**. Therefore:

- If the source transaction rolls back, the `AFTER_COMMIT` listener does not run.
- If it commits, the listener is permitted to start; a worker exception **does not turn the completed commit into a rollback**.
- If published outside a transaction, the listener by default **does not run**, unless `fallbackExecution=true` is used with clear intent.
- If the worker needs to write to the database, use a separate transaction; do not treat the source transaction's resources as still open for additional commits.
- If the process dies between commit and task completion, work can still be lost.

**After commit ≠ reliable delivery.** When notifications or external integrations must not be lost, persist the work durably.

## 8. Error Paths When the Executor Is Overloaded or Shutting Down

An async listener can fail **before its method body starts**. Examples:

- The thread pool has reached capacity and the queue is full.
- The executor is shutting down.
- Executor name configuration cannot find a matching bean.
- Misconfigured async proxy/annotation prevents the call from running as expected.
- The task is canceled or timed out by an external policy.

In some executors, submission failure throws `TaskRejectedException` or `RejectedExecutionException` on the call path; with some multicasters/handlers, there may be fallback or logging instead of throwing the same exception. Therefore, **do not rely on a blanket expectation that every rejection goes to `AsyncUncaughtExceptionHandler`**: this handler is for exceptions inside an executed `@Async void` method, not an umbrella API covering all scheduling errors.

### Executor Policy Example

~~~java
ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
executor.setCorePoolSize(4);
executor.setMaxPoolSize(8);
executor.setQueueCapacity(100);
executor.setThreadNamePrefix("event-");
executor.initialize();
~~~

This is an illustrative configuration snippet, not an optimal capacity formula for every application. You must measure real load, downstream call durations, burst sizes, and resource limits.

For jobs that must not be lost, an executor's **in-memory** queue is also not durable across process crashes. If you need backpressure, scheduled retries, or recovery after restart, consider a message broker/outbox/job storage and a consumer with an idempotency policy.

### Impact of Shutdown

`ContextClosedEvent` occurs while the context is closing. At that time, executors and dependencies may also be stopping. Do not plan "just publish an async event at close time and everything will definitely flush" unless there is a tested shutdown policy. Mandatory cleanup actions belong in appropriate lifecycle beans such as `SmartLifecycle` or `@PreDestroy`, with explicit timeouts and ordering.

## 9. Retry, Idempotency, and Failure States

If an async listener fails while calling an external service, recovery depends on the nature of the work:

| Work | Typically sensible policy |
| --- | --- |
| Auxiliary, optional diagnostic log | Log error/metrics, may ignore |
| Updating a rebuildable read model | Controlled retry, idempotency, rebuild capability |
| Sending a confirmation email | Persist sending intent, retry, and prevent duplicate sends |
| Updating payment/inventory | Commands and workflow state, deduplication, compensation when needed |
| Mandatory audit that must not be lost | Write audit/outbox inside transaction or durable storage |

Do not perform infinite retries in a `while(true)` loop inside a listener: it ties up the thread pool and can stall all other events. Instead, choose attempt limits, backoff, jitter, transient/permanent error classification, dead-letter/quarantine, and monitoring.

### 9.1. Why Do Retries Require Idempotency?

Suppose a worker calls an email provider successfully, yet times out before receiving the response. The handler records "failure" and retries; the customer could receive **two emails**. A database check by event ID, provider idempotency key, or job state can reduce duplicates, provided atomicity/retryability are designed properly.

Information that should exist on the event/job:

- Stable `eventId` or `jobId` for the same fact/task.
- `aggregateId` or business key.
- `correlationId`/`causationId` to trace errors across steps.
- `attempt` count and retry timestamp; do not change the event ID when redelivering the same fact.
- Error category code and processing state without exposing sensitive data.

A `Set<UUID>` in a singleton only deduplicates within one living JVM; it is insufficient across multiple pods, restarts, or parallel outbox dispatchers.

### 9.2. Transactional Outbox

When an event must be delivered even if the process dies, **transactional outbox** is a common pattern:

~~~text
T1 BEGIN
  INSERT order
  INSERT outbox(eventId, type=OrderCreated, payload, state=PENDING)
T1 COMMIT
             |
             v
Outbox dispatcher -> broker / worker
                     retry, backoff, dedup
~~~

The order and outbox row commit or roll back together. The dispatcher reads committed records, delivers them, and updates state. Consumers are idempotent because redelivery can occur. Outbox closes **the lost-work window between database commit and message publishing**, though it does not automatically create "end-to-end exactly once."

A pure `@Async` listener is a mechanism for running work on an executor, not a replacement for an outbox, message broker, or durable job system.

## 10. Where to Catch Errors Without Masking Failure Signals

A listener may intentionally catch exceptions when it owns the recovery policy:

~~~java
@Async("eventsExecutor")
@EventListener
public void onOrderCreated(OrderCreated event) {
    try {
        externalClient.notify(event.orderId());
    } catch (TransientGatewayException ex) {
        retryQueue.enqueue(event.eventId());
        metrics.counter("notification_retry_queued").increment();
    }
}
~~~

This is an **illustrative** snippet, requiring `externalClient`, `retryQueue`, `metrics`, `TransientGatewayException`, and `OrderCreated` in the system. It is only suitable if `retryQueue.enqueue(...)` genuinely guarantees the work is persisted per its contract. If the queue also fails, the error must be handled/propagated so the system knows task handoff did not complete.

Do not write:

~~~java
try {
    sendEmail();
} catch (Exception ignored) {
    // Silent: the application does not know the work failed.
}
~~~

A catch-all that swallows errors can make logs and metrics report false success. Classify errors:

- **Transient errors:** network timeout, 503, rate limit; can be retried with bounds.
- **Permanent business errors:** invalid address, disallowed state; can transition to failed/quarantine.
- **Coding/configuration errors:** NPE, missing bean, bad mapping; usually require alerts and code fixes rather than infinite retries.

Do not rely blindly on exception classes; downstream APIs must expose clear enough error codes/contracts to decide retryability.

## 11. Logs, Metrics, and Tracing

A failing async listener may execute outside the initial HTTP trace, so **causality** must be recorded. Structured logs should contain:

- `eventType`, `eventId`, `aggregateId`.
- `correlationId`, `causationId` if the workflow has multiple steps.
- `listenerName`, `executorName`, `threadName`.
- `attempt`, `durationMs`, `status` (success/failure/retry_scheduled).
- `errorClass` and controlled error codes.
- `traceId`/`spanId` if distributed tracing is properly wired.

Example:

~~~text
event=OrderCreated id=e-42 corr=order-42 listener=EmailListener phase=async attempt=1 status=failed error=GATEWAY_TIMEOUT
event=OrderCreated id=e-42 corr=order-42 listener=EmailListener phase=retry attempt=2 status=scheduled
~~~

**Do not put event IDs or order IDs into metric labels** such as Prometheus counters because that creates high cardinality. A custom metric name could be `app_event_listener_failures_total{listener="email",error="timeout"}`, with bounded label values. Granular IDs belong in logs/traces.

MDC and ThreadLocal do not automatically follow every thread; use `TaskDecorator`, tracing context propagation, or pass metadata in the event/job per policy. Do not pass JPA persistence contexts, transactions, or secrets directly to an executor.

## 12. Testing: Verify Both Success and Failure Paths

A trustworthy async test must check the **final outcome**, not merely that `publishEvent(...)` did not throw an exception.

| Test case | Expectation |
| --- | --- |
| Valid event, listener succeeds | Outcome is stored/confirmed; publisher does not wait unless the contract says so |
| Worker throws `RuntimeException` | Async error handler/monitor receives it; publisher does not automatically receive worker error |
| Executor rejects task | Scheduling failure policy is explicitly executed; not marked "processed" |
| Listener forgot `@EnableAsync` | Test detects synchronous execution or misconfigured startup/config |
| Multiple listeners, one fails | Verify impact on other listeners according to dispatch mode |
| Publisher in rolling-back transaction | Worker must not assume it shares T1; after-commit handler does not run if T1 rolls back |
| `@Async @Transactional` worker fails | Worker's transaction may roll back; publisher's transaction is not reversed |
| Process stops after T1 commits | Durable outbox/job can recover; in-memory async queue is insufficient |
| Retry after downstream timeout | Does not create duplicate side effects when idempotent |
| Multiple instances consuming together | Cross-instance deduplication lock/rules work |
| Replaying historical events | Does not re-run dangerous actions just to rebuild a projection |
| Executor shutdown with running tasks | Graceful shutdown/timeout policy is verified |

### 12.1. Do Not Use Thread.sleep to Guess

A test using `Thread.sleep(100)` before checking a variable can be flaky due to scheduling and CI load. The complete example in Section 5 uses **two CountDownLatches with timeouts**, distinguishing "publish has returned" from "async exception has reached the handler."

For integration tests with a database, do not conclude commit/rollback simply because a listener printed a log. Let the transaction actually finish, then query the data at the appropriate boundary. If the test itself is wrapped in `@Transactional` and rolls back at the end of the test, results may differ from production requests.

### 12.2. Test Submission and Execution Paths Separately

To test executor rejection, configure a small executor/queue and a controlled task occupying the thread, then measure the policy when submitting beyond capacity. That test **differs** from testing an exception thrown inside a worker. If the library/executor falls back to the caller thread, assert that fallback rather than rigidly expecting a `RejectedExecutionException`.

### 12.3. Test Failures Without Losing Work

If the system requirement is "every created order produces one notification processing even across crashes," tests must include:

1. Committing the order and outbox in one transaction.
2. Simulating a crash or stopping the dispatcher before processing.
3. Restarting the dispatcher and reading pending records.
4. Performing retries if the first attempt fails.
5. Verifying the outcome, outbox state, and idempotency key.
6. Simulating duplicate delivery to ensure no unintended duplicate sends.

A unit test of `@Async` cannot replace this kind of integration test.

## 13. Common Mistakes

1. **Wrapping publish in try/catch and thinking async errors are caught:** exceptions occurring later on another thread do not automatically enter that catch block.
2. **Adding @Async without @EnableAsync or with misconfigured proxies:** the listener may run synchronously unexpectedly.
3. **Using final/private/self-invocation so proxies cannot intercept as intended:** verify the real proxy mechanism.
4. **Configuring only the multicaster's ErrorHandler:** may not handle exceptions inside `@Async void` bodies already intercepted by the async interceptor.
5. **Treating AsyncUncaughtExceptionHandler as a retry system:** it only executes the exception policy you write; it does not persist jobs or replay them.
6. **Believing a failing worker will roll back an already committed transaction:** rollback only applies within the corresponding transaction boundary.
7. **Thinking @TransactionalEventListener(AFTER_COMMIT) is a durable queue:** it does not survive process crashes after commit.
8. **Ignoring task submission errors:** the executor can reject before the listener runs; this is a separate failure path.
9. **Using infinite retries inside the listener:** ties up threads and can cause an event storm.
10. **Lacking idempotency:** a timeout after success causes retries to create duplicate side effects.
11. **Catching Exception and ignoring it:** causes false-success reporting with no alerts or processing status.
12. **Relying on thread name as the sole proof:** must verify executor, timing, and outcome.
13. **Not managing shutdown:** queued tasks may be dropped when the context closes.
14. **Assuming MDC, SecurityContext, and transactions are inherited automatically:** thread-bound contexts must be propagated or initialized properly; never copy transactions.
15. **Confusing error handler logging with business recovery:** a successful log does not confirm an email, projection, or payment was processed.
16. **Thinking @Order guarantees async completion order:** the annotation can order dispatch, not task completion.
17. **Returning an event from an async listener expecting Spring to publish it automatically:** with async listeners, publish follow-up events explicitly.
18. **Lacking a correlation ID:** makes it hard to tell which request/aggregate a failed async task belongs to.

## 14. Self-Check Exercises

1. Why does `try { publisher.publishEvent(event); } catch (...)` usually fail to catch errors in an `@Async void` body?
2. At which pipeline layer do `AsyncUncaughtExceptionHandler` and `SimpleApplicationEventMulticaster.setErrorHandler` differ?
3. The executor runs out of capacity right at submission time. Does this error necessarily go to `AsyncUncaughtExceptionHandler`?
4. The publisher has committed the order, and the async email listener fails. Can the order be rolled back by throwing `RuntimeException` in the worker?
5. An async worker has `@Transactional`; is its transaction the same transaction opened in the publisher?
6. What does `@TransactionalEventListener(AFTER_COMMIT)` guarantee when the publisher rolls back? Does it guarantee the notification is sent before the process stops?
7. Why is `CompletableFuture` useful for tracking async service results, yet does not turn `publishEvent` into a call returning futures for all listeners?
8. If the email provider already sent the email but the response timed out, what happens when retrying without idempotency?
9. Why is a `Thread.sleep(100)` test less reliable than a latch with a timeout?
10. What else does a mandatory task that must not be lost after commit need besides `@Async @EventListener`?
11. With multiple pods, why is a `Set` stored in a singleton insufficient to deduplicate events?
12. What problems can arise when a listener is invoked asynchronously while the context is closing?

**Answer hints:** (1) the task fails after the publisher has already returned; (2) async method interceptor vs. multicaster listener invocation; (3) no, scheduling errors take a separate path; (4) no, the source transaction has already completed; (5) no, the worker has its own transaction when properly proxied; (6) does not run on rollback, yet does not guarantee durability; (7) Future belongs to a service with a return type, not an event-listener aggregation mechanism; (8) duplicate sends; (9) scheduling has no fixed timing; (10) durable outbox/job, retry/idempotency/monitoring; (11) local memory is lost on restart and not synchronized across pods; (12) task rejection, dependencies/connections/executor shutting down.

## 15. Summary

Errors in async listeners have two defining characteristics: **they no longer share a call stack with the publisher** and **they do not automatically share the source transaction**. Therefore:

- Synchronous and async listeners have different exception propagation paths.
- For `@Async void`, observe exceptions via `AsyncUncaughtExceptionHandler`, not a `try/catch` at the publisher.
- With a multicaster executor, understand `setErrorHandler`, thread offloading, and executor policies; do not conflate the two error layers.
- Handle task-submission errors separately from errors inside the worker.
- `@TransactionalEventListener(AFTER_COMMIT)` binds timing to commit, yet does not guarantee durable work delivery.
- Use bounded retries, idempotency, and outbox/job storage when work is mandatory.
- Test async behavior with outcome state and reliable synchronization, never arbitrary sleeps.

## References

- Spring Framework Reference — *Application Events, Asynchronous Listeners*: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Spring Framework Reference — *Task Execution and Scheduling, Exception Management with @Async*: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Spring Framework Reference — *Transaction-bound Events*: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
- Spring Framework Reference — *Declarative Transaction Management*: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework 6.2.8 Javadoc — *SimpleApplicationEventMulticaster*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html
- Spring Framework 6.2.8 Javadoc — *AsyncUncaughtExceptionHandler*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/aop/interceptor/AsyncUncaughtExceptionHandler.html
- Spring Framework 6.2.8 Javadoc — *AsyncConfigurer*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/scheduling/annotation/AsyncConfigurer.html
