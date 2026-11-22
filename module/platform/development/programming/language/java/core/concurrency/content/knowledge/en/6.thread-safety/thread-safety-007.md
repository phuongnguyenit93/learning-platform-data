# Defensive Copies and Immutable Snapshots in Java Concurrency

## 1. The Problem to Solve: Sharing a Mutable Reference

In multithreaded Java programs, bugs can occur when two components accidentally share a mutable object. One component assumes it has stored a stable configuration, while another thread still holds a reference to the original configuration and mutates it. Even when no immediate concurrency failure occurs, that design loses control over state and makes proving thread safety difficult.

Two key techniques:

- **Defensive copy:** creating an appropriate copy at the boundary where data is received or returned so that external code cannot mutate internal state through a shared reference.
- **Immutable snapshot:** representing state at a point in time as a value that is immutable after creation; readers can hold onto that snapshot while writers create and publish a new version.

The **immutability** of a snapshot prevents races on the *contents* of the snapshot. However, **publishing the snapshot reference to other threads still requires proper Java Memory Model guarantees**, for example through a `volatile` field, `AtomicReference`, a monitor lock, or data-transfer mechanisms that establish a happens-before relationship.

This lesson focuses on general Java: collections, objects, records, locks, `volatile`, and atomic APIs in the JDK. No framework is needed to apply these principles.

### Learning Objectives

1. Distinguish between an independent copy, an unmodifiable view, an immutable value, a shallow copy, and a deep copy.
2. Know when to copy on **input** and on **output** at the right ownership boundaries.
3. Use `List.copyOf`, `Set.copyOf`, `Map.copyOf`, immutable constructors, and defensive getters properly.
4. Create consistent snapshots from multi-variable state and publish snapshots safely to readers.
5. Understand the limitations: collection copies do not automatically copy mutable elements, unmodifiable does not mean thread-safe, and snapshots have memory overhead and can become stale over time.

## 2. Aliasing Bugs: Two References Pointing to the Same Object

**Aliasing** occurs when two variables point to the same object. For mutable objects, a mutation through one variable is visible through the other:

~~~java
// Illustration inside a Java method, not a standalone program.
List<String> original = new ArrayList<>();
original.add("read");

List<String> alias = original;  // No copy.
alias.add("write");

// original now contains ["read", "write"].
~~~

When `original` is passed into a constructor and stored as-is, the caller can mutate the object's internals through the original variable. If a getter directly returns an internal `ArrayList`, the caller can also mutate the state after receiving the object.

In multithreaded applications, these two mutation paths are especially dangerous:

- While a reader is iterating over a collection, a concurrent writer can cause inconsistent results, exceptions, or data races depending on the collection type.
- A component defines an invariant such as "the configuration always contains a validated set of permissions," yet the caller adds or removes elements after validation.
- One thread publishes a configuration while another thread reads multiple fields at different times and combines them into a state that never existed.

The solution starts with **ownership**: who is allowed to mutate the data, who only reads it, and at which boundaries a copy or an immutable value must be passed.

## 3. Unmodifiable Views vs. Defensive Copies

An *unmodifiable view* blocks mutation operations **through the view**, but it can still reflect changes in the backing collection. In contrast, `List.copyOf` creates a list that cannot be modified through the `List` interface and is no longer affected by **structural changes** to the mutable source after the copy is made.

### Example 1 — A "Read-Only" View Still Changes with the Source (Java 17+)

Create the file `ViewVsSnapshotDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class ViewVsSnapshotDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("alpha");

        List<String> liveView =
            Collections.unmodifiableList(source);
        List<String> snapshot = List.copyOf(source);

        source.add("beta");

        System.out.println("view = " + liveView);
        System.out.println("snapshot = " + snapshot);

        try {
            snapshot.add("gamma");
        } catch (UnsupportedOperationException error) {
            System.out.println("snapshot rejects add");
        }
    }
}
~~~

Compile and run:

~~~bash
javac ViewVsSnapshotDemo.java
java ViewVsSnapshotDemo
~~~

Stdout:

~~~text
view = [alpha, beta]
snapshot = [alpha]
snapshot rejects add
~~~

Explanation:

- `Collections.unmodifiableList(source)` creates a view that forbids adding or removing through the view; when `source` is mutated directly, the view sees the new contents.
- `List.copyOf(source)` captures the list of elements at the time of copying, so after `beta` is added to `source`, the structure of `snapshot` does not change.
- Both objects reject `add` through their interfaces. Rejecting `add` **does not prove that both have snapshot semantics**.
- `List.copyOf` may reuse an input list that already belongs to an appropriate unmodifiable family; **do not rely on the result always having a different identity from the source**. What must be guaranteed is that the snapshot cannot be structurally altered by the mutable source after copying.

| Creation approach | Can it be modified via the result? | Do later structural changes to the source affect the result? | Are mutable elements inside copied? |
| --- | --- | --- | --- |
| `alias = source` | Yes, if the source is mutable | Yes | No |
| `Collections.unmodifiableList(source)` | Not via the view | **Yes**, the view reflects the backing list | No |
| `new ArrayList<>(source)` | Yes, the copy is mutable | No (for structural operations on the source after copying) | No |
| `List.copyOf(source)` | No | No, if the source is a regular mutable collection | **No**, structural copy only |
| `List.of("A", "B")` | No | No external mutable backing list | Not applicable with immutable `String` |

A structural copy does not automatically guarantee a consistent snapshot if **the source is being modified by another thread during the copy**. Coordination is needed when performing the copy, such as locking, a snapshot mechanism on the source data, or designing for immutable publication from the start.

### Limitations of `copyOf`

- `List.copyOf`, `Set.copyOf`, and `Map.copyOf` are available in Java 10+, so they work with Java 17.
- These factory/copy methods **do not accept null elements**; for maps, neither null keys nor null values are accepted. If the source contains null, a `NullPointerException` will be thrown.
- The result is an unmodifiable collection at the collection level, **not deeply immutable** if elements or values are still mutable.
- Do not depend on the identity or implementation class of the result, and do not use the result as a monitor lock with a stable identity.
- For an input collection with duplicate elements according to `equals`, `Set.copyOf` keeps only one representative; **it does not guarantee which representative is chosen**. Do not use it when preserving duplicates or order is a business requirement.
- `Map.copyOf` takes a `Map` and does not make nested maps/lists immutable; map iteration order is also not guaranteed to match the original.

## 4. Copying at Object Input and Output Boundaries

A class that wants to protect its internal state typically needs both sides:

1. **Copy in:** when a constructor or setter receives a mutable collection or object from a caller, copy it before storing.
2. **Copy out:** a getter must not let callers mutate internal state through the returned reference. It can directly return an **immutable value** that is already guaranteed safe; if internal state remains mutable, it must return an appropriate copy.

### Example 2 — Immutable Class with Copy-In and Safe Return Value

Create the file `ImmutableConfigDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ImmutableConfigDemo {
    static final class WorkerConfig {
        private final List<String> permissions;

        WorkerConfig(List<String> requestedPermissions) {
            this.permissions = List.copyOf(requestedPermissions);
        }

        List<String> permissions() {
            return permissions;
        }
    }

    public static void main(String[] args) {
        List<String> input = new ArrayList<>();
        input.add("read");

        WorkerConfig config = new WorkerConfig(input);
        input.add("delete");

        System.out.println("config = " + config.permissions());

        try {
            config.permissions().add("write");
        } catch (UnsupportedOperationException error) {
            System.out.println("getter result is unmodifiable");
        }
    }
}
~~~

Compile and run:

~~~bash
javac ImmutableConfigDemo.java
java ImmutableConfigDemo
~~~

Stdout:

~~~text
config = [read]
getter result is unmodifiable
~~~

Because `WorkerConfig` holds a `final List<String>` created via `List.copyOf` and its elements are immutable `String`s, callers cannot mutate the contents through either `input` or the getter. **The getter does not necessarily need to make another copy** when the internal data is already a safely shareable immutable value. Repeatedly copying on every read only increases allocation without providing additional protection in this case.

The `final` keyword ensures **the field reference cannot be reassigned**, but it does not automatically make the referenced object immutable. If you store a mutable `ArrayList` directly into a `final List`, callers can still modify the elements and structure of that list through another reference.

### When Internal State Must Be Mutable, the Getter Must Protect It

For example, a class stores an `ArrayList` and updates it under a lock. If a getter wants to return a snapshot, it must also copy **while holding the same lock**:

~~~java
// Illustration inside the same class; not a standalone program.
private final List<String> events = new ArrayList<>();

public synchronized void addEvent(String event) {
    events.add(event);
}

public synchronized List<String> snapshotEvents() {
    return List.copyOf(events);
}
~~~

In the snippet above, the copy is performed while holding the lock on the current object; writer operations in the same class must also use the **same monitor**. This is necessary so that the snapshot is not modified mid-copy. If the getter returned `Collections.unmodifiableList(events)`, callers would receive a view that keeps changing with subsequent additions, not a snapshot.

## 5. Shallow Copies Do Not Protect Mutable Elements

`List.copyOf` only copies the collection structure. If an element holds mutable state, both the source and the snapshot still hold **the same element reference**.

~~~java
// Illustration inside a method, not a standalone program.
StringBuilder item = new StringBuilder("A");
List<StringBuilder> snapshot = List.copyOf(List.of(item));

item.append("B");
// snapshot.get(0).toString() is now "AB".
~~~

`snapshot.add(...)` is blocked, but `snapshot.get(0).append(...)` still mutates the element object. Therefore, the snapshot does not achieve **deep immutability**.

### Example 3 — Converting Mutable Elements into Immutable Data (Java 17+)

Create the file `DeepCopyBoundaryDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;

public class DeepCopyBoundaryDemo {
    static final class MutableLabel {
        private String text;

        MutableLabel(String text) {
            this.text = text;
        }

        String text() {
            return text;
        }

        void rename(String value) {
            text = value;
        }
    }

    static final class LabelSnapshot {
        private final List<String> values;

        LabelSnapshot(List<MutableLabel> input) {
            List<String> copy = new ArrayList<>();
            for (MutableLabel label : input) {
                copy.add(label.text());
            }
            values = List.copyOf(copy);
        }

        List<String> values() {
            return values;
        }
    }

    public static void main(String[] args) {
        MutableLabel label = new MutableLabel("alpha");
        List<MutableLabel> source = new ArrayList<>();
        source.add(label);

        LabelSnapshot snapshot = new LabelSnapshot(source);
        label.rename("beta");
        source.add(new MutableLabel("gamma"));

        System.out.println("snapshot = " + snapshot.values());
        System.out.println("current = " + label.text());
    }
}
~~~

Compile and run:

~~~bash
javac DeepCopyBoundaryDemo.java
java DeepCopyBoundaryDemo
~~~

Stdout:

~~~text
snapshot = [alpha]
current = beta
~~~

In the constructor, each `MutableLabel` is **converted into an immutable `String` value**, and then the resulting list is made unmodifiable. Thus, neither structural changes to `source` nor mutations to `label` after the constructor runs affect the snapshot.

**Important:** this example illustrates copying when the source is not being concurrently mutated while the constructor executes. If another writer is calling `rename` during the copy, you need synchronization or a snapshot protocol from the source to obtain a consistent point-in-time observation. A deep copy alone does not make reading multiple objects atomic.

### Choosing Between Shallow and Deep Copy

| Need | Appropriate copy |
| --- | --- |
| `List<String>` with immutable elements | `List.copyOf` is usually sufficient |
| `List<MutableOrder>` shared with writers | Copy each `MutableOrder` into an immutable DTO/snapshot, then `List.copyOf` |
| `byte[]` array received from outside | `clone()` / `Arrays.copyOf` on input; copy again on output |
| Object array containing mutable elements | Copy the array **and** each mutable element inside if a deep copy is needed |
| Record with a `List<MutableThing>` field | A record is by default only immutable at the reference level; must copy/normalize contents |

For object graphs with circular references or resources like sockets or files, "deep copy everything" may be infeasible or meaningless. In those cases, designing an immutable projection containing only the data needed for reading is usually clearer than arbitrarily cloning an entire object graph.

## 6. Arrays, Dates, Records, and Common Immutability Traps

### 6.1. Arrays Are Always Mutable

A `private final byte[] key` field does not mean the array contents cannot change. If the caller still holds a reference to the array, they can modify `key[0]` after passing it into the constructor.

A defensive pattern:

~~~java
// Illustration inside a class holding byte[]; not a standalone program.
private final byte[] bytes;

public Payload(byte[] input) {
    this.bytes = input.clone();
}

public byte[] bytes() {
    return bytes.clone();
}
~~~

`clone()` on a primitive array creates an independent copy of the primitive values. On an object array, `clone()` only copies the array of references—**it does not clone each child object**. When using arrays to store secrets, you must also design appropriate data lifecycles, access controls, and sensitive-data zeroing policies; cloning alone does not solve secret management.

### 6.2. Date and Time Types

`java.util.Date` is mutable; returning a `Date` directly from a getter allows callers to mutate it with `setTime(...)`. You can copy via `new Date(original.getTime())` at input/output boundaries or switch to immutable types in `java.time` such as `Instant` or `LocalDate` when appropriate for the domain.

### 6.3. Records Are Not Automatically Deeply Immutable

A Java `record` makes its **component fields** `private final` and generates accessors, but the referenced objects can still be mutable.

~~~java
// Java 17+ illustration, not a standalone program.
record Batch(List<String> items) {
    Batch {
        items = List.copyOf(items);
    }
}
~~~

In the compact canonical constructor, the `items` parameter is reassigned to an unmodifiable copy before being stored in the generated field. With immutable `String` elements, this record forms a value object suitable for sharing. If `items` contains mutable objects, you must also convert or copy the elements. If a record contains an array, the default accessor returns the array reference; you may need to override the accessor to copy out.

Do not confuse an **immutable class** with "every field is `final`." Immutability must be evaluated recursively across all **observable and modifiable state**.

## 7. Immutable Snapshots and Point-in-Time Consistency

A snapshot is meaningful when it represents **a valid state** at a single point of transition. Suppose system state has two variables `left` and `right`, with the invariant `left + right == 100`. If a reader reads `left`, then a writer updates both, and then the reader reads `right`, the reader can combine values from two different points in time into a sum not equal to 100.

Even if both variables are `volatile`, reading them sequentially **does not create an atomic snapshot of the pair**.

Two common strategies:

1. **Copy under a lock:** the reader holds the same lock that the writer uses throughout the entire copy; the snapshot reflects a state without writer interference.
2. **Single immutable state object:** the writer creates a complete new state object and publishes the entire reference via `volatile` or `AtomicReference`; the reader reads the reference once and uses that same object for all fields.

Distinguish **immutability** from **publication**:

- Not mutating the snapshot object after creation prevents readers from racing on its contents.
- Publishing the reference through a mechanism with happens-before guarantees ensures readers see the initialized state.
- A reader may hold onto an older snapshot version while a writer publishes a new version; that is a desired property in many designs, not a visibility bug.
- A snapshot does not mean reading "the newest data at all times"; it means reading **one consistent version**.

## 8. Example 4 — Copying a Snapshot Under `synchronized` (Java 17+)

Create the file `LockedSnapshotDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;

public class LockedSnapshotDemo {
    static final class EventStore {
        private final List<String> events = new ArrayList<>();

        synchronized void add(String value) {
            events.add(value);
        }

        synchronized List<String> snapshot() {
            return List.copyOf(events);
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        EventStore store = new EventStore();
        store.add("created");

        List<String> firstSnapshot = store.snapshot();

        Thread writer = new Thread(() -> {
            store.add("processed");
        }, "event-writer");

        writer.start();
        writer.join();

        System.out.println("old = " + firstSnapshot);
        System.out.println("new = " + store.snapshot());
    }
}
~~~

Compile and run:

~~~bash
javac LockedSnapshotDemo.java
java LockedSnapshotDemo
~~~

Stdout:

~~~text
old = [created]
new = [created, processed]
~~~

`add` and `snapshot` use the same `EventStore` monitor, so no writer can interleave while `snapshot` copies the list. `firstSnapshot` preserves the old state even after the writer adds `processed`. `join()` ensures the writer has completed before taking the second snapshot.

This differs from holding `Collections.unmodifiableList(events)`: that view would reflect the `processed` element in both reads.

Even a properly locked snapshot copy has a cost: each `snapshot()` call requires traversal and allocation proportional to the collection size. If readers vastly outnumber writers, consider publishing a monolithic immutable state so readers only read a reference.

## 9. Publishing Snapshots via `volatile` or `AtomicReference`

### 9.1. A Single `volatile` Reference for the Entire State

Conceptual structure example:

~~~java
// Illustration inside a class; the immutable config is validly constructed.
private volatile ConfigSnapshot current;

// Writer:
current = newSnapshot;

// Reader:
ConfigSnapshot local = current;
// Continue reading all fields through the same local variable.
~~~

**Assigning a reference** is an atomic operation; when using `volatile`, it also provides visibility and ordering guarantees for publication. If a reader reads `current` once and then reads fields from `local`, those fields belong to **the same version**. If a reader calls `current.a()` and then `current.b()` across two separate reference reads, a writer could swap the snapshot in between and the reader would mix two versions—a bug in the reading pattern.

`volatile` **does not prevent lost updates when multiple writers** perform read–modify–write cycles like "read `current`, build a new version, assign `current`." With multiple contending writers, use locking or CAS/`AtomicReference.updateAndGet` with pure update logic.

### 9.2. Example 5 — Immutable Snapshot Updated with CAS (Java 17+)

Create the file `AtomicSnapshotDemo.java`:

~~~java
import java.util.concurrent.atomic.AtomicReference;

public class AtomicSnapshotDemo {
    record Inventory(int available, int reserved, long version) {
        Inventory {
            if (available < 0 || reserved < 0) {
                throw new IllegalArgumentException("Negative stock");
            }
        }

        int total() {
            return available + reserved;
        }
    }

    public static void main(String[] args) {
        AtomicReference<Inventory> state =
            new AtomicReference<>(new Inventory(10, 0, 0));

        Inventory before = state.get();

        state.updateAndGet(old ->
            new Inventory(
                old.available() - 3,
                old.reserved() + 3,
                old.version() + 1
            )
        );

        Inventory after = state.get();

        System.out.println(
            "before=" + before + ", total=" + before.total()
        );
        System.out.println(
            "after=" + after + ", total=" + after.total()
        );
    }
}
~~~

Compile and run:

~~~bash
javac AtomicSnapshotDemo.java
java AtomicSnapshotDemo
~~~

Stdout:

~~~text
before=Inventory[available=10, reserved=0, version=0], total=10
after=Inventory[available=7, reserved=3, version=1], total=10
~~~

`Inventory` is a record containing only three primitive values; after creation, it has no mutable internal fields. `AtomicReference.get()` returns a shareable snapshot, while `updateAndGet` attempts to replace the entire reference with a new snapshot based on the current value. A reader holding `before` continues to see version 0, while a reader fetching `after` sees version 1. The sum `available + reserved` is consistent in every version.

**Important limitations:**

- The function passed to `updateAndGet` **may be executed multiple times** under contention; place only pure computation inside it—do not send requests, write files, or trigger side effects that must run exactly once.
- If an update would make `available` negative, the constructor in the example throws an exception. In real applications, validate business conditions and handle failure outcomes according to a clear contract.
- CAS protects swapping **a single reference**; it does not turn external side effects such as database writes into atomic transactions.
- Holding onto old snapshot versions for a long time keeps that version's data in memory until no references remain.
- When there is only a single writer and many readers, `volatile` can be used to publish a complete snapshot; CAS is useful when multiple writers must coordinate state updates based on the current version.

### Read and Write Flow

~~~text
Writer:
  read current v1
       |
  create immutable state v2
       |
  publish v2 via volatile/CAS
       |
Reader A: holds v1, reads consistent v1
Reader B: gets v2, reads consistent v2
~~~

There is no requirement for the writer to wait for all readers to finish before creating a new version. This is why copy-on-write designs are very useful for **read-heavy, write-rare** workloads.

## 10. Ensuring Thread Safety When Copying

### 10.1. Copying While the Source Is Being Modified Is a Separate Problem

A common mistake is:

~~~java
// Unsafe illustration if source is an ArrayList being modified concurrently.
List<String> snapshot = List.copyOf(source);
~~~

If another writer modifies `source` during the copy, you do not get a **point-in-time consistent** snapshot. On collections that do not support concurrent modification, iteration/copying may also throw exceptions or behave unexpectedly.

Clearly define the protocol:

- **Exclusively owned source:** no other thread modifies it during the copy.
- **Lock-protected source:** writer and snapshot share the same monitor/lock.
- **Immutable state source:** the reader simply captures the reference once, without iterating over a changing mutable collection.
- **Concurrent collection source:** read the specific contract of the operation. "Concurrent" does not automatically mean a copy reflects an atomic instant of the entire collection.

For example, `ConcurrentHashMap` iterators are typically **weakly consistent**: they may reflect partial concurrent updates without throwing a fail-fast `ConcurrentModificationException`. Creating a `Map.copyOf` from a changing concurrent map does not automatically guarantee a linearizable snapshot of the whole map if cross-entry consistency is required.

### 10.2. `CopyOnWriteArrayList` Is a Specialized Option

`CopyOnWriteArrayList` creates a copy of the underlying array on structural modifications and provides a **snapshot** iterator unaffected by subsequent structural updates. It fits **read/iterate-heavy, write-rare** data, such as listener lists.

In return, each write must copy the underlying array; when the list is large or writes are frequent, allocation, memory, and CPU overhead can be high. The snapshot iterator only protects the contents of the **reference array** at the time the iterator was created—it does not make mutable element objects immutable.

`CopyOnWriteArrayList` is a concurrent container, whereas an immutable snapshot is **a state representation pattern**. Depending on the problem, an `AtomicReference<List<ImmutableValue>>` swapped as a whole may make version control easier.

### 10.3. Consistency and Freshness Are Different Requirements

| Property | Meaning |
| --- | --- |
| Consistent snapshot | All fields belong to the same valid version |
| Freshness | How up-to-date the snapshot is relative to the current writer |
| Atomic publication | Readers see either the old or new version reference, never a half-constructed state |
| Thread-safe source | The source's read/write mechanism does not violate synchronization rules |
| Deep immutability | All observable contents cannot be mutated through any other alias |

An older snapshot can be completely consistent yet not fresh enough for a business requirement. For instance, a configuration display UI might tolerate being one version behind; checking inventory to place an order may need to re-check close to write time, coordinating the condition atomically with the update.

## 11. Memory Cost, Performance, and Design

Defensive copies and immutable snapshots reduce mutable sharing, but every large copy costs time, memory, and GC pressure.

**Evaluate the following:**

1. **Write frequency:** With many writers, copying the entire collection on every edit can be expensive. Consider locking, state partitioning, or a suitable data structure.
2. **Read frequency:** When readers are numerous and state changes rarely, publishing an immutable snapshot via a single reference can avoid locks on the read path.
3. **Snapshot size:** Copying a list of millions of elements per request is a major cost; consider pagination, partial snapshots, persistent data structures, or narrowing scope.
4. **Retention time of old versions:** Many readers holding old snapshots increase live data in the heap. Monitor heap occupancy and GC pressure.
5. **Quality of immutability:** If elements are still mutable, snapshot-sharing optimizations can lose their guarantees.
6. **When to copy:** Copy on input, before publication, or on every getter? Returning an already safely published immutable value is usually cheaper than copying repeatedly.
7. **Versioning requirements:** Does the snapshot need a `version` or timestamp so consumers can check freshness and avoid overwriting an update from another version?

There is no rule to "copy every object all the time." The right approach depends on ownership, concurrency level, consistency requirements, and measurements on realistic workloads.

## 12. Common Mistakes and How to Fix Them

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| `this.items = input` and assuming the caller won't mutate it | Caller retains an alias | Copy in or explicitly transfer ownership |
| Getter returns an internal `ArrayList` | Caller mutates state directly | Return an immutable snapshot or defensive copy |
| `Collections.unmodifiableList(mutableList)` and calling it a snapshot | View reflects changes from the backing list | `List.copyOf` at a properly synchronized point |
| `List.copyOf(List<MutableItem>)` and calling it deeply immutable | Elements still share mutable references | Copy/project each element into an immutable value |
| Record with `byte[]` and assuming the record is fully immutable | Field is `final` but the array is mutable | Copy the array in the constructor and accessor |
| Copying a collection while a writer mutates it without a lock | Snapshot may be inconsistent or throw an exception | Copy under the same lock or use an immutable source design |
| Assigning two `volatile` fields and calling it an atomic snapshot | Reader can mix two versions | Combine into one immutable state object and publish a single reference |
| Writer reads `volatile` state and assigns new state without CAS | Multiple writers can lose updates | Use a lock or `AtomicReference.compareAndSet`/`updateAndGet` |
| Using `AtomicReference` with an update function that has side effects | CAS retries repeat the side effect | Use a pure transformation function; run side effects after a successful update |
| Using `CopyOnWriteArrayList` for write-heavy workloads | Every write copies the underlying array | Measure load and choose a more suitable collection or locking strategy |
| Believing `final` makes an object graph immutable | `final` only locks reference reassignment | Design recursive immutability across observable data |
| Relying on `Thread.sleep` to wait for a snapshot to "stabilize" | Sleep provides neither happens-before nor atomicity | Use locks, latches, futures, or `volatile`/CAS properly |

## 13. Review Checklist and Self-Check

When reviewing a class shared across multiple threads:

- **Ownership:** Which callers still hold references to input objects? Can they mutate those objects after the constructor?
- **Copy in:** Does the constructor/setter capture an independent copy before storing? If nested data is mutable, is the copy deep enough?
- **Copy out:** Does any getter accidentally return an internal mutable object? If returning an immutable snapshot, are the elements themselves truly immutable?
- **Consistency:** If multiple fields must satisfy an invariant, is the snapshot created under the same lock or from a single immutable state object?
- **Publication:** Do writers and readers share a clear happens-before protocol via `volatile`, CAS, locks, queues, `start`/`join`, or other primitives?
- **Concurrency:** Can any writer mutate the source during a copy without coordination?
- **Performance:** Are copy frequency, snapshot size, and retention time of old versions appropriate?
- **Tests:** Are there tests for mutating the source after copying, mutating elements, concurrent writers/readers, and snapshot invariants?

### Question 1

`List<String> view = Collections.unmodifiableList(source)`. Another thread mutates `source`. Does `view` still preserve the exact contents from when it was created?

**Answer:** Not guaranteed. `view` is an unmodifiable view that reflects the backing source. If mutations and reads happen concurrently without a proper protocol, it can also violate thread safety.

### Question 2

`List<MutableOrder> snapshot = List.copyOf(orders)`. Can we claim that all `MutableOrder` instances inside can no longer be modified?

**Answer:** No. `copyOf` does not clone or deep-copy the orders. You need to convert them into immutable projections or defensively copy each element according to the appropriate ownership model.

### Question 3

Can a reader read `current.left()` and immediately afterward `current.right()`, while `current` is a `volatile` reference pointing to an immutable state and a writer replaces it?

**Answer:** Two separate accesses to `current` can read **two different versions**. To get a consistent snapshot, assign `State local = current` once and read both `local.left()` and `local.right()`.

### Question 4

Why shouldn't `AtomicReference.updateAndGet` take a lambda that both creates a new state and writes a billing audit log?

**Answer:** CAS can retry under contention, causing the lambda to be invoked multiple times for a single successful update. The state transformation function must be pure; side effects must be handled separately.

### Question 5

If a thread holds onto an older immutable snapshot while a writer publishes a new snapshot, is that thread experiencing a data race?

**Answer:** No, provided the snapshot is truly immutable and safely published. The reader is using a consistent older version. How quickly it must see newer versions is a business **freshness** requirement that must be specified separately.

**Key takeaway:** Defensive copies protect **data ownership boundaries**; immutable snapshots protect **the consistency of the version being read**; safe publication ensures **other threads see a validly constructed version**. Achieving thread safety requires combining all three when the problem demands it, while evaluating copy overhead and snapshot freshness.
