# `MethodHandle.invoke`, `invokeExact`, and Argument Conversion Differences

## 1. Lesson Objectives

`java.lang.invoke.MethodHandle` is a typed reference to an invocable operation, such as a method, constructor, or field access. Every handle has **its own `MethodType`**. When invoking a handle, what matters is whether the signature at the call site matches the handle's signature.

This lesson helps you:

- Read `handle.type()` to know the exact argument types, parameter count, and return type.
- Use `invokeExact(...)` (exact match) and `invoke(...)` (allows type conversions) properly.
- Explain boxing/unboxing, numeric widening, reference casts, and conversion failures.
- Recognize why the **return type at the call site** can also cause `invokeExact` to fail.
- Proactively build an adapter with `asType(...)` when you want to change the signature.
- Distinguish `MethodHandle` from `VarHandle` access modes.

The examples below run on Java 17+ with no external libraries.

## 2. `MethodType` Is the Contract of a MethodHandle

Consider the method:

```java
public static long sum(long a, long b) {
    return a + b;
}
```

Create a handle to that static method with `MethodHandles.Lookup.findStatic` (the snippet below is placed inside `MethodHandleInvokeDemo`, which defines `sum`):

```java
MethodHandle sum = MethodHandles.lookup().findStatic(
        MethodHandleInvokeDemo.class, "sum",
        MethodType.methodType(long.class, long.class, long.class));
System.out.println(sum.type()); // (long,long)long
```

`MethodType.methodType(returnType, parameterTypes...)` takes the **return type first**, followed by each parameter type. `(long,long)long` means accepting `long, long` and returning `long`. `MethodType` does not store the method name; it only describes the types required to invoke.

**Two types to distinguish:**

| Concept | Meaning |
| --- | --- |
| **Target type** | The actual signature of the handle, inspected via `sum.type()` |
| **Call-site type** | The signature derived from the static types of the argument expressions and the result type expected by code at the call site |

`invoke` and `invokeExact` are **signature-polymorphic** methods: each call is compiled with the actual argument types and return type at that location. Even though the API declaration looks like `Object...`, ordinary calls do not pack arguments into an `Object[]` via Java varargs rules. The JVM checks the signature emitted in bytecode.

## 3. `invokeExact` Requires an Exact Match, No Conversions

For a `(long,long)long` handle, this is a valid call:

```java
long answer = (long) sum.invokeExact(10L, 20L); // 30
```

The call site has type `(long,long)long`, matching `sum.type()` completely.

By contrast:

```java
long answer = (long) sum.invokeExact(10, 20L);
```

The call above still **compiles** because this is a signature-polymorphic API, but at runtime it throws `WrongMethodTypeException`: the literal `10` has type `int`; `invokeExact` does not automatically widen `int` to `long`. Fix: change it to `10L` or `(long) 10`.

### The Return Type Must Also Match

```java
Object result = sum.invokeExact(10L, 20L);
```

This snippet also throws `WrongMethodTypeException`. Even though a `long` value can be boxed into `Long` in many other Java contexts, `invokeExact` does not automatically box the return value for a call site expecting `Object`.

Three frequently confused cases:

- `long x = (long) sum.invokeExact(10L, 20L);`: valid; the requested return type is `long`.
- `Object x = sum.invokeExact(10L, 20L);`: invalid; the call site expects return type `Object`.
- `sum.invokeExact(10L, 20L);` written as a standalone statement: the call site expects `void`, so it is also invalid when the handle returns `long`.

If you want to discard the result, you can assign it to a suitable `long` variable. `invokeExact` must match **arity, every parameter type, and the return type**; there is no implicit coercion in the sense of `invoke`.

## 4. `invoke`: Can Adapt the Signature via `asType`

If the call-site type matches the target type, `invoke` behaves like `invokeExact`. When they differ, `invoke` attempts to adapt the handle as if by `handle.asType(callSiteType)` and then executes. The JVM may optimize this without allocating a visible adapter.

```java
long answer = (long) sum.invoke(10, 20L); // 30
```

The call site has type `(int,long)long`. `invoke` allows converting `int` to `long` before calling `sum`.

Another example:

```java
Object result = sum.invoke(10, 20);
System.out.println(result.getClass().getSimpleName()); // Long
```

Both `int` arguments are widened to `long`; the primitive `long` result is boxed into `Long` to be used as `Object`.

Typical conversions that can happen when `invoke` adapts types include: primitive widening (such as `int -> long`); boxing/unboxing between primitives and wrappers; casts between reference types (checked at runtime); and compatible return conversions. These operations follow the rules of `MethodHandle.asType`, **not arbitrary data conversions**.

| Case (target is the type on the right) | `invokeExact` | `invoke` |
| --- | --- | --- |
| `long` -> `long` | Allowed | Allowed |
| `int` -> `long` | `WrongMethodTypeException` | Can widen |
| `Integer` -> `int` | Static type mismatch | Can unbox |
| `Object` holding `String` -> `String` | Static type mismatch | Can cast at runtime |
| Returned `long` -> `Object` at call site | Return type mismatch | Can box |
| String `"123"` -> `long` | Type mismatch | Does not parse strings automatically |
| Missing or extra arguments | Invalid | Invalid for fixed-arity handles |

**Note:** *varargs collector* handles have additional rules for gathering trailing arguments. For ordinary handles, `invoke` does not automatically add or drop parameters; an appropriate adapter is needed for such changes.

## 5. Complete Java 17+ Program

Create file `MethodHandleInvokeDemo.java`:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;

public class MethodHandleInvokeDemo {
    public static long sum(long a, long b) {
        return a + b;
    }

    public static String decorate(String text) {
        return "[" + text + "]";
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodHandle sum = lookup.findStatic(
                MethodHandleInvokeDemo.class, "sum",
                MethodType.methodType(long.class, long.class, long.class));
        System.out.println(sum.type());

        long exact = (long) sum.invokeExact(10L, 20L);
        long flexible = (long) sum.invoke(10, 20L);
        Object boxed = sum.invoke(10, 20);
        System.out.println("exact=" + exact);
        System.out.println("invoke=" + flexible);
        System.out.println("boxed=" + boxed.getClass().getSimpleName());

        MethodHandle adapted = sum.asType(
                MethodType.methodType(long.class, int.class, long.class));
        long adaptedExact = (long) adapted.invokeExact(10, 20L);
        System.out.println("adaptedExact=" + adaptedExact);

        try {
            long ignored = (long) sum.invokeExact(10, 20L);
            System.out.println(ignored);
        } catch (WrongMethodTypeException e) {
            System.out.println("exact arguments mismatch");
        }

        try {
            Object ignored = sum.invokeExact(10L, 20L);
            System.out.println(ignored);
        } catch (WrongMethodTypeException e) {
            System.out.println("exact return mismatch");
        }

        MethodHandle decorate = lookup.findStatic(
                MethodHandleInvokeDemo.class, "decorate",
                MethodType.methodType(String.class, String.class));
        System.out.println((String) decorate.invoke((Object) "Java"));
        try {
            String ignored = (String) decorate.invoke((Object) Integer.valueOf(7));
            System.out.println(ignored);
        } catch (ClassCastException e) {
            System.out.println("bad runtime argument");
        }
    }
}
```

Compile and run:

```bash
javac MethodHandleInvokeDemo.java
java MethodHandleInvokeDemo
```

Verified exact output:

```text
(long,long)long
exact=30
invoke=30
boxed=Long
adaptedExact=30
exact arguments mismatch
exact return mismatch
[Java]
bad runtime argument
```

**Analysis:** `sum.invokeExact(10L, 20L)` has the exact signature. `sum.invoke(10, 20L)` widens `int` to `long`. When assigning the `invoke` result to `Object`, `long` is boxed so the class name is `Long`. The two intentionally mismatched exact calls fail on the `int` argument and the `Object` return type respectively, so both raise `WrongMethodTypeException`. Finally, `decorate.invoke((Object) "Java")` casts `Object` to `String` successfully because the actual object is a string; an actual `Integer` causes `ClassCastException` on cast.

The program uses `main(String[] args) throws Throwable` because `MethodHandle.invoke` and `invokeExact` have signature `throws Throwable`; exceptions thrown by the target method can pass straight through the handle. In real production code, enforce an explicit exception-handling policy.

## 6. Creating an Adapter with `asType` for Exact Calls

If an application frequently calls with signature `(int,long)long` while the original handle has type `(long,long)long`, you can create a new handle:

```java
MethodHandle adapted = sum.asType(
        MethodType.methodType(long.class, int.class, long.class));

System.out.println(adapted.type()); // (int,long)long
long answer = (long) adapted.invokeExact(10, 20L); // 30
```

`adapted.type()` is already `(int,long)long`, so `invokeExact` on the adapter needs no further conversion at the call site. Inside the adapter, the `int` value is widened to `long` before forwarding to the original handle. MethodHandles are immutable; `sum.type()` remains unchanged.

Choose the invocation style to fit your requirements: use `invokeExact` when you know the exact signature and want mismatch errors caught clearly; use `invoke` when compatible conversions are desired; use `asType` to explicitly represent and reuse an adapter with the new signature. `MethodHandles.explicitCastArguments` handles intentional cases needing broader casting rules than `asType`, though you must manage the risk of data loss.

**Do not equate this with** `invokeWithArguments(...)`: this API accepts `Object[]` or `List<?>` and invokes generically, suited for times when arguments must be taken from a dynamic list. The following snippet is a code fragment inside the program in section 5:

```java
Object result = sum.invokeWithArguments(10L, 20L);
System.out.println(result); // 30
```

`invokeWithArguments` performs boxing/unboxing and argument-list processing; it does not enforce exact matching like `invokeExact`.

## 7. Static Types and Runtime Types Differ

`invokeExact` relies on the **static type of each expression at the call site**, not the actual class that an `Object` variable points to at runtime.

```java
Object value = Long.valueOf(10L);
```

For a `(long,long)long` handle:

- `(long) sum.invokeExact(value, 20L)`: fails because the call site's first argument has static type `Object`.
- `(long) sum.invoke(value, 20L)`: can succeed via runtime cast/unboxing from an `Object` containing `Long` to `long`.
- `long unboxed = ((Long) value).longValue();` then `(long) sum.invokeExact(unboxed, 20L)`: matches exactly.

This also applies to variables declared with an interface or superclass type; assigning a concrete instance does not change the variable's static type. With generics, Java uses the **erased** type in the call signature.

When receiving a result, the expected type also matters. In many cases, a cast directly on the call expression `(long) handle.invokeExact(...)` is not merely casting the value *after* the call; it determines **the return type of the call site itself**.

## 8. Common Exceptions

| Exception | Scenario | How to Handle |
| --- | --- | --- |
| `WrongMethodTypeException` with `invokeExact` | Call-site signature differs from `handle.type()`, including the return part | Compare arity, parameter types, and return type; add casts or adjust literals |
| `WrongMethodTypeException` with `invoke` | Unable to build a valid `asType` adaptation or invalid arity | Use compatible types or an intentional adapter |
| `ClassCastException` with `invoke` | Adapter allows a reference cast, but the actual object lacks a compatible type | Check runtime type before invoking |
| `NullPointerException` during conversion | Unboxing `null` into a primitive | Guard against null values or choose a reference-accepting contract |
| Exception from target method | The actual target throws an exception | Handle according to the target's contract |

Troubleshooting workflow: read `handle.type()`; list the **static type** of every argument; determine the return type at the call site (cast or used as a `void` statement); check `asType` conversion feasibility; and finally check runtime values and target exceptions. Do not "fix" `invokeExact` calls by casting everything to `Object`, as that usually makes the signature even more mismatched.

A `findVirtual` handle also requires an appropriate receiver in the **first argument** (for example, invoking `String.length` via a handle with signature `(String)int`). Do not forget the receiver when counting arity.

## 9. Relation to `VarHandle`

`VarHandle` belongs to the same `java.lang.invoke` package, but is normally used via **access modes** such as `get`, `set`, and `compareAndSet`, rather than calling `MethodHandle.invoke` or `MethodHandle.invokeExact` directly. Access modes also use signature-polymorphic invocation and have type-checking rules.

In Java 17, you can create a VarHandle with **exact behavior**:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public class VarHandleBehaviorDemo {
    private static int number;

    public static void main(String[] args) throws ReflectiveOperationException {
        VarHandle handle = MethodHandles.lookup().findStaticVarHandle(
                VarHandleBehaviorDemo.class, "number", int.class);
        handle.set(7);
        System.out.println((int) handle.get());

        VarHandle exactBehavior = handle.withInvokeExactBehavior();
        exactBehavior.set(9);
        System.out.println((int) exactBehavior.get());
    }
}
```

Save as `VarHandleBehaviorDemo.java`, run:

```bash
javac VarHandleBehaviorDemo.java
java VarHandleBehaviorDemo
```

Verified output:

```text
7
9
```

`withInvokeExactBehavior()` sets the mode that enforces **exact access-mode signature matching** without creating a new MethodHandle. To obtain a MethodHandle corresponding to an access mode, look up `VarHandle.toMethodHandle(VarHandle.AccessMode)`.

## 10. Self-Check Questions

1. For handle `(long,long)long`, does `(long) h.invokeExact(1, 2L)` run? **No**, argument `1` is `int`. Use `1L`.
2. Can `Object x = h.invoke(1, 2)` run? **Yes** when adaptation is valid: widens both `int`s to `long` and boxes the `long` result to `Long`.
3. Why is `Object x = h.invokeExact(1L, 2L)` invalid? **The call site's `Object` return type differs from the handle's `long`**.
4. Does `asType` mutate the original `h`? **No**; it returns a new handle with the new signature.
5. Why can `invoke` throw `ClassCastException` even with a valid adapter? **The runtime value** fails the reference cast.
6. If arguments are only available in a `List<?>` at runtime, which API should you look into? `invokeWithArguments(List<?>)`.
7. Why can `h.invokeExact(...)` used as a statement fail when the target returns `long`? Because the call site's return type becomes `void`.

## 11. Summary and References

- `invokeExact`: matches 100% of the call-site types with `handle.type()`, including parameters **and return**.
- `invoke`: adapts the signature via `asType` rules when valid; does not parse arbitrary data.
- `asType`: creates an adapter with a new type, allowing `invokeExact` with a deliberately chosen signature.
- `WrongMethodTypeException` signals that you should inspect types on **both sides**, while `ClassCastException` usually involves runtime reference values.
- `VarHandle` uses access modes and provides `withInvokeExactBehavior()` to opt into exact matching when accessing variables.

Official JDK 17 documentation:

- [MethodHandle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html)
- [MethodType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html)
- [MethodHandles](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html)
- [VarHandle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.html)