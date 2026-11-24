# Distinguishing Bean Scope from Synchronization Mechanisms in the Spring Framework

## Objectives

After this lesson, you will be able to distinguish **bean scope** (the lifetime and *instance* sharing managed by Spring) from **synchronization mechanisms** (how state is protected when multiple threads access it simultaneously). You will also know why `singleton` does not mean "thread-safe," why `prototype` does not guarantee eliminating race conditions, why `request` and `session` are not locks, and how to choose the right design for stateful beans.

The context is the Spring Framework running in a multithreaded application: HTTP requests, `@Async` tasks, schedulers, or executors can all invoke a bean. You do not need multithreading in every program to understand scope, yet whenever multiple threads touch mutable data, thread-safety must be evaluated separately.

## 1. Two Different Questions

**Bean scope answers:** "Which *bean instance* does Spring create, store, and supply for this request, within what scope and lifecycle?"

**Synchronization answers:** "If multiple threads read/write *the same mutable state*, which operations must have atomicity, ordering, and visibility across threads?"

Picture it this way:

- **Scope** decides who gets a key to enter the same room (the same object) and when the room is created/destroyed.
- **Synchronization** decides how people inside the room share a notebook without losing lines, misreading, or overwriting one another.

These two dimensions are independent. A singleton can be completely thread-safe if it holds no mutable state or protects its state properly. A prototype can still be non-thread-safe if its reference is handed to two workers or it modifies a `static` variable, collection, cache, or shared resource.

```text
Spring container / scope          Threads and state access
        |                                       |
        | fetch or inject instance              | call method on instance
        v                                       v
  Bean instance ------------------------> field / object / storage
        |                                       |
 governs instance sharing                requires analyzing races, visibility,
 and lifecycle                            atomicity, invariants
```

**Do not infer** from `@Scope`, `@Component`, `@Service`, `@Async`, or `@Transactional` that the framework automatically places a lock around your entire business method. Each annotation has its own contract.

## 2. Common Scopes and Sharing Levels

| Scope | When does Spring supply an instance? | Concurrency considerations |
| --- | --- | --- |
| `singleton` (default) | One object per bean definition in **one Spring IoC container**. Lookups of the same bean definition return the same instance. | Multiple threads can call concurrently and share instance fields; requires safe design if state is mutable. |
| `prototype` | Creates a new object **each time the container is asked to supply the bean**. | Does not automatically create one instance per method call or thread; a prototype object can still be shared after allocation. |
| `request` | One object per HTTP request in a web-aware context. | Different requests get isolated bean state, yet the same request can still have multithreaded access; watch request context when switching threads. |
| `session` | One object per HTTP session. | Multiple parallel requests from the same session can share the bean; session scope **does not** serialize operations. |
| `application` | One object per `ServletContext`. | Can be shared by many requests/beans; `ServletContext` is not a locking boundary. |
| `websocket` | Bound to a WebSocket session in supported environments. | Multiple callbacks/tasks tied to the same session still need proper concurrency design. |

Spring also supports **custom scopes**. `SimpleThreadScope` exists out of the box yet **is not registered by default**: it binds instances per thread if you register it yourself. In a thread pool, one worker can run many tasks for many users, so "one bean per thread" **is not equivalent to** "one bean per request." Avoid using thread scope as a general cure for race conditions.

Boundary notes:

1. Spring `singleton` is **per container, per bean definition**, not one unique object across the entire JVM, all application contexts, or an entire server cluster. Two bean definitions of the same class can still create two distinct singletons.
2. Web scopes only operate when an appropriate web context exists; a plain `AnnotationConfigApplicationContext` does not automatically provide request/session scopes.
3. Scope only governs **container-managed beans**. Manually created `new SomeClass()` outside Spring and `static` fields do not change their lifecycle just because the class carries an annotation.
4. When multiple instances share a database, Redis, files, a shared cache, or other resources, separating bean instances does not isolate the underlying resource.

## 3. Identifying Whether State Lives Inside or Outside the Bean

A local variable belongs to each invocation, yet **the object pointed to by a local variable may still be shared**; conversely, a singleton's field is normally seen by many callers at once. Before picking a scope or lock, trace the actual references:

| State location | Relationship to scope | Questions to answer |
| --- | --- | --- |
| Parameters, local variables | Private variable slot per invocation | Does the reference point to a shared mutable List/DTO? |
| Singleton instance field | Field belonging to a shared bean instance | Is the field modified after initialization; do all readers/writers coordinate? |
| Field of prototype/request/session | Depends on how the bean is obtained and references are held | Can the same target be accessed by multiple threads or retained past its lifecycle? |
| Static, cache, DB, other dependencies | Not isolated merely by changing the caller bean's scope | Who owns the shared resource and what is its synchronization mechanism? |

For example, `final List<String> items` does not make the list immutable; `AtomicInteger` protects incrementing one value in one JVM, yet does not protect a database or a multi-step workflow.

## 4. How Does Scope Differ from Synchronization?

Three key concurrency properties:

- **Atomicity:** an operation or group of operations must be observed as a valid unit. For example, "read stock, check sufficiency, deduct stock" is a multi-step invariant.
- **Visibility:** thread A's write must be observed by thread B under an appropriate happens-before relationship; otherwise B may read stale values.
- **Ordering:** the compiler, CPU, and runtime can optimize/reorder operations under the Java Memory Model when no synchronization relationship exists; happens-before relationships must be established whenever logic depends on order.

| Tool | What does it solve well? | What does it not solve automatically? |
| --- | --- | --- |
| Immutable data, stateless design | Eliminates most contention on the service's own state. | Races in mutable dependencies or external storage. |
| Local variables, thread-confined objects | Reduces state sharing because each call keeps its own state. | Objects handed off to other threads or global state can still contend. |
| `synchronized` / `ReentrantLock` | Protects critical sections, establishes happens-before on the same lock, guards multi-step invariants. | Does not synchronize with code using a different lock or bypassing the protocol; does not lock across JVMs. |
| `AtomicInteger`, `AtomicLong`, CAS | Single atomic operations like incrementing a counter. | Complex invariants spanning multiple fields or statements without coordinated design. |
| `volatile` | Visibility and ordering for suitable fields, such as a stop flag. | Turning `count++`, "check-then-update," or multi-field invariants atomic. |
| `ConcurrentHashMap`, concurrent collections | Concurrent operations per the collection contract; certain atomic operations like `computeIfAbsent` per spec. | Whole workflows of multiple independent operations when end-to-end atomicity is needed. |
| Database transactions / locks / optimistic versioning | Consistency at the data layer with proper transactions. | Automatic thread-safety for in-JVM instance fields. |

With `synchronized`, what matters is that **threads synchronize on *the exact same lock*** and all related accesses obey that rule:

```java
private int count;

public synchronized int increment() {
    return ++count;
}

public synchronized int current() {
    return count;
}
```

Both methods use the monitor of **the same instance**. If there are two separate objects, each has its own lock; they do not protect an external shared resource. If you need to lock the same database record across multiple application instances, you must use storage/transaction/concurrency-control strategies, not merely `synchronized` on a bean.

**Never lock an entire service out of habit.** Serializing all calls can tank throughput, raise latency, and create deadlock risk. Lock only the invariant that needs protection, keep critical sections short, and prefer immutable/atomic data where appropriate.

## 5. Runnable Example: Bean Scope and a Race Condition

The following example uses **Java 17+** and Spring Framework `spring-context` **6.2.0**. It demonstrates four things:

1. Fetching a singleton twice for the same bean definition yields the same object.
2. Each prototype request directly or via `ObjectProvider` creates a distinct object.
3. A prototype **injected once into a singleton** does not refresh on every singleton call.
4. Two threads calling the same singleton can lose an increment; using `AtomicInteger` preserves both increments.

To make the race demonstration **deterministic**, `CyclicBarrier` is used solely in the intentionally buggy class to force both threads to read `0` before writing. This is a bug-reproduction device, **not a bug-fixing mechanism**.

Create the structure:

```text
scope-sync-demo/
├── pom.xml
└── src/main/java/example/ScopeSyncDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>scope-sync-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
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
                <version>3.3.0</version>
                <configuration>
                    <mainClass>example.ScopeSyncDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/example/ScopeSyncDemo.java`:

```java
package example;

import java.util.concurrent.BrokenBarrierException;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Scope;

public class ScopeSyncDemo {

    // Intentionally not thread-safe to demonstrate lost updates.
    public static class UnsafeCounter {
        private int value;
        private final CyclicBarrier bothHaveRead = new CyclicBarrier(2);

        public void incrementTogether() {
            int snapshot = value; // Both threads must read before writing.
            try {
                bothHaveRead.await(10, TimeUnit.SECONDS);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("Interrupted", ex);
            } catch (BrokenBarrierException | TimeoutException ex) {
                throw new IllegalStateException("Barrier failed", ex);
            }
            value = snapshot + 1;
        }

        public int current() {
            return value;
        }
    }

    // Each incrementAndGet is an atomic operation.
    public static class SafeCounter {
        private final AtomicInteger value = new AtomicInteger();

        public int increment() {
            return value.incrementAndGet();
        }

        public int current() {
            return value.get();
        }
    }

    public static class ScratchPad {
        private int notes;

        public void addNote() {
            notes++;
        }

        public int notes() {
            return notes;
        }
    }

    // Singleton holds one prototype injected at initialization,
    // while also having a provider to request a new prototype.
    public static class Client {
        private final ScratchPad injectedOnce;
        private final ObjectProvider<ScratchPad> provider;

        public Client(ScratchPad injectedOnce,
                      ObjectProvider<ScratchPad> provider) {
            this.injectedOnce = injectedOnce;
            this.provider = provider;
        }

        public ScratchPad injected() {
            return injectedOnce;
        }

        public ScratchPad newPad() {
            return provider.getObject();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public UnsafeCounter unsafeCounter() {
            return new UnsafeCounter(); // singleton by default
        }

        @Bean
        public SafeCounter safeCounter() {
            return new SafeCounter(); // also a singleton
        }

        @Bean
        @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
        public ScratchPad scratchPad() {
            return new ScratchPad();
        }

        @Bean
        public Client client(ScratchPad pad,
                             ObjectProvider<ScratchPad> provider) {
            return new Client(pad, provider);
        }
    }

    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            UnsafeCounter unsafe = context.getBean(UnsafeCounter.class);
            SafeCounter safe = context.getBean(SafeCounter.class);
            Client client = context.getBean(Client.class);

            System.out.println("singletonSame="
                + (unsafe == context.getBean(UnsafeCounter.class)));

            ScratchPad direct1 = context.getBean(ScratchPad.class);
            ScratchPad direct2 = context.getBean(ScratchPad.class);
            System.out.println("prototypeDirectDistinct="
                + (direct1 != direct2));

            System.out.println("prototypeInjectedSame="
                + (client.injected() == client.injected()));

            System.out.println("prototypeViaProviderDistinct="
                + (client.newPad() != client.newPad()));

            ExecutorService workers = Executors.newFixedThreadPool(2);
            try {
                Future<?> u1 = workers.submit(
                    () -> { unsafe.incrementTogether(); });
                Future<?> u2 = workers.submit(
                    () -> { unsafe.incrementTogether(); });
                u1.get(); // wait and observe the bug before printing results
                u2.get();

                Future<?> s1 = workers.submit(
                    () -> { safe.increment(); });
                Future<?> s2 = workers.submit(
                    () -> { safe.increment(); });
                s1.get();
                s2.get();
            } finally {
                workers.shutdownNow();
            }

            System.out.println("unsafeAfterTwoCalls=" + unsafe.current());
            System.out.println("safeAfterTwoCalls=" + safe.current());
        }
    }
}
```

Run in the `scope-sync-demo` directory (with JDK 17+ and Maven installed):

```bash
mvn -q compile exec:java
```

Lines printed by the program, in order:

```text
singletonSame=true
prototypeDirectDistinct=true
prototypeInjectedSame=true
prototypeViaProviderDistinct=true
unsafeAfterTwoCalls=1
safeAfterTwoCalls=2
```

Analysis:

- `unsafe` is a singleton, and both `Future`s call **the same instance**; both capture snapshot `0`, wait for each other, and then write `1`. Two increments should have produced `2`. `Future.get()` lets `main` await both tasks and inspect the outcome after completion; it does not fix the lost increment.
- `safe` is also a **singleton**, yet uses `AtomicInteger.incrementAndGet()`: both increments are counted, yielding `2`. **Same scope, different thread-safety**.
- `direct1 != direct2` confirms two direct prototype lookups create two objects. `client.injected()` keeps returning one fixed object because the singleton `Client` was constructed with that dependency beforehand.
- `client.newPad()` calls `ObjectProvider.getObject()` each time, producing a new prototype. Having multiple instances only reduces state-sharing risk when you genuinely avoid handing those instances to multiple threads concurrently.
- `ScratchPad.addNote()` has no synchronization; it is only safe if each instance is strictly confined to one thread/unit of work or properly protected.

In real production code, **never** put a `CyclicBarrier` inside a counter like this; it is purely a device to stage a lost update in the lesson. Use concurrency testing tools or stress tests to probe real behavior. Never test by assuming "running 1,000 times will surely catch any race": bugs depend on execution scheduling.

## 6. Why Is Prototype Not the Default Fix for Races?

Calling `getBean(PrototypeBean.class)` creates a new instance, yet carries no guarantee that *each thread* gets a different bean. Consider these cases:

**Case A — prototype injected once into a singleton:**

```java
@Service
class CheckoutService {
    private final MutableBasket basket;

    CheckoutService(MutableBasket basket) {
        this.basket = basket; // injected only once into the singleton
    }
}
```

Suppose `MutableBasket` is prototype-scoped: once `CheckoutService` is initialized, every request calling that singleton can access **the exact same injected basket**. This is a partial illustrative example requiring bean/configuration declarations to run. If you want a new instance per processing unit, use `ObjectProvider<MutableBasket>`, method injection, or create an appropriate local object.

**Case B — prototype shared via reference:** a prototype object passed into two tasks of an executor is still **one object touched by two threads**. Scope annotations do not stop Java from sharing references.

**Case C — state lives outside the prototype:** two prototypes write to a shared `static Map`, a shared singleton repository, or the same database record. Separating prototype instances creates no atomicity for that underlying resource.

A practical design rule: only choose prototype when you genuinely need the lifecycle "dispense a new object on demand." If work only needs temporary state, creating local variables or immutable value objects is usually simpler. If you need `ObjectProvider`, call `getObject()` right at the unit-of-work boundary; never store the result in a singleton field expecting it to change on the next call.

## 7. `request`, `session`, `@Async`: Scope Does Not Follow Threads Automatically

### Request Scope

`@RequestScope` binds a bean to an HTTP request. In standard MVC request handling, Spring Web establishes the request context along the request-processing path. Two different requests get two different request-scoped instances, yet that **does not prove** only one thread can touch the instance within the same request or that every operation on it is atomic.

Illustrative example specific to a Spring MVC app with a web context:

```java
@RequestScope
@Component
public class RequestCart {
    private final java.util.List<String> items = new java.util.ArrayList<>();

    public void add(String item) {
        items.add(item); // not automatically thread-safe when the same instance is accessed concurrently
    }
}
```

This is merely a snippet for an MVC app, **not** standalone-runnable with the previous `AnnotationConfigApplicationContext` example. If an HTTP handler explicitly spawns parallel tasks sharing the same `RequestCart`, sharing and synchronization must be designed properly.

In particular, **the request context is not present by default on `@Async` threads**. Calling a request-scoped proxy from a worker lacking valid request attributes can fail; context propagation requires explicit supported mechanisms, respecting lifetimes and avoiding reading request data after the request ends. Never "fix" this carelessly with `InheritableThreadLocal` on thread pools, because threads are reused.

### Session Scope

`@SessionScope` binds an object to an HTTP session. A browser can send multiple requests in the same session nearly simultaneously (multiple tabs, parallel fetches), so two requests can mutate the same session bean. **One session does not equal one thread.** If session state is mutable, consider immutable designs, atomic operations, synchronizing on the shared object, or moving state to a store with proper concurrency control.

### Scoped Proxies and Short-Lived Dependencies

A singleton needing a request/session-scoped bean typically injects a **scoped proxy** or `ObjectProvider`. The proxy gives the singleton a stable reference and resolves the *active target bean* when invoked within a valid context. The proxy **does not automatically lock** the target's methods. `@RequestScope`/`@SessionScope` provide standard proxy settings to enable this injection style.

For prototypes, scoped proxies have their own semantics too: a prototype scoped proxy can fetch a new target on every method call; if you need multiple operations on **the same prototype** in one workflow, fetch one object from a provider and hold the reference for that workflow's scope. Do not expect a proxy to manage a multi-call "business transaction."

### `@Async` and Executors

`@Async`, when properly triggered through a Spring proxy, moves method *execution* to an executor, yet **does not change the service's scope**:

```text
HTTP request thread                       Worker in executor
    | calls @Async on singleton                  |
    +------------- submit --------------------->| calls method on same singleton
    | receives Future/CompletableFuture          | reads/writes singleton field
    | handles other work                         |
```

If multiple HTTP requests invoke the same `@Async` singleton service, multiple workers can concurrently modify fields on the same instance. `@Async`, `@EnableAsync`, and thread pool size **do not replace** synchronization mechanisms. A thread pool size of 1 only limits parallelism within that one executor; request threads or other executors can still touch the same bean. Never base safety on assuming only one worker ever exists.

Similarly, `@Scheduled` invokes bean methods on a schedule without making fields thread-safe. Inspect scheduler configuration, other call paths, and whether multiple schedules or multiple application instances can touch the same state together.

## 8. Designing Stateful Beans Safely

### Prefer Stateless Singletons

A singleton needs no lock merely because it has many callers: if a method computes `"Hello " + name` from a `String name` parameter without storing the request name in a field or mutating shared dependencies, every invocation has independent data. Conversely, a `currentName` field in a singleton is **one shared slot** even if annotated with `volatile` or wrapped in `AtomicReference`; those mechanisms do not separate data per request.

When per-request state is needed, create dedicated locals/DTOs or use request scope with proper lifecycle handling. When shared mutable state is truly required, define invariants and protect related operations.

### Choose Tools by Invariant

- Individual counter: `AtomicLong` / `AtomicInteger`.
- Multiple fields that must change consistently: a shared lock or immutable snapshots swapped atomically with an appropriate structure.
- Multithreaded cache: concurrent collection and atomic operations matching its contract, paying attention to immutability of **values** placed in the map.
- Multi-JVM/replica data: database transactions, optimistic locking (`@Version` when appropriate with ORM), unique constraints, or concurrency control at storage.
- Critical background work: consider durable queues, idempotency, and lifecycle management rather than merely multiplying prototypes/singletons.

Never equate `@Transactional` with `synchronized`: transactions protect consistency according to the transaction manager/storage layer and active isolation level, not by placing a mutex around Java fields; multiple transactions can still execute concurrently.

### Check Multi-Container and Multi-Instance Consequences

A Spring singleton in app A and a same-named singleton in app B are two different objects. An in-bean lock does not distribute across replicas. Conversely, two prototype beans in **the same JVM** can still access shared static state or a shared cache. Always identify the exact resource needing protection and its real execution boundary.

### Lifecycle

Spring actively manages singletons from initialization through context shutdown per their lifecycle. For prototypes, Spring creates/configures and hands over the instance, yet **does not automatically invoke prototype destruction callbacks in the full-lifecycle way it does for singletons**. If a prototype holds file handles, sockets, or expensive resources, the caller is responsible for proper cleanup. `request`/`session` beans follow request/session lifecycles when supported by a web context.

## 9. Wrong Conclusions to Avoid

| Misconception | Reality |
| --- | --- |
| "Singletons aren't thread-safe, so switch everything to prototype." | Stateless singletons can be completely safe. Prototypes can still be shared or mutate shared storage. |
| "Each task / each thread automatically gets its own prototype." | Prototypes are created when *the container is asked for a bean*, not based on thread identity. |
| "Injecting a prototype into a singleton gives a new prototype on the next service call." | The dependency is resolved when creating the singleton; use a provider or method injection to fetch fresh ones. |
| "Request scope guarantees no race conditions." | It isolates between HTTP requests; the same request or object references can still see concurrent access. |
| "Session scope locks all requests for the same user." | Requests in the same session can run in parallel. |
| "`@Async` / `@Scheduled` creates new beans or synchronizes automatically." | They orchestrate execution, not bean scope or state mutexes. |
| "Using `volatile` makes `count++` accurate." | Volatile ensures visibility per its rules, not making read-modify-write atomic. |
| "Using `@Transactional` locks fields inside the singleton." | Transactions do not replace JVM synchronization. |
| "Using `synchronized` in a singleton is safe across the whole server cluster." | A monitor lives on an object inside a single JVM. |

## 10. Process for Analyzing a Bean in a Real Project

1. **Identify instances:** where is the bean created, what is its scope, how many application contexts/replicas exist, are there scoped proxies or `ObjectProvider`s?
2. **List state:** mutable fields, injected objects, collections, `static` state, and storage data; which variables are actually shared?
3. **List call paths:** HTTP requests, `@Async`, schedulers, listeners, callbacks, executors; can two threads enter a write path together?
4. **State invariants:** e.g., "an order deducts stock only once," "increments are never lost," "a session holds valid config"; is the atomic unit one operation or multiple steps?
5. **Choose strategy:** remove state from the singleton, use immutability, atomic classes, locks on the same monitor, concurrent collections, or storage-level transactions/locks.
6. **Verify:** write contention tests with explicit coordination (`CountDownLatch`, `CyclicBarrier`) and clear post-assertions; measure races, deadlocks, and contention when needed. Never use `Thread.sleep()` to pretend to prove ordering.

Code-reading example: a singleton `@Service` has `Map<String, Cart>` and a controller handling parallel requests. **The question is not just scope**: is the `Map` safe for concurrent updates, can each `Cart` be modified simultaneously by two requests from the same user, and where is the total-price invariant protected? Switching `@Service` to prototype may fragment the cache while still failing to protect a shared `Cart` in the database.

## 11. Self-Check

**Question 1.** A singleton has no mutable fields; all request data travels via parameters and local variables. Must every method be `synchronized` simply because it is a singleton?

**Answer:** No. Shared dependencies/resources must still be checked, yet singleton scope itself creates no race if no mutable state is shared.

**Question 2.** A singleton injects `@Scope("prototype") PaymentDraft` via constructor. Is every request calling the singleton guaranteed to get a fresh `PaymentDraft`?

**Answer:** No. The prototype is created only once when Spring resolves dependencies during singleton initialization. To create per workflow, use `ObjectProvider.getObject()` or an appropriate scoping solution.

**Question 3.** Two requests in the same HTTP session update a `@SessionScope` bean at the exact same moment. Does the scope automatically protect `balance = balance - amount`?

**Answer:** No. The same session can have parallel execution. Furthermore, balances in a database must be protected at storage; a JVM lock is insufficient across multiple replicas.

**Question 4.** A singleton bean uses `AtomicInteger.incrementAndGet()` for a counter. Must it be switched to prototype so two threads increment accurately?

**Answer:** No. Atomic increment already handles that single operation on the shared atomic object; singleton is completely appropriate.

**Question 5.** An `@Async` worker is invoked from a request thread and attempts to use a request-scoped bean. What must be checked?

**Answer:** Check whether a valid request context exists on the execution thread, the context's lifecycle, how data is passed, and whether multiple threads access the state concurrently. Never assume request context travels automatically to workers.

### Key Takeaway

**Scope manages bean allocation/sharing and lifecycle; synchronization manages concurrent access to state.** Only by identifying *which object*, *which threads*, *which state*, and *which invariants* are shared can you select a safe design.

### Official References

- [Spring Framework — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html): singleton, prototype, web scopes, injecting prototypes into singletons, scoped proxies, `ObjectProvider`, and custom scopes.
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): executors, `@Async`, schedulers, and execution thread boundaries.
- [Java SE — AtomicInteger](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): semantics of atomic increments.
- [Java SE — Java Language Specification, Chapter 17](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): Java Memory Model, synchronization, and happens-before.
