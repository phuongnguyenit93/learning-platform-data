# Mistakes with `block()`, Manual `subscribe()`, and Work Outside the Reactive Chain

## 1. Learning Objectives and Scope

In Spring WebFlux, APIs returning `Mono<T>` or `Flux<T>` let you compose asynchronous work into a Reactor chain. However, code can use the right `Mono`/`Flux` types and still break the reactive model if the author blocks threads, manually triggers subscriptions, or moves work outside the pipeline. These mistakes are especially dangerous in applications using **Spring Security Reactive**, because user identity and permissions are bound to the subscription's **Reactor Context**.

After this lesson, you will:
- Know when `block()` is wrong inside a WebFlux request flow and when synchronous waiting should appear only at the outermost boundary.
- Understand why WebFlux controllers/services should usually **return a Publisher** so the framework owns the subscription, instead of calling `subscribe()` manually.
- Recognize "created a `Mono` nobody subscribed to", "fire-and-forget" bugs, and work executed via `Thread`, `CompletableFuture`, or `@Async` detached from the request.
- Preserve propagation of data, errors, cancellation, and `ReactiveSecurityContextHolder` when using `flatMap`, `then`, `contextWrite`, and schedulers.
- Know how to isolate unavoidable blocking APIs and design work that genuinely must continue after the HTTP response ends.

**Scope:** this is a Reactor foundations lesson in the Spring Security Reactive module. Examples use Java 17+, Reactor Core, and illustrative WebFlux/Spring Security snippets. The focus is on pipeline, subscription, and context mechanics—not building a full login system.

## 2. Model to Grasp First: A Publisher Is a Work Description

When you write:

~~~java
Mono<String> work = Mono.fromSupplier(() -> readValue());
~~~

you are **creating a description for reading data**, not necessarily executing `readValue()`. With this `fromSupplier` source, code inside the supplier runs upon subscription. Operators like `map`, `flatMap`, `filter`, and `onErrorResume` generally append steps without triggering them yet.

One way to visualize it:

~~~text
Controller returns Mono/Flux
          |
          v
Framework subscribes to the returned publisher
          |
          v
Data source -> map/flatMap -> security context -> response
          |             |                   |
          +----- error / cancel / completion signal -----+
~~~

`subscribe()` is an **execution boundary**: once a subscriber arrives, the Publisher starts emitting `onNext`, `onError`, and `onComplete` signals per the Reactive Streams contract. In WebFlux, the framework orchestrates subscribing to the publisher returned by the handler, thereby managing the response and tying into the request lifecycle.

Not every Publisher is "cold": there are hot, multicast, or `cache`/`share` sources. Yet common sources like `Mono.fromCallable`, `Mono.defer`, and many query chains are **lazy**, so failing to subscribe means "nothing runs". `Mono.just(expensiveCall())` is an important exception: `expensiveCall()` already ran **when creating** `Mono.just`, before subscription. To defer a synchronous call into a Publisher description, use `fromSupplier` or `fromCallable` as appropriate.

A proper pipeline forms **one connected chain** through which downstream receives values, errors, completion, and cancellation signals. All three mistakes in this lesson break one or more of those links.

## 3. First Mistake: Calling `block()` Inside WebFlux

### 3.1. What does `block()` actually do?

`Mono.block()` subscribes to the `Mono`, then **blocks the current thread** until a value arrives, it completes empty, or an error is emitted. `Flux.blockFirst()` and `Flux.blockLast()` share the same problem.

Wrong example in a WebFlux controller:

~~~java
// WRONG example; services and controllers are illustrative only, not standalone.
@GetMapping("/users/{id}")
public Mono<UserDto> user(@PathVariable String id) {
    UserDto user = userService.findById(id).block();
    return Mono.just(user);
}
~~~

Problems:
1. The handler may be running on Reactor Netty's **event loop**. Blocking the event loop prevents it from serving other requests; Reactor's blocking APIs on threads marked non-blocking normally throw `IllegalStateException` stating blocking is unsupported.
2. `block()` creates its own subscription and terminates the reactive portion early. Surrounding retry, timeout, cancellation, or context logic from the request may no longer be wired as expected.
3. If the source emits `Mono.empty()`, `block()` can return `null`, and `Mono.just(null)` is invalid.
4. Under high request counts, holding many threads waiting lowers throughput and increases latency.

Correct approach: return the publisher directly, or keep transforming it with operators:

~~~java
@GetMapping("/users/{id}")
public Mono<UserDto> user(@PathVariable String id) {
    return userService.findById(id);
}
~~~

If you need to inspect data and call another reactive service:

~~~java
@GetMapping("/users/{id}")
public Mono<UserDto> user(@PathVariable String id) {
    return userService.findById(id)
            .flatMap(user -> permissionService.verifyCanRead(user)
                    .thenReturn(user));
}
~~~

`verifyCanRead` in the example returns `Mono<Void>`: completing successfully means permitted; errors travel through the pipeline so the appropriate error/authorization handler decides the response. This is an integration snippet; define the corresponding services to run it.

### 3.2. Special danger when calling `block()` to get SecurityContext

Wrong example:

~~~java
String username = ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName())
        .block(); // WRONG in a WebFlux handler/service
~~~

`ReactiveSecurityContextHolder` reads caller information from the **subscription's Reactor Context**, not from a global variable. `block()` creates another subscription; besides the risk of blocking a thread, the new subscription is not guaranteed to carry the Reactor Context attached to the original request. The result can be missing context or an error.

Correct approach:

~~~java
Mono<String> username = ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName());
~~~

Then use `flatMap` to continue tasks that need the identity:

~~~java
return ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName())
        .flatMap(username -> orderService.findOrdersForUser(username));
~~~

Do not convert `Mono<SecurityContext>` into a synchronous `SecurityContext` just to use familiar Spring MVC syntax.

### 3.3. When is `block()` allowed?

Yes, at **outer boundaries outside Reactor** that you control, such as:
- A console program's `main` method waiting for the program to finish.
- A synchronous test or integration adapter with a synchronous API, when the current thread is not a non-blocking thread and blocking impact has been assessed.
- A boundary adapter where the application is no longer operating as a WebFlux request.

Using `block()` in `main` **does not** make it valid in a controller, WebFilter, or service inside a WebFlux pipeline. Do not use `block()` as a "fix" for code missing `flatMap`.

## 4. Second Mistake: Calling `subscribe()` Manually in a Controller or Service

### 4.1. The "I already called the service" mistake

Suppose `auditService.save` returns `Mono<Void>`:

~~~java
// WRONG: creates a Mono without placing it in the pipeline; audit may never be written.
return orderService.findById(orderId)
        .doOnNext(order -> auditService.save(order));
~~~

`doOnNext` takes a callback meant for observation or **fast, synchronous** side effects. This callback merely constructs a new `Mono` without chaining it into the sequence; for a lazy service, saving the audit never executes.

A "quick fix" that is still wrong:

~~~java
// WRONG: fire-and-forget; second subscription is detached from the response.
return orderService.findById(orderId)
        .doOnNext(order -> auditService.save(order).subscribe());
~~~

Calling `subscribe()` manually creates **two independent subscriptions**: one for the request/response, and one for saving the audit. Possible consequences:

- The response finishes before the audit finishes; if the audit fails, the original request never receives that error.
- Cancelling the request (e.g., client disconnects) does not automatically cancel the separately subscribed task.
- There is no guarantee that the request's context—especially `ReactiveSecurityContextHolder`—propagates to the new subscriber.
- Retries or timeouts on the main pipeline do not govern the side task.
- Simple callback `subscribe` overloads usually request unbounded demand upfront; with large `Flux` streams, backpressure becomes hard to manage.
- An unmanaged subscription can keep consuming resources after the request no longer needs the result.

**The right way is to chain the side task into the pipeline with `flatMap` and `thenReturn`:**

~~~java
return orderService.findById(orderId)
        .flatMap(order -> auditService.save(order)
                .thenReturn(order));
~~~

Both steps belong to the same subscription. If `auditService.save` fails, the error flows through the same chain; on cancellation, the cancel signal propagates to linked publishers when possible. `thenReturn(order)` waits for the audit publisher to complete successfully before returning `order`. This fits when business logic **must ensure the audit completed before sending the response**.

If auditing is merely auxiliary and failures must not break the response, express that policy transparently in the pipeline as well—for instance, `onErrorResume` with proper logging/metrics. Never silently swallow errors from a security-critical or data-integrity-critical step.

### 4.2. The "self-subscribe then immediately return a response" mistake

~~~java
// WRONG: does not wait for the authorization check result.
public Mono<String> handle(String orderId) {
    permissionService.checkAccess(orderId).subscribe();
    return Mono.just("OK");
}
~~~

Dangerous runtime behavior: the response can return `OK` even when the permission check has not finished or has failed. Authorization checks must never become a "background task" detached from the access decision.

Fix:

~~~java
public Mono<String> handle(String orderId) {
    return permissionService.checkAccess(orderId)
            .thenReturn("OK");
}
~~~

If `checkAccess` returns `Mono<Boolean>`, inspect the boolean value with `flatMap`; **do not** use `thenReturn("OK")` and accidentally ignore `false`. Example:

~~~java
return permissionService.canAccess(orderId)
        .flatMap(allowed -> allowed
                ? Mono.just("OK")
                : Mono.error(new AccessDeniedException("Not allowed")));
~~~

`AccessDeniedException` here is Spring Security's exception type; the snippet requires proper imports/services. In real implementations, prefer Spring Security's authorization mechanisms at the filter or method level and enforce object-level authorization in services where needed.

### 4.3. When is calling `subscribe()` yourself right?

At the **final boundary** where a component is genuinely responsible for consuming the Publisher—such as a console app, a reactive event consumer service, or infrastructure owning the subscription lifecycle. That component must then manage:
- `Disposable` and close/cancel mechanisms.
- `onError`, completion, and resource limits.
- Backpressure or load strategies when consuming a `Flux`.
- Identity/context to pass along and durability requirements after the caller leaves.

In a normal WebFlux HTTP handler, you **return `Mono`/`Flux`** and let WebFlux act as the subscriber. Never self-subscribe inside the same handler to "kick off" an operation.

## 5. Third Mistake: Pushing Work Outside the Reactive Chain

Common risky patterns:

~~~java
new Thread(() -> sendNotification(orderId)).start();

CompletableFuture.runAsync(() -> auditRepository.write(orderId));

// Or calling an @Async method without tying completion/error to the returned Mono.
~~~

These are illustrative anti-patterns, not a standalone Java program. Such tasks can run on different threads outside the request's lifecycle scope. If they rely on Servlet-familiar `ThreadLocal` `SecurityContextHolder`, they have no guarantee of preserving the original WebFlux identity either.

Distinguish two scenarios:

**A. The task must complete for the request to count as successful.** Keep it in the pipeline:

~~~java
return orderService.save(input)
        .flatMap(saved -> notificationService.sendReactive(saved)
                .thenReturn(saved));
~~~

If two independent data sources are needed, you can use `Mono.zip`; if sequential execution is required, use `flatMap`, `then`, `concatMap`, etc. depending on ordering constraints. The core idea is that the publisher is **composed** into the returned result.

**B. The task can reliably continue after returning the HTTP response.** Then it **genuinely has its own lifecycle** and must not secretly piggyback on the request subscription. Use a mechanism with an explicit owner—such as a job scheduler, message broker, durable queue, or transactional outbox—with retries and monitoring. Pass required facts (user ID, correlation ID, order ID, appropriate permission scope) as an **explicit payload**; do not expect an HTTP request's Reactor Context to live forever inside a background worker.

Simply calling `subscribe()` to simulate a background queue is insufficient: process shutdowns, asynchronous errors, network failures, or scaling across instances can lose work. Critical tasks require dedicated durability and tracking strategies.

## 6. Reactor Context and Spring Security: Bugs That Only Appear at Runtime

### 6.1. What is Reactor Context?

Reactor Context is a data structure traveling with the **subscription**, used to store metadata such as correlation IDs or security context without depending on a pinned thread. Each subscription creates a context flow associated with that subscriber; operators can read it via `Mono.deferContextual` or Spring Security's `ReactiveSecurityContextHolder`.

Basic Reactor example:

~~~java
Mono<String> greeting = Mono.deferContextual(ctx ->
        Mono.just("Hello " + ctx.get("username")))
    .contextWrite(reactor.util.context.Context.of("username", "alice"));
~~~

`contextWrite` supplies context to **upstream** operators within the same subscription. Reactor Context is structurally immutable; `put`/`contextWrite` calls create new views/contexts rather than mutating a global object shared across requests.

**Important point:** switching schedulers with `publishOn` or `subscribeOn` **does not inherently lose Reactor Context** while all operations stay in the same Reactor chain. Losing context usually comes from creating another subscription, pushing work to an API outside Reactor, or using `ThreadLocal` without proper propagation.

### 6.2. Wrong way to read the user in a detached task

~~~java
// WRONG: creates a subscription detached from the request.
orderService.findById(id).subscribe(order -> {
    ReactiveSecurityContextHolder.getContext()
            .subscribe(ctx -> externalAudit(
                    ctx.getAuthentication().getName(), order));
});
~~~

This snippet has nested subscriptions; the HTTP request's security context is not guaranteed to appear in the new subscription. It also breaks error and completion coordination for both the query and the audit.

Correct way when the audit must complete with the request:

~~~java
return ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName())
        .flatMap(username -> orderService.findById(id)
                .flatMap(order -> auditService.write(username, order)
                        .thenReturn(order)));
~~~

Extracting `username` in the pipeline and passing it explicitly to downstream APIs also reduces service coupling to implicit context. Only authentication verified by Spring Security should be used for access decisions.

### 6.3. What you must not infer from a single thread switch

- Switching threads within the same chain **does not automatically** lose Reactor Context.
- Spawning a `Thread`/`CompletableFuture` **does not automatically** inherit Reactor Context or `ReactiveSecurityContextHolder`.
- `block()` opens a new subscription; you cannot assume it has the same security context as the original subscription.
- Never copy full credentials/tokens from a request into a background queue; pass only the minimal required fields per security policy.

To wire tracing/logging in complex environments, understand the context-propagation mechanism actually supported by your framework/libraries. Never use `ThreadLocal` as the sole source of truth for a WebFlux request's identity.

## 7. Mandatory Synchronous APIs: How Much Does `boundedElastic` Solve?

Sometimes a system must call a legacy library with synchronous I/O—such as an old JDBC driver, a blocking-only SDK, or a file-reading library. Putting that call directly inside `map`, `doOnNext`, or `Mono.just(blockingCall())` will **still block the thread running the callback**.

Wrong:

~~~java
return Mono.just(legacyClient.fetch(id)); // fetch() runs immediately when creating Mono
~~~

Better when the library cannot be replaced yet:

~~~java
return Mono.fromCallable(() -> legacyClient.fetch(id))
        .subscribeOn(Schedulers.boundedElastic());
~~~

`Mono.fromCallable` defers invoking the API; `subscribeOn(Schedulers.boundedElastic())` moves the subscription/blocking source onto a scheduler meant for potentially blocking work. `Schedulers.boundedElastic()` has bounded resources, so this is a **temporary compatibility measure**, not a conversion into true non-blocking I/O. Set timeouts, watch for queue/thread exhaustion, and verify whether cancellation can actually stop synchronous I/O.

If the library offers a native reactive API (R2DBC, reactive HTTP client, etc.), generally prefer that API to reduce the number of threads held waiting on I/O.

`publishOn` changes where **downstream operators** execute; `subscribeOn` affects subscribing and the upstream source. Do not add random schedulers hoping blocking errors will vanish. What matters is placing the blocking call inside `fromCallable`/`defer` and scheduling at the proper boundary.

**Do not "fix" things by calling `block()` inside `boundedElastic` and pretending you have a reactive pipeline.** If the target API already returns `Mono`, compose it; isolate only genuinely synchronous calls when no better option exists.

## 8. Standalone Runnable Java 17+ Example: Composing Data Read, Audit, and Context

The example below needs only **Reactor Core**, with no Spring Boot or server required. The goal is to clearly see three facts: building a pipeline does not execute work yet, auditing is part of the subscription, and context is read inside the pipeline.

Structure:

~~~text
reactor-pipeline-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/ReactorPipelineDemo.java
~~~

**`settings.gradle`**

~~~groovy
rootProject.name = 'reactor-pipeline-demo'
~~~

**`build.gradle`**

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'io.projectreactor:reactor-core:3.6.6'
}

application {
    mainClass = 'demo.ReactorPipelineDemo'
}
~~~

**`src/main/java/demo/ReactorPipelineDemo.java`**

~~~java
package demo;

import reactor.core.publisher.Mono;
import reactor.util.context.Context;

public final class ReactorPipelineDemo {

    private ReactorPipelineDemo() {
    }

    private static Mono<String> loadResource(String id) {
        return Mono.fromSupplier(() -> {
            System.out.println("load:" + id);
            return "resource-" + id;
        });
    }

    private static Mono<Void> saveAudit(String principal, String resource) {
        return Mono.fromRunnable(() ->
                System.out.println("audit:" + principal + ":" + resource)
        ).then();
    }

    private static Mono<String> handle(String id) {
        return Mono.deferContextual(contextView -> {
            String principal = contextView.get("principal");
            return loadResource(id)
                    .flatMap(resource -> saveAudit(principal, resource)
                            .thenReturn("ok:" + resource));
        });
    }

    public static void main(String[] args) {
        Mono<String> pending = handle("42")
                .contextWrite(Context.of("principal", "alice"));

        System.out.println("assembled");
        String result = pending.block(); // Only at the console main() boundary.
        System.out.println("result:" + result);
    }
}
~~~

Run command (requires Java 17-compatible Gradle installed; if a Gradle Wrapper exists, replace with `./gradlew run`):

~~~bash
gradle run --quiet
~~~

**Program output:**

~~~text
assembled
load:42
audit:alice:resource-42
result:ok:resource-42
~~~

Exact explanation:
1. `handle("42")` builds the Publisher; printing `load:42` has not happened yet because `loadResource` uses `fromSupplier`.
2. The line `assembled` appears before any pipeline work runs.
3. `pending.block()` sits in `main` of the console program, acting as the outermost subscriber and waiting for the result; **do not** copy this into a WebFlux controller.
4. `contextWrite` places `principal=alice` into the context for the same subscription.
5. `flatMap` waits for `saveAudit` to finish before `thenReturn` returns the result. Hence the audit line appears before `result:...`.

In this small example, `saveAudit` only prints to the console when subscribed. It **does not simulate a real database or network client**; if real auditing uses asynchronous I/O, return that client's Publisher, or isolate blocking APIs as in Section 7.

### 8.1. Try modifying to observe the "forgotten publisher" bug

If you change `handle` to:

~~~java
private static Mono<String> handle(String id) {
    return loadResource(id)
            .doOnNext(resource -> saveAudit("alice", resource))
            .map(resource -> "ok:" + resource);
}
~~~

the `audit:...` line **is not printed**, because `saveAudit` returns a lazy `Mono` yet the callback neither composes nor subscribes to that publisher. This edit is a replacement within the same class above, not a standalone program.

If you further replace `saveAudit(...)` with `saveAudit(...).subscribe()`, the audit might appear in this synchronous demo, but only by coincidence because `fromRunnable` finishes immediately. With asynchronous I/O, the side task can finish after the response, fail independently, or miss request context. Never treat a successful console print as proof that detached subscriptions are safe.

## 9. Proper Integration in Spring WebFlux + Spring Security Reactive

In a WebFlux application with a security filter chain and authenticated routes, illustrative code can keep all business decisions inside one `Mono`:

~~~java
// Integration snippet: requires beans/orderService/auditService and appropriate imports.
@GetMapping("/orders/{id}")
public Mono<OrderDto> getOrder(@PathVariable String id) {
    return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication())
            .flatMap(authentication ->
                    orderService.findById(id)
                            .flatMap(order ->
                                    permissionService.requireOwner(
                                                    order, authentication.getName())
                                            .then(auditService.saveViewed(
                                                    order, authentication.getName()))
                                            .thenReturn(order)));
}
~~~

Here:
- `ReactiveSecurityContextHolder` retrieves `Authentication` from the request pipeline established by the security filter chain.
- `requireOwner` must complete successfully **before** access is accepted; if it emits an error, the pipeline stops and does not return `order`.
- `saveViewed` is a Publisher chained into the sequence, without manual `subscribe()`.
- `thenReturn(order)` runs only after all preceding steps succeed.
- Spring WebFlux subscribes to the Publisher returned by the controller.

For applications requiring no audit to be saved when the permission check fails, this structure enforces that exact order. Emitting `AccessDeniedException`/appropriate status must follow real security and exception-handling configuration. Object-level access checks such as order ownership are still needed in services; having `authenticated()` on the route does not automatically prove the order belongs to the caller.

**Note:** the snippet above illustrates composition, not an independently runnable program. `OrderDto`, `orderService`, `permissionService`, and `auditService` are application components that must be defined.

If you want to return the identity on a protected endpoint, the minimal pattern is:

~~~java
@GetMapping("/me")
public Mono<String> me() {
    return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication().getName());
}
~~~

No `block()`, no `subscribe()`, no manual `ThreadLocal` copying across threads.

## 10. Errors, Cancellation, and Timeouts: Verifying Chain Integrity

A vital aspect of reactive programming is **signals**, not merely return values.

| Scenario | When all steps share one chain | When calling `subscribe()` manually / spawning external tasks |
| --- | --- | --- |
| Query failure | `onError` flows down the pipeline for centralized handling | Errors can land in a secondary subscription without affecting the response |
| Client cancels request | Cancellation propagates upstream to linked publishers where possible | Detached tasks can continue running |
| Request timeout | `timeout` within the pipeline governs the request's publisher | Does not automatically govern detached jobs |
| Need step B to finish before returning A | `flatMap(...).thenReturn(...)` expresses ordering | Response can finish before B |
| Reading reactive security context | Relies on the current subscription's context | No guarantee context is present in a new subscription |

Intentional error-handling example:

~~~java
return orderService.findById(orderId)
        .flatMap(order -> auditService.save(order).thenReturn(order))
        .timeout(Duration.ofSeconds(3))
        .doOnError(error -> log.error("Order flow failed", error));
~~~

`timeout` generates an error signal if the chain fails to finish in time; `doOnError` only observes the error, **without swallowing it**. To turn an error into a fallback value, use `onErrorResume`, and only when business rules permit. Import `java.time.Duration` and an appropriate logger; this snippet is not standalone. Above all, **never** use a fallback that grants access when an authorization step fails.

Cancellation in Reactor is a cooperative signal: it does not guarantee instantaneously halting every blocking I/O call, external call, or work already handed to another system. Hence distinguish "cancellation was propagated" from "work definitely stopped".

You can diagnose publisher lifecycles via `doOnSubscribe`, `doOnError`, `doFinally`, and `StepVerifier` tests. When logging, avoid printing credentials, JWTs, passwords, personal data, or the entire security context.

## 11. When to Use Which Operator?

| Need | Usually appropriate pattern | Avoid |
| --- | --- | --- |
| Fast, synchronous value transformation | `map(value -> transform(value))` | `map(value -> blockingI/O(value))` on the event loop |
| Calling a service returning `Mono<R>` and needing its result | `flatMap(value -> service.call(value))` | `service.call(value).subscribe()` inside a callback |
| Waiting for `Mono<Void>` to finish while keeping original data | `flatMap(x -> save(x).thenReturn(x))` | `doOnNext(x -> save(x))` |
| Running next task after completion, discarding prior result | `first.then(second)` | Manually calling `subscribe()` on the first step |
| Reading subscription-bound data | `Mono.deferContextual(...)` / `ReactiveSecurityContextHolder` | Relying on `ThreadLocal` or detached subscriptions |
| Wrapping an unreplaceable blocking API | `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` | Blocking the event loop, or `Mono.just(blockingCall())` |
| Running post-response work needing reliability | Queue/job/outbox with lifecycle, retries, monitoring | Unowned fire-and-forget inside HTTP handlers |

This table does not replace inspecting return interfaces: `flatMap` on `Mono` vs. `flatMap`/`concatMap` on `Flux` differ in concurrency and ordering; choose per business requirements. `doOnNext` suits lightweight synchronous logging/metrics, not coordinating an asynchronous Publisher that must complete.

## 12. Real-World Scenarios and Analysis

### Scenario A — API occasionally loses audit logs

The controller returns a successful response, yet audits sometimes never appear. Look for `auditService.save(...).subscribe()` and `doOnNext(x -> auditService.save(x))`. If auditing is a condition for success, compose it with `flatMap(...).thenReturn(...)`. If the audit must outlive the request, switch to a durable mechanism suited to system requirements.

### Scenario B — Works on a small machine, slows down under heavy load

A service calls `blockingClient.fetch()` inside `map`, or `block()` in a controller, causing the event loop to wait on I/O. Inspect thread/stack traces, remove blocking from reactive chains, or isolate blocking APIs with `fromCallable` + `boundedElastic`. Measure and monitor scheduler limits; do not raise thread counts indefinitely.

### Scenario C — `ReactiveSecurityContextHolder.getContext()` is empty in an async task

Check whether the task was detached from the subscription via `subscribe()`, `new Thread`, or `CompletableFuture.runAsync`. If the result is needed before the response, compose it into the current chain. If it is a background job, pass the authenticated principal/actor ID explicitly as data along with valid authorization policies where the job runs.

### Scenario D — Unauthorized user still gets 200

Look for code manually calling `checkAccess().subscribe()` and then returning `Mono.just(success)`. Ensure the authorization result is **awaited and checked** within the returned publisher. Write tests with unauthenticated users, authenticated users lacking permission, and authorized users, and also verify data ownership checks in the service layer.

## 13. Self-Check Questions

1. Why can `Mono.just(repository.find())` call the repository before subscription, whereas `Mono.fromCallable(repository::find)` does not call it immediately?
2. When a WebFlux controller already returns `Mono<Order>`, why shouldn't the controller call `subscribe()` itself to "make the code run"?
3. `audit.save(x)` returns `Mono<Void>`. Why might `doOnNext(x -> audit.save(x))` write nothing? Rewrite it using `flatMap` and `thenReturn`.
4. A service calls `ReactiveSecurityContextHolder.getContext().block()` from a WebFlux request. What **two** categories of bugs should you think of?
5. Does `publishOn(Schedulers.parallel())` in the same chain necessarily lose Reactor Context? How does `CompletableFuture.runAsync` differ?
6. If work must continue after the HTTP response and not be lost if the instance dies, why is manual `subscribe()` not enough?
7. Moving a synchronous JDBC client onto `boundedElastic`—has that client become non-blocking?

**Suggested answers:** (1) `just`'s argument is evaluated eagerly, while `fromCallable` defers until subscribe; (2) WebFlux owns the response subscription; (3) `doOnNext` does not subscribe to a returned Publisher, so chain `flatMap(x -> audit.save(x).thenReturn(x))`; (4) risk of blocking on a non-blocking thread and creating a new subscription lacking the request context; (5) context is not lost merely by switching schedulers within the same chain, whereas a manually launched future does not automatically inherit Reactor Context; (6) you need lifecycle/durability/retries/monitoring; (7) no, it is a blocking API isolated on an appropriate scheduler.

## 14. Takeaways

**Core Reactor rule in WebFlux: keep required work inside one returned pipeline; the framework subscribes at the HTTP boundary; never block the event loop, never spawn arbitrary side subscriptions, and never treat SecurityContext as a thread-local variable present everywhere.**

When you need data from another Publisher, **compose with operators**. When you must call a blocking library, **isolate it explicitly and with bounds**. When you need a job truly independent of the request, **hand it to a component with its own lifecycle and reliability guarantees**. These choices determine authorization correctness, error observability, and WebFlux application stability.

References:
- Project Reactor — Blocking Can Be Wasteful: https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html
- Project Reactor — Adding a Context to a Reactive Sequence: https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html
- Project Reactor — Simple Ways to Create a Flux or Mono and Subscribe to It: https://projectreactor.io/docs/core/release/reference/coreFeatures/simple-ways-to-create-a-flux-or-mono-and-subscribe-to-it.html
- Spring Security — Reactive Security Context: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html