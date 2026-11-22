# Atomic compound reference via immutable state

In Java concurrency programming, an operation often has to change **multiple fields at the same time** to preserve a business invariant. For example: decreasing the available slot count and increasing the reserved slot count; transferring money between two balances; or updating a configuration list together with its version. Two independent writes still create a **gap in between** where another thread can observe an incomplete state, even if each field uses `AtomicInteger`, `volatile`, or thread-safe getters.

**Atomic compound reference via immutable state** is a technique that bundles all fields that must stay consistent into **one immutable object**, then manages **a single reference** with `AtomicReference<State>`. A writer reads the current snapshot, creates a new snapshot, and uses `compareAndSet(old, next)` to **swap a single reference atomically**. A reader simply grabs one snapshot with `get()` and reads every component from that same snapshot.

The goal is to guarantee:
- **Readers never see a half-updated state** across the group of fields bundled in the same snapshot.
- **Writers do not lose updates** from other writers if conditions are checked, the new state is computed, and the commit uses a proper CAS loop.
- **Old objects are never modified**, so threads still holding an older snapshot continue to read a consistent version.

All mechanisms in this article are core Java (`java.util.concurrent.atomic` and the Java Memory Model), with no framework dependencies.

## 1. Why do multiple atomic fields still have invariant-level races?

Suppose an `Inventory` class manages two numbers:

```text
available >= 0
reserved >= 0
available + reserved == totalCapacity
```

This update is **not atomic as a pair**:

```java
// Illustration code: both variables are AtomicInteger.
available.decrementAndGet();
reserved.incrementAndGet();
```

`decrementAndGet()` and `incrementAndGet()` are safe **individually**, but a reader can run after the decrement and before the increment, seeing a temporarily wrong total. `volatile` does not solve this because it does not turn two writes into one transaction.

### Example 1 — Reproducing an inconsistent snapshot

Create **`SplitAtomicState.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class SplitAtomicState {
    public static void main(String[] args) throws InterruptedException {
        AtomicInteger available = new AtomicInteger(1);
        AtomicInteger reserved = new AtomicInteger(0);

        CountDownLatch firstWriteDone = new CountDownLatch(1);
        CountDownLatch allowSecondWrite = new CountDownLatch(1);

        Thread writer = new Thread(() -> {
            available.decrementAndGet();
            firstWriteDone.countDown();

            try {
                allowSecondWrite.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }
            reserved.incrementAndGet();
        }, "writer");

        writer.start();
        firstWriteDone.await();

        System.out.println("Intermediate: available="
                + available.get() + ", reserved=" + reserved.get());
        System.out.println("Intermediate total: "
                + (available.get() + reserved.get()));

        allowSecondWrite.countDown();
        writer.join();

        System.out.println("Final total: "
                + (available.get() + reserved.get()));
    }
}
```

Compile and run with JDK 17+:

```bash
javac SplitAtomicState.java
java SplitAtomicState
```

Output in a normal run without external interrupts:

```text
Intermediate: available=0, reserved=0
Intermediate total: 0
Final total: 1
```

The two `CountDownLatch` instances control the interleaving so `main` reads at the exact moment the first write has completed while the second write has not yet run. This is an **invariant race condition**, not a bug in `AtomicInteger` itself. The fact that the total eventually returns to 1 **does not make valid** the temporary total of 0 that a client could observe.

If clients need to read `available` and `reserved` as a single unit, there must be a protocol protecting both—such as a shared monitor or an immutable state snapshot published atomically.

## 2. Designing an immutable State: one version, multiple fields

We use a Java 17 record for the value object:

```java
record Inventory(int available, int reserved) {
}
```

This is a type definition snippet, not a standalone program. The record holds only two `int` values with no way to mutate fields after creation, so each instance is an **immutable snapshot**. When a change is needed, create a new object:

```java
Inventory old = new Inventory(2, 0);
Inventory next = new Inventory(1, 1);
// old is still (2, 0), next is (1, 1).
```

Use a single central reference:

```java
AtomicReference<Inventory> state =
        new AtomicReference<>(new Inventory(2, 0));
```

The snippet above requires importing `java.util.concurrent.atomic.AtomicReference`. A reader reads properly like this:

```java
Inventory snapshot = state.get();
int total = snapshot.available() + snapshot.reserved();
```

Notice: **call `get()` once**. If you write `int a = state.get().available(); int b = state.get().reserved();`, the two `get()` calls can receive **two different snapshots** if a writer updates in between, reproducing a mixed-version bug even though each snapshot is consistent on its own.

Correctness comes from **two combined parts**:

1. **Immutable snapshot:** once published, the object cannot be modified through any alias.
2. **AtomicReference:** `get()` reads a reference atomically; CAS commits a reference atomically while applying the appropriate Java Memory Model memory effects.

Merely placing `AtomicReference<MutableState>` and calling `state.get().setX(...)` **does not make internal mutations safe**. CAS only protects swapping the reference, not every setter on the object it points to.

## 3. CAS loop: read snapshot, compute new state, commit or retry

Algorithm skeleton:

```java
while (true) {
    State oldState = state.get();
    State newState = transform(oldState);
    if (state.compareAndSet(oldState, newState)) {
        break; // Commit succeeded.
    }
    // Another thread changed the state; must re-read and recompute.
}
```

This is an illustrative snippet assuming `State`, `state`, and `transform` are already defined. `compareAndSet(expected, update)` succeeds when the current reference **is the exact `expected` reference (`==`)**, and replaces it with `update` in one atomic step. It compares **identity**, not `equals()` on two records with identical components.

Example of two concurrent writers:

```text
current = S0

Thread A: get S0 -> create S1
Thread B: get S0 -> create S2

A: CAS(S0, S1) = true   -> current = S1
B: CAS(S0, S2) = false  -> does not overwrite S1
B: get S1 -> recompute S3 from S1
B: CAS(S1, S3) = true   -> current = S3
```

If B used `state.set(S2)` instead of retrying, A's update could be overwritten. **Atomic reference assignment** is different from an **atomic read-compute-write update**. The CAS loop establishes a *linearization point* at the successful CAS.

Mandatory rule: business conditions must also be checked **against the latest snapshot on every iteration**. Never read "two slots left" before the loop and keep trying to write if other writers have already taken all slots.

## 4. Example 2 — AtomicInventory: updating multiple fields together

Create **`AtomicInventory.java`**:

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class AtomicInventory {
    record Inventory(int available, int reserved) {
    }

    static final class Store {
        private final AtomicReference<Inventory> state =
                new AtomicReference<>(new Inventory(2, 0));

        boolean reserveOne() {
            while (true) {
                Inventory old = state.get();

                if (old.available() <= 0) {
                    return false;
                }

                Inventory next = new Inventory(
                        old.available() - 1,
                        old.reserved() + 1
                );

                if (state.compareAndSet(old, next)) {
                    return true;
                }
                // Retry with the new snapshot and re-check the available slots.
            }
        }

        Inventory snapshot() {
            return state.get();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Store store = new Store();
        AtomicInteger accepted = new AtomicInteger();

        Runnable request = () -> {
            if (store.reserveOne()) {
                accepted.incrementAndGet();
            }
        };

        Thread a = new Thread(request, "A");
        Thread b = new Thread(request, "B");
        Thread c = new Thread(request, "C");

        a.start();
        b.start();
        c.start();
        a.join();
        b.join();
        c.join();

        Inventory s = store.snapshot();
        System.out.println("Accepted: " + accepted.get());
        System.out.println("Available: " + s.available());
        System.out.println("Reserved: " + s.reserved());
        System.out.println("Total: " + (s.available() + s.reserved()));
    }
}
```

```bash
javac AtomicInventory.java
java AtomicInventory
```

Output:

```text
Accepted: 2
Available: 0
Reserved: 2
Total: 2
```

**Explanation:**

- Initially there is only the `Inventory(2, 0)` object.
- Each thread calls `reserveOne()` concurrently and may read the same snapshot. However, **only one CAS** with the same expected object wins while `current` is still that object.
- Threads whose CAS fails **do not modify state**. They must fetch the new snapshot, re-check `available`, and recompute.
- Ultimately two reservations succeed, resulting in `Inventory(0, 2)`. The third thread sees zero available slots on some iteration and returns `false`.
- **Which thread wins** is non-deterministic, but the invariant `available + reserved == 2` holds for **every published snapshot**.
- `accepted` is a measurement variable in the demo program, not part of protecting `Store`'s invariant. `join()` waits for all workers before `main` prints the final state.

Readers can call `store.snapshot()` while writers are running. The returned snapshot is never mutated, so even if another thread commits the next version, the reader still sees **a consistent version**. However, it may already be stale by the time the reader makes a decision; decisions that need to commit must go back through CAS or a lock, rather than relying solely on a previously read snapshot.

## 5. Returning a result after CAS and designing composite APIs

A real-world request often needs not only to know whether the reservation succeeded, but also the counts **right after that reservation**. Inside a CAS loop, you can return `next` **after CAS succeeds**, because that is the committed snapshot of the call.

```java
// Snippet inside Store; Inventory/state are defined as in Example 2.
Inventory reserveAndReturn() {
    while (true) {
        Inventory old = state.get();
        if (old.available() == 0) {
            return old; // Minimal example: branch when reservation fails.
        }
        Inventory next = new Inventory(
                old.available() - 1,
                old.reserved() + 1
        );
        if (state.compareAndSet(old, next)) {
            return next;
        }
    }
}
```

In a production API, define a result type that explicitly indicates **whether the reservation succeeded or failed**; do not force callers to infer it from the returned `Inventory`. The `next` snapshot reflects the exact committed state, yet **another thread can replace it immediately after CAS wins**. It is not a guarantee that "this will remain the latest state until the caller finishes processing."

Avoid designing an API with `getAvailable()` followed by `reserve()` and expecting callers to perform check-then-act themselves. Expose only composite operations like `reserveOne()` / `tryReserve()` so the invariant is enforced at the decision boundary.

## 6. Example 3 — Transferring money between two balances in the same snapshot

Another application is moving value from `checking` to `savings`. Invariant: both balances are non-negative and **their sum is constant**. We bundle both balances into a record so every commit updates both values as a single unit.

Create **`AtomicAccounts.java`**:

```java
import java.util.concurrent.atomic.AtomicReference;

public class AtomicAccounts {
    record Balances(long checking, long savings) {
    }

    static final class Ledger {
        private final AtomicReference<Balances> state =
                new AtomicReference<>(new Balances(100, 0));

        boolean moveToSavings(long amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("amount must be positive");
            }

            while (true) {
                Balances old = state.get();
                if (old.checking() < amount) {
                    return false;
                }
                Balances next = new Balances(
                        old.checking() - amount,
                        old.savings() + amount
                );
                if (state.compareAndSet(old, next)) {
                    return true;
                }
            }
        }

        Balances snapshot() {
            return state.get();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Ledger ledger = new Ledger();

        Thread a = new Thread(() -> ledger.moveToSavings(30));
        Thread b = new Thread(() -> ledger.moveToSavings(40));

        a.start();
        b.start();
        a.join();
        b.join();

        Balances s = ledger.snapshot();
        System.out.println("Checking: " + s.checking());
        System.out.println("Savings: " + s.savings());
        System.out.println("Total: " + (s.checking() + s.savings()));
    }
}
```

```bash
javac AtomicAccounts.java
java AtomicAccounts
```

Output:

```text
Checking: 30
Savings: 70
Total: 100
```

Both transfers of 30 and 40 can succeed from an initial balance of 100; either CAS order leads to 30/70. Every committed snapshot maintains a total of 100. **This is only an in-memory ledger example within a single JVM**: it does not provide durability, recovery, auditing, or cross-database/cross-process transactions. Real money requires proper arithmetic design (smallest integer currency units or `BigDecimal` with appropriate rules), transactions, and idempotency mechanisms in external systems. CAS **does not** replace the data-owning system's transactions.

## 7. Immutable means no mutable aliases: a record is not enough in every case

Records with primitives and `String` are relatively straightforward to share. However, a record containing a list can still be **only shallowly immutable at the reference level**:

```java
record UnsafeCatalog(java.util.List<String> items) {
    // A caller holding the passed-in mutable List can still modify it.
}
```

This is a data-type snippet. A `final List` field does not stop an external `ArrayList` from having its contents modified. Protect it with a defensive copy:

```java
record Catalog(java.util.List<String> items) {
    Catalog {
        items = java.util.List.copyOf(items);
    }
}
```

`List.copyOf` creates or reuses an **unmodifiable** list with the given elements according to its contract. If the elements are immutable `String`s, the state is safe to share. If the elements are `MutableOrder` objects with setters, copying the list **does not deep-copy** each item; mutable references inside can still be modified. In that case, you need immutable components, deep copying, or ownership control.

Do not confuse `Collections.unmodifiableList(original)` (a view that forbids direct modification, while `original` can still be mutated elsewhere) with an independent snapshot.

## 8. Example 4 — Updating Catalog with copy-on-write and updateAndGet

Create **`AtomicCatalog.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.atomic.AtomicReference;

public class AtomicCatalog {
    record Catalog(List<String> items) {
        Catalog {
            items = List.copyOf(items);
        }
    }

    static final class Store {
        private final AtomicReference<Catalog> catalog =
                new AtomicReference<>(new Catalog(List.of()));

        void add(String item) {
            catalog.updateAndGet(old -> {
                List<String> next = new ArrayList<>(old.items());
                next.add(item);
                return new Catalog(next);
            });
        }

        Catalog snapshot() {
            return catalog.get();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Store store = new Store();

        Thread a = new Thread(() -> store.add("A"));
        Thread b = new Thread(() -> store.add("B"));
        a.start();
        b.start();
        a.join();
        b.join();

        List<String> printed = new ArrayList<>(store.snapshot().items());
        Collections.sort(printed);
        System.out.println("Items: " + printed);
        System.out.println("Count: " + printed.size());
    }
}
```

```bash
javac AtomicCatalog.java
java AtomicCatalog
```

Output:

```text
Items: [A, B]
Count: 2
```

`AtomicReference.updateAndGet` updates atomically per its contract, and **the update function may be re-evaluated** under CAS contention. Therefore, the lambda creates only a **local** list, does not mutate the old snapshot, and produces no external side effects. When two threads concurrently add A and B, the committed result contains both elements. Insertion order depends on scheduling; the program sorts **a copy for deterministic printing**, not the published snapshot itself.

If the list is very large and updates are frequent, copy-on-write incurs `O(n)` allocation and copying cost per addition. In that case, an appropriate concurrent collection or a lock protecting a mutable structure may be more efficient.

**Do not do this:**

```java
// ANTI-EXAMPLE snippet: lambda with an external side effect.
state.updateAndGet(old -> {
    sendEmail(); // May execute multiple times if retried.
    return transform(old);
});
```

The snippet above assumes `state`, `sendEmail`, and `transform` exist. Because the lambda can run again, sending an email inside it can be duplicated even though only one update wins CAS. To avoid this, compute the new snapshot with a pure function, commit first, and design side effects with idempotency, transactions, or separate recovery mechanisms. Moving the side effect after CAS **does not automatically guarantee** atomicity between the side effect and the JVM commit if the process can crash.

## 9. Memory effects and safe publication under the JMM

`AtomicReference.get()` has the memory effects of a **volatile read**; `set()` has those of a **volatile write**; a successful `compareAndSet()` has volatile read/write memory effects per the API contract. When a writer constructs `new State(...)` completely and publishes it via an atomic operation, a reader obtaining the reference with `get()` can rely on the corresponding **happens-before** synchronization relationship to see the fields properly initialized.

However, distinguish three things:

- **Visibility/publication:** readers see the initialized fields of the snapshot.
- **No subsequent mutation:** the immutable snapshot protects readers from deeper changes.
- **No lost updates:** writers use a CAS loop instead of a plain `get()` followed by `set()`.

If any of the three is missing, results can be wrong. Having `final` fields on `State` helps guarantee proper initialization under the JMM, **not** immutability of mutable objects it points to. Never let `this` or a reference to a partially constructed state escape the constructor before completion.

You can use `volatile State current` so readers grab **one snapshot** via a volatile read if there is only a single writer or writers are coordinated externally. But when multiple writers do `newState = f(current); current = newState`, two computations can both read the same old state and overwrite each other. CAS or a lock is required when you want composite updates without lost changes.

## 10. How do set(), getAndSet(), compareAndSet(), and updateAndGet() differ?

| API | Primary contract | When it fits |
|---|---|---|
| `get()` | Reads the current reference with volatile read effects. | Reader grabs **one** immutable snapshot to read multiple fields. |
| `set(next)` | Writes a reference atomically with volatile write effects. | Publishing a predetermined value; does not protect multi-writer computations from `current`. |
| `getAndSet(next)` | Swaps the reference and returns the old reference as one atomic operation. | Swapping in a pre-built value reference. |
| `compareAndSet(old, next)` | Swaps only if `current` is the **same reference** as `old`; returns `boolean`. | Check-then-act on an immutable snapshot with a CAS loop. |
| `updateAndGet(fn)` | Transforms and commits the new state atomically, returning the new value. | Pure updates where the lambda tolerates retries. |
| `getAndUpdate(fn)` | Similar, but returns the state prior to the update. | Need to know the old snapshot of the commit; lambda must still be pure. |

**Identity vs. equality:** `AtomicReference.compareAndSet` compares object references, not `equals()`. If you construct a `new State(...)` with the same values as the current state and pass it as `expected`, CAS can fail because it is a different instance. Always pass the exact reference `old = state.get()` as `expected`.

## 11. ABA: a value can return without CAS knowing the history

**ABA problem**: Thread T1 reads reference A; thread T2 changes A → B → **back to the exact same reference A**; T1 calls `CAS(expected A, next)` and can still win because `current` is A again, even though intermediate changes occurred.

Key point: **same contents does not mean same reference**. If T2 creates a new instance A with identical components to the old A but a different identity, CAS with the old reference will not win. A design that **always creates a new snapshot and never republishes an old instance** mitigates identity-based ABA; however, any algorithm that needs to detect "has any update occurred since reading" still needs an explicit version design.

You can add a `version` incremented with each snapshot, or consider `AtomicStampedReference` if detecting intermediate changes is required. When using versions, account for overflow and reuse policies. Do not assume raw CAS remembers state history.

## 12. Costs and progress guarantees

A CAS loop does not hold a monitor blocking other writers while computing a snapshot; it is an **optimistic concurrency** technique. This is helpful when reads are frequent, snapshots are small, updates are infrequent, or contention is moderate. Still, consider:

- **Retries:** under contention, a thread can fail CAS many times, burning CPU.
- **Allocation/GC:** each attempt may allocate a new object; failed attempts become garbage.
- **Copy-on-write:** snapshots containing large collections can require `O(n)` work and memory per update.
- **Fairness:** CAS does not guarantee that every individual thread finishes within a bounded time.
- **Side effects:** operations must be designed to retry safely, because the computation may run repeatedly.

Using an atomic reference does not automatically make **the whole algorithm wait-free** or guarantee unbounded liveness. If the state is complex or must invoke lengthy external code, a `synchronized` block or `ReentrantLock` covering the invariant can be simpler and easier to prove correct. Optimize only after measuring actual contention, latency, and throughput.

## 13. Atomicity boundaries: one reference is not every resource

Bundling two fields into an immutable `State` only makes **the set of values pointed to by that reference** atomic. It does **not** create a transaction for:

- Two **different** `AtomicReference` instances updated sequentially.
- Mutable objects elsewhere that are not included in the snapshot.
- Databases, files, networks, or other JVM processes.
- Side effects such as an HTTP call, sending a message, or writing an audit log.

If business logic requires atomicity across multiple systems, it must rely on transactions, constraints, idempotency, outbox patterns, or consistency protocols supported by the storage/integration systems. A lock or CAS inside a single JVM cannot force external processes to comply.

The `AtomicAccounts` example is an **in-memory illustrative ledger**, not real banking transactions. Combining disparate requirements (durability, rollback, client request retries) requires architecture beyond `AtomicReference`.

## 14. Comparing the options

| Scenario | Suitable tool | Conditions / limitations |
|---|---|---|
| Incrementing a single counter | `AtomicInteger.incrementAndGet()` | Single atomic update on one variable. |
| Remaining/used quota is a multi-field invariant | `AtomicReference<ImmutableState>` + CAS or monitor | Must protect both snapshot reads and all update paths. |
| Many readers, few writers, small state | Immutable snapshot + atomic reference | Easy, consistent reads at the cost of allocation on writes. |
| Multi-field update with long/complex branches | `synchronized` or `ReentrantLock` | Every path accessing the same invariant must use the same lock. |
| Map with independent keys | `ConcurrentHashMap` | Per-operation atomicity per contract; no automatic multi-key transactions. |
| Shared list with many reads / few writes | Copy-on-write or immutable snapshot | Avoid if the list is very large and writers are very frequent. |
| State shared across multiple JVMs | Data backend transactions / conditional writes | CAS within one JVM provides no global guarantee. |

**Choose the mechanism based on the scope of the invariant.** If all related state fits in one immutable object and updates can be computed purely, CAS makes sense. If state spans multiple systems or requires non-retryable operations, the model needs a different tool.

## 15. Checklist for designing a compound atomic state

1. **Write down the invariant:** list all fields that must remain consistent with one another.
2. **Put them in an immutable State:** record, `final` class, defensive copies, and immutable components.
3. **Hide the AtomicReference:** use `private final AtomicReference<State>`; do not let callers arbitrarily call `set()`.
4. **Readers capture once:** `State snapshot = state.get()`, reading all fields from that same snapshot.
5. **Writers read–check–compute:** create a new object from the read snapshot; never mutate the old object.
6. **CAS commit:** report success only when `compareAndSet(old, next)` succeeds.
7. **Retry properly:** when CAS fails, re-read and re-check business conditions; never merge stale state.
8. **Pure transform function:** no I/O, sending emails, or mutating other state inside the retry lambda.
9. **Clear contract for returned snapshots:** a snapshot may become stale right after `get()`, even though it is consistent.
10. **Measure performance:** monitor retries, computation time, allocation rate, and snapshot size.
11. **Test invariants under contention:** use latches/barriers to force interleavings, `join()` workers, and verify commit totals.
12. **Handle off-JVM failures separately:** never assume CAS commits atomically with a database, message, or file.

## 16. Self-check questions

1. **Why do two `AtomicInteger` instances fail to protect a two-field sum invariant?** Each variable is atomic individually; a reader can observe the gap between the two updates.
2. **Why shouldn't a reader call `state.get()` twice and combine two fields?** The two calls can read snapshots from two different versions.
3. **Does CAS on `AtomicReference` compare with `==` or `equals()`?** It compares reference identity (`==`).
4. **If CAS fails, can you call `state.set(next)` with the old attempt's value?** No, because it can overwrite another writer's result.
5. **Why should `updateAndGet` receive a side-effect-free lambda?** The lambda may be invoked multiple times due to retries.
6. **Can you mutate an `ArrayList` inside a record with a `final` field and still consider the state immutable?** No; you must avoid mutable aliases by using defensive copies and immutable components.
7. **Does a just-won CAS mean the snapshot stays the latest until the caller finishes processing?** No; another writer can replace it immediately afterward.
8. **Does CAS turn the database and the JVM into a single transaction?** No; a separate mechanism in the storage system is required.
9. **What does ABA mean?** Reference A changes to B and then back to **the same A**, so identity-only CAS may fail to notice the history.
10. **When might a lock be more suitable than CAS?** Complex state, hard-to-retry side effects, expensive snapshot copying, or heavy contention.

**Remember:** when multiple fields belong to the same invariant, publish **one immutable State through one AtomicReference**, use **CAS** to commit composite changes, and let readers grab **a single snapshot**. Never mutate old snapshots; keep retries pure; and in-JVM synchronization does not automatically replace external transactions.
