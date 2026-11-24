# Pitfalls of Keeping a Request Object in an Application Event: Threads, Lifecycles, and Building Safe Payloads

## 1. The Problem: `HttpServletRequest` Is Not Durable Event Data

In a Spring MVC application, `jakarta.servlet.http.HttpServletRequest` represents **a specific HTTP request currently being processed by the Servlet container**. It lets controllers/filters read the method, path, headers, parameters, attributes, principal, and body stream within the scope of that request.

A common design mistake is putting **the entire `HttpServletRequest` object** into a Spring Application Event:

```java
public record OrderReceivedEvent(HttpServletRequest request) {}

@PostMapping("/orders")
public ResponseEntity<Void> submit(HttpServletRequest request) {
    publisher.publishEvent(new OrderReceivedEvent(request));
    return ResponseEntity.accepted().build();
}
```

This is **illustrative code**; it requires a Spring MVC controller, `ApplicationEventPublisher`, Servlet API imports, and the corresponding application configuration.

When the listener executes immediately and synchronously on the request thread, the code may appear to work. However, if later the listener uses `@Async`, the multicaster gets an executor, the listener runs after commit, or the event is queued, the worker may access the request **after the thread/controller has finished processing**. At that point the data may be invalid, mutated, unsafe to access, or container-implementation-dependent.

**Principle:** Events must contain **required business information already copied into immutable data** while the request is still valid, instead of holding onto a request, response, session, input stream, or objects tied to thread/request scope.

Preferred example:

```java
public record OrderReceivedEvent(
        String orderId,
        String requestId,
        String tenantId,
        String actorId) {}
```

This is an illustrative record; the IDs are values already **verified/normalized** by the application. Never take a raw client-supplied `X-Tenant-Id` header as an authorized identity without an authorization step.

## 2. Three Different Lifecycles That Are Easily Confused

In Spring, the lifecycles of an event, a thread, and a request **are not identical**.

| Object / context | Who manages it? | Note |
| --- | --- | --- |
| `HttpServletRequest` | Servlet container and request processing | Meaningful within the request lifecycle; not a long-lived storage object |
| `RequestContextHolder` | Spring Web, usually bound to the request-processing thread | Does not automatically transfer to worker threads used by `@Async` |
| `ApplicationEvent` | Spring event publisher/multicaster and consumers | May be processed immediately, asynchronously, by transaction phase, or retained by the app |
| `SecurityContextHolder` | Spring Security per its context strategy | Defaults to thread-local; requires an explicit propagation policy |
| MDC/tracing/observation context | Logging/observability integration | Not part of the default event payload |
| JDBC/JPA transaction | `PlatformTransactionManager` | Imperative transactions are typically thread-bound; `@Async` does not inherit them |

Dangerous flow:

```text
HTTP request thread
  |
  +-- Controller receives HttpServletRequest R1
  +-- publishEvent(new MyEvent(R1))
  |     |
  |     +-- @Async listener -> submits task
  |
  +-- Controller returns HTTP response
  +-- Servlet filter/DispatcherServlet ends request
  +-- RequestContextHolder is cleaned up
  +-- Container may reclaim/recycle request resources
                         |
                         v
                 Executor worker thread
                         |
                         +-- reads event.request()
                         +-- request data may no longer be valid
                         +-- RequestContextHolder may be null
```

Spring Framework dispatches `@EventListener` **synchronously on the publisher thread** by default when using the default multicaster. However, `@Async` or an executor configured on `applicationEventMulticaster` causes the listener to run on another thread. **Even if Spring does not enable async today, payloads should still be designed not to depend on a request object**; a single architectural change later can turn working code into a race condition.

## 3. Six Risk Categories of Keeping a Request in an Event

### 3.1. The Request Lifecycle Ends Before the Listener Reads It

Several Servlet objects have lifecycles tied to the request. Once the request finishes, the container may release or internally reuse them. The Servlet API establishes no contract allowing you to hold an `HttpServletRequest` reference indefinitely and reuse it in a background worker after the request ends.

Consequences vary by container, filter, wrapper, and timing:

- `IllegalStateException` or undefined behavior when accessing lifecycle-dependent properties;
- `getInputStream()`/`getReader()` are no longer usable as expected;
- attribute data is mutated by another stage in the pipeline;
- wrappers reference already-closed resources;
- the worker reads state that no longer represents the original request.

Do not claim "Tomcat always recycles and returns request B when reading A's reference"—that is not a universal Servlet API rule. **The issue is that there is no safety contract for lifetime or thread-safety once the request ends.**

### 3.2. Request Objects and Attributes Can Be Mutable

`HttpServletRequest` exposes `setAttribute(...)` and `removeAttribute(...)` via `ServletRequest`. Filters, interceptors, or controllers may mutate attributes during processing. Passing a reference into an event **does not snapshot values**:

```java
request.setAttribute("tenantId", "alpha");
publisher.publishEvent(new UnsafeEvent(request));
request.setAttribute("tenantId", "beta");
```

An async listener reading `event.request().getAttribute("tenantId")` later might see `"beta"`, not `"alpha"` from when the event was published. With multiple threads reading and writing concurrently, data inconsistency also arises. Wrapping the request in a Java `record` only stores the reference in a `final` field; **it does not make the request immutable**.

### 3.3. `RequestContextHolder` Is Thread-Bound

Broken code example:

```java
@Async
@EventListener
public void onOrderReceived(OrderReceivedEvent event) {
    ServletRequestAttributes attrs =
            (ServletRequestAttributes)
                    RequestContextHolder.currentRequestAttributes();
    HttpServletRequest request = attrs.getRequest();
    // May throw IllegalStateException: no request context
    // is bound to the worker thread.
}
```

This is **illustrative code**, not a standalone program. `RequestContextHolder.currentRequestAttributes()` throws `IllegalStateException` if no matching context exists. Conversely, `getRequestAttributes()` may return `null`.

Request context in `DispatcherServlet` is bound for request handling; executor workers **do not automatically share that `ThreadLocal`**. Passing a request reference into the event does not mean the `ThreadLocal` request context has been bound to that thread.

### 3.4. Body Streams, Multipart Files, and Sessions

Specifically avoid storing in an event:

- `ServletInputStream`/`BufferedReader` from the request body: the stream may already be read, single-use, or closed.
- `MultipartFile`/`Part` tied to temporary uploads: temporary files may be cleaned up after the request.
- `HttpSession`: concurrent access is not automatically thread-safe; the session may expire or be invalidated.
- `HttpServletResponse`: the response is usually already committed; headers/status/body cannot be modified from a background listener as in a controller.
- `ServletRequestAttributes` or Spring `WebRequest`: merely wrappers around request scope/context, not immutable snapshots.

If a worker must process an uploaded file after the HTTP response, **actively move the file to durable storage while the request is still active**, then put `objectKey`, checksum, size, and verified metadata into the event. Do not merely hold a `MultipartFile` and try to read it on an async thread.

### 3.5. Memory Retention and Information Leakage Risks

An `HttpServletRequest` reference can indirectly retain attributes, security/session data, wrappers, body buffers, and a large object graph. If the event sits in an executor queue, cache, or retry list for a long time, the garbage collector cannot reclaim those reachable objects.

If the system accidentally serializes or logs the entire request, it can also expose `Authorization` tokens, cookies, IPs, query strings, personal data, or secrets stored in attributes. Events should apply **data minimization**: include only fields with a clear business purpose.

### 3.6. `@TransactionalEventListener(AFTER_COMMIT)` Does Not Save a Request Reference Either

`AFTER_COMMIT` only ties the listener to the **DB transaction outcome**; it does not extend the lifetime of `HttpServletRequest`. If the callback runs on the request thread right after commit, the request is sometimes still accessible, but relying on that timing detail is fragile coupling. When the callback moves to `@Async` or runs after the response, the request may already be invalid.

If writing to the database after commit is needed, a new appropriate transaction (`Propagation.REQUIRES_NEW`) must be handled separately from the request context problem; these are **two independent concerns**.

## 4. The Right Design: Immutable Snapshot Payloads

Instead of an event containing `HttpServletRequest`, extract **the exact values needed** before publishing.

Payload example:

```java
public record RequestSnapshot(
        String requestId,
        String tenantId,
        String actorId,
        String httpMethod,
        String route) {}

public record OrderProcessingRequested(
        String orderId,
        RequestSnapshot context) {}
```

These are illustrative definitions. `String` values are immutable; Java records ensure components cannot be reassigned after creation. If adding `List`/`Map` or nested DTOs, defensively copy (`List.copyOf`, `Map.copyOf`) and ensure **elements inside are also immutable**.

A boundary helper to capture from the request:

```java
private static RequestSnapshot capture(
        HttpServletRequest request,
        String verifiedActorId,
        String verifiedTenantId) {

    String requestId =
            (String) request.getAttribute("correlationId");

    return new RequestSnapshot(
            requestId,
            verifiedTenantId,
            verifiedActorId,
            request.getMethod(),
            request.getRequestURI());
}
```

This is an illustrative snippet; `verifiedActorId` and `verifiedTenantId` must be supplied by the authentication/authorization layer. `getRequestURI()` may contain user data in the path, so consider using a **normalized route pattern** like `/orders/{orderId}` for telemetry and general payloads. If the route is not needed, **omit that field**.

**Lock in snapshot timing:** capture **on the request thread while data is still valid and authenticated**, and only then call `publisher.publishEvent(...)`. Never give an async worker a `Supplier<HttpServletRequest>` or an entity/request reference to capture lazily.

A useful payload typically only needs `orderId`, `eventId`, `requestId`, `actorId`, and verified `tenantId`. If the listener needs business content, pass a sufficient business snapshot DTO or ID/version to query the DB in a separate transaction.

## 5. Runnable Java 17+ Example: Mock Request Mutated While Listener Waits

This example uses **Spring Framework 6.2.12**, `spring-web`, `spring-test`, Jakarta Servlet API, Gradle, and Java 17+. No Spring Boot or web server is needed.

Demo goals:

1. Create a `MockHttpServletRequest` with initial tenant `"tenant-original"`.
2. Publish an **unsafe event** holding `HttpServletRequest` and a **safe event** holding a snapshot record.
3. Two `@Async @EventListener` methods use a `CountDownLatch` to **pause before reading the payload**, eliminating timing randomness.
4. The publisher changes the request attribute to `"tenant-modified"`, marks request attributes completed, unbinds `RequestContextHolder`, and then releases the workers.
5. The worker holding the reference reads the **new tenant**, while the worker holding the snapshot reads the **old tenant**. Workers have no request context under default `ThreadLocal` configuration.

**Note:** `MockHttpServletRequest` from `spring-test` lets us simulate post-publish mutation deterministically; it **does not fully simulate the recycling/cleanup behavior of Tomcat, Jetty, or Undertow**. The demo proves shared mutable references and thread-bound context; with real requests, consequences also depend on the Servlet container.

### 5.1. Project Structure

```text
request-payload-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/RequestPayloadDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'request-payload-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.12'
    implementation 'org.springframework:spring-web:6.2.12'
    implementation 'org.springframework:spring-test:6.2.12'
    implementation 'jakarta.servlet:jakarta.servlet-api:6.0.0'
}

application {
    mainClass = 'demo.RequestPayloadDemo'
}
```

`spring-test` is placed in `implementation` **only because this demo is a console application using `MockHttpServletRequest` at runtime**. In a production web application, Spring Test is not needed on the main classpath; it normally belongs in `testImplementation`.

### 5.2. `src/main/java/demo/RequestPayloadDemo.java`

```java
package demo;

import java.util.Objects;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

public class RequestPayloadDemo {

    // Anti-pattern: holds a reference to a mutable request.
    public record UnsafeEvent(HttpServletRequest request) {}

    // Correct: snapshots required values into an immutable object.
    public record RequestSnapshot(
            String requestId,
            String tenantId,
            String method,
            String path) {

        public static RequestSnapshot from(HttpServletRequest request) {
            return new RequestSnapshot(
                    Objects.toString(
                            request.getAttribute("requestId"), ""),
                    Objects.toString(
                            request.getAttribute("tenantId"), ""),
                    request.getMethod(),
                    request.getRequestURI());
        }
    }

    public record SafeEvent(RequestSnapshot snapshot) {}

    // Standalone bean to share test state with the async proxy.
    public static class Probe {
        final CountDownLatch entered = new CountDownLatch(2);
        final CountDownLatch release = new CountDownLatch(1);
        final CountDownLatch finished = new CountDownLatch(2);

        final AtomicReference<String> unsafeTenant =
                new AtomicReference<>();
        final AtomicReference<String> safeTenant =
                new AtomicReference<>();
        final AtomicReference<Boolean> workerHasRequestContext =
                new AtomicReference<>();
        final AtomicReference<Exception> error =
                new AtomicReference<>();

        void waitUntilReleased() throws InterruptedException {
            entered.countDown();
            if (!release.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("worker wait timed out");
            }
        }
    }

    public static class RequestEventListeners {
        private final Probe probe;

        public RequestEventListeners(Probe probe) {
            this.probe = probe;
        }

        @Async("eventExecutor")
        @EventListener
        public void onUnsafe(UnsafeEvent event) {
            try {
                probe.waitUntilReleased();

                // Same request reference that was mutated by the publisher.
                probe.unsafeTenant.set(Objects.toString(
                        event.request().getAttribute("tenantId"), ""));

                probe.workerHasRequestContext.set(
                        RequestContextHolder.getRequestAttributes() != null);
            } catch (Exception ex) {
                probe.error.compareAndSet(null, ex);
                if (ex instanceof InterruptedException) {
                    Thread.currentThread().interrupt();
                }
            } finally {
                probe.finished.countDown();
            }
        }

        @Async("eventExecutor")
        @EventListener
        public void onSafe(SafeEvent event) {
            try {
                probe.waitUntilReleased();

                // Snapshot holds only immutable Strings.
                probe.safeTenant.set(event.snapshot().tenantId());
            } catch (Exception ex) {
                probe.error.compareAndSet(null, ex);
                if (ex instanceof InterruptedException) {
                    Thread.currentThread().interrupt();
                }
            } finally {
                probe.finished.countDown();
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class AppConfig {

        @Bean("eventExecutor")
        ThreadPoolTaskExecutor eventExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(2);
            executor.setMaxPoolSize(2);
            executor.setQueueCapacity(10);
            executor.setThreadNamePrefix("event-");
            executor.setWaitForTasksToCompleteOnShutdown(true);
            executor.setAwaitTerminationSeconds(5);
            return executor;
        }

        @Bean
        Probe probe() {
            return new Probe();
        }

        @Bean
        RequestEventListeners requestEventListeners(Probe probe) {
            return new RequestEventListeners(probe);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {

            Probe probe = context.getBean(Probe.class);

            // Mock request: not a real Servlet container.
            MockHttpServletRequest request =
                    new MockHttpServletRequest("POST", "/orders");
            request.setAttribute("requestId", "REQ-42");
            request.setAttribute("tenantId", "tenant-original");

            ServletRequestAttributes attributes =
                    new ServletRequestAttributes(request);

            RequestContextHolder.setRequestAttributes(attributes);
            try {
                // Capture snapshot BEFORE publishing.
                RequestSnapshot snapshot =
                        RequestSnapshot.from(request);

                context.publishEvent(new UnsafeEvent(request));
                context.publishEvent(new SafeEvent(snapshot));

                if (!probe.entered.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "both async listeners did not enter");
                }

                // After both workers are waiting, mutate the request.
                request.setAttribute("tenantId", "tenant-modified");

                // Simulate request attributes completion.
                attributes.requestCompleted();
            } finally {
                RequestContextHolder.resetRequestAttributes();
                probe.release.countDown();
            }

            if (!probe.finished.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "async listeners did not finish");
            }
            if (probe.error.get() != null) {
                throw new IllegalStateException(
                        "async listener failure", probe.error.get());
            }

            System.out.println(
                    "unsafe event tenant=" + probe.unsafeTenant.get());
            System.out.println(
                    "snapshot event tenant=" + probe.safeTenant.get());
            System.out.println(
                    "worker has request context="
                            + probe.workerHasRequestContext.get());
            System.out.println(
                    "publisher context after cleanup="
                            + (RequestContextHolder
                                    .getRequestAttributes() != null));
        }
    }
}
```

### 5.3. Running and Output

With JDK 17+ and Gradle installed:

```bash
gradle -q run
```

`System.out.println` lines from the program:

```text
unsafe event tenant=tenant-modified
snapshot event tenant=tenant-original
worker has request context=false
publisher context after cleanup=false
```

Gradle may print its own build logs; the four lines above are the verification output produced by the program. `CountDownLatch` ensures the result does not depend on which worker the scheduler runs first. Each `@Async` listener waits on a shared latch, while the publisher mutates the request only after both have begun waiting.

**Why do the results differ?**

1. `UnsafeEvent(request)` holds a reference to the same mutable `MockHttpServletRequest` the publisher is using.
2. `SafeEvent(snapshot)` holds `String` values read **before publishing**; `RequestSnapshot` does not hold the request object.
3. After both listeners enter the waiting state, the publisher changes the attribute from `"tenant-original"` to `"tenant-modified"`.
4. Once the latch is released, `onUnsafe` reads the reference and gets the new value; `onSafe` reads the snapshot and still gets the old value.
5. `RequestContextHolder.setRequestAttributes(...)` binds only to **the publisher thread** by default; worker threads from `ThreadPoolTaskExecutor` do not automatically carry the binding. Hence `worker has request context=false`.
6. In the `finally` block, the publisher calls `RequestContextHolder.resetRequestAttributes()`, preventing request context from leaking into other work on that same thread.
7. The program awaits `finished` and checks `error` before printing; it uses `AtomicReference` and latches to pass results safely across threads.

**Intentional limitation:** `MockHttpServletRequest` still allows reading attributes after `attributes.requestCompleted()` in this simulation. **Do not conclude** that a real request is safe to use after completion. The program proves that a reference is not a snapshot; the bad example is included strictly for learning, not as a production pattern.

## 6. Practical Application in a Spring MVC Controller

Instead of:

```java
@PostMapping("/orders")
public ResponseEntity<Void> submit(
        HttpServletRequest request,
        @RequestBody CreateOrderRequest body) {

    publisher.publishEvent(new OrderCreatedEvent(request, body));
    return ResponseEntity.accepted().build();
}
```

This is code **to avoid**: the event retains the request and may also retain a mutable `body`. `CreateOrderRequest` is an application-defined DTO.

A better approach separates verified data from the Servlet object:

```java
public record OrderCreatedEvent(
        String orderId,
        String requestId,
        String tenantId,
        String actorId) {}

@PostMapping("/orders")
public ResponseEntity<Void> submit(
        HttpServletRequest request,
        @Valid @RequestBody CreateOrderRequest body,
        Authentication authentication) {

    // Illustrative example: application must validate/authz body,
    // tenantId, and principal per real security mechanisms.
    String tenantId = tenantAccess.verifiedTenantId(authentication);
    String actorId = authentication.getName();
    String requestId = correlationIdResolver.resolve(request);

    String orderId = orderService.create(
            body, tenantId, actorId);

    publisher.publishEvent(new OrderCreatedEvent(
            orderId, requestId, tenantId, actorId));

    return ResponseEntity.accepted().build();
}
```

This is an **illustrative snippet, not a standalone program**. Dependencies `tenantAccess`, `correlationIdResolver`, `orderService`, and `CreateOrderRequest` are application-defined; Spring MVC, Jakarta Validation/Spring Security are required as appropriate. `@Valid` is only DTO validation and **does not replace tenant authorization checks**. `authentication.getName()` is one identifier example; production should use a stable domain subject ID if available.

One case to watch out for: if `orderService.create(...)` runs its own transaction, by the time it returns the transaction may already have committed; publishing the event in the controller may then **no longer be inside a transaction**. If you want `@TransactionalEventListener(AFTER_COMMIT)` listeners to receive the event, **publish inside the service transaction**:

```java
@Service
public class OrderService {
    @Transactional
    public String create(CreateOrderCommand command) {
        String id = repository.insert(command);
        publisher.publishEvent(new OrderCreatedEvent(
                id, command.requestId(),
                command.tenantId(), command.actorId()));
        return id;
    }
}
```

This is **illustrative code**; `CreateOrderCommand`, `repository`, and `publisher` are application-defined. Here `command` is an immutable/validated DTO passed from the controller to the service; **it does not contain `HttpServletRequest`**. Because the event is published inside the transaction, `AFTER_COMMIT` listeners can register callbacks for the right phase.

## 7. `RequestContextHolder`, `@RequestScope`, and Thread Pools

`RequestContextHolder` holds thread-bound `RequestAttributes`; `DispatcherServlet` normally exposes request context while handling a request. `getRequestAttributes()` can return `null` if the thread is unbound:

```java
RequestAttributes attrs =
        RequestContextHolder.getRequestAttributes();

if (attrs == null) {
    // Current thread has no valid request context.
}
```

The snippet above is illustrative; import `RequestAttributes` and `RequestContextHolder` from package `org.springframework.web.context.request`.

### Pitfalls with Request-Scoped Beans

```java
@RequestScope
@Component
public class RequestIdentity {
    private String correlationId;
    // ...
}
```

If an async listener tries to access a request-scoped proxy from a worker **that has no request context**, it may hit `ScopeNotActiveException`, `IllegalStateException`, or related errors depending on how it is accessed. If the listener needs a correlation ID, capture the `String` before publishing; do not pass a request-scoped proxy into the event.

### Do Not Fix This by Enabling Inheritable Request Context for All Threads

`RequestContextHolder.setRequestAttributes(attributes, true)` can pass request context to **newly created child threads** via `InheritableThreadLocal` in certain cases. However, an executor with a thread pool **reuses threads**: inheritable `ThreadLocal` cannot serve as a proper per-task context propagation mechanism. Threads may already exist beforehand or retain data that is no longer valid.

Spring documentation warns against using inheritable request context with thread pools capable of adding threads on demand. Do not enable `RequestContextFilter.setThreadContextInheritable(true)` as a trick to let async listeners access the servlet request. Risks include **the wrong user's request context**, stale data, or holding resources longer than intended.

If a program binds a `ThreadLocal` manually to run a controlled task, **always restore or remove it in `finally`**. Still, being able to bind a technical request context **does not make a Servlet object safe after the request finishes**.

## 8. `@Async` and Context Propagation Mechanisms: Use for the Right Purpose

Spring Framework supports `TaskDecorator`, and with the Micrometer Context Propagation library also provides `ContextPropagatingTaskDecorator` to carry certain observation/tracing/logging contexts across executors:

```java
@Bean("observedExecutor")
public ThreadPoolTaskExecutor observedExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(100);
    executor.setTaskDecorator(
            new ContextPropagatingTaskDecorator());
    executor.setThreadNamePrefix("observed-");
    return executor;
}
```

This is **illustrative code**, not part of the console example; it requires Spring 6.2, Micrometer Context Propagation on the classpath, and imports for `ThreadPoolTaskExecutor`, `ContextPropagatingTaskDecorator`, and `Bean`. The decorator supports restoring **contexts that have appropriate accessors/configuration**. Not every arbitrary `ThreadLocal` will be transferred automatically, and context propagation does not extend the life of a Servlet request.

Separate two distinct needs clearly:

1. **Observability:** trace ID, span context, MDC for logging/correlation. You can use framework propagation with proper setup/cleanup so worker logs stay linked to the request.
2. **Business payload:** business values the listener needs to process accurately (`orderId`, `actorId`, verified `tenantId`, `eventId`). Put them in an **immutable event DTO** or persisted work item rather than relying on a logging context that may be cleared.

If using Spring Security, mechanisms like `DelegatingSecurityContextAsyncTaskExecutor` exist to propagate `SecurityContext` for specific tasks; however, **do not** treat that as a reason to keep a raw `Authentication`, session, or request object in a long-lived event. Background task execution privileges need their own trust boundary, especially when a job retries after user permissions have changed.

### Context Scope by Thread

| Context | Default synchronous `@EventListener` | Default `@Async @EventListener` |
| --- | --- | --- |
| Immutable event payload | Yes | Yes |
| `RequestContextHolder` | May be present if running on request thread | **Not automatically propagated** |
| `SecurityContextHolder` | May be present if filter bound it | Not guaranteed to be present |
| MDC/trace | Usually sees current thread's value | Not guaranteed without configured propagation |
| Imperative JDBC transaction | Can participate in publisher's transaction | Not automatically passed to worker |
| Servlet request reference | Accessible during request lifetime | **Should not be used**, even if reference is passed |

An event containing an immutable snapshot is the most reliable way to cross thread, lifecycle, and retry boundaries.

## 9. Multipart, File Uploads, and Request Bodies Must Be Handled Before Publishing

Broken example:

```java
public record FileUploadedEvent(MultipartFile file) {}

@PostMapping("/files")
public void upload(@RequestParam MultipartFile file) {
    publisher.publishEvent(new FileUploadedEvent(file));
}
```

This is **bad illustrative code**, not an implementation recommendation. `MultipartFile` may be backed by a temporary file managed by the multipart resolver; after the request, the container may clean up resources. An async listener reading `file.getInputStream()` later may fail or find the data gone.

More reliable approach:

```text
Active HTTP request
   |
   +-- validate format/size
   +-- stream upload to controlled persistent storage
   +-- verify checksum and determine objectKey
   +-- publish FileReady(objectKey, checksum, size, requestId)
        |
        +-- async listener reads from storage by objectKey
```

Do not stuff entire file bytes into an Application Event if the size is large; that inflates memory, queue, and logging overhead. If the file needs deletion when a transaction rolls back, design a compensating cleanup strategy; external storage uploads do not automatically roll back with a JDBC transaction.

For JSON bodies, controllers can use `@RequestBody` to read and validate into a DTO. **Map the required information into an event DTO/value object** before publishing, instead of keeping `HttpServletRequest` or re-reading the body stream from a worker.

## 10. Security Boundary: Never Use Raw Headers as Authority

A dangerous mistake not limited to async:

```java
String tenantId = request.getHeader("X-Tenant-Id");
publisher.publishEvent(new WorkRequested(tenantId, orderId));
```

This is **risky illustrative code**. If a header is arbitrarily sent by a client and the consumer treats it as an authorized tenant, the application can introduce a cross-tenant vulnerability. A snapshot only preserves **the value**; it does not prove that value is trustworthy.

Safe practices:

- Authenticate the principal and verify tenant/resource permissions at ingress.
- Include only **verified tenant ID** and **stable actor ID** in the event when genuinely needed.
- Avoid putting raw `Authorization` headers, cookies, session IDs, bearer tokens, refresh tokens, CSRF tokens, or raw `Authentication` objects containing credentials into events.
- Treat external `X-Request-Id` or correlation IDs as **input requiring length/format validation**. Generate a system request ID if the input is untrusted.
- Never log entire events if payloads contain personal data; Java records auto-generate `toString()` over all components.
- When a worker runs late or retries, re-check permissions requiring **current authorization** if business policy demands it; permissions at initial request time do not necessarily remain valid.

If the listener only needs an actor ID to audit an already-authorized action, snapshotting a verified actor ID is appropriate. If the worker performs **a new sensitive action**, explicitly design which authority it runs under and whether re-authorization or a service identity is required.

## 11. Can a Synchronous Listener Hold the Request?

A synchronous listener executing immediately on the request thread can read the request **while the request is still active**, for instance a listener logging request metadata. Even then, limitations remain:

- The payload becomes tightly coupled to the web layer, making reuse from batch/scheduler/message brokers difficult.
- Unit tests have to create/mock a Servlet request instead of simply passing business values.
- If later switched to async or transaction-bound processing, the code can break.
- A listener might stash the event/request in a collection, cache, `CompletableFuture`, or retry task without callers realizing it.
- Mutating request attributes after publishing causes late reference readers to observe the new values.
- Accessing sessions/streams has its own lifecycle/thread rules that are not automatically made safe just because the listener is synchronous.

**Being allowed to access the request directly during an HTTP request does not mean you should embed it in an application-level event.** Separating web adapters from business events makes code resilient to asynchronous execution.

If an event serves only a *purely web* operation that must run synchronously inside the request, consider using an interceptor/filter instead of pushing a request object into a domain event.

## 12. Should You Put All Request Data into a Snapshot DTO?

No. A true snapshot is **an intentional capture**, not a dump of the entire Servlet request.

| Payload type | Suitable when | Risks to control |
| --- | --- | --- |
| `orderId`, `eventId` | Consumer only needs to look up or mark a business milestone | DB may change after the event; need a version if historical state matters |
| `orderId`, `requestId`, `actorId`, `tenantId` | Audit/correlation needs verified IDs | Protect PII/tenant boundaries; never log credentials |
| Immutable business snapshot | Consumer needs exact information at event creation time | Deep immutability, schema/versioning, size |
| `HttpServletRequest` | **Should not be used as an event payload across async/lifecycle boundaries** | Lifetime, `ThreadLocal`, mutable state, memory retention |
| `HttpSession`/`MultipartFile`/`InputStream` | **Should not be retained in long-lived events** | Thread safety, cleanup, one-shot streams, sensitive data |

Durable events often carry metadata:

```java
public record WorkRequested(
        String eventId,
        String requestId,
        String aggregateId,
        long aggregateVersion,
        String verifiedActorId,
        String verifiedTenantId) {}
```

This is an illustrative snippet; validate the IDs and pay attention to capture timing. If consumers may process duplicates, `eventId` supports idempotency. If historical state matters, `aggregateVersion` or a business snapshot lets consumers detect stale events when re-reading the DB.

### Avoid Shallow Copies

For a payload containing `List<MutableLine>`, `List.copyOf(...)` only prevents modification through the list itself—**it does not make the `MutableLine` elements immutable**. Map each element to an immutable DTO, such as a Java record holding `String`, `int`, `BigDecimal`, and immutable nested DTOs; then wrap the collection with `List.copyOf(...)`.

Do not put a JPA entity/lazy-loading proxy into an async event expecting the request/transaction persistence context to remain alive. Snapshot DTOs inside a transaction holding valid data, or pass an ID/version so the consumer opens its own transaction and queries appropriately.

## 13. `@TransactionalEventListener` and `@Async` Can Combine, but Do Not Extend Request Lifetime

Example:

```java
@Async("eventExecutor")
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onOrderCommitted(OrderCreatedEvent event) {
    // Process immutable event DTO on worker thread.
    notificationService.schedule(event.orderId());
}
```

This is illustrative code with application-defined event and service types. It requires:

1. `OrderCreatedEvent` published **inside the transaction** you want to observe.
2. `@EnableAsync` and the `eventExecutor` executor.
3. The listener as a Spring-managed bean whose method is intercepted by the async proxy.
4. An event containing an **appropriate snapshot/ID**, not holding the request.
5. The worker opening its own DB transaction via a Spring service if DB operations are needed.

`AFTER_COMMIT` addresses **timing relative to the source transaction**, `@Async` addresses **the executing thread**, and an immutable DTO addresses **payload stability**. None of these three mechanisms performs the job of the other two.

`@TransactionalEventListener` ignores events published **outside a transaction** by default (`fallbackExecution=false`). If a controller publishes an event **after** a `@Transactional` service has already finished, the listener may not run; publish inside the service transaction or adjust the design accordingly.

When losing tasks across crashes is unacceptable, a transactional outbox/persistent work queue is required. In-memory Spring Application Events do not provide durable storage or replay on their own.

## 14. Testing to Catch Request Reference Bugs

A good test suite should explicitly prove that listeners **do not depend on a completed Servlet request**:

1. **Snapshot before publish:** the request has tenant `"original"`, a snapshot is taken, then after publish the mutable request changes to `"changed"`; the safe event still holds `"original"`.
2. **Async scheduling:** use latches to hold workers before reading; avoid arbitrary `Thread.sleep`.
3. **Request context on worker:** `RequestContextHolder.getRequestAttributes()` is normally `null` without configured propagation; do not treat that as a Spring bug.
4. **Cleanup:** unbind request context at the boundary and verify reused threads do not carry old requests.
5. **Request scope:** never access request-scoped beans from a worker without valid context.
6. **Multipart:** move uploads to persistent storage before request completion, then test the listener using only `objectKey`.
7. **Security:** untrusted raw tenant headers must be rejected or verified before creating events.
8. **Transactions:** events meant for `AFTER_COMMIT` must be published inside a transaction; test rollback to verify the listener does not run.
9. **Retries:** duplicate/delayed event IDs/versions must not cause duplicate side effects.
10. **Leaks:** never retain requests/sessions/responses in queues for long; inspect payloads and event logs for sensitive data.

### When Tests Use Web Mocks

Tests using `MockMvc` help verify controller behavior with mock Servlet requests, but **do not prove** how a real request is recycled by a container. To test memory/lifecycle under load, include integration tests with a real web server, slow consumers, and concurrency limits; inspect tracing, thread dumps, and heap profiles when needed.

For `@Async` listeners, tests need latches, futures, or Awaitility with timeouts. Check event output after the worker signals completion rather than inferring completion from the HTTP response returning.

## 15. Diagnosing Common Failures

| Symptom | Likely cause to check | Fix |
| --- | --- | --- |
| `No thread-bound request found` from worker | `RequestContextHolder` has no binding on executor thread | Do not read request context in async consumers; put data in immutable events |
| Request attribute differs from publish time | Event only held a shared `HttpServletRequest` reference | Capture a DTO snapshot before publishing |
| Exception reading request/body after response | Container already cleaned up or stream was consumed/closed | Read/validate/copy data during the request; worker receives only ID/DTO |
| `MultipartFile` can no longer be read | Temp file was cleaned up after the request | Move to durable storage before publishing |
| Error using `@RequestScope` bean on worker | Request scope does not operate outside a request-bound thread | Do not pass request-scoped beans across async boundaries |
| Thread pool occasionally uses another user's context | Inheritable `ThreadLocal`/binding not cleaned up or pool reuse | Never inherit raw request context; restore/remove properly in `finally` |
| MDC/trace ID disappears | Logging context does not auto-propagate | Use `TaskDecorator`/Context Propagation for observability, or an event correlation ID |
| Tenant spoofing | Snapshotted raw `X-Tenant-Id` without verification | Use authenticated and authorized tenant IDs |
| `AFTER_COMMIT` listener does not run | Published outside a transaction or T1 rolled back | Publish inside the right transaction; test both commit and rollback |
| Same job sends email twice | Retries/duplicate events are not idempotent | Event ID, unique key, outbox/durable retries |
| Heap grows when event queue fills up | Events retain a large request object graph | Minimal payloads, bounded queues, never cache Servlet requests |
| Async listener runs on caller thread | Missing `@EnableAsync` or self-invocation | Use Spring bean proxies/executors properly |

## 16. Design Checklist Before Taking Events to Production

Before publishing from an HTTP request, ask yourself:

- Does the event hold **a Servlet object** or only **immutable values**?
- Could any listener run **after the response** or **on another thread**?
- Which fields are required for business logic vs. tracing only? Can the payload be slimmed down?
- Have actor/tenant/resource gone through **authentication + authorization**?
- Have sensitive fields such as tokens, cookies, bodies, sessions, or PII been kept out of the event?
- If a listener needs an uploaded file, is the file already in **persistent storage**?
- If a listener needs committed DB state, is the event published inside the right transaction and handled at `AFTER_COMMIT`?
- Does the worker need its own transaction, timeouts, retry/idempotency, or an outbox?
- If trace/MDC must propagate, does the executor have **appropriate context propagation and cleanup**?
- Do tests prove the snapshot remains unchanged when the request object is mutated or completed?

**Conclusion:** `HttpServletRequest` is the context of a single HTTP processing pass, not a reliable payload for an Application Event outliving the request or crossing to an executor. **Snapshot an immutable DTO before publishing, pass verified IDs/metadata, and let workers open the resources and transactions they need.** Context propagation can assist observability in supported scenarios, but it never makes a request object safe to retain indefinitely.

## Official Documentation

- [Spring Framework 6.2 — ApplicationContext Events and Asynchronous Listeners](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework 6.2 — `RequestContextHolder` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/context/request/RequestContextHolder.html)
- [Spring Framework 6.2 — `ServletRequestAttributes` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/context/request/ServletRequestAttributes.html)
- [Spring Framework 6.2 — Spring MVC Controller Method Arguments](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/arguments.html)
- [Spring Framework 6.2 — Application Events Observability & Context Propagation](https://docs.spring.io/spring-framework/reference/6.2/integration/observability.html)
- [Spring Framework 6.2 — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html)
- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Jakarta Servlet 6.0 — `ServletRequest` Interface](https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/servletrequest)
