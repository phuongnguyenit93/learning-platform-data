# 12.2. ConstantCallSite and Fixed Call Targets

## Learning Objectives

After this lesson, you can:

- Distinguish **MethodHandle** (a callable handle), **CallSite** (a linkage point holding a target handle), and **ConstantCallSite** (a linkage point with a permanent target).
- Create a `ConstantCallSite` from a `MethodHandle` and verify `type()`, `getTarget()`, and `dynamicInvoker()`.
- Correctly explain the meaning of **constant**: *the target handle/reference does not change*; the execution result and data inside the target method **do not have to be immutable**.
- Understand why `setTarget(...)` is always prohibited, even when the new method has a compatible signature.
- Describe the role of `ConstantCallSite` when the JVM links an `invokedynamic` instruction via a bootstrap method, including the `MethodType` matching requirement.
- Identify common errors: `NullPointerException` when the target is null, `WrongMethodTypeException` when the call site/handle does not match, errors from a bootstrap hook, and access permissions when creating a handle.
- Know when to use `MutableCallSite` or `VolatileCallSite` instead of trying to change the target of a `ConstantCallSite`.

## 1. Context: How Do MethodHandle, CallSite, and invokedynamic Differ?

In Java, a `MethodHandle` is an object referencing a callable operation: a method, constructor, field operation, or a combination of adapters. Each handle carries a **`MethodType`**, consisting of a parameter type list and a return type.

For example, a handle for `static int add(int, int)` has the type:

~~~text
(int,int)int
~~~

A handle is the **execution target**. However, `invokedynamic` in bytecode does not directly store the target Java method name like a normal `invokestatic` call. It has a **dynamic linkage** step performed by the JVM and a bootstrap method; the linkage result is typically a `CallSite`.

One way to view it:

~~~text
invokedynamic instruction in bytecode
             |
             | linked by bootstrap method
             v
           CallSite
             |
             | getTarget()
             v
         MethodHandle
             |
             v
      Execution operation
~~~

Each element holds a distinct role:

| Component | What it represents | What can be stable or change? |
| --- | --- | --- |
| `MethodHandle` | A callable object carrying a `MethodType` | The handle is a value; the logic behind the handle can still read mutable state |
| `CallSite` | The linkage point between a dynamic invocation and a target handle | Depending on the subclass, the target may be fixed or changeable |
| `ConstantCallSite` | A CallSite with a **permanent target** | The target cannot be changed after construction completes |
| `MutableCallSite` | A CallSite whose target can be updated | Can call `setTarget`; requires attention to cross-thread publication |
| `VolatileCallSite` | A CallSite whose target is updated with volatile semantics | Useful when cross-thread update visibility is needed per the API contract |

**Important:** `CallSite` is not `java.lang.reflect.Method`. `Method` provides Reflection metadata and its own `invoke` operation; `CallSite` is tied to the `java.lang.invoke` mechanism and call linkage.

### 1.1. At What Level Is It “Constant”?

`ConstantCallSite` does **not** mean:

- The target method must be `static final`.
- The target method must return a constant.
- The arguments are frozen.
- Every call must return the same result.
- The call will have no side effects.
- The JIT is guaranteed to inline it, or every call has zero overhead.

It only guarantees that **the call site's target MethodHandle value is fixed**. When the target points to the `add` method, `add(6,7)` and `add(10,20)` still produce two different results. If the target is bound to a receiver that has a mutable field, the result can change even though the target handle has never changed.

## 2. Core API of ConstantCallSite

In Java SE 17, the class resides in `java.lang.invoke.ConstantCallSite`, which is a subclass of `CallSite`. The common constructor:

~~~java
// API signature for reference, not a standalone code snippet:
public ConstantCallSite(MethodHandle target);
~~~

A **non-null** `MethodHandle` object is a mandatory condition. If the target is `null`, the constructor throws `NullPointerException`.

The methods users typically need:

| API | Value/behavior | Notes |
| --- | --- | --- |
| `site.type()` | `MethodType` of the target | Includes the return type |
| `site.getTarget()` | The target handle assigned at construction | Does not change after the constructor completes |
| `site.dynamicInvoker()` | Returns **the permanent target itself** | For `ConstantCallSite`, it is not a wrapper that looks up a new target on each call |
| `site.setTarget(handle)` | Always throws `UnsupportedOperationException` | Cannot relink, even if the new handle has the same `MethodType` |

Both `getTarget()` and `dynamicInvoker()` of `ConstantCallSite` are `final`, and calling them before the protected constructor has completed follows special rules that will be examined in section 8.

Illustrative example:

~~~java
// Fragment: lookup has access to method add and binary is the matching MethodType.
MethodHandle addHandle = lookup.findStatic(Example.class, "add", binary);
ConstantCallSite site = new ConstantCallSite(addHandle);
MethodHandle fixed = site.getTarget();
MethodHandle invoker = site.dynamicInvoker();
~~~

This is a **fragment**, not a standalone program. You need to know class `Example`, `lookup`, `binary`, and handle checked exceptions. A complete runnable example is in section 4.

### 2.1. Why Is dynamicInvoker() the Direct Target?

With `MutableCallSite`, the meaning of a dynamic invoker is to **go through the current target**, because the target can be replaced. With `ConstantCallSite`, the target **never changes**, so `dynamicInvoker()` can directly return the stored MethodHandle.

For a normal site that has been successfully constructed:

~~~java
// Fragment, comparing reference identity of the two MethodHandles.
boolean same = site.dynamicInvoker() == site.getTarget();
~~~

The value is `true` according to the `ConstantCallSite` specification. However, do **not** apply that conclusion to every `CallSite` subclass; call sites that can change their target must use a mechanism to observe the new target.

### 2.2. What Is type()?

`CallSite.type()` returns the `MethodType` of the target. `ConstantCallSite` inherits that type from the initial handle. For example:

~~~text
MethodHandle:       (int,int)int
ConstantCallSite:   type() = (int,int)int
dynamicInvoker():   (int,int)int
~~~

A `MethodType` includes the **return type**. With `MethodHandle.invokeExact`, the call-site descriptor must match **both the parameter types and the return type** of the handle's type. Simply passing the right number of arguments is not enough.

### 2.3. Why Is setTarget Not Allowed?

`ConstantCallSite.setTarget(MethodHandle ignore)` is defined to **always throw `UnsupportedOperationException`**, regardless of what handle is proposed. It does **not** attempt to change the target and roll back, nor does it allow switching to a handle with the same signature.

~~~java
// Fragment: multiplyHandle may have the same (int,int)int type as addHandle.
try {
    site.setTarget(multiplyHandle);
} catch (UnsupportedOperationException ex) {
    // ConstantCallSite does not allow replacing the target.
}
~~~

Do not catch the exception and assume the target has changed. Subsequent calls still execute **the old target**.

If the business requirement genuinely needs to change the target logic, you must **design from the start** with an appropriate mutable call site type, or create a *new* `ConstantCallSite` and replace where the reference to it is held. Replacing an external reference does not cause the old call site to be relinked.

## 3. Lifecycle Diagram of a ConstantCallSite

~~~text
1. Choose MethodType and look up MethodHandle
               |
               v
2. new ConstantCallSite(target)
               |
               v
   target is fixed inside the site
               |
               +----> type()           -> target type
               |
               +----> getTarget()      -> fixed target
               |
               +----> dynamicInvoker() -> same target
               |
               v
3. Invoke MethodHandle multiple times
               |
               v
   Result depends on arguments / target state
               |
               v
4. setTarget(other) -> UnsupportedOperationException
               |
               v
   Old target remains preserved
~~~

A `ConstantCallSite` can exist independently of `invokedynamic` bytecode; such an object is sometimes called a *free-floating call site*. Creating an object with `new ConstantCallSite(...)` **does not automatically turn** a Java source call into an `invokedynamic` opcode. To understand actual bytecode linkage, we need to examine bootstrap methods in section 7.

## 4. Java 17+ Program: Fixed Target, getTarget, dynamicInvoker, and Target Replacement Error

Save the file **ConstantSiteBasicsDemo.java**:

~~~java
import java.lang.invoke.CallSite;
import java.lang.invoke.ConstantCallSite;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;

public class ConstantSiteBasicsDemo {
    static int add(int x, int y) { return x + y; }
    static int multiply(int x, int y) { return x * y; }

    static final class Multiplier {
        int factor = 2;
        int apply(int n) { return n * factor; }
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType binary = MethodType.methodType(int.class, int.class, int.class);
        MethodHandle addHandle = lookup.findStatic(
                ConstantSiteBasicsDemo.class, "add", binary);
        MethodHandle multiplyHandle = lookup.findStatic(
                ConstantSiteBasicsDemo.class, "multiply", binary);

        ConstantCallSite site = new ConstantCallSite(addHandle);
        MethodHandle invoker = site.dynamicInvoker();
        CallSite general = site;
        System.out.println("type=" + site.type());
        System.out.println("targetSame=" + (site.getTarget() == addHandle));
        System.out.println("invokerSameTarget=" + (invoker == site.getTarget()));
        System.out.println("viaTarget=" + (int) site.getTarget().invokeExact(6, 7));
        System.out.println("viaInvoker=" + (int) invoker.invokeExact(6, 7));
        System.out.println("viaCallSite=" + (int) general.dynamicInvoker().invokeExact(6, 7));

        try {
            site.setTarget(multiplyHandle);
        } catch (UnsupportedOperationException ex) {
            System.out.println("setTarget=" + ex.getClass().getSimpleName());
        }
        System.out.println("afterSetAttempt=" + (int) invoker.invokeExact(6, 7));

        try {
            long wrong = (long) invoker.invokeExact(6, 7);
            System.out.println(wrong);
        } catch (WrongMethodTypeException ex) {
            System.out.println("wrongReturn=" + ex.getClass().getSimpleName());
        }

        try {
            new ConstantCallSite(null);
        } catch (NullPointerException ex) {
            System.out.println("nullTarget=" + ex.getClass().getSimpleName());
        }

        Multiplier receiver = new Multiplier();
        MethodHandle bound = lookup.findVirtual(
                Multiplier.class, "apply",
                MethodType.methodType(int.class, int.class)).bindTo(receiver);
        ConstantCallSite stateSite = new ConstantCallSite(bound);
        MethodHandle stable = stateSite.dynamicInvoker();
        System.out.println("boundType=" + stateSite.type());
        System.out.println("beforeStateChange=" + (int) stable.invokeExact(9));
        receiver.factor = 3;
        System.out.println("afterStateChange=" + (int) stable.invokeExact(9));
        System.out.println("stillSameTarget=" + (stable == stateSite.getTarget()));
    }
}
~~~

Compile/run with **JDK 17+**:

~~~bash
javac -encoding UTF-8 ConstantSiteBasicsDemo.java
java ConstantSiteBasicsDemo
~~~

Stdout:

~~~text
type=(int,int)int
targetSame=true
invokerSameTarget=true
viaTarget=13
viaInvoker=13
viaCallSite=13
setTarget=UnsupportedOperationException
afterSetAttempt=13
wrongReturn=WrongMethodTypeException
nullTarget=NullPointerException
boundType=(int)int
beforeStateChange=18
afterStateChange=27
stillSameTarget=true
~~~

### 4.1. Three Call Paths to the Same Target

`getTarget()` returns `addHandle`, and `dynamicInvoker()` is also that handle. Whether the variable is declared as `ConstantCallSite` or upcast to `CallSite`, the actual implementation is still `ConstantCallSite`.

~~~text
site.getTarget()                   ─┐
site.dynamicInvoker()             ─┼─> add(int,int)int
((CallSite) site).dynamicInvoker() ┘
~~~

In the example, all three return **13** for `(6,7)`. The `==` comparisons also prove that the MethodHandle identity is the exact same reference, not merely “two methods with the same logic”.

### 4.2. Unchanged After a Target Replacement Attempt

`multiplyHandle` has the same `(int,int)int` type as `addHandle`. That does **not** make `setTarget` allowed. The call:

~~~java
// Fragment:
site.setTarget(multiplyHandle);
~~~

throws `UnsupportedOperationException`; after catching the error, `invoker.invokeExact(6,7)` still yields **13**, not **42**.

Do not infer that `setTarget` will only fail if the new signature is wrong. **In ConstantCallSite, modifying the target is completely prohibited.**

### 4.3. Return Type Error in invokeExact

The `add` handle has type `(int,int)int`. The expression:

~~~java
// Fragment with an intentionally wrong return type at the call site:
long wrong = (long) invoker.invokeExact(6, 7);
~~~

creates a call-site descriptor expecting `long` instead of `int`. `invokeExact` **does not automatically widen** from `int` to `long` at that call site; the example catches `WrongMethodTypeException`. If you want a valid conversion, you need to use `invoke` or create an appropriate `asType` adapter, while still understanding the descriptor at the call site.

### 4.4. Constructor Requires a Non-Null Target

`new ConstantCallSite(null)` throws `NullPointerException`. There is no concept of a “site without a target yet, to be set later” with this public constructor. If you need a special target-binding design tied to the site itself, the API provides a **protected constructor with a hook**, presented in section 8.

## 5. “Fixed Target” Does Not Mean “Fixed Result”

The end of the program defines a receiver:

~~~java
static final class Multiplier {
    int factor = 2;
    int apply(int n) { return n * factor; }
}
~~~

The handle is created from the `apply(int)` method and then **bindTo(receiver)**:

~~~java
// Fragment from the program above:
MethodHandle bound = lookup.findVirtual(
        Multiplier.class, "apply",
        MethodType.methodType(int.class, int.class)).bindTo(receiver);
ConstantCallSite stateSite = new ConstantCallSite(bound);
~~~

Initially:

~~~text
receiver.factor = 2
fixedHandle.invokeExact(9) -> 18
~~~

After the same program changes:

~~~text
receiver.factor = 3
fixedHandle.invokeExact(9) -> 27
~~~

`stateSite.getTarget()` still holds the same MethodHandle. The invariant of `ConstantCallSite` is **not replacing the stored handle**, not freezing the heap object referenced by the handle.

Distinguish four layers of state:

| What can change? | With ConstantCallSite |
| --- | --- |
| **Reference to the site's target handle** | **No** |
| **Arguments passed to the handle** | Yes |
| **State of the receiver bound to the handle** | Yes, if the object and logic allow it |
| **Result/side effect of the target method** | Can change |
| **Call site's type `type()`** | No |

**Cross-thread note:** The example modifies `factor` from the same thread. If the receiver is shared across threads, reading/writing that state must still follow the Java Memory Model and appropriate synchronization mechanisms. A `ConstantCallSite` **does not make a bound field volatile**, nor does it create synchronization between threads.

### 5.1. Can You “Change the Target” Indirectly via a Branching Target?

You can design **a fixed MethodHandle** that internally calls a dispatcher reading configuration and choosing between logic A/B. When the configuration changes, the **behavior** of the dispatcher can change while the **ConstantCallSite's target handle** remains intact. That is a change *inside the operation*, not relinking the CallSite.

If you genuinely need a call site with a changing target to optimize an inline cache or switch algorithms at runtime, using `MutableCallSite`/`VolatileCallSite` expresses the intent more clearly instead of hiding retargeting inside a dispatcher without an equivalent contract.

## 6. Why Is a Fixed Target Useful?

In a linkage that is used repeatedly, target immutability simplifies reasoning:

1. There is no `setTarget` protocol to update the linkage point.
2. No separate publication mechanism is needed for **changing the target**, because the target does not change.
3. `ConstantCallSite.dynamicInvoker()` directly returns the permanent target, instead of having to look up the current target each time.
4. The JVM may have optimization opportunities when it knows the linkage is stable, depending on the call site, MethodHandle chain, and JIT.

However, **do not promise** that `ConstantCallSite` is always faster than every `MutableCallSite` by a fixed factor, or that every call through it is inlined. Performance depends on the signature, adapters, type profile stability, warmup time, target method, and workload.

A reasonable scenario: the system already knows at linkage time that the `upper` operation always maps to a single handle. The system can return a `ConstantCallSite` and needs no infrastructure to update the target later.

An unreasonable scenario: an application wants to **hot swap** handling logic after each configuration bundle. Attempting to use `setTarget` on a `ConstantCallSite` is immediately wrong per the API contract.

## 7. ConstantCallSite at the Boundary of invokedynamic and Bootstrap Methods

When the JVM processes an `invokedynamic` instruction in bytecode, it links the call site based on the **bootstrap method** described in the constant pool/BootstrapMethods attribute and the call site's linkage parameters.

Typical bootstrap method form:

~~~java
// Illustrative signature (may include additional static bootstrap arguments):
static CallSite bootstrap(MethodHandles.Lookup caller,
                          String name,
                          MethodType siteType) throws Throwable;
~~~

- `caller` is the `Lookup` representing the linkage context provided by the JVM.
- `name` is the dynamic name represented in bytecode, which can be used to select the operation.
- `siteType` is the type required at the **`invokedynamic` site**, not just the actual type of any arbitrary Java method.
- The bootstrap selects/adapts the target handle, then returns a `CallSite`.
- If it returns a `ConstantCallSite`, that linkage is **permanently bound to the returned target**; it cannot be relinked via `setTarget`.

Here is a conceptual diagram:

~~~text
invokedynamic "upper" (String)String
                    |
                    | Bootstrap Lookup, name="upper", type=(String)String
                    v
            bootstrap(...)
                    |
                    | findStatic("upper", (String)String)
                    v
            MethodHandle target
                    |
                    v
           new ConstantCallSite(target)
                    |
                    v
   JVM uses immutable linkage for this call site
~~~

If the selected handle does not match `siteType`, the bootstrap can use **`asType`** when a conversion is valid; if the type cannot be adapted, linkage preparation fails. `ConstantCallSite` **does not automatically fix** a mismatched signature.

### 7.1. Java 17+ Program: Calling a Bootstrap Method Illustratively

Save the file **ConstantSiteLinkDemo.java**:

~~~java
import java.lang.invoke.CallSite;
import java.lang.invoke.ConstantCallSite;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;

public class ConstantSiteLinkDemo {
    private static String upper(String value) {
        return value.toUpperCase(java.util.Locale.ROOT);
    }

    public static CallSite bootstrap(MethodHandles.Lookup caller,
                                     String name,
                                     MethodType siteType)
            throws ReflectiveOperationException {
        if (!name.equals("upper")) {
            throw new IllegalArgumentException("Unknown operation: " + name);
        }
        MethodHandle target = caller.findStatic(
                ConstantSiteLinkDemo.class, "upper",
                MethodType.methodType(String.class, String.class));
        return new ConstantCallSite(target.asType(siteType));
    }

    public static void main(String[] args) throws Throwable {
        MethodType wanted = MethodType.methodType(String.class, String.class);
        CallSite linked = bootstrap(MethodHandles.lookup(), "upper", wanted);
        System.out.println("linked.type=" + linked.type());
        System.out.println("linked.class=" + linked.getClass().getSimpleName());
        MethodHandle invoker = linked.dynamicInvoker();
        System.out.println("first=" + (String) invoker.invokeExact("hello"));
        System.out.println("second=" + (String) invoker.invokeExact("java"));

        try {
            bootstrap(MethodHandles.lookup(), "missing", wanted);
        } catch (IllegalArgumentException ex) {
            System.out.println("badName=" + ex.getClass().getSimpleName());
        }
        try {
            MethodType impossible = MethodType.methodType(String.class, int.class);
            bootstrap(MethodHandles.lookup(), "upper", impossible);
        } catch (WrongMethodTypeException ex) {
            System.out.println("badType=" + ex.getClass().getSimpleName());
        }
    }
}
~~~

Run commands:

~~~bash
javac -encoding UTF-8 ConstantSiteLinkDemo.java
java ConstantSiteLinkDemo
~~~

Stdout:

~~~text
linked.type=(String)String
linked.class=ConstantCallSite
first=HELLO
second=JAVA
badName=IllegalArgumentException
badType=WrongMethodTypeException
~~~

**Limitation of the example:** The Java source code **calls `bootstrap(...)` itself**, and then directly invokes `dynamicInvoker()`. It **does not emit a custom `invokedynamic` instruction**. You must distinguish **simulating linkage logic** (this example) from **the JVM actually linking an invokedynamic opcode** (bytecode generated by a compiler or bytecode generator).

### 7.2. Why Must the Bootstrap Match the Type?

`wanted` is `(String)String`, matching the type of handle `upper`; therefore `target.asType(wanted)` is valid. The site receives the exact type, `dynamicInvoker` is also a handle carrying that type, and `invokeExact("hello")` returns `HELLO`.

The `badName` branch illustrates an error due to **business rules** in the bootstrap: there is no `missing` operation, so the code explicitly throws `IllegalArgumentException`.

The `badType` branch asks for a target of type `(int)String`. There is no conversion from `int` to a `String` parameter under `MethodHandle.asType` rules, so `WrongMethodTypeException` is thrown.

Key distinctions:

- **Wrong operation name** is a target selection error according to the bootstrap's policy.
- **Wrong MethodType** is a signature linkage/conversion error.
- **Lookup permission errors** can come from `Lookup.findStatic` or other lookup operations.
- When the **JVM** actually processes `invokedynamic`, bootstrap/linkage errors may be represented via **`BootstrapMethodError`** (or related errors per the JVMS), not necessarily the direct exception printed by the Java snippet calling the bootstrap manually.

Do not conclude that every error in a handler is `WrongMethodTypeException`; an exception thrown by the target method after successful linkage is a different matter.

### 7.3. Is the Bootstrap Called Again on Every Invocation?

Once an invokedynamic site has been successfully linked, the JVM maintains that site's linkage; subsequent calls use the linkage rather than looping through method name lookup and running bootstrap logic on **every call**.

With `ConstantCallSite`, the linked site's target is permanent. If the target is executed with different inputs, the inputs do not cause the site to relink. If you need a linkage that updates its target, you need a call site type that allows updates, not `ConstantCallSite`.

**Do not equate** “linking a bytecode site once” with “the entire application has only one site”. Multiple bytecode sites, class loaders, or linkage contexts can each have their own separate call sites, even with the same dynamic name.

## 8. Protected Constructor: Creating the Target via createTargetHook

In addition to the public constructor taking a handle, `ConstantCallSite` has a **protected constructor**:

~~~java
// Reference API signature:
protected ConstantCallSite(MethodType targetType,
                           MethodHandle createTargetHook) throws Throwable;
~~~

It is intended for subclasses that need to create the target during initialization, especially when the target must be **bound to the CallSite object itself**.

By contract, the constructor invokes the hook as:

~~~text
(MethodHandle) createTargetHook.invoke(this)
~~~

The hook must return a `MethodHandle` whose **MethodType is exactly equal to `targetType`**. While the hook is running, the ConstantCallSite object is **not yet fully initialized**:

- You can call `site.type()` to find out the type the site will have.
- Calling `site.getTarget()` or attempting to use the target, including `dynamicInvoker()`, before completion will throw `IllegalStateException`.
- You must not leave the target uninitialized and return normally from the constructor.
- The hook may ignore the site and return a static handle; however, the legitimate use case is usually when complex binding is needed for a subclass.

This protected constructor does **not** make the target mutable. After construction, the site is still permanently fixed.

### 8.1. Java 17+ Program: Observing the Uninitialized State

Save the file **ConstantSiteHookDemo.java**:

~~~java
import java.lang.invoke.ConstantCallSite;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;

public class ConstantSiteHookDemo {
    static int doubleIt(int value) { return value * 2; }

    static MethodHandle makeTarget(ConstantCallSite site)
            throws ReflectiveOperationException {
        System.out.println("hook.type=" + site.type());
        try {
            site.getTarget();
        } catch (IllegalStateException ex) {
            System.out.println("hook.uninitialized=" + ex.getClass().getSimpleName());
        }
        return MethodHandles.lookup().findStatic(
                ConstantSiteHookDemo.class, "doubleIt",
                MethodType.methodType(int.class, int.class));
    }

    static MethodHandle makeWrongTarget(ConstantCallSite site)
            throws ReflectiveOperationException {
        return MethodHandles.lookup().findStatic(
                ConstantSiteHookDemo.class, "doubleIt",
                MethodType.methodType(int.class, int.class));
    }

    static final class HookedSite extends ConstantCallSite {
        HookedSite(MethodType type, MethodHandle factory) throws Throwable {
            super(type, factory);
        }
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodHandle factory = lookup.findStatic(
                ConstantSiteHookDemo.class, "makeTarget",
                MethodType.methodType(MethodHandle.class, ConstantCallSite.class));
        MethodType wanted = MethodType.methodType(int.class, int.class);
        HookedSite site = new HookedSite(wanted, factory);
        System.out.println("final.type=" + site.type());
        System.out.println("result=" + (int) site.dynamicInvoker().invokeExact(21));

        MethodHandle mismatchFactory = lookup.findStatic(
                ConstantSiteHookDemo.class, "makeWrongTarget",
                MethodType.methodType(MethodHandle.class, ConstantCallSite.class));
        try {
            new HookedSite(MethodType.methodType(long.class, long.class),
                    mismatchFactory);
        } catch (WrongMethodTypeException ex) {
            System.out.println("wrongHookTarget=" + ex.getClass().getSimpleName());
        }
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 ConstantSiteHookDemo.java
java ConstantSiteHookDemo
~~~

Stdout:

~~~text
hook.type=(int)int
hook.uninitialized=IllegalStateException
final.type=(int)int
result=42
wrongHookTarget=WrongMethodTypeException
~~~

### 8.2. Analyzing the Protected Hook

1. `HookedSite` is a subclass, so it is allowed to call the `protected` constructor.
2. `factory` is a handle taking a `ConstantCallSite` and returning a `MethodHandle`.
3. Inside the hook, `site.type()` works and returns `(int)int`, but `site.getTarget()` reports `IllegalStateException` because the target is not yet finalized.
4. The hook returns a handle to `doubleIt(int)` with type **exactly `(int)int`**, so the constructor completes and `invokeExact(21)` returns **42**.
5. Trying `targetType=(long)long` while the hook returns `(int)int` fails with **`WrongMethodTypeException`**. This is a type-constraint error **during site creation**, not an error on a subsequent call.

### 8.3. Other Error Cases from the Hook

The Javadoc describes the important cases:

| Hook situation | Possible error |
| --- | --- |
| Hook cannot be invoked with the appropriate argument | `WrongMethodTypeException` |
| Hook returns a handle whose `MethodType` does not equal targetType | `WrongMethodTypeException` |
| Hook returns `null` | `NullPointerException` |
| Hook returns an object that is not a `MethodHandle` | `ClassCastException` |
| Hook throws another exception | Exception from the hook can propagate per the contract |
| Using `getTarget/dynamicInvoker` before constructor completes | `IllegalStateException` |

Because the protected hook runs while the object is still under construction, avoid **exposing `this`** to other threads or components. Binding can be done, but it does not replace safe object construction rules.

**Practical assessment:** Most application code only needs the public constructor `new ConstantCallSite(target)`. Use the protected hook when there is a specific technical requirement; initialization complexity is higher and there is additional risk from incomplete state.

## 9. Comparing the Three CallSite Types

| Property | `ConstantCallSite` | `MutableCallSite` | `VolatileCallSite` |
| --- | --- | --- | --- |
| Can target change after construction? | **No** | **Yes** | **Yes** |
| `setTarget` | Always throws `UnsupportedOperationException` | Valid for a target with the same MethodType | Valid for a target with the same MethodType |
| `dynamicInvoker()` | Returns the permanent target directly | Tracks the site's current target | Tracks the current target with volatile semantics |
| Typical purpose | Fixed linkage, target never relinks | Runtime target updates | Target updates with clear cross-thread visibility |
| Publication protocol for a new target | Not needed, because there is no new target | Must follow `MutableCallSite` rules, can use `syncAll` when appropriate | Follows the API's volatile rules |

Do not choose `ConstantCallSite` just because of the word “dynamic” in `invokedynamic`. “Dynamic linkage” refers to **when/how the target is chosen**, not necessarily that the target will **change** during runtime.

For example: a bootstrap may select an implementation based on name and signature **at link time**, and never change it again; `ConstantCallSite` fits very well. Conversely, a runtime with a speculative inline cache that needs to update a dispatcher when receiver types change may need a mutable call site.

### 9.1. MutableCallSite and VolatileCallSite Do Not Allow Arbitrary Type Changes

Even though the target can change, `CallSite.type()` remains immutable. A `MutableCallSite` of type `(int,int)int` cannot be changed directly to a `(String)String` target. To change logic while keeping the shape, build an adapter with the same `MethodType` before calling `setTarget`.

This ensures each invokedynamic site has **a stable call-site type** matching its bytecode descriptor, while the concrete implementation underneath can vary in call site types that permit it.

## 10. Common Errors and How to Diagnose Them

| Symptom | Cause | How to fix |
| --- | --- | --- |
| `new ConstantCallSite(null)` throws an error | Target is not allowed to be null | Create a valid MethodHandle before building the site |
| `setTarget(...)` gets `UnsupportedOperationException` | Site is constant, **not mutable** | Choose the right CallSite type from the start; do not retry |
| `invokeExact` hits `WrongMethodTypeException` | Call-site descriptor does not match `MethodType`, including return type | Print `site.type()`, fix the cast/signature, or use a valid adapter |
| `findStatic`/`findVirtual` gets `NoSuchMethodException` | Target name/signature is inaccurate | Verify method name, arity, and return type |
| Lookup gets `IllegalAccessException` | Lookup context lacks permission for the member | Use an appropriate API/public lookup; do not try to bypass modules via a site |
| Bootstrap returns a target of the wrong type | Does not match `siteType` at linkage | Use `asType` when conversion is valid, otherwise fix the bootstrap contract |
| Hook returns null/wrong type | Hook does not satisfy constructor contract | Return a MethodHandle of the exact type, do not use a placeholder |
| Hook uses getTarget too early | ConstantCallSite is still being constructed | Only use `type()` during the hook phase when needed |
| Target stays the same but result differs | Input or internal state of the target method changed | Check the target's logic, do not blame relinking |
| Call throws a business exception | Target method threw an exception | Handle the error per the target method's contract, separate from linkage |
| Test prints unexpected result after `setTarget` | Assumed the set succeeded | With ConstantCallSite, set always fails and the old target remains |

A short debugging checklist:

~~~text
1. Is site.getClass() actually ConstantCallSite?
2. Does site.type() equal the signature the call site is requesting?
3. Is site.getTarget().type() equivalent to site.type()?
4. Was the MethodHandle created from lookup with the right permissions and right method?
5. Does the invokeExact call have the right return type at the Java call site?
6. Are you expecting to change a target that cannot be changed?
7. Is the target reading a mutable object/field?
8. If it is a real invokedynamic: did the bootstrap return a valid site/type?
~~~

For a `ConstantCallSite` successfully constructed via the public constructor, `site.type()` and `site.getTarget().type()` always correspond. If you receive invalid data or unexpected results, check **the adapter chain, inputs, and target method state** first.

## 11. Security, Concurrency, and Performance

### 11.1. ConstantCallSite Does Not Grant New Access Permissions

`MethodHandles.Lookup` must have permission to look up/create the target method handle according to Java and module rules. `ConstantCallSite` only holds the target it received; it **does not grant access** to private members on its own. If a bootstrap looks up a private method without proper permission, the error may occur at **lookup/linking**, before a valid site exists.

Similarly, do not accept arbitrary class/method names from untrusted input and call `findStatic` for all of them. A plugin system should define an allowlist of operations and clear access policies.

### 11.2. Thread Safety and Target State

The target reference itself does not change; that helps keep linkage stable across threads. However, if a target reads a `Map`, field, or mutable object, thread-safety rules **still apply to that data**. For example, `Multiplier.factor` in the program does not use volatile/synchronization, so when multiple threads are involved, appropriate synchronization design is needed.

**Do not equate:** “constant call site” with “immutable computation”. The result can read a clock, access the network, increment a counter, or depend on state, even though the target handle is fixed.

### 11.3. Can We Claim It Is Faster Than Every Other Call Type?

No. `ConstantCallSite` creates optimization opportunities thanks to permanent linkage, but there is no fixed overhead across all workloads. If you want to evaluate performance:

- Create method handles, adapters, and call sites **outside the measurement loop** if the application does so.
- Use JMH or a benchmark with warmup/blackhole to prevent the JIT from eliminating the work.
- Compare **the same behavior**, same data, and same return type.
- Do not use a result from the 6+7 example as performance proof.
- Consider both performance and relinking needs: a `ConstantCallSite` cannot change its target, even if fast.

## 12. Self-Check Questions

**Question 1.** Does `ConstantCallSite` make the target method always return the same result?

**Answer:** No. It keeps the **target MethodHandle fixed**; the target method still receives inputs and can read mutable state.

**Question 2.** Can `site.setTarget(newHandle)` be used when newHandle has the same `MethodType`?

**Answer:** No. For `ConstantCallSite`, `setTarget` always throws `UnsupportedOperationException`, even if the type matches.

**Question 3.** Is `site.dynamicInvoker()` always a wrapper that reads `getTarget()` every time?

**Answer:** No. For `ConstantCallSite`, it returns the **permanent target directly**. It is for mutable types that dynamic invoker must observe the current target per the contract.

**Question 4.** Why can `long x = (long) handle.invokeExact(6,7)` fail when the actual handle is `(int,int)int`?

**Answer:** Because the return type at the call site is `long`, which differs from `int` on the MethodHandle. `invokeExact` requires the return type to match as well.

**Question 5.** Can a protected hook call `getTarget()` while the constructor is running?

**Answer:** No. The target is not finalized yet, so `getTarget()` throws `IllegalStateException`; `type()` is allowed to be called.

**Question 6.** Does calling a bootstrap manually in Java code prove that the bytecode is using `invokedynamic`?

**Answer:** No. That is only simulating linkage rules. A real `invokedynamic` is an opcode in bytecode generated by a compiler or tool.

**Question 7.** If two different ConstantCallSites hold the same MethodHandle, are they a single site?

**Answer:** No. They are two separate CallSite objects. They can have the same target reference and the same type, but the site identity is still different.

**Question 8.** When is `MutableCallSite` or `VolatileCallSite` more appropriate?

**Answer:** When there is a requirement to **update the target after linkage**. Choose mutable/volatile according to the publication and concurrency model, rather than trying to replace a ConstantCallSite.

**Question 9.** Type `(String)String` is needed, but the bootstrap returns a `(int)String` target. Does ConstantCallSite automatically validate/adapt it?

**Answer:** No. The target must correspond to the linkage type. If there is no valid `asType` conversion, you must fix the bootstrap or target selection.

**Question 10.** If a target handle is bound to a receiver with mutable state, who ensures the receiver's thread safety?

**Answer:** The state and synchronization design of the application code. ConstantCallSite does not change the Java Memory Model.

## Quick Summary

- `ConstantCallSite` is a **CallSite with a permanent target**.
- Common constructor: `new ConstantCallSite(target)` with `target != null`.
- `getTarget()` and `dynamicInvoker()` on `ConstantCallSite` return the permanent MethodHandle; `type()` reflects the target signature.
- `setTarget(...)` **always fails** with `UnsupportedOperationException`.
- **An unchanging target is different from an unchanging result.** The same handle can produce different values depending on input and state.
- When linking `invokedynamic`, the bootstrap must return a `CallSite` matching `MethodType`; choose `ConstantCallSite` when relinking is not needed.
- The protected constructor with a hook supports creating the target during initialization; the target must not be used while the site is still incomplete.
- Need an updatable target? Use `MutableCallSite` or `VolatileCallSite`, not `ConstantCallSite`.

## References

- Java SE 17, **ConstantCallSite** (constructor, `getTarget`, `setTarget`, `dynamicInvoker`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/ConstantCallSite.html
- Java SE 17, **CallSite** (concept, fixed type, mutable/volatile, and invokedynamic): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/CallSite.html
- Java SE 17, **MethodHandle** (`invoke`, `invokeExact`, `asType`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html
- Java SE 17, **MethodHandles.Lookup**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html
- Java Virtual Machine Specification SE 17, chapter on **invokedynamic** and dynamic linkage: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html#jvms-6.5.invokedynamic
