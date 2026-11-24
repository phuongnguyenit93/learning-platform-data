# Local Variables, Instance Fields, and Shared Data in Spring Beans

## 1. Why Does Bean State Matter Under Multithreading?

A Spring MVC application typically handles many HTTP requests at the same time. Each request is served by a thread from the servlet container; those threads can concurrently invoke **the same** `@RestController`, `@Service`, or `@Repository` object. By default, Spring beans have `singleton` scope: Spring creates **one instance per bean definition per `ApplicationContext`** and provides that same instance to all components that need it.

This **does not make every variable inside a bean shared**. We must distinguish:

- **Local variable:** declared inside a method or block; each method invocation has its own set of local variables. Local primitive values cannot be directly modified by another request.
- **Instance field:** belongs to an instance. If it is a singleton bean, every thread calling the bean sees that same field; the field can be safe when immutable, or risky when updated concurrently.
- **Shared data:** any object or state that multiple threads can access: it could be a field, an object referenced from a local variable, a static field, a cache, a collection, a database, Redis, or a file. Where a variable is declared **does not solely determine** whether data is shared.

For example: two requests both call `reportService.generate(id)`. Each call has its own local `id` variable, yet both execute on the same `reportService` instance. If the service holds `private String currentReportId` and mutates the field on every request, two requests can overwrite each other. If the service only reads an immutable configuration and passes `id` as a parameter down to the repository, there is no shared business state in fields.

### State Identification Table

| Data location | Who owns it? | Can another thread touch it? | Typical design |
| --- | --- | --- | --- |
| `int total` inside a method | A single method invocation | No, for that local variable itself | Temporary calculations |
| Local `List<Item> items` | Reference variable of one invocation | **Yes**, if the list came from a field/cache or escapes outside | Determine the origin and ownership of the referenced object |
| `private final Config config` in a singleton | One bean instance | Same object referenced by all calls | Immutable configuration, built before serving requests |
| `private long count` in a singleton | One bean instance | **Yes**, when requests read/write | Do not use unsynchronized `++`; use atomics/locks when appropriate |
| `private static Map<...> cache` | Class within a classloader | Can be shared across multiple bean instances | Manage safely like any other shared state |
| Data row in DB/Redis | Out-of-process store | Can be shared across **multiple application instances** | Transactions, locks/version conditions, idempotency |

**JVM note:** the saying "locals on the stack, objects on the heap" is helpful for intuition, but should not be used as a thread-safety criterion. A local reference lives in a separate invocation yet can still point to the *same object* on the heap; that object may escape the method and be used by multiple threads. The JVM also performs internal optimizations, so analyzing **who owns and who can access an object** is what is actually accurate.

## 2. Bad Example: Storing Per-Request State in a Singleton Field

~~~java
import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    // Demo anti-pattern: one request can overwrite another.
    private String currentUser;

    public String greet(String user) {
        currentUser = user;
        // Between these two lines, another thread can modify currentUser.
        return "Hello " + currentUser;
    }
}
~~~

If request A calls `greet("Mai")` and pauses after the assignment, and request B calls `greet("Linh")` and assigns `currentUser`, when A resumes it **may** return `"Hello Linh"`. You do not need two controller instances; simply sharing one `GreetingService` singleton is enough to create a race. The snippet above illustrates a service class, not a standalone Java program.

Replace it with a design that **does not store request data in fields**:

~~~java
import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    public String greet(String user) {
        String normalized = user.strip(); // Local to each invocation.
        return "Hello " + normalized;
    }
}
~~~

Calls no longer write to shared state. However, if `user` were replaced by a mutable `List` or DTO fetched from a cache, a local reference **does not copy** the object. The following example still mutates the shared list:

~~~java
// Illustrative snippet inside a method (not standalone).
List<String> localAlias = sharedList; // sharedList is a field.
localAlias.add("report");             // Actually modifies sharedList.
~~~

For data that needs modification, explicitly choose one of these approaches: create a per-request copy, use immutable values, synchronize access, or perform atomic updates in the data store.

## 3. Race Conditions and the Java Memory Model

### 3.1. `count++` Consists of Multiple Steps

The statement `count++` is logically equivalent to reading the value, adding one, and writing it back. Two threads can both read 0 and both write 1; after two increments it should be 2, yet in practice it ends up as 1 (**lost update**). `private` does not stop two methods of the same singleton from accessing a field; `final` only forbids reassigning the reference field and does not automatically protect the object's contents; `volatile` guarantees certain *visibility/ordering* relationships, **without turning `count++` into an atomic increment**.

The following standalone Java 17 example deliberately uses two latches to force both threads to read the initial value, making the outcome deterministic rather than relying on scheduling luck. Save as `LostUpdateDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;

public class LostUpdateDemo {
    static class Counter {
        private int value;
        final CountDownLatch bothRead = new CountDownLatch(2);
        final CountDownLatch continueWriting = new CountDownLatch(1);

        void increment() {
            int snapshot = value;  // Both read 0 before writing.
            bothRead.countDown();
            try {
                continueWriting.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }
            value = snapshot + 1;
        }

        int get() {
            return value;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Counter counter = new Counter();
        Thread first = new Thread(counter::increment);
        Thread second = new Thread(counter::increment);

        first.start();
        second.start();
        counter.bothRead.await();
        counter.continueWriting.countDown();
        first.join();
        second.join();

        System.out.println("Expected = 2");
        System.out.println("Actual   = " + counter.get());
    }
}
~~~

Compile and run:

~~~bash
javac LostUpdateDemo.java
java LostUpdateDemo
~~~

Exact stdout:

~~~text
Expected = 2
Actual   = 1
~~~

In a real application, execution order is not forced like in this example, so a sequential test may **fail to expose the bug**. The two `join()` calls in the demo ensure `main` reads the result after both threads finish. The two latches only serve to reproduce a lost update; they are not how you build a production counter.

### 3.2. Distinguishing the Three Concerns

- **Atomicity:** a multi-step operation cannot be interleaved in a way that produces an invalid state. `AtomicLong.incrementAndGet()` performs an atomic increment for *one* variable.
- **Visibility:** changes made by thread A become observable to thread B according to the *happens-before* rules of the Java Memory Model (JMM); `volatile`, monitor locks, atomics, and certain synchronization mechanisms establish the required relationships.
- **Ordering:** the compiler and CPU may optimize by reordering operations as long as they preserve the semantics allowed by the JMM; proper synchronization establishes necessary ordering constraints.

`synchronized` provides mutual exclusion and visibility relationships when using the **same monitor**. Atomic classes fit independent updates such as counters. `volatile boolean shutdownRequested` fits a signal where one thread writes and another reads, but does not solve compound updates like "check-then-add" across multiple fields.

## 4. Spring Boot 3 Example: Placing Local, Field, and Request-Scoped State Properly

This example can be run with **Java 17+ and Maven**, using Spring Boot 3.3.5 to start a web server. An unsafe field is defined here solely **to observe the bug**; do not use such an endpoint for production metrics.

Structure:

~~~text
spring-bean-state/
├── pom.xml
└── src/main/java/com/example/beanstate/
    ├── BeanStateApplication.java
    ├── CounterService.java
    ├── RequestStamp.java
    └── VisitController.java
~~~

### 4.1. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>spring-bean-state</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

### 4.2. Boot application

`src/main/java/com/example/beanstate/BeanStateApplication.java`:

~~~java
package com.example.beanstate;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BeanStateApplication {
    public static void main(String[] args) {
        SpringApplication.run(BeanStateApplication.class, args);
    }
}
~~~

### 4.3. A Singleton Containing Both Safe and Unsafe Fields

`src/main/java/com/example/beanstate/CounterService.java`:

~~~java
package com.example.beanstate;

import java.util.Map;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.stereotype.Service;

@Service
public class CounterService {
    // Only to demonstrate a race: non-atomic read/add/write.
    private long unsafeTotal;

    // Also a singleton field, but the increment is atomic.
    private final AtomicLong safeTotal = new AtomicLong();

    // Read-only data with immutable String values.
    private final Map<String, String> labels = Map.of(
            "report", "Report",
            "sync", "Sync"
    );

    public long unsafeIncrement() {
        return ++unsafeTotal;
    }

    public long safeIncrement() {
        return safeTotal.incrementAndGet();
    }

    public String labelFor(String type) {
        return labels.getOrDefault(type, "Other");
    }
}
~~~

Sharing `safeTotal` across the same singleton is **intentional**: every request increments the same counter and `AtomicLong` protects the increment. `final` guarantees the `safeTotal` reference cannot be reassigned; `AtomicLong` itself protects the updates. `labels` is not modified after creation and uses `Map.of` with immutable `String`s, so it can be read concurrently safely once the bean is normally initialized and published by Spring.

### 4.4. A New Bean per HTTP Request

`src/main/java/com/example/beanstate/RequestStamp.java`:

~~~java
package com.example.beanstate;

import java.util.UUID;
import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.RequestScope;

@Component
@RequestScope
public class RequestStamp {
    private final String id = UUID.randomUUID().toString();

    public String id() {
        return id;
    }
}
~~~

`@RequestScope` creates a new `RequestStamp` object for each HTTP request. This annotation uses a scoped proxy by default, which is why the singleton controller can inject `RequestStamp`: in fact it holds a **proxy**, and the proxy looks up the object belonging to the current request when invoked. Two calls to `id()` within the same request return the same value; two different requests will almost certainly have different IDs.

`@RequestScope` is not available by default on threads running `@Async`, `@Scheduled`, or in a test without an HTTP request context. Before leaving the HTTP thread, extract the concrete data (for example the request ID) and pass it as a parameter to the worker.

### 4.5. Singleton Controller with Per-Invocation Locals

`src/main/java/com/example/beanstate/VisitController.java`:

~~~java
package com.example.beanstate;

import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class VisitController {
    private final CounterService counters;
    private final RequestStamp requestStamp;

    public VisitController(CounterService counters, RequestStamp requestStamp) {
        this.counters = counters;
        this.requestStamp = requestStamp;
    }

    @GetMapping("/visit")
    public Map<String, Object> visit(
            @RequestParam(defaultValue = "Mai") String name) {
        String normalized = name.strip().toLowerCase(Locale.ROOT);
        int length = normalized.length();

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("name", normalized);
        result.put("length", length);
        result.put("requestId", requestStamp.id());
        result.put("label", counters.labelFor("report"));
        return result;
    }

    @GetMapping("/counter/unsafe")
    public Map<String, Long> unsafe() {
        return Map.of("value", counters.unsafeIncrement());
    }

    @GetMapping("/counter/safe")
    public Map<String, Long> safe() {
        return Map.of("value", counters.safeIncrement());
    }
}
~~~

`normalized`, `length`, and `result` are local to each invocation of `visit()`; each request creates a new map. `counters` is a controller field, referencing the shared singleton service; `requestStamp` is also a field, but references a **scoped proxy** serving data specific to each request. You cannot simply look at the keywords `private` or `final` and conclude the referenced object is always thread-safe.

### 4.6. Run and Observe

In the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

In another terminal:

~~~bash
curl "http://localhost:8080/visit?name=%20Mai%20"
curl "http://localhost:8080/visit?name=%20Mai%20"
curl http://localhost:8080/counter/safe
curl http://localhost:8080/counter/safe
curl http://localhost:8080/counter/unsafe
~~~

The response from `/visit` looks like:

~~~json
{
  "name": "mai",
  "length": 3,
  "requestId": "550e8400-e29b-41d4-a716-446655440000",
  "label": "Report"
}
~~~

The UUID here is only an **example**; each request gets a new ID. In a freshly started application with no other requests, the first two sequential calls to `/counter/safe` will return `{"value":1}` and then `{"value":2}`. The unsafe counter *can* also produce the right result when called sequentially; lost updates only appear under certain interleaving schedules. Both counters start independently from 0 and lose state on restart.

When running many requests in parallel, `unsafeTotal` can miss increments, whereas `safeTotal.incrementAndGet()` does not lose increments **within the same instance**. Do not use the return value of the unsafe endpoint as a reliable metric. The two-latch experiment in section 3 provides deterministic proof of a lost update.

## 5. Choosing the Right Strategy for Each Kind of State

### 5.1. Prefer Stateless Singletons and Immutable Input/Output

The most maintainable design is for beans to hold shared dependencies/configuration, while per-request data resides in parameters, local variables, immutable DTOs, or the DB. With Java 17, you can use `record` for results, e.g., `record ReportResult(String id, long total) {}`. A record only guarantees its component references are `final`; if it contains a mutable `List`, it **does not automatically become deeply immutable**. Use `List.copyOf`, `Map.copyOf`, and immutable elements when a true snapshot is needed.

### 5.2. When You Need a Counter or Status Flag in a Single Instance

| Need | Commonly used tool | Limitation |
| --- | --- | --- |
| Incrementing an ID/counter of **one instance** | `AtomicLong.incrementAndGet()` | Not shared across pods, lost on restart |
| Collecting high-write-frequency counter metrics | `LongAdder.increment()` | `sum()` under concurrent load is not an atomic snapshot |
| Toggle flag observed across threads | `volatile boolean` or `AtomicBoolean` | Does not protect multiple fields together |
| Updating multiple fields consistently | `synchronized`, `ReentrantLock`, or atomically swapped immutable snapshot | Lock applies only within the process/instance |
| Map modified concurrently by multiple threads | `ConcurrentHashMap`, `compute`, `putIfAbsent` | Multi-step operations outside the map still need coordination |

Example of a per-task-type counter in the same service (non-standalone method snippet):

~~~java
private final java.util.concurrent.ConcurrentMap<String,
        java.util.concurrent.atomic.AtomicLong> byType =
        new java.util.concurrent.ConcurrentHashMap<>();

public long record(String type) {
    return byType.computeIfAbsent(type,
            ignored -> new java.util.concurrent.atomic.AtomicLong())
            .incrementAndGet();
}
~~~

`ConcurrentHashMap` protects the map structure and `AtomicLong` protects each key's counter. Do not replace this with the pattern `if (!map.containsKey(k)) map.put(k, new Counter())` if multiple threads can initialize the same key concurrently. When an update must modify *multiple related attributes*, individual atomics do not guarantee an overall transaction: consider a lock or an immutable state structure swapped atomically.

### 5.3. Read-Heavy / Write-Rarely Shared Data Snapshots

To publish a fully built configuration set to many reader threads, you can swap the **entire reference**:

~~~java
// Snippet inside a configuration management class.
private volatile Map<String, String> snapshot = Map.of();

public void replaceSnapshot(Map<String, String> next) {
    snapshot = Map.copyOf(next);
}

public String find(String key) {
    return snapshot.get(key);
}
~~~

With immutable `String` keys/values, each `find` call sees a consistent snapshot. `volatile` supports visibility when replacing the reference; `Map.copyOf` creates a copy that cannot be mutated through the map API. However, two writers both basing their changes on an old snapshot can overwrite each other's updates; you need versioning, CAS, or a lock if the replacement depends on a condition. If values are mutable objects, copying the map **does not automatically deep-copy** the values.

### 5.4. Scope Does Not Replace Thread-Safety Guarantees

| Spring scope | Lifecycle | What to watch out for |
| --- | --- | --- |
| `singleton` (default) | One instance per bean definition in the context | Can be invoked concurrently by multiple requests; best kept stateless |
| `prototype` | Spring creates a bean when requested | Direct injection into a singleton usually **creates it only once at injection time**; use `ObjectProvider<T>` or a provider when a new instance is needed each time |
| `request` | One instance per active HTTP request scope | Suits request state; may not exist on async/scheduled threads |
| `session` | One instance per HTTP session | Two tabs or two requests in the same session can still run concurrently; mutable session state still needs care |

Scope controls **bean lifecycle and lookup**, and does not automatically provide atomicity, visibility, transactions, or synchronization across multiple instances. `@Scope("prototype")` also does not mean Spring automatically cleans up all prototype resources; the consumer must manage its lifecycle appropriately.

### 5.5. `ThreadLocal` Is Thread-Bound State, Not Request-Bound

`ThreadLocal<T>` stores a separate value per **Java thread**. Servlet containers and `TaskExecutor` typically reuse threads across many requests/tasks, so forgetting to clear a value can leak it into subsequent executions. If you truly use it, call `remove()` in a `finally` block:

~~~java
// Illustrative snippet, not a standalone program.
private static final ThreadLocal<String> TRACE_ID = new ThreadLocal<>();

void withTrace(String traceId, Runnable work) {
    TRACE_ID.set(traceId);
    try {
        work.run();
    } finally {
        TRACE_ID.remove();
    }
}
~~~

Do not use `ThreadLocal` as a substitute for a database for business state; and do not assume `ThreadLocal` values automatically travel to `@Async` or `CompletableFuture` threads. Logging MDC, SecurityContext, and transaction context are typically thread-bound and require properly configured propagation mechanisms; the simplest approach for background jobs is passing essential data such as IDs as parameters.

## 6. Shared Data Beyond One Bean and One JVM

Data in a Java field, `AtomicLong`, or `synchronized` only protects scenarios **within a single instance/process** as designed. If you deploy 3 pods, each pod has its own `CounterService` and `safeTotal`; a client routed by a load balancer to another pod can observe a different counter value. `static` does not turn a variable into distributed state either.

When you need a consistent total order count across the entire system, store the total in a DB or appropriate store and ensure atomic updates there. Simple SQL example for a single row:

~~~sql
UPDATE report_stats
SET processed_count = processed_count + 1
WHERE id = 1;
~~~

In a suitable transactional DB, the UPDATE statement is executed using the DB's concurrency control, rather than reading the number into Java and overwriting it with a stale value. For business rules checking balances, inventory, or modifying multiple rows, you need transactions, conditional updates, isolation/locking, or optimistic versioning depending on data rules; `synchronized` on a bean cannot lock other processes.

With JPA, managed entities and `EntityManager` are tied to a persistence context/transaction; **do not store a mutable managed entity or `EntityManager` as arbitrary state shared across requests**. A Spring Data repository can be a singleton proxy, yet operations must use the proper transaction/persistence context—different from holding onto a shared JPA object yourself. Distinguish Java synchronization mechanisms from database transactions and isolation.

## 7. Common Misconceptions and How to Check

| Misconception/symptom | What to check | How to address |
| --- | --- | --- |
| "Controller is singleton so locals get modified by other requests" | Locals belong to each invocation; does it reference a shared object? | Keep request data in locals/DTOs, do not store `currentUser` in a field |
| "`private final List` field is thread-safe" | `final` only fixes the reference; can the `List` still be mutated? | Use an immutable collection or proper synchronization mechanism |
| "Adding `volatile int counter` is enough" | Are there `++` or check-then-act operations? | `AtomicInteger`, `synchronized`, or atomic DB update |
| "`ConcurrentHashMap` makes all operations safe" | Is there a multi-step `get → modify object → put` flow? | Use `compute`, immutable values, or appropriate locks/transactions |
| "`@RequestScope` works in every worker" | Does the worker have an active request context? | Pass required request data into the task |
| "`prototype` is injected on every call" | When was the prototype bean injected directly into the singleton? | Use a provider whenever a fresh bean is needed |
| "A counter that works in dev will work on a cluster" | Are there multiple processes/pods or restarts? | Use a shared store, transactions/versioning, idempotency |
| "10 test requests passed so there is no race" | Did the test actually run concurrently and verify invariants? | Test controlled concurrency/latches, stress test, monitor errors |

### How to Self-Audit a Bean

1. List every **instance/static field**: who assigns it, when, is it modified after startup, and is the referenced object mutable?
2. For each public method, separate **per-invocation data** from references escaping to external services/caches/entities.
3. Flag every "read → check → write", "add if absent", or "increment counter" operation: do they need to be atomic?
4. Determine the sharing scope: **one invocation**, **one request**, **one singleton in one context**, **one JVM**, or **cluster-wide**.
5. Pick the minimal measure that satisfies the invariants: local/immutable first; then atomic, lock, or DB transaction when truly required. Measure performance if using locks on a hot path.
6. Test concurrent requests together; verify the final state, not just HTTP status codes. Test running multiple instances if data requires cluster-wide consistency.

### Knowledge Self-Check

- Is a singleton `@Service` with only `final` dependencies and methods using local variables guaranteed to be thread-safe? Can those dependencies themselves hold mutable state?
- Is the local variable `List<String> copied = cache.get(key)` guaranteed to be a private list? What must you do if you need to modify the list?
- Why can `volatile long total; total++;` still lose increments, whereas `AtomicLong.incrementAndGet()` does not?
- How do `@RequestScope` and `@SessionScope` differ when two requests arrive concurrently? Which scope guarantees automatic thread-safety?
- When scaling from one instance to three pods, why is a counter in a bean no longer a system-wide counter? What extra condition does a DB/Redis design need so retries do not double-count?

**Design rule:** keep Spring singleton beans as *stateless* as possible; distinguish a local variable from **the object it points to**; any mutable state reachable by multiple threads must have clear ownership and coordination.