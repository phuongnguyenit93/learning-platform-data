# 12.8. Inline Cache at the Call Site, Receiver Type Guarding, and the Relink Branch

## Learning Objectives

After this lesson, you can:

1. Explain the meaning of **call site**, `CallSite.getTarget()`, `CallSite.dynamicInvoker()`, and why updating the target avoids performing a full lookup on every dynamic call.
2. Distinguish **monomorphic inline cache**, **polymorphic inline cache (PIC)**, and the **megamorphic** case; know why the number of guards needs to be bounded.
3. Create a **receiver type check** using `receiver.getClass() == expectedClass` and `MethodHandles.guardWithTest(...)`.
4. Design a **fallback/relink branch**: cache miss → find `MethodHandle` for the new receiver type → convert to the common `MethodType` → attach guard → update `MutableCallSite.setTarget(...)` → invoke the newly found target.
5. Understand that **a CallSite's target has a fixed type** even when the selected method changes; distinguish `asType`, `invokeExact`, and `WrongMethodTypeException`.
6. Handle `null`, non-existent methods, access permissions, class loaders, invalidation, and concurrency; understand the roles of `MutableCallSite.syncAll(...)`, `VolatileCallSite`, and `SwitchPoint`.
7. Run a Java 17+ example with a cache of up to three receiver classes, observe hits/misses, and avoid confusing a cache hit with a guarantee that the JIT has optimized it.

**Context:** In dynamic languages running on the JVM, an expression like `receiver.speak()` can receive many different object types at the same location in code. A naive implementation would look up the matching method again on every call. An **inline cache** remembers previously seen types and their corresponding call paths right at the **call site** to speed up the hot path. `CallSite`, `MethodHandle`, and `guardWithTest` allow modeling how this works using Java APIs.

## 1. What is a call site and what does it hold?

`java.lang.invoke.CallSite` is an object that stores a **target `MethodHandle`**. The target is the behavior that will be invoked at that call site.

- `site.type()` returns the **fixed `MethodType`** of the call site.
- `site.getTarget()` returns the currently linked target according to the semantics of the `CallSite` class.
- `site.dynamicInvoker()` creates a handle whose behavior invokes the site's current target; it **does not simply freeze the initial target** for a mutable site.
- `site.setTarget(newTarget)` changes the target if the site kind allows it and `newTarget.type()` **equals** `site.type()` **exactly**.

Three important variants:

| Kind | Can target be changed? | Key points to remember |
| --- | --- | --- |
| `ConstantCallSite` | No | The target is permanently linked; suitable for calls that do not need relinking. |
| `MutableCallSite` | Yes | Target updates have the semantics of an ordinary variable; publishing changes properly to other threads requires designing synchronization, usually using `syncAll`. |
| `VolatileCallSite` | Yes | Target updates have volatile semantics, suitable when changes need to be visible across multiple threads under the volatile contract. |

At the JVM level, an `invokedynamic` instruction is linked to a `CallSite`. However, in a pure Java program, we can also **instantiate a site directly and invoke `dynamicInvoker()`** to simulate relinking behavior. The complete example in section 7 **does not emit `invokedynamic` bytecode for the sample calls**; it illustrates the exact mechanism of building and updating targets.

### 1.1. The target type is kept fixed

Suppose a call site has the contract:

```text
(Object receiver)String
```

It accepts a receiver at compile time of type `Object` and returns `String`. From then on, whether the actual receiver is `Dog`, `Cat`, or `Bird`, the site's target **must still have type `(Object)String`**.

This differs from targets looked up at runtime:
- `findVirtual(Dog.class, "speak", ()String)` yields a handle of type `(Dog)String`.
- `findVirtual(Cat.class, "speak", ()String)` yields a handle of type `(Cat)String`.

These two handles cannot be placed directly into an `(Object)String` site. They must be **adapted** to the same site type using `asType(MethodType.methodType(String.class, Object.class))`. When adapting a `(Dog)String` handle to `(Object)String`, the adapter will require a receiver compatible with `Dog` at runtime.

**Key invariant:** Relinking changes the **execution path**, not the signature of the call site. `CallSite.setTarget` rejects a target with the wrong `MethodType` by throwing `WrongMethodTypeException`.

## 2. Inline cache at the call site (*inline cache*)

An inline cache is a form of memoization **right at a specific call site**, usually based on the type or shape (*shape*) of the receiver. Instead of repeating a full lookup:

```text
Every call (without cache)
    receiver -> get type/shape -> look up method -> create adapter -> invoke target
```

We can use:

```text
First time:
    receiver -> CACHE MISS
             -> resolve target for the new type
             -> install a type guard and the resolved target
             -> invoke target

Next time with the same type:
    receiver -> GUARD MATCHES -> invoke cached target (CACHE HIT)

When receiver has a different type:
    receiver -> GUARD FAILS -> FALLBACK -> resolve/relink
```

The key point: **multiple call sites** in the same method can observe different receiver distributions. For example, a call site inside a loop processing `Dog` 99% of the time can cache `Dog` on its own, without being affected by a call site elsewhere in the code that mainly invokes `Cat`.

Comparison with a global cache:
- **Per-site inline cache:** optimizes for behavior at the call site; can help the JIT see paths that frequently go through stable guards.
- **Global lookup cache:** shares method resolution data across multiple call sites; can reduce resolution cost but does not itself replace each site's guards/dispatch branches.
- The two layers can be **combined**. A per-site PIC can point to handles cached by class in a shared table.

### 2.1. Monomorphic, polymorphic, megamorphic

| State | Receivers seen at site | Typical structure |
| --- | --- | --- |
| **Monomorphic** | One dominant class | One guard `receiver.class == Dog`, one fast target, one miss fallback |
| **Polymorphic (PIC)** | A small number of common classes | A short chain `guard(Dog) → guard(Cat) → guard(Bird) → fallback` |
| **Megamorphic** | Very many classes/shapes | Usually needs a generic dispatch path, a cache table, or another optimized lookup instead of growing the guard chain indefinitely |

There is no fixed threshold that applies to every runtime. The example in section 7 chooses **at most three guards** for easy observation; that is a demo decision, not a threshold mandated by the JVM/JDK.

Creating a guard for every class ever seen can cause:
- an increasingly long chain of checks;
- a growing number of `MethodHandle` instances and metadata;
- harder JIT optimization and higher memory consumption;
- holding references to `Class`/class loaders longer than necessary.

Therefore, a PIC is usually **bounded**, and when saturated it can use a generic fallback or a global megamorphic cache.

## 3. Guard: checking the receiver type before entering the fast path

### 3.1. Exact-class check predicate

A minimal predicate:

```java
static boolean isExactClass(Class<?> expected, Object receiver) {
    return receiver != null && receiver.getClass() == expected;
}
```

This is an illustrative method in a Java class. It returns `true` only when the receiver is non-`null` and its runtime class is **exactly** `expected`.

Why use `==` between two `Class<?>` objects?
- `Class` represents the true **class identity** of the JVM, including the class loader context. Comparing string names with `getName().equals(...)` can confuse two classes defined by two different loaders.
- If you want to cache the result of a method lookup specifically for one class, an exact-class guard ensures the resolved adapter receives the exact checked receiver.
- The predicate does not throw `NullPointerException` for `null`; null will go to the fallback to be handled according to an explicit policy.

### 3.2. Exact class vs. `instanceof`

With `receiver instanceof Dog`, a subclass of `Dog` also passes the guard. This approach **can be valid** if the resolved target is truly compatible and the dispatch contract allows using the same adapter, such as a virtual method inherited/overridden according to standard Java rules.

However, in a dynamic runtime, a subclass may have a different method resolution due to overloads, extensions, monkey patching, property lookup, or its own descriptor. An exact-class guard is the **safe and easy-to-prove** choice for the demo: one cached target for one exact type.

**Warning:** Checking the receiver type **does not replace** other protocol conditions. If dispatch also depends on a plugin version, runtime configuration, access permissions, or schema, guarding only on the class can lead to a **stale** cache. In that case, version/invalidation guards must be added.

### 3.3. MethodHandles.guardWithTest

API:

```java
MethodHandle branch = MethodHandles.guardWithTest(
        test, fastTarget, fallback);
```

This snippet only illustrates the call structure; the three variables must be `MethodHandle`s with compatible types.

When `branch` is invoked:
1. Run `test(receiver)`.
2. If `true`, run `fastTarget(receiver)`.
3. If `false`, run `fallback(receiver)`.

To be compatible:
- `test` in the demo has type `(Object)boolean`.
- `fastTarget` has type `(Object)String`.
- `fallback` has type `(Object)String`.

According to the API, the guard can take fewer parameters than target/fallback, but it **must** return `boolean`. If target/fallback have mismatching `MethodType`s, or the test is incompatible, `guardWithTest` throws `IllegalArgumentException` immediately when creating the adapter.

### 3.4. Binding the class to compare using insertArguments

In its original form, `isExactClass(Class<?> expected,Object receiver)` takes **two parameters**, giving a handle of type `(Class,Object)boolean`. We can bind `expected` to the resolved class:

```java
MethodHandle test = MethodHandles.insertArguments(
        IS_EXACT_CLASS, 0, actualClass);
// Remaining test type: (Object)boolean.
```

This is an illustrative snippet assuming `IS_EXACT_CLASS` and `actualClass` already exist. `insertArguments` **pre-binds** the first parameter at position `0`, making the new handle only need the receiver. It does not mutate the original handle and does not perform a new lookup on every test.

Combining:
- exact-class guard;
- target adapted to `(Object)String`;
- fallback still `(Object)String`.

When the receiver class matches, the fast path **does not re-run the relink branch**.

## 4. How does the relink branch (*relink fallback*) work?

The fallback is invoked when there is no matching guard yet, or when the cached path is no longer valid.

A simple PIC diagram:

```text
site.target = guard(Bird, invokeBird,
                guard(Cat, invokeCat,
                  guard(Dog, invokeDog,
                    relinkFallback)))

Call(receiver):
    if class(receiver) == Bird -> invokeBird
    else if class(receiver) == Cat -> invokeCat
    else if class(receiver) == Dog -> invokeDog
    else -> relinkFallback(receiver)
```

**Path on a miss:**

1. Receive the receiver.
2. Check `null` and the call site's preconditions.
3. Get `receiver.getClass()`; if dispatch is complex, runtime shape/version may also be needed.
4. Resolve target: for example `Lookup.findVirtual(actualClass,"speak", MethodType.methodType(String.class))`.
5. Convert the newly found handle to `site.type()` using `asType(...)`.
6. Build the exact-class predicate, then create a new adapter:
   `guardWithTest(test, newDirectHandle, oldTarget)`.
7. If the cache is not saturated and policy allows, replace `site.setTarget(newChain)`.
8. Publish the update across threads according to the call site kind's semantics, e.g. `MutableCallSite.syncAll(...)`.
9. **Invoke the newly found target** for this very miss, then return the result normally.

Why does step 9 invoke the target directly instead of calling `dynamicInvoker` again? Because the target has already been resolved for the current receiver. Calling back through the entire chain without care could cause repeated relinks, double invocation, or unnecessary recursion. The demo code uses `direct.invokeExact(receiver)` right after linking.

### 4.1. Do not change the CallSite's type when relinking

Example `(Object)String` site:
- Look up the Dog method `(Dog)String`.
- Adapt to `(Object)String`.
- The class-bound guard has type `(Object)boolean`.
- `guardWithTest` produces `(Object)String`.
- `setTarget` accepts it.

If you forget `asType` and pass `(Dog)String` directly to `setTarget`, the update is rejected with `WrongMethodTypeException`. `CallSite` keeps its type fixed even when the target changes many times.

### 4.2. Why keep the fallback at the end?

If you only install a target for `Dog` with no fallback, when encountering `Cat` it could:
- throw `ClassCastException` from the adapter;
- or invoke the wrong logic;
- or have nowhere to resolve the new method.

A `guardWithTest` branch must lead to a **contract-compliant fallback**, rather than assuming the receiver will never change type. Even after the PIC reaches its limit, the fallback must handle uncached classes if the application's goal requires supporting them.

### 4.3. Avoiding caching the wrong class on concurrent misses

In a multithreaded system, two threads can miss at the same time with different classes. If each thread does `getTarget → guardWithTest → setTarget` without coordination, one thread's update can overwrite the branch just added by the other (*lost relink*).

The demo pattern places the **cache check and target update** inside `synchronized(site)`. This serializes writers relinking the same site. In addition, an appropriate visibility mechanism must be used for readers, because the writer's lock **does not automatically guarantee** that threads only invoking the target without acquiring that lock will see changes in a `MutableCallSite`.

## 5. Call-site caching: hit and miss costs

### 5.1. Cache hit

With a cached `Dog` receiver:
- Check one or a few guards.
- Jump to the resolved adapter handle.
- Do not call `Lookup.findVirtual` and do not change the target.

A cache hit is usually cheaper than a full resolution. If a call site is stable, the JVM/JIT **can** optimize the frequently executed path, but there is no guarantee that every call site will be inlined by the JIT.

### 5.2. Cache miss

A miss may have to:
- check multiple guards;
- get class/shape;
- check permissions/method;
- create/adapt a handle;
- allocate a new guard node;
- update/publish the callsite target;
- and finally invoke the target method.

Therefore, **a miss is more expensive than a hit**. Putting `syncAll` on every call or relinking unnecessarily defeats the optimization goal. You should only relink when there is actually a new target to cache and policy permits it.

### 5.3. Bounded Polymorphic Inline Cache (PIC)

The demo uses a limit of 3 classes:
- `Dog`, `Cat`, `Bird`: cached.
- `Fox`: still dispatches correctly through the fallback, but **does not add a fourth guard**.
- `Fox` is called again: goes to the fallback again, because we intentionally do not cache it.

This models the **generic path** after PIC saturation, not the ultimate optimal megamorphic algorithm. In production, a lookup table cached by `Class`, `ClassValue`, or another dispatch structure can be used to avoid expensive lookups when rare types appear repeatedly.

### 5.4. Do not equate miss count with distinct receiver count

An uncached receiver class can generate **many misses**, especially once the PIC limit is exceeded. Conversely, many different objects of the same class can all hit a single guard. Therefore, miss statistics must be interpreted in terms of the **call site**, **class distribution**, and **cache policy**.

## 6. Minimal API and mandatory type rules

| API | Purpose | Rules to follow |
| --- | --- | --- |
| `new MutableCallSite(MethodType)` | Create a site with a fixed signature | The initial target is only a placeholder; a usable target must be installed before invocation |
| `site.dynamicInvoker()` | Invoke following the current target | The invoker's type equals `site.type()` |
| `site.getTarget()` | Get the chain currently in use | With MutableCallSite, other threads may need sync to see the new target |
| `site.setTarget(handle)` | Update the execution path | `handle.type().equals(site.type())` is mandatory |
| `MutableCallSite.syncAll(sites)` | Synchronize target updates | Cost can be significant; do not call on the hot path on every invocation |
| `Lookup.findVirtual(...)` | Resolve the target method for the runtime class | Needs the right name, signature, and access permissions |
| `handle.asType(site.type())` | Adapt argument/return types | Only supports valid conversions; may perform runtime checks/casts |
| `MethodHandles.insertArguments(...)` | Bind the expected receiver class for the test | The result has fewer parameters, at the bound positions |
| `MethodHandles.guardWithTest(...)` | Combine fast path and fallback | Predicate returns boolean; target/fallback have the same method type |

Do not confuse:
- **`MethodType`** is a signature, not something that executes a method by itself.
- **`MethodHandle`** is an executable object representing a call path.
- **`CallSite`** holds a mutable or fixed target handle.
- **Inline cache** is a **strategy** for building a guard/target/fallback structure around a call site, not a built-in Java subtype named `InlineCache`.

## 7. Complete Java 17+ Example: PIC with receiver guard and relink fallback

The file **`InlineCacheDemo.java`** below has four different receiver classes, each declaring `public String speak()`. `Cache` is a `MutableCallSite` of type `(Object)String`. A fallback resolves using `findVirtual`, builds a guard based on **exact runtime class**, and updates the target if fewer than three classes are cached.

**Standalone runnable source code:**

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.MutableCallSite;
import java.util.LinkedHashSet;
import java.util.Objects;
import java.util.Set;

public class InlineCacheDemo {
    private static final MethodHandles.Lookup LOOKUP = MethodHandles.lookup();
    private static final MethodType SITE_TYPE =
            MethodType.methodType(String.class, Object.class);
    private static final int MAX_GUARDS = 3;
    private static final MethodHandle RELINK;
    private static final MethodHandle IS_EXACT_CLASS;

    static {
        try {
            RELINK = LOOKUP.findStatic(
                    InlineCacheDemo.class, "relink",
                    MethodType.methodType(String.class, Cache.class, Object.class));
            IS_EXACT_CLASS = LOOKUP.findStatic(
                    InlineCacheDemo.class, "isExactClass",
                    MethodType.methodType(boolean.class, Class.class, Object.class));
        } catch (ReflectiveOperationException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    public static final class Dog {
        public String speak() { return "woof"; }
    }
    public static final class Cat {
        public String speak() { return "meow"; }
    }
    public static final class Bird {
        public String speak() { return "chirp"; }
    }
    public static final class Fox {
        public String speak() { return "yip"; }
    }

    static final class Cache extends MutableCallSite {
        final MethodHandle invoker;
        final Set<Class<?>> cachedTypes = new LinkedHashSet<>();
        int misses;

        Cache() {
            super(SITE_TYPE);
            MethodHandle fallback = MethodHandles.insertArguments(RELINK, 0, this);
            setTarget(fallback);
            invoker = dynamicInvoker();
        }
    }

    private static boolean isExactClass(Class<?> expected, Object receiver) {
        return receiver != null && receiver.getClass() == expected;
    }

    private static String relink(Cache site, Object receiver) throws Throwable {
        Objects.requireNonNull(receiver, "receiver");
        Class<?> actual = receiver.getClass();

        MethodHandle direct = LOOKUP.findVirtual(
                actual, "speak", MethodType.methodType(String.class))
                .asType(SITE_TYPE);

        synchronized (site) {
            site.misses++;
            if (site.cachedTypes.size() < MAX_GUARDS
                    && !site.cachedTypes.contains(actual)) {
                MethodHandle test =
                        MethodHandles.insertArguments(IS_EXACT_CLASS, 0, actual);
                MethodHandle next = MethodHandles.guardWithTest(
                        test, direct, site.getTarget());
                site.setTarget(next);
                site.cachedTypes.add(actual);
                MutableCallSite.syncAll(new MutableCallSite[]{site});
            }
        }
        return (String) direct.invokeExact(receiver);
    }

    private static void call(Cache site, String label, Object receiver)
            throws Throwable {
        String result = (String) site.invoker.invokeExact(receiver);
        System.out.println(label + "=" + result
                + ";misses=" + site.misses
                + ";cached=" + site.cachedTypes.size());
    }

    public static void main(String[] args) throws Throwable {
        Cache site = new Cache();
        System.out.println("siteType=" + site.type());
        call(site, "dog1", new Dog());
        call(site, "dog2", new Dog());
        call(site, "cat1", new Cat());
        call(site, "dog3", new Dog());
        call(site, "bird1", new Bird());
        call(site, "fox1", new Fox());
        call(site, "fox2", new Fox());
        call(site, "cat2", new Cat());

        try {
            String ignored = (String) site.invoker.invokeExact((Object) null);
        } catch (NullPointerException e) {
            System.out.println("nullReceiver=" + e.getClass().getSimpleName());
        }
        try {
            String ignored = (String) site.invoker.invokeExact((Object) new Object());
        } catch (NoSuchMethodException e) {
            System.out.println("unsupported=" + e.getClass().getSimpleName());
        }
    }
}
```

Compile and run:

```bash
javac --release 17 InlineCacheDemo.java
java InlineCacheDemo
```

**Stdout verified with a Java 17-compatible Java version:**

```text
siteType=(Object)String
dog1=woof;misses=1;cached=1
dog2=woof;misses=1;cached=1
cat1=meow;misses=2;cached=2
dog3=woof;misses=2;cached=2
bird1=chirp;misses=3;cached=3
fox1=yip;misses=4;cached=3
fox2=yip;misses=5;cached=3
cat2=meow;misses=5;cached=3
nullReceiver=NullPointerException
unsupported=NoSuchMethodException
```

### 7.1. Initialization with a fallback

`new MutableCallSite(SITE_TYPE)` fixes the `(Object)String` signature. `Cache`'s constructor builds the fallback via `insertArguments(RELINK,0,this)`, turning `relink(Cache,Object)String` into an `(Object)String` handle and then calling `setTarget(fallback)`. No class is cached yet, so the first call must go to the fallback.

`invoker = dynamicInvoker()` is created **once** and remains usable after every target replacement. This is the key property: the caller **does not need to obtain a new MethodHandle** whenever the receiver class changes.

### 7.2. First `Dog`: miss and learning the target

Line `dog1=woof;misses=1;cached=1`:

1. `invoker` goes to the fallback.
2. `relink` receives `Dog` and looks up `Dog.speak()` with `findVirtual`.
3. `asType(SITE_TYPE)` converts `(Dog)String` to `(Object)String`.
4. `insertArguments` binds `Dog.class` into the predicate, creating `(Object)boolean`.
5. `guardWithTest(test, direct, oldTarget)` creates a new target consisting of the Dog fast path and the old fallback.
6. `setTarget` installs the chain, and `syncAll` publishes the change.
7. The fallback invokes `direct.invokeExact(receiver)` for **this very first call**, receiving `"woof"`.

### 7.3. Second `Dog`: cache hit

Line `dog2=woof;misses=1;cached=1` demonstrates that the second call with **a different Dog object** having the same runtime class is recognized by the guard and does not enter `relink`. The miss count does not increase.

This is **caching by class**, not caching by object instance. Two different `new Dog()` objects both satisfy `receiver.getClass() == Dog.class`.

### 7.4. `Cat` and `Bird`: expanding the PIC

When `Cat` is first seen, the `Dog` guard returns false, the fallback resolves the `Cat` target, and then installs:

```text
guard(Cat, catHandle, guard(Dog, dogHandle, fallback))
```

When `Bird` is first seen, the structure becomes:

```text
guard(Bird, birdHandle,
    guard(Cat, catHandle,
        guard(Dog, dogHandle,
            fallback)))
```

Subsequent `Dog`/`Cat` calls still hit their respective guards. Because the newly added guard is at the **head of the chain**, the most recently added type is checked first; this order is not an algorithm that is always optimal for every workload. With a stable distribution, you can order by frequency or change the PIC policy after measurement.

### 7.5. `Fox` after the cache already has three classes

Line `fox1=yip;misses=4;cached=3` shows that `Fox` is handled properly via the miss path, but **no new guard is added** because `MAX_GUARDS=3` has been reached. Calling `Fox` again increases `misses` to `5`.

Both `Fox` calls return `"yip"` validly. Do not equate "not cached" with "method unsupported". The fallback can still invoke any class that has a `speak()String` method accessible to `Lookup`.

### 7.6. Null and non-existent method

- `nullReceiver=NullPointerException`: the exact-class predicate returns false for null; the fallback explicitly uses `Objects.requireNonNull` before lookup.
- `unsupported=NoSuchMethodException`: `new Object()` does not have a `speak()String` method, so `Lookup.findVirtual` fails. This is a **resolution error**, not a normal cache miss that dispatched successfully.

In the demo, `misses` is only incremented **after** `findVirtual` succeeds, so null and unsupported do not increment the counter. This is how **this example** defines its metric, not a JVM-wide convention.

### 7.7. Correctness when multiple threads use the same site

Installing the guard happens inside `synchronized(site)`, reducing the risk of two writers overwriting each other's chain. `syncAll` publishes the new target to other threads according to `MutableCallSite` semantics.

**Intentional limitation of the program:** The `call(...)` invocations in `main` run **sequentially** so stdout is deterministic. The two fields `misses` and `cachedTypes` are read for display without acquiring a lock because the demo has no readers writing concurrently during printing. In multithreaded production code, synchronization or thread-safe primitives are needed for **metrics and cache state**, not only for replacing the target.

### 7.8. Why is the example not a benchmark?

The number of misses and cached classes are **evidence of the dispatch path**, not performance measurements or proof that the JIT has inlined the methods. `System.out.println`, allocations, first-time class loading, and handle setup significantly affect direct timing in a demo. A serious benchmark should have warm-up, an explicit receiver distribution, and a tool like JMH.

## 8. Thread safety and visibility of MutableCallSite

`MutableCallSite.setTarget(...)` has the semantics of an **ordinary variable**. Merely calling `setTarget` from one thread **does not force** other threads currently executing the target to see the update immediately; the JIT/runtime is allowed to keep the old target under conditions permitted by the memory model.

`MutableCallSite.syncAll(MutableCallSite[] sites)` provides a special synchronization mechanism so that subsequent reads adopt the latest target relative to the sync. It **does not roll back** invocations that have already started running on the old target.

### 8.1. Correct publishing steps

In the demo code, a relink performs:
1. Enter `synchronized(site)` (coordinating writers).
2. Read the current `site.getTarget()` **inside the lock**.
3. Attach the new guard onto the existing chain.
4. `site.setTarget(newChain)`.
5. Record metadata about the cached class.
6. `MutableCallSite.syncAll(new MutableCallSite[]{site})`.
7. Exit the lock.

This helps avoid lost relinks and ensures publication when readers continue calling through `dynamicInvoker()`. A reader may have already started with the old chain before the sync; since that chain still has a valid fallback, it does not lose correctness.

**Note:** `syncAll` can carry significant cost, and may coordinate/wait for threads holding the old target. Do not call it after **every cache hit**. When batching multiple sites that change together, you can group them to sync once when appropriate.

### 8.2. When to choose VolatileCallSite?

If you require **all threads** to see target updates under volatile visibility without managing `syncAll` separately, `VolatileCallSite` has the appropriate semantics. In return, each target access carries the cost/optimization constraints of volatile semantics. There is no universally faster answer: consider relink frequency, thread count, site stability, and post-warmup performance.

`ConstantCallSite` does not support relinking via `setTarget`; it makes sense if the bootstrap already determines the target and the target does not change. Do not pick `ConstantCallSite` and expect to build a PIC by directly updating the target.

### 8.3. Do not use a target update to fix a transaction

A CallSite's target determines the **execution path**, and does not by itself guarantee application data consistency when plugins/configs change. If the target references mutable state, that state itself still needs synchronization under the Java Memory Model. A relink is not equivalent to a transaction or a distributed configuration barrier.

## 9. Cache invalidation and the relink branch

A class-based cache is valid when the method resolution result **depends only on the runtime class and stable factors**. If the system also supports:
- plugin hot reload;
- access/policy changes;
- schema or protocol versions;
- dynamic-language method tables/runtime shapes;
- feature flags switching the target implementation;

then the cache can become **stale** even if the receiver class has not changed. A single class guard cannot detect all such changes.

### 9.1. Invalidation with SwitchPoint

`java.lang.invoke.SwitchPoint` supports a one-way **valid → invalid** switch. It can wrap a fast target and a fallback:

```java
SwitchPoint version = new SwitchPoint();
MethodHandle guarded = version.guardWithTest(fastTarget, fallback);
// When this version is no longer usable:
SwitchPoint.invalidateAll(new SwitchPoint[]{version});
```

This is an illustrative snippet; it requires importing `java.lang.invoke.SwitchPoint` and having `fastTarget/fallback` of the **same MethodType**. After invalidation, calls to that guard route through the fallback. The same `SwitchPoint` cannot be "turned back on"; to cache a new generation, create a new switch point/guard.

**Important:** The invalidation mechanism must be called by the application when policy/metadata changes. `SwitchPoint` **does not automatically watch** configuration files or plugin changes to detect a stale cache.

### 9.2. Cache miss vs. cache invalidation

- **Miss:** There is no matching guard yet for a new receiver, or the PIC is saturated so the receiver takes the generic branch.
- **Invalidation:** A guard/target was cached but is considered no longer valid because version/policy/shape changed.
- **Relink:** The action of finding and installing a new call path; it can originate from a miss **or** an invalidation.

Using one fallback for both situations is fine, but metrics/policies should be distinguished to avoid infinite relinking when configuration is invalid.

### 9.3. ClassLoader and long-lived references

A guard holds a `Class<?>` object and handles referencing methods/classes. If a cache outlives a plugin/class loader, it can prevent the class loader from being garbage collected. In a dynamic plugin system:
- scope caches to the plugin/tenant lifecycle;
- clear or replace targets on unload;
- bound PIC chains;
- consider weak references/`ClassValue` when designing a global cache, while understanding their actual semantics and lifecycle;
- do not use string class names as unique identifiers if multiple loaders can define the same name.

The three-guard limit in the demo both aids learning and illustrates how to limit accumulating class references on a site.

## 10. Error handling in lookup, adapters, and targets

The fallback path in the example performs:

```java
MethodHandle direct = LOOKUP.findVirtual(
        actual, "speak", MethodType.methodType(String.class))
        .asType(SITE_TYPE);
```

This is an excerpt from the full program. Errors to distinguish:

| Stage | Example | Result or handling |
| --- | --- | --- |
| Null receiver | Caller passes `null` | The demo explicitly throws `NullPointerException("receiver")`; can be changed to a custom policy |
| Lookup: non-existent method | Class has no matching `speak()String` | `NoSuchMethodException` |
| Lookup: access permission | Method/class is not accessible with the current `Lookup` | `IllegalAccessException` |
| Adapter: incompatible | `asType` cannot convert types as requested | Can throw `WrongMethodTypeException` when creating the adapter or a conversion error on invoke |
| Site update: wrong target type | `setTarget` receives a `MethodHandle` different from `site.type()` | `WrongMethodTypeException` |
| Guard: mismatched handle types | `guardWithTest` receives incompatible test/target/fallback | `IllegalArgumentException` |
| Target execution | `speak()` throws an exception | A Throwable from the target can propagate directly through MethodHandle; it is not automatically wrapped in `InvocationTargetException` |
| Cache too large | Accumulating many guards, handles, classes | Increases cost/memory; needs a cap, fallback, and eviction/invalidation policy |

You should not catch every exception in the fallback and then **cache a generic error** or return a default string, unless that is the application contract. For example, a non-existent method may need clear diagnostics:
- observed runtime class;
- requested name and method type;
- class loader or module;
- site policy and fallback action.

### 10.1. Security considerations of dynamic method lookup

`MethodHandles.lookup()` carries the access rights of the class where the lookup is created. It **does not** allow bypassing all `private` members/module boundaries. Do not take arbitrary class names/method names from external data and allow calling any method: validate whitelists/schemas/permissions, use restricted lookups, and control exceptions.

In the demo program, the `Dog/Cat/Bird/Fox` classes are in the same enclosing class (nest) and the methods are `public`, so lookup is valid. With real plugins, JPMS `exports`/`opens`, access context, and package visibility can affect the result.

### 10.2. Do not collapse target errors into a "cache miss"

When a guard hits and the target method throws `IllegalStateException`, that is a **target error**, not a call that should relink by default. If you catch `Throwable` across the entire hot path and re-resolve on every exception, you may re-execute dangerous side effects or hide business logic bugs.

Only take the relink branch when **guard/invalidation conditions fail**. Exceptions from the target must follow the method contract and the application's error handling mechanism.

## 11. A call site does not necessarily always cache the same set of types

A site can go through phases:

```text
Initial (cold)
    target = relinkFallback

Monomorphic
    target = guard(Dog, dogHandle, relinkFallback)

Polymorphic
    target = guard(Cat, catHandle,
                guard(Dog, dogHandle, relinkFallback))

Saturated PIC
    target = guard(Bird, birdHandle,
                guard(Cat, catHandle,
                    guard(Dog, dogHandle, relinkFallback)))

New receiver after saturation
    -> fallback (resolve/generic dispatch, no new guard added)
```

A more sophisticated optimizing runtime can replace the chain with:
- a class-keyed lookup table;
- dispatch by receiver shape;
- an optimized generic target for megamorphic sites;
- a code cache rebuilt based on profiles or JIT tiers.

These are **design choices**, not default states that `MutableCallSite` automatically transitions between. The JDK only provides primitives; the application/runtime must implement the logic to switch between strategies.

## 12. Common misconceptions

1. **"`CallSite` automatically caches every receiver class."** False. `CallSite` only holds a single target handle. Caching/guarding/relinking is logic built by the application runtime.
2. **"`dynamicInvoker()` always invokes the initial target."** False for a mutable call site; it follows the site's current target, according to the corresponding visibility semantics.
3. **"To optimize for Dog, change the site type from Object to Dog."** Invalid. `CallSite.type()` is fixed; individual targets must be adapted using `asType`.
4. **"Checking class names by string is equivalent to checking Class identity."** False when multiple class loaders exist.
5. **"A guard can accept null and then invoke the method normally."** No if the target needs a receiver instance; an explicit null policy must be chosen.
6. **"A guard using `instanceof` is always safe."** No if dispatch depends on exact runtime class, shape, or version.
7. **"Relink must call `dynamicInvoker` again for the current miss."** Not required and prone to recursion/double counting; the resolved direct handle can be invoked.
8. **"`MutableCallSite.setTarget` guarantees all threads see it immediately."** False. Appropriate synchronization is required, such as `syncAll`; `VolatileCallSite` has different semantics.
9. **"`syncAll` makes invocations already running the old target switch back to running the new target."** False; calls that have already started may finish on the old target.
10. **"Adding guards for every class is always fastest."** No. A very long PIC costs more on misses, increases footprint, and can hurt the JIT.
11. **"The number of misses equals the number of distinct classes."** No; uncached classes can miss multiple times.
12. **"A cache hit means the JIT has definitely inlined the target."** No. A hit only describes the path through the guard/handle; JIT optimization requires profiling and is not guaranteed.
13. **"One failed lookup means the receiver has no method in any context."** No. `Lookup` rights, module access, method signature, and loader affect resolution.
14. **"Relinking can also fix business state when a target exception occurs."** No. Relinking changes the dispatch path, not arbitrary side-effect retries.
15. **"Holding Class/MethodHandle in a cache does not affect plugin unloading."** It can affect class loader lifecycle and memory.
16. **"`SwitchPoint` automatically invalidates when a plugin changes."** No. The application must signal invalidation according to its own policy.

## 13. Self-check

### Exercise 1 — Drawing the PIC

A site has target `guard(Cat, catHandle, guard(Dog, dogHandle, miss))`. When called with a new `Dog`, which branch runs?

**Answer:** The Cat guard returns false, the Dog guard returns true, so `dogHandle` is invoked. `miss` is not called and no cache entry is added.

### Exercise 2 — Receiver class and MethodType

The site has type `(Object)String`, while `findVirtual(Dog.class,"speak",()String)` produces `(Dog)String`. Can we call `site.setTarget(dogHandle)` directly?

**Answer:** No. `setTarget` requires a method type **equal** to the site type. We need `dogHandle.asType(MethodType.methodType(String.class,Object.class))`, and then attach a `Dog.class` guard to ensure the right receiver.

### Exercise 3 — Misses in a full cache

The PIC is limited to three classes, and Dog/Cat/Bird are already cached. There are two consecutive calls with Fox. If the fallback does not add Fox to the cache, how many new misses will there be?

**Answer:** Two misses. Each time Fox goes through all three guards and enters the fallback; it can still return the right result.

### Exercise 4 — Synchronizing writers

Two threads concurrently read `oldTarget`; one installs a Dog guard, one installs a Cat guard. Both call `setTarget` without a lock. What is the risk?

**Answer:** Lost relink: the final target may be missing the guard just added by the other thread. The chain must be updated under a writer coordination policy (e.g. `synchronized(site)`) and target visibility for readers must be ensured via an appropriate mechanism.

### Exercise 5 — Invalidation

The receiver is still Dog, but the plugin is configured so `Dog.speak` has new behavior. The guard `getClass()==Dog.class` still returns true. Does the PIC automatically know the target is stale?

**Answer:** No. If dispatch behavior depends on version/config outside class identity, an additional guard or invalidation is required, for example via `SwitchPoint.invalidateAll(...)` and relinking to the new-generation target.

### Exercise 6 — Exact invocation with the right type

`MethodHandle invoker` has type `(Object)String`. What is the difference between:

```java
String good = (String) invoker.invokeExact((Object) new Dog());
String bad = (String) invoker.invokeExact(new Dog());
```

These are two illustrative lines inside a method that has variable `invoker` and class `Dog`. Since the static type of the second expression is `Dog`, it does not match the `Object` parameter that `invokeExact` requires; it can throw `WrongMethodTypeException`. The first line casts the receiver to `Object` to produce the right call-site descriptor, while the runtime guard still sees the actual class `Dog`.

### Exercise 7 — Performance criteria

When a PIC has three guards, calling 100 different classes once each in a row: why might this be slower than an appropriate generic dispatch?

**Answer:** Most calls go through all three guards and then miss, having to resolve and possibly create a new adapter without caching; the per-miss cost is high. You should measure the real workload, optimize the fallback for megamorphic sites, or choose an appropriate global cache.

## Official Documentation

- [Java SE 17 — CallSite](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/CallSite.html): `type`, `target`, and `dynamicInvoker` contract.
- [Java SE 17 — MutableCallSite](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MutableCallSite.html): `setTarget`, `syncAll`, and cross-thread visibility.
- [Java SE 17 — VolatileCallSite](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VolatileCallSite.html): target under volatile semantics.
- [Java SE 17 — MethodHandles](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html): `guardWithTest`, `insertArguments`, `Lookup.findVirtual`.
- [Java SE 17 — MethodHandle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html): `asType`, `invokeExact`.
- [Java SE 17 — SwitchPoint](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/SwitchPoint.html): invalidating guarded targets when cached information expires.

## Conclusion

Inline caching at the call site **turns repeated dynamic lookups into a guarded fast path**. For previously seen receiver classes, `guardWithTest` selects the resolved target; when encountering a different class, the **fallback/relink** branch checks the type, looks up the new handle, adapts it to `CallSite.type()`, and updates the chain. `MutableCallSite` does not provide a PIC out of the box: the application must build guards, bound the number of branches, synchronize updates across threads, and manage invalidation. A correct design must preserve the type contract, not ignore null/lookup failures, not accidentally cache stale targets, and not equate a cache hit with a JIT optimization guarantee.
