# `final` Fields and Safe Initialization Guarantees in the Java Memory Model

## 1. Why Does `final` Matter for Multithreaded Programming?

When multiple threads access the same object, the first question is: **does a reading thread see the object's state as fully initialized?** Compilers, processors, and caches can perform optimizations within the bounds of the Java Memory Model (JMM). If one thread creates an object and passes the reference to another thread without a proper publication mechanism, the reading thread may lack visibility guarantees for some writes in the constructor.

`final` has two distinct meanings that should be separated:

1. **Language rule:** a `final` instance field can only be assigned during valid initialization; afterward, normal Java code cannot reassign that field. For primitive types, the field's value cannot be reassigned; for reference types, the *reference* itself cannot be reassigned.
2. **Java Memory Model guarantee:** when an object is **properly constructed**, the `final` field values set in the constructor have special visibility guarantees to other threads, even in some cases where there is no normal `happens-before` relationship for publishing the reference.

The most important condition is **not letting the `this` reference escape for another thread to use before the constructor completes**. If this is violated, you cannot rely on the `final` guarantee to claim that another thread will always see the initialized state.

Core concepts:

- **Initialization:** the constructor and initialization steps that establish an object's initial state.
- **Publication:** making a reference to an object accessible from another thread.
- **Visibility:** whether a reading thread is guaranteed to observe the writes that created the state.
- **Safe publication:** using an appropriate synchronization relationship when transferring an object to another thread, such as a `volatile` field, `synchronized`, `AtomicReference`, `BlockingQueue`, or class initialization under Java's contract.
- **Immutability:** an object's observable state does not change after initialization; merely adding `final` to a reference is not enough to make every referenced object immutable.

This lesson focuses on **general Java concurrency** and the JMM guarantees themselves; it is framework-independent.

## 2. An Intuitive Example

Consider a configuration object:

```java
final class RetrySettings {
    private final String serviceName;
    private final int maxRetries;

    RetrySettings(String serviceName, int maxRetries) {
        if (serviceName == null || serviceName.isBlank()) {
            throw new IllegalArgumentException("serviceName");
        }
        if (maxRetries < 0) {
            throw new IllegalArgumentException("maxRetries");
        }
        this.serviceName = serviceName;
        this.maxRetries = maxRetries;
    }

    String serviceName() {
        return serviceName;
    }

    int maxRetries() {
        return maxRetries;
    }
}
```

This is an **illustrative class definition** (without `main`). Both fields are assigned when the constructor runs and cannot be reassigned through normal Java code. `String` is also immutable, so this data type can be used as a simple immutable value object.

If the object is created with `new RetrySettings("catalog", 3)`, does not expose `this` during initialization, and another thread receives that reference, the special `final` guarantee ensures that the reading thread sees `serviceName = "catalog"` and `maxRetries = 3` under final-field semantics. This is a significant difference from an object with regular (non-final) fields published via a data race.

**Do not overgeneralize:** the `final` field value guarantee does not automatically guarantee that another thread will *receive the reference* in a timely manner, does not protect non-final fields, and does not make subsequent state updates on other objects safe.

## 3. Language Rules for `final` Fields

### 3.1. Assigned Once During Initialization

A **blank final instance field** is a `final` field that is not assigned at its declaration site. Java requires that the field be properly assigned on every normal completion path of the constructor, either in the constructor or in a valid instance initializer. A `final` field that already has a value from an initializer cannot be reassigned in the constructor.

```java
class Point {
    final int x;
    final int y;

    Point(int x, int y) {
        this.x = x;
        this.y = y;
    }
}
```

This is an illustrative class definition snippet. After creating `Point p = new Point(2, 5)`, `p.x = 7` is rejected at compile time. The constructor is allowed to choose values from its parameters, and all valid initialization paths must complete the field assignments.

For `static final` fields, assignment typically occurs at the declaration or in a `static` initializer. The JMM provides a separate **class initialization mechanism** to coordinate class initialization; that mechanism should not be confused with the special guarantee of **instance final fields** in a constructor.

### 3.2. `final` Does Not Mean "Deeply Immutable Object"

```java
class Bag {
    final int[] values = {1, 2};
}
```

`bag.values = new int[] {3, 4}` is invalid after initialization. However, `bag.values[0] = 99` is still valid: an **array** is a mutable object, whereas `final` only prevents reassigning the **reference to the array**.

Similarly:

```java
private final java.util.List<String> items = new java.util.ArrayList<>();
```

The list still allows `items.add(...)`. Accessing/modifying the list from multiple threads can cause a race condition or structural corruption. A `final` field does not turn an `ArrayList` into a thread-safe collection.

To design for stronger immutability, you can make defensive copies (`List.copyOf`) and avoid exposing element objects that can be mutated. `List.copyOf` creates a list that does not support structural modification through the returned reference, but it **does not automatically deep-copy** every element; mutable elements still need to be handled separately.

## 4. The JMM Special Guarantee: Constructor Completion and the Freeze Action

The JMM defines a **freeze action** associated with `final` fields at the point when the constructor that writes those fields finishes according to JLS rules. At the application level: when an object completes initialization validly, the JMM establishes special rules that allow other threads to read those `final` fields with the values set during initialization.

This is why Java commonly encourages creating **immutable value objects** using `final` fields. Even if a reference is published without synchronization, the `final` fields of a **properly constructed** object still have their own guarantee for their initialized values, provided that the other thread actually obtains that reference and the read satisfies JMM semantics.

However, there are important limitations:

- This is **not** a guarantee that every non-final field written in the constructor will also be seen correctly across an unsafe publication.
- It **does not create** a general `happens-before` relationship like using `synchronized` or `volatile` for publication.
- It **does not make a mutable object thread-safe** after the constructor finishes.
- It **does not replace** a synchronization protocol for multiple reads/writes that form a single logical operation.
- It depends on **proper construction**: not letting another thread observe `this` before the fields are initialized and the required constructor finishes.

`final` fields referencing objects/arrays also have additional visibility rules for the state of those referenced objects at initialization time. Those rules should not be interpreted as "all subsequent changes to child objects are automatically safe"; subsequent changes still require proper synchronization.

For production code, **safe publication of the entire object remains the easier policy to verify**, because it protects non-final data as well and establishes a clear sharing contract.

## 5. Properly Constructed: Do Not Expose `this` in the Constructor

**This escape** is a situation where a reference to an object under construction escapes to code that can use it before the constructor completes. Common ways this happens:

- Assigning `this` to a `static` variable or a shared holder inside the constructor.
- Registering `this` as a listener/callback that another thread can invoke immediately.
- Starting a thread inside the constructor and passing a lambda that can access fields of `this`.
- Submitting `this` to another service or executor for concurrent execution.
- Calling an overridable method from a superclass constructor; the overriding method in the subclass can see the subclass's state **before the subclass finishes initializing**, or expose the reference to another thread.

In those cases, another thread can read a field while it still holds its **default value** (`0` for `int`, `false` for `boolean`, `null` for references), because the constructor has not yet executed the assignment. No JMM mechanism allows a thread reading before an assignment has occurred to require the future value to appear.

### 5.1. Runnable Demonstration: Publishing `this` Too Early

This example uses `volatile` and two `CountDownLatch` instances to **deliberately catch the uninitialized state**. This setup produces a deterministic result and shows that even publishing the reference via `volatile` cannot "fix" publishing **before the constructor completes**.

Create `ThisEscapeDemo.java`:

```java
import java.util.concurrent.CountDownLatch;

public class ThisEscapeDemo {
    private static volatile Leaky published;
    private static final CountDownLatch referenceVisible =
            new CountDownLatch(1);
    private static final CountDownLatch finishConstructor =
            new CountDownLatch(1);

    private static final class Leaky {
        final int answer;

        Leaky() {
            published = this; // Published before answer is assigned.
            referenceVisible.countDown();

            try {
                finishConstructor.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(e);
            }

            answer = 42;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Thread builder = new Thread(Leaky::new, "builder");
        builder.start();

        referenceVisible.await();
        Leaky leaked = published;
        System.out.println("Khi constructor chưa xong: " + leaked.answer);

        finishConstructor.countDown();
        builder.join();
        System.out.println("Sau khi constructor xong: " + leaked.answer);
    }
}
```

Compile and run on Java 17+:

```bash
javac ThisEscapeDemo.java
java ThisEscapeDemo
```

Output when there is no external interrupt request:

```text
Khi constructor chưa xong: 0
Sau khi constructor xong: 42
```

**Why doesn't this depend on scheduling luck?**

1. The worker assigns `published = this` through a `volatile` field **before** assigning `answer = 42`.
2. The worker signals `referenceVisible` and then waits on `finishConstructor`, so `main` knows the reference is visible while the `answer` assignment cannot run yet.
3. `main` reads `leaked.answer`: because no assignment has occurred yet, the `int` field holds its default value `0`.
4. `main` opens the latch, allowing the constructor to execute `answer = 42` and finish.
5. `builder.join()` completion establishes a *happens-before* relationship from the builder's actions to the final read in `main`; the value `42` is observed after completion.

This example is only for **explaining the hazard and initialization conditions**. Application code should never store an object whose constructor has not finished like this. Having `volatile` in the example does not make an unassigned state valid.

### 5.2. Fix by Finishing Initialization Before Publishing

Separate the two actions completely:

```java
LeakyReplacement object = new LeakyReplacement(42);
// The constructor has returned successfully.
registry.publish(object);
```

This is **illustrative code** where `LeakyReplacement` and `registry` are application-defined APIs. What matters is that the constructor does not register `this` externally; the caller receives the completed object and only then publishes it through the registry's thread-safe mechanism. Do not assume that merely renaming variables or adding `final` to constructor parameters will prevent `this` escape.

## 6. Safe Publication: Pathways for Transferring an Object to Another Thread

A properly constructed object should be transferred through a mechanism with a clear memory relationship. Common approaches:

| Mechanism | Guarantee to Remember | Suitable When |
| --- | --- | --- |
| Assign to a `volatile` field after the constructor finishes | A volatile write and corresponding volatile read establish visibility; a complete reference is published | A current configuration is replaced by version |
| `AtomicReference.set/get` | Publishes/reads a reference with proper memory semantics; provides CAS for contended updates | Multiple readers and monolithic immutable state |
| Transfer the object via `BlockingQueue.put/take` | Concurrent collection API provides data-transfer guarantees between producer and consumer | Handing off tasks or messages |
| Write/read under the same `synchronized` block or lock with a memory contract | Releasing a lock happens-before the next acquisition of that same mechanism | Mutable data requiring consistent protection |
| Store the reference in a `static` field initialized safely with the class | Class initialization has its own synchronization rules | Singletons/constants initialized when the class is used |
| Publish before `Thread.start()` to the newly created thread | The caller's actions before `start()` happen-before the started thread's actions | Handing off data when creating a worker |

Simply storing a reference in a regular field and letting another thread read it **is not safe publication by default**. The special `final` guarantee may help some initialization data, but unsynchronized publication causes other issues: readers may not see the new reference in time, may read non-final fields unreliably, or may lack clear ordering with subsequent updates.

**Avoid a common misconception:** `volatile` on a reference field does not automatically make the **contents of a mutable object** thread-safe. A good model is to build a completely immutable object, then swap **a single reference** using a proper publication mechanism. If multiple writers compute a new value based on the old value, update contention must be resolved with CAS or locking, because a bare `current = next` can cause lost logical updates.

## 7. Complete Example: Creating an Immutable Object and Publishing Safely

Create `FinalSettingsDemo.java`:

```java
import java.util.Objects;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicReference;

public class FinalSettingsDemo {
    private static final class Settings {
        private final String service;
        private final int maxAttempts;

        Settings(String service, int maxAttempts) {
            this.service = Objects.requireNonNull(service);
            if (maxAttempts <= 0) {
                throw new IllegalArgumentException("maxAttempts");
            }
            this.maxAttempts = maxAttempts;
        }

        String service() {
            return service;
        }

        int maxAttempts() {
            return maxAttempts;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        AtomicReference<Settings> current = new AtomicReference<>();
        CountDownLatch published = new CountDownLatch(1);

        Thread builder = new Thread(() -> {
            Settings complete = new Settings("catalog", 3);
            current.set(complete); // Publish after constructor.
            published.countDown();
        }, "builder");

        builder.start();
        published.await();

        Settings snapshot = current.get();
        System.out.println("service=" + snapshot.service());
        System.out.println("maxAttempts=" + snapshot.maxAttempts());
        builder.join();
    }
}
```

```bash
javac FinalSettingsDemo.java
java FinalSettingsDemo
```

Output:

```text
service=catalog
maxAttempts=3
```

Analysis:

1. `new Settings(...)` sets the `final` fields and the constructor returns before the object is published.
2. `AtomicReference.set` transfers the complete reference under the memory contract of an atomic reference. `CountDownLatch` also establishes coordination so `main` does not read `null`.
3. `main` obtains a `snapshot` reference and reads both fields from the same immutable object.
4. The `service` field is an immutable `String` and `maxAttempts` is an `int`, so no mutable sub-state is shared through these two fields.
5. `builder.join()` ends the worker's lifecycle. In this example, both `AtomicReference` and the latch already provide data-handoff guarantees; therefore **this result is not an isolated test of the JMM `final` guarantee when a reference is published without synchronization**. It illustrates the recommended safe design pattern.

If configuration needs to change, create a **new `Settings`** and publish the new reference instead of trying to mutate `final` fields. Readers using an old snapshot continue to see that snapshot unchanged; new readers may receive the new snapshot depending on when they read.

## 8. `final` on a Mutable Reference: Bugs Can Still Happen

Create `FinalReferenceDemo.java`:

```java
public class FinalReferenceDemo {
    private static final class Box {
        final int[] values = {10, 20};
    }

    public static void main(String[] args) {
        Box box = new Box();

        System.out.println("before=" + box.values[0]);
        box.values[0] = 99;
        System.out.println("after=" + box.values[0]);
    }
}
```

```bash
javac FinalReferenceDemo.java
java FinalReferenceDemo
```

Output:

```text
before=10
after=99
```

`box.values` cannot be reassigned to a new array, but the elements inside the array can still change. If multiple threads read/write `values[0]` without proper synchronization, `final` on `values` does not prevent a data race.

Ways to improve the design:

- Use truly immutable types, such as a `record` containing primitive fields or immutable `String` fields.
- For mutable arrays, make defensive copies when accepting them in the constructor and when returning them if needed to prevent callers from keeping a reference and mutating it behind your back.
- For collections, use unmodifiable copies and check whether the elements inside are mutable.
- If the object truly must change at runtime, use proper synchronization around **all read/write paths** of that state rather than relying on `final` as a substitute for locks.

This is the distinction between an **immutable object**, an **effectively immutable object** (created and never modified afterward in practice), and a **final reference to a mutable object**. Only the first directly provides a clear immutability model from the type's contract. "Effectively immutable" can be very useful, but you must ensure no update paths execute after publication.

## 9. How Does a `final` Field Differ from `volatile`?

| Aspect | `final` instance field | `volatile` field |
| --- | --- | --- |
| Can it be reassigned in normal Java after initialization? | No | Yes |
| Primary use | Stable initial state and immutable design | Values updated/published across threads |
| Key JMM guarantee | Final-field initialization and freeze rules when properly constructed | Visibility and memory ordering of volatile operations |
| Does it make multiple fields a single transaction? | No | No |
| Does it make the referenced object immutable? | No | No |
| Does it replace a monitor when updating multiple related fields? | No | No |

A field can be both `static final` and hold a **reference to a mutable object**, such as `static final AtomicInteger COUNT`. The `COUNT` reference does not change, but the internal state of `AtomicInteger` can change through its thread-safe methods. You must distinguish the properties of the **reference variable** from the properties of the **referenced object**.

Similarly, `final int[] values` does not make array elements `final`; `volatile int[] values` does not make individual array elements `volatile`. These are two classic examples of how guarantees at the **reference** level do not automatically propagate to all inner fields/elements.

## 10. When Are Final-Field Initialization Guarantees Not Enough?

### 10.1. Other Fields Are Not `final`

```java
class MixedState {
    final int id;
    int status;

    MixedState(int id) {
        this.id = id;
        this.status = 1;
    }
}
```

For a properly constructed object whose reference is **published unsafely**, `final` rules protect the `id` field within their special scope; you cannot use those rules to claim that the non-final `status` will always be seen with the value assigned by the constructor. Safe publication simplifies the contract for **both fields**.

### 10.2. Updates Occur After the Constructor

Suppose `Settings` holds a `final List<String> endpoints` and multiple threads call `endpoints.add(...)`. The initialization guarantee of the final field does not tell you whether threads reading the list will see newly added elements, nor does it prevent concurrent updates from corrupting the list.

If you want controlled state changes, either create a new snapshot and swap the reference atomically, or protect the mutable object with synchronization.

### 10.3. `this` Escape Occurs

If `this` is registered before the constructor completes, another thread may read default values while the final field has not yet been assigned, as in `ThisEscapeDemo`. You cannot "rescue" that behavior merely by changing the field to `volatile` or adding `Thread.sleep(...)` hoping the constructor finishes first. You must fix **when publication happens**.

### 10.4. Updating a Group of Related Variables

Two `final` fields cannot change after the constructor, which fits when both together form an **immutable state**. However, if business data always requires updating a pair of values together, changing both fields to `volatile` and updating them separately will not preserve invariants. Choose an immutable snapshot published atomically, or lock the same monitor for both updates and reads.

### 10.5. Reflection, Serialization, and Special Mechanisms

Reflection, deserialization mechanisms, native/unsafe access, or bytecode instrumentation can intervene in initialization through paths unlike a normal Java constructor. Modifying final fields through special mechanisms involves complex rules and limitations that may depend on the JDK and runtime. **Do not design concurrent protocols around mutating final fields after the constructor.** In normal Java applications, create a new object and publish the new reference.

## 11. Designing Constructors So Objects Are Hard to Observe Half-Built

Several design habits help ensure `final` actually delivers value:

1. **Validate inputs before publishing:** check for `null`, value ranges, and consistency across parameters inside the constructor or factory.
2. **Do not pass `this` to another thread in the constructor:** avoid writing to registries, firing events, registering callbacks that may run immediately, or `new Thread(() -> use(this)).start()`.
3. **Do not call overridable methods from a constructor** when those methods might use subclass state or expose `this`. Use `private`/`final` methods for internal initialization logic when appropriate.
4. **Watch out for mutable fields referenced by `final`:** make defensive copies, avoid returning mutable arrays or collections directly, or establish an explicit synchronization contract.
5. **Prefer small, complete, immutable objects:** the constructor sets all related values; subsequent operations are read-only.
6. **Publish after the constructor returns:** use `volatile`, atomic references, concurrent collections, or monitors. In a factory, finish constructing the object before placing it into a cache/registry.
7. **Preserve consistency on updates:** replace the entire snapshot in one atomic action or use locks for mutable state; a final field does not protect other resources just because they belong to the same object.

### Factory Example Instead of Registering `this` During Construction

Instead of a self-registering constructor:

```java
// Illustrative example of code organization, not a standalone program.
final class Listener {
    private final String name;

    private Listener(String name) {
        this.name = name;
    }

    static Listener createAndRegister(String name, Registry registry) {
        Listener complete = new Listener(name);
        registry.register(complete);
        return complete;
    }
}
```

`Registry` is an application-defined interface; `register` must be thread-safe if accessed by other threads. The architectural change is that **the constructor only handles initialization**, while the factory registers only after the object is complete.

Making the constructor `private` is not a mandatory requirement for final-field semantics, but it helps the API prevent callers from invoking the constructor and unintentionally leaking `this`.

## 12. Distinguishing Guarantees from Observations in Concurrency Experiments

When testing a JMM example, you should not write a busy-wait loop on a non-volatile field and conclude: "I ran it a million times and always saw the right result, so publication is safe." The JMM permits many behaviors that a specific machine and JVM version might **not easily exhibit**. A program with a data race can appear correct across many runs and fail when optimizations, CPUs, or load change.

Sound ways to reason:

- If the design requires reader threads to always receive a complete object, **prove the publication path has happens-before**, rather than only checking output.
- If the design requires the object not to change after initialization, **check for mutable state leaks**: are there arrays, collections, builders, listeners, or references to mutable objects?
- If a constructor could be accessed mid-execution, use latch coordination in a lesson demo to **prove the unassigned state is real**, as in `ThisEscapeDemo`. That does not prove the bug always occurs at the same frequency in an uncoordinated program.
- If you want to verify correctness of multi-field updates, create consistent snapshots under a lock or use immutable snapshots, and clearly document the publication point.
- Use Java Flight Recorder, thread dumps, or stress tests to find real issues when needed, but do not treat one specific execution schedule as the definition of the Java Memory Model.

## 13. Common Misconceptions

**"A `final` field makes every field of an object thread-safe."** False. It provides a specific guarantee for `final` initialization data; mutable/non-final fields still need appropriate synchronization.

**"Simply declaring `final List<?>` gives you an immutable list."** False. `final` locks the reference, not modifications to the collection's contents.

**"It is fine to register `this` in a constructor because all fields are `final`."** False. Another thread can read the object before the assignments actually happen, and final-field guarantees require proper construction.

**"Using `volatile` when publishing the reference hides an unfinished constructor."** False. If the reference is published too early, another thread can see default values. `volatile` only applies memory guarantees according to the actual order of operations that occurred.

**"An object with `final` fields does not need safe publication."** Too broad a conclusion. `final` provides a special guarantee for those fields if the object is properly constructed, but it does not solve the entire lifecycle or related data. Safe publication remains the recommended policy when transferring objects between threads.

**"Using `static final` is identical to an instance `final`."** Not quite. `static final` is tied to class initialization; the JVM ensures class initialization synchronization via its own mechanism. If a `static final` field holds a mutable object, that object's internal state still needs coordination when modified.

**"A `record` is always deeply immutable."** Incorrect. Record components are stored in `final` fields, but if a component is an array or mutable object, its contents can still change. A `record` is a good choice for value objects when its components are also designed to be immutable or defensively copied appropriately.

## 14. Self-Check Questions

**Question 1.** A class has `final int value` assigned in its constructor, the object is properly constructed, and a reference to it is eventually read by another thread through an unsynchronized publication path. What is the special guarantee of `final`?

**Answer:** When another thread obtains the reference and reads the `final` field according to JMM semantics, the `final` values assigned during proper construction have a special visibility guarantee. This does not guarantee that the reading thread will receive the reference in a timely manner, nor does it extend all guarantees to non-final fields.

**Question 2.** Why does `final int[] values` not guarantee that `values[0]` is safe when multiple threads modify it?

**Answer:** `final` only prohibits reassigning the `values` reference; the array's contents remain mutable. Concurrent element reads/writes can still data race.

**Question 3.** In a constructor, an object assigns `shared = this` before assigning `final int answer = 42` (or before assigning a blank final in the constructor). Can a reader see `answer = 0`?

**Answer:** Yes. The reader can run while the final value has not yet been assigned. Early publication violates the proper construction condition.

**Question 4.** Should you use `volatile` for every field that is only set once and never changes after the constructor?

**Answer:** You do not need to do that by default. `final` fields express an immutability contract and have their own initialization guarantee. When transferring the object between threads, choose a safe publication mechanism for the whole object and use `volatile`/locks if state actually needs to be updated.

**Question 5.** `AtomicReference<Config>` holds an immutable `Config`. Multiple writers update to a new version based on the old version using plain `set`. Can updates be lost?

**Answer:** Yes. Each `set` is atomic, but two writers can read the same old version and overwrite each other. If each update depends on the previous state, use `updateAndGet`/CAS with a side-effect-free transformation function, or use appropriate locking.

**Question 6.** A `record Config(int limit, List<String> hosts)` has been initialized. Is it guaranteed to be deeply immutable?

**Answer:** No. The `hosts` reference field is `final`, but the `List` itself may be mutable. The constructor should create an unmodifiable copy (`List.copyOf`) when the contract requires immutability and consider the types of the elements inside.

**Question 7.** Why is calling an overridable method from a superclass constructor dangerous even when no new thread is created?

**Answer:** The subclass's overriding method can run before the subclass's fields finish initializing, causing it to observe default state. If the method also publishes `this`, another thread can also observe an incomplete object.

## 15. Summary

**`final` is a commitment about initialization and not reassigning a field**, while also providing a special guarantee in the Java Memory Model so that the initialized values of `final` fields are observed correctly when an object is validly constructed. The foundational requirement is that **the constructor completes without exposing `this` for another thread to use beforehand**.

A design that is easy to keep correct is to build immutable objects with `final` fields, validate all invariants in the constructor, publish only after completion via a thread-safe mechanism, and then read the object as a snapshot. If an object contains mutable state, a `final` reference does not replace locks or concurrent structures. Distinguishing **proper construction**, **safe publication**, and **safe concurrent updates** is the key to applying the JMM accurately, avoiding both initialization visibility bugs and race conditions that arise later.
