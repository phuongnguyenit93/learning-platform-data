# Lazy Initialization: First Request, Warm-Up, and Readiness in Spring Boot

## 1. Core Problem

**Lazy initialization** defers creating certain Spring beans until they are actually requested. As a result, the startup time reported by Spring Boot can be shorter. In exchange, the **first request** touching an uncreated bean pays the initialization cost, which can increase latency or expose configuration errors that startup did not detect.

Three questions should be separated:

1. **Startup time:** how long does the application take to reach the end of startup?
2. **Cold-path latency:** how many unready components must the first user of a feature wait to initialize?
3. **Readiness:** is the instance eligible for the load balancer or Kubernetes to send traffic to it?

Spring Boot **does not automatically create all lazy beans** before switching `ReadinessState` to `ACCEPTING_TRAFFIC`. A readiness probe can return `UP` while a business endpoint has never been called and its beans remain lazy.

Context of this lesson: **Spring Boot 3.3.x, Spring Framework 6.1.x, Java 17+**. The hands-on example combines `@Lazy`, `ObjectProvider`, `ApplicationRunner`, and Actuator to contrast two runs: a cold request and pre-ready warm-up.

## 2. Eager vs. Lazy Lifecycle

Normally, `ApplicationContext` creates non-lazy singletons during `refresh()`. When a bean definition has the lazy flag, Spring defers instantiation until the `BeanFactory` actually needs it.

```text
EAGER SINGLETON
---------------------
SpringApplication.run()
    |
ApplicationContext.refresh()
    +-- create non-lazy singletons
    +-- invoke init / @PostConstruct callbacks
    |
ApplicationStartedEvent
ApplicationRunner / CommandLineRunner
ApplicationReadyEvent
Readiness = ACCEPTING_TRAFFIC
    |
first request -> uses already-created bean

LAZY SINGLETON
---------------------
SpringApplication.run()
    |
ApplicationContext.refresh()
    +-- register bean definition
    +-- does not necessarily create lazy bean X yet
    |
ApplicationStartedEvent
ApplicationRunner / CommandLineRunner
ApplicationReadyEvent
Readiness = ACCEPTING_TRAFFIC
    |
first request needing X
    +-- BeanFactory creates X
    +-- create X's dependencies if missing
    +-- run init / @PostConstruct callbacks
    +-- handle request
    |
subsequent requests -> typically reuse singleton X
```

This is a conceptual model. A lazy bean **can still be created at startup** if an eager bean requires it as a dependency, if a runner fetches it, or if the framework proactively initializes it. Not all web infrastructure is deferred equally.

### 2.1. `@Lazy` Does Not Change Scope

- `@Lazy` on a singleton: defers **first creation**, then keeps the same singleton instance in `BeanFactory`.
- `@Scope("prototype")`: each bean request can create a new instance; different from a lazy singleton.
- Request/session scopes in web apps have their own lifecycles; do not equate them with lazy singletons.
- Once a lazy singleton is created, subsequent requests usually avoid paying that bean's constructor cost again, though they may still encounter JIT/cache/network cold costs.

### 2.2. Lazy Defers Until *Demand*, Not Necessarily HTTP

A lazy bean can be requested by:

- An eager singleton injecting it directly.
- `ObjectProvider.getObject()` inside an `ApplicationRunner`.
- A scheduler or message listener.
- An integration test calling `getBean(...)`.
- A REST request reaching the service.
- An intentional warm-up task creating the bean.

"Lazy" does not mean only the first HTTP request can trigger bean creation.

## 3. Spring Boot 3.3 Configuration

Enable global lazy in `src/main/resources/application.properties`:

```properties
spring.main.lazy-initialization=true
```

Or `application.yml`:

```yaml
spring:
  main:
    lazy-initialization: true
```

The default is `false`. When enabled, many beans switch to on-demand creation, potentially reducing startup time; however, some infrastructure and beans marked eager still need early creation.

In Java, before `run`:

```java
SpringApplication app = new SpringApplication(MyApplication.class);
app.setLazyInitialization(true);
app.run(args);
```

This is a snippet in `main`; `MyApplication` is the project-defined startup class.

### 3.1. Per-Bean Lazy

```java
@Bean
@Lazy
ExpensiveCatalog expensiveCatalog() {
    return new ExpensiveCatalog();
}
```

This is an illustrative method inside `@Configuration` or `@SpringBootApplication`, requiring `@Bean` and `@Lazy` imports as well as the `ExpensiveCatalog` class. This bean will not undergo eager pre-instantiation solely because the `@Bean` method exists.

A component can use:

```java
@Service
@Lazy
public class ReportService {
    public ReportService() {
        // Initialize service resources.
    }
}
```

This is an illustrative class requiring Spring stereotype imports.

### 3.2. Forcing Eager in a Global Lazy Application

`@Lazy(false)` marks a bean that must initialize early, such as an important runner:

```java
@Bean
@Lazy(false)
ApplicationRunner mandatoryInitializer() {
    return args -> System.out.println("Startup initialization hook");
}
```

This snippet lives in a configuration class. `@Lazy(false)` can be placed on components/controllers that must be created at startup.

**Do not enable global lazy and then mark all beans eager by gut feel.** Identify the critical path needing early creation and measure the results.

## 4. Easy-to-Miss Trap: Lazy Bean with an Eager Dependency

Spring Framework notes that a lazy bean can still be created at startup if a non-lazy singleton requires that dependency.

```text
EagerController
    |
    +-- constructor(CatalogService)
                       |
                       +-- CatalogService @Lazy
                       +-- may still be created right at startup
```

Reason: Spring cannot construct `EagerController` if its constructor requires a `CatalogService` instance without a dependency-deferral mechanism.

**`@Lazy` on bean definition:**

```java
@Bean
@Lazy
CatalogService catalogService() {
    return new CatalogService();
}
```

**`@Lazy` at injection point:**

```java
public CatalogController(@Lazy CatalogService service) {
    this.service = service;
}
```

The second snippet is an illustrative constructor: Spring can inject a proxy and resolve the service when the proxy is used. Proxy behavior has limits based on types, `final` classes, AOP mechanics, and injection points.

**`ObjectProvider`:**

```java
public CatalogController(ObjectProvider<CatalogService> provider) {
    this.provider = provider;
}

public String lookup() {
    return provider.getObject().find("item");
}
```

This is a snippet inside a controller with an `ObjectProvider<CatalogService> provider` field already defined. Accepting `ObjectProvider` does not require creating `CatalogService` immediately; `getObject()` is the explicit resolution point. The demo uses this approach to separate controller creation from service creation.

### 4.1. `@PostConstruct` Warning

`@PostConstruct` on a lazy bean **does not run automatically at startup** if the bean has not been initialized yet. It runs **when the bean is created**. If the callback loads a cache or makes a slow backend connection, that cost shifts to the first request.

For a component that must initialize before receiving traffic, use an eager bean or a warm-up runner instead of assuming `@PostConstruct` runs early.

## 5. Why Can the First Request Be Slow?

| Cost Type | Cause | Can Surface Late? |
| --- | --- | --- |
| Bean creation | Constructor, dependency graph, factory method | Yes |
| Bean post-processing | Proxies, validation, post-processors | Yes |
| Initialization callbacks | `@PostConstruct` and init methods | Yes, when the bean is created late |
| Servlet/MVC/WebFlux infrastructure | Handlers, serializers, codecs, mappings | Possibly depending on mode/config |
| JIT/class loading | JVM compilation and class loading | Yes |
| DB connection/pool | Opening first connection, authentication | Possibly |
| ORM/query | Query compilation, metadata, mappings | Possibly |
| Cache | Loading initial data/index | Possibly |
| Remote API | DNS/TLS/authentication | Possibly |
| File/model resource | Reading schemas/templates/dictionaries | Possibly |

Enabling lazy mainly shifts **bean creation** and dependent initialization costs to use time. It does not erase JVM, network, or business logic costs. Even an eager service can still have a **cold path** if HTTP routes, caches, or connections are still cold.

### 5.1. First Request to Route A Differs from Route B

Suppose `GET /ping` does not need `ReportService`, while `GET /reports` does. Once the app is ready:

```text
GET /readyz   -> UP (per active readiness group)
GET /ping     -> may return quickly
GET /reports  -> BeanFactory creates lazy ReportService on first hit
GET /reports  -> typically reuses singleton
```

Do not treat a health probe as an "application-wide warming" request. It does not automatically touch every business bean.

### 5.2. Concurrent Requests and Singleton Cold Start

If 50 concurrent requests simultaneously need an uncreated lazy singleton, the requests may have to wait on bean creation under `BeanFactory` synchronization. That can spike p95/p99 right after a rollout.

A single sequential `curl /reports` test does not adequately simulate concurrent load. Measure multiple instances and initial post-deploy bursts.

## 6. Trading Fast Startup for Late Error Detection and Late Memory Growth

Spring Boot 3.3 explicitly highlights two downsides of lazy initialization:

- **Late error detection:** a misconfigured bean may not be created during startup. Then the first request hitting that feature throws `BeanCreationException` or an init error.
- **Shifted heap footprint:** initial startup may use less heap, yet many beans are created as traffic spreads across features. Sizing memory limits strictly from post-startup snapshots risks running out of heap.

Late-error example: a lazy service requires the mandatory property `reports.endpoint`; the property is missing; Boot skips creating the service at startup and still reaches ready. Only when a controller or runner retrieves the service is the missing configuration detected.

Do not treat "startup succeeded" as a certificate that all beans are configured properly. For critical paths, enforce fail-fast behavior, integration tests, or pre-readiness warm-up.

## 7. What Is Warm-Up?

Warm-up proactively prepares components before real traffic needs them. It can be divided into three layers:

1. **Bean warm-up:** triggers creation of selected lazy singletons; runs constructors, dependency injection, and init callbacks.
2. **Service warm-up:** runs safe operations to prepare caches, mappers, query plans, connections, or indexes.
3. **Request-path warm-up:** exercises a representative request path to touch handlers/serialization/security. Requires extra care regarding side effects.

Calling `getBean(Service.class)` alone does not necessarily warm databases, JSON serializers, JVM JIT, or the full request path.

### 7.1. Properties of Good Warm-Up

- **Idempotent** if the app/tests/pods start multiple times.
- **Free of business side effects** (no placing real orders, transferring money, or sending emails).
- Has a clear **timeout/budget** and failure policy.
- Does not leak secrets into logs.
- Measured for duration and outcome.
- Avoids opening excessive simultaneous connections when multiple pods roll out together.
- Does only what is necessary for **critical paths**.
- Does not hold startup locks/threads with infinite retries.

A service can expose a read-only or local-state `warmUp()` method invoked from an `ApplicationRunner`.

### 7.2. Warming Every Bean Is Not Always Better

If there are hundreds of rarely used features, forcing all beans to instantiate at startup defeats lazy initialization and increases CPU and memory right at deploy time. Often effective: **eager/runner warm-up** for core paths; keep rarely used features with acceptable cold latency lazy; add integration tests for lazy features so config errors are caught before real users hit them.

## 8. Spring Boot Readiness and the Best Place to Warm Up

Spring Boot 3.3 typically emits these major milestones:

```text
ApplicationContext.refresh()
    |
ContextRefreshedEvent
    |
ApplicationStartedEvent
    |
LivenessState.CORRECT
    |
ApplicationRunner / CommandLineRunner  <--- mandatory warm-up
    |
ApplicationReadyEvent
    |
ReadinessState.ACCEPTING_TRAFFIC
    |
SpringApplication.run() returns
```

Before runners complete, Boot's default readiness is typically `REFUSING_TRAFFIC`. Therefore a **synchronous** `ApplicationRunner` is a logical place for warm-up that must succeed **before** the instance accepts traffic.

**Key point:** Boot does not scan all lazy beans by default before marking READY. A runner only executes what its code requests. A runner initializing one service does not guarantee another route is warm.

### 8.1. What If a Runner Fails?

If a runner throws an unhandled exception, startup fails and `ApplicationReadyEvent` is normally not published. This can be the right behavior if the instance must not accept requests without a mandatory dependency.

If an optional feature fails to warm up, falling back while still becoming ready can be acceptable, provided the policy is explicitly defined and measured. Avoid `catch (Exception ignored)` followed by printing `"WARMUP_SUCCESS"` when warm-up did not finish.

### 8.2. `@Async` Is Not Equivalent to a Synchronous Runner

If a runner merely calls `CompletableFuture.runAsync(...)` and returns, Boot may publish `ApplicationReadyEvent` and mark accepting traffic **while warm-up is still running**. To guarantee completion before ready, the runner must wait with a bounded timeout or use a readiness state machine with clear ownership.

## 9. Java 17+ Demo: Comparing a Cold Request vs. Pre-READY Warm-Up

This is a **Spring Boot 3.3.x + Spring MVC + Actuator** example with:

- `GET /demo/ping`: does not need the catalog.
- `GET /demo/catalog`: lazily retrieves `CatalogService` via `ObjectProvider`.
- `ApplicationRunner`: can warm the catalog before Boot completes ready.
- `/livez` and `/readyz`: observe health groups on the main port.

`CatalogService`'s constructor includes `Thread.sleep(500)` **solely to simulate initialization cost**; never use such sleep in production.

### 9.1. Structure

```text
lazy-readiness-demo/
  settings.gradle
  build.gradle
  src/main/resources/application.properties
  src/main/java/com/example/lazy/
    LazyReadinessApplication.java
    CatalogService.java
    CatalogController.java
```

### 9.2. `settings.gradle`

```groovy
rootProject.name = 'lazy-readiness-demo'
```

### 9.3. `build.gradle`

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

This example pins Spring Boot 3.3.13 for consistency with the lesson. The project requires Gradle and Java 17+, and the run commands below assume the Gradle Wrapper is present. Do not mix Spring Boot 4 dependencies into a 3.3 project.

### 9.4. `application.properties`

```properties
server.port=8080

# Use lazy for eligible beans unless marked eager.
spring.main.lazy-initialization=true

# Allow enabling warm-up via command-line property.
demo.warmup.enabled=false

# Enable health groups even outside Kubernetes.
management.endpoint.health.probes.enabled=true

# Expose /livez and /readyz on the main HTTP port.
management.endpoint.health.probes.add-additional-paths=true
```

### 9.5. `LazyReadinessApplication.java`

```java
package com.example.lazy;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Lazy;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class LazyReadinessApplication {

    public static void main(String[] args) {
        SpringApplication.run(LazyReadinessApplication.class, args);
        System.out.println("BOOT_COMPLETED");
    }

    @Bean
    @Lazy
    CatalogService catalogService() {
        return new CatalogService();
    }

    @Bean
    @Lazy(false)
    ApplicationRunner optionalWarmup(
            ObjectProvider<CatalogService> catalogProvider,
            Environment environment) {

        return args -> {
            boolean enabled = environment.getProperty(
                    "demo.warmup.enabled", Boolean.class, false);

            if (enabled) {
                System.out.println("WARMUP_START");
                CatalogService catalog = catalogProvider.getObject();
                catalog.lookup("startup");
                System.out.println("WARMUP_DONE");
            }
        };
    }
}
```

Explanation:

1. `@Bean @Lazy` registers the `CatalogService` bean definition without requesting immediate creation.
2. `@Bean @Lazy(false)` forces the runner to participate in the startup phase even with global lazy enabled.
3. `ObjectProvider<CatalogService>` is injected into the runner without instantiating `CatalogService`.
4. When the warmup flag is false, the runner does not call `getObject()`, so the catalog can remain uncreated.
5. When the warmup flag is true, the runner calls `getObject()`, the constructor runs **before** the runner finishes and before Boot's default accepting milestone.
6. `BOOT_COMPLETED` is printed after `SpringApplication.run(...)` returns, marking when Boot startup completes.

### 9.6. `CatalogService.java`

```java
package com.example.lazy;

public final class CatalogService {

    public CatalogService() {
        System.out.println("CATALOG_CREATED");

        try {
            Thread.sleep(500); // Only simulates expensive initialization.
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                    "Demo initialization interrupted", ex);
        }
    }

    public String lookup(String key) {
        return "catalog:" + key;
    }
}
```

This is a plain Java class; **no `@Service` is needed** because a `@Bean` method creates it. `Thread.sleep` is strictly to make the delay clearly observable for learners, not an optimization technique.

### 9.7. `CatalogController.java`

```java
package com.example.lazy;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.context.annotation.Lazy;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@Lazy(false)
public class CatalogController {

    private final ObjectProvider<CatalogService> catalogProvider;

    public CatalogController(
            ObjectProvider<CatalogService> catalogProvider) {
        this.catalogProvider = catalogProvider;
    }

    @GetMapping("/demo/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/demo/catalog")
    public String catalog() {
        return catalogProvider.getObject().lookup("request");
    }
}
```

The controller is marked eager to keep **lazy `CatalogService`** as the isolated variable in the demo. `ObjectProvider` ensures the controller's constructor does not force `CatalogService` creation itself. Some framework components may still initialize late due to global lazy; thus when measuring total latency, also watch the `CATALOG_CREATED` log.

## 10. Experiment A: Without Warm-Up

Run from the directory containing the Gradle Wrapper:

```bash
./gradlew bootRun
```

Windows CMD: `gradlew.bat bootRun`. PowerShell: `.\gradlew.bat bootRun`.

With `demo.warmup.enabled=false`, the program prints from `main`:

```text
BOOT_COMPLETED
```

At this point, `CATALOG_CREATED` **has not printed** as long as nothing else requested the catalog bean.

Using a second terminal:

```bash
curl -i http://localhost:8080/readyz
curl -i http://localhost:8080/demo/ping
curl -i http://localhost:8080/demo/catalog
curl -i http://localhost:8080/demo/catalog
```

Response bodies defined by the demo:

```text
GET /demo/ping        -> pong
GET /demo/catalog     -> catalog:request
GET /demo/catalog     -> catalog:request
```

When the first request actually asks for the catalog, the server console prints:

```text
CATALOG_CREATED
```

This request can incur the simulated ~500 ms wait plus other framework/JVM costs. The next request reuses the `CatalogService` singleton and does not re-print the constructor log. **Do not guarantee an exact 500 ms HTTP duration** since the scheduler, JIT, HTTP server, and network all affect timing.

### 10.1. `/readyz` Green Before `/demo/catalog` Is Valid Behavior

`/readyz` reflects the currently configured Spring Boot readiness/health group, **not an instantiation check for `CatalogService`**. It can return `UP` while the catalog bean remains uncreated. That is not an Actuator bug; it is the scope of the default readiness contract.

Only add a health indicator or catalog check if it is genuinely a **mandatory prerequisite for accepting traffic**, and avoid turning health checks into heavy work on every probe.

### 10.2. Why Might `/demo/ping` Still Be Slow Even Though Catalog Wasn't Created?

Global lazy can defer some MVC/servlet/serialization infrastructure initialization until the first request. `/demo/ping` may pay cold costs unrelated to the catalog. Use the `CATALOG_CREATED` marker to track when the catalog bean is constructed rather than inferring from a single request's total latency.

## 11. Experiment B: Runner Warms Up Before Ready

Stop the previous process and rerun with the argument:

```bash
./gradlew bootRun --args="--demo.warmup.enabled=true"
```

`--args` is how Gradle `bootRun` passes arguments to Spring Boot. If multiple main classes exist, configure `springBoot.mainClass` in the build script instead of using an unverified `--main-class` flag on `bootRun`.

Lines from the demo code in order:

```text
WARMUP_START
CATALOG_CREATED
WARMUP_DONE
BOOT_COMPLETED
```

Interpretation:

- The runner executes after refresh yet before `ApplicationReadyEvent`.
- `ObjectProvider.getObject()` creates `CatalogService` during warm-up.
- The constructor runs exactly once.
- The runner calls `lookup("startup")` and completes.
- Boot then finishes default startup/readiness, and `run(...)` returns to `main`.

Call:

```bash
curl -i http://localhost:8080/readyz
curl -i http://localhost:8080/demo/catalog
curl -i http://localhost:8080/demo/catalog
```

There is no second `CATALOG_CREATED` line because the singleton already exists. **Only `CatalogService` and the invoked method were warmed**; costs on other routes, JSON serializers, JIT, DB, or TLS may still be cold.

### 11.1. Comparison Table

| Criterion | Lazy, No Warm-Up | Lazy + Runner Warm-Up |
| --- | --- | --- |
| Startup-to-ready | Usually shorter | Pays extra warm-up time |
| First use of `CatalogService` | Creates bean on first request | Bean already created before ready |
| Error detection for `CatalogService` | Potentially late | Opportunity to fail before ready |
| Memory right after ready | Potentially lower | Higher because catalog was created |
| Are other routes ready? | Cannot be inferred | Still cannot be inferred |
| Total singleton creation cost | Does not vanish | Only shifts timing |

## 12. Warming the Right Critical Execution Path

A real service has a graph like:

```text
POST /orders
  -> Security / validation / tracing
  -> OrderController
  -> OrderService
      -> PricingEngine
      -> InventoryClient
      -> OrderRepository
          -> DataSource
          -> TransactionManager
  -> JSON serialization
```

Merely calling `getBean(OrderService.class)` may not touch queries, connections, mappers/serialization, or actual remote dependencies.

Warm-up design should answer:

1. Which routes have strict first-request SLOs?
2. Which beans are causing cold latency?
3. Which init callbacks must complete before traffic?
4. Are there caches/indexes/queries/connections to warm?
5. Does warm-up cause side effects?
6. Should startup fail fast if a mandatory dependency is missing?
7. How does warming many pods simultaneously affect databases/APIs?
8. Do measurements after warm-up under real traffic prove an improvement?

### 12.1. Avoid Defaulting to Self-HTTP

Some applications send HTTP requests to localhost to warm routes. That approach easily causes problems:

- Creating real orders/transactions or business side effects.
- Wrong authentication/authorization context.
- Requiring the HTTP server to already be serving.
- Deadlocks if startup waits on a self-request that cannot run yet.
- Logs/traces that blur warm-up with real customer traffic.

Prefer a **dedicated service warm-up method** invoked from a runner when possible. If full HTTP path warm-up is required, use side-effect-free requests and **gate readiness** properly so customer traffic does not interleave.

### 12.2. Thundering Herd on Rollout

If 30 pods start simultaneously and each warms 100,000 rows from the DB, shared resources can be overwhelmed. Consider concurrency limits, time budgets, rolling deployments, shared caches, batch sizes, and backoff. Never let mandatory warm-up retry forever and leave every pod stuck unready indefinitely.

## 13. Actuator Readiness/Liveness and Laziness

In web applications with `spring-boot-starter-actuator`, Spring Boot exposes two health groups backed by `ApplicationAvailability`:

- `/actuator/health/liveness`
- `/actuator/health/readiness`

With `management.endpoint.health.probes.add-additional-paths=true`, those groups also get paths on the main port:

- `/livez`
- `/readyz`

Readiness answers **whether traffic should be routed to the instance**, not "have all lazy beans been instantiated yet."

### 13.1. Availability Milestones and Runners

```text
STARTING: Liveness BROKEN; Readiness REFUSING_TRAFFIC
    |
Context refreshed / ApplicationStartedEvent
    |
Liveness CORRECT; Readiness REFUSING_TRAFFIC
    |
ApplicationRunner warm-up
    |
ApplicationReadyEvent
    |
Readiness ACCEPTING_TRAFFIC
```

The initial `BROKEN` state is how Boot withholds declaring the instance live during startup; it does not mean the application suffered internal corruption. The HTTP server may also not be open yet, so probes cannot reach it yet.

### 13.2. Do Not Mix Up Readiness and Liveness

- **Liveness:** signal to restart the instance if internal state cannot self-recover.
- **Readiness:** signal to stop routing traffic during startup, overload, loss of mandatory dependencies, or warm-up.
- **Global health:** may aggregate database/cache/other indicators.

Do not indiscriminately put external dependency checks into liveness: when a shared DB loses connectivity, every pod can restart together and amplify the outage.

### 13.3. Probes on the Main Port

An Actuator running on a separate management port might report green even if the web app's main port is broken. Configuring `/livez` and `/readyz` on the main server port routes probes through the application port. However **it still does not invoke business endpoints**, so it is not a full route warm-up.

## 14. What If Warm-Up Can Only Run After `ApplicationReadyEvent`?

This is a more complex pattern. If you start asynchronous warm-up **after** the ready milestone, Boot can switch readiness to `ACCEPTING_TRAFFIC` before the task finishes.

In that case you need a state machine with clear ownership:

1. Keep `ReadinessState` at `REFUSING_TRAFFIC` if the application is not yet allowed to take work.
2. Run warm-up with a timeout and explicit outcome.
3. Publish `ACCEPTING_TRAFFIC` only once mandatory conditions finish.
4. Manage races against default availability events, shutdown, and other listeners.
5. Do not simply expect `@Async` to make Boot wait.

API showing state transitions:

```java
AvailabilityChangeEvent.publish(
        applicationContext, ReadinessState.REFUSING_TRAFFIC);

// Run designed warm-up: with timeout and failure handling.

AvailabilityChangeEvent.publish(
        applicationContext, ReadinessState.ACCEPTING_TRAFFIC);
```

This snippet **only illustrates the API**; `applicationContext` must be a valid context, with `AvailabilityChangeEvent` and `ReadinessState` imported. Do not drop this straight into an `@EventListener(ApplicationReadyEvent.class)` and assume all races are automatically solved. If warm-up **must** complete before taking traffic, a **synchronous runner** is usually much easier to keep ordered.

## 15. Configuration Errors on First Request: Causes and Fixes

```text
Startup:
  Bean ReportService @Lazy
  -> not yet created
  -> Boot reaches readiness ACCEPTING_TRAFFIC

GET /reports:
  -> BeanFactory creates ReportService
  -> missing property / dependency / init error
  -> BeanCreationException / root cause
  -> request fails
  -> readiness may remain ACCEPTING_TRAFFIC
```

Actual HTTP status depends on exception handling and the web stack; do not guarantee the exact same status code in every case.

Risk mitigations:

- Mark core beans eager.
- Have a runner retrieve required beans and run validation/warm-up before ready.
- Use proper config validation.
- Run integration tests exercising critical routes and dependencies.
- Design explicit timeouts/fallbacks for external services.
- Do not merely raise health-probe timeouts to mask business errors.

A rarely used lazy bean may reasonably surface errors only when accessed in some plugin/optional designs, provided an appropriate error policy exists. For core business paths, **fail before traffic** is usually more reliable.

## 16. Measuring First-Request Latency Properly

Do not look solely at the `Started Application in X seconds` log line.

| Metric | Question |
| --- | --- |
| Process-to-ready | How long until readiness is accepting? |
| Per-route first-hit latency | How long does the first user wait? |
| Post-deploy p50/p95/p99 | Is there a spike on initial traffic? |
| Bean creation duration | Which constructors/init callbacks are slow? |
| First-request error rate | Were init errors hidden until a request arrived? |
| Startup CPU | How does warm-up affect CPU spikes? |
| Heap right after ready | What are the initial memory savings of lazy? |
| Heap after full critical workload | Does memory climb back to expected levels? |
| Database/remote load | Do many pods warming simultaneously cause a request storm? |

POSIX shell example measuring two requests:

```bash
curl -s -o /dev/null -w 'first=%{time_total}\n' \
  http://localhost:8080/demo/catalog

curl -s -o /dev/null -w 'next=%{time_total}\n' \
  http://localhost:8080/demo/catalog
```

These commands target shells with `/dev/null`; on Windows, adjust body discarding and quoting, e.g., using `curl.exe`. Each "first" test must use a **fresh instance**; once the singleton is created, calling it again in the same process no longer reproduces cold bean creation.

Use multiple deployments/instances to observe the latency distribution rather than concluding from one run on a laptop. Compare alongside error rates, JIT/GC, CPU, and network metrics.

## 17. Real-World Application Scenarios

**A — Payment service:** core path has strict SLOs. Keep mandatory components eager/warmed, validate configuration, and only publish ready when requests can be handled safely.

**B — Reporting portal with many rarely used modules:** keep low-traffic reports lazy, warm popular routes. Accept first-hit cold latency on niche modules with tests and timeouts in place.

**C — Serverless / scale-to-zero:** lazy speeds up startup logs, yet the first request still pays the cost on short-lived instances. Measure total *first invocation* time, not just container boot time.

**D — Startup cache taking 60 seconds:** if the cache is mandatory before traffic, runner warm-up should finish before readiness and align with startup probe/deployment timeouts. If the cache can populate incrementally, consider fallbacks/partial service and clear readiness rules.

**E — External dependency disconnected:** transient API/DB failures must not flip liveness to BROKEN. Govern retries/circuit breakers/readiness based on serving capability; do not restart every pod simply because an external service is down.

**F — Many initial requests hitting one singleton concurrently:** can spike p99 as requests wait for initialization. Warm in a runner or keep critical paths eager.

**G — `@Lazy` applied yet startup did not change:** inspect the eager graph; an eager bean may directly inject the lazy bean, forcing early creation.

## 18. Anti-Patterns to Avoid

| Mistake | Why It Is Wrong | Replacement |
| --- | --- | --- |
| Enabling global lazy just for a faster startup log | Shifts costs/errors onto live traffic | Measure startup + first-request + errors |
| Treating `/readyz` UP as "all lazy beans are ready" | Probes do not traverse the whole `BeanFactory` | Warm/test critical paths |
| Assuming a `@Lazy` bean's `@PostConstruct` already warmed up | Callback only runs when the bean is created | Eager or runner |
| Eager controller directly injecting a lazy service | Service may still be created early | `ObjectProvider`/lazy injection |
| Putting `@Async` on warm-up and assuming Boot waits | Task may still run after ready | Synchronous runner or readiness gating |
| Self-HTTP POST for warm-up | Can trigger business side effects | Dedicated warm-up method |
| Warming every bean | Loses lazy benefits; increases CPU/memory | Pick the critical set |
| Letting bean init failures reach production | First request absorbs the failure | Startup validation and integration tests |
| Using liveness to check the database | Restart storm when a shared DB fails | Separate availability groups |
| Shrinking heap limits based on post-startup memory | Lazy beans are created later | Measure memory under traffic |
| Testing only sequential single requests | Misses bursts and p99 | Test concurrency and rollouts |
| Letting a warm-up runner retry infinitely | Instance never becomes ready | Timeouts + failure policy |
| Having health probes call heavy business endpoints | Probes generate load/side effects | Lightweight contract-based health indicators |
| Setting readiness accepting right when context is created | Runners have not finished yet | Rely on Boot's ready state or explicit policy |
| Unbounded multi-pod warm-up | Thundering herd on DB/remotes | Bounded concurrency/rollout |

## 19. Strategy Selection Table

| Goal | Strategy | Price Paid |
| --- | --- | --- |
| Catch config errors early, stable startup | Keep default eager | Startup constructs many singletons |
| Rarely used feature with heavy init | Selective `@Lazy` | Cold latency on first use |
| Very tight startup budget, many rare beans | Global lazy + thorough testing | Managing first-hit/errors/memory |
| Critical route must not spike | Eager or runner warm-up | Longer time-to-ready |
| Need backend verification before traffic | Fail-fast runner and proper readiness | Can fail deployments if mandatory backend is unavailable |
| Background warm-up after Boot ready | Coordinate readiness and state machine | Races and operational complexity |
| Many pods warming shared data | Rolling deploy / concurrency limits / cache | Total rollout duration may increase |
| Optional service with fallback | Lazy + timeout/circuit breaker | First request for that feature may be slow |

## 20. Self-Check Questions

**1. Does enabling global lazy mean every singleton is created only when an HTTP request arrives?**

No. Eager dependencies, framework components, and runners can create beans earlier; beans can also be requested by schedulers, tests, or non-HTTP logic.

**2. Why does `@Lazy` not always reduce startup time?**

An eager bean directly injecting a lazy dependency can force Spring to create that dependency at startup.

**3. How does `@Lazy` at an injection point differ from `@Lazy` on a bean?**

On a bean definition, it controls eager instantiation; at an injection point, it can use a proxy to defer resolution.

**4. Does `ApplicationReadyEvent` wait for all lazy beans?**

No. Boot waits for mandatory startup steps, without proactively instantiating every lazy bean.

**5. Does a 200 readiness response guarantee the first request won't be slow?**

No. Probes do not warm all routes; JIT, caches, network, serializers, and lazy beans can still be cold.

**6. Does `ApplicationRunner` warm-up run before or after ready?**

Before `ApplicationReadyEvent` and before `ReadinessState.ACCEPTING_TRAFFIC` in the standard Boot 3.3 sequence.

**7. Can first-request latency be reduced without disabling or enabling global lazy?**

Yes. Optimize bean initialization, caches, connection pools, JVM/JIT, or safely warm request paths depending on the bottleneck.

**8. Why not use `@Async` and consider warm-up finished?**

Async tasks can keep running after the runner method returns and Boot starts accepting traffic.

**9. Should DB health be added to liveness to check whether the app can serve?**

Usually no: a shared DB outage could cause all pods to restart at once.

**10. When should `@Lazy(false)` be used even with global lazy enabled?**

For critical runners/beans that must be created at startup or to catch config errors before traffic.

**11. Is a lazy singleton recreated on every request?**

No. It is normally created once per `BeanFactory`; request/prototype scopes are separate mechanisms.

**12. Is measuring heap right after startup enough to set memory limits?**

No. Lazy beans can significantly increase memory once multiple features are invoked.

## 21. Implementation Checklist

1. Define the objective: startup, memory, first-request SLO, or reliability.
2. Capture baselines for time-to-ready and first-hit latency before toggling lazy.
3. Choose global lazy or per-bean lazy with clear justification.
4. Audit the dependency graph: are any eager singletons pulling lazy beans?
5. Identify critical routes and their associated beans.
6. Make mandatory dependencies eager or warm them up before ready.
7. Use `ObjectProvider`/lazy injection where genuine deferral is needed.
8. For warm-up runners in global-lazy apps, mark the runner eager if needed.
9. Ensure warm-up is idempotent and free of business side effects.
10. Configure timeouts, retry policies, and fail-fast/fallback behavior.
11. Do not equate `@PostConstruct` with eager startup on a lazy bean.
12. Test missing/invalid properties/config, init exceptions, and first requests.
13. Observe `/readyz` alongside real business requests, not just `/ping`.
14. Measure cold-request p95/p99 across rollouts under concurrency.
15. Monitor memory/CPU after lazy beans have been created.
16. Bound warm-up concurrency when multiple pods start together.
17. Configure an appropriate `startupProbe` if warm-up takes significant time.
18. Do not place external health checks into liveness indiscriminately.
19. Distinguish bean warm-up, service warm-up, and full HTTP path warm-up.
20. Keep configuration easy to roll back if lazy increases errors or latency.
21. Do not expose secrets in logs or Actuator.
22. Choose explicit strategies for optional features.

## 22. Summary

```text
SPRING BOOT LAZY INITIALIZATION
        |
        +-- Startup can be shorter
        |
        +-- Beans may still remain uncreated after ApplicationReadyEvent
                    |
                    +-- First request: pays cold cost / hits init failure
                    |
                    +-- OR ApplicationRunner initializes critical beans
                             before readiness ACCEPTING_TRAFFIC

READY != all lazy beans have been initialized
READY != all request paths are warm
READY != all external dependencies are healthy
```

**Core principle:** laziness **shifts cost and error-detection timing**, without eliminating them. For critical processing paths, warm or create beans **before receiving traffic** and verify with real first-request measurements. Synchronous `ApplicationRunner` is a straightforward choice when warm-up is mandatory before readiness; meanwhile, liveness, readiness, and health indicators must each stay true to their intended purpose.

## Official Documentation

- [Spring Boot 3.3 — SpringApplication: Lazy Initialization, Application Events, Runners](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
- [Spring Boot 3.3 — Actuator Endpoints and Kubernetes Probes](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)
- [Spring Boot 3.3 — SpringApplication.setLazyInitialization API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html)
- [Spring Framework 6.1 — @Lazy annotation API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/annotation/Lazy.html)
- [Spring Framework — Lazy-initialized Beans and eager dependencies](https://docs.spring.io/spring-framework/reference/6.1/core/beans/dependencies/factory-lazy-init.html)
- [Spring Framework 6.1 — ObjectProvider API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/beans/factory/ObjectProvider.html)
