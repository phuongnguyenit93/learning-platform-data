# Spring AOP with Publisher-Returning Methods: Execution Timing and Reactive State

## Objectives

When a Spring bean has a method returning a Reactor `Mono`/`Flux` or a Reactive Streams `Publisher`, you must distinguish **the method call passing through the Spring AOP proxy** from **subscribing to the Publisher returned by the method**. These two moments can be separated by a long interval, occur on different threads, or never reach subscription at all. Consequently, advice that measures duration, logs errors, or manages state simply by placing statements before/after `ProceedingJoinPoint.proceed()` usually cannot observe the entire asynchronous work.

After this lesson, you will be able to identify which advice runs when the Publisher is returned, place instrumentation into the proper subscription lifecycle, store state safely across multiple concurrent subscribers, and test outcomes upon completion, error, or cancellation.

## 1. Spring AOP Proxy Boundary and the Reactive Pipeline

In proxy mode, Spring AOP intercepts **method executions** invoked through a Spring-managed bean proxy. A method returning `Mono`/`Flux` is still a normal Java method execution: the call goes through the proxy, enters the advice, reaches the method body, and returns a `Publisher` object.

Example:

~~~java
@Service
class BookService {
    public Mono<String> findTitle() {
        System.out.println("method body: build Mono");
        return Mono.fromSupplier(() -> {
            System.out.println("deferred work");
            return "Spring AOP";
        });
    }
}
~~~

Suppose a client receives the bean via a Spring proxy and calls:

~~~java
Mono<String> result = bookService.findTitle(); // proxy/advice runs here
// ... time passes, not subscribed yet ...
String title = result.block();                  // subscribe here
~~~

- When `findTitle()` is called: the method body runs and constructs the `Mono`; any regular advice logic wrapping the call also executes. `"method body: build Mono"` is printed immediately.
- When `block()` or `subscribe()` is called: `Mono.fromSupplier` finally executes the supplier and prints `"deferred work"`. Spring AOP **does not automatically intercept a second time** at this point.
- If nobody subscribes, the deferred work never runs. However, *eager* side effects placed directly in the method body or advice have already happened.
- If two subscribers subscribe to a cold `Publisher`, upstream work may run twice; **advice at the method boundary** still runs only once if the method was called only once.
- If the method returns a hot/eager `Publisher`, or uses `cache`/`share`, upstream work and sharing behavior can differ. Do not assume every `Publisher` is lazy, cold, or replays per subscriber.

Typical timeline model:

~~~text
T0  caller -> Spring proxy -> @Around.enter
T1  @Around -> proceed() -> target creates Publisher -> returns Publisher
T2  @Around.exit -> caller receives Publisher
    ... no subscription yet; may switch threads ...
T3  subscriber subscribes to Publisher
T4  upstream processes and emits onNext (0..n), onError, or onComplete
T5  subscription may end via cancel before terminal signal
~~~

T0–T2 measures **method invocation / pipeline assembly time**. T3–T5 is the **subscription lifecycle / stream execution**. For asynchronous operations, T2 does not mean the query finished, the connection was released, or the response was sent.

## 2. What Does Each Spring Advice See?

| Spring AOP component | When does it run for a Publisher-returning method? | Do not misunderstand |
| --- | --- | --- |
| `@Before` | Before the target method call, when going through the proxy | Not a callback before each subscription |
| `@AfterReturning` | When the method returns normally; the return value is typically the `Mono`/`Flux`/`Publisher` object | Not `onNext` data or the `onComplete` event |
| `@AfterThrowing` | When the proxied method execution itself throws synchronously | Does not automatically receive late `onError` emitted by the `Publisher` |
| `@After` | When the proxied method execution exits, including when throwing | Does not wait for pipeline completion/cancellation |
| `@Around` | Wraps `proceed()` and can replace the returned `Publisher` with one decorated with operators | Only code running in the advice is synchronous; operators inside the `Publisher` have their own lifecycle |

The example below logs only the method invocation duration (useful for measuring pipeline assembly cost, **not** reactive latency):

~~~java
@Around("execution(reactor.core.publisher.Mono demo.BookService.*(..))")
public Object assemblyTime(ProceedingJoinPoint pjp) throws Throwable {
    long start = System.nanoTime();
    try {
        return pjp.proceed();
    } finally {
        long nanos = System.nanoTime() - start;
        System.out.println("method/assembly ns = " + nanos);
    }
}
~~~

If a `Mono` is returned successfully and later emits `onError`, `@AfterReturning` for the method call may still have run. The two facts do not contradict each other: one is the *normal return of a Java method*, and the other is the *terminal signal of a reactive sequence*. Similarly, `catch (Throwable)` around `proceed()` catches only errors thrown immediately during the method call, not errors emitted by `supplier`, `map`, `flatMap`, or I/O at subscription time.

## 3. Writing `@Around` to Observe Subscriptions

When the goal is counting subscriptions, measuring actual processing duration, and recording terminal states, the advice needs to **return a `Publisher` decorated with Reactor operators**.

A pattern for methods declared to return `Mono`:

~~~java
@Around("execution(reactor.core.publisher.Mono demo.BookService.*(..))")
public Object observeMono(ProceedingJoinPoint pjp) throws Throwable {
    Object returned = pjp.proceed(); // invoke target at method invocation time
    if (!(returned instanceof Mono<?> source)) {
        return returned; // return type contract must be preserved
    }

    String operation = pjp.getSignature().toShortString();

    return Mono.defer(() -> {
        long start = System.nanoTime(); // each subscription has its own state
        System.out.println("subscribed: " + operation);

        return source
            .doOnNext(value -> System.out.println("onNext: " + operation))
            .doOnError(error -> System.out.println(
                "onError: " + operation + ", " + error.getClass().getSimpleName()))
            .doFinally(signal -> {
                long elapsedNs = System.nanoTime() - start;
                System.out.println("terminal: " + operation + ", "
                    + signal + ", elapsedNs=" + elapsedNs);
            });
    });
}
~~~

Points to read carefully:

1. `proceed()` is still called when the Spring proxy receives the call, so the method body is not unintentionally postponed to another time.
2. `Mono.defer` creates a fresh `start` for **each subscription**. Never store `start` in a mutable field of a singleton `@Aspect` or a variable shared across subscribers.
3. `doOnNext` observes items; an empty `Mono` can complete without emitting `onNext`. `doOnSuccess` (if used) has its own convention for an empty `Mono`: the callback may receive `null`.
4. `doOnError` observes error signals from upstream. When upstream emits `onError`, `doFinally` receives `ON_ERROR`; success receives `ON_COMPLETE`; cancellation receives `CANCEL`.
5. `doFinally` is useful for metrics and cleanup because it includes cancellation. A `doFinally` callback is a side effect and should not be relied on to alter the `Publisher`'s value or guarantee strict log ordering relative to a thread waiting on `block()`.
6. The advice must return a type compatible with the method signature. Do not return a `Flux` for a method declared to return `Mono`; do not coerce every `Publisher` to `Mono` (which loses multi-item semantics).

Special case: if `proceed()` throws `Throwable` **immediately at method invocation time**, the advice block above has not yet created a wrapper; that is a synchronous error, which should still follow Spring's synchronous error path or be observed separately via `try/catch` around `proceed()`. Do not silently turn every synchronous error into `onError` unless intentionally changing the API contract.

### Variant with Flux

For methods declared to return `Flux`, use `Flux.defer` and the operators with the same semantics:

~~~java
@Around("execution(reactor.core.publisher.Flux demo.StreamService.*(..))")
public Object observeFlux(ProceedingJoinPoint pjp) throws Throwable {
    Flux<?> source = (Flux<?>) pjp.proceed();
    String operation = pjp.getSignature().toShortString();

    return Flux.defer(() -> {
        long start = System.nanoTime();
        return source
            .doOnSubscribe(s -> System.out.println("subscribe " + operation))
            .doOnError(e -> System.out.println("error " + operation))
            .doFinally(signal -> System.out.println(
                operation + ": " + signal + " after "
                + (System.nanoTime() - start) + " ns"));
    });
}
~~~

For signatures returning `org.reactivestreams.Publisher<T>`, `Flux.from(source)` may be used **when compatible with the contract**. Separately consider returned `Mono`, `Flux`, custom publishers, empty/null (in reactive APIs `null` should generally be avoided), multi-item semantics, backpressure, and preserving identity/behavior; do not apply an unsafe `Mono`/`Flux` cast to every endpoint.

## 4. Runnable Example: Spring Proxy + Mono Returned Before Work Runs

The following standalone example uses Java 17, Spring Framework 6.1, Reactor Core, and `@AspectJ`-style Spring AOP (Spring proxies, no AspectJ weaving required). Structure:

~~~text
reactive-aop-demo/
├── pom.xml
└── src/main/java/demo/App.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>reactive-aop-demo</artifactId>
    <version>1.0.0</version>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.15</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.1.15</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.22.1</version>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.6.12</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration><release>17</release></configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration><mainClass>demo.App</mainClass></configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/App.java**

~~~java
package demo;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Configuration
@ComponentScan("demo")
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class App {
    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(App.class)) {
            GreetingService service = context.getBean(GreetingService.class);

            System.out.println("A. call through proxy");
            Mono<String> mono = service.greet("Ada");
            System.out.println("B. method returned");
            String value = mono.block();
            System.out.println("C. value = " + value);
        }
    }
}

@Component
class GreetingService {
    public Mono<String> greet(String name) {
        System.out.println("target: build Mono");
        return Mono.fromSupplier(() -> {
            System.out.println("source: compute");
            return "Hello " + name;
        });
    }
}

@Aspect
@Component
class ReactiveObservationAspect {
    @Around("execution(reactor.core.publisher.Mono demo.GreetingService.greet(..))")
    public Object observe(ProceedingJoinPoint pjp) throws Throwable {
        System.out.println("advice: enter");
        Mono<?> source = (Mono<?>) pjp.proceed();
        System.out.println("advice: wrap Publisher");

        return Mono.defer(() -> {
            System.out.println("pipeline: subscribe");
            return source
                .doOnNext(value -> System.out.println("pipeline: onNext"))
                .doOnError(error -> System.out.println("pipeline: onError"))
                .doFinally(signal ->
                    System.out.println("pipeline: finally " + signal));
        });
    }
}
~~~

In the project directory, run:

~~~bash
mvn -q compile exec:java
~~~

The meaningful ordered portion of the output (ignoring any library startup logs) is:

~~~text
A. call through proxy
advice: enter
target: build Mono
advice: wrap Publisher
B. method returned
pipeline: subscribe
source: compute
pipeline: onNext
~~~

`"C. value = Hello Ada"` appears after `block()` retrieves the value. The `"pipeline: finally onComplete"` callback also runs when the sequence ends, though you should not rely on the exact ordering of that log line relative to line C across all scheduling/threading arrangements. If you replace `block()` by merely holding the `mono` variable, only logs up to `"B. method returned"` appear, because the `Mono` from the supplier has no subscriber yet.

This example intentionally measures subscription timing via `Mono.defer`. It does not call `subscribe()` inside the advice: subscribing belongs to downstream (such as the WebFlux layer), which controls demand, error handling, and cancellation.

## 5. State and Concurrency: One Call, Multiple Subscriptions

Suppose:

~~~java
Mono<String> onePublisher = service.greet("Ada");
Mono<String> first = onePublisher;
Mono<String> second = onePublisher;
~~~

When declaring `onePublisher`, the Spring proxy runs **once**. If `first` and `second` are subscribed independently, `Mono.defer` in the wrapper runs **twice**, each with its own `start`. For a cold publisher from a supplier, the work can run twice; for a cached/hot publisher, upstream execution counts may differ. Advice state should reflect the exact quantity being measured:

| Quantity | Proper place to count | Meaning |
| --- | --- | --- |
| Number of times the bean method was called through the proxy | Body of `@Before`/`@Around` before `proceed()` | Invocation count |
| Cost of creating/returning the Publisher | Before and after `proceed()` | Assembly time |
| Number of subscriptions to the returned Publisher | `Mono.defer`/`Flux.defer` or appropriate `doOnSubscribe` | Subscription count |
| Duration a subscription stays active | Start per subscription, end in `doFinally` | Subscription duration |
| Number of `onNext`/`onError`/`onComplete`/`cancel` | Corresponding Reactor operators | Reactive signal count |

In concurrent systems, an `@Aspect` is usually a Spring singleton. A field like `"long startNanos"` on an `@Aspect` is overwritten across concurrent invocations and subscribers; use an invocation local variable when measuring assembly and a local variable **inside `defer`** when measuring subscriptions. When writing counters/metrics, use thread-safe mechanisms (`LongAdder`, `AtomicLong`, metrics recorders); never update a plain `HashMap` from multiple concurrent callbacks.

Reactive flows can switch threads due to schedulers or I/O callbacks. `ThreadLocal` and MDC set in `@Around` when the method is called **are not automatically present** in `onNext`/`onError` on another thread. When correlation ID or request context is needed, prefer `Reactor Context` and configured context propagation mechanisms in the Spring ecosystem, rather than assuming `ThreadLocal` propagates automatically:

~~~java
return Mono.deferContextual(context -> {
    String requestId = context.getOrDefault("requestId", "unknown");
    return source.doOnError(error ->
        logger.warn("requestId={} failed", requestId, error));
});
~~~

The code above illustrates retrieving per-subscriber context; `logger` and `source` are existing variables in the corresponding method/advice. Reading context via `ThreadLocal` only at assembly time and holding it as global state easily tags the wrong request under concurrent subscriptions. If the application uses a `Reactor Context ↔ MDC` bridge, check the application's actual context propagation policy.

## 6. Completion, Errors, Cancellation, and Timing Semantics

In reactive flows, "method returns" differs from the subsequent signals:

- `onNext` carries data (`Mono` at most one item, `Flux` potentially many items).
- `onComplete` confirms the `Publisher` finished normally; an empty `Mono` still emits `onComplete`.
- `onError` terminates the stream with an error; Spring AOP's `@AfterThrowing` for returning the `Publisher` does not replace `doOnError`.
- `cancel` is a downstream action requesting subscription cancellation; upstream may be processing resources/tasks, and cancelling does not mean every external task stops instantaneously.

Timing a WebFlux request with a clock started before `proceed()` and stopped right after `proceed()` usually measures only pipeline creation. Using `defer` + `doFinally` measures each subscription's duration, including waiting for data once subscription actually starts. Choose a clear latency definition: **from method invocation**, **from subscribe**, **to first element**, or **to terminal**. These are distinct metrics; metric names must not conflate them.

The `doFinally` operator is the right place to observe `ON_COMPLETE`, `ON_ERROR`, and `CANCEL`; for real resources, use resource-management APIs with proper reactive semantics (such as `usingWhen`) instead of relying on `finally` in the Publisher-creating method. Placing `doOnError` near upstream only records errors without handling/recovering them; if the pipeline has `onErrorResume` downstream, the final outcome of the whole chain may be success. Operator placement in the chain affects what gets observed.

For non-terminating `Flux` streams (long-lived streams, SSE), duration to terminal can be very long or end only on `cancel`; add a "time to first signal" metric when that reflects the real need. If a publisher never gets subscribed to, subscription metrics are not produced, while invocation metrics are still recorded.

## 7. Spring-Managed Transaction Advice and Reactor Context

An important case in Spring is `@Transactional`. Spring uses `TransactionInterceptor` based on AOP proxies. With **`ReactiveTransactionManager`** and a method returning a suitable reactive type, Spring uses the reactive transaction branch; transaction context is propagated via **`Reactor Context`** attached to the reactive pipeline, rather than relying on `PlatformTransactionManager`'s thread-bound transaction.

Therefore:

- Do not conclude a transaction committed merely because `@AfterReturning` observed the method returning a `Mono` normally.
- Do not read transaction state via an arbitrary `ThreadLocal` inside a reactive callback and assume it stays valid across schedulers.
- Do not manually open/close a transaction around `proceed()` assuming it automatically covers the whole pipeline; database work can execute after `proceed()` returns.
- When combining multiple aspects (metrics, authorization, transactional advice), check advisor ordering/`@Order` and operator placement, because each interceptor's wrapper layer affects where signals are observed.
- Exact transaction rules also depend on the configured transaction manager, return type, and how the pipeline is subscribed to. Do not treat every `@Transactional` on a `Mono` as a reactive transaction if the app only has an imperative manager.

This section only explains consequences at the Spring AOP boundary; transaction configuration and reactive data design belong to dedicated transaction/WebFlux lessons.

## 8. Common Pitfalls and How to Fix Them

| Flawed practice | Consequence | Fix in Spring AOP |
| --- | --- | --- |
| Logging "request success" in `@AfterReturning` when receiving `Mono` | Reports success before the pipeline may emit `onError` | Distinguish "Publisher returned" from `doOnComplete`/`doOnError` |
| Using `try/catch` around `proceed()` to catch all async errors | Misses `onError` emitted upon subscription | Observe `doOnError` on the `Publisher`; catch synchronous errors separately |
| Putting mutable `startTime` in an `@Aspect` field | Race across concurrent requests/subscribers | Local per invocation or local inside each `defer` |
| Calling `block()`/`subscribe()` inside advice | Hijacks WebFlux execution, adds extra subscription, may block event loop | Return decorated `Publisher`; let downstream subscribe |
| Calling `proceed()` inside `Mono.defer` callback unintentionally | Shifts method execution and advice chain to subscription; may run multiple times | Normally call `proceed()` at invocation, defer only reactive callbacks |
| Returning `Flux` from advice for a method declared as `Mono` | Breaks return contract, potential `ClassCastException` | Preserve matching `Mono`/`Flux` types |
| Assuming every publisher is cold | Mismeasures side effects, duplicate work, and timing | Know whether the source publisher is cold/hot/cached/shared |
| Relying on MDC/`ThreadLocal` across schedulers | Wrong request ID or lost context | `Reactor Context` and configured propagation |
| Using `@After` to release async resources | Closes before subscriber finishes using them | Manage resources using the reactive lifecycle |
| Calling `this.otherMethod()` internally expecting advice to run | Self-invocation bypasses Spring proxy | Call via a valid bean proxy or reorganize bean boundaries |
| Target is a `final` class/`final` method with class-based proxy | Proxy cannot advise the method as expected | Use appropriate bean/proxy style, check proxying constraints |

## 9. Testing Checklist

Testing the true Spring AOP boundary requires **retrieving beans from the Spring context**, not instantiating the target with `new`. Test at least these scenarios:

1. **Unsubscribed:** call the method, confirm invocation advice ran; deferred supplier and subscription observer have not run.
2. **Subscribed once:** confirm upstream emits values and the observer sees signals; errors are not turned into successes.
3. **Subscribed twice to the same Publisher:** invocation advice runs once, subscription observer runs twice; compare against the source's cold/hot/cached semantics.
4. **Synchronous error:** method throws immediately before returning `Publisher`; observe synchronous failure via Spring advice.
5. **Reactive error:** method returns `Mono.error(...)` normally; receives `onError` in the pipeline while `@AfterThrowing` is not triggered by this terminal error alone.
6. **`Mono.empty()`:** no `onNext`, yet `complete` occurs; duration timer still stops.
7. **Cancellation:** subscription is disposed/cancelled; `doFinally` receives `CANCEL` when cancellation passes through that operator.
8. **Concurrency:** multiple subscriptions across schedulers without sharing timestamps or corrupting request IDs.
9. **Proxy boundary:** call from an external bean through the Spring proxy; compare with self-invocation if diagnosing why advice did not trigger.

With Reactor Test, you can use `StepVerifier` to assert completion/error/cancel and use `AtomicInteger`/`LongAdder` to count invocations, subscriptions, and terminal signals. Avoid asserting exact log ordering or exact nanosecond timings; synchronize via reactive signals and observable test conditions.

## Key Takeaways

**Spring AOP intercepts the method call that returns a `Publisher`; Reactive Streams governs work per subscription and signal.** For lazy `Mono`/`Flux`, a Spring advice seeing a returned object does not mean upstream work has completed. To observe actual progress, attach Reactor operators to the returned `Publisher`, manage state per subscription, and strictly separate synchronous method errors from asynchronous pipeline `onError` signals.

Official documentation:
- Spring Framework — Declaring Advice: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html
- Spring Framework — TransactionInterceptor and reactive transactions: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Reactor — Error handling and `doFinally`: https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html
