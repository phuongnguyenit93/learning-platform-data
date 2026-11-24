# Singleton Beans Are Used by Multiple Threads and Do Not Become Thread-Safe Automatically

## 1. The Problem to Understand

In the Spring Framework, a bean with **singleton** scope is normally created once per bean definition within a Spring IoC container. When multiple components inject that bean, they normally receive the **same reference** to the object. If multiple threads invoke methods on the bean at the same time, they can concurrently read or modify its fields.

**Singleton only describes the instance count and lifecycle managed by the container; singleton is not a guarantee of thread-safety.** Spring does not automatically lock every call, turn fields into atomics, or serialize every request entering a singleton bean. Thread-safety is the responsibility of design and appropriate synchronization mechanisms.

Common examples:

- Two HTTP requests entering the same singleton **@RestController** or **@Service** in a Spring MVC application can run on two different request threads.
- A method of a singleton bean is called from an executor via **@Async**, while simultaneously being called by another request.
- A singleton service is invoked by **@Scheduled**, a listener, or multiple worker threads.
- Multiple parts of the code inject the same singleton and concurrently act on an internal cache, counter, or mutable configuration inside the bean.

Not every Spring application has multiple active threads, and not every method on a singleton is invoked concurrently. However, **the default singleton scope does not prevent concurrency** when the execution environment introduces it.

> Design rule: prefer singleton services that **do not hold per-request mutable state**. When shared mutable state is unavoidable, you must define the invariants, required consistency level, synchronization boundaries, and how to verify them.

## 2. What Does Spring's Singleton Actually Mean?

### 2.1. One Instance Shared Within the Container Scope

The default bean scope in Spring is singleton. Fetching the **same bean definition** twice from the same ApplicationContext will point to the same object, for example:

~~~java
// Illustration inside an application that already has an ApplicationContext.
Object first = context.getBean("orderService");
Object second = context.getBean("orderService");
System.out.println(first == second); // true
~~~

It is important to distinguish:

| Statement | True or false? | Reason |
| --- | --- | --- |
| A singleton bean can be injected into multiple consumers | True | Consumers share the same target instance provided by the container |
| A Spring singleton is a single object across the entire JVM | False | Singleton scope is managed per IoC container and per bean definition; multiple contexts/definitions can create different instances |
| Every instance of the same class is a single singleton bean | False | Two different bean definitions can create two objects of the same class |
| Singleton automatically locks method calls | False | Scope has no thread synchronization functionality |
| Without mutable shared state, a singleton is usually easy to use concurrently | True, conditionally | You still need to inspect dependencies and any shared mutable objects |
| Because a bean is a singleton, it is always called by multiple threads | False | Depends on runtime behavior and request/task execution paths |

Note about **proxies**: in Spring AOP, a caller may hold a proxy instead of the target. Even though the proxy intercepts the call, you must not assume the target automatically becomes thread-safe. Mechanisms such as **@Transactional**, **@Async**, or **@Cacheable** are not a global lock protecting all fields of the bean either.

### 2.2. Distinguishing Per-Call State from Shared State

Observe the following two methods:

~~~java
@Service
public class InvoiceService {
    // This part does not store per-call data in a field.
    public long calculate(long quantity, long unitPrice) {
        long subtotal = quantity * unitPrice;
        return subtotal;
    }
}
~~~

This is an illustrative snippet (without imports and standalone Spring configuration). The variable **subtotal** is a local variable; each invocation has its own variable. If the parameters are primitives or immutable data and there are no mutable dependencies used unsafely, concurrent calls do not contend on any field in this example.

Conversely:

~~~java
@Service
public class OrderService {
    private String currentOrderId;

    public void process(String orderId) {
        currentOrderId = orderId;
        // Subsequent steps read currentOrderId.
    }
}
~~~

Two requests A and B share **currentOrderId**. A might write "A", B writes "B", and then A reads back "B". The program has mixed up data between requests even though each method invocation had its own parameter.

Data that should normally **not** be kept in a singleton's fields: current request id, current user, per-request authentication info, form data being processed, temporary calculation variables, an improperly obtained request-scoped object, or a reusable mutable buffer without protection.

Keep request data in parameters, local variables, return values, or move it to a storage mechanism with the proper scope and lifecycle. A local variable only protects the **local reference**: if it points to a mutable object that other threads also share, a race condition still exists on that object.

## 3. Why Does Shared Mutable State Cause Race Conditions?

### 3.1. Lost Update on a Counter Increment

Suppose a singleton has a field:

~~~java
private int count = 0;

public int next() {
    return ++count;
}
~~~

**++count** is not a single atomic operation. Logically, it consists of reading the current value, computing the new value, and writing it back. Two threads can interleave:

| Step | Thread A | Thread B | count stored in bean |
| --- | --- | --- | --- |
| 1 | Reads 0 | | 0 |
| 2 | | Reads 0 | 0 |
| 3 | Computes 1, writes 1 | | 1 |
| 4 | | Computes 1, writes 1 | 1 |
| 5 | Finishes | Finishes | **1 instead of 2** |

This is a **lost update**. Concurrently, you can also encounter **stale reads** (reading an outdated value), **check-then-act races** (checking a condition and then acting after the condition has changed), and **invariant violations** when an operation needs to update multiple fields consistently.

### 3.2. Visibility, Atomicity, and Ordering Are Three Separate Concepts

- **Visibility:** when thread A makes an update, is thread B guaranteed to see that update in time? The Java Memory Model and *happens-before* relationships govern this.
- **Atomicity:** can a compound multi-step operation be interleaved by other threads in the middle?
- **Ordering:** the compiler, CPU, and runtime may reorder operations within the bounds permitted by the Java Memory Model; synchronization mechanisms establish crucial ordering constraints.

Marking a field **volatile** strengthens visibility and ordering guarantees for corresponding accesses, but **does not turn count++ into an atomic increment**. Two threads can still read the same old number and both write the new number.

Similarly, declaring an object **final** fixes the field reference after initialization, but **does not automatically make the contents of the referenced object immutable**. For example, a final List does not mean every add/remove call is thread-safe.

## 4. Runnable Example: The Same Singleton Called by Two Threads

The example below uses **Java 17+, Spring Framework 6.1.14, and Gradle 8.5+**. No Spring Boot or web server is needed; an AnnotationConfigApplicationContext creates two singleton beans, and then an executor with two workers calls the same instance. **CyclicBarrier** is placed in the buggy example solely to *force both threads to read the old value before writing*, thereby reproducing a lost update in a controlled manner. In real business code, never add a barrier to increment a counter.

Project structure:

~~~text
singleton-race-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/SingletonRaceDemo.java
~~~

**settings.gradle**:

~~~groovy
rootProject.name = 'singleton-race-demo'
~~~

**build.gradle**:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.14'
}

application {
    mainClass = 'demo.SingletonRaceDemo'
}
~~~

**src/main/java/demo/SingletonRaceDemo.java** (a complete Java file):

~~~java
package demo;

import java.util.concurrent.BrokenBarrierException;
import java.util.concurrent.Callable;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class SingletonRaceDemo {

    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(BeanConfig.class)) {

            UnsafeCounter unsafe = context.getBean(UnsafeCounter.class);
            SafeCounter safe = context.getBean(SafeCounter.class);

            System.out.println("same bean instance = " +
                    (unsafe == context.getBean(UnsafeCounter.class)));

            ExecutorService pool = Executors.newFixedThreadPool(2);
            try {
                // Both tasks must read the same initial value before writing.
                CyclicBarrier bothRead = new CyclicBarrier(2);
                Callable<Void> unsafeCall = () -> {
                    unsafe.incrementForDemo(bothRead);
                    return null;
                };

                Future<Void> first = pool.submit(unsafeCall);
                Future<Void> second = pool.submit(unsafeCall);
                first.get();
                second.get();

                System.out.println("unsafe updates = " + unsafe.value());

                // AtomicInteger performs an atomic increment.
                Callable<Void> safeCall = () -> {
                    safe.increment();
                    return null;
                };

                Future<Void> third = pool.submit(safeCall);
                Future<Void> fourth = pool.submit(safeCall);
                third.get();
                fourth.get();

                System.out.println("atomic updates = " + safe.value());
            } finally {
                pool.shutdown();
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class BeanConfig {
        @Bean
        UnsafeCounter unsafeCounter() {
            return new UnsafeCounter();
        }

        @Bean
        SafeCounter safeCounter() {
            return new SafeCounter();
        }
    }

    static final class UnsafeCounter {
        // volatile does NOT make read + increment + write atomic.
        private volatile int count;

        void incrementForDemo(CyclicBarrier bothRead)
                throws InterruptedException, BrokenBarrierException {
            int before = count;
            bothRead.await(); // Used solely to demonstrate the race.
            count = before + 1;
        }

        int value() {
            return count;
        }
    }

    static final class SafeCounter {
        private final AtomicInteger count = new AtomicInteger();

        void increment() {
            count.incrementAndGet();
        }

        int value() {
            return count.get();
        }
    }
}
~~~

In the **singleton-race-demo** directory, run:

~~~bash
gradle run
~~~

If the project has a Gradle Wrapper, replace the command with **./gradlew run** (Linux/macOS) or **gradlew.bat run** (Windows). The three lines printed by the program itself will be:

~~~text
same bean instance = true
unsafe updates = 1
atomic updates = 2
~~~

Gradle may print additional build messages and logging depending on the environment. Why are the three values above predictable? **@Bean** uses singleton scope by default; two calls to getBean return the same bean. In UnsafeCounter, the barrier forces both tasks to hold a copy of **0**, and then both write **1**. In SafeCounter, AtomicInteger.incrementAndGet() applies two atomic increments, so the final result is **2**. Waiting on Future.get() ensures main only reads the results after the tasks have completed.

The example is not meant to measure throughput or prove an algorithm can always reproduce a race in production. It intentionally controls the interleaving timing to show that **singleton scope does not prevent lost updates**.

## 5. How to Design Safe Singletons in Practice

### 5.1. Prefer Stateless Services

It is best for a method to accept all necessary inputs, compute, and return the result; fields should only hold injected dependencies or fixed configuration. Illustrative example:

~~~java
@Service
public class PriceService {
    public long total(long unitPrice, int quantity) {
        return Math.multiplyExact(unitPrice, quantity);
    }
}
~~~

Per-request data flows through parameters and return values. If there are injected dependencies, you must still consider the thread-safety of those dependencies; a stateless singleton calling a shared mutable object without synchronization **can still be unsafe**. Do not move state from one field into a static field or a shared cache just to look stateless.

### 5.2. Use Immutable State When Sharing Configuration

Immutable objects (whose contents cannot change after construction) are ideal for sharing, such as String, records containing immutable components, or a defensively copied read-only list. Ensure nested objects cannot be mutated elsewhere either if invariants depend on them.

~~~java
public record FeePolicy(int percent, String currency) { }

// The same immutable FeePolicy can be safely read by multiple requests concurrently.
~~~

If the entire configuration set needs to be swapped at runtime, one approach is to build a new **immutable snapshot** and swap the reference using AtomicReference or volatile, rather than updating multiple fields piecemeal. Be sure to distinguish atomic replacement of a single reference from atomicity across multiple independent resources.

### 5.3. Use Atomics and Concurrent Data Structures Appropriately

A shared counter can be declared as:

~~~java
private final AtomicLong requestCount = new AtomicLong();

public long nextNumber() {
    return requestCount.incrementAndGet();
}
~~~

AtomicLong is suitable for incrementing, decrementing, and compare-and-set on **a single value** within a JVM. For high-frequency write statistics, LongAdder can reduce contention, but **sum() is not an atomic snapshot** while updates are still ongoing. Do not use it for sequence numbers that must be unique and monotonically incremented per call.

For a map updated by multiple threads, consider **ConcurrentHashMap** and operations such as compute, merge, and putIfAbsent when a key needs to be updated atomically:

~~~java
private final ConcurrentHashMap<String, Long> counts =
        new ConcurrentHashMap<>();

public void record(String type) {
    counts.merge(type, 1L, Long::sum);
}
~~~

The snippet above is an illustration inside a class that imports java.util.concurrent.ConcurrentHashMap. **ConcurrentHashMap** protects the specified map operations; it does not make a mutable object stored as a value thread-safe, nor does it turn multiple operations across multiple keys into a single transaction.

### 5.4. Use synchronized or Lock When Multi-Step Invariants Exist

When you need to check a condition and update multiple fields as a single logical unit, protect the **entire operation block** with the same lock:

~~~java
public class BoundedInventory {
    private int available = 3;

    public synchronized boolean reserve() {
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
~~~

If every read/write path to **available** obeys the same monitor, the invariant cannot be violated by two threads competing within a single instance. You can use ReentrantLock with try/finally and other lock options when truly needed. Locks help guarantee correctness, but carry contention cost and can cause deadlocks if multiple resources are locked inconsistently. Avoid holding locks while performing I/O, network calls, or waiting on other tasks unless carefully evaluated.

**@Transactional** is a transaction mechanism, not a replacement for a monitor lock on Java fields. Conversely, **synchronized** only locks within one JVM/object and does not provide database transactions or data coordination across multiple application replicas.

### 5.5. Data Shared Across Multiple Application Instances Must Live at the Proper Boundary

When running multiple pods/instances, each ApplicationContext has its own singletons. An AtomicInteger or synchronized in one instance **does not keep a cluster-wide counter** consistent. For examples such as inventory quantities, business sequence numbers, quotas, or duplicate-processing prevention, use a consistent mechanism on the true data source: transactions and conditional updates, database optimistic/pessimistic locking, unique constraints, atomic operations of an appropriate data store, or a coordination service designed for that purpose.

Do not use static fields or a pure-Java Singleton pattern as a "distributed lock": they do not cross process boundaries either.

## 6. Do Other Scopes Solve Thread-Safety?

| Scope/mechanism | Changes lifecycle or allocation | Guarantees thread-safety automatically? |
| --- | --- | --- |
| **singleton** | One bean instance per bean definition in the container | **No** |
| **prototype** | Creates a new instance each time the container receives a request for the bean | **No**; the same prototype can still be shared across multiple threads |
| **request** | One bean for the active HTTP request scope (in supported web contexts) | **No**; logic may have concurrent/asynchronous access within the request |
| **session** | One bean per HTTP session | **No**; two requests in the same session can access it concurrently |
| **ObjectProvider<T>** | Allows requesting a bean on demand, e.g., obtaining a prototype each time | Only manages instance retrieval; does not synchronize state automatically |

An important trap: **injecting a prototype directly into a singleton's constructor does not mean each method call on the singleton automatically gets a new prototype**. The dependency is normally resolved when constructing the singleton and the same reference is reused thereafter; if you need a fresh instance every time, use ObjectProvider, a lookup method, or a scoped proxy as appropriate for the context.

Scope is also not a substitute for data design: even a request-scoped bean can still write to a shared static map, call a mutable singleton, or share an object across multiple worker threads.

## 7. Frequently Confused Interactions in Spring Concurrency

**Spring MVC:** in the traditional Servlet model, concurrent requests can be handled by different worker threads. Singleton controllers and services are shared objects. The fact that a controller does not `new` a service on every request is a property of DI/scope, not a serialization guarantee.

**@Async:** routing a valid call through a Spring proxy to an executor can introduce additional threads using the same bean or dependencies. If an @Async method reads/writes mutable singleton fields, switching to async **increases contention scenarios** rather than fixing a race. If data from a request is needed, pass the necessary data explicitly or manage context propagation properly.

**@Scheduled:** the scheduler triggers a method over time; the same singleton can also be called from elsewhere or from multiple registrations. Do not assume each scheduled bean has "its own thread" or that every call is locked. Overlap depends on the scheduler, how it is registered, execution duration, and whether @Async is separated.

**@Transactional:** a transaction is typically bound to the execution thread/transaction manager mechanism and storage data; it does not protect an int variable in a singleton from two threads modifying it concurrently. If two transactions modify the same record, you need a data-layer concurrency control strategy.

**ThreadLocal:** holds data per thread, not per Spring singleton or automatically per HTTP request. With thread pools, threads can be reused; you must properly manage set/remove and context propagation. ThreadLocal does not solve races on shared fields, does not replace passing parameters, and is not automatically safe when switching threads with @Async.

**Reactive/WebFlux:** do not assume processing always stays on a fixed thread; callbacks can run on different schedulers. A singleton with shared mutable state still requires proper synchronization, while blocking locks/I/O on an event-loop can severely impact responsiveness. Stateless and non-blocking designs are generally preferred.

## 8. Common Pitfalls and Fixes

| Symptom | Cause worth checking | Resolution |
| --- | --- | --- |
| Counter occasionally increments too little | **count++** in singleton hits lost updates | AtomicLong/AtomicInteger or a lock covering the entire update |
| User A's data appears in user B's processing | Storing currentUser/currentRequest in a singleton field | Pass request data via parameters or use a scope/context with the right lifecycle |
| HashMap/ArrayList errors or missing elements under concurrent access | Shared mutable collection without protection | Choose a concurrent collection and proper atomic operations; or lock |
| Wrong totals even though the field uses volatile | Volatile does not make compound operations atomic | Switch to Atomic*, a lock, or an algorithm without shared updates |
| Created prototype beans but still seeing races | Prototype injected once into singleton or reference is shared | Check when instances are fetched, ownership, and sharing limits |
| Synchronization is right in one instance but multiple pods still lose updates | Locks/atomics only protect one JVM's memory | Move invariants to transactions, unique constraints, or atomic operations in a shared store |
| Occasionally reading a patchwork configuration | Writing multiple fields individually while other threads read | Use an immutable snapshot swapped atomically or protect multiple fields under the same lock |

Another easily overlooked bug is calling a *non*-thread-safe dependency from a singleton. For example, sharing a mutable SimpleDateFormat or a StringBuilder buffer across requests without protection. Not every dependency needs locking: first check its thread-safety documentation and actual usage.

## 9. How to Audit a Singleton Before Putting It into a Concurrent Environment

1. **Identify the instance and callers.** Which context does the bean belong to? How many places inject it? Are there requests, schedulers, listeners, async tasks, or callbacks calling it concurrently?
2. **List shared state.** Mutable fields of the bean itself, mutable objects reached through dependencies, static state, caches, collections, reloadable configuration variables.
3. **Analyze operations.** Read-only? Single value needing an atomic update? An invariant spanning multiple fields? Is there a publication/happens-before mechanism between writer and reader?
4. **Choose an appropriate strategy.** Prefer stateless/immutable first, then Atomic* or concurrent collections; when multi-step invariants exist, use the same lock or the corresponding data-layer transaction.
5. **Verify with real concurrent scenarios.** Use CountDownLatch, CyclicBarrier, or concurrent calls to force interleavings and assert invariants; add stress tests if needed. A test passing once **does not prove** there is no race; running random tests many times does not replace analyzing memory and locking either.
6. **Observe production.** Measure error rates, retry counts, queues, latency, and violated invariants. Distinguish JVM concurrency bugs from data conflicts in the database or across multiple instances.

When a method only returns a result computed from independent inputs without keeping per-request state, that is usually the easiest singleton case to use safely. When it must store shared state, make explicit **who owns the data, which operations are atomic, and whether the protection boundary covers all callers**.

## 10. Self-Check Questions

1. Two different controllers inject the same singleton service. Do they use two independent service objects? **No**, if both resolve the same bean definition in the same container.
2. Does marking **volatile int count** and calling **count++** from two threads guarantee the result increments twice? **No**, because read-modify-write is not atomic.
3. Does replacing singleton with prototype automatically fix the bug if the same object is shared across multiple workers? **No**. Scope controls how the container creates/allocates beans, and does not automatically lock operations.
4. A completely stateless singleton calls an unprotected shared mutable HashMap: is it guaranteed to be thread-safe? **No**. You must inspect dependencies and shared objects too.
5. Does adding **@Transactional** around a method updating a field prevent two threads from modifying that field at the same time? **No**. A transaction is not a monitor lock for Java memory.
6. Does AtomicInteger in a single instance guarantee a business counter increments accurately across three pods? **No**. Consistency rules must be placed in a shared storage/coordination system.

**Remember:** singleton governs **instance sharing**, whereas thread-safety governs **whether sharing remains correct when operations interleave**. Spring provides the container, proxies, and concurrency integrations, but designing mutable state, atomicity, and invariants still belongs to application code.

Official references:
- [Spring Framework — Bean Scopes, Singleton Scope](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html#beans-factory-scopes-singleton)
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Java SE — AtomicInteger](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html)
