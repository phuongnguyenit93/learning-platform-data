# 12.5. Distinguishing `getTarget` from `dynamicInvoker` When a `CallSite`'s Target Can Change

In `java.lang.invoke`, a `CallSite` stores a `MethodHandle` called the **target**. If the call site is a `MutableCallSite` or `VolatileCallSite`, the program can use `setTarget(...)` to change the target at runtime. Two seemingly similar methods serve **two different needs**:

- **`site.getTarget()`:** reads and returns the **currently observed MethodHandle object**. If you keep the result in a variable, you hold *a reference to the handle at the time of reading*, not a self-updating link.
- **`site.dynamicInvoker()`:** returns a **MethodHandle used to dispatch through the CallSite itself**. When invoking this handle, it delegates to the target that the call site observes at that dispatch; if the call site is relinked and the update is visible, the same dynamic invoker can execute the new target.

**The decisive difference:** `getTarget()` is useful for taking a snapshot of the *target link*; `dynamicInvoker()` is useful for keeping a call path **following a changeable link**. Do not confuse a **MethodHandle cached from `getTarget()`** with a cached dynamic invoker. Furthermore, "following the new link" does not mean all threads automatically see the update immediately: memory visibility rules depend on the `CallSite` type and synchronization mechanism.

This lesson presents the differences on Java 17+, explains `ConstantCallSite`, `MutableCallSite`, and `VolatileCallSite`, relates to `invokedynamic`, handles type invariants, `syncAll`, caches/combinators, common errors, and provides a complete program with verified output.

## 1. Nature of `CallSite` and target

`CallSite` is a holder for a target `MethodHandle`. When a JVM `invokedynamic` instruction is linked to a call site, dispatching will be based on the target belonging to that link. However, you can also create a call site and call `dynamicInvoker()` **without having to write an `invokedynamic` instruction in bytecode yourself** (*free-floating call site*).

Suppose:

```java
MethodHandle a = MethodHandles.constant(String.class, "A");
MutableCallSite site = new MutableCallSite(a);
```

Target `a` has type `()String`: it takes no arguments and returns `String`. Here:

- `site` is a **CallSite**, not a `String` value.
- `site.getTarget()` returns a **MethodHandle**, which is target `a` when there has been no update yet.
- `site.dynamicInvoker()` also returns a **MethodHandle**, but it is **the call path through the site**.
- Only when `(String) handle.invokeExact()` is called does it execute the target and obtain the string `"A"`.

Diagram:

```text
T0: site.target = handle A
T1: site.setTarget(handle B)
T2: site.setTarget(handle C)

snapshot = site.getTarget() at T0 ------> handle A (keeps reference A forever)
live     = site.dynamicInvoker() at T0 --> reads link from site on invoke
                                            at T0: A
                                            at T1: B if update is observed
                                            at T2: C if update is observed
```

This is the difference between **holding an implementation** and **holding a dispatch point**. `setTarget(B)` replaces the **target reference in the CallSite**, does not mutate the `MethodHandle A` object, does not rewrite the local variable `snapshot`, and does not automatically update every pipeline that previously used A.

### 1.1. `CallSite.type()` is always fixed

Every call site has a permanent `MethodType`, represented by `site.type()`. `setTarget(newTarget)` is only valid if `newTarget.type().equals(site.type())`; the requirement includes the **exact number of parameters, exact type of each parameter, and exact return type**. Even if two types *can* be converted using an adapter, `setTarget` does not automatically call `asType`.

```java
MethodHandle a = MethodHandles.constant(String.class, "A"); // ()String
MethodHandle b = MethodHandles.constant(String.class, "B"); // ()String
MethodHandle i = MethodHandles.constant(int.class, 42);    // ()int

MutableCallSite site = new MutableCallSite(a);
site.setTarget(b); // Valid: ()String equals ()String
// site.setTarget(i); // WrongMethodTypeException: ()int differs from ()String
```

`setTarget(i)` is commented out to illustrate the error condition. The standalone program below performs this invalid call inside a `try/catch` block and prints the exception. A call site **can change its target forever, but cannot change its MethodType**. `site.dynamicInvoker().type()` is also equal to `site.type()`.

## 2. API comparison table: handle snapshot or dynamic link?

| Criterion | `getTarget()` | `dynamicInvoker()` |
| --- | --- | --- |
| Returns | `MethodHandle` stored as target at the time of reading | `MethodHandle` used to call indirectly through `CallSite` |
| If stored in a variable | Variable holds the exact handle read | Variable holds the call path bound to the site |
| After `setTarget(B)` | The handle **obtained previously** is still A; a **new** `getTarget()` call may read B | The same invoker can call B once the update is observed |
| Type of result | `site.type()` | `site.type()` |
| Cost/behavior | Calls the captured target; does not need to re-read the site on each invoke | Each dispatch must have the semantics of retrieving the target through the site |
| Other threads | Each `getTarget()` call follows subclass semantics, may encounter stale value in MutableCallSite | Similarly: dynamic route follows subclass semantics, does not automatically turn Mutable into volatile |
| `ConstantCallSite` | Always fixed target | Always returns the fixed target |
| Use cases | Diagnostics, pinning implementation/version, auditing | Relinking, strategy swapping, mutable router |

**A "snapshot" is only a snapshot of the MethodHandle reference currently in the site**, not an immutable copy of the entire behavior. If MethodHandle A itself reads a mutable variable or calls `dynamicInvoker()` of another CallSite, A's result can still change. One should not state that "`getTarget()` makes all internal state of the target immutable".

### 2.1. Caching `getTarget()` keeps the old target

```java
MutableCallSite site = new MutableCallSite(
        MethodHandles.constant(String.class, "A"));

MethodHandle snapshot = site.getTarget();
site.setTarget(MethodHandles.constant(String.class, "B"));

String oldResult = (String) snapshot.invokeExact();  // "A"
String newResult = (String) site.getTarget().invokeExact(); // "B" same thread
```

`snapshot` is not a pointer that can automatically switch its destination to B. For `MutableCallSite`, a new `site.getTarget()` call can see B; when both `setTarget` and `getTarget` occur in the same thread as in the example, it sees B. However, if **another** thread reads the site, seeing the new target depends on synchronization.

### 2.2. Caching `dynamicInvoker()` keeps the dynamic dispatch path

```java
MutableCallSite site = new MutableCallSite(
        MethodHandles.constant(String.class, "A"));

MethodHandle live = site.dynamicInvoker();
String before = (String) live.invokeExact(); // "A"

site.setTarget(MethodHandles.constant(String.class, "B"));
String after = (String) live.invokeExact(); // "B" in the updating thread
```

There is no need to call `dynamicInvoker()` again after each `setTarget`. This is the practical difference in systems that update targets at runtime.

The Javadoc describes the dynamic invoker as equivalent to a chain combining the site's `getTarget` with `MethodHandles.exactInvoker(site.type())`, via `MethodHandles.foldArguments(...)`. Therefore, in terms of **behavior**, it reads the target according to the site's state at dispatch time, then executes that target. That is the specification's way of expressing it, not forcing the JVM to execute every step literally like an interpreter; the JVM can optimize as long as it preserves the contract.

**Do not rely on object identity** of `dynamicInvoker()` results from multiple calls across different subclasses to verify "dynamic" behavior. What matters is **behavior**, not whether there is a single wrapper object or multiple objects.

## 3. Impact of the three `CallSite` subclasses

### 3.1. `ConstantCallSite`: permanent target

`ConstantCallSite` from the start **does not allow relinking**. `setTarget(...)` always throws `UnsupportedOperationException`. `getTarget()` returns the permanent target, and `dynamicInvoker()` can and in fact **returns that exact target**, because there is no dynamic state to re-read.

```java
MethodHandle target =
        MethodHandles.constant(String.class, "fixed");
ConstantCallSite site = new ConstantCallSite(target);

MethodHandle captured = site.getTarget();
MethodHandle dynamic = site.dynamicInvoker();

System.out.println(captured == dynamic); // true for ConstantCallSite
// site.setTarget(target); // UnsupportedOperationException
```

`captured == dynamic` is true according to `ConstantCallSite`'s contract, but **one must not infer** that `getTarget()` and `dynamicInvoker()` calls in general always return the same object on `MutableCallSite`/`VolatileCallSite`.

If you never want to change the implementation, `ConstantCallSite` is the clear-intent choice and avoids the overhead/visibility rules of a mutable target.

### 3.2. `MutableCallSite`: target as an ordinary field

`MutableCallSite.setTarget(...)` is allowed to update, and `getTarget()` has the semantics of an **ordinary non-volatile field read**. Another reading thread **may not see the new update from the writing thread**, and may hold/cache the old target indefinitely if synchronization is lacking. The dynamic invoker of a mutable call site is also subject to the same type of link semantics.

```java
MutableCallSite site = new MutableCallSite(
        MethodHandles.constant(String.class, "A"));
MethodHandle live = site.dynamicInvoker();

site.setTarget(MethodHandles.constant(String.class, "B"));
MutableCallSite.syncAll(new MutableCallSite[] {site});
```

`syncAll` is the dedicated operation to publish updates of **the MutableCallSites listed in the array** and force reading threads to discard cached old targets. Essential points:

- Perform `setTarget` for the right site **before** `syncAll`.
- Readers may already see the new target immediately after `setTarget`, **or** still see the old target until the synchronization process.
- `syncAll` does not go back to modify invocations that have already **started** on the old target.
- If updating multiple sites at once, `syncAll(new MutableCallSite[]{a,b})` **does not** turn the two updates into an atomic transaction for readers.
- The Javadoc recommends coordinating `setTarget` and `syncAll` under appropriate **mutual exclusion** among writers, avoiding competing update batches.
- `syncAll` can be expensive; multiple sites can be batched into one sync when the algorithm allows.

Do not state "`dynamicInvoker` always calls the globally newest target" for MutableCallSite. A more accurate statement: it **goes through the target that the call site observes at the time of invocation**, and `MutableCallSite`'s visibility may delay the observation of updates in other threads.

### 3.3. `VolatileCallSite`: target with volatile semantics

`VolatileCallSite` also allows changing the target, but `setTarget` is defined as a **volatile write**, and `getTarget` as a **volatile read**. The dynamic invoker follows this link so it can observe updates according to volatile semantics without needing `MutableCallSite.syncAll`.

```java
VolatileCallSite site = new VolatileCallSite(
        MethodHandles.constant(String.class, "A"));

MethodHandle frozen = site.getTarget();
MethodHandle live = site.dynamicInvoker();
site.setTarget(MethodHandles.constant(String.class, "B"));

String a = (String) frozen.invokeExact(); // "A"
String b = (String) live.invokeExact();   // "B" with read after write
```

In other threads, the VolatileCallSite specification guarantees update observability corresponding to **volatile read/write** of the Java Memory Model. That does not mean an invocation **currently mid-execution** on A will suddenly be switched to B. Application correctness must still handle calls that have already entered the old implementation.

### 3.4. Rules for choosing a subclass

| Need | Suitable choice |
| --- | --- |
| Never change target during lifetime | `ConstantCallSite` |
| Change target infrequently, have a batch publishing mechanism, and accept `syncAll` cost | `MutableCallSite` |
| Target changes need to be seen by readers in other threads with volatile semantics | `VolatileCallSite` |
| Need to swap multiple handlers atomically at the system level | A snapshot/routing policy with its own synchronization; calling `syncAll` alone is not enough |

None of the types guarantees automatically interrupting an old target call that has already started. Quiescence/epoch/versioning or locks are needed if the problem requires no requests to remain processing with the old implementation after a specific point.

## 4. Traps when building `MethodHandle` chains

A method-handle pipeline can be built directly from the target or from the dynamic invoker:

```java
MethodHandle frozen = site.getTarget();
MethodHandle live = site.dynamicInvoker();

MethodHandle frozenFilter =
        MethodHandles.filterReturnValue(frozen, appendMark);
MethodHandle liveFilter =
        MethodHandles.filterReturnValue(live, appendMark);
```

Here, assume `site.type() == ()String` and `appendMark.type() == (String)String`; `appendMark` appends `!`, and variables have been declared in the appropriate context. After the site changes from A to B:

- `frozenFilter`: still calls A then appends the mark → `"A!"`.
- `liveFilter`: calls through the site, so once B is observed it returns `"B!"`.

`MethodHandles.filterReturnValue(...)` **does not automatically know** that `frozen` originated from `CallSite.getTarget()`. It wires the exact handle object passed in. If you need the pipeline to adapt to relinking, **put the dynamic invoker into the pipeline from the beginning** or proactively rebuild the pipeline when the target changes.

## 5. Complete, compilable, and runnable Java 17+ example

The example uses targets of type `()String` to make the output clear. Target changes on `MutableCallSite` are performed in **the same thread** and call `syncAll` to illustrate the official publishing method; the program does not use concurrency timing to infer visibility.

File **`CallSiteTargetDemo.java`**:

```java
import java.lang.invoke.CallSite;
import java.lang.invoke.ConstantCallSite;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.MutableCallSite;
import java.lang.invoke.VolatileCallSite;
import java.lang.invoke.WrongMethodTypeException;

public class CallSiteTargetDemo {
    static String call(MethodHandle handle) throws Throwable {
        return (String) handle.invokeExact();
    }

    public static void main(String[] args) throws Throwable {
        MethodHandle a = MethodHandles.constant(String.class, "A");
        MethodHandle b = MethodHandles.constant(String.class, "B");
        MethodHandle c = MethodHandles.constant(String.class, "C");

        MutableCallSite mutable = new MutableCallSite(a);
        MethodHandle snapshot = mutable.getTarget();
        MethodHandle live = mutable.dynamicInvoker();

        System.out.println("mutable.type=" + mutable.type());
        System.out.println("before.snapshot=" + call(snapshot));
        System.out.println("before.live=" + call(live));

        MethodHandle concat = MethodHandles.lookup().findVirtual(
                String.class, "concat", MethodType.methodType(
                        String.class, String.class));
        MethodHandle appendMark =
                MethodHandles.insertArguments(concat, 1, "!");
        MethodHandle frozenFilter =
                MethodHandles.filterReturnValue(snapshot, appendMark);
        MethodHandle liveFilter =
                MethodHandles.filterReturnValue(live, appendMark);

        mutable.setTarget(b);
        MutableCallSite.syncAll(new MutableCallSite[]{mutable});
        System.out.println("after.snapshot=" + call(snapshot));
        System.out.println("after.fresh=" + call(mutable.getTarget()));
        System.out.println("after.live=" + call(live));
        System.out.println("after.frozenFilter=" + call(frozenFilter));
        System.out.println("after.liveFilter=" + call(liveFilter));

        mutable.setTarget(c);
        MutableCallSite.syncAll(new MutableCallSite[]{mutable});
        System.out.println("later.snapshot=" + call(snapshot));
        System.out.println("later.live=" + call(live));
        System.out.println("later.liveFilter=" + call(liveFilter));

        VolatileCallSite volatileSite = new VolatileCallSite(a);
        MethodHandle volatileSnapshot = volatileSite.getTarget();
        MethodHandle volatileLive = volatileSite.dynamicInvoker();
        System.out.println("volatile.before=" + call(volatileLive));
        volatileSite.setTarget(b);
        System.out.println("volatile.snapshot=" + call(volatileSnapshot));
        System.out.println("volatile.live=" + call(volatileLive));

        CallSite constant = new ConstantCallSite(a);
        System.out.println("constant.snapshot="
                + call(constant.getTarget()));
        System.out.println("constant.dynamic="
                + call(constant.dynamicInvoker()));
        System.out.println("constant.same="
                + (constant.getTarget() == constant.dynamicInvoker()));
        try {
            constant.setTarget(b);
        } catch (UnsupportedOperationException e) {
            System.out.println("constant.write="
                    + e.getClass().getSimpleName());
        }

        try {
            mutable.setTarget(MethodHandles.constant(int.class, 1));
        } catch (WrongMethodTypeException e) {
            System.out.println("wrongType="
                    + e.getClass().getSimpleName());
        }
        try {
            mutable.setTarget(null);
        } catch (NullPointerException e) {
            System.out.println("nullTarget="
                    + e.getClass().getSimpleName());
        }

        MutableCallSite blank = new MutableCallSite(
                MethodType.methodType(String.class));
        MethodHandle blankLive = blank.dynamicInvoker();
        System.out.println("blank.type=" + blank.type());
        try {
            call(blankLive);
        } catch (IllegalStateException e) {
            System.out.println("blank.before="
                    + e.getClass().getSimpleName());
        }
        blank.setTarget(MethodHandles.constant(String.class, "D"));
        System.out.println("blank.after=" + call(blankLive));
    }
}
```

Run in the directory containing the file using JDK 17:

```bash
javac --release 17 CallSiteTargetDemo.java
java CallSiteTargetDemo
```

**Exact** `stdout`:

```text
mutable.type=()String
before.snapshot=A
before.live=A
after.snapshot=A
after.fresh=B
after.live=B
after.frozenFilter=A!
after.liveFilter=B!
later.snapshot=A
later.live=C
later.liveFilter=C!
volatile.before=A
volatile.snapshot=A
volatile.live=B
constant.snapshot=A
constant.dynamic=A
constant.same=true
constant.write=UnsupportedOperationException
wrongType=WrongMethodTypeException
nullTarget=NullPointerException
blank.type=()String
blank.before=IllegalStateException
blank.after=D
```

### 5.1. Output explanation

1. **`mutable.type=()String`:** `CallSite` has a fixed type, which does not change when switching targets A → B → C.
2. **`before.snapshot=A` / `before.live=A`:** before relinking, both go to A.
3. **`after.snapshot=A` / `after.fresh=B`:** the old snapshot keeps A; a **new** `getTarget()` call in the same thread receives B.
4. **`after.live=B`:** the same `live` variable created before relinking still calls B, without needing to recreate `dynamicInvoker()`.
5. **`after.frozenFilter=A!` / `after.liveFilter=B!`:** a pipeline using a snapshot differs from a pipeline using a dynamic invoker. After switching further to C, `later.snapshot=A` and `later.liveFilter=C!` continue to confirm the difference.
6. **`volatile.snapshot=A` / `volatile.live=B`:** the same snapshot vs dynamic route rule on `VolatileCallSite`; adds volatile semantics across threads.
7. **`constant.same=true`:** for `ConstantCallSite`, `getTarget` and `dynamicInvoker` both return the permanent target. `setTarget` is rejected.
8. **`wrongType`:** `MutableCallSite` does not accept an `()int` handle when `type()==()String`.
9. **`nullTarget`:** `setTarget(null)` is blocked; CallSite requires a non-null target.
10. **`blank.before` / `blank.after`:** the constructor taking a `MethodType` sets an initial target with the right type that **throws IllegalStateException when invoked**. After `setTarget(D)`, the **same** `blankLive` runs and returns D.

**Limitation of the demonstration:** the code runs sequentially, so it is not a stress test guaranteeing visibility across multiple threads. Any claims about `syncAll` and volatile semantics should be based on the API specification, not a single run printing the expected output.

## 6. Do not confuse calling `getTarget()` once with re-reading every time

Three different ways of writing it (pseudocode; replace `...` with real argument lists and types):

```java
// A: Read the target once and keep it long-term.
MethodHandle cached = site.getTarget();
for (...) {
    cached.invokeExact(...);
}

// B: Re-read the site's target on every call.
for (...) {
    site.getTarget().invokeExact(...);
}

// C: Get the dynamic invoker once; dispatch through the site on every call.
MethodHandle live = site.dynamicInvoker();
for (...) {
    live.invokeExact(...);
}
```

- **A** does not see relinks through that site; if handle A contains mutable logic internally, the result can still change due to **other state**, not because the site was relinked.
- **B** can see new relinks in `getTarget` reads, but with `MutableCallSite` and multiple threads, a read is **not guaranteed** to see the newest target without synchronization.
- **C** keeps the dynamic call path and application code does not have to read the target itself in the loop. However, with `MutableCallSite`, the visibility of each dispatch still follows ordinary-field semantics.

Approaches B and C are not necessarily equivalent in cost or optimization; the semantic rule is that both read the target via the CallSite at invocation time, unlike approach A which holds a specific MethodHandle.

With `ConstantCallSite`, A and C differ in code intent but have no observable difference regarding relinking, because the target cannot be changed.

## 7. MethodType immutability and adapters

`setTarget` does not automatically adapt types; the target type must equal `site.type()`. Example:

```java
MethodHandle oldTarget =
        MethodHandles.constant(String.class, "A"); // ()String
MutableCallSite site = new MutableCallSite(oldTarget);

MethodHandle wrong =
        MethodHandles.constant(Object.class, "B"); // ()Object

// site.setTarget(wrong); // WrongMethodTypeException

MethodHandle adapted = wrong.asType(site.type()); // ()String
site.setTarget(adapted);                         // Valid
```

The snippet above is illustrative and can be placed inside an exception-handling method according to the project. `asType` only works when the conversion can be performed; it **does not** grant permission to change the number of parameters, create arbitrary conversions, or ignore a target returning an incompatible value.

For example, if the new target needs to take an `int`:

```java
MethodType signature =
        MethodType.methodType(String.class, int.class); // (int)String
MutableCallSite site = new MutableCallSite(signature);

// To replace with a constant ()String, an ignored int parameter must be added:
MethodHandle constant =
        MethodHandles.constant(String.class, "ok");
MethodHandle acceptsInt =
        MethodHandles.dropArguments(constant, 0, int.class);

site.setTarget(acceptsInt); // (int)String, valid
```

`site.dynamicInvoker()` also has type `(int)String`. When calling `invokeExact`, the caller must pass `int` and expect a `String` return at the call site; if the descriptor is wrong, `WrongMethodTypeException` comes from **the MethodHandle invocation**, not necessarily from `setTarget`. There are two different sources of type errors that must be diagnosed properly.

## 8. Other threads and `syncAll`: do not infer from single-threaded tests

Imagine:

```text
Updater                              Reader
-------                              -------------------------
site.setTarget(B)                    savedLive.invokeExact()
MutableCallSite.syncAll([site])      savedLive.invokeExact()
                                     savedLive.invokeExact()
```

This is a logical diagram, not runnable Java code. Before `syncAll` takes effect, the reader **may see B early** or still see A. Once synchronization completes, future readers must accept the new target state according to `syncAll`'s contract, but invocations that have already started with A are not reversed. If another writer relinks again to C at that moment, the race must be considered separately.

**Distinguish two needs:**

- **Want threads to see the new target after every update:** `VolatileCallSite` is the direct choice for volatile semantics.
- **Want infrequent, batched updates:** `MutableCallSite` + `syncAll`, with writer discipline and appropriate synchronization cost, may be better for an infrequent relinking model.

Even `VolatileCallSite` does not make a promise like "after exactly 5 ms all old tasks have finished". Memory visibility and request scheduling/lifetime are two different issues.

If you need to update **multiple CallSites simultaneously as a transaction**, `MutableCallSite.syncAll(new MutableCallSite[]{a,b})` does not provide an atomic snapshot of the entire group to readers. One possible solution is to publish **a single** target pointing to an immutable routing snapshot containing all strategies, or use a lock/epoch/version to manage the group.

## 9. Relationship to `invokedynamic` and bootstrap

An `invokedynamic` call site in bytecode needs a bootstrap method to determine the linkage. The bootstrap method can return a `CallSite`; subsequent calls to the dynamic site then dispatch to the target according to the linked call site.

`site.dynamicInvoker()` provides a `MethodHandle` that behaves like an `invokedynamic` call **already linked to that site**, even when the site object is created in Java source just for standalone use.

Do not confuse:

- **`CallSite`:** the holder of the linkage state.
- **`getTarget()`:** reads the MethodHandle currently acting as the target.
- **`dynamicInvoker()`:** creates/retrieves a MethodHandle that calls through the link.
- **`MethodHandle.invokeExact()`:** executes a MethodHandle with the descriptor at the call site; not an operation to retrieve the link.

```java
MethodHandle live = site.dynamicInvoker();
String answer = (String) live.invokeExact(); // when site.type() is ()String
```

The `(String)` cast near `invokeExact` determines the call site's return type as `String`; for other types, the arguments and cast must be chosen to match the exact `MethodType`. Fixing `setTarget` cannot rescue a caller with a wrong `invokeExact` descriptor.

## 10. Call site initialized with `MethodType` but without a useful target yet

Not every constructor receives a ready `MethodHandle`:

```java
MutableCallSite site = new MutableCallSite(
        MethodType.methodType(String.class));
MethodHandle live = site.dynamicInvoker();
```

This call site has type `()String` and a **non-null target**. The default target is a **throwing MethodHandle** of the matching type; if invoked immediately, it throws `IllegalStateException`. This differs from `site.setTarget(null)`, which throws `NullPointerException`.

```java
// Illustrative snippet in a method that throws Throwable.
try {
    String value = (String) live.invokeExact();
} catch (IllegalStateException e) {
    // No useful execution target has been set yet.
}

site.setTarget(MethodHandles.constant(String.class, "ready"));
String value = (String) live.invokeExact(); // "ready"
```

`live` does not need to be recreated. For a call site linked by a bootstrap method, it is usually necessary to set a valid target before exposing the call site to avoid this temporary state.

## 11. Common errors and troubleshooting table

| Symptom | Cause | Fix |
| --- | --- | --- |
| Cached handle then target changed but result is still old | Cached `site.getTarget()` | If relink tracking is needed, cache `site.dynamicInvoker()` |
| Calling `getTarget()` multiple times in another thread still sees old target | `MutableCallSite` has ordinary field semantics | Use `syncAll`/appropriate synchronization or `VolatileCallSite` |
| `live.invokeExact()` throws `WrongMethodTypeException` | Descriptor at caller differs from `live.type()` | Check parameter types and **return type**, cast `invokeExact` correctly |
| `setTarget` throws `WrongMethodTypeException` | `newTarget.type()` differs from `site.type()` | Adapt with `asType`/valid combinator before setting |
| `setTarget(null)` throws `NullPointerException` | Target cannot be null | Use an explicit throwing target if not ready yet |
| `ConstantCallSite.setTarget(...)` throws `UnsupportedOperationException` | Constant's target is permanent | Use Mutable/Volatile if relinking is needed |
| New call site with `MethodType` throws `IllegalStateException` on invoke | Default target is a throwing handle | Set a valid target before invoking |
| `filterReturnValue` pipeline still executes A | Pipeline was built from `getTarget()` snapshot | Build pipeline from dynamic invoker or rebuild on update |
| After `syncAll` still see requests processing A | Request already retrieved or started target A | Use quiescence/epoch/lock if old requests must be blocked |
| Changed multiple sites then `syncAll` but see mixed state | `syncAll` is not a multi-site transaction | Design a group-level snapshot/version |

**Quick debug**, in a context where `site` and `newTarget` already exist:

```java
System.out.println("site.type: " + site.type());
System.out.println("current.type: " + site.getTarget().type());
System.out.println("new.type: " + newTarget.type());
System.out.println("invoker.type: " + site.dynamicInvoker().type());
```

This snippet helps find **type mismatches**. Do not assume that `println` calls automatically solve visibility on all other multithreaded paths.

## 12. When to intentionally use a snapshot, and when to keep a dynamic invoker?

**Pinning a version for an entire request.** If a request must use the exact implementation chosen at the start, fetching `MethodHandle requestTarget = site.getTarget()` once can be a legitimate business requirement. Afterward, the request will run the same handle. However, if that handle itself reads mutable state, "same handle" does not mean "all the same data".

**Swapping strategies for subsequent requests.** When an application wants to hot-swap algorithms or update a dynamic dispatch table, caching `dynamicInvoker()` is the natural approach. The producer changes the target and publishes the update appropriately for `MutableCallSite`/`VolatileCallSite`; the caller does not have to reassemble every pipeline itself.

**Ensuring version consistency across multiple targets.** If targets A/B/C form a configuration set, consider publishing an immutable snapshot via a single target instead of updating multiple sites separately without a version transaction.

*Correctness* issues must come before *speed* guesses: a snapshot pipeline might run fast in some benchmarks, but if the requirement is to follow updates, it is functionally wrong; a dynamic pipeline, even if it updates properly, still needs appropriate synchronization.

## 13. Comprehension check exercises

Suppose the following calls occur in order **in the same thread**:

```java
MethodHandle a = MethodHandles.constant(String.class, "A");
MethodHandle b = MethodHandles.constant(String.class, "B");

MutableCallSite site = new MutableCallSite(a);
MethodHandle x = site.getTarget();
MethodHandle y = site.dynamicInvoker();

site.setTarget(b);
MutableCallSite.syncAll(new MutableCallSite[]{site});
```

**A.** What does `(String) x.invokeExact()` return? What does `(String) y.invokeExact()` return?

**B.** If after `setTarget(b)` we call `MethodHandle z = site.getTarget()`, does `z` have the same result as `x`? Does `y` need to be reinitialized?

**C.** If we build `filterReturnValue(x, appendMark)` and `filterReturnValue(y, appendMark)`, after relinking further to C how will the two pipelines differ?

**D.** Thread 1 calls `setTarget(B)`, thread 2 calls `y.invokeExact()` continuously without synchronization. Is it valid to assert that thread 2 will soon see B?

**E.** What does `VolatileCallSite` help solve in D? Does it stop A invocations that are already running?

**F.** Can an `()String` handle be replaced with `()int` via `site.setTarget(...)`? If we want to replace `()Object` with `()String`, what needs to be done first?

**G.** With `ConstantCallSite`, can `getTarget()` and `dynamicInvoker()` return the same object? Is `setTarget` allowed?

**H.** Does `new MutableCallSite(MethodType.methodType(String.class))` have a null target? If invoked before `setTarget`, which error appears?

**Answers:**

- **A:** `x` returns `"A"` because it captured the old handle; `y` returns `"B"` because it goes through the CallSite and the update is observed.
- **B:** `z` points to target B, while `x` keeps A; `y` is still usable and does not need to be recreated.
- **C:** The pipeline from `x` continues to call A; the pipeline from `y` follows the new target C once the link is observed.
- **D:** No. `MutableCallSite` reads the target like an ordinary field, so another thread may keep the old target without synchronization.
- **E:** A volatile target has the semantics of a volatile variable, providing stronger visibility; it does not retroactively change A calls that have already started.
- **F:** No, `()int` differs from `()String` and `setTarget` throws `WrongMethodTypeException`. For `()Object`, use `asType(site.type())` if the conversion is valid before setting.
- **G:** Yes; `ConstantCallSite` actually returns the permanent target for both. `setTarget` throws `UnsupportedOperationException`.
- **H:** No; the default target is a throwing MethodHandle with the right type, so the initial invocation throws `IllegalStateException`.

## 14. Official reference sources

- [Java SE 17 — `CallSite`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/CallSite.html): target, `getTarget`, `dynamicInvoker`, immutable `MethodType`.
- [Java SE 17 — `MutableCallSite`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MutableCallSite.html): ordinary-field memory semantics, `syncAll`, cached target values across multiple threads.
- [Java SE 17 — `VolatileCallSite`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VolatileCallSite.html): target with volatile semantics and dynamic invoker.
- [Java SE 17 — `ConstantCallSite`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/ConstantCallSite.html): permanent target and unsupported `setTarget`.
- [Java SE 17 — `MethodHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html): `invokeExact`, `asType`, and signature rules.
- [Java Language Specification SE 17 — `17.4 Memory Model](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4): memory visibility and happens-before.

**Remember:** `getTarget()` reads out a current MethodHandle; when caching the result, you **keep that target**. `dynamicInvoker()` is a MethodHandle that calls **through the CallSite**, which can be kept long-term and still follow relinks. With multiple threads, you must synchronize properly: `MutableCallSite` may need `syncAll`, while `VolatileCallSite` provides volatile semantics. The target can change, but **`CallSite.type()` does not change**.
