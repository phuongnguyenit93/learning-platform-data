# 12.4 VolatileCallSite and New Target Publication Semantics

**Context:** Java Advance → dynamic-runtime → 12. CallSite.

In Java `java.lang.invoke`, a `CallSite` is a container holding a **target `MethodHandle`** used by a dynamic call site. For `VolatileCallSite`, this target carries **memory semantics like a `volatile` variable**. When thread A installs a new `MethodHandle` via `setTarget`, thread B using `getTarget` or invoking via `dynamicInvoker` will observe the update according to the `volatile` synchronization rules of the Java Memory Model (JMM). This is the reason `VolatileCallSite` exists: **changing dispatch behavior at runtime with cross-thread update visibility guarantees**, without needing `MutableCallSite.syncAll`.

This lesson explains the mechanism, API, when volatile read/write occurs, the *happens-before* relationship, the difference between **live invoker** and **target snapshot**, type rules, publication limits, how to verify with Java 17, and common mistakes.

## 1. What does a `CallSite` hold and why must a target be published?

A `MethodHandle` describes a behavior with a `MethodType` signature. `CallSite` is a **linkage point** containing the target handle used to process calls. A call site can serve one or more `invokedynamic` call sites, or be used standalone via `dynamicInvoker()`.

For example, a routing system initially points to a handler:

```text
Caller  ->  live invoker  ->  callSite.target = handle V1
                                   |
                                   +-- V1("A") -> "first:A"
```

When configuration changes, we do not want to rebuild every call site. Instead, the writer replaces `callSite.target`:

```text
                       writer thread
                            |
                   setTarget(handle V2)
                            |
                            v
Caller -> live invoker -> callSite.target = handle V2
                                              |
                                              +-- V2("A") -> "second:A"
```

**`VolatileCallSite` does not require modifying bytecode or replacing the invoker object.** The `MethodHandle` object returned by `dynamicInvoker()` can still be cached at the caller; the **actual underlying target** will be read according to the call site state at each call per the API semantics.

In practice, applications such as plugin routers, feature switches, policy dispatchers, or dynamic implementation replacement can build such an adapter. However, an important condition is that the new target **must have the same `MethodType`** and state management code must respect synchronization, errors, and lifecycle.

## 2. Three important variants of `CallSite`

| Type | Does `target` change? | Visibility semantics on change | Usage pattern |
| --- | --- | --- | --- |
| `ConstantCallSite` | No; `setTarget` throws `UnsupportedOperationException` | Target does not change after valid initialization | Fixed linkage, no need to change implementation |
| `MutableCallSite` | Yes | Similar to a **normal field**, does not automatically force other threads to see the new target promptly; `syncAll` helps synchronize listed call sites | Infrequent changes, wanting to actively confirm or batch updates |
| `VolatileCallSite` | Yes | `setTarget` as a **volatile write**, `getTarget` as a **volatile read**; live invoker uses the current target | When other threads need to see updates via the `volatile` mechanism without calling `syncAll` |

Do not interpret these three classes as three strictly ranked "speed" levels. Correctness and memory visibility requirements must be chosen first; performance is evaluated afterward. `VolatileCallSite` may have higher volatile access overhead in workloads with continuous calls; `MutableCallSite.syncAll` can be expensive and is designed for synchronization/batching. Real benchmarks depend on the JVM/JIT and target change frequency.

### How does `VolatileCallSite` differ from `MutableCallSite`?

`MutableCallSite.setTarget(newTarget)` updates like writing a normal variable. According to the Javadoc, other threads **may continue using the old target** without appropriate synchronization actions. With `MutableCallSite`, `syncAll(MutableCallSite[] sites)` is a mechanism that causes readers to discard old cached targets of the listed call sites. Do not confuse it with an operation that updates the target or a transaction that freezes all threads: calls **already started** on the old target are not revoked.

`VolatileCallSite` has no separate `syncAll`: **each `setTarget` call itself is a volatile write**. According to the Javadoc, `getTarget` performs a volatile read and must obey updates under this memory model. Using `MutableCallSite.syncAll` for a `VolatileCallSite` is the wrong API type; it accepts a `MutableCallSite[]` array, not `VolatileCallSite[]`.

## 3. Core APIs and type contracts

### 3.1 Initializing a call site

Two common constructors:

```java
// Has a target from the beginning:
VolatileCallSite readySite = new VolatileCallSite(initialHandle);

// Business behavior not yet provided:
VolatileCallSite blankSite = new VolatileCallSite(
        MethodType.methodType(String.class, String.class));
```

This is an **illustrative snippet** in a context that already has `initialHandle` and the necessary imports. With the constructor taking `MethodHandle`, the site's type is taken from `initialHandle.type()` and that handle is the initial target. With the constructor taking `MethodType`, the site has a **default target of the same type that throws `IllegalStateException` if invoked**, until you set an actual target.

Both constructors reject `null`. Therefore, do not publish a `dynamicInvoker` to a consumer and forget `setTarget` if using the `MethodType` constructor: the consumer may encounter `IllegalStateException` because the site is uninitialized.

### 3.2 `type()` does not change when relinking

`CallSite.type()` always returns **a fixed `MethodType`**. For example:

```text
(String)String
```

A `setTarget` call is only valid if `newTarget.type().equals(site.type())`. The `VolatileCallSite` class **does not** automatically perform overload resolution, boxing, or `asType` to coerce a handle with a different signature. If the new target has type `(Object)Object` or `()int`, it cannot replace a target of type `(String)String` via a direct `setTarget` call. In that case, `WrongMethodTypeException` is thrown immediately upon update and the old target remains.

You can proactively adapt a handle via `asType` according to valid conversion rules **before** passing it to `setTarget`:

```java
MethodHandle adapted = someHandle.asType(site.type());
site.setTarget(adapted);
```

The above is a **snippet**, not a standalone program. `asType` only supports the conversions it defines and may throw `WrongMethodTypeException`; it does not turn an arbitrary method into an arbitrary signature. When designing a runtime router, you should confirm `type()` from the start and create all versions with the same contract.

### 3.3 `setTarget`, `getTarget`, `dynamicInvoker`

| Operation | Effect | Characteristics |
| --- | --- | --- |
| `site.setTarget(h2)` | Installs `h2` as the new target | **Volatile write**; requires same MethodType; `null` → `NullPointerException` |
| `site.getTarget()` | Gets the target at the time of read | **Volatile read**; the received handle is a **snapshot reference** |
| `site.dynamicInvoker()` | Creates a MethodHandle that dispatches through the call site | **Live invoker**: subsequent calls use the current target, not fixed to the time the invoker was obtained |
| `site.type()` | Gets the fixed signature | Unchanged throughout the call site's lifetime |

**An important distinction:**

```java
MethodHandle live = site.dynamicInvoker();
MethodHandle captured = site.getTarget();

site.setTarget(newHandle);
```

This is a snippet with an already-initialized `site`. `live` still points **to the call site** behaviorally, so subsequent calls will follow the current target. Conversely, `captured` holds **the exact reference of a target handle that was read out**; `captured.invokeExact(...)` does not automatically look up the new target after `setTarget`. Do not mistake `getTarget()` for a way to create a live invoker.

## 4. `VolatileCallSite` and the Java Memory Model

### 4.1 `volatile` semantics of a publication

Consider two threads that both see **the same `VolatileCallSite` object**:

- The writer prepares data, creates a new target, and calls `site.setTarget(newTarget)`.
- The reader calls `site.getTarget()` or `site.dynamicInvoker()`, where fetching the target has volatile read semantics.

In memory terms, `setTarget` acts like **writing to a volatile variable**, and `getTarget` acts like **reading that volatile variable**. According to the JMM, a volatile write to that variable **synchronizes-with** subsequent volatile reads of the same variable in synchronization order; program order and synchronizes-with combine to form a **happens-before** relationship.

This enables **publishing data that was prepared before changing the target**:

```text
writer thread                               reader thread
-------------                               -------------
payload = "published";  [normal write]
             |
             v
site.setTarget(V2);     [volatile write]
                      -- synchronizes-with -->
                                           site.getTarget(); [volatile read]
                                           // observes V2
                                                     |
                                                     v
                                             read payload
                                             // sees the published data
```

Assuming the reader recognizes that it read the exact `V2` target published by the writer, and no other writer causes overlapping changes, the write operations before `setTarget(V2)` are protected by the happens-before relationship with respect to read operations after the volatile read. This is the basis for publishing a completely prepared new configuration/target.

**Crucially important:** This guarantee **does not automatically make every field elsewhere volatile** or make all application code thread-safe. It publishes states written **before** the release/volatile write to readers observing via the corresponding acquire/volatile read. If you **continue mutating** a mutable object after publication without other synchronization, a data race can still occur. You should use immutable configurations, snapshots, or proper concurrency mechanisms for state inside the target.

### 4.2 Target selection is an atomic decision point

A call site holds **one `MethodHandle` reference**. `setTarget` changes the reference with volatile semantics; a reader will use a specific target for **a single dispatch**. If there are two versions `V1` and `V2`, a call near the update time may validly go through the old **or** new version, depending on the order of reading the target and changing the target.

Distinguish clearly:

- **No "half target":** A read does not receive a torn reference; the target is always a valid `MethodHandle` if set validly.
- **No "rewinding" old calls:** If a call already selected `V1` before `setTarget(V2)`, it can continue running or finish under `V1` even after the writer has published `V2`.
- **No absolute wall-clock cutover:** The volatile relationship is expressed via synchronization order, not a guarantee that all concurrently executing threads immediately stop at the exact same nanosecond.
- **No multi-call-site transaction:** Two independent `VolatileCallSite`s having `setTarget` called sequentially are two different volatile writes; a reader may see one site as new and the other as old.

If a **fully consistent business transition** across multiple targets or multiple resources is required, you must additionally design versioning, immutable configuration snapshots, coordination, or transactions at the application layer.

### 4.3 How does `dynamicInvoker` read the current target?

By the `CallSite.dynamicInvoker()` contract, the produced handle is conceptually equivalent to:

```text
getTarget = callSite.getTarget()
return invokeExact(getTarget, arguments...)
```

This is **pseudocode**, not full Java. With `VolatileCallSite`, fetching the target uses volatile semantics. Therefore, **caching the `dynamicInvoker` object itself is correct**; that adapter always points back to the call site. Conversely, **caching the result of `getTarget()` and invoking that handle directly** fixes the version at the time of reading.

The JIT compiler may optimize the implementation as long as it **preserves the observable semantics** of the volatile call site; a program must not rely on assuming the JIT always executes a specific type of memory instruction or that the target must be resolved via an explicit Java access in source.

## 5. Complete Java 17 demo: updating target and publishing across threads

Create a file **`VolatilePublicationDemo.java`** with the following content. The program has a simple demo flow in `main` and a reader thread verifying the publication relationship. The example runs with **Java 17** and requires no dependencies outside the JDK.

```java
import java.lang.invoke.CallSite;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.VolatileCallSite;
import java.lang.invoke.WrongMethodTypeException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public final class VolatilePublicationDemo {
    static String payload;

    public static String first(String key) { return "first:" + key; }
    public static String second(String key) { return "second:" + key; }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType signature = MethodType.methodType(String.class, String.class);
        MethodHandle h1 = lookup.findStatic(VolatilePublicationDemo.class, "first", signature);
        MethodHandle h2 = lookup.findStatic(VolatilePublicationDemo.class, "second", signature);

        VolatileCallSite site = new VolatileCallSite(signature);
        MethodHandle live = site.dynamicInvoker();
        System.out.println("site.type=" + site.type());

        try {
            String ignored = (String) live.invokeExact("A");
        } catch (IllegalStateException expected) {
            System.out.println("uninitialized=IllegalStateException");
        }

        site.setTarget(h1);
        MethodHandle snapshot = site.getTarget();
        System.out.println("before=" + (String) live.invokeExact("A"));
        site.setTarget(h2);
        System.out.println("after=" + (String) live.invokeExact("A"));
        System.out.println("snapshot=" + (String) snapshot.invokeExact("A"));
        System.out.println("getTarget.isH2=" + (site.getTarget() == h2));

        try {
            site.setTarget(MethodHandles.constant(int.class, 7));
        } catch (WrongMethodTypeException expected) {
            System.out.println("badTarget=WrongMethodTypeException");
        }
        System.out.println("afterBadTarget=" + (String) live.invokeExact("A"));

        VolatileCallSite shared = new VolatileCallSite(h1);
        MethodHandle sharedInvoker = shared.dynamicInvoker();
        CountDownLatch readerStarted = new CountDownLatch(1);
        AtomicReference<String> observed = new AtomicReference<>();
        AtomicReference<Throwable> failure = new AtomicReference<>();

        Thread reader = new Thread(() -> {
            readerStarted.countDown();
            try {
                long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
                while (shared.getTarget() != h2) {
                    if (System.nanoTime() > deadline) {
                        throw new IllegalStateException("deadline exceeded");
                    }
                    Thread.onSpinWait();
                }
                observed.set(payload + "|" + (String) sharedInvoker.invokeExact("B"));
            } catch (Throwable t) {
                failure.set(t);
            }
        }, "reader");

        reader.start();
        readerStarted.await();
        payload = "published"; // normal write, before volatile setTarget
        shared.setTarget(h2);  // volatile write, publishes preceding write
        reader.join();
        if (failure.get() != null) throw new AssertionError(failure.get());
        System.out.println("reader=" + observed.get());
    }
}
```

Compile and run from the directory containing the file above:

```bash
javac --release 17 -encoding UTF-8 VolatilePublicationDemo.java
java VolatilePublicationDemo
```

**Stdout of the program on a successful run:**

```text
site.type=(String)String
uninitialized=IllegalStateException
before=first:A
after=second:A
snapshot=first:A
getTarget.isH2=true
badTarget=WrongMethodTypeException
afterBadTarget=second:A
reader=published|second:B
```

If the execution environment is paused/frozen long enough that the reader hits the 5-second deadline before seeing the update, the program will throw an `AssertionError` containing the cause; this is a **hung-test detection mechanism**, not proof that the JMM guarantees updates must complete within 5 seconds. On a normally scheduled JVM, the program produces the output above. Avoid designing business logic that forces all threads to run within a hard wall-clock interval just because `volatile` exists.

### Explanation of each stdout line

| Output line | Meaning |
| --- | --- |
| `site.type=(String)String` | The call site has a fixed target signature. |
| `uninitialized=IllegalStateException` | The constructor taking `MethodType` installs a temporary target that throws until `setTarget`. |
| `before=first:A` | `dynamicInvoker` dispatches to the installed `first` handle. |
| `after=second:A` | After `setTarget(h2)`, the same `live` object invokes the new target. |
| `snapshot=first:A` | The handle obtained from `getTarget()` before the update still invokes the old version; it is not live-linked to the site. |
| `getTarget.isH2=true` | A volatile read returns the exact `h2` reference. |
| `badTarget=WrongMethodTypeException` | The `()int` handle does not have the same type as the `(String)String` site. |
| `afterBadTarget=second:A` | A rejected update does not replace the currently valid target. |
| `reader=published\|second:B` | The reader observes `h2` via `getTarget`, sees the previously published `payload`, and then live-invokes `second`. |

### Why does the second example actually test the publication idea?

In the main thread:

```java
payload = "published"; // normal field, not volatile
shared.setTarget(h2);  // volatile write
```

In the reader thread:

```java
while (shared.getTarget() != h2) {
    Thread.onSpinWait();
}
String value = payload;
```

The two snippets above are **snippets extracted from the complete program**, not standalone applications. When the volatile read from `getTarget()` observes the `h2` reference written by the writer, the `payload` value assigned by the writer **before `setTarget(h2)`** is published by happens-before. Therefore, the reader is entitled to rely on the published value when reading `payload` after the loop.

`CountDownLatch readerStarted` is only used to **ensure the reader has started** before the writer performs the update; it is **not used as a post-publication signal** to substitute for demonstrating the volatile read. `AtomicReference` is used to safely pass the result/exception back to `main`; `Thread.join()` lets `main` wait for completion and print the result. `Thread.onSpinWait()` is only an active-wait optimization hint, **not** a synchronization/happens-before operation.

**Important for practice:** The spin loop here is meant to clarify API semantics; in production, you should not poll infinitely waiting for a `MethodHandle` to change. Use events, queues, latches, signals, or appropriate coordination mechanisms; `VolatileCallSite` guarantees target visibility, not a replacement for scheduling/liveness mechanisms.

## 6. `getTarget` snapshot vs `dynamicInvoker` live handle

This is the most important trap when designing hot-swap.

```text
               at t0                           at t1
              -------                         -------
callSite.target = H1          ->        callSite.target = H2
                  |                                |
                  + getTarget()                    + setTarget(H2)
                       |
                 snapshot = H1

live = callSite.dynamicInvoker()

snapshot.invokeExact(...)  -> H1, H1, H1, ... (does not auto-refresh)
live.invokeExact(...)      -> H1 at t0; H2 after the update is observed
```

A `MethodHandle` obtained from `getTarget` does not become a "volatile method handle" capable of changing its behavior by itself: volatile semantics lie in **the action of reading the reference from the call site**, not attached to the retrieved `MethodHandle` object.

There are two deliberate choices:

1. **Live dispatch:** Create `MethodHandle invoker = site.dynamicInvoker()` once and reuse it for calls. If the site changes target, the invoker uses the current target per call site semantics.
2. **Snapshot dispatch:** Retrieve `MethodHandle current = site.getTarget()` and execute directly on `current`. Every call using that reference follows the selected target, until code actively reads `getTarget()` again.

A snapshot can be useful when a business operation **needs to keep the same version across multiple calls**, but **it does not automatically guarantee lifecycle safety** of that version. If the old version needs to be released, resources/in-flight work must be managed separately. Changing the target does not automatically destroy old method handles held in caches or on another thread's stack.

### Do not confuse direct `invokeExact` with reflection `Method.invoke`

`MethodHandle.invokeExact` requires the call site's types to match the handle's `MethodType` exactly. With a `(String)String` target, the demo code uses:

```java
String answer = (String) live.invokeExact("A");
```

If you try to invoke with incorrect parameter/return types, the JVM may throw `WrongMethodTypeException` at invocation time, even if the target exists and `setTarget` was valid. This is a **different** error from `setTarget` receiving a handle with the wrong `MethodType`. `MethodHandle` also does not wrap exceptions from the target into `InvocationTargetException` like `java.lang.reflect.Method.invoke`.

## 7. Cutover design: what is guaranteed and what is not?

| Question | Exact conclusion |
| --- | --- |
| The writer installs `H2` successfully; do readers need `syncAll` to receive the update? | **No.** `VolatileCallSite` uses volatile semantics directly at `setTarget/getTarget`. |
| Will a call that already selected `H1` be stopped or switched to `H2` mid-execution? | **Not automatically.** A call that has entered `H1` can continue running on `H1`. |
| Can a target read receive "half H1 reference, half H2"? | **No.** The target reference is read/written atomically with volatile semantics. |
| Does `setTarget(H2)` replace all `MethodHandle` objects previously returned by `getTarget`? | **No.** Snapshot references still point to the version they received. |
| Does installing `H2` automatically make `H2`'s internal mutable state thread-safe? | **No.** Safe publication and synchronization for post-publication mutations are required. |
| Is changing two `VolatileCallSite`s consecutively an atomic transaction? | **No.** Each site has its own target; a reader can see a mixed combination of versions. |
| Do two writers concurrently calling `setTarget` automatically resolve conflicts by version/business priority? | **No.** Writes are ordered in synchronization order, but the application must manage update ordering. |
| Does `VolatileCallSite` guarantee every thread is scheduled on the CPU within X milliseconds? | **No.** That is a scheduling issue, not a memory visibility rule. |
| Can the compiler "freeze" a live invoker at the old target forever? | **Must not violate** volatile call site semantics; optimizations must preserve update observability. |

### Mid-request updates can mix results from multiple versions

Suppose a request calls the same dynamic invoker twice:

```text
request:
  resultA = live.invokeExact("A")    -> H1
            [writer sets H2]
  resultB = live.invokeExact("B")    -> H2
```

This is a valid scenario. If business logic **needs both computations in the same version**, the caller should **take a target snapshot once** (or a single configuration object snapshot) and hold it throughout the request. This may change how updates are observed: an already-started request may continue using the old version. The design must choose the appropriate consistency boundary, rather than relying on volatility for every case.

### Concurrent writers and versioning

If writer A publishes `H2` and writer B publishes `H3` nearly simultaneously, `VolatileCallSite` guarantees that the volatile operations follow memory order, but **does not decide which update is valid from a business standpoint**. `setTarget` is not a compare-and-set with an expected version.

For example, a policy needing monotonic updates from version 10 → 11 → 12 should not rely solely on two threads calling `setTarget`. You can use a single update-coordinating thread, a lock, CAS on an external state descriptor, or a separate version gate, and only then publish the final handle. Avoid assuming that "the target written last by one thread's clock" always has the highest business priority.

## 8. Safely publishing state attached to a target

### Good scenario: target and data are complete before publication

A new router implementation may attach an immutable config, dispatch table, or initialized data structure:

```text
Writer:
    newConfig = buildImmutableConfig()
    newHandle = createHandleBoundTo(newConfig)
    callSite.setTarget(newHandle)  // volatile publication

Reader:
    callSite.dynamicInvoker().invokeExact(...)
    // selected target sees state prepared before publication
```

This is **pseudocode**, not standalone runnable Java code. The happens-before relationship through the volatile target helps publish writes that occurred earlier. If the config is immutable and the target only reads the config, reasoning about/proving correctness is usually simpler.

### Dangerous scenario: mutating state after publication

```text
Writer:
    callSite.setTarget(newHandle)
    mutableConfig.put("feature", true)  // write after publication, not protected by setTarget alone

Reader:
    callSite.dynamicInvoker().invokeExact(...)
    // cannot rely solely on volatile target to guarantee seeing this mutation
```

Do not use changing a `MethodHandle` to replace all data synchronization. If a target accesses a shared mutable `HashMap`, and multiple threads modify it without a lock/concurrent collection, a data race still occurs. In many cases, the best strategy is to **build a complete immutable config and then publish a new target**; subsequent updates will create another version instead of mutating the published version.

### Memory visibility does not equal business invariants

Even when all readers see the new target at read time, the system still has other contracts: are the target's resources still active, are any requests still using the old state, is it safe to close connections/release the class loader, and how will rollback policies respond? `VolatileCallSite` solves **selecting and publishing the target reference**, not managing the lifecycle of the logic behind the target.

## 9. `VolatileCallSite` in `invokedynamic` and runtime adapter architectures

A `CallSite` can be returned by a **bootstrap method** serving `invokedynamic`, though you do not have to write `invokedynamic` bytecode to use it. `dynamicInvoker()` is the convenient API for experimenting and integrating in ordinary Java code.

A bootstrap method returns a `VolatileCallSite` to the JVM; the call site links to that site. Later, the runtime can call `setTarget` to relink the call. When updates occur across threads, volatile semantics ensure the new target is visible under the JMM. However, the bootstrap method must return a site whose `MethodType` matches exactly what the JVM requests for the dynamic call site; changing the target later **cannot** change that signature.

**Distinguish three layers of behavior:**

1. **Bootstrap/linkage:** creating/defining the call site for a dynamic call site, managing the initial name and type.
2. **Relinking:** changing `target` via `setTarget`, keeping `MethodType` unchanged.
3. **Invocation:** `dynamicInvoker`/`invokedynamic` fetches the current target and invokes it according to the signature; no need to recreate proxies or recompile Java source.

A JVM may compile and optimize the call path appropriately, but it must not apply optimizations that break observability of new targets on `VolatileCallSite`. This is why you should trust **the Javadoc/JMM contract** rather than guessing "the JIT has surely inlined H1 so setTarget has no effect".

## 10. Choosing between `VolatileCallSite` and `MutableCallSite`

### Choose `VolatileCallSite` when

- You want the new target published with **volatile semantics** to readers on other threads without `syncAll`.
- Updates are relatively frequent and you want a simple update path.
- You accept the volatile synchronization trade-off on the dispatch path, after verifying with benchmarks.
- The system needs a **live selector** with clear current-target semantics.

### Choose `MutableCallSite` when

- The latest target does not need to be received immediately by every reader with volatile semantics on every call.
- You can batch multiple updates and then call `MutableCallSite.syncAll(...)` to confirm propagation.
- Update frequency is low, the hot read path is critical, and the latency/cost of `syncAll` has been evaluated.
- There is a centralized relink management point, managing locks/versions as needed.

Illustrative snippet for updating `MutableCallSite`, **not a standalone program**:

```java
MutableCallSite mutable = new MutableCallSite(initialHandle);
mutable.setTarget(replacementHandle);
MutableCallSite.syncAll(new MutableCallSite[]{mutable});
```

`initialHandle` and `replacementHandle` must have the same `MethodType`, and the code needs to import `java.lang.invoke.MutableCallSite`. `syncAll` does not change the target; it helps readers of the listed sites discard old cached values per the API contract. Do not replace `syncAll` with a `Thread.sleep` and conclude that all threads are guaranteed to see the update.

### Choose `ConstantCallSite` when

There is no need to change the target after linkage. This is the simplest option semantically, with no mutation to publish. `ConstantCallSite.setTarget` always throws `UnsupportedOperationException`. If a system makes millions of calls but **never** relinks, there is no reason to carry target-switching capability just because flexibility sounds appealing.

## 11. Common mistakes and how to fix them

| Symptom | Common cause | How to handle |
| --- | --- | --- |
| `IllegalStateException` on first invoke | Created `new VolatileCallSite(MethodType)` without installing an actual target | `setTarget` before letting consumers invoke; or use the constructor taking a target |
| `WrongMethodTypeException` immediately at `setTarget` | `newTarget.type()` differs from `site.type()` | Check return/parameter types accurately; adapt validly before setting |
| `NullPointerException` at `setTarget(null)` | Target must be a non-null `MethodHandle` | Use a valid fallback handle if you want to "disable" functionality |
| Live invoker changed but code still calls V1 | Code holds `site.getTarget()` snapshot instead of `dynamicInvoker()` | Use the live invoker or actively re-read the target |
| Target update took effect but in-flight requests still use V1 | Request entered V1 before relink or holds a V1 snapshot | This is valid behavior; design cutover by request/version |
| One request sees V1 in the first step, V2 in the next step | Two live invocations crossing the target-change point | Take a separate snapshot/version if the request requires consistency |
| Data race with target configuration | Data mutated after `setTarget` or lacking separate synchronization | Publish immutable state before relinking; synchronize subsequent mutations |
| Two writers overwrite each other causing unintended rollback | `setTarget` does not check expected version | Use a coordinator/version gate or serialize updates |
| Test just calls `sleep(100)` and reads result | Sleep duration does not create happens-before proof for all logic | Use latch/queue, explicit volatile read, and verify ordering |
| Chose `MutableCallSite` but expects immediate cross-thread updates | Mutable's target field has normal field semantics | `syncAll` or choose Volatile according to visibility requirements |
| Tried calling `MutableCallSite.syncAll` on Volatile | Wrong class and unnecessary | Use `VolatileCallSite.setTarget` directly |
| New target prepared by non-thread-safe code | Volatile target does not fix internal target races | Protect state, prefer immutable/safe publication |
| `invokeExact` throws `WrongMethodTypeException` even though `setTarget` succeeded | Static call-site types do not match `site.type()` | Match MethodType and cast the result properly |
| Calling old target in cache after relink | Cache holds direct handle | If hot dispatch is needed, cache `dynamicInvoker` instead of snapshot |

### Pitfall: checking `getTarget() == h2` is only part of the story

A printout of `true` confirms the exact `h2` reference **at the time of the read**. It **does not** prove all threads have finished all old requests, does not prove in-progress targets are no longer running, does not verify the target guarantees thread-safety, or that closing the old version will be safe. This is why runtimes with hot reload often need an additional **lifecycle protocol**.

## 12. Debugging and testing at the right level

### 12.1 Checking type, target, and invoker

In code that already has `VolatileCallSite site` (snippet, **not standalone**):

```java
MethodType expectedType = site.type();
MethodHandle current = site.getTarget();
MethodHandle live = site.dynamicInvoker();
System.out.println("site type=" + expectedType);
System.out.println("current target type=" + current.type());
System.out.println("invoker type=" + live.type());
```

Before relinking, log `newTarget.type()` and check `equals(site.type())`. If there are wrappers/adapters, print the type **after** `asType`, `filterArguments`, or `filterReturnValue` before `setTarget`. Keep logs free of secrets or user data.

### 12.2 Testing target switching

Single-threaded testing should verify three distinct behaviors:

1. Create `dynamicInvoker` once while H1 is active; the call returns H1's result.
2. Install H2; use **the same invoker**; the call returns H2's result.
3. The target snapshot obtained before relinking still returns H1's result.

The example in section 5 implements all three cases completely. Do not just call `site.getTarget().invokeExact(...)` before and after the update and conclude `dynamicInvoker` works, because such calls fetch a new snapshot each time and do not prove the old invoker updates dynamically.

### 12.3 Testing memory publication

Create a reader and a writer as **two threads**, let the writer write normal data before `setTarget(H2)`, and have the reader wait **via volatile getTarget** until it sees H2 before reading the data. Do not use a synchronization event **after publication** that accidentally makes the test pass because of a latch rather than the volatile call site.

In the demo, the latch only proves the reader started before the writer updated; the `getTarget()` loop actually observes the new target. The reader's read of `payload` is placed **after** the successful volatile read, making this a practical demonstration of the happens-before relationship.

Note: A single passing test **cannot be a formal proof for every scheduling and every JIT**, but combining tests with the Javadoc/JMM is the way to validate the contract. For serious concurrency testing, you should have stress tests, test isolation, reasonable timeouts, and analysis of possible interleavings rather than relying on a single run.

### 12.4 When there are multiple updates

Use a clear identifier/version for each `MethodHandle`. If a rule requires "only a newer version can be installed", do not use `setTarget` as a simple CAS. When rolling back, define requirements for old requests, old resources/configs, transactions, and how to track in-flight invocations. A call site only guarantees the semantics of **the target reference**, not a replacement for **application-level governance**.

## 13. Self-check questions with answers

**Q1.** What kind of memory operation is `VolatileCallSite.setTarget(newTarget)` equivalent to?

**Answer:** A volatile write to the call site's target variable, with semantics conforming to the JMM. `getTarget` is the corresponding volatile read.

**Q2.** Why does `VolatileCallSite` not need `MutableCallSite.syncAll`?

**Answer:** Because each `setTarget`/`getTarget` has volatile semantics, cross-thread publication is guaranteed by the corresponding volatile operations. `syncAll` is an API of `MutableCallSite` to handle a target field with normal semantics.

**Q3.** A caller holds `MethodHandle saved = site.getTarget()`, and then another thread installs a new target. Does `saved.invokeExact` automatically run the new version?

**Answer:** No. `saved` is a snapshot reference to the handle that was read. Use `site.dynamicInvoker()` if you want calls to follow the current target.

**Q4.** A site has `type() = (String)String`. Is calling `setTarget` with a `(String)Object` handle valid if Object can hold a String?

**Answer:** No. `MethodType` must match **exactly**, including the return type; `setTarget` will throw `WrongMethodTypeException`. If there is a valid `asType` conversion, adapt the handle before installing.

**Q5.** If a thread has already entered H1 before the site switches to H2, is the H1 call cancelled?

**Answer:** No. The update does not reverse or automatically stop calls that have already started. New calls select the target according to the order of volatile reads and updates.

**Q6.** The writer prepares an immutable config, creates a handle pointing to the config, and calls `setTarget`. The reader sees the new handle via `getTarget`. Can it rely on the data written before `setTarget`?

**Answer:** Yes, under the conditions of the happens-before relationship: normal writes before the volatile write are published to subsequent reads after the corresponding volatile read. Do not infer that **post-publication** mutations are also automatically protected.

**Q7.** Installing target H2 into two `VolatileCallSite`s consecutively guarantees that a reader sees either both old or both new?

**Answer:** No. These are two different volatile locations, not a transaction. You need to publish a shared coordinating snapshot if you want multiple components' state to switch synchronously as one business unit.

**Q8.** Can you use a `while (!updated) Thread.sleep(10)` loop to replace `VolatileCallSite.getTarget` and claim you have verified the semantics?

**Answer:** No. `sleep` is not proof of a target's happens-before relationship. You must observe the relevant synchronized variable/object directly or apply the appropriate Java Memory Model rules.

**Q9.** What happens if `new VolatileCallSite(MethodType)` is initially invoked before `setTarget`?

**Answer:** The default target has the right MethodType but throws `IllegalStateException` when invoked. You should install a valid target before publishing the invoker to consuming code.

**Q10.** If a new target is installed but a caller still sees old results from a cached `MethodHandle`, what is the first cause to check?

**Answer:** Check whether the caller cached **`site.getTarget()`** (direct snapshot) or **`site.dynamicInvoker()`** (live invoker). Then check whether the call had already started before relinking and whether any other synchronization/lifecycle is involved.

**Q11.** Can `setTarget` replace CAS and automatically order version updates among multiple writers?

**Answer:** No. It is a volatile write of the target reference; the application needs a coordinator, lock, version checking, or another atomic state mechanism to satisfy business ordering.

**Q12.** Just because `VolatileCallSite` sees the new handle, are all mutable objects inside the handle thread-safe?

**Answer:** No. Safe publication protects state prepared before publication; subsequent mutations require separate synchronization. Prefer immutable snapshots when appropriate.

**Q13.** Does `MutableCallSite.syncAll` automatically restart requests that already started using the old target?

**Answer:** No. `syncAll` is for synchronizing visibility of the new target; it does not reverse calls currently running under the old target. Similarly, `VolatileCallSite` is not stop-the-world either.

**Q14.** Is the cost of `VolatileCallSite` always lower than `MutableCallSite`?

**Answer:** There is no fixed conclusion. Volatile semantics can increase overhead on the read path; `syncAll` also has overhead when synchronization is needed. Choose based on the visibility contract first, then benchmark with actual workload/update frequency.

## 14. Summary

- **`VolatileCallSite` is a call site whose target has `volatile` semantics.** `setTarget` is a volatile write, `getTarget` is a volatile read.
- **`dynamicInvoker` is a live dispatcher.** You can cache the invoker and still receive new targets; `getTarget` returns a target snapshot at the time of reading.
- **`MethodType` does not change.** `setTarget` requires a handle of the same type, `null` is rejected, and a mismatch causes `WrongMethodTypeException`.
- **Data publication:** normal writes before `setTarget(H2)` can be seen by readers after a volatile read observes H2, by happens-before.
- **No stop-the-world:** calls already using H1 can continue; multiple calls in the same request can go through two versions if the target changes mid-way.
- **No multi-call-site transactions or automatic version management.** A separate application strategy is needed when updating concurrently or requiring cross-request consistency.
- **Difference from `MutableCallSite`:** Mutable has normal field semantics and supports `syncAll`; Volatile does not need `syncAll` because writes/reads already synchronize under volatile rules.
- **Performance is a trade-off:** volatile read/write can incur extra cost; benchmarks and correctness requirements determine the choice.

### Official Java SE 17 Documentation

- [Oracle Javadoc — `VolatileCallSite`: volatile target, `setTarget`, `getTarget`, `dynamicInvoker`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VolatileCallSite.html)
- [Oracle Javadoc — `MutableCallSite`: normal field semantics and `syncAll`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MutableCallSite.html)
- [Oracle Javadoc — `CallSite`: target/MethodType invariant and `invokedynamic` linkage](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/CallSite.html)
- [JLS Java SE 17 `17.4: Java Memory Model, synchronization order, and happens-before](https://docs.oracle.com/en/java/javase/specs/jls/se17/html/jls-17.html#jls-17.4)