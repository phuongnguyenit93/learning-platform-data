# AtomicIntegerFieldUpdater and Applicability Conditions in Java

## 1. Problem: Needing Atomic Updates for an Object's Field

In Java concurrency, incrementing `counter++` on a regular `int` field is not atomic: two threads can read the same old value and overwrite each other's result. A familiar solution is to keep an `AtomicInteger` inside each object:

~~~java
// Illustration inside a class, not a standalone program.
private final AtomicInteger counter = new AtomicInteger();

void increment() {
    counter.incrementAndGet();
}
~~~

This approach is simple and is usually the first choice. However, if the program has **very many objects**, each needing a small counter, placing a separate `AtomicInteger` object inside every instance can incur extra allocation, reference, and memory overhead.

`java.util.concurrent.atomic.AtomicIntegerFieldUpdater<T>` allows atomic operations on **a `volatile int` field residing directly inside an object of type T**:

~~~java
// Illustration inside the class declaring the field, not a standalone program.
private volatile int count;

private static final AtomicIntegerFieldUpdater<MyCounter> COUNT =
    AtomicIntegerFieldUpdater.newUpdater(MyCounter.class, "count");
~~~

You can then call `COUNT.incrementAndGet(this)`, `COUNT.compareAndSet(this, expected, update)`, or `COUNT.get(this)`. **A single updater can be shared** to update the corresponding field across many instances, without each instance holding an `AtomicInteger` object.

**Important to remember from the start:** A field updater is a low-level tool for a specific field; it **does not replace** designing ownership, protecting multi-variable invariants, and ensuring all update paths follow the same protocol.

This article focuses on the JDK API and the Java Memory Model of **Java in general**, without going into framework configuration.

### Learning Objectives

After this article, you should understand:

1. Why a field updater differs from `AtomicInteger` and when it is beneficial.
2. The mandatory conditions: an **instance** field, exact type **primitive `int`**, **`volatile`** modifier, and valid access at the updater creation site.
3. How to create `AtomicIntegerFieldUpdater.newUpdater(...)`, update using CAS, and interpret the returned results properly.
4. Why mixing an updater with direct writes or `count++` can break the atomic protocol.
5. The scope of the updater's visibility/ordering guarantees, and its limits regarding multiple fields, contention, and retries.
6. How to choose between an updater, `AtomicInteger`, `AtomicLongFieldUpdater`, `AtomicReferenceFieldUpdater`, and `VarHandle` on Java 17+.

## 2. Concept and API Signatures

An updater is an object that describes **how to atomically access** a specific `int` field of an object type.

~~~java
// API syntax at an illustrative level, not a standalone program.
AtomicIntegerFieldUpdater<Worker> updater =
    AtomicIntegerFieldUpdater.newUpdater(Worker.class, "progress");

// target must be a valid Worker.
updater.get(target);
updater.incrementAndGet(target);
updater.compareAndSet(target, 10, 11);
~~~

Factory method:

~~~java
// General signature, not a standalone program snippet.
public static <U> AtomicIntegerFieldUpdater<U> newUpdater(
    Class<U> tclass,
    String fieldName
);
~~~

Where:

- `tclass` is the class declaring the target field; in the example, `Worker.class`.
- `fieldName` is the **actual field name** as a string, such as `"progress"`. It is not a getter name, and the compiler does not verify the existence of this string.
- `U` is the type of the target object; each updater operation takes an **instance** containing the field.
- The updater object is usually created once and stored in `private static final` so that many instances can share it.

Most familiar operations of `AtomicInteger` are also available on the updater, except they take an additional **target object**:

| Updater API | Meaning |
| --- | --- |
| `get(obj)` | Reads the field with volatile semantics |
| `set(obj, newValue)` | Writes the field with volatile semantics |
| `lazySet(obj, newValue)` | Writes with release/lazy set semantics, weaker than a full volatile set |
| `compareAndSet(obj, expected, update)` | CAS: changes the value if it currently equals `expected`, returns boolean |
| `getAndSet(obj, update)` | Sets the new value and returns the old value |
| `getAndIncrement(obj)` | Atomically increments, returns the **value before incrementing** |
| `incrementAndGet(obj)` | Atomically increments, returns the **value after incrementing** |
| `getAndAdd(obj, delta)` | Atomically adds, returns the old value |
| `addAndGet(obj, delta)` | Atomically adds, returns the new value |
| `updateAndGet(obj, function)` | Atomically updates using a transformation function, returns the new value |

A single updater applies to **many instances of the same class**, but a call on instance A does not automatically update instance B. A field updater manages **the field location within each object**, not a shared global variable.

## 3. Mandatory Conditions When Declaring the Field

### 3.1. Must be an instance field, not static

`AtomicIntegerFieldUpdater` updates a specific field of a **given object**. A field declared `static` is not suitable because it belongs to the class, not to individual instances.

~~~java
// Valid field shape, when the updater is created within an appropriate access scope:
private volatile int attempts;

// Invalid as a target for AtomicIntegerFieldUpdater:
private static volatile int globalAttempts;
~~~

For a global counter, you can use a `static final AtomicInteger`, or choose another field/handle mechanism if there is a clear reason.

### 3.2. Type must be strictly primitive int

The target field must have primitive type `int`. The following types are **not** usable with `AtomicIntegerFieldUpdater`:

- `Integer`: object wrapper, not primitive `int`.
- `long`: use `AtomicLongFieldUpdater` if you have the same need.
- `boolean`: not a target for an integer field updater; you can use `AtomicBoolean` or represent state with `int` when truly needed.
- `Object` or any reference type: consider `AtomicReferenceFieldUpdater<T,V>`.

Automatic boxing/unboxing of `Integer` in Java expressions does not make an `Integer` field an `int` field as far as reflection and the API are concerned.

### 3.3. Must have volatile

The field must be declared `volatile`:

~~~java
// Valid condition.
private volatile int state;

// Invalid for creating an updater.
private int stateWithoutVolatile;
~~~

`volatile` establishes cross-thread visibility/ordering semantics under the Java Memory Model, while the updater adds **atomic read–modify–write** operations such as CAS and `incrementAndGet`.

You should not omit `volatile` on the grounds that “we are already calling the updater”: the updater constructor/factory checks the field type and modifiers, and a non-volatile field will be rejected.

### 3.4. Access rights must be valid at the newUpdater call site

Each updater is created via reflection and performs access checks based on the caller's context. A simple, reliable encapsulation pattern is to **place the updater factory inside the very class that declares the field**:

~~~java
// Valid illustrative snippet inside class Worker, not a standalone program.
private volatile int progress;

private static final AtomicIntegerFieldUpdater<Worker> PROGRESS =
    AtomicIntegerFieldUpdater.newUpdater(Worker.class, "progress");
~~~

`private volatile` is **completely usable** if the updater is created from a context that has access to that private field. Therefore, the rule “the field must be public” is **false**.

Conversely, an external class creating an updater for another class's private field may be denied access. With package-private/protected fields, the package, inheritance relationship, and actual receiver can also affect access rights. In applications using Java modules, access/module boundaries must also be considered.

Do not try to fix an access error by arbitrarily making every field public. Prefer placing the factory inside the class that owns the field and exposing appropriate business methods.

### 3.5. Do not repurpose the field

Because the field is a normal `volatile int`, Java still allows code within the class to read or write it directly. However, once you choose an updater to enforce update rules, **every writer to that field must follow the defined protocol**. An unexpected direct setter can overwrite a CAS-computed value or break an invariant.

A field also cannot be simultaneously `final volatile` under Java language rules. It needs to be updated during the object's lifecycle, so it cannot be a final field.

## 4. Example 1 — Multiple Threads Incrementing a Field with an Updater (Java 17+)

Create the file `FieldUpdaterCounterDemo.java`:

~~~java
import java.util.concurrent.atomic.AtomicIntegerFieldUpdater;

public class FieldUpdaterCounterDemo {
    static final class Counter {
        private volatile int value;

        private static final AtomicIntegerFieldUpdater<Counter> VALUE =
            AtomicIntegerFieldUpdater.newUpdater(
                Counter.class, "value"
            );

        void increment() {
            VALUE.incrementAndGet(this);
        }

        int get() {
            return VALUE.get(this);
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        Counter counter = new Counter();

        Runnable work = () -> {
            for (int i = 0; i < 5000; i++) {
                counter.increment();
            }
        };

        Thread first = new Thread(work, "counter-1");
        Thread second = new Thread(work, "counter-2");
        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println("value = " + counter.get());
    }
}
~~~

Compile and run:

~~~bash
javac FieldUpdaterCounterDemo.java
java FieldUpdaterCounterDemo
~~~

Exact output when both workers finish:

~~~text
value = 10000
~~~

Explanation:

1. `Counter` has a `private volatile int value` field, meeting the type/modifier/instance requirements.
2. `VALUE` is `static final`, so both threads use **one updater**, while acting on the field of the same `counter` object.
3. `incrementAndGet(this)` performs an atomic increment, avoiding the lost update of regular `value++`.
4. `join()` waits for both workers to finish before `main` reads and prints; the result is 2 × 5,000 = 10,000.
5. Using an updater does not make `Counter` automatically protect **all other state**; only the `value` field is updated under that protocol.

If the class has other fields that depend on `value`, a single CAS operation does not turn a multi-field update into a transaction.

## 5. CAS for One-Way State Transitions: Example 2 (Java 17+)

An application often has states such as `NEW → RUNNING → DONE`. If two threads simultaneously request to start a job, **only one** may transition it from NEW to RUNNING. `compareAndSet` is well-suited to perform this state transition atomically.

Create the file `UpdaterStateMachineDemo.java`:

~~~java
import java.util.concurrent.atomic.AtomicIntegerFieldUpdater;

public class UpdaterStateMachineDemo {
    static final class Job {
        private static final int NEW = 0;
        private static final int RUNNING = 1;
        private static final int DONE = 2;

        private volatile int state = NEW;

        private static final AtomicIntegerFieldUpdater<Job> STATE =
            AtomicIntegerFieldUpdater.newUpdater(
                Job.class, "state"
            );

        boolean tryStart() {
            return STATE.compareAndSet(this, NEW, RUNNING);
        }

        boolean finish() {
            return STATE.compareAndSet(this, RUNNING, DONE);
        }

        String stateName() {
            return switch (STATE.get(this)) {
                case NEW -> "NEW";
                case RUNNING -> "RUNNING";
                case DONE -> "DONE";
                default -> "INVALID";
            };
        }
    }

    public static void main(String[] args) {
        Job job = new Job();

        System.out.println("start first = " + job.tryStart());
        System.out.println("start second = " + job.tryStart());
        System.out.println("finish = " + job.finish());
        System.out.println("state = " + job.stateName());
    }
}
~~~

Compile and run with Java 17+:

~~~bash
javac UpdaterStateMachineDemo.java
java UpdaterStateMachineDemo
~~~

Exact output:

~~~text
start first = true
start second = false
finish = true
state = DONE
~~~

- The first CAS sees `state == NEW` and transitions it to RUNNING.
- The second CAS requires `state == NEW`, but state is already RUNNING, so it returns `false`.
- `finish` only transitions RUNNING to DONE.
- Do not use `if (state == NEW) state = RUNNING` for this task: check-then-act can be interleaved by another thread between the two steps.

If two threads actually call `tryStart()` concurrently, only **one of the two** can succeed, though which thread wins is not fixed. Do not rely on “thread A wins” as a guaranteed outcome.

For a state machine with multiple transitions, you still have to define all states, transition conditions, and failure handling. CAS on an `int` only protects the specific transition written; it does not complete the job, roll back side effects, or manage timeouts.

## 6. Mixing an Updater with Direct Writes: A Critical Bug

### 6.1. Why can a “volatile field” still suffer lost updates?

A field like `private volatile int value` gives individual reads and writes volatile semantics, but **`value++` still consists of multiple steps**. If one code path calls `VALUE.incrementAndGet(this)` while another code path calls `value++` or `value = cached + 1`, the operations can interleave and cause lost updates.

Do not mix them:

~~~java
// Illustration in a class with updater VALUE; NOT safe if run concurrently.
void incrementWrong() {
    value++;
}

void incrementRight() {
    VALUE.incrementAndGet(this);
}
~~~

Even though the direct write is also a volatile write and has visibility, the compound update lacks atomicity. In addition, a direct setter can bypass CAS conditions such as “transition NEW to RUNNING only once.”

The Javadoc notes that the atomicity guarantees of a field updater depend on callers operating **in accordance with the atomic protocol**; an updater cannot prevent other methods from accessing the field unsafely. That is why you should keep the field `private` and provide methods whose names clearly express the transitions.

### 6.2. Example 3 — Controlled Lost Update (Java 17+)

Instead of hoping the scheduler randomly triggers a race, we use a latch so both threads read the old value before writing. At the same time, another field is updated via an updater for comparison.

Create the file `FieldUpdaterRaceDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicIntegerFieldUpdater;

public class FieldUpdaterRaceDemo {
    static final class Counts {
        private volatile int unsafe;
        private volatile int safe;

        private static final AtomicIntegerFieldUpdater<Counts> SAFE =
            AtomicIntegerFieldUpdater.newUpdater(
                Counts.class, "safe"
            );

        void incrementSafe() {
            SAFE.incrementAndGet(this);
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        Counts counts = new Counts();
        CountDownLatch bothRead = new CountDownLatch(2);

        Runnable work = () -> {
            int before = counts.unsafe;
            bothRead.countDown();

            try {
                bothRead.await();
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
                return;
            }

            counts.unsafe = before + 1;
            counts.incrementSafe();
        };

        Thread a = new Thread(work, "worker-a");
        Thread b = new Thread(work, "worker-b");
        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("unsafe = " + counts.unsafe);
        System.out.println("safe = " + Counts.SAFE.get(counts));
    }
}
~~~

Compile and run:

~~~bash
javac FieldUpdaterRaceDemo.java
java FieldUpdaterRaceDemo
~~~

Exact output when workers are not interrupted:

~~~text
unsafe = 1
safe = 2
~~~

Both threads read the same `before == 0` and are then released past `bothRead`. As a result, both `counts.unsafe = before + 1` writes store 1, even though the field is `volatile`. For the `safe` field, the two `SAFE.incrementAndGet(counts)` calls use atomic read–modify–write, producing 2.

This experiment intentionally orders the reads before the writes; it is not a random stress test. The latch coordinates the example; it does not make the `unsafe` update atomic.

## 7. Writing a Correct CAS Loop and Handling Contention

Not every update logic has a ready-made simple method. For example, incrementing a counter **without exceeding a limit**:

~~~java
// Illustration in a class with private volatile int value and updater VALUE.
int incrementUnlessAtMax() {
    for (;;) {
        int oldValue = VALUE.get(this);

        if (oldValue == Integer.MAX_VALUE) {
            return oldValue;
        }

        if (VALUE.compareAndSet(this, oldValue, oldValue + 1)) {
            return oldValue + 1;
        }

        // Contention occurred: re-read and retry CAS on the new state.
    }
}
~~~

Explanation:

- `get` reads the old value with volatile semantics.
- If the limit is already reached, no change is made.
- If not yet reached, CAS only changes it if the field still equals the value read. If another thread updated it first, CAS fails and the loop retries.
- Checking `Integer.MAX_VALUE` prevents overflow for this increment.

**Points to watch out for in a CAS loop:**

1. **Side effects:** Do not send emails, call APIs, write files, or deduct money inside a section that can be repeated multiple times. An attempt may fail after the side effect has already executed.
2. **Progress:** CAS does not guarantee fair turns for each thread. One thread may fail repeatedly under contention even while the overall system makes progress.
3. **CPU:** Excessive spinning wastes CPU; measure actual contention and consider backoff, locks, queues, or sharding state.
4. **Overflow:** Java `int` arithmetic wraps around when exceeding its range; business protocols need explicit rules.
5. **Invariants:** If a change must affect two variables, CAS on a single field does not preserve atomicity across both.
6. **ABA:** A state sequence A → B → A can allow a CAS from A to C to succeed even though the state changed between read and update; if history/version matters, use a version number or an appropriate state representation.

The `updateAndGet` and `getAndUpdate` methods may also invoke the transformation function multiple times due to CAS retries. The function should be short, side-effect-free, and safe for repeated execution.

## 8. Example 4 — One Updater, Many Independent Objects (Java 17+)

The valuable point of a field updater is **not creating an atomic wrapper per instance**. A single static updater is shared yet still operates on different objects.

Create the file `ManyCountersDemo.java`:

~~~java
import java.util.concurrent.atomic.AtomicIntegerFieldUpdater;

public class ManyCountersDemo {
    static final class Bucket {
        private volatile int hits;

        private static final AtomicIntegerFieldUpdater<Bucket> HITS =
            AtomicIntegerFieldUpdater.newUpdater(
                Bucket.class, "hits"
            );

        void addHit() {
            HITS.incrementAndGet(this);
        }

        int hits() {
            return HITS.get(this);
        }
    }

    public static void main(String[] args) {
        Bucket first = new Bucket();
        Bucket second = new Bucket();

        first.addHit();
        first.addHit();
        second.addHit();

        System.out.println("first = " + first.hits());
        System.out.println("second = " + second.hits());
    }
}
~~~

Compile and run:

~~~bash
javac ManyCountersDemo.java
java ManyCountersDemo
~~~

Exact output:

~~~text
first = 2
second = 1
~~~

`Bucket.HITS` does not hold a value of its own. It knows *which field* to update. `first` and `second` still have two independent `hits` fields. Creating a separate updater per instance would miss the benefit of reusing the factory and introduce unnecessary reflective access operations.

However, do not conclude that an updater is always faster than `AtomicInteger`. Operation time also depends on the JVM, field layout, cache contention, thread count, allocation policy, and workload. **The notable potential benefit is reducing wrapper objects per instance**, not guaranteeing higher throughput in every case.

## 9. Java Memory Model: Visibility and Ordering of Updaters

### 9.1. Why does the field need volatile?

`volatile` does not make `x++` atomic. However, it provides cross-thread read/write guarantees when there is an appropriate publication protocol:

- A volatile write and a corresponding volatile read are bound by a **synchronizes-with/happens-before** relationship under the JMM.
- A single volatile read/write is atomic for an `int` field; the updater adds CAS and atomic compound updates.
- Actions before a volatile write can be published to a thread that later performs a volatile read under the appropriate HB relationship.

You must distinguish **visibility**, **ordering**, and **atomicity**. An updater does not automatically make the entire object thread-safe. For example, if there are two fields `processed` and `failed`, two independent updaters do not produce an atomic snapshot of the pair of values.

### 9.2. Can direct read paths be used?

A method `get() { return value; }` in a class containing `private volatile int value` still has volatile read semantics. However, to centralize the protocol and ease code review, using `VALUE.get(this)` makes it clear that the operation goes through the updater.

**Important:** Directly reading a volatile field does not cause an error by itself; the main risk lies in **write/update paths that do not follow the same invariant**, such as `value++` or `value = newValue` breaking CAS conditions. Do not absolutize that all direct accesses are “forbidden by the JVM”; they are valid in the language but can be a design mistake.

### 9.3. An updater does not create a multi-field transaction

Consider two fields `remaining` and `reserved`. Calling `getAndDecrement` on `remaining` followed by `incrementAndGet` on `reserved` consists of **two separate atomic operations**; a reader can observe the state in between the two updates.

If the invariant must hold at a single point of observation, consider:

- `synchronized` or `Lock` protecting both fields and all appropriate read paths.
- An immutable object holding both values, replaced via an `AtomicReference<Snapshot>`.
- Transferring ownership to a single thread that processes messages sequentially, if the system model allows.

A field updater is especially suited for **an independent numeric state**, **a counter**, **a numeric flag**, or **a single-field transition** where all update paths are controlled.

## 10. Comparing AtomicInteger, Updaters, VarHandle, and Other Updaters

| Option | Where is state stored? | When is it suitable? | Notes |
| --- | --- | --- | --- |
| `AtomicInteger` | Inside a separate atomic object | Few instances, simple code, clear API needed | Adds a wrapper object if each instance holds an atomic |
| `AtomicIntegerFieldUpdater<T>` | `volatile int` field in `T`; updater is shared | Very many small objects, want CAS directly on the field | Requires string field name, access rights, instance volatile int |
| `AtomicLongFieldUpdater<T>` | `volatile long` field in `T` | 64-bit counters across many instances | Also consider access, performance, and contention |
| `AtomicReferenceFieldUpdater<T,V>` | `volatile V` field in `T` | Atomically switching reference state | Protects the reference, does not make the referenced object immutable |
| `VarHandle` (Java 9+) | Handle to a field/array element/other | Want flexible access mode control | Low-level API, many memory-ordering modes, easy to misuse |
| `synchronized` / `Lock` | State can span multiple fields | Protecting compound invariants, complex updates | Contention and deadlock risk with nested locks |
| `LongAdder` | Internally multiple cells for summation | Counting statistics under high contention | `sum()` is not an atomic snapshot during concurrent updates |

### 10.1. When is AtomicInteger still the better choice?

If there are only a few objects and a modest number of workers, `AtomicInteger` is usually:

- Easier to read and use, without requiring a string field name.
- Cleaner in encapsulation, with atomic operations directly on the instance.
- Less prone to a direct setter mistakenly writing to the primitive field.
- Easier to move code or refactor fields without maintaining string names in the factory.

Do not choose an updater just to “micro-optimize” a rarely instantiated class. Measure allocation, heap, throughput, tail latency, and GC before deciding.

### 10.2. VarHandle on Java 17+

`VarHandle` can point to a field and supports `getVolatile`, `setVolatile`, `compareAndSet`, `getAndAdd`, and various other access modes.

~~~java
// Illustration of looking up a VarHandle, not a standalone program.
VarHandle handle = MethodHandles.lookup().findVarHandle(
    Counter.class, "value", int.class
);
int old = (int) handle.getAndAdd(counter, 1);
~~~

The snippet above assumes the code has access to the field, imports `java.lang.invoke.MethodHandles` and `java.lang.invoke.VarHandle`, and handles checked reflection exceptions. The `value` field must be an instance field of type `int`. Unlike an updater, `VarHandle` has multiple access modes; you must understand the memory ordering contract of each mode to avoid choosing an operation weaker than required.

`VarHandle` is not inherently safer or faster than an updater; switching requires benchmarking, reviewing memory semantics, and testing on the target JDK.

## 11. Common Configuration Mistakes

### 11.1. Confusing a regular field with a volatile field

~~~java
// Incorrect illustration: the updater will reject a non-volatile field.
static final class WrongCounter {
    int count;
}
~~~

Calling `AtomicIntegerFieldUpdater.newUpdater(WrongCounter.class, "count")` cannot create a valid updater for this field. The fix is not a cast or different generic, but redesigning the field to meet the `volatile int` condition and update protocol.

### 11.2. Confusing Integer with int

~~~java
// Incorrect illustration for AtomicIntegerFieldUpdater:
private volatile Integer count;
~~~

Even though the reference is declared volatile, the field does not have primitive type `int`. Use `volatile int`, or an atomic structure appropriate for object references if the problem truly requires a reference.

### 11.3. Confusing a static field with an instance field

~~~java
// Incorrect illustration for AtomicIntegerFieldUpdater:
private static volatile int count;
~~~

A field updater operates on individual objects. For a global counter, use a shared `AtomicInteger` or an appropriate global state mechanism.

### 11.4. Creating an updater for a private field from an external class

A class without access to a private field cannot rely on `newUpdater(Target.class, "secretCounter")` to arbitrarily update that field. The factory may be rejected at runtime. The right solution is usually to place the updater **in the owning class** and provide business methods or use a controlled public API.

### 11.5. String name errors during refactoring

If you rename a field from `"attempts"` to `"retries"` but forget to change the literal in `newUpdater`, the code may **compile successfully yet fail when initializing the updater at runtime**. IDEs and tests should verify field names in initializers. Keep the factory centralized in the declaring class to make refactoring easier.

### 11.6. Mixing an updater with a regular setter

A `reset() { count = 0; }` method running concurrently can break the counter contract, even though `count` remains volatile. If reset is allowed, you must determine whether it can occur during increments, the corresponding atomic reset mechanism (e.g., `getAndSet`), and the business meaning of in-flight updates.

### 11.7. Assuming CAS always guarantees every thread makes progress

A CAS loop can fail repeatedly under contention. There is no promise that a specific thread will acquire the right to update after a finite number of attempts. That differs from the overall algorithm making progress under a separately proven lock-free property.

### 11.8. Using an updater like a coarse-grained lock

A field updater only updates one field. It does not lock all actions of the caller and does not make multi-step operations across files, databases, or multiple objects atomic.

## 12. Performance: Memory, Contention, and Factory Overhead

### 12.1. When the number of objects is large, why is it worth considering?

Suppose a system has millions of `Node` objects, each with a `visits` counter. If each node holds its own `AtomicInteger`, the JVM may have to allocate many wrapper objects. A `volatile int visits` paired with **one static updater** can reduce the number of auxiliary objects.

Do not cite a generic “saves X bytes per node” figure for all machines: object size depends on JVM layout, compressed references, alignment, padding, and other fields. Use a profiler or allocation measurements on your actual JVM configuration.

### 12.2. FieldUpdater does not guarantee better throughput

An updater must resolve field offset/access and go through its corresponding call path. The JIT can optimize heavily, but results depend on the workload. Under heavy contention, threads still compete on CAS against **a single memory location**, which can increase cache coherence traffic and retry counts.

When updates to **the same field** are extremely frequent, switching to an updater does not eliminate contention. Consider distributing counters, batching, sharding, or `LongAdder` for statistics when an exact instantaneous snapshot is not required.

### 12.3. Do not create an updater on every call

~~~java
// Design anti-pattern illustration, not a standalone program.
void incrementInefficient() {
    AtomicIntegerFieldUpdater<Counter> updater =
        AtomicIntegerFieldUpdater.newUpdater(Counter.class, "value");
    updater.incrementAndGet(this);
}
~~~

The factory uses reflection and access checks; recreating it repeatedly is wasteful. Configuring a `private static final` updater in the class that owns the field is simpler and has lower overhead.

For benchmarks, compare identical logic and contention levels, with warm-up/JIT, multiple runs, measuring both throughput and allocation/GC as well as p95/p99 latency. A hand-rolled microbenchmark using a few `System.nanoTime()` calls can be misleading.

## 13. Testing and Observing Properly

**Checking factory validity:**

- The field is truly an instance `volatile int`.
- The field name string is exact and the declaring class is correct.
- The caller has access rights; the updater is created in the field's owner.
- The updater is not created repeatedly.

**Checking concurrent correctness:**

- Multiple threads increment the same instance and join; the result equals the expected total.
- Multiple instances share the same updater; each instance must remain independent.
- Multiple threads race with CAS to transition state from NEW: only one thread succeeds.
- No direct setter/`++` violates the protocol.
- If CAS retry is needed, the computation function can repeat without producing side effects.
- Multi-field invariants are protected by a separate mechanism.

**Checking performance:**

- Instance count and allocation difference between `AtomicInteger` and updater.
- Wait time, CAS failure count, and CPU under high contention.
- Effects of false sharing/cache-line contention and layout in the real environment.
- Tail latency and completion rate across threads; do not treat aggregate speed as a fairness guarantee for individual threads.

Stress tests can uncover bugs, but several passing runs do not prove the memory protocol is correct for all interleavings. Reason through the JMM and review every field access path.

## 14. Checklist for Choosing AtomicIntegerFieldUpdater

| Question | If the answer is “no” |
| --- | --- |
| Is the target field an **instance primitive int**? | Do not use `AtomicIntegerFieldUpdater` |
| Does the field have the **volatile** modifier? | Fix the declaration or choose another approach |
| Is the updater created in a context with access rights? | Move the factory to the owning class or change the API |
| Are there many instances and a measurable reason to reduce wrapper objects? | `AtomicInteger` is usually simpler |
| Do all field write paths share one atomic protocol? | Easy to lose updates or break the state machine |
| Is one field enough to protect the invariant? | Use a lock or an atomic immutable snapshot |
| Is the CAS retry function free of side effects? | Move side effects outside the loop |
| Are there policies for contention, overflow, and liveness? | Add them before production use |
| Has performance been measured on a real workload? | Do not claim the updater is always faster |

### Self-Check Questions

**1.** Can `private volatile int count` be used with a field updater?

**Yes**, if the updater is created in a context with access to that private field, such as a static factory inside the same class. The field **does not need to be public**.

**2.** Why is `private volatile Integer count` invalid?

Because `AtomicIntegerFieldUpdater` requires **primitive `int`**, not the `Integer` reference type. Making the reference volatile does not change the field's type.

**3.** If two threads both call `incrementAndGet` on the same field updater and the same object, will updates be lost like `count++`?

No, with updater operations following a valid protocol, the read–modify–write is atomic. If unsafe direct write paths coexist, the overall guarantee can be broken.

**4.** Can one static updater be used for two `Counter` objects?

Yes. The updater describes the target field, and each call receives a specific object. The two instances still maintain separate values.

**5.** Does using CAS to update `state` also atomically update `progress` and `timestamp` as a transaction?

No. CAS on one `int` only protects that field itself. You need a shared immutable snapshot swapped atomically or a lock for multi-field invariants.

**6.** Why shouldn't you put an API call with side effects inside the lambda of `updateAndGet`?

Because the lambda may be invoked again when CAS fails due to contention. The side effect could be repeated even though only one final update succeeds.

**7.** If a class has only a few instances and no evidence of allocation overhead, which tool should be preferred?

Usually start with `AtomicInteger` for clearer code, and consider an updater only when memory/design benefits are actually measured and verified.

**Summary:** `AtomicIntegerFieldUpdater` allows atomic updates on an **instance `volatile int` field** through a shareable updater. Use it when field/access conditions are met, update protocols are controlled, and layout/allocation savings are significant. It does not replace decisions about multi-field invariants, safe publication, side effects, contention, and overall system correctness.