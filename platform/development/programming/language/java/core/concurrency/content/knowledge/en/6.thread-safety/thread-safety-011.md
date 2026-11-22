# Identifying Mutable Collaborators That Break Thread Safety in Java

A class can use `private`, `final`, and `synchronized` with completely valid syntax and still be **not thread-safe** because it depends on a mutable object to which another thread also holds a reference. That dependent object is called a **collaborator**. If a collaborator has **mutable state** and is not protected by the same synchronization protocol, the safety assumptions of the outer class can be broken.

A common example is a class that uses a lock to protect a `List` but accepts an `ArrayList` from the caller and stores the raw reference, or returns the internal list directly through a getter. The caller can modify the list without acquiring the class's lock. Even a perfect internal lock **cannot coordinate external access paths that it does not control**.

This article focuses on **general Java concurrency**: object graphs, aliasing, encapsulation, memory visibility, defensive copying, immutable snapshots, thread-safe collaborators, and how to verify synchronization contracts. Spring-specific mechanisms are out of scope.

## 1. What is a “mutable collaborator”?

A **collaborator** is an object that a component calls or uses to perform its work: a dependency passed through a constructor/setter, a collection stored in a field, a cache, a formatter, a callback, a clock, a client, a repository, a listener, or an object that contains other objects. A collaborator can be a Java library class, a custom class, or an API of another system.

A **mutable collaborator** is a collaborator whose internal state or referenced data can change after being shared. Examples include:

- `ArrayList`, `HashMap`, `HashSet`, and mutable elements inside a collection.
- `StringBuilder`, `StringBuffer`, `java.util.Date`, `Calendar`, `ByteBuffer`.
- `SimpleDateFormat` (which holds formatting state and is not safe for concurrent use by multiple threads without synchronization).
- A configuration object with setters, a counter, a cache, a registry, or a worker that manages its own state.
- A collaborator that returns mutable data via `getItems()`, `getConfig()`, `getBuffer()`, even if the accessor itself is synchronized.
- A callback or listener that retains a reference to an object the component thinks it owns exclusively.

The danger is that **multiple threads can reach the same mutable object** and at least one thread can mutate it through a path that the main class does not control.

### Object graph and aliasing

```java
List<String> supplied = new ArrayList<>();
Registry registry = new Registry(supplied);
```

If the `Registry` constructor simply assigns `this.entries = supplied`, then `registry.entries` and `supplied` are **two references to the exact same object**. This is *aliasing*, not two independent copies. An external thread can still call `supplied.add(...)`, even after `registry` has been published to other threads.

A `private final List<String> entries` field does not prevent this: `private` only restricts access at the language level; `final` guarantees that the **reference** cannot be reassigned through the field after construction—it does not make the contents of the `List` immutable.

### When does a collaborator not cause problems?

- A collaborator is **thread-confined**: owned by only a single thread and never escapes to another thread.
- The collaborator is designed to be **truly immutable**, has been safely published, and contains no exposed mutable object branches.
- The collaborator is itself thread-safe for the **exact operations being used**, or all threads participate in the same consistent locking/synchronization protocol.
- The class owns a **private copy** of the incoming data and only exposes immutable values/snapshots, so callers cannot mutate internal state via an alias.

A mutable object is not necessarily a bug; you must examine **who it is shared with, which paths can mutate it, which invariants are being protected, and whether appropriate happens-before relationships exist**.

## 2. Why can a class with “all methods locked” still be wrong?

Consider the following illustrative class (a snippet, without `main`):

```java
import java.util.List;

class Registry {
    private final List<String> entries;

    Registry(List<String> supplied) {
        this.entries = supplied; // Stores the caller's raw alias
    }

    synchronized int size() {
        return entries.size();
    }

    synchronized void add(String value) {
        entries.add(value);
    }

    synchronized List<String> entries() {
        return entries; // Exposes the internal reference
    }
}
```

Every call to `size()`, `add()`, and `entries()` uses the monitor of the same `Registry` instance. However:

```java
List<String> callerList = new ArrayList<>();
Registry registry = new Registry(callerList);

callerList.add("ngoai-khoa");          // Bypasses the Registry monitor
registry.entries().clear();           // Getter returns the internal list directly
```

This is also a snippet; it requires importing `java.util.ArrayList`, `java.util.List`, and the `Registry` class above. Neither mutation **acquires Registry's monitor**. `synchronized` on the getter only protects the duration of retrieving/returning the reference; it **does not carry the lock along with the reference** to subsequent `add` or `clear` calls.

Several consequences can occur if threads actually access it concurrently without synchronization:

1. **Data race** on the internal state of the collection/elements due to the lack of a happens-before relationship.
2. **Broken invariants**: the class expects the element count, sum, order, or uniqueness to change only through controlled methods, yet the collaborator is modified externally.
3. **Incorrect visibility**: a thread holding the class lock is still not guaranteed to see updates made through a path that does not share the same lock as part of a proper synchronization cycle.
4. **Exceptions or inconsistent data**: iterating while concurrent modifications occur can trigger `ConcurrentModificationException`, skip elements, or produce nondeterministic results. Do not rely on fail-fast iterators as a protection mechanism: the exception is **not guaranteed** to be thrown every time.
5. **Unintended privilege escalation**: callers can mutate private state through an alias, even when all public methods of the class forbid or validate that operation.

**Rule:** the safety of a component depends on **every access path to the same mutable state**, not just the methods visible inside the main class.

## 3. Java 17 experiment: breaking invariants even while the owner holds the lock

The example below uses two `CountDownLatch` instances to create an explicit schedule. The worker holds the monitor of the `UnsafeInventory` object while waiting for `main` to directly modify the `seed` list whose alias the constructor retained. Afterward, the worker observes the changed list **inside its own critical section**.

We deliberately order the two reads around the modification; the program proves that **Inventory's lock cannot protect external modification paths**, without relying on a random data race.

Create `LeakyInventoryExample.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class LeakyInventoryExample {
    static class UnsafeInventory {
        private final List<String> items;

        UnsafeInventory(List<String> supplied) {
            this.items = supplied;
        }

        synchronized int countChangesWhileLocked(
                CountDownLatch entered, CountDownLatch externalChanged)
                throws InterruptedException {
            int before = items.size();
            entered.countDown();

            if (!externalChanged.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("External update timed out");
            }

            return items.size() - before;
        }

        synchronized int size() {
            return items.size();
        }

        synchronized List<String> getItems() {
            return items;
        }
    }

    public static void main(String[] args) throws Exception {
        List<String> seed = new ArrayList<>(List.of("A"));
        UnsafeInventory inventory = new UnsafeInventory(seed);
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch externalChanged = new CountDownLatch(1);
        ExecutorService pool = Executors.newSingleThreadExecutor();

        try {
            Future<Integer> difference = pool.submit(
                    () -> inventory.countChangesWhileLocked(
                            entered, externalChanged));

            if (!entered.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker did not enter lock");
            }

            seed.add("B"); // Never acquires inventory's monitor
            externalChanged.countDown();

            System.out.println("changedWhileLocked="
                    + difference.get(5, TimeUnit.SECONDS));

            inventory.getItems().add("C"); // Alias leaked from getter
            System.out.println("sizeAfterEscapedMutation="
                    + inventory.size());
        } finally {
            externalChanged.countDown();
            pool.shutdownNow();
        }
    }
}
```

Compile/run with Java 17+:

```bash
javac LeakyInventoryExample.java
java LeakyInventoryExample
```

Stdout when the program completes normally:

```text
changedWhileLocked=1
sizeAfterEscapedMutation=3
```

**Why is the output deterministic?**

- `main` initially has one element `"A"`; the constructor stores the exact `seed` object without copying.
- The worker acquires `inventory`'s monitor, reads size `1`, and signals `entered.countDown()`. The worker **has not released the monitor** because it is awaiting `externalChanged` right inside the synchronized method.
- `main` receives the `entered` signal and calls `seed.add("B")` directly. `main` does not need to acquire `inventory`'s monitor; the size becomes `2`.
- `main` triggers `externalChanged.countDown()`; the worker finishes waiting, reads size `2` while **still holding the monitor**, and returns `2 - 1 = 1`.
- After `Future.get`, `main` calls the getter (which is synchronized) and receives the internal reference; then `add("C")` executes **after the getter has released the monitor**, making the size `3`.

The latches establish the read/modify ordering in a **controlled experiment**. Therefore, do not use this result as evidence that a data race without happens-before actually occurred during the measurement steps; it proves an **ownership/encapsulation** flaw: external code can mutate a resource that the class assumes it owns exclusively.

**Key takeaway:** being inside a `synchronized` method does not mean all collaborators are protected. A lock only works when **every actor mutating the state adheres to the same lock**. Direct access via `seed` and the getter broke that contract.

## 4. Two common gateways: input and output

### 4.1. Constructor/setter retains mutable input

```java
class UnsafeSettings {
    private final List<String> hosts;

    UnsafeSettings(List<String> hosts) {
        this.hosts = hosts; // Caller still holds the reference
    }
}
```

If the caller modifies `hosts` after creating `UnsafeSettings`, the object's state changes too. Marking the field `final` only prevents the reference from being reassigned by the class itself; it copies neither the structure nor the elements.

**How to handle it:** when a component wants to own the data, copy the input into a private structure at the ownership boundary. If internal mutation is not needed, `List.copyOf(input)` gives an unmodifiable list that does not share the **list structure** for the caller to mutate; however, note that elements may still be mutable. If internal mutation is needed, use `new ArrayList<>(input)` (shallow copy) and protect all internal accesses with an appropriate locking protocol.

**Precondition for copying:** the source must be stable during copying or the caller must coordinate. Copying an `ArrayList` while another thread is modifying it **right as the constructor is copying** is not automatically safe. You usually need a contract stating “the input is not modified during handoff”, or a snapshot taken under the source owner's lock.

### 4.2. Getter returns a mutable object directly

```java
synchronized List<String> getEntries() {
    return internalEntries;
}
```

This is a snippet, assuming a field `internalEntries`. The getter is locked **only for the duration of the method execution**. Afterward, the caller holds the reference and can call `clear`, `add`, iterate, or pass the reference to another thread.

**How to handle it:** provide controlled operation methods (`add`, `remove`, `getSnapshot`) instead of allowing callers to mutate the entire data structure. When returning a read-only list, use a snapshot such as `List.copyOf(internalEntries)` **while holding the lock** (if elements are immutable). Returning a *live view* is a different API choice that requires its own synchronization contract; do not casually call it a snapshot.

### 4.3. Setters and callbacks also leak collaborators

A getter is not the only place where an alias can escape:

- A setter accepts a mutable object and stores the raw reference.
- A method passes `this`, an internal collection, a buffer, or a mutable entry to an external callback/listener; the listener can retain it.
- Iterators, `Map.Entry`, sublists, and views from `Map.keySet()` / `values()` / `entrySet()` can remain linked to the backing collection.
- `Collections.unmodifiableList(backing)` forbids modification **through the view**, but the owner can still mutate `backing` and the view reflects the changes: it is an *unmodifiable live view*, not necessarily a snapshot.
- `ByteBuffer.slice()` / `duplicate()` typically share the backing data region with the original buffer; different wrapper objects do not prove independent underlying data memory.
- Closures/lambdas or asynchronous tasks capturing mutable references can extend lifetimes and carry objects to other threads.

You should audit every boundary that a **reference** crosses, not just every `synchronized` statement.

## 5. Java 17: fixing with defensive copy and immutable snapshot

A straightforward fix: copy the input list at construction, perform all internal mutations through locked methods, and have the getter create an unmodifiable snapshot. This example uses immutable `String` elements, so copying the list structure is sufficient for the illustrated state scope.

Create `SafeInventoryExample.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class SafeInventoryExample {
    static class SafeInventory {
        private final List<String> items;

        SafeInventory(List<String> source) {
            this.items = new ArrayList<>(source);
        }

        synchronized void add(String item) {
            items.add(Objects.requireNonNull(item));
        }

        synchronized int size() {
            return items.size();
        }

        synchronized List<String> snapshot() {
            return List.copyOf(items);
        }
    }

    public static void main(String[] args) {
        List<String> input = new ArrayList<>(List.of("A"));
        SafeInventory inventory = new SafeInventory(input);

        input.add("B"); // Does not change the internal copy
        System.out.println("afterCallerMutation=" + inventory.size());

        List<String> oldSnapshot = inventory.snapshot();
        inventory.add("C");

        System.out.println("snapshotSize=" + oldSnapshot.size());
        System.out.println("currentSize=" + inventory.size());

        try {
            oldSnapshot.add("D");
            System.out.println("snapshotMutable=true");
        } catch (UnsupportedOperationException expected) {
            System.out.println("snapshotMutable=false");
        }
    }
}
```

Run:

```bash
javac SafeInventoryExample.java
java SafeInventoryExample
```

Exact stdout:

```text
afterCallerMutation=1
snapshotSize=1
currentSize=2
snapshotMutable=false
```

**Explanation:**

- `new ArrayList<>(source)` creates a **private list structure** right in the constructor. When the caller adds `"B"` to the original list, it no longer modifies the inventory.
- `synchronized` on `add`, `size`, and `snapshot` uses the **same monitor** to protect operations on the privately owned state.
- `List.copyOf(items)` returns a collection that does not support structural modification through the returned reference; when the inventory adds `"C"`, the old snapshot still has size `1`.
- Because the elements are immutable `String` objects, the caller cannot mutate an element to alter the contents of the snapshot/inventory via an element alias. With mutable element objects, additional protection at the element layer is required.
- If the contract allows `null` in the list, `List.copyOf` is unsuitable because it rejects null elements; adjust the representation or validate input explicitly rather than assuming every collection accepts null.

**Locks are not always needed:** if a class only stores a safely published immutable list with no subsequent updates and immutable elements, readers can read without locking around each access. The example above intentionally allows mutation via `add`, so it chooses a shared monitor to clearly demonstrate ownership.

## 6. Major pitfall: shallow defensive copy does not protect mutable elements

Neither `new ArrayList<>(source)` nor `List.copyOf(source)` automatically *deep-copies* the objects inside. For a `List<MutableUser>`, both the copied list and the original list still reference the **exact same User instances**. Thus, a class may have copied the collection yet still leak collaborators at the element level.

Create `ShallowCopyExample.java`:

```java
import java.util.List;

public class ShallowCopyExample {
    static class MutableUser {
        private String name;

        MutableUser(String name) {
            this.name = name;
        }

        String name() {
            return name;
        }

        void rename(String name) {
            this.name = name;
        }
    }

    record UserView(String name) { }

    public static void main(String[] args) {
        MutableUser user = new MutableUser("An");
        List<MutableUser> copied = List.copyOf(List.of(user));

        user.rename("Binh");
        System.out.println("copiedElementName="
                + copied.get(0).name());

        List<UserView> valueSnapshot = copied.stream()
                .map(u -> new UserView(u.name()))
                .toList();

        user.rename("Chi");
        System.out.println("valueSnapshotName="
                + valueSnapshot.get(0).name());
        System.out.println("originalName=" + user.name());
    }
}
```

Run with Java 17+:

```bash
javac ShallowCopyExample.java
java ShallowCopyExample
```

Stdout:

```text
copiedElementName=Binh
valueSnapshotName=Binh
originalName=Chi
```

The `copied` list is **unmodifiable**, but the `MutableUser` element has a `rename` method. When modifying the `user` object, `copied.get(0)` observes the new name because it is still the **same instance**. Then the program creates `UserView` containing `String` (immutable), so renaming `user` a second time does not change the value snapshot.

This is a sequential experiment to explain aliasing; in a real multi-threaded environment, if one thread renames while another thread reads the name without synchronization, visibility issues also arise.

### How to design a truly safe owner when elements are mutable?

- At the entry boundary: if the owner needs to hold mutable entities, create **independent copies of each element**, or convert them into immutable value objects. The contract must state clearly whether deep copying is performed.
- Inside the owner: protect **every update and every snapshot** with the same lock, or organize the state as an immutable aggregate and swap the reference atomically.
- At the exit boundary: return only **value snapshots** (e.g., records containing `String`, `int`, and other immutable values) or defensive copies that share no mutable children; do not return internal mutable entities.
- If a record contains `List<MutableUser>`, the `record` keyword does not automatically deep-freeze the list or its elements. A record only generates final fields and standard methods; defensive copying/validation is still needed in the constructor and accessors when mutable members are present.
- Deeper copying costs more CPU/memory; consider an immutable model by design rather than copying the entire graph on every request.

## 7. Synchronizing the right class but the wrong lock identity

Suppose an `Account` holds a mutable collaborator `Ledger`. `Account` locks on `this`, while other code modifies `Ledger` directly or locks on `ledger` instead of `account`:

```java
class Account {
    private final Ledger ledger;

    Account(Ledger ledger) {
        this.ledger = ledger;
    }

    synchronized void debit(int amount) {
        ledger.debit(amount);
    }
}
```

This is a snippet, `Ledger` is not defined; it is not a standalone program. `synchronized` on `Account.debit` only blocks callers that also try to acquire the monitor **of the same Account instance**. It **does not force** code holding a reference to `ledger` to acquire that monitor. Two different `Account` instances could even reference the same `ledger` while acquiring **two different monitors**. Consequently, `Ledger` state can still be updated concurrently.

Three ways to solve this, depending on ownership and contract:

1. **Account owns Ledger exclusively:** the constructor accepts value data and creates `Ledger` internally; it never exposes the `Ledger` reference, only operations/snapshots.
2. **Ledger is shared and thread-safe on its own:** all `Ledger` operations must have appropriate atomicity/visibility contracts. However, if business logic requires “check balance then debit”, **the entire sequence** must be protected, not just individual methods.
3. **One shared lock/protocol for all actors:** only when every access path truly adheres to the same lock can compound invariants be protected. Passing a lock object across the system has design overhead and deadlock risk; if it is hard to manage, designing clear ownership/encapsulation is usually cleaner.

### Lock ordering and unintended collaborator calls

If `Account` holds lock A and calls an external collaborator that calls back into `Account` or acquires lock B, another thread might hold B and wait for A, creating a deadlock cycle. This is especially dangerous when invoking **user-supplied callbacks** or unbounded I/O inside a critical section. Try to create an immutable event snapshot **inside** the lock and invoke the callback **after releasing the lock** if business logic allows. When callbacks run outside the lock, you must clearly define **event ordering across threads** if consumers depend on order.

## 8. A thread-safe collaborator is not enough for every invariant

A collaborator documented as “thread-safe” does not mean an entire sequence of operations using it is atomic.

### `ConcurrentHashMap` example

```java
if (!cache.containsKey(key)) {
    cache.put(key, createValue());
}
```

This is a snippet, assuming `cache` is a `ConcurrentHashMap<Key, Value>`. Individual `containsKey` and `put` operations have their own guarantees. However, two threads can both observe that the key does not exist and both call `createValue()`; the final map state may retain only one value, but the **side effect of creating the data happened twice**.

You can use `computeIfAbsent(key, mappingFunction)` or `putIfAbsent` if their semantics match your exact requirements. The mapping function of `ConcurrentHashMap.computeIfAbsent` should be short, clear, and avoid modifying the map itself along paths that could cause deadlocks or errors. If `createValue()` calls a database or external API with side effects, consider transactions/idempotency and failure/retry—do not assume a single map call solves everything.

### `Collections.synchronizedList` example

`Collections.synchronizedList(list)` protects individual wrapper methods with its corresponding monitor. However:

```java
List<String> syncList =
        java.util.Collections.synchronizedList(new ArrayList<>());

synchronized (syncList) {
    for (String item : syncList) {
        System.out.println(item);
    }
}
```

This is a snippet requiring imports for `java.util.List` and `java.util.ArrayList`; it illustrates the pattern from the JDK documentation: **when iterating over the collection with an iterator, the caller must manually synchronize on the exact wrapper list** to prevent interleaved mutations through the wrapper during iteration. If someone still holds the **original backing list** and modifies it directly outside the wrapper, this lock block is still bypassed. It is best not to let the backing mutable reference be usable outside the contract.

### Thread-safe operations but mutable values example

`ConcurrentHashMap<String, MutableUser>` is safe at the map-operation level, but it does not make `MutableUser.rename(...)` thread-safe. Retrieving a reference from the map and mutating the object without synchronization can still race. Concurrent collections only protect the scope promised by their API; every **value object** and related invariant must be examined separately.

## 9. Visibility and safe publication do not replace ownership

The Java Memory Model provides *happens-before* (HB) relationships. For example:

- Releasing a monitor happens-before a **subsequent acquisition of the same monitor**.
- Writing to a `volatile` field happens-before a subsequent read of that same field under JMM rules.
- Actions before `Thread.start()` happen-before actions in the started thread.
- Actions in a worker happen-before the caller observes the thread terminating via a corresponding `Thread.join()`.
- `java.util.concurrent` utilities have memory-consistency effects defined by their respective contracts.

These mechanisms ensure data is published and observed in the specified order. However, **safe publication only solves handing off already-constructed state**; it does not protect subsequent mutations if multiple threads still hold mutable aliases.

For example:

```java
class Holder {
    volatile List<String> values;
}
```

Assigning an `ArrayList` reference to `volatile values` ensures other threads see the new reference according to volatile semantics; it **does not make `values.add` or `values.clear` thread-safe**, nor does it guarantee that ongoing iterations are not interleaved with modifications. If you want to swap in an immutable snapshot, the writer creates a new immutable list object and assigns `volatile values = List.copyOf(...)`, while readers grab **one reference** and read only that snapshot. You must still ensure elements are immutable or appropriately copied, and multiple writers merging changes may need CAS/locks to avoid lost updates.

### What do `final` fields guarantee?

A properly constructed object with `final` fields has specific initialization safety guarantees. However:

- `final` **does not create mutual exclusion** for operations after the constructor.
- `final List<T>` does not make every `T` object immutable.
- If `this` escapes during construction (registering a listener or starting a thread too early), publication assumptions can be broken.
- If the constructor receives a mutable collaborator from another thread, the caller can still mutate it afterward; a `final` field only locks the reference, not ownership of the object.

**The right question:** not just “how is the reference published?”, but also “who is allowed to mutate **the entire object graph reachable from that reference** after publication?”.

## 10. Collaborators easily overlooked during code review

| Collaborator | Why it can be mutable / dangerous | Typical appropriate handling |
| --- | --- | --- |
| `List`/`Map` passed via constructor | Caller keeps an alias, mutates without owner's lock | Copy structure, establish clear ownership |
| Mutable elements inside an immutable list | Structure is fixed, element objects can still change | Immutable values / deep copy as needed |
| Getter returning internal map/list | Reference escapes after getter unlocks | Return a snapshot or operation API |
| `Collections.unmodifiableList(backing)` | Read-only *view* still changes when backing changes | `List.copyOf` or copy under lock for a snapshot |
| `Map.keySet()`, `entrySet()`, `subList()` | Views remain linked to the backing collection | Return an independent snapshot if isolation is needed |
| `Date`, `Calendar` | Timestamp/configuration can be mutated | Prefer immutable `java.time` types like `Instant`, `LocalDate` |
| `SimpleDateFormat` | Holds mutable formatting state | `DateTimeFormatter` (immutable, thread-safe by API contract) |
| `StringBuilder` | Mutable buffer and not thread-safe | Per-task builder or produce immutable `String` |
| `StringBuffer` | Methods are synchronized, but multi-step sequences are not atomic | Hold proper lock around the whole workflow or confine |
| `ByteBuffer`/backing array | Slice/duplicate can share underlying bytes | Copy data when separate ownership is needed, apply locking protocol |
| Listener/callback | May retain reference and mutate later, or be reentrant | Pass immutable events, define lock/order/lifecycle |
| Cache with mutable values | Thread-safe cache only protects map operations | Use immutable values or synchronize the values themselves |
| `ThreadLocal<T>` holding a mutable object | Limits cross-thread sharing, but worker pools reuse threads | Clean up with `remove()` per lifecycle; do not pass values across threads |
| A mutable config object | Setters change config while tasks are reading | Immutable configuration snapshot, volatile/atomic publish |
| Mutable API client/session | Thread-safety contract may be limited per method or instance | Read docs, one client/session per task if needed, bound lifecycle |

**Do not assume a class name implies thread-safety.** A library may allow certain operations concurrently without guaranteeing the result of a multi-call sequence, or it may require that the input collection not be mutated during an operation.

## 11. A method for identifying mutable collaborators in a codebase

Instead of just searching for the `synchronized` keyword, draw an **ownership map of mutable state**.

### Step 1: Find all direct and indirect mutable state

Non-`final` fields, collections, caches, configurations, buffers, listener lists, objects with setters, and mutable value objects are all candidates. For each reference field, check whether **the object's contents** can change, including multi-level children.

### Step 2: Trace who creates/holds the reference

Ask: does the reference come from a constructor, setter, factory, static singleton, library getter, or cache result? Does the caller still hold the reference after handing it to the component? If an object is received from outside without an explicit copy or ownership transfer, assume an alias may still exist.

### Step 3: Find every escape path

Audit return values, callback arguments, listener registrations, getters, iterators/views, lambdas/async tasks, methods taking `Consumer`/`Function`, objects inserted into shared collections, and returning `this`. An internal reference escaping the class can be used on another thread unseen by the class.

### Step 4: Read the collaborator's thread-safety contract

Questions to answer:

- Is it thread-safe for the **entire instance** or only specific methods?
- Are mutating operations linearizable/atomic? Which compound operations are not guaranteed?
- Does it require callers to synchronize during iteration?
- Does the API return a **copy, snapshot, live view, or alias**?
- Can an instance be shared across threads, or does it require thread confinement?
- Does it require inputs not to be mutated while a method runs?
- If a callback is invoked while holding a lock, can it reenter the component?

Without documentation, never assume a mutable collaborator is safe on its own.

### Step 5: List invariants and protection boundaries

For example: “size never exceeds capacity”, “balance is non-negative”, “a key is created once”, “fields belong to the same version”. Determine whether **the entire read–check–write** sits inside a single atomic operation/critical section or is split across multiple calls that can interleave. Locking `add` alone is insufficient if `canAdd` is checked separately before calling `add`.

### Step 6: Check lock identity and happens-before

Is the same mutable object accessed through multiple wrappers/owners? Do they use **the exact same lock**? Are there unlocked reads, direct accesses from callers, or reads through views? Is there volatile/safe publication ensuring proper visibility? Never infer thread-safety merely from “I see a lock somewhere.”

### Step 7: Build tests that force bypass paths

A test can hold the owner's lock on thread A and have thread B modify the collaborator via an alias. If B can still mutate the state, the owner's lock does not control all modification paths. Use `CountDownLatch`/`CyclicBarrier` to coordinate, timeouts so tests do not hang, and `Future.get` to propagate worker errors to the test runner. Tests do not replace Java Memory Model analysis, but they pinpoint design flaws accurately.

### Step 8: Evaluate fixes and trade-offs

You can switch to immutable values, defensive copies, read-only interfaces, thread confinement, message passing, or a synchronized/atomic operation covering the entire invariant. Also consider the cost of large copies, memory, GC, throughput, lock contention, deadlocks, and callback ordering. Do not fix only a getter and forget the constructor alias.

## 12. Two common “half-fix” mistakes

### 12.1. Wrapping only with `Collections.unmodifiableList`

```java
List<String> backing = new ArrayList<>(List.of("A"));
List<String> view = java.util.Collections.unmodifiableList(backing);

backing.add("B");
// view.size() is now 2.
```

This is a snippet requiring imports for `java.util.List` and `java.util.ArrayList`. Callers cannot invoke `view.add`, but `backing.add` can still be called. If you want a snapshot, create **an independent value structure** from `backing` at the desired point in time, such as `List.copyOf(backing)` when the source is stable or properly protected.

### 12.2. Using only `volatile` on the reference

```java
private volatile List<String> shared = new ArrayList<>();
```

This is a field declaration inside a class. `volatile` is useful for **publishing/swapping the reference**, but it does not make the internal methods of `ArrayList` safe when multiple threads mutate it concurrently. Increasing visibility does not create mutual exclusion. For manual copy-on-write, a writer can copy the old state, modify the copy, and publish a new immutable snapshot; with **multiple writers**, a shared lock or CAS loop is needed to prevent one writer from overwriting another writer's snapshot.

## 13. Immutable snapshots and versioned publication

A design with many readers and few writers can hold state as an immutable record and publish the whole state via a single volatile reference:

```java
import java.util.List;

record InventoryView(int version, List<String> items) {
    InventoryView {
        items = List.copyOf(items);
    }
}

class SnapshotInventory {
    private volatile InventoryView current =
            new InventoryView(0, List.of());

    InventoryView read() {
        return current;
    }

    synchronized void add(String item) {
        InventoryView old = current;
        List<String> next = new java.util.ArrayList<>(old.items());
        next.add(item);
        current = new InventoryView(old.version() + 1, next);
    }
}
```

This is a **compilable snippet if placed in an appropriate file**, though it has no `main`. The record constructor enforces copying the list structure into an immutable representation (elements here are `String`). Readers only need to call `read()` **once** to get a consistent version and contents; writers synchronize when performing read–modify–publish, preventing lost updates among multiple writers. When writing the volatile `current` field, the state is published under the JMM contract. Once the snapshot is published, readers do not need to hold the writer's lock to read that snapshot.

If the data is large and updated continuously, copying the entire `List` on every addition can be costly in memory/CPU; consider persistent data structures, partitioned ownership, or another synchronization mechanism. If elements are mutable, the list copy is still shallow: design immutable elements or deep copy per contract.

## 14. Calling callbacks from a thread-safe object

A component may own its state safely yet invoke a listener in a way that exposes it:

```java
synchronized void notifyListener(Consumer<List<String>> listener) {
    listener.accept(internalItems);
}
```

This is a snippet assuming imports for `java.util.function.Consumer`, `java.util.List`, and a field `internalItems`. The caller-supplied listener can retain the reference for later use, or call `clear()` right inside the callback. The method's lock does not restrict the listener's actions after the method returns; moreover, a reentrant or long-blocking callback while the owner holds the monitor can cause latency and deadlocks.

A safer pattern when business logic permits:

```java
void publish(Consumer<List<String>> listener) {
    List<String> snapshot;
    synchronized (this) {
        snapshot = List.copyOf(internalItems);
    }
    listener.accept(snapshot);
}
```

This is also a snippet, assuming immutable elements and that the list only needs a snapshot. The listener can keep the `snapshot` reference without altering internal state; meanwhile, the owner has released its monitor before calling external code. If multiple threads publish different snapshots, **the order in which callbacks complete is not automatically the order in which state was updated**; if consumers require ordering, a queue/sequence number or explicit serialization protocol is needed.

## 15. What tests confirm a fix is correct?

**Ownership checks (can be run sequentially):**

1. Create mutable input, pass it to the constructor, and mutate the input. Does the owner's state change unexpectedly?
2. Call the getter/snapshot, try mutating the collection (if the API claims immutability) and mutating elements. Does the owner's state change?
3. Take two snapshots at two different times: is the old snapshot affected by a new update?
4. Test views from `subList`, `keySet`, `entrySet`, buffer slices, and callback references; do any still point to backing state?
5. If input is cloned, test multi-level nested structures; does shallow copying match the contract?

**Concurrency checks:**

1. Use two threads and latches to force an external modification path to run while the owner holds its monitor; observe invariants. `LeakyInventoryExample` tested this exact kind of bypass.
2. Create stress tests with multiple writers/readers on **real operations** and assert invariants after workers finish (with timeouts and fail-fast reporting).
3. Do not use `Thread.sleep` to “reliably” hit a race; use explicit conditional checkpoints.
4. For shared maps/lists, test compound operations (check–then–act), iteration during mutation, and mutable elements—not just isolated `add`/`get` calls.
5. Passing a test multiple times does not prove the absence of data races; code review for HB, lock ownership, and API contracts is still required.
6. If using virtual threads (Java 21+) instead of platform threads, the rules for mutable collaborators, publication, and atomicity **do not change**.

Also note: test orchestration can introduce **new happens-before edges** and mask certain visibility bugs. It is great for proving bypass paths and known logic flaws, but insufficient to prove all interleavings/JMM outcomes. Subtle memory ordering issues may require specialized stress/litmus tests.

## 16. Quick code-review checklist

For every class claiming to be “thread-safe”, check:

- **Object graph:** does the class hold only primitives/immutable values, or does it hold mutable collaborators?
- **Reference origin:** is the collaborator created exclusively inside, or passed from outside with the caller retaining an alias?
- **Escape paths:** do getters, callbacks, iterators, live views, elements, listeners, or async tasks return or retain mutable references?
- **Copy scope:** is only the structure copied, or are elements/child objects copied too? Is a deep copy required?
- **Locking discipline:** do all read/write paths use **the exact same lock identity**, or does the collaborator self-protect the full operation scope?
- **Compound operation contract:** can check–then–act, read–modify–write, or multi-field invariants be interleaved?
- **Visibility:** by what HB relationship is state published? Are `final`/`volatile` being mistaken for a mutex?
- **Thread-safe collections:** are the values/elements themselves mutable and in need of separate synchronization?
- **Callbacks:** is external code called while holding a lock? Are live references passed or unexpected side effects possible?
- **Testing:** are both the constructor path and getter path fixed? Do tests verify snapshots are unaffected when callers mutate inputs/elements?

## 17. Misconceptions to avoid

| Misconception | Reality |
| --- | --- |
| “All methods are `synchronized`, so the class is safe.” | If a mutable collaborator leaks or is mutated via an alias outside the monitor, the lock does not control all state. |
| “A `private final` field is immutable.” | Only the reference cannot be reassigned; the referenced object can still be mutable. |
| “A `synchronized` getter returning a list is thread-safe.” | The lock is only held during the getter; caller usage of the reference after return is unlocked. |
| “`List.copyOf` copies the elements too.” | It only creates an unmodifiable structure; mutable elements are still shared. |
| “`Collections.unmodifiableList` is a snapshot.” | It is typically a live view of the backing list; the backing list can still change. |
| “`ConcurrentHashMap` protects the map's values too.” | It does not make mutable value objects thread-safe. |
| “Collaboration is only about method calls.” | Passing and storing a **reference** also grants access to mutable state. |
| “Safe publication solves all future accesses.” | It ensures proper handoff; subsequent mutations still require a synchronization protocol. |
| “Having a `volatile List` makes `add/clear` safe.” | A volatile reference does not provide mutual exclusion for collection operations. |
| “Locking on any wrapper is fine.” | Actors must use the exact same lock, or the collaborator API must provide sufficiently strong guarantees. |
| “Running a concurrent test a few times is enough.” | Tests can miss dangerous schedules; ownership and happens-before must still be proven. |
| “An immutable record is always deep-immutable.” | A record containing mutable references requires proper defensive copying/immutable children. |

## 18. Self-check questions

**1. Why does `private final ArrayList<String> list` not guarantee thread safety?** Because `final` does not forbid mutating the list's contents. If the reference is shared, multiple threads can still mutate it; locking and ownership must still be clear.

**2. The constructor uses `new ArrayList<>(input)`, but the elements are `MutableUser`. Is it completely isolated?** No. Copying the list structure still shares references to each `MutableUser`. You need immutable elements, a deep copy, or synchronization for the elements.

**3. A synchronized getter returns an internal `List`. Do callers need to synchronize when calling `list.add`?** The getter has already released the monitor upon returning; callers can mutate without the lock and break invariants. Avoid leaking references and provide operations/snapshots with clear contracts.

**4. The owner locks on `this`, and the collaborator locks itself using a different monitor. Is that safe?** Only if the collaborator's contract and all compound invariants are properly protected. Two different monitors do not by themselves provide shared mutual exclusion for state that requires atomic updates.

**5. Is `List.copyOf` safe if the input is modified by another thread right during copying?** Not by default. You need a contract ensuring the input is not concurrently modified, or take the snapshot under an appropriate synchronization mechanism.

**6. If `ConcurrentHashMap` is thread-safe, is `map.get(k).setName(...)` thread-safe?** You cannot conclude that. `setName` mutates a mutable value; you must examine the thread-safety of the value itself.

**7. Does making a collaborator field `volatile` fix races on a mutable list?** No. `volatile` guarantees publication/reference visibility; it does not protect in-place mutations of the list.

**8. Why can `LeakyInventoryExample` prove a flaw even though it uses latches that create happens-before?** Because what needs proving is that **`main` can still mutate state via an alias while the owner holds the monitor**. The latches control ordering, and the output shows that locking the owner does not establish exclusive ownership over an exposed resource.

**9. When is a list snapshot enough, and when is a deep copy needed?** A list snapshot is enough when elements are immutable and invariants depend only on structure. If elements are mutable, examine usage conditions and create immutable values/deep copies for the data that needs isolation.

**10. Why should callbacks be invoked outside locks?** Callbacks can be slow, reentrant, acquire other locks, or retain references. When feasible, create an immutable event under the lock and notify outside the lock; if event ordering is required, add a separate mechanism.

**Key rule to remember:** *Thread safety is a property of the entire protocol accessing **the same mutable state**, including every collaborator and alias that can touch it.* A `final` field or a `synchronized` method only protects what it actually controls. Establish ownership, prevent mutable references from escaping, copy/publish immutable values when appropriate, and protect compound invariants with the same synchronization mechanism.
