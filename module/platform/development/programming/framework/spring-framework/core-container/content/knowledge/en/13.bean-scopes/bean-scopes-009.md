# Shared State and Thread Safety of Singletons in the Spring Framework

## 1. What does Singleton actually mean in Spring?

By default, a bean managed by the Spring IoC Container has `singleton` scope. When the same bean definition (same identifier) is retrieved multiple times within **one Spring container**, Spring returns the same object. A singleton service/controller is commonly invoked concurrently by multiple callers, especially when the application serves multiple HTTP requests, executor tasks, or message listeners.

```text
                  Spring ApplicationContext
                            |
                  singleton bean: OrderService
                            |
           +----------------+----------------+
           |                |                |
       Thread A         Thread B         Thread C
       request #1       request #2       background job
           |                |                |
           +----------- same instance -------+
```

**Core point:** singleton only governs **instance count and sharing**. Singleton does **not** mean methods are automatically locked by Spring, executed sequentially, or guaranteed to be thread-safe. Spring does not automatically make a mutable field atomic or isolate per-request data.

The Spring singleton boundary is **per bean definition, per container**. One class can be declared under two bean names and receive two distinct instances; two independent `ApplicationContext`s or two JVMs/pods do not automatically share a system-wide singleton. This is not a JVM-wide static instance singleton pattern.

Distinguish:

- **Stateless singleton**: keeps no per-request mutable data in fields; uses only parameters, local variables, thread-safe dependencies, or immutable configuration. This is the preferred style for business services.
- **Stateful singleton**: holds fields modified at runtime, such as `lastUserId`, `items`, `count`, caches, or temporary transaction state. Requires explicit concurrency design if accessed by multiple threads.
- **Thread-safe**: concurrent calls preserve defined invariants, prevent data races that corrupt logic, and maintain proper memory visibility rules across threads.
- **Reentrant**: a method can be called recursively or concurrently while still behaving correctly due to its own design; this term is not automatically synonymous with singleton or thread-safe.

A singleton holding `final Repository repository` does not mean the repository and the objects it returns are immutable; safety must be evaluated across **the entire object graph and invoked behavior**.

## 2. Why do race conditions happen so easily?

Consider a service storing the current user in a field:

```java
import org.springframework.stereotype.Service;

@Service
public class UnsafeGreetingService {
    private String currentName;

    public String greet(String name) {
        currentName = name;             // Write shared field
        return "Hello " + currentName;  // Read shared field
    }
}
```

This is an illustrative class snippet; it requires running inside a Spring context with component scanning. If two requests call `greet` concurrently, one valid execution ordering could be:

| Time | Request A | Request B |
| --- | --- | --- |
| 1 | `currentName = "Alice"` | |
| 2 | | `currentName = "Bob"` |
| 3 | Reads `currentName`, may receive `"Bob"` | |
| 4 | | Reads `currentName` |

Request A can return `"Hello Bob"` even though A's argument was `"Alice"`. Actual outcomes also depend on scheduling and JVM memory rules: **the bug will not reproduce on every run**. Even when each call runs very quickly, interleaving can still occur between two statements.

The best fix here is to eliminate the field holding call-specific state:

```java
import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    public String greet(String name) {
        String message = "Hello " + name;
        return message;
    }
}
```

The `message` variable and `name` parameter belong to each method invocation, not to a bean field. The two threads have separate stacks and invocations. `String` is immutable, so this example creates no shared mutable state. However, if a local variable points to a **shared** collection or object, merely being a local variable is not enough to guarantee thread safety.

### Three failure categories to distinguish

1. **Race condition / lost update:** multiple threads modify the same state; the outcome depends on interleaving. For example, `count++` under concurrent execution can lose increments.
2. **Visibility:** one thread writes a value, yet another thread is not guaranteed to see the update in time without a happens-before relationship; the compiler/CPU/JVM may optimize or reorder operations under the Java Memory Model.
3. **Broken invariant:** individual fields or operations may each be safe, yet a multi-step combination is not atomic. For instance, checking balance then deducting funds, or checking a key then calling `put`, can fail when steps interleave.

`count++` is semantically equivalent to **read → increment → write** and is not an atomic operation. `volatile int count` only provides visibility and ordering guarantees for field reads/writes; `count++` on a `volatile` field is still non-atomic.

## 3. Choose a stateless design before adding locks

A Spring service should normally only coordinate dependencies and transform input into output:

```java
package edu.example.design;

import java.math.BigDecimal;
import org.springframework.stereotype.Service;

@Service
public class PriceService {
    private static final BigDecimal TAX_RATE = new BigDecimal("0.10");

    public BigDecimal totalWithTax(BigDecimal subtotal) {
        return subtotal.multiply(BigDecimal.ONE.add(TAX_RATE));
    }
}
```

The snippet above is a Spring component class, not a standalone `main` program. `BigDecimal` is immutable; no customer subtotal is stored in a field. `totalWithTax` can be called from multiple threads with different values.

Several ways to reduce shared mutable state:

- **Constructor injection + `final`** for required dependencies; avoid swapping dependencies between requests.
- **Immutable value objects/records** for exchanged data; each call creates new values when needed.
- **Local variables** for intermediate state within a single execution, instead of storing it in singleton fields.
- **Long-lived business data** belongs in a repository/database with appropriate transaction and concurrency rules.
- **Per-request state** carried via parameters or an appropriate scoped context; do not attach a request DTO to a singleton field.

`final` locks the **field reference**, not making the referenced object automatically immutable:

```java
private final java.util.List<String> names = new java.util.ArrayList<>();
// Cannot reassign names = anotherList, yet names.add("Alice") still mutates the ArrayList.
```

For read-only data, you can build a snapshot and publish it immutably via `List.copyOf`/`Map.copyOf`. Ensure the elements themselves are also immutable or safely used if you want to guarantee the entire structure never changes.

## 4. When shared state is unavoidable: pick the right tool

| Requirement | Usually Appropriate Tool | Limits / Points to Consider |
| --- | --- | --- |
| Read-only configuration after initialization | `final` + immutable object | Inner objects must also be immutable or properly managed |
| A simple counter/sequence within one JVM | `AtomicLong`/`AtomicInteger` | Does not automatically group multiple fields into a transaction |
| Many threads counting frequencies under high contention | `LongAdder` | `sum()` under concurrent updates is not an atomic snapshot |
| Protecting a multi-step invariant | `synchronized`, `ReentrantLock` | Use the same lock across all related steps; avoid long I/O inside locks |
| A concurrently accessed map | `ConcurrentHashMap` | Separate `get` followed by `put` is not atomic |
| Simple read/write status flag | `volatile` or `AtomicBoolean` | `volatile` does not protect read-modify-write operations |
| Per-HTTP-request state | Method parameters/local variables or `@RequestScope` | Not automatically propagated into executor threads |
| State for one HTTP session | `@SessionScope` if genuinely needed | Two requests in the same session can still run in parallel |
| Data consistent across multiple processes/pods | DB transactions, optimistic locking, Redis/appropriate atomic ops | JVM locks/atomics protect only one process's memory |

No single Spring annotation solves every case. The tool must match the actual invariant: counting, conditional checks, updating multiple fields, cross-JVM access, or per-request isolation.

### 4.1. AtomicLong: consistent counter within one JVM

```java
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.stereotype.Service;

@Service
public class RequestCounter {
    private final AtomicLong count = new AtomicLong();

    public long next() {
        return count.incrementAndGet();
    }

    public long current() {
        return count.get();
    }
}
```

Each `incrementAndGet()` is an atomic update returning the incremented value. For example, with one counter instance and 8 threads calling it 1,000 times per thread, the final total **is guaranteed to be 8,000**, provided there are no other calls and all tasks complete successfully. The ordering of returned numbers across threads is not guaranteed; the final total is accurate.

When two fields must always change together, two independent `AtomicLong`s cannot be treated as a single transaction. You can store an immutable record in an `AtomicReference` and update via CAS on **the entire record**, or use a lock to protect the invariant.

### 4.2. synchronized: protecting multiple steps with the same lock

```java
public final class StockCounter {
    private int available = 10;

    public synchronized boolean reserveOne() {
        if (available <= 0) {
            return false;
        }
        available--;
        return true;
    }

    public synchronized int remaining() {
        return available;
    }
}
```

Both `synchronized` instance methods use the same `this` monitor. With every access to `available` going through locked methods, the `available > 0` check and decrement sit inside the same critical section. The `synchronized` construct establishes a happens-before relationship between an unlock and a subsequent lock on **the same monitor**, while preserving atomicity for the entire block.

Do not bypass the lock by reading/writing `available` directly from an unsynchronized method if you want to preserve the invariant. Nor should you use two separate locks for two steps of the same rule. For logic involving I/O, databases, or network services, minimize lock hold duration and consider enforcing consistency in the data store.

### 4.3. ConcurrentHashMap and compound operations

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.LongAdder;

public final class MetricsByRoute {
    private final ConcurrentHashMap<String, LongAdder> hits =
            new ConcurrentHashMap<>();

    public void record(String route) {
        hits.computeIfAbsent(route, key -> new LongAdder()).increment();
    }

    public long approximateCount(String route) {
        LongAdder adder = hits.get(route);
        return adder == null ? 0L : adder.sum();
    }
}
```

`computeIfAbsent` atomically installs a value when the key is absent; the adders are separate per-key counters. `LongAdder.sum()` is useful for metrics/telemetry, yet while threads are updating concurrently, the read total may not represent a linearizable point-in-time snapshot. If strict transactional accuracy and consistency are required, use a different tool.

Do not write `if (!map.containsKey(key)) map.put(key, value)` expecting both steps to be atomic; another thread can insert between the two operations. Avoid unintended side effects inside `computeIfAbsent` or `compute` lambdas, as the function may run inside internal synchronization and must not perform long-running work.

### 4.4. Where is volatile appropriate?

```java
public final class ShutdownSignal {
    private volatile boolean stopping;

    public void requestStop() {
        stopping = true;
    }

    public boolean isStopping() {
        return stopping;
    }
}
```

When one thread calls `requestStop()`, other threads reading `isStopping()` get proper visibility guarantees under the Java Memory Model. This works for simple stop flags. However, if the logic is "read if false, then set true so only one thread wins", use `AtomicBoolean.compareAndSet(false, true)` to combine the check and update atomically.

## 5. Practical Spring Core Example on Java 17+

This project directly demonstrates a **Spring Core Container** singleton, requiring no web server. It uses Java 17+, Maven 3.9+, and the `spring-context:6.2.18` dependency. We create a singleton bean `SafeCounter`, retrieve it twice from the context, and increment it concurrently across eight threads. Run the complete program for deterministic output.

Structure:

```text
spring-singleton-concurrency/
├── pom.xml
└── src/main/java/edu/example/concurrency/
    ├── AppConfig.java
    ├── SafeCounter.java
    └── App.java
```

**pom.xml**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.example</groupId>
    <artifactId>spring-singleton-concurrency</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.18</version>
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
                <version>3.5.0</version>
                <configuration>
                    <mainClass>edu.example.concurrency.App</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**src/main/java/edu/example/concurrency/AppConfig.java**

```java
package edu.example.concurrency;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class AppConfig {
    @Bean // Default is singleton in this ApplicationContext.
    public SafeCounter safeCounter() {
        return new SafeCounter();
    }
}
```

**src/main/java/edu/example/concurrency/SafeCounter.java**

```java
package edu.example.concurrency;

import java.util.concurrent.atomic.AtomicLong;

public final class SafeCounter {
    private final AtomicLong value = new AtomicLong();

    public long increment() {
        return value.incrementAndGet();
    }

    public long get() {
        return value.get();
    }
}
```

**src/main/java/edu/example/concurrency/App.java**

```java
package edu.example.concurrency;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class App {
    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            SafeCounter first = context.getBean(SafeCounter.class);
            SafeCounter second = context.getBean(SafeCounter.class);
            System.out.println("same singleton: " + (first == second));

            int threadCount = 8;
            int callsPerThread = 1_000;
            ExecutorService executor = Executors.newFixedThreadPool(threadCount);
            CountDownLatch start = new CountDownLatch(1);
            List<Future<?>> futures = new ArrayList<>();

            try {
                for (int t = 0; t < threadCount; t++) {
                    futures.add(executor.submit(() -> {
                        start.await();
                        for (int i = 0; i < callsPerThread; i++) {
                            first.increment();
                        }
                        return null;
                    }));
                }
                start.countDown();
                for (Future<?> future : futures) {
                    future.get();  // Wait for completion, while surfacing task errors.
                }
                System.out.println("counter: " + first.get());
            } finally {
                executor.shutdown();
            }
        }
    }
}
```

Run in the directory containing `pom.xml`:

```bash
mvn -q compile exec:java
```

**Program stdout:**

```text
same singleton: true
counter: 8000
```

Maven/Spring logs emitted by your environment may vary; the two lines above are the `System.out.println` output. The value `8000` is deterministic because `AtomicLong` guarantees every increment and the program's `Future.get()` waits for all eight tasks. This run has only one context, one `safeCounter` bean definition, and no other threads modifying the bean. Execution timing and thread names are non-deterministic yet do not affect the final value.

**Contrast experiment:** If you replace the `AtomicLong` field in `SafeCounter` with `private long value;` and change `increment()` to `return ++value;`, the program has a data race. The final value **can** be less than 8000, though on some runs it may still output 8000 depending on thread scheduling; never use a single passing run to prove code is thread-safe. The main version above intentionally uses only the safe implementation for reliable output.

> In production, choose a Spring version supported by your project and keep it updated per your maintenance policy; the version in the POM here is for reproducing the example.

## 6. Why must constructor injection, `final`, and `@PostConstruct` still be understood properly?

```java
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {
    private final PricePolicy pricePolicy;

    public CheckoutService(PricePolicy pricePolicy) {
        this.pricePolicy = pricePolicy;
    }

    public Money checkout(Order order) {
        return pricePolicy.calculate(order);
    }
}
```

This illustrates a single component; `PricePolicy`, `Money`, and `Order` are domain types that must be defined in the application, not a standalone runnable program. The `pricePolicy` field is `final` and assigned in the constructor. That keeps the dependency consistent across the bean's lifecycle and avoids certain improper-initialization publication issues. However, if `PricePolicy` contains an unsynchronized mutable `HashMap`, `checkout` can still be unsafe.

A typical Spring bean lifecycle is **construct → inject dependencies → initialization callbacks / `BeanPostProcessor` → publish for normal use**. You can initialize a cache in `@PostConstruct`, yet avoid mutating state arbitrarily afterward if multiple threads can use the bean. Avoid letting `this` escape from the constructor, such as registering into a global registry or starting threads that use an incompletely initialized instance. Circular dependencies and early references can also break simple initialization-order assumptions.

If a cache needs updates after startup, use immutable snapshots published via `volatile`/`AtomicReference` or an appropriate locking mechanism. Example:

```java
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;

public final class SettingsSnapshot {
    private final AtomicReference<Map<String, String>> current =
            new AtomicReference<>(Map.of());

    public void replace(Map<String, String> fresh) {
        current.set(Map.copyOf(fresh));
    }

    public String lookup(String key) {
        return current.get().get(key);
    }
}
```

`Map.copyOf` produces a map that cannot be mutated through its API; `AtomicReference.set/get` publishes the whole snapshot. If keys/values are mutable objects, they must be controlled separately; here `String` is immutable. Each `lookup` sees **one complete snapshot**; there is no `clear` followed by `putAll` exposing a half-updated map to readers.

## 7. Do other scopes solve all concurrency problems?

| Scope | Who shares the bean? | Recommendation |
| --- | --- | --- |
| `singleton` | Callers referencing the same bean in the same container | Prefer stateless, immutable, or explicit synchronization |
| `prototype` | Each container request for the bean receives a new target | Avoid sharing the target if state is private; caller manages lifetime |
| `request` | Components within the same HTTP request | Isolates per-request state, yet does not replace rules when intentionally sharing objects |
| `session` | HTTP requests in the same `HttpSession` | A session can handle **multiple concurrent requests**; mutable state still needs protection |
| `application` | One `ServletContext` | Shared state, subject to concurrency and scoped to one application instance |
| `websocket` | One corresponding WebSocket/STOMP session | Multiple messages in the same session may still need synchronization depending on processing flow |

Changing a bean to `prototype` does not necessarily fix the bug:

```java
@Component
@Scope("prototype")
class RequestBuffer {
    private final StringBuilder builder = new StringBuilder();

    public void append(String s) { builder.append(s); }
    public String result() { return builder.toString(); }
}

@Service
class WrongSingletonConsumer {
    private final RequestBuffer buffer;

    WrongSingletonConsumer(RequestBuffer buffer) {
        this.buffer = buffer; // Prototype is resolved once when the singleton is created.
    }
}
```

The snippet above requires imports for `org.springframework.stereotype.Component`, `Service`, and `org.springframework.context.annotation.Scope`. `WrongSingletonConsumer` still uses **one** `RequestBuffer` injected at singleton creation; threads calling the consumer can touch the same mutable buffer concurrently. If a fresh instance is truly needed each time, inject `ObjectProvider<RequestBuffer>` and call `getObject()` at operation time, or apply the appropriate scope design. Do not try to fix race conditions by randomly changing scopes.

With `@RequestScope` and `@SessionScope`, Spring can use a scoped proxy so a singleton invokes the target of the active scope. A scoped proxy does **not** automatically make the target thread-safe and does not automatically propagate the request context to an `@Async` task. HTTP session state can also be updated simultaneously by two HTTP requests belonging to the same session. If both requests mutate the same cart/session bean, you must enforce invariants just like for a singleton.

## 8. Places where people mistakenly assume Spring will synchronize

**Spring MVC controllers:** `@RestController`/`@Controller` are usually singleton beans. The servlet container can use multiple request threads calling handlers on **the same controller object**. Do not store `currentRequest`, `loggedInUser`, request DTOs, or response builders as controller instance fields. Use handler parameters, request attributes, models, or properly designed services.

```java
@RestController
class HelloController {
    // Do not store lastName in a singleton field.
    @GetMapping("/hello")
    String hello(@RequestParam String name) {
        return "Hello " + name;
    }
}
```

This snippet requires Spring MVC imports (`RestController`, `GetMapping`, `RequestParam`) and the web starter; it illustrates a simple endpoint. Each request has its own `name` parameter.

**`@Transactional`:** Transactions are managed per invocation and matching resource context. It **does not lock a Java singleton instance**; nor does it make `count++` on a service field atomic. Database data consistency also depends on isolation levels, row/version locking, and transaction boundaries. Do not retain a mutable JPA `EntityManager`/entity for direct unsafe sharing across requests.

**`@Async`, `@Scheduled`, message listeners:** The same bean can be invoked from multiple tasks/threads. `@Async` can run in parallel; `@Scheduled` can interact with other tasks, and async mechanisms do not automatically make shared fields safe. Thread-bound request contexts are not normally propagated automatically into thread pools. Avoid using `ThreadLocal` as a substitute for request scope without `remove()` cleanup in a `finally` block, because worker threads are reused.

**`@Cacheable`:** A cache provider may protect its internal cache storage structure, yet it does not automatically make returned mutable value objects thread-safe. Multiple concurrent calls can also compute a cache miss simultaneously unless the configuration/engine supports appropriate coalescing; do not rely on cache annotations to guard arbitrary shared critical sections.

**Prototype, proxies, and `@Lazy`:** These mechanisms control how beans are created, resolved, or deferred; they do not automatically provide thread confinement for mutable singleton fields. Spring AOP proxies also do not implicitly serialize method calls.

## 9. Multi-level concurrency control

A logical mutation may need protection at multiple layers:

```text
Request thread A --                   +--> singleton service -- AtomicLong / synchronized
Request thread B --/              |
                                  +--> repository / database
                                               |
                                      transaction + version check
                                               |
                                        multiple instances/pods
```

- **Within one JVM:** `synchronized`, `Lock`, `Atomic*`, concurrent collections, or stateless design preserve object invariants.
- **Across multiple JVMs/pods:** JVM monitors/`AtomicLong` do not coordinate across two processes. For inventory counts, balances, uniqueness, idempotency, and system-wide limits, enforce guarantees in a shared store: unique constraints, optimistic locking (`@Version` in JPA), conditional updates, database locks, or atomic Redis operations where appropriate.
- **Consistency across multiple systems:** a Java lock does not extend to a message broker or another service. You must design idempotency, retries, and eventual/strong consistency according to actual requirements.

The `AtomicLong` counter in `SafeCounter` in section 5 is accurate **for that bean**. If you deploy two application instances, each instance has its own counter; a cluster-wide total must be aggregated/synchronized outside the JVM.

## 10. Testing race conditions and thread safety

Single-threaded tests do not verify concurrent code. For objects with clear invariants, design tests with multiple tasks, synchronize their start with `CountDownLatch` or `CyclicBarrier`, and **await every `Future`** before asserting final state. `App.java` in section 5 does exactly this. A counter safety test can assert `finalCount == threadCount * incrementsPerThread`.

Keep in mind:

- Tests exercise a few actual interleavings; they **do not generally prove** that every possible schedule is correct.
- Do not rely on `Thread.sleep` to force thread ordering; sleeping does not guarantee desired rendezvous points.
- A data race may not surface on a developer laptop yet appear in production under higher traffic, different CPUs/JVMs, or different scheduler conditions.
- Use stress testing and specialized tools like **jcstress** when low-level Java Memory Model behaviors must be evaluated; for business logic, start with invariants and representative integration/concurrency tests.
- Check exception handling from tasks: `submit` stores exceptions inside the `Future`; if you omit `get`, tests can silently miss failures.
- Evaluate contention and latency: a locking strategy that yields correct results yet holds locks too long can cause bottlenecks; optimize only with profiling/load-test evidence.

A short review checklist for any singleton with fields:

1. Does the field change **after initialization**?
2. Is there any path for two threads to access it concurrently, including MVC, scheduled, async, listeners, or websocket?
3. Is there an invariant spanning multiple operations or multiple objects?
4. Who owns the state? Is it per-request, per-session, per-instance, or cluster-wide data?
5. Are there publication/visibility/happens-before guarantees? Do all read/write paths follow the same synchronization mechanism?
6. Does the concurrency test check invariants and retrieve exceptions from tasks?

## 11. Common errors and how to fix them

| Error | Why It Is Wrong | How to Fix |
| --- | --- | --- |
| Singleton `@Service` holds `currentUser` | Requests overwrite each other's state | Use method parameters or an appropriate request context |
| `volatile long count; count++;` | `++` is not atomic | `AtomicLong.incrementAndGet()` or a lock |
| Using `HashMap` and mutating from multiple threads | Structure and visibility are unprotected | `ConcurrentHashMap` and appropriate atomic operations |
| Using `Collections.synchronizedMap` with check-then-put outside a lock | Individual thread-safe methods do not make compound sequences atomic | Wrap the entire compound operation in the same lock or use `computeIfAbsent` |
| Assuming `final List` means immutable | `final` only fixes the reference | Use an immutable copy or guard updates |
| Using `@Scope("prototype")` to cure singleton state | Prototype may still be retained by a singleton injected once | Separate state; look up prototype at runtime when needed |
| Keeping mutable `@SessionScope` without locking | Parallel requests can share the same session bean | Define invariants and use appropriate synchronization |
| Assuming `@Transactional` automatically protects Java fields | DB transactions do not create monitor locks for singletons | Distinguish Java concurrency from DB consistency |
| Using `synchronized` to maintain total count across multiple pods | Locks exist only inside that single JVM | Use a shared store/atomic updates outside the JVM |
| Updating multiple fields with separate `Atomic*` and treating as a transaction | Does not preserve cross-field invariants | Use a single atomic snapshot or a lock |
| Observing no race in a single test run | Not observing a race does not mean none exists | Stress test, invariant-based assertions, JMM review |

## 12. Self-assessment exercises

1. Two requests call the same `@Service` and both write `private String lastUser`. Is this singleton bean safe? Why?
2. If `private final AtomicLong counter` resides in a singleton, and 16 threads each call `incrementAndGet()` 250 times, what is the value after all tasks succeed?
3. Why is `volatile int counter` insufficient for `counter++` to be accurate? State one fix.
4. Can `@SessionScope` be accessed by multiple threads simultaneously? Give an example with two requests sharing a cookie.
5. A singleton directly injects a mutable prototype: once the singleton bean is created, does every request use a fresh prototype?
6. Two replicas use `synchronized` on their own singletons to manage the same SKU with 1 item remaining. Will the system prevent overselling?
7. You want to swap a configuration map at runtime so every request always reads one consistent version. How do you use an immutable snapshot + `AtomicReference`?
8. When should you choose `LongAdder` over `AtomicLong`, and why is `sum()` unsuitable if you need a strictly exact snapshot between updates?

**Answer hints:** (1) No, a shared mutable field causes races/data leaks. (2) 4,000. (3) Read-modify-write consists of multiple steps; use `AtomicInteger.incrementAndGet()` or a lock. (4) Yes, a browser can send two concurrent requests in the same session. (5) No, the prototype is resolved once at injection time unless using a lookup/provider. (6) No, each lock is confined to one JVM; use a shared store with consistency guarantees. (7) Create an immutable `Map.copyOf` and publish via `set`; each reader calls `get` for one snapshot. (8) Use for heavily updated statistical counters; `sum` is not an atomic snapshot under concurrent updates.

## References

- Spring Framework Reference — Bean Scopes (singleton, prototype, and web scopes): https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html
- Spring Framework Reference — Using `@PostConstruct` and `@PreDestroy`: https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/postconstruct-and-predestroy-annotations.html
- Java SE 17 — `AtomicLong`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicLong.html
- Java SE 17 — `ConcurrentHashMap`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html
- Java Language Specification — Chapter 17: Threads and Locks (happens-before, synchronization, volatile): https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html
