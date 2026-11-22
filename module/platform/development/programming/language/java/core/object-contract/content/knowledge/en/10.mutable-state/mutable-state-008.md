# Avoiding Comparing Concurrently Mutated State Without a Consistency Policy

When implementing `equals(Object)` and `hashCode()` for **mutable** objects, we often read multiple fields to decide whether two objects are equal. If another thread modifies those fields right in the middle of the comparison, the result can be based on **values from different points in time**. At that point, the program no longer has a clear policy on what state is being compared.

This problem appears especially in multithreaded Java: an expression `a.equals(b)` looks like a single operation in source code, yet internally it may perform multiple field reads, and Java **does not automatically make the entire `equals` call an atomic operation**.

This lesson clarifies the risk, its connection to the object contract, and the policies you can apply: preferring immutable objects, taking consistent snapshots, or synchronizing the entire read and write process when mutable objects are genuinely needed.

## 1. The `equals()`/`hashCode()` contract when state changes

For two objects `a` and `b`, a valid `equals` implementation must be reflexive, symmetric, transitive, consistent when the information used for comparison **does not change**, and `a.equals(null)` must be `false`. For `hashCode`, if `a.equals(b)` is `true`, the two hash codes must be equal. Under the `Object.hashCode` contract, consecutive calls must return the same result provided no information used in `equals` changes.

The condition **"provided information used for comparison does not change"** is crucial. If state genuinely mutates, the result of `equals` or `hashCode` may change according to the class's rules; that by itself is not a contract violation. However, when one thread reads while another writes, lacking a synchronization policy introduces three additional risks:

- **Inconsistent reads:** one field is read from an old version and another field from a new version, causing the comparison to reflect a state that was never published as a whole.
- **Schedule-dependent results:** on the same pair of references, two back-to-back comparisons can yield different outcomes, or fail to reflect the logical instant the program intended.
- **Mismatch between `equals` and `hashCode` at usage time:** `equals` and `hashCode` may observe different versions of the data under concurrent operations, which is especially dangerous for keys in hash-based collections.

The `equals` specification does not promise stability while relevant fields are being modified; it is the class's threading design and contract that must specify what happens in that case.

## 2. Why can field-by-field comparison observe mixed state?

Suppose a logical configuration must update two fields `endpoint` and `timeoutMs` **together**:

| Moment | `endpoint` | `timeoutMs` | Meaning |
| --- | --- | --- | --- |
| Version 1 | `alpha` | `100` | Valid old configuration |
| During field-by-field update | `beta` | `100` | Intermediate state if the two fields are assigned separately |
| Version 2 | `beta` | `200` | Valid new configuration |

The following illustrative snippet **is not yet a standalone program**:

```java
// Inside an equals(Object) that has already checked the proper type.
return timeoutMs == other.timeoutMs
        && Objects.equals(endpoint, other.endpoint);
```

If another thread updates the same object, the two expressions can read the fields at different moments. Even if each field is declared `volatile`, **`volatile` only provides visibility and ordering guarantees appropriate for each individual access**, rather than combining reads of `endpoint` and `timeoutMs` into one atomic snapshot.

Similarly:

- `Objects.equals(x, y)` helps handle `null`; it **does not lock** `x` or `y`.
- `synchronized` on each individual getter only protects each single call; if the lock is released between two getters, a writer can interleave.
- `ConcurrentHashMap` protects map operations per its contract; it **does not automatically protect mutable fields inside keys/values**.
- Even independent `AtomicInteger` / two `AtomicReference` instances do not create a transaction across the pair of fields.

Do not rely on "no bug was observed during testing": bugs depend on scheduling, CPU, optimizations, and synchronization details.

## 3. Preferred policy: compare immutable values

The simplest and most verifiable approach is to **define the state to be compared as an immutable object**. Instead of updating individual fields directly on an object being read by others, create a new value and publish the whole thing via an atomic reference replacement.

In Java 17+, a `record` fits well for representing a snapshot with simple, immutable components such as `String` and `int`. A record auto-generates `equals`, `hashCode`, and `toString` based on its components. Note: a `record` holding a reference to a `List` or array **does not automatically make the inner data deeply immutable**; if the referenced part remains mutable, you must defensively copy or use an appropriate immutable representation.

### Runnable Java 17+ program

Save as **`SnapshotComparisonDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicReference;

public class SnapshotComparisonDemo {
    record Settings(String endpoint, int timeoutMs) {}

    static final class LiveSettings {
        private final AtomicReference<Settings> current =
                new AtomicReference<>(new Settings("alpha", 100));

        Settings snapshot() {
            return current.get();
        }

        void replace(Settings next) {
            current.set(next);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        LiveSettings live = new LiveSettings();

        Settings before = live.snapshot();
        CountDownLatch startWriter = new CountDownLatch(1);

        Thread writer = new Thread(() -> {
            try {
                startWriter.await();
                live.replace(new Settings("beta", 200));
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });
        writer.start();

        startWriter.countDown();
        writer.join();

        Settings after = live.snapshot();
        Settings equalCopy = new Settings("alpha", 100);

        System.out.println("Before: " + before);
        System.out.println("After: " + after);
        System.out.println("Old snapshot unchanged: " + before);
        System.out.println("Before equals copy: " + before.equals(equalCopy));
        System.out.println("Before hash matches copy: "
                + (before.hashCode() == equalCopy.hashCode()));
        System.out.println("Before equals after: " + before.equals(after));
    }
}
```

Compile and run:

```bash
javac SnapshotComparisonDemo.java
java SnapshotComparisonDemo
```

Deterministic output:

```text
Before: Settings[endpoint=alpha, timeoutMs=100]
After: Settings[endpoint=beta, timeoutMs=200]
Old snapshot unchanged: Settings[endpoint=alpha, timeoutMs=100]
Before equals copy: true
Before hash matches copy: true
Before equals after: false
```

**Why is this example safe under concurrent updates?**

1. `Settings` is an immutable value within the scope of the example: neither `endpoint` (immutable `String`) nor `timeoutMs` is modified after creating the record.
2. `AtomicReference<Settings>` holds **a single reference** to the entire configuration. `current.set(next)` publishes a new record via atomic reference replacement, rather than writing two fields of a record currently being used by readers.
3. `snapshot()` calls `current.get()` **once**. A reader may receive either the full old version or the full new version if an update is in progress, never a mixed pair of fields from separate reads.
4. `CountDownLatch` and `Thread.join()` in the example simply clarify observation order so stdout can be checked deterministically. Once the writer thread finishes, `after` is the new version. `before` keeps the old state.
5. `before.equals(equalCopy)` and `before.hashCode() == equalCopy.hashCode()` are consistent because neither snapshot mutates anymore.

The `AtomicReference` solution fits when an update **replaces the entire state value**. If multiple writers must update based on the current value and must not overwrite each other's updates, an appropriate policy such as `compareAndSet`/`updateAndGet` loops with side-effect-free update functions, or locks for complex invariants, must be used.

## 4. A single snapshot per object is not necessarily a global snapshot

Suppose there are **two independent mutable objects** `left` and `right`. If you take `left.snapshot()` at time T1 and then `right.snapshot()` at T2, the two individual snapshots may each be self-consistent, yet **they are not guaranteed to belong to the same logical instant**.

There are three common policies; you should **choose and explicitly document** one policy for the API:

| Policy | Meaning of comparison | When appropriate |
| --- | --- | --- |
| Compare two separately captured snapshots | Each side is a valid value at its capture time; same instant is not promised | Comparing independent configs, logs, UI allowing time-skewed state |
| Consistent snapshot under a shared lock | Blocks relevant writers across the entire span of capturing both sides | When fields/multiple objects must belong to one logical version |
| Versioned/transactional snapshot | Compares only when a version passing validation is read; retries on conflict | Systems with version counters, optimistic reads, or transaction support |

If both objects can be protected under **one shared lock**, the comparison operation must hold the lock throughout producing the readable values. With two independent locks, you must define a **fixed lock-acquisition order** to prevent deadlocks and ensure all relevant readers/writers follow the same protocol. Locking only one side, or locking each side once and releasing, may not satisfy global consistency requirements.

An application-level snapshot comparison pattern:

```java
// Java pseudocode: caller holds appropriate locks/executes a transaction
// before creating both snapshots.
var leftSnapshot = left.captureState();
var rightSnapshot = right.captureState();
return leftSnapshot.equals(rightSnapshot);
```

This is a **design pattern**, not a standalone runnable snippet: the two `captureState()` methods and the locking/transaction mechanism must be provided by the application. Even though the code looks short, correctness comes from the **writer/reader coordination protocol**, not from method names.

With optimistic versioning, a reader can read a version before and after the data and accept only when the version is valid and data did not change during the read window. Implementing versioning requires proper memory visibility, writer rules, and exact update ordering. Sloppy version checks, missing writer protocols, or ignoring the ABA problem (changing and returning to the same version) can still be buggy.

## 5. When should you avoid overriding `equals` based on live state?

Some classes actually represent **entities with stable identity** (for example, an order with an ID), while attributes such as status, price, description, and location change over time. If `equals` compares every live attribute, the same entity before and after an update can be considered "not equal"; sometimes that is not the goal of the model.

Define upfront what "equal" means:

- **Value object:** two objects are equal when their **immutable logical values** are equal. Snapshots or immutable records are natural choices.
- **Entity with a stable ID:** comparison can rely on a **stable identifier, unique within the business domain**, allocated and managed consistently. If the ID is assigned late or changes across the lifecycle, the `equals`/`hashCode` design must handle it carefully; do not substitute `hashCode` for an ID.
- **Concurrently mutated state:** many fields may change without needing to belong to the wrapper's `equals`. Provide a `snapshot()` API so callers **compare frozen versions**, and clearly document state-capture semantics.

Not every class should override `equals`. For a resource/session manager whose semantics is instance identity, the default `Object.equals` can be more accurate than reading continuously changing state.

## 6. Especially dangerous: mutable keys in `HashMap` or `HashSet`

Suppose `hashCode` depends on `status` or `name`, and the object is placed as a key in a `HashMap`. If another thread subsequently changes that field, `hashCode` at lookup time can differ from the hash at insertion time, causing `map.get(key)` to fail to find the element even while holding the exact key reference.

This **is not cured** merely by using `ConcurrentHashMap`. The map can handle map operations concurrently per its contract, yet it cannot turn a key object with mutable `equals`/`hashCode` into a stable key.

Safer approaches:

- Use immutable keys such as `String`, `UUID`, a `record Key(...)` containing immutable components, or a stable business-domain ID.
- If lookup by snapshot is needed, insert the **immutable snapshot** as the key; the old snapshot retains its contents and hash after live state is updated.
- If a mutable key must be used, a very strict protocol is required so fields participating in `equals`/`hashCode` never change during the entire time the key resides in the hash structure. Locking around a single `put` is insufficient if fields still change later.

For example, in the program in section 3, the `Settings` object retrieved from `live.snapshot()` does not change when `live.replace(...)` is called; using the snapshot as a key has stable semantics compared to using the live wrapper with a `hashCode` that changes with `current.get()`.

## 7. Common misconceptions

1. **"I marked every field `volatile`, so the pair will be consistent."** No. Individual reads/writes have proper visibility, yet the pair of operations does not automatically become a transaction.
2. **"Putting `synchronized` on getters is enough."** Not necessarily. A writer can interleave between two getter calls once the lock is released; requiring a multi-field snapshot means keeping the same protocol across the entire capture span.
3. **"Calling `Objects.equals` is automatically thread-safe."** No. It merely handles `null` and then calls `equals` when needed.
4. **"A `record` is always deeply immutable."** No. Reference components can point to mutable lists, arrays, or objects. You must freeze/copy the data that `equals` and `hashCode` depend on.
5. **"Two individual snapshots agreeing means they reflect the same point in time."** No. If a consistent transaction across multiple entities is required, you must coordinate the capture process.
6. **"`ConcurrentHashMap` fixes all bugs with mutable keys."** No. Rules about keys and the hash contract must still be upheld by the application.
7. **"You can fix races by re-reading until two reads match."** That cannot be relied upon as a general guarantee without versioning/synchronization followed by writers; values can change back and forth, visibility may be inadequate, and the loop might never terminate.
8. **"`a.equals(b)` always gives one unique result for a pair of references."** That only holds when the `equals` rule and state are kept sufficiently stable. For mutable live data, explicitly state **which version** is being compared.

## 8. Design and review checklist

Before using `equals`/`hashCode` on data with multithreaded updates, answer the following questions:

1. Which fields determine equality? Are they immutable or can they be modified by another thread?
2. Is a same-instant snapshot required across multiple fields or multiple objects, or does each object only need individual consistency?
3. Do all readers and writers use the same protocol (atomic publication, locking, versioning, or transactions)?
4. If using locks, does the lock scope cover the **entire read operation of the data needed for comparison**? Is there any deadlock risk between two locks?
5. If comparing two snapshots, do they contain appropriate deep/immutable copies of mutable components?
6. Is the object serving as a key in a hash-based map/set? Are its hash and `equals`-participating fields stable throughout its time stored in the map/set?
7. Do tests exercise multiple writer threads, multiple versions, and business-domain invariants? Is there a way to measure/log snapshot versions when debugging?

**Takeaway:** `equals()` is a check according to an **equality rule**, not a synchronization barrier. When state can be mutated concurrently, you must clearly define **which version is being compared** and ensure readers/writers follow that same policy. Prefer comparing **immutable snapshots**; if the state of multiple objects at one logical point in time is required, use synchronization or transactions with sufficient scope.