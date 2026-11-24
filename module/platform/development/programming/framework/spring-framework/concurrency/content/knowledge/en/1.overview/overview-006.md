# Guarantees Spring Provides vs. Responsibilities of Business Code

> **Scope:** Spring Framework – concurrency, **Overview** section. This lesson draws the exact line between mechanisms managed by Spring and correctness when multiple requests, threads, tasks, and instances execute concurrently, which business code must protect itself.

## 1. Why Must We Distinguish Them?

A Spring application can accept multiple HTTP requests, run @Async tasks, process messages, trigger @Scheduled jobs, and execute transactions at the same time. Calls can access the same singleton bean, the same database row, or the same external service. The framework can organize where execution happens, but it does not automatically know invariants such as "inventory must not go negative," "an order must not be paid twice," or "an event must be safely reprocessable."

There are three layers of responsibility to separate:

1. **Coordination:** where and when execution happens, executors/schedulers, routing calls through Spring proxies, and bean/task lifecycles.
2. **Access safety:** shared data, the Java Memory Model, atomicity, locking, isolation, and update ordering.
3. **Business correctness:** invariants, idempotency, failure recovery, duplicates, timeouts, and cross-system consistency.

Spring handles the first layer and provides tools for the other two. **Thread safety and exactly-once semantics do not appear automatically just by adding annotations.**

## 2. Matrix of Guarantees and Responsibilities

| Mechanism | What Spring Provides | What Business Code Must Ensure |
| --- | --- | --- |
| IoC, DI, and bean scopes | Creates, wires dependencies, and manages lifecycle; singleton defaults to one bean instance per bean definition in a container | Bean state and shared dependencies must be thread-safe or stateless |
| TaskExecutor, @Async | Routes calls through a proxy to the chosen executor and returns Future/CompletableFuture if the contract requires | Pools, queues, load limits, rejections, errors, cancellation, timeouts, shared state, and final results |
| TaskScheduler, @Scheduled | Triggers tasks on schedule within the configured runtime | Overlapping runs, duplicate runs across multiple instances, missed runs, retries, idempotency, and recovery |
| @Transactional (imperative) | Applies the transaction interceptor and transaction manager on the executing thread when the call goes through the proxy | Transaction boundaries, isolation, locks/versions, conflicts, and side effects outside the DB |
| Request/session scope | Manages objects by request/session lifetime when a valid web context exists | Do not use request objects after the request ends; a session can still be accessed concurrently |
| TaskDecorator and context-aware adapters | Customization hooks to carry certain execution contexts into tasks | Choosing valid contexts to propagate, clearing ThreadLocal after the task, preventing data leaks between requests |
| Lifecycle and shutdown | Init/destroy hooks, managing executors and schedulers, shutdown options | Wait deadlines, controlled cancellation, persisting in-flight job state, crash recovery |

A Spring mechanism only honors its contract when **configured and invoked along the proper path**. @Async means nothing if the annotation is bypassed due to self-invocation; @Transactional does not create a transaction for a call that does not pass through the interceptor of the corresponding proxy configuration.

## 3. Singleton Beans Can Be Called Concurrently

A singleton is **the exact same object** reused within a Spring IoC container, not a separate object per request. Dangerous example:

~~~java
@Service
public class UnsafeCounterService {
    private int value;

    public int next() {
        return ++value;
    }
}
~~~

This is a Spring illustration snippet (imports omitted to focus on the bug). The ++ operation is read–compute–write, so two threads can read the same value and write duplicate results. Being created/injected by Spring **does not** make this operation atomic.

Proper practice by data category:

- **Stateless singleton:** fields are primarily dependencies or immutable configuration; use local variables and per-call inputs/outputs. Constructor injection helps control dependencies.
- **Mutable state within a single JVM:** use AtomicInteger/AtomicLong, synchronized/Lock, ConcurrentHashMap, or other JDK primitives according to the specific invariant. volatile supports visibility/ordering but **does not** make increments or "check-then-insert" sequences atomic.
- **Durable state shared across multiple replicas:** enforce invariants at the datastore with transactions, constraints, conditional updates, optimistic/pessimistic locking, and unique keys; in-JVM locks do not protect other instances.
- **Other scopes do not necessarily solve it:** prototype creates an object when requested; a prototype injected once into a singleton can still be held and shared. Request scope isolates instances per request but does not make session/application scope thread-safe.

### Standalone Java 17+ Example: Atomic Updates

Save as **AtomicCounterDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicCounterDemo {
    public static void main(String[] args) throws Exception {
        AtomicInteger counter = new AtomicInteger();
        ExecutorService executor = Executors.newFixedThreadPool(8);
        try {
            List<Future<?>> tasks = new ArrayList<>();
            for (int i = 0; i < 8; i++) {
                tasks.add(executor.submit(() -> {
                    for (int j = 0; j < 1_000; j++) {
                        counter.incrementAndGet();
                    }
                }));
            }
            for (Future<?> task : tasks) {
                task.get();
            }
            System.out.println("Total = " + counter.get());
        } finally {
            executor.shutdown();
        }
    }
}
~~~

~~~bash
javac AtomicCounterDemo.java
java AtomicCounterDemo
~~~

When all Futures complete successfully, the exact stdout is:

~~~text
Total = 8000
~~~

Eight tasks times 1,000 atomic incrementAndGet operations produce 8,000, and get() waits for all of them to finish before printing. This is only **counter safety within a single process**, not a solution for inventory or balances stored in a DB and updated by multiple instances.

## 4. What @Async Actually Does

When @EnableAsync (or equivalent configuration) is active and the caller goes through the Spring proxy, @Async submits work to the appropriate TaskExecutor. Spring handles interception and routing; the executor decides whether to run using a thread pool, virtual threads, or another mechanism. A TaskExecutor can even run synchronously depending on its implementation; do not infer that "every @Async always creates a new thread."

- Calling **this.asyncMethod()** within the same instance bypasses the Spring proxy in default proxy mode, preventing async advice from running. Place call boundaries between beans or design callers to use a Spring-injected bean.
- @Async does not automatically guarantee task start order, task completion order, bounded queues, timeouts, retries, or durable completion. Each depends on the executor and design.
- @Async returning Future/CompletableFuture lets you observe results/failures asynchronously; get()/join() can throw wrapped exceptions. With @Async returning void, errors do not return to the caller's stack; configure AsyncUncaughtExceptionHandler or an appropriate Future-returning contract. **Submission** errors when the pool rejects a task differ from errors **inside the task**.
- An @Async invocation does not mean the caller's transaction, security context, request context, or MDC is preserved onto the worker thread.

### Spring Integration Example: Bounded Executor, Dedicated Transaction on Worker

This example uses **Java 17+, Spring Framework, spring-jdbc, a transaction manager, and a DB with table inventory(product_id, available)**. Place the entire snippet in **BusinessAsyncConfig.java** in a component-scanned package; an ApplicationContext/DataSource/schema/transaction management setup is needed to run it. This is an integration example, **not** a standalone javac/java program.

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Configuration
@EnableAsync
public class BusinessAsyncConfig {
    @Bean("businessExecutor")
    public ThreadPoolTaskExecutor businessExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("business-");
        executor.setRejectedExecutionHandler(new ThreadPoolExecutor.AbortPolicy());
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(30);
        return executor;
    }
}

record ReservationCommand(long productId, int quantity) {
    ReservationCommand {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
    }
}

@Service
class ReservationAsyncService {
    private final ReservationTxService transactionService;

    ReservationAsyncService(ReservationTxService transactionService) {
        this.transactionService = transactionService;
    }

    @Async("businessExecutor")
    public CompletableFuture<Boolean> reserveAsync(ReservationCommand command) {
        boolean reserved = transactionService.reserve(command);
        return CompletableFuture.completedFuture(reserved);
    }
}

@Service
class ReservationTxService {
    private final JdbcTemplate jdbc;

    ReservationTxService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public boolean reserve(ReservationCommand command) {
        int updatedRows = jdbc.update(
            "UPDATE inventory SET available = available - ? " +
            "WHERE product_id = ? AND available >= ?",
            command.quantity(), command.productId(), command.quantity()
        );
        return updatedRows == 1;
    }
}
~~~

Analyzing each boundary accurately:

1. **Invocation:** a caller from another bean invokes ReservationAsyncService through the proxy; @Async submits the task to businessExecutor. Self-invocation would not trigger the proxy advice.
2. **Input data:** the ReservationCommand record is immutable; do not pass EntityManager, HttpServletRequest, connections, or mutable session objects to the worker.
3. **Transaction:** inside the worker, AsyncService calls **another bean**, ReservationTxService. @Transactional takes effect via the transaction proxy and opens/participates in a transaction via the transaction manager **on the worker thread**; it does not inherit the HTTP caller's transaction.
4. **DB invariant:** the SQL UPDATE checks available >= quantity in the same update statement. When unsatisfied, 0 rows are updated. Actual guarantees depend on the DB, schema, constraints, and transaction manager. An idempotency key should be added to avoid deducting twice if the same command is retried.
5. **Resources:** the pool is configured with 4 core, 8 max, and queue 100; tasks exceeding capacity can be rejected. These are **illustrative numbers**; measure throughput/connection pool/downstream latency before choosing values for production. Calling code needs a rejection-handling policy.
6. **Shutdown:** allows waiting for tasks up to a configured 30-second limit; crashes, kills, or power loss can still leave jobs unfinished. When durability is required, store commands in a reliable datastore/queue.

## 5. Transactions Do Not Automatically Cross Thread Boundaries

With **imperative transactions** using PlatformTransactionManager, Spring typically binds the transaction and resources to the current thread. Creating a new thread via @Async, ExecutorService, CompletableFuture.supplyAsync, or new Thread does not automatically propagate the caller's transaction.

~~~text
Thread A (HTTP request)                       Thread B (@Async worker)
@Transaction places order
  writes order (uncommitted)
  submits async task -----------------------> continues processing, outside transaction A
  commit / rollback A                         needs its own transaction when writing to DB
~~~

Consequences:

- The worker may run **before commit**. It might fail to see A's row or send a notification for an order that is later rolled back.
- If the worker needs a transaction, open one on the worker via a Spring-managed service/interceptor or TransactionTemplate.
- @Transactional does not automatically prevent lost updates, deadlocks, or races outside the DB; default isolation levels depend on the data source/manager. You must manage versioning, locks, unique constraints, and bounded conflict retries.
- Email, HTTP calls, files, and message brokers are not inherently in the same transaction as the DB. When you need to change DB state and durably emit events, consider a **transactional outbox** and **idempotent** consumer processing.
- With **ReactiveTransactionManager**, transaction context lives in the Reactor Context, not following the ThreadLocal rules of imperative transactions. Do not misapply models between the two stacks.

## 6. Thread and Request Contexts Are Not Automatically Copied

RequestContextHolder, SecurityContextHolder under its default ThreadLocal strategy, logging MDC, locale, and certain transaction resources depend on thread context. A worker thread can differ from the calling thread and is typically reused. Never assume a task automatically sees the caller's principal, correlation ID, locale, or request object.

- Pass validated business data **explicitly** via immutable commands: required orderId, tenantId, correlationId.
- To propagate security/tracing/logging context when genuinely needed, use appropriate adapters such as security-aware executors, TaskDecorator, or runtime-compatible context propagation mechanisms. Only propagate permitted data; ensure ThreadLocal is restored/cleared in finally so subsequent tasks do not receive data from previous tasks.
- Avoid carrying live request/response/session objects into tasks that outlive the request. Passing a verified userId also does not replace authorization checks at the time the work actually executes.
- InheritableThreadLocal is not a general solution for passing context into thread pools: pools usually reuse threads created earlier.

## 7. Schedulers and Message Listeners Do Not Guarantee Exactly-Once

@Scheduled/fixedRate/fixedDelay/cron triggers a method within the runtime; it **does not** persist schedules durably, recover all missed runs, or ensure only one JVM in a cluster executes. Overlapping executions can occur depending on schedule/executor configuration, and a job itself may be registered on multiple instances.

For a job scanning expired orders, always ask:

1. If the job takes longer than the period, can the current setup overlap? What is the actual configured behavior of fixedRate, fixedDelay, and the scheduler?
2. When deploying three replicas, will three copies scan the data simultaneously?
3. If the process dies mid-job, what checkpoint allows resuming?
4. If the same item is processed twice, is the effect idempotent?
5. Are there batch limits, timeouts, locks/leases, retries, or appropriate dead-letter handling?

If a single cluster-wide job is needed, use a lease/lock with a clear lifecycle, a clustering-capable scheduler, or an appropriate queue/job store; local @Scheduled does not elect a leader. For message listeners, consumer count, ordering by key/partition, ack, and redelivery depend on the broker/adapter/configuration. Consumers must handle duplicates, poison messages, and partial failures according to the actual contract.

## 8. Choosing the Right Mechanism to Protect Invariants

Example invariant: **inventory must not go negative**.

| Technique | Useful Scope | Limitations |
| --- | --- | --- |
| Immutable inputs, local variables | Prevents races from sharing variables across requests | Does not stop two DB transactions from updating concurrently |
| AtomicInteger/synchronized | A single value or critical section within **one JVM** | Does not synchronize across multiple replicas |
| ConcurrentHashMap | Individual collection operations guaranteed by the API; compute/merge can support atomic per-key updates | Does not turn multi-step/multi-resource workflows into a single transaction |
| Conditional SQL UPDATE | Checks condition and updates in the same DB statement | Does not automatically prevent duplicate logical retries of the same operation |
| Unique constraint + idempotency key | Blocks duplicate commands/orders by business key | Requires designing responses, key validity, and retry states |
| Optimistic locking/version | Detects concurrent update conflicts | Caller must handle exceptions/bounded retries |
| Transactional outbox + queue | Records event-emission intent in the same DB transaction, recovers emission process | Consumers can still receive duplicates and must be idempotent |

**Rule:** An invariant must be protected at the layer that controls all parties updating it. A mutex in a Spring singleton does not protect inventory when two replicas write to the same DB. A DB transaction does not automatically make an email-sending call atomic with an UPDATE statement.

## 9. Resource Limits and Overload Behavior

Concurrency increases the ability to handle many I/O-waiting tasks, but it also consumes CPU, memory, connection pools, locks, and external service quotas. A large MaxPoolSize does not fix a small DB pool or an external API that has hit its limit.

- **Pools and queues:** define clear bounds; long queues can increase latency and consume memory. With ThreadPoolExecutor, how the queue accepts tasks affects when the executor scales workers toward max; understand queue configuration before raising maxPoolSize.
- **Backpressure/rejection:** define how callers behave when no more tasks can be accepted: return an overload status, retry with backoff/jitter, or write to a durable queue; avoid infinite retries.
- **Timeouts and cancellation:** set deadlines for I/O, DB, and tasks; canceling a Future does not automatically reverse side effects already completed. Close resources with finally/try-with-resources.
- **Shutdown:** stop accepting new work, wait within bounds, save checkpoints, and reprocess unfinished work. Graceful shutdown does not solve sudden crashes.
- **Virtual threads:** can reduce the overhead of many compatible blocking workloads, but do not make shared mutable state thread-safe, nor do they increase DB connections or remote API quotas.

Monitor active tasks, queue depth, rejection count, queue wait time, task duration, timeouts, retries, downstream latency, and DB connection pool usage. These metrics support evidence-based policy choices rather than guessing from annotations.

## 10. Before-and-After Scenarios

### A. Singleton Service Counter

**Before:** int total++ in an @Service; two requests can lose an increment. @Transactional does not fix a Java field race.

**After:** if it is only a single-JVM internal metric, use AtomicLong or a metrics library; if it is durable loyalty points updated by multiple replicas, enforce conditions/constraints and update logic in the DB, handling optimistic conflicts/retries per the invariant.

### B. Placing an Order Then Sending an @Async Email

**Before:** a request creates an order in transaction A and then calls @Async to send an email. The worker might send the email before A commits; if A rolls back, the email was still sent.

**After:** write an "OrderCommitted" event to a transactional outbox in the same transaction A; the worker only reads committed events, sends the email, and saves the state. If the worker crashes after sending but before marking complete, the event may be re-run: you must have an idempotency key/deduplication mechanism or accept a defined duplicate-sending policy. Spring provides the programming building blocks, while the system's correctness rules are determined by business requirements.

## 11. Verifying with Concurrency and Failure Tests

1. Read the actual configuration: bean counts, bean scopes, executor used, pool/queue/rejection settings, scheduler, proxies, transaction manager, instance count, and shutdown policy.
2. Use CountDownLatch/CyclicBarrier to force two or more workers to contend simultaneously; assert invariants rather than using Thread.sleep and hoping a race shows up.
3. Run integration tests with **real DB transactions and connections** and multiple concurrent callers; verify non-negative inventory, no duplicate orders, and proper handling of optimistic conflicts/deadlocks.
4. Simulate caller rollbacks, executor rejections, timeouts, crashes/restarts, message redeliveries, and duplicate retries; verify final outcomes and recovery state.
5. Verify context propagates the right objects without leaking across tasks in the thread pool; verify correlation IDs in logs and observable saturation metrics.

## 12. Design Checklist

- I have stated the exact business invariants and which data can be updated by multiple threads/instances.
- Singleton beans are stateless or protect all shared mutable state according to the chosen concurrency model.
- Protection scope sits at the right layer: JVM, DB, queue, or distributed coordinator.
- @Async and @Transactional actually pass through proxies; no reliance on self-invocation.
- Workers have their own transactions and input data; no accidental use of the caller's transaction/request context.
- Executors/schedulers have bounds, failure policies, and defined behavior on restart/shutdown.
- Tasks that can be retried/duplicated are designed to be idempotent where needed.
- Concurrency tests, failure tests, and metrics confirm these assumptions.

**Takeaway:** Spring manages **how beans and tasks are created, invoked, and executed according to configuration**. Business code must ensure **correct, consistent, and recoverable outcomes** under contention, overload, and failure. No single annotation replaces invariant design.

## Official Reference Documentation

- Spring Framework – Task Execution and Scheduling: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Spring Framework – Bean Scopes: https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html
- Spring Framework – Declarative Transaction Implementation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Spring Framework – Proxying Mechanisms: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Java Language Specification 17, Chapter 17 – Threads and Locks: https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html