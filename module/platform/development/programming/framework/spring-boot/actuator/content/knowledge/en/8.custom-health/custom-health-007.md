# Combining Synchronous and Reactive Checks in a WebFlux Application

## 1. WebFlux Does Not Turn Every Library Non-Blocking

A WebFlux application may simultaneously use a legacy SDK that only provides synchronous methods and a new client returning `Mono`. When publishing health, we still need to observe both components. The issue is not merely merging two results into JSON, but **running each check on the appropriate execution mechanism**.

Event-loop threads are used to process many non-blocking tasks. If a check holds onto that thread waiting for synchronous I/O, other requests can be delayed as a result. Changing the return type to `Mono<Health>` does not automatically move blocking code onto another thread.

In this lesson, the application has:

- `legacyStore`: a synchronous check representing a legacy library that may block threads.
- `catalog`: a reactive check representing a client providing asynchronous results.

We keep both contracts true to their nature, letting Actuator adapt the synchronous indicator and aggregate them on the reactive flow. The standalone example uses **Java 21, Spring Boot 3.3.0, and Reactor 3.6.6 managed by this Boot version**.

## 2. Two Contracts Coexisting in the Health Tree

| Contract | Result | Meaning |
| --- | --- | --- |
| `HealthIndicator` | `Health` | Method returns the result directly; may contain synchronous operations. |
| `ReactiveHealthIndicator` | `Mono<Health>` | Result is emitted via a publisher; obtaining it must obey the reactive contract. |
| `ReactiveHealthContributorRegistry` | Named contributors | Component tree used by the reactive health publishing path. |

In a reactive application, Actuator configuration can collect both regular `HealthContributor` beans and `ReactiveHealthContributor` beans. Synchronous contributors are adapted to the reactive contract; the application does not need to rewrite every synchronous indicator just to appear in WebFlux.

With Spring Boot 3.3.0, the adapter for a `HealthIndicator` uses:

```java
Mono.fromCallable(delegate::health)
        .subscribeOn(Schedulers.boundedElastic());
```

This is a mechanism excerpt, not a standalone Java file. `fromCallable` defers the call until a subscriber requests the result; `subscribeOn` schedules that call on a scheduler suited for potentially blocking work. See [Spring Boot 3.3.0 HealthIndicatorReactiveAdapter](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/health/HealthIndicatorReactiveAdapter.java).

Adaptation changes **where the waiting happens**, not turning a synchronous client into non-blocking I/O. When the legacy SDK waits for data, a worker is still occupied. Therefore, wait times, connection limits, and concurrency still need to be controlled.

### Regular Bean Registration and Dynamic Registration Are Two Separate Cases

For beans initialized with the application, declaring one `HealthIndicator` bean and one `ReactiveHealthIndicator` bean is usually sufficient; Actuator configuration performs collection and adaptation. Do not create an extra wrapper bean for the same check just to "make sure there is a reactive one," as this can create duplicate entries or run the check twice.

If actively registering contributors while the application is running, use `ReactiveHealthContributorRegistry`; a synchronous contributor must be converted via `ReactiveHealthContributor.adapt(...)` before registration. This is the rule of [reactive health in Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health.reactive-health-indicators).

Do not choose an implementation solely from a product name like Redis or MongoDB. Some integrations have both synchronous and reactive variants; inspect the actual contributors and configuration conditions of the version in use.

## 3. Four Mistakes That Let Blocking Code Into the Event Loop

The following snippets illustrate a site that already has a `HealthIndicator` variable named `legacy`.

### Calling First and Wrapping in `Mono` Afterward

```java
return Mono.just(legacy.health());
```

`Mono.just`'s argument is evaluated upfront by Java. `legacy.health()` already ran on the calling thread right while constructing the publisher. Adding `publishOn(...)` afterward cannot move a call that has already completed or blocked earlier onto another thread.

### Deferring Without Choosing a Scheduler

```java
return Mono.fromCallable(legacy::health);
```

This snippet defers execution, yet does not choose a worker for blocking work. It may execute on whichever thread subscribes, including the event loop. When you genuinely need to wrap a synchronous call yourself, use `fromCallable(...).subscribeOn(Schedulers.boundedElastic())` or Actuator's adapter.

### Assuming `Mono.defer` Automatically Switches Threads

```java
return Mono.defer(() -> Mono.just(legacy.health()));
```

`defer` delays publisher creation, not a switch for changing schedulers. Its supplier must still be non-blocking if running on a non-blocking thread.

### Calling `block` or `subscribe` Inside a Reactive Indicator

Calling `.block()` can hold the request-serving thread and defeat the purpose of WebFlux. Calling `.subscribe()` and immediately returning another `Health` makes the published result stop waiting for the real check. **Return the complete `Mono<Health>` chain**, so the infrastructure subscribes and awaits signals via the reactive mechanism.

Do not use `publishOn` as a catch-all fix everywhere. It affects signal processing downstream of where the operator is placed; the recommended pattern for blocking synchronous sources is placing `subscribeOn` right after the source. You can cross-check [Reactor's guide on wrapping blocking calls](https://projectreactor.io/docs/core/3.6.6/reference/#faq.wrap-blocking).

## 4. Creating Two Indicators with Distinct Responsibilities

Create a standalone Maven project. Add only the WebFlux starter for the example's web stack, not `spring-boot-starter-web`.

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>
    <groupId>learning</groupId>
    <artifactId>mixed-health-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>21</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 4.1. Synchronous Indicator

File `src/main/java/learning/mixedhealth/LegacyStoreHealthIndicator.java`:

```java
package learning.mixedhealth;

import java.util.Objects;
import java.util.concurrent.Callable;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;

public final class LegacyStoreHealthIndicator implements HealthIndicator {

    private final Callable<Boolean> check;

    public LegacyStoreHealthIndicator(Callable<Boolean> check) {
        this.check = Objects.requireNonNull(check, "check");
    }

    @Override
    public Health health() {
        try {
            return Boolean.TRUE.equals(check.call())
                    ? Health.up().withDetail("reason", "READY").build()
                    : Health.down().withDetail("reason", "NOT_READY").build();
        }
        catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            return Health.down().withDetail("reason", "INTERRUPTED").build();
        }
        catch (Exception ex) {
            return Health.down().withDetail("reason", "CHECK_FAILED").build();
        }
    }
}
```

This remains a synchronous indicator. It does not create threads or wrap `Mono` itself. When collected into Actuator's reactive health tree, the adapter performs the conversion. If other code calls `legacy.health()` directly, that direct call does not get the adapter automatically.

`Callable<Boolean>` is a hook allowing the example to plug in different checks. In a real integration, it can call a legacy SDK configured with timeouts. The indicator must not use a probe that mutates business data.

### 4.2. Reactive Indicator

File `src/main/java/learning/mixedhealth/CatalogReactiveHealthIndicator.java`:

```java
package learning.mixedhealth;

import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.TimeoutException;
import java.util.function.Supplier;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.ReactiveHealthIndicator;

import reactor.core.publisher.Mono;

public final class CatalogReactiveHealthIndicator implements ReactiveHealthIndicator {

    private final Supplier<Mono<Boolean>> check;
    private final Duration timeout;

    public CatalogReactiveHealthIndicator(Supplier<Mono<Boolean>> check, Duration timeout) {
        this.check = Objects.requireNonNull(check, "check");
        this.timeout = Objects.requireNonNull(timeout, "timeout");
        if (timeout.isZero() || timeout.isNegative()) {
            throw new IllegalArgumentException("timeout must be positive");
        }
    }

    @Override
    public Mono<Health> health() {
        return Mono.defer(check)
                .map(ready -> ready
                        ? Health.up().withDetail("reason", "READY").build()
                        : Health.down().withDetail("reason", "NOT_READY").build())
                .switchIfEmpty(Mono.fromSupplier(() ->
                        Health.down().withDetail("reason", "EMPTY_RESPONSE").build()))
                .timeout(timeout)
                .onErrorResume(TimeoutException.class, ex -> Mono.just(
                        Health.down().withDetail("reason", "TIMEOUT").build()))
                .onErrorResume(Exception.class, ex -> Mono.just(
                        Health.down().withDetail("reason", "CHECK_FAILED").build()));
    }
}
```

The contract of `check` here is to emit a single `Boolean` representing the check outcome. The supplier only constructs a non-blocking reactive chain; if it calls a blocking SDK before returning `Mono`, `defer` cannot rescue that design either.

Each part of the chain serves a distinct role:

1. `defer` creates a new probe upon subscription; ordinary exceptions thrown while invoking the supplier also enter the error chain.
2. `map` turns a valued result into a `Health`.
3. `switchIfEmpty` turns completing without a value into `DOWN/EMPTY_RESPONSE`, per the example's contract.
4. `timeout` limits how long this chain waits for signals.
5. `onErrorResume` converts timeouts or ordinary errors into a safe health result.

Do not add `subscribeOn(boundedElastic())` to every reactive client just because async is involved. For an inherently non-blocking client, preserve its reactive chain; only offload genuinely blocking parts when there is evidence requiring offloading.

## 5. Verifying Deferral, Schedulers, and Result Types

File `src/main/java/learning/mixedhealth/MixedHealthDemo.java`:

```java
package learning.mixedhealth;

import java.time.Duration;
import java.util.Objects;
import java.util.HashSet;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.Supplier;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.ReactiveHealthContributor;
import org.springframework.boot.actuate.health.ReactiveHealthIndicator;
import org.springframework.boot.actuate.health.SimpleStatusAggregator;
import org.springframework.boot.actuate.health.Status;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

public class MixedHealthDemo {

    private static final Duration WAIT = Duration.ofSeconds(5);

    public static void main(String[] args) {
        AtomicInteger calls = new AtomicInteger();
        AtomicReference<Boolean> ranOnNonBlockingThread = new AtomicReference<>();
        var legacy = new LegacyStoreHealthIndicator(() -> {
            calls.incrementAndGet();
            ranOnNonBlockingThread.set(Schedulers.isInNonBlockingThread());
            Thread.sleep(20);
            return true;
        });
        var adapted = (ReactiveHealthIndicator) ReactiveHealthContributor.adapt(legacy);
        Mono<Health> pending = adapted.health();
        if (calls.get() != 0) {
            throw new AssertionError("Legacy check ran before subscription");
        }
        System.out.println("legacyBeforeSubscribe=" + calls.get());

        Scheduler eventLoop = Schedulers.newSingle("health-event-loop-demo");
        try {
            Health legacyResult = Objects.requireNonNull(pending.subscribeOn(eventLoop).block(WAIT));
            if (!Status.UP.equals(legacyResult.getStatus())
                    || !Boolean.FALSE.equals(ranOnNonBlockingThread.get())) {
                throw new AssertionError("Legacy check was not isolated correctly");
            }
            System.out.println("legacy=" + legacyResult.getStatus().getCode());
            System.out.println("legacyRanOnNonBlockingThread=" + ranOnNonBlockingThread.get());

            verify("reactive", () -> Mono.delay(Duration.ofMillis(20)).map(value -> true),
                    Status.UP, "READY");
            verify("reactiveDown", () -> Mono.just(false), Status.DOWN, "NOT_READY");
            verify("reactiveError", () -> Mono.error(new IllegalStateException("test error")),
                    Status.DOWN, "CHECK_FAILED");
            verify("reactiveEmpty", Mono::empty, Status.DOWN, "EMPTY_RESPONSE");
            verify("reactiveTimeout", Mono::never, Status.DOWN, "TIMEOUT");
            verify("factoryError", () -> { throw new IllegalStateException("factory error"); },
                    Status.DOWN, "CHECK_FAILED");

            var failedCatalog = new CatalogReactiveHealthIndicator(() -> Mono.just(false), Duration.ofSeconds(1));
            Status mixed = Objects.requireNonNull(Mono.zip(adapted.health(), failedCatalog.health())
                    .map(pair -> {
                        var statuses = new HashSet<Status>();
                        statuses.add(pair.getT1().getStatus());
                        statuses.add(pair.getT2().getStatus());
                        return new SimpleStatusAggregator().getAggregateStatus(statuses);
                    }).block(WAIT));
            if (!Status.DOWN.equals(mixed)) {
                throw new AssertionError("Unexpected mixed result");
            }
            System.out.println("mixed=" + mixed.getCode());
        }
        finally {
            eventLoop.dispose();
        }
    }

    private static void verify(String name, Supplier<Mono<Boolean>> source, Status expected, String reason) {
        var indicator = new CatalogReactiveHealthIndicator(source, Duration.ofMillis(200));
        Health result = Objects.requireNonNull(indicator.health().block(WAIT));
        if (!expected.equals(result.getStatus()) || !reason.equals(result.getDetails().get("reason"))) {
            throw new AssertionError("Unexpected result for " + name + ": " + result);
        }
        System.out.println(name + "=" + result.getStatus().getCode());
    }
}
```

**Scope of the check program:** `Thread.sleep(20)` only simulates a blocking SDK. `Mono.delay` creates an asynchronous delay without calling a real network service. `Schedulers.newSingle` provides a scheduler with non-blocking thread characteristics to test the subscription path; it is not a real Reactor Netty HTTP event loop.

The `.block(...)` calls reside only inside the command-line program, where the `main` thread must await results for verification. Do not copy them into indicators, WebFlux controllers, or request handlers. The program only disposes the scheduler it created itself; it does not dispose Reactor's shared schedulers.

In the project directory, verify Maven uses JDK 21 and run:

```shell
mvn -version
mvn compile dependency:build-classpath "-Dmdep.outputFile=target/classpath.txt"
```

On PowerShell:

```powershell
$dependencyClasspath = (Get-Content -Raw -LiteralPath 'target/classpath.txt').Trim()
java -cp "target/classes;$dependencyClasspath" learning.mixedhealth.MixedHealthDemo
```

On Linux/macOS:

```shell
java -cp "target/classes:$(cat target/classpath.txt)" learning.mixedhealth.MixedHealthDemo
```

Maven performed Java compilation and classpath resolution. Do not compile a single file standalone with `javac` without supplying the required Spring Boot and Reactor libraries.

Stdout of the program is:

```text
legacyBeforeSubscribe=0
legacy=UP
legacyRanOnNonBlockingThread=false
reactive=UP
reactiveDown=DOWN
reactiveError=DOWN
reactiveEmpty=DOWN
reactiveTimeout=DOWN
factoryError=DOWN
mixed=DOWN
```

The program does not print specific thread names because worker names and numbers may vary across runs. The evidence to verify is: before subscription, the SDK has not run; once subscribed from a non-blocking scheduler, the SDK call is shifted by the adapter onto an appropriate worker.

The `Mono.zip` snippet only illustrates combining two results inside the check program. A normal Actuator application does not need a hand-written aggregate indicator just to collect already-registered beans.

## 6. Letting Actuator Collect Both Bean Types in WebFlux

File `src/main/java/learning/mixedhealth/MixedHealthApplication.java`:

```java
package learning.mixedhealth;

import java.time.Duration;
import java.util.function.Supplier;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class MixedHealthApplication {

    public static void main(String[] args) {
        SpringApplication.run(MixedHealthApplication.class, args);
    }

    @Bean
    LegacyStoreHealthIndicator legacyStoreHealthIndicator(
            @Value("${demo.legacy-up:true}") boolean ready) {
        return new LegacyStoreHealthIndicator(() -> {
            Thread.sleep(80);
            return ready;
        });
    }

    @Bean
    CatalogReactiveHealthIndicator catalogHealthIndicator(
            @Value("${demo.catalog-mode:up}") String mode) {
        Supplier<Mono<Boolean>> probe = switch (mode) {
            case "up" -> () -> Mono.delay(Duration.ofMillis(40)).map(value -> true);
            case "down" -> () -> Mono.just(false);
            case "error" -> () -> Mono.error(new IllegalStateException("simulated error"));
            case "empty" -> Mono::empty;
            case "never" -> Mono::never;
            case "factoryError" -> () -> { throw new IllegalStateException("simulated factory error"); };
            default -> throw new IllegalArgumentException("Unsupported catalog demo mode");
        };
        return new CatalogReactiveHealthIndicator(probe, Duration.ofMillis(500));
    }
}
```

File `src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
server.port=8080
management.endpoints.web.exposure.include=health
management.endpoint.health.show-components=always
management.endpoint.health.show-details=always
management.endpoint.health.group.dependencies.include=legacyStore,catalog
```

The example intentionally uses simulated sources to focus on composition and scheduling; `Thread.sleep(80)` is not how to check a data store in production. When replacing with real clients, preserve the sync/reactive boundary and configure appropriate timeouts for those clients.

The two beans are named `legacyStoreHealthIndicator` and `catalogHealthIndicator`, so the corresponding contributors are `legacyStore` and `catalog`. Do not declare an extra wrapper bean for legacy: Actuator performs the adaptation when collecting into the reactive registry.

Run the application:

```shell
mvn spring-boot:run "-Dspring-boot.run.main-class=learning.mixedhealth.MixedHealthApplication"
```

In another terminal:

```shell
curl -i http://127.0.0.1:8080/actuator/health/dependencies
curl -i http://127.0.0.1:8080/actuator/health/legacyStore
curl -i http://127.0.0.1:8080/actuator/health/catalog
```

On Windows, you can use `mvn.cmd` and `curl.exe`. With the default configuration, the `dependencies` group has two `UP` components; the body has the structure:

```json
{
  "status": "UP",
  "components": {
    "catalog": { "status": "UP", "details": { "reason": "READY" } },
    "legacyStore": { "status": "UP", "details": { "reason": "READY" } }
  }
}
```

JSON key ordering is not significant. The selected group contains only the example's two contributors, helping avoid confusing their statuses with other default components on the aggregate endpoint.

Stop the application, then test a silent catalog:

```shell
mvn spring-boot:run "-Dspring-boot.run.main-class=learning.mixedhealth.MixedHealthApplication" "-Dspring-boot.run.arguments=--demo.catalog-mode=never"
```

After catalog's wait limit expires, the `catalog` branch returns `DOWN` with `reason=TIMEOUT`; the `dependencies` group returns `DOWN` and HTTP `503` per default mapping. Change the argument to `--demo.catalog-mode=empty` to see `EMPTY_RESPONSE`, or `--demo.legacy-up=false` to see `legacyStore` return `NOT_READY`.

Details are displayed fully on loopback for observation. In production, choose appropriate access permissions and visibility policies; do not put credentials or sensitive error messages into custom details.

## 7. Differences Between Errors, Empty Completion, and Timeouts

### Publisher Emits an Error

Errors can occur after subscription, after the `health()` method has returned. A `try/catch` wrapping only publisher construction cannot handle subsequent `onError` signals. Handle them inside the chain, such as with `onErrorResume`, or use a reactive support class matching the application's policy.

`Mono.defer(check)` also routes ordinary exceptions thrown directly inside the supplier into the chain's error path. It does not protect work already performed before calling `defer`, nor does it make a blocking supplier non-blocking.

### Publisher Completes Empty

For the lesson's `Mono<Boolean>`, completing empty means having no `true/false` evidence; we deliberately return `DOWN/EMPTY_RESPONSE`. If ignored, an operator like `zip` may complete without producing the expected result tuple.

However, **do not treat every empty `Mono` as an error**. Some APIs use `Mono<Void>` to signal success by completing normally without a value. Under that contract, convert the completion signal into `Health`, for example:

```java
return client.verify()
        .timeout(Duration.ofMillis(500))
        .thenReturn(Health.up().build())
        .onErrorResume(Exception.class, ex -> Mono.just(Health.down().build()));
```

This snippet illustrates a `client.verify()` returning `Mono<Void>`, not a standalone program. `thenReturn` sits after `timeout` so a valueless success still produces a `Health`; upstream errors still flow to the error-handling branch. Do not use `thenReturn(UP)` to turn a `false` Boolean result into healthy.

### Publisher Emits No Signal

`Mono.never()` neither completes, emits a value, nor emits an error. The example's `timeout` operator turns an exceeded wait into an error signal and maps it to `DOWN/TIMEOUT`.

A chain-level timeout is a subscriber wait limit, not proof that all underlying I/O operations stopped immediately. Both client timeouts and proper cancellation mechanisms are needed. If the client disconnects or the chain is canceled, do not assume `onErrorResume` always runs and publishes a final status; cancellation is not identical to an error signal.

## 8. When Must You Wrap Synchronous Work Yourself Inside a `ReactiveHealthIndicator`?

Keeping a `HealthIndicator` and letting Actuator adapt it is the clean choice when you already have a complete synchronous indicator. However, if you are building a composite reactive indicator with multiple steps, one step may unavoidably call a legacy SDK. In that case, wrap **only that step**, without blocking the entire chain.

The pattern where `legacy` is already available is:

```java
Mono<Health> legacyResult = Mono.fromCallable(legacy::health)
        .subscribeOn(Schedulers.boundedElastic());
```

Then combine `legacyResult` with reactive sources using appropriate operators, while normalizing errors/empties on each source per contract. This pattern does not give the SDK network-layer backpressure and does not automatically bound the SDK's timeout.

`boundedElastic` has resource and queue limits; it is not an infinite thread pool. When many health requests wait on a slow service simultaneously, queuing time can also grow. Avoid creating a new scheduler or executor on every health call. If a dedicated pool is needed to isolate an SDK, manage that pool's lifecycle, limits, and resource cleanup.

For the two regular beans in this lesson, this manual wrapping step is unnecessary. Also do not use a `ReactiveHealthIndicator` to call `legacy.health()` directly assuming the framework will detect the blocking portion inside: the framework received a reactive contract and will not analyze the method body to move code for the application.

## 9. Verify Which Web Stack the Application Actually Runs On

Having `Mono` on the classpath or having a `ReactiveHealthIndicator` is not enough to prove HTTP is served by WebFlux. When both Spring MVC and WebFlux are present, Boot's default web stack choice can be Servlet/MVC.

Therefore, for a real project, verify runtime dependencies, auto-configuration conditions, and the type of running application context. Do not add a Servlet starter just for a convenient dependency and then assume the WebFlux event loop remains the HTTP serving path.

The example declares only WebFlux and Actuator. If moving into a repository with orchestration that automatically adds starters by module type, check the effective module configuration rather than looking only at the `dependencies` snippet you just wrote.

`HealthContributorRegistry` and `ReactiveHealthContributorRegistry` serve different roles. When testing the reactive path, inspect the registry and web extension of that exact path; a direct call to a synchronous API does not prove how WebFlux HTTP executes. Accessing reactive components through a synchronous bridge may block waiting for results, so do not use it on the event loop.

## 10. What to Test for Real Evidence?

| What to prove | Meaningful test approach |
| --- | --- |
| SDK does not run before subscription | Use a counter before subscribing. |
| Blocking SDK does not run on non-blocking threads | Record `Schedulers.isInNonBlockingThread()` inside the simulated SDK when subscribed from a non-blocking scheduler. |
| Native reactive is not turned blocking | Verify the chain has no `.block()` and calls no synchronous SDK inside suppliers/maps running on the event loop. |
| Each source has a clear outcome | Test `true`, `false`, async error, source-creation error, empty completion, and no signal. |
| Automatic adaptation works properly | Start a WebFlux context, verify the registry has both `legacyStore` and `catalog` without duplicate wrappers. |
| HTTP uses the same policy | Call the health group via `WebTestClient` or real HTTP, checking `UP/200` and `DOWN/503`. |
| Timeout/cancellation work with real clients | Measure behavior under slow networks or cancellation; simulated sources do not prove this yet. |

For Reactor tests, use `StepVerifier` and virtual time for chains with timers; create the chain inside the virtual-time supplier so operators use the test scheduler. Do not rely on one long `Thread.sleep()` as stable proof of timeouts or non-blocking behavior.

When measuring performance, do not take thread names or a brief check as proof that the system handles load well. Also observe health duration, queuing delay, connection counts, and client concurrency limits. Even when the adapter protects the event loop, pools can still saturate when a dependency slows down.

The first bugs to look for when WebFlux health hangs or slows down are: calls executed before `Mono.just`, synchronous sources without scheduler offloading, `.block()` in request chains, silent publishers missing timeouts, and blocking code hidden behind a reactive return type.
