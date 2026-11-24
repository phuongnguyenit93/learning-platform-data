# Avoiding Nested Subscribe Calls That Break Error and Cancellation Propagation

**Context:** Spring Framework Reactive → **Cancellation and resources**.

In Project Reactor, a `Mono<T>` or `Flux<T>` is a `Publisher`: it describes work and a signal chain. Calling `subscribe()` creates **a new subscription**, with its own subscriber, data demand (`request`), `onError` path, `onComplete` lifecycle, and cancellation right (`cancel`).

A common mistake is calling `subscribe()` **inside** a callback of a running reactive chain:

```java
return loadOrder(id)
        .doOnNext(order -> reserveStock(order).subscribe());
```

This code may look like “load the order then reserve stock”, but it actually creates **two independent subscriptions**:

1. The parent subscription processes `loadOrder(id)` and can complete.
2. The child subscription created manually by `reserveStock(order).subscribe()` is no longer part of the result returned by `return`.

Consequence: **the parent can succeed before the child finishes, child errors do not automatically flow to the parent's `onErrorResume`/HTTP handler, and cancelling the parent does not automatically cancel the child**. Child side effects can keep running after the client disconnects, leaking resources, sending late data, or performing work that is no longer needed.

**How to fix when the child task is part of the parent request:** do not subscribe to the child; **return the child publisher into a composing operator** such as `flatMap`, `concatMap`, `flatMapMany`, `then`, or `Mono.when`. Only the subscription at the final boundary (for example Spring WebFlux, a test, or a lifecycle-managed component) launches the composed flow.

## 1. The Right Structure: One Work Tree Managed by the Final Subscription

Incorrect pattern:

```java
Mono<Order> pipeline = findOrder(id)
        .doOnNext(order ->
                stockService.reserve(order).subscribe());
```

Composed pattern:

```java
Mono<Order> pipeline = findOrder(id)
        .flatMap(order ->
                stockService.reserve(order).thenReturn(order));
```

These are **snippets** requiring `Order`, `findOrder`, and `stockService` in the application. Assume `reserve(order)` returns `Mono<Void>` and completes once the reservation succeeds per the service contract.

The difference:

| Question | `doOnNext(...subscribe())` | `flatMap(...thenReturn(...))` |
|---|---|---|
| Who subscribes to the reserve work? | Callback manually creates a child subscription | The `flatMap` operator manages the inner subscription |
| Does parent wait for reserve to succeed before returning item? | **No** | **Yes**, because `thenReturn(order)` waits for completion |
| Reserve signals `onError`? | Error belongs to the **child subscription** | Error propagates into the **parent pipeline** |
| Client cancels the parent subscription? | Does not automatically cancel the child subscription | Cancellation propagates to still-active inner publishers |
| Can timeout/retry apply to the entire chain? | Cannot control the child work | Yes, per operator placement and policy |
| Can everything be observed with a trailing `doFinally`? | Does not see the independent child lifecycle | Observes termination/cancellation of the composed result |

**Note:** cancellation is **propagated**, yet it is not a transaction-undo mechanism. An already-sent HTTP/DB request, recorded payment, or external side effect is not necessarily rolled back when Reactor calls `cancel()`. This is analyzed separately in section 11.

## 2. How to Read the Three Lifecycle Signal Kinds

A reactive subscription can go through:

```text
subscribe → onSubscribe(subscription)
          → request(n)              (demand, may occur multiple times)
          → onNext(value)           (0..N times; Mono at most 1)
          → onComplete()            (success)

Or:
subscribe → ... → onError(Throwable) (error, terminal)

Or:
subscribe → ... → cancel()          (cancel, not an onError terminal)
```

- `onError` and `onComplete` are two distinct terminal signals; one subscription **never receives both**.
- `cancel()` expresses that the subscriber no longer needs data. The source must react per contract, though the actual effect on external work depends on the adapter.
- `doOnError` observes errors; **it does not recover by itself**.
- `doOnCancel` observes cancellation.
- `doFinally(signalType)` runs after the pipeline terminates via complete, error, or cancel, receiving `SignalType.ON_COMPLETE`, `SignalType.ON_ERROR`, or `SignalType.CANCEL`.

If you manually `subscribe()` to an inner publisher, the inner has **its own subscription**, so the parent's canceller or error handler has no automatic mechanism owning that path.

### How Does “Nested Subscribe” Differ from “Nested Publisher”?

```java
Mono<Mono<String>> nestedValue =
        Mono.just("user-1")
                .map(id -> lookupName(id));
```

Here `map` produces a **value of type `Mono<String>`** inside the outer Mono, i.e., `Mono<Mono<String>>`. That is usually not what you want, yet **it has not subscribed yet**; you can still flatten it.

```java
Mono<String> composed =
        Mono.just("user-1")
                .flatMap(id -> lookupName(id));
```

`flatMap` accepts the child `Publisher`, subscribes to it under the operator's lifecycle, and **emits its results/errors into the parent**. Do not replace it with:

```java
Mono<String> wrong = Mono.just("user-1")
        .map(id -> {
            lookupName(id).subscribe();  // subscription detached from parent
            return id;                  // not the looked-up name
        });
```

These three snippets are **illustrative**; `lookupName` is assumed to return `Mono<String>`.

## 3. Why Is subscribe() Inside doOnNext So Error-Prone?

`doOnNext`, `doOnSuccess`, and `doOnError` are **observation/side-effect hooks**, not publisher-composition tools.

Example:

```java
Mono<Order> result = findOrder(id)
        .doOnNext(order ->
                emailService.sendConfirmation(order)
                        .subscribe());
```

If `sendConfirmation` errors, that error belongs to the child subscription. `result.onErrorResume(...)` only sees errors flowing **through `result`**, not errors from an independent child subscription. If `sendConfirmation` has not finished, `findOrder` can still complete and the controller can return a response.

Several subtle consequences:

- **Lost error reporting:** parent completes 200/202 even when email/stock/payment failed; if the inner `subscribe` lacks an error consumer, Reactor may even report “ErrorCallbackNotImplemented”/dropped error via hooks.
- **Lost cancellation:** the user cancels the request yet the email still sends or the child connection remains open.
- **Lost ordering:** subsequent work in the parent can run without waiting for the child work.
- **Lost backpressure:** the parent's demand does not automatically throttle the new subscriber's demand. Zero-arg/consumer `subscribe()` overloads usually request unbounded demand for that subscription.
- **Lost context:** Reactor `Context`, tracing/security/transaction data attached to the parent subscriber are not guaranteed to transfer to a separately created child subscription.
- **Lost testability:** `StepVerifier` on the parent can turn green even though the child failed afterward.
- **Hard resource cleanup:** the `Disposable` handle returned by the inner `subscribe` is discarded; there is no owner to dispose it when the request ends.
- **Retries cause repeated execution:** retrying the parent can spawn multiple independent children if every attempt passes through the callback.

**Not every `subscribe()` call is wrong:** at an **actively owned application boundary** such as a command-line `main`, a scheduled background job, a test harness, or a component with managed start/stop, subscribing can be valid. The problem is creating an unowned child subscription for work **that belongs to the current request's result**.

## 4. Visualizing Broken Error and Cancellation Paths

### Nested subscribe (detached)

```text
HTTP request / parent Subscriber
              |
              v
          findOrder()
              |
          doOnNext(order)
              |  \
              |   \--- reserveStock(order).subscribe()
              |           |
              |           +--- CHILD Subscription
              |                 +--- onError → child handler/hook
              |                 +--- separate cancel, if handle exists
              v
       parent onNext + onComplete

Client disconnect → cancel(parent) --X--> child is not auto-cancelled
Parent onErrorResume(...)        --X--> child error does not arrive
```

**The broken arrow `X`** means there is no automatic management link between the two subscriptions.

### flatMap (keeping the child component inside the chain)

```text
HTTP request / Subscriber
             |
             v
         findOrder()
             |
             v
        flatMap(order)
             |
             +--- reserveStock(order) [inner managed by operator]
                      |
                      +--- onComplete → continue to thenReturn(order)
                      +--- onError ----→ parent onError
                      +--- cancel ←---- parent cancel
             |
             v
         parent onNext(order), onComplete

Client disconnect → cancel(parent) → cancel(still-active inner)
```

**Why does the operator know about the inner?** Because the `flatMap` callback **returns the Mono** for Reactor to manage, instead of calling `subscribe` and throwing the handle away.

## 5. Choosing Composition Operators for the Right Purpose

| Need | Reasonable choice | Signals/characteristics to know |
|---|---|---|
| Have a `Mono<A>`, need to call `Mono<B>` using value A | `mono.flatMap(a -> loadB(a))` | Inner errors and cancellation belong to the composed result |
| Have a `Mono<A>`, need to emit many `Flux<B>` elements | `mono.flatMapMany(a -> streamB(a))` | Result is `Flux<B>` |
| Have a `Flux<A>`, process multiple inner publishers concurrently | `flux.flatMap(a -> process(a), concurrency)` | Results may interleave; limits concurrency |
| Have a `Flux<A>`, need to preserve order of each inner | `flux.concatMap(a -> process(a))` | Processes inners sequentially; no nested subscribe needed |
| Need to run B after A **completes successfully** | `a.then(b)` | B does not run if A errors; A's value is discarded |
| Need to keep A after side effect B finishes | `a.flatMap(v -> b(v).thenReturn(v))` | Returns original value after B succeeds |
| Have independent `Mono<Void>` tasks, need to wait for all | `Mono.when(one, two)` | Completes only when all sources complete; error can cancel the rest |
| Need to combine two Monos **that both emit a value** | `Mono.zip(a, b)` | Combines two values; if either source is empty, no tuple is emitted |
| Only want to observe items/errors | `doOnNext`/`doOnError` | Observation only, does not compose child tasks |
| Need to clean up publisher-bound resources | `using`/`usingWhen`, `doFinally` per semantics | Keeps lifecycle within the same subscription |

### 5.1. flatMap: Value-Dependent Business Logic

```java
Mono<ProfileCard> card = findUser(userId)
        .flatMap(user -> avatarService.findAvatar(user.id())
                .map(url -> new ProfileCard(user.name(), url)));
```

**Snippet:** `findUser` and `avatarService` are assumed to return `Mono<User>` and `Mono<String>`. If finding the user errors, fetching the avatar errors, or the client cancels while waiting for the avatar, control mechanics remain in one chain. However, if the avatar is empty, `card` is also empty; decide fallback behavior per business rules.

### 5.2. then: Operation B Must Wait for A to Succeed

```java
Mono<Void> workflow = validate(order)
        .then(reserve(order))
        .then(save(order));
```

This snippet assumes all three methods return `Mono<Void>` or a compatible `Mono<?>`. `then` ignores A's items and only subscribes to B after A's successful `onComplete`. If `reserve` errors, `save` is not subscribed to by this chain segment. Watch **how sources are created**: `save(order)` might eagerly perform side effects when the factory is called if implemented wrongly; to defer even publisher creation when needed, use `Mono.defer(() -> save(order))`.

### 5.3. concatMap: Ordered Item-by-Item Processing

```java
Flux<Receipt> results = orders
        .concatMap(order ->
                paymentService.charge(order)
                        .flatMap(receipt -> auditService.record(receipt)
                                .thenReturn(receipt)));
```

This is a snippet. `concatMap` waits for the previous inner to finish before processing the next inner, preserving output order; errors/cancellation still belong to one chain. Do not use `concatMap` as an “exactly-once payment” guarantee: design transactions, idempotency keys, and retry/compensation in external systems.

### 5.4. flatMap Concurrency: Does Not Mean Unbounded Fan-Out

```java
Flux<EnrichedUser> enriched = userIds
        .flatMap(id -> userService.enrich(id), 8);
```

This snippet assumes `userIds` and `userService`. The number 8 limits concurrent active inner publishers managed by this operator in this overload, **not an application-wide total network request quota**. `flatMap` can interleave results and does not preserve ID order. When ordered output is required alongside overlapping execution, consider `flatMapSequential` with appropriate buffer/resource limits.

## 6. Runnable Java 17+ Program: Detached Errors and Detached Cancellation

The following example **runs standalone with Maven + Reactor Core** and uses no sleep/timers/network, so output ordering can be verified deterministically. There are four scenarios:

1. Inner errors inside `doOnNext(...subscribe())` while parent completes successfully.
2. Inner errors inside `flatMap` and parent receives the error.
3. Cancelling the parent of a nested subscription does not cancel the inner `Mono.never()`.
4. Cancelling the parent of `flatMap` cancels the pending inner publisher.

Directory structure:

```text
reactor-nested-subscribe-demo/
├── pom.xml
└── src/main/java/demo/NestedSubscribeDemo.java
```

Contents of `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>reactor-nested-subscribe-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.8.8</version>
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
                <version>3.4.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Contents of `src/main/java/demo/NestedSubscribeDemo.java`:

```java
package demo;

import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;
import reactor.core.Disposable;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class NestedSubscribeDemo {

    private static Mono<String> failStock() {
        return Mono.error(new IllegalStateException("stock unavailable"));
    }

    public static void main(String[] args) {
        System.out.println("1) nested error");
        Mono.just("order-7")
                .doOnNext(order -> failStock().subscribe(
                        ignored -> System.out.println("child:next=" + ignored),
                        error -> System.out.println(
                                "child:error=" + error.getMessage())))
                .subscribe(
                        order -> System.out.println("parent:next=" + order),
                        error -> System.out.println(
                                "parent:error=" + error.getMessage()),
                        () -> System.out.println("parent:complete"));

        System.out.println("2) composed error");
        Mono.just("order-7")
                .flatMap(order -> failStock())
                .subscribe(
                        value -> System.out.println("composed:next=" + value),
                        error -> System.out.println(
                                "composed:error=" + error.getMessage()),
                        () -> System.out.println("composed:complete"));

        System.out.println("3) nested cancellation");
        AtomicBoolean nestedChildCancelled = new AtomicBoolean();
        AtomicReference<Disposable> child = new AtomicReference<>();

        Flux<Integer> nestedParent = Flux.just(1)
                .concatWith(Flux.<Integer>never())
                .doOnNext(number -> child.set(
                        Mono.<String>never()
                                .doOnCancel(() ->
                                        nestedChildCancelled.set(true))
                                .subscribe()));

        Disposable parent = nestedParent.subscribe(
                number -> System.out.println("parent:next=" + number),
                error -> System.out.println(
                        "parent:error=" + error.getMessage()));

        parent.dispose();
        System.out.println("childCancelledAfterParentDispose="
                + nestedChildCancelled.get());

        child.get().dispose();
        System.out.println("childCancelledAfterManualDispose="
                + nestedChildCancelled.get());

        System.out.println("4) composed cancellation");
        AtomicBoolean composedChildCancelled = new AtomicBoolean();

        Disposable composed = Flux.just(1)
                .concatWith(Flux.<Integer>never())
                .flatMap(number ->
                        Mono.<String>never()
                                .doOnCancel(() ->
                                        composedChildCancelled.set(true)))
                .subscribe(
                        value -> System.out.println("composed:next=" + value),
                        error -> System.out.println(
                                "composed:error=" + error.getMessage()));

        composed.dispose();
        System.out.println("composedChildCancelledAfterDispose="
                + composedChildCancelled.get());
    }
}
```

Run from the directory containing `pom.xml` with JDK 17+ and Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.NestedSubscribeDemo
```

**Expected standard output** (excluding Maven logs):

```text
1) nested error
child:error=stock unavailable
parent:next=order-7
parent:complete
2) composed error
composed:error=stock unavailable
3) nested cancellation
parent:next=1
childCancelledAfterParentDispose=false
childCancelledAfterManualDispose=true
4) composed cancellation
composedChildCancelledAfterDispose=true
```

**Why is the output deterministic in this demo?**

- `Mono.just`, `Mono.error`, and `Flux.just` emit synchronously upon subscription; `Mono.never`/`Flux.never` emit nothing and never complete.
- In scenario 1, `doOnNext` runs its observer and creates the child subscription before the parent's `onNext` is passed down, so the child error callback prints before `parent:next`; the parent still completes.
- In scenario 2, `flatMap` wires the inner error into the parent; there is no `composed:complete`.
- In scenario 3, the parent stays active because of `Flux.never()` after item 1. Calling `parent.dispose()` cancels the parent subscription; the child `Mono.never` created by manual `subscribe` is **not** cancelled yet. Only `child.get().dispose()` triggers the child's `doOnCancel`.
- In scenario 4, `flatMap` manages the inner `Mono.never`. `composed.dispose()` cancels the parent and the still-active inner; the flag becomes `true`.

In real applications, I/O can execute asynchronously across multiple threads, so **log ordering must not be treated as proof** of completion order. Here the sources and cancellation calls are synchronous, and `AtomicBoolean` serves as direct evidence of the cancellation callback.

**Limitation:** this example demonstrates only Reactor signal propagation. An HTTP/DB library might not be able to undo a side effect already sent to a server even after the subscription is cancelled.

## 7. WebFlux Controller: Do Not Subscribe Manually When Preparing an HTTP Response

A WebFlux controller is responsible for **returning a publisher** or an appropriate response. The framework registers the subscriber to connect the chain to the HTTP request/response. Never call `subscribe` just to “make the publisher run” if that work determines the final response.

### 7.1. Wrong Way: Response Can Complete Too Early

```java
@GetMapping("/users/{id}/card")
public Mono<UserDto> wrong(@PathVariable String id) {
    return userService.findById(id)
            .doOnNext(user ->
                    avatarService.loadAvatar(user.id())
                            .subscribe());
}
```

This snippet assumes a controller with `userService`, `avatarService`, and `UserDto`. The method returns only the user, does not wait for the avatar, does not return the avatar, and does not propagate avatar errors into HTTP handling. If the client disconnects, the inner subscription is not automatically cancelled by the framework.

**Do not fix this with `block()`**:

```java
// WRONG in WebFlux event loop: blocks the request thread.
UserDto user = userService.findById(id).block();
String avatar = avatarService.loadAvatar(user.id()).block();
```

`block()` breaks the non-blocking model and can be rejected by Reactor on threads marked non-blocking. Compose the publishers instead.

### 7.2. Right Way: Card Depends on Both User and Avatar

The example below is a **valid Java 17 controller inside a Spring Boot app with the WebFlux starter**, including supporting types; it requires real service beans and a main application.

```java
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/users")
public class UserCardController {
    private final UserService userService;
    private final AvatarService avatarService;

    public UserCardController(UserService userService,
                              AvatarService avatarService) {
        this.userService = userService;
        this.avatarService = avatarService;
    }

    @GetMapping("/{id}/card")
    public Mono<UserCard> getCard(@PathVariable String id) {
        return userService.findById(id)
                .switchIfEmpty(Mono.error(
                        new ResponseStatusException(
                                HttpStatus.NOT_FOUND, "User not found")))
                .flatMap(user ->
                        avatarService.loadAvatar(user.id())
                                .defaultIfEmpty("default.png")
                                .map(avatarUrl ->
                                        new UserCard(user.id(),
                                                user.displayName(),
                                                avatarUrl)));
    }
}

record UserDto(String id, String displayName) { }
record UserCard(String id, String displayName, String avatarUrl) { }

interface UserService {
    Mono<UserDto> findById(String id);
}

interface AvatarService {
    Mono<String> loadAvatar(String userId);
}
```

Processing flow:

1. `userService.findById(id)` returns `Mono<UserDto>`; the framework subscribes when handling HTTP.
2. If no user exists, `switchIfEmpty` emits an HTTP 404 error per the example contract.
3. If a user exists, `flatMap` composes `loadAvatar` as a child task. The inner can emit a URL, empty, or an error.
4. `defaultIfEmpty("default.png")` only recovers the **missing avatar (empty)** case; it **does not hide connection errors** from the avatar service.
5. When the avatar succeeds, `map` builds `UserCard`; the 200 response contains data from both services.
6. If loading the avatar fails, the error propagates in the returned chain for the WebFlux error handler to process.
7. If the client cancels before the avatar finishes, cancellation can reach the still-active inner publisher; drivers/services must support cancellation to reduce actual work.

There is no `subscribe()` call anywhere in the controller. The example is a **Spring Boot app-dependent snippet**, not a standalone server program; service implementations must ensure non-blocking I/O if end-to-end non-blocking WebFlux is required.

### 7.3. When the Secondary Task Is Mono<Void>

When you only need the success/failure of the secondary task and still return the user:

```java
Mono<UserDto> response = userService.findById(id)
        .flatMap(user -> auditService.recordAccess(user)
                .thenReturn(user));
```

This snippet assumes `recordAccess` returns `Mono<Void>`. `thenReturn(user)` emits the user only after audit recording completes successfully; if auditing fails, the response pipeline fails. However, **cancellation does not guarantee the audit was durably written**, so if legal auditing must survive client disconnects, design a durable/outbox model or an independent background worker with dedicated ownership rather than “fixing” it with an unowned nested subscribe.

## 8. Error Pitfalls: Parent onErrorResume Does Not Catch Detached Child Errors

Consider:

```java
Mono<String> result = Mono.just("job")
        .doOnNext(job ->
                Mono.<String>error(
                        new IllegalStateException("child failed"))
                    .subscribe())
        .onErrorResume(error -> Mono.just("fallback"));
```

**Wrong for recovery goals.** The child error does not become an `onError` in the parent. Moreover, calling `subscribe()` without an error handler can cause Reactor to report an unhandled error. The parent's `onErrorResume` has no error signal to handle, so the parent may still emit `"job"` normally.

Right way:

```java
Mono<String> result = Mono.just("job")
        .flatMap(job ->
                Mono.<String>error(
                        new IllegalStateException("child failed")))
        .onErrorResume(IllegalStateException.class,
                error -> Mono.just("fallback"));
```

Upon subscribing, the child error flows through `flatMap` so `onErrorResume` can replace it with `fallback`. In real business logic, recover only **recoverable** error types; do not use `onErrorResume(error -> Mono.empty())` for all exceptions if doing so masks system failures.

### Placing Observers Before and After Recovery

```java
Mono<String> result = remoteCall()
        .flatMap(value -> childCall(value))
        .doOnError(error -> log.warn("Combined workflow failed", error))
        .onErrorResume(TransientFailure.class,
                error -> cachedFallback());
```

This is a snippet with hypothetical methods/services/exceptions. The `doOnError` observer sits **after `flatMap`**, so it sees errors propagated from either `remoteCall` or `childCall`. `onErrorResume` recovers only matching errors. If you place the observer after recovery, it does not see **already-recovered** errors, though it can still see non-matching errors or fallback failures.

**Note on checked exceptions:** when calling APIs that throw checked exceptions inside `map`/`flatMap`, wrap them appropriately or use `Mono.fromCallable` inside the chain. Do not catch and call `subscribe()` as a shortcut.

## 9. Cancellation Pitfalls: “Cancelled Parent” Does Not Mean “Cancelled Everything”

In a properly composed chain, operators maintain links to upstream/inner subscriptions. When the external subscriber calls `cancel()` or `Disposable.dispose()`, Reactor can deliver cancellation to still-active upstream/inner publishers.

Distinctions to keep clear:

| Issue | What can be guaranteed in the pipeline | What must not be assumed |
|---|---|---|
| Cancelling `flatMap` | Active inner subscriptions are managed and receive cancel | Cancel does not automatically roll back already-processed HTTP requests |
| Cancelling `then` | The currently subscribed source can receive cancel | Already-completed source B cannot “un-complete” |
| Cancelling outer `Flux` | Operator stops requesting/emitting further as appropriate | External producer (broker/device) definitely stopped |
| Cancelling `Mono.never` subscription | `doOnCancel` callback runs if subscription was established and cancelled | Any external work is necessarily cancellable |
| Cancelling a manual nested `subscribe` | Only if you hold a handle and actively dispose that child | `cancel(parent)` will automatically locate the child |
| Client closes HTTP connection | WebFlux/transport usually cancels the response subscription | Disconnect detection is always instant and all side effects are undone |

### Using doOnCancel and doFinally to Observe

```java
Mono<String> workflow = parentOperation()
        .flatMap(value -> childOperation(value))
        .doOnCancel(() ->
                log.info("Workflow subscription was cancelled"))
        .doFinally(signal ->
                metrics.counter("workflow.terminal",
                        "signal", signal.name()).increment());
```

This is a snippet with `log`/`metrics` and hypothetical methods. `doOnCancel` observes cancellation signals. `doFinally` receives `CANCEL`, `ON_COMPLETE`, or `ON_ERROR` when the pipeline ends accordingly.

**Final observation:** `doFinally` is a hook that runs **after the terminal signal has been forwarded downstream**. With cancellation/concurrency, log ordering across threads can mislead; test with controllable publishers and explicit synchronization when needed rather than guessing from logs.

## 10. Backpressure and Nested Subscribe

Reactive Streams establishes a demand channel between subscriber and upstream via `request(n)`. If inside a callback you write:

```java
source.doOnNext(item ->
        childFlux(item).subscribe(value -> process(value)));
```

then `childFlux(item)` receives a **new subscriber**. Consumer-based `subscribe` overloads typically request unbounded data (`Long.MAX_VALUE`), so parent demand **no longer bounds/throttles** the child source accurately. If many parent items arrive fast, each item can spawn another child subscription, pushing the system into:

- More HTTP connections than expected.
- Concurrent database queries or I/O sources multiplying.
- Growing queues, CPU, direct memory, and response latency.
- No strategy to cancel all children when the request cancels.
- Out-of-order emissions or broken business transactions.

Composed approach:

```java
Flux<Result> limited = source
        .flatMap(item -> childFlux(item), 4);
```

This is a snippet; `Result`, `source`, and `childFlux` must be declared. The number 4 limits **concurrently active inner publishers at this operator**, not total connections or queues across all services. Downstream can also use `limitRate` or other operators to shape demand. For data requiring order, use `concatMap` or `flatMapSequential` as appropriate.

**Do not use nested subscribe as an “async optimization”**. Detaching the child only lets the parent response return sooner because **it stopped waiting for work it needed to wait for**, not because the system became faster, more accurate, or more resource-efficient.

## 11. Resources, Cancellation, and Practical Limits of Cancellation

### 11.1. Subscriptions with Cleanup Hooks

If a publisher uses per-subscription resources, cleanup must be attached across all three paths: **complete**, **error**, and **cancel**.

```java
Flux<String> monitored = readEvents()
        .doOnCancel(() -> log.info("Consumer cancelled"))
        .doFinally(signal ->
                log.info("Read workflow finished: {}", signal));
```

This snippet assumes `readEvents` returns `Flux<String>`. Observation hooks help reveal lifecycle events; however, if a resource must be closed reliably, place resource acquisition/cleanup in the appropriate operator rather than hoping logging alone releases resources.

### 11.2. using: Synchronous Resources, Cleanup on Termination/Cancellation

Simplified example of `Flux.using` with a hypothetical `AutoCloseable`:

```java
Flux<String> lines = Flux.using(
        () -> openTextSource(),
        source -> readLinesAsFlux(source),
        source -> source.close());
```

This is a **model snippet**, not standalone runnable: `openTextSource()`, `readLinesAsFlux(...)`, and the resource type must be implemented. Key idea: the resource is created **per subscription**, the reading source sits within the resource's ownership scope, and Reactor invokes cleanup on complete, error, or cancel. Whether opening/reading/closing is blocking depends on the implementation; `using` by itself does not turn blocking I/O into non-blocking.

### 11.3. usingWhen: Asynchronous Resources and Cleanup

For resources whose cleanup returns a publisher (such as reactive connections/transactions), `Mono.usingWhen` and `Flux.usingWhen` model the lifecycle:

```java
Mono<Report> report = Mono.usingWhen(
        acquireSession(),                     // Mono<Session>
        session -> fetchReport(session),      // Mono<Report>
        session -> closeSession(session),     // cleanup publisher on complete
        (session, error) ->
                abortAndCloseSession(session, error), // cleanup on error
        session -> cancelAndCloseSession(session)     // cleanup on cancel
);
```

**Illustrative code**; `acquireSession`, `fetchReport`, `closeSession`, `abortAndCloseSession`, `cancelAndCloseSession`, and types `Session`/`Report` must be declared in a real system. Cleanup functions return `Publisher<?>`; do not call `subscribe` inside them.

Important point: both the resource closure and cleanup reside inside **one composed publisher**, so the operator can manage complete/error/cancel paths. With `Mono.usingWhen`, Reactor defers delivering the success/error signal downstream until the corresponding async cleanup finishes; **cleanup failures can alter the final outcome**. Do not treat cleanup as an ignorable side effect.

### 11.4. Cancellation Is Not Transaction Rollback

Example of a money-transfer POST:

1. Client calls API.
2. Upstream sends request to payment provider.
3. Client aborts HTTP.
4. Reactor cancels the waiting subscription.
5. Payment provider **may have already processed the transfer** even though the client is no longer listening for the response.

Hence systems need idempotency keys, status ledgers, re-query mechanisms, outboxes, or business-appropriate compensation. **Never use cancellation as a guarantee that “no transaction occurred”.**

### 11.5. Cleanup on Discard/Buffering

A publisher may emit reference-counted `DataBuffer`/`ByteBuf`. When an operator drops elements (filter, drop, cancel...), they sometimes need releasing per resource contracts. Reactor offers `doOnDiscard` for operators supporting discard; Spring provides matching `DataBuffer` release utilities.

```java
Flux<DataBuffer> incoming = receiveBuffers()
        .filter(buffer -> keepBuffer(buffer))
        .doOnDiscard(DataBuffer.class,
                org.springframework.core.io.buffer.DataBufferUtils::release);
```

This is a **hook-illustration snippet only**, requiring `DataBuffer`, `receiveBuffers`, `keepBuffer`, and the Spring import. It is not by itself proof that no path leaks: you must check ownership, reference counting, which operators support discard, and avoid double release. In real pipelines, prefer Spring-managed APIs rather than mixing manual reference-counting with nested subscribes.

## 12. Context, Tracing, Security, and Transactions Are Affected Too

A Reactor subscription carries a `Context` attached to the subscriber. Composed operators can use `deferContextual` to read request/correlation IDs provided via `contextWrite` or corresponding tracing integrations.

Example:

```java
Mono<String> request = Mono.deferContextual(context ->
        Mono.just(context.getOrDefault("traceId", "missing")))
    .flatMap(id -> childService(id))
    .contextWrite(ctx -> ctx.put("traceId", "trace-123"));
```

This is a snippet assuming `childService` returns `Mono<String>`. The child publisher composed inside `flatMap` can observe the Reactor Context propagated along the chain. **Do not casually use `ThreadLocal`** as proof that context automatically follows reactive tasks, since schedulers can switch threads.

By contrast:

```java
Mono<String> detached = Mono.just("request")
        .doOnNext(value ->
            Mono.deferContextual(context ->
                Mono.just(context.getOrDefault("traceId", "missing")))
            .subscribe())
        .contextWrite(ctx -> ctx.put("traceId", "trace-123"));
```

This is a snippet. The new `subscribe` call creates a separate subscriber/context, so **you cannot assume** the inner sees the parent's `traceId`. Beyond tracing, the same design flaw can break expectations for Spring reactive transactions, security, or request-scoped data. Do not claim every transaction is definitely lost: behavior depends on the transaction manager, operators, and how sources use `Context`; the rule is **do not detach a subscription if you need to preserve the parent's lifecycle/context**.

## 13. Testing Errors and Cancellation with StepVerifier

When fixing nested subscribes, test **the parent's terminal signal** and **cancellation impact on the child**, not merely whether a callback was invoked.

Create a `Mono<String>` with a simulated error and compose:

```java
Mono<String> combined = Mono.just("order-7")
        .flatMap(order ->
                Mono.<String>error(
                        new IllegalStateException("stock unavailable")));
```

JUnit 5 + `reactor-test` tests:

```java
import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertTrue;

class CompositionTest {
    @Test
    void innerErrorBecomesOuterError() {
        Mono<String> combined = Mono.just("order-7")
                .flatMap(order -> Mono.<String>error(
                        new IllegalStateException("stock unavailable")));

        StepVerifier.create(combined)
                .expectErrorMatches(error ->
                        error instanceof IllegalStateException
                        && error.getMessage().equals("stock unavailable"))
                .verify();
    }

    @Test
    void cancellingOuterCancelsInner() {
        AtomicBoolean innerCancelled = new AtomicBoolean();

        Mono<String> combined = Mono.just("order-7")
                .flatMap(order -> Mono.<String>never()
                        .doOnCancel(() -> innerCancelled.set(true)));

        StepVerifier.create(combined)
                .thenCancel()
                .verify();

        assertTrue(innerCancelled.get());
    }
}
```

This is a **test class for a project with `reactor-test` and JUnit Jupiter**, not included in the Maven demo in section 6 unless test dependencies/surefire are added. In the cancel test, `Mono.just` synchronously emits the order, and `flatMap` subscribes to `Mono.never` before `StepVerifier` requests cancellation, so the callback can be observed.

**Concurrency testing note:** when the inner actually runs on a scheduler or network, do not use `Thread.sleep` to “hope cancellation happens” and then assert. Use controllable publishers/sinks, `PublisherProbe`, virtual time, or proper synchronization. `PublisherProbe` is also helpful to confirm that a code path actually subscribed to or cancelled a composed publisher.

### Testing a Nested Subscription Can Pass Wrongly

```java
Mono<String> wrong = Mono.just("order-7")
        .doOnNext(order ->
                Mono.<String>error(
                        new IllegalStateException("stock unavailable"))
                    .subscribe(
                        value -> { },
                        error -> System.out.println("Detached: " + error)));

StepVerifier.create(wrong)
        .expectNext("order-7")
        .verifyComplete();
```

This snippet shows that **the parent can pass tests successfully** even while the child fails on its own. What tests must prove is the intended business semantics; if reserving stock must succeed before returning the order, a parent `verifyComplete()` like above **is not a valid test of the workflow**.

## 14. When Is “Fire-and-Forget” an Intentional Design?

Yes, when it is **an independent workflow with its own ownership and reliability**, rather than an unowned `subscribe()` call hidden inside a request's `map`/`doOnNext`.

For instance, a user submits a report-generation command and the server only needs to return HTTP 202 Accepted. The system can write the **job to a durable queue** inside an appropriate transaction, then return 202 after confirming durable enqueueing. A lifecycle-managed background worker consumes the job; the client disconnecting after 202 does not lose the job.

Conceptual design:

```text
HTTP request → validate → persist job / enqueue durably → 202 + jobId
                                                    |
                                          Background worker
                                                    |
                                       process + retry + audit
```

If a component truly subscribes proactively outside a request, it must have:

1. **A lifecycle owner**: application start/stop or a scheduler/job manager.
2. **A `Disposable` handle or subscription management**: a way to stop on shutdown.
3. **An explicit error handler**: logging/metrics/dead-letter or recovery strategy.
4. **Concurrency/resource limits**: not creating unbounded work per request.
5. **Durability or accepted loss**: does a reboot lose the work?
6. **Idempotency and bounded retries**: avoiding duplicate emails/charges.
7. **Tracing/context established by the workflow itself**: not relying on thread-locals or the context of an already-ended request.

For tasks that must outlive a request, do not default to nested `subscribe()` as a strategy. Use a job management system or reliable message broker; if it is simply a request-dependent computation, compose and return the publisher.

## 15. Common Code Review Mistakes

### Mistake 1 — subscribe inside map or doOnNext

```java
// Wrong: creates a child task outside the parent's lifecycle.
return loadUser(id)
        .map(user -> {
            sendEmail(user).subscribe();
            return user;
        });
```

**Fix:**

```java
return loadUser(id)
        .flatMap(user -> sendEmail(user).thenReturn(user));
```

These are snippets. If sending email fails, the result will fail; if email should be optional, design recovery **inside the inner** and document that policy.

### Mistake 2 — subscribe inside flatMap without returning the Mono

```java
// Wrong: flatMap returns Mono.just(...) while the real child is detached.
return loadUser(id)
        .flatMap(user -> {
            updateAvatar(user).subscribe();
            return Mono.just(user);
        });
```

**Fix:** return `updateAvatar(user).thenReturn(user)` so the operator manages the work. The name `flatMap` alone cannot save you if the callback still calls `subscribe()` manually.

### Mistake 3 — using then when factory B already performs side effects eagerly

```java
// Can be wrong if updateB() executes its work eagerly when called.
Mono<Void> workflow = updateA().then(updateB());
```

**Fix:** reactive APIs should return cold/lazy publishers. If even publisher creation must be deferred, use `updateA().then(Mono.defer(() -> updateB()))`. `Mono.defer` does not by itself convert blocking I/O into non-blocking.

### Mistake 4 — adding onErrorResume to parent and assuming child is protected

```java
return loadOrder(id)
        .doOnNext(order -> reserve(order).subscribe())
        .onErrorResume(error -> fallbackOrder());
```

**Fix:** compose `reserve` with `flatMap` first, then place recovery according to error type and needed position. The parent cannot automatically catch errors from an independent child subscription.

### Mistake 5 — unbounded child creation from a fast Flux

```java
return source.doOnNext(item ->
        remoteRequest(item).subscribe());
```

Each item opens a new inner subscription, which can spike connections/CPU. **Fix:** `flatMap(item -> remoteRequest(item), concurrency)` or `concatMap` if sequential execution is needed.

### Mistake 6 — calling subscribe inside a WebFlux controller and returning Mono.empty

```java
@PostMapping("/tasks")
public Mono<Void> wrong() {
    processTask().subscribe();
    return Mono.empty();
}
```

The parent response can complete immediately even though the task is not finished; task errors/cancellations are outside the HTTP workflow. **Fix:** if the task must complete before responding, `return processTask();`. If an independent job must run after HTTP 202, design a job/queue with genuine ownership.

### Mistake 7 — not disposing Disposable created by manual subscribe

```java
Disposable child = eventStream.subscribe(event -> handle(event));
```

If subscribing is valid at an application boundary, **retain the `Disposable` and dispose it on stop**; also include an error consumer and source bounds. If this subscription was created inside a request as part of the response, replace it with composition.

### Mistake 8 — thinking cancel means rollback

Once a request is sent to a payment provider, cancelling the subscription does not guarantee reversal. **Fix:** idempotency keys, transaction state, durable queues, reconciliation, and business-appropriate compensation.

### Mistake 9 — treating parent doFinally as cleanup for an unowned child

If the child is an independent subscription, the parent's `doFinally` does not guarantee closing the child. **Fix:** compose the inner or manage the child handle with clear ownership. For subscription-scoped resources, use `using`/`usingWhen`.

### Mistake 10 — tests checking only the parent result

`StepVerifier.create(parent).verifyComplete()` can pass when the parent ignores child errors. **Fix:** test error propagation and cancellation to the inner, using `PublisherProbe` if helpful to verify lifecycle.

### Mistake 11 — lost trace/auth/transaction context

A new `subscribe()` creates a new subscriber and context. **Fix:** compose so the framework propagates context to the inner; if an independent workflow is genuinely required, establish explicit security/tracing context and do not retain expired request data.

### Mistake 12 — “all errors in async callbacks automatically flow into parent”

Callbacks outside a Publisher can throw exceptions on another thread outside the signal chain; the parent's `onErrorResume` will not see them. **Fix:** wrap callback APIs using `Mono.create`/`Flux.create`/`Sinks` per contract, managing disposal and error signals; do not call `subscribe` as a patch.

## 16. Option Selection Checklist

When reviewing code containing a `subscribe()` call, answer in order:

1. **Who is the final subscriber?** WebFlux, a test, CLI, or a workflow-managing component? If the framework already subscribes, why is another subscriber needed?
2. **Must the child task succeed before the parent completes?** If yes, compose with `flatMap`/`then`.
3. **Should the child emit multiple items?** If yes, consider `flatMapMany` or `Flux.flatMap`, `concatMap`.
4. **Must child errors affect the request?** If yes, do not detach the subscription.
5. **If the client cancels, must the child work stop?** If yes, keep the child in the chain and verify driver cancellation support.
6. **How many concurrent children can exist?** Are concurrency, queues, connections, and demand bounded?
7. **Who closes resources?** Are there `usingWhen`, cleanup on cancel/error/complete, and leak tests?
8. **Are there retries/timeouts?** Where are operators placed, and is the child within retry/timeout scope?
9. **Is Reactor Context/tracing/security involved?** If yes, a new subscription can sever context.
10. **If intentionally fire-and-forget, does the job have a real owner?** Does it have error handling, shutdown, durability, and idempotency?
11. **Do tests verify inner errors and inner cancellation?** Not only the parent response.
12. **Are there un-rollbackable side effects?** If yes, cancel is only a signal, so design compensation.

## 17. Practice Exercises

**Exercise 1 — Spot the bug:**

```java
Mono<String> bad = Mono.just("A")
        .doOnNext(v ->
                Mono.<String>error(
                        new IllegalArgumentException("child"))
                        .subscribe())
        .onErrorReturn("fallback");
```

Question: does `bad` return `fallback`?

**Answer:** Not from the child error alone. The parent's `onErrorReturn` does not receive the independent child error. Without an error consumer, an unhandled child subscriber error will be raised.

**Exercise 2 — Fix the chain:**

Requirement: load the user, record audit successfully, then return the user. If auditing fails, the entire workflow fails.

```java
Mono<User> correct = loadUser(id)
        .flatMap(user ->
                auditService.record(user).thenReturn(user));
```

This is a snippet. `record` returns `Mono<Void>`. Because the inner is composed, errors/cancellation are part of the parent. Do not use `doOnNext(user -> auditService.record(user).subscribe())`.

**Exercise 3 — Cancellation:**

`Flux.just(1).concatWith(Flux.never())` is active, and inside `doOnNext` it manually subscribed to `Mono.never`. Does cancelling outer cancel child?

**Answer:** Not automatically. The child has an independent subscription; you must hold a handle to cancel it, or compose the child with `flatMap`.

**Exercise 4 — Retry:**

If `source.doOnNext(v -> remote(v).subscribe()).retry(2)`, each attempt can spawn additional children when item `v` is emitted. `retry` knows nothing about detached children, risking duplicate or parallel side effects. **Fix:** compose `remote` into `source` before `retry`, classify errors, and design idempotency.

**Exercise 5 — Resource cleanup:**

A source holds a reactive DB connection requiring async cleanup on complete/error/cancel. Is using `doOnNext` to open the connection and `subscribe()` to close it right?

**Answer:** Not recommended. Use publisher-scoped resource management (`usingWhen`/appropriate transaction operator) so cleanup belongs to the same lifecycle; test both cancellation and cleanup errors.

**Exercise 6 — A task that must survive client disconnect:**

A client requests a 20-minute report export. Should you call `reportService.generate().subscribe()` in the controller and return HTTP 202 immediately?

**Answer:** Not a reliable pattern if the subscription is not managed by a job manager; the request no longer owns cancellation/errors, and process restarts can lose the work. Persist the job durably or use an independent job management tool, return a job ID, and provide status/result retrieval endpoints.

**Final takeaway:** In reactive programming, **a subscription is an ownership boundary**. `subscribe()` starts a new lifecycle stream. If inner work must contribute to the parent's outcome, **return the child publisher to a composition operator** rather than calling `subscribe` and discarding it. Doing so preserves error, cancellation, demand, context, and resource-management links; whereas a genuinely independent workflow must have its own owner and contract.

## References

- Project Reactor — [Reference: Nothing Happens Until You subscribe()](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html) and [Reactive Programming: Asynchronicity](https://projectreactor.io/docs/core/release/reference/reactiveProgramming.html).
- Project Reactor — [Mono API: flatMap, then, doFinally, usingWhen](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html).
- Project Reactor — [Flux API: flatMap, concatMap, flatMapSequential](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html).
- Project Reactor — [Handling Errors: onErrorResume, onErrorMap](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html).
- Project Reactor — [Using Resources and the Finally Block](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html#_using_resources_and_the_finally_block).
- Project Reactor — [Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html).
- Spring Framework — [WebFlux annotated controllers](https://docs.spring.io/spring-framework/reference/web/webflux/controller.html).
- Spring Framework — [Reactive transaction management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html).
