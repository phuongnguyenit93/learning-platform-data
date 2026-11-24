# Designing a Data Warm-Up Runner Before Publishing Readiness in Spring Boot

## 1. Objectives and Real-World Scenario

A Spring Boot application may finish creating its ApplicationContext and starting the embedded web server, yet **still lack data sufficient to serve requests**. For example: a pricing service needs a verified price-table snapshot; a routing service needs a rules table; a product lookup app needs to load a local catalog; or an authorization engine needs a required metadata set.

If the system is marked ready while the cache is still empty or half-loaded, initial requests may see missing data, return wrong results, or suffer latency because each request triggers warm-up itself. Checking only that the JVM is alive, the HTTP port is open, or Spring logged **Started** is not enough.

Spring Boot provides **ApplicationRunner** and **CommandLineRunner** to execute work **after the ApplicationContext is refreshed but before ApplicationReadyEvent**. A runner that executes synchronously, completes loading/validating/publishing data, and only then returns acts as a **startup gate**: Spring Boot only transitions readiness to **ACCEPTING_TRAFFIC** after all runners finish successfully.

This lab designs the solution on **Spring Boot 3.5.x, Java 17+**, including a Maven POM, runnable Java code, an HTTP endpoint reading the cache, Actuator readiness, intentional startup failure, curl/Kubernetes checks, failure policies, and concurrency pitfalls.

**Desired outcome:** while warming up, readiness is **REFUSING_TRAFFIC**; once the snapshot is consistent and the runner completes, Spring Boot publishes ApplicationReadyEvent and switches to **ACCEPTING_TRAFFIC**. If mandatory warm-up fails, startup must fail in a controlled manner instead of falsely reporting ready.

## 2. Differences Between Started, Live, and Ready

Spring Boot publishes three easily confused concepts:

- **Context refreshed:** the BeanFactory, auto-configuration, singleton initialization, and embedded server phase have finished refreshing.
- **LivenessState.CORRECT:** the application is not considered broken in internal state after refresh.
- **ReadinessState.ACCEPTING_TRAFFIC:** the application is considered eligible to receive traffic, after ApplicationRunner/CommandLineRunner execution completes.

Standard flow in Spring Boot 3.5:

~~~text
SpringApplication.run(args)
     |
     +--> Environment / ApplicationContext preparation
     |
     +--> ApplicationContext.refresh()
     |       Bean definitions, singleton beans, web server
     |
     +--> ApplicationStartedEvent
     |
     +--> AvailabilityChangeEvent(LivenessState.CORRECT)
     |       ReadinessState = REFUSING_TRAFFIC
     |
     +--> ApplicationRunner / CommandLineRunner
     |       - mandatory load
     |       - validate data
     |       - publish snapshot
     |
     +--> ApplicationReadyEvent
     |
     +--> AvailabilityChangeEvent(
     |        ReadinessState.ACCEPTING_TRAFFIC)
     |
     +--> SpringApplication.run returns successfully
~~~

When a runner throws an exception, SpringApplication handles **startup failure** and does not emit the successful Ready milestone. The context may have refreshed, yet overall startup is still **unsuccessful**.

| Timing | Liveness | Readiness | Should Route Traffic? |
| --- | --- | --- | --- |
| Before refresh | BROKEN in startup model | REFUSING_TRAFFIC | No |
| After refresh, before runners | CORRECT | REFUSING_TRAFFIC | No |
| Runner warming up | CORRECT | REFUSING_TRAFFIC | No |
| All runners complete | CORRECT | ACCEPTING_TRAFFIC | Yes, once probes/infrastructure recognize it |
| Runner throws | Startup failure | Does not publish Ready successfully | No |
| Graceful shutdown | May still be CORRECT while draining | REFUSING_TRAFFIC | Stop accepting new traffic |

**Important:** readiness is a state and mechanism for infrastructure to **make routing decisions**. It is not a firewall that automatically blocks every direct request to the IP/port. HTTP connectors/probes may also be temporarily unavailable during startup; curl failing to connect before Ready does not by itself prove warm-up failed.

## 3. Why Choose ApplicationRunner Instead of @PostConstruct?

### @PostConstruct

Invoked while Spring is initializing a bean, meaning still inside **refresh()**. It suits lightweight, local initialization that does not depend on the entire application having finished configuration. Putting long I/O, multi-table queries, or network retries into @PostConstruct slows bean creation and fails as a BeanCreationException; many dependencies may not be ready yet.

### ApplicationRunner

Invoked by Spring Boot **after refresh** and before Ready. It can inject Repository, HTTP client, DataSource, Environment, and cache services, using already-configured beans. It suits mandatory startup tasks with a clear success/failure condition.

~~~java
@Bean
ApplicationRunner warmup(MyWarmupService service) {
    return args -> {
        service.loadAndValidateSynchronously();
    };
}
~~~

This is an illustrative snippet requiring MyWarmupService and a real Spring configuration. Meaning: **run() only returns after loadAndValidateSynchronously() finishes successfully**.

### Some Other Hooks

| Hook | Timing/Characteristic | Recommendation |
| --- | --- | --- |
| Constructor | During bean creation | Do not perform long I/O |
| @PostConstruct | During bean init inside refresh | Short init; do not abuse for business warm-up |
| SmartInitializingSingleton | When non-lazy singletons have initialized | Suits wiring, not the clearest startup readiness gate |
| ApplicationRunner | After Started, before Ready | **Preferred** for required warm-up |
| CommandLineRunner | Same phase, uses String args | Equivalently usable |
| @EventListener(ApplicationReadyEvent.class) | While Ready event is being published | Do not design required warm-up around this milestone |
| @Scheduled | Scheduled execution | For post-startup refresh, not a runner replacement |
| @Async task submitted by runner that returns | Work may still run after runner finishes | Dangerous if readiness depends on the task |

**Practical distinction:** a Runner is a mechanism to wait until a condition is satisfied; it is not automatically a worker pool, retry engine, or readiness probe.

## 4. Define the Data Contract Before Coding

Not every cache needs to block readiness.

### Required Group

Missing data causes requests to be **incorrect**, violate invariants, or become unsafe to serve. Examples: effective price tables, tenant/region mappings, access control policies, or mandatory schema versions.

A complete contract should specify:

1. **Data source:** database, versioned file, remote API, or shared cache.
2. **Scope:** all records or a required set of keys.
3. **Consistency:** whether records share the same version/snapshot.
4. **Validation:** no duplicate keys, no missing fields, valid version/checksum.
5. **Deadline:** individual I/O timeouts and total allowable wait budget.
6. **Failure:** fail startup rather than advertising ready when conditions are unmet.
7. **Publication:** snapshot becomes visible to readers only after validation completes.

### Best Effort Group

The cache only accelerates reads; cache misses fall back to the primary source with safe timeouts/fallbacks. If warm-up fails, the application still returns **correct** results, albeit potentially slower. It can log/emit metrics and proceed to Ready per an approved policy.

**Do not label a cache best effort just to ignore errors.** If missing cache data causes wrong prices/missing permissions or overwhelms the backend source, it is a required concern or needs an explicit degraded-mode contract.

### Know Whether an Empty Dataset Is Valid

In our example, the contract is **exactly three products**, so empty data is an error. In real systems, 0 rows may be valid; in that case use an **initialized** flag or version metadata separate from **Map.isEmpty()**. Do not use map size as the ready criterion for every problem.

## 5. Designing a Standard Warm-Up Pipeline

~~~text
ApplicationRunner.run()
      |
      +--> START: record timestamp, deadline
      |
      +--> LOAD: read from source with timeout
      |
      +--> VALIDATE: count records, check keys/prices/version
      |
      +--> BUILD: construct an isolated immutable snapshot
      |
      +--> PUBLISH: atomic swap into cache
      |
      +--> END: record duration/size then return
      |
      v
Boot completes runners
      |
      v
ApplicationReadyEvent
      |
      v
ReadinessState.ACCEPTING_TRAFFIC
~~~

If LOAD/VALIDATE fails, **do not publish a partial snapshot**. The runner must throw an exception with an actionable message, allowing SpringApplication to terminate startup unsuccessfully.

### Why Use an Immutable Snapshot?

Common mistake:

~~~java
sharedCache.clear();
for (Product item : sourceItems) {
    sharedCache.put(item.sku(), item);
}
~~~

This is a **counter-example snippet** with undefined variables/classes. Requests arriving mid-loop can see partial data; an exception halfway leaves an incomplete cache.

Better pattern:

~~~java
Map<String, Product> next = loadAndValidate();
cacheSnapshot.set(Map.copyOf(next));
~~~

This is a conceptual snippet needing real variables and methods. Build off to the side, construct an immutable Map, and use **AtomicReference.set** to publish **a single complete reference**. If Product is also an immutable record, consumers have no way to mutate the internal snapshot.

**Note:** if two maps are related, wrap both in a single immutable **CatalogSnapshot** object and swap one reference; do not publish each map separately so readers never observe mismatched versions.

## 6. Runnable Spring Boot 3.5 Example on Java 17+

The example creates three products in a mock data source with a 6-second delay so learners can observe readiness while the runner is still working. After loading, it checks for duplicate SKUs, missing names, and negative prices, then publishes the snapshot once.

The application includes:

- **Spring Web** to test GET /catalog/P101.
- **Actuator** to test GET /actuator/health/readiness or /readyz.
- Flag **demo.warmup.fail=true** to intentionally trigger a required startup failure.
- Event observer for **ApplicationReadyEvent** and **AvailabilityChangeEvent**.
- No external database/network required; the source can later be replaced with JDBC/HTTP.

### 6.1. Directory Layout

~~~text
readiness-warmup/
  pom.xml
  src/main/
    java/com/example/warmup/ReadinessWarmupApplication.java
    resources/application.properties
~~~

You can generate a Maven Wrapper from Spring Initializr; here commands use an installed Maven.

### 6.2. Complete pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>readiness-warmup</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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
~~~

The POM uses starter-parent to manage compatible Spring Framework/Jackson/Tomcat versions; the plugin creates an executable JAR. Spring Security is unnecessary for a localhost demo; in production, secure endpoints according to your architecture.

### 6.3. application.properties

~~~properties
spring.application.name=readiness-warmup
server.port=8080

# Enable probe groups even when running locally:
management.endpoint.health.probes.enabled=true
management.endpoints.web.exposure.include=health,info

# /livez and /readyz directly on the application server port:
management.endpoint.health.probes.add-additional-paths=true

# Demo-specific property:
demo.warmup.fail=false
~~~

Do not mistake demo.warmup.fail for a standard Spring Boot property; it is only read by the example code.

### 6.4. Complete Java File

Place at **src/main/java/com/example/warmup/ReadinessWarmupApplication.java**:

~~~java
package com.example.warmup;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;
import org.springframework.core.env.Environment;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ReadinessWarmupApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReadinessWarmupApplication.class, args);
    }

    public record Product(String sku, String name, long price) {
    }

    @Component
    static class CatalogSource {

        List<Product> load() throws InterruptedException {
            // Simulate I/O operation. Real clients must have timeouts.
            TimeUnit.SECONDS.sleep(6);

            return List.of(
                    new Product("P101", "Sổ tay", 45000),
                    new Product("P102", "Bút chì", 12000),
                    new Product("P103", "Kẹp giấy", 18000));
        }
    }

    @Component
    static class CatalogCache {

        private final AtomicReference<Map<String, Product>> current =
                new AtomicReference<>(Map.of());

        void publish(Map<String, Product> data) {
            current.set(Map.copyOf(data));
        }

        boolean isLoaded() {
            return !current.get().isEmpty();
        }

        Product find(String sku) {
            return current.get().get(sku);
        }
    }

    @Bean
    ApplicationRunner warmupRunner(
            CatalogSource source,
            CatalogCache cache,
            ApplicationAvailability availability,
            Environment environment) {

        return args -> {
            System.out.println("WARMUP_BEGIN readiness="
                    + availability.getReadinessState());

            boolean forceFailure = environment.getProperty(
                    "demo.warmup.fail", Boolean.class, false);

            if (forceFailure) {
                System.out.println("WARMUP_FORCED_FAILURE");
                throw new IllegalStateException(
                        "Required catalogue warm-up failed");
            }

            Map<String, Product> next = new LinkedHashMap<>();

            try {
                for (Product product : source.load()) {

                    if (product.sku() == null
                            || product.sku().isBlank()
                            || product.name() == null
                            || product.name().isBlank()
                            || product.price() < 0) {
                        throw new IllegalStateException(
                                "Invalid product in source");
                    }

                    Product previous =
                            next.putIfAbsent(product.sku(), product);

                    if (previous != null) {
                        throw new IllegalStateException(
                                "Duplicate SKU: " + product.sku());
                    }
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(
                        "Warm-up interrupted", ex);
            }

            if (next.size() != 3) {
                throw new IllegalStateException(
                        "Incomplete catalogue: expected 3");
            }

            cache.publish(next);
            System.out.println("WARMUP_DONE count=" + next.size());
        };
    }

    @RestController
    static class CatalogController {

        private final CatalogCache cache;

        CatalogController(CatalogCache cache) {
            this.cache = cache;
        }

        @GetMapping("/catalog/{sku}")
        public ResponseEntity<?> find(@PathVariable String sku) {

            // Guard in case requests bypass readiness routing.
            if (!cache.isLoaded()) {
                return ResponseEntity
                        .status(HttpStatus.SERVICE_UNAVAILABLE)
                        .body(Map.of("status", "WARMING_UP"));
            }

            Product product = cache.find(sku);

            if (product == null) {
                return ResponseEntity.notFound().build();
            }

            return ResponseEntity.ok(product);
        }
    }

    @Component
    static class ReadyObserver {

        @EventListener
        public void onReady(ApplicationReadyEvent event) {
            System.out.println("EVENT_APPLICATION_READY");
        }

        @EventListener
        public void onAvailability(AvailabilityChangeEvent<?> event) {
            if (event.getState()
                    == ReadinessState.ACCEPTING_TRAFFIC) {
                System.out.println("READINESS_ACCEPTING_TRAFFIC");
            }
        }
    }
}
~~~

### 6.5. Code Explanation and Compilation QA

- Public class **ReadinessWarmupApplication** matches the file/package name.
- Java 17 supports record Product; a nested record is static with public accessors.
- **@SpringBootApplication** enables auto-configuration and component scanning.
- Nested static classes with @Component/@RestController are managed by Spring.
- ApplicationRunner is a functional interface; the lambda is invoked by Spring Boot after refresh.
- **CatalogSource.load** uses a 6-second sleep to simulate I/O, validly declaring InterruptedException.
- **Environment.getProperty** with Boolean.class and default false uses Spring's conversion service.
- **LinkedHashMap.putIfAbsent** allows detecting duplicate SKUs before publication.
- **Map.copyOf** creates an unmodifiable snapshot through the Map interface; Product is an immutable record.
- **AtomicReference.set** publishes once atomically, preventing consumers from seeing a half-filled map.
- **ResponseEntity<?>** is valid for a 503 Map body, 404 empty body, or 200 Product.
- **AvailabilityChangeEvent<?>** listens for availability changes and filters specifically for ReadinessState.ACCEPTING_TRAFFIC.
- @EventListener(ApplicationReadyEvent) only prints a marker and is not used to load mandatory data.
- The program uses no Java API newer than 17; dependencies are declared in the POM.

In a real application, replace sleep with a client having **connect/read/query timeouts**, instead of merely measuring duration after a blocking call completes. All stdout markers in the example come from System.out, while Spring/Tomcat/Maven emit separate logs.

### 6.6. Build and Run

~~~bash
java -version
mvn -version
mvn clean package
java -jar target/readiness-warmup-0.0.1-SNAPSHOT.jar
~~~

If you have a Maven Wrapper from Initializr:

~~~bash
# Linux/macOS:
./mvnw clean package

# Windows PowerShell/cmd:
# .\mvnw.cmd clean package
~~~

Given the POM's artifactId/version, the exact JAR is **target/readiness-warmup-0.0.1-SNAPSHOT.jar**.

### 6.7. Expected Output

Lines **printed directly by the example code**, excluding Boot/Tomcat logs:

~~~text
WARMUP_BEGIN readiness=REFUSING_TRAFFIC
WARMUP_DONE count=3
EVENT_APPLICATION_READY
READINESS_ACCEPTING_TRAFFIC
~~~

The gap between BEGIN and DONE is roughly 6 seconds plus overhead. Spring Boot's **Started log** may appear before WARMUP_BEGIN or before the runner finishes; that is not the Ready event.

### 6.8. Checking After Completion

~~~bash
curl -i http://localhost:8080/actuator/health/readiness
curl -i http://localhost:8080/readyz
curl -i http://localhost:8080/catalog/P101
curl -i http://localhost:8080/catalog/UNKNOWN
~~~

After normal startup, readiness typically returns HTTP 200 with body:

~~~json
{"status":"UP"}
~~~

Product P101:

~~~json
{"sku":"P101","name":"Sổ tay","price":45000}
~~~

UNKNOWN returns 404. JSON field order and Unicode escaping depend on Jackson. What should be asserted are **status codes and data values**, not byte-for-byte headers/JSON.

### 6.9. Observing While the Runner Has Not Yet Finished

In Linux/macOS terminal A:

~~~bash
java -jar target/readiness-warmup-0.0.1-SNAPSHOT.jar &
APP_PID=$!
echo "$APP_PID"
~~~

In terminal B:

~~~bash
for i in 1 2 3 4 5 6 7 8; do
  curl -s -o /dev/null -w "HTTP=%{http_code}\n" \
    http://localhost:8080/actuator/health/readiness
  sleep 1
done
~~~

**Do not hard-code results per second.** Before the connector is ready, curl may display 000. Once the connector allows probe queries while readiness is still REFUSING_TRAFFIC, the health group may report OUT_OF_SERVICE/503. After Ready succeeds, it is normally UP/200.

The Spring Boot Reference describes availability state and notes that the connector may be unavailable in some phases; therefore cross-check **event markers and probes** rather than concluding from a single network status. Direct HTTP requests bypassing a Kubernetes Service can behave differently from routing via readinessProbe; CatalogController has its own 503 guard if the cache is not yet loaded.

### 6.10. Simulating Required Warm-Up Failure

Stop the process, then run:

~~~bash
java -jar target/readiness-warmup-0.0.1-SNAPSHOT.jar --demo.warmup.fail=true
~~~

Markers printed by the code:

~~~text
WARMUP_BEGIN readiness=REFUSING_TRAFFIC
WARMUP_FORCED_FAILURE
~~~

This error path does not print:

~~~text
WARMUP_DONE count=3
EVENT_APPLICATION_READY
READINESS_ACCEPTING_TRAFFIC
~~~

Boot logs the startup exception and closes the context per error handling. When the runner throws IllegalStateException, **Ready is not published successfully**. Do not assert exact exit codes or wrapper log strings across every shell and runtime.

## 7. Standardizing Timeouts and Retries for Production

Simulating with TimeUnit.SECONDS.sleep makes observation easy, yet **imposes no real deadline on a database or network**. A production runner needs budgets:

| Budget | Example | Meaning |
| --- | --- | --- |
| Connect timeout | 2s | Do not wait indefinitely to establish a connection |
| Query/response timeout | 5s | Bound a single DB/API call |
| Retry count | 3 attempts | Retry only transient errors |
| Backoff | 1s, 2s + jitter | Avoid synchronized retry storms |
| Overall warm-up deadline | 20s | Do not wait too long before Ready |
| Kubernetes startup budget | Service-dependent, greater than actual startup | Prevent premature kubelet restarts |

**The numbers above are purely illustrative**, not defaults of Spring Boot or a specific HTTP client.

Summing up: three attempts up to 5s each plus two backoffs totaling 3s can consume about **18s** plus validation, connection acquisition, and overhead. Calculate according to your actual libraries.

### Deadline Control Pattern

~~~java
// Pseudocode: source.fetch, validate, isTransient, publish,
// and the types are application-provided APIs.
long deadline = System.nanoTime() + budget.toNanos();

for (int attempt = 1; attempt <= maxAttempts; attempt++) {
    long remaining = deadline - System.nanoTime();
    if (remaining <= 0) {
        throw new IllegalStateException("Warm-up deadline exceeded");
    }

    try {
        Dataset dataset = source.fetch(
                Duration.ofNanos(remaining));
        validate(dataset);
        publish(dataset);
        break;
    } catch (RemoteDataException ex) {
        if (attempt == maxAttempts || !isTransient(ex)) {
            throw ex;
        }
        // Bounded backoff within remaining deadline.
    }
}
~~~

This is **not a standalone runnable file**: application variables, classes, and APIs are illustrative only. It demonstrates the required structure. Avoid writing a stopwatch around an operation that lacks a per-call timeout; checking a deadline after an operation returns cannot rescue a thread blocked indefinitely.

Do not retry permanent errors such as invalid schema, permission denied, or missing required config. Do not retry infinitely, as that can make startup probes fail forever and overload downstreams.

## 8. Pitfalls of @Async, CompletableFuture, and Virtual Threads

Broken pattern:

~~~java
@Bean
ApplicationRunner brokenWarmup(AsyncCatalogLoader loader) {
    return args -> {
        loader.loadAsync(); // Does not wait.
    };
}
~~~

This snippet is not standalone; it assumes an AsyncCatalogLoader bean. The runner returns immediately, so Boot can proceed to ApplicationReadyEvent while the async task has not finished. A CompletableFuture failing in the background does not undo a startup already marked ready.

If parallelizing loading steps is needed:

~~~java
CompletableFuture<PartA> left = service.loadPartA();
CompletableFuture<PartB> right = service.loadPartB();

CompletableFuture.allOf(left, right).join();
PartA a = left.join();
PartB b = right.join();
validateThenPublish(a, b);
~~~

This is a conceptual snippet needing service, types, and imports. **Join has no built-in timeout**; required tasks need timeouts/cancellation. When using Spring @Async, remember to enable @EnableAsync and invoke through the Spring bean proxy; self-invocation may not be intercepted.

**Virtual threads on Java 21+ do not alter readiness lifecycle.** Even with spring.threads.virtual.enabled enabled, Boot still only waits for the runner's **run() to complete**, not automatically for threads spawned by the application. Await completion and propagate failures as usual.

## 9. Multiple Runners, @Order, and Dependency Ordering

An application may have Runner A checking schema, Runner B loading policies, and Runner C warming up cache. Spring Boot supports **Ordered** or **@Order** to specify execution order when multiple ApplicationRunner/CommandLineRunner beans exist.

~~~java
@Component
@Order(10)
class SchemaCheckRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("schema-check");
    }
}
~~~

This illustrative class snippet needs imports and placement in a project. It only prints a marker and **does not actually check a schema**. When business logic has complex dependencies, it is often better to consolidate into **one coordinator runner** calling steps in explicit sequence rather than scattering @Order annotations.

If a runner throws, subsequent runners may not execute and startup fails. Do not write logic relying on another runner's side effects without explicit ordering and a clear transaction/recovery policy.

### Regarding Flyway/Liquibase

Do not hand-roll migrations inside a runner just to run before Ready. Spring Boot integrates schema migration cleanly via auto-configuration; runners can check post-conditions and warm up data after migration. If a runner seeds data with side effects, ensure idempotency and transactions.

## 10. Readiness After Startup: What If the Cache Corrupts?

ApplicationRunner only runs at startup. If cache data is lost, expires, schema changes, or the remote source fails **after already becoming Ready**, Boot does not re-run the runner automatically.

You can design a periodic or event-driven refresh task combining:

1. Building a new versioned snapshot outside the currently published reference.
2. Validating thoroughly.
3. Atomically swapping if successful.
4. If refresh fails while the old snapshot remains valid, keeping the old snapshot and alerting.
5. If the old snapshot is no longer safe to serve, transitioning the instance to **REFUSING_TRAFFIC** per an explicit policy.
6. Upon recovery, considering publishing ACCEPTING_TRAFFIC again.

Spring Boot provides the API:

~~~java
AvailabilityChangeEvent.publish(
        applicationContext,
        ReadinessState.REFUSING_TRAFFIC);
~~~

This is an illustrative snippet; ApplicationContext and imports are required. Do not manually publish ACCEPTING_TRAFFIC **before required runners finish** just to "turn readiness green".

If the cache is strictly optional, do not turn every cache miss into a readiness failure. If a shared external dependency fails, forcing every Pod unready can cause a cluster-wide outage. Design readiness around **true ability to serve** with circuit breakers/fallbacks.

## 11. Kubernetes readinessProbe, livenessProbe, and startupProbe

With Actuator configured as in section 6, you can use **/readyz** and **/livez** directly on the main port.

PodSpec fragment:

~~~yaml
spec:
  containers:
    - name: catalog
      image: registry.example.com/readiness-warmup:1.0
      ports:
        - name: http
          containerPort: 8080
      readinessProbe:
        httpGet:
          path: /readyz
          port: http
        periodSeconds: 2
        timeoutSeconds: 1
        failureThreshold: 2
      livenessProbe:
        httpGet:
          path: /livez
          port: http
        periodSeconds: 10
        timeoutSeconds: 2
        failureThreshold: 3
      startupProbe:
        httpGet:
          path: /livez
          port: http
        periodSeconds: 5
        failureThreshold: 12
~~~

This is a fragment, not a complete Deployment. Replace image with your real artifact. **startupProbe** prevents liveness from restarting an application that takes longer to prepare, while **readinessProbe** coordinates when the instance starts receiving traffic.

- **ReadinessProbe:** failing during warm-up is normal; Kubernetes does not route traffic to an unready Pod.
- **LivenessProbe:** should not directly depend on every external DB/API, as that can cause restart storms.
- **StartupProbe:** helpful for slow starts; when configured, liveness/readiness checks are deferred until the startup probe succeeds per Kubernetes semantics.
- **Separate Actuator management port:** may report healthy even when the main connector fails. Therefore Spring Boot recommends considering probe paths on the **main server port**.

**Do not assume you will always read 503 directly from the Pod at all times:** when the web connector has not opened yet or ingress has no ready endpoints, clients may see connection errors or load balancer status codes instead of Spring Actuator.

### Startup Budget

If a runner typically takes 25s, a startupProbe with periodSeconds=5 and failureThreshold=12 provides roughly a 60s budget before kubelet declares failure, still subject to timeouts, scheduling, and actual startup. Choose budgets based on cold starts and p95/p99, not a single run on a fast machine.

## 12. Warm-Up Across Multiple Replicas and Rolling Deploys

An often-overlooked risk: **thundering herd**.

If every Pod loads a large dataset from the DB, scaling from 1 to 30 replicas can trigger 30 identical heavy queries simultaneously, exhausting connection pools, spiking latency, and slowing all startups together.

Considerations:

- Scale replicas in batches, using readiness gating and rollout budgets.
- Rate limits or semaphores at genuinely constrained downstreams.
- Bounded retries, jitter, and backoff.
- Precomputed snapshots/artifacts if data is suitable for sharing.
- Version/checksum metadata so stale builds are not accidentally overwritten.
- Peak memory limits when constructing immutable snapshots while retaining the previous copy.
- Whether cache warm-up must occur on every replica or if a shared cache suffices.
- Ingress, Pod startup, and deployment progress deadline timeouts.

**A faster startup is not necessarily a better service** if it merely shifts the cost onto the first request or saturates the source DB during rollouts. Measure both **time-to-ready** and **first-request latency**.

## 13. Transactions, Side Effects, and Idempotency

Warm-ups that purely read data and build an immutable cache are usually safe to restart. However, a runner might also **seed a DB, publish messages, or allocate resources**. When startup fails and Kubernetes restarts:

- Committed data may still persist.
- One transaction may roll back while an external API already experienced a side effect.
- Re-running the runner may create duplicate rows/messages.
- Tasks running across multiple replicas may perform the same action multiple times.

Design practices:

1. Stable **business keys** and unique constraints.
2. Insert-if-absent/upsert with clear semantics.
3. Valid transaction boundaries via Spring service proxies or TransactionTemplate.
4. Distributed locks/leases if strictly one replica is allowed to execute.
5. Idempotent retries; outbox pattern when DB + message broker are both involved.
6. DB/network timeouts and recovery policies.

**An ApplicationRunner throwing does not automatically roll back already-committed effects.** Spring Boot startup failure only manages lifecycle/container teardown; it cannot undo an HTTP call or email already sent.

## 14. Comprehensive Testing

### Cache Logic Tests

- Source returns three valid records → cache holds all data and API returns them accurately.
- Duplicate SKU, blank SKU, blank name, negative price → validation fails.
- Fewer products returned → fail instead of publishing.
- Source throws InterruptedException → restore interrupt flag and fail.
- Active cache snapshot is not mutated while building the next snapshot.
- Concurrent reads during publish → never see half-populated data.
- If an empty dataset is valid in another system, use an explicit initialized state.

### Startup Lifecycle Tests

- ApplicationStartedEvent is observed **before the runner begins**.
- ReadinessState remains REFUSING_TRAFFIC during required warm-up.
- Runner succeeds → ApplicationReadyEvent/ACCEPTING_TRAFFIC follow.
- Runner throws → normal Ready is not published.
- No required Promise/Future left drifting after the runner returns.
- ReadinessProbe is never considered UP while required data is not ready.

### Integration / Kubernetes Tests

- StartupProbe provides sufficient budget when the source is slow.
- ReadinessProbe /readyz transitions to UP after warm-up.
- Direct calls bypassing readiness never return invalid business data.
- When a pod scales down, shutdown and in-flight requests follow lifecycle rules.
- Multiple pods starting concurrently do not overwhelm the DB.
- Retries on source timeouts do not cause request cascades.
- Production warm-up does not write secrets/large payloads to logs.

With @SpringBootTest, remember context caching: do not assume runners re-execute for every test method. For startup-failure scenarios, prefer tests creating a fresh context or controlled integration process runs.

## 15. Observing and Measuring Warm-Up Quality

Recommended telemetry:

| Metric / Field | Meaning |
| --- | --- |
| warmup.begin timestamp | Startup task start milestone |
| warmup.duration | Time until snapshot published |
| warmup.records.loaded | Number of records loaded |
| warmup.data.version | Snapshot version/checksum |
| warmup.validation.failure | Distinguishes invalid data failures |
| warmup.retry.attempts | Signals unstable network/source |
| application.ready time | Actual startup completion milestone |
| cache.hit/miss after Ready | Whether warm-up provides real benefit |
| pod readiness timeline | When infrastructure starts routing traffic |
| memory/GC during warm-up | Cost of loading and copying snapshots |

Illustrative log design:

~~~text
warmup.start source=catalog required=true
warmup.load.complete records=3 elapsedMs=6020
warmup.validate.complete version=v42
warmup.publish.complete count=3
readiness=ACCEPTING_TRAFFIC
~~~

This is an **illustrative log example**, not verbatim demo output. Use real measurements and versions in deployment. Do not log passwords, tokens, or sensitive record payloads.

## 16. Common Pitfalls and Fixes

| Symptom | Cause | Recommendation |
| --- | --- | --- |
| Spring logs Started but cache isn't done | Started fires before runners | Watch ApplicationReadyEvent/ReadinessState |
| App reports Ready while Future still runs | Runner returned too early | Await required tasks + propagate failure |
| Warm-up fails yet Pod becomes ready | Catch-all swallows error | Required: throw/fail startup |
| Map only contains half the records | Published while loading | Build offline, validate, atomic swap |
| 404 for an existing SKU | Source missing/invalid data | Check completeness before publication |
| Pod killed before warm-up completes | Insufficient liveness/startupProbe budget | Configure an appropriate startupProbe |
| Probe cannot connect right at start | HTTP connector not ready yet | Distinguish network failure from readiness state |
| Liveness depends on shared DB | DB outage triggers mass restarts | Keep liveness internal; handle readiness thoughtfully |
| Runner waits indefinitely | Remote client lacks timeout | Per-call timeout and overall deadline |
| Dozens of Pods warming up choke DB | Thundering herd | Rate limit, precompute, stagger rollout |
| Data goes stale after Ready | Runner executes only once | Refresh policy + atomic swap |
| Management probe UP yet app doesn't serve | Two separate connectors | Main-port /readyz and end-to-end checks |
| Valid empty cache treated as error | `!map.isEmpty()` violates contract | Explicit initialized flag |
| @PostConstruct calls slow external API | I/O inside refresh | Move into runner with deadline |
| Runner seeds duplicate rows after restart | Non-idempotent side effects | Unique keys, transactions/outbox |
| @Order insufficient to express dependencies | Runner ordering scattered | Clear coordinator and explicit dependencies |

## 17. Self-Test Exercises

**1.** Does ApplicationRunner run before or after ApplicationStartedEvent? Before or after ApplicationReadyEvent?

**2.** While the runner is still warming up, what are LivenessState and ReadinessState typically?

**3.** A runner only calls asyncLoader.load() and returns. Is warm-up guaranteed to finish before Ready?

**4.** Why is @PostConstruct less suitable than a runner for loading multiple data sources that depend on Spring-managed services?

**5.** Why shouldn't you write records one by one directly into a shared HashMap during warm-up?

**6.** What do Map.copyOf + AtomicReference.set protect? Do they automatically make mutable Product objects immutable?

**7.** If the source returns two records instead of three, will the demo reach Ready or fail startup?

**8.** If an empty cache is valid, why is checking map.isEmpty() wrong?

**9.** Why is a stopwatch alone insufficient to bound a hanging JDBC/HTTP call?

**10.** How does ReadinessProbe differ from startupProbe and livenessProbe?

**11.** If the management port differs from the main port, why doesn't probe UP prove requests to the main server succeed?

**12.** If a runner seeds data and then throws, is already-committed data automatically rolled back?

**13.** Why can warming up 30 pods be slower than warming up 1 pod?

**14.** After reaching Ready, the cache becomes corrupted. Does the runner re-run automatically, and how should readiness be managed?

### Answer Hints

1. Runner runs after Started, before Ready.
2. Liveness is CORRECT and readiness is REFUSING_TRAFFIC.
3. No; Boot waits for the runner to return, not automatically for any returned/spawned Future.
4. @PostConstruct runs during refresh, before dependencies/lifecycle are as complete as after refresh.
5. Readers can observe partial datasets, and the cache stays corrupted if an exception occurs mid-way.
6. Atomically publishing an unmodifiable map snapshot; values themselves also need to be immutable.
7. Throws IllegalStateException and does not publish Ready successfully.
8. You need an initialized state/version independent of record count.
9. The operation must have timeouts/cancellation directly in the I/O library.
10. Readiness routes traffic; startupProbe allows sufficient startup time; liveness drives container restart decisions.
11. The two connectors can fail independently; use main-port probes/end-to-end checks.
12. No; transactions, idempotency, and recovery are required.
13. DB/API resources and bandwidth are contended, creating a thundering herd.
14. No; runtime refresh is required, and depending on severity, publish REFUSING_TRAFFIC or use a fallback.

## 18. Delivery and Operations Checklist

- [ ] Required vs. best-effort data classification is clearly defined.
- [ ] Completion criteria include validation: keys, version, completeness.
- [ ] Runner executes after context refresh and before Ready.
- [ ] Required work completes **before the runner returns**.
- [ ] Source has finite network/query timeouts.
- [ ] Retries are bounded with backoff/jitter.
- [ ] Snapshot is immutable, published once after validation.
- [ ] No partial data exposure.
- [ ] Required failure throws rather than catching and returning.
- [ ] ACCEPTING_TRAFFIC is never forced prematurely.
- [ ] Valid readinessProbe configured appropriately on the main server port.
- [ ] startupProbe configured if liveness might kill a slowly starting app.
- [ ] Avoid liveness checks that continuously call shared DB/APIs.
- [ ] Runtime cache loss and recovery handling implemented.
- [ ] Metrics for time-to-ready, duration, retries, loaded records.
- [ ] Load throttling when multiple replicas start simultaneously.
- [ ] Side effects are idempotent with clear transactions.
- [ ] Tests cover happy path, invalid data, network timeout, concurrency, and restart.
- [ ] No secrets/PII written to logs.

## 19. Conclusion and Official Documentation

**A properly designed warm-up runner acts as a true conditional gate before readiness:**

~~~text
Spring context refreshed
         |
         v
ApplicationStartedEvent
         |
         v
ApplicationRunner
    load + timeout
    validate + completeness
    build immutable snapshot
    atomic publish
         |
         +--> SUCCESS --> return
         |                  |
         |                  v
         |          ApplicationReadyEvent
         |                  |
         |                  v
         |          ReadinessState.ACCEPTING_TRAFFIC
         |
         +--> FAILURE --> throw
                            |
                            v
                       Startup failure
                       NOT Ready successfully
~~~

Three key takeaways:

1. **Runners execute synchronously or await all required tasks before returning.**
2. **Validate data integrity then atomically publish**, preventing consumers from seeing an incomplete cache.
3. **Readiness and liveness have distinct meanings**; combine Actuator probes and Kubernetes routing so traffic only reaches eligible Pods.

References for the Spring Boot 3.5 branch:

1. Spring Boot 3.5 Reference — SpringApplication, Application Events and Listeners, Application Availability, ApplicationRunner: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html
2. Spring Boot 3.5 Reference — Actuator, Kubernetes Liveness and Readiness Probes, Application Lifecycle: https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html
3. Spring Boot 3.5 API — ApplicationAvailability: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/availability/ApplicationAvailability.html
4. Spring Boot 3.5 API — ReadinessState: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/availability/ReadinessState.html
5. Spring Boot 3.5 API — ApplicationRunner: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/ApplicationRunner.html
6. Spring Framework Reference — Bean lifecycle callbacks: https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
7. Kubernetes — Liveness, Readiness and Startup Probes: https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/

**Example versions:** Java 17+, Spring Boot 3.5.16, Spring MVC, and Actuator. The 6-second sleep and three products are simulated data to observe readiness; when using real JDBC/Redis/HTTP, add client timeouts, transaction/snapshot consistency, data security, and business-appropriate recovery mechanisms.