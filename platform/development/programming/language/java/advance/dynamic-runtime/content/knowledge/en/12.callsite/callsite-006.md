# 12.6. Using MutableCallSite.syncAll and Coordinating Update Threads

> **Context:** Knowledge article in group **12. CallSite** of module **Java Advance – dynamic-runtime**, applying the standard **Java 21** API. A `MutableCallSite` can change its `MethodHandle target` after the application has already held `dynamicInvoker()`. However, `setTarget()` only writes with **ordinary variable** semantics and does not automatically guarantee that other calling threads see the new target in time. `MutableCallSite.syncAll(...)` is the dedicated mechanism to force threads to accept target changes; to update safely with **multiple writers**, an additional coordination protocol is needed, and the non-atomic limitation across multiple call sites must be understood.

## 1. Objectives and Prerequisites

After this lesson, you should be able to:

1. Distinguish `CallSite.type()`, `getTarget()`, `setTarget()`, and `dynamicInvoker()`; understand that the target's type is fixed throughout the call site's lifetime.
2. Explain why `MutableCallSite.setTarget(...)` is **not** a volatile write and why a reader running on JIT-optimized code may temporarily use the old target.
3. State accurately the meaning of `MutableCallSite.syncAll(MutableCallSite[] sites)` according to the Java 21 Javadoc, including in-flight calls, when readers may see the new/old value, cost, null handling, and concurrent writers.
4. Use a single `syncAll` call after changing **multiple call sites** to batch synchronization; avoid calling it once per site change if unnecessary.
5. Keep `setTarget` and `syncAll` within **the same mutual exclusion region** when there are multiple writers; do not confuse this with an atomic transaction on the reader side.
6. Design how to publish an **immutable snapshot** if a request must observe a consistent set of routing/configuration values.
7. Choose appropriately between `MutableCallSite`, `VolatileCallSite`, and `ConstantCallSite`, considering update frequency, visibility, and overhead.
8. Run five Java labs with deterministic output and understand the limitations of concurrency experiments.

**Prerequisites:** `MethodHandle`, `MethodType`, `MethodHandles.constant`, synchronized/lock, Java Memory Model (JMM), `CountDownLatch`, the happens-before concept, and race hazards. You do not need to write `invokedynamic` bytecode manually to learn the semantics: `dynamicInvoker()` lets you practice an invocation path equivalent to a linked call site.

## 2. CallSite, target, and dynamic invoker

`CallSite` is a dynamic call linkage point. Each call site is bound to a fixed `MethodType` and a `MethodHandle` target of that same type. Common subclasses:

| Type | Can target change? | Visibility when changing target | Suitable use case |
| --- | --- | --- | --- |
| `ConstantCallSite` | **No** | Fixed target | Linkage that never changes after bootstrap. |
| `MutableCallSite` | **Yes** | Target read/written like an **ordinary field**; use `syncAll` when needing to force threads to accept the updated target | Infrequent, batched invalidation/relink. |
| `VolatileCallSite` | **Yes** | `getTarget/setTarget` like **volatile read/write** | Frequent changes or needing visibility tied to each update. |

`MutableCallSite` has two ways to be initialized:

```java
// Illustrative snippet; requires import java.lang.invoke.*
MethodHandle initial = MethodHandles.constant(String.class, "old");
MutableCallSite site = new MutableCallSite(initial);      // type = ()String
MutableCallSite blank = new MutableCallSite(initial.type()); // no useful target yet
```

The first way uses `initial` as the target. The second way creates a default target that throws `IllegalStateException` when invoked until assigned via `setTarget`.

`site.type()` is always the initial `MethodType`; `site.setTarget(newTarget)` requires **newTarget.type() to equal site.type() exactly**. There is no implicit type conversion step: if you want to change the signature, you can intentionally use `MethodHandle.asType(...)` to create a compatible handle; you still must check the conversion and return type.

### 2.1. Two different ways of using a target

```java
// Illustrative snippet after creating site.
MethodHandle live = site.dynamicInvoker();
MethodHandle snapshot = site.getTarget();
```

- `live` is a **dynamic invoker**, so when invoked it links to the current target of **the same call site** according to the visibility rules of `MutableCallSite`.
- `snapshot` is just a **reference to a specific MethodHandle** obtained at the time `getTarget()` was read. Invoking `snapshot` itself later has no reason to switch to the newly installed handle.
- Creating **a new MutableCallSite** and reassigning the Java variable to point to it has no effect on automatically switching invokers already attached to **the old call site**; to relink, change the target of the call site that the invoker is using.
- `dynamicInvoker()` is a convenient practice path. Actual `invokedynamic` in bytecode is linked via a bootstrap method; the call site target rules are shared, but normal programs do not automatically turn every Java method call into `invokedynamic`.

## 3. The visibility problem: why is setTarget not enough?

According to the Java 21 Javadoc, the target variable of `MutableCallSite` behaves like a **non-volatile field**. When the updater thread runs:

```text
Updater thread                  Reader thread
    |                               |
site.setTarget(newHandle)          invoke via dynamicInvoker
    |                               |
    +-- ordinary write             +-- may still see oldHandle
    |                               |
    +-- no                         +-- not forced to detect
        cross-thread barrier            the change in time
```

An independent thread without proper synchronization may **continue using a cached target** for an unbounded amount of time under the corresponding model. Do not use observations like "on my machine it appears immediately" as proof that this operation is thread-safe in the visibility sense.

Distinguish three issues:

- **Type correctness**: `setTarget` checks the handle's type; unrelated to whether other threads see the update.
- **Visibility**: other threads observe **the new target**; `syncAll` has its own guarantee contract for this.
- **Coordination/consistency**: multiple writers may overwrite each other, multiple sites may be at different versions; `syncAll` does not automatically provide locks or transactions.

The JMM allows the compiler/JIT to optimize reads that lack sufficient synchronization. `syncAll` is designed so implementations force future target reads to accept the new version, rather than relying on the luck of ordinary cache coherence.

## 4. Contract of MutableCallSite.syncAll(...) in Java 21

Exact signature:

```java
public static void MutableCallSite.syncAll(MutableCallSite[] sites);
```

In Java, the actual method declaration syntax is `public static void syncAll(MutableCallSite[] sites)` inside class `MutableCallSite`; the line above is only a notation for the **full API path**, not valid declaration source code when placed inside another class.

`syncAll` accepts an array of **MutableCallSite objects**. For each provided site, the synchronization operation forces other threads to discard any old cached target values and accept the updated value in future target reads, per the JMM details in the Javadoc.

### 4.1. Standard sequence

```java
// Illustrative snippet, sites already created and newA/newB have matching types.
synchronized (updateLock) {
    siteA.setTarget(newA);
    siteB.setTarget(newB);
    MutableCallSite.syncAll(new MutableCallSite[] {siteA, siteB});
}
```

**Prepare/validate** the `MethodHandle`s before entering the write region if compilation/lookup work is expensive; keep only the commit section concise inside the lock. If there are multiple writers, **all writers must follow the same locking policy** to prevent a `setTarget` from another writer from interleaving between your `setTarget` and `syncAll`.

### 4.2. What is guaranteed?

- `setTarget` writes the target as an ordinary variable. `syncAll` provides a **synchronization action** whose effect is equivalent to a volatile write in the updater followed by volatile reads in threads reading the affected sites, according to the model described by the Javadoc.
- It forces future readers of each call-site target to accept **the latest stored value corresponding to the synchronization operation**, except for newer updates occurring afterward.
- Some readers may see the new target **right after `setTarget`, before `syncAll`**; there is no need to wait for the final publication to "unlock" the new value.
- A reader may still use the old target **after `setTarget` but before `syncAll` completes**. A call that has already started on the old target **is not rolled back**, is not re-executed, and is not upgraded mid-flight.
- `syncAll` may have to wait for the synchronization mechanism of the involved threads; details of cache invalidation/safepoint/deoptimization are JVM-dependent. Do not assume it is merely a super-cheap memory fence.
- `syncAll` applies to **each site in the array**, but **is not an atomic transaction across the entire set of sites** from a reader's perspective.

### 4.3. What is NOT promised

| Claim | True/False | Explanation |
| --- | --- | --- |
| "`setTarget` automatically notifies all other threads" | **False** | An ordinary write does not enforce immediate visibility. |
| "Readers cannot see the new target before `syncAll`" | **False** | The Javadoc allows early visibility immediately after `setTarget`. |
| "`syncAll` waits for all old calls to return" | **False** | Calls already started on the old target may continue to completion on the old target. |
| "One `syncAll` call is a transaction changing all sites at once" | **False** | Readers may observe a mix of versions when reading multiple sites. |
| "`syncAll` eliminates races between two writers" | **False** | You must coordinate/lock `setTarget` and `syncAll` when there are multiple updaters. |
| "Each site must call `syncAll` separately" | **False** | The API accepts an array; batching is usually appropriate. |
| "Reading `getTarget()` and keeping the old handle will auto-update" | **False** | That is a captured MethodHandle snapshot; use `dynamicInvoker` to go through the site. |

### 4.4. Null array, null element, and error handling

`syncAll(null)` throws `NullPointerException`. If the `sites` array contains `null`, it also throws `NullPointerException`, but **may have already synchronized some non-null elements before throwing**; which elements were processed is implementation-dependent. Do not treat a call that failed due to null as "all-or-nothing".

To avoid unpredictable state, build a valid site list using your own API, ensuring the array is non-null and has no null elements **before** entering the commit step. `syncAll(new MutableCallSite[0])` has no sites to synchronize; you cannot use an empty array to publish updates of sites you forgot to pass in.

## 5. The JMM model of syncAll: understanding it accurately and sufficiently

The Java 21 Javadoc explains it using a **conceptual volatile variable V** for each synced site `S`. Visualize:

1. The updater thread has written the new target to `S` before calling `syncAll`.
2. A synchronization action similar to a **volatile write to V** is placed in the global synchronization order; actions performed earlier in the updater are ordered before this write.
3. Threads may continue calling the site, but the implementation must force them to eventually observe that synchronization point like a **conceptual volatile read** before future target reads under JMM constraints.
4. After the relevant synchronization point, they must not continue using an older target value as if the updates before `syncAll` had not occurred.

**There is no public variable `V` in the program for learners to read/write manually**; this is a formal model describing the effect, not advice to build a `volatile boolean` yourself and hope it accurately replaces `syncAll` across all JIT-compiled call paths.

The Javadoc also allows an implementation to delay completion of `syncAll` while readers continue using the old value, as long as the JMM is respected; implementations are encouraged to avoid livelock and eventually force threads to take the change into account.

### 5.1. A common misconception: "The writer already has a lock, so readers will definitely see it"

If only the updater holds `synchronized(lock)` while the reader calls `dynamicInvoker()` **without acquiring the same lock**, then the writer-side lock alone does not create a complete coordinated read-write protocol between both sides. `syncAll` has its own contract for target visibility. If the reader's entire business operation requires multi-step consistency, a reader-side synchronization/snapshot protocol is needed, not just a writer lock.

## 6. Lab 1 — changing target, syncing one site, and keeping an old snapshot

Create a standalone file **`BasicSyncLab.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MutableCallSite;
import java.lang.invoke.WrongMethodTypeException;

public class BasicSyncLab {
    public static void main(String[] args) throws Throwable {
        MutableCallSite site =
                new MutableCallSite(MethodHandles.constant(String.class, "blue"));
        MethodHandle live = site.dynamicInvoker();
        MethodHandle oldTarget = site.getTarget();

        System.out.println("type=" + site.type());
        System.out.println("before=" + (String) live.invokeExact());

        site.setTarget(MethodHandles.constant(String.class, "green"));
        MutableCallSite.syncAll(new MutableCallSite[] {site});

        System.out.println("after=" + (String) live.invokeExact());
        System.out.println("oldSnapshot=" + (String) oldTarget.invokeExact());

        try {
            site.setTarget(MethodHandles.constant(int.class, 7));
            System.out.println("wrongType=unexpected");
        } catch (WrongMethodTypeException expected) {
            System.out.println("wrongType=WrongMethodTypeException");
        }
    }
}
```

Compile/run with Java 21:

```sh
javac --release 21 -Xlint:all BasicSyncLab.java
java BasicSyncLab
```

**Stdout:**

```text
type=()String
before=blue
after=green
oldSnapshot=blue
wrongType=WrongMethodTypeException
```

### 6.1. Interpretation

- `MethodHandles.constant(String.class,"blue")` is a zero-argument handle returning `String`, so `site.type()` is `()String`.
- `live` goes through `site`; after the update and `syncAll` it reads the new target. `oldTarget`, obtained earlier via `getTarget`, remains a direct handle returning "blue".
- `setTarget` on a `()String` site does not accept `()int`; it throws `WrongMethodTypeException` and does not automatically change the call site's type.
- The program runs on **a single thread**, so do not use the `"after=green"` result to conclude that omitting `syncAll` is safe across multiple threads. We call `syncAll` to demonstrate the update protocol needed when scaling to a concurrent runtime.

## 7. Coordinating multiple sites: staging, commit, and a single syncAll

Suppose a system has two route targets `routeRead` and `routeWrite`. Each route has a `MutableCallSite` to allow plugins to replace implementations. When replacing two targets, a controlled pattern:

```text
[Prepare newRead, newWrite; check MethodType]
                 |
[Writer lock: prevent other writers from interleaving]
                 |
      readSite.setTarget(newRead)
     writeSite.setTarget(newWrite)
                 |
 MutableCallSite.syncAll([readSite, writeSite])
                 |
[Writer lock released; record that batch was published]
```

**Best practices:**

- Prepare target handles outside the lock, ensuring `newRead.type().equals(readSite.type())` and similarly for other sites.
- Acquire the lock **shared by all writers**; call all `setTarget`s followed by **a single** `syncAll` for the changed sites.
- Do not interleave writer B's updates between writer A's commands; if rollback on error must be supported, build an explicit state machine outside `syncAll`.
- Log the version/batch id after publishing, but do not treat the completed log as proof that **all previously started calls** have switched logic.
- When needing to replace multiple sites that have cross-dependencies, evaluate the **single site holding an immutable snapshot** solution in Section 11.

### 7.1. Why is batching useful?

By specification, a single `syncAll` with multiple sites has the same formal effect as syncing each site individually. However, the JVM may incur a **large fixed cost** per global coordination and a small incremental cost per site. Therefore, group related changes rather than forcing all threads to synchronize after every `setTarget`.

There is no fixed runtime guarantee for `syncAll`; benchmarks must be based on the actual JDK, OS, reader count, and workload. Do not use it as a thousands-of-times-per-second API without evaluating its cost; consider `VolatileCallSite` for continuous updates.

## 8. Lab 2 — batching two sites and a coordinated reader

Create **`BatchVisibilityLab.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MutableCallSite;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicReference;

public class BatchVisibilityLab {
    public static void main(String[] args) throws Throwable {
        MutableCallSite left =
                new MutableCallSite(MethodHandles.constant(String.class, "left-1"));
        MutableCallSite right =
                new MutableCallSite(MethodHandles.constant(String.class, "right-1"));
        MethodHandle readLeft = left.dynamicInvoker();
        MethodHandle readRight = right.dynamicInvoker();

        CountDownLatch firstReadDone = new CountDownLatch(1);
        CountDownLatch published = new CountDownLatch(1);
        AtomicReference<String> before = new AtomicReference<>();
        AtomicReference<String> after = new AtomicReference<>();
        AtomicReference<Throwable> failure = new AtomicReference<>();

        Thread reader = new Thread(() -> {
            try {
                String oldLeft = (String) readLeft.invokeExact();
                String oldRight = (String) readRight.invokeExact();
                before.set(oldLeft + "/" + oldRight);
                firstReadDone.countDown();

                published.await();
                String newLeft = (String) readLeft.invokeExact();
                String newRight = (String) readRight.invokeExact();
                after.set(newLeft + "/" + newRight);
            } catch (Throwable e) {
                failure.set(e);
                firstReadDone.countDown();
            }
        }, "reader");
        reader.start();
        firstReadDone.await();

        Object updateLock = new Object();
        synchronized (updateLock) {
            left.setTarget(MethodHandles.constant(String.class, "left-2"));
            right.setTarget(MethodHandles.constant(String.class, "right-2"));
            MutableCallSite.syncAll(new MutableCallSite[] {left, right});
        }
        published.countDown();
        reader.join();
        if (failure.get() != null) throw new AssertionError(failure.get());

        System.out.println("before=" + before.get());
        System.out.println("after=" + after.get());
        System.out.println("updatedTargets=" +
                left.getTarget().type().equals(right.getTarget().type()));
    }
}
```

Commands:

```sh
javac --release 21 -Xlint:all BatchVisibilityLab.java
java BatchVisibilityLab
```

**Stdout:**

```text
before=left-1/right-1
after=left-2/right-2
updatedTargets=true
```

### 8.1. Why is the output deterministic?

- The reader reads both handles before allowing the updater to proceed via `firstReadDone`.
- The updater replaces both targets and calls **one** `syncAll`. After it returns, the updater opens the `published` gate; only then does the reader proceed.
- `reader.join()` ensures `main` has received the reader's results before printing.
- `updatedTargets=true` in the lab only compares the **MethodType** of the two targets (both `()String`); it **does not** prove the two values form a transaction. The "before/after" lines are the observed values under this coordinated schedule.

**What must NOT be inferred:** `CountDownLatch` itself provides synchronization/happens-before. Therefore, this is **not** a quantitative experiment on visibility latency when **omitting `syncAll`**, and it does not prove that `syncAll` alone makes multi-site combinations atomic. The lab's goal is to test API usage and a coordinated update sequence that produces stable stdout.

### 8.2. Extended experiment (not recommended as an assertion)

You can have the reader run a continuous loop and change the two sites one after another to observe occasional mixes like `left-2/right-1`. However, failing to observe that combination in a single run **does not prove atomicity either**. The scheduler, JIT, CPU, and memory architecture affect the result; do not write tests that rely on the random occurrence of a race.

## 9. Multiple writers: putting setTarget and syncAll in the same critical section

`syncAll` does not lock the call site. If two updaters act on the same site simultaneously:

```text
Writer A: setTarget(A)
Writer B: setTarget(B)
Writer A: syncAll([site])
Writer B: syncAll([site])
```

Then A's `syncAll` may end up synchronizing **value B**, not necessarily value A that A intended to publish. If A checks right after sync and logs "published A", the record may be false about the actual state.

Correct pattern when **all writers obey the same lock**:

```java
// Illustrative snippet: shared update control point.
synchronized (UPDATE_LOCK) {
    int nextVersion = ++version;
    site.setTarget(MethodHandles.constant(String.class, "v-" + nextVersion));
    MutableCallSite.syncAll(new MutableCallSite[] {site});
}
```

`synchronized` on the writer itself ensures **writers do not interleave with each other**. It does not automatically create an atomic snapshot for readers and does not make readers wait while the writer updates, unless readers also participate in an appropriate protocol.

**If multiple call sites are updated by multiple groups:** use one shared lock for sites sharing the same invariant, or partition locks according to non-overlapping rules and design acquisition order/deadlock avoidance. Do not use multiple independent locks for the same site if interleaving is possible.

## 10. Lab 3 — two writers publishing together with one lock

Create **`CoordinatedWritersLab.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MutableCallSite;
import java.util.concurrent.CountDownLatch;

public class CoordinatedWritersLab {
    private static final Object UPDATE_LOCK = new Object();
    private static final MutableCallSite SITE =
            new MutableCallSite(MethodHandles.constant(String.class, "version-0"));
    private static int version;

    private static void publishNext() {
        synchronized (UPDATE_LOCK) {
            int next = ++version;
            SITE.setTarget(MethodHandles.constant(String.class, "version-" + next));
            MutableCallSite.syncAll(new MutableCallSite[] {SITE});
        }
    }

    public static void main(String[] args) throws Throwable {
        MethodHandle live = SITE.dynamicInvoker();
        CountDownLatch start = new CountDownLatch(1);

        Runnable writer = () -> {
            try {
                start.await();
                publishNext();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(ex);
            }
        };

        Thread a = new Thread(writer, "writer-A");
        Thread b = new Thread(writer, "writer-B");
        a.start();
        b.start();
        start.countDown();
        a.join();
        b.join();

        System.out.println("published=" + version);
        System.out.println("result=" + (String) live.invokeExact());
    }
}
```

```sh
javac --release 21 -Xlint:all CoordinatedWritersLab.java
java CoordinatedWritersLab
```

**Stdout:**

```text
published=2
result=version-2
```

### 10.1. Concurrency analysis

- Both writers start close together after `start.countDown()`. Which of **writer-A or writer-B enters the lock first** is non-deterministic and does not need to be deterministic.
- Whichever writer enters the lock increments `version`, updates the target, and calls `syncAll` **before releasing the lock**; the next writer cannot interleave between those statements.
- After `a.join()` and `b.join()`, both updaters have finished; `version` equals 2 and the final target returns `"version-2"` regardless of writer identity.
- This is a good example to separate **writer mutual exclusion** from **target visibility to readers**. `join()` and `CountDownLatch` also introduce synchronization into the lab, so do not use it to measure the likelihood of stale targets when omitting `syncAll`.

**Production tip:** handle writer errors intentionally (e.g., via `Future`, `ExecutorService`, completion record). In the lab, the existing code paths always build a target of the right type, so the program needs no rollback branch.

## 11. Syncing an array does not create an atomic multi-site transaction

This is the most important limitation when designing a dynamic routing system.

Suppose `siteA` and `siteB` must have the same version within a transaction:

```text
              Initial values: A=v1, B=v1

Updater (with writer lock)        Reader (without lock)
------------------------          -----------------------
siteA.setTarget(A_v2)             read siteA -> may be v2
siteB.setTarget(B_v2)             read siteB -> may be v1
syncAll([siteA,siteB])            // observed the v2/v1 combination
```

The writer holding a lock **does not block readers** unless readers also acquire that lock or read a valid immutable snapshot. The Javadoc allows readers to see the new target before `syncAll`; multiple sites may be read at different times. Even right after `syncAll`, if a reader makes **two separate calls** and a new updater runs **between the two calls**, the reader can still see **two different versions**.

`syncAll` serves to synchronize **target values**, not to turn multiple calls into an atomic business transaction. If the requirement is "a request must see configuration A+B of the same version", an additional consistency model is needed.

### 11.1. How to do it: publish an immutable snapshot

Bundle the related parts into an immutable object:

```text
RouteSnapshot(version, routeA, routeB)  // immutable record
                  |
          MethodHandle ()RouteSnapshot
                  |
            MutableCallSite
                  |
             dynamicInvoker()
                  |
           Reader reads 1 snapshot
                  |
      uses both routeA and routeB from that snapshot
```

The updater builds a complete `RouteSnapshot`, then replaces **a single target** returning that snapshot and calls `syncAll`. The reader holds **one snapshot result** for the entire logical operation. Thus, within a single snapshot there is no mix of two different versions.

This is a guarantee of **data structure / single read point**, not because `syncAll` makes an object's fields transactional. Java records have final fields, but if a record contains mutable references you must still apply **copying/defensive immutability**. Do not mutate an already published object afterward if you want immutability.

## 12. Lab 4 — publishing a consistent snapshot

Create **`SnapshotPublicationLab.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MutableCallSite;

public class SnapshotPublicationLab {
    record RouteSnapshot(int generation, String first, String second) {}

    public static void main(String[] args) throws Throwable {
        MutableCallSite site = new MutableCallSite(
                MethodHandles.constant(RouteSnapshot.class,
                        new RouteSnapshot(1, "A1", "B1")));
        MethodHandle readSnapshot = site.dynamicInvoker();

        RouteSnapshot oldValue = (RouteSnapshot) readSnapshot.invokeExact();
        site.setTarget(MethodHandles.constant(RouteSnapshot.class,
                new RouteSnapshot(2, "A2", "B2")));
        MutableCallSite.syncAll(new MutableCallSite[] {site});
        RouteSnapshot newValue = (RouteSnapshot) readSnapshot.invokeExact();

        System.out.println("before=" + oldValue.generation() + ":" +
                oldValue.first() + "/" + oldValue.second());
        System.out.println("after=" + newValue.generation() + ":" +
                newValue.first() + "/" + newValue.second());
        System.out.println("oldStillImmutable=" + oldValue.first());
    }
}
```

```sh
javac --release 21 -Xlint:all SnapshotPublicationLab.java
java SnapshotPublicationLab
```

**Stdout:**

```text
before=1:A1/B1
after=2:A2/B2
oldStillImmutable=A1
```

### 12.1. Understanding the snapshot guarantee accurately

- The call site type is `()RouteSnapshot`. The entire configuration is read via **one invocation** and held in a local variable.
- After update + sync, new calls can receive snapshot v2; the previously obtained snapshot v1 remains an immutable object `(1,A1,B1)`.
- If there are additional reader threads, they may see v1 or v2 depending on valid timing; **there is no snapshot containing A2/B1** because the updater never creates such an object.
- If a reader needs multiple values within the same request, invoke `readSnapshot.invokeExact()` **once** and use the returned object, rather than invoking again each time `routeA`/`routeB` is needed.

**Limitation:** if the writer publishes multiple consecutive snapshots, two different requests may still see two different versions — that is normal. If low visibility latency on every continuous update is needed, `VolatileCallSite` or `AtomicReference<RouteSnapshot>` may be more suitable depending on overall requirements.

## 13. Choosing Mutable, Volatile, or Constant CallSite

| Criterion | `ConstantCallSite` | `MutableCallSite` | `VolatileCallSite` |
| --- | --- | --- | --- |
| Can call `setTarget`? | No, throws `UnsupportedOperationException` | Yes | Yes |
| Target semantics | Final/permanent | Ordinary field + `syncAll` to force accepting updates | Volatile read/write |
| Multiple reader threads | Uses fixed target | Needs visibility planning when relinking | Every update has volatile semantics |
| Typical update frequency | Never changes | Infrequent, batchable | Frequent |
| Batch sync support | Not needed | `syncAll(MutableCallSite[])` | Not needed / no separate `syncAll` |
| Cost and optimization | Often high optimization opportunity | Changes rarely, per-batch sync cost can be large | Tight coupling between reader/updater may cause overhead |
| Guarantees multi-member transaction? | Not applicable | **No** | **No** |

**`VolatileCallSite`:** The Javadoc states the target behaves like a volatile variable, and reader threads must not stubbornly use an old target when an appropriate update occurs; no `syncAll` call is needed. In return, there may be overhead on the dynamic read/call path. For frequent updates, the `MutableCallSite` Javadoc recommends considering a volatile call site.

**`ConstantCallSite`:** Once bound, the target cannot be changed. `dynamicInvoker()` returns the permanent target, suitable for linkages that never change.

**Practical choice:** if a plugin system needs to update rules a few times per hour and has many hot call sites, `MutableCallSite` + batched `syncAll` is a reasonable candidate. If configuration changes many times per second, evaluate `VolatileCallSite`. If you only need to read reference data or immutable config without method-handle composition, a `volatile` field/`AtomicReference` may be simpler. Do not introduce `CallSite` into code just to replace every mutable variable.

## 14. Lab 5 — Volatile, Constant, blank site, and null errors

Create **`CallSiteChoicesLab.java`**:

```java
import java.lang.invoke.ConstantCallSite;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.MutableCallSite;
import java.lang.invoke.VolatileCallSite;

public class CallSiteChoicesLab {
    public static void main(String[] args) throws Throwable {
        VolatileCallSite volatileSite =
                new VolatileCallSite(MethodHandles.constant(int.class, 1));
        MethodHandle live = volatileSite.dynamicInvoker();
        System.out.println("volatileBefore=" + (int) live.invokeExact());
        volatileSite.setTarget(MethodHandles.constant(int.class, 2));
        System.out.println("volatileAfter=" + (int) live.invokeExact());

        ConstantCallSite constantSite =
                new ConstantCallSite(MethodHandles.constant(String.class, "fixed"));
        System.out.println("constant=" +
                (String) constantSite.dynamicInvoker().invokeExact());
        try {
            constantSite.setTarget(MethodHandles.constant(String.class, "other"));
            System.out.println("constantSet=unexpected");
        } catch (UnsupportedOperationException expected) {
            System.out.println("constantSet=UnsupportedOperationException");
        }

        MutableCallSite blank = new MutableCallSite(MethodType.methodType(int.class));
        try {
            int ignored = (int) blank.dynamicInvoker().invokeExact();
            System.out.println("blank=unexpected " + ignored);
        } catch (IllegalStateException expected) {
            System.out.println("blank=IllegalStateException");
        }

        try {
            MutableCallSite.syncAll(null);
            System.out.println("nullArray=unexpected");
        } catch (NullPointerException expected) {
            System.out.println("nullArray=NullPointerException");
        }
        try {
            MutableCallSite.syncAll(new MutableCallSite[] {blank, null});
            System.out.println("nullElement=unexpected");
        } catch (NullPointerException expected) {
            System.out.println("nullElement=NullPointerException");
        }
    }
}
```

```sh
javac --release 21 -Xlint:all CallSiteChoicesLab.java
java CallSiteChoicesLab
```

**Stdout:**

```text
volatileBefore=1
volatileAfter=2
constant=fixed
constantSet=UnsupportedOperationException
blank=IllegalStateException
nullArray=NullPointerException
nullElement=NullPointerException
```

### 14.1. Distinguishing exceptions

- `ConstantCallSite.setTarget` does not support changing the target even if the new handle has the same type.
- `new MutableCallSite(MethodType.methodType(int.class))` creates a site with type `()int` but without a useful target installed yet, so invoking `dynamicInvoker` at this point throws `IllegalStateException`.
- `syncAll` with a `null` array reference or a `null` element throws `NullPointerException`.
- For an array with a null element, **do not conclude that all non-null sites were not synchronized**: the Javadoc allows some sites to have been processed before the null is detected. You must validate the entire array beforehand.
- The `VolatileCallSite` lab runs in a single thread so it is not a benchmark or visibility stress test, only an API and output verification. Multi-threaded semantics must be based on the Javadoc, not on a few lines of output.

## 15. Real-world pitfalls when building runtime relinking

| Symptom | Common cause | Fix |
| --- | --- | --- |
| `setTarget` throws `WrongMethodTypeException` | New target has a different `MethodType` from site type | Check `newHandle.type().equals(site.type())`; only use `asType` if the conversion is valid/intentional. |
| `setTarget(null)` throws `NullPointerException` | Null target is not supported | Use a handle returning a sentinel or throwing with the exact signature, do not set null. |
| `dynamicInvoker` of a blank site throws `IllegalStateException` | Using `MutableCallSite(MethodType)` before attaching a real target | Install an initial target before publishing the site. |
| Readers still see old target | Missing cross-thread visibility or call already started on old handle | Call `syncAll` per protocol; do not expect cancellation of in-flight calls. |
| Updates from two writers overwrite each other | `setTarget` and `syncAll` are not protected together | Apply the same lock, define version rules, staging, and commit. |
| Reader sees `A2/B1` | Sites are read separately, batch sync is **not atomic** | Use one immutable snapshot or a reader protocol with lock/version validation. |
| Latency spikes during updates | `syncAll` has thread coordination overhead | Group sites into one sync, reduce frequency, benchmark, consider volatile call site. |
| Holding direct handle from `getTarget` invokes old logic | Direct `MethodHandle` is not linked to the site | Invoke via `dynamicInvoker`, or re-fetch target under a synchronized protocol. |
| `syncAll` finishes but old service requests still run | Calls started earlier are not rolled back | Design separate drain/ref-count/barrier if needing to wait for in-flight requests. |
| `syncAll` throws `NullPointerException` mid-batch | Array contains null | Validate array before commit; do not assume a failed call left everything unsynced. |
| Replaced `MutableCallSite` object but invoker still runs old site | `dynamicInvoker()` is bound to a specific site | Keep site identity; update the target of that same site. |
| Stress test run 100 times always sees new version before sync | Lucky scheduler/JIT configuration | Do not use "no error observed" to refute the JMM; verify design against the spec/concurrency rules. |

### 15.1. Cases requiring mechanisms beyond syncAll

- **Graceful shutdown or hot reload:** if you want to wait for all calls to the old target to finish, you need in-flight request accounting, quiescence, a stop-the-world protocol, ref-counting, or a lifecycle barrier. `syncAll` does not solve this requirement.
- **Multi-route transaction:** requires snapshot/lock/atomic state hand-off; `syncAll` does not provide atomicity across two separate `dynamicInvoker` calls.
- **Version monotonicity for readers:** if readers must reject older versions and only accept increasing versions, add a version check per logical request.
- **Failure recovery:** a multi-site update may fail partway due to validation/lookup/error; stage all targets first, decide rollback/compensation per application spec. Do not assume `syncAll` has an undo mechanism.
- **Blocking operation:** do not call `syncAll` on a latency-critical hot path without evaluating it, because it may need to coordinate reader threads.

## 16. Production workflow: prepare, publish, measure

A concise yet controlled workflow:

```text
[1] Receive request to change logic (plugin/config/feature flag)
       |
[2] Build & validate all new MethodHandles outside writer lock
       |   - correct owner/class loader
       |   - exact MethodType per CallSite
       v
[3] Verify policy, new version, and non-null MutableCallSites list
       |
[4] Acquire shared writer lock
       |
[5] setTarget for relevant sites
       |
[6] syncAll(one array containing all changed sites)
       |
[7] Record commit version / release writer lock
       |
[8] Reader uses dynamicInvoker and consistency contract
       |
[9] Monitor: update rate, syncAll latency, version, in-flight traffic
```

### 16.1. Choosing the boundaries of the critical section

Do not create/run compilers, invoke plugin user code, or block on network I/O while holding the writer lock if it can be staged beforehand. Keep `setTarget` and `syncAll` inside the same lock; this may make other writers wait longer if `syncAll` is expensive, so tune cadence/batching.

### 16.2. Designing logging without overclaiming

Log "update batch X completed `syncAll`" rather than "all running requests are using version X". You can log the target's version and the number of call sites, but you cannot deduce the exact time each reader started or finished merely from the updater returning.

### 16.3. Avoiding misuse of JIT assumptions

Implementations may need invalidation/deoptimization, or may use volatile targets making `syncAll` very lightweight. Do not write code that depends on specific HotSpot details (e.g., "always flushes CPU cache in way X") or promise deterministic latency. The **API-level contract** is the authoritative source for reasoning about visibility.

### 16.4. Difference between visibility and publication of other data

`syncAll` guarantees the specified visibility semantics for the **call-site target**. If the new target points to other mutable state, you must still ensure **safe publication, immutable construction, or appropriate synchronization** for that state. Recommendation: build the new target completely before `setTarget`; share data via immutable objects, final fields, or explicit JMM mechanisms. Do not use `syncAll` as a universal fix for all data races in the application.

## 17. Self-check exercises

**Exercise 1 – Distinguishing live handle and snapshot.** In Lab 1, explain why `live.invokeExact()` returns `"green"` while `oldTarget.invokeExact()` still returns `"blue"`. If you create a new `MutableCallSite` with `"red"` and reassign the `site` variable, will `live` switch to `"red"`? Why?

**Exercise 2 – Type mismatch.** Create a `(int)String` site, then try `setTarget` with a `()String` handle. Predict the exception; fix it by building a handle of the right type or intentionally using `dropArguments`/`asType`. Distinguish Java compile-time errors from runtime errors when setting the target.

**Exercise 3 – Batch update.** Add `siteC` to Lab 2, attach a `()String` target `"third-1"` then change it to `"third-2"` along with the other two sites. Use a single three-site array for `syncAll`. Explain the benefit of batching and why there is still no multi-site transaction.

**Exercise 4 – Two writers.** Remove `synchronized (UPDATE_LOCK)` in Lab 3. Why can you no longer prove that `published=2` and that the final target reflects the exact commit version order? You do not need to wait for a race to appear on every run; analyze a specific interleaving.

**Exercise 5 – Reader without latch.** Extend Lab 2 so the reader runs multiple iterations while the writer updates. List the values that may be observed before `syncAll` completes, including old/new mixes. Do not build assertions requiring a specific race combination to appear.

**Exercise 6 – Per-request atomic snapshot.** In Lab 4, read `RouteSnapshot` only once and then process both `first` and `second`. Have the updater run multiple versions; prove that a given record always contains a pair of values from the same generation, even though independent requests may see different versions.

**Exercise 7 – Volatile vs Mutable.** Change `MutableCallSite` in Lab 1 to `VolatileCallSite` and remove `syncAll`; explain volatile semantics. Experiments on update frequency/throughput are only meaningful if you benchmark warmup, avoid side effects, use enough threads, and have measurement criteria.

**Exercise 8 – Null in batch.** Put `null` into an array containing multiple sites. Why does `NullPointerException` not allow claiming that no site was synced? Design a prevalidation step.

**Exercise 9 – Hot reload.** A plugin wants to ensure no requests are still running the old target before unloading a JAR. Is `syncAll` enough? Propose a separate quiescence/in-flight accounting mechanism, distinguishing update visibility from completion of already-started requests.

**Exercise 10 – Design review.** Given a system with 1000 sites updated once per day, describe the batching and locking strategy. If 10 sites need updates every millisecond, evaluate `VolatileCallSite` or an `AtomicReference` as state indirection; analyze the tradeoffs at the API level before microbenchmarking.

### 17.1. Completion checklist

- [ ] Clearly distinguish `setTarget` as an ordinary write and `syncAll` as synchronization of the affected sites.
- [ ] State that readers can see the new target before sync and old calls still complete after sync.
- [ ] Do not claim `syncAll` makes multiple sites atomic or waits for all old requests to return.
- [ ] Protect `setTarget + syncAll` with a shared lock when there are multiple writers.
- [ ] Know how to use `dynamicInvoker` and understand direct handle snapshots from `getTarget`.
- [ ] Properly check `MethodType`, null sites, and exceptions.
- [ ] Have a strategy for batching, immutable snapshots, and choosing appropriately among Mutable/Volatile/Constant.
- [ ] Run and explain the output of the five labs, while stating the limitations of concurrency tests.

## 18. Standard Java 21 References

- [Java SE 21 – MutableCallSite](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MutableCallSite.html): contract of `setTarget`, `getTarget`, `dynamicInvoker`, `syncAll`, Java Memory Model details, null handling, and batching.
- [Java SE 21 – VolatileCallSite](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/VolatileCallSite.html): target volatile semantics and why there is no `syncAll`.
- [Java SE 21 – ConstantCallSite](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/ConstantCallSite.html): fixed target and `setTarget` unsupported.
- [Java SE 21 – CallSite](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/CallSite.html): `type()` and the CallSite contract.
- [Java SE 21 – MethodHandle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandle.html): `invokeExact`, `type`, and adapters.
- [Java SE 21 – MethodHandles](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandles.html): `constant`, `dropArguments`, `exactInvoker`.
- [Java Language Specification 21 – `17.4 Memory Model](https://docs.oracle.com/javase/specs/jls/se21/html/jls-17.html#jls-17.4): synchronization actions, happens-before, and visibility.

**Key takeaway:** `MutableCallSite.setTarget` changes **the target**, `MutableCallSite.syncAll` synchronizes **threads' acceptance of the target** per the JMM contract; a shared writer lock coordinates **updaters**, while an immutable snapshot or reader protocol coordinates **multi-value consistency**. None of those three mechanisms completely replaces the other two.
