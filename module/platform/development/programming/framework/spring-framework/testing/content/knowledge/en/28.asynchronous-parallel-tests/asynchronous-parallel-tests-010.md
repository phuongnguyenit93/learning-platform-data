# Transaction or Request Context Does Not Automatically Propagate to Other Threads

## 1. Why does switching threads lose context?

In a Spring application, much information is bound to the current thread so components deep in the call stack can access it without passing parameters through every method. For example:

- Imperative transactions managed by Spring are typically bound to the thread executing the transaction.
- Servlet request context is accessed via `RequestContextHolder`, which is also bound to the current thread by default.
- Data such as MDC logging or certain security contexts use their own per-thread storage mechanisms.

When code runs synchronously, methods are normally invoked on the same thread, so these components can read the established context. When work is handed off to another thread via `@Async`, `Executor`, `CompletableFuture`, or a thread pool, the new thread has its own state. Spring does not automatically transfer the entire transaction or request context from the calling thread to the executing thread.

This is essential to understand when designing asynchronous and parallel processing: passing an object, a lambda, or a `CompletableFuture` to an executor does not mean transferring the original thread's execution environment.

## 2. ThreadLocal and context scope

`ThreadLocal` stores a separate value per thread. Two threads can use the same `ThreadLocal` variable, yet each thread reads its own value.

```text
HTTP request handling thread
  ThreadLocal<RequestAttributes> = request A
  Transaction context             = transaction A
             |
             | submit task to Executor
             v
Thread pool worker thread
  ThreadLocal<RequestAttributes> = null (or worker's own value)
  Transaction context             = no transaction A
```

The worker thread does not automatically receive a copy of the calling thread's transaction or request context. If the worker previously processed another task, it may even have leftover state if prior code did not clean up properly. Therefore, context must be established and restored carefully per task.

`InheritableThreadLocal` behaves differently: a newly created child thread can inherit values from the parent thread at creation time. However, thread pools normally create workers once and reuse them. An existing worker does not inherit new values from each subsequently submitted request. Inheritance can also cause a worker to retain references to a request that has already finished. Thus, `InheritableThreadLocal` is not a safe context propagation mechanism for thread pools.

## 3. Imperative transactions do not propagate to other threads

With `PlatformTransactionManager` and imperative `@Transactional`, Spring typically stores transaction resources and synchronization state in `TransactionSynchronizationManager`, bound to the current thread.

When a `@Transactional` method is invoked through a Spring proxy, the transaction manager starts or joins a transaction on the thread executing that method. When the method finishes, Spring commits or rolls back based on the execution outcome.

If a method inside a transaction launches work running on another thread, the worker thread does not participate in the original transaction. For example:

```java
@Service
class OrderService {

    private final Executor taskExecutor;
    private final OrderRepository orderRepository;

    OrderService(Executor taskExecutor, OrderRepository orderRepository) {
        this.taskExecutor = taskExecutor;
        this.orderRepository = orderRepository;
    }

    @Transactional
    public void updateAndSchedule(long orderId) {
        Order order = orderRepository.findById(orderId).orElseThrow();
        order.markProcessing();

        // taskExecutor here is a thread-pool executor, not an executor running directly on the caller.
        taskExecutor.execute(() -> {
            // This is another thread; the transaction of updateAndSchedule does not follow.
            orderRepository.findById(orderId);
        });
    }
}
```

In this example, the transaction wrapping `updateAndSchedule(...)` only governs operations on the calling thread. The lambda is executed by the executor on a worker thread and does not automatically join that transaction. If the worker needs to read data, it runs in whatever transaction exists on the worker (if any) or without a transaction, depending on how the repository/service is configured.

This can cause several subtle issues:

- The worker reads data before the calling thread's transaction commits and therefore does not see uncommitted changes.
- The worker does not share the same rollback boundary as the calling thread. If the original transaction rolls back, the launched task can still proceed.
- An `EntityManager`, Hibernate `Session`, JDBC `Connection`, or transaction resource cannot be carried over to a worker for shared use.
- Worker operations can commit independently, even if the request's transaction later rolls back.

Do not pass a `Connection`, `EntityManager`, `Session`, transaction status, or transaction-managed persistence objects across an executor. Pass IDs and necessary immutable data instead; the worker reloads data inside its own transaction.

## 4. Creating a separate transaction for background work

If a background task needs database access, have the worker invoke a transactional method through a Spring proxy. A transaction is opened on the worker execution thread with an independent lifecycle.

```java
import java.util.concurrent.CompletableFuture;

import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class OrderAsyncFacade {

    private final OrderWorker orderWorker;

    OrderAsyncFacade(OrderWorker orderWorker) {
        this.orderWorker = orderWorker;
    }

    @Async("applicationTaskExecutor")
    public CompletableFuture<Void> processAsync(long orderId) {
        orderWorker.process(orderId);
        return CompletableFuture.completedFuture(null);
    }
}

@Service
class OrderWorker {

    private final OrderRepository orderRepository;

    OrderWorker(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional
    public void process(long orderId) {
        Order order = orderRepository.findById(orderId).orElseThrow();
        order.completeProcessing();
    }
}
```

Here `OrderAsyncFacade` and `OrderWorker` are two separate Spring beans. When `processAsync(...)` is invoked through the `@Async` proxy, Spring dispatches the call to the executor. On the worker thread, calling `orderWorker.process(...)` passes through the transaction proxy of the `OrderWorker` bean, opening a fresh transaction directly on that thread.

Async processing must be enabled in application configuration, such as via `@EnableAsync`, with an appropriate executor configured:

```java
@Configuration
@EnableAsync
class AsyncConfiguration {
    // applicationTaskExecutor can be declared here.
}
```

Another option is using `Executor` directly:

```java
taskExecutor.execute(() -> orderWorker.process(orderId));
```

The key point remains that `orderWorker` must be an injected Spring bean and the `process(...)` call must go through the proxy. Manually creating the worker with `new OrderWorker(...)` or calling a `@Transactional` method via self-invocation on the same object may bypass the transaction interceptor.

### REQUIRED and REQUIRES_NEW in workers

When a worker starts running on a new thread, the calling thread's transaction does not exist there. Therefore:

- `Propagation.REQUIRED` (default) joins an existing transaction on the worker if one exists; otherwise it creates a new transaction.
- `Propagation.REQUIRES_NEW` always requires an independent transaction on the current thread. If the worker has no transaction yet, it creates a new one; if the worker already has a transaction, that transaction is suspended while a new one is opened.
- `Propagation.MANDATORY` requires an active transaction on the current thread and fails if none exists.

`REQUIRES_NEW` does not mean taking the calling thread's transaction and moving it to the worker. It only decides how the transaction manager handles any transaction already present on the thread executing the method.

## 5. Do not dispatch tasks before required data is committed

A common design mistake is submitting background work right inside a transaction that writes data, when the worker needs to read that newly created data:

```java
@Transactional
public void createOrder(CreateOrderCommand command) {
    Order order = orderRepository.save(Order.from(command));
    asyncFacade.processAsync(order.getId());
}
```

`processAsync(...)` can start before `createOrder(...)`'s transaction commits. Even with its own transaction, the worker cannot see uncommitted data from the original transaction. It may fail to find the order or process stale state.

If the task must run only after the transaction succeeds, schedule the work via an after-commit event. For example:

```java
@Service
class OrderApplicationService {

    private final OrderRepository orderRepository;
    private final ApplicationEventPublisher events;

    OrderApplicationService(
            OrderRepository orderRepository,
            ApplicationEventPublisher events) {
        this.orderRepository = orderRepository;
        this.events = events;
    }

    @Transactional
    public void createOrder(CreateOrderCommand command) {
        Order order = orderRepository.save(Order.from(command));
        events.publishEvent(new OrderCreated(order.getId()));
    }
}

record OrderCreated(long orderId) {
}

@Component
class OrderCreatedListener {

    private final OrderAsyncFacade asyncFacade;

    OrderCreatedListener(OrderAsyncFacade asyncFacade) {
        this.asyncFacade = asyncFacade;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterOrderCreated(OrderCreated event) {
        asyncFacade.processAsync(event.orderId());
    }
}
```

`@TransactionalEventListener(phase = AFTER_COMMIT)` triggers the listener only after the event-publishing transaction commits successfully. The listener then invokes the async facade so the worker begins processing committed data.

In-memory events are not a durable queue. If the application stops after commit but before the task is submitted or completed, work can be lost. When processing requires at-least-once delivery or crash recovery, consider a transactional outbox or a message broker with durable storage.

## 6. Request context is also thread-bound

In Servlet applications, `RequestContextHolder` provides the `RequestAttributes` of the current request. Spring uses this context for features such as request-scoped beans and accessing request attributes from code that does not directly receive `HttpServletRequest`.

Normally `DispatcherServlet` sets up the request context during request handling and clears it when the dispatch finishes. By default, the context is bound to the thread handling the request. When code submits an arbitrary task to an executor, the worker does not automatically receive the original request's `RequestAttributes`.

Example:

```java
@Service
class AuditAsyncService {

    @Async
    public CompletableFuture<Void> writeAudit() {
        RequestAttributes attributes = RequestContextHolder.getRequestAttributes();
        // On a regular worker thread, attributes can be null.
        return CompletableFuture.completedFuture(null);
    }
}
```

If worker code calls `RequestContextHolder.currentRequestAttributes()` when no request context is bound, Spring throws `IllegalStateException` with a message similar to `No thread-bound request found`.

Spring MVC has context management mechanisms for certain async flows orchestrated by the framework itself, such as `Callable` processing and the subsequent async dispatch. That does not mean every task submitted manually by the application via `@Async`, `Executor`, or `CompletableFuture` automatically receives the request context. In particular, `DeferredResult` callbacks may run on whichever thread completes the result; do not assume the callback thread holds the request context.

## 7. Do not retain request objects or request-scoped beans for background tasks

A request-scoped bean is created and managed according to the HTTP request lifecycle. A scoped proxy resolves the instance from the current request when invoked. If a worker runs outside a request context, the proxy has no active request to resolve the instance and can throw a scope-inactive error.

Do not pass the following objects to a background task and use them after the request finishes:

- `HttpServletRequest`, `HttpServletResponse`, or `ServletRequestAttributes`.
- Beans annotated with `@RequestScope` or their proxies.
- Streams or input bodies tied to the request that the container may close after handling.
- Mutable objects belonging to the request that could be modified concurrently.

Instead, extract the needed values while the request is active and pass them as plain input data:

```java
import java.security.Principal;
import java.util.Locale;
import java.util.concurrent.CompletableFuture;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.ResponseEntity;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

record RequestMetadata(String correlationId, String tenantId, Locale locale) {
}

@RestController
class ExportController {

    private final ExportAsyncService exportService;

    ExportController(ExportAsyncService exportService) {
        this.exportService = exportService;
    }

    @PostMapping("/exports")
    ResponseEntity<Void> startExport(
            HttpServletRequest request,
            Principal principal) {

        RequestMetadata metadata = new RequestMetadata(
                request.getHeader("X-Correlation-Id"),
                request.getHeader("X-Tenant-Id"),
                request.getLocale());

        exportService.start(principal.getName(), metadata);
        return ResponseEntity.accepted().build();
    }
}

@Service
class ExportAsyncService {

    @Async
    public CompletableFuture<Void> start(String username, RequestMetadata metadata) {
        // Use the extracted data, do not access HttpServletRequest.
        return CompletableFuture.completedFuture(null);
    }
}
```

`RequestMetadata` is an immutable record holding the exact values needed for background work. In practice, the worker can use the correlation ID for logging, the tenant ID to scope data, and the locale for content generation. Validate and verify input values before submitting; never assume client-sent headers are trustworthy.

## 8. Why should InheritableThreadLocal not be enabled for thread pools?

`RequestContextHolder.setRequestAttributes(attributes, true)` can store request attributes in an `InheritableThreadLocal`. Child threads created afterward can inherit a reference to those attributes. This only makes sense for newly created child threads with a short, controlled lifecycle at the right moment.

With thread pools, workers are typically pre-created and reused across many tasks. An existing worker does not pick up new values from the submitting thread. If a worker was created while request A was active, it can hold a reference to request A and continue carrying it after request A has ended. This can cause data leaks across requests or access to expired resources.

Therefore, do not enable inheritable mode to force request context propagation into a shared executor. Pass required business data via parameters and keep the request lifecycle within HTTP handling scope.

## 9. TaskDecorator and controlled context propagation

Certain metadata contexts such as MDC logging, trace IDs, or observation contexts may need to propagate across an executor so worker logs carry the same correlation/trace. Spring provides `TaskDecorator` to wrap a `Runnable` before the executor runs it. Micrometer Context Propagation can also capture and restore registered contexts through appropriate accessors.

`ContextPropagatingTaskDecorator` has been available since Spring Framework 6.1 and requires `io.micrometer:context-propagation` on the classpath. With Gradle and proper dependency management, you can declare:

```groovy
dependencies {
    implementation("io.micrometer:context-propagation")
}
```

Example configuring an executor with `ContextPropagatingTaskDecorator`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.TaskDecorator;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
class WorkerConfiguration {

    @Bean
    TaskDecorator contextPropagatingTaskDecorator() {
        return new ContextPropagatingTaskDecorator();
    }

    @Bean("applicationTaskExecutor")
    ThreadPoolTaskExecutor applicationTaskExecutor(TaskDecorator decorator) {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("app-worker-");
        executor.setTaskDecorator(decorator);
        executor.initialize();
        return executor;
    }
}
```

`ContextPropagatingTaskDecorator` uses Micrometer Context Propagation to restore registered contexts for the task. Propagation relies on corresponding `ThreadLocalAccessor` implementations; it does not automatically copy every `ThreadLocal` variable in the application.

Task decorators suit metadata contexts with well-defined lifecycles and propagation rules. Do not register or propagate Servlet request attributes into work that may run after the response finishes unless the application has a strictly controlled lifecycle mechanism of its own. Do not use a decorator to copy transaction resources, JDBC connections, `EntityManager`, or transaction synchronization to a worker. Transactions must be opened and closed properly on the worker thread by a transaction manager.

Similarly, if `SecurityContext` needs to transfer to async tasks, use Spring Security's integration such as `DelegatingSecurityContextAsyncTaskExecutor` or the mechanism corresponding to your version. Security context is its own type of context; propagating it does not imply request context or transaction context is also propagated.

## 10. Distinguishing imperative transactions from reactive contexts

The rules above describe imperative transactions, typically managed by `PlatformTransactionManager` and bound to a thread. With Spring WebFlux or reactive data access, transactions managed by `ReactiveTransactionManager` are stored in the Reactor `Context`, without relying on a fixed thread.

Reactor `Context` travels with the subscriber along the same reactive chain, so reactive transactions can continue across scheduler-switching operators such as `publishOn` or `subscribeOn`. This is a key difference compared to imperative `ThreadLocal`.

However, Reactor Context also does not appear automatically in arbitrary detached work. When creating an independent subscription, calling `CompletableFuture`, submitting a `Runnable` directly to an executor, or sending data to another system, an explicit bridge or data-passing mechanism is needed. Do not transfer an active imperative transaction into a reactive chain or vice versa by copying ThreadLocals.

| Context type | How Spring typically manages it | Behavior when switching scheduler/thread |
|---|---|---|
| Imperative transaction | Thread-bound resources and synchronization via `TransactionSynchronizationManager` | Does not automatically propagate to other threads. |
| Servlet request context | `RequestAttributes` in `RequestContextHolder`, thread-bound by default | Does not automatically propagate to arbitrary executor tasks; MVC has dedicated handling for some async lifecycles. |
| Reactive transaction | Reactor `Context` used by `ReactiveTransactionManager` | Follows the subscriber within the same reactive chain, even across scheduler switches; does not automatically propagate to independent subscriptions. |
| MDC/tracing/security context | Depends on integration mechanism and registered accessors | Requires an explicit propagation mechanism; cannot be inferred from whether transaction/request context propagates. |

## 11. Testing to verify context does not propagate automatically

You can write a small test to observe the difference between the request thread and a worker. The example below binds request attributes to the test thread and then reads `RequestContextHolder` from an executor thread:

```java
import static org.junit.jupiter.api.Assertions.assertNull;

import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.RequestAttributes;
import org.springframework.web.context.request.ServletRequestAttributes;

class RequestContextPropagationTests {

    @Test
    void requestAttributesAreNotAutomaticallyAvailableInWorkerThread() throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        MockHttpServletRequest request = new MockHttpServletRequest();
        ServletRequestAttributes attributes = new ServletRequestAttributes(request);

        RequestContextHolder.setRequestAttributes(attributes);
        try {
            Callable<RequestAttributes> readWorkerContext =
                    RequestContextHolder::getRequestAttributes;
            RequestAttributes workerAttributes = executor.submit(readWorkerContext)
                    .get(2, TimeUnit.SECONDS);

            assertNull(workerAttributes);
        } finally {
            attributes.requestCompleted();
            RequestContextHolder.resetRequestAttributes();
            executor.shutdownNow();
        }
    }
}
```

The test uses `RequestContextHolder`'s default `ThreadLocal`. The worker thread does not receive the request attributes bound on the test thread. The `finally` block completes the request attributes, clears context from the calling thread, and stops the executor so the test leaves no worker thread behind.

You can test transactions similarly using a Spring test running inside a transaction on the test thread:

```java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@SpringJUnitConfig(TestDatabaseConfiguration.class)
class TransactionContextPropagationTests {

    @Test
    @Transactional
    void callerTransactionIsNotActiveOnWorkerThread() throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            assertTrue(TransactionSynchronizationManager.isActualTransactionActive());

            Callable<Boolean> checkWorkerTransaction =
                    TransactionSynchronizationManager::isActualTransactionActive;
            boolean workerHasTransaction = executor.submit(checkWorkerTransaction)
                    .get(2, TimeUnit.SECONDS);

            assertFalse(workerHasTransaction);
        } finally {
            executor.shutdownNow();
        }
    }
}
```

This example assumes `TestDatabaseConfiguration` configures a valid `PlatformTransactionManager` so Spring Test opens a transaction for the test method. The test transaction is bound to the test execution thread; the executor worker does not automatically join that transaction. In real tests, `TestDatabaseConfiguration` can be replaced with the application's persistence configuration.

## 12. Common errors and how to handle them

| Symptom | Cause | How to handle |
|---|---|---|
| Worker does not see recently written data | Task ran before the caller transaction committed; caller transaction does not propagate to worker. | Run after commit via a transactional event listener or outbox; worker opens its own transaction and reloads by ID. |
| `No thread-bound request found` in `@Async` | Worker thread lacks the HTTP request's `RequestAttributes`. | Extract required data from the request and pass it into the task as parameters. |
| Request-scoped bean reports inactive scope | Worker runs outside the request lifecycle or has no valid request context. | Do not access request-scoped beans from background tasks; convert required data into an immutable DTO/record. |
| Transaction rolled back yet background task still wrote data | Worker has its own transaction or runs outside the caller transaction. | Submit only after commit; use an outbox if delivery guarantees are needed; define the worker's transaction boundary explicitly. |
| Thread pool uses wrong tenant or correlation ID | ThreadLocal was not cleaned up or context was propagated with the wrong lifecycle. | Use controlled context propagation, restore state in `finally`, and prefer explicit metadata passing. |
| `@Transactional` does not work in worker | Method was invoked via self-invocation, a manually created object, or bypassed the Spring proxy. | Place transactional methods on an injected bean and call through the proxy. |
| Used `REQUIRES_NEW` yet still does not see caller transaction | `REQUIRES_NEW` creates an independent transaction on the current thread; it does not transfer a transaction from another thread. | Pass IDs/data and open a new transaction in the worker; wait for the caller to commit if newly written data must be read. |
| Reactive transaction lost when launching separate work | Work was detached from the current Reactor subscriber/context. | Keep processing within the same reactive chain or pass context/data explicitly; avoid creating detached subscriptions. |

## 13. Design principles

- Treat imperative transactions and Servlet request contexts as thread-scoped contexts with concrete lifecycles.
- Do not pass JDBC connections, `EntityManager`, Hibernate `Session`, Servlet request/response objects, or request-scoped beans to workers.
- Pass IDs and necessary immutable data to background tasks; workers load data within their own scope.
- Open a separate transaction on the worker via a Spring bean annotated with `@Transactional` and called through its proxy.
- If a task depends on newly committed data, launch it only after commit; use a transactional outbox when durability is required.
- Do not use `InheritableThreadLocal` as a general solution for thread pools.
- Use `TaskDecorator`, Micrometer Context Propagation, or specialized mechanisms to propagate metadata such as trace/MDC/security when needed; never copy transaction resources.
- Distinguish imperative ThreadLocal context from Reactor Context in reactive applications.
- Test explicitly which context, transaction, and data a worker sees rather than relying on implicit thread state.

## 14. Conclusion

Spring's imperative transactions and request contexts are normally bound to the processing thread. When work moves to an executor or `@Async`, the worker does not automatically join the calling thread's transaction or inherit its request attributes. Pass necessary business data explicitly, open a fresh transaction in the worker via a Spring proxy, and run tasks only after commit if they depend on newly written data. For metadata such as traces or MDC, use controlled context propagation; do not use it to share transaction resources or extend a Servlet request's lifecycle.
