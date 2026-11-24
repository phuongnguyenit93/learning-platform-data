# Immutable Objects and Safe Publication in the Spring Framework

A `@Service` bean may have only a single instance in the Spring container yet be invoked concurrently by multiple requests, `@Async` tasks, or `@Scheduled` jobs. The key question is not merely "is the bean a `singleton`?", but also: **what state is shared, can that state change, and are reader threads guaranteed to see properly initialized or updated data?**

This lesson focuses on **immutable objects** and **safe publication** when designing bean state in Spring. The theoretical foundation is the **Java Memory Model (JMM)**, particularly `happens-before` rules and the semantics of `final` fields. The practical goal is to build beans whose state is easy to reason about, safe to update, and independent of scheduling luck across threads.

## 1. Bean Scope Does Not Mean Thread-Safety

Spring uses `singleton` scope by default: **one object per bean definition per IoC container**. Multiple controllers, requests, and workers can reference that same bean. This is not "one unique instance across the entire JVM," and it certainly does not guarantee that mutable state inside the bean is automatically thread-safe.

Example of a flawed service:

```java
import org.springframework.stereotype.Service;

@Service
public class UnsafeGreetingService {
    private String lastName;

    public String greet(String name) {
        lastName = name;
        return "Hello, " + lastName;
    }
}
```

Suppose request A calls `greet("An")` and request B calls `greet("Binh")`. If A assigns `lastName = "An"`, B assigns `lastName = "Binh"`, and then A reads it, A may reply `Hello, Binh`. This is a **race condition** on a shared instance field. You must never infer that a web application is safe just because a single-threaded test "passes."

A better version for data that only serves a single call:

```java
@Service
public class GreetingService {
    public String greet(String name) {
        String currentName = name; // Local variable, private to each invocation
        return "Hello, " + currentName;
    }
}
```

There is no business reason to store a user's name in an instance field. **Keeping request state in local variables** is the simplest way to reduce shared mutable state. If long-lived state must be kept, choosing the right data structure and publication/update mechanism is part of the application's responsibility.

## 2. What Is an Immutable Object?

An **immutable** object has observable state that cannot change after valid construction. When multiple threads concurrently read a truly immutable object, they do not need locks merely to protect read operations.

In Java, a typical immutable design has these characteristics:

1. All logical state is established when constructing the object; thereafter, no method modifies it.
2. Use `private final` fields where appropriate and do not let the `this` reference escape while the constructor is running.
3. Do not directly retain references to mutable data owned by the caller if the caller can still mutate it; use a **defensive copy**.
4. Do not directly return internal mutable structures to the caller to modify; return a copy or an immutable structure.
5. Control inheritance if a subclass could add behavior that breaks the immutability contract, for example by using a `final class` or `record` for suitable value objects.

Example where **shallow immutability** is insufficient:

```java
final class WeakPolicy {
    private final java.util.Map<String, String> values;

    WeakPolicy(java.util.Map<String, String> values) {
        this.values = values; // Keeps caller's mutable reference
    }

    java.util.Map<String, String> values() {
        return values; // Returns the same mutable Map
    }
}
```

`final` here only prevents **reassigning the `values` field**; it does not stop `values.put(...)` from altering the Map's contents. One thread reading can race with another thread modifying the Map, and `HashMap` is not designed for uncoordinated concurrent reads and writes.

A better design when both keys and values are immutable:

```java
import java.util.Map;
import java.util.Objects;

public record Policy(String name, Map<String, String> values) {
    public Policy {
        Objects.requireNonNull(name, "name");
        values = Map.copyOf(Objects.requireNonNull(values, "values"));
    }
}
```

When creating `new Policy("standard", originalMap)`, the constructor takes an immutable snapshot of the entries; subsequent modifications to `originalMap` do not affect `Policy`. The `values()` accessor returns a Map whose contents cannot be changed via `put` or `remove`.

**Note on shallow copying:** `Map.copyOf` prevents structural modifications to the Map and detaches the Map's state from mutations to the original Map, but **does not automatically make value objects immutable**. With `Map<String, List<String>>`, a mutable `List` inside can still be modified through another reference; you must copy each value or use an immutable model all the way down to the data layers that need protection. `List.copyOf` and `Set.copyOf` have similar limitations. The `copyOf` methods reject disallowed null elements according to their contract.

### Record and final Are Not a "Thread-Safety Charm"

- `record Person(String name, List<String> tags)` automatically generates `final` fields, yet `tags` can still be a mutable List; a record **does not automatically deep copy**.
- `final List<String> tags = new ArrayList<>()` is a stable reference to a mutable list.
- `Collections.unmodifiableList(source)` creates a **view that cannot be modified through the view**, but if another thread modifies `source`, the view's contents still change. When you want an independent snapshot, prefer `List.copyOf(source)` when elements meet its requirements.
- `String`, `LocalDate`, and `BigDecimal` are useful examples of immutable objects for value objects. For `byte[]` arrays, legacy `Date`, or mutable DTOs, you must isolate the data.

The essential contract is that **there is no path for another thread to mutate observable state**, rather than merely counting occurrences of the `final` keyword.

## 3. What Is Publishing an Object?

**Publication** is the moment a reference to an object becomes accessible from another thread. Examples: storing it in a singleton bean's field, a shared cache, a static registry, a queue, or a Future.

Two different questions must be distinguished:

- **Is the object completely initialized?** Did the constructor properly set up state and protect any mutable data?
- **Which writes does another thread observe?** Does the Java Memory Model establish an appropriate synchronization relationship between the writer/publisher and the reader?

If one thread writes fields and assigns the object to an ordinary shared variable, another thread reading that variable **does not automatically have visibility guarantees** for all prior writes. Without a `happens-before` relationship, the program can exhibit stale reads, default values, or inconsistent observations; results are unstable, so you cannot rely on "it always works on my machine."

### 3.1. What Does Happens-Before Guarantee?

The `happens-before` (abbreviated HB) relationship defines the visibility ordering guaranteed by the JMM. If write operation W `happens-before` read operation R, the effects of W are guaranteed to be visible under the memory model rules at R, unless other valid writes intervene.

Some familiar mechanisms that establish HB relationships:

- **Same thread:** operations appearing earlier in program order happen-before later operations.
- **`synchronized`:** unlocking a monitor happens-before every subsequent lock of *that same monitor*.
- **`volatile`:** a write to a volatile variable happens-before every subsequent read of that same variable in synchronization order.
- **`Thread.start()`:** actions before calling `start()` happen-before actions in the started thread; actions of a terminating thread happen-before another thread completes `join()` on it.
- **java.util.concurrent:** constructs such as `BlockingQueue`, `ConcurrentHashMap`, `ExecutorService`, and `Future.get()` carry memory-consistency effects documented in their API contracts.

HB **does not require threads to take turns sequentially**. It is a constraint on data visibility, not a promise about execution speed or global log ordering.

### 3.2. The Special Role of `final`

The JMM has dedicated rules for **final-field semantics**. For a properly constructed object, when the constructor finishes there is a "freeze" for final fields set during initialization. Another thread obtaining a reference to a properly constructed object has stronger guarantees when observing final-field values, even if the reference transfer itself was not synchronized in the usual way.

Example:

```java
final class HostInfo {
    final String host;
    final int port;

    HostInfo(String host, int port) {
        this.host = host;
        this.port = port;
    }
}
```

The final fields of `HostInfo` have initialization semantics protected by the JMM if the object is properly constructed and `this` does not escape during the constructor. However, remember:

1. This **does not guarantee another thread will immediately see the new reference** if the variable used to publish the reference is read/written in a racy manner.
2. If a final field points to a mutable object, **subsequent modifications** to that object are not automatically protected by final-field semantics.
3. Final fields do not replace synchronization for update protocols, coordinating multiple fields, or other shared mutable state.
4. Never publish `this` inside a constructor—for example by placing it in a static registry, registering a listener that immediately calls back, or starting a task that may access the object before the constructor completes.

**Conclusion:** final fields help guarantee that an immutable object's initial state is read correctly; safe publication remains the clear way to hand off references, ensure updates become visible on time, and handle objects that are not fully immutable.

## 4. Safe Ways to Publish Data

### 4.1. Static Initialization

Class initialization has synchronization managed by the JVM. Data created during class initialization is safely published under class initialization rules.

```java
final class Defaults {
    static final Policy POLICY =
            new Policy("default", java.util.Map.of("mode", "safe"));

    private Defaults() {}
}
```

This pattern suits fixed configuration used within a class. It does not address updating snapshots at runtime.

### 4.2. Passing References via `volatile`

`volatile` fits when a variable represents **an independent value/snapshot**, where the writer swaps the entire reference and readers read once:

```java
import java.util.Map;

final class PolicyStore {
    private volatile Policy current = new Policy("v1", Map.of("level", "basic"));

    public Policy snapshot() {
        return current;            // volatile read
    }

    public void replace(Policy next) {
        current = java.util.Objects.requireNonNull(next); // volatile write
    }
}
```

Suppose one thread calls `replace(new Policy(...))` and another thread reads the new reference via `snapshot()`; it observes the state initialized prior to the volatile write. Each reader can continue using an old snapshot without it changing underneath; a reader arriving before or after a replacement may see **different versions**, but will never see "half old Map, half new Map" inside an immutable snapshot.

**Limitation:** `volatile` only guarantees visibility and atomicity for **a single reference read/write**; it does not turn a "read → modify → write" sequence into an atomic operation. If two writers concurrently run `current = modify(current)`, one update can be overwritten.

### 4.3. `synchronized` with the Same Lock

`synchronized` establishes both mutual exclusion and visibility via lock/unlock:

```java
final class LockedCounter {
    private long count;

    public synchronized void increment() {
        count++;
    }

    public synchronized long get() {
        return count;
    }
}
```

Both methods must use the same monitor (here `this`) to protect the shared state. `synchronized` is a simple choice for invariants involving multiple steps or multiple fields. Never return an internal mutable object outside and continue assuming the getter's lock protects all later mutations.

### 4.4. Handoff Through Concurrent Structures

Placing data into a `BlockingQueue` and taking from it, completing a `Future` and consuming via `get()`, or performing appropriate operations on concurrent collections are all forms of **safe handoff/publication** per their specific API contracts. For example, a producer finishes building a job object and calls `queue.put(job)`; the consumer calls `queue.take()` and receives the job with all writes made before enqueuing properly published.

Separate **the thread-safe behavior of the container** from the behavior of its elements: `ConcurrentHashMap<String, MutableReport>` does not make mutating each `MutableReport` safe. Data retrieved from the map must still be immutable or have its own synchronization if it can still change.

### 4.5. `AtomicReference` and Swapping Snapshots with CAS

When multiple writers concurrently update from prior state, use `AtomicReference<Snapshot>` with `updateAndGet` or a `compareAndSet` loop. CAS can retry when another writer updates first; it avoids two independent writers reading the same old state and overwriting each other's result.

```text
State v4
  ├── Writer A wants to add flag A ──┐
  └── Writer B wants to add flag B ──┼── CAS: one writer wins
                                     └── The other writer reads the new snapshot, recomputes, and retries CAS
Final state: contains both updates (if the merge rule is right)
```

Condition: the update function must **have no non-repeatable side effects**, because `updateAndGet` may re-invoke the function under contention. Do not send emails, write to a database, or call external services directly inside the update lambda.

## 5. Runnable Java 17+: Immutable Snapshot + Safe Publication + Multiple Writers

This example builds a snapshot with `record`, defensively copies via `Map.copyOf`, and uses `AtomicReference.updateAndGet` so 4 workers concurrently increment a counter without losing updates. Previously read snapshots remain unchanged.

Save as **ImmutablePublicationDemo.java**:

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicReference;

public class ImmutablePublicationDemo {
    public record Snapshot(int version, Map<String, Integer> counts) {
        public Snapshot {
            counts = Map.copyOf(counts);
        }

        public int count(String key) {
            return counts.getOrDefault(key, 0);
        }
    }

    private static final class Store {
        private final AtomicReference<Snapshot> current =
                new AtomicReference<>(new Snapshot(0, Map.of("views", 0)));

        Snapshot read() {
            return current.get();
        }

        void increment() {
            current.updateAndGet(old -> {
                Map<String, Integer> copy = new HashMap<>(old.counts());
                copy.merge("views", 1, Integer::sum);
                return new Snapshot(old.version() + 1, copy);
            });
        }
    }

    public static void main(String[] args) throws Exception {
        Map<String, Integer> input = new HashMap<>();
        input.put("views", 7);
        Snapshot copy = new Snapshot(5, input);
        input.put("views", 999);
        System.out.println("defensive copy: " + copy.count("views"));

        Store store = new Store();
        Snapshot before = store.read();

        ExecutorService pool = Executors.newFixedThreadPool(4);
        try {
            List<Future<?>> tasks = new ArrayList<>();

            for (int worker = 0; worker < 4; worker++) {
                tasks.add(pool.submit(() -> {
                    for (int i = 0; i < 100; i++) {
                        store.increment();
                    }
                }));
            }

            for (Future<?> task : tasks) {
                task.get();
            }
        } finally {
            pool.shutdown();
        }

        Snapshot after = store.read();
        System.out.println("before: " + before.version()
                + "/" + before.count("views"));
        System.out.println("after: " + after.version()
                + "/" + after.count("views"));
        System.out.println("old snapshot remains: " + before.count("views"));
    }
}
```

Compile/run with JDK 17 or later:

```bash
javac ImmutablePublicationDemo.java
java ImmutablePublicationDemo
```

**Deterministic stdout:**

```text
defensive copy: 7
before: 0/0
after: 400/400
old snapshot remains: 0
```

Why is the result right?

1. `Snapshot` is a record containing an `int` and a Map with `String` keys and `Integer` values, all immutable; the compact constructor uses `Map.copyOf` to prevent external modification of the snapshot Map. The `copy` instance still retains 7 even though `input` is changed to 999.
2. `Store.read()` reads the current reference via `AtomicReference.get()`; each snapshot is **a complete state**.
3. Each `increment()` constructs a new Map, creates a new Snapshot, and `updateAndGet` performs an atomic update with CAS/retry. No Map undergoing mutation is shared across threads.
4. Four workers perform a total of 400 increments. `Future.get()` ensures tasks have completed while providing the appropriate memory-consistency relationship before `main` reads the result.
5. Snapshot `before` still has version 0 and `views=0`: the old object was never mutated. Writers only swap the current reference to a new snapshot.

Note: **CAS can re-run the lambda** multiple times; every operation inside the lambda here only computes in local memory and creates new objects. This approach does not remove business requirements around persistence, transactions, or durability across restarts.

## 6. Applying the Snapshot Model to a Spring Singleton Bean

### 6.1. Read-Heavy Bean with Runtime Configuration Updates

Example service managing feature flags. It reads an immutable snapshot, writes with CAS, and keeps a version to observe changes. This is a fragment for a Spring Framework 6+/Spring Boot 3+ project, requiring Spring dependencies and placed in **src/main/java/com/example/demo/FeatureFlagService.java**; it will not compile with standalone `javac` without Spring on the classpath.

```java
package com.example.demo;

import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.stereotype.Service;

@Service
public class FeatureFlagService {
    private final AtomicReference<Flags> current =
            new AtomicReference<>(new Flags(0, Map.of()));

    public boolean enabled(String name) {
        Objects.requireNonNull(name, "name");
        Flags snapshot = current.get();
        return snapshot.values().getOrDefault(name, false);
    }

    public Flags snapshot() {
        return current.get();
    }

    public void setFlag(String name, boolean enabled) {
        Objects.requireNonNull(name, "name");
        current.updateAndGet(old -> {
            Map<String, Boolean> next = new HashMap<>(old.values());
            next.put(name, enabled);
            return new Flags(old.version() + 1, next);
        });
    }

    public record Flags(long version, Map<String, Boolean> values) {
        public Flags {
            values = Map.copyOf(Objects.requireNonNull(values, "values"));
        }
    }
}
```

A controller/request thread can call `enabled("newCheckout")` while a scheduler/admin thread calls `setFlag(...)`. Each read obtains **a consistent snapshot**; there is no Map being mutated in place to cause a race. Two writers updating **two different flag names** do not drop updates because CAS recomputes from the new state under contention. However, two writers setting **the same flag** to different values still have the outcome "whichever update linearizes last wins"; that is a **business rule**, not a JMM bug.

Key points to note:

- `FeatureFlagService` can be injected into multiple controllers and jobs because one singleton instance serves concurrent accesses; thread-safety comes from immutable snapshots and AtomicReference, not from `@Service`.
- Each update copies the entire Map, incurring memory and CPU cost proportional to the Map's size. This fits **read-heavy/write-rarely** cases like feature flags/configuration; if writes are continuous on very large data, evaluate alternatives such as `ConcurrentHashMap`, partitioning, event streams, or appropriately scoped locks.
- If the pair `values + version` must always belong to the same snapshot, put them inside **the same Flags object** as shown above. Two independent volatile fields do not guarantee that separate reads form a consistent pair.
- Exposing `snapshot()` here remains safe because `Flags` itself is immutable with `String/Boolean`. If values are mutable, you must adjust the copying strategy.
- When updates involve a database, event, or network call, do not perform side effects inside the CAS lambda; perform them after the update succeeds and design failure semantics explicitly.

### 6.2. Constructor Injection + Final Dependency

Another Spring singleton bean might have no mutable state at all:

```java
import org.springframework.stereotype.Service;

@Service
public class PriceService {
    private final TaxPolicy taxPolicy;

    public PriceService(TaxPolicy taxPolicy) {
        this.taxPolicy = taxPolicy;
    }

    public long totalWithTax(long amount) {
        return taxPolicy.apply(amount);
    }
}
```

This is a **fragment** illustrating DI; `TaxPolicy` is an assumed abstraction defined elsewhere. The `final` field ensures `PriceService` does not swap the dependency reference after construction; whether `PriceService` is thread-safe also depends on **whether `TaxPolicy` holds mutable state** and how its `apply` method behaves. If the dependency is immutable or thread-safe and the method holds no other shared state, this pattern is very straightforward to use concurrently.

**Do not equate "dependency field is final" with "the entire object graph is immutable."** A final field pointing to a mutable cache still requires synchronization rules for that cache.

## 7. Bean Publication in the Spring Lifecycle

In the standard lifecycle, Spring instantiates the bean, handles dependency injection, invokes initialization callbacks (such as `@PostConstruct`), and then publishes the ready-to-use bean through the container. Spring documentation notes that configuration state modified only **during initialization** has proper visibility guarantees once the container finishes publishing the singleton; ordinary configuration fields do not necessarily need to be marked volatile merely because setter injection runs during initialization.

However, distinguish carefully:

| Scenario | Assessment |
| --- | --- |
| Bean constructor receives dependency into a `final` field, unmodified afterwards | Good design for fixed configuration/dependencies |
| Setter or `@PostConstruct` sets up state and stops modifying it; Spring publishes the bean normally after init | Container publishes the bean's initialized state per its lifecycle |
| An arbitrary thread modifies a plain field **after** the bean is initialized | No visibility/thread-safety guarantee merely from being a singleton |
| Field changes at runtime and has multiple readers | Needs `volatile`, a lock, atomics, a concurrent structure, or an appropriate mechanism |
| Bean hands `this` to a static registry/another thread during constructor/init | Risk of premature publication before initialization completes |
| Circular dependency forces Spring to expose the bean early before initialization finishes | Can create exceptions to normal publication rules; avoid circular dependencies |

### 7.1. Why Does `@PostConstruct` Not Replace Concurrency Control?

`@PostConstruct` runs during lifecycle initialization. This method is well-suited for validating configuration or creating initial data structures. Once complete, the container considers the bean initialized under the standard flow. However, if some method keeps modifying a Map or plain field while multiple requests are using the bean, **visibility for runtime updates does not arise automatically**. Appropriate synchronization must be designed.

Do not start workers yourself, register listener callbacks prematurely, or hand `this` to uncontrolled components before construction/init completes. If you need to execute long-running work after all singletons have finished initializing, consider an appropriate lifecycle hook such as `SmartInitializingSingleton.afterSingletonsInstantiated()`, `ContextRefreshedEvent`, or `SmartLifecycle`; these address **startup timing**, whereas runtime state sharing must still satisfy the JMM.

### 7.2. Do Prototype or Request Scopes Solve This?

`prototype` creates a new instance each time the container directly resolves the bean, yet if a prototype bean is injected once into a singleton, the singleton normally keeps that exact injected instance. `request` scope provides one instance per request in an appropriate web context, yet it can still share mutable data via dependencies, caches, or async handoffs. Thus, scope is a tool for **defining lifecycle and sharing boundaries**, not a general synchronization mechanism.

## 8. Choosing a Mechanism by Bean State Pattern

| Kind of state | Preferred design approach | What to avoid |
| --- | --- | --- |
| Parameters tied to a single request/call | Local variables, immutable DTOs | Storing current user/request in a singleton instance field |
| Configuration unchanged after bootstrap | Constructor injection, `final`, immutable value objects | Retaining references to mutable input Maps/Lists |
| Configuration replaced wholesale by version, read-heavy | Immutable snapshot in `volatile` / `AtomicReference` | Mutating the old snapshot's Map in place |
| Multiple writers updating from previous state | `AtomicReference.updateAndGet` / CAS or lock | `volatile` plus `state = derive(state)` under contention |
| Single atomic counter/value | `AtomicLong`, `LongAdder` depending on exact read requirements | `count++` on `volatile long`, as it is not an atomic increment |
| Map needing independent high-frequency per-key updates | `ConcurrentHashMap.compute` or `merge` | `get` then `put` assuming the combination is atomic |
| Multiple fields sharing an invariant | Lock covering the entire operation or a combined snapshot | Separate volatile fields read piecemeal into a "mixed" state |
| Handing off work between threads | Executor, queue, Future with clear HB contracts | Sharing a mutable object and neglecting synchronization |

**Invariant example:** if `min <= max` must always hold, making `min` and `max` two volatile variables does not guarantee every reader sees a valid pair from the same version. You can use a `Range(int min, int max)` record, validate the invariant in the constructor, and swap the entire `volatile Range`/`AtomicReference<Range>` in one step, or lock around reading/writing both fields together.

### Performance Note

Immutable snapshots typically trade a cost **per update** for fast and simple reads, which works very well for rarely-written configuration. For continuously changing, large state, copying an entire Map every time is suboptimal. Choosing between atomics, locks, concurrent collections, or snapshots must stem from read/write ratio, state size, invariants to protect, and latency requirements; no single mechanism is always best.

## 9. Common Mistakes

**Mistake 1 — Assuming singleton = thread-safe.** Singleton only defines the container-managed instance count. If requests mutate the same field, a race still exists.

**Mistake 2 — Using a `final HashMap` and modifying it with `put`.** `final` holds the reference, not freeze the HashMap's contents. Use an immutable Map, synchronization, or a concurrent collection as needed.

**Mistake 3 — Wrapping a still-mutable source Map in `Collections.unmodifiableMap`.** The view cannot be mutated through its API, yet still reflects changes to the underlying source. When an isolated snapshot is needed, copy the data.

**Mistake 4 — Exposing the object before the constructor completes.** Registering listeners, saving `this` into a static field, or launching tasks from a constructor can let another thread see a partially constructed object, violating the conditions for final-field guarantees.

**Mistake 5 — Assuming `@PostConstruct` makes all future updates visible.** The container's initial state publication guarantee does not cover runtime mutations. Proper memory barriers/synchronization are required.

**Mistake 6 — Simply marking a Map `volatile` and continuing to call `map.put`.** A volatile reference does not make operations inside `HashMap` atomic or safe. Swap an entire immutable snapshot or use proper structures/thread coordination.

**Mistake 7 — Using `volatile count++`.** Incrementing involves read, add, write and can lose updates. `AtomicLong.incrementAndGet()` or `synchronized` guarantees atomicity for a single counter.

**Mistake 8 — Confusing safe publication with safe mutation.** Safe publication lets consumers see state *at the moment of handoff*; if the object remains mutable and writers modify it later, accessing those modifications still requires thread-safety.

**Mistake 9 — Hearing "concurrent collection" and placing mutable data inside.** A thread-safe Map does not automatically protect each value's state. Immutable values or explicit synchronization are needed.

**Mistake 10 — Calling a DB/HTTP inside `AtomicReference.updateAndGet`.** The lambda can be re-executed during CAS retries, producing duplicate side effects. Only compute the new object inside the lambda; coordinate I/O via an explicit protocol.

**Mistake 11 — Reading two different snapshots within a single decision.** If two calls to `store.snapshot()` can return two versions, business logic can mix inconsistent data. Grab the snapshot **once** at the start of a decision requiring consistency and use it throughout.

**Mistake 12 — Mistaking visibility for persistence.** Volatile and CAS ensure memory ordering between threads within the same JVM; they do not persist state across restarts and do not synchronize state across multiple Spring Boot replicas. Those problems require a database, message broker, or distributed mechanism.

## 10. Check Your Understanding

**Question 1.** A Spring `@Service` has `private final Map<String, Integer> totals = new HashMap<>();`. Concurrent requests call `totals.merge(...)`. Is it thread-safe?

**Answer:** No. The final field only keeps the Map reference fixed; a mutable HashMap is unsafe for concurrent updates. Depending on requirements, use a concurrent map with `merge/compute`, a lock, or immutable snapshots swapped with CAS.

**Question 2.** Is `record Config(List<String> servers)` always deeply immutable?

**Answer:** No. A record does not automatically copy the list. The constructor can use `servers = List.copyOf(servers)` for a list of immutable String elements and avoid returning internal mutable data.

**Question 3.** When one thread assigns `volatile Config current` to a newly constructed object, will a reader fetching the object through that same volatile variable see the initialized state?

**Answer:** Yes, for writes happening before the volatile write and the corresponding volatile read under HB rules. If the object is later modified through another unsynchronized path, this guarantee does not automatically protect subsequent mutations.

**Question 4.** Why can `volatile long counter; counter++;` lose increments?

**Answer:** Because volatile does not merge read-modify-write into a single atomic action. Two threads can read the same old value and write the same new value; use an atomic counter or a lock.

**Question 5.** Why does an old immutable snapshot remain usable when the bean switches to a new snapshot?

**Answer:** The writer creates a new object and only swaps the current reference. A reader holding the old object still sees a consistent old state, provided the state graph is genuinely immutable and the object was properly constructed/published.

**Question 6.** Spring guarantees a singleton is published after completing standard initialization; does that mean plain fields can be modified by multiple requests without synchronization?

**Answer:** No. Initial publication and runtime updates are two distinct concerns. After initialization, shared mutable state still requires proper thread-safety/visibility mechanisms.

## 11. Pre-Production Bean Checklist

1. Identify exactly which fields are **per-request**, which are **shared**, and whether any writers exist outside request threads (schedulers, async tasks, listeners).
2. For read-only state, design **immutable value objects**, defensively copy nested structures, and use constructor injection for required dependencies.
3. Prevent `this` or internal mutable references from escaping before the object is completely initialized.
4. For dynamic updates, choose a **volatile snapshot** for simple replacements or **CAS/locks** for updates depending on previous state; keep invariants within a single snapshot.
5. Verify that shared objects and elements are truly immutable or have an explicit synchronization protocol; do not blindly trust the `final` keyword.
6. Test behavior under competing writers, delayed async jobs, instance restarts, and multiple active replicas.
7. Separate **thread-safety within the JVM** from **data durability and distributed consistency**.

**Takeaway:** *Immutability* eliminates post-construction state mutation; *safe publication* guarantees other threads receive initialized/updated state under proper memory rules; *Spring bean scope* governs the scope within which objects are shared. Combining these three perspectives leads to sound concurrency reasoning in Spring applications.

## References

- Java Language Specification, Chapter 17 — Threads and Locks; `17.4 (Memory Model)`, `17.5 (Final Field Semantics)`: https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html
- Spring Framework — Bean Scopes: https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html
- Spring Framework — Dependency Injection (constructor injection, circular references): https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html
- Spring Framework — Customizing the Nature of a Bean (init/publication and runtime state): https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
- Java SE API — `java.util.concurrent`, `AtomicReference`, `Future`, `ConcurrentHashMap`, and `BlockingQueue`.
