# Building a ReactiveHealthIndicator Without Blocking Reactive Threads

A health endpoint often makes calls to a database, cache, or external service. In a reactive application, if a check holds onto a processing thread waiting for I/O, the very endpoint meant to observe health can degrade the application's serving capacity.

`ReactiveHealthIndicator` returns `Mono<Health>`, yet that return type alone does not guarantee the work inside is non-blocking. You must design **the data source, execution timing, scheduler, time limits, and error-handling path**.

This lesson uses Java 21, Spring Boot 3.3.x, and Reactor 3.6.x. The standalone runner pins Boot 3.3.0, Reactor 3.6.6, and Spring Framework 6.1.8 to verify the examples.

## 1. The Reactive Contract of a Health Check

`ReactiveHealthIndicator` has the primary method:

```java
Mono<Health> health();
```

This is an interface signature, not a standalone program. `Mono` represents a sequence that can emit at most one value, complete without a value, or terminate with an error. [Boot 3.3 ReactiveHealthIndicator API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/ReactiveHealthIndicator.html).

For an indicator you write yourself, clearly define outcomes for common cases:

| Observed outcome | Illustrative policy in this lesson |
| --- | --- |
| Dependency satisfies check criteria | Emit a Health UP |
| Dependency returns failing result | Emit a Health DOWN |
| Publisher completes with no data | Emit UNKNOWN with reason EMPTY_REPLY |
| Time budget exhausted | Emit DOWN with reason PROBE_TIMEOUT |
| Check emits an error | Emit DOWN with a curated reason |
| Caller cancels subscription | Propagate cancellation upstream, clean up resources per source contract |

The UNKNOWN policy for an empty result is a choice of this example. Another system might treat it as DOWN. What matters is making a deliberate choice instead of accidentally returning `Mono.empty()` and wondering why a health result is missing.

Actuator's reactive infrastructure combines contributors to produce the response. An indicator should return a publisher for that infrastructure to manage subscription, rather than triggering detached work on its own. [Reactive health in Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health.reactive-health-indicators).

## 2. Why Does Blocking a Reactive Thread Have Such a Large Impact?

In an event-loop processing model, a limited number of threads can serve many connections. When I/O data is not yet ready, work resumes when events arrive rather than holding the thread in a waiting state.

If a callback on that thread performs a synchronous JDBC call, slow file read, or `Thread.sleep`, the thread is held. Other tasks needing that same thread must wait even though they are unrelated to the health check.

```text
Genuine reactive API:
send request → yield control → receive signal → build Health

Synchronous API placed directly on a reactive thread:
send request → hold thread waiting for I/O → receive result → build Health
```

Operations that typically require careful inspection:

- Synchronous network calls.
- JDBC or synchronous SDKs.
- File reads/writes that can block.
- `block()`, `Future.get()`, `join()`, or lock waits.
- Heavy computation inside `map` or result-receiving callbacks.
- Logging or utility calls with synchronous I/O on the execution path.

Using `map` is not inherently wrong. Turning a boolean into `Health` or adding a few diagnostic fields is short work suitable to run directly in the chain. Evaluate the actual work invoked inside the callback.

## 3. Creating `Mono` at the Right Time

There are three moments to distinguish:

1. Calling the `health()` method to obtain a publisher.
2. The infrastructure subscribing to the publisher.
3. The data source and data-processing callbacks executing.

In the following illustrative snippets, `syncClient.ping()` is an existing synchronous I/O call of the application.

### 3.1. `Mono.just` Does Not Defer a Call Placed in Its Argument

Problematic snippet:

```java
return Mono.just(syncClient.ping());
```

Java must evaluate the argument before calling `Mono.just`. Therefore, `ping()` has already run and may block right when creating the `Mono`.

Chaining a scheduler afterward also cannot move a call that has already finished onto another thread.

### 3.2. `defer` Delays Source Creation, but Does Not Automatically Switch Schedulers

The following snippet defers the call until subscription:

```java
return Mono.defer(() -> Mono.just(syncClient.ping()));
```

However, `ping()` still runs synchronously on whichever thread executes the supplier. `defer` does not turn a blocking API into a non-blocking API.

### 3.3. `fromCallable` Is Suitable for Wrapping Synchronous Operations

```java
return Mono.fromCallable(syncClient::ping)
        .subscribeOn(Schedulers.boundedElastic());
```

Here, the operation is deferred and source execution is scheduled on a scheduler suited for blocking work. The task remains blocking in nature, yet it is isolated from the reactive processing threads that must be protected.

The snippets above illustrate call placement and schedulers, not a complete indicator. [Reactor recipe for wrapping blocking calls](https://projectreactor.io/docs/core/3.6.6/reference/#faq.wrap-blocking).

## 4. Prefer Genuine Reactive APIs When Available

If a client already returns `Mono` and performs non-blocking I/O, compose that publisher:

```text
Client's publisher
    → evaluate result
    → convert to Health
    → apply time budget
    → convert errors into results per policy
```

There is no need to call `block()` to extract an intermediate result and wrap it back into `Mono.just`.

If the transformation step only returns `Health`, using `map` is appropriate. If the next step returns another publisher, compose with an appropriate operator such as `flatMap`; avoid accidentally creating a `Mono<Mono<Health>>` structure.

For a source that completes without a value, `map` is not invoked. This is important when the source is `Mono<Void>`: to produce `Health` after the operation completes successfully, you can use `thenReturn(health)`. Beforehand, understand what "completing successfully" proves under the operation's contract.

[Mono operator semantics in Reactor 3.6.6](https://projectreactor.io/docs/core/3.6.6/api/reactor/core/publisher/Mono.html).

## 5. An Indicator Handling Empty Results, Errors, and Timeouts

The runnable example in a later section has a `Probe` interface returning `Mono<Boolean>` and a `DependencyIndicator` class executing the chain:

```text
Mono.defer(probe::check)
    → map result to Health
    → switchIfEmpty per policy
    → timeout per budget
    → handle TimeoutException
    → handle remaining errors
```

Rationale behind each decision:

- `defer` re-invokes publisher creation for each subscription and routes exceptions thrown in the supplier into the chain's error path.
- `map` performs only short work to build the result.
- `switchIfEmpty` handles completing without a boolean.
- `timeout` prevents a silent source from keeping the request waiting indefinitely.
- The timeout branch precedes the generic error branch so its specific reason is preserved.
- Each outcome creates a fresh Builder and includes only curated diagnostic data.

Using `defer` does not exempt `probe.check()` from returning control quickly. If the supplier itself performs blocking I/O before returning a `Mono`, you must still fix the source or isolate the blocking portion with a scheduler.

The example does not expose verbatim exception messages in health because messages may contain internal URLs or data. The reason codes are conventions of this lesson, not mandatory Boot fields.

## 6. `WebClient`: Checking HTTP with a Non-Blocking Chain

The class below uses `WebClient` to call `/internal/ping` of an inventory service. The example's policy accepts HTTP 2xx codes; other codes produce DOWN.

This check only proves the selected HTTP condition. If the service's contract requires verifying response body content as well, read and evaluate the body accordingly.

File `InventoryReactiveHealthIndicator.java`:

```java
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.ReactiveHealthIndicator;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Component("inventory")
public final class InventoryReactiveHealthIndicator
        implements ReactiveHealthIndicator {

    private static final Duration BUDGET = Duration.ofMillis(500);
    private final WebClient client;

    public InventoryReactiveHealthIndicator(
            WebClient.Builder builder,
            @Value("${app.inventory.base-url}") String baseUrl) {
        this.client = builder.clone().baseUrl(baseUrl).build();
    }

    @Override
    public Mono<Health> health() {
        return Mono.defer(() -> client.get()
                        .uri("/internal/ping")
                        .exchangeToMono(response -> {
                            int code = response.statusCode().value();
                            boolean up = response.statusCode().is2xxSuccessful();
                            Health health = (up ? Health.up() : Health.down())
                                    .withDetail("target", "inventory")
                                    .withDetail("reasonCode", up
                                            ? "HTTP_OK" : "HTTP_STATUS_NOT_2XX")
                                    .withDetail("httpStatus", code)
                                    .build();
                            return response.releaseBody().thenReturn(health);
                        }))
                .switchIfEmpty(Mono.fromSupplier(() -> failure("EMPTY_RESPONSE")))
                .timeout(BUDGET)
                .onErrorResume(TimeoutException.class, error ->
                        Mono.just(failure("PROBE_TIMEOUT")))
                .onErrorResume(error ->
                        Mono.just(failure("REQUEST_FAILED")));
    }

    private static Health failure(String reason) {
        return Health.down()
                .withDetail("target", "inventory")
                .withDetail("reasonCode", reason)
                .withDetail("timeoutMillis", BUDGET.toMillis())
                .build();
    }
}
```

### Why Does This Chain Preserve Proper Reactive Handling?

**No `block` or `subscribe` inside `health`.** The method returns the publisher for Actuator's infrastructure to subscribe to.

**Source is created upon subscription.** `Mono.defer` wraps request creation for each subscription.

**Explicit policy per HTTP code.** A 503 response from the dependency becomes DOWN with detail `httpStatus=503`; "received an HTTP response" is not confused with "passed the check."

**Unused bodies are not retained.** The example only needs the status code, so it releases the body and then uses `thenReturn` after the completion signal.

**Bounded time and error-handling path.** The chain aims to produce a result with a clear reason rather than letting ordinary errors escape unintentionally.

`exchangeToMono` supports handling based on status code. When content is unneeded, consume or release it properly within its lifecycle to manage client resources. [Spring Framework 6.1.8 ClientResponse](https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/web/reactive/function/client/ClientResponse.html).

### Conditions When Integrating into a Spring Boot Application

The class above has `@Component("inventory")`. In a reactive application, place it in a scanned package, have a `WebClient.Builder` provided by application configuration, and declare the target address, for example:

```yaml
app:
  inventory:
    base-url: http://127.0.0.1:9090
```

The address configures a real dependency; it does not automatically launch an inventory service. The `/internal/ping` path should have low cost and cause no business mutations.

The application must genuinely run on the appropriate reactive model. Adding the interface or adding a WebFlux dependency does not automatically prove every existing configuration has switched to reactive.

Details created in code remain subject to health visibility policies and access permissions. Whether details appear over HTTP is a separate configuration question from whether the chain blocks.

## 7. When Only a Synchronous Client Exists: Isolate the Source Properly

A simple adapter, placed inside a class that already imports `Mono` and `Schedulers`, can look like this:

```java
static Mono<Boolean> adaptBlocking(
        java.util.concurrent.Callable<Boolean> operation) {
    return Mono.fromCallable(operation)
            .subscribeOn(Schedulers.boundedElastic());
}
```

This method returns a publisher and does not subscribe itself. When used for an indicator, you still need steps to select status, handle empty sources, enforce timeouts, and handle errors per contract.

### `subscribeOn` and `publishOn` Address Different Positions

`subscribeOn` is typically placed right after `fromCallable` to place source execution onto the desired scheduler. `publishOn` switches the processing context for operators downstream of it; do not rely on placing `publishOn` after a blocking source to protect source work that already executed earlier.

`boundedElastic` serves potentially blocking work with bounded resources. `parallel` or `single` target short non-blocking work; pushing blocking I/O there can starve resources needed by other tasks. [Reactor 3.6.6 Schedulers](https://projectreactor.io/docs/core/3.6.6/api/reactor/core/scheduler/Schedulers.html).

### Bounds Still Must Be Designed

Isolating work does not make resources infinite. If many concurrent probes wait on a slow dependency, queues and workers can still saturate.

When a dedicated scheduler is needed for checks:

- Create and manage the scheduler along the application lifecycle.
- Choose worker and queue limits suited to the load.
- Clean up the dedicated scheduler when the application shuts down.
- Do not create a new scheduler for each health request.
- Do not dispose Reactor's shared schedulers just because one indicator finishes.

Boot has a mechanism that adapts synchronous contributors for reactive environments, and `ReactiveHealthContributor.adapt` is the related API for dynamic registration. Understand the mechanism already used by the infrastructure before adding extra layers of schedulers yourself.

## 8. Timeouts, Errors, and Cancellation Have Different Boundaries

### 8.1. Timeout Bounds Waiting for Signals in the Chain

In the WebClient example, `timeout` sits after obtaining the response and releasing the body. It sits on the path producing the Health result, rather than applying to only a tiny fraction of the check.

Distinguish:

| Limit | What it controls |
| --- | --- |
| Connect timeout | Time to establish connection per client/connector |
| Client read/response timeout | Corresponding I/O activity per client configuration |
| Reactor `timeout` operator | Wait time for signals on the publisher segment beneath that policy |
| Health caller's timeout | How long the external system is willing to wait for the endpoint |

These tiers must align with one another. An indicator finishing right near the caller's threshold may frequently be canceled before the result is received.

### 8.2. Timeout Does Not Guarantee Force-Stopping Every Operation

When the timeout operator triggers, the source is canceled per reactive protocol and the chain can fall back to an alternative result. However, how far actual I/O work stops depends on the client, driver, and the source's cancellation support.

A synchronous call that does not respond to interruption may keep occupying a worker even after the caller received a timeout result. Hence, client-level timeouts, concurrency limits, and appropriate source selection remain necessary.

Similarly, placing `timeout` around a blocking callback does not make that callback non-blocking. The held thread remains a problem to solve.

### 8.3. Cancellation Is Not a New Business Failure

If the caller closes the connection or actively cancels the subscription, there is no need to try sending another Health DOWN to someone who already canceled.

Avoid calling `subscribe()` yourself to spawn background work detached from the original subscription. That makes propagating cancellation, managing errors, and bounding dependency call counts difficult.

If adding `retry`, recalculate the total budget and extra load generated when a dependency is failing. A health check should not trigger an unbounded wave of retries.

## 9. Standalone Verification Program

This section runs with controlled publishers and a fake HTTP client. It does not need to open a port, start a server, or call an external inventory service.

The program verifies:

1. Asynchronous source succeeds.
2. Dependency returns failing result.
3. Source completes empty.
4. Error emitted through the publisher.
5. Exception thrown while creating the publisher.
6. Probe is not called before subscription and is re-invoked per subscription.
7. Timeout propagates cancellation upstream.
8. Caller cancellation reaches the source.
9. Synchronous call is isolated from threads marked non-blocking.
10. WebClient maps an HTTP 503 response to Health DOWN.

### 9.1. Project Files

Prepare JDK 21 and Gradle 8.5:

```text
reactive-health-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/
    ├── ReactiveHealthDemo.java
    └── InventoryReactiveHealthIndicator.java
```

File `settings.gradle`:

```groovy
rootProject.name = 'reactive-health-demo'
```

File `build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.0')
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.projectreactor:reactor-test'
}

application {
    mainClass = 'ReactiveHealthDemo'
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
```

The project uses the `application` plugin to run the demonstration suite in `main`, so `reactor-test` is placed in `implementation`. In a typical application project, tests live in the `test` source set and this dependency normally belongs in `testImplementation`.

File `InventoryReactiveHealthIndicator.java` uses the code in section 6 verbatim. The console program does not start `SpringApplication`; the component annotation does not by itself turn it into a listening server.

### 9.2. Complete Verification Code

File `src/main/java/ReactiveHealthDemo.java`:

```java
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.ReactiveHealthIndicator;
import org.springframework.http.HttpStatus;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

public class ReactiveHealthDemo {
    private static final Duration VERIFY_LIMIT = Duration.ofSeconds(3);

    @FunctionalInterface
    interface Probe {
        Mono<Boolean> check();
    }

    static final class DependencyIndicator implements ReactiveHealthIndicator {
        private final Probe probe;
        private final Duration budget;

        DependencyIndicator(Probe probe, Duration budget) {
            if (probe == null || budget == null
                    || budget.isZero() || budget.isNegative()) {
                throw new IllegalArgumentException("Probe and positive budget required");
            }
            this.probe = probe;
            this.budget = budget;
        }

        @Override
        public Mono<Health> health() {
            return Mono.defer(probe::check)
                    .map(ok -> result(ok, ok ? "PROBE_OK" : "NEGATIVE_REPLY"))
                    .switchIfEmpty(Mono.fromSupplier(() ->
                            Health.unknown()
                                    .withDetail("target", "inventory")
                                    .withDetail("reasonCode", "EMPTY_REPLY")
                                    .build()))
                    .timeout(budget)
                    .onErrorResume(TimeoutException.class, error ->
                            Mono.just(Health.down()
                                    .withDetail("target", "inventory")
                                    .withDetail("reasonCode", "PROBE_TIMEOUT")
                                    .withDetail("timeoutMillis", budget.toMillis())
                                    .build()))
                    .onErrorResume(error ->
                            Mono.just(result(false, "PROBE_FAILED")));
        }
    }

    static Health result(boolean up, String reason) {
        return (up ? Health.up() : Health.down())
                .withDetail("target", "inventory")
                .withDetail("reasonCode", reason)
                .build();
    }

    static DependencyIndicator indicator(Probe probe) {
        return new DependencyIndicator(probe, Duration.ofSeconds(1));
    }

    static boolean matches(Health health, String status, String reason) {
        return health.getStatus().getCode().equals(status)
                && reason.equals(health.getDetails().get("reasonCode"));
    }

    static void verify(
            String name,
            ReactiveHealthIndicator indicator,
            String status,
            String reason) {
        StepVerifier.create(indicator.health())
                .expectNextMatches(health -> matches(health, status, reason))
                .expectComplete()
                .verify(VERIFY_LIMIT);
        System.out.println(name + "=PASS");
    }

    static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        StepVerifier.withVirtualTime(() ->
                        indicator(() -> Mono.delay(Duration.ofMillis(100))
                                .thenReturn(true)).health())
                .expectSubscription()
                .thenAwait(Duration.ofMillis(100))
                .expectNextMatches(health -> matches(health, "UP", "PROBE_OK"))
                .expectComplete()
                .verify(VERIFY_LIMIT);
        System.out.println("async-up=PASS");

        verify("reported-down", indicator(() -> Mono.just(false)),
                "DOWN", "NEGATIVE_REPLY");
        verify("empty-result", indicator(Mono::empty),
                "UNKNOWN", "EMPTY_REPLY");
        verify("reactive-error", indicator(() ->
                        Mono.error(new IllegalStateException("unavailable"))),
                "DOWN", "PROBE_FAILED");
        verify("synchronous-error", indicator(() -> {
            throw new IllegalStateException("cannot create probe");
        }), "DOWN", "PROBE_FAILED");

        AtomicInteger calls = new AtomicInteger();
        Mono<Health> reusable = indicator(() -> {
            calls.incrementAndGet();
            return Mono.just(true);
        }).health();
        require(calls.get() == 0, "Probe ran before subscription");
        for (int i = 0; i < 2; i++) {
            StepVerifier.create(reusable)
                    .expectNextMatches(health -> matches(health, "UP", "PROBE_OK"))
                    .expectComplete()
                    .verify(VERIFY_LIMIT);
        }
        require(calls.get() == 2, "Each subscription must invoke the probe");
        System.out.println("lazy-per-subscription=PASS");

        AtomicBoolean timeoutCancelled = new AtomicBoolean();
        StepVerifier.withVirtualTime(() ->
                        indicator(() -> Mono.<Boolean>never()
                                .doOnCancel(() -> timeoutCancelled.set(true)))
                                .health())
                .expectSubscription()
                .thenAwait(Duration.ofSeconds(2))
                .expectNextMatches(health -> matches(
                        health, "DOWN", "PROBE_TIMEOUT"))
                .expectComplete()
                .verify(VERIFY_LIMIT);
        require(timeoutCancelled.get(), "Timeout did not cancel the source");
        System.out.println("timeout-cancels-upstream=PASS");

        AtomicBoolean callerCancelled = new AtomicBoolean();
        StepVerifier.create(indicator(() -> Mono.<Boolean>never()
                        .doOnCancel(() -> callerCancelled.set(true))).health())
                .expectSubscription()
                .thenCancel()
                .verify(VERIFY_LIMIT);
        require(callerCancelled.get(), "Caller cancellation was not propagated");
        System.out.println("caller-cancellation=PASS");

        Scheduler eventLoop = Schedulers.newSingle("demo-event-loop");
        Scheduler blockingWorker =
                Schedulers.newBoundedElastic(2, 10, "demo-health-worker");
        try {
            ReactiveHealthIndicator isolated = indicator(() ->
                    Mono.fromCallable(() -> {
                        require(!Schedulers.isInNonBlockingThread(),
                                "Legacy call ran on a non-blocking worker");
                        return true;
                    }).subscribeOn(blockingWorker));

            StepVerifier.create(Mono.defer(() -> {
                        require(Schedulers.isInNonBlockingThread(),
                                "Test did not start on a non-blocking worker");
                        return isolated.health();
                    }).subscribeOn(eventLoop))
                    .expectNextMatches(health -> matches(health, "UP", "PROBE_OK"))
                    .expectComplete()
                    .verify(VERIFY_LIMIT);
            System.out.println("legacy-offloaded=PASS");
        }
        finally {
            eventLoop.dispose();
            blockingWorker.dispose();
        }

        WebClient.Builder fakeClient = WebClient.builder()
                .clientConnector((method, uri, callback) ->
                        Mono.error(new IllegalStateException("Real I/O disabled")))
                .exchangeFunction(request -> Mono.just(
                        ClientResponse.create(HttpStatus.SERVICE_UNAVAILABLE)
                                .body("ignored").build()));
        InventoryReactiveHealthIndicator httpIndicator =
                new InventoryReactiveHealthIndicator(
                        fakeClient, "http://unused.invalid");
        StepVerifier.create(httpIndicator.health())
                .expectNextMatches(health ->
                        matches(health, "DOWN", "HTTP_STATUS_NOT_2XX")
                        && Integer.valueOf(503).equals(
                                health.getDetails().get("httpStatus")))
                .expectComplete()
                .verify(VERIFY_LIMIT);
        System.out.println("webclient-status=PASS");
    }
}
```

### 9.3. Running and Reading Results

In the project directory:

```shell
gradle -q run --console=plain
```

If a wrapper is present, in PowerShell:

```powershell
.\gradlew.bat -q run --console=plain
```

Or on Linux/macOS:

```shell
./gradlew -q run --console=plain
```

Gradle provides the classpath of Spring and Reactor libraries. If invoking `javac`/`java` directly, provide all corresponding dependencies.

Stdout of the program, excluding messages from Gradle or dependency resolution:

```text
async-up=PASS
reported-down=PASS
empty-result=PASS
reactive-error=PASS
synchronous-error=PASS
lazy-per-subscription=PASS
timeout-cancels-upstream=PASS
caller-cancellation=PASS
legacy-offloaded=PASS
webclient-status=PASS
```

Each PASS line is printed only after the corresponding expectations pass. If they fail, the program throws an `AssertionError` or verification error and must not be considered passing.

### 9.4. Key Evidence in the Program

**Virtual time:** `StepVerifier.withVirtualTime` tests timing operators using a controlled scheduler. Publishers with time operators are created inside the supplier so they use the appropriate clock. This tests timeout behavior without real sleeping to wait.

**Lazy source:** the counter stays at 0 after calling `health()`, then increments on each subscription. This is evidence of probe invocation timing in the example, not proof that every external client shares the same behavior.

**Cancellation:** the `never` sources in the lesson carry a `doOnCancel` callback to verify cancellation signals from timeout or the caller. It proves protocol signals reach the fake source; it does not prove an arbitrary driver always stops real resources immediately.

**Scheduler isolation:** the test starts on a worker marked non-blocking by Reactor, while the callable runs on a scheduler meant for blocking work. The sample callable returns quickly; the verification confirms the execution location of the portion that will be replaced by a real synchronous call.

**Fake HTTP:** `exchangeFunction` creates a 503 response in memory. The fake client connector rejects real I/O so the verification does not open dependency connections. This section tests the HTTP-to-Health status mapping policy; it does not yet test networking, TLS, DNS, or connection pooling.

**Test verification timeout:** `verify` has a time limit on the thread running the verification program. The test suite's blocking wait is not a pattern to place inside health on serving threads.

`StepVerifier` lets you express expected signals and trigger verification at the final step. [Reactor testing documentation](https://projectreactor.io/docs/core/3.6.6/reference/#testing).

## 10. What These Verifications Do Not Replace

The demonstration suite proves specific behaviors in chains and schedulers. Before deploying to a real application, verify additional environment-dependent aspects:

- Whether the real client/driver performs non-blocking I/O or has its blocking work properly isolated.
- Whether timeouts and cancellations release resources as expected.
- Whether the HTTP body is read/released across all relevant branches.
- Whether concurrent health calls avoid exhausting workers, queues, or connection pools.
- Whether the endpoint finishes within the budget of the system calling the probe.
- Whether detail visibility permissions are appropriate and diagnostic data contains no secrets.
- Whether rules placing the dependency into health groups match operational goals.

A blocking-call detector such as [BlockHound](https://github.com/reactor/BlockHound) can be added in tests compatible with your version and runtime environment. It is supplementary evidence; you still need to evaluate the real call path and client resource management.

A health check does not need to read lots of data or call an entire expensive business flow just to look thorough. Pick an observation meaningful enough for the operational decision it serves.

## 11. Common Mistakes and Fixes

| Mistake | Why is it a problem? | Fix |
| --- | --- | --- |
| Returning `Mono.just(syncCall())` | The call already ran before creating the Mono | Use a reactive source or `fromCallable` with an appropriate scheduler |
| Wrapping a blocking call in `defer` and assuming it is non-blocking | Only changes timing, not execution thread | Isolate the blocking work itself |
| Calling `block` inside `health` | Holds the thread waiting and breaks publisher composition | Return the composed chain |
| Calling `subscribe` directly inside `health` | Spawns work detached from calling infrastructure | Let the infrastructure own subscription |
| Placing `publishOn` after a blocking source | Does not protect the upstream source portion | Place `subscribeOn` appropriately near the source |
| Running JDBC inside `WebClient`'s `map` | Callback can still block reactive workers | Use a reactive driver or dedicated isolation adapter |
| Ignoring `Mono.empty` | May emit no Health at all | Define an explicit `switchIfEmpty` policy |
| Only calling `map` on `Mono<Void>` | There is no value to run `map` on | Use completion signal like `thenReturn` when the contract fits |
| Having `timeout` without bounding the synchronous client | Work may keep occupying workers | Configure client timeouts and control resources |
| Neglecting unused HTTP bodies | Can mismanage resources | Consume or release per the client API |
| Creating a new scheduler per health call | Increases resource usage and is hard to clean up | Manage schedulers along the application lifecycle |
| Calling `cache` without defining freshness | Stale results can mask new failures | Choose TTL and publisher sharing location intentionally |

If using `cache`, know whether the cache belongs to one publisher or is shared across multiple method calls. Creating a publisher with a fresh `cache` on every health call differs from sharing a TTL-bounded result across multiple requests. You must also publish or understand the acceptable staleness of the observation.

## 12. Practice

1. Change the source to `Mono.just(false)` and explain why that is an observed outcome rather than an `onError` signal.
2. Change the source to `Mono.empty()`. Compare the lesson's UNKNOWN policy with a DOWN policy if the system requires receiving an answer.
3. Remove `switchIfEmpty` in the test build and use `StepVerifier` to observe the chain emitting no Health.
4. Keep the `never` source and vary the time budget. Check the reason code along with the cancellation signal.
5. Replace the fast-returning callable with a real synchronous client in a test environment. Verify the executing worker and the client's own timeout.
6. Change the fake HTTP response from 503 to 204. Predict the status and reason code of `InventoryReactiveHealthIndicator`.
7. Make the fake `exchangeFunction` emit an error, then confirm the `REQUEST_FAILED` branch.
8. Evaluate adding one retry: does total duration still stay within the caller's budget and is the dependency call count bounded?

Cross-check:

- A `false` source produces DOWN with `NEGATIVE_REPLY` per the example policy.
- An `empty` source produces UNKNOWN with `EMPTY_REPLY` if `switchIfEmpty` is kept.
- A `never` source is bounded by `timeout` and produces DOWN with `PROBE_TIMEOUT`.
- HTTP 204 belongs to 2xx and therefore produces UP with `HTTP_OK`, even without a response body.
- Ordinary errors from the HTTP source are curated into `REQUEST_FAILED`; the specific timeout type in the example is `TimeoutException` on the corresponding processing path.

When evaluating a `ReactiveHealthIndicator`, read from the I/O source through to the final `Health`: what can wait, where does it execute, what does each termination mean, and how are resources handled when the caller stops waiting. That reading protects reactive threads and keeps health signals trustworthy both during normal dependency operation and during incidents.
