# 7.5 Distinguishing `WrongMethodTypeException`, `ClassCastException`, and `null` unboxing errors

When invoking a `MethodHandle`, three easily confused errors are:

- **`WrongMethodTypeException`**: the *call-site type* does not match the handle's `MethodType`, and cannot (or is not allowed to) be adapted.
- **`ClassCastException`**: the call-site type can be adapted, but the **actual value** cannot be cast to the required type; sometimes the error comes from the target code or a cast at the caller.
- **`NullPointerException` when unboxing `null`**: the adapter needs to convert a `null` reference into a primitive such as `int` or `long`. There are also other `NullPointerException`s, such as an instance method's receiver being `null`.

All three errors can appear in a dynamic invocation flow. To diagnose accurately, you first need to distinguish **the handle's type**, **the call-site type**, **the runtime value**, and **the target code being executed**.

> Context: Java 17+, `java.lang.invoke.MethodHandle`, `MethodType`, `MethodHandles.Lookup` APIs; this article focuses on `invokeExact`, `invoke`, and the `asType` adapter.

## 1. Four layers of information before classifying errors

Suppose we look up the handle for the method `static int plusOne(int value)`:

~~~java
MethodHandle one = MethodHandles.lookup().findStatic(
        MethodHandleFailureDemo.class,
        "plusOne",
        MethodType.methodType(int.class, int.class));
System.out.println(one.type()); // (int)int
~~~

The snippet above is only an illustration inside the `MethodHandleFailureDemo` class; the full runnable program is in section 6.

Here:

1. **Target** is the method `plusOne(int)`.
2. **Handle type** is `(int)int`: takes an `int`, returns an `int`. `MethodType` includes **both parameters and return type**.
3. **Call-site type** is recorded by the compiler into the signature-polymorphic call. For example, `(int) one.invokeExact(4)` requests `(int)int`; `(Object) one.invokeExact(4)` requests `(int)Object` even though the target still returns `int`.
4. **Actual value** can be a number, a string, or `null`. A call site with type `Object` can pass the string `"4"` or `Integer.valueOf(4)`; only at runtime is it known which value can be converted.

The `invokeExact` and `invoke` syntax is **signature-polymorphic**: the source call looks like a method taking `Object...`, but the JVM uses the actual descriptor generated at the call site. The Java compiler does not automatically perform normal parameter conversions for these two invokers; the argument expression types play the decisive role.

For `invokeExact`, the return type is inferred from the direct cast on the call expression, or the contextual type specified by Java: without a cast, using the result as an expression may have type `Object`; calling it as a standalone statement has return type `void`. Therefore, merely changing the result-receiving context can also produce a `WrongMethodTypeException`.

## 2. Quick decision table

| Symptom | First check | Example | Typical result |
| --- | --- | --- | --- |
| `invokeExact` has the wrong parameter type, return type, or parameter count | `handle.type()` compared to the call-site descriptor | Handle `(int)int`, caller uses `(long)int` | `WrongMethodTypeException` |
| `invoke` or `asType` needs a conversion that **cannot exist at the type level** | Can a valid adapter be created? | `String` → `int` via `asType` | `WrongMethodTypeException` |
| Type conversion is **theoretically possible**, but the actual object has the wrong type | Actual runtime type of the `Object` value | `Object value = "4";` then `int` is needed | `ClassCastException` |
| Need to unbox a `null` value into a primitive | Is there a `null` at a wrapper/reference → primitive boundary? | `Integer value = null;` used with a handle taking `int` | `NullPointerException` |
| The target itself throws an error | Has execution entered the target? Where does the stack trace point? | `String.length()` with a `null` receiver | `NullPointerException`, **not** an unboxing error |

These exceptions **do not exclude** errors originating from the target itself: a method invoked through a handle can actively throw all three types. Only the stack trace, where the exception originates, and the target code reveal the cause.

## 3. `WrongMethodTypeException`: incompatible descriptor

### 3.1. `invokeExact`: must match exactly

For a handle with type `(int)int`:

~~~java
int ok = (int) one.invokeExact(4);       // Success
int bad = (int) one.invokeExact(4L);     // WrongMethodTypeException
Object badReturn = (Object) one.invokeExact(4); // WrongMethodTypeException
~~~

The two failing lines have different causes:

- `4L` has type `long`; the call site requests `(long)int`, which differs from `(int)int`. `invokeExact` **does not** automatically narrow `long` to `int`.
- The `(Object)` cast requests return type `Object` at the call site. Even though Java can box `int` into `Integer` in other situations, **`invokeExact` does not automatically box the result**.

Even calling `one.invokeExact(4);` as a statement without using the result requests return type `void` at the call site and can fail if the handle returns `int`. Do not confuse this with "ignoring the return value" after a flexible `invoke` call.

The right fix is to make the **actual type** explicit:

~~~java
int value = (int) one.invokeExact(4);
~~~

If the caller needs a different type, choose `invoke` to allow the specified conversions, or create an adapter with `asType` and then call `invokeExact` using **the adapter's exact type**.

### 3.2. `invoke`: flexible, but not unlimited

`invoke` allows a call whose descriptor differs from `handle.type()`, semantically equivalent to adapting the handle with `asType(callSiteType)` and then invoking exact:

~~~java
Object boxed = (Object) one.invoke(4); // returned int is boxed to Integer
long widened = (long) one.invoke(4);  // returned int is widened to long
~~~

However, `(int) one.invoke("4")` still leads to `WrongMethodTypeException`: the static parameter type `String` has no valid direct `asType` conversion to primitive `int`. `asType` does not parse the numeric string `"4"` into the number `4`.

The same kind of error can occur when the argument count does not match (aside from special rules for handles capable of collecting varargs). With `asType` directly, an unadaptable error is detected immediately at adapter creation time:

~~~java
one.asType(MethodType.methodType(int.class, String.class));
// WrongMethodTypeException: no valid String -> int conversion
~~~

**Do not fix every `WrongMethodTypeException` by blindly casting to `Object`.** Changing the descriptor may make the structure valid but shift the error to `ClassCastException` at runtime. You need to verify the actual type contract and input data.

## 4. `ClassCastException`: valid adapter, wrong value type

The `asType` adapter allows the parameter type `Object` to convert to `int` because `Object` *can hold* an `Integer`. However, the actual `Object` value at runtime may not be an appropriate numeric wrapper.

~~~java
Object candidate = "4";
int result = (int) one.invoke(candidate); // ClassCastException
~~~

The call site requests type `(Object)int`. Structurally, converting `Object` → `int` is allowed: the JVM will check the wrapper type and then unbox (possibly widening if appropriate). When it sees `String`, the reference-conversion/unboxing step fails and throws `ClassCastException`.

Distinguish two points in time:

~~~java
MethodHandle adapter =
        one.asType(MethodType.methodType(int.class, Object.class));
// Adapter creation SUCCEEDS: type = (Object)int

int valid = (int) adapter.invokeExact((Object) Integer.valueOf(4)); // 5
int invalid = (int) adapter.invokeExact((Object) "4");             // ClassCastException
~~~

`invokeExact` on the **adapter** of type `(Object)int` matches completely; the error occurs **inside the adapter** when the data `"4"` cannot be converted into an `int`.

In other cases, `ClassCastException` can come from:

- An ordinary Java cast at the **caller** (not the handle adapter).
- The **target** code itself performing an invalid cast or throwing the exception.
- Another adapter (for example `asSpreader`/`invokeWithArguments`) having to cast each argument.

Check the stack trace and the conversion site. Seeing `ClassCastException` **does not prove** that the handle was created with the wrong type.

## 5. `NullPointerException` when unboxing `null`

Unboxing is converting from a wrapper/reference to a primitive, such as `Integer` → `int`. There is no primitive value corresponding to `null`, so an `asType` conversion from `null` to a primitive can throw `NullPointerException`.

### 5.1. `null` in an argument

~~~java
Integer boxed = null;
int result = (int) one.invoke(boxed); // NullPointerException when unboxing
~~~

The underlying handle requires `int`, and the `invoke` call site has parameter type `Integer`. Type adaptation can be established; the error only appears **at runtime** because the value to unbox is `null`.

If you use `one.invokeExact(boxed)` with a call-site argument of `Integer`, that is first an **incorrect descriptor**, leading to `WrongMethodTypeException`. `invokeExact` itself does not unbox `Integer` to `int`.

Note: the expression `(int) (Integer) null` also causes an NPE due to **Java unboxing before the call**; this is a different error source from unboxing inside the adapter.

### 5.2. `null` in the return value

If the target returns `Integer` and actually returns `null`:

~~~java
MethodHandle nullable = MethodHandles.lookup().findStatic(
        MethodHandleFailureDemo.class,
        "nullableResult",
        MethodType.methodType(Integer.class, int.class));

Integer safe = (Integer) nullable.invokeExact(1); // null, no error yet
int unsafe = (int) nullable.invoke(1);             // NullPointerException
~~~

On the second line, the call site requests return type `int`, while the target returns `Integer`; the adapter tries to unbox the `null` result. Returning a `null` reference **is not automatically an error**; an error only occurs when a subsequent step requires a primitive.

### 5.3. Do not lump every NPE into "null unboxing"

For example, `String.length()` invoked through a handle with receiver `(String) null` also throws `NullPointerException`. This is an **instance call with a null receiver**, not unboxing. Similarly, the target itself may dereference a null field or throw an NPE directly.

Another exception worth knowing: `MethodHandles.explicitCastArguments` has conversion rules **different from `asType`**; as of Java 17, when converting `null` to a primitive, an explicit-cast adapter may supply the corresponding **zero value**. Therefore, do not apply the rule "unboxing null always throws NPE" to **every** kind of adapter; check the specific API being used.

## 6. Complete, runnable Java 17 program with deterministic output

Save the entire program as **`MethodHandleFailureDemo.java`**. The `report` method catches the three exceptions to display the **class name**, avoiding dependence on error messages that may vary across JDK versions. The cases are arranged so that one failure does not block subsequent cases.

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;

public final class MethodHandleFailureDemo {
    static int plusOne(int value) {
        return value + 1;
    }

    static Integer nullableResult(int ignored) {
        return null;
    }

    @FunctionalInterface
    interface Operation {
        Object run() throws Throwable;
    }

    static void report(String label, Operation operation) {
        try {
            System.out.println(label + " -> " + operation.run());
        } catch (WrongMethodTypeException | ClassCastException | NullPointerException e) {
            System.out.println(label + " -> " + e.getClass().getSimpleName());
        } catch (Throwable e) {
            throw new AssertionError("Unexpected failure: " + label, e);
        }
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodHandle one = lookup.findStatic(
                MethodHandleFailureDemo.class,
                "plusOne", MethodType.methodType(int.class, int.class));

        System.out.println("handle: " + one.type());
        System.out.println("exact: " + (int) one.invokeExact(4));
        report("exact wrong argument", () -> (int) one.invokeExact(4L));
        report("exact wrong return", () -> (Object) one.invokeExact(4));
        report("invoke boxes result", () -> (Object) one.invoke(4));
        report("invoke widens result", () -> (long) one.invoke(4));
        report("impossible call type", () -> (int) one.invoke("4"));

        report("bad dynamic value", () -> {
            Object candidate = "4";
            return (int) one.invoke(candidate);
        });
        report("null unboxing argument", () -> {
            Integer boxed = null;
            return (int) one.invoke(boxed);
        });

        MethodHandle adapter = one.asType(
                MethodType.methodType(int.class, Object.class));
        System.out.println("adapter: " + adapter.type());
        report("adapter wrong value", () -> (int) adapter.invokeExact((Object) "4"));
        report("adapter null", () -> (int) adapter.invokeExact((Object) null));
        report("asType impossible", () -> {
            one.asType(MethodType.methodType(int.class, String.class));
            return "unreachable";
        });

        MethodHandle nullable = lookup.findStatic(
                MethodHandleFailureDemo.class,
                "nullableResult", MethodType.methodType(Integer.class, int.class));
        report("null exact return", () -> (Integer) nullable.invokeExact(1));
        report("null unboxing return", () -> (int) nullable.invoke(1));

        MethodHandle length = lookup.findVirtual(
                String.class, "length", MethodType.methodType(int.class));
        report("null receiver", () -> (int) length.invokeExact((String) null));
    }
}
~~~

Compile and run in the directory containing the file:

~~~bash
javac --release 17 MethodHandleFailureDemo.java
java MethodHandleFailureDemo
~~~

**Exact stdout:**

~~~text
handle: (int)int
exact: 5
exact wrong argument -> WrongMethodTypeException
exact wrong return -> WrongMethodTypeException
invoke boxes result -> 5
invoke widens result -> 5
impossible call type -> WrongMethodTypeException
bad dynamic value -> ClassCastException
null unboxing argument -> NullPointerException
adapter: (Object)int
adapter wrong value -> ClassCastException
adapter null -> NullPointerException
asType impossible -> WrongMethodTypeException
null exact return -> null
null unboxing return -> NullPointerException
null receiver -> NullPointerException
~~~

Reading the output by group:

1. The two `exact wrong ...` failures prove that `invokeExact` matches **both argument types and return type**.
2. The two lines `invoke boxes result`/`invoke widens result` prove that `invoke` has valid conversions; `impossible call type` proves that flexibility has limits.
3. `bad dynamic value` and `adapter wrong value` both produce `ClassCastException` because the source carries `String` while the target requires `int`. The `(Object)int` adapter was created successfully beforehand.
4. `null unboxing argument` and `adapter null` are both NPEs on the path converting an **argument** to `int`; `null unboxing return` is an NPE on the path converting the **result** `Integer` to `int`.
5. `null exact return` proves that returning `null` as type `Integer` causes no error. `null receiver` illustrates an NPE **unrelated to unboxing**.

This program uses `throws Throwable` on `main` because the two invokers `MethodHandle.invoke`/`invokeExact` declare that they can throw `Throwable`. In real applications, handle exceptions at the appropriate dynamic-call boundary instead of unconditionally catching `Throwable` and ignoring it.

## 7. Does `invokeWithArguments` behave differently?

`invokeWithArguments(Object...)` accepts inputs as `Object`, then uses the type-conversion mechanism to call the target. It is convenient for argument lists built at runtime, but it is not a shortcut that bypasses type checking. For the handle `one` of type `(int)int` in the program above, typical results are:

| Illustrative call (in `main`) | Result |
| --- | --- |
| `one.invokeWithArguments(4)` | Returns an `Integer` with value `5` |
| `one.invokeWithArguments()` | `WrongMethodTypeException` due to argument count mismatch |
| `one.invokeWithArguments("4")` | `ClassCastException` because a `String` value cannot be unboxed to `int` |
| `one.invokeWithArguments(new Object[] { null })` | `NullPointerException` due to unboxing `null` |

For a `MethodHandle` that is a **variable-arity collector**, different argument-counting rules may apply. Do not guess the exception solely from the argument count while ignoring the handle type and varargs mode.

## 8. Diagnostic workflow for real-world applications

1. **Record `handle.type()`:** for example `(String,int)long`. For a handle created from an instance method, the first argument is usually the **receiver**. For a handle that has had `bindTo` called, the receiver may already be bound and absent from the parameter list.
2. **Determine the call-site descriptor:** inspect the **static type** of each argument expression, and the **return type** determined by the cast/context. For `invokeExact`, compare the *entire* `MethodType`; do not look only at the argument count.
3. **Identify the `invoke`/`asType` conversion kind:** `int` ↔ `Object` may require boxing/unboxing; `Object` → `int` is structurally feasible but still requires a value check. Direct `String` → `int` is not a valid `asType` conversion.
4. **Check runtime values and nullability:** values received from JSON, reflection, plugins, or maps may carry a `String` instead of an `Integer`, or be `null`. Validate before creating/calling the adapter.
5. **Distinguish adapter errors from target errors:** check the stack trace and test the target directly when possible. A `ClassCastException` or `NullPointerException` thrown by the target itself also passes through the handle unchanged.
6. **Fix at the right layer:** adjust the call site or `MethodType` when the descriptor is wrong; convert/validate data when the runtime value is wrong; use a wrapper/null-check/default when data can be null.

The following validation snippet is an **illustrative helper**, not a standalone runnable program; Java 17 supports pattern matching for `instanceof`:

~~~java
static int requireInt(Object input) {
    if (!(input instanceof Integer number)) {
        throw new IllegalArgumentException("Expected a non-null Integer");
    }
    return number.intValue();
}
~~~

Use `requireInt(input)` when your contract genuinely requires `Integer`. That way, data errors (strings, `null`) are caught clearly before invoking the method handle, instead of letting the adapter throw a low-level `ClassCastException`/`NullPointerException`.

If the input is accepted as a **numeric string**, parse it explicitly and handle `NumberFormatException`:

~~~java
int number = Integer.parseInt("4"); // 4, intentional conversion
~~~

`asType` does not perform string parsing.

To verify an adapter directly:

~~~java
MethodType expected = MethodType.methodType(int.class, Object.class);
MethodHandle adapted = one.asType(expected);
System.out.println(adapted.type().equals(expected)); // true
~~~

An adapter having the right `type()` **does not guarantee** that all `Object` values can be converted when called; input validation is still necessary.

## 9. Common misconceptions

| Misconception | Correct understanding |
| --- | --- |
| "`invokeExact` automatically boxes/unboxes like a normal Java call." | The descriptor must match exactly; automatic conversions belong to `invoke`/adapters when permitted. |
| "Only parameters affect `WrongMethodTypeException`." | The call site's **return type** also participates in matching. |
| "`invoke` can always fix any type mismatch." | `invoke` only adapts according to `asType` rules; mismatches without a valid conversion cause `WrongMethodTypeException`. |
| "Having `asType(Object)` means any Object value is accepted." | Type `Object` can be structurally valid, but a runtime value of the wrong type can still cause `ClassCastException`. |
| "The string `"42"` will automatically become `int 42`." | No. To parse a string, you must call a conversion API such as `Integer.parseInt`. |
| "`ClassCastException` is always caused by `invoke`." | The caller, an adapter, and the target itself can all throw this exception. |
| "Passing `null` through a handle always fails immediately." | `null` is a valid reference in a reference position; an unboxing error only occurs when a primitive is needed. |
| "Every NPE when invoking a handle is unboxing." | A null receiver, dereferencing inside the target, and unboxing are different causes. |
| "Every adapter throws NPE on `null` → primitive." | `explicitCastArguments` has different null rules from `asType`; you must check the exact API. |
| "Just looking at the exception message is enough." | Inspect `MethodType`, the descriptor, runtime values, and the stack trace; message text can change. |

## 10. Self-check questions

Given `one.type() == MethodType.methodType(int.class, int.class)`, predict the exception (or value) for each call:

1. `(int) one.invokeExact(2L)`
2. `(Object) one.invoke(2)`
3. `Object x = "2"; (int) one.invoke(x)`
4. `Integer x = null; (int) one.invoke(x)`
5. `(int) one.invoke("2")`
6. `(int) one.asType(MethodType.methodType(int.class, Object.class)).invokeExact((Object) Integer.valueOf(2))`

**Answers:** (1) `WrongMethodTypeException` because the call site uses `long`; (2) `Integer(3)` boxed into `Object`; (3) `ClassCastException` because `String` cannot be unboxed to `int`; (4) `NullPointerException` due to unboxing `null`; (5) `WrongMethodTypeException` because type `String` cannot be directly adapted to `int` via `asType`; (6) returns `3` because the adapter accepts `Object` holding `Integer(2)` and unboxes it successfully.

**Java SE 17 Documentation:**

- [`MethodHandle`: `invokeExact`, `invoke`, `asType`, `invokeWithArguments`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html)
- [`MethodType` and descriptor structure](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html)
- [`WrongMethodTypeException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/WrongMethodTypeException.html)
- [`MethodHandles.explicitCastArguments`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html#explicitCastArguments(java.lang.invoke.MethodHandle,java.lang.invoke.MethodType))