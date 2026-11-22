# 12.7 `SwitchPoint`, `guardWithTest`, and One-Way Invalidation

In `java.lang.invoke`, `SwitchPoint` represents **an assumption that is either still valid or permanently invalidated**. While the assumption holds, a guarded `MethodHandle` invokes the `target` branch (usually the fast path). After the program actively invalidates the assumption, the same handle switches to invoking the `fallback` branch. This is an important tool when building inline caches, dynamic language runtimes, call-site linking systems, or optimizations that depend on a configuration version.

Two APIs have similar names but different meanings:

- `point.guardWithTest(target, fallback)` on **`SwitchPoint`**: chooses a branch based on **the valid/invalidated state of the point**. Before invalidation it uses `target`, and afterward it uses `fallback`. Invalidation is **only one-way: valid → invalidated**.
- `MethodHandles.guardWithTest(test, target, fallback)`: invokes a **`test` MethodHandle returning `boolean`** to choose a branch by predicate. The test can depend on the input on each invocation and can alternate between returning true and false.

They must not be conflated. A `SwitchPoint` does **not** inspect user parameters, does **not** automatically detect data changes, and does **not** reset itself when the fallback finishes its work. To start a new optimization cycle after invalidation, you must create a new `SwitchPoint` and a new guarded handle, then publish the new configuration according to an appropriate protocol.

This lesson belongs to the **CallSite** group because guarded handles can serve as targets of `ConstantCallSite` or `MutableCallSite`. However, `SwitchPoint` is **not a CallSite**: invalidation switches the guard's branch without necessarily changing the target object held in the CallSite.

After this lesson, you will be able to explain the one-way lifecycle, distinguish the two `guardWithTest` variants, build `MethodType`-compatible fast/fallback handles, handle `invalidateAll`, combine guards with CallSite, avoid concurrency misconceptions, and debug exceptions. The examples are standalone Java 17+ programs, with `javac`/`java` commands and stdout verified by actual execution.

## 1. Purpose: optimizing based on an assumption with a lifetime

Suppose a runtime library has looked up a method and stored a linked result. As long as the application's configuration or schema does not change, this fast call path is valid. When a configuration change event occurs, the fast call path must be discarded, and subsequent calls must go through a correct resolver/fallback.

```text
   Is the schema/config assumption still true?
                    |
                 SwitchPoint
                    |
          +---------+----------+
          |                    |
       valid               invalidated
          |                    |
          v                    v
    optimized target       safe fallback
    (can use cache)     (resolve/read new version)
```

A regular Java check can also express this idea:

```java
// Illustrative snippet, not a standalone program:
if (assumptionIsValid) {
    return fastPath(input);
}
return fallbackPath(input);
```

However, when the application organizes calls through **MethodHandle chains**, `SwitchPoint` lets you describe the guard as a new `MethodHandle`, allowing the runtime to optimize while the assumption remains stable. `SwitchPoint` does not cache the **return value** of a method and does not handle business logic on behalf of the two branches; you actively supply both `target` and `fallback`.

Reasonable use cases: a generation of a field cache, a method dispatch strategy linked based on the current class hierarchy, or a routing rule that can be changed but only needs to **invalidate the old generation**. A predicate that changes continuously per request, on the other hand, is not an appropriate use case for `SwitchPoint`.

## 2. Lifecycle of `SwitchPoint`: one-way

A new `SwitchPoint` starts in the **valid** state:

```java
SwitchPoint point = new SwitchPoint();
System.out.println(point.hasBeenInvalidated()); // false
```

To invalidate it:

```java
SwitchPoint.invalidateAll(new SwitchPoint[] {point});
System.out.println(point.hasBeenInvalidated()); // true
```

Both snippets are illustrative code inside a class/method that imports `java.lang.invoke.SwitchPoint`. `invalidateAll` is a **static method** that takes an array of `SwitchPoint`s to invalidate. Calling it when a point is already invalidated does not reactivate that point.

```text
 new SwitchPoint()
       |
       v
    VALID  ---- invalidateAll(...) ----> INVALIDATED
                                           |
                                 invalidateAll(...) again
                                           |
                                           v
                                       INVALIDATED
```

**There is no `reset()`, `validate()`, or `enable()` on `SwitchPoint`.** This is a key design rule: a point represents an **assumption of a single generation**, and once that generation is invalidated, it cannot be restored in the same object.

Consequences:

1. A guard created from a valid point before invalidation will use `target`.
2. After invalidation, subsequent calls to the guard, per the API semantics, will choose `fallback`.
3. **Every guard** created from the same point shares the same invalidated state, even if the guards have different targets/fallbacks.
4. Invalidation does not destroy the `MethodHandle` object and does not change `guard.type()`; it changes the **execution branch**.
5. To bring the fast path back for new data, create a **new point + new guard**; keeping the old guard still leads to `fallback`.
6. Other switch points are not invalidated just because some point was invalidated. You need to manage the list of dependent points.

Do not treat `SwitchPoint` as a mutable boolean that can be set to `true` and `false` repeatedly. It is designed so that **the JIT/runtime can trust that invalidated is the final state of the object**.

## 3. How to create a guarded MethodHandle and signature requirements

Steps:

```java
// Illustration: target and fallback are already created MethodHandles.
SwitchPoint point = new SwitchPoint();
MethodHandle guarded = point.guardWithTest(target, fallback);
```

`point.guardWithTest` requires both branches to have the **same `MethodType`**, including parameter count, order, parameter types, **and return type**:

```text
target.type()   = (String)String
fallback.type() = (String)String
guarded.type()  = (String)String
```

If `target` returns `String` while `fallback` returns `Object`, the two types `(String)String` and `(String)Object` are **not equivalent** even though `String` inherits from `Object`. Constructing the guard will throw `IllegalArgumentException`, rather than automatically converting the return type. Similarly, `(int)int` differs from `(long)int`, and `(int)void` differs from `(int)int`.

When you genuinely want to create an adapter, make the conversion explicit:

```java
// Illustrative snippet: rawFallback.type() == (String)Object.
// Casting Object -> String is only appropriate if the returned data is actually a String.
MethodHandle convertedFallback = rawFallback.asType(
        MethodType.methodType(String.class, String.class));
MethodHandle guarded =
        point.guardWithTest(target, convertedFallback);
```

`asType` does not guarantee that every conversion succeeds: an unsupported conversion can cause `WrongMethodTypeException`; a reference conversion that is created but encounters an object of the wrong type can lead to `ClassCastException` at runtime.

### 3.1. `invokeExact` requires a matching caller signature

A guarded handle of type `(String)String` must be invoked with **static argument type `String`** and return type **`String`** at the call site:

```java
// guarded.type() == (String)String
String name = "Ada";
String answer = (String) guarded.invokeExact(name);
```

Conversely:

```java
// Illustrative snippet of an incorrect call, will throw WrongMethodTypeException:
Object value = "Ada";
String answer = (String) guarded.invokeExact(value);
```

The runtime value of `value` is `String`, but the **static** type of the argument is `Object`; the caller's descriptor does not match `(String)String`. This is a `MethodHandle.invokeExact` error, not an invalidation error.

You must distinguish **two levels of type checking**: when creating the guard, `target` and `fallback` must have the same type; when calling via `invokeExact`, the caller's descriptor must match the guard's type.

## 4. Standalone example 1 — `SwitchPoint` switching fast → fallback

Create the file **`SwitchPointDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.SwitchPoint;

public class SwitchPointDemo {
    private static String fast(String value) {
        return "cache:" + value;
    }

    private static String slow(String value) {
        return "fresh:" + value;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType type = MethodType.methodType(String.class, String.class);
        MethodHandle fast = lookup.findStatic(SwitchPointDemo.class, "fast", type);
        MethodHandle slow = lookup.findStatic(SwitchPointDemo.class, "slow", type);

        SwitchPoint point = new SwitchPoint();
        MethodHandle guard = point.guardWithTest(fast, slow);

        System.out.println("type: " + guard.type());
        System.out.println("invalid before: " + point.hasBeenInvalidated());
        System.out.println("before: " + (String) guard.invokeExact("Ada"));

        SwitchPoint.invalidateAll(new SwitchPoint[] {point});

        System.out.println("invalid after: " + point.hasBeenInvalidated());
        System.out.println("after: " + (String) guard.invokeExact("Ada"));
        SwitchPoint.invalidateAll(new SwitchPoint[] {point});
        System.out.println("after repeat: " + (String) guard.invokeExact("Lin"));

        SwitchPoint replacement = new SwitchPoint();
        MethodHandle newGuard = replacement.guardWithTest(fast, slow);
        System.out.println("replacement invalid: " + replacement.hasBeenInvalidated());
        System.out.println("replacement: " + (String) newGuard.invokeExact("Lin"));
        System.out.println("old still: " + (String) guard.invokeExact("Lin"));
    }
}
```

Compile and run on JDK 17+:

```bash
javac --release 17 SwitchPointDemo.java
java SwitchPointDemo
```

Verified stdout:

```text
type: (String)String
invalid before: false
before: cache:Ada
invalid after: true
after: fresh:Ada
after repeat: fresh:Lin
replacement invalid: false
replacement: cache:Lin
old still: fresh:Lin
```

Explanation:

- `findStatic` returns MethodHandles for `fast` and `slow`, both having `(String)String`.
- The new point is still valid, so `guard.invokeExact("Ada")` goes through `fast`, printing `cache:Ada`.
- `invalidateAll` transitions the point to invalidated. The guard is still valid to invoke, but now calls `slow`, printing `fresh:Ada`.
- Invalidating again does not change the state. With a new input `Lin`, the guard still uses `slow`.
- `replacement` is a **new** object, so it is valid. `newGuard` can take the fast path; the **old** guard does not go back to fast.

`fast` and `slow` themselves in the example only return strings for easy observation. In a real runtime, the fallback typically has to **re-resolve data**, read a consistent source, or take another safe path. `SwitchPoint` does not automatically provide "fresh" logic.

## 5. Two different `guardWithTest` variants

This is the core pair of APIs to remember:

```java
MethodHandle conditionally = MethodHandles.guardWithTest(
        booleanTestHandle, target, fallback);

MethodHandle generationGuard = point.guardWithTest(
        target, fallback);
```

This snippet is illustrative code, with variables already declared in scope. Both create a `MethodHandle` whose `type()` equals `target.type()` and `fallback.type()`, but the **source of the branching decision** is different.

| Criterion | `MethodHandles.guardWithTest(test,target,fallback)` | `SwitchPoint.guardWithTest(target,fallback)` |
| --- | --- | --- |
| Condition | `boolean` result of the `test` handle | Valid/invalidated state of the point |
| When branch is chosen | Evaluates the predicate on every call | Chooses based on the point's state |
| Depends on arguments? | Yes; `test` receives matching arguments | No by API; `point` does not take arguments to test |
| Can go true → false → true? | Yes, if the predicate returns those results | No: invalidated cannot become valid |
| Invalidation API | No combinator-specific invalidation | `SwitchPoint.invalidateAll(...)` |
| Typical goal | Business conditions, input types, selectors | Invalidating a cache/optimization generation assumption |
| Type constraint | Target/fallback same type; test returns boolean and parameters are a matching prefix | Target/fallback same type |

### 5.1. `MethodHandles.guardWithTest` requires the test to return boolean

With target/fallback of type `(String,int)String`, you can use a test `(String)boolean` that checks only the first argument. The test receives a **prefix of the arguments**; if the test returns true, `target` runs with **all arguments**; if false, `fallback` also receives all arguments.

Example of valid signatures:

```text
test:     (String)boolean
target:   (String,int)String
fallback: (String,int)String
guard:    (String,int)String
```

A test `(String)int` is **invalid** because Java does not automatically treat 0 as false and 1 as true. A test whose parameter types do not match the prefix is also invalid. These errors are typically caught immediately when creating the guard with `IllegalArgumentException`.

### 5.2. SwitchPoint does not inspect individual requests

Suppose you need to choose a privilege based on username. If you use a valid SwitchPoint, **every** username goes through `target`, including ineligible users. After invalidation, **every** username goes through `fallback`. In that case, you need a **boolean predicate handle** or `if/else`, not an invalidation switch.

Guards can be nested in a complex runtime: `SwitchPoint` decides whether the cache generation is still valid, and a predicate decides how to handle a specific input. However, check order, type signatures, and security requirements must be clearly designed; never use `SwitchPoint` to bypass mandatory permission checks.

## 6. Standalone example 2 — predicate and switch point

Create the file **`GuardComparisonDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.SwitchPoint;

public class GuardComparisonDemo {
    private static boolean isVip(String user) {
        return user.equals("vip");
    }

    private static String preferred(String user) {
        return "VIP:" + user;
    }

    private static String standard(String user) {
        return "STANDARD:" + user;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType stringToString = MethodType.methodType(String.class, String.class);
        MethodHandle condition = lookup.findStatic(
                GuardComparisonDemo.class, "isVip",
                MethodType.methodType(boolean.class, String.class));
        MethodHandle preferred = lookup.findStatic(
                GuardComparisonDemo.class, "preferred", stringToString);
        MethodHandle standard = lookup.findStatic(
                GuardComparisonDemo.class, "standard", stringToString);

        MethodHandle conditional =
                MethodHandles.guardWithTest(condition, preferred, standard);
        System.out.println("conditional vip: "
                + (String) conditional.invokeExact("vip"));
        System.out.println("conditional guest: "
                + (String) conditional.invokeExact("guest"));

        SwitchPoint point = new SwitchPoint();
        MethodHandle epochGuard = point.guardWithTest(preferred, standard);
        System.out.println("switchpoint guest before: "
                + (String) epochGuard.invokeExact("guest"));

        SwitchPoint.invalidateAll(new SwitchPoint[] {point});
        System.out.println("switchpoint vip after: "
                + (String) epochGuard.invokeExact("vip"));
    }
}
```

Run:

```bash
javac --release 17 GuardComparisonDemo.java
java GuardComparisonDemo
```

Verified stdout:

```text
conditional vip: VIP:vip
conditional guest: STANDARD:guest
switchpoint guest before: VIP:guest
switchpoint vip after: STANDARD:vip
```

**Why is the output intentionally different?**

`conditional` invokes `isVip(user)`: user `"vip"` selects `target`, while user `"guest"` selects `fallback`. It branches based on **the call's data**.

`epochGuard` does **not** invoke `isVip`. When the point is valid, even `"guest"` takes the `preferred` branch; after being invalidated, even `"vip"` takes the `standard` branch. It chooses a branch based on **generation state**, not user data.

Therefore, you must **not** replace a predicate combinator with `SwitchPoint` if `target` contains an action requiring per-user permission or business conditions.

## 7. Relationship with `CallSite`: different purposes

`CallSite` in `java.lang.invoke` holds a **target `MethodHandle`** with a stable type. Common cases:

- `ConstantCallSite`: the target reference is fixed after initialization.
- `MutableCallSite`: `setTarget` allows changing the target to another handle of the **same `MethodType`**; it has publication/synchronization rules, such as `syncAll`.
- `VolatileCallSite`: the target can be replaced with volatile semantics for visibility across threads.

`SwitchPoint` is **not** a subclass of `CallSite`. It creates a **guarded handle**. This handle can be placed into a `CallSite` as a target:

```java
// Illustrative snippet assuming point, fast, and fallback already exist.
MethodHandle guard = point.guardWithTest(fast, fallback);
CallSite site = new ConstantCallSite(guard);
MethodHandle invoker = site.dynamicInvoker();
```

After invalidation, **`site.getTarget()` is still the `guard` object** if `site` is a `ConstantCallSite`. Yet the guard's behavior can change because the point has been invalidated. This does not contradict "Constant": that refers to the immutability **of the stored target MethodHandle**, not a guarantee that the computation result inside the target will never change.

`MutableCallSite` addresses a different problem: it can replace the entire target multiple times (fast → fallback → fast), as long as the same type is kept and publication is handled properly. An old `SwitchPoint`, on the other hand, **cannot** be re-validated.

## 8. Standalone example 3 — `ConstantCallSite` and `MutableCallSite`

Create the file **`CallSiteSwitchPointDemo.java`**:

```java
import java.lang.invoke.CallSite;
import java.lang.invoke.ConstantCallSite;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.MutableCallSite;
import java.lang.invoke.SwitchPoint;

public class CallSiteSwitchPointDemo {
    private static int fast(int number) {
        return number + 100;
    }

    private static int fallback(int number) {
        return number + 1;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType type = MethodType.methodType(int.class, int.class);
        MethodHandle fast = lookup.findStatic(
                CallSiteSwitchPointDemo.class, "fast", type);
        MethodHandle fallback = lookup.findStatic(
                CallSiteSwitchPointDemo.class, "fallback", type);

        SwitchPoint point = new SwitchPoint();
        MethodHandle guard = point.guardWithTest(fast, fallback);
        CallSite site = new ConstantCallSite(guard);
        MethodHandle invoker = site.dynamicInvoker();

        int before = (int) invoker.invokeExact(5);
        System.out.println("constant before: " + before);

        SwitchPoint.invalidateAll(new SwitchPoint[] {point});
        int after = (int) invoker.invokeExact(5);
        System.out.println("constant after: " + after);
        System.out.println("constant target same: "
                + (site.getTarget() == guard));

        MutableCallSite mutable = new MutableCallSite(fast);
        MethodHandle dynamic = mutable.dynamicInvoker();
        System.out.println("mutable fast: " + (int) dynamic.invokeExact(5));
        mutable.setTarget(fallback);
        MutableCallSite.syncAll(new MutableCallSite[] {mutable});
        System.out.println("mutable fallback: " + (int) dynamic.invokeExact(5));
        mutable.setTarget(fast);
        MutableCallSite.syncAll(new MutableCallSite[] {mutable});
        System.out.println("mutable fast again: "
                + (int) dynamic.invokeExact(5));
    }
}
```

Compile and run:

```bash
javac --release 17 CallSiteSwitchPointDemo.java
java CallSiteSwitchPointDemo
```

Verified stdout:

```text
constant before: 105
constant after: 6
constant target same: true
mutable fast: 105
mutable fallback: 6
mutable fast again: 105
```

`ConstantCallSite` holds the same guard object. Before invalidation, `invoker.invokeExact(5)` returns `105`; after invalidation, still going through **that exact same invoker and guard**, the fallback branch returns `6`. The check `site.getTarget() == guard` is `true`.

`MutableCallSite` in the second half of the program switches the target from `fast` to `fallback` and then back to `fast` — something an **invalidated** `SwitchPoint` cannot do. All targets have type `(int)int`; `syncAll` is used to illustrate the publication API.

**Note:** calling `CallSite.dynamicInvoker()` from Java source is a test of the CallSite API. It **does not emit a custom `invokedynamic` opcode**. When a real `invokedynamic` instruction is linked to a `CallSite` whose target is a guarded handle, the internal branch switch can also be observed according to these semantics.

## 9. Multiple guarded handles depending on one SwitchPoint

If multiple fast paths rely on the same assumption "schema V1 is valid", you can use one `SwitchPoint` to create multiple guards. When invalidating the assumption, call `invalidateAll` with that same point so all related guards switch to their fallbacks.

```text
SwitchPoint A
   |
   +-- guard A1: target1 / fallback1
   |
   +-- guard A2: target2 / fallback2

SwitchPoint B
   |
   +-- guard B1: target3 / fallback3

invalidateAll([A]):
  guard A1 -> fallback1
  guard A2 -> fallback2
  guard B1 -> still target3 if B is valid
```

**Different** guarded handles using the same point **do not need to share the same `MethodType` with each other**: the same-type rule applies only **within each target/fallback pair when creating a guard**. The point only carries the shared valid/invalidated state.

### 9.1. Group invalidation

```java
SwitchPoint.invalidateAll(new SwitchPoint[] {point1, point2});
```

The array specifies **the points you want to invalidate**; it is not a command to invalidate every `SwitchPoint` on the JVM. If two assumptions are closely related, you can manage them in the same operation. If they are independent, invalidating one point should not drag the other down with it.

Do not treat invalidating an array of multiple points as an **atomic transaction that updates all business data**. Snapshots, maps, registries, and code lifecycles still require their own synchronization protocols.

## 10. Standalone example 4 — two points, three guards

Create the file **`InvalidationGroupDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.SwitchPoint;

public class InvalidationGroupDemo {
    private static String active(String value) {
        return "active:" + value;
    }

    private static String retired(String value) {
        return "retired:" + value;
    }

    public static void main(String[] args) throws Throwable {
        MethodType type = MethodType.methodType(String.class, String.class);
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodHandle active = lookup.findStatic(
                InvalidationGroupDemo.class, "active", type);
        MethodHandle retired = lookup.findStatic(
                InvalidationGroupDemo.class, "retired", type);

        SwitchPoint first = new SwitchPoint();
        SwitchPoint second = new SwitchPoint();
        MethodHandle a = first.guardWithTest(active, retired);
        MethodHandle b = first.guardWithTest(active, retired);
        MethodHandle c = second.guardWithTest(active, retired);

        System.out.println("a before: " + (String) a.invokeExact("A"));
        System.out.println("b before: " + (String) b.invokeExact("B"));
        System.out.println("c before: " + (String) c.invokeExact("C"));

        SwitchPoint.invalidateAll(new SwitchPoint[] {first, second});

        System.out.println("a after: " + (String) a.invokeExact("A"));
        System.out.println("b after: " + (String) b.invokeExact("B"));
        System.out.println("c after: " + (String) c.invokeExact("C"));
        System.out.println("states: "
                + first.hasBeenInvalidated() + ","
                + second.hasBeenInvalidated());
    }
}
```

Run:

```bash
javac --release 17 InvalidationGroupDemo.java
java InvalidationGroupDemo
```

Verified stdout:

```text
a before: active:A
b before: active:B
c before: active:C
a after: retired:A
b after: retired:B
c after: retired:C
states: true,true
```

`a` and `b` share `first`, while `c` uses `second`. Invalidating both points causes all three guards to switch to `fallback`. If only `first` were passed, guard `c` would still choose `target` while `second` remained valid.

This clearly shows how **invalidation affects the guards depending on a point**, rather than deleting MethodHandles or automatically invalidating independent points.

## 11. Errors when building a guard and when invoking a guard

`SwitchPoint.guardWithTest` and `MethodHandles.guardWithTest` check type contracts at combinator creation time; `MethodHandle.invokeExact` checks types at invocation time.

| Error location | Symptom | Cause to check |
| --- | --- | --- |
| `point.guardWithTest(target,fallback)` | `IllegalArgumentException` | `target.type()` differs from `fallback.type()` |
| `MethodHandles.guardWithTest(test,target,fallback)` | `IllegalArgumentException` | Test does not return boolean, test parameters do not match, or the two branch types differ |
| `guard.invokeExact(...)` | `WrongMethodTypeException` | Caller descriptor does not equal `guard.type()`: wrong static argument types or return cast |
| `lookup.findStatic(...)` | `NoSuchMethodException` | Wrong name, class, static kind, or lookup `MethodType` |
| `lookup.findStatic(...)` | `IllegalAccessException` | Lookup lacks access permissions to the target |
| Body of target/fallback | Business exception | Target was invoked and threw an exception itself; not by default due to guard type or invalidation |

If you use `asType` to change a branch's signature, understand that adaptation can throw `WrongMethodTypeException` immediately when creating the adapter or cause a runtime cast error later. Do not "fix" a mismatch with an ambiguous cast without knowing the actual object.

### 11.1. Standalone example 5 — three kinds of mismatch

Create the file **`GuardTypeDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.SwitchPoint;
import java.lang.invoke.WrongMethodTypeException;

public class GuardTypeDemo {
    private static String text(String input) {
        return "text:" + input;
    }
    private static Object object(String input) {
        return "object:" + input;
    }
    private static boolean valid(String input) {
        return input.length() > 0;
    }
    private static int wrongTest(String input) {
        return input.length();
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType stringType = MethodType.methodType(String.class, String.class);
        MethodHandle good = lookup.findStatic(GuardTypeDemo.class, "text", stringType);
        MethodHandle wrongReturn = lookup.findStatic(GuardTypeDemo.class, "object",
                MethodType.methodType(Object.class, String.class));
        MethodHandle goodTest = lookup.findStatic(GuardTypeDemo.class, "valid",
                MethodType.methodType(boolean.class, String.class));
        MethodHandle wrongTest = lookup.findStatic(GuardTypeDemo.class, "wrongTest",
                MethodType.methodType(int.class, String.class));
        SwitchPoint point = new SwitchPoint();

        try {
            point.guardWithTest(good, wrongReturn);
        } catch (IllegalArgumentException e) {
            System.out.println("switchpoint mismatch: IllegalArgumentException");
        }
        try {
            MethodHandles.guardWithTest(wrongTest, good, good);
        } catch (IllegalArgumentException e) {
            System.out.println("predicate mismatch: IllegalArgumentException");
        }
        MethodHandle guarded = MethodHandles.guardWithTest(goodTest, good, good);
        try {
            Object broad = "ok";
            String no = (String) guarded.invokeExact(broad);
            System.out.println(no);
        } catch (WrongMethodTypeException e) {
            System.out.println("call mismatch: WrongMethodTypeException");
        }
        System.out.println("correct: " + (String) guarded.invokeExact("ok"));
    }
}
```

Run:

```bash
javac --release 17 GuardTypeDemo.java
java GuardTypeDemo
```

Verified stdout:

```text
switchpoint mismatch: IllegalArgumentException
predicate mismatch: IllegalArgumentException
call mismatch: WrongMethodTypeException
correct: text:ok
```

In the first error, `good` is `(String)String` while `wrongReturn` is `(String)Object`; the two branches do not have the same type. In the second error, the test returns `int` instead of `boolean`. In the third error, the guard is already valid, but the caller passes a variable with static type `Object`; `String` is required. Finally, `(String) guarded.invokeExact("ok")` has the right descriptor and runs successfully.

When debugging, print `test.type()`, `target.type()`, `fallback.type()`, and `guard.type()` instead of just looking at source methods with the same name.

## 12. Concurrency: invalidate does not cancel in-flight work

`SwitchPoint.invalidateAll` transitions the guard state according to the API semantics. However, **it does not mean that all calls started before invalidation must stop**, or that a half-executed business transaction is rolled back.

Example of a possible interleaving:

```text
Thread A                              Thread B
------------------------------------------------------------
starts calling guarded handle
has entered fast target
                                      configuration changes
                                      invalidateAll(point)
fast target completes
                                      next call chooses fallback
```

A program that wants to **revoke permissions even for in-flight operations**, wait for all old requests to finish before changing configuration, or require transactional consistency must have a **separate synchronization protocol**. `SwitchPoint` does not act as a cancellation token for an already-executing target.

### 12.1. Publishing snapshots/configurations must be thread-safe

For example, the fast path reads an old-generation `Map` or snapshot object. Even though invalidation switches the guard to `fallback`, the related data still needs to follow Java Memory Model rules:

- The writer builds the new snapshot before publishing.
- Readers receive the new snapshot via `volatile`, locks, safely published immutable objects, or an appropriate happens-before mechanism.
- The fallback does not silently use the old cache if the cache is already invalidated.
- References already held by old callers are reclaimed/closed only according to a safe lifecycle.
- If the requirement is "no call may run fast after a transactional point in time", an additional protocol must coordinate in-flight calls.

`hasBeenInvalidated()` is useful for observation; it does **not** automatically make a sequence of operations atomic:

```java
// Illustrative snippet of check-then-act with a race condition:
if (!point.hasBeenInvalidated()) {
    useOldSnapshot();
}
```

The point can be invalidated between the `if` statement and `useOldSnapshot()`. Do not rely on this check as a complete barrier for multi-step transactions.

### 12.2. Do not invalidate on every request

`SwitchPoint` is built for **relatively stable assumptions** that are invalidated when a real event occurs. Creating and invalidating countless points on a hot path can increase overhead and complexity without benefit. If a condition changes continuously per input, use a predicate guard or a Java `if`.

Besides object creation and method handle chain overhead, invalidation can affect JIT/runtime optimizations depending on the implementation. There is no guarantee that `SwitchPoint` is always faster than a direct branch or `MutableCallSite`. Verify semantics first, then benchmark with a real workload.

## 13. Generation-based design: to become fast again, you need a new point

One design approach is for each **generation** to have its own snapshot, `SwitchPoint`, and guarded handle:

```text
Generation 1:
   snapshotV1
   pointV1 (valid)
   guardV1 = pointV1.guardWithTest(cachedV1, resolver)

Configuration update:
   invalidate(pointV1)
   guardV1 from now on uses resolver/fallback

Generation 2:
   build snapshotV2 and cachedV2
   pointV2 = new SwitchPoint()
   guardV2 = pointV2.guardWithTest(cachedV2, resolver)
   safely publish generation 2

Callers still holding guardV1: fallback.
Callers receiving guardV2: fast path while pointV2 is valid.
```

This diagram is a logical architecture, **not a complete concurrency implementation**. The order of invalidating, building, and publishing must match the system's consistency requirements. If users need strong consistency or zero downtime, you need to add version checks, double buffering, locks, or in-flight operation management.

A good fallback should:

1. Produce a correct result when the cache is completely expired.
2. Not accidentally call back into **the same invalidated old guard** in an infinite loop.
3. Keep the exact `MethodType` of the fast target.
4. Have a clear resolver error-handling path (reporting the cause, bounded retry if appropriate).
5. If designed to self-relink, take responsibility for updating the registry/callsite and safe publication.
6. Not publish the new generation before targets/adapters/snapshots are ready.

### 13.1. Comparison with relinking `MutableCallSite`

There are two valid models that are not identical:

- **Generation-based SwitchPoint:** invalidate V1, create `pointV2` and `guardV2`, publish the new handle/generation. Guard V1 continues to fall back.
- **MutableCallSite:** `setTarget(newTarget)` directly changes the target of the same CallSite object; it can continue switching to other targets as long as they have the same `MethodType` and sync is handled appropriately.

You can combine both, though it is not required. `SwitchPoint` easily expresses "permanently invalidate this assumption", while `MutableCallSite` easily expresses "this is the currently linked implementation". Choose based on the real lifecycle, not the API name.

### 13.2. One point can be used for multiple different types

Suppose a schema rule affects two operations:

```text
lookupUser:  (long)User
lookupOrder: (long)Order
```

You can build `guardUser = point.guardWithTest(userFast,userFallback)` and `guardOrder = point.guardWithTest(orderFast,orderFallback)`. `guardUser.type()` does not need to equal `guardOrder.type()`. Only **each** fast/fallback pair needs to have the same type. Invalidating that point affects both.

This is an advantage when managing a shared assumption, but also a risk if bundling many independent assumptions into one point makes invalidation overly broad.

## 14. Common errors and misconceptions

**1. "A SwitchPoint can be reset after invalidate."** False. The lifecycle is one-way; a new generation needs a new point.

**2. "SwitchPoint automatically detects Map/config changes."** False. The application must actively call `invalidateAll` when the assumption is broken.

**3. "A SwitchPoint guard evaluates a boolean predicate every time."** False. It uses the point's state; `MethodHandles.guardWithTest` is the one that takes a predicate handle.

**4. "Use SwitchPoint to distinguish VIP and guest users."** False if relying only on the point's state: every argument in the same epoch chooses the same branch. Per-user conditions must be checked separately.

**5. "Having the same number of arguments for target/fallback is enough."** False. Every argument type and the return type must match. `(String)Object` is not the same as `(String)String`.

**6. "`invokeExact` will automatically cast `Object` to `String`."** False. The call-site descriptor must be exact; cast the argument beforehand if the object is actually of that type, or use an adaptation API according to policy.

**7. "Invalidating a point also modifies the target of a CallSite."** False. A guard can change its behavior inside a `ConstantCallSite` while `getTarget()` remains unchanged.

**8. "`MutableCallSite` also only changes one way."** False. It can call `setTarget` multiple times to handles with the same `MethodType`, completely different from the SwitchPoint lifecycle.

**9. "After invalidate, all threads stop using fast even if they already entered target."** Not guaranteed under a transactional model. In-flight work must be handled separately.

**10. "`hasBeenInvalidated` guarantees subsequent code is consistent."** No. Check-then-act still has a race condition; it does not replace a synchronization protocol.

**11. "A `SwitchPoint` is equivalent to an entire cache invalidation framework."** No. The point is only a condition for method-handle guards; cache contents, registries, and resource lifecycles are your code's responsibility.

**12. "A guard always performs better than `if`."** There is no absolute guarantee. Performance depends on the JIT, invalidation frequency, handle shape, and workload.

**13. "If you invalidate again, there will be an intermediate branch."** False. A second invalidation does not reverse or create any new state.

**14. "Any MethodHandles using the same point must have the same signature."** False. Only target/fallback **within the same guard** need the same type; different guards can have different signatures.

**15. "Running the fallback means new data has automatically appeared."** False. The fallback must resolve/read a correct state itself according to the application contract.

## 15. Quick diagnostic table

| Symptom | First check | Resolution |
| --- | --- | --- |
| Guard always enters fast | Did you invalidate the exact **point instance** that the guard holds? | Check the point reference and `hasBeenInvalidated()`; avoid accidentally creating a different point |
| Guard always enters fallback | Was the point already invalid before use? | Create a new generation; do not reuse an invalidated point |
| Results are still old after invalidate | Are there in-flight calls? Does fallback use an old cache? Do callers hold a different guard? | Check dependencies/lifecycle and synchronization |
| `point.guardWithTest` throws `IllegalArgumentException` | Compare `target.type()`, `fallback.type()` | Fix the exact `MethodType` or add an explicit adapter |
| `MethodHandles.guardWithTest` throws `IllegalArgumentException` | Does `test.type()` return boolean and have matching prefix parameters? | Fix the test type and branch types |
| `invokeExact` throws `WrongMethodTypeException` | Caller's static argument types and return cast | Make the call-site descriptor match `guard.type()` |
| Lookup throws `IllegalAccessException` | Scope of `MethodHandles.Lookup` and Java modules | Fix the access contract, do not blame SwitchPoint |
| `MutableCallSite.setTarget` fails | New target type vs. `site.type()` | Normalize the target before setting |
| A thread does not observe the new target of MutableCallSite | Publication protocol, `syncAll` | Use proper Mutable/VolatileCallSite semantics |
| Memory retains many old snapshots | Registry/callers still hold old generations/guards | Manage lifecycle and reference retention safely |

## 16. Self-check questions

**Question 1.** What is `hasBeenInvalidated()` on `SwitchPoint point = new SwitchPoint();`?

**Answer:** `false`. A new point is valid; a guard created from it chooses `target` until it is invalidated.

**Question 2.** Does invalidating the same point twice re-enable the fast path?

**Answer:** No. A point is permanently invalidated; to get a new fast path, you must create a new point/guard.

**Question 3.** Two guarded handles are attached to the same point that gets invalidated. Do they both switch to fallback?

**Answer:** Yes. All guards depending on that point will choose `fallback` after invalidation according to the API semantics.

**Question 4.** Which guard is needed for a per-user predicate `isAdmin(String)`?

**Answer:** Use `MethodHandles.guardWithTest(test,target,fallback)` or a regular `if`. `SwitchPoint` does not inspect usernames itself and does not replace permission checks.

**Question 5.** Why cannot a target `(String)String` and a fallback `(String)Object` be passed directly to `point.guardWithTest`?

**Answer:** Their `MethodType`s have different return types; both branches must have the exact same type or a valid adapter.

**Question 6.** `guard.type()` is `(String)String`, but the caller passes `Object s = "A"` to `invokeExact`. What happens?

**Answer:** `WrongMethodTypeException` because the static caller argument type is `Object`, not `String`.

**Question 7.** Does invalidating a guard held in `ConstantCallSite` require changing `CallSite.getTarget()`?

**Answer:** No. The target reference remains the same guarded handle, but the logic inside the handle chooses `fallback`.

**Question 8.** Can `MutableCallSite` switch its target from fast to slow and back to fast?

**Answer:** Yes, if they have the same type and proper publication; unlike the one-way invalidation of `SwitchPoint`.

**Question 9.** Is a thread that already started the fast path before invalidation automatically cancelled?

**Answer:** No. `SwitchPoint` does not replace cancellation or a transaction barrier; you must add a concurrency protocol if needed.

**Question 10.** Does a new guard built from an **already invalidated** point return to the fast path?

**Answer:** No. It still uses that point's state; you need a new `SwitchPoint`.

**Question 11.** Can `test` of `MethodHandles.guardWithTest` return `int` to represent true/false?

**Answer:** No. It must return `boolean`.

**Question 12.** When should you use two `SwitchPoint`s instead of one?

**Answer:** When two assumptions are independent and invalidating one should not affect the guards of the other.

**Question 13.** What makes `SwitchPoint` advantageous for cache generations?

**Answer:** Multiple guarded handles can share one point for an assumption, and invalidation retires the old generation one-way, helping build a new generation cleanly.

**Question 14.** Does `SwitchPoint` automatically guarantee memory visibility of every Map/snapshot used by fast and fallback?

**Answer:** No. Data outside the guard still requires safe publication, synchronization, and proper ownership.

**Question 15.** Can two guards use the same point while having different `MethodType`s?

**Answer:** Yes. The equal-type rule only requires the target/fallback of **each guard** to match; different guards can have different signatures.

## 17. Extended practice

### Exercise A — Refreshing a cache version

Design a target `cachedPrice(String sku)` and fallback `resolvePrice(String sku)`, both of type `(String)long`. Let the `SwitchPoint` of snapshot V1 start valid, and call the guard to observe the fast path. When prices update, invalidate V1; call the old guard to observe the resolver. Then build snapshot V2, create point V2 and guard V2 so the new fast path works.

**Expectation:** point V1 cannot be reactivated; creating a new point V2 is the valid way. If there are multiple threads, snapshot/guard V2 must be published safely.

### Exercise B — Separating two assumptions

Create separate `pointForSchema` and `pointForPlugin`, each protecting two guards with matching types within each pair. Invalidate only schema: the plugin's guards stay on the fast path. Invalidate plugin: both groups now enter fallback, but due to **two separate events**.

**Expectation:** invalidation scope follows the point reference, not method names or a global registry.

### Exercise C — Comparing with an argument-based predicate

Create `isVip(String)` returning boolean and use `MethodHandles.guardWithTest` to choose `preferred`/`standard`. Use multiple usernames to illustrate the branch changing per input, without invalidating any object.

**Expectation:** a boolean test can be true/false on different calls. `SwitchPoint` is not a replacement tool for this.

## 18. Authoritative references

- Java SE 17, **`SwitchPoint`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/SwitchPoint.html — valid/invalidated state, `guardWithTest`, `invalidateAll`, `hasBeenInvalidated`.
- Java SE 17, **`MethodHandles.guardWithTest`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html — boolean test combinator, type constraints, lookup.
- Java SE 17, **`MethodHandle`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html — `invokeExact`, `asType`, method-handle types.
- Java SE 17, **`MethodType`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html — parameter list and return type.
- Java SE 17, **`CallSite`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/CallSite.html — `getTarget`, `dynamicInvoker`, method type.
- Java SE 17, **`ConstantCallSite`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/ConstantCallSite.html — immutable target.
- Java SE 17, **`MutableCallSite`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MutableCallSite.html — `setTarget`, `syncAll`, propagation.
- Java SE 17, **`VolatileCallSite`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VolatileCallSite.html — volatile semantics of target.
- Java Language Specification 17, **§17.4 Java Memory Model**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4 — concurrency, happens-before, synchronization.

**Conclusion:** `SwitchPoint` is a **one-way invalidation latch**, `MethodHandles.guardWithTest` is **branching by boolean predicate**, and `CallSite` is a **holder of a target for dynamic invocation**. They can be combined, provided you preserve the exact `MethodType`, assumption scope, concurrency boundaries, and how a new generation is created after invalidation.