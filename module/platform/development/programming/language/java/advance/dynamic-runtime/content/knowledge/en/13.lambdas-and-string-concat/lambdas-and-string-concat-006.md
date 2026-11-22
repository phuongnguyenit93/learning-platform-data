# 13.6 Adapting a handle to an interface with MethodHandleProxies and its limitations

## 1. When a MethodHandle needs to be used as an interface

In Java, a `MethodHandle` is a typed reference to an executable invocation, typically created using `MethodHandles.Lookup` or combinators in `MethodHandles`. However, many Java APIs **do not accept a MethodHandle**; they require a specific interface such as `Runnable`, `Callable<V>`, `Comparator<T>`, an application callback, or a plugin contract.

Instead of writing an intermediate implementation class just to forward the call, Java provides:

```java
T adapter = MethodHandleProxies.asInterfaceInstance(
        InterfaceType.class, targetHandle);
```

This is **illustrative syntax**: `InterfaceType` must be an interface that satisfies the factory's conditions, and `targetHandle` is a `MethodHandle` that can be adapted to the method to be implemented. The factory returns an object **implementing the requested interface**, forwarding calls to the interface's abstract method to the target handle.

Conceptual example: a dynamic runtime system already has a `MethodHandle` of type `(long)String`, but an external SDK wants an interface:

```java
public interface IntToText {
    String apply(int value);
}
```

If the interface is valid and the `int → long` conversion is permitted, `asInterfaceInstance` can provide an `IntToText` without having to manually write an adapter class.

### Lesson Objectives

After this lesson, you can:

1. Understand the conditions of a **single-method interface**, without mechanically equating it to all uses of `@FunctionalInterface`.
2. Create a wrapper using `MethodHandleProxies.asInterfaceInstance` and inspect `isWrapperInstance`, `wrapperInstanceType`, `wrapperInstanceTarget`.
3. Explain **per-signature conversion** according to `MethodHandle.asType`, supporting same-name overloads/bridge methods and default methods.
4. Handle `WrongMethodTypeException`, `IllegalArgumentException`, `NullPointerException`, `UndeclaredThrowableException`.
5. State the boundaries of **public, non-sealed interface, single abstract method name**, permission/capability checks, class loaders, JPMS, and cases where the API should not be used.
6. Distinguish this approach from Java lambdas, `LambdaMetafactory`, and `Proxy.newProxyInstance`.

`MethodHandleProxies` has been available since **Java 7**. The examples use **Java 17+** because Java 17 has the `sealed interface` concept that needs to be noted in the input conditions.

## 2. Core API of MethodHandleProxies

The `java.lang.invoke.MethodHandleProxies` class provides four main static methods:

| API | Input | Meaning |
| --- | --- | --- |
| `<T> T asInterfaceInstance(Class<T> intfc, MethodHandle target)` | Interface type and target handle | Creates an adapter implementing the interface, delegating method calls to the target. |
| `boolean isWrapperInstance(Object x)` | Any object | Checks whether the object is a wrapper created by `asInterfaceInstance`; `null` returns `false`. |
| `MethodHandle wrapperInstanceTarget(Object x)` | Valid wrapper | Retrieves a handle **behaviorally equivalent** to the wrapper's target. |
| `Class<?> wrapperInstanceType(Object x)` | Valid wrapper | Retrieves the exact interface type that the factory used to create the wrapper. |

Only `asInterfaceInstance` **creates an adapter**. The other three methods serve to inspect/recover metadata of the wrapper.

**Do not assume** `wrapperInstanceTarget(x) == originalTarget` is always true by object identity. The Javadoc contract guarantees the recovered handle is **behaviorally equivalent**, not that it returns the exact same object passed to the factory. When checking, use `type()` and test-invoke according to the contract; do not use `==` as the primary criterion.

`wrapperInstanceTarget` and `wrapperInstanceType` are **not** functions for analyzing arbitrary lambdas/adapters. If given an object not created by `asInterfaceInstance`, they throw `IllegalArgumentException`. Call `isWrapperInstance(x)` first if the object source is untrusted.

### 2.1. Typical example, not yet a standalone program

```java
// Illustrative snippet inside a method that already has the right target type.
IntToText adapter = MethodHandleProxies.asInterfaceInstance(
        IntToText.class, target);
String value = adapter.apply(42);
boolean recognized = MethodHandleProxies.isWrapperInstance(adapter);
```

Here, the target must have **argument count/return type** adaptable to `String apply(int)`. If the target cannot be converted, the factory throws an error **before finishing creating the wrapper**; there is no adapter that "can be called with any type".

## 3. Interface conditions — the most easily misunderstood part

The Java SE 17 Javadoc uses the concept of **single-method interface** (an interface with **a single abstract method name**). When determining the single method name, the API **ignores**:

- Public methods of `Object`: `toString`, `equals`, `hashCode`.
- **Default/non-abstract** methods of the interface, because they have their own implementation.

In addition to the method name condition, `intfc` must:

1. Actually be an **interface**, not an abstract class.
2. Have **public** access (not a package-private/private interface).
3. **Not be a sealed interface** on Java 17+.
4. Have a single abstract method name after ignoring the cases above; abstract declarations with the **same name** may still have multiple descriptors due to overloads/bridges.
5. Be able to adapt `target` to **all** signatures that need to be handled according to `MethodHandle.asType`.

### 3.1. Distinguishing "one method name" from "exactly one declaration"

Two illustrative interfaces:

```java
public interface Renderer {
    String render(int n);
    String render(long n);
    default String label() { return "DEFAULT"; }
}

public interface TwoNames {
    String render(int n);
    String format(int n);
}
```

These are **illustrative declarations**; in actual files, if they are top-level public types, each type needs a corresponding Java file. Or they can be placed as **nested public interfaces** inside a public class like the runnable example in section 6.

- `Renderer` has **two declarations but the same name `render`**. It *can* be accepted by `MethodHandleProxies` if a target can be adapted to **both** method descriptors.
- `label()` is a default method and is not counted in the list of abstract method names that the factory needs to implement.
- `TwoNames` has two **different abstract names**: `render` and `format`, so it is invalid.
- Object methods such as `equals(Object)` may be redeclared by the interface, yet **do not** make it lose its single-method status under this rule.

**Difference from `@FunctionalInterface`:** an interface with overloads `render(int)` and `render(long)` is usually **not a valid functional interface for Java lambdas**, because it has two non-equivalent abstract method signatures; however, `MethodHandleProxies` allows **the same name with multiple descriptors** if the target can adapt to each descriptor. Conversely, a valid `@FunctionalInterface` may still not be accepted by `MethodHandleProxies` if the interface is not public or is sealed.

A common example in the Java API: `Comparator` is a single-method interface according to `MethodHandleProxies`'s counting because `compare` is the abstract method name to implement, while `equals` from Object and other default methods are not counted.

### 3.2. Why are sealed interfaces not supported?

A `sealed interface` restricts which classes are allowed to implement it via `permits`. `MethodHandleProxies` creates a runtime-managed wrapper implementation; the Java 17 contract requires the interface to be **not sealed**. When the input is sealed, the factory throws `IllegalArgumentException` instead of bypassing `permits`.

This cannot be fixed with `setAccessible(true)`, a lookup with private access, or arbitrarily changing the class loader. This is a **design limitation of the factory**; to have an adapter for a sealed hierarchy, you need a valid implementation listed in `permits` or another suitable API.

### 3.3. To what extent is the interface implemented?

The wrapper implements **the requested interface and its superinterfaces**, and does not automatically add every interface that happens to have the same method. Therefore, one cannot assume a `IntToText` wrapper is also `instanceof Function<Integer,String>` just because the two APIs have similar ideas.

The Javadoc also does not guarantee that the factory creates a new object instance on every call: the result is defined by **behavior**, not by identity. Avoid building logic that requires every `asInterfaceInstance` call to return a completely new identity.

## 4. Call forwarding mechanism: from interface method to target MethodHandle

When `adapter.method(args...)` is called:

1. The JVM dispatches the interface method through the wrapper.
2. The wrapper forwards the input to the target handle **as if calling `target.invoke(...)`** (not necessarily `invokeExact`).
3. A conversion equivalent to `target.asType(interfaceMethodType)` is checked for **each method descriptor** when creating the adapter.
4. If the type can be adapted, the result or exception from the target is converted/propagated according to the interface's contract.

This explains why a `(long)String` target can serve `String apply(int)`: the `int` input is widened to `long`. But a `()String` target cannot automatically accept an int parameter if you have not used a combinator like `dropArguments` to add a dummy parameter.

### 4.1. Comparing some conversions

| Interface method | Target type | Result |
| --- | --- | --- |
| `String apply(int)` | `(long)String` | Valid: int → long. |
| `String apply(long)` | `(long)String` | Valid: exact match. |
| `String apply(int)` | `()String` | Invalid: different parameter count; `WrongMethodTypeException` when creating the wrapper. |
| `int compute(int)` | `(int)int` | Valid: matching signature. |
| `String apply(String)` | `(int)String` | No automatic String → int conversion under `asType`; needs a separate adapter/conversion. |

Not **every** Java conversion is permitted in `MethodHandle.asType`: boxing/unboxing, reference casting, and primitive widening have specific rules; it does not automatically parse numeric strings, does not automatically drop arguments, and cannot arbitrarily transform return types. With generic interfaces, Java erasure and bridge methods also affect runtime descriptors.

When the target can throw an exception, the factory cannot use the return type to know what the logic will throw; exceptions are handled at the time of **calling the method on the wrapper**.

### 4.2. Same-name overloads and bridge methods

If an interface declares `render(int)` and `render(long)`, the factory processes **each descriptor**. A `(long)String` target will use adaptation:

```text
Renderer.render(int)  -> adapt (int)String  -> (long)String target
Renderer.render(long) -> adapt (long)String -> (long)String target
```

The generic bridge method case is similar: the class file may contain bridges with different descriptors, and the API computes adaptation for each declaration. The condition is not "a single bytecode method", but **a single abstract method name** with descriptors convertible to the target.

**Limitation:** if just one overload cannot be adapted, the factory may throw `WrongMethodTypeException` immediately upon creation, even if the other overload matches completely. Do not use a single target for overloads with different semantics if they cannot genuinely share an implementation.

## 5. Java 17 Example 1 — creating an interface wrapper and retrieving the target

Create the file **`MethodHandleProxiesBasicsDemo.java`**:

```java
import java.lang.invoke.*;

public class MethodHandleProxiesBasicsDemo {
    public interface IntToText {
        String apply(int value);
    }

    private static String format(long value) {
        return "value=" + value;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandle target = MethodHandles.lookup().findStatic(
                MethodHandleProxiesBasicsDemo.class,
                "format",
                MethodType.methodType(String.class, long.class));

        IntToText adapter =
                MethodHandleProxies.asInterfaceInstance(
                        IntToText.class, target);

        System.out.println("interface call: " + adapter.apply(7));
        System.out.println("instanceof: " + (adapter instanceof IntToText));
        System.out.println("recognized: "
                + MethodHandleProxies.isWrapperInstance(adapter));
        System.out.println("type recovered: "
                + (MethodHandleProxies.wrapperInstanceType(adapter)
                        == IntToText.class));

        MethodHandle recovered =
                MethodHandleProxies.wrapperInstanceTarget(adapter);
        System.out.println("target type: " + recovered.type());
        System.out.println("target call: "
                + (String) recovered.invoke(8L));

        System.out.println("ordinary instance recognized: "
                + MethodHandleProxies.isWrapperInstance(
                        (IntToText) n -> "normal:" + n));
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 --release 17 MethodHandleProxiesBasicsDemo.java
java MethodHandleProxiesBasicsDemo
```

Stdout:

```text
interface call: value=7
instanceof: true
recognized: true
type recovered: true
target type: (long)String
target call: value=8
ordinary instance recognized: false
```

**Part-by-part explanation:**

1. `findStatic` creates a handle to the **private static** method `format(long)`. The lookup inside the demo class itself has permission to access this method, so the target is valid. `MethodHandleProxies` **does not look up private methods on its own**; it only receives an already-created handle.
2. The interface requires `apply(int)`; the target accepts `long`. The factory checks the `int → long` adaptation before returning the wrapper, so `adapter.apply(7)` yields `value=7`.
3. The wrapper is indeed `instanceof IntToText` and `isWrapperInstance(adapter)` returns true.
4. `wrapperInstanceType(adapter)` returns the exact `Class` of `IntToText`.
5. `wrapperInstanceTarget(adapter)` returns a handle behaviorally equivalent to the target, which in the demo has `type() == (long)String` and calling `invoke(8L)` returns `value=8`. **Do not generalize this specific `target.type()` result into a requirement that every wrapper must return the exact original target object.**
6. An ordinary Java lambda implementing `IntToText` is **not** a product of `asInterfaceInstance`; `isWrapperInstance` returns false. This recognition API is not for detecting all objects implementing an interface.

**Be careful with permissions:** in the example, the wrapper exposes the behavior of a private method through a nested public interface. That is an intentionally granted capability; if the method is sensitive, do not hand out the adapter to untrusted APIs.

## 6. Java 17 Example 2 — overloads, default methods, and rejected interfaces

Create the file **`MethodHandleProxiesOverloadDemo.java`**:

```java
import java.lang.invoke.*;

public class MethodHandleProxiesOverloadDemo {
    public interface Renderer {
        String render(int x);
        String render(long x);

        default String label() {
            return "DEFAULT";
        }
    }

    public interface TwoNames {
        String first(int x);
        String second(int x);
    }

    interface PackagePrivate {
        String render(long x);
    }

    public sealed interface SealedRenderer permits SealedImpl {
        String render(long x);
    }

    public static final class SealedImpl implements SealedRenderer {
        public String render(long x) {
            return "impl";
        }
    }

    private static String show(long value) {
        return "num=" + value;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandle target = MethodHandles.lookup().findStatic(
                MethodHandleProxiesOverloadDemo.class,
                "show",
                MethodType.methodType(String.class, long.class));

        Renderer renderer =
                MethodHandleProxies.asInterfaceInstance(
                        Renderer.class, target);

        System.out.println("render int: " + renderer.render(3));
        System.out.println("render long: " + renderer.render(4L));
        System.out.println("default method: " + renderer.label());
        System.out.println("object method nonnull: "
                + (renderer.toString() != null));

        try {
            MethodHandleProxies.asInterfaceInstance(
                    TwoNames.class, target);
        } catch (IllegalArgumentException expected) {
            System.out.println("two names: rejected");
        }
        try {
            MethodHandleProxies.asInterfaceInstance(
                    PackagePrivate.class, target);
        } catch (IllegalArgumentException expected) {
            System.out.println("nonpublic: rejected");
        }
        try {
            MethodHandleProxies.asInterfaceInstance(
                    SealedRenderer.class, target);
        } catch (IllegalArgumentException expected) {
            System.out.println("sealed: rejected");
        }
        try {
            MethodHandleProxies.asInterfaceInstance(
                    java.util.function.Function.class,
                    MethodHandles.constant(String.class, "fixed"));
        } catch (WrongMethodTypeException expected) {
            System.out.println("incompatible arity: rejected");
        }
    }
}
```

Command:

```bash
javac -encoding UTF-8 --release 17 MethodHandleProxiesOverloadDemo.java
java MethodHandleProxiesOverloadDemo
```

Stdout:

```text
render int: num=3
render long: num=4
default method: DEFAULT
object method nonnull: true
two names: rejected
nonpublic: rejected
sealed: rejected
incompatible arity: rejected
```

**Explanation:**

- `Renderer` has two **overloads with the same name `render`** and a default `label`. The `(long)String` target can adapt to both `render(int)` and `render(long)`, so the wrapper is valid.
- `renderer.label()` runs its own default method, without going through the `show` target. Object methods are excluded from the abstract name count, but **do not depend** on the `toString`/`equals`/`hashCode` details of the runtime-generated wrapper class.
- `TwoNames` has two abstract method **names**, violating the factory's contract.
- `PackagePrivate` is not public and `SealedRenderer` is sealed on Java 17; both are rejected even though the caller code can see those types.
- `Function` requires the `apply(Object)Object` method (after erasure), but the constant `()String` target takes no input. The factory does not add arguments on its own, so it throws `WrongMethodTypeException`.

Note: this demo class **does not** place `@FunctionalInterface` on `Renderer` because two same-name overloads are not a single functional method signature for Java lambdas; however, it **is still** a valid single-method interface under the special definition of `MethodHandleProxies`.

## 7. Exceptions when calling the wrapper: checked and unchecked

A `MethodHandle` can throw any `Throwable`. The Java method signature of the interface might **not declare** that checked exception. `MethodHandleProxies` has the rules:

- **Unchecked** exceptions (such as `RuntimeException`, `Error`) are propagated with normal behavior.
- Checked exceptions **declared** by the interface method can be thrown directly to the caller.
- **Undeclared** checked exceptions (and unsuitable checked throwables) are **wrapped** in `java.lang.reflect.UndeclaredThrowableException`.
- The factory does not throw business exceptions just because the target **might** throw; the error occurs when the call actually enters the throwing branch of the target.

### 7.1. Java 17 Example 3 — same target, two different exception contracts

Create the file **`MethodHandleProxiesExceptionsDemo.java`**:

```java
import java.io.IOException;
import java.lang.invoke.*;
import java.lang.reflect.UndeclaredThrowableException;

public class MethodHandleProxiesExceptionsDemo {
    public interface PlainAction {
        String run();
    }

    public interface CheckedAction {
        String run() throws IOException;
    }

    public interface IntegerInput {
        String run(int number);
    }

    private static String fail() throws IOException {
        throw new IOException("disk-offline");
    }

    public static void main(String[] args) throws Throwable {
        MethodHandle target = MethodHandles.lookup().findStatic(
                MethodHandleProxiesExceptionsDemo.class,
                "fail",
                MethodType.methodType(String.class));

        PlainAction plain =
                MethodHandleProxies.asInterfaceInstance(
                        PlainAction.class, target);
        CheckedAction checked =
                MethodHandleProxies.asInterfaceInstance(
                        CheckedAction.class, target);

        try {
            plain.run();
        } catch (UndeclaredThrowableException e) {
            System.out.println("undeclared wrapper: "
                    + e.getUndeclaredThrowable()
                            .getClass().getSimpleName());
            System.out.println("undeclared message: "
                    + e.getUndeclaredThrowable().getMessage());
        }

        try {
            checked.run();
        } catch (IOException e) {
            System.out.println("declared direct: " + e.getMessage());
        }

        System.out.println("null recognized: "
                + MethodHandleProxies.isWrapperInstance(null));

        try {
            MethodHandleProxies.wrapperInstanceTarget(
                    (PlainAction) () -> "ordinary");
        } catch (IllegalArgumentException e) {
            System.out.println("unwrap ordinary: rejected");
        }

        try {
            MethodHandleProxies.asInterfaceInstance(
                    IntegerInput.class, target);
        } catch (WrongMethodTypeException e) {
            System.out.println("wrong argument count: rejected");
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 --release 17 MethodHandleProxiesExceptionsDemo.java
java MethodHandleProxiesExceptionsDemo
```

Stdout:

```text
undeclared wrapper: IOException
undeclared message: disk-offline
declared direct: disk-offline
null recognized: false
unwrap ordinary: rejected
wrong argument count: rejected
```

**Analysis:**

1. Both wrappers have the same `()String` target, so both **throw IOException** when `run()` is called.
2. The `PlainAction.run()` interface **does not** declare the checked exception; the wrapper wraps it into `UndeclaredThrowableException`. Use `getUndeclaredThrowable()` (or `getCause()`) to retrieve the cause when debugging.
3. The `CheckedAction.run() throws IOException` interface allows the exception to be propagated directly, so catching `IOException` works as a normal Java contract.
4. `isWrapperInstance(null)` returns false; a wrapper created by an **ordinary lambda** is not accepted by `wrapperInstanceTarget`.
5. `IntegerInput.run(int)` is incompatible with the `()String` target due to missing parameters. `WrongMethodTypeException` appears at **adapter creation time**, separate from the `IOException` at invoke time.

For frameworks, it is necessary to clearly specify the **exception contract** of callbacks. Do not let checked exceptions turn into `UndeclaredThrowableException` at an outer layer and get logged as an unknown-source error.

## 8. Error table and timing of occurrence

| Condition | Common exception | Timing | Remediation |
| --- | --- | --- | --- |
| `intfc == null` or `target == null` | `NullPointerException` | Factory call | Do not pass null; validate beforehand. |
| `intfc` is a class, not an interface | `IllegalArgumentException` | Factory | Choose a valid public interface. |
| Package-private or `sealed` interface | `IllegalArgumentException` | Factory | Use a public, non-sealed interface per contract. |
| Interface has two different abstract method names | `IllegalArgumentException` | Factory | Write a manual adapter or use `Proxy` if multiple differently named methods are needed. |
| Interface has overloads but one descriptor cannot be adapted | `WrongMethodTypeException` | Factory | Adjust `target.asType`/combinators properly or separate the cases. |
| Interface needs 1 parameter, target has 0 | `WrongMethodTypeException` | Factory | Use `dropArguments` if dropping the input is allowed, or fix the target. |
| Target throws a checked exception not declared by the interface | `UndeclaredThrowableException` | When calling method via wrapper | Declare the checked exception if appropriate or handle the cause. |
| `wrapperInstanceTarget(x)` with an ordinary lambda/object | `IllegalArgumentException` | When unwrapping | Check `isWrapperInstance(x)` first. |
| Target receives a reference of a different actual type | `ClassCastException` or related type conversion error | At call time | Identify erasure, casts, conversions, validate data. |
| Adapter received a handle to private logic, handed to other code | Capability risk | After exposing wrapper | Do not publish the adapter when the target's permissions should not be shared. |

### 8.1. Conversion before or after creation?

The Javadoc requires the target's type to be checked **before the wrapper is created**, as if applying `asType` to each declaration to be implemented. This means an **unadaptable** mismatch will be detected at the factory. However, if a reference-type adaptation is acceptable at the descriptor level and only the specific data is invalid, errors like `ClassCastException` may arise **at invoke time**.

For example, a generic interface often has an erased descriptor like `(Object)Object`. Converting `Object` to a specific type may be a dynamic cast; do not infer that testing with one `Integer` value succeeding means every `Object` will be handled by the target.

### 8.2. Object methods, default methods, and identity

The wrapper object still has methods such as `toString`, `equals`, `hashCode`; those methods **are not counted** as abstract names of a single-method interface. But do not force them into becoming business call paths to the target. If you need to compare callbacks or cache them, use explicit keys/metadata instead of relying on the runtime class name or shape of the wrapper.

A default method like `Renderer.label()` can run according to the interface's default implementation; it is not turned into a separate branch calling the `show` handle. If you want multiple method **names** with separate semantics, this factory is not a general solution.

## 9. Comparison with lambdas, method references, LambdaMetafactory, and dynamic Proxy

| Implementation approach | Advantages | Limitations / when to avoid |
| --- | --- | --- |
| **Java Lambda** `x -> compute(x)` | Concise, compile-time type-safe, readable. | Requires Java code or a matching method reference at compile time; cannot directly take an arbitrary dynamic MethodHandle as a callback without an adapter. |
| **MethodHandleProxies.asInterfaceInstance** | Turns an existing `MethodHandle` into an object implementing a public single-method interface; handles `asType`; easy to use in dynamic runtimes. | Does not support non-public/sealed interfaces, multiple abstract method names; has wrapper indirection; requires managing checked exceptions. |
| **LambdaMetafactory** | Tool for linking lambdas/SAMs at the `invokedynamic` level with Lookup and call-site semantics; usually suitable when building custom runtimes/bytecode generators. | Bootstrap, invoked type, and signature constraints are more complex; not a direct one-line replacement for `asInterfaceInstance`. |
| **Proxy.newProxyInstance** | Can implement **multiple differently named methods** with `InvocationHandler` handling each; supports many dynamic cases. | Requires dispatch through handler/reflection semantics, method tables, and intentional handling of default methods/exceptions; does not share the simple contract of MethodHandleProxies. |
| **Manual adapter class** | Maximum control over validation, exception policy, logging, per-method semantics. | Lots of boilerplate; not automatically suited for method handles chosen at runtime. |

### 9.1. When using MethodHandleProxies is reasonable

- A public plugin API requires a callback interface with only one method name, while the application already has a method handle linked from runtime configuration.
- A dispatch pipeline uses MethodHandle, but an external library only accepts `Runnable`, `Comparator`, or a similar callback interface.
- Quickly prototyping a typed interface contract on an existing method handle without generating custom bytecode.

### 9.2. When to choose another tool

- **Non-public or sealed** interface: must change the interface/implementation design; cannot force the factory to accept it via reflection.
- Interface has **multiple differently named abstract methods**: an adapter class or dynamic Proxy may be more suitable.
- Need fine-grained control over each overload's semantics, logging, retries, or exception policy: a hand-written wrapper may be easier to maintain.
- A high-performance application extremely sensitive to hot-path overhead: should measure and consider suitable lambdas/handle combinators/LambdaMetafactory, **do not assume** proxy is faster or slower on every JVM.
- No dynamic binding requirement: ordinary Java lambdas or method references are usually simpler and clearer in intent.

## 10. Security and module/class loader boundaries

`MethodHandleProxies` **is not a privilege-escalation mechanism**. A `MethodHandle` created by `Lookup.findStatic`, `findVirtual`, `unreflect`, etc., already undergoes **access checks at handle creation time**. If the caller has permission to create a handle to a private method and then hands out the wrapper externally, the wrapper's recipient can trigger that method through the interface: the capability has been transferred.

Remember:

1. Only expose a MethodHandle/adapter externally if the consumer is genuinely allowed to invoke the bound operation.
2. The interface must be public and non-sealed per the factory's conditions; the Javadoc states the factory **performs no additional access checks** on the interface beyond the stated conditions. Do not infer that merely having a wrapper bypasses JPMS to create handles to arbitrary members.
3. If the interface and target use classes loaded by **different class loaders**, `Class` identities and descriptors may be incompatible even if type names look the same. `MethodHandle` and `MethodType` use actual `Class` objects, not just string names.
4. With named modules, design package `exports`/`opens`, module reads relationships, and `Lookup` permissions at the **handle creation** stage. Do not enable `--add-opens` indiscriminately just to dodge API design flaws.
5. If a legacy security manager is installed (Java 17 context), the Javadoc describes `asInterfaceInstance` as caller-sensitive and saving the caller's context for security manager checks when the wrapper invokes the target. This is a legacy compatibility detail; do not use it as the primary protection mechanism for new applications.

**Especially:** `wrapperInstanceTarget(wrapper)` can provide a handle behaviorally equivalent to the target; if the wrapper is already a sensitive capability, exposing the interface object may entail access to the handle. Do not think a wrapper is a sandbox just because it has an abstract interface type.

### 10.1. Cannot "swap the target" by reassigning a Java variable

If code creates:

```java
MethodHandle current = first;
MyAction action =
        MethodHandleProxies.asInterfaceInstance(
                MyAction.class, current);
current = second;
```

this is an **illustrative** snippet with a public interface `MyAction` and two compatible handles `first`/`second`. Reassigning the Java variable `current` **does not** make the `action` object automatically follow `second`; the factory already received the handle reference at adapter creation time.

If the goal is to **relink calls dynamically**, you can pass a handle carrying a mutable dispatch mechanism, for example `MutableCallSite.dynamicInvoker()`, and then control the call site's target according to its memory semantics. However, this is a separate **CallSite** technique, not a target-swapping feature of `MethodHandleProxies`; you must follow `setTarget`/`syncAll` rules or use an appropriate CallSite kind.

## 11. Performance and maintainability

There is no contract that `MethodHandleProxies` always produces an implementation as fast as a compiler lambda or that it can inline every case. It solves the **handle-to-interface interop** problem, not a performance promise.

Practical suggestions:

- Create the adapter **once** at bootstrap/initialization when the target is stable; reuse the interface object instead of creating a wrapper on every request.
- With overloads, test all signatures and conversion behaviors **before publishing** the adapter.
- Avoid catching every `Throwable` in a callback and turning it into a fake success value; log the exact cause of `UndeclaredThrowableException` when it occurs.
- Benchmark on representative workloads with warmup using JMH if throughput/latency matters. Measure both **proxy creation** cost and **invoke through interface** cost, as they are two different quantities.
- Use clear public contracts so code readers understand what the callback invokes; since MethodHandle can be chosen dynamically, appropriate metadata/debugging is needed.

If the interface is a stable public API and the target is just a simple static function, using a normal Java lambda may be less complex. Choose `MethodHandleProxies` when the real value comes from a **target handle selected/composed at runtime**.

## 12. How to test properly

A proper test suite should include:

1. **Valid interface:** public, non-sealed, exactly one abstract method name; the wrapper returns the expected value when called.
2. **Same-name overloads:** two different descriptors still bind the same target and convert properly for each overload.
3. **Default and Object methods:** do not invalidate the interface; do not rely on implementation details of object methods.
4. **Input boundaries:** ordinary class, package-private interface, sealed interface, two different abstract names are all rejected.
5. **Type errors:** target with wrong argument count or invalid conversion -> `WrongMethodTypeException` at the factory.
6. **Wrapper metadata:** `isWrapperInstance(wrapper) == true`; `wrapperInstanceType(wrapper) == requestedType`; `wrapperInstanceTarget(wrapper)` is behaviorally equivalent.
7. **Non-wrapper objects:** ordinary lambda -> `isWrapperInstance == false` and unwrap -> `IllegalArgumentException`.
8. **Checked exceptions:** declared by interface -> thrown directly; undeclared -> `UndeclaredThrowableException` with the appropriate cause.
9. **Null:** null arguments at the factory -> `NullPointerException`; `isWrapperInstance(null) == false`.
10. **Security:** test not granting private handles to untrusted consumers; module/class-loader boundaries if present in the deployment environment.

### 12.1. Check by signature instead of guessing by method name

When an adapter fails, print:

```java
System.out.println(target.type());
```

and compare against the erased Java descriptor of each interface method. If arity does not match, use combinators like `dropArguments` or `insertArguments` only when semantics genuinely allow it. If parameter values need to be transformed (e.g., parsing String to int), there must be an explicit conversion handle/logic; `asType` does not automatically parse application data.

### 12.2. Testing whether output works is not enough

A single test `adapter.apply(7) == "value=7"` does not prove the system properly handles type errors, checked exceptions, overloads, and module configurations. Write tests for **rejected** input contracts, not just the happy path.

## 13. Common misconceptions

| Misconception | Reality | How to fix |
| --- | --- | --- |
| "Must have `@FunctionalInterface` to be usable." | The factory checks for **one abstract method name** and public/non-sealed; the annotation is not a condition. | Read the interface structure, including overloads and default methods. |
| "Any interface with one method is valid, even package-private." | The interface must be **public**. | Publish the interface as public when it is the intended contract. |
| "A sealed interface also works because it has one abstract method." | The Java 17 contract rejects sealed. | Use a permitted implementation or another API. |
| "Overloading two descriptors means two method names, so it must be rejected." | The **same name** is allowed if the target can adapt to both. | Check each descriptor and conversion semantics. |
| "A `()String` target automatically serves `apply(int)`." | The factory does not add arguments automatically. | Use `dropArguments` or fix the target. |
| "The wrapper calls the target using invokeExact." | It behaves like `target.invoke`, with checked adaptation. | Understand `asType` and factory/invocation exceptions. |
| "An ordinary lambda is a wrapperInstance." | Only instances from `asInterfaceInstance` are recognized. | Call `isWrapperInstance` before unwrapping. |
| "wrapperInstanceTarget is always the exact same original `target` object." | Only **behavioral equivalence** is guaranteed. | Do not assert identity; test the contract. |
| "Checked exceptions are always thrown as-is." | If the interface does not declare them, they are wrapped in `UndeclaredThrowableException`. | Design the throws clause or unwrap the root cause. |
| "Reassigning the `target` variable makes the adapter use the new handle too." | The adapter is bound to the handle passed at creation time. | Create a new adapter or use a dynamic dispatch handle if needed. |
| "A wrapper is harmless because it only has an interface type." | The handle may have been granted sensitive private access. | Manage capabilities; do not distribute indiscriminately. |
| "Creating a proxy is always faster than a lambda." | The API makes no such performance promise. | Benchmark, and choose the simplest abstraction level. |

## 14. Self-check questions

**Question 1.** Why can `MethodHandleProxies.asInterfaceInstance(IntToText.class, target)` adapt a `(long)String` target to `String apply(int)`?

**Answer:** `asInterfaceInstance` checks adaptation like `MethodHandle.asType`; `int → long` is a valid widening primitive conversion, so the interface method's descriptor can invoke the target.

**Question 2.** Is an interface with `render(int)` and `render(long)` automatically rejected for having two methods?

**Answer:** No. Both have the same **name `render`**; the factory allows same-name overloads and adapts the target to each descriptor. An incompatible overload can still cause the factory to throw `WrongMethodTypeException`.

**Question 3.** What about an interface with `render(int)` and `format(int)`?

**Answer:** Invalid because it has **two** abstract method **names**. `asInterfaceInstance` throws `IllegalArgumentException`.

**Question 4.** Is a `public sealed interface` with only one abstract method accepted?

**Answer:** Not on Java 17; the contract requires the interface to be public and **not sealed**.

**Question 5.** Why is a Java lambda implementing the same interface not accepted by `wrapperInstanceTarget`?

**Answer:** It was not created by `MethodHandleProxies.asInterfaceInstance`; `isWrapperInstance` returns false and unwrapping throws `IllegalArgumentException`.

**Question 6.** If the target throws `IOException` but the interface does not declare `throws IOException`, what does the caller see?

**Answer:** An `UndeclaredThrowableException` wrapping the checked `IOException`; use `getUndeclaredThrowable()`/`getCause()` to retrieve the cause.

**Question 7.** If the `MethodHandle target` variable is reassigned after creating the adapter, do calls on the adapter automatically switch implementations?

**Answer:** No. The adapter uses the handle passed in at creation time; dynamic dispatch requires a handle/CallSite with target-switching semantics or recreating the adapter.

**Question 8.** Why should you not send a wrapper created from a sensitive private MethodHandle to an untrusted plugin?

**Answer:** A handle is a capability. Access permissions were already verified when creating the handle; the wrapper forwards calls into that capability and does not block them just because the method has a public interface type.

## 15. Summary

- **`MethodHandleProxies.asInterfaceInstance`** adapts a MethodHandle to a **public, non-sealed, single-method interface**.
- **Single-method** here means **one abstract method name**; same-name overloads/bridge methods are permitted if all descriptors can be adapted. Object methods and default methods are not counted.
- Adaptation follows **`asType` / `target.invoke` semantics**; wrong arity/unconvertible types are reported with `WrongMethodTypeException` right at the factory.
- **`isWrapperInstance`, `wrapperInstanceTarget`, `wrapperInstanceType`** apply only to wrappers created by the factory itself; the recovered target only needs to be **behaviorally equivalent**.
- **Undeclared checked exceptions** are wrapped in `UndeclaredThrowableException`; pay attention to the callback contract.
- A wrapper **is not a sandbox or an automatic target-swapper**. Protect MethodHandle permissions and choose lambdas, LambdaMetafactory, Proxy, or another adapter class when this factory is not suitable.

### Official References (Java SE 17)

- [`MethodHandleProxies`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandleProxies.html): single-method interface definition, public/non-sealed requirement, overloads, conversions, wrapper metadata, and checked exceptions.
- [`MethodHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html): `invoke`, `invokeExact`, `asType`, types, and capabilities.
- [`MethodHandles`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html): `Lookup.findStatic`, combinators such as `dropArguments`/`insertArguments`.
- [`MethodType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html): representation of Java/JVM signatures.
- [`LambdaMetafactory`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/LambdaMetafactory.html) and [`Proxy`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Proxy.html): other dynamic options, with different contracts and limitations.
