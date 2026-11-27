# Singleton Lifecycle, Shared State, and Thread Safety

In **SPRING_CLOUD_FUNCTION**, a business function is expressed as a **Supplier<T>**, **Function<T, R>**, or **Consumer<T>** and is typically registered as a Spring bean. By default, beans have **singleton scope**: one object managed by Spring within an application context and reused across multiple invocations. When the same bean is triggered multiple times by HTTP, Spring Cloud Stream, or serverless adapters, state stored inside the bean or objects captured by a lambda may be accessed simultaneously by multiple calls.

That is why understanding **singleton lifecycle, shared state, and thread safety** is essential for reusing business logic independently of protocols. This lesson belongs to the **Function Model** chapter, progressing from how Spring instantiates beans to race condition bugs, stateless solutions, scenarios that genuinely require managed state, and testing strategies.

## 1. What Does Singleton Mean in Spring?

In Spring, **singleton scope** means Spring normally creates and manages **one bean instance per bean definition within a single application context**. A bean name does not imply a single global instance across every process, host, or application context in the world.

| Context | Scope of a Singleton Bean |
| --- | --- |
| One Spring application context | Repeated lookups of the same bean typically return the same instance |
| Two Spring application contexts in one JVM | Each context can have its own singleton |
| Two application replicas | Each replica has its own application context and singletons |
| Serverless cold start or another instance | May initialize a fresh context and beans |
| New HTTP request or message | Does not recreate the singleton bean by default |

In a declaration like:

~~~java
@Bean("normalizeCode")
Function<String, String> normalizeCode() {
    return input -> input.trim().toUpperCase(java.util.Locale.ROOT);
}
~~~

Spring calls the **normalizeCode()** method when constructing the bean (during the appropriate initialization phase), then holds the returned Function object. When an adapter or FunctionCatalog invokes **apply(...)**, the lambda body executes the normalization.

~~~mermaid
flowchart TD
    A["ApplicationContext initializes"] --> B["@Bean normalizeCode()"]
    B --> C["One singleton Function bean"]
    C --> D["Invocation apply #1"]
    C --> E["Invocation apply #2"]
    C --> F["Invocation apply #3"]
~~~

**Singleton does not mean only one call is processed at a time.** Spring does not automatically wrap **Function.apply(...)**, **Supplier.get()**, or **Consumer.accept(...)** with a lock merely because the object is a singleton bean. Actual concurrency depends on the adapter, thread pool, scheduler, binder, and deployment configuration.

Nor should **Spring bean singleton scope** be confused with the **Java Singleton pattern**: Spring manages object scope inside its container without requiring the Java class to have a private constructor or a static **getInstance()** method.

## 2. Distinguishing Three Points in Time

To analyze state bugs, distinguish:

1. **Bean creation:** Spring runs the **@Bean** factory method or constructor and injects dependencies.
2. **Function object creation:** the lambda, method reference, or class **implementing Function** is returned/registered; for a singleton bean, this object is usually reused.
3. **Function invocation:** the adapter or Java code triggers **get()**, **apply(input)**, or **accept(input)**. This can happen repeatedly and concurrently.

Example of a Supplier returning time:

~~~java
@Bean
Supplier<Instant> startupTime(Clock clock) {
    Instant snapshot = clock.instant();
    return () -> snapshot;
}

@Bean
Supplier<Instant> currentTime(Clock clock) {
    return clock::instant;
}
~~~

Assuming **java.time.Clock**, **java.time.Instant**, and **java.util.function.Supplier** are imported:

- **startupTime** computes **snapshot** as soon as the bean is created, so subsequent **get()** calls return the same timestamp.
- **currentTime** holds a reference to **clock.instant()**, invoked on every **get()** call.
- Both beans can still be singletons. **Freshness of the result** depends on where the computation runs, not on switching to prototype scope.

Similarly, in **Function<T, R>**, variables declared inside the **apply(...)** body are local to each invocation, whereas objects outside the lambda that are **captured** can be shared across invocations.

## 3. Where Does Shared State Appear?

Shared state is data that multiple invocations can read or update through the same object. It can reside in:

- Mutable fields of a singleton bean.
- Mutable local variables inside a **@Bean** method that are referenced by a lambda (*captured variables*).
- Services, caches, repositories, or clients injected into the Function.
- Shared collections such as **ArrayList**, **HashMap**, mutable DTOs, or counters.
- Global storage (**static fields**), other singletons, or shared memory within the same instance.

Example creating a buggy Function:

~~~java
@Bean("unsafeCounter")
Function<String, Long> unsafeCounter() {
    long[] counter = {0L};

    return input -> {
        long next = counter[0] + 1;
        counter[0] = next;
        return next;
    };
}
~~~

Even though **counter** is a local variable of **unsafeCounter()**, the **long[]** array remains referenced by the lambda after the method returns. Invocations of the same Function bean update **the exact same array element**.

With two threads:

~~~text
Initial value: counter[0] = 8

Thread A                  Thread B
----------------------    ----------------------
read counter[0] = 8
                          read counter[0] = 8
compute next = 9
                          compute next = 9
write counter[0] = 9
                          write counter[0] = 9

Actual result: 9; expected after two increments: 10
~~~

This is a **lost update**, a form of **race condition**. The read–increment–write sequence is not atomic, even though the syntax spans only a few lines.

## 4. Three Aspects of Thread Safety

Whether a function is safe under concurrent calls depends on the data and the operations accessing it.

| Aspect | Question | Risk Example |
| --- | --- | --- |
| **Atomicity** | Must a sequence of operations happen as a single unit? | **counter++** consists of read, add, write |
| **Visibility** | Do other threads see updates in a timely manner? | Mutable field lacking proper synchronization |
| **Ordering** | Must steps preserve observation or execution order? | Writing state before emitting event while two threads interleave |

**volatile** helps guarantee visibility and certain access ordering rules, yet **it does not make counter++ an atomic increment**. Adding **volatile** to a field while keeping a non-atomic increment still fails to fix lost updates.

Likewise, **Collections.synchronizedList(...)** guards individual operations according to that collection's contract; compound sequences like "check absent then add" may still need synchronization across the entire critical section. **ConcurrentHashMap** protects its supported concurrent operations, but it does not automatically guarantee multi-step workflows or transactions across databases/brokers.

Distinguish two properties:

- **Thread-safe:** data structures or logic do not corrupt state and preserve declared invariants under multi-threaded access.
- **Idempotent:** repeating the same request/event causes no unwanted extra business effect.

An **AtomicLong** counter can be thread-safe yet **not idempotent**: if the same event is redelivered, it increments again.

## 5. Preferred Approach: Stateless Functions with Immutable DTOs

For most business transformation logic, the simplest and most testable approach is **avoiding shared mutable state**. Each invocation receives input, computes using local variables, and returns a new output.

Example Java 17+ application using Spring Boot and Spring Cloud Function. For convenience, data types are placed in a single file **SafeFunctionsApplication.java**:

~~~java
package example.function;

import java.math.BigDecimal;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.Function;
import java.util.function.Supplier;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class SafeFunctionsApplication {

    public static void main(String[] args) {
        SpringApplication.run(SafeFunctionsApplication.class, args);
    }

    public record PriceRequest(
        String sku,
        int quantity
    ) {}

    public record PriceQuote(
        String sku,
        int quantity,
        BigDecimal unitPrice,
        BigDecimal total
    ) {}

    public static final class PriceCatalog {
        private final Map<String, BigDecimal> prices;

        public PriceCatalog(Map<String, BigDecimal> prices) {
            this.prices = Map.copyOf(prices);
        }

        public BigDecimal getUnitPrice(String sku) {
            BigDecimal price = prices.get(sku);
            if (price == null) {
                throw new IllegalArgumentException(
                    "Unknown SKU: " + sku);
            }
            return price;
        }
    }

    public static final class PriceService {
        private final PriceCatalog catalog;

        public PriceService(PriceCatalog catalog) {
            this.catalog = catalog;
        }

        public PriceQuote quote(PriceRequest request) {
            if (request == null
                    || request.sku() == null
                    || request.sku().isBlank()
                    || request.quantity() <= 0) {
                throw new IllegalArgumentException(
                    "Invalid price request");
            }

            String sku = request.sku()
                .trim().toUpperCase(Locale.ROOT);

            BigDecimal unitPrice =
                catalog.getUnitPrice(sku);

            // All variables below belong to a single invocation.
            BigDecimal total = unitPrice.multiply(
                BigDecimal.valueOf(request.quantity()));

            return new PriceQuote(
                sku, request.quantity(), unitPrice, total);
        }
    }

    @Bean
    PriceCatalog priceCatalog() {
        return new PriceCatalog(Map.of(
            "BOOK", new BigDecimal("85000"),
            "PEN", new BigDecimal("12000")
        ));
    }

    @Bean
    PriceService priceService(PriceCatalog catalog) {
        return new PriceService(catalog);
    }

    @Bean("calculatePrice")
    Function<PriceRequest, PriceQuote> calculatePrice(
            PriceService service) {
        return service::quote;
    }

    // Demo for state requiring atomic increments within ONE instance.
    @Bean("newReference")
    Supplier<String> newReference() {
        AtomicLong counter = new AtomicLong();
        return () -> "demo-" + counter.incrementAndGet();
    }
}
~~~

With input:

~~~json
{
  "sku": "book",
  "quantity": 3
}
~~~

**calculatePrice** returns equivalent data:

~~~json
{
  "sku": "BOOK",
  "quantity": 3,
  "unitPrice": 85000,
  "total": 255000
}
~~~

Why is **calculatePrice** well-suited for concurrent calls?

1. **PriceRequest** and **PriceQuote** are Java records; all components in the example are immutable types or used immutably.
2. **PriceCatalog** holds an immutable **Map.copyOf(...)** with immutable **BigDecimal** values.
3. **PriceService** has a **final** field referencing the read-only catalog; the service itself never stores the current request.
4. Variables **sku**, **unitPrice**, and **total** live inside **quote(...)** and are computed per invocation.
5. The Function bean is reused but contains no mutable counter or list used in price calculation.

Thread safety here comes from **design and the objects involved**, not automatically from **@Bean**, **final**, or **record**. A record containing a **mutable List** or a **final** field pointing to a **mutable HashMap** can still expose shared state.

## 6. When Shared State Is Needed: Choosing the Right Mechanism

Not every Function can be stateless. Counters, caches, concurrency limits, or connection state may need to be shared across calls. The protection mechanism must match the requirement.

| Requirement | Typical Suitable Approach | Limitation |
| --- | --- | --- |
| Increment counter in one JVM | **AtomicLong**, **LongAdder** | Valid only within the current instance |
| Concurrently accessed key/value map | **ConcurrentHashMap** and appropriate atomic operations | Does not replace multi-step transactions |
| Protect a multi-field invariant | **synchronized** or **Lock** with small, clear critical sections | Can increase latency and reduce throughput |
| Data caching | Thread-safe cache with TTL and reload policy | Caches are not automatically consistent across replicas |
| Business event ordering | Ordering/partitioning mechanism or versioned store | Cannot rely solely on in-JVM synchronized |
| Unique sequence across multiple replicas | Database sequence or suitable distributed ID generator | AtomicLong in one bean is not system-wide |
| Business data must be durable | Database, transactions, unique constraints | Singleton memory is lost on application restart |

In the **newReference** example, each **Supplier.get()** calls **AtomicLong.incrementAndGet()**; the value increments safely when multiple threads access **the same Supplier instance**.

~~~java
Supplier<String> ref = new SafeFunctionsApplication().newReference();

String first = ref.get();  // "demo-1"
String second = ref.get(); // "demo-2"
~~~

However, **demo-1** can appear again on another replica or after an application restart. Therefore, **do not use this counter as a transaction code or global ID in a multi-instance system**. If replacing **AtomicLong** with **LongAdder**, adds and reads suit throughput metrics well, though **sum()** is not an atomic snapshot concurrent with ongoing updates.

### synchronized Does Not Solve Distributed Systems

Example:

~~~java
public final class LocalSequence {
    private long current;

    public synchronized long next() {
        return ++current;
    }
}
~~~

**next()** is safe if all calls access **the same LocalSequence inside one JVM**. When running three application instances, each instance has its own **current** variable. A Java lock does not lock JVMs on separate machines.

## 7. Common Traps When Lambdas Capture State

A lambda may look like a pure function because it has no class fields, yet it can still capture a mutable object:

~~~java
@Bean
Function<String, Integer> countRequests() {
    java.util.List<String> requests =
        new java.util.ArrayList<>();

    return value -> {
        requests.add(value);
        return requests.size();
    };
}
~~~

Here, **requests** lives as long as the Function bean because the lambda holds a reference to it. **ArrayList** is not designed for threads adding elements concurrently without proper synchronization. Results may be wrong, internal state corrupted, or exceptions thrown.

One fix if business logic genuinely just needs an invocation count:

~~~java
@Bean
Function<String, Long> countRequestsSafely() {
    AtomicLong calls = new AtomicLong();
    return ignored -> calls.incrementAndGet();
}
~~~

Yet if only **operational statistics** are needed, use a dedicated metrics mechanism rather than putting a business counter inside the function. If every request must be stored, evaluate security, memory, durability, concurrency, and retention requirements; switching to **Collections.synchronizedList** does not address all of those.

**Code review rule:** inspect fields, injected dependencies, and variables captured by lambdas. The absence of fields in a **@Configuration** class is not enough to conclude a Function is stateless.

## 8. Invocations from HTTP, Events, and Serverless May Differ

The same Function bean may be invoked by adapters using different concurrency strategies.

| Environment | What Can Happen | What to Control |
| --- | --- | --- |
| **HTTP** | Multiple requests handled by multiple threads on the same instance | Shared mutable state, request context, timeouts |
| **Spring Cloud Stream** | Binder invokes function as a consumer, possibly configured for concurrency or multiple instances | Message order, retries, partitions, idempotency |
| **Serverless** | Runtime may reuse an instance or spin up multiple parallel instances | Reset state, per-instance divergence, retries |
| **Reactive adapter** | Elements processed via publishers and may switch schedulers/threads | Shared state, subscriptions, backpressure, thread hopping |

From the **Function<T, R> signature**, you cannot deduce thread counts or concurrency limits. A binder might consume sequentially on one thread in one configuration, yet changing the binder, partitions, or instance count alters those conditions.

**Proper designs should be verified under realistic deployment configurations** and avoid relying on the assumption that an adapter will always invoke functions sequentially.

Example using the same **calculatePrice** over HTTP with the Spring Cloud Function Web starter:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-function-web</artifactId>
</dependency>
~~~

Select the bean:

~~~yaml
spring:
  cloud:
    function:
      definition: calculatePrice
~~~

Send HTTP POST when the app runs on port 8080:

~~~bash
curl -i -X POST http://localhost:8080/calculatePrice \
  -H "Content-Type: application/json" \
  -d '{"sku":"book","quantity":3}'
~~~

Multiple clients may send requests concurrently. The adapter invokes the same **calculatePrice.apply(...)** logic across requests; there is no automatic guarantee that it creates a new **PriceService** per request.

With Spring Cloud Stream and a suitable binder, the same bean can be selected:

~~~yaml
spring:
  cloud:
    function:
      definition: calculatePrice
    stream:
      bindings:
        calculatePrice-in-0:
          destination: price-requests
        calculatePrice-out-0:
          destination: price-quotes
~~~

Spring Cloud Stream dependencies, a binder, a broker, and real connection configuration are required. The **PriceService.quote** logic stays unchanged. Message order, concurrency, and retries depend on the binder and configuration; **do not treat a singleton Function as a global event serialization mechanism**.

## 9. Prototype and Request Scopes Are Not Default Fixes

Spring supports scopes beyond singleton, though their boundaries must be understood.

**Prototype** creates a new bean whenever the Spring container is asked to create/fetch it during dependency resolution. It **does not mean** "every time Function.apply(...) runs, Spring automatically creates a new object."

Confusing example:

~~~java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
class Worker {
    private int count;

    int execute() {
        return ++count;
    }
}

@Bean
Function<String, Integer> useWorker(Worker worker) {
    return ignored -> worker.execute();
}
~~~

With appropriate imports and Spring configuration, if **useWorker** is a singleton, the **worker** dependency is supplied by Spring when constructing that singleton. The lambda may retain **the exact same Worker** across all **apply(...)** invocations, even though **Worker** is defined with prototype scope.

If a fresh instance is genuinely needed per invocation:

~~~java
@Bean
Function<String, Integer> useFreshWorker(
        org.springframework.beans.factory.ObjectProvider<Worker> workers) {
    return ignored -> workers.getObject().execute();
}
~~~

**ObjectProvider.getObject()** fetches a new prototype instance when the lambda executes. Even so, this carries object allocation costs and resource lifecycle overhead; for short, stateless transformations, creating a worker per invocation is usually unnecessary.

**Request scope** depends on a request context (typically HTTP), so do not rely on it for a Function meant to be reused unchanged across brokers or serverless. Scoped proxies have their own behavior; you must verify context availability at invocation time and never assume every adapter provides an HTTP request scope.

> Fix **the root cause of shared mutable state** before changing bean scopes. Stateless singletons are usually simpler, more resource-efficient, and well-suited to Spring Cloud Function.

## 10. Supplier, Function, Consumer: Different State Risks

| Model | Examples of State That Could Be Shared | Prevention |
| --- | --- | --- |
| **Supplier<T>** | Counters, caches, bean-creation timestamps | Compute fresh values inside **get()**, use synchronization when needed |
| **Function<T, R>** | **lastRequest** fields, result lists, captured variables | Prefer local variables, immutable DTOs, stateless dependencies |
| **Consumer<T>** | Buffers, sets of processed IDs, connections and side effects | Idempotency, transactions, resource management, concurrency control |

Example audit-logging Consumer:

~~~java
public record AuditEvent(String eventId, String action) {}

public interface AuditRepository {
    // Implementation must guarantee idempotent/durable behavior by eventId.
    void insertIfAbsent(AuditEvent event);
}

@Bean("recordAudit")
java.util.function.Consumer<AuditEvent> recordAudit(
        AuditRepository repository) {
    return repository::insertIfAbsent;
}
~~~

This is a **design pattern**, assuming an injected **AuditRepository** implementation exists. The **recordAudit** bean can still be a singleton; safety depends on the repository contract and the implementation of **insertIfAbsent**.

An in-memory **HashSet<String> seenIds** inside a singleton bean may block duplicates in limited single-JVM scenarios, but it does not survive restarts and does not coordinate across replicas. An operation like **if (!seen.contains(id)) { seen.add(id); save(); }** is also non-atomic when multiple threads execute concurrently.

If events can be redelivered, use a stable business key and unique constraints/transactions in an appropriate storage system. **In-JVM thread safety does not replace distributed idempotency.**

## 11. Reactive: Subscriptions, Schedulers, and Shared State

Spring Cloud Function can also use **Supplier<Flux<T>>** or **Function<Flux<T>, Flux<R>>** with Project Reactor. Distinguish two moments: creating the publisher and **subscribing** to the publisher.

Example:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.function.Supplier;
import reactor.core.publisher.Flux;

@Bean
Supplier<Flux<Instant>> streamCurrentTime(Clock clock) {
    return () -> Flux.defer(() -> Flux.just(clock.instant()));
}
~~~

With this publisher, **clock.instant()** is evaluated when the returned Flux receives a subscription, thanks to **Flux.defer(...)**. If written as:

~~~java
@Bean
Supplier<Flux<Instant>> streamSnapshotTime(Clock clock) {
    Instant snapshot = clock.instant();
    return () -> Flux.just(snapshot);
}
~~~

the **snapshot** value is captured when the bean is initialized; invoking the Supplier again or adding new subscriptions will still emit the same stored value.

Triggering semantics for a **reactive Supplier** via a specific adapter must be verified: some adapters subscribe once to a long-lived publisher, while others follow different rules. **Do not assume Supplier.get() is invoked once per Flux element**.

Another bug:

~~~java
java.util.List<String> shared = new java.util.ArrayList<>();

Function<Flux<String>, Flux<Integer>> unsafeStream = inputs ->
    inputs.map(value -> {
        shared.add(value);
        return shared.size();
    });
~~~

When multiple subscriptions/threads share this Function object, **shared** can be updated concurrently. Reactor does not automatically make an external **ArrayList** thread-safe. Choose operators that scope state per subscription, use proper concurrent structures, or isolate state into a component with an explicit concurrency contract.

**ThreadLocal is also unsafe for holding request context across arbitrary reactive pipelines.** When async boundaries or schedulers switch threads, ThreadLocal values may not propagate; pooled threads may be reused. For metadata traveling with requests/messages, consider **Message<T> headers** or context propagation supported by the library, accompanied by tests across asynchronous boundaries.

## 12. Protecting Metadata and Input Data

In Spring Cloud Function adapters, input data sometimes arrives as **Message<T>** containing payload and headers. Do not mutate shared payloads or header Maps if objects are reused.

~~~java
@Bean
Function<
        org.springframework.messaging.Message<String>,
        org.springframework.messaging.Message<String>> normalizeMessage() {

    return input ->
        org.springframework.messaging.support.MessageBuilder
            .withPayload(input.getPayload().trim())
            .copyHeaders(input.getHeaders())
            .build();
}
~~~

This example creates a **new Message**. It retains references to copied header values; if values are mutable objects, examine data ownership boundaries carefully. **copyHeaders(...)** does not deep-copy nested objects.

Business messages should be cleanly typed; a **record** with immutable field references does not automatically make a contained List or Map immutable. To curb shared mutable state, use **List.copyOf(...)** or **Map.copyOf(...)** in constructors or DTO factories where appropriate.

For metadata passing through HTTP, Stream, or serverless, adapters may map headers differently. Never rely on client-declared headers as authentication/authorization proof unless verified by an appropriate security layer.

## 13. Testing Correctness Under Concurrency

An ordinary unit test invoking **apply(...)** once only checks business logic; it is unlikely to catch race conditions when multiple invocations run simultaneously.

### 13.1. Unit Tests for Stateless Functions

Based on **SafeFunctionsApplication**:

~~~java
package example.function;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class SafeFunctionsApplicationTest {

    private final SafeFunctionsApplication app =
        new SafeFunctionsApplication();

    @Test
    void quoteUsesLocalValuesAndImmutableCatalog() {
        var service = app.priceService(app.priceCatalog());
        var function = app.calculatePrice(service);

        var quote = function.apply(
            new SafeFunctionsApplication.PriceRequest("book", 3));

        assertEquals("BOOK", quote.sku());
        assertEquals(new BigDecimal("255000"), quote.total());
    }

    @Test
    void rejectsInvalidQuantity() {
        var function = app.calculatePrice(
            app.priceService(app.priceCatalog()));

        assertThrows(IllegalArgumentException.class,
            () -> function.apply(
                new SafeFunctionsApplication.PriceRequest("BOOK", 0)));
    }
}
~~~

### 13.2. Testing an Atomic Counter Under Concurrent Bean Calls

~~~java
package example.function;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.HashSet;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.Executors;
import java.util.function.Supplier;
import java.util.stream.IntStream;

import org.junit.jupiter.api.Test;

class ConcurrentSupplierTest {

    @Test
    void oneSupplierProducesDistinctLocalSequenceValues()
            throws Exception {

        Supplier<String> supplier =
            new SafeFunctionsApplication().newReference();

        var executor = Executors.newFixedThreadPool(8);

        try {
            List<Callable<String>> calls =
                IntStream.range(0, 100)
                    .mapToObj(i -> (Callable<String>) supplier::get)
                    .toList();

            var futures = executor.invokeAll(calls);
            var unique = new HashSet<String>();

            for (var future : futures) {
                unique.add(future.get());
            }

            assertEquals(100, unique.size());
        } finally {
            executor.shutdownNow();
        }
    }
}
~~~

This test has bounded value: it tests **100 concurrent invocations on one Supplier instance** and expects 100 distinct values. It does not prove return order matches submission order, does not prove uniqueness across replicas, and does not guarantee all other concurrency paths in the application are safe.

A test intentionally running **unsafeCounter** across multiple threads may occasionally pass under favorable thread scheduling. Thus, never rely on "a single passing stress test" as sole proof; combine shared-data analysis, atomic operations, and targeted concurrency tests.

### 13.3. Testing Bean Lifecycle in a Spring Context

When verifying real singleton behavior and FunctionCatalog, use **Spring Boot Test**:

~~~java
package example.function;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertSame;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.cloud.function.context.FunctionCatalog;

@SpringBootTest
class SingletonRegistrationTest {

    @Autowired
    ApplicationContext context;

    @Autowired
    FunctionCatalog catalog;

    @Test
    void oneContextReusesBeanAndCatalogCanFindIt() {
        Object first = context.getBean("calculatePrice");
        Object second = context.getBean("calculatePrice");

        assertSame(first, second);
        assertNotNull(catalog.lookup("calculatePrice"));
    }
}
~~~

Note that **catalog.lookup(...)** may return a wrapper supporting conversion and composition; do not use **assertSame** between the catalog lookup result and the raw bean to prove singleton scope. Checking **assertSame** across two lookups of **the bean from the same ApplicationContext** directly verifies singleton scope in the example.

These tests require appropriate JUnit 5/Spring Boot Test and Spring Cloud Function dependencies. No HTTP server or broker is needed for unit tests; add integration tests against the actual adapters in use when verifying concurrency, conversion, and binder settings.

## 14. Common Pitfalls and Diagnostics

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Two requests receive the same sequence number | **counter++** on shared variable, lost update | **AtomicLong** if JVM-local only; durable ID if system-wide |
| Function returns data from a previous request | Stored **lastRequest** in a singleton field | Use local variables or immutable input/output |
| Supplier always returns an old timestamp | Value computed at bean creation time | Move time lookup into **get()** or a properly scoped publisher |
| Single-threaded test passes but production fails | Race only manifests under real concurrency | Audit shared state, add concurrency tests, review adapter config |
| Changed to prototype scope but state is still shared | Prototype injected once into a singleton | Use **ObjectProvider** per call if a fresh instance is truly needed |
| Data vanishes after restart | Stored business state in singleton/in-memory map | Use durable storage |
| Multiple replicas emit duplicate IDs | Each instance maintains its own counter | Database sequence or suitable distributed ID generator |
| Retries cause Consumer to write duplicates | Thread-safe but not idempotent | Unique constraint on eventId and retry policy |
| Reactive pipeline suffers data races | Mutable collection outside subscription | Scope state per subscription or synchronize explicitly |
| ThreadLocal values missing/wrong across schedulers | Context not propagated over async boundaries | Pass metadata explicitly or use supported context propagation |
| Modifying Message headers throws exception | Header map may be read-only | Build a new Message via MessageBuilder |
| Headers vanish after composition | No propagation configured | Define header contract and test conversion |

A quick check during code reviews is to ask: **what data outlives a single apply/get/accept call, can multiple calls access it simultaneously, and what mechanism protects its invariants?**

## 15. Practice Exercises

**Exercise 1 — Identifying a race condition.** Read the **unsafeCounter** bean in Section 3 and trace an interleaving of two threads that loses an increment. Explain why changing **long[]** to a **volatile long** field while keeping **counter++** is insufficient.

**Exercise 2 — Stateless Function.** Write a **Function<ShippingRequest, ShippingFee>** that calculates fees from weight and an immutable rate table. Register a singleton bean and test the same function handling multiple distinct requests without keeping a "latest request" field.

**Exercise 3 — Choosing synchronization tools.** An application needs to (a) count calls inside one JVM, (b) hold read-only product config, and (c) generate unique order IDs across multiple replicas. Choose the appropriate tool for each and explain why **AtomicLong** does not solve requirement (c).

**Exercise 4 — Prototype injection.** Create a prototype-scoped **Worker** class with an internal counter. Compare a **@Bean Function<Input, Output>** injecting Worker directly against a Function injecting **ObjectProvider<Worker>**, and explain when Spring instantiates Worker.

**Exercise 5 — Consumer and event redelivery.** A **Consumer<OrderPaid>** writes to a database and later receives the same **eventId** after a failed ack. Design the idempotency key, unique constraint, and retry handling; explain why synchronizing around accept in one instance does not prevent duplicate writes across multiple instances.

**Exercise 6 — Reactive context.** Build a **Supplier<Flux<Instant>>** returning timestamps per subscription using **Flux.defer**. Contrast it with a Supplier capturing **Instant** at bean creation time, then explain the role of schedulers and the risk of using ThreadLocal for correlation IDs.

**Exercise 7 — Integration testing.** Using **FunctionCatalog.lookup("calculatePrice")**, test HTTP POST via the web adapter and verify two requests are processed independently. Then describe what extra tests are needed when switching to Spring Cloud Stream and changing concurrency/binder configuration.

### Key Takeaways

- A **Spring singleton** is one bean instance managed within **a single application context**; it can serve many invocations concurrently and does not automatically guarantee thread safety.
- **Stateless + immutable input/output + read-only dependencies** is usually the simplest design for reusable business functions.
- When state must be shared, choose appropriate atomic operations or synchronization; **AtomicLong**, **synchronized**, and concurrent collections protect only within the scope they were designed for.
- **Thread safety differs from idempotency and durability**. Multiple replicas, restarts, and retries require storage/transactions/business keys at the proper layer.
- **Scopes**, **reactive subscriptions**, and **HTTP/Stream/serverless adapters** affect when objects are created and invoked; verify real behavior rather than assuming the framework isolates each request automatically.
- Test **isolated logic**, **concurrent access**, and **adapter integration** to catch issues at the right boundaries.
