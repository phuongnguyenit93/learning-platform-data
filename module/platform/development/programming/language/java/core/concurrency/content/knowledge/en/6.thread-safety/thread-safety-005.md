# Encapsulation of State Requiring Synchronization in Java

## 1. Why is encapsulation the foundation of thread safety?

**Encapsulation** is the practice of an object retaining control over its own state and only allowing external access through operations with clear contracts. In Java concurrent programming, encapsulation is also the way to ensure that **all potentially conflicting accesses follow the same synchronization rule**.

A class can declare its fields as `private` and still **not be thread-safe**. If a getter returns the internal mutable object itself, the caller can modify it without going through the lock. If a method acquires a lock when writing, but shared data is read without an appropriate synchronization mechanism, the class can still suffer from a data race or read an inconsistent state.

The goal is not simply to "wrap `synchronized` around every method." The goals are:

1. Identify the **invariants** of the state: for example, non-negative inventory; the total balance across two wallets remains conserved; a list can only be modified through a single API.
2. Identify **who owns the mutable state** and who can read/write it.
3. Place **all operations related to the same invariant** under an appropriate protection protocol: a shared lock, atomic primitives, immutable state replaced atomically, or thread confinement.
4. Do not let mutable references or control over the lock escape in a way that breaks that protocol.
5. Publish results, snapshots, or data exchanged with other threads using an appropriate happens-before relationship.

This is a general Java concurrency topic. The techniques in this article use Java 17+ and standard JDK APIs.

## 2. State, invariants, and synchronization policy

A **state** is the set of data that an object's behavior depends on. State can reside in primitive fields, reference objects, collections, or nested objects.

An **invariant** is a condition that must always hold true at points where the state is considered valid. For example:

- `remaining >= 0` for an inventory that does not allow overselling.
- `fromBalance + toBalance == total` during an internal funds transfer.
- An identifier has only one active record.
- The `name` and `version` fields of a snapshot must belong to the same update.

A **synchronization policy** is the convention that all related accesses must adhere to, such as "all reads/writes of the two balance fields must hold the object's `lock`," or "the state is published as an immutable snapshot via `AtomicReference`."

A class that wants to truly encapsulate thread safety must control **all entry paths to its state**. Even a single method bypassing the policy can break the guarantees of the entire object.

### Invariant scope determines lock scope

If `quantity` and `reserved` must satisfy `quantity >= reserved`, two updates on two separate `AtomicInteger` instances **do not** guarantee the cross-field invariant at every read point. If two fields need to be updated as a single logical unit, you can:

- Protect both under **the same lock** and provide synchronized update/snapshot methods.
- Store the entire state in an immutable object and swap the reference using `AtomicReference.compareAndSet(...)`, recomputing when CAS fails.
- Use a single owning thread and send messages to that owner, if the application model fits.

Do not choose the number of locks or atomic fields based solely on the number of data fields. Start from the invariants that need to be protected.

## 3. Common forms of "state leakage"

### 3.1. Getter returning an internal mutable reference

Create the file `EscapedList.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class EscapedList {
    private final List<String> items = new ArrayList<>();

    public synchronized void add(String item) {
        items.add(item);
    }

    public synchronized int size() {
        return items.size();
    }

    // Design flaw: returns the actual mutable list being protected.
    public synchronized List<String> items() {
        return items;
    }

    public static void main(String[] args) {
        EscapedList store = new EscapedList();
        store.add("A");

        List<String> leaked = store.items();
        leaked.clear(); // Bypasses all synchronized methods of store.

        System.out.println("Store size: " + store.size());
    }
}
```

Run on Java 17+:

```bash
javac EscapedList.java
java EscapedList
```

Output:

```text
Store size: 0
```

Even running sequentially is enough to demonstrate the flaw of **losing control over state**: the caller clears the data without going through the `add` API or any modification policy of the store. With multiple threads, `leaked.clear()` can execute concurrently with `add()`/`size()`. Having `items()` synchronized only protects **the moment the reference is returned**; once the method returns, the reference still points to the internal list itself.

**Fix:** keep the list private and only return an appropriate copy; provide synchronized read/write operations on the object that owns the state.

### 3.2. Getter returning a mutable array, map, or object

Dangerous design patterns:

```java
// Illustrative example; fields are assumed to be declared.
public byte[] buffer() { return internalBuffer; }
public Map<String, String> entries() { return mutableMap; }
public MutableConfig config() { return internalConfig; }
```

Returning the reference allows callers to write to the internal object without the class observing or properly synchronizing it. `private final byte[] internalBuffer` also **does not protect the array's contents**: `final` only prevents reassigning the field reference, it does not make the array immutable.

If mutable data must be exchanged, consider copying on **input** and **output**, using immutable value objects, or transferring ownership explicitly. Even in a constructor that receives a `List` from the caller, storing that reference directly can allow the caller to still modify the state later.

### 3.3. An unmodifiable view is not an immutable snapshot

`Collections.unmodifiableList(backingList)` creates a view that disallows modification through the view, but **the backing list can still change** if the owner or another reference modifies it. Therefore, this view can reflect future changes and does not replace taking a snapshot inside a lock.

`List.copyOf(source)` creates an unmodifiable list that does not reflect subsequent additions/removals from the source. However, it is a **shallow copy**: if the elements are mutable objects, callers can still modify those objects' contents. Additionally, `List.copyOf` does not accept null elements.

For `List<String>`, immutable strings make snapshot examples straightforward. For complex mutable objects, switch to immutable DTOs/value objects or deep-copy according to domain semantics when needed.

## 4. Java 17+: encapsulation via an invariant-preserving API

Create the file `SafeInventory.java`:

```java
import java.util.concurrent.atomic.AtomicInteger;

public class SafeInventory {
    private int remaining = 5;

    // Both check and decrement are inside the same critical section.
    public synchronized boolean reserveOne() {
        if (remaining <= 0) {
            return false;
        }
        remaining--;
        return true;
    }

    public synchronized int available() {
        return remaining;
    }

    public static void main(String[] args) throws InterruptedException {
        SafeInventory inventory = new SafeInventory();
        AtomicInteger accepted = new AtomicInteger();
        Thread[] workers = new Thread[12];

        for (int i = 0; i < workers.length; i++) {
            workers[i] = new Thread(() -> {
                if (inventory.reserveOne()) {
                    accepted.incrementAndGet();
                }
            }, "buyer-" + i);
            workers[i].start();
        }

        for (Thread worker : workers) {
            worker.join();
        }

        System.out.println("Accepted: " + accepted.get());
        System.out.println("Remaining: " + inventory.available());
    }
}
```

Compile and run:

```bash
javac SafeInventory.java
java SafeInventory
```

Output when the workers complete normally:

```text
Accepted: 5
Remaining: 0
```

**Why is the result always correct?**

- `remaining` is `private` and has no arbitrary setter; external code can only call `reserveOne()` or read `available()`.
- `reserveOne()` holds the monitor of the `inventory` object itself throughout the **check stock → decrement stock** sequence. No other thread can interleave between these two steps if it also goes through the object's API.
- `available()` uses **the same monitor** to read the value, thus establishing an appropriate synchronization relationship with the updates.
- The twelve workers may be scheduled in any order; only five reservations succeed. `AtomicInteger accepted` allows recording the number of accepted reservations from multiple threads without losing counts.
- `join()` makes `main` wait for all workers before printing the result.

In this class, the invariant `remaining >= 0` is preserved across every API call. **The design condition** is that there is no other path modifying `remaining` outside the policy; an unchecked standalone setter or exposing a reference to mutable state would break the guarantee.

### Check–then–act must be inside the same operation

An API pattern like calling `available()` then `reserveOne()` is safe if the caller **does not assume** the earlier `available()` result will still hold. Only `reserveOne()` is the decision point for accepting/rejecting. If replaced with two unconstrained methods `hasStock()` and `decrement()`, two callers could both pass the check and then both decrement the quantity. A separate lock per method **is not enough** to make a caller-composed sequence atomic.

Good design **puts the business operation that needs to be atomic into a single method on the object owning the state**.

## 5. Internal locks, consistent policies, and retaining control

A `synchronized` instance method locks the monitor of `this`. This works for the `SafeInventory` example, but any code holding a reference to the object can write `synchronized (inventory)`, causing contention or holding the lock unexpectedly. When you want tighter control over the lock, use a **private lock object**:

```java
final class Counter {
    private final Object lock = new Object();
    private int value;

    public void increment() {
        synchronized (lock) {
            value++;
        }
    }

    public int get() {
        synchronized (lock) {
            return value;
        }
    }
}
```

This is a helper class that can be compiled in a file containing a non-public class without `main`. `lock` is never returned externally, never reassigned, and never used to synchronize unrelated objects. With the same lock, all updates and reads of `value` are protected, and monitor unlock/lock establishes the appropriate happens-before relationship.

Key rules:

1. **Document which state each lock protects.** If there are multiple locks, be explicit about which fields each invariant depends on; do not lock each field individually and assume you have a consistent cross-field snapshot.
2. **Protect both read and write paths.** Reading without locking a variable being written by another thread can create a data race; even a simple getter must follow the policy or use safely published data.
3. **Hold the lock long enough to protect the invariant**, then release it as soon as possible. Do not intentionally unlock between check and update.
4. **Avoid uncontrolled callbacks inside a critical section.** A callback might re-enter the API, block on I/O, acquire another lock, or create a deadlock cycle.
5. **Do not publish internal locks.** Returning `lock`, using a public object as a monitor, or using string literals as locks reduces control over contention.
6. **External resources need their own protocol.** A monitor in one JVM does not protect a database, file, or service that can be modified by another process/JVM.

### `volatile` and `AtomicInteger` do not replace all locks

`volatile` provides certain visibility/ordering guarantees, suitable for simple flags under a clear protocol, but `count++` on a `volatile int` is still not atomic. `AtomicInteger.incrementAndGet()` fits an independent counter; multiple separate atomic variables do not form a transaction covering an invariant across them.

Conversely, locking every single field is not always necessary either. Immutable state or state confined to a single thread does not require a lock on every read. Choose the mechanism based on actual sharing conditions and invariants.

## 6. Encapsulation when returning a snapshot to callers

If a caller wants to inspect the contents of a collection, do not return the mutable backing collection directly. You can create a snapshot **inside the locked region** and publish the immutable snapshot externally.

Create the file `SnapshotStore.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class SnapshotStore {
    private final Object lock = new Object();
    private final List<String> items = new ArrayList<>();

    public void add(String value) {
        synchronized (lock) {
            items.add(value);
        }
    }

    public List<String> snapshot() {
        synchronized (lock) {
            return List.copyOf(items);
        }
    }

    public static void main(String[] args) {
        SnapshotStore store = new SnapshotStore();
        store.add("A");

        List<String> oldSnapshot = store.snapshot();
        store.add("B");

        System.out.println("Old: " + oldSnapshot);
        System.out.println("Current: " + store.snapshot());

        try {
            oldSnapshot.add("C");
        } catch (UnsupportedOperationException expected) {
            System.out.println("Snapshot is read-only");
        }
    }
}
```

Run:

```bash
javac SnapshotStore.java
java SnapshotStore
```

Output:

```text
Old: [A]
Current: [A, B]
Snapshot is read-only
```

**Analysis:**

- `snapshot()` holds the same `lock` that `add()` uses, so the copy is created at a logical point in time consistent with the store's mutations.
- `List.copyOf(items)` returns an unmodifiable list, isolating its element structure from subsequent additions/removals in `items`.
- `oldSnapshot` does not automatically become `[A, B]` after the store changes; callers cannot call `add()` on the snapshot.
- Here the elements are immutable `String`s. If each element were a `MutableOrder`, `List.copyOf` **does not deep-copy** the orders; you still need to design immutable snapshots for each element separately.

**Cost:** snapshots cost time and memory proportional to the number of elements; if the data is large, read frequency is high, or many records need to be streamed, consider pagination, a read-only interface with an appropriate contract, copy-on-write, or another data transfer approach. A consistent snapshot can be well worth the copying cost when it prevents state leakage.

### Defensive copy on input as well

A constructor that simply writes `this.items = input` may retain a reference to a collection that the caller still manages. If the goal is to own the data, create `new ArrayList<>(input)` or `List.copyOf(input)` depending on mutable/immutable needs. **Remember to copy on both input and output** if both directions could allow the state to be modified outside the protocol.

## 7. Multi-field invariants: a snapshot must be synchronized with updates

Create the file `AccountBookDemo.java`:

```java
public class AccountBookDemo {
    record Balances(int from, int to) {
        int total() {
            return from + to;
        }
    }

    private static final class AccountBook {
        private int from = 100;
        private int to = 0;

        public synchronized boolean transfer(int amount) {
            if (amount <= 0 || amount > from) {
                return false;
            }
            from -= amount;
            to += amount;
            return true;
        }

        public synchronized Balances snapshot() {
            return new Balances(from, to);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        AccountBook book = new AccountBook();
        Thread first = new Thread(() -> book.transfer(30));
        Thread second = new Thread(() -> book.transfer(20));

        first.start();
        second.start();
        first.join();
        second.join();

        Balances result = book.snapshot();
        System.out.println(result);
        System.out.println("Total: " + result.total());
    }
}
```

Run with Java 17+ (which supports `record`):

```bash
javac AccountBookDemo.java
java AccountBookDemo
```

Output:

```text
Balances[from=50, to=50]
Total: 100
```

The two threads can call `transfer` in any order, but **each transfer is executed under the same monitor**. A transfer does not expose the intermediate state between subtracting from `from` and adding to `to` to callers using the synchronized API. The `snapshot()` method holds that same monitor to copy both values **simultaneously** into an immutable `record Balances`. Callers cannot modify `from` and `to` directly.

If you wrote two synchronized getters `getFrom()` and `getTo()` and the caller invoked them separately, a transfer could happen **between the two calls**. Two results that were each valid at the moment they were read might still fail to form a consistent snapshot together. When an invariant spans multiple fields, return a snapshot captured within **a single** critical section.

The example uses small integers to focus on concurrency; when handling real money, you also need appropriate monetary types and business rules. The lock in the example only protects the state of one `AccountBook` object within the JVM, not a cross-system transaction.

## 8. Safe publication and object ownership

Even for a class where all methods are synchronized, the process of **creating and publishing references** must also be considered. Do not let `this` "escape" before the constructor completes—for example, starting a thread that holds a `this` reference from inside the constructor, or registering a callback on an external object before the state is ready.

`final` has special JMM rules during proper initialization, but `final List<?>` only fixes the **reference** and does not make the elements or the list's contents immutable. A constructed object can be handed off via `Thread.start()`, `BlockingQueue`, `volatile`/`AtomicReference`, `synchronized`, or other mechanisms with appropriate memory-consistency guarantees.

**Thread confinement:** if all mutable state is accessed only by a single owning thread, no lock may be needed for that state. Other threads send messages/tasks to the owner instead of writing state directly. The condition is that no mutable reference is unintentionally shared.

**Immutable state:** if an object has no mutable state after proper construction and its reference is safely published, multiple readers can use it without locking on each read. This often makes code easier to reason about.

**Shared mutable state:** if multiple threads are allowed to modify an object, the synchronization policy must be specified by the object owning the state and enforced across every related API.

## 9. A "thread-safe" API does not mean every combination of API calls is atomic

A concurrent collection typically only guarantees the operations described in its contract. For example, using `ConcurrentHashMap`:

```java
// Illustration: map is already a ConcurrentHashMap<String, String>.
if (!map.containsKey("job-1")) {
    map.put("job-1", "running");
}
```

This is a **non-standalone snippet**. Although `containsKey` and `put` are thread-safe when called individually, two threads can both see that the key does not exist yet and both decide to register. If the invariant is "only one registrant," you must use `putIfAbsent` or an appropriate key-level atomic operation.

Similarly, the individual `size()` and `remove()` methods of a synchronized wrapper do not automatically make the sequence `if (size() > 0) remove()` atomic with respect to other threads. If a conditional action is needed, **encapsulate both check and act** into a single API on the state owner and protect that entire sequence.

### Callbacks and caller-supplied functions

An API that accepts a `Consumer`, `Function`, or comparator from the caller may indirectly execute arbitrary code while holding a lock. The callback might block on I/O, call back into the same object, attempt to acquire another lock, or cause a deadlock. Explicitly decide whether the callback runs inside or outside the critical section, and evaluate correctness if it runs on a snapshot outside the lock.

For example, "copy a snapshot under the lock then apply the callback outside the lock" usually avoids running unknown code while holding a lock; however, it is only correct when the operation genuinely allows working on a stale snapshot. If the callback must update the state itself based on the condition just read, releasing the lock before writing can reintroduce a TOCTOU bug. There is no single default choice that fits every invariant.

## 10. At what boundaries does encapsulation guarantee synchronization?

| Scope | Can Java encapsulation/locks protect it? | Notes |
| --- | --- | --- |
| Multiple threads sharing one instance in one JVM | Yes, when all access paths follow the policy | Same lock or appropriate atomic primitives |
| Multiple instances, each with its own lock | Only each instance's own state | Does not protect shared static state if policies differ |
| Multiple JVMs/processes accessing the same file | Not automatically | Requires appropriate filesystem locking/atomic mechanisms |
| Multiple applications updating the same storage | Not automatically | Requires transactions/conditional updates/unique constraints at the source of truth |
| Safely published immutable snapshot | Usually no lock needed for read-only access | Must not contain or expose unprotected mutable elements |

A mutable `static` variable can be shared by all instances. If each instance uses `synchronized` on `this` to protect a static variable, the instances have **different monitors** and do not exclude one another. When protecting shared static state, you must choose a shared policy matching that state's scope.

## 11. Common pitfalls

- **"Private fields mean thread-safe."** False when the API still returns mutable references, callbacks expose state, or other accesses bypass the policy.
- **"Adding synchronized to a list getter is enough."** False if the getter returns the backing list; callers continue modifying it outside the lock.
- **"final makes a list or array immutable."** False: `final` fixes the field reference; the object's contents can still be mutable.
- **"unmodifiableList is an immutable copy."** False: the view disallows modification through itself, but the backing collection can still change.
- **"List.copyOf deep-copies every element."** False: it copies the list structure, not the mutable objects at each element.
- **"Synchronizing each getter makes a multi-field snapshot consistent."** False if the getters run in two separate critical sections with an update in between.
- **"Using volatile/atomic for each field keeps multi-field invariants always true."** False if atomicity across fields is required.
- **"Locking only writers is enough."** False if readers read the same state without an appropriate visibility/ordering protocol.
- **"A private lock solves modifications from another service."** False: a monitor only coordinates threads using that monitor within the same JVM.
- **"Calling a callback inside synchronized is always safe."** Not necessarily: an uncontrolled callback can prolong lock hold time or create lock-ordering cycles.
- **"Putting Thread.sleep inside a critical section gives other threads time to update."** False: sleep does not release the monitor and does not make an algorithm safe.

## 12. Checklist for designing a thread-safe class

1. **List state and invariants:** which fields are related, what values are valid, and who is allowed to modify them?
2. **Designate ownership:** does a single object control updates, or is state unintentionally shared?
3. **Define the synchronization policy:** same lock for all related accesses, atomics for single-variable updates, or immutable/thread-confined state?
4. **Audit input/output APIs:** does the constructor retain a caller's mutable reference? Do getters return internal objects/arrays/maps/lists?
5. **Encapsulate business operations:** check–then–act or read–modify–write sequences that need atomicity should live in a single protected method.
6. **Ensure consistent snapshots:** when multiple fields form an invariant, copy them inside the same critical section into an immutable result.
7. **Review callbacks and lifecycle:** do not let `this` escape before initialization completes; avoid running unknown code or waiting on I/O while holding a lock.
8. **Check scalability:** measure contention, snapshot copy cost, and critical section length; do not trade correctness for speculative performance.
9. **Test interleavings:** use multiple workers, `CountDownLatch`, invariant assertions, and stress tests; passing a few runs does not prove the absence of races.
10. **Keep guarantees within their true scope:** local locks do not automatically protect other processes or external data sources.

**Remember:** thread safety is a property of **the entire state-access protocol**, not of the `private` keyword or a few isolated `synchronized` methods. Effective encapsulation keeps update authority inside the object, protects the same invariant with a consistent synchronization policy, and only exposes data externally through APIs that do not leak mutable state.