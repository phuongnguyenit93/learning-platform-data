# Deferring Computation with defer, fromSupplier, and fromCallable

## 1. Why Defer Computation When Creating a Reactive Source?

In Project Reactor, an expression creating a Mono or Flux usually only **describes a pipeline**. Creating the Publisher object, subscribing (subscribe), and executing a task happen at different points in time. If you call a time-consuming method **before** passing its result into a Publisher, the work has already occurred right when assembling the pipeline; wrapping the result with Mono cannot undo that.

Example:

~~~java
String value = loadData();       // loadData() runs right here.
Mono<String> mono = Mono.just(value); // Mono holds the existing value.
~~~

Shortening it to Mono.just(loadData()) still causes loadData() to run **right when the Java expression is evaluated**, before any subscriber appears.

Three important factories for creating *lazy* sources:

- **Mono.defer(...)**: each subscription asks the factory to **create and return another Mono**; Reactor subscribes to the newly created Mono.
- **Mono.fromSupplier(...)**: each subscription executes Supplier.get() to produce **one value T**, or completes empty if the value is null.
- **Mono.fromCallable(...)**: each subscription executes Callable.call() to produce **one value T**, or completes empty if null; Callable also allows throwing **checked exceptions**.

All three create Publishers that are typically used in a **cold** manner, meaning each independent subscription re-triggers the work that supplies data. **Lazy does not automatically mean asynchronous, multi-threaded, or non-blocking.** This is a critical boundary when using them with Spring WebFlux.

## 2. Three Points in Time to Distinguish

~~~text
T0: Assembly
    Create Mono, assemble map/filter/flatMap...; there may be no Subscriber yet.
                  |
                  v
T1: Subscription
    A subscriber arrives; a cold source prepares the work for that subscription.
                  |
                  v
T2: Signal
    Emit onNext(value), onComplete(), or onError(error).
~~~

In small examples with synchronous data, T1 and T2 can be very close together and happen **on the thread calling subscribe()/block()**. With sources that have schedulers, network I/O, hot sources, or demand/cancellation, actual timing and threads can differ. Saying “the factory runs on subscription” describes the semantics, not a guarantee that the callback always runs at the exact source code line calling subscribe() or that all behavior runs synchronously.

Comparison table:

| Creation Method | Factory Argument | When Is the Value Fetched / Source Chosen? | When to Use? |
| --- | --- | --- | --- |
| **Mono.just(value)** | An existing value T, null not accepted | Value is evaluated before/at assembly | Already have a stable value, want to replay that value |
| **Mono.justOrEmpty(value)** | An already-evaluated value T/Optional | Similar to just, but allows null/empty | Already have an optional value; no need to defer computation |
| **Mono.fromSupplier(supplier)** | Supplier<T> returning T | When the source is subscribed and has suitable demand | Synchronous computation without needing to declare checked exceptions |
| **Mono.fromCallable(callable)** | Callable<T> returning T, may throw Exception | When the source is subscribed and has suitable demand | Calling functions with checked exceptions; wrapping synchronous I/O APIs |
| **Mono.defer(factory)** | Supplier<? extends Mono<? extends T>> returning Mono | On subscribe, chooses/creates a **Publisher** to subscribe to next | Choosing a pipeline branch based on state at subscription time, creating a new source per subscription |

These are methods on **Mono**. Flux also has **Flux.defer** to defer choosing/creating a multi-element Publisher. Do not infer that Flux has the same fromSupplier/fromCallable methods with Mono's signatures.

## 3. Mono.fromSupplier: Deferring a Computation Returning T

Signature meaning:

~~~java
static <T> Mono<T> fromSupplier(Supplier<? extends T> supplier)
~~~

**java.util.function.Supplier<T>** supplies T via get() and does not declare checked exceptions. When the subscription needs a value, Reactor calls the Supplier and emits the result.

~~~java
AtomicInteger version = new AtomicInteger();

Mono<String> currentValue =
        Mono.fromSupplier(() -> "version-" + version.incrementAndGet());

// version has not been incremented yet here.
String a = currentValue.block(); // version-1
String b = currentValue.block(); // version-2
~~~

Here, the two **block() calls are two separate subscriptions**. We receive two different values because the Supplier is invoked again; this is not a mandatory property of all data: if the Supplier only returns a constant, two subscribers can still receive the same value.

**Supplier returns null**: Mono.fromSupplier completes **empty (onComplete, no onNext)**. It does not emit null via onNext because Reactor does not allow emitting null elements. You can handle this with defaultIfEmpty or switchIfEmpty when needed.

~~~java
Mono<String> missing = Mono.fromSupplier(() -> null);
Mono<String> result = missing.defaultIfEmpty("unknown");
// result emits "unknown".
~~~

**Supplier throws RuntimeException**: Reactor turns the error into an onError for the subscription, so error-handling operators like onErrorResume see it. Supplier<T> does not declare throws IOException; if the underlying API throws checked exceptions, use fromCallable for clarity.

**Avoid doing work outside the lambda**:

~~~java
// Defeats the lazy goal: the expensive function already ran before creating the Mono.
String cached = expensiveLookup();
Mono<String> eager = Mono.fromSupplier(() -> cached);

// Proper lazy: the call is inside the lambda and runs on subscription.
Mono<String> lazy = Mono.fromSupplier(() -> expensiveLookup());
~~~

These two snippets are **illustrative examples**, assuming a method expensiveLookup() returning String exists; they are not standalone Java classes.

## 4. Mono.fromCallable: Deferring Computation That May Throw Checked Exceptions

Signature meaning:

~~~java
static <T> Mono<T> fromCallable(Callable<? extends T> callable)
~~~

**java.util.concurrent.Callable<T>** has a call() method declaring throws Exception. Because of that, Java APIs like reading files, synchronous queries, or calling legacy libraries with checked exceptions can be brought into the pipeline without wrapping them into RuntimeException directly inside the lambda.

~~~java
import java.io.IOException;
import reactor.core.publisher.Mono;

Mono<String> value = Mono.fromCallable(() -> {
    if (externalServiceUnavailable()) {
        throw new IOException("Service unavailable");
    }
    return "ok";
});

Mono<String> recovered =
        value.onErrorResume(IOException.class, error -> Mono.just("fallback"));
~~~

This is an illustrative snippet: externalServiceUnavailable() is not defined. Note that **IOException occurs during subscription** and becomes an onError signal; calling Mono.fromCallable(...) to assemble the pipeline does not run that lambda body.

Outcome cases:

| Callable.call() | Mono Signal |
| --- | --- |
| Returns non-null T | onNext(T) then onComplete() |
| Returns null | onComplete() emitting no value |
| Throws Exception | onError(exception) |
| Not subscribed yet | Callable not called yet because only the source was created |

**fromCallable does not automatically turn a blocking function into non-blocking.** If call() waits on the filesystem, JDBC, or a synchronous HTTP client, the thread executing call() is still occupied while waiting. A scheduler must be chosen separately when used in an event-loop runtime like WebFlux.

## 5. Mono.defer: Deferring **Creating/Choosing a Publisher**

Signature meaning:

~~~java
static <T> Mono<T> defer(Supplier<? extends Mono<? extends T>> factory)
~~~

Unlike fromSupplier/fromCallable, the argument to defer **must return a Mono**, not just T.

~~~java
AtomicBoolean usePrimary = new AtomicBoolean(true);

Mono<String> selected = Mono.defer(() ->
        usePrimary.get()
                ? Mono.just("primary")
                : Mono.just("secondary")
);

String first = selected.block(); // primary
usePrimary.set(false);
String second = selected.block(); // secondary
~~~

It is the same selected object, yet **each subscription re-evaluates the choice**. If you write:

~~~java
Mono<String> selectedEager =
        usePrimary.get() ? Mono.just("primary") : Mono.just("secondary");
~~~

then the branch is chosen **at assembly time**, because the Java conditional operator runs before the Mono is subscribed to. Changing usePrimary afterward does not change the contents of the already-created Mono.

Suitable use cases for defer:

- Choosing one of several Publishers based on configuration or current state when a subscriber arrives.
- Creating a Publisher whose parameters, resources, or side effects of **initializing the Publisher** need to be postponed until subscription.
- Wrapping a fallback branch in switchIfEmpty to avoid calling the function that **builds the fallback** too early.
- Choosing between Mono.empty(), Mono.error(...), or a data Mono based on per-subscription logic.
- Using **Mono.deferContextual** when you need each subscriber's own Reactor Context, rather than only reading global state.

Do not overuse defer if you only want to call a function returning T at subscribe time. Mono.fromSupplier(() -> getValue()) or Mono.fromCallable(() -> getValue()) is usually simpler than Mono.defer(() -> Mono.just(getValue())).

**Returning null instead of a Mono** is invalid: the defer factory must return a valid Publisher/Mono; if it returns null, the subscription will terminate with a NullPointerException error. This **differs from** a Supplier/Callable returning null in fromSupplier/fromCallable, which is represented as an empty Mono.

## 6. Visual Comparison with Mono.just

~~~text
Mono.just(load())                Mono.fromSupplier(() -> load())
     |                                         |
     | -- load() immediately at assembly       | -- assembly only holds Supplier
     v                                         v
  value T                                   subscribe
     |                                         |
   subscribe                                 load()
     |                                         |
     v                                         v
   emit T                                    emit T

Mono.defer(() -> createMono())
     |
     | -- assembly only holds factory returning Mono
     v
   subscribe
     |
   createMono() -> concrete Mono
     |
  subscribe concrete Mono -> emit signals
~~~

A helpful note: **defer defers creating the inner Mono**, but sources inside the inner Mono still follow their own semantics. For example, Mono.defer(() -> Mono.just(expensive())) runs expensive() when the factory is called; Mono.defer(() -> Mono.fromCallable(this::readFile)) creates an inner Mono that is also lazy and only reads the file when it is subscribed to. Nesting multiple layers of laziness may be necessary to select a pipeline, but does not inherently bring extra benefits just from having more lambdas.

## 7. Runnable Java 17+ Example: Observing Exact Invocation Counts

This example isolates the three factories and compares them with Mono.just. It uses **Java 17+, Maven 3.9+**, and Project Reactor Core. Create:

~~~text
lazy-factory-demo/
├── pom.xml
└── src/main/java/example/LazyFactoriesDemo.java
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>lazy-factory-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.6.17</version>
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
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/example/LazyFactoriesDemo.java**:

~~~java
package example;

import java.io.IOException;
import java.util.concurrent.atomic.AtomicInteger;
import reactor.core.publisher.Mono;

public class LazyFactoriesDemo {
    private static String compute(String kind, AtomicInteger counter) {
        String value = kind + "#" + counter.incrementAndGet();
        System.out.println("compute " + value);
        return value;
    }

    public static void main(String[] args) {
        AtomicInteger justCalls = new AtomicInteger();
        AtomicInteger supplierCalls = new AtomicInteger();
        AtomicInteger callableCalls = new AtomicInteger();
        AtomicInteger deferCalls = new AtomicInteger();

        Mono<String> just = Mono.just(compute("just", justCalls));

        Mono<String> supplier =
                Mono.fromSupplier(() -> compute("supplier", supplierCalls));

        Mono<String> callable =
                Mono.fromCallable(() -> compute("callable", callableCalls));

        Mono<String> deferred = Mono.defer(() -> {
            System.out.println("build deferred Mono");
            return Mono.just(compute("defer", deferCalls));
        });

        System.out.println("assembled");

        System.out.println("just A=" + just.block());
        System.out.println("just B=" + just.block());
        System.out.println("supplier A=" + supplier.block());
        System.out.println("supplier B=" + supplier.block());
        System.out.println("callable A=" + callable.block());
        System.out.println("callable B=" + callable.block());
        System.out.println("defer A=" + deferred.block());
        System.out.println("defer B=" + deferred.block());

        Mono<String> recovered = Mono.<String>fromCallable(() -> {
            throw new IOException("disk unavailable");
        }).onErrorResume(IOException.class, error -> Mono.just("fallback"));

        Mono<String> missing = Mono.fromSupplier(() -> (String) null);

        System.out.println("recovered=" + recovered.block());
        System.out.println("has value=" + missing.hasElement().block());
    }
}
~~~

From the project directory, run:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.LazyFactoriesDemo
~~~

**Lines printed by the program** (excluding Maven logs if the environment has separate logs):

~~~text
compute just#1
assembled
just A=just#1
just B=just#1
compute supplier#1
supplier A=supplier#1
compute supplier#2
supplier B=supplier#2
compute callable#1
callable A=callable#1
compute callable#2
callable B=callable#2
build deferred Mono
compute defer#1
defer A=defer#1
build deferred Mono
compute defer#2
defer B=defer#2
recovered=fallback
has value=false
~~~

Explanation of the output:

1. **compute just#1** appears before **assembled** because Mono.just(compute(...)) calls compute right when assigning the just variable.
2. The two block() calls on Mono.just emit the same held value without running compute again.
3. supplier.block() and callable.block() run their respective lambdas **on each subscription**, so each counter increases from 1 to 2.
4. defer.block() first prints **build deferred Mono**, and then creates Mono.just(compute(...)); both choosing the source and computing the value happen per subscription.
5. The checked IOException from Callable is turned into onError and then onErrorResume returns **fallback**; no try/catch is needed outside block().
6. The Supplier returning null makes the Mono complete empty; hasElement() returns false.

**Note on block():** block() is only used at the console program boundary to observe results easily. Each call to block() is a subscription; do not place block()/blockLast() inside WebFlux handlers or event-loop threads.

## 8. Mono.defer in Fallback Cases: Avoiding Premature Initialization Work

A common trap is thinking switchIfEmpty also defers **creating the alternate argument**. In Java, arguments are evaluated before calling the method:

~~~java
// The expensiveFallback() function already ran when assembling the alternate Mono:
Mono<String> alternateEager = Mono.just(expensiveFallback());
Mono<String> result = primary.switchIfEmpty(alternateEager);
~~~

Even when primary has data, expensiveFallback() already ran when initializing alternateEager.

One alternative:

~~~java
Mono<String> result = primary.switchIfEmpty(
        Mono.defer(() -> Mono.just(expensiveFallback()))
);
~~~

Or shorter if only producing a single value:

~~~java
Mono<String> result = primary.switchIfEmpty(
        Mono.fromSupplier(() -> expensiveFallback())
);
~~~

Both snippets are **illustrative**, assuming primary is an existing Mono<String> and expensiveFallback() returns a non-null String. In the lazy snippets, expensiveFallback() only runs **if the fallback is actually subscribed to**. With a primary that has a value, switchIfEmpty does not need to subscribe to the alternate.

When the fallback is created by a function returning a Mono, defer is especially useful:

~~~java
// Only when primary is empty is the function building the fallback Publisher called.
Mono<String> result =
        primary.switchIfEmpty(Mono.defer(() -> buildFallbackMono()));
~~~

buildFallbackMono() returns Mono<String> and can choose branches, log, or configure the Publisher as needed. If buildFallbackMono() simply returns an already-prepared Mono.fromCallable and performs no work at assembly time, adding defer may bring no extra benefit.

## 9. Reading Reactor Context per Subscriber: Mono.deferContextual

Sometimes data varies according to **each subscription's context** (such as tenant ID or correlation ID) rather than global variables. Reactor Context is data attached to the subscription; do not confuse it with ThreadLocal.

Mono.deferContextual receives a ContextView to create a Publisher:

~~~java
import reactor.core.publisher.Mono;
import reactor.util.context.Context;

Mono<String> tenant = Mono.deferContextual(ctx ->
        Mono.just("tenant=" + ctx.getOrDefault("tenantId", "guest")));

System.out.println(tenant.contextWrite(
        Context.of("tenantId", "north")).block());

System.out.println(tenant.contextWrite(
        Context.of("tenantId", "south")).block());
~~~

This is an **illustrative snippet placed inside a Java method**, not a standalone class. The outputs are respectively:

~~~text
tenant=north
tenant=south
~~~

The same initial Mono can produce different results according to each subscriber's Context. For request data in reactive applications, deferContextual is usually better suited than reading request info from static variables or unmanaged ThreadLocals.

## 10. Deferring Does Not Automatically Solve Blocking: Use Scheduler in the Right Place

Supplier/Callable computation normally runs on the **thread performing the subscription** if there is no operator changing the scheduler. In WebFlux, if that block occupies an event-loop thread for long, other requests may also be affected.

Pattern when forced to integrate a synchronous blocking API:

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

Mono<String> legacyValue = Mono.fromCallable(
        () -> legacyBlockingClient.fetch()
).subscribeOn(Schedulers.boundedElastic());
~~~

This is an **illustrative** example, assuming legacyBlockingClient.fetch() returns String and may block. The boundedElastic scheduler shifts the work of subscribing/running the Callable to a worker suitable for waiting on blocking operations; it has **resource limits** and does not guarantee unbounded load. This is a compatibility measure when you cannot yet switch APIs; prefer non-blocking APIs/drivers if the path is designed to be fully reactive.

Important distinctions:

- **Mono.fromCallable** addresses *when* synchronous code is invoked.
- **subscribeOn(Schedulers.boundedElastic())** affects *where* the blocking source portion is executed.
- Without subscribeOn, Callable **does not automatically** run on another thread pool.
- Place subscribeOn close to the blocking source so the code is easy to understand; which thread a downstream map operator runs on also depends on other operators like publishOn.
- Do not use the **parallel** scheduler to wait on long blocking I/O; those threads are meant for tasks suited to non-blocking/CPU models.
- boundedElastic isolates blocking from the event loop but does not turn JDBC or a synchronous HTTP client into non-blocking I/O; an execution resource is still occupied while waiting.
- If performing many blocking operations, consider connection pools, timeouts, concurrency limits, and resilience policies; wrapping in Callable alone is not enough.

An example having the same issue even with Supplier:

~~~java
// Still blocking if subscribed on the event loop:
Mono<String> source = Mono.fromSupplier(() -> legacyBlockingClient.fetch());
~~~

Choosing **fromSupplier or fromCallable** does not determine async behavior; the actual call type and scheduler determine the thread impact.

## 11. Impact of Multiple Subscriptions, Retry, Cache, and Shared State

Lazy factories generally operate **per subscription**. That is both their strength and a source of bugs if the lambda has side effects.

### Multiple Subscribers

~~~java
AtomicInteger count = new AtomicInteger();
Mono<Integer> source = Mono.fromSupplier(count::incrementAndGet);

Integer first = source.block();  // 1
Integer second = source.block(); // 2
~~~

If the system has multiple concurrent subscribers, side effects may run in parallel on threads depending on the scheduler; use thread-safe structures if writing shared state. Do not assume subscriptions are serialized with each other just because they share one Mono object.

### Retry Can Re-invoke the Source

~~~java
AtomicInteger tries = new AtomicInteger();

Mono<String> operation = Mono.fromCallable(() -> {
    if (tries.incrementAndGet() == 1) {
        throw new java.io.IOException("temporary");
    }
    return "ok";
}).retry(1);
~~~

This is a **code snippet placed inside a method**, not a standalone class. When subscribed with suitable demand, on the first failure, retry(1) will **resubscribe** to the source and the Callable is called again. This example succeeds with "ok" when calling operation.block(). For operations with external side effects such as payments, writing files, or writing to a database, retry can repeat the action; you need to design for idempotency and a clear retry policy.

### Cache Changes Re-execution Behavior

~~~java
AtomicInteger count = new AtomicInteger();
Mono<Integer> cached =
        Mono.fromSupplier(count::incrementAndGet).cache();

Integer a = cached.block(); // 1
Integer b = cached.block(); // 1 (retrieves the cached signal)
~~~

**cache()** stores the result/terminal signal for later subscribers according to the operator's semantics. Once the source has been cached, it is no longer true that **every subscriber re-invokes the Supplier**. A source being cold before applying cache does not mean the entire pipeline always re-executes.

**Be careful with per-request personal data:** do not cache a pipeline carrying tenant/user information at application-wide scope without an appropriate cache key policy and data isolation.

## 12. Proper Usage in Spring WebFlux

WebFlux controllers should generally **return Mono/Flux**, letting the framework coordinate the subscription alongside the HTTP lifecycle. If a service needs to build the source when the request is actually subscribed to, return a lazy Publisher:

~~~java
@RestController
class ReportController {
    private final LegacyReportService reportService;

    ReportController(LegacyReportService reportService) {
        this.reportService = reportService;
    }

    @GetMapping("/reports/{id}")
    Mono<Report> getReport(@PathVariable long id) {
        return Mono.fromCallable(() -> reportService.loadById(id))
                   .subscribeOn(Schedulers.boundedElastic())
                   .switchIfEmpty(Mono.error(
                           new ResponseStatusException(HttpStatus.NOT_FOUND)));
    }
}
~~~

**Structural illustration** snippet, assuming classes Report and LegacyReportService exist with loadById(id) which may block and return null if missing. Requires importing Spring Web annotations, Mono, Schedulers, HttpStatus, and ResponseStatusException; not yet a standalone class. In the code above:

1. The controller method is called to **return a Mono**; loadById does not run yet when Mono.fromCallable is created.
2. When the framework subscribes, the Callable is executed under boundedElastic.
3. If loadById returns a Report, the Mono emits the value and WebFlux handles the response.
4. If loadById returns null, the Mono completes empty and switchIfEmpty produces a 404 error.
5. If loadById throws another error, the pipeline receives onError and handles it according to the active error handler.

If you already have an R2DBC driver or a truly reactive HTTP client, **do not wrap an existing reactive call in fromCallable just to make it lazy**. Return the original publisher or use defer when you need to choose or create a publisher per subscription.

## 13. Common Mistakes

| Mistake | Why It Is Wrong | Fix |
| --- | --- | --- |
| Using Mono.just(expensive()) and thinking expensive() runs later | Java evaluates arguments before calling just | Put the call in fromSupplier/fromCallable or defer of the right type |
| Using Mono.defer(() -> value) where value is a String | defer requires a Publisher/Mono, not T | Use Mono.fromSupplier(() -> value) or Mono.defer(() -> Mono.just(value)) |
| Using Mono.fromSupplier for a function declaring throws IOException without handling | Supplier.get() does not declare checked exceptions | Use Mono.fromCallable |
| Using only fromCallable for JDBC and thinking it is non-blocking | Callable still occupies a thread while waiting | Use subscribeOn(boundedElastic) when needed, prefer non-blocking APIs |
| defer factory returns null | No valid Publisher to subscribe to | Return Mono.empty(), Mono.justOrEmpty(value), or Mono.error(...) |
| Mono.just(null) | just does not accept null | Use Mono.justOrEmpty(null) for an existing value, or fromSupplier/fromCallable returning null for an empty Mono |
| Calling subscribe() in a controller and returning Mono.empty() | Detaches the task from the HTTP response and cancellation | Return the Mono so WebFlux owns the subscription |
| Using a lambda with side effects while enabling uncontrolled retry | Retry may execute side effects again | Design idempotently, limit retries, and classify retryable errors |
| Thinking Mono.fromSupplier always recomputes despite calling cache() | cache stores the signal after the first subscribe | Choose caching per requirements and understand the shared scope |
| Reading ThreadLocal variables in a pipeline that switches schedulers | The thread can change between operators | Pass data explicitly or use Reactor Context/deferContextual |

A note on error handling: when a factory throws an error at subscription time, downstream **onErrorResume, onErrorMap, retry** operators can handle the error. However, if **the computation already threw an error before creating the Mono**, no Publisher is created for downstream to handle. This is a practical reason to place work that can fail inside a lazy factory.

## 14. Choosing a Factory with Short Questions

~~~text
I already have a value T and do not need to recompute?
    -> Mono.just(T) or Mono.justOrEmpty(T).

I want each subscription to COMPUTE a value T itself?
    -> Computation does not need to declare checked exceptions?
           -> Mono.fromSupplier(...)
       May throw checked exceptions?
           -> Mono.fromCallable(...)

I want each subscription to CHOOSE/CREATE a Mono/Flux itself?
    -> Mono.defer(...) / Flux.defer(...)

I need the subscriber's Context?
    -> Mono.deferContextual(...)

I am calling a blocking API?
    -> Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())
       and control resources/timeouts; consider a non-blocking API.
~~~

You do not need to nest defer and fromCallable for every computation. Choose the **unit to defer**: a **value** or **creating/choosing the entire Publisher source**. This is the most important design distinction among the three methods.

## 15. Self-Check

**Question 1.** Why can Mono.just(System.currentTimeMillis()) emit the same timestamp for multiple subscriptions?

Because System.currentTimeMillis() is called when the Mono.just expression is evaluated; Mono holds that value. Mono.fromSupplier(System::currentTimeMillis) retrieves the time on each subscription (closely spaced calls can still share the same millisecond).

**Question 2.** If you want a file-reading API that throws IOException to run only on subscribe, what should you use?

Mono.fromCallable(() -> Files.readString(path)). If called in WebFlux and it is blocking I/O, consider subscribeOn(Schedulers.boundedElastic()) and timeout/resource policies.

**Question 3.** If the factory of Mono.defer returns null, does it emit null?

No. It fails to produce a valid Mono, leading to an error. To represent having no element, return Mono.empty() or Mono.justOrEmpty(value).

**Question 4.** Can fromSupplier be replaced with defer(() -> Mono.just(...))?

Possible when the value is non-null, but fromSupplier is usually simpler when only producing T. When the value can be null, use Mono.justOrEmpty inside defer or let Supplier/Callable return null so the Mono completes empty.

**Question 5.** Does using fromCallable and placing subscribeOn(boundedElastic) automatically turn a synchronous database into non-blocking?

No. It dispatches the blocking work to an appropriate worker; the call itself is still blocking on that thread.

**Question 6.** Why might a source from fromSupplier invoke the Supplier only once for three subscribers?

The pipeline might have cache() or another sharing operator applied, causing later subscribers to receive the stored result without creating a new subscription to the original source.

**Question 7.** When is Mono.deferContextual better than Mono.defer?

When the decision to create the source or data must depend on **each subscription's Reactor Context**, such as tenant ID or correlation ID, instead of reading global state.

## 16. References

- [Project Reactor: Mono API — defer, deferContextual, fromSupplier, fromCallable, just](https://projectreactor.io/docs/core/3.6.17/api/reactor/core/publisher/Mono.html).
- [Project Reactor: Reactor Core Reference Guide](https://projectreactor.io/docs/core/3.6.17/reference/), section on sequence creation and best practices.
- [Project Reactor FAQ: wrapping a synchronous, blocking call](https://projectreactor.io/docs/core/3.6.17/reference/#faq.wrap-blocking).
- [Java 17: Supplier<T>](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Supplier.html) and [Callable<T>](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Callable.html).

**Takeaway:** **fromSupplier** and **fromCallable** defer producing a **value** per subscription; **defer** defers creating or choosing a **Publisher** per subscription. **Mono.just** takes an already-evaluated value. All three lazy factories can run blocking code if the code inside is blocking; using them safely in WebFlux requires understanding threads, demand, cancellation, errors, and operators like retry/cache.