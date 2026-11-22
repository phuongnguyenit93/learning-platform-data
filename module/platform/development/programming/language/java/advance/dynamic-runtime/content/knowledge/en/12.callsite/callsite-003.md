# 12.3 MutableCallSite, setTarget, and Cross-Thread Visibility of Changes

## 1. Problem: replacing an already linked call at runtime

In a dynamic linking system, sometimes the same call site needs to **change its implementation** without changing its signature. For example: a runtime switches a handler from version A to version B; a DSL changes its processing operation based on configuration; or a dispatcher detects a new data type and needs to relink the call.

Java supports this with `java.lang.invoke.CallSite`, an object that holds a current `MethodHandle` called the **target**. With `MutableCallSite`, the target can be changed via `setTarget(...)`. An `invokedynamic` call linked to the site or `site.dynamicInvoker()` will dispatch to the target used by the site at the time of the call.

The hard part does not lie in the statement that replaces the target, but in the **Java Memory Model (JMM)**: the fact that one thread writes a new target does not automatically force other running threads to see that change immediately. This is the main goal of this lesson.

### After this lesson, you will

- Create a `MutableCallSite` with an initial target or a `MethodType` that does not yet have a useful target.
- Distinguish between `getTarget()`, `setTarget(...)`, and `dynamicInvoker()`.
- Replace a valid target while keeping the call site's type invariant, and analyze `WrongMethodTypeException`.
- Correctly explain the cross-thread semantics of `setTarget`, `getTarget`, and `MutableCallSite.syncAll(...)`.
- Distinguish the visibility guarantees of `MutableCallSite` from `VolatileCallSite` and `ConstantCallSite`.
- Design relinking that manages races, overhead, consistency, and concurrency testing without drawing false conclusions from an accidental execution result.

## 2. CallSite Map and Important Components

A `CallSite` has an **immutable type** `MethodType`. Even if the target changes, every new target must have **the exact same type** as the old target. Three main kinds of call sites:

| Type | Is target mutable? | Visibility semantics across threads | When appropriate |
| --- | --- | --- | --- |
| `ConstantCallSite` | No | Fixed binding after creation; no target replacement. | The call target never changes throughout the site's lifetime. |
| `MutableCallSite` | Yes | Target behaves like an **ordinary field** (not volatile). Calling `setTarget` alone does not guarantee other threads quickly see the new target. | Infrequent/batched relinking; `syncAll` can be used to publish the target. |
| `VolatileCallSite` | Yes | Target behaves like a **volatile field**; reads must obey JMM volatile guarantees. | The target changes frequently or requires cross-thread visibility with volatile semantics. |

Components to separate clearly:

- **`site.type()`:** the immutable type of the site, for example `(int)String`.
- **`site.getTarget()`:** gets a **MethodHandle that is the target the caller currently observes**. This is not a "live wrapper" that automatically replaces the reference value already stored in a Java variable.
- **`site.setTarget(newTarget)`:** replaces the stored target. The type `newTarget.type()` must equal `site.type()`.
- **`site.dynamicInvoker()`:** creates a MethodHandle used to go through the **site**, picking up subsequent target changes according to the memory semantics of the call site type.
- **`MutableCallSite.syncAll(sites)`:** a synchronization operation for an **array of mutable call sites**, so that other threads do not continue using an overly stale cached target according to the API contract.

### 2.1. Difference between dynamic linking and normal method calls

`dynamicInvoker()` creates a MethodHandle that has the same linking behavior as an `invokedynamic` instruction linked to the site. In a plain Java program, we can demonstrate relinking by calling `dynamicInvoker().invokeExact(...)` without needing to generate `invokedynamic` bytecode ourselves.

That **does not mean** every normal Java call goes through a call site. An `obj.method()` call in Java code does not automatically use your `MutableCallSite`. A framework, compiler, or runtime must **explicitly** link the call site to the site or use the dynamic invoker provided by the site.

### 2.2. Conceptual data flow

```text
Caller / invokedynamic
          |
          v
  dynamicInvoker()
          |
          v
  MutableCallSite ─────> target = MethodHandle V1
          |             ^
          |             |
          └─ setTarget(MethodHandle V2)
                        |
                        v
                 target = V2

Writer thread: setTarget(V2) -> [syncAll when publication is needed]
Reader thread: may still see V1 before synchronization guarantees are applied
```

This is a **semantic** diagram, not a rigid description of how the JIT generates machine instructions. The JVM may optimize, inline, or cache in ways that conform to the JMM.

## 3. Creating a MutableCallSite: an existing target or an uninitialized type

There are two constructors:

```java
// Illustrative snippet: target is a MethodHandle with type (int)String.
MutableCallSite ready = new MutableCallSite(target);

// Only has a type, not yet attached to a useful implementation.
MutableCallSite blank = new MutableCallSite(
        MethodType.methodType(String.class, int.class));
```

This is an excerpt in code that has already imported `java.lang.invoke.MethodHandle`, `MethodType`, `MutableCallSite` and has a corresponding `target` variable. Distinguish clearly:

- `new MutableCallSite(target)` immediately takes `target.type()` as the immutable type.
- `new MutableCallSite(type)` sets the site type to `type` and attaches a **special initial target that will throw `IllegalStateException` if invoked**. It does not automatically return `null` or a default value.
- `type == null` or `target == null` causes the corresponding constructor to throw `NullPointerException`.
- Before putting a blank site into an actual call path, one should normally `setTarget(...)` to a useful handle of the right type.

A call site is not an array whose type can be changed arbitrarily: once created as `(int)String`, it remains `(int)String` for the rest of its lifetime. If you need to change the signature, you must design an appropriate call site or adapter; you must not use `setTarget` to sneakily change the number of parameters.

## 4. `setTarget`: changing the binding without changing the signature

For example, a `(int)String` site currently points to:

```java
static String versionOne(int x) { return "ONE:" + x; }
static String versionTwo(int x) { return "TWO:" + x; }
```

The method snippets above are **illustrative** within a class. When two `MethodHandle`s point to two methods with the **same** `MethodType.methodType(String.class, int.class)`, they can take turns as the target of the same site.

Type invariance is checked **at `setTarget`**:

- `newTarget == null` -> `NullPointerException`.
- `newTarget.type()` does not equal `site.type()` -> `WrongMethodTypeException`.
- Target with the same type -> attached to the site; **there is no automatic type conversion** just because `invoke` can adapt types at the call site.

For example, `MethodHandles.constant(String.class, "hi")` has type `()String`, which is not the same as `(int)String`, so it cannot be directly substituted into a `(int)String` site. If you want to accept an additional `int` parameter and ignore it, you need to create an adapter:

```java
MethodHandle zeroArg = MethodHandles.constant(String.class, "hi");
MethodHandle compatible = MethodHandles.dropArguments(
        zeroArg, 0, int.class);
// compatible.type() == (int)String
site.setTarget(compatible);
```

This snippet is an excerpt, assuming `site` has type `(int)String`. Normalizing the type with `asType` or another combinator must be **intentional** and must match the business semantics.

## 5. `dynamicInvoker()` differs from storing `getTarget()` in a variable

The two approaches below are **not equivalent after the site is relinked**:

```java
MethodHandle followsSite = site.dynamicInvoker();
MethodHandle savedTarget = site.getTarget();
```

- `followsSite` is a **bridge through the call site**. At the API level, when invoked, it dispatches to the current target that the calling thread is allowed to observe.
- `savedTarget` is **the exact MethodHandle at the time of that `getTarget()` call**. If code keeps the `savedTarget` variable and calls it again after relinking, this variable does not automatically change to the new target.
- If you later call `site.getTarget()` again, the new read result is still subject to the ordinary-field memory semantics of `MutableCallSite`; whereas on the **same thread**, after `setTarget`, the newly written target is used according to program order.

This is the key difference between **dynamic binding** and a **snapshot of a handle reference**. If you want the caller to follow relinking, it must use `dynamicInvoker` or an `invokedynamic` linked to the site; do not keep holding onto an old `getTarget()` and expect it to be automatically updated.

### 5.1. Complete Java 17 example: relinking, type error, and blank site

Create the file **`MutableCallSiteBasicsDemo.java`**:

```java
import java.lang.invoke.*;

public class MutableCallSiteBasicsDemo {
    private static String one(int x) {
        return "ONE:" + x;
    }

    private static String two(int x) {
        return "TWO:" + x;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType type =
                MethodType.methodType(String.class, int.class);

        MethodHandle first = lookup.findStatic(
                MutableCallSiteBasicsDemo.class, "one", type);
        MethodHandle second = lookup.findStatic(
                MutableCallSiteBasicsDemo.class, "two", type);

        MutableCallSite site = new MutableCallSite(first);
        MethodHandle dynamic = site.dynamicInvoker();
        MethodHandle snapshot = site.getTarget();

        System.out.println("site type: " + site.type());
        System.out.println("before: "
                + (String) dynamic.invokeExact(3));

        site.setTarget(second);
        System.out.println("after same thread: "
                + (String) dynamic.invokeExact(3));
        System.out.println("saved handle: "
                + (String) snapshot.invokeExact(3));

        try {
            site.setTarget(
                    MethodHandles.constant(String.class, "bad"));
        } catch (WrongMethodTypeException expected) {
            System.out.println("wrong target type: rejected");
        }
        System.out.println("still target two: "
                + (String) dynamic.invokeExact(3));

        MutableCallSite blank = new MutableCallSite(type);
        MethodHandle blankInvoker = blank.dynamicInvoker();

        try {
            String ignored = (String) blankInvoker.invokeExact(1);
            System.out.println("unexpected: " + ignored);
        } catch (IllegalStateException expected) {
            System.out.println("blank initial target: uninitialized");
        }

        blank.setTarget(first);
        System.out.println("initialized blank: "
                + (String) blankInvoker.invokeExact(1));
    }
}
```

Compile and run commands (JDK 17+):

```bash
javac -encoding UTF-8 --release 17 MutableCallSiteBasicsDemo.java
java MutableCallSiteBasicsDemo
```

Exact stdout:

```text
site type: (int)String
before: ONE:3
after same thread: TWO:3
saved handle: ONE:3
wrong target type: rejected
still target two: TWO:3
blank initial target: uninitialized
initialized blank: ONE:1
```

**Explanation:**

1. The site's `type()` is `(int)String`; both methods have the same type so they are allowed to replace each other.
2. On the **same thread**, after `setTarget(second)`, the dynamic invoker calls `two` and returns `TWO:3`. This **does not prove** that another thread is guaranteed to see version two.
3. The variable `snapshot` holds the old target `one`, therefore it returns `ONE:3`; it no longer goes through the site.
4. The constant `()String` does not match the type `(int)String`, so `setTarget` throws `WrongMethodTypeException`. The last valid target remains `two`.
5. The blank site with `MethodType` has a special target that throws `IllegalStateException`. After setting `first` properly, the previously obtained dynamic invoker also works: `ONE:1`.

**Note:** `invokeExact` checks the signature at the call site. For example, receive `String` with `(String) dynamic.invokeExact(3)`, not `Object` or discarding the result altogether.

## 6. Cross-thread issue: `setTarget` is not a volatile write

According to the Java SE 17 Javadoc, the target field in `MutableCallSite` **behaves like an ordinary non-volatile field**. Therefore:

- Thread A calling `site.setTarget(newHandle)` **does not automatically force** a running thread B to recognize the new target immediately.
- Without appropriate synchronization involving the site, B may continue using the cached old target value, and may even **delay observing it indefinitely** according to the contract.
- B **may also see** the new target immediately after `setTarget`, before a `syncAll` call completes. That does not turn `setTarget` into a volatile write.
- Within a single thread, reading the target again after that same thread calls `setTarget` obeys program order; single-threaded examples usually produce the new result immediately.

### 6.1. Conceptual timeline example

```text
Time            Writer (A)                   Reader (B)
t0              target = V1                  calls V1
t1              setTarget(V2)                may still call V1
t2              ...                          may call V1 or V2
t3              syncAll([site]) starts       may still see V1 during synchronization
t4              syncAll completes            future target reads
                                             must obey the effect of syncAll
```

This is a timeline explaining **permitted outcomes**, not a mandatory ordering of every JDK. The JIT may optimize the target under appropriate assumptions, and `syncAll` helps the JVM perform the necessary operations so threads recognize the change.

**Do not conclude from a single run** that "on this machine `setTarget` is always visible immediately". Just because a reader happens to see V2 does not mean the program has a correct cross-thread contract.

### 6.2. Things that do not prove visibility

- `Thread.sleep(...)` or waiting a few milliseconds: the passage of time does not itself create a JMM guarantee.
- Using `System.out.println(...)` in a loop to observe: printing logs has synchronization and side effects, altering test behavior.
- Reading multiple times and seeing the new target: only tells you that **that particular attempt** had visibility, not that it is always true.
- Using a `volatile boolean published`, `CountDownLatch`, `join`, or lock to coordinate and then seeing V2: these mechanisms **themselves create synchronization/happens-before relationships**; you cannot isolate the effect of `syncAll` from that output.

Therefore, multithreaded examples should be designed to demonstrate how to use the API **with synchronization and verifiable output**, rather than trying to create a machine-dependent "race test" to prove a stale value.

## 7. `MutableCallSite.syncAll(...)`: publishing a new target to threads

Signature:

```java
MutableCallSite.syncAll(new MutableCallSite[]{site});
```

It performs synchronization on **each site in the array**, forcing other threads to discard stale cached targets according to the constraints of the Java Memory Model. According to the API contract, future target reads must accept the most recently stored value **relative to that `syncAll` call** (or a later update).

### 7.1. Correct order: set target then sync

If you want to publish a relink:

```java
site.setTarget(newTarget);
MutableCallSite.syncAll(new MutableCallSite[]{site});
```

This is an illustrative snippet, assuming `site` is a valid `MutableCallSite` and `newTarget` has the exact `site.type()`. You must set first because `syncAll` publishes updates **that occurred before it**; calling sync first and then set does not guarantee that the target set afterward is published.

If changing **a group of sites**, the API allows batching:

```java
synchronized (relinkLock) {
    first.setTarget(nextFirst);
    second.setTarget(nextSecond);
    MutableCallSite.syncAll(new MutableCallSite[]{first, second});
}
```

This is an excerpt within a class that has the corresponding variables `relinkLock`, `first`, `second`, `nextFirst`, `nextSecond`. With multiple writers, the Javadoc recommends using appropriate **mutual exclusion** to prevent `setTarget` and `syncAll` from interleaving and causing races. A lock can be used on the **writer** path. Normal readers do not need to acquire this lock just to call the dynamic invoker.

### 7.2. What does syncAll guarantee and not guarantee?

**Guarantees/purpose according to the contract:**

- Forces threads using the site to eventually discard old cached target values; the effect can be modeled similarly to a volatile write and appropriate volatile reads.
- Refers to the latest update **prior to** the `syncAll` call in question, within a controlled relinking protocol.
- Applies to **an array of multiple sites**, convenient for batch updates.

**Does not guarantee:**

- **Does not roll back** or cancel calls that have already started running on the old target.
- Does not require B to always call V1 until sync finishes; B may see V2 **early**.
- Does not automatically turn updating multiple sites into **an atomic transaction**. A reader may observe some sites already updated and some sites still old, especially during the interval when the writer is updating each site one by one.
- Does not fix data bugs or provide an atomic protocol for **all other application state**. If the new target depends on other fields/configs, their publication and consistency must be designed separately.
- Does not guarantee the operation is **cheap**: `syncAll` may require the JVM to coordinate/invalidate JIT caches across threads and **may block** until processing finishes.

### 7.3. Cost characteristics and invalid parameters

The Javadoc emphasizes that `syncAll` can be expensive, so **use it sparingly and batch when possible**, especially if the runtime has many call sites that need to be relinked in the same wave.

If the passed array is `null` or contains a `null` element, the API throws `NullPointerException`. With an array containing null, some valid sites may have already been processed **before the exception is thrown**; the set of processed sites is implementation-dependent. Do not pass an invalid array and expect an "all-or-nothing" operation.

An implementation may store the target using volatile and make `syncAll` practically very lightweight/no-op while still conforming to the contract. **Do not** rely on HotSpot details or a specific JDK version as a reason to omit sync in code that requires cross-thread compatibility.

## 8. Multithreaded Java 17 example: publishing then observing with coordination

This is a **deterministic demonstration** program: the worker reads OLD, waits; the writer changes the target to NEW and calls `syncAll`; the worker continues and reads NEW. We use `CountDownLatch` to control timing and avoid races affecting stdout.

Create the file **`MutableCallSiteThreadDemo.java`**:

```java
import java.lang.invoke.*;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicReference;

public class MutableCallSiteThreadDemo {
    public static void main(String[] args) throws Throwable {
        MutableCallSite site = new MutableCallSite(
                MethodHandles.constant(String.class, "OLD"));
        MethodHandle dynamic = site.dynamicInvoker();

        CountDownLatch firstRead = new CountDownLatch(1);
        CountDownLatch continueRead = new CountDownLatch(1);
        AtomicReference<String> before = new AtomicReference<>();
        AtomicReference<String> after = new AtomicReference<>();
        AtomicReference<Throwable> failure = new AtomicReference<>();

        Thread reader = new Thread(() -> {
            try {
                before.set((String) dynamic.invokeExact());
                firstRead.countDown();
                continueRead.await();
                after.set((String) dynamic.invokeExact());
            } catch (Throwable e) {
                failure.set(e);
                firstRead.countDown();
            }
        }, "reader");

        reader.start();
        firstRead.await();

        site.setTarget(MethodHandles.constant(String.class, "NEW"));
        MutableCallSite.syncAll(new MutableCallSite[]{site});

        continueRead.countDown();
        reader.join();

        if (failure.get() != null) {
            throw new AssertionError(failure.get());
        }

        System.out.println("reader before: " + before.get());
        System.out.println("reader after syncAll: " + after.get());
        System.out.println("call site type: " + site.type());
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 MutableCallSiteThreadDemo.java
java MutableCallSiteThreadDemo
```

Stdout:

```text
reader before: OLD
reader after syncAll: NEW
call site type: ()String
```

**Careful analysis of correctness:**

1. The reader is allowed to perform the first call before the writer sets the target because the writer waits on `firstRead.await()`. Thus the first call returns OLD.
2. The writer sets NEW, then calls `syncAll`, and only then releases `continueRead`. The second read occurs after the synchronization point; the result is NEW.
3. `dynamicInvoker` was created before the target changed, yet it still dispatches through the site to pick up the current version according to the applicable memory semantics.
4. **Limitation of the demo:** `CountDownLatch` and `AtomicReference` both have their own synchronization rules. Therefore, the program demonstrates a valid protocol and produces stable output, **it cannot be used as empirical proof that omitting `syncAll` would cause the thread to observe OLD**. The absence of `syncAll` in another program must be analyzed using the JMM, not based on how many times a test passes.
5. Calling `reader.join()` only makes the main program wait for the thread to finish and read the result; `join` does not make the target visible in a loop **that was already running earlier** without an appropriate protocol.

In production, delaying readers to guarantee a read after sync may not suit throughput requirements. You need to decide the **consistency requirement**: whether updates can become visible after a relink batch, or whether readers need to observe each change immediately.

## 9. Comparison with ConstantCallSite and VolatileCallSite

### 9.1. ConstantCallSite

`ConstantCallSite` is linked once and keeps a fixed target. There is no `syncAll` because no target updates are permitted. `setTarget(...)` cannot be used to relink; if you need to change logic at runtime, choose a different site type from the design phase.

Appropriate when bootstrap has already computed the final implementation, subsequent changes are unnecessary, and the JVM has the opportunity to optimize the stable binding.

### 9.2. VolatileCallSite

`VolatileCallSite` stores the target like a **volatile field**:

- `setTarget` has the effect of a **volatile write**.
- `getTarget` has the effect of a **volatile read**; a thread cannot indefinitely hold an old target when performing reads after an update according to synchronization order rules.
- `dynamicInvoker` / `invokedynamic` instructions linked to the site also follow the corresponding target visibility semantics.
- **There is no `VolatileCallSite.syncAll`**; each site update already carries volatile guarantees.
- In return, it can be **more expensive on frequent reads/calls** compared to MutableCallSite, because the coupling between threads is tighter.

Volatile does not mean that all in-flight calls are cancelled or that all reader results must appear in a completely fixed total order; it is a memory visibility / happens-before contract for the target.

### 9.3. Decision table

| Question | ConstantCallSite | MutableCallSite | VolatileCallSite |
| --- | --- | --- | --- |
| Can it be relinked? | No | Yes | Yes |
| Target field semantics | Immutable | Ordinary (non-volatile) | Volatile |
| When changing target, is `syncAll` needed for equivalent guarantees? | Not applicable | Normally **yes** if you want to publish to other threads without alternative synchronization | No |
| Target read cost | Can be optimized very well | Suitable when updates are rare or batched | May add read synchronization cost |
| Application model | Fixed bootstrap result | Batched hot relinking | Each update needs visibility with volatile semantics |

**This is not advice to "always use Mutable for performance".** Choose the call site type based on visibility requirements and update frequency; only benchmark after correctness is ensured.

## 10. Java 17 Example: three site types with the same signature

Create the file **`CallSiteChoiceDemo.java`**:

```java
import java.lang.invoke.*;

public class CallSiteChoiceDemo {
    public static void main(String[] args) throws Throwable {
        MethodHandle one = MethodHandles.constant(int.class, 1);
        MethodHandle two = MethodHandles.constant(int.class, 2);

        ConstantCallSite fixed = new ConstantCallSite(one);
        MutableCallSite mutable = new MutableCallSite(one);
        VolatileCallSite volatileSite = new VolatileCallSite(one);

        MethodHandle fixedInvoker = fixed.dynamicInvoker();
        MethodHandle mutableInvoker = mutable.dynamicInvoker();
        MethodHandle volatileInvoker = volatileSite.dynamicInvoker();

        System.out.println("before: "
                + (int) fixedInvoker.invokeExact()
                + "," + (int) mutableInvoker.invokeExact()
                + "," + (int) volatileInvoker.invokeExact());

        mutable.setTarget(two);
        MutableCallSite.syncAll(new MutableCallSite[]{mutable});
        volatileSite.setTarget(two);

        System.out.println("after: "
                + (int) fixedInvoker.invokeExact()
                + "," + (int) mutableInvoker.invokeExact()
                + "," + (int) volatileInvoker.invokeExact());
    }
}
```

Run:

```bash
javac -encoding UTF-8 --release 17 CallSiteChoiceDemo.java
java CallSiteChoiceDemo
```

Stdout:

```text
before: 1,1,1
after: 1,2,2
```

This example **runs on a single thread** to have stable output. It illustrates the same `()int` type with three different target policies: constant stays 1, mutable after relinking is 2, volatile after relinking is 2. **Do not** use single-threaded output to infer that `VolatileCallSite` and `MutableCallSite` are identical in cross-thread visibility.

## 11. Why syncAll does not turn multiple targets into a transaction

Suppose an application has two sites `calculatePrice` and `calculateTax` that must switch together to policy set V2. The writer performs:

```java
synchronized (updateLock) {
    calculatePrice.setTarget(priceV2);
    calculateTax.setTarget(taxV2);
    MutableCallSite.syncAll(new MutableCallSite[]{
            calculatePrice, calculateTax
    });
}
```

This is **illustrative code**, with `updateLock` and the two sites/handles already created, having the same type as each site's previous target.

The guarantee that `syncAll` applies to **each site** does not mean readers see both sites change at the exact same instant. While the writer is calling `setTarget` on each site one by one, a reader may pick target V2 at the price site and V1 at the tax site. The writer lock does not automatically protect readers if readers do not use the same lock.

If the business logic requires an **atomic snapshot of the entire policy set**, design a **single publication point**: for example, replace one coordinating site to a handle pointing to an **immutable** configuration object containing all of price/tax V2, or use an atomic/volatile reference to a completed policy snapshot. Group atomicity cannot be inferred merely from a `syncAll(new MutableCallSite[]{...})`.

At the same time, if multiple writers can relink the same site, you need to serialize `setTarget` and `syncAll`, managing versions or policy ordering; if writer B interleaves between A's set and sync, the "latest value" might no longer correspond to the version A intended to publish.

## 12. Performance and relinking architecture

### 12.1. Why can syncAll be expensive?

The Javadoc notes that the operation may have to wait for threads using the site to discard old cached target versions. On some JVMs, this involves JIT optimizations and deoptimization/handshakes or other internal mechanisms, though one **should not assume** fixed implementation details.

A program that calls `syncAll` on every request while the target is constantly changing may lose the optimization benefits of MutableCallSite. Options:

- **Batch multiple sites** if updating in the same wave; avoid a separate sync call for each site when unnecessary.
- **Relink when configuration changes**, not during normal data reads.
- If updates are very frequent and require volatile visibility, consider **`VolatileCallSite`**.
- If most call sites do not change after bootstrap, use **`ConstantCallSite`** where appropriate.
- If you need to change **data** rather than **implementation**, consider a fixed MethodHandle that reads from a `volatile`/atomic reference configuration instead of continuously replacing the target.
- Measure with stable benchmarks, including throughput, tail latency, and the cost of both **writer relinking** and **reader dispatch**, not just the nanoseconds of a single invoke.

### 12.2. When the target has side effects

Changing the target only changes **the implementation chosen for subsequent calls**. It does not cancel work already running on the old target. A V1 method currently writing to a database can still complete after V2 has been published. If the logic requires the entire transaction to use the same version, you should:

- Attach the version to the request/context;
- Pin the handler/snapshot at the start of the transaction;
- Define a graceful drain or handoff protocol;
- Avoid assuming `syncAll` is a "stop-the-world rollback" of V1 calls.

**The visibility boundary of the target** and **the business consistency constraint of the entire request** are two different problems.

## 13. Linking lifecycle with invokedynamic

An `invokedynamic` bootstrap method can return a `CallSite` whose `type()` matches the descriptor of the call site. If the bootstrap chooses `MutableCallSite`, invocations linked through the site can use the new target after relinking according to the semantics just learned.

**Conceptual illustrative** snippet, not a standalone program that generates bytecode itself:

```java
// Suppose caller, name, type are parameters from bootstrap
// and chooseInitialTarget(...) returns an appropriate MethodHandle.
MethodHandle initial = chooseInitialTarget(caller, name, type);
MutableCallSite site = new MutableCallSite(
        initial.asType(type));
return site; // return value of the bootstrap method
```

When the runtime later wants to switch implementations, it needs to retain a reference to `site` and call `site.setTarget(nextTarget)` with the same `type`, then publish with `syncAll` if cross-thread guarantees are needed.

In the runnable Java examples of this lesson, we use `site.dynamicInvoker()` as an equivalent path to observe relinking. This is a suitable choice for **learning the API without having to manually compile or emit invokedynamic bytecode**. Do not confuse creating a `MutableCallSite` in a Java class with every invocation in the class automatically going through the site.

## 14. Common mistakes and fixes

| Mistake/misconception | Why it is wrong | How to handle |
| --- | --- | --- |
| Assuming `setTarget` is a volatile write | MutableCallSite has ordinary-field target semantics. | If cross-thread publication is needed, use `syncAll` or proper synchronization, or choose `VolatileCallSite`. |
| Testing and seeing the reader receive V2 after sleeping, then concluding it is always right | Elapsed time / test conditions do not establish a JMM contract. | Analyze happens-before, do not rely on accidental observation. |
| Keeping `MethodHandle cached = site.getTarget()` and expecting `cached` to follow relinking | The `cached` variable holds a specific old target. | Use `site.dynamicInvoker()` to dispatch through the site. |
| Passing a handle with a different type to `setTarget` | `site.type()` is immutable. | Normalize with `asType`/adapters and check `type().equals(...)`. |
| Creating `MutableCallSite(MethodType)` and calling it immediately | The initial target is designed to throw `IllegalStateException`. | Attach a useful target before publishing the site. |
| Treating `syncAll` as an atomic commit of multiple sites | It synchronizes each site; readers may see a mixture. | Use a single snapshot/publication point when group consistency is needed. |
| Assuming `syncAll` cancels already-running V1 calls | It cannot roll back old executions. | Structure versioning, draining, or transaction boundaries. |
| Calling `syncAll` before `setTarget` and expecting the later target to be published | Sync publishes updates relative to the time of the sync. | Set first, sync later, and coordinate writers. |
| Using `syncAll` on every request when the target changes very rapidly | Can cause high overhead. | Batch or consider `VolatileCallSite`. |
| Reading `VolatileCallSite.getTarget()` as an ordinary field | Volatile site has volatile semantics. | Choose the site type matching visibility requirements. |
| Turning a target into `()String` for a `(int)String` site | Different type => `WrongMethodTypeException`. | Add dummy parameters with `dropArguments` if semantics allow. |
| Passing `null` to `syncAll` or containing a null element | NPE; some sites may have been processed before the error. | Validate the site array before calling. |

### 14.1. JMM errors are not type errors

`WrongMethodTypeException` in `setTarget` reports that the new handle **does not match the type**. It is unrelated to whether target V2 is observed by other threads.

Conversely, a program where **all handles have the right signatures** can still have concurrency bugs due to missing publication. A correct solution needs to satisfy both contracts simultaneously: *MethodType invariant* and *memory visibility*.

## 15. Testing and quality criteria

### 15.1. Single-threaded testing

- Create a site with handle V1 and store the dynamic invoker.
- Invoke successfully; after `setTarget(V2)`, invoke V2 successfully.
- Keep a `getTarget()` snapshot before relinking and verify it still calls V1.
- Try a handle with the wrong `MethodType`, catching `WrongMethodTypeException`.
- Create a blank site, verify the initial target throws `IllegalStateException`; after attaching a target, verify it works.
- Check that `site.type()` always remains unchanged.

These are **stable** assertions that do not need a scheduler or sleep.

### 15.2. Multithreaded testing

- Use a latch/barrier to govern when the worker is allowed to read; **clearly note** that these primitives themselves introduce additional synchronization.
- After `setTarget` + `syncAll`, allow the worker to perform the next read and verify the appropriate result.
- Use thread exception capture and check `join`/timeout; do not let tests pass falsely just because a background thread died.
- Do not write unit tests expecting "the reader must see OLD if `syncAll` is omitted": the JMM **allows the reader to see NEW early**.
- If consistency across multiple sites is required, write separate tests for the snapshot/version protocol rather than testing `syncAll` as a transaction.

### 15.3. Testing the relink capacity of a real system

In a production-like benchmark, observe the number of `syncAll` calls per second, writer blocked time, relink rate, tail latency of calling threads, and the distribution of V1/V2 versions around the switch point. For targets with side effects, add a version trace to logs/metrics to know which execution started with which implementation. **Do not conclude correctness from benchmarks**; correctness must be based on the JMM + API contract.

## 16. Self-check questions

**1. Why does calling `dynamicInvoker()` after `setTarget(V2)` on the same thread usually return V2, whereas on another thread you cannot assert that solely from `setTarget`?**

Because the writing thread obeys program order; whereas the target of `MutableCallSite` has ordinary-field semantics, so without synchronization another thread may continue using a stale cached V1.

**2. Why does `site.getTarget()` stored in a variable not change with `setTarget`, while `site.dynamicInvoker()` still tracks the site?**

`getTarget` returns the exact MethodHandle observed at that read; the variable holds the old reference. Dynamic invoker is a handle that dispatches through the site on each call according to the call site's semantics.

**3. Does `setTarget` accept a MethodHandle with the same return type but a different number of parameters?**

No. `newTarget.type()` must **completely equal** `site.type()`, otherwise `WrongMethodTypeException` is thrown. An explicit adapter can be created if business logic permits.

**4. Does `syncAll` guarantee that calls already started on V1 stop and switch to V2?**

No. It affects the visibility of the target in subsequent reads, not reversing invocations already running on the old handle.

**5. Why is `syncAll(new MutableCallSite[]{a,b})` not enough to atomically replace a two-site policy set?**

Because the writer replaces each target one by one and readers can observe an interleaved state; `syncAll` synchronizes each site's target, not creating an atomic transaction for the entire policy set.

**6. When should `VolatileCallSite` be chosen?**

When the target may update frequently and the application needs volatile-like visibility for each change, instead of coordinating `MutableCallSite.syncAll` in batches. One must accept and measure the corresponding read/write cost.

**7. Does running the multithreaded demo with `CountDownLatch` and seeing V2 prove that `syncAll` alone created the visibility?**

No. `CountDownLatch` also provides synchronization/happens-before. The demo illustrates proper coordination and stable output; reasoning about `syncAll`'s guarantees must rely on the Javadoc/JMM.

## 17. Key takeaways

- **`MutableCallSite` allows relinking the `MethodHandle` target**, while `site.type()` is immutable.
- **`setTarget` is only an ordinary-field write for cross-thread purposes**, not automatically forcing readers on other threads to see the new target immediately.
- **`dynamicInvoker()` dispatches through the site**, unlike holding a snapshot from `getTarget()`.
- **`syncAll(new MutableCallSite[]{...})` is used to publish updates to threads**, which can be expensive; place it after `setTarget` and coordinate multiple writers.
- **Readers may see the new target early**, but calls already started on the old target are not revoked; a group of multiple sites does not automatically have atomicity.
- **`VolatileCallSite`** uses volatile semantics for the target and has no `syncAll`; **`ConstantCallSite`** is a fixed binding.
- **Testing JMM behavior must be based on the contract**, not concluded from sleep/log/timing or a test happening to pass once.

### Official Java SE 17 Documentation

- [`MutableCallSite`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MutableCallSite.html) — constructors, `getTarget`, `setTarget`, `dynamicInvoker`, `syncAll`, the *Non-synchronization of target values* and *Java Memory Model details* sections.
- [`CallSite`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/CallSite.html) — immutable type, target and dynamic invoker, the three subclasses.
- [`VolatileCallSite`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VolatileCallSite.html) — volatile read/write semantics and differences from MutableCallSite.
- [`MethodHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html) and [`MethodType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html) — signature rules for targets and invocations.
