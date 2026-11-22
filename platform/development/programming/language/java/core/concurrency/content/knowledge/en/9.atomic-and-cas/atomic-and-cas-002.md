# AtomicReference and Updating Object State in Java Concurrency

## 1. Goal: Updating the State of an Entire Object with a Single Atomic Point

In Java, a business operation may need to update **multiple related fields** at the same time. For example, a reservation needs to decrease `available` and increase `reserved` so that the invariant `available + reserved = total` always holds. If two threads read and then write each field individually, they can cause lost updates or expose a partial state.

`AtomicReference<V>` holds **an object reference** that can be read, written, or replaced atomically. When combined with **immutable object state** and a **compare-and-set (CAS)** operation, we can turn changing multiple values into **a single reference swap to a new snapshot**. A reader that grabs a reference will observe a consistent version of the state.

Lesson objectives:

- Understand which **reference** `AtomicReference<V>` actually protects, and why it does not automatically make the pointed-to mutable object thread-safe.
- Distinguish `get()`, `set()`, `getAndSet()`, `compareAndSet(expected, update)`, `getAndUpdate()`, `updateAndGet()`, and the accumulate methods.
- Explain the CAS loop, reference identity (`==`), retrying under contention, and the **linearization point** of a successful update.
- Know when to use an immutable record/immutable class, why an update function must be treated as **side-effect-free**, and how to preserve multi-field invariants.
- Reproduce two threads competing over a snapshot, proving that a failed CAS is retried instead of causing a lost update.
- Recognize ABA, stale snapshots, mutable nested objects, external side effects, starvation/contention, and multi-resource transaction boundaries.
- Choose among `AtomicReference`, `AtomicInteger`/`AtomicLong`, `LongAdder`, `synchronized`, and `Lock` depending on the problem.

**Scope:** Java SE/JVM concurrency. Examples use **Java 17+**, compatible with records and `java.util.concurrent.atomic`. No frameworks are used.

## 2. What Does AtomicReference Guarantee?

Declaration:

~~~java
import java.util.concurrent.atomic.AtomicReference;

AtomicReference<String> state = new AtomicReference<>("NEW");
String observed = state.get();
state.set("READY");
~~~

An `AtomicReference` object contains a reference slot; in the example, the reference slot initially points to `"NEW"`, and is then replaced with a reference to `"READY"`. In the Java Memory Model, `get()` has volatile read semantics; `set()` has volatile write semantics. CAS is atomic with memory effects according to `VarHandle.compareAndSet`.

We can visualize it as:

~~~text
           AtomicReference<State>
           ┌─────────────────────┐
           │ current ────────────┼────────► State v1 (immutable)
           └─────────────────────┘            available=5
                                              reserved=0

A thread creates a complete State v2 (3,2) and succeeds with CAS:

           AtomicReference<State>
           ┌─────────────────────┐
           │ current ────────────┼────────► State v2 (immutable)
           └─────────────────────┘            available=3
                                              reserved=2

Readers already holding v1 continue to see v1; new readers may obtain v2.
There is no point at which a reader sees half of v1 plus half of v2
if it reads one snapshot and the snapshot is truly immutable.
~~~

**Core limitation:** AtomicReference only protects **reading/replacing the reference**; it does not automatically lock the object or any fields inside it. The following example still has a data race:

~~~java
class MutableState {
    int count;
}

AtomicReference<MutableState> ref =
        new AtomicReference<>(new MutableState());

// Two threads call simultaneously:
ref.get().count++; // NOT atomic, can cause lost update
~~~

`ref.get()` returns the reference with atomic/volatile semantics, but `count++` mutates the **same mutable object** without protection. There is no CAS on the reference in this expression. Wrapping a mutable object in `AtomicReference` is **not** an automatic transformation into thread-safety.

## 3. From Individually Updated Fields to an Immutable Snapshot

Consider an inventory state with two fields:

~~~java
int available = 5;
int reserved = 0;
~~~

Every valid `reserve(2)` operation must decrease available and increase reserved, preserving the invariant that their sum equals 5. If the two fields are updated separately:

~~~java
available -= 2;
reserved += 2;
~~~

a reader could step in between and see available already decreased while reserved has not yet increased. If there are multiple writers, both could also read the same old values and overwrite each other.

Solution: use an immutable record containing **the entire state that needs to be consistent**:

~~~java
record Stock(int available, int reserved) {
    Stock {
        if (available < 0 || reserved < 0) {
            throw new IllegalArgumentException("negative stock");
        }
    }
}
~~~

Once created, the record has no setters for `available` or `reserved`; both are primitive components and there are no mutable nested references. An update creates a **new record**, then uses CAS to swap the reference:

~~~java
AtomicReference<Stock> stock =
        new AtomicReference<>(new Stock(5, 0));

Stock before = stock.get();
Stock after = new Stock(before.available() - 2,
                        before.reserved() + 2);

boolean ok = stock.compareAndSet(before, after);
~~~

If `ok == true`, the update of the entire pair has been published atomically. If `ok == false`, the state may have been changed by another thread: you must not assume the update succeeded, and must instead **re-read and recompute** based on the new version.

To preserve multi-field invariants, the logic that constructs the new state must guard the conditions before CAS. For instance, do not construct a negative Stock when available is insufficient. An immutable constructor is an additional layer of defense, but it does not replace checking business conditions and updating on the latest snapshot.

## 4. compareAndSet(expected, update): Comparing Reference Identity

The most important method:

~~~java
boolean updated = ref.compareAndSet(expected, replacement);
~~~

Rules of `AtomicReference.compareAndSet`:

1. Read the current reference of the atomic reference.
2. If the current reference **is the exact same object** as `expected` under `==`, replace it with `replacement` in a single atomic operation and return `true`.
3. If the current reference **is not the same object**, leave the reference unchanged and return `false`.
4. Correctness of the operation is guaranteed by the API's memory semantics; no extra `synchronized` is needed just to protect that CAS itself.

**CAS compares identity; it does not call `equals()` to compare content values.** For records, `equals()` may consider two records with identical fields equal, but `compareAndSet` still treats them as **two different references**.

Example:

~~~java
AtomicReference<String> text =
        new AtomicReference<>(new String("READY"));

String equalButDifferent = new String("READY");
System.out.println(text.get().equals(equalButDifferent)); // true
System.out.println(text.compareAndSet(equalButDifferent, "DONE")); // false
~~~

This is a Java snippet inside a method, not a standalone `main` program. The two strings created with `new String(...)` have equal contents but different references. Using `String` to illustrate CAS does not mean all string comparisons in business logic should use `==`; ordinary string values still need `equals()`.

### Linearization point

A successful CAS is a point in the concurrent execution where the entire reference swap can be viewed as happening **at a single logical instant**. Threads contending on the same atomic reference can see either the before version or the after version, but never a partial reference replacement.

With an immutable snapshot, the successful CAS point is the point that **publishes** the new version. If a state contains two fields constructed consistently beforehand, publishing just one reference lets readers obtain a **complete version** without locking.

### Why not use get() followed by set()?

~~~java
State old = current.get();
State updated = transform(old);
current.set(updated); // risk of overwriting an update from another thread
~~~

`get()` and `set()` are **individual** atomic accesses. If threads A and B both read the same `old`, both can compute a new version and call set; the later set can overwrite the valid update from the earlier thread. This is a **lost update** at the object-state level.

`getAndSet(newState)` also only **replaces unconditionally** and returns the old reference; it is unsuitable if the new version is computed from an old snapshot and concurrent updates must not be lost. To protect read–modify–write, use a CAS loop or `updateAndGet` with a pure update function.

## 5. A Correct CAS Loop: Read, Compute, Attempt Swap, Retry on Failure

Basic pattern:

~~~java
while (true) {
    State before = state.get();       // a current snapshot
    State after = transform(before);  // construct a new version
    if (state.compareAndSet(before, after)) {
        return;                       // update succeeded
    }
    // Another thread changed state: re-read and recompute.
}
~~~

Here `State` and `transform` are application types/functions; this snippet describes an algorithm inside a method, **not a standalone runnable program**.

Things to watch out for in a CAS loop:

- `transform(before)` must produce a valid state based on the **`before` snapshot**.
- If there is a **business failure condition** (out of stock, insufficient quota), check the condition on **each re-read snapshot**, not only on the first attempt.
- CAS returning false is not an exception; it is a normal contention outcome. Never return success when CAS returns false.
- Under contention, a thread may have to retry multiple times. AtomicReference does not promise that every caller finishes in a bounded number of iterations; **lock-free at the algorithm level** does not mean **wait-free for each individual thread**.
- The update function should not perform I/O, emit events, write files, increment auxiliary metrics, or mutate observable state. If CAS fails, the function may be invoked again.
- If the operation can throw an exception (validation, `Math.addExact`), the exception should occur **before CAS** and leave no partial update in shared state.
- A successful CAS only protects the state inside this atomic reference. If you swap state and also update another database/queue, those two actions **do not automatically become a single transaction**.

## 6. Standalone Example 1: Two Threads Updating the Same Snapshot Without Lost Updates

To reproduce contention deterministically, the program has two threads **both read the initial version** before letting them attempt CAS. One thread wins the first CAS; the other thread must fail **exactly once**, re-read, compute a new version, and then succeed. The outcome is determined by latches, without relying on sleep intervals.

Save the file **AtomicReferenceCasDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class AtomicReferenceCasDemo {
    record State(int count, int revision) {}

    private static final AtomicReference<State> state =
            new AtomicReference<>(new State(0, 0));
    private static final AtomicInteger failedCas = new AtomicInteger();

    public static void main(String[] args) throws InterruptedException {
        CountDownLatch bothRead = new CountDownLatch(2);
        CountDownLatch beginCas = new CountDownLatch(1);

        Runnable increment = () -> {
            State before = state.get();
            bothRead.countDown();

            try {
                beginCas.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }

            while (true) {
                State after =
                        new State(before.count() + 1, before.revision() + 1);
                if (state.compareAndSet(before, after)) {
                    return;
                }
                failedCas.incrementAndGet();
                before = state.get();
            }
        };

        Thread a = new Thread(increment, "cas-a");
        Thread b = new Thread(increment, "cas-b");
        a.start();
        b.start();

        bothRead.await();
        beginCas.countDown();
        a.join();
        b.join();

        State result = state.get();
        System.out.println("count=" + result.count());
        System.out.println("revision=" + result.revision());
        System.out.println("failedCAS=" + failedCas.get());
    }
}
~~~

Compile and run on JDK 17+:

~~~bash
javac AtomicReferenceCasDemo.java
java AtomicReferenceCasDemo
~~~

Output when there is no external interrupt request:

~~~text
count=2
revision=2
failedCAS=1
~~~

**Why this is deterministic:**

1. `bothRead` ensures both A and B have fetched the same initial `State(0,0)` reference before `beginCas` is opened.
2. Both construct their own `State(1,1)` and attempt to swap **the same initial expected object**.
3. Only **one** CAS can replace the initial reference with the new version. The other thread's CAS returns false, incrementing `failedCas` exactly once.
4. The losing thread reads the newly published `State(1,1)` version, constructs `State(2,2)`, and succeeds with CAS; there are no other contenders updating.
5. `join()` waits for both threads to finish; operations performed before a worker terminates are properly observed by main after join. The final result reflects both increments, with no lost update.
6. This is a **logically correct** CAS example. It does not prove an application should retry unboundedly in every workload, and it is not a speed benchmark.

Observation: If the CAS loop were replaced with `state.set(after)`, both A and B could write `State(1,1)` and lose one increment. The essence of this pattern is tying the version that was read to the right to replace it **only if that version is still current**.

## 7. Standalone Example 2: Updating Multiple Fields of Object State

Problem: maintain the invariant `available + reserved = initialStock` within **a single JVM**. Each reservation must check that enough stock is available and then move the amount from available to reserved. If multiple threads arrive concurrently, CAS must protect the entire **check + update**.

Save the file **AtomicInventoryDemo.java**:

~~~java
import java.util.concurrent.atomic.AtomicReference;

public class AtomicInventoryDemo {
    record Stock(int available, int reserved) {
        Stock {
            if (available < 0 || reserved < 0) {
                throw new IllegalArgumentException("negative stock");
            }
        }
    }

    private final AtomicReference<Stock> current;

    public AtomicInventoryDemo(int initial) {
        if (initial < 0) {
            throw new IllegalArgumentException("negative initial stock");
        }
        current = new AtomicReference<>(new Stock(initial, 0));
    }

    public boolean reserve(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }

        while (true) {
            Stock before = current.get();
            if (before.available() < amount) {
                return false;
            }

            Stock after = new Stock(
                    before.available() - amount,
                    Math.addExact(before.reserved(), amount));

            if (current.compareAndSet(before, after)) {
                return true;
            }
        }
    }

    public Stock snapshot() {
        return current.get();
    }

    public static void main(String[] args) {
        AtomicInventoryDemo inventory = new AtomicInventoryDemo(5);

        System.out.println("reserve2=" + inventory.reserve(2));
        System.out.println("reserve4=" + inventory.reserve(4));
        System.out.println("reserve1=" + inventory.reserve(1));

        Stock result = inventory.snapshot();
        System.out.println("available=" + result.available());
        System.out.println("reserved=" + result.reserved());
        System.out.println("total=" +
                (result.available() + result.reserved()));
    }
}
~~~

Run:

~~~bash
javac AtomicInventoryDemo.java
java AtomicInventoryDemo
~~~

Output:

~~~text
reserve2=true
reserve4=false
reserve1=true
available=2
reserved=3
total=5
~~~

**Why is reserve thread-safe on the same instance?**

- The `Stock` record has only two primitive components, so every instance is truly immutable.
- `reserve` reads **one snapshot**, checks the sufficient-stock condition, and creates a new snapshot with an unchanged total.
- If another thread changed current before CAS, the attempt returns false and the loop **re-reads**; it never reserves based on a stale snapshot.
- A successful CAS publishes **both available and reserved** in a single reference swap; a reader using a local `Stock` sees the same version of both fields.
- `snapshot()` obtains a consistent reference at the time of reading, but **does not lock future updates**. If a caller calls `snapshot()` multiple times, each call may see a different version.
- `Math.addExact` detects overflow when adding to reserved; in normal valid states with small stock counts, it raises no error.
- The main example calls sequentially so stdout is deterministic. The same `reserve` code can be called concurrently by multiple threads; the invariant guarantee applies only if **all** changes to Stock go through that instance's proper protocol.

**Important boundary:** `AtomicReference` here is not a transaction across multiple processes, databases, or other services. It does not manage reservation timeouts, idempotency, or external transactions. Those are separate business requirements.

## 8. Convenience Methods for Updating Based on Previous State

`AtomicReference` provides these common APIs:

| API | Meaning | Return value |
|---|---|---|
| `get()` | Read the current reference with volatile read semantics | Current reference |
| `set(next)` | Write a new reference with volatile write semantics | `void` |
| `lazySet(next)` | Write a new reference with release semantics | `void` |
| `getAndSet(next)` | Replace unconditionally and atomically | Reference before replacement |
| `compareAndSet(expect, next)` | Replace if current reference `== expect` | `boolean` success/failure |
| `compareAndExchange(expect, next)` | Replace if current reference `== expect` | Actual reference observed during the attempt (witness) |
| `updateAndGet(fn)` | Compute from current state and update atomically | **New** reference after update |
| `getAndUpdate(fn)` | Compute from current state and update atomically | **Old** reference before update |
| `accumulateAndGet(x, fn)` | Combine current and `x` with a two-argument function | **New** reference after update |
| `getAndAccumulate(x, fn)` | Same as above, but returns the previous version | **Old** reference |

The function-based methods use atomic mechanisms; under contention, **the function may be invoked repeatedly**. Therefore avoid side effects in the function and do not assume the function runs only once per API call.

Example with an immutable record:

~~~java
record Versioned(String text, int revision) {}

AtomicReference<Versioned> ref =
        new AtomicReference<>(new Versioned("draft", 0));

Versioned old = ref.getAndUpdate(s ->
        new Versioned(s.text(), s.revision() + 1));

Versioned current = ref.updateAndGet(s ->
        new Versioned("published", s.revision() + 1));
~~~

This is a snippet inside a method. When only one thread executes these lines, `old` is `Versioned("draft", 0)` and `current` is `Versioned("published", 2)`. The difference is the **return value** of `getAndUpdate` versus `updateAndGet`. Under concurrency, the outcome and timing of each version follow the order of successful updates, and cannot be inferred from statement order across different threads.

### When is using `set` or `getAndSet` appropriate?

`set(next)` is appropriate when the caller intentionally **publishes a completely new state without needing to preserve concurrent updates**, such as updating an immutable configuration snapshot with a "latest version replaces old version" policy. `getAndSet(next)` is useful when you need to atomically **replace and retrieve the old reference** at the same time. However, if `next` is derived from the current state and other updates must not be lost, use CAS or an atomic update function.

## 9. Standalone Example 3: updateAndGet and getAndUpdate APIs

Save the file **AtomicReferenceUpdateDemo.java**:

~~~java
import java.util.concurrent.atomic.AtomicReference;

public class AtomicReferenceUpdateDemo {
    record Config(String mode, int revision) {}

    public static void main(String[] args) {
        AtomicReference<Config> ref =
                new AtomicReference<>(new Config("draft", 0));

        Config before = ref.getAndUpdate(s ->
                new Config(s.mode(), s.revision() + 1));

        Config after = ref.updateAndGet(s ->
                new Config("published", s.revision() + 1));

        System.out.println("old=" + before.mode()
                + "/" + before.revision());
        System.out.println("new=" + after.mode()
                + "/" + after.revision());
        System.out.println("current=" + ref.get().revision());
    }
}
~~~

Run:

~~~bash
javac AtomicReferenceUpdateDemo.java
java AtomicReferenceUpdateDemo
~~~

Output in this single-threaded sequence:

~~~text
old=draft/0
new=published/2
current=2
~~~

Using the update methods makes code concise, but **does not change the purity rule** for the state-transition function. In an application with contention, the lambda can be re-executed and create multiple candidate objects; only one update per successful call is published.

## 10. Why Must the Update Lambda Be Side-Effect-Free?

**Incorrect** example:

~~~java
ref.updateAndGet(old -> {
    sendEmail("State is changing"); // WRONG: side effect may repeat
    return new State(old.value() + 1);
});
~~~

This snippet illustrates code inside a method with `ref` and application-defined types/methods. Suppose thread A computes a candidate from version 1, but thread B publishes version 2 before A's CAS. A must **retry** the lambda with version 2. `sendEmail` may already have run on the first attempt **even though that attempt's candidate was never published**, and then run a second time. The result is duplicate events or effects that do not match the state.

Principled solution:

1. The lambda only computes and returns a **candidate immutable state**, with no I/O and no external mutation.
2. After CAS succeeds, the caller can perform the side effect **once on the success branch**.
3. If you require **atomically** coupling a side effect with a state transition (for example, updating a DB and sending a notification strictly once), AtomicReference is **not enough**: you need a protocol at the layer owning the resource (transaction/outbox/idempotency or an equivalent mechanism), rather than assuming "CAS then send" is atomic across two systems.

Even a post-CAS side effect can still fail: the in-memory update succeeds, while sending the notification fails. Durability, retry, and idempotency requirements must be designed separately.

### Exceptions in the update function

If the update function throws an exception **before CAS**, that update call fails and does not publish the candidate of the current attempt. However, if the function already performed a side effect before throwing, that side effect **does not automatically roll back**. Hence purity helps both correctness and error recovery.

## 11. Snapshot References, Immutability, and Nested Structures

An immutable snapshot must be genuinely immutable across the scope of data that readers rely on.

**Unsafe if only the outer layer is a record:**

~~~java
import java.util.List;

record Settings(List<String> features) {}

List<String> mutable = new java.util.ArrayList<>();
mutable.add("search");

AtomicReference<Settings> ref =
        new AtomicReference<>(new Settings(mutable));

// Another thread can still do:
mutable.add("billing");
~~~

The record prevents changing the `features` reference, but the `List` inside is still mutable and the caller holds a reference to it. A reader receiving `Settings` through AtomicReference may see the List modified concurrently after publication.

**Create an appropriate defensive copy:**

~~~java
import java.util.List;

record Settings(List<String> features) {
    Settings {
        features = List.copyOf(features);
    }
}
~~~

`List.copyOf` creates an unmodifiable list at the container level. If the elements are **immutable Strings**, this makes the state appropriate. If the elements are mutable objects, `List.copyOf` does not automatically make the elements immutable; deeper copying or an immutable element design is required.

Key takeaways:
- A safe reference swap **does not automatically isolate mutations on old objects**.
- A reader holding an old snapshot can still use it after current points to a new snapshot; the design must ensure old snapshots **are not mutated**.
- To update a complex Map/List, typically create a new immutable copy and CAS-publish it rather than mutating the old Map/List in place.
- Copy-on-write fits **read-heavy, write-light** workloads; if the state is large and updated continuously, copying can be expensive in CPU/heap/GC.

## 12. Multi-Field Invariants: Snapshot Atomicity Does Not Extend to Other Resources

With an immutable `State(a,b,c)`, CAS swapping the reference makes all three fields appear together in one version. But we must distinguish:

| Scope | Can AtomicReference guarantee it? | Notes |
|---|---|---|
| Swapping one reference from old to new | **Yes** | CAS provides the atomic point. |
| Preserving invariants of fields within **the same immutable state** | **Yes, if transform is correct** | Every candidate must be valid and all writers must follow the protocol. |
| Swapping two different AtomicReferences simultaneously | **Not automatically** | A reader can interleave between two separate CAS operations. |
| Mutations inside an already-published mutable object | **No** | Requires a separate mechanism or an immutable design. |
| Writing files, databases, or network atomically with CAS | **No** | Outside the scope of a JVM atomic reference. |
| Guaranteeing an individual writer will not starve | **No** | A CAS loop may retry continuously under contention. |
| Guaranteeing state durability across a process crash | **No** | AtomicReference lives in process memory. |

If an invariant spans multiple objects that cannot be combined into a single immutable snapshot, `synchronized`/`Lock` may be easier to reason about; across multiple processes or external storage, a transaction/consistency system at the data source is required.

## 13. ABA: Reference Changed A → B → A Without CAS Detecting It

CAS returns true if **current reference `== expected`**. It does not answer the question "between the time I read and the time I updated, **has this object ever changed**?".

Example:

~~~text
T1 reads expected = reference A
T2 CAS A -> B             (state changes)
T2 CAS B -> A             (points back to the exact same old object A)
T1 CAS expected A -> C    (succeeds because current == A)
~~~

T1 does not detect the A→B→A cycle, even though the intervening actions may affect the logic of the data structure. This is the **ABA problem**, which requires special attention in lock-free structures managing nodes, stacks, freelists, or object lifecycles.

**Do not confuse ABA with two objects that are `equals()`:** if T2 replaces A with an object A2 that has the same content but a **different reference**, T1 holding A will fail CAS. ABA is dangerous when current returns to **the exact same old reference A**.

### Solutions when change history matters

`AtomicStampedReference<V>` holds **a (reference, integer stamp) pair** and allows CAS on both the reference and the stamp:

~~~java
import java.util.concurrent.atomic.AtomicStampedReference;

AtomicStampedReference<String> stamped =
        new AtomicStampedReference<>("A", 0);

int[] holder = new int[1];
String current = stamped.get(holder);  // read a consistent pair
int version = holder[0];

boolean changed =
        stamped.compareAndSet(current, "B", version, version + 1);
~~~

This is a snippet used inside a method. `get(holder)` returns the reference and fills the corresponding stamp into `holder[0]`. `compareAndSet` succeeds only when **both reference and stamp** match the expected values. Incrementing the stamp on every transition helps detect A→B→A even when the reference returns to A. However, an integer stamp has a finite range and can overflow/wrap around; wraparound risk must be evaluated in long-running workloads.

`AtomicMarkableReference<V>` stores `(reference, boolean mark)`, which fits certain algorithms that need a mark bit, but a boolean mark cannot replace a general-purpose version counter.

**When is ABA less of a concern?** In the immutable-state pattern where **every update creates a new object and never re-publishes an old object**, the same old identity is unlikely to reappear under that protocol. Even so, do not deduce from this that all CAS algorithms are immune to ABA: explicitly examine reference reuse and the structure's invariants.

## 14. Updating Object State and the Java Memory Model

Synchronization guarantees are not "accidental thanks to CPU caches". The Java API specifies memory effects:

- `AtomicReference.get()` has volatile read semantics.
- `AtomicReference.set(...)` has volatile write semantics.
- `compareAndSet(...)` has memory effects according to `VarHandle.compareAndSet` and performs the reference update atomically.
- When a writer initializes a candidate object **before** successfully publishing it, a reader reading the published reference properly can observe the prior initialization writes via happens-before.
- Final fields in an immutable object also have their own JMM initialization rules; however, you should not rely on final to allow mutable nested objects to be modified arbitrarily after publication.

A helpful model:

~~~text
Writer:    new State(complete fields)
                  │
                  ▼
           CAS current old → new (publish)
                  │
           proper synchronization
                  │
                  ▼
Reader:    State snapshot = current.get()
                  │
                  ▼
           read fields from the exact same snapshot
~~~

Readers **do not need a lock** to read fields of a safely published immutable state. However, a reader may observe **an old or a new version** depending on interaction order; it is not guaranteed to always see a future update before that update exists.

If a reader calls `current.get()` twice and reads field A from the first version and field B from the later version, it can assemble a mixed snapshot on its own. Keep **one local reference**:

~~~java
State snapshot = current.get();
int a = snapshot.a();
int b = snapshot.b();
~~~

This illustration assumes State has accessors a()/b(). Both fields are read from **the exact same immutable object**. This differs from "locking all updates" and still lets writers operate concurrently.

## 15. CAS Failures, Retries, and Performance Cost

AtomicReference is often very effective when state changes relatively infrequently or the transformation is fast; however, **every failed CAS** can waste computation and the newly allocated candidate object.

Sources of cost:

1. **Contention:** many writers read the same reference and compete to commit.
2. **Allocation:** each attempt may allocate a new immutable State object; failed candidates become garbage.
3. **Retry:** transform may run multiple times, especially when using updateAndGet/functional methods.
4. **Cache coherence:** multiple cores contend on a single shared update location.
5. **Read/write balance:** copying a very large immutable Map/Tree on every update can cost more than a lock protecting a mutable structure.
6. **Fairness/starvation:** lock-free CAS does not guarantee each thread finishes within bounded time.
7. **Backpressure policy:** if every request retries unboundedly when the system is overloaded, CPU contention can increase instead of serving better.

**Do not benchmark with a single run.** To compare `AtomicReference` with a lock, use the same invariants, same workload, number of writers/readers, transform duration, number of fields, contention ratio, and JDK/CPU configuration, and measure throughput, p95/p99 latency, allocation, and GC. In some cases, `synchronized` or `ReentrantLock` is simpler and performs better.

### Is backoff needed?

Under high contention, sometimes consider bounded retries, backoff, or serializing updates through a single owner thread. There is no fixed backoff formula that fits every workload. `Thread.onSpinWait()` is only a **hint** for short spin loops; it does not make CAS succeed or provide fairness; do not call sleep/yield arbitrarily to "fix" correctness. If deadline or cancellation guarantees are needed, design an explicit retry/cancellation policy.

## 16. Choosing AtomicReference, Atomic Counters, or Locks

| Scenario | Usually sensible choice | Why |
|---|---|---|
| Increment an exact `int` or `long` variable | `AtomicInteger`/`AtomicLong` | Specialized increment/CAS without allocating a snapshot object on each increment. |
| Many writers record metrics, readers only take an observed total | `LongAdder` | Reduces contention, though `sum()` is not an atomic snapshot when writers are active. |
| Replace an immutable config snapshot | `AtomicReference<Config>` | Atomically publishes a new object; readers get a consistent snapshot. |
| Check and update **multiple fields in the same immutable state** | `AtomicReference<State>` + CAS loop | Atomic reference swap protects invariants across fields. |
| Large mutable graph, complex transform, high contention | `synchronized`/`ReentrantLock` | Can be easier to maintain and avoids continuous allocation/copying. |
| State depending on external resources | Appropriate transaction/consistency protocol | AtomicReference does not cover databases, files, or network. |
| Need to distinguish A→B→A on the same reference | `AtomicStampedReference` or appropriate versioning algorithm | Provides a version/stamp to detect reference cycles if wraparound does not occur. |
| Only need to publish an immutable value independent of old | `volatile` field or `AtomicReference.set` | No CAS needed if there is no competing read-modify-write to protect. |

### When a lock is simpler

If an update needs to do lengthy work, call APIs with side effects, or operate on multiple mutable structures that are hard to copy, a CAS loop forces the transform to potentially repeat; code becomes complex. A critical section with a shared lock sometimes expresses **the entire business unit** more clearly. However, holding a lock across long I/O can increase contention; the design must evaluate synchronization boundaries rather than assuming locks are always better or CAS is always faster.

## 17. Common Mistakes During Code Review

**Mistake 1 — Treating AtomicReference<Mutable> as a lock.** `ref.get().field++` is still racy. An atomic reference does not make field updates atomic.

**Mistake 2 — Calling get() then set(transform(old)).** Two separate operations can lose updates. CAS or an atomic update function is required if the update depends on the current state.

**Mistake 3 — Using equals instead of expected identity.** `compareAndSet` relies on `==` reference identity. Two records with equal content can still be different references.

**Mistake 4 — Returning true or applying the old candidate after CAS returns false.** Re-read current and recompute all conditions and the snapshot.

**Mistake 5 — Updating multiple fields using two independent AtomicReferences.** Two separate CAS operations are not a transaction. If a consistent snapshot is needed, bundle both fields into one immutable State.

**Mistake 6 — A record containing a mutable List/Map.** Records are only shallowly immutable. Copy or avoid mutating shared nested state.

**Mistake 7 — Sending email or incrementing auxiliary metrics inside an updateAndGet lambda.** The function may run multiple times when CAS retries. Use only pure functions, and perform side effects after success if the contract allows.

**Mistake 8 — Reading current twice and combining fields from two versions.** Keep one `State snapshot = ref.get()` to read multiple fields consistently.

**Mistake 9 — Confusing reference identity with version history.** ABA can occur if the same reference is re-published. Consider a stamped/versioned protocol when invariants need to know about all intermediate changes.

**Mistake 10 — Mutating an old object after publishing a new one.** Readers still holding the old object can be affected. Use immutable snapshots and do not mutate them after publication.

**Mistake 11 — Unbounded CAS loops in every workload.** Under high contention, starvation, CPU, and allocation can spike. Measure load and set deadlines/retry budgets when business requirements demand it.

**Mistake 12 — Conflating Java in-memory CAS with database transactions.** AtomicReference is scoped only to a single JVM process.

**Mistake 13 — Ignoring overflow/validation.** An atomic snapshot can still contain invalid business data if transform does not preserve invariants. Use condition checks and `Math.addExact` when needed.

**Mistake 14 — Replacing state with set(null) and assuming all readers are non-null.** The no-arg constructor of AtomicReference initializes to null; if null is allowed, every read path must have explicit handling or validation contracts.

## 18. Practical Design Pattern

A service holds immutable runtime configuration with operations:

~~~java
import java.util.Objects;
import java.util.concurrent.atomic.AtomicReference;

public final class RuntimeSettings {
    public record Config(String endpoint, int retryLimit) {
        public Config {
            Objects.requireNonNull(endpoint);
            if (retryLimit < 0) {
                throw new IllegalArgumentException("negative retryLimit");
            }
        }
    }

    private final AtomicReference<Config> current =
            new AtomicReference<>(new Config("api-a", 2));

    public Config snapshot() {
        return current.get();
    }

    public Config updateRetryLimit(int newLimit) {
        if (newLimit < 0) {
            throw new IllegalArgumentException("negative newLimit");
        }
        return current.updateAndGet(
                old -> new Config(old.endpoint(), newLimit));
    }

    public void publish(Config replacement) {
        current.set(Objects.requireNonNull(replacement));
    }
}
~~~

This Java 17+ class has no main; its purpose is to illustrate **two different update policies**:

- `publish(replacement)`: intentionally replaces **the entire config** with the caller's snapshot, without needing to preserve other updates. If concurrent writers call publish, the last write in actual execution order wins.
- `updateRetryLimit(newLimit)`: updates **one property based on the latest config**; if another writer changes endpoint before CAS, the function can be re-executed and preserve the new endpoint instead of overwriting it with an old endpoint.

**Semantic boundary:** In a race between `publish` and `updateRetryLimit`, each method has its own atomic point. Callers must not assume "the call invoked first" is necessarily committed first across different threads. If a strict business order or priority between the two update types is required, a clearer versioning/locking policy is needed.

### Thinking about writer ownership

If an application has only one config publisher and many readers, a simple `volatile Config` is sometimes sufficient. When multiple writers need to update based on old state without losing each other's changes, AtomicReference/CAS is more suitable. Do not choose CAS just because "thread-safe" sounds appealing; first determine whether there is a **compound update/invariant** that needs protection.

## 19. Verification with Stress Tests and Tools

Proper testing approaches:

1. **Deterministic interleaving**: use `CountDownLatch` to force two writers to read the same snapshot, proving CAS returns false and retries as in the first example.
2. **Stress test**: have multiple threads update a shared reference; wait for `join()` or `Future.get()` and then verify invariants and total update count, avoiding reading too early.
3. **Snapshot consistency**: for multi-field state, verify that every observed version satisfies the invariants, not just the final state.
4. **Contention metrics**: count CAS failures/retries, allocation, CPU, processing latency, tail latency, and throughput.
5. **Exception/cancellation**: check whether a function throwing partway through leaves side effects; when stopping tasks, check whether any writer still updates after the checkpoint.
6. **Reference lifecycle**: check whether object identities are reused or old snapshots are mutated; ABA or memory retention can affect the algorithm.

A single passing stress test **does not prove** there is no race on every interleaving. For subtle concurrency algorithms, you can explore OpenJDK jcstress to probe observable outcomes under the Java Memory Model. Do not use `Thread.sleep()` durations as proof of correctness or to "synchronize" threads.

## 20. Self-Check Exercises

**Question 1.** Why is `AtomicReference<MutableCounter> ref` with `ref.get().count++` not thread-safe?

**Answer:** AtomicReference only protects getting/replacing **the reference**. Incrementing a field on the mutable object is still a non-atomic read–modify–write and can lose updates.

**Question 2.** Can two records with `equals() == true` cause `compareAndSet` to return false?

**Answer:** Yes. CAS compares reference identity using `==`; two records with equal fields that are distinct instances are not the same expected reference.

**Question 3.** When CAS returns false, should the already-computed candidate be published with `set(candidate)` so it "doesn't go to waste"?

**Answer:** No, if the candidate depends on old state. `set` can overwrite another thread's update. Re-read the snapshot, re-evaluate conditions, and perform a new CAS.

**Question 4.** Why must an updateAndGet lambda not send an email?

**Answer:** Under contention, the lambda can re-run before CAS succeeds; the side effect may happen multiple times or happen even though the candidate is never committed.

**Question 5.** For two fields `balance` and `version`, does using two separate AtomicIntegers guarantee readers always see the same version?

**Answer:** No. Two independent atomic updates do not become a single transaction. Bundle the data into an immutable snapshot and swap the reference atomically, or use a lock protecting reads/writes according to the invariant.

**Question 6.** A reader calls `ref.get()` once and keeps the immutable State locally while a writer performs CAS many times. Will the reader see the state "change mid-way"?

**Answer:** No, if State is truly immutable. The reader holds a specific snapshot object, while the writer publishes new references.

**Question 7.** Why can CAS still be wrong sometimes even though each CAS is atomic?

**Answer:** Surrounding code may rely on stale assumptions, violate invariants, contain side effects, or encounter ABA if the same reference is reused. Atomic CAS alone does not prove the entire algorithm correct.

**Question 8.** When is `AtomicLong` better than `AtomicReference<State>`?

**Answer:** When you only need to increment/decrement a single integer, AtomicLong has a direct API and avoids allocating a snapshot on every update; if multi-field invariants are needed, a State snapshot may be more suitable.

## 21. Official API Documentation

- `AtomicReference<V>`, Java 21: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html
- `AtomicStampedReference<V>`, Java 21: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/AtomicStampedReference.html
- `AtomicMarkableReference<V>`, Java 21: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/AtomicMarkableReference.html
- `AtomicInteger`, Java 21: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html
- `VarHandle`, Java 21: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/VarHandle.html
- **JLS `17 — Threads and Locks (Java Memory Model):** https://docs.oracle.com/javase/specs/jls/se21/html/jls-17.html

**Core takeaway:** AtomicReference protects **a single object reference swap**, and does not automatically protect mutations inside the object. To update multi-field state consistently, build a **new immutable snapshot** from the old snapshot, validate invariants, and publish with CAS; if CAS fails, re-read and recompute. Any function that may be invoked on retry must be side-effect-free. When state spans beyond a single reference or touches external resources, a broader consistency protocol is required.
