# Request Context Does Not Automatically Propagate to a New Thread

## 1. The Problem: A Listener Processes an Event on a Different Thread from the Request

In a Spring MVC application, an HTTP request is normally handled on a servlet container thread. Spring binds `RequestAttributes` to that thread so APIs such as `RequestContextHolder`, `request scope` beans, and various web components can access information about the current request.

When the application publishes an event during a request:

~~~text
HTTP request /orders
    |
    v
Servlet thread: http-nio-8080-exec-1
  RequestContextHolder = RequestAttributes of the current request
    |
    +-- publishEvent(new OrderPlaced(...))
            |
            +-- default synchronous @EventListener:
            |      runs on the servlet thread itself
            |      -> can see the request's RequestAttributes
            |
            +-- @Async @EventListener:
                   runs on executor thread event-1
                   -> does NOT automatically have RequestAttributes
~~~

A common trap is a listener calling:

~~~java
RequestAttributes attributes =
    RequestContextHolder.currentRequestAttributes();
~~~

That snippet works on the request thread, but on an asynchronous event-handling thread it can throw `IllegalStateException` with a message like **"No thread-bound request found"**. If `RequestContextHolder.getRequestAttributes()` is used instead, the result is typically `null` rather than an exception.

Crucially: **the event payload is still passed to the listener**, whereas **the thread-bound request context is not automatically transferred**. These are two separate mechanisms.

## 2. What Is Request Context in Spring?

In Spring Web MVC/Servlet, request context is typically represented by `org.springframework.web.context.request.RequestAttributes`. It provides access to scoped attributes, such as `RequestAttributes.SCOPE_REQUEST`.

`RequestContextHolder` keeps this reference in thread-bound storage; depending on configuration, it may use `ThreadLocal` or `InheritableThreadLocal`. Related components include:

| Component | Role |
| --- | --- |
| `DispatcherServlet` | Normally supplies request context during Spring MVC HTTP dispatch |
| `RequestContextFilter` / `RequestContextListener` | Can bind request context for appropriate servlet processing flows |
| `RequestContextHolder.getRequestAttributes()` | Retrieves the request attributes bound to the thread, or `null` if none |
| `RequestContextHolder.currentRequestAttributes()` | Requires request attributes to be present; throws an exception if missing |
| `@RequestScope` bean | Bean whose lifecycle is tied to the request; accessing it outside a valid request context normally fails |
| `ThreadPoolTaskExecutor` / `@Async` | Runs tasks on an executor thread; does not automatically transport all thread-bound contexts |

A request may contain data such as `requestId`, `tenantId`, language, headers, or principal. However, **not all of this data lives in the same context**. Distinguish among:

- `RequestContextHolder`: Spring Web request attributes.
- `LocaleContextHolder`: thread-bound locale/time zone.
- `SecurityContextHolder`: Spring Security authentication/security context.
- Logging framework MDC: logging information such as request ID, correlation ID.
- Imperative transaction context: transaction resources bound to the thread by Spring.

Propagating one of these contexts **does not automatically propagate all the others**. Nor should you copy all contexts just because a listener needs a `correlationId` string.

## 3. Why Doesn't ThreadLocal Automatically Travel with the Event?

`ThreadLocal<T>` holds a **per-thread** value, not a field on the event object and not a shared global variable.

Conceptual example:

~~~text
Thread A (request)              Thread B (executor)
--------------------            -------------------
ThreadLocal<Request> = R1       ThreadLocal<Request> = null

publishEvent(event)
    |
    +-- executor.execute(task)
                           -->  listener(event)
                                event exists
                                request context does not automatically appear
~~~

`ApplicationEventPublisher.publishEvent(...)` passes the **event object** to the multicaster mechanism. When a listener runs synchronously, it usually runs on the publisher's thread and can observe the current thread context. When `@Async` is used or a custom `ApplicationEventMulticaster` is configured with a `TaskExecutor`, the listener can execute on another thread and lose the request's thread-local bindings.

Do not confuse these:

- **A shared singleton bean** does not mean a shared request context.
- **An event containing a request ID** does not mean `RequestContextHolder` is also propagated.
- **A `TaskExecutor` running in the same Java process** does not mean the source thread's thread-local appears on the target thread.
- **Calling `publishEvent` inside a transaction** does not mean an asynchronous listener participates in that transaction.

In systems using a thread pool, worker threads are reused across multiple requests; accidentally binding request context from request A onto a thread and leaving it behind can cause request B to see stale data. This is both a **correctness and a security risk**.

## 4. Runnable Java 17+ Example: Request Has Context, @Async Listener Does Not

This demo uses **Spring Framework 6.2.18**, `spring-web`, `spring-test`, and a simulated request using `MockHttpServletRequest`. No web server is needed; the goal is to reproduce the exact difference between the request thread and the executor thread. The useful `correlationId` data is safely passed via the **`OrderPlaced` payload**, rather than expecting `RequestContextHolder` to cross to the new thread automatically.

### Project Structure

~~~text
request-context-async-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/RequestContextDemo.java
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'request-context-async-demo'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.18'
    implementation 'org.springframework:spring-web:6.2.18'
    implementation 'org.springframework:spring-test:6.2.18'
    implementation 'jakarta.servlet:jakarta.servlet-api:6.0.0'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.RequestContextDemo'
}
~~~

File `src/main/java/demo/RequestContextDemo.java`:

~~~java
package demo;

import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.web.context.request.RequestAttributes;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

@Configuration
@EnableAsync
public class RequestContextDemo {

    // Payload is a value snapshot. Do not carry HttpServletRequest
    // or RequestAttributes onto another thread.
    public record OrderPlaced(long orderId, String correlationId) {}

    public record Observation(
        String contextCorrelationId,
        String eventCorrelationId,
        boolean onExecutorThread
    ) {}

    @Bean(name = "taskExecutor")
    ThreadPoolTaskExecutor taskExecutor() {
        var executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(1);
        executor.setQueueCapacity(10);
        executor.setThreadNamePrefix("event-");
        return executor;
    }

    @Bean
    BlockingQueue<Observation> observations() {
        return new LinkedBlockingQueue<>();
    }

    @Bean
    AsyncOrderListener asyncOrderListener(
            BlockingQueue<Observation> results) {
        return new AsyncOrderListener(results);
    }

    // Do not mark class/method final: @Async requires a proxy
    // in standard proxy configuration.
    public static class AsyncOrderListener {
        private final BlockingQueue<Observation> results;

        public AsyncOrderListener(BlockingQueue<Observation> results) {
            this.results = results;
        }

        @Async
        @EventListener
        public void onOrderPlaced(OrderPlaced event) {
            RequestAttributes attributes =
                RequestContextHolder.getRequestAttributes();

            String contextId = attributes == null
                ? "<none>"
                : String.valueOf(attributes.getAttribute(
                    "correlationId",
                    RequestAttributes.SCOPE_REQUEST
                ));

            results.add(new Observation(
                contextId,
                event.correlationId(),
                Thread.currentThread().getName().startsWith("event-")
            ));
        }
    }

    public static void main(String[] args) throws Exception {
        try (var context = new AnnotationConfigApplicationContext(
                RequestContextDemo.class)) {

            // Simulate the HTTP request-handling thread.
            var request = new MockHttpServletRequest();
            request.setAttribute("correlationId", "REQ-101");

            RequestContextHolder.setRequestAttributes(
                new ServletRequestAttributes(request),
                false  // Do NOT enable InheritableThreadLocal
            );

            try {
                String requestId = String.valueOf(
                    RequestContextHolder.currentRequestAttributes()
                        .getAttribute(
                            "correlationId",
                            RequestAttributes.SCOPE_REQUEST
                        )
                );
                System.out.println("request thread context: " + requestId);

                // Put required data into an immutable event payload.
                context.publishEvent(new OrderPlaced(101L, requestId));

                // Wait for the executor listener to finish for verification;
                // do not block in a real web request-handling thread.
                // Queue may not have the result immediately after publishEvent.
                // Wait for the worker thread signal up to 10 seconds.
                @SuppressWarnings("unchecked")
                BlockingQueue<Observation> queue =
                    (BlockingQueue<Observation>) context
                        .getBean("observations");
                Observation result = queue.poll(10, TimeUnit.SECONDS);

                if (result == null) {
                    throw new IllegalStateException(
                        "Async listener did not finish"
                    );
                }

                System.out.println(
                    "listener on executor: " + result.onExecutorThread()
                );
                System.out.println(
                    "worker request context: " + result.contextCorrelationId()
                );
                System.out.println(
                    "event correlationId: " + result.eventCorrelationId()
                );
            } finally {
                // Unbind request context from the source thread.
                RequestContextHolder.resetRequestAttributes();
            }
        }
    }
}
~~~

**Note on waiting for events:** in the demo, `poll(timeout)` is used to turn the asynchronous result into inspectable stdout. In real Spring MVC applications, you should not use `block()` or wait on the request thread just for work that business rules allow to run in the background. Use job status, durable queues, or an appropriate response API instead.

Run with JDK 17+ and Gradle / Gradle Wrapper if present:

~~~bash
gradle run --quiet
# Linux/macOS with wrapper: ./gradlew run --quiet
# Windows with wrapper: gradlew.bat run --quiet
~~~

Lines printed by the program itself:

~~~text
request thread context: REQ-101
listener on executor: true
worker request context: <none>
event correlationId: REQ-101
~~~

Explanation:

1. `RequestContextHolder.setRequestAttributes(..., false)` binds the simulated request to the **main thread**; hence the first line reads `REQ-101`.
2. `context.publishEvent(...)` publishes `OrderPlaced` containing a copy of the correlation ID string.
3. `@Async` combined with `@EnableAsync` dispatches the listener onto `ThreadPoolTaskExecutor`; this is a different thread. With no `RequestAttributes` propagation mechanism, the listener sees `null` and prints `<none>`.
4. Even though request context did not travel along, **the `OrderPlaced.correlationId` payload remains intact**, because Spring delivers the event object to the listener.
5. Finally, `resetRequestAttributes()` ensures the request binding on the original thread is cleared; the executor shuts down when the Spring context closes.

**Why does the demo use `MockHttpServletRequest`?** It reproduces `ServletRequestAttributes` without needing a servlet container. This lesson is about **thread-local context**, not a full simulation of the HTTP lifecycle, Spring Security, or transactions.

## 5. Recommended Approach: Snapshot Required Data into the Event Payload

If a listener only needs `requestId`, `correlationId`, `tenantId`, or the initiator's ID, extract **authorized, usable values** right at the boundary where valid context exists, and publish an event containing those values.

Spring MVC example:

~~~java
// Illustrative snippet in controller/service; not a standalone file.
@PostMapping("/orders")
public ResponseEntity<Void> placeOrder(
        @RequestHeader("X-Correlation-ID") String correlationId,
        @RequestBody PlaceOrder command) {

    // Validate header, access permissions, format, and ID size.
    applicationService.place(command, correlationId);
    return ResponseEntity.accepted().build();
}
~~~

At the application layer:

~~~java
// Illustrative snippet; requires application types and beans.
public void place(PlaceOrder command, String correlationId) {
    Order order = orderDomainService.place(command);
    publisher.publishEvent(new OrderPlaced(
        order.getId(),
        correlationId
    ));
}
~~~

Asynchronous listener:

~~~java
@Async
@EventListener
public void onOrderPlaced(OrderPlaced event) {
    notificationService.enqueue(
        event.orderId(),
        event.correlationId()
    );
}
~~~

This is a clean approach because:

- It does not depend on the request remaining alive after the controller returns a response.
- It avoids copying the entire HTTP request, session, or request-scoped beans to a worker.
- It makes consumers easy to test: just construct the event payload.
- It upgrades easily from local events to a broker/outbox because metadata is part of the contract.
- It prevents request state leakage across tasks running in a thread pool.

**Do not put all headers, access tokens, cookies, or a mutable `HttpServletRequest` into an event**. Extract only fields with a clear purpose, following privacy and security policies. If authorization is needed, the worker must verify permissions against its own trust boundary; a `userId` string in an event does not by itself prove access rights.

## 6. Common Pitfalls

### Pitfall 1 — Trying to Call currentRequestAttributes() Inside an @Async Listener

~~~java
@Async
@EventListener
public void handle(OrderPlaced event) {
    String id = (String) RequestContextHolder
        .currentRequestAttributes()
        .getAttribute("correlationId", RequestAttributes.SCOPE_REQUEST);
}
~~~

This can throw `IllegalStateException` when the worker has no request context. In an async `void` listener, exceptions also normally **do not propagate back to the publishing thread**, so you need logging, `AsyncUncaughtExceptionHandler`, or task-monitoring mechanisms.

Fix: use `event.correlationId()` under a clear contract, or implement controlled propagation when the full execution context is genuinely needed.

### Pitfall 2 — Setting inheritable=true to "Fix All Threads"

~~~java
RequestContextHolder.setRequestAttributes(attributes, true);
~~~

The `true` argument uses `InheritableThreadLocal` so **newly created child threads** can inherit the value. It is **not a general solution for thread pools**:

- Threads in the pool may already exist, so they inherit nothing.
- A thread pool may create a new thread while serving request A and then **reuse that thread** for request B; the old request context risks being retained or leaked.
- Request A may already have finished when the task runs, rendering its request attributes invalid.

Spring's Javadoc warns against enabling request context inheritance on pooled threads that may dynamically spawn threads under load. `RequestContextFilter.setThreadContextInheritable` defaults to `false` for that reason.

### Pitfall 3 — Copying HttpServletRequest or Request-Scoped Beans to a Background Task

~~~java
// Anti-pattern; not a standalone compilable file:
executor.execute(() -> {
    String token = request.getHeader("Authorization");
    doBackgroundWork(token);
});
~~~

The task may run after the request ends; furthermore, passing raw tokens directly to another task easily causes security and lifecycle-management issues. Never rely on a live request object when a listener executes. Extract only the non-sensitive data needed, and design independent authorization and appropriate processing deadlines.

### Pitfall 4 — Forgetting to Clean Up ThreadLocal on the Worker

If an application genuinely must propagate certain **execution context** via a `TaskDecorator`, the runnable wrapper must **restore the previous state or clear it in `finally`**. Forgetting cleanup causes a worker serving request B to read request A's metadata. Never use `ThreadLocal` as a permanent data store.

### Pitfall 5 — Confusing Logger MDC, Security, and Request Scope

Enabling context propagation for MDC/observability **does not mean** request-scoped beans automatically work on every executor. Security context uses its own mechanism, such as Spring Security's executor wrappers when appropriate. If a context is not supplied, never "fix" it by fabricating a fake principal.

## 7. When to Use TaskDecorator or ContextPropagatingTaskDecorator?

`ThreadPoolTaskExecutor` supports `TaskDecorator` to wrap a `Runnable` before handing it to a worker. This is an extension point for propagating controlled **execution metadata**, such as logging correlation and observation/trace context.

In Spring 6.1+, `org.springframework.core.task.support.ContextPropagatingTaskDecorator` supports restoring context based on the **Micrometer Context Propagation** library and its registered accessors.

**Illustrative** configuration example, not included in the section 4 demo:

~~~java
@Bean
ThreadPoolTaskExecutor taskExecutor() {
    var executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setThreadNamePrefix("event-");

    // Requires the micrometer-context-propagation dependency and
    // appropriately registered ThreadLocalAccessor implementations.
    executor.setTaskDecorator(
        new ContextPropagatingTaskDecorator()
    );
    return executor;
}
~~~

Requires importing `org.springframework.core.task.support.ContextPropagatingTaskDecorator` and having the corresponding Micrometer dependency. Key points:

1. Decorators should be used for **lifecycle-safe metadata**, such as tracing/log context, not to copy an entire `ServletRequestAttributes` by default.
2. It is **not magic**: only contexts with an appropriate capture/restore mechanism and accessor are propagated.
3. Capture/restore introduces overhead; benchmark under workload.
4. Restoring/clearing in `finally` is critical so pooled threads are never polluted.
5. If the goal is merely to use a `correlationId` in a listener, **an explicit event payload is usually simpler**.

### Does Spring Ever Bind Request Context Automatically in Async Servlets?

Yes. An **async servlet dispatch** passing through `DispatcherServlet` or `RequestContextFilter` may have request context bound by Spring for that **dispatch thread**. However, that is behavior of the **container-managed async servlet lifecycle**, not a guarantee for arbitrary `@Async` methods, executor tasks, or application-triggered event listeners. Distinguish the two mechanisms clearly.

## 8. @TransactionalEventListener, @Async, and Transaction Context

This lesson focuses on HTTP request context, but when using Spring application events there is another trap: **request context, transaction context, and listener invocation timing are not the same thing**.

| Listener | Typical thread and timing | Notes |
| --- | --- | --- |
| Default `@EventListener` | Synchronous, usually on the thread calling `publishEvent` | Can see request attributes if published on a servlet request thread |
| `@Async @EventListener` | Runs on an executor thread; may start right after the event is dispatched | Does not automatically receive request/transaction thread context; may run **before DB commit** |
| Custom `SimpleApplicationEventMulticaster` with executor | May use worker threads for listeners supporting async | Listeners that **do not support async execution** may still run synchronously per their own contract |
| `@TransactionalEventListener(AFTER_COMMIT)` | Registers a callback inside the transaction; runs when the transaction commits successfully | **Does not automatically create a new transaction**, nor transfer HTTP request context |
| `@TransactionalEventListener(AFTER_COMMIT)` with `@Async` | Callback is triggered after commit, while the method is handed to an executor via async proxy | Request/transaction thread context is not automatically transferred to the worker; must manage lifecycle and async errors |

With `TransactionalEventListener`, Spring may still have transaction synchronization resources bound before cleanup; if the listener needs to write to the DB **after commit**, it must establish a new transaction as needed (for example, `REQUIRES_NEW` in imperative code). Never use request context to "guess" transaction state.

When using WebFlux/R2DBC, transactions and many context types are stored in the **Reactor Context** attached to the subscriber, not in servlet `RequestContextHolder`. Reactor Context has its own propagation rules across a reactive chain; calling `subscribe()` independently or crossing another boundary still requires explicit design. Do not jump from Servlet thread-local loss to concluding that Reactor Context is always lost.

## 9. Practical Testing and Diagnosis

### Tests Must Distinguish the Source Thread from the Worker Thread

A good test suite does more than assert that a listener "was called"; it proves **whether thread context is present or absent** and **that the payload remains accurate**.

| Case | Expectation |
| --- | --- |
| Default `@EventListener` running on a servlet request thread | Can read `RequestContextHolder` while the request is active |
| `@Async @EventListener` running in a default thread pool | `getRequestAttributes()` normally returns `null` |
| `@Async` listener receiving a `correlationId` payload | Reads the exact value the publisher snapshotted into the event |
| `currentRequestAttributes()` in an unbound worker | May throw `IllegalStateException` |
| Submitting task A, then task B on the same worker thread | No leakage of request A's metadata into B |
| Executing the task after the HTTP request has ended | Does not dereference a raw request object; payload snapshot remains valid |
| Transaction T1 rolls back while `@Async @EventListener` already ran | Do not treat an async listener as after-commit; choose the right callback/outbox |
| Context-propagating executor | Only properly configured contexts are propagated, and they must be cleaned up properly |

### Debugging Questions to Follow in Order

1. **Which thread is the listener running on?** Log thread names at `publishEvent` and inside the listener.
2. **Which type of listener is being used?** `@EventListener`, `@Async`, a multicaster executor, or `@TransactionalEventListener`?
3. **Are `RequestAttributes` present on the source thread?** Use `RequestContextHolder.getRequestAttributes()` to check safely.
4. **Is the worker missing request context, or has the request already ended?** These are two distinct bugs, both making reliance on raw requests dangerous.
5. **What data does the listener actually need?** `orderId`, `tenantId`, `correlationId`? If it is just a few values, put them into an immutable payload.
6. **Is `InheritableThreadLocal` or a custom decorator enabled?** Evaluate cross-task leakage risk and clear/restore logic.
7. **Are subscriptions/tasks created outside managed lifecycles?** Independent `subscribe()`, raw `new Thread(...)`, or a misconfigured executor can bypass context propagation.
8. **Are async errors going unreported to the caller?** Observe error handlers, `Future`/`CompletableFuture`, queues, metrics, and tracing.
9. **Does the event need to fire only after DB commit?** If so, separate the transaction-timing problem from HTTP context.
10. **Have concurrent requests and thread pool reuse been tested?** That is where cross-user data leaks surface most easily.

## 10. Design Checklist to Avoid Depending on Request Context in Workers

- [ ] Read HTTP/request data only while the request is valid.
- [ ] Snapshot the exact metadata needed (e.g., `correlationId`) into the payload or envelope before leaving the boundary.
- [ ] Never pass raw `HttpServletRequest`, access tokens, or request-scoped beans into background tasks.
- [ ] Never call `currentRequestAttributes()` in an async handler without an explicit context-binding design.
- [ ] Never enable `inheritable=true` on pooled threads as a default workaround.
- [ ] If propagating logging/observation context, use explicit capture/restore/cleanup logic.
- [ ] Distinguish HTTP request context, security context, locale, MDC, transaction context, and Reactor Context.
- [ ] Test request completion, consecutive requests, worker reuse, async errors, and transaction rollback.
- [ ] For critical side effects, implement retry/idempotency policies or an outbox based on reliability requirements.

### Remember

~~~text
Spring ApplicationEventPublisher:
  Delivers the event object to listeners.

Default @EventListener:
  Same thread as publisher -> can see existing thread-bound context.

@Async @EventListener:
  Moves to a worker thread -> does not automatically receive the request's RequestContextHolder.

Preferred approach:
  Extract valid metadata while still inside the request.
  Place minimal values into an immutable event payload.
  Listeners rely only on the payload / independent system data.

Do not use:
  InheritableThreadLocal on a thread pool as a default "fix".
  Raw HttpServletRequest for work executing after the request.
~~~

## Official Documentation

- [Spring Framework — ApplicationContext Events and Asynchronous Listeners](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework — RequestContextHolder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/context/request/RequestContextHolder.html)
- [Spring Framework — RequestContextFilter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/filter/RequestContextFilter.html)
- [Spring Framework — ThreadPoolTaskExecutor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework — ContextPropagatingTaskDecorator](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
