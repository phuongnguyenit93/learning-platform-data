# Distinguishing Enabling Boot Support from Automatically Converting All Tasks in an Application

**`spring.threads.virtual.enabled=true` is not a switch that turns every thread in a Java application into a virtual thread.** It is an option for **Spring Boot to use virtual threads at the integration points that Spring Boot auto-configures or supports**, when running on **Java 21 or higher**. Code that manually creates `Thread`, `ExecutorService`, `ThreadPoolExecutor`, `CompletableFuture`, or threads managed by external libraries **is not automatically rewritten** simply because this property appears in `application.properties`.

This lesson belongs to the **Spring Boot Application Runtime** module, **Virtual Threads** group, using **Spring Boot 3.3.x / Spring Framework 6.1 / Java 21**. The goal is not to recommend moving every task to virtual threads, but to identify **which task runs where**, verify with `Thread.currentThread().isVirtual()`, and choose the right change.

After this lesson, you should be able to:

- Explain how virtual threads differ from platform threads, and why they fit best for many tasks **waiting on I/O**.
- Know how `spring.threads.virtual.enabled` affects executors, schedulers, and corresponding web integrations in Spring Boot 3.3.
- Know that `@Async` does not work automatically without `@EnableAsync` and that calls not going through a Spring proxy may not be dispatched to the executor.
- Identify that manually created pools, `new Thread`, `CompletableFuture.supplyAsync`, or self-managed library threads **are not automatically migrated**.
- Measure directly using `isVirtual()` instead of guessing from thread names, configuration, or perceived performance.
- Understand risks of `@Scheduled(fixedDelay=...)`, daemon threads, pinning on Java 21, overloading external resources, and pre-production testing.

## 1. A virtual thread is a type of `Thread`, not a JVM-wide global mode

Since Java 21, virtual threads have been an official part of the Java platform under **JEP 444**. Both platform threads and virtual threads are `java.lang.Thread`, execute Java code, have stack traces, and can use appropriate synchronization mechanisms.

| Characteristic | Platform thread | Virtual thread |
| --- | --- | --- |
| Relation to OS thread | Typically bound to one OS thread for its lifetime | Scheduled by the JVM onto carrier platform threads |
| Cost with many I/O-waiting tasks | OS thread is held during wait time | Virtual thread can yield, freeing the carrier for other work |
| Typical suitable count | Bounded by OS threads and system resources | Can create far larger numbers for suitable tasks |
| How to create in Java 21 | `new Thread(...)`, `Thread.ofPlatform()`, traditional thread pools | `Thread.ofVirtual()`, `Executors.newVirtualThreadPerTaskExecutor()` |
| `Thread.currentThread().isVirtual()` | `false` | `true` |
| CPU-bound execution time | Not automatically sped up by virtual threads | Not automatically sped up by virtual threads |

Virtual threads can improve **the capacity to serve many concurrent waiting tasks** (e.g., calling HTTP, database, or sockets with blocking APIs), rather than **making a heavy CPU computation run faster**. They also do not remove limits of database connection pools, remote API rate limits, memory, or system resources.

### Try with plain Java 21, without Spring

Create `ThreadKinds.java`:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class ThreadKinds {
    public static void main(String[] args) throws Exception {
        System.out.println(
                "mainVirtual=" + Thread.currentThread().isVirtual());

        try (ExecutorService fixed = Executors.newFixedThreadPool(1);
             ExecutorService virtual = Executors.newVirtualThreadPerTaskExecutor()) {

            boolean fixedResult = fixed.submit(
                    () -> Thread.currentThread().isVirtual()).get();

            boolean virtualResult = virtual.submit(
                    () -> Thread.currentThread().isVirtual()).get();

            System.out.println("fixedPoolVirtual=" + fixedResult);
            System.out.println("explicitVirtual=" + virtualResult);
        }
    }
}
~~~

Compile and run with **JDK 21+**:

~~~bash
javac ThreadKinds.java
java ThreadKinds
~~~

Lines printed by the program:

~~~text
mainVirtual=false
fixedPoolVirtual=false
explicitVirtual=true
~~~

There is no Spring Boot, no property, and a virtual thread is still created. This is a **Java feature**, not something that only exists when Spring Boot enables support. Conversely, a default `newFixedThreadPool` continues to use platform threads if you do not actively change how the executor is created.

## 2. What does `spring.threads.virtual.enabled` actually indicate?

In Spring Boot 3.3, the configuration:

~~~properties
spring.threads.virtual.enabled=true
~~~

or:

~~~yaml
spring:
  threads:
    virtual:
      enabled: true
~~~

instructs Spring Boot to use virtual thread support **in the relevant integration parts** when the application runs on **Java 21 or later**.

Conditions must be separated clearly:

1. **JVM:** actually run on Java 21+; do not merely declare `sourceCompatibility` or `toolchain` and run production on an older JVM.
2. **Spring Boot:** a version with virtual threads support, such as Spring Boot 3.3.
3. **Integration:** the component actually uses Boot-configured executor/scheduler/web-server integration; it is not replaced by an incompatible custom executor.
4. **Call path:** the code actually passes through that mechanism. A synchronous method called directly does not automatically become an async task.

The configuration does **not** mean the following:

~~~text
spring.threads.virtual.enabled=true
    X  Replace all new Thread(...) in source
    X  Replace every Executors.newFixedThreadPool(...)
    X  Switch every CompletableFuture.supplyAsync(...) to virtual
    X  Force every third-party library to use virtual threads
    X  Move every CPU-bound loop to virtual
    X  Turn all Netty event-loop threads into virtual
    X  Guarantee every method called after run() runs virtually
~~~

You need to inspect the actual code and executor configuration to know where tasks are dispatched.

## 3. Scope table: what does Boot support, and what needs separate handling?

This table considers **Spring Boot 3.3** with JDK 21+, and does not automatically apply verbatim to every Boot version or library.

| Execution path | What enabling the property can do? | Conditions or limitations |
| --- | --- | --- |
| HTTP requests on Boot-managed **embedded Tomcat/Jetty** | Has integration using virtual threads for request handling | Depends on actual server and not replacing executor config manually |
| `@Async` via Spring async infrastructure | Auto-config `AsyncTaskExecutor` uses `SimpleAsyncTaskExecutor` with virtual threads | Requires `@EnableAsync` and call going through Spring proxy; custom executor can override |
| Spring MVC asynchronous request processing | Uses appropriate Boot-managed `applicationTaskExecutor` | Does not mean every controller is moved to another task |
| Spring for GraphQL `Callable` async | Can use auto-configured executor | Only processing paths that actually go through the integration |
| Spring WebFlux **blocking execution support** | Can use Boot task executor when offloading blocking work to the executor | Does **not** switch Reactor Netty event-loop threads to virtual by default |
| `@Scheduled` with auto-configured scheduler | Uses `SimpleAsyncTaskScheduler` supporting virtual threads | Requires `@EnableScheduling`; fixed-delay has a scheduler-thread exception |
| Self-written `Executors.newFixedThreadPool(...)` | **Does not change automatically** | To use virtual, explicitly change the executor or dispatch path |
| `new Thread(...)` or `Thread.ofPlatform()` | **Does not change automatically** | Remains a platform thread if created via platform API |
| `Executors.newVirtualThreadPerTaskExecutor()` | Still creates virtual threads even when Boot property is `false` | This is an explicit Java decision in the application |
| `CompletableFuture.supplyAsync(...)` without passing an executor | **Does not automatically switch to Boot executor** | Defaults to `ForkJoinPool.commonPool()` or JDK fallback mechanism |
| `@Async("legacyExecutor")` | Uses the executor named `legacyExecutor` | If this executor is a platform pool, the task stays on platform |
| Reactor `publishOn`/`subscribeOn` with default schedulers | **Not rewritten automatically** | Must inspect the chosen scheduler, not just look at Boot's property |
| Thread pool managed by an SDK/client/broker itself | Cannot be inferred to change automatically | Check each SDK's corresponding documentation/integration |

**Emphasis:** integration is a specific feature. Saying “Boot supports virtual threads” does not prove “all application threads are virtual”.

## 4. Auto-configured task executor: the most important support point

According to Spring Boot 3.3 task execution documentation, **when no application-provided `Executor` bean exists**, Boot auto-configures an `AsyncTaskExecutor`:

~~~text
Java 21+, spring.threads.virtual.enabled=false
    -> ThreadPoolTaskExecutor (platform thread pool)

Java 21+, spring.threads.virtual.enabled=true
    -> SimpleAsyncTaskExecutor using virtual threads
~~~

`SimpleAsyncTaskExecutor` in this configuration uses a **task-per-thread** model, not a traditional platform worker pool. When running with virtual threads, thread-pool sizing properties like `spring.task.execution.pool.core-size`, `max-size`, and `queue-capacity` **no longer have meaning for the Boot-created virtual executor**. That does **not** mean all custom pools in the application are disabled.

Some integrations that `applicationTaskExecutor` can serve in Spring Boot 3.3:

- Running `@Async` methods when Spring async support is enabled and no other executor takes precedence.
- Spring MVC asynchronous request processing.
- Certain asynchronous paths in Spring for GraphQL.
- Offloading blocking execution to an executor in Spring WebFlux.

### Why is a custom `Executor` so important?

If you declare your own `Executor` bean:

~~~java
@Configuration
public class LegacyExecutorConfig {
    @Bean(destroyMethod = "shutdown")
    ExecutorService legacyExecutor() {
        return Executors.newFixedThreadPool(8);
    }
}
~~~

this **illustrative** snippet requires importing `@Configuration`, `@Bean`, `ExecutorService`, and `Executors` in a Spring project. It can cause Boot's default executor auto-configuration to **back off**. Then, `@Async` tasks may use the existing custom executor according to Spring's executor selection rules, rather than automatically moving to virtual threads.

Some Spring Boot 3.3 rules:

- When a custom `Executor` is present in the context, executor selection for `@EnableAsync` and GraphQL may follow the custom bean.
- Spring MVC/WebFlux require a suitable `AsyncTaskExecutor` type and `applicationTaskExecutor` name for corresponding integrations.
- If multiple `Executor` beans exist, the names `taskExecutor` and `applicationTaskExecutor` along with `AsyncConfigurer` are points to inspect as intended.
- `@Async("legacyExecutor")` explicitly specifies the custom executor by name or qualifier, so Boot will **not** silently ignore that choice.

**Do not copy defaults about `spring.task.execution.mode=force` from newer Spring Boot versions onto 3.3 without cross-checking.** This lesson is pinned to Spring Boot 3.3 behavior; for other versions, re-read the exact documentation for that version.

### `@Async` only takes effect when Spring manages the call

~~~java
@Service
public class AsyncService {

    @Async
    public CompletableFuture<Boolean> checkThread() {
        return CompletableFuture.completedFuture(
                Thread.currentThread().isVirtual());
    }
}
~~~

This is an **illustrative class snippet**, requiring imports for `@Service`, `@Async`, and `CompletableFuture`, along with `@EnableAsync` in Spring configuration. For the task to run in an executor:

- The `@Async` method should be called **through the bean proxy provided by Spring**, e.g., controller A calls service bean B.
- Internal calls `this.checkThread()` within the same bean can **bypass the proxy**; the method runs synchronously on the current thread.
- If the method has `@Async("someExecutor")`, inspect the chosen executor, not only the global property.
- Adding `@Async` without enabling `@EnableAsync` in a standard Spring project does not ensure Spring activates async advice.

Do not confuse: an activated async method and a task using a virtual thread are **two separate concerns**. They connect via the chosen executor, yet are not a single operation.

## 5. Scheduling: real support, yet not all schedule types behave alike

If scheduling is enabled (usually via `@EnableScheduling`), Spring Boot can auto-create a scheduler to run `@Scheduled`:

~~~text
Virtual threads off:
  ThreadPoolTaskScheduler (pool-backed)

Virtual threads on and suitable conditions:
  SimpleAsyncTaskScheduler (virtual-thread capable)
~~~

`SimpleAsyncTaskScheduler` operates with a single coordinating scheduler thread and can create a separate thread for each execution. **Important Spring Framework 6.1 exception:** `@Scheduled(fixedDelay=...)` tasks use **a single scheduler thread** to preserve fixed-delay semantics, so they may not have the expected parallelism. Tasks using `fixedRate` or `cron` fit the virtual-thread-per-task scheduler model better, though overlap risks and actual load must still be checked.

An illustrative example placed in a bean:

~~~java
@Component
class TimedJobs {
    @Scheduled(fixedRate = 5000)
    void poll() {
        System.out.println(
                "scheduledVirtual=" + Thread.currentThread().isVirtual());
    }
}
~~~

The snippet above requires importing `@Component`, `@Scheduled`, and `@EnableScheduling` configuration. **Do not predict stdout line counts or exact timing**, as schedules depend on application start and stop times.

When virtual threads are enabled:

- `spring.task.scheduling.pool.size` and pool-related properties are not used to control `SimpleAsyncTaskScheduler` like `ThreadPoolTaskScheduler`.
- If you define your own `TaskScheduler` or `SchedulingConfigurer` selecting a custom scheduler, the outcome depends on that scheduler.
- An `@Scheduled` method not managed by Spring as a valid bean/scheduler will not start automatically just because the property is enabled.
- For tasks at risk of overlapping or accessing shared resources, limit concurrency and verify correctness.

### Virtual threads are daemon: the scheduler-only application issue

Java virtual threads are **daemon threads**. If the process **has no non-daemon threads left**, the JVM can exit even if you think “scheduled jobs still remain”. When needing to keep the JVM running, Spring Boot 3.3 recommends:

~~~properties
spring.threads.virtual.enabled=true
spring.main.keep-alive=true
~~~

`spring.main.keep-alive=true` keeps the process alive even when remaining work consists of daemon/virtual threads. This is especially important for **CLI applications running `@Scheduled` without a web server or other non-daemon work**.

In a web application, the server lifecycle may have its own mechanism keeping the process alive; do not generalize “whenever virtual threads are enabled, the JVM always exits”. Check according to your actual application type and server.

## 6. HTTP requests: Tomcat/Jetty differ from the WebFlux event loop

In Spring Boot 3.3 on Java 21+, embedded **Tomcat/Jetty** is supported by Boot configuration to handle HTTP requests using virtual threads when the property is enabled and the matching web-server config is active. A synchronous MVC controller method handling a request can therefore be invoked on a virtual thread.

This does **not** mean:

- The `main` thread becomes virtual.
- Every internal Tomcat, connector, acceptor, JVM GC, and SDK thread becomes virtual.
- A controller calling a custom executor makes those custom tasks virtual.
- Reactor Netty event loops of a WebFlux app automatically turn into virtual threads.
- Every HTTP client in the application changes its executor or protocol.

With Spring WebFlux, the event-loop/non-blocking model remains. Boot's virtual executor integration can play a role in **blocking execution support** when work is properly offloaded, rather than being a switch that turns the entire reactive pipeline into a virtual-thread-per-operator model.

A helpful distinction table:

| Scenario | What must be checked |
| --- | --- |
| `@RestController` with Spring MVC and embedded Tomcat | `Thread.currentThread().isVirtual()` inside the request handler |
| `@Async` called by a controller | Thread inside the async method, and actual executor used |
| Controller calling `Executors.newFixedThreadPool` | Thread inside the pool, not the controller's thread |
| Reactive pipeline with `publishOn(Schedulers.boundedElastic())` | Reactor's actual scheduler/version/config, not inferred from Boot's flag |
| Separate HTTP client library with a thread pool | Client's executor and documentation |

**One request can traverse both virtual and platform threads**, depending on where work is handed off. Labeling an entire request as “virtual” just because the controller entry point is virtual can lead to misunderstandings.

## 7. Runnable Spring Boot 3.3 example: four execution paths, four results

This example uses **Spring Boot 3.3.13 + Java 21 + Gradle**, with embedded Tomcat from `spring-boot-starter-web`. The `GET /threads` endpoint directly measures:

1. **`requestVirtual`:** the thread executing the controller (served by Tomcat).
2. **`asyncVirtual`:** the thread executing an `@Async` method through another Spring bean.
3. **`legacyPoolVirtual`:** a thread from a manually created `Executors.newFixedThreadPool(1)`.
4. **`explicitVirtual`:** a thread explicitly created with `Thread.ofVirtual()`.

This is a behavior-verification demo, not a production architecture: do not spawn a new thread per request outside experimentation, and do not rely on synchronous `Future.get()` to build high-load systems without considering timeouts/backpressure.

### 7.1. Project structure

~~~text
boot-virtual-scope-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/com/example/virtualscope/
    │   ├── VirtualScopeApplication.java
    │   ├── AsyncProbe.java
    │   └── ThreadProbeController.java
    └── resources/application.properties
~~~

### 7.2. File `settings.gradle`

~~~groovy
rootProject.name = 'boot-virtual-scope-demo'
~~~

### 7.3. File `build.gradle`

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    // Gradle native BOM manages compatible starter versions.
    implementation platform(
            org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Note **Java 21**, not just Java 17 as in many typical Spring Boot examples. Use a Gradle version compatible with Spring Boot 3.3 and a JDK 21+ to **run the actual JVM**. The Gradle toolchain uses a Java 21 compiler, yet runtime `java -version` must also show Java 21+.

The BOM is declared so `spring-boot-starter-web` does not need an explicit version. Do not remove the BOM thinking the `org.springframework.boot` plugin alone always manages every dependency version automatically.

### 7.4. `application.properties`

~~~properties
server.port=8080
spring.threads.virtual.enabled=true
~~~

This is the default application value in the demo. To run a comparison, we will override it with `--spring.threads.virtual.enabled=false` without **editing code**.

### 7.5. Application class and `@EnableAsync`

`src/main/java/com/example/virtualscope/VirtualScopeApplication.java`:

~~~java
package com.example.virtualscope;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableAsync;

@SpringBootApplication
@EnableAsync
public class VirtualScopeApplication {

    public static void main(String[] args) {
        System.out.println(
                "MAIN virtual=" + Thread.currentThread().isVirtual());
        SpringApplication.run(VirtualScopeApplication.class, args);
    }
}
~~~

**Why include `@EnableAsync`?** Because it is the condition enabling execution of `@Async` methods through Spring async infrastructure. Enabling only the virtual-thread property **does not automatically make normal methods async**.

The line `MAIN virtual=false` shows that `main` remains a platform thread even though Boot is about to use virtual threads for subsequent integrations.

### 7.6. Service using `@Async`

`src/main/java/com/example/virtualscope/AsyncProbe.java`:

~~~java
package com.example.virtualscope;

import java.util.concurrent.CompletableFuture;

import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class AsyncProbe {

    @Async
    public CompletableFuture<Boolean> inspect() {
        boolean isVirtual = Thread.currentThread().isVirtual();
        return CompletableFuture.completedFuture(isVirtual);
    }
}
~~~

`inspect()` is dispatched by Spring AOP/proxy to the appropriate executor when invoked from another bean. It records the status of **the thread running the method body**, not the caller's thread. Here `CompletableFuture.completedFuture(...)` wraps the value measured inside the method; there is no `CompletableFuture.supplyAsync` with an unclear executor.

Do not call `new AsyncProbe().inspect()` or `this.inspect()` and expect async behavior: those calls do not go through the Spring proxy.

### 7.7. Controller comparing thread sources

`src/main/java/com/example/virtualscope/ThreadProbeController.java`:

~~~java
package com.example.virtualscope;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

import jakarta.annotation.PreDestroy;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ThreadProbeController {

    private final AsyncProbe asyncProbe;

    // This is just a controller field, NOT an @Bean Executor.
    // It is kept fixed as a platform-thread pool in both modes.
    private final ExecutorService legacyPool =
            Executors.newFixedThreadPool(1);

    public ThreadProbeController(AsyncProbe asyncProbe) {
        this.asyncProbe = asyncProbe;
    }

    @GetMapping("/threads")
    public Map<String, Boolean> check() throws Exception {
        boolean requestVirtual = Thread.currentThread().isVirtual();

        // Call through the bean/proxy, since AsyncProbe is a separate @Service.
        boolean asyncVirtual = asyncProbe.inspect()
                .get(5, TimeUnit.SECONDS);

        Future<Boolean> legacyFuture = legacyPool.submit(
                () -> Thread.currentThread().isVirtual());
        boolean legacyPoolVirtual = legacyFuture.get(5, TimeUnit.SECONDS);

        AtomicBoolean explicitResult = new AtomicBoolean();
        Thread explicit = Thread.ofVirtual().start(() ->
                explicitResult.set(Thread.currentThread().isVirtual()));
        explicit.join();

        Map<String, Boolean> result = new LinkedHashMap<>();
        result.put("requestVirtual", requestVirtual);
        result.put("asyncVirtual", asyncVirtual);
        result.put("legacyPoolVirtual", legacyPoolVirtual);
        result.put("explicitVirtual", explicitResult.get());
        return result;
    }

    @PreDestroy
    public void closePool() {
        legacyPool.shutdownNow();
    }
}
~~~

**Understand the `legacyPool` field accurately:** because the executor is created as a **private field**, not registered as an `@Bean Executor`, it **does not cause Boot's auto-configured task executor to back off**. This is an intentional demo design to preserve `@Async`'s executor while still observing a pool managed directly by application code.

Creating a fixed platform thread pool is solely to demonstrate the difference. In a real application, manage pool size, queue, shutdown, and backpressure based on load. Do not create a separate pool per request.

### 7.8. Run with virtual threads enabled

With the project's Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

If only a pre-installed Gradle is available, you can use `gradle bootRun`.

In another terminal:

~~~bash
curl -sS http://localhost:8080/threads
~~~

With **JDK 21+**, Spring Boot 3.3.13, embedded Tomcat, and **no custom `Executor` bean altering auto-configuration**, the expected JSON is:

~~~json
{
  "requestVirtual": true,
  "asyncVirtual": true,
  "legacyPoolVirtual": false,
  "explicitVirtual": true
}
~~~

JSON may be printed on one line; key order is prepared with `LinkedHashMap` for readability. Aside from JSON, the server console will show Spring Boot startup logs and the line:

~~~text
MAIN virtual=false
~~~

**Explanation of each value:**

- `requestVirtual=true`: Boot-configured Tomcat handles the request on a virtual thread in the described demo environment.
- `asyncVirtual=true`: `@Async` passes through the auto-configured executor using virtual threads.
- `legacyPoolVirtual=false`: manually created `Executors.newFixedThreadPool(1)` still uses a platform thread.
- `explicitVirtual=true`: `Thread.ofVirtual()` creates a virtual thread **regardless of Boot's flag**.

### 7.9. Run the same code again with virtual threads disabled

Stop the previous server, then restart:

~~~bash
./gradlew bootRun --args="--spring.threads.virtual.enabled=false"
~~~

On PowerShell:

~~~powershell
.\gradlew.bat bootRun --args="--spring.threads.virtual.enabled=false"
~~~

Call again:

~~~bash
curl -sS http://localhost:8080/threads
~~~

Expected output under demo conditions:

~~~json
{
  "requestVirtual": false,
  "asyncVirtual": false,
  "legacyPoolVirtual": false,
  "explicitVirtual": true
}
~~~

When Boot's property is off, the Tomcat controller uses platform request threads and the auto-configured `@Async` executor uses a platform pool. The two application-controlled sources **do not change**: the legacy pool remains platform and `Thread.ofVirtual()` remains virtual.

This demonstrates:

> **Enabling Boot support changes Boot-managed integration paths, rather than automatically converting all tasks or disabling Java's ability to create virtual threads directly.**

If in a real project you see `asyncVirtual=false` despite enabling the flag, do not jump to concluding Spring Boot has a bug. Check `@EnableAsync`, custom executor beans, `@Async("...")`, `AsyncConfigurer`, proxy invocation, and runtime JDK.

### 7.10. Build and run JAR directly

~~~bash
./gradlew clean bootJar
java -version
java -jar build/libs/boot-virtual-scope-demo-1.0.0.jar \
     --spring.threads.virtual.enabled=true
~~~

The JAR filename above follows the sample project name/version; if Gradle reconfigures classifier or artifact name, use the actual build name. On JDKs lower than 21, `Thread.ofVirtual()`/`Thread.isVirtual()` APIs are unavailable, so **do not run the same Java 21 project on a Java 17 runtime**.

## 8. Self-test with JUnit and HTTP instead of guessing

The lab can add `spring-boot-starter-test` to `build.gradle`:

~~~groovy
dependencies {
    testImplementation platform(
            org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

This is **a snippet to merge into the existing build file**; if `dependencies` already exists, **only add the two dependency lines to the existing block** instead of creating two blocks just because the example presents them separately.

### Test with virtual threads enabled

File `src/test/java/com/example/virtualscope/VirtualEnabledTest.java`:

~~~java
package com.example.virtualscope;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = "spring.threads.virtual.enabled=true")
class VirtualEnabledTest {

    @Autowired
    TestRestTemplate rest;

    @Test
    void managedPathsUseVirtualAndLegacyPoolStaysPlatform() {
        Map<?, ?> body = rest.getForObject("/threads", Map.class);

        assertEquals(Boolean.TRUE, body.get("requestVirtual"));
        assertEquals(Boolean.TRUE, body.get("asyncVirtual"));
        assertEquals(Boolean.FALSE, body.get("legacyPoolVirtual"));
        assertEquals(Boolean.TRUE, body.get("explicitVirtual"));
    }
}
~~~

### Test with virtual threads disabled

File `src/test/java/com/example/virtualscope/VirtualDisabledTest.java`:

~~~java
package com.example.virtualscope;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = "spring.threads.virtual.enabled=false")
class VirtualDisabledTest {

    @Autowired
    TestRestTemplate rest;

    @Test
    void propertyOffDoesNotDisableExplicitVirtualThreads() {
        Map<?, ?> body = rest.getForObject("/threads", Map.class);

        assertEquals(Boolean.FALSE, body.get("requestVirtual"));
        assertEquals(Boolean.FALSE, body.get("asyncVirtual"));
        assertEquals(Boolean.FALSE, body.get("legacyPoolVirtual"));
        assertEquals(Boolean.TRUE, body.get("explicitVirtual"));
    }
}
~~~

Run:

~~~bash
./gradlew test
~~~

The two test classes use different property values, so Spring Boot Test requires separate contexts per configuration. They are **behavior checks**, not throughput benchmarks. Do not infer latency from Gradle test duration because Gradle/JUnit/test context startup differs from production.

If using a server other than Tomcat, a custom `Executor`, custom `TaskScheduler`, or other Boot configuration, adjust the expected results to **actual supported capabilities** instead of copying the JSON above verbatim.

## 9. Manually converting tasks outside Boot: places commonly overlooked

### `new Thread(...)`

~~~java
Thread worker = new Thread(() ->
        System.out.println(Thread.currentThread().isVirtual()));
worker.start();
worker.join();
~~~

This is an illustrative snippet inside a method with `throws InterruptedException` or corresponding handling. It uses a platform thread via default construction, independent of `spring.threads.virtual.enabled`.

To explicitly use virtual:

~~~java
Thread worker = Thread.ofVirtual().start(() ->
        System.out.println(Thread.currentThread().isVirtual()));
worker.join();
~~~

When running Java 21, the output of the second snippet is:

~~~text
true
~~~

Not because Boot enabled the flag, but because code directly calls `Thread.ofVirtual()`.

### Self-created `ExecutorService`

~~~java
ExecutorService oldPool = Executors.newFixedThreadPool(16);
~~~

The line above creates a traditional platform thread pool. Boot's flag does not automatically turn the pool virtual. If appropriate for the workload model, you can explicitly create:

~~~java
ExecutorService virtualExecutor =
        Executors.newVirtualThreadPerTaskExecutor();
~~~

This snippet is **a fragment**, not a complete Java program. If code creates an executor, close it properly per lifecycle: `try-with-resources` for local tasks, or `shutdown()`/`shutdownNow()` per policy if long-lived.

A virtual thread executor **is not a thread pool that needs old-style core/max-size settings**. Concurrency limits should be set according to **scarce resources** such as DB connections, downstream requests, or queue capacity, not by “only creating N virtual threads”.

### `CompletableFuture.supplyAsync(...)`

~~~java
CompletableFuture<Boolean> result =
        CompletableFuture.supplyAsync(
                () -> Thread.currentThread().isVirtual());
~~~

The snippet above defaults to the common pool or JDK-managed fallback path, **not automatically picking Spring Boot's `applicationTaskExecutor`**. To control the executor, pass it explicitly:

~~~java
CompletableFuture<Boolean> result =
        CompletableFuture.supplyAsync(
                () -> Thread.currentThread().isVirtual(),
                virtualExecutor);
~~~

Here `virtualExecutor` must be an already created and managed `Executor`. If it is `Executors.newVirtualThreadPerTaskExecutor()`, the task runs on a virtual thread. If it is a fixed pool, the task runs on a platform thread.

This also applies to Java APIs using a default executor or accepting a dedicated executor: **you must identify the source executor** to be certain of the thread type.

### `@Async("someExecutor")`

~~~java
@Async("reportExecutor")
public CompletableFuture<String> generateReport() {
    return CompletableFuture.completedFuture("done");
}
~~~

This is a fragment inside a Spring-managed bean. It requests using `reportExecutor` selected by qualifier. If `reportExecutor` is a platform `ThreadPoolTaskExecutor` or a fixed-pool `ExecutorService`, the method keeps running on platform threads **even when the Boot property is enabled**.

Changing only the `@Async` annotation while ignoring the actual executor is not enough to migrate the work.

### Reactor, Kafka, RabbitMQ, SDKs

Some technologies have **dedicated integrations** with Spring Boot virtual-thread support in specific versions (for example, certain listener containers). However, that **does not allow concluding every thread in a Kafka client, RabbitMQ client, Netty event loop, HTTP SDK, or file-processing library changes type**.

For each technology, you must:

1. Identify the bean/container factory and the actual executor/scheduler used.
2. Read the corresponding documentation **for the exact version**.
3. Observe `Thread.currentThread().isVirtual()` inside critical callbacks.
4. Measure actual load and errors before deciding to change configuration.

Do not put the assumption “virtual enabled means 100% virtual threads” into dashboards or operational docs.

## 10. Distinguishing handling many requests from spawning new tasks

Suppose a synchronous controller handles:

~~~java
@GetMapping("/report")
public String report() {
    return reportService.generate();
}
~~~

When Tomcat processes the request on a virtual thread, the **synchronous** Java call `reportService.generate()` normally runs on **that same virtual thread** if there is no thread handoff point. This **does not spawn a new virtual thread for every method call**.

Conversely:

~~~java
@GetMapping("/report")
public CompletableFuture<String> report() {
    return reportService.generateAsync();
}
~~~

If `generateAsync()` is handled by an `@Async` proxy or an appropriate executor, it runs on **the executor's task thread**, which may be a **different** virtual thread. One request can use multiple threads, whereas a synchronous method can simply be a call on the same stack.

This is why you need to measure at **the point where the code actually executes**, not merely check an `Environment` property.

### Distinguishing thread name from thread type

Do not write:

~~~java
boolean virtual = Thread.currentThread().getName()
        .contains("virtual");
~~~

Thread names can be customized or empty; this is not a contract check. On Java 21, use:

~~~java
boolean virtual = Thread.currentThread().isVirtual();
~~~

If you want diagnostic logs, record both `isVirtual()` and thread name, along with operation/trace ID. Avoid logging too frequently on high-load paths.

## 11. When virtual threads are enabled, what can degrade performance?

Virtual threads fit when **many concurrent tasks block waiting on I/O** while you still want readable blocking-style code. Yet they **do not give the CPU more cores**, do not change DB read speed, and do not eliminate contention.

### CPU-bound work

If 100 tasks concurrently compute heavy hashes or encrypt data saturating CPU, spawning 100 virtual threads **does not guarantee shorter total time** than using controlled platform threads. The JVM still schedules them across finite carrier threads and physical CPUs.

### Downstream services and connection pools

For example, the application creates thousands of virtual threads while the DB pool has only 20 connections. The remaining tasks still have to wait for a connection. Sending too many simultaneous requests to a rate-limited API can trigger timeouts/rate limiting.

Therefore, do not make virtual threads an excuse to drop **concurrency, queue, backpressure**, and **timeout** limits. Bound according to actual downstream capacity, not how many virtual threads the JVM can create.

### Pinning on Java 21

In Java 21, a virtual thread can get **pinned** to its carrier thread when performing a blocking operation inside a `synchronized` block or suitable native/foreign code. The carrier is then not released to serve other virtual threads, potentially lowering throughput if blocking occurs **frequently and for long durations**.

Example illustrating the issue:

~~~java
synchronized (lock) {
    blockingRemoteCall();
}
~~~

This is **illustrative code**, assuming `lock` and `blockingRemoteCall()` already exist. Not every `synchronized` block is dangerous: short locks protecting in-memory state are usually fine. What needs measuring is **prolonged blocking while the thread is pinned**.

With Java 21, you can use:

~~~bash
java -Djdk.tracePinnedThreads=short -jar app.jar \
     --spring.threads.virtual.enabled=true
~~~

or use **Java Flight Recorder (JFR)**, specifically the `jdk.VirtualThreadPinned` event when recorded. Do not replace every `synchronized` mechanically. Only fix sections actually causing long and frequent pinning, such as considering `ReentrantLock` when it fits the synchronization contract.

**Version note:** pinning mechanics changed in newer JDKs. This exercise is fixed on **Java 21**; do not apply every conclusion about `synchronized` to future JDKs without testing.

## 12. ThreadLocal, context propagation, and functional bugs

Virtual threads still support `ThreadLocal`. Yet when there are many short-lived task threads and transitions across Spring MVC, `@Async`, executors, Reactor, or external libraries, thread-attached data may **not automatically propagate to another thread**.

Data to inspect:

- Logging MDC, trace ID, correlation ID.
- Spring Security `SecurityContext`.
- Request context, locale, tenant context.
- Transaction context normally bound to a thread.
- Libraries using `ThreadLocal` to cache large objects or hold long-lived state.

Do not assume `@Transactional` on the request thread automatically carries the transaction over to a new `@Async` task thread. Async creates a thread boundary, so transaction/context propagation must be designed explicitly.

`TaskDecorator` or dedicated context propagation mechanisms can help, though usage varies by integration and version. **Virtual threads do not solve context propagation automatically**, and conversely, using virtual threads does not wipe out all thread-locals; the key issue is **thread-handoff boundaries**.

### Why shouldn't `ThreadLocal` be used as an unbounded cache?

Even with a platform thread pool having few long-lived workers, storing large state in `ThreadLocal` carries leak risks. With virtual-thread-per-task, thread counts can be vastly higher; inappropriate per-thread caching can rapidly inflate allocation/memory. Design caches scoped to the application, request, or appropriate data store, and measure actual footprint.

## 13. Distinguishing concurrency optimization from latency optimization

An I/O request taking 500 ms to receive a response from a remote service **does not magically finish in 5 ms** because it is on a virtual thread. The benefit may be that the JVM does not have to hold a dedicated OS thread throughout that 500 ms wait, enabling more concurrent requests under suitable conditions.

To decide whether to enable the property or migrate more tasks, measure:

| Metric | Purpose |
| --- | --- |
| Concurrent requests/throughput | How much more I/O-waiting work does the app serve? |
| p50/p95/p99 latency | Does tail latency improve or degrade? |
| Error rate, timeouts | Is downstream becoming overloaded? |
| CPU utilization and carrier saturation | Has work become CPU-bound? |
| Heap/RSS/GC | Do many concurrent tasks increase memory? |
| Connection pool wait time | Have DB/HTTP client pools become a bottleneck? |
| JFR virtual-thread pinning events | Is there long/frequent pinned blocking? |
| Thread dump/metrics and `isVirtual()` | Which thread type do actual code paths run on? |
| Shutdown and unfinished work | Do executors close cleanly, or are tasks dropped mid-flight? |

### A/B testing

1. **Baseline:** Java 21, Spring Boot 3.3, `spring.threads.virtual.enabled=false`; keep versions, artifacts, and configuration consistent.
2. **Candidate:** enable only `spring.threads.virtual.enabled=true`; inspect framework executors/web-server and actual custom executors.
3. **Workload sample:** include I/O-heavy endpoints, CPU-heavy work, scheduled jobs, and tasks using custom pools.
4. **Appropriate warm-up:** separate cold startup/classloading from steady-state load measurements.
5. **Constraints:** keep the same CPU, memory, DB connections, upstream rate limits, heap, and environment type.
6. **Read results:** if throughput rises while p99/5xx or memory spikes sharply, do not declare the config better based on throughput alone.

**Do not assume every task must migrate.** You can keep a platform pool for CPU-heavy groups or groups needing strict concurrency bounds, while using virtual threads for I/O-heavy tasks via an appropriate executor.

## 14. Process for auditing every execution flow in a real project

Before enabling in production, build a table:

| Work path | Who creates the thread/executor? | Already virtual? | Action needed? |
| --- | --- | --- | --- |
| Spring MVC request on embedded Tomcat | Boot/server integration | Check `isVirtual()` in controller | Measure web latency/concurrency |
| `@Async` service | AsyncConfigurer or Boot `applicationTaskExecutor` | Check inside method | Check proxy/qualifier/custom executor |
| `@Scheduled` job | TaskScheduler / SchedulingConfigurer | Check inside method and trigger type | Pay special attention to fixedDelay |
| `CompletableFuture.supplyAsync` | JDK commonPool or passed executor | Check inside supplier | Pass explicit executor if needed |
| Self-written `new Thread` or fixed pool | Application code | Platform if created via platform API | Change intentionally, clean up executor properly |
| Kafka/Rabbit listener | Container factory and version-specific integration | Measure inside listener | Check actual config/version |
| Reactor pipeline | Reactor Scheduler | Measure inside key operator | Do not infer from Boot flag |
| HTTP client/DB driver | Library, network loop, pool | Check docs/metrics | Check connection/resource limits |
| Batch job, standalone script | Custom code | Depends on creation method | Evaluate each JVM executable separately |

For each row:

1. Record the actual bean/executor name or thread-creation API.
2. Run `Thread.currentThread().isVirtual()` at **the point where the task actually runs**.
3. Compare behavior with the property on and off, using the same artifact and JDK.
4. Assess impacts on concurrency, context propagation, errors, and shutdown.
5. Replace an executor only when there is a clear benefit or requirement; add tests to prevent regression.

Do not use “property is `true`” as proof that every task has migrated.

## 15. Common mistakes

**Mistake 1 — Thinking enabling the property changes `new Thread`.** False: Java code creating platform threads stays platform; change how they are created if truly needed.

**Mistake 2 — Thinking every `@Async` is virtual.** Needs `@EnableAsync`, proxy invocation, and the right executor; qualifiers/custom executors can keep it on platform threads.

**Mistake 3 — Defining `@Bean ExecutorService` and wondering why Boot didn't create a virtual executor.** A custom `Executor` can cause auto-config to back off. Inspect bean type, name, and `AsyncConfigurer`.

**Mistake 4 — Using `@Async` to call a method in the same bean via `this`.** Self-invocation skips the Spring AOP proxy; the method may run synchronously.

**Mistake 5 — Thinking a virtual controller makes every task it calls virtual.** Only synchronous calls on the same thread keep the thread type; when handed off to another executor, that executor decides the thread type.

**Mistake 6 — Thinking `CompletableFuture.supplyAsync` uses Boot's executor by default.** No: the overload without an executor is not automatically bound to the Boot context.

**Mistake 7 — Thinking Netty event loops automatically turn virtual.** Reactive event-loop architecture retains its own schedulers; verify each integration.

**Mistake 8 — Thinking all `@Scheduled` tasks execute the same way.** `fixedDelay` in `SimpleAsyncTaskScheduler` has special behavior on the scheduler thread; distinguish it from fixedRate/cron.

**Mistake 9 — Enabling virtual yet the scheduler-only app exits.** Virtual threads are daemon; consider `spring.main.keep-alive=true` and process lifecycle.

**Mistake 10 — Relying on thread names.** Names can be customized. Use `Thread.currentThread().isVirtual()`.

**Mistake 11 — Assuming virtual = faster requests.** Virtual threads mainly help concurrency while waiting; CPU and downstream do not speed up because of the flag.

**Mistake 12 — Not bounding concurrent tasks.** Virtual threads are cheaper than OS threads, yet DB pools, memory, and upstream APIs remain finite.

**Mistake 13 — Ignoring pinning on Java 21.** Prolonged blocking inside `synchronized`/native can hold carriers; use JFR and fix code based on evidence.

**Mistake 14 — Ignoring ThreadLocal/security/transactions.** Context does not automatically flow across every async boundary; verify propagation.

**Mistake 15 — Failing to close custom executors.** Unstopped threads/tasks can hold resources or cause shutdown failures.

**Mistake 16 — Comparing two apps with different JDK versions or configs.** Throughput/latency differences cannot be attributed solely to virtual threads.

**Mistake 17 — Applying new config from a different Boot version onto Boot 3.3.** Cross-check documentation for the exact version.

## 16. Self-check questions

1. **Does `spring.threads.virtual.enabled=true` convert all `new Thread` calls?** No.
2. **Minimum JDK to use virtual threads support in Spring Boot 3.3?** Java 21.
3. **Does Boot's flag stop `Executors.newVirtualThreadPerTaskExecutor()` from creating virtual threads when off?** No. That is an independent Java API.
4. **When does the auto-configured task executor use virtual `SimpleAsyncTaskExecutor`?** When Java 21+, flag is enabled, and no custom `Executor` alters auto-configuration under Boot's conditions.
5. **Is `@EnableAsync` needed when using `@Async` in standard Spring?** Yes.
6. **Why can `this.asyncMethod()` run synchronously?** It bypasses the proxy managing async advice.
7. **Does `@Async("fixedPool")` use virtual threads due to the property even if fixedPool is platform?** No; the explicit executor decides.
8. **Does `CompletableFuture.supplyAsync(...)` without an executor use Boot's executor?** No, it follows the JDK default.
9. **Does a Spring MVC request running virtually mean the request never uses a platform thread?** No; it can delegate to another custom executor/platform thread.
10. **Do Spring WebFlux Netty event loops automatically become virtual due to Boot's flag?** No.
11. **What is special about `@Scheduled(fixedDelay)` with `SimpleAsyncTaskScheduler`?** It can execute on a single scheduler thread per fixed-delay semantics; do not assume parallelism like cron/fixedRate.
12. **Why can an application with only scheduled virtual tasks exit on its own?** Virtual threads are daemon threads, not keeping the JVM alive if no other non-daemon thread exists.
13. **Which Boot property helps keep the JVM alive in this situation?** `spring.main.keep-alive=true`.
14. **Proper way to check thread type in Java 21?** `Thread.currentThread().isVirtual()`.
15. **Do virtual threads speed up CPU-bound computation?** Not automatically.
16. **When is a pinned virtual thread on Java 21 dangerous?** When frequent/prolonged blocking holds carriers, reducing throughput.
17. **If a DB pool only has 20 connections, does spawning 10,000 virtual threads become 10,000 connections?** No.
18. **Is MDC/security data guaranteed to cross an `@Async` boundary automatically?** No; check propagation mechanisms.
19. **If the flag is on yet an SDK still uses platform threads, is that definitely a Boot bug?** No; the SDK can manage its own executor independently.
20. **What criteria decide whether to move a task to virtual threads?** Actual execution path, I/O vs CPU workload, resource limits, latency/throughput, context, and shutdown; not configuration alone.

**Summary:** Spring Boot 3.3 virtual threads support is **a targeted choice at Boot-managed integration points**, not an automatic conversion of all source code or every library. Enabling `spring.threads.virtual.enabled=true` allows web requests on Tomcat/Jetty and matching auto-configured executors/schedulers to use virtual threads. However, `new Thread`, fixed pools, default `CompletableFuture`, custom `@Async` executors, and SDK threads still follow how they were created. **Measure with `isVirtual()` on every execution path**, read version-accurate documentation, test JDK 21 pinning/concurrency/daemon/context propagation, and migrate only workloads with real benefits.

### References

- Spring Boot 3.3.13 — **SpringApplication: Virtual threads** (enable flag, pinning, daemon, and `spring.main.keep-alive`): https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3.13 — **Task Execution and Scheduling** (auto-configured `AsyncTaskExecutor`, `TaskScheduler`, custom `Executor`): https://docs.spring.io/spring-boot/3.3/reference/features/task-execution-and-scheduling.html
- Spring Boot 3.2 release notes — **Technology Specific Integrations**, Tomcat/Jetty, task executors: https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.2-Release-Notes
- Spring Framework 6.1 — **SimpleAsyncTaskScheduler** (fixed-delay scheduling semantics): https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/scheduling/concurrent/SimpleAsyncTaskScheduler.html
- Oracle Java 21 — **Virtual Threads** (creating virtual threads, `isVirtual`, pinning, JFR): https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html
- JEP 444 — Virtual Threads: https://openjdk.org/jeps/444
- Spring Boot 3.3 — Gradle Plugin: Managing Dependencies: https://docs.spring.io/spring-boot/3.3/gradle-plugin/managing-dependencies.html
