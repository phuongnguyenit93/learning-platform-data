# Distinguishing Reactive Return Types from Truly Non-Blocking Work

## 1. A Reactive Return Type Does Not Prove the Work Inside Is Non-Blocking

A controller can declare:

~~~java
@GetMapping("/products/{id}")
public Mono<Product> find(@PathVariable String id) {
    return Mono.just(repository.findById(id));
}
~~~

Looking at the signature, the method returns **Mono<Product>**, so it looks reactive. But if the repository uses JDBC or a synchronous library, the call **repository.findById(id)** already ran as soon as Java executed the method. The current thread must wait for the database to return the result **before Mono.just(...) finishes being created and returned**.

This is the core point:

> **A reactive return type describes how signals are represented and composed. Non-blocking describes how work actually waits and uses threads. The two are related, not synonymous.**

A Mono/Flux can:

- Emit data synchronously right on the subscribing thread.
- Defer a blocking call until subscribe time, yet still run that call on the subscribing thread.
- Wrap a Future running on a thread pool; the caller does not wait directly, but the work inside may still block another worker.
- Use an asynchronous I/O API to register a callback, yield control of the thread while waiting for I/O, and emit a signal when the result is ready.

Therefore, looking only at **Mono<T>** or **Flux<T>** is not enough to conclude that a WebFlux request will not block the event loop.

## 2. Distinguishing Four Commonly Confused Concepts

### 2.1. Reactive

**Reactive** is a way of describing data and behavior through Publisher/Subscriber, onNext/onError/onComplete signals, operators to transform/combine, and the demand/backpressure mechanism of Reactive Streams.

In Reactor:

- **Mono<T>** represents 0 or 1 value.
- **Flux<T>** represents 0 to many values.
- Operators such as map, filter, flatMap, timeout, and retryWhen help build pipelines.

A reactive API helps describe a workflow and coordinate results. It does not require every computation in the pipeline to run asynchronously or on a separate thread.

### 2.2. Asynchronous

An asynchronous operation lets the caller continue other work while the result will be notified later, typically via a callback, Future, or Publisher.

However, **asynchronous does not automatically mean non-blocking at every layer**. For example:

~~~java
CompletableFuture<Product> future =
        CompletableFuture.supplyAsync(() -> blockingRepository.find(id));
~~~

The caller receives the Future immediately, yet a worker of the Executor still has to wait inside blockingRepository.find(id). This decouples waiting time from the caller; it does not turn JDBC into non-blocking I/O.

### 2.3. Non-Blocking

A **non-blocking I/O** operation does not hold a thread waiting synchronously until the socket/database is ready. The runtime registers an I/O readiness/completion event and continues processing other work; when data is ready, a callback or reactive signal is emitted.

The goal in WebFlux is not to occupy the scarce event-loop threads just to wait for network I/O or database I/O.

### 2.4. Synchronous Is Not Necessarily Blocking I/O

A CPU computation such as:

~~~java
int result = price * quantity;
~~~

executes synchronously on the current thread, yet it is not an operation waiting for I/O. It still uses CPU and holds the thread while computing, but it does not sleep/wait for a socket or database.

We must distinguish:

- **Synchronous CPU work:** runs immediately on the current thread; can consume CPU but does not wait on I/O.
- **Blocking I/O:** the thread is held waiting for an external operation.
- **Asynchronous work:** the result arrives later via a completion mechanism; the underlying task may be non-blocking or still blocking on another worker.
- **Reactive composition:** describes how Publishers are combined; by itself it does not certify the kind of I/O.

## 3. Why Can Mono/Flux Contain Blocking Work?

Reactor cannot automatically tell whether Java statements inside a lambda are JDBC, file I/O, blocking sockets, CPU calculation, or callback APIs. A Publisher can be created from any Java code.

Example:

~~~java
Mono<Product> product = Mono.fromCallable(
        () -> jdbcRepository.findById("P01")
);
~~~

**fromCallable** defers the call until a subscription occurs. Yet if no Scheduler is specified, the synchronous Callable usually runs in the request/subscription context. If the request is being handled on WebFlux's event loop, the JDBC call can still block the event loop.

Similarly:

~~~java
Mono<String> result = remoteClient.fetch()
        .map(response -> legacyBlockingParser.parse(response));
~~~

If remoteClient.fetch() is a non-blocking Publisher yet **legacyBlockingParser.parse(...)** performs blocking I/O, map runs that function synchronously on the thread emitting onNext. A non-blocking source does not protect downstream steps from blocking.

**The reactive return type is a signal contract; non-blocking behavior depends on each executed operation and where that operation runs.**

## 4. Execution Timing: Mono.just, fromCallable, defer, and Future

A reactive source is often described as lazy, yet not every Java expression used to create a source is lazy. You need to determine whether work is called **when building the Publisher** or **at subscribe time**.

### 4.1. Mono.just(expression): the expression is evaluated immediately

~~~java
Mono<Product> wrong = Mono.just(
        jdbcRepository.findById(id)
);
~~~

Java evaluates the argument before calling Mono.just. Therefore:

1. Call jdbcRepository.findById(id).
2. The current thread waits for JDBC to return the result.
3. Only then is Mono.just(product) called.
4. The Publisher emits the already-computed value when subscribed.

**Mono.just does not defer evaluating its argument.** It holds an already-computed value to emit later.

### 4.2. Mono.fromCallable: deferring Callable to subscription

~~~java
Mono<Product> deferred = Mono.fromCallable(
        () -> jdbcRepository.findById(id)
);
~~~

At this point JDBC has not run when merely creating the Mono. The Callable is invoked when a subscription occurs. That solves **eager evaluation**, but does not yet solve thread placement:

- Subscribed on the event loop: the Callable can block the event loop.
- Subscribed on a properly chosen worker: the Callable blocks that worker.
- If the Callable calls a non-blocking API, there is no reason to move it to boundedElastic merely because it is inside fromCallable.

### 4.3. Mono.defer: creating a new Publisher per subscription

~~~java
Mono<Product> deferred = Mono.defer(() -> {
    String id = requestContext.currentProductId();
    return productService.findReactive(id);
});
~~~

**defer** invokes the Supplier upon subscribe and receives a Publisher for that subscription. It is useful when you need to:

- Read a context value at subscription time.
- Create a new request for each retry attempt.
- Avoid eagerly calling an API that creates a Future or Publisher when assembling the pipeline.
- Create a separate Publisher for each subscription.

Yet **defer does not switch threads by itself and does not make the inner function non-blocking**. If the Supplier calls a blocking API, the operation still blocks the subscribing thread unless scheduled appropriately.

### 4.4. Mono.fromFuture: the Future may already be running before being wrapped

~~~java
CompletableFuture<Product> future =
        CompletableFuture.supplyAsync(() -> remoteService.fetch());

Mono<Product> eagerFuture = Mono.fromFuture(future);
~~~

In this example, **supplyAsync** is called as soon as the Java expression is evaluated. The Future may start executing before the Mono is subscribed. fromFuture(future) wraps an already-existing Future.

If you want to create the Future per subscription:

~~~java
Mono<Product> lazyFuture =
        Mono.fromFuture(() ->
                CompletableFuture.supplyAsync(
                        () -> remoteService.fetch(),
                        applicationExecutor
                )
        );
~~~

The overload accepting **Supplier<CompletableFuture>** defers creating the Future until subscribe time. However, if remoteService.fetch() is still a blocking API, a worker from applicationExecutor is still occupied while waiting. **Future is asynchronous in how it notifies the result; it does not change the nature of the underlying API.**

When using fromFuture, understand its cancellation policy: Reactor can propagate cancel to the Future depending on the chosen overload, yet cancelling a Future does not guarantee that an already-sent remote command will roll back or that a running thread will stop instantaneously.

### 4.5. Quick Comparison Table

| Way to create Publisher | When does the inner call run? | Is it automatically non-blocking? |
| --- | --- | --- |
| **Mono.just(blockingCall())** | Immediately when evaluating the Java expression | No; can block even before subscription |
| **Mono.fromCallable(blockingCall)** | At subscribe time | No; Callable still runs synchronously on the subscription thread unless scheduled |
| **Mono.defer(() -> publisher)** | Supplier runs at subscribe time | No; depends on the created Publisher/function |
| **Mono.fromFuture(existingFuture)** | Future may already have started before wrapping | No; depends on how the Future was created |
| **Mono.fromFuture(futureSupplier)** | Supplier creates the Future at subscribe time | No; depends on the work inside the Future |
| **WebClient / reactive driver** | I/O is coordinated asynchronously by the runtime | Usually non-blocking if the connector/driver and surrounding steps are also non-blocking |

## 5. map and flatMap Do Not Change Blocking Behavior on Their Own

### 5.1. map executes a synchronous function

~~~java
Mono<String> result = Mono.just("P01")
        .map(id -> jdbcRepository.findById(id).getName());
~~~

The function in map is invoked when upstream emits onNext. It runs synchronously on the thread handling that signal. If JDBC blocks, that thread blocks.

map fits synchronous, fast transformations that do not wait on I/O, for example:

~~~java
Mono<Integer> total = Mono.just(10)
        .map(value -> value * 2);
~~~

### 5.2. flatMap composes Publishers; it does not turn a blocking function into async

~~~java
Mono<Product> product = Mono.just("P01")
        .flatMap(id -> Mono.just(jdbcRepository.findById(id)));
~~~

This is still wrong code if the repository is blocking. The call jdbcRepository.findById(id) is evaluated **before** Mono.just; flatMap cannot make it asynchronous.

flatMap is useful when the function returns a genuinely reactive Publisher:

~~~java
Mono<Product> product = Mono.just("P01")
        .flatMap(id -> webClient.get()
                .uri("/products/{id}", id)
                .retrieve()
                .bodyToMono(Product.class));
~~~

Here flatMap composes the Publisher from WebClient; HTTP I/O is performed by the non-blocking client. flatMap does not create a separate thread per element; concurrency depends on the inner Publisher and the overload/concurrency strategy used.

### 5.3. A More Correct Way to Wrap Blocking Calls

~~~java
Mono<Product> product = Mono.fromCallable(
        () -> jdbcRepository.findById(id)
).subscribeOn(Schedulers.boundedElastic());
~~~

The Callable is deferred and **subscribeOn** schedules subscribing/the source onto a boundedElastic worker. The event-loop thread does not have to wait for JDBC.

This is how to **isolate blocking** to integrate a library without a reactive API. It does not turn JDBC into non-blocking; each task still occupies one worker while waiting. BoundedElastic has thread and queue limits, so monitor load and set appropriate bounds.

## 6. Schedulers Isolate Blocking; They Do Not Eliminate Blocking

### 6.1. subscribeOn: scheduling the source

When the initial source is a blocking Callable:

~~~java
Mono<Product> product = Mono.fromCallable(
        () -> jdbcRepository.findById(id)
).subscribeOn(Schedulers.boundedElastic());
~~~

Placing subscribeOn near the source schedules subscription/the source onto a suitable Scheduler. This is the commonly recommended Reactor pattern for wrapping a synchronous, blocking call.

**boundedElastic** fits unavoidable blocking work because it bounds resources rather than creating unlimited threads. As load rises, tasks may have to wait in a queue; therefore timeouts, concurrency limits, metrics, and an overload policy are needed.

### 6.2. publishOn: switching downstream context

If a WebClient source is non-blocking yet the next step calls a blocking library:

~~~java
Mono<Report> report = webClient.get()
        .uri("/data/{id}", id)
        .retrieve()
        .bodyToMono(Data.class)
        .publishOn(Schedulers.boundedElastic())
        .map(data -> legacyBlockingFormatter.format(data));
~~~

publishOn is placed before map so that the formatting function runs on a boundedElastic worker. If publishOn is placed **after** map, map may already have run on the upstream thread and blocked before signals were switched.

### 6.3. A Scheduler Does Not Equal a Non-Blocking API

| Approach | What changes? | What does not change? |
| --- | --- | --- |
| fromCallable + subscribeOn(boundedElastic) | Blocking work runs on a more suitable worker, reducing risk of blocking the event loop | The API still blocks and occupies a worker while waiting |
| publishOn(boundedElastic) before a blocking step | The downstream step is moved to another worker | That work still occupies a worker |
| subscribeOn(parallel) with JDBC | JDBC runs on a CPU-oriented worker | Unsuitable for prolonged blocking; can stall the Scheduler |
| WebClient with a non-blocking connector | I/O is coordinated via callbacks/event loop | Application-side map/filter can still block |
| Mono.delay(Duration) | A timer is scheduled and emits a signal after the delay | If block() is called to wait at the caller, the caller itself is still blocked at the synchronous boundary |

**Schedulers.parallel()** is for short, non-blocking CPU-bound work. **Schedulers.boundedElastic()** is for unavoidable blocking work. Do not use parallel to "run faster" a blocking JDBC API.

## 7. Why Does This Matter Especially in Spring WebFlux?

WebFlux is designed with the assumption that request handlers do not block. With an event-loop runtime such as Reactor Netty, the number of request-handling threads is relatively small and fixed compared to the number of concurrent requests/connections that can be managed.

One event-loop thread can coordinate many connections. If a controller calls JDBC synchronously:

~~~text
Event-loop worker
    |
    +--> receives request A
    |
    +--> calls JDBC and waits 800 ms  <--- thread is held
    |
    +--> cannot handle other callbacks on that worker yet
    |
    +--> JDBC returns result
    |
    +--> continues response
~~~

While waiting, other tasks assigned to the same worker can be delayed. Under load, this leads to higher latency, growing queues, cascading timeouts, and reduced throughput.

Not every thread in WebFlux is an event loop, and exact thread names depend on the server/runtime/configuration. However, the principle remains: **do not run blocking I/O on threads designed to serve many reactive signals**.

### 7.1. Controller returns Mono yet still blocks before returning

~~~java
@GetMapping("/products/{id}")
Mono<Product> get(@PathVariable String id) {
    Product product = jdbcRepository.findById(id); // Blocks right here.
    return Mono.just(product);
}
~~~

The method return type is Mono, yet the controller returns Mono only **after JDBC has finished**. WebFlux cannot turn back time to make a synchronous call asynchronous.

### 7.2. Controller returns Mono and defers, yet still blocks the event loop

~~~java
@GetMapping("/products/{id}")
Mono<Product> get(@PathVariable String id) {
    return Mono.fromCallable(
            () -> jdbcRepository.findById(id)
    );
}
~~~

The eager call was avoided, yet if subscription happens on the request/event-loop thread, the Callable can still run on that thread. You need a reactive driver or to schedule the blocking call onto boundedElastic.

### 7.3. Controller returns Mono and keeps I/O non-blocking

~~~java
@GetMapping("/products/{id}")
Mono<Product> get(@PathVariable String id) {
    return webClient.get()
            .uri("/products/{id}", id)
            .retrieve()
            .bodyToMono(Product.class);
}
~~~

WebClient with a non-blocking connector performs HTTP I/O in an event-driven manner. The controller returns the Publisher and the framework manages subscription/response. However, every subsequent map/filter/validation step still needs to avoid blocking.

## 8. Use a Reactive Driver End-to-End When Possible

If the database is the main source of waiting, driver choice matters greatly.

| Data layer | Common API | Characteristics |
| --- | --- | --- |
| JDBC | JdbcTemplate, JDBC Repository | Blocking I/O |
| Traditional JPA/Hibernate ORM | EntityManager, JpaRepository | Usually blocking via JDBC |
| R2DBC | DatabaseClient, ReactiveCrudRepository | Reactive/non-blocking I/O if driver and config support it |
| Reactive MongoDB driver | ReactiveMongoTemplate/Repository | Reactive I/O |
| HTTP WebClient | retrieve().bodyToMono(...) | Non-blocking with a supporting connector |
| Synchronous HTTP client | RestTemplate or blocking client | Caller usually waits for the response |

Example service using R2DBC:

~~~java
@Service
class ProductService {
    private final ReactiveCrudRepository<Product, String> repository;

    ProductService(ReactiveCrudRepository<Product, String> repository) {
        this.repository = repository;
    }

    Mono<Product> find(String id) {
        return repository.findById(id);
    }
}
~~~

This is an illustrative snippet, assuming the repository is configured with a suitable reactive database driver. The Publisher is created from a reactive API; there is no need to wrap it in fromCallable or move it to boundedElastic just because it is a database call.

Some notes:

- **The reactive driver must actually be non-blocking** at the network/driver layer.
- If the reactive pipeline calls JDBC or JPA inside, the whole chain is no longer non-blocking end-to-end.
- Transactions need a suitable reactive transaction manager; do not use a synchronous transaction and expect the Publisher to adapt automatically.
- Do not choose R2DBC just because it says reactive if the application has no corresponding concurrency/streaming need; stack selection should be based on architecture and operations.

## 9. CompletableFuture and Thread Pools: Asynchronous Does Not Equal Non-Blocking

A common example:

~~~java
Mono<Product> result = Mono.fromFuture(
        CompletableFuture.supplyAsync(
                () -> blockingRepository.findById(id)
        )
);
~~~

The caller may receive Mono immediately, yet supplyAsync is invoked as soon as the expression is built. It uses the common ForkJoinPool if no Executor is passed. If blockingRepository waits on JDBC, a worker in the pool is still held. Under load, the pool may run out of workers for other tasks.

If a Future API must be used:

1. Determine whether the underlying API is genuinely non-blocking or merely runs blocking work on an executor.
2. Use a properly configured and bounded Executor for blocking work.
3. Use the Supplier overload of fromFuture or defer if you need to create the Future per subscription.
4. Have timeouts, cancellation, and error handling per contract.
5. Do not treat cancelling a Future as rolling back a remote operation.

Example of lazily creating a Future with a dedicated executor:

~~~java
Mono<Product> result = Mono.fromFuture(() ->
        CompletableFuture.supplyAsync(
                () -> blockingRepository.findById(id),
                blockingExecutor
        )
);
~~~

This is still **isolating a blocking call on an Executor**. If the library has a genuinely non-blocking callback API, prefer adapting a Publisher directly from that API.

## 10. Backpressure Does Not Turn Blocking into Non-Blocking

Reactive Streams uses demand so the Subscriber throttles how many elements the Publisher is allowed to emit. This mechanism helps manage data rate, yet it does not make a JDBC call, Thread.sleep, Future.get, or Mono.block non-blocking.

Example:

~~~java
Flux<Integer> values = Flux.range(1, 100)
        .map(number -> {
            Thread.sleep(100);
            return number;
        });
~~~

This is an illustrative code snippet. Even though Flux supports backpressure, map still blocks the thread handling onNext for 100 ms per element.

Separate the two issues:

- **Backpressure:** controls how many signals are requested/delivered downstream.
- **Non-blocking execution:** does not hold threads waiting for I/O; uses callbacks/event loops or appropriate async mechanisms.

A source that cannot slow down may need buffering, dropping, or failing according to policy. Buffering also cannot fix an operator that is blocking on the event loop.

## 11. Cancellation and Timeouts Do Not Guarantee Blocking Work Stops Immediately

When downstream cancels a subscription or a timeout occurs, Reactor sends a cancellation signal upstream. However:

- A Callable that has already started may be in the middle of a JDBC/file I/O call.
- Thread interruption may not be supported by an external library or may not stop the operation immediately.
- Future.cancel(true) does not guarantee every already-started task stops instantaneously.
- An HTTP request that has reached the server may continue executing even after the client cancels.
- Already-committed side effects do not automatically roll back just because the Publisher is cancelled.

Therefore, for blocking operations you need:

- Timeouts at the right client/driver layer and operation deadlines.
- APIs that support cancellation if available.
- Limits on concurrency and pending tasks.
- Idempotency for write operations that may be retried.
- Observability of tasks still running after the request ends.

**Cancellation is a signal controlling the Publisher, not a guarantee to stop every external system.**

## 12. Runnable Java 17+ Example: Demonstrating the Difference Between Eager, Deferred, and Offloaded

The following example uses pure **Reactor Core**, without Spring Boot or a real database. The blockingRead function simulates a synchronous API with a short Thread.sleep. The goal is to observe when and on which thread the function runs.

Structure:

~~~text
reactive-vs-nonblocking/
├── pom.xml
└── src/main/java/ReactiveDoesNotMeanNonBlockingDemo.java
~~~

### 12.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>reactive-vs-nonblocking</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.6.12</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>ReactiveDoesNotMeanNonBlockingDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 12.2. ReactiveDoesNotMeanNonBlockingDemo.java

~~~java
import java.time.Duration;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

public class ReactiveDoesNotMeanNonBlockingDemo {

    private static String blockingRead(AtomicBoolean invoked) {
        invoked.set(true);
        try {
            Thread.sleep(20); // Simulate a blocking I/O call.
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted", error);
        }
        return "record";
    }

    public static void main(String[] args) {
        String callerThread = Thread.currentThread().getName();

        // 1. Mono.just receives a value already computed when building the Publisher.
        AtomicBoolean eagerInvoked = new AtomicBoolean();
        Mono<String> eager = Mono.just(blockingRead(eagerInvoked));
        boolean eagerRanBeforeSubscribe = eagerInvoked.get();
        eager.block();

        // 2. fromCallable defers the call until subscription.
        AtomicBoolean deferredInvoked = new AtomicBoolean();
        AtomicReference<String> deferredThread = new AtomicReference<>();

        Mono<String> deferred = Mono.fromCallable(() -> {
            deferredThread.set(Thread.currentThread().getName());
            return blockingRead(deferredInvoked);
        });

        boolean callableWasDeferred = !deferredInvoked.get();
        deferred.block();
        boolean callableRanOnCaller =
                callerThread.equals(deferredThread.get());

        // 3. subscribeOn moves the blocking source to boundedElastic.
        AtomicReference<String> workerThread = new AtomicReference<>();

        Mono<String> isolated = Mono.fromCallable(() -> {
            workerThread.set(Thread.currentThread().getName());
            return blockingRead(new AtomicBoolean());
        }).subscribeOn(Schedulers.boundedElastic());

        isolated.block();
        boolean blockingCallMovedOffCaller =
                !callerThread.equals(workerThread.get());

        // 4. The timer emits a signal asynchronously; block is used only
        //    at the console boundary to observe the result.
        long timerValue = Mono.delay(Duration.ofMillis(10)).block();

        System.out.println(
                "eager work ran before subscribe = " + eagerRanBeforeSubscribe);
        System.out.println(
                "fromCallable work was deferred = " + callableWasDeferred);
        System.out.println(
                "fromCallable ran on caller thread = " + callableRanOnCaller);
        System.out.println(
                "boundedElastic moved work off caller = "
                        + blockingCallMovedOffCaller);
        System.out.println("Mono.delay emitted = " + timerValue);
    }
}
~~~

### 12.3. Running the Program

Requires **JDK 17+**, Maven, and connectivity to download dependencies on the first run. In the directory containing pom.xml:

~~~bash
mvn -q compile exec:java
~~~

**Stdout printed by the program:**

~~~text
eager work ran before subscribe = true
fromCallable work was deferred = true
fromCallable ran on caller thread = true
boundedElastic moved work off caller = true
Mono.delay emitted = 0
~~~

### 12.4. Analyzing the Results

1. **eager work ran before subscribe = true**: blockingRead already ran when Java evaluated the argument of Mono.just, before block was called.
2. **fromCallable work was deferred = true**: the Callable did not run when merely creating the Publisher; it ran when block() subscribed.
3. **fromCallable ran on caller thread = true**: fromCallable does not switch Schedulers by default. block() subscribed on the main thread, so the synchronous Callable ran on that thread.
4. **boundedElastic moved work off caller = true**: subscribeOn(boundedElastic) scheduled the source onto another worker. The call still used a worker during Thread.sleep; it was only isolated from the caller.
5. **Mono.delay emitted = 0**: the timer was scheduled and emitted a signal after the preset delay. In the console demo, block() waits for the result to print; a real WebFlux controller returns the Publisher instead of blocking.

This program **illustrates timing/thread behavior**, not a benchmark. Thread.sleep only simulates a blocking API; actual durations and worker names can vary by runtime. The program does not conclude that every API using Future or Mono is non-blocking.

## 13. Practical Examples in Controllers and Services

### 13.1. Pattern to Use When Calling Blocking JDBC/JPA Is Unavoidable

~~~java
@Service
class LegacyProductService {
    private final ProductRepository repository;

    LegacyProductService(ProductRepository repository) {
        this.repository = repository;
    }

    Mono<Product> find(String id) {
        return Mono.fromCallable(() -> repository.findById(id))
                .subscribeOn(Schedulers.boundedElastic());
    }
}
~~~

This is an **illustrative snippet**, assuming ProductRepository is a blocking API returning Product. fromCallable defers the call; subscribeOn isolates it on boundedElastic.

The controller returns the Publisher:

~~~java
@RestController
class ProductController {
    private final LegacyProductService service;

    ProductController(LegacyProductService service) {
        this.service = service;
    }

    @GetMapping("/products/{id}")
    Mono<Product> find(@PathVariable String id) {
        return service.find(id);
    }
}
~~~

Do not call subscribe() or block() in the controller. The framework manages the response lifecycle. If a blocking source can take a long time, configure timeouts and limit pending tasks; do not rely on boundedElastic as an unbounded pool.

### 13.2. Pattern to Use with a Genuinely Reactive API

~~~java
@Service
class ReactiveProductService {
    private final WebClient webClient;

    ReactiveProductService(WebClient.Builder builder) {
        this.webClient = builder.baseUrl("https://catalog.example").build();
    }

    Mono<Product> find(String id) {
        return webClient.get()
                .uri("/products/{id}", id)
                .retrieve()
                .bodyToMono(Product.class);
    }
}
~~~

This is an illustrative service snippet with Product and WebClient configured in the application. HTTP I/O is performed by the non-blocking connector. There is no need to wrap WebClient with fromCallable or subscribeOn(boundedElastic).

If there is a significant CPU-bound step after bodyToMono, consider an appropriate Scheduler boundary. If that step calls a blocking API, you must isolate the blocking or replace the library with a non-blocking API.

### 13.3. Do Not Place publishOn After an Operation That Already Blocked

~~~java
// Wrong: JDBC already ran before publishOn.
Mono<Product> wrong = Mono.just(repository.findById(id))
        .publishOn(Schedulers.boundedElastic());
~~~

~~~java
// Better: defer and schedule the blocking call.
Mono<Product> wrapped = Mono.fromCallable(
        () -> repository.findById(id)
).subscribeOn(Schedulers.boundedElastic());
~~~

publishOn only changes where processing runs **downstream** from where it is placed. It cannot move an already-completed call backward.

## 14. Checking Whether a Pipeline Is Truly Non-Blocking

A method signature is not enough. You need to observe the implementation and execution threads.

### 14.1. Checking Data Sources and Libraries

- Does the repository use **JDBC/JPA** or **R2DBC/a reactive driver**?
- Does the HTTP client use **WebClient/a non-blocking connector** or a synchronous API?
- Does file I/O use a synchronous or async API?
- Are there Thread.sleep, Object.wait, CountDownLatch.await, Future.get, CompletableFuture.join, Mono.block, or Flux.blockLast calls?
- Does any mapper/validator/serializer perform network queries or file reads?
- Are Futures created eagerly before the Publisher is subscribed?

### 14.2. Checking Threads

Record threads at sensitive steps:

~~~java
Mono<Product> result = productService.find(id)
        .doOnNext(product -> log.debug(
                "product received on thread {}",
                Thread.currentThread().getName()
        ));
~~~

This is an illustrative snippet with a logger. Thread names can help recognize the event loop (reactor-http-nio-... with Reactor Netty) or boundedElastic (boundedElastic-...), yet **do not use thread names as a fixed contract** because the runtime/configuration may change.

### 14.3. Using BlockHound in Development/Test Environments

**BlockHound** is a tool that integrates with Reactor to detect certain blocking calls on threads marked non-blocking. It is useful for finding Thread.sleep, synchronous waits, or blocking APIs in a pipeline.

Keep in mind:

- Configure BlockHound and its integration according to JDK, Reactor, and library versions.
- Not every custom blocking API is automatically detected; appropriate instrumentation/allow-lists may be needed.
- Run in tests or development environments for early detection.
- BlockHound does not replace code review, performance measurement, or checking drivers.

### 14.4. Measuring Under Real Load

Monitor:

- Event-loop threads held for a long time or rising CPU/queues.
- P95/P99 latency and in-flight requests.
- BoundedElastic active threads, queued tasks, and rejected tasks.
- Connection pool pending acquires and DB query times.
- Timeout/cancel rates and operations still continuing in external systems.
- Active subscriptions and memory consumption during streaming.

Reactive/non-blocking does not automatically make every application faster. The benefit is usually clear when there is much slow or unpredictable I/O and the layers genuinely support non-blocking. If the entire system is still blocking, switching to WebFlux can add complexity without achieving the desired benefits.

## 15. Common Misconceptions

| Misconception | Consequence | Correct understanding |
| --- | --- | --- |
| A method returns Mono so it must be non-blocking | JDBC can block before Mono is returned | Check every call and the execution thread |
| Mono.just defers expressions | Blocking happens right when building the Mono | Java arguments are evaluated before calling just |
| fromCallable runs asynchronously by itself | Callable can run on the subscribing thread | A suitable Scheduler is needed if the Callable is blocking |
| defer turns code into non-blocking | Supplier can still block at subscribe time | defer only defers creating the Publisher |
| flatMap creates its own thread | Blocking lambdas still run synchronously | flatMap composes Publishers; the inner source determines behavior |
| Placing publishOn after map moves map | Map may already have blocked upstream | Place the boundary before the step that needs switching |
| subscribeOn(boundedElastic) makes JDBC reactive | A worker is still occupied while JDBC waits | This is blocking isolation, not non-blocking I/O |
| CompletableFuture is always non-blocking | A worker in the executor may run a blocking API | Inspect the task inside the Future |
| Backpressure prevents threads from blocking | map or JDBC still blocks the thread | Backpressure regulates demand, it does not change I/O semantics |
| Cancel means the server stops immediately | Remote side effects may still run | Cancellation depends on driver/protocol and does not auto-rollback |
| Reactive is always faster than MVC | Extra schedulers/operators can add overhead | Measure the workload and pick the right model |
| Fixed thread names are the only verification method | Tests break easily when runtime changes | Check Scheduler types, stack traces, and metrics |

## 16. Checklist Before Writing a Reactive Controller

1. **Does the method do work before returning the Publisher?** Avoid blocking/eager calls before Mono.just.
2. **Is the source really lazy?** Distinguish Mono.just, fromCallable, defer, and already-running Futures.
3. **Are the I/O clients/drivers truly non-blocking?** Check the implementation, not just the return type.
4. **Do map/filter/doOnNext lambdas block?** Synchronous operators run on the signal-emitting thread.
5. **If blocking is unavoidable, is it properly isolated?** Use fromCallable + subscribeOn(boundedElastic) for blocking sources or publishOn before a downstream blocking step.
6. **Is the right Scheduler used?** parallel for CPU-bound; boundedElastic for blocking.
7. **Is there any block/get/join/sleep on the event loop?** Remove it or design a clear synchronous boundary.
8. **Are concurrency and queues bounded?** Avoid piling up too many blocking tasks.
9. **What do cancellation and timeout mean for the driver/remote API?** Do not assume automatic rollback.
10. **Are there tests/metrics to detect blocking?** Use BlockHound when appropriate, and watch event-loop and latency metrics under load.

## 17. Conclusion

**Returning Mono or Flux does not mean the work is genuinely non-blocking.** Mono.just can receive a result already computed by a blocking call; fromCallable defers the call yet can still run on the subscribing thread; defer only defers creating the Publisher; Future can run blocking work on another executor.

To make a WebFlux application genuinely non-blocking, use **WebClient and a reactive database driver** or equivalent async/non-blocking APIs throughout. When a blocking library must be integrated, use **fromCallable + subscribeOn(boundedElastic)** or publishOn in the right position to protect the event loop, while bounding load and monitoring queues. This is an isolation measure, not converting a blocking API into non-blocking.

Before concluding that a reactive controller is safe for WebFlux, trace **from when the method is called, when the Publisher is created, when it is subscribed, through every operator, to the I/O driver, and at cancellation**. The return type is only part of the answer.

**Official documentation:**
- [Spring Framework — WebFlux Overview: reactive, non-blocking, and concurrency model](https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html)
- [Reactor Reference — How do I wrap a synchronous, blocking call?](https://projectreactor.io/docs/core/release/reference/faq.html)
- [Reactor Mono API — fromCallable, fromFuture, and subscribeOn](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html)
- [Reactor Reference — Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html)
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html)
- [Spring Data R2DBC — Reference](https://docs.spring.io/spring-data/relational/reference/r2dbc.html)
