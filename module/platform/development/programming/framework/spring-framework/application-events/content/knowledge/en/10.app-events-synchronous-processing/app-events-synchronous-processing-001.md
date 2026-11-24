# Listeners Run on the Publisher Thread in Spring Application Events

## 1. What Synchronous Processing Means

In the Spring Framework, `ApplicationEventPublisher.publishEvent(event)` submits an event into the event-dispatching mechanism of `ApplicationContext`. With the default configuration of `SimpleApplicationEventMulticaster`, synchronous listeners are invoked **directly on the thread currently executing the `publishEvent(...)` call**. That thread is called the **publisher thread**.

Key points to remember:

- A **publisher** is the code emitting an event via `publishEvent`; the publisher can be a controller, a service, a scheduled task, a message consumer, or an application-created thread.
- A **listener** is the callback receiving the event, such as a method annotated with `@EventListener` or a bean implementing `ApplicationListener`.
- **Synchronous** means the publisher enters the listener and waits for the callback to finish before continuing after `publishEvent`. Under the default configuration, no new thread is created just because Spring Events are used.
- **"Same thread as the publisher" does not always mean the `main` thread**. If the event-emitting code runs on an HTTP request thread or a worker thread, synchronous listeners run directly on that exact thread.

This is the standard default behavior of Spring Application Events; `publishEvent` is a way of handing an event to the dispatching mechanism, **not a promise that every configuration or every kind of listener runs synchronously**. `@Async`, a custom executor on the multicaster, and transaction-phase listeners can change the execution timing or thread.

## 2. Single-Thread Call Flow

With ordinary listeners and the default synchronous multicaster, the call structure for **a single** event publication can be visualized as follows:

~~~text
Thread P (calling publishEvent)
  |
  +-- service calls publisher.publishEvent(new OrderPlaced(...))
          |
          +-- ApplicationContext / ApplicationEventMulticaster
                  |
                  +-- Listener A: finishes processing
                  |
                  +-- Listener B: finishes processing
          |
  +-- publishEvent returns
  |
  +-- service executes the next statement
~~~

All of these call arrows stay within **Thread P's call stack** when listeners execute synchronously. Within the same publication of an event, a listener with a lower `@Order` value may be invoked first; if both are synchronous and succeed, the earlier callback finishes before the later callback begins.

For example, if Listener A takes 150 ms and Listener B takes 80 ms, their sequential execution time contributes roughly 230 ms to the latency of the publish call, excluding overhead. The publisher cannot treat "publishing finished" as instantaneous when slow synchronous listeners are present.

**Consequence:** If a listener throws an unhandled exception, the exception typically propagates back to the caller of `publishEvent`, and subsequent listeners may not have been invoked yet. Configuring an `ErrorHandler` on the multicaster can alter how errors are handled. You should not assume all listeners always finish running in every failure scenario.

## 3. Runnable Java 17+ Example: Listeners Use the Exact Thread That Published the Event

This example uses **Spring Framework 6.2.x**, Java 17+, and Maven. We publish events sequentially from a thread named `publisher-main` and another thread named `publisher-worker`. Each event is handled by two synchronous listeners, and only afterward does the publisher print the `after publish` line.

### 3.1. Project Structure

~~~text
spring-sync-event/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── SynchronousEventDemo.java
~~~

Create `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>spring-sync-event</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
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
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Create `src/main/java/demo/SynchronousEventDemo.java`:

~~~java
package demo;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;

public class SynchronousEventDemo {

    // Pure data payload; carries no thread or mutable state.
    public record StockChanged(String sku) {}

    @Configuration
    public static class Config {
        @Bean
        public StockListeners stockListeners() {
            return new StockListeners();
        }
    }

    public static class StockListeners {

        @EventListener
        @Order(1)
        public void audit(StockChanged event) {
            log("listener-audit", event.sku());
        }

        @EventListener
        @Order(2)
        public void updateCache(StockChanged event) {
            log("listener-cache", event.sku());
        }
    }

    private static void log(String action, String sku) {
        System.out.printf(
                "%s | thread=%s | sku=%s%n",
                action,
                Thread.currentThread().getName(),
                sku
        );
    }

    private static void publish(
            AnnotationConfigApplicationContext context, String sku) {
        log("before publish", sku);
        context.publishEvent(new StockChanged(sku));
        log("after publish", sku);
    }

    public static void main(String[] args) throws InterruptedException {
        Thread.currentThread().setName("publisher-main");

        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            // Run 1: publisher is on the thread executing the main method.
            publish(context, "SKU-104");

            // Run 2: publisher is on a worker thread we created.
            Thread worker = new Thread(
                    () -> publish(context, "SKU-105"),
                    "publisher-worker"
            );
            worker.start();
            worker.join();
        }
    }
}
~~~

Run inside the `spring-sync-event` directory:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.SynchronousEventDemo
~~~

Output lines printed by the program itself (excluding Maven logs if your environment prints extra logs):

~~~text
before publish | thread=publisher-main | sku=SKU-104
listener-audit | thread=publisher-main | sku=SKU-104
listener-cache | thread=publisher-main | sku=SKU-104
after publish | thread=publisher-main | sku=SKU-104
before publish | thread=publisher-worker | sku=SKU-105
listener-audit | thread=publisher-worker | sku=SKU-105
listener-cache | thread=publisher-worker | sku=SKU-105
after publish | thread=publisher-worker | sku=SKU-105
~~~

### 3.2. Explaining the Output

1. Publishing `SKU-104` happens on `publisher-main`; both listeners print that same thread name. The `after publish` line only appears after both callbacks.
2. Publishing `SKU-105` happens on `publisher-worker`; both listeners also run on **this worker thread**, without switching back to `publisher-main`.
3. `worker.join()` only makes `main` wait for the worker to finish so the Spring context can close safely in the example; it is **not the mechanism that makes the event listeners run synchronously**.
4. `@Order(1)` and `@Order(2)` mainly illustrate invocation ordering when there are multiple listeners. They **do not create new threads** and are not a prerequisite for Spring to run synchronously.
5. The program does not configure an executor for the event multicaster and has no `@Async`, so it follows the default path: invoking listeners directly on the thread that published the event.

Thread names are used for observation in logs; in real applications, do not use a **thread name** as a contract for ordering or data access permissions. A thread can be renamed, and multiple distinct threads can share the same name.

## 4. Distinguishing the Publisher Thread from Request Threads and the Main Thread

In a Spring application, "publisher thread" simply means **the thread currently executing the code that calls `publishEvent` at that moment**. Common cases include:

| Where `publishEvent` is called | Actual publisher thread | Default synchronous listener |
| --- | --- | --- |
| Inside `main` | Current thread running `main` | Runs on that thread |
| Inside an HTTP request handler method (Spring MVC) | Thread serving the request | Runs on the same request thread |
| Inside a `@Scheduled` method | Scheduler thread executing the method | Runs on the same scheduler thread |
| Inside an `@Async` service method | Executor thread running the method | Runs on that executor thread |
| Inside a Kafka/JMS consumer callback | Thread invoking the callback (per container) | Runs on that callback thread |
| Inside a `new Thread(...)` | Application thread just created | Runs on that thread |

Do not infer that a listener runs on the main thread just because the application starts from `main`. Likewise, do not infer that a listener is asynchronous just because the publisher runs on a background thread: **the entire publish call and its listeners can still be synchronous relative to that background thread**.

### Inside an HTTP Request

Suppose a controller calls a service, the service saves data, and then calls `publishEvent`; synchronous listeners check permissions, update an index, or call a remote service. The request thread waits for the listeners to finish before the service continues. Therefore, slow synchronous listeners can increase response time, hold onto request resources, and reduce throughput.

### Inside a Background Thread

If a scheduled job publishes an event from a single scheduler thread, a slow synchronous listener prolongs that job execution itself. Depending on scheduler configuration, this affects when subsequent tasks start. The synchronous nature of Spring Events does not turn work into a durable queue or an independent background process.

## 5. Why Do Listeners Run on the Same Thread by Default?

`ApplicationContext` uses an `ApplicationEventMulticaster` to locate and invoke matching listeners. With the default `SimpleApplicationEventMulticaster` **having no asynchronous `TaskExecutor`**, each eligible listener is invoked directly during `multicastEvent`. That invocation continues using the current call stack, so there is no handoff to another thread.

You can picture it like this (pseudocode, not Spring's internal source):

~~~java
// PSEUDOCODE to understand the synchronous mechanism; do not copy verbatim to build.
void publishEvent(Object event) {
    for (ApplicationListener<?> listener : matchingListeners(event)) {
        invokeSynchronously(listener, event);
    }
}
~~~

The `invokeSynchronously` function illustrates ordinary callback invocation. In reality, Spring also handles listener registration and filtering, ordering, generic event types, and error strategies. The key point is that neither `Thread.start()` nor `Executor.execute(...)` is needed in the default synchronous path.

The `@EventListener` annotation lets Spring recognize callback methods and create listener adapters; `@EventListener` alone **does not enable async**.

## 6. When Does "Same Thread" Stop Holding?

### 6.1. `@Async` on a Listener

When `@EnableAsync` is enabled, an executor is configured, and an `@EventListener` method is annotated with `@Async`, the listener body may be handed off to an executor thread:

~~~java
// Configuration/annotation example only: requires @EnableAsync and a suitable executor.
@Async("eventExecutor")
@EventListener
public void onStockChanged(StockChanged event) {
    // May run on a different thread from the one calling publishEvent.
    sendNotification(event.sku());
}
~~~

This is an **illustrative snippet**, not a standalone Java file. In this model, the `publishEvent` call typically only submits the task and does not wait for the listener body to finish. Consequently, reading data updated by an async listener immediately afterward can yield stale results. An exception in an `@Async void` listener does not automatically propagate back to the publisher thread the way a synchronous exception does.

### 6.2. Executor on the Event Multicaster

An application can register an `applicationEventMulticaster` bean using `SimpleApplicationEventMulticaster.setTaskExecutor(...)`. Listeners that **support async execution** can be dispatched by the multicaster to the executor and run on another thread. Some listeners have contracts requiring synchronous execution; you must not assume every listener is offloaded to the executor just because the multicaster has an executor.

### 6.3. `@TransactionalEventListener`

`@TransactionalEventListener` behaves according to a transaction phase, defaulting to `AFTER_COMMIT`. When a transaction is active, the listener invocation can be **deferred until the corresponding transaction phase**, so it does not run immediately at the `publishEvent` call like an ordinary `@EventListener`. When there is no transaction, by default this listener may not run at all (unless `fallbackExecution` is enabled). Thus, you need to separate **execution timing** from **which thread it runs on**.

### 6.4. A Listener Spawns Its Own Background Task

A synchronous listener can also call `CompletableFuture.runAsync(...)`, submit a job to an executor, send to a broker, or trigger an HTTP request and return. In that case, the direct callback remains synchronous, but **sub-tasks** may continue after `publishEvent` returns. You should not deduce that all side effects of a listener have finished merely because the callback returned.

## 7. Consequences for Performance, Errors, and Transactions

### 7.1. Latency and Resources

The publisher has to wait for synchronous callbacks. Listeners performing heavy CPU work, database reads/writes, HTTP calls, or holding locks can slow down the publishing request, scheduled job, or consumer. If long-running work is needed, consider controlled async execution or a queuing system; base the choice on latency, reliability, and business ordering requirements.

Do not convert every listener to async merely to lower latency. Async brings queue overhead, task rejection risks, thread/transaction context issues, and failure tracking complexity.

### 7.2. Exceptions Propagating to the Publisher

With ordinary synchronous listeners and a multicaster without a custom `ErrorHandler`, an unhandled exception in a listener can cause `publishEvent` to throw the error up to the caller. Listeners ordered after the failing listener may not be invoked during that multicast pass. Note that `@Order` orders callbacks, but **does not automatically guarantee retries**, rollbacks, or that every listener will still be called on failure.

If a listener performs a side effect and then throws an exception, the publisher receiving the error does not mean that side effect is automatically undone. Design retry/idempotency and transaction boundaries around the specific resources involved.

### 7.3. Transactions and Thread-Local Context

If `publishEvent` occurs inside an open transaction on the current thread and the listener is a synchronous `@EventListener`, the listener can participate in the active transaction according to how its data operations are configured. However, calling a synchronous listener **does not create a transaction by itself** and does not replace placing `@Transactional` appropriately.

Because the same thread is used, existing `ThreadLocal` contexts such as MDC/tracing or transaction-bound resources can be available inside the synchronous callback. If switched to `@Async`, those contexts **do not automatically propagate by default** to another thread; you must pass IDs explicitly or use proper context propagation.

`publishEvent` is not a durable event storage system. If the process stops or the transaction rolls back, do not assume the event will be replayed. For cross-service integration events requiring high reliability, consider the transactional outbox pattern and a message broker as needed.

## 8. Common Misconceptions

| Misconception | Accurate explanation |
| --- | --- |
| "Spring handles every event on its own dedicated thread." | No: `@EventListener` runs on the event-publishing thread by default. |
| "Running on the publisher thread means always running on the `main` thread." | The publisher can be a request thread, scheduler, consumer, or executor thread. |
| "`publishEvent` always returns immediately." | With synchronous listeners, it waits for processing; exceptions can be thrown to the caller. |
| "`@Order` creates threads or enables parallel execution." | `@Order` only orders listener invocations; it does not choose an executor. |
| "Once `publishEvent` returns, all side effects are definitely done." | You can only say synchronous callbacks returned normally; they might launch async subtasks or deferred work. |
| "A synchronous listener is guaranteed to commit a transaction by default." | You must consider the caller's transaction, propagation, exceptions, and commit timing; a listener does not commit by itself. |
| "`@TransactionalEventListener` works identically to a regular listener." | It registers handling for a transaction phase, so activation timing can differ. |

## 9. How to Test Properly in Real Projects

To verify whether a specific listener actually runs on the publisher thread:

1. Place logs **right before `publishEvent`**, inside the listener, and **right after `publishEvent`**. Print the thread name, event ID, and correlation ID; if strict verification is needed, compare `Thread.currentThread()` object references in a controlled test.
2. Make sure you know the actual configuration: whether `@EnableAsync` and `@Async` are present, whether the multicaster has a `TaskExecutor`, and whether the listener uses deferred execution or a transaction phase.
3. For synchronous listeners, verify the listener starts and finishes **before** the line after `publishEvent`. Do not rely on a few logs that "happened to line up" to conclude that an async setup guarantees ordering.
4. Try publishing events from two different publisher threads; each synchronous listener should run on the thread of its respective publish call, assuming no thread-switching config/logic is active.
5. Test a listener throwing an exception in a test environment to see how the caller and remaining listeners react. Do not run such failure tests against uncontrolled live transactions.

An automated test can capture `Thread.currentThread()` in the publisher and compare it with `==` against the thread observed inside the listener. That is stronger than only comparing thread names. If a test needs to wait for an async listener to finish, use `CountDownLatch` or `CompletableFuture` with a timeout; avoid using `Thread.sleep` to guess scheduling.

## 10. Self-Check Questions

**Question 1.** A controller publishes `OrderPlaced` while handling an HTTP request, and the `@EventListener` has no async configuration. Which thread does the listener run on?

**Answer:** The same thread calling `publishEvent` for the request (under the default synchronous multicaster configuration). The request is held until the callback finishes or throws an exception.

**Question 2.** An `@Async` service calls `publishEvent`, while the listener is synchronous. Does the listener necessarily run on the original request thread?

**Answer:** No. It runs synchronously **on the executor thread executing the `@Async` service**, because that is the publisher thread at the moment `publishEvent` is called.

**Question 3.** Why might the line after `publishEvent` appear before the listener's completion log when `@Async` is enabled?

**Answer:** The publisher can submit the task to the executor and continue without waiting for the listener body to complete. Thread execution order is not constrained by callback invocation order.

**Question 4.** If a synchronous listener throws an unhandled `RuntimeException`, is the publisher guaranteed to continue past `publishEvent`?

**Answer:** No. With the default synchronous multicaster and no custom error handler, the exception can propagate to the caller. The caller needs an appropriate error/transaction handling strategy.

## 11. Key Takeaways and References

- A **default synchronous Spring Event listener runs directly on the thread calling `publishEvent`**; the publisher must wait for the callback to return.
- The "publisher thread" is the thread of whatever actually emits the event—which may be a main, request, worker, or scheduler thread.
- `@Async`, an executor on the multicaster, transaction-phase listeners, and background tasks created by the listener itself are separate cases to evaluate.
- Synchronous behavior makes call stacks, thread context, and exceptions easier to reason about, but causes listener latency to impact the publisher directly.

Spring Framework documentation:

- Application Events, ApplicationEventPublisher, listener ordering, and asynchronous listeners: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- `SimpleApplicationEventMulticaster` and attaching a `TaskExecutor`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html
- `@TransactionalEventListener`: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
- Task Execution, Scheduling, and `@Async`: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
