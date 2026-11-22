# 18.5 GuardedInvocation: composing execution handle, guard, and invalidation conditions

`GuardedInvocation` is a central construct of **Dynalink** (`jdk.dynalink`): it wraps an **execution `MethodHandle`** (invocation) together with conditions that determine **when that handle is still appropriate** for the arguments and runtime state. Conditions can include a **guard handle returning `boolean`**, one or more **`SwitchPoint`s** that can be invalidated externally, and an **expected exception class** signaling that the current linkage is no longer applicable.

In short, `GuardedInvocation` expresses a proposal:

> "For this kind of object/situation, call this implementation; if the guard is not satisfied, the version is invalidated, or the implementation throws the specified exception type, switch to the fallback path to find or use a more suitable implementation."

Those constituent parts are packaged in **an immutable tuple** and can be combined into **a single `MethodHandle`** using `compose(...)`. When running through real Dynalink, `GuardingDynamicLinker.getGuardedInvocation(...)` typically supplies this tuple to `DynamicLinker`; a `RelinkableCallSite` uses it to build a call path with a fast path and a **relink-and-invoke** path when the conditions are no longer met.

**Distinguish immediately:** `GuardedInvocation` is **not** a `CallSite`, not an `invokedynamic` instruction on its own, and does not search for a new implementation by itself. It describes **a conditional choice**. Whether the fallback simply returns a value or actually **relinks** depends on the `MethodHandle` provided as the fallback and how `DynamicLinker`/the call site manages it.

> **Environment:** JDK 17 or later, module **`jdk.dynalink`**. The programs below run on the classpath with the commands `javac --release 17 --add-modules jdk.dynalink` and `java --add-modules jdk.dynalink`. All four complete examples were compiled and run, with stdout verified against actual output. In a project with `module-info.java`, you can use `requires jdk.dynalink;` in the module descriptor instead of forcing the classpath execution style of the examples.

## 1. Learning Objectives

After this lesson, you will be able to:

- Understand the role of `jdk.dynalink.linker.GuardedInvocation` in **dynamic linking**, especially between `GuardingDynamicLinker`, `DynamicLinker`, and `RelinkableCallSite`.
- Correctly read its four components: `invocation`, `guard`, `SwitchPoint[]`, and `Class<? extends Throwable> exception`.
- Grasp the meaning of `getInvocation()`, `getGuard()`, `getSwitchPoints()`, `getException()`, and `hasBeenInvalidated()`.
- Use `compose(fallback)` or `compose(guardFallback, switchpointFallback, catchFallback)` with handles of compatible types.
- Distinguish **guard false**, **switch point invalidated**, and **exception-based fallback**: they can all branch, but they do not share the same mechanism or state.
- Understand why `hasBeenInvalidated()` only reflects switch points, **not** guard false or caught exceptions.
- Use `replaceMethods(...)`, `addSwitchPoint(...)`, `asType(...)`, `dropArguments(...)`, and `filterArguments(...)` without losing the semantics of the attached conditions.
- Explain why a fast path needs conditions that check the right receiver/type/state and when relinking is useful.
- Build a real Dynalink pipeline yourself: a custom `GuardingDynamicLinker` returning `GuardedInvocation` for different receiver types, with `SimpleRelinkableCallSite` running and relinking when the guard fails.
- Diagnose mismatched `MethodType`, incompatible fallback, invalidated switchpoints, or linkers not handling an operation.

## 2. Where does guarded invocation sit in Dynalink?

**Dynalink** is a library in the JDK module `jdk.dynalink` that builds a mechanism for linking operations such as property reads, property writes, and function calls on objects with dynamic types. It can be used with the `invokedynamic` bytecode or invoked directly from an interpreter via the Java API.

The roles:

| Component | What is it? | Job |
| --- | --- | --- |
| `CallSiteDescriptor` | Metadata of the call site | Holds `Lookup`, `Operation`, and `MethodType` |
| `GuardingDynamicLinker` | Operation resolver provided by a framework/language | Inspects `LinkRequest`; if it understands the receiver/operation, returns `GuardedInvocation` |
| `GuardedInvocation` | Conditional tuple | Target implementation, guard, switch points, exception policy |
| `DynamicLinker` | Coordinator of linkers/fallbacks | Finds a suitable guarded invocation, supports relinking |
| `RelinkableCallSite` | Call site that receives and composes guarded invocations | Installs target `MethodHandle` with a fallback path for relinking |
| `SimpleRelinkableCallSite` | Monomorphic cache implementation | Holds a single active guarded invocation |
| `ChainedCallSite` | Polymorphic cache implementation | Holds a chain of guarded invocations to try multiple types |
| `SwitchPoint` | One-way invalidation signal | When invalidated, fast paths depending on it go to the fallback |

Conceptual flow:

```text
Client runs site with receiver (A)
          |
          v
RelinkableCallSite (no fast path yet)
          |
      relink fallback
          |
          v
DynamicLinker -> GuardingDynamicLinker
                    |
                    v
             GuardedInvocation
                invocation   -> handle executing A
                guard        -> matches receiver A?
                switchpoints -> configuration still fresh?
                exception    -> expected error requiring relink?
                    |
                    v
       Call site composes guarded handle + fallback
                    |
                calls fast path A

Later, a receiver of a different type (B):
      guard A returns false -> fallback -> linker selects B
                                               |
                                          GuardedInvocation B
                                               |
                                            updates site
```

An important rule: `GuardingDynamicLinker.getGuardedInvocation(request, services)` **can return `null`** when the linker does not handle the operation/receiver. `null` here does not mean "a guarded invocation with a null invocation": the `GuardedInvocation` constructor requires a non-null invocation.

### 2.1. "GuardedInvocation" does not attach itself to JVM `invokedynamic`

You can create one directly on your own:

```java
GuardedInvocation gi = new GuardedInvocation(target, test);
MethodHandle composed = gi.compose(fallback);
```

This is a **fragment**; the variables `target`/`test`/`fallback` are assumed to be initialized. It creates a **composite MethodHandle** in memory, without emitting `invokedynamic` bytecode and without creating a `CallSite`. In Dynalink, linking/relinking on guard failure is handled by the coordinator and the call site's fallback.

If a JVM `invokedynamic` has already bootstrapped into a `RelinkableCallSite` and the framework later replaces the target on guard failure, that is **Dynalink relink logic**. You should not think of this activity as the JVM being forced to re-run the bootstrap method to reset the linked state of the same opcode.

## 3. The four fields of `GuardedInvocation`

At a conceptual level:

```text
GuardedInvocation
  |
  +-- invocation: MethodHandle         [required]
  |
  +-- guard: MethodHandle              [optional, returns boolean]
  |
  +-- switchPoints: SwitchPoint[]      [optional, zero or more]
  |
  +-- exception: Class<? extends Throwable>
                                       [optional]
```

The corresponding getters:

```java
// Fragment: gi is a valid GuardedInvocation.
MethodHandle invoke = gi.getInvocation();
MethodHandle guard = gi.getGuard();             // may be null
SwitchPoint[] switches = gi.getSwitchPoints(); // may be null
Class<? extends Throwable> invalidating = gi.getException(); // may be null
boolean invalidated = gi.hasBeenInvalidated();
```

The tuple itself is considered **immutable**: replacing methods or adding a switch point produces a different `GuardedInvocation`. However, **a referenced `SwitchPoint` still has mutable state outside the tuple**: someone can call `SwitchPoint.invalidateAll(...)` and render the old tuple no longer valid.

### 3.1. Invocation: the execution fast path

`getInvocation()` returns the handle that **actually performs the work** while the current selection is still valid. For example:

```text
(String)String : value -> "fast:" + value
(Object)Object : obj -> ((Box)obj).name
```

The `MethodHandle` is usually obtained from `MethodHandles.Lookup.findStatic`, `findVirtual`, `asType`, or combinators. It has a very specific `MethodType`: parameter count and order, parameter types, and return type.

**Do not** assume `gi.getInvocation().invokeExact(...)` executes the guard on its own. If you invoke the invocation getter directly, you are **bypassing the guard, switchpoints, and fallback**, which can lead to a bad cast or behavior that is no longer appropriate. To apply all conditions, you must use the composite or let a Dynalink call site manage it.

### 3.2. Guard: checking whether the invocation applies to the current arguments

A guard is a `MethodHandle` returning **primitive `boolean`**. Typically, the guard takes the same parameters as the invocation, or a parameter prefix needed according to the `MethodHandles.guardWithTest` contract. For example:

```text
invocation : (Object)Object
guard      : (Object)boolean
fallback   : (Object)Object

guard(receiver) == true:
    invocation(receiver)

guard(receiver) == false:
    fallback(receiver)
```

If the guard distinguishes the receiver's class:

```java
static boolean isBox(Object receiver) {
    return receiver instanceof Box;
}
```

This is a **fragment**, requiring the `Box` class to be defined in the full code. After the guard passes, the target can cast `receiver` to `Box`. If the guard is false, it should go to the fallback to pick another target instead of casting and throwing `ClassCastException`.

**A guard is not a generic `Predicate` object**: Dynalink uses a `MethodHandle` with a compatible method type, and does not automatically treat a `Predicate` lambda as a guard. Nor is a guard a boolean computed **once at link time**. It can be invoked **on every execution of the composed path** when a decision is needed.

### 3.3. Switch points: whether the linked state is still fresh

`SwitchPoint` is a primitive in `java.lang.invoke` for signaling that **a shared condition has expired**. For example, the object model configuration changed, a property layout was modified, or an old optimization is no longer safe.

- A new `SwitchPoint` has `hasBeenInvalidated() == false`.
- `SwitchPoint.invalidateAll(new SwitchPoint[]{sp})` transitions it to **invalidated**.
- A `SwitchPoint` **cannot be revalidated**. To optimize again, create a new switch point and a new guarded invocation.
- When a guarded invocation contains **multiple switch points**, **only one** needs to be invalidated for `GuardedInvocation.hasBeenInvalidated()` to return `true`.
- When a composite contains an invalidated switch point, it takes the **switchpoint fallback**, skipping the guarded fast path.
- Invalidating does **not** automatically replace the target of a `CallSite` or invoke a linker if the fallback is just a normal method; the fallback decides what happens next.

**Do not confuse** a `SwitchPoint` being in the invalidated state with a `guard` returning false for a given input. A guard can return true on a later call if the receiver is different; an invalidated switchpoint stays **permanently invalidated**.

### 3.4. Exception class: signaling that the condition no longer fits

The optional exception parameter has type `Class<? extends Throwable>`. When the invocation throws an exception of the specified type, the composite can branch to the **catch fallback**, and in Dynalink that fallback usually leads to relinking.

For example, choosing `ClassCastException.class` when the fast path assumes the receiver has a particular class. This can be an optimization strategy when cast failures are rare and checking a guard on every call is expensive; however, it should only be done when the exception truly indicates an **assumption mismatch**.

**Important:**

- `gi.getException()` returns the configured class; **not** "the last exception that occurred".
- `gi.hasBeenInvalidated()` **only inspects switchpoints**, so a false guard or a caught exception **does not turn it into true**.
- An exception trigger can send **the current call** to the fallback/relink. The tuple itself has no memory of "caught once, so permanently invalidated".
- Do not declare `Exception.class`/`Throwable.class` indiscriminately: that can swallow programming/application bugs and cause an infinite relink loop.
- Do not treat every `ClassCastException` as a safe signal to relink: the exception might come from an internal bug in the implementation rather than a receiver type assumption.

## 4. Important constructors and getters

Constructors in the Java 17 API:

| Construction | Meaning |
| --- | --- |
| `new GuardedInvocation(invocation)` | Unconditional invocation: no guard/switch/exception |
| `new GuardedInvocation(invocation, guard)` | Guard-based validity |
| `new GuardedInvocation(invocation, switchPoint)` | Validity depends on a single switch point |
| `new GuardedInvocation(invocation, guard, switchPoint)` | Requires both guard and switch point |
| `new GuardedInvocation(invocation, guard, switchPoint, exception)` | Adds exception-based fallback |
| `new GuardedInvocation(invocation, guard, switchPoints, exception)` | Multiple switch points and exception policy |

`invocation` must not be null. `guard` may be null, `switchPoint` may be null, the `switchPoints` array may be null; the exception class may also be null. The guard needs a compatible method type according to `MethodHandles.guardWithTest` rules, in particular returning `boolean`.

Getters expose the elements so a resolver/call site can inspect, adapt, or compose them:

```java
// Fragment: no API automatically invokes the target inside the getters.
gi.getInvocation();
gi.getGuard();
gi.getSwitchPoints();
gi.getException();
gi.hasBeenInvalidated();
```

Seeing `getGuard()==null` does not automatically imply bad code: an **unconditional** invocation can be completely valid when the target always handles every receiver allowed by the descriptor. However, for a linker that only applies to `Box`, returning an unconditional target that **casts to Box** for a site receiving `Object` will be very dangerous when a new receiver changes to `String`.

## 5. Composing conditions with `compose`

Core API:

```java
MethodHandle complete = gi.compose(fallback);
```

This is a fragment. `fallback` is a `MethodHandle` responsible for accepting the exact arguments and having a return type matching `invocation`. This call uses **one shared fallback** for all three situations: guard false, switchpoint invalidated, or an exception of the configured type.

If you need to know the exact cause, use the overload:

```java
MethodHandle complete = gi.compose(
        guardFallback,
        switchpointFallback,
        catchFallback);
```

**Argument order matters**: `guardFallback` first, `switchpointFallback` second, `catchFallback` third. In Example 2, the three handles return distinct prefixes `guard:`, `switch:`, and `catch:` to verify this.

### 5.1. Control flow of the composite

```text
     invoked composite MethodHandle
                 |
                 v
        SwitchPoint still valid?
           |               |
          no              yes
           |               |
           v               v
  switchpointFallback   guard present?
                           |
                   +-------+-------+
                   |               |
                 false            true/none
                   |               |
                   v               v
             guardFallback     invocation
                                   |
                        exception configured?
                                   |
                          +--------+--------+
                          |                 |
                   type matches          normal
                          |                 |
                          v                 v
                     catchFallback        result
```

The diagram describes the typical logic of the composite. The implementation may use `MethodHandles.guardWithTest`, `SwitchPoint.guardWithTest`, and `catchException`; JVM optimization details are not public API.

If a switch point is invalidated, the composite can go straight to the switchpoint fallback before testing the guard; this is verified by Example 2 where the input `"skip-X"` picks `guard:` before invalidation, and `switch:` after invalidation.

### 5.2. `compose(fallback)` does not necessarily relink

If `fallback(String)` simply returns `"fallback:"+s`, the composite merely invokes it when the guard is false. It does **not** ask `GuardingDynamicLinker` again to pick a new invocation.

In a Dynalink pipeline, the fallback is typically a **relink-and-invoke handle** supplied by `DynamicLinker`. Therefore, when a guard fails, Dynalink can:

1. Inspect the current request and receiver.
2. Ask the `GuardingDynamicLinker`s to produce another `GuardedInvocation`.
3. Call `RelinkableCallSite.relink(...)`/`resetAndRelink(...)` to update the fast path.
4. Execute the operation on the receiver that just caused the guard miss.

The same `compose` with different fallbacks produces different behaviors. `GuardedInvocation` itself does not manage a monomorphic/polymorphic cache.

### 5.3. Conditions and actions table

| State | Composite with one fallback | Composite with three fallbacks | `hasBeenInvalidated()` |
| --- | --- | --- | --- |
| Guard passes, switchpoints valid, invocation does not throw trigger exception | Calls invocation | Calls invocation | `false` if no switchpoint has been invalidated |
| Guard false | Calls fallback | Calls guardFallback | Does not change because of guard false |
| Any switchpoint invalidated | Calls fallback | Calls switchpointFallback | `true` |
| Invocation throws configured exception type | Calls fallback | Calls catchFallback | Does not change *because of the exception*; still depends on switchpoints |
| Invocation throws exception not matching policy | Exception propagates to caller | Exception propagates to caller | Does not change on its own |

In real code, a fallback can still throw an exception; a guard can also have side effects or errors. Do not treat this table as a promise that every code path always returns a value.

## 6. Example 1 — Guard pass/fail and unconditional invocation

Create **`GuardComposeDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import jdk.dynalink.linker.GuardedInvocation;

public final class GuardComposeDemo {
    static String fast(String value) {
        return "fast:" + value;
    }

    static boolean accepts(String value) {
        return value.startsWith("ok");
    }

    static String fallback(String value) {
        return "fallback:" + value;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType type = MethodType.methodType(String.class, String.class);
        MethodHandle target = lookup.findStatic(GuardComposeDemo.class, "fast", type);
        MethodHandle guard = lookup.findStatic(GuardComposeDemo.class, "accepts",
                type.changeReturnType(boolean.class));
        MethodHandle otherwise = lookup.findStatic(GuardComposeDemo.class, "fallback", type);

        GuardedInvocation guarded = new GuardedInvocation(target, guard);
        MethodHandle composite = guarded.compose(otherwise);
        System.out.println("invocation type: " + guarded.getInvocation().type());
        System.out.println("guard type: " + guarded.getGuard().type());
        System.out.println("exception absent: " + (guarded.getException() == null));
        System.out.println("initially invalidated: " + guarded.hasBeenInvalidated());
        System.out.println("composite type: " + composite.type());
        System.out.println("accept: " + (String) composite.invokeExact("ok-A"));
        System.out.println("reject: " + (String) composite.invokeExact("no-B"));

        GuardedInvocation unconditional = new GuardedInvocation(target);
        MethodHandle plain = unconditional.compose(otherwise);
        System.out.println("no guard: " + (unconditional.getGuard() == null));
        System.out.println("unconditional: " + (String) plain.invokeExact("no-C"));
    }
}
```

Run:

```bash
javac --release 17 --add-modules jdk.dynalink GuardComposeDemo.java
java --add-modules jdk.dynalink GuardComposeDemo
```

**Verified stdout:**

```text
invocation type: (String)String
guard type: (String)boolean
exception absent: true
initially invalidated: false
composite type: (String)String
accept: fast:ok-A
reject: fallback:no-B
no guard: true
unconditional: fast:no-C
```

Explanation:

1. `fast` has type `(String)String`; `accepts` has type `(String)boolean`. The parameter counts/types match and the guard returns boolean.
2. `guarded.compose(otherwise)` creates a `(String)String` composite. With `"ok-A"` the guard is true, returning `fast:ok-A`.
3. With `"no-B"` the guard is false, invoking the fallback handle `otherwise` to return `fallback:no-B`.
4. `getException()==null` because no exception policy was configured; `hasBeenInvalidated()==false` because there is no invalidated switchpoint (in fact, no switchpoint at all).
5. `new GuardedInvocation(target)` creates an unconditional invocation, so the input `"no-C"` still calls the fast target. From `no guard: true`, you must not infer that this target is valid for every input **in every application**; in the example, `fast` only concatenates strings so there is no cast assumption.

### 6.1. Direct relation to `MethodHandles.guardWithTest`

A guarded invocation with only invocation+guard is essentially equivalent to composing:

```java
// Fragment: target, test, fallback have compatible MethodTypes.
MethodHandle composite =
        MethodHandles.guardWithTest(test, target, fallback);
```

`GuardedInvocation` adds switchpoints/exception metadata and unified transformation methods for both target/guard. Using the wrapper allows dynamic linkers to exchange a complete linkage proposal instead of inventing ad-hoc formats of three or four independent handles.

## 7. Example 2 — Guard fallback, switchpoint fallback, and catch fallback

This is the most common point of confusion: **the three condition types are not synonymous**. The example uses an execution method that throws `IllegalArgumentException` on input `"boom"`, a guard that rejects the prefix `"skip"`, and a `SwitchPoint` that can be invalidated externally.

Create **`InvalidateComposeDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.SwitchPoint;
import jdk.dynalink.linker.GuardedInvocation;

public final class InvalidateComposeDemo {
    static String execute(String value) {
        if (value.equals("boom")) throw new IllegalArgumentException("outdated");
        return "invoke:" + value;
    }

    static boolean guard(String value) {
        return !value.startsWith("skip");
    }

    static String onGuard(String value) {
        return "guard:" + value;
    }

    static String onSwitch(String value) {
        return "switch:" + value;
    }

    static String onCatch(String value) {
        return "catch:" + value;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType signature = MethodType.methodType(String.class, String.class);
        MethodHandle invocation = lookup.findStatic(
                InvalidateComposeDemo.class, "execute", signature);
        MethodHandle check = lookup.findStatic(
                InvalidateComposeDemo.class, "guard", signature.changeReturnType(boolean.class));
        MethodHandle guardFallback = lookup.findStatic(
                InvalidateComposeDemo.class, "onGuard", signature);
        MethodHandle switchFallback = lookup.findStatic(
                InvalidateComposeDemo.class, "onSwitch", signature);
        MethodHandle catchFallback = lookup.findStatic(
                InvalidateComposeDemo.class, "onCatch", signature);
        SwitchPoint switchPoint = new SwitchPoint();

        GuardedInvocation guarded = new GuardedInvocation(
                invocation, check, switchPoint, IllegalArgumentException.class);
        MethodHandle composite = guarded.compose(
                guardFallback, switchFallback, catchFallback);
        System.out.println("normal: " + (String) composite.invokeExact("ok"));
        System.out.println("guard false: " + (String) composite.invokeExact("skip-X"));
        System.out.println("expected exception: " + (String) composite.invokeExact("boom"));
        System.out.println("invalid after exception: " + guarded.hasBeenInvalidated());
        System.out.println("exception policy: " + guarded.getException().getSimpleName());

        SwitchPoint.invalidateAll(new SwitchPoint[]{switchPoint});
        System.out.println("invalid after switch: " + guarded.hasBeenInvalidated());
        System.out.println("switched: " + (String) composite.invokeExact("ok"));
        System.out.println("switch before guard: " + (String) composite.invokeExact("skip-X"));
    }
}
```

Commands:

```bash
javac --release 17 --add-modules jdk.dynalink InvalidateComposeDemo.java
java --add-modules jdk.dynalink InvalidateComposeDemo
```

**Exact stdout:**

```text
normal: invoke:ok
guard false: guard:skip-X
expected exception: catch:boom
invalid after exception: false
exception policy: IllegalArgumentException
invalid after switch: true
switched: switch:ok
switch before guard: switch:skip-X
```

### 7.1. Analyzing the three fallback paths

- **Normal:** `execute("ok")` returns `invoke:ok`.
- **Guard false:** `guard("skip-X")` returns false, so it goes to `onGuard`; the execution target does not need to be called.
- **Exception:** `execute("boom")` throws `IllegalArgumentException`; the composite catches **the exact configured type** and calls `onCatch`. The actual exception is not passed as the first parameter to `onCatch` in this example; the fallback receives the same `String` argument as the site.
- **Status:** After the exception, `guarded.hasBeenInvalidated()` remains false. This is what distinguishes an exception-triggered fallback from switchpoint state.
- **External invalidation:** `SwitchPoint.invalidateAll(...)` transitions the switch point to invalidated; `hasBeenInvalidated()` returns true from then on.
- **Switchpoint priority:** Both `"ok"` and `"skip-X"` calls select `onSwitch` after invalidation because the wrapper no longer allows running the guard/fast path.

### 7.2. Does an exception permanently "invalidate" the guard?

Not for a `GuardedInvocation` manually composed into a static handle like in the demo. The exception policy creates a **catch fallback when the exception matches**; it does not call `SwitchPoint.invalidateAll(...)` or record a permanent invalidated flag in the tuple. Thus, if the switchpoint is not invalidated, a new call with `"ok"` can still run `execute("ok")`, and a new call with `"boom"` throws the exception again and gets caught.

When the fallback is Dynalink's **relink-and-invoke**, an expected exception can lead to a relink process and replace/update the call site's target. That is **the behavior of the fallback and call site**, not a default state field of the tuple.

### 7.3. Multiple `SwitchPoint`s

You can use the constructor that accepts an array:

```java
// Fragment: invocation and guard are MethodHandles with compatible types.
GuardedInvocation gi = new GuardedInvocation(
        invocation, guard,
        new SwitchPoint[]{schemaSwitch, configSwitch},
        ClassCastException.class);
```

Either switchpoint being invalidated makes `gi.hasBeenInvalidated()` true. This condition corresponds to the idea "the fast path is only valid while **both schema and configuration** remain valid". There is no need to manually check both on every call if they are composed into the composite.

## 8. Immutable tuple and `GuardedInvocation` transformations

A `GuardedInvocation` has no `setInvocation(...)` to mutate the tuple directly. Instead, the Java 17 API provides:

| Method | Result / purpose |
| --- | --- |
| `replaceMethods(newInvocation, newGuard)` | Creates a new tuple with the new invocation/guard; preserves switchpoint(s) and exception policy |
| `addSwitchPoint(sp)` | Creates a new tuple adding a switchpoint (if `sp==null`, typically returns the current tuple) |
| `asType(MethodType)` | Adapts invocation and guard (if present) to the target signature; guard still returns boolean |
| `asType(LinkerServices, MethodType)` | Uses the conversion rules of linker services |
| `asTypeSafeReturn(LinkerServices, MethodType)` | Uses conversions without losing precision/magnitude for the return type |
| `asType(CallSiteDescriptor)` | Adapts according to the method type in the descriptor |
| `dropArguments(pos, types...)` | Adds unused arguments to invocation and guard accordingly |
| `filterArguments(pos, filters...)` | Applies corresponding filters to invocation and guard |

**Warning:** "Preserves switchpoint" does not mean copying out a new un-invalidated `SwitchPoint`. If two tuples reference the same switchpoint, invalidating that switchpoint can affect both. Conversely, `addSwitchPoint(extra)` does not add `extra` to the original tuple.

### 8.1. `asType` has two method types to watch

A `GuardedInvocation` has:

```text
invocation type: (String)String
guard type:      (String)boolean
```

After `gi.asType(MethodType.methodType(Object.class, String.class))`:

```text
invocation type: (String)Object
guard type:      (String)boolean
```

The guard's return type remains **boolean**; it does not turn the guard into `(String)Object` just because the invocation returns `Object`. If the guard only inspects a prefix of the parameter list, the adapter must maintain compatibility with the guard-composition mechanism. With `LinkerServices`, conversion capabilities also depend on the conversion rules registered by the linker, not arbitrary Java casts.

### 8.2. `dropArguments` does not delete existing context information

`dropArguments(0, int.class)` on a `(String)String` tuple turns the invocation into `(int,String)String`. The first `int` parameter is accepted but **ignored**. The corresponding guard also needs to accept the argument at a valid position so the composite can work.

Do not confuse the `dropArguments` method-handle combinator with `MethodType.dropParameterTypes` (which removes parameter types from a `MethodType`) or `insertArguments` (which binds fixed values, reducing the parameter count). Use it when a call site provides an extra context argument that the current fast implementation does not need.

### 8.3. `filterArguments` affects both guard and invocation

If you trim input `" ok-B "` before passing it to the target, the guard should also see the same `"ok-B"` value. `GuardedInvocation.filterArguments(0, trimHandle)` does that for both the invocation and guard at the corresponding position, avoiding the bug where the guard checks the unnormalized string while the target receives the normalized one.

Of course, the filter must have the right signature; a wrongly typed filter can cause adapter creation to fail. Detailed behavior when the guard has fewer parameters than the invocation is described in the API Javadoc.

## 9. Example 3 — `replaceMethods`, `addSwitchPoint`, `filterArguments`, `dropArguments`, and `asType`

Create **`GuardTransformDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.SwitchPoint;
import jdk.dynalink.linker.GuardedInvocation;

public final class GuardTransformDemo {
    static String first(String s) {
        return "v1:" + s;
    }

    static String second(String s) {
        return "v2:" + s;
    }

    static boolean guard(String s) {
        return s.startsWith("ok");
    }

    static String fallback(String s) {
        return "fallback:" + s;
    }

    static String normalize(String s) {
        return s.trim();
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType signature = MethodType.methodType(String.class, String.class);
        MethodHandle first = lookup.findStatic(GuardTransformDemo.class, "first", signature);
        MethodHandle second = lookup.findStatic(GuardTransformDemo.class, "second", signature);
        MethodHandle guard = lookup.findStatic(GuardTransformDemo.class, "guard",
                signature.changeReturnType(boolean.class));
        MethodHandle fallback = lookup.findStatic(GuardTransformDemo.class, "fallback", signature);
        MethodHandle filter = lookup.findStatic(GuardTransformDemo.class, "normalize", signature);
        SwitchPoint initialSwitch = new SwitchPoint();
        SwitchPoint extraSwitch = new SwitchPoint();
        GuardedInvocation original = new GuardedInvocation(first, guard, initialSwitch);
        GuardedInvocation changed = original.replaceMethods(second, guard);
        GuardedInvocation expanded = changed.addSwitchPoint(extraSwitch);
        System.out.println("same descriptor: "
                + original.getInvocation().type().equals(changed.getInvocation().type()));
        System.out.println("original target: "
                + (String) original.compose(fallback).invokeExact("ok-A"));
        System.out.println("changed target: "
                + (String) changed.compose(fallback).invokeExact("ok-A"));
        System.out.println("expanded switchpoints: " + expanded.getSwitchPoints().length);

        GuardedInvocation trimmed = expanded.filterArguments(0, filter);
        System.out.println("filter target: "
                + (String) trimmed.compose(fallback).invokeExact(" ok-B "));
        GuardedInvocation withContext = original.dropArguments(0, int.class);
        MethodHandle fallbackWithContext = MethodHandles.dropArguments(
                fallback, 0, int.class);
        System.out.println("dropped type: " + withContext.getInvocation().type());
        System.out.println("ignored context: " + (String) withContext.compose(
                fallbackWithContext).invokeExact(3, "ok-C"));
        MethodType widened = MethodType.methodType(Object.class, String.class);
        GuardedInvocation adapted = original.asType(widened);
        System.out.println("adapted type: " + adapted.getInvocation().type());
        System.out.println("adapted result: " + (Object) adapted.compose(
                fallback.asType(widened)).invokeExact("ok-D"));

        SwitchPoint.invalidateAll(new SwitchPoint[]{extraSwitch});
        System.out.println("original invalid: " + original.hasBeenInvalidated());
        System.out.println("expanded invalid: " + expanded.hasBeenInvalidated());
        System.out.println("expanded fallback: "
                + (String) expanded.compose(fallback).invokeExact("ok-E"));
        System.out.println("original still executes: "
                + (String) original.compose(fallback).invokeExact("ok-E"));
    }
}
```

Run:

```bash
javac --release 17 --add-modules jdk.dynalink GuardTransformDemo.java
java --add-modules jdk.dynalink GuardTransformDemo
```

**Verified stdout:**

```text
same descriptor: true
original target: v1:ok-A
changed target: v2:ok-A
expanded switchpoints: 2
filter target: v2:ok-B
dropped type: (int,String)String
ignored context: v1:ok-C
adapted type: (String)Object
adapted result: v1:ok-D
original invalid: false
expanded invalid: true
expanded fallback: fallback:ok-E
original still executes: v1:ok-E
```

Explanation:

1. `replaceMethods(second, guard)` creates tuple `changed`; tuple `original` still holds `first`.
2. `addSwitchPoint(extraSwitch)` creates `expanded`, with **two** switchpoints. Invalidating `extraSwitch` only affects tuples that contain that additional switchpoint; `original` and `changed` do not automatically receive `extraSwitch`.
3. `filterArguments(0, normalize)` trims the input on both guard and invocation. Hence `" ok-B "` becomes `"ok-B"` so the guard passes, and the output from `second` is `v2:ok-B`.
4. `dropArguments(0, int.class)` adds an ignored context argument to invocation/guard. The `(String)String` fallback must also be adapted to `(int,String)String`; it does not automatically drop the extra argument.
5. `asType((String)Object)` changes the invocation's return type; the guard still returns boolean. The fallback is adapted accordingly before composing.
6. After `invalidateAll(extraSwitch)`, `expanded.hasBeenInvalidated()` is true and goes to the fallback. `original` remains valid because it only has `initialSwitch`, which has not been invalidated.
7. These outputs show that **an immutable tuple does not mean a "deep copy" of all shared mutable state**: attached switchpoints can be invalidated externally in common.

## 10. Real Dynalink: `GuardingDynamicLinker` producing GuardedInvocation for dynamic receivers

The previous three examples manually called `new GuardedInvocation(...)` and `compose(...)`. To see how it works in **Dynalink**, let's try a `GET PROPERTY "label"` operation on two receiver types: `Box` and `String`.

In the sample pipeline:

- `CallSiteDescriptor` stores `Lookup`, the operation, and the `(Object)Object` signature.
- `DynamicLinkerFactory` is configured with a **prioritized custom linker**.
- `SimpleRelinkableCallSite` holds a single fast path, fitting the **monomorphic cache** model.
- When receiving `Box` first, the linker returns invocation `boxValue` + guard `isBox`.
- When receiving `String`, guard `isBox` fails; Dynalink uses the fallback to call the custom linker again, obtains invocation `stringValue` + guard `isString`, and updates the site.
- When switching back to `Box`, `SimpleRelinkableCallSite` has already replaced the previous fast path, so it must relink again.

This illustrates that **a guard is a linking condition**, while Dynalink's fallback is **a path to refresh linkage at runtime**, not an ordinary string-formatted fallback.

### 10.1. Example 4 — Custom linker, guard miss, and monomorphic relink

Create **`DynalinkPipelineDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import jdk.dynalink.CallSiteDescriptor;
import jdk.dynalink.DynamicLinker;
import jdk.dynalink.DynamicLinkerFactory;
import jdk.dynalink.StandardNamespace;
import jdk.dynalink.StandardOperation;
import jdk.dynalink.linker.GuardedInvocation;
import jdk.dynalink.linker.GuardingDynamicLinker;
import jdk.dynalink.support.SimpleRelinkableCallSite;

public final class DynalinkPipelineDemo {
    static final class Box {
        final String name;
        Box(String name) { this.name = name; }
    }

    static Object boxValue(Object object) {
        return "box:" + ((Box) object).name;
    }

    static boolean isBox(Object object) {
        return object instanceof Box;
    }

    static Object stringValue(Object object) {
        return "text:" + object;
    }

    static boolean isString(Object object) {
        return object instanceof String;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType type = MethodType.methodType(Object.class, Object.class);
        MethodType guardType = type.changeReturnType(boolean.class);
        MethodHandle boxHandle = lookup.findStatic(
                DynalinkPipelineDemo.class, "boxValue", type);
        MethodHandle boxGuard = lookup.findStatic(
                DynalinkPipelineDemo.class, "isBox", guardType);
        MethodHandle stringHandle = lookup.findStatic(
                DynalinkPipelineDemo.class, "stringValue", type);
        MethodHandle stringGuard = lookup.findStatic(
                DynalinkPipelineDemo.class, "isString", guardType);

        int[] linkRequests = {0};
        GuardingDynamicLinker custom = (request, services) -> {
            Object receiver = request.getReceiver();
            if (receiver instanceof Box) {
                linkRequests[0]++;
                return new GuardedInvocation(boxHandle, boxGuard);
            }
            if (receiver instanceof String) {
                linkRequests[0]++;
                return new GuardedInvocation(stringHandle, stringGuard);
            }
            return null;
        };

        DynamicLinkerFactory factory = new DynamicLinkerFactory();
        factory.setPrioritizedLinkers(custom);
        DynamicLinker linker = factory.createLinker();
        CallSiteDescriptor descriptor = new CallSiteDescriptor(
                lookup, StandardOperation.GET.withNamespace(
                        StandardNamespace.PROPERTY).named("label"), type);
        SimpleRelinkableCallSite site =
                linker.link(new SimpleRelinkableCallSite(descriptor));
        MethodHandle invoke = site.dynamicInvoker();
        System.out.println("site type: " + site.type());
        System.out.println("first box: "
                + (Object) invoke.invokeExact((Object) new Box("A")));
        System.out.println("links after box: " + linkRequests[0]);
        System.out.println("second box: "
                + (Object) invoke.invokeExact((Object) new Box("B")));
        System.out.println("links after same type: " + linkRequests[0]);
        System.out.println("first string: "
                + (Object) invoke.invokeExact((Object) "Hello"));
        System.out.println("links after string: " + linkRequests[0]);
        System.out.println("second string: "
                + (Object) invoke.invokeExact((Object) "World"));
        System.out.println("links after same string type: " + linkRequests[0]);
        System.out.println("back to box: "
                + (Object) invoke.invokeExact((Object) new Box("C")));
        System.out.println("links after switch back: " + linkRequests[0]);
    }
}
```

Run:

```bash
javac --release 17 --add-modules jdk.dynalink DynalinkPipelineDemo.java
java --add-modules jdk.dynalink DynalinkPipelineDemo
```

**Verified stdout:**

```text
site type: (Object)Object
first box: box:A
links after box: 1
second box: box:B
links after same type: 1
first string: text:Hello
links after string: 2
second string: text:World
links after same string type: 2
back to box: box:C
links after switch back: 3
```

### 10.2. Why does the second call of the same type not relink?

The `Box("B")` call enters the existing fast path:

```text
guard isBox("Box B") -> true
    |
    v
boxValue(...) -> "box:B"
```

There is no need to ask the custom linker again, so the count stays at 1. When `"Hello"` arrives, guard `isBox` returns false, so the fallback of `SimpleRelinkableCallSite`/`DynamicLinker` selects the `String` strategy and the count becomes 2. When `Box("C")` arrives, the monomorphic cache is holding the String path, so the guard fails and the count becomes 3.

These counts are **the number of times the custom linker produced a GuardedInvocation** in the single-threaded demo, not the number of times a JVM bootstrap method ran. The program creates `SimpleRelinkableCallSite` directly in Java source, **without emitting an `invokedynamic` opcode**.

### 10.3. An intentional limitation of the custom linker

The custom linker in the demo is only tested on **one** descriptor for `GET PROPERTY "label"`. It chooses the target based on **receiver type** and does not check `request.getCallSiteDescriptor().getOperation()`. In real production code, a `GuardingDynamicLinker` usually must verify operation/name/namespace before handling the request. Otherwise, the linker might accidentally apply the property `label` lookup logic to another operation such as `CALL` or `SET`.

If it receives a receiver other than `Box`/`String`, the custom linker returns null so other linkers in the factory can try handling it. Dynalink has a standard `BeansLinker` fallback; an operation not handled by any linker at all can lead to `NoSuchDynamicMethodException`. Do not replace `return null` with a fake tuple containing a null invocation.

### 10.4. `SimpleRelinkableCallSite` and `ChainedCallSite`

- `SimpleRelinkableCallSite` stores one guarded invocation as the target at a time, convenient when the receiver is usually of the same type. When switching `Box → String → Box`, it will replace the fast path multiple times.
- `ChainedCallSite` can hold **a chain** of linked invocations, typically supporting a polymorphic inline cache. Switching receivers among several familiar types can pass through multiple guards in the chain instead of running the linker every time.
- Both are **implementations of `RelinkableCallSite`**. The choice affects caching/performance, while `GuardedInvocation` remains the unit of contract returned from `GuardingDynamicLinker`.
- When a `SwitchPoint` is invalidated, a cache can discard/stop using the old guarded invocation and call the linker to create a new tuple.

Do not assume every `ChainedCallSite` caches infinitely: the chain has implementation-specific limits and relink/reset policies.

## 11. `MethodHandle` types are a mandatory contract

Common signature table:

| Role | Example MethodType |
| --- | --- |
| Dynamic call site | `(Object)Object` |
| Target for `Box` receiver | `(Object)Object` |
| Guard `isBox` | `(Object)boolean` |
| Relink fallback | `(Object)Object` |
| Call site receiving extra context | `(int,Object)Object` |
| Guard if only checking the first receiver | Can be a matching prefix, still must obey guardWithTest/adaptation |

If the actual target has type `(Box)String` while the call site takes `(Object)Object`, it can be adapted via `MethodHandle.asType` or `LinkerServices.asType`. However, the `Object→Box` cast can fail; the guard must enforce the right condition and appropriate type. Dynalink's `LinkerServices` provides specialized type conversion mechanisms for language runtimes, as not all conversions are ordinary JVM casts.

### 11.1. Read signatures before composing

Before debugging logic, print:

```java
// Fragment: target, guard, and fallback already exist.
System.out.println(target.type());
System.out.println(guard.type());
System.out.println(fallback.type());
```

With `invokeExact`, **the static types at the Java call site** (including the return type from the cast) must also match. `WrongMethodTypeException` can occur if invoking a handle with the wrong signature; `IllegalArgumentException` can occur when trying to compose incompatible handles. Do not treat these errors as "guard false" or "relink request".

### 11.2. Guards must check enough assumptions, not be overly broad

If the invocation casts the receiver to `ArrayList`, a guard that only tests `receiver instanceof List` is **too broad** because there are other `List`s that are not `ArrayList`. Consequence: the guard passes, but the target throws `ClassCastException`. You can check `receiver instanceof ArrayList` or design the invocation to accept `List` if it genuinely supports all relevant subtypes.

Conversely, a guard `receiver.getClass() == ExactClass.class` is sometimes too narrow if the logic also safely handles subclasses. Choose a guard tied to the target's **real assumptions**, not just a microbenchmark optimization.

### 11.3. Guards should have minimal side effects

Guards run on the hot path; side effects (global counters, I/O, mutation) can make behavior unpredictable, especially when the compiler/JVM optimizes `MethodHandle`s or when multiple threads access them concurrently. Keep guards fast, pure, and based on state with proper memory visibility.

If caching depends on **schema/layout/config** that changes asynchronously, `SwitchPoint` is usually a better signal than having the guard perform I/O or read complex configuration every time.

## 12. Diagram of an invalidation/relink strategy

Suppose the runtime has a "schema version" that affects how properties are read. When the schema changes, the old invocation is no longer valid.

```text
Version 1:
   GuardedInvocation v1
       invocation: readPropertyV1
       guard:      receiver instanceof Record
       switch:     schemaV1Switch

   call site -> composed v1 -> readPropertyV1

Schema updated:
   SwitchPoint.invalidateAll([schemaV1Switch])

Next call:
   composed v1 -> switchpointFallback -> DynamicLinker
                                           |
                                      create v2 handles
                                           |
                                      new SwitchPoint v2
                                           |
                                      GuardedInvocation v2
                                           |
                                      call site relink
                                           |
                                      readPropertyV2
```

**Note:** `SwitchPoint.invalidateAll(...)` **does not create v2 by itself**. That is the responsibility of **fallback + linker**. If the code uses `compose(plainFallback)` and `plainFallback` only returns a default value, every subsequent call after invalidation will continue returning that value; there is no magic re-link.

### 12.1. Invalidating multiple sites on a single event

If multiple guarded invocations depend on one schema, they can share the same `SwitchPoint`. When the schema changes, invalidating that single object sends all related handles to their fallback. This is an effective invalidation tool, though it requires lifetime/ownership management:

- Do not share a `SwitchPoint` across independent assumptions if a change does not need to invalidate every cache.
- An invalidated switchpoint cannot be reused for a new version; create a new one.
- If multiple threads update the schema and invoke the site, publish state/caches consistently according to the Java Memory Model, rather than treating invalidate as a global transaction.
- An invocation may already be executing on the old target at the moment of invalidation; invalidation does not forcibly abort code already in flight.

### 12.2. Exception-based relink should only be for expected errors

For instance, when varied receivers cause cast assumptions to fail occasionally, a linker might choose `ClassCastException.class` as the invalidating exception. However:

- First, the exception path is usually expensive if failures happen continuously; an explicit guard may be better.
- Second, the exception must carry the right meaning: an unexpected NPE or a bug in the target should not turn into an infinite relink attempt.
- Third, `hasBeenInvalidated()` does not track prior exception events; if you want tracking, place metrics inside the fallback/linker.
- Fourth, an exception can be caught inside the target before escaping, so the catch fallback **will not see** it; only exceptions escaping through the composite and matching the type trigger this branch.

## 13. Common pitfalls and anti-patterns

| Symptom | Why it happens | How to fix |
| --- | --- | --- |
| `ClassNotFoundException` or "package jdk.dynalink not visible" | Module `jdk.dynalink` is not resolved/required | Add `--add-modules jdk.dynalink` in the classpath examples or `requires jdk.dynalink;` in the module |
| `NullPointerException` when creating `GuardedInvocation` | Invocation handle is null | Always provide a valid `MethodHandle`; if a linker cannot handle the request, return `null` |
| `IllegalArgumentException` during compose | Guard/fallback/target method types are incompatible | Print `MethodHandle.type()`, adapt intentionally |
| `WrongMethodTypeException` on `invokeExact` | Java call site is statically typed with wrong parameter/return types | Cast the return type accurately; verify the signature |
| `ClassCastException` after guard passes | Guard is too broad or argument filter is wrong | Guard must check the exact assumption of the target |
| Every receiver is routed to the same target by the linker | Custom linker does not check operation/receiver | Verify `LinkRequest.getCallSiteDescriptor()` and `getReceiver()` |
| Guard false but linker never runs | Fallback is just a handle returning a default value | Install the relink-and-invoke path provided by Dynalink |
| `hasBeenInvalidated()==false` after catch fallback | Getter only reflects switchpoints | Track exception events via metrics/fallback if needed |
| Switchpoint invalidated yet invocation still called directly | `getInvocation()` bypasses guards | Invoke the composite/call site; do not bypass validity |
| Still using old cached version after invalidation | Fallback does not relink or new reference not published | Check `RelinkableCallSite.relink` and visibility |
| `SwitchPoint` cannot be restored | One-way invalidation | Create a new `SwitchPoint` + new `GuardedInvocation` |
| `addSwitchPoint` called yet original is unaffected | Immutable tuple | Keep the returned tuple reference |
| `replaceMethods` causes guard to evaluate wrong type | Replaced target without adapting guard | Use `asType`/a guard compatible with the new invocation |
| `filterArguments` causes guard and target to see different inputs | Filters or input assumptions are inconsistent | Apply matching filters to both via the tuple API |
| After `dropArguments`, compose fallback has wrong arity | Fallback does not accept the new context parameters | `MethodHandles.dropArguments` on the fallback |
| Too many relinks when receiving Box/String alternately | `SimpleRelinkableCallSite` is a monomorphic cache | Consider `ChainedCallSite` if the workload is polymorphic |
| No relink when using `ChainedCallSite` for a few familiar types | Guarded invocations remain valid in the chain | Understand cache hits; do not equate "every call" with a link request |
| Using `Throwable.class` as invalidating exception | Catches programming/fatal errors as well | Choose a narrow exception representing a stale assumption |
| `getSwitchPoints()` returns null | Tuple has no switchpoints | Handle null; do not call `.length` unconditionally |
| Using `GuardedInvocation` for security/sandboxing | Guard is only a dispatch condition | Enforce access control in a separate Java/module/classloader layer |

### 13.1. Avoiding fallback loops

A linker that only knows how to handle `Box`, yet returns a guard that is always false for `Box` itself, can cause the fallback to request relinking **repeatedly**. Symptoms may be high CPU, stack overflow, or degraded throughput. Check:

1. Does the linker return an invocation suitable for the actual request?
2. Does the newly created guard pass for the current receiver?
3. Does the `MethodType` match the descriptor?
4. Is the switchpoint **already invalidated** at the time the tuple is returned?
5. Is an expected exception thrown **every time** by the invocation?
6. Can the fallback exit when no linker handles the operation?

Dynalink provides the logic to manage relinking, but it cannot fix a guard that is always false or an assumption that never becomes true.

### 13.2. "Guarded" is not an authorization mechanism

In a dynamic runtime, a guard `receiver instanceof AdminObject` does not grant admin privileges, does not validate a session, and does not enforce business access control. It only determines **whether the `MethodHandle` fast path applies**.

If the target method performs a privileged action, check authorization inside the appropriate domain/security layer, rather than relying only on a guard/`SwitchPoint` to prevent an untrusted caller from invoking the method directly.

### 13.3. The fallback's `MethodType` must be right *after* all adapters

If GI `original` has target `(String)String`, but `dropArguments(0,int.class)` produces target `(int,String)String`, a fallback that is still `(String)String` will not satisfy the compose contract. Example 3 intentionally does:

```java
MethodHandle fallbackWithContext =
        MethodHandles.dropArguments(fallback, 0, int.class);
```

This is a fragment. Do not arbitrarily cast a `MethodHandle` to a generic type because a Java method handle is a typed invocation at runtime; you need the proper combinator.

## 14. Distinguishing three layers of "invalidation"

| Mechanism | Trigger condition | Persistence | Action in composite | When used in Dynalink |
| --- | --- | --- | --- | --- |
| **Guard failure** | Current input fails the guard | Per-invocation; next call may pass | Guard fallback | Relink for another receiver or choose another path |
| **SwitchPoint invalidation** | Owner invalidates switchpoint externally | One-way, applies to subsequent calls | Switchpoint fallback | Stale schema/cache/config; must establish a new path |
| **Invalidating exception** | Target throws declared exception | Per-invoke; tuple does not record a permanent flag | Catch fallback | Linker revises assumption after expected failure |

Treat all three as **ways of expressing "the fast path is no longer suitable"** with **different properties and effects**. Do not use `hasBeenInvalidated()` to count all of them.

### 14.1. Similar Java tools that are not complete replacements

- `MethodHandles.guardWithTest`: a choice between two handles based on a guard; does not carry metadata for multiple switchpoints and an exception policy.
- `SwitchPoint.guardWithTest`: a one-way guard based on invalidation; does not contain a generic receiver-specific guard.
- `MethodHandles.catchException`: catches an exception type and calls a handler; does not know Dynalink relink semantics.
- `GuardedInvocation.compose`: combines all three condition types with the invocation into a composite for the runtime linker.
- `RelinkableCallSite.relink`: receives a guarded invocation from Dynalink and installs the new path; not a `GuardedInvocation` constructor.

Which combination fits depends on the language/framework's dynamic model; `GuardedInvocation` is convenient when you want to represent **a complete, exchangeable linkage proposal** between components.

## 15. Guided Extension Exercises

**Exercise A — Receiver-based guard:** Modify `DynalinkPipelineDemo` to also accept `Integer` and return `"number:"+value`. Hint: add a target handle, an `instanceof Integer` guard, and a branch in the linker; observe `linkRequests` on the sequence Box → String → Integer → Box.

**Exercise B — Schema version:** Create a `SwitchPoint` attached to the `GuardedInvocation` handling `Box`. After `SwitchPoint.invalidateAll`, ensure there is a relink fallback path that creates a new `SwitchPoint`, otherwise the site will always take the old fallback. Check `hasBeenInvalidated()` before/after.

**Exercise C — Exception policy:** Try changing `IllegalArgumentException.class` to `ClassCastException.class` in Example 2; predict the result of `composite.invokeExact("boom")`. Why is the exception no longer handled by the catch fallback? Try an expected exception that genuinely represents a stale assumption.

**Exercise D — Polymorphic cache:** Replace `SimpleRelinkableCallSite` with `ChainedCallSite` in Demo 4, keeping the same descriptor and linker. Compare the number of linkings when alternating among several receiver types after the program warms up; keep the chain limit policy in mind.

**Exercise E — Handle types:** Change the call site's `(Object)Object` to `(Object)String`, and adapt the invocation/guard accordingly. Observe the error if you still return the target with the old type. Explain why `asType` is literally part of the linking contract.

## 16. Self-check Questions

1. Is `GuardedInvocation` a `CallSite`, a `MethodHandle`, or a metadata tuple?
2. Which component of `GuardedInvocation` must be non-null?
3. What type does a guard return, and how must it be compatible with the invocation's parameters?
4. Does `getInvocation()` automatically check `getGuard()`?
5. Distinguish `compose(fallback)` from `compose(guardFallback, switchpointFallback, catchFallback)`.
6. When the guard is false, does `hasBeenInvalidated()` automatically become true?
7. When the invocation throws the invalidating exception, does `hasBeenInvalidated()` automatically become true?
8. When one of two switchpoints is invalidated, what does `hasBeenInvalidated()` return?
9. Can an invalidated `SwitchPoint` be reset to valid?
10. If `compose` uses a fallback that only returns a default value, does Dynalink necessarily relink?
11. Why does `replaceMethods` return a new `GuardedInvocation` instead of mutating the original tuple?
12. Does `addSwitchPoint(extra)` automatically add `extra` to the original tuple?
13. Why does `filterArguments` need to transform both the guard and the invocation at the corresponding positions?
14. How does `dropArguments(0,int.class)` affect the fallback type?
15. In `DynalinkPipelineDemo`, why do two consecutive calls with `Box` only create one `GuardedInvocation`?
16. Why does alternating `Box → String → Box` on `SimpleRelinkableCallSite` trigger three link requests in the demo?
17. How does `ChainedCallSite` differ from `SimpleRelinkableCallSite` in caching strategy?
18. If a custom linker does not understand the receiver/operation, what should it return from `getGuardedInvocation`?
19. Which module is `jdk.dynalink` part of? For a Java 17 classpath application, which option is used in the example commands?
20. Is a `ClassCastException` caused by an implementation bug always a valid reason to trigger a relink?

### Suggested Answers

1. It is a **tuple** describing an invocation with validity conditions; `compose` is what creates the composite `MethodHandle`.
2. `invocation`; the remaining conditions are optional.
3. Primitive `boolean`, with parameters compatible with the invocation per `guardWithTest`.
4. No; calling the invocation getter directly can bypass the guard/switchpoint.
5. One shared fallback; the three-fallback overload separates guard/switch/exception.
6. No, it is only a per-input decision.
7. No; this flag only observes switchpoints.
8. `true`, because only one invalidated switchpoint is needed.
9. No; create a new `SwitchPoint`.
10. No; only a proper Dynalink relink-and-invoke fallback causes relinking.
11. The tuple is immutable; to change methods, a new object is created.
12. No; only the returned tuple has the added switchpoint.
13. So that the guard and target see the same data transformation, avoiding mismatched assumptions.
14. The new target is `(int,String)String`, so the fallback also needs to adapt to that call signature.
15. Guard `isBox` still passes, resulting in a cache hit.
16. A monomorphic cache replaces the single current guarded invocation when the receiver class changes.
17. `ChainedCallSite` can hold multiple guarded invocations in a chain.
18. Return `null` to let other linkers try; do not return a `GuardedInvocation` with a null invocation.
19. Module `jdk.dynalink`; in the classpath examples, `--add-modules jdk.dynalink` is used.
20. No; you must ensure the exception genuinely marks an assumption mismatch, avoiding swallowed bugs and relink loops.

## 17. Official References

- [Java SE 17 API — `GuardedInvocation`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/linker/GuardedInvocation.html): constructors, getters, `hasBeenInvalidated`, `compose`, `replaceMethods`, `addSwitchPoint`, and adapters.
- [Java SE 17 API — `GuardingDynamicLinker`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/linker/GuardingDynamicLinker.html): `getGuardedInvocation` contract, returning `null`, and relink requests.
- [Java SE 17 API — module `jdk.dynalink`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/module-summary.html): purpose, operation model, lifecycle, Dynalink in bytecode/interpreters.
- [Java SE 17 API — `DynamicLinkerFactory`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/DynamicLinkerFactory.html) and [`DynamicLinker`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/DynamicLinker.html): creating/linking call sites, prioritized linkers, fallback resolution.
- [Java SE 17 API — `SimpleRelinkableCallSite`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/support/SimpleRelinkableCallSite.html) and [`ChainedCallSite`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/support/ChainedCallSite.html): monomorphic and polymorphic inline caches.
- [Java SE 17 API — `RelinkableCallSite`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/RelinkableCallSite.html): `relink`, `resetAndRelink`, `initialize`, and relink-and-invoke fallback.
- [Java SE 17 API — `SwitchPoint`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/SwitchPoint.html): `guardWithTest`, invalidation, and visibility semantics.
- [Java SE 17 API — `MethodHandles`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html): `guardWithTest`, `filterArguments`, `dropArguments`, `catchException`.
- [Java SE 17 API — `MethodHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html): `invokeExact`, `MethodType`, and adapter semantics.

**Summary:** `GuardedInvocation` is **invocation + guard + switchpoint invalidation + exception fallback policy**. `compose` turns that tuple into a method handle with a fast path/fallback. Guard false and exceptions only decide per-call; `hasBeenInvalidated()` detects **one-way switchpoint invalidation**, not every kind of failure. When placed in Dynalink, `GuardingDynamicLinker` produces the guarded invocation and `RelinkableCallSite` turns a guard miss/invalidation into an opportunity to **select a new target**. Always verify method types, guard conditions, and the actual fallback instead of assuming the tuple relinks automatically.