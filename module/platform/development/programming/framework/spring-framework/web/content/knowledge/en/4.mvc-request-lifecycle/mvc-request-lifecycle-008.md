# Singleton Controller Lifecycle and the Risks of Shared State in Spring Web MVC

## 1. Learning Objectives

In Spring Web MVC, a regular `@RestController` **is a Spring bean with `singleton` scope**. Multiple HTTP requests can invoke **the same controller instance** concurrently. This is a fundamental characteristic of the MVC processing flow: Spring does not instantiate a new Java controller object per request simply because multiple clients access an endpoint.

After this lesson, you will be able to:

- Describe how a controller is created, initialized, used, and destroyed in the Spring `ApplicationContext` lifecycle.
- Distinguish Spring's `singleton` from GoF singleton, "one instance per JVM" objects, and the "one controller per request" mental model.
- Explain why local variables inside a handler differ in sharing behavior from mutable instance fields, static fields, or mutable dependencies.
- Reproduce a race condition where data from request A leaks into request B's response.
- Design stateless controllers and place state in the right location: request, session, database, or appropriate concurrency components.
- Distinguish `@RequestScope`, `@SessionScope`, `prototype`, scoped proxies, `ThreadLocal`, and thread-safe primitives.
- Test singleton behavior, request independence, and concurrency risks with Java 17+ and Spring MVC.

**Core message:** `singleton` only defines **the count and lifetime of instances**. It **does not automatically guarantee thread safety**. The safe default is writing stateless controllers, keeping per-request data in parameters/local variables, and using collaborators with appropriate concurrency contracts.

## 2. How Are Controllers Created in Spring MVC?

A class annotated with `@Controller` or `@RestController` is a Spring component candidate. When component scanning or explicit configuration registers the bean definition, the Spring container creates and manages the instance according to the bean's scope.

Example:

```java
package com.example.lifecycle.web;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {

    @GetMapping("/api/ping")
    public String ping() {
        return "pong";
    }
}
```

This class defaults to **`singleton` scope**, equivalent to declaring `@Scope("singleton")` explicitly. Within a Spring `ApplicationContext`, Spring retains one instance per controller **bean definition** and reuses it. The same class can still appear across multiple bean definitions or contexts; Spring's "singleton" means **per container and per bean**, not a single object across the entire JVM.

### Typical Lifecycle

```text
Application starts
    |
    v
Create ApplicationContext and register bean definitions
    |
    v
Instantiate singleton controller (eager by default, unless lazy/conditional)
    |
    v
Resolve and inject dependencies (constructor, ...)
    |
    v
Bean lifecycle: post-processors, @PostConstruct, and related callbacks
    |
    v
Context ready to receive requests
    |
    +-- HTTP request A --> HandlerMapping/HandlerAdapter --> controller INSTANCE X
    |
    +-- HTTP request B --> HandlerMapping/HandlerAdapter --> controller INSTANCE X
    |
    +-- HTTP request C --> HandlerMapping/HandlerAdapter --> controller INSTANCE X
    |
    v
ApplicationContext closes
    |
    v
Singleton destroy callbacks (if any), release managed resources
```

Startup details can vary due to lazy initialization, proxies, bean post-processors, or context hierarchies. **Do not** read the diagram as "every bean has `@PostConstruct`" or "every bean is created at one absolute moment." For standard singleton controllers, the key point is that the instance lives across many requests and usually lasts as long as the context lifecycle.

`@PostConstruct` runs during bean initialization, **not on every HTTP request**. `@PreDestroy` or singleton destruction callbacks normally run on context shutdown, **not when a controller finishes handling a request**.

### Why Does Spring MVC Share Controllers?

In Spring MVC, the Servlet container dispatches requests to `DispatcherServlet`. `HandlerMapping` selects a registered handler; `HandlerAdapter` invokes the corresponding method on the existing controller bean. The Spring container does not call `new` on the controller every time a handler method is selected. Multiple concurrent requests may be served by different servlet threads invoking the same method on one object:

```text
Request A (thread T1):  controllerInstance.getUser("A")
                                 |
                                 +--> same object
                                 |
Request B (thread T2):  controllerInstance.getUser("B")
```

Threads here are just a visual model. With async processing, a request can move across multiple dispatches or executors. What matters is that **multiple execution flows can access the same fields on the controller object**.

## 3. Distinguishing Local Data, Fields, and Shared Data

```java
@RestController
class ExampleController {

    private final GreetingService service;        // single bean reference
    private String lastName;                       // mutable instance field
    private static long globalCounter;             // static mutable field

    ExampleController(GreetingService service) {
        this.service = service;
    }

    @GetMapping("/api/example")
    String example(@RequestParam String name) {
        String normalized = name.trim();          // local variable
        lastName = normalized;                     // shared state!
        globalCounter++;                           // shared state + race!
        return service.greet(normalized);
    }
}
```

This is an **illustrative snippet**: it needs corresponding imports and a `GreetingService` bean to compile in a Spring project. Do not copy this example as a production controller.

| Data kind | Where it lives | Risk when multiple requests access concurrently |
|---|---|---|
| Handler parameter, e.g. `name` | Per method invocation | Not a shared field; can still point to another mutable object. |
| Local variable, e.g. `normalized` | Per method invocation | Local variables are not shared across invocations; only risky if their reference escapes into shared state. |
| `final` instance field pointing to service | Same singleton controller | Reference cannot be reassigned; the referenced service/object itself can still be mutable and must be thread-safe. |
| Mutable instance field, e.g. `lastName` | Same controller instance | Other requests can overwrite it, read each other's data, or cause data races. |
| `static` field, e.g. `globalCounter` | Bound to class/ClassLoader in JVM | Shared across controller instances; does not become safe merely by changing controller scope. |
| Mutable state inside injected singleton service | Inside singleton service | Same risk, merely moved from controller into service. |
| Request-scoped bean | One valid HTTP request scope | Isolated across different requests; **does not** automatically protect if multiple threads within the same request access that object. |
| Session-scoped bean | One HTTP session scope | Multiple requests in the **same session** can still run concurrently and collide on state. |

When a controller only calls pure/stateless methods and uses local data, many threads sharing one instance is **generally safe**, because the object holds no per-request state. Yet a stateless controller can still call services, caches, or databases whose update protocols are unsafe; always evaluate the entire dependency chain.

## 4. Classic Race Condition: One Request Overwrites Another Request's Name

Consider an erroneous controller:

```java
package com.example.lifecycle.web;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class UnsafeGreetingController {

    private String currentName;

    @GetMapping("/api/unsafe")
    public String greet(@RequestParam(name = "name") String name) {
        currentName = name;
        // Another request can overwrite currentName right here.
        return "Hello, " + currentName;
    }
}
```

With two overlapping requests, an interleaving **could** be:

```text
Thread A                             Thread B
----------------------------------   ----------------------------------
GET /api/unsafe?name=An              GET /api/unsafe?name=Binh
currentName = "An"
                                     currentName = "Binh"
return "Hello, " + currentName
-> may return "Hello, Binh"!
                                     return "Hello, Binh"
```

This is one possible schedule, not a guaranteed outcome of every HTTP test. The bug might appear only under load and be very hard to reproduce with sequential URL calls. Beyond interleaving, unsynchronized fields also suffer from memory visibility issues under the Java Memory Model: threads may not see each other's updates at the moment a developer imagines.

**Business consequences can be severe**: storing `currentUserId`, `tenantId`, `cart`, `accessToken`, `searchCriteria`, or user-specific response data in a singleton field can cause one user's request to use another user's data. This is a data-isolation failure, not merely a miscounted metric.

### Why Is `volatile` Not a General Fix?

Changing it to:

```java
private volatile String currentName;
```

only adds certain visibility and ordering guarantees for reads/writes on the field. It **does not** bind a value to the request that produced it. Request A can still read the value B just wrote. Likewise, `counter++` is a read–modify–write sequence, so adding `volatile` to a counter does **not** make increments atomic.

The real problem to solve is: **do not store per-request data in shared objects**.

## 5. Java 17+ Experiment: Reproducing the Bug in a Controlled Way

You do not need to start a web server to prove the nature of the bug. The standalone Java file below uses two threads, one shared service instance, and a `CyclicBarrier` to force both calls to write state before reading. `volatile` is used here so visibility is consistent for display; `volatile` still does not fix request mixing.

File `SharedStateRace.java`:

```java
import java.util.concurrent.BrokenBarrierException;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class SharedStateRace {

    static final class UnsafeGreeter {
        private volatile String currentName;
        private final CyclicBarrier bothWritten = new CyclicBarrier(2);

        String greet(String name)
                throws InterruptedException, BrokenBarrierException {
            currentName = name;
            bothWritten.await();
            return currentName;
        }
    }

    public static void main(String[] args) throws Exception {
        UnsafeGreeter greeter = new UnsafeGreeter();

        try (ExecutorService pool = Executors.newFixedThreadPool(2)) {
            Future<String> first = pool.submit(() -> greeter.greet("An"));
            Future<String> second = pool.submit(() -> greeter.greet("Binh"));

            String a = first.get();
            String b = second.get();

            System.out.println("Same response: " + a.equals(b));
            System.out.println("Exactly one correct: "
                    + (a.equals("An") != b.equals("Binh")));
        }
    }
}
```

**Note:** `ExecutorService` implements `AutoCloseable` starting in Java 19; `try (ExecutorService ...)` requires **Java 19+**, so to run cleanly on Java 17 as targeted by this lesson, use the version below calling `shutdown()` in `finally`:

```java
import java.util.concurrent.BrokenBarrierException;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class SharedStateRace {

    static final class UnsafeGreeter {
        private volatile String currentName;
        private final CyclicBarrier bothWritten = new CyclicBarrier(2);

        String greet(String name)
                throws InterruptedException, BrokenBarrierException {
            currentName = name;
            bothWritten.await();
            return currentName;
        }
    }

    public static void main(String[] args) throws Exception {
        UnsafeGreeter greeter = new UnsafeGreeter();
        ExecutorService pool = Executors.newFixedThreadPool(2);

        try {
            Future<String> first = pool.submit(() -> greeter.greet("An"));
            Future<String> second = pool.submit(() -> greeter.greet("Binh"));

            String a = first.get();
            String b = second.get();

            System.out.println("Same response: " + a.equals(b));
            System.out.println("Exactly one correct: "
                    + (a.equals("An") != b.equals("Binh")));
        } finally {
            pool.shutdown();
        }
    }
}
```

Create the file with only **the second code block** (Java 17-compatible), saved as UTF-8. Run:

```bash
javac -encoding UTF-8 SharedStateRace.java
java SharedStateRace
```

Stdout:

```text
Same response: true
Exactly one correct: true
```

Explanation: each thread writes its own name and then waits for both threads to reach the barrier. After the barrier, both read **the same field determined by whichever write happened last**. The final value may be `An` or `Binh`, yet both responses are identical, meaning exactly one of the two requests got the wrong name. The barrier in this experiment forces a deterministic interleaving; **never put a barrier into a production controller** to "synchronize requests."

Fix the logic by removing the mutable shared field:

```java
static final class SafeGreeter {
    String greet(String name) {
        String normalized = name.trim();
        return normalized;
    }
}
```

Each invocation has its own `name`/`normalized`. No `volatile`, `synchronized`, or lock is needed to protect state that does not exist.

## 6. Runnable Spring Web MVC: Designing a Stateless Controller

This section builds a Spring Boot 3.5.x + Spring MVC application using Java 17 and Gradle 8.5. The example picks specific version **Spring Boot 3.5.16**; in production systems, follow your supported BOM and upgrade path. With Spring Boot 3.5, the Servlet-stack web starter remains `spring-boot-starter-web`.

### 6.1. Project Structure

```text
controller-lifecycle-demo/
├── settings.gradle
├── build.gradle
├── gradlew                      # if generated with Gradle Wrapper/Initializr
├── gradlew.bat
├── gradle/wrapper/...
└── src/
    ├── main/
    │   ├── java/com/example/lifecycle/
    │   │   ├── LifecycleApplication.java
    │   │   ├── service/GreetingService.java
    │   │   └── web/GreetingController.java
    │   └── resources/application.properties
    └── test/java/com/example/lifecycle/
        └── GreetingControllerTest.java
```

You can generate the project via https://start.spring.io with Gradle/Groovy, Java 17, and the **Spring Web** dependency, or create files manually and generate the Gradle Wrapper. `gradlew` and `gradle/wrapper/*` files must be generated by Gradle Wrapper or Initializr; do not fabricate a fake `gradle-wrapper.jar`.

`settings.gradle`:

```groovy
rootProject.name = 'controller-lifecycle-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

The Spring Boot BOM manages versions of Spring Framework, Jackson, and most related dependencies; do not arbitrarily override `spring-webmvc` with a different version. `spring-boot-starter-test` brings in JUnit and Spring Test commonly used to verify handlers.

### 6.2. Bootstrapping the Application

`src/main/java/com/example/lifecycle/LifecycleApplication.java`:

```java
package com.example.lifecycle;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LifecycleApplication {

    public static void main(String[] args) {
        SpringApplication.run(LifecycleApplication.class, args);
    }
}
```

Place `@SpringBootApplication` in the parent package `com.example.lifecycle` so component scanning discovers the service and controller underneath. Spring Boot automatically configures the embedded Servlet container and `DispatcherServlet` when the appropriate web starter is present.

`src/main/resources/application.properties`:

```properties
spring.application.name=controller-lifecycle-demo
server.port=8080
```

### 6.3. Stateless Service

`src/main/java/com/example/lifecycle/service/GreetingService.java`:

```java
package com.example.lifecycle.service;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    public String greet(String name) {
        String normalized = name.trim();
        return "Hello, " + normalized + "!";
    }
}
```

`@Service` is also a singleton bean by default. This service is **safe for concurrent calls as written** because it neither reads nor writes shared mutable state. Local variables of each method invocation are not shared with other invocations.

If one day you add `private String lastName;` to the service for "temporary storage," you have only **moved the race condition from the controller into the service**. Statelessness must be verified across the entire collaborator chain.

### 6.4. Proper Singleton Controller

`src/main/java/com/example/lifecycle/web/GreetingController.java`:

```java
package com.example.lifecycle.web;

import java.util.Map;
import com.example.lifecycle.service.GreetingService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {

    private final GreetingService greetingService;

    public GreetingController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping("/api/greeting")
    public Map<String, String> greeting(
            @RequestParam(name = "name", defaultValue = "friend") String name) {

        String message = greetingService.greet(name);
        return Map.of("message", message);
    }
}
```

In this example:

- Spring creates a normal singleton `GreetingController`.
- Constructor injection wires the required collaborator; `private final` prevents reassigning the reference after construction.
- `name`, `message`, and `Map.of(...)` are all created/used within the current handler invocation. `Map.of` returns an immutable map so it introduces no shared mutable state from the controller.
- There is no `lastName` or `currentUser` instance field. Two concurrent requests invoke the same bean while each computes its response from its own input.
- `GreetingService` is also a singleton, which remains safe because it stores no request data in fields.

**Note:** `final GreetingService greetingService` protects the reference, and **does not by itself make the service thread-safe**. If the service holds a mutable `HashMap`, list, unsynchronized cache, or objects mutated across threads, it still needs proper redesign.

### 6.5. Running and Observing Responses

On Windows PowerShell:

```powershell
.\gradlew.bat clean test
.\gradlew.bat bootRun
```

On Linux/macOS:

```bash
./gradlew clean test
./gradlew bootRun
```

In a second terminal, send requests:

```bash
curl -i "http://localhost:8080/api/greeting?name=An"
curl -i "http://localhost:8080/api/greeting?name=Binh"
curl -i "http://localhost:8080/api/greeting"
```

Corresponding JSON bodies:

```json
{"message":"Hello, An!"}
```

```json
{"message":"Hello, Binh!"}
```

```json
{"message":"Hello, friend!"}
```

Expected status is HTTP 200, with JSON `Content-Type` produced by the message converter. Exact headers, header ordering, and startup logs depend on the environment; the example only guarantees the content generated by the code.

## 7. Testing Singleton Identity and Request Independence

File `src/test/java/com/example/lifecycle/GreetingControllerTest.java`:

```java
package com.example.lifecycle;

import static org.junit.jupiter.api.Assertions.assertSame;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.example.lifecycle.web.GreetingController;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class GreetingControllerTest {

    @Autowired
    ApplicationContext context;

    @Autowired
    MockMvc mvc;

    @Test
    void controllerIsSameSingletonBeanInThisContext() {
        GreetingController first = context.getBean(GreetingController.class);
        GreetingController second = context.getBean(GreetingController.class);
        assertSame(first, second);
    }

    @Test
    void independentRequestsProduceIndependentResponses() throws Exception {
        mvc.perform(get("/api/greeting").param("name", "An"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message").value("Hello, An!"));

        mvc.perform(get("/api/greeting").param("name", "Binh"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message").value("Hello, Binh!"));

        mvc.perform(get("/api/greeting"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message").value("Hello, friend!"));
    }
}
```

What is verified:
- `assertSame` proves two lookups of **the same bean definition in the same context** return the same reference. It does not prove only one instance exists across the entire JVM.
- MockMvc verifies mapping, binding, and JSON for the Spring MVC app.
- The MockMvc requests here run **sequentially**, so they **do not prove** a controller can never have a concurrency bug. The stateless source design and the `SharedStateRace` experiment explain why avoiding shared request state matters.
- A concurrent HTTP integration test against a real server can uncover some races, yet cannot exhaustively prove every interleaving is safe. Reviewing state design and ownership remains essential.

## 8. Safe Design Rules: Where Does State Belong?

When storing data, first identify its **lifecycle and owner**, then pick the matching storage location:

| Data kind | Where it should live | Example |
|---|---|---|
| Used only in one handler call | Parameters/local variables, DTOs | `name`, `orderId`, `validatedInput` |
| Bound to one HTTP request | Request attribute or `@RequestScope` | Request correlation context, temporary computed data |
| For a user session | Session store / controlled `@SessionScope` | Wizard form state, UI preferences |
| Durable business data | Database or transactional/consistent store | Persistent cart, orders, balances |
| Shared cache | Cache API with proper concurrency/TTL policy | Cacheable reference data |
| Process-local metrics counter | Metrics registry or suitable atomic/adder | Request count handled on one instance |
| Immutable configuration | Immutable configuration object or constructor-injected collaborator | Endpoint base URL, formatting rules |
| Data tied to authenticated user | Framework-managed request/security context | Principal/authorities for the current request |

Data security requires **checking permissions per request/operation**, never storing the current user in `static` or singleton fields. A single application instance can serve many users/tenants concurrently.

### `@RequestScope` When You Truly Need a Per-Request Object

Sometimes multiple components within a single request need to share a temporary object. In that case use `@RequestScope`:

```java
package com.example.lifecycle.web;

import java.util.UUID;
import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.RequestScope;

@Component
@RequestScope
public class RequestMarker {

    private final String id = UUID.randomUUID().toString();

    public String id() {
        return id;
    }
}
```

A singleton controller can inject this bean:

```java
package com.example.lifecycle.web;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class RequestMarkerController {

    private final RequestMarker marker;

    public RequestMarkerController(RequestMarker marker) {
        this.marker = marker;
    }

    @GetMapping("/api/marker")
    public Map<String, String> marker() {
        return Map.of("requestId", marker.id());
    }
}
```

The two Java files above are a **standalone extension**, placed in the same source tree as the project in Section 6; no extra library beyond the web starter is needed. `@RequestScope` is a shortcut for request scope and **uses a class-based scoped proxy by default**. Singleton `RequestMarkerController` holds a stable proxy; on each request, calling `marker.id()` delegates to the **target `RequestMarker` of the current request**. That way constructor injection on the singleton does not have to instantiate a request object at startup.

Calling `/api/marker` twice **typically returns different** UUID values because each request has its own marker instance. UUIDs are random data, so you cannot hardcode an exact stdout expectation; a good test checks that IDs are valid and distinct across two requests if desired. Within one request, calling `marker.id()` multiple times returns the same ID because it hits the same target bean.

**Do not make controllers request-scoped** for ordinary CRUD endpoints: request-local variables suffice in most cases, with less overhead and greater simplicity. `@RequestScope` is useful when you genuinely need a collaborator carrying per-request identity/state.

### `@SessionScope` Does Not Automatically Make State Thread-Safe

`@SessionScope` creates one instance per HTTP session, yet **two requests from the same user** (two browser tabs, parallel AJAX calls) can still access the same session bean concurrently.

Example:

```java
@Component
@SessionScope
public class WizardState {

    private int step;

    public int advance() {
        return ++step;
    }
}
```

This is a snippet for analysis, not a production recommendation. `++step` is not atomic. If two requests in the same session call `advance()` concurrently, an increment can be lost. You need synchronized updates or an appropriate storage/state model; in multi-instance deployments, consider session replication, serialization, and centralized storage. Moreover, a session bean is never a global cache across all users.

### Is `prototype` a Solution for Controllers?

`@Scope("prototype")` tells Spring to create a new object every time the container **is asked for the prototype bean**; it does not mean a new instance is automatically created for **every HTTP request** in normal MVC dispatch. Injecting a prototype into a singleton at initialization can leave the singleton holding that same prototype instance for its entire lifetime. Therefore, **do not switch controllers to prototype just to work around shared request data**. Design stateless controllers or use request scope purposefully.

If a singleton needs to create fresh stateful objects per operation, use `ObjectProvider<T>.getObject()` or an explicit factory to obtain a new prototype **on each call**. That is a bean lookup mechanism, not a mechanism that automatically turns prototype into request-scoped.

## 9. Synchronization Measures: Knowing the Exact Limits

There are cases where state **truly belongs to the process** and must be shared, such as a metrics counter. In those cases concurrency primitives help, but should not be used to patch over misplaced user data lifetimes.

### `AtomicInteger` and Counter Increments

Wrong:

```java
private int count;

public int next() {
    return ++count;
}
```

Two threads can read the same old value and lose updates. If this is a counter **local to one JVM instance**:

```java
import java.util.concurrent.atomic.AtomicInteger;

private final AtomicInteger count = new AtomicInteger();

public int next() {
    return count.incrementAndGet();
}
```

`incrementAndGet()` performs an atomic increment on an `AtomicInteger`. Yet the counter still belongs only to that process; across 3 replicas or restarts, processes have separate state and do not form a globally durable ID sequence. For business IDs or balances/inventory, use database sequences, atomic updates, transactions, or properly designed consistency mechanisms.

### `synchronized` / Locks

`synchronized` can guarantee mutual exclusion of a critical section within **the same JVM/monitor**. However:

- Synchronizing an entire handler method serializes requests, reducing throughput.
- If results are returned from a global user field, locking does not make the lifecycle or semantics right.
- A lock inside one process does not protect the same business record across multiple running instances.
- Complex locking and shared state easily cause deadlocks, contention, and hard-to-test bugs.

**Prefer removing request-specific state from singletons** over adding global locks.

### Concurrent Collections and Compound Operations

`ConcurrentHashMap` provides thread-safe contracts for individual collection operations. However, a `containsKey` → `put` sequence can still race at the **business logic** level. Use atomic methods like `computeIfAbsent` or `merge` when semantics require it, and evaluate callback functions and side effects. A thread-safe collection does not automatically make "check-then-update" across multiple resources/database transactions atomic.

### Immutable Objects

A class with `final` fields pointing to immutable values (such as `String`, or a `record` containing immutable components) generally prevents unintended mutation. However:
- `final List<T>` only locks the reference, **not** turning an `ArrayList` immutable.
- A `record` holding a reference to a mutable object is not deeply immutable either.
- A stateless controller can hold immutable configuration and references to services, repositories, and clients as long as those collaborators are used according to their concurrency contracts.

## 10. Mistakes Involving Request Context and ThreadLocal

`ThreadLocal` can store thread-bound context, such as correlation info for logging. However, servlet containers **reuse worker threads**; failing to clean up leaks the previous request's context into the next request. With async execution, processing can move to a different thread and `ThreadLocal` does not automatically follow the request.

An illustrative-only example:

```java
private static final ThreadLocal<String> CURRENT_ID = new ThreadLocal<>();

void process(String id) {
    CURRENT_ID.set(id);
    try {
        // synchronous work on current thread
    } finally {
        CURRENT_ID.remove();
    }
}
```

This snippet **does not** create a true request scope, does not replace `SecurityContext`/request attributes, and does not automatically propagate state to `@Async`, `CompletableFuture`, or asynchronous MVC dispatches. If cross-thread context is needed, use propagation mechanisms provided by your framework/observability/security libraries with clear policies.

### HttpServletRequest, @RequestParam, and Principal

In a controller, receiving request data via method parameters is straightforward:

```java
@GetMapping("/api/me")
public Map<String, String> whoAmI(java.security.Principal principal) {
    return Map.of("name", principal.getName());
}
```

This snippet assumes a security principal is present. If authentication is not configured, `principal` may be `null` and the example above must handle that case. The point here is **never store a request's principal in a singleton field**. Objects passed into the handler or retrieved via security APIs at the right moment belong to the request context; they must not be cached as an application-wide "current user."

## 11. Do Async Controllers and Virtual Threads Change the Conclusion?

No. Whether the Servlet container uses platform worker threads, an async MVC executor, or virtual threads in some configurations, a singleton controller remains a single object **used by multiple concurrent execution flows**. Changing thread implementations does not change bean scope.

Example controller returning `Callable<String>`:

```java
@GetMapping("/api/async-greeting")
public java.util.concurrent.Callable<String> asyncGreeting(
        @RequestParam(name = "name") String name) {

    return () -> "Hello, " + name + "!";
}
```

This is a controller snippet placed inside an existing `@RestController`. `name` is a local/parameter captured per invocation, so no shared field is needed. Spring MVC can execute the `Callable` via a configured async executor and perform an async dispatch to complete the response. If the lambda reads/writes a mutable singleton field instead of capturing request inputs, the race still exists.

For request-scoped beans and security/request contexts, async execution has specific propagation/lifecycle rules; do not rely on manual `ThreadLocal` assumptions that beans are always present on every thread. Programming around thread-safe state ownership remains foundational.

## 12. Quick Code Review Checklist

| Smell in controller/service | Question to ask | Typically appropriate fix |
|---|---|---|
| `private String currentUser;` | Does this value vary per request/user? | Remove field; pass as parameter or read from request/security context. |
| `private Map<String, Cart> carts = new HashMap<>();` | Is the map accessed concurrently by requests, or needed persistently/multi-node? | Design repository/store/cache with explicit concurrency and ownership. |
| `private final List<...> cache = new ArrayList<>();` | `final` only locks the reference—is the list mutated? | Use immutable snapshots or a proper thread-safe cache. |
| `private int requestCount;` and `++requestCount` | Need a process-level or system-wide count? | Metrics registry, atomic primitive, or properly scoped backend counter. |
| `@Scope("prototype")` on controller | Expecting one instance per request? | Review semantics; prefer stateless controllers. |
| `@SessionScope` with many mutable fields | Can the same session have parallel requests? | Protect updates / design session state explicitly. |
| `ThreadLocal` without `remove()` | Does the container reuse threads? | Clean up in `finally` and define async propagation. |
| `synchronized` on handler | Using locks to patch misplaced state? | Move state to its proper owner; if shared data is required, use atomic operations/transactions. |
| Injected singleton service has mutable fields | Controller is stateless, but is the service safe? | Audit the entire dependency chain. |
| `static` mutable field | Is data unexpectedly shared across classes? | Avoid for request/user state; isolate or explicitly manage process-global state. |

## 13. Exercises and Self-Check Questions

### Exercise 1: Spot the Dangerous Variable

```java
@RestController
class CartController {

    private String cartId;
    private final CartService service;

    CartController(CartService service) {
        this.service = service;
    }

    @GetMapping("/api/cart")
    CartDto getCart(@RequestParam String id) {
        cartId = id;
        return service.load(cartId);
    }
}
```

Identify why responses can mix up shopping carts when requests A and B run concurrently. Rewrite the handler as `return service.load(id);` and delete the `cartId` field. If `CartService` stores `lastLoadedCart` as a mutable singleton field, the problem is still unsolved.

### Exercise 2: Experiment with Scopes

Add `RequestMarker` and `RequestMarkerController` from Section 8 to the running application. Send two `/api/marker` requests and observe different UUIDs across requests. Inside **one** handler, call `marker.id()` twice and compare them; they share the same request-scoped target while that same request is active.

### Exercise 3: Multi-Instance Model

Suppose a load balancer routes requests to two independent app instances A and B. Each instance has a singleton bean holding `AtomicInteger counter`. If a client calls `/counter` repeatedly, is the counter guaranteed to increment globally? **No**: A and B have separate objects and values. State when a shared database or metrics backend should be used.

### Frequently Asked Questions

**1. Does Spring create a new controller for each HTTP request?**  
By default, no. `@RestController` is a singleton Spring bean per bean definition and context. Request mappings normally invoke the same instance.

**2. Does a singleton bean mean the controller is not thread-safe?**  
Not necessarily. A stateless singleton or one with properly managed shared state can be thread-safe. Risk arises when multiple threads access mutable state without proper ownership/synchronization.

**3. Can a local variable `String name` inside a handler be overwritten by another request?**  
Not the way an instance field is overwritten; each invocation has its own local variables. However, a local reference pointing to a shared mutable object can still cause a race.

**4. Is using `volatile` on `currentUser` safe?**  
No. It provides no per-request isolation; user A can still read user B's name.

**5. Is using `@RequestScope` on all controllers better?**  
Usually unnecessary. Stateless singleton controllers are simpler and idiomatic. Use request scope only when you genuinely need an object whose lifecycle is tied to the request.

**6. Does injecting a `prototype` into a singleton create a new object on every request?**  
No. The dependency is typically resolved when constructing the singleton; use a factory/provider if you want a new prototype per call.

**7. Does `@SessionScope` prevent races between requests from the same user?**  
Not automatically. Two concurrent requests in the same session can mutate a session-scoped bean at the same time.

**8. Can we put all business state in a singleton service and just keep the controller stateless?**  
No, if user/request-specific business state is still shared unsafely. Use local values, request/session scope when appropriate, persistence, or state systems with sound concurrency design.

## 14. Further Reading

- Spring Framework Reference — Bean Scopes, singleton/prototype/request/session, scoped proxies: https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html
- Spring Framework Reference — Classpath Scanning and Managed Components, `@RequestScope` and `@SessionScope`: https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html
- Spring Framework Reference — Spring MVC annotated controllers: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller.html
- Spring Framework Reference — MVC asynchronous requests: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html
- Spring Boot 3.5 — Web applications: https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
- Java SE 17 — `java.util.concurrent`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/package-summary.html
