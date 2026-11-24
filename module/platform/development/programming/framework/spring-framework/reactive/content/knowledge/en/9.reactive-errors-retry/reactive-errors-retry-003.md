# onErrorResume and Switching to a Fallback Source in Reactor

## 1. The Problem to Solve

In **Project Reactor**, a **Mono<T>** or **Flux<T>** can fail because an external service is temporarily unavailable, times out, closes the connection, or fails a data transformation. According to Reactive Streams, **onError** is a terminal signal: a Publisher that has errored cannot continue emitting the remaining elements.

In many Spring WebFlux systems, a technical error can be handled using an alternative source. For example: calling the primary API to fetch a user profile; when the API temporarily fails, reading the profile stored in cache. The **onErrorResume** operator's job is to **switch to a fallback Publisher** when upstream emits a matching error:

~~~java
Mono<User> result = remoteClient.find(id)
    .onErrorResume(error -> localCache.find(id));
~~~

The snippet above illustrates hypothetical application types and methods. It does not automatically turn a remote read into a cache read when the remote returns empty, and it does not re-call the remote. The goal of this lesson is to understand accurately **when the fallback runs, which errors are recovered, what data is emitted, what happens when the fallback also fails**, and how to apply it safely in WebFlux.

After this lesson, you will be able to:

- Explain the onSubscribe/onNext/onError/onComplete signal sequence before and after onErrorResume.
- Distinguish **error recovery**, **retry**, and **empty fallback**.
- Use **Class** or **Predicate** overloads to catch only recoverable errors.
- Place onErrorResume in the right position in Mono, Flux pipelines, and inside flatMap/concatMap mappers.
- Design fallbacks with timeout limits, observability of the original error, and without hiding business errors.
- Run and explain a Java 17 program with Reactor Core illustrating success, error, empty source, and multi-tier fallback paths.

## 2. Signal Mechanism: Errored Source Terminates, Fallback Source Is Subscribed

The Reactive Streams protocol on a Subscription:

~~~text
onSubscribe → onNext* → (onError | onComplete)?
~~~

**onError** and **onComplete** are two mutually exclusive terminal signals. onErrorResume does not let the old Publisher continue emitting on its own after an error. Instead, it handles the error signal and **subscribes to a new Publisher** returned by the fallback function.

~~~text
Primary source:
  onSubscribe → onNext(A) → onError(primaryError)
                                       │
                                       ▼
                                onErrorResume
                                       │
                                choose Publisher
                                       │
Fallback source:           onSubscribe → onNext(B) → onComplete
                                       │
                                       ▼
Downstream sees:
  onSubscribe → onNext(A) → onNext(B) → onComplete
~~~

If the fallback also emits **onError**, downstream receives that error, unless another error-handling operator sits further downstream.

Consequences:

1. Any **onNext** already sent before the Flux error are preserved downstream. onErrorResume does not erase or roll back data already emitted.
2. **The primary source does not resume from the element after the error.** Recovery means replacing the remainder with a new source.
3. **The fallback function is only called when upstream emits a matching onError** during subscription; it does not run immediately just because the Mono/Flux object was constructed.
4. **Downstream Subscription demand/backpressure must still be respected** when switching to the fallback source.
5. When the final Subscriber calls **cancel**, that is a cancellation action, not an error; cancel does not trigger onErrorResume by default.
6. onErrorResume only catches errors from the **pipeline section upstream of its position**. Errors raised by operators placed after it must be handled at another downstream location.

For **Mono<T>**, the fallback can be a successful Mono with a value, Mono.empty, or Mono.error. For **Flux<T>**, the fallback can emit multiple elements. You should not interpret the name onErrorResume as "re-running the same call".

## 3. Syntax and Overloads

Basic forms:

~~~java
Mono<T> recoveredMono = sourceMono
    .onErrorResume(error -> alternativeMono(error));

Flux<T> recoveredFlux = sourceFlux
    .onErrorResume(error -> alternativePublisher(error));
~~~

The function takes a **Throwable** and returns a Publisher with a data type compatible with the source. Reactor provides variants that filter by class or predicate:

~~~java
// Only one exception type and its subclasses.
source.onErrorResume(
    RemoteUnavailableException.class,
    error -> cacheLookup()
);

// Only exceptions matching the predicate.
source.onErrorResume(
    error -> isRecoverable(error),
    error -> cacheLookup()
);

// Classify multiple cases manually.
source.onErrorResume(error -> {
    if (error instanceof TimeoutException) {
        return cachedData();
    }
    if (error instanceof RateLimitedException) {
        return alternateRegion();
    }
    return Mono.error(error);
});
~~~

These examples are snippets requiring definitions for **RemoteUnavailableException**, **RateLimitedException**, data access functions, and importing **java.util.concurrent.TimeoutException**. When you do not want to recover from an error, you can **return Mono.error(error)** to preserve the original error. If you only want to turn a Throwable into another business error, **onErrorMap** is usually more appropriate.

**Choose the smallest possible scope.** An unfiltered onErrorResume can accidentally turn authentication, validation, or programming errors into fallback results, making debugging hard and even violating access-control contracts.

## 4. Distinguishing Value Results, Empty, and Errors

This is the most important distinction when designing fallbacks:

| Primary source | Signal | Does onErrorResume run? | Result |
| --- | --- | --- | --- |
| **Mono.just("ok")** | onNext + onComplete | No | Value ok |
| **Mono.empty()** | onComplete, no onNext | No | Empty result |
| **Mono.error(e)** | onError | Yes, if error matches | Data/complete/error from fallback |
| **Flux** emits A, B then errors | A, B, onError | Yes | A, B then fallback data |
| **Mono.never()** | No terminal | No | Waits, unless cancelled/timed out |
| **cancel()** from downstream | Cancellation request | Not by default | Stops processing per cancel contract |

An empty result **is not an error**:

~~~java
Mono<String> value = Mono.<String>empty()
    .onErrorResume(error -> Mono.just("backup"));

// Value still completes empty, does not return "backup".
~~~

To have a fallback **when empty**, use **switchIfEmpty**:

~~~java
Mono<String> value = source
    .switchIfEmpty(Mono.defer(() -> loadCache()));
~~~

If you want to handle both situations distinctly:

~~~java
Mono<String> value = source
    .onErrorResume(RecoverableException.class, error -> loadCache())
    .switchIfEmpty(Mono.defer(() -> loadCache()));
~~~

Think carefully about calling the cache twice: if the primary source errors, the first fallback calls the cache, and if the cache completes empty, **switchIfEmpty placed after it may call the cache a second time**. When you want only a single cache access, redesign the flow with an explicit contract or place the empty-handling branch before the recovery branch.

**Mono.empty** is allowed to mean "no resource". **Mono.error** means "query could not be executed". Do not turn every empty case into a technical error just so you can use onErrorResume.

## 5. Business Example: Remote Fails, Read Cache

Suppose a system reads product information from a primary service, with a local cache allowed to serve stale data:

~~~java
public Mono<Product> findProduct(String id) {
    return remoteProductClient.get(id)
        .onErrorResume(
            RemoteUnavailableException.class,
            error -> productCache.findById(id)
        );
}
~~~

Assume the **Product** type and dependencies are already defined; both access methods return Mono<Product>.

Control flow:

~~~text
remoteProductClient.get(id)
     ├─ onNext(Product) + onComplete ──────────> Product from remote
     ├─ onComplete (empty) ────────────────────> Empty, no fallback
     └─ onError(RemoteUnavailableException)
                          │
                          ▼
                  productCache.findById(id)
                        ├─ onNext(Product) → Product from cache
                        ├─ onComplete empty → No fallback data available
                        └─ onError        → Cache error goes downstream
~~~

This is the reactive model of the idea:

~~~java
try {
    return remoteBlockingCall(id);
} catch (RemoteUnavailableException e) {
    return cacheBlockingCall(id);
}
~~~

The second example describes an **imperative, blocking** approach, not an implementation for an asynchronous pipeline. In Reactor, many errors only happen **at subscribe time**, after the Mono object has been created. Therefore, a try/catch around a call returning Mono cannot replace onErrorResume.

## 6. Only Fall Back for Recoverable Errors

| Error | Should you usually switch sources? | Reason |
| --- | --- | --- |
| Data read timeout, transient connection failure | Possibly, if cache/backup is valid | Primary source temporarily unavailable |
| HTTP 503 from a read service | Possibly, depending on SLA and data age | Can serve in degraded mode |
| HTTP 401/403 | Usually no | Must preserve authentication and authorization policy |
| Invalid input validation | No | Fallback hides caller mistakes |
| Data normally does not exist | Depends on contract, usually empty/404 | Do not mistake it for a remote outage |
| NullPointerException from a bug | Should not | Easily hides programming bugs |
| Write error with unclear commit state | Requires dedicated design | Can cause duplicate writes or consistency violations |

Illustrative snippet using a predicate:

~~~java
Mono<Order> result = remote.find(id)
    .onErrorResume(
        error -> error instanceof TimeoutException
              || error instanceof ConnectException,
        error -> cache.find(id)
    );
~~~

This is a hypothetical snippet requiring imports for **java.util.concurrent.TimeoutException**, **java.net.ConnectException**, and application types. The actual exception may be wrapped by the HTTP client in another exception type. When writing production predicates, base them on the exact Throwable types the library actually emits, including the cause if the library contract specifies it.

Do not use a blanket **onErrorResume(error -> Mono.empty())** statement just to make the system "report no errors". If the caller needs to know the query failed, returning Mono.empty can be misinterpreted as non-existent data.

## 7. Fallback Source Is Lazy and Has Its Own Lifecycle

### 7.1. When is backup called?

~~~java
Mono<String> result = remote()
    .onErrorResume(error -> loadBackup());
~~~

The **loadBackup** function inside the lambda is only called after upstream reports an error. It does not run when remote succeeds.

If **constructing** the Publisher itself has side effects, you can use **Mono.defer** to ensure the action happens when the fallback is subscribed:

~~~java
Mono<String> result = remote()
    .onErrorResume(error ->
        Mono.defer(() -> loadBackup())
    );
~~~

**Mono.just(expensiveCall())** executes **expensiveCall** immediately when the Mono creation statement is evaluated; **Mono.fromCallable(this::expensiveCall)** defers the computation until subscribe. For blocking I/O, choose an appropriate scheduler (e.g., boundedElastic for blocking work) so you do not block WebFlux event-loop threads.

### 7.2. Fallbacks can fail

~~~java
Mono<String> result = remote()
    .onErrorResume(error -> cache())
    .onErrorResume(error -> secondRegion());
~~~

If remote fails, cache is subscribed. If cache also fails, **the second onErrorResume** is triggered and switches to secondRegion. **The first onErrorResume does not catch errors from its own fallback**, so another handling operator downstream is needed if you want an additional recovery tier.

If all paths fail, you must eventually propagate a meaningful error to the caller; do not build an infinite chain of fallbacks. When you need to preserve both the original error and backup error, record them in logs/traces or design an exception containing the appropriate cause and context.

### 7.3. Fallbacks can be empty or emit multiple values

~~~java
Mono<String> optional = remote()
    .onErrorResume(RecoverableException.class,
        error -> Mono.empty());

Flux<String> stream = primaryFlux()
    .onErrorResume(error -> Flux.just("backup-A", "backup-B"));
~~~

The first case means the application **intentionally accepts** losing data on classified errors and returns an empty success. In the second case, if primaryFlux already emitted X, Y before failing, downstream sees **X, Y, backup-A, backup-B** according to demand; onErrorResume does not erase X and Y emitted earlier.

## 8. Error-Catching Scope in Flux: Outside the Chain or Inside Each Item

This difference easily causes serious bugs. Suppose you receive a list of identifiers and run a query for each identifier.

**Placed outside concatMap:**

~~~java
Flux.fromIterable(ids)
    .concatMap(id -> remote.find(id))
    .onErrorResume(error -> fallbackFeed());
~~~

When one request fails, **the entire chain before onErrorResume** has terminated with an error. onErrorResume subscribes to fallbackFeed and **does not go back to process the remaining ids** from the source Flux. It keeps the results already sent before the error.

**Placed inside each inner:**

~~~java
Flux.fromIterable(ids)
    .concatMap(id ->
        remote.find(id)
            .onErrorResume(
                RecoverableException.class,
                error -> cache.find(id)
            )
    );
~~~

If one id fails with a recoverable error, the inner for that id switches to cache, completes, and then concatMap moves on to the next id. This is the right approach for independent operations that each have their own fallback. If the cache returns empty, the number of output results may be fewer than the number of ids. If the cache also fails or the exception does not match, the pipeline can still terminate with an error.

With **flatMap**, inners can run concurrently and result ordering is not guaranteed. With **concatMap**, each inner completes before moving to the next inner, so item order is preserved. **Where recovery is placed matters more than just knowing operator names.**

Do not manually call subscribe inside a mapper:

~~~java
// Wrong task coordination: the inner subscription is detached.
return ids.concatMap(id -> {
    remote.find(id).subscribe(this::record);
    return Mono.just(id);
});
~~~

Here concatMap only waits for Mono.just(id), not remote.find(id), and remote errors can escape the pipeline. Better to **return the Publisher containing all the work**, then attach onErrorResume to that inner itself.

## 9. Comparison with retry, switchIfEmpty, and Other Error Operators

| Operator | When triggered | Behavior |
| --- | --- | --- |
| **onErrorResume** | Error from upstream | Subscribes to a fallback Publisher |
| **onErrorReturn** | Matching error | Returns a fixed value |
| **onErrorComplete** | Matching error | Turns error into onComplete, no new data |
| **onErrorMap** | Matching error | Transforms exception, continues error path |
| **doOnError** | Error passes operator position | Observes/logs; does not recover |
| **retry / retryWhen** | Error from upstream | Re-subscribes upstream; may repeat side effects |
| **switchIfEmpty** | Source completes empty | Subscribes to another Publisher |
| **defaultIfEmpty** | Source completes empty | Emits a default value |
| **timeout** | Exceeds deadline condition | Emits timeout error or uses fallback overload |

Examples:

~~~java
Mono<String> a = remote().onErrorReturn("default");

Mono<String> b = remote().onErrorResume(
    error -> cache()
);

Mono<String> c = remote().switchIfEmpty(
    Mono.defer(() -> cache())
);

Mono<String> d = remote().onErrorMap(
    error -> new DomainException("lookup failed", error)
);
~~~

Methods and types in the snippet are hypothetical. If you need to **retry remote** on transient errors, choose a bounded retry; if you want to **switch sources**, choose onErrorResume; if you want **a single static default result**, onErrorReturn is cleaner; if the source is **empty**, switchIfEmpty is the right choice.

## 10. Combining timeout and retry Before Fallback

A common policy: wait for remote within a limit, retry in a controlled way, and only then fall back to cache.

~~~java
Mono<Data> result = remote.find(id)
    .timeout(Duration.ofSeconds(2))
    .retryWhen(
        Retry.backoff(2, Duration.ofMillis(100))
            .filter(this::isTransientFailure)
    )
    .onErrorResume(
        error -> shouldUseCache(error),
        error -> cache.find(id)
    );
~~~

This is a snippet in a service with **Data**, remote/cache, and hypothetical predicate methods; imports **java.time.Duration** and **reactor.util.retry.Retry**.

- **timeout** causes a single upstream subscription to emit an error if it exceeds the deadline.
- **retryWhen** can re-subscribe upstream on matching errors, up to **two retries** after the initial attempt. Side effects and idempotency must be evaluated.
- Once retry stops with an error, **onErrorResume** decides whether to switch to cache or keep the error path.
- **Retry exhaustion** may wrap the exception in a retry-exhausted type. A predicate checking only TimeoutException directly **may no longer match**. Verify the actual exception, use Reactor contracts like **Exceptions.isRetryExhausted** and the cause, or configure **onRetryExhaustedThrow** to define the desired final error.
- If the cache also fails, the cache error continues downstream unless there is another handler.

**Operator order changes the result.** If onErrorResume sits **before** retry and turns the error into successful cache data, retry will not be triggered. If retry sits **after** the fallback, it can re-subscribe the pipeline when the fallback fails. Write the order according to business logic rather than assembling operators by habit.

Timeout sends a cancellation request to active upstream work, but does not guarantee external operations have stopped or rolled back. For write transactions, only retry and fall back when an explicit idempotency policy is in place.

## 11. Observing the Original Error and Degraded Mode

Once a fallback succeeds, downstream no longer receives the original error. Therefore, **doOnError** placement is critical:

~~~java
Mono<User> result = remote.find(id)
    .doOnError(error -> logPrimaryFailure(id, error))
    .onErrorResume(error -> {
        countFallbackAttempt(id, error);
        return cache.find(id);
    })
    .doOnError(error -> logUnrecoveredFailure(id, error))
    .doFinally(signal -> recordTerminalSignal(signal));
~~~

Logging functions, metrics, and service are illustrative components.

- **doOnError before onErrorResume** sees the original remote error.
- The **onErrorResume** callback reports when the fallback is chosen.
- **doOnError after onErrorResume** sees remaining errors, such as when the cache also fails; when recovery succeeds, it **does not** see the remote error.
- **doFinally** sees the termination reason at the observation point, including onComplete, onError, or cancel.
- Mono's **doOnSuccess** receives a null argument when the Mono completes empty; this is not onNext(null).

Metrics to consider: remote request count, remote errors by type, fallback count, fallback success rate, fallback empty count, fallback errors, fallback latency, and rate of responses using stale data. Do not treat Mono.empty's onComplete as having retrieved valid data.

If the caller needs to know which source the result came from, model it transparently:

~~~java
record SourcedUser(User user, String source) {}

Mono<SourcedUser> found = remote.find(id)
    .map(user -> new SourcedUser(user, "PRIMARY"))
    .onErrorResume(
        RecoverableException.class,
        error -> cache.find(id)
            .map(user -> new SourcedUser(user, "CACHE"))
    );
~~~

This snippet depends on User, remote/cache, and application exceptions. A result type with a source field prevents cached content from being presented as fresh data. Whether to expose source info in the HTTP response or only record metrics depends on business and security requirements.

## 12. Complete Java 17+ Example, Runnable with Maven

The example demonstrates six cases: remote succeeds; remote errors and switches to cache; remote empty; error type ineligible for fallback; per-item fallback; and first fallback errors requiring switching to a second source.

Structure:

~~~text
onerrorresume-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── OnErrorResumeDemo.java
~~~

File **pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>onerrorresume-demo</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-core</artifactId>
      <version>3.6.6</version>
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

File **src/main/java/OnErrorResumeDemo.java**:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class OnErrorResumeDemo {

    static Mono<String> primary(String key) {
        return Mono.defer(() -> {
            System.out.println("primary " + key);
            return switch (key) {
                case "ok" -> Mono.just("remote-ok");
                case "down" -> Mono.<String>error(
                    new IllegalStateException("service down")
                );
                case "missing" -> Mono.<String>empty();
                case "bad" -> Mono.<String>error(
                    new IllegalArgumentException("invalid input")
                );
                default -> Mono.<String>error(
                    new IllegalStateException("unknown")
                );
            };
        });
    }

    static Mono<String> cache(String key) {
        return Mono.defer(() -> {
            System.out.println("fallback " + key);
            return Mono.just("cache-" + key);
        });
    }

    public static void main(String[] args) {
        System.out.println("=== 1. Primary success ===");
        primary("ok")
            .onErrorResume(
                IllegalStateException.class,
                error -> cache("ok")
            )
            .doOnNext(System.out::println)
            .block();

        System.out.println("=== 2. Primary error ===");
        primary("down")
            .onErrorResume(
                IllegalStateException.class,
                error -> cache("down")
            )
            .doOnNext(System.out::println)
            .block();

        System.out.println("=== 3. Empty is not error ===");
        primary("missing")
            .onErrorResume(error -> cache("missing"))
            .doOnSuccess(value ->
                System.out.println("result=" + value)
            )
            .block();

        System.out.println("=== 4. Error type does not match ===");
        primary("bad")
            .onErrorResume(
                IllegalStateException.class,
                error -> cache("bad")
            )
            .onErrorResume(error -> {
                System.out.println(
                    "unhandled " + error.getClass().getSimpleName()
                );
                return Mono.empty();
            })
            .block();

        System.out.println("=== 5. Per-item recovery ===");
        Flux.just("ok", "down", "ok")
            .concatMap(key ->
                primary(key)
                    .onErrorResume(
                        IllegalStateException.class,
                        error -> cache(key)
                    )
            )
            .doOnNext(System.out::println)
            .blockLast();

        System.out.println("=== 6. Backup also fails ===");
        Mono.<String>error(
                new IllegalStateException("primary offline")
            )
            .onErrorResume(error ->
                Mono.error(
                    new UnsupportedOperationException("backup offline")
                )
            )
            .onErrorResume(
                UnsupportedOperationException.class,
                error -> Mono.just("secondary-backup")
            )
            .doOnNext(System.out::println)
            .block();
    }
}
~~~

Run from the directory containing **pom.xml** with **JDK 17+** and Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=OnErrorResumeDemo
~~~

**Expected stdout:**

~~~text
=== 1. Primary success ===
primary ok
remote-ok
=== 2. Primary error ===
primary down
fallback down
cache-down
=== 3. Empty is not error ===
primary missing
result=null
=== 4. Error type does not match ===
primary bad
unhandled IllegalArgumentException
=== 5. Per-item recovery ===
primary ok
remote-ok
primary down
fallback down
cache-down
primary ok
remote-ok
=== 6. Backup also fails ===
secondary-backup
~~~

Explanation:

1. For **ok**, the fallback lambda is not called. Because the source uses **Mono.defer**, the primary line appears when subscription actually happens.
2. For **down**, IllegalStateException matches the error-type filtering overload, so cache is subscribed and returns **cache-down**.
3. For **missing**, Mono.empty completes with an empty success; fallback does not run. **doOnSuccess** receives **null**, but there is no onNext(null).
4. For **bad**, IllegalArgumentException does not match IllegalStateException; cache does not run. The next handler prints the exception name and converts it to empty **only for CLI demonstration**. In a real application, validation errors should be returned to the caller per policy.
5. With the three-item sequence, the fallback sits inside concatMap. When the second item is recovered, the third item is still processed, preserving input order.
6. The first fallback emits UnsupportedOperationException; only the second onErrorResume operator handles that new error and returns **secondary-backup**.

All sources in the program are synchronous and do not use sleep, so stdout ordering is stable. **block()** and **blockLast()** are only used in the CLI application's main method to observe results; they are **not suitable on a Spring WebFlux event loop**.

## 13. Applying with WebClient in Spring WebFlux

Suppose an endpoint reads a profile from an external service. Only when remote returns **HTTP 5xx** is the cache allowed to be used:

~~~java
@GetMapping("/profiles/{id}")
public Mono<Profile> getProfile(@PathVariable String id) {
    return webClient.get()
        .uri("/profiles/{id}", id)
        .retrieve()
        .bodyToMono(Profile.class)
        .doOnError(error -> recordPrimaryFailure(id, error))
        .onErrorResume(
            error -> error instanceof WebClientResponseException response
                  && response.getStatusCode().is5xxServerError(),
            error -> profileCache.findById(id)
        );
}
~~~

This is a **controller snippet**, with hypothetical dependencies **webClient**, **profileCache**, type **Profile**, and method **recordPrimaryFailure**. Requires importing Spring WebFlux's **WebClientResponseException** and the corresponding MVC/WebFlux annotations.

Note:

- With **retrieve()**, HTTP 4xx/5xx are converted into WebClientResponseException errors by default unless the application changes response-handling configuration.
- The predicate above only recovers for **5xx** responses. A connection failure may be a different exception type; if you want to catch network errors, add an intentional condition.
- HTTP **401/403** do not fall back automatically, preserving the access-control error path.
- If the cache returns Mono.empty, downstream completes empty; how that maps to an HTTP status must be defined by the endpoint contract.
- If the cache errors, the new error is handled by the framework through the pipeline.
- The controller **returns Mono** to Spring without calling subscribe itself. The framework owns the HTTP request's subscription lifecycle.

### Do not call subscribe manually to handle fallbacks

~~~java
// Avoid: loses connection to the response and error-reporting mechanism.
public Mono<Profile> bad(String id) {
    remote.find(id).subscribe(
        value -> updateCache(value)
    );
    return profileCache.findById(id);
}
~~~

The snippet above illustrates an architectural error; **updateCache** and the dependencies are hypothetical. Calling subscribe starts a detached subscription, so the HTTP pipeline does not wait for remote and cannot manage errors or cancellation of the side task.

Instead:

~~~java
public Mono<Profile> good(String id) {
    return remote.find(id)
        .onErrorResume(
            RecoverableException.class,
            error -> profileCache.findById(id)
        );
}
~~~

When you need to synchronize the cache after a successful read, you can chain **flatMap** into the same pipeline and explicitly model both the success and error paths.

## 14. Safety Boundaries: Writing Data, Stale Cache, and External Failures

onErrorResume **is not a transaction or rollback**. If a POST operation to remote times out, remote may have committed before losing the connection. In that case, switching to a backup system to perform the same write operation risks duplicate writes.

Implementation rules:

1. For **read operations**, define maximum acceptable cache staleness, access permissions, and compatibility of backup data.
2. For **write operations**, require an idempotency key, clear commit state, or a compensating workflow before retrying/falling back.
3. Do not use **Mono.empty()** to hide errors of operations that must succeed in writing.
4. Set separate timeouts for primary and backup; a hanging backup can still keep the entire request from finishing.
5. Account for **many concurrent requests failing over to backup** when the primary source has an outage, overloading the backup system.
6. When primary and backup share a common dependency, fallback does not necessarily improve resilience.
7. Cancellation/timeout in Reactor does not prove that work in the network or external database was undone.
8. If using a cache containing sensitive data, re-check authorization on every request; do not treat cache as a bypass around access policies.

To observe degraded mode, report fallback rate, data age, and fallback errors. A successful HTTP response from cache can be helpful to users, yet it remains a signal for operations to inspect the remote service.

## 15. Backpressure and Cancellation When Switching Sources

When onErrorResume switches to a fallback Flux, data must still obey the final Subscriber's **request(n)**. Items already emitted from the primary source before the error have consumed part of the demand. The fallback must not ignore the remaining demand and emit freely.

Some scenarios:

- Downstream has no remaining demand: the fallback may wait for the next request before emitting onNext.
- Downstream cancels before primary errors: there is no onError, so the fallback is not triggered.
- Downstream cancels after fallback starts: the fallback subscription is requested to cancel; this does not necessarily stop external side effects immediately.
- Fallback errors: the fallback's onError propagates unless there is another handler downstream.
- Fallback never completes: the pipeline may wait indefinitely without a timeout/cancellation.

Example timeout per branch:

~~~java
Mono<Result> result = primary()
    .timeout(Duration.ofSeconds(2))
    .onErrorResume(
        TimeoutException.class,
        error -> backup()
            .timeout(Duration.ofSeconds(1))
    );
~~~

This is a snippet with hypothetical type Result and methods primary/backup. If backup also times out, the second timeout error is reported downstream. If you need a total deadline for the entire operation, place a time-limiting mechanism at the appropriate boundary of the whole pipeline rather than assuming SLA equals the sum of per-step deadlines.

## 16. Common Mistakes

| Misconception or symptom | Accurate understanding |
| --- | --- |
| onErrorResume makes upstream continue after the failed item | Upstream has already terminated and is **replaced by another Publisher** |
| onErrorResume handles Mono.empty | No, switchIfEmpty is needed |
| onErrorResume is like retry | No, retry **re-subscribes upstream**, whereas onErrorResume switches sources |
| onErrorResume catches all errors at any position | Only errors upstream of the operator; placement matters |
| onErrorResume outside concatMap helps process the next item | No; the old concatMap source already errored. Put recovery inside the inner if items need independent handling |
| Cache returns empty but is reported as loaded successfully | Empty is a distinct outcome; requires explicit HTTP/business policy |
| onErrorResume automatically catches errors from its own fallback | No; another handler downstream is needed |
| doOnError after recovery sees the primary error | If recovery succeeds, the primary error was already handled before this point |
| Falling back on 401/403 is harmless | Can violate access control; errors must be classified |
| onErrorResume(error -> Mono.empty()) is always safe | Easily hides errors that must be reported |
| Timeout proves remote did not write | No; commit may have already happened |
| Calling subscribe in a controller and returning another Mono | Detached subscription; framework does not automatically wait for that task |
| Fallback is guaranteed to be faster | Can be slow, hang, or overload; must measure latency and apply limits |
| retryWhen keeps the original exception type when retries run out | Not certain; may be a retry-exhausted wrapper |
| Subscription cancellation triggers fallback | Cancel is not onError |

## 17. Self-Check and Exercises

**Question 1.** Does Mono.just("OK").onErrorResume(e -> backup()) call backup?  
**Answer:** no, because upstream succeeded.

**Question 2.** Does Mono.empty().onErrorResume(e -> backup()) produce a backup result?  
**Answer:** no, because empty is an empty success. Use switchIfEmpty if the goal is a backup when empty.

**Question 3.** A Flux emits A, B and then errors, and the fallback is Flux.just(C,D). What does downstream receive?  
**Answer:** A, B, C, D and then complete, if the fallback succeeds and there is sufficient demand.

**Question 4.** In [1,2,3], querying id 2 errors. Does recovery placed outside concatMap run id 3?  
**Answer:** no. If you want to keep processing, place appropriate recovery inside the Publisher for each id.

**Question 5.** If the backup also fails, does the first onErrorResume automatically retry?  
**Answer:** no. The backup error propagates downstream; switching to a third source requires another handler.

**Question 6.** When should the original error be preserved instead of returning cache?  
**Answer:** when the error is non-recoverable such as validation or authentication/authorization, or when cached data is ineligible for use.

**Exercise A:** Modify the example in section 12, adding **switchIfEmpty(Mono.defer(() -> cache("missing")))** for case 3. Observe the fallback missing line and the value cache-missing.

**Exercise B:** Move onErrorResume in case 5 outside concatMap. Replace the fallback with Flux.just("global-backup") and check whether the third item from primary is executed.

**Exercise C:** Place doOnError before and after onErrorResume, make remote fail while cache succeeds. Record which position receives the primary error.

**Exercise D:** Add a timeout, bounded retryWhen, and fallback. Check the final exception when retries are exhausted and ensure the fallback predicate matches the actual error class.

## 18. References

- Reactor Reference Guide — Handling Errors / Fallback Method: https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html
- Reactor Core — Mono API: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html
- Reactor Core — Flux API: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html
- Reactor Reference Guide — Operator Choice: https://projectreactor.io/docs/core/release/reference/apdx-operatorChoice.html
- Spring Framework — WebClient: https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html
- Reactive Streams JVM Specification: https://github.com/reactive-streams/reactive-streams-jvm
