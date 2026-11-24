# No Ordering Guarantees Under Asynchronous Execution in Spring Application Events

## 1. The Problem to Understand

When an event is published via `ApplicationEventPublisher.publishEvent(...)`, Spring finds matching listeners to handle it. In default mode, `SimpleApplicationEventMulticaster` invokes listeners **synchronously on the event-publishing thread**. For synchronous listeners of the same event, `@Order` can specify which listener is **invoked first** (smaller values have higher priority).

When listeners run **asynchronously**, the order of invoking/submitting work and the order of **starting or completing work** are two different concepts. Even if Spring invokes listener A with `@Order(1)` before B with `@Order(2)`, A may take longer, wait on I/O, or not yet be scheduled on a CPU, so B can finish before A. **Do not use `@Order` as a mechanism to guarantee completion order of asynchronous listeners.**

Business example: an `OrderPlaced` event triggers two tasks—sending a confirmation email and updating a reporting system. If run in parallel, the reporting system may finish updating before the email is sent. That may be completely acceptable. However, if task B strictly requires using a result produced by A, designing two independent asynchronous listeners will easily cause a race condition.

## 2. Three Types of Ordering to Distinguish

| Order Type | Question | With `@Async` listeners running on multiple threads |
| --- | --- | --- |
| Invoking/submitting task to executor | Which listener does Spring invoke to submit the task first? | `@Order` helps order listener invocation while publishing **one** event; it does not force tasks to run sequentially. |
| Starting execution | Which thread actually begins executing the listener method body first? | No general guarantee: depends on thread scheduling, executor, system load, and queue. |
| Completing and taking business effect | Which listener persists data, sends a request, or finishes first? | No general guarantee: I/O latency, retries, locks, and errors can invert the order. |

With **multiple event publications**, even the order of `publishEvent` calls in the application does not automatically create a global processing order if there are multiple publishers/threads or multiple executors.

### Two Common Ways to Run Asynchronously

1. **`@Async` on `@EventListener` methods:** Spring registers the listener and when the listener is invoked, the `@Async` proxy mechanism submits the method body to a `TaskExecutor`. `@EnableAsync` must be enabled with a suitable executor. If a listener is just a regular `@EventListener`, it is synchronous by default.
2. **An executor for the entire event multicaster:** define a bean named `applicationEventMulticaster` and configure `SimpleApplicationEventMulticaster.setTaskExecutor(...)`. The multicaster can then dispatch async-capable listeners to other threads; some listeners that require synchronous execution may still run on the event-publishing thread (depending on the listener's `supportsAsyncExecution` contract).

Neither approach guarantees **completion** order by default. There is no need to enable both just to make a listener asynchronous: choose a clear execution mechanism to avoid difficulty controlling the executor and context.

## 3. Java 17+ Example: `@Order(2)` Finishes Before `@Order(1)`

The example below uses **Spring Framework 6.2.x**, Java 17+, and Maven. Two listeners receive the same event and run on a two-thread executor. Listener A (`@Order(1)`) intentionally waits for a signal from main; B (`@Order(2)`) can complete while A is still waiting. `CountDownLatch` demonstrates the result in a controlled way, instead of relying on `Thread.sleep` and race probabilities.

Create the structure:

~~~text
async-event-order/
├── pom.xml
└── src/main/java/demo/AsyncOrderDemo.java
~~~

**`pom.xml`:**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>async-event-order</artifactId>
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

**`src/main/java/demo/AsyncOrderDemo.java`:**

~~~java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executor;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class AsyncOrderDemo {
    public record OrderPlaced(String orderId) {}

    public static class Gates {
        final CountDownLatch aStarted = new CountDownLatch(1);
        final CountDownLatch releaseA = new CountDownLatch(1);
        final CountDownLatch aCompleted = new CountDownLatch(1);
        final CountDownLatch bCompleted = new CountDownLatch(1);
    }

    @Configuration
    @EnableAsync
    public static class Config {
        @Bean
        public Gates gates() {
            return new Gates();
        }

        @Bean("eventExecutor")
        public Executor eventExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(2);
            executor.setMaxPoolSize(2);
            executor.setQueueCapacity(8);
            executor.setThreadNamePrefix("event-");
            return executor; // Spring automatically initializes and closes this bean
        }

        @Bean
        public Listeners listeners(Gates gates) {
            return new Listeners(gates);
        }
    }

    public static class Listeners {
        private final Gates gates;

        public Listeners(Gates gates) {
            this.gates = gates;
        }

        @Async("eventExecutor")
        @EventListener
        @Order(1)
        public void listenerA(OrderPlaced event) {
            gates.aStarted.countDown();
            try {
                gates.releaseA.await();
                System.out.println("A: completed @Order(1)");
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("Listener A interrupted", ex);
            } finally {
                gates.aCompleted.countDown();
            }
        }

        @Async("eventExecutor")
        @EventListener
        @Order(2)
        public void listenerB(OrderPlaced event) {
            System.out.println("B: completed @Order(2)");
            gates.bCompleted.countDown();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            Gates gates = context.getBean(Gates.class);

            try {
                context.publishEvent(new OrderPlaced("O-100"));

                boolean aStarted = gates.aStarted.await(5, TimeUnit.SECONDS);
                boolean bFinished = gates.bCompleted.await(5, TimeUnit.SECONDS);
                if (!aStarted || !bFinished) {
                    throw new IllegalStateException("Listeners did not complete in time");
                }
                if (gates.aCompleted.getCount() != 1) {
                    throw new AssertionError("A is no longer waiting");
                }

                System.out.println("Main: B finished, A is still waiting");
            } finally {
                // Always release A, even if checks fail.
                gates.releaseA.countDown();
            }

            if (!gates.aCompleted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("A did not finish in time");
            }
        }
    }
}
~~~

Command to run from the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.AsyncOrderDemo
~~~

Main `stdout` lines of the program (the order is actively controlled by the latches):

~~~text
B: completed @Order(2)
Main: B finished, A is still waiting
A: completed @Order(1)
~~~

**Explanation:** B increments `bCompleted` (counts down) only after printing. Main waits for B to complete and verifies that A has not completed yet; only after printing the conclusion does main open `releaseA`. Thus, the example demonstrates a valid execution schedule where the listener with lower invocation priority **completes first**. In real applications, delays come from CPU, network, database, retries, or other tasks; order inversion can still occur even without latches.

> Note: this code uses latches to **demonstrate and verify**, not to block threads in order to "fix" ordering in production applications. When designing for production, express business dependencies through an explicit processing flow.

## 4. What Does `@Order` Guarantee and What Does It Not Guarantee?

With the default **synchronous** multicaster configuration, an `@Order(1)` listener is invoked before `@Order(2)` when both are eligible to receive an event; because the earlier call runs to completion before the next is invoked, completion order follows invocation order when listeners all finish normally. An unhandled exception can prevent subsequent listeners from running.

With `@Async` listeners, the invocation seen by the multicaster is primarily submitting a task to the executor. `@Order(1)` may be **submitted** first, yet A and B run on different threads. Therefore, "A finishes before B" cannot be inferred from `@Order(1)` and `@Order(2)`.

With a multicaster configured with a `TaskExecutor`, the same applies: **scheduling** listeners may follow order, but completion is still governed by the executor and processing time. Moreover, not every listener is guaranteed to accept asynchronous execution by default.

| Configuration | Can execution/completion order be expected? |
| --- | --- |
| Synchronous listeners, default multicaster, distinct `@Order` | Yes, within a single event publication, when listeners run successfully and do not hand off work to another task themselves. |
| Two `@Async` listeners, multi-threaded executor | No: completion can reverse order. |
| Multicaster using a multi-threaded executor | No: async-eligible listeners can run in parallel. |
| A single-threaded executor for related tasks | Tasks indeed enter the same queue and are processed sequentially; you must still account for task submission order, multiple publishers, retries, multiple instances, and side effects in external systems. |

## 5. How to Design When Business Logic Requires Strict Order

**Case A — Two directly dependent steps:** Combine them into **one orchestrating flow** with an explicit sequence. The whole flow can run asynchronously, while inside it A runs to completion before B:

~~~java
// Illustrates the body of a listener; must be declared as a Spring bean
// and have @EnableAsync enabled if using @Async.
@Async("eventExecutor")
@EventListener
public void onOrderPlaced(OrderPlaced event) {
    reserveInventory(event);  // Finishes or fails explicitly
    chargePayment(event);     // Invoked only after the previous step completes
}
~~~

The snippet above is **illustrative code**, not a standalone program. If step A returns a `CompletableFuture`, `thenCompose` can be used to chain step B upon A's success; exceptions and retries must be handled within the chain. For tasks involving databases and transactions, define commit timing and the strategy for when A succeeds but B fails.

**Case B — Sequential processing needed on a queue:** Use a single-threaded executor or a queue/consumer with appropriate ordering. This serializes tasks **submitted to the exact same executor/partition**, but does not automatically guarantee chronological order across multiple publishers or multiple instances. Avoid claiming "global ordering" when a distributed architecture does not actually provide those conditions.

**Case C — Independent tasks:** Keep processing parallel; design **idempotent** listeners, appropriate retries, business locks/sequence numbers, or version checks when writing shared data. If an event arrives late, the listener must know how to ignore stale updates or reconcile state.

**Case D — Ordering needed across services:** Use an orchestrated workflow, or a message broker capable of ordering by **a business key** with appropriate consumers/partitions. Enqueue order, consume order, and commit order must still be defined separately. Do not rely on Spring's `@Order` to guarantee ordering across services.

## 6. Commonly Overlooked Technical Risks

- **Do not wait for results via `publishEvent`:** When listeners are async, `publishEvent(...)` may return before listeners finish. Do not immediately query the database assuming the task has already run. If waiting is needed, use an explicitly designed feedback/synchronization mechanism.
- **Exceptions:** Exceptions from `@Async` listeners returning `void` do not automatically propagate back to the thread calling `publishEvent`. You need logging/metrics, an `AsyncUncaughtExceptionHandler`, or proper result and retry design. Exceptions from synchronous listeners have different semantics.
- **Transactions and thread context:** Async does not automatically carry over the publisher's transaction, `ThreadLocal`, request context, or logging MDC. `@TransactionalEventListener(phase = AFTER_COMMIT)` controls *when* the event is received after commit, and does not guarantee completion order among async listeners. If identity/tracing information is needed, pass a correlation ID in the event or configure controlled context propagation.
- **Executor limits:** Bounded pools and queues can become saturated or reject tasks under high load. Design rejection handling, shutdown, and latency monitoring; do not treat "event published" as "processed successfully".
- **Mutable events:** Do not let multiple listeners write to the same mutable object without synchronization. Prefer immutable events containing finalized data, such as a Java `record`.
- **Flawed testing:** A few runs producing A before B do not prove the system is always ordered. Use `CountDownLatch`, `CompletableFuture`, and inspect synchronization states/points to create contention scenarios; avoid `Thread.sleep` as "proof" of ordering guarantees.

## 7. Strategy Selection Checklist

1. Do the two listeners **have a data dependency**? If yes, design a processing chain/orchestration instead of relying on the order of async callbacks.
2. Do you need **invocation**, **start**, **completion**, or **durable write** order? Specify the requirement explicitly in a business contract.
3. How many executors, threads, publishers, and instances are there? A single thread in one process does not solve ordering across the entire system.
4. Are there timeouts, errors, retries, or late-arriving data? Add idempotency, versions/sequences, and error observability.
5. Have tests actively simulated B finishing before A, network delays, multiple publishers, and shutdown?

**Remember:** `@Order` helps sort **listener invocation**; `@Async` runs the work at a different time. If **completion** order carries business meaning, express the dependency via an orchestrating flow, a constrained queue, or versioning rather than hoping on thread scheduling.

## Official Documentation

- Spring Framework — ApplicationContext, Asynchronous Listeners, Ordering Listeners, ApplicationEventMulticaster: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Spring Framework — Task Execution and Scheduling, `@Async`, executors, and exception handling: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Spring Framework — Observability/Context Propagation with Application Events: https://docs.spring.io/spring-framework/reference/integration/observability.html
