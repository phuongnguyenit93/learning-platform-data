# 7.4. Effects of Variable Types, Result Casts, `null`, and Result-Discarding Statements

When calling `MethodHandle.invokeExact(...)` or `MethodHandle.invoke(...)`, Java does not treat the call like an ordinary method with fixed `Object...` parameters and an `Object` return type. These are two **signature-polymorphic** methods: the compiler generates the *call-site signature* (*call-site method descriptor*) from the **static type of each argument** and **how the result expression is used**.

A memorable consequence: the same `MethodHandle`, with the same input value, can have its call **succeed, dynamically adapt, or throw `WrongMethodTypeException`** simply by changing a variable type from `String` to `Object`, adding or removing a result cast, writing `null` directly, or discarding the result altogether in a statement. To diagnose correctly, you must look at the **bytecode signature at the call site**, not just the runtime values.

This lesson uses Java 17+, compares `invokeExact` and `invoke`, explains the `null` and `void` cases, and then verifies them with a standalone compilable/runnable program.

## 1. Two Important Signatures: The Handle's Type and the Call Site's Type

Every method handle has an immutable type for its invocation interface, represented by `MethodType`:

```java
MethodHandle greet = MethodHandles.constant(String.class, "hello");
System.out.println(greet.type()); // ()String
```

`()String` means **takes no parameters**, returns `String`. If a handle references an unbound instance method `String repeat(int n)`, its type may be `(Owner,int)String`: the receiver is at the first parameter position; if already `bindTo(owner)`, it may be `(int)String`. To know the truth, read `handle.type()` and each `parameterType(i)`/`returnType()` of `MethodType`.

But there is a second type: **the signature that the compiler records in the instruction at the call site**. For `invokeExact` and `invoke`, the compiler does not treat the call as an "actual `Object[]` array"; it generates a specialized descriptor according to the Java source.

Suppose `greet.type()` is `()String`. The following calls all have **0 arguments**, but **different expected return types**:

```java
String a = (String) greet.invokeExact(); // call site: ()String
Object b = (Object) greet.invokeExact(); // call site: ()Object
greet.invokeExact();                     // call site: ()void
```

Only the first line has a descriptor matching `()String` exactly. The next two lines **compile but throw `WrongMethodTypeException` at runtime**. This is surprising if you only view all three as "calling the same handle with no arguments".

`invokeExact` requires the **call-site signature to match `handle.type()` completely**, including the number of parameters, the type of each parameter, **and the return type**. `invoke` allows adapting certain types like `handle.asType(callSiteType)`, including adapting the return type; it does not guarantee that every conversion is valid.

| Method | When call-site type differs from `handle.type()` | When conversion is valid |
| --- | --- | --- |
| `invokeExact` | Throws `WrongMethodTypeException`; does not auto-convert | Not applicable: can only be called with the exact type |
| `invoke` | Attempts type adaptation according to `asType` rules; if impossible, typically throws `WrongMethodTypeException` | Can cast references, box/unbox, widen primitives, discard the result, or produce a default value for the return type according to applicable rules |
| `invokeWithArguments` | Does not use a special call-site type like the two APIs above; arguments are passed as `Object`/list | Designed for dynamic argument lists, with its own overhead and conversion rules |

`invokeExact`/`invoke` calls are declared `throws Throwable`. The standalone example in this lesson uses `main(String[] args) throws Throwable` so as not to dilute the focus. In application code, you must decide how to handle exceptions according to the method handle's contract.

## 2. The Variable Type of **Arguments** Determines Parameters in the Descriptor

Consider an identity handle of type `(String)String`:

```java
MethodHandle identity = MethodHandles.identity(String.class);
String text = "A";
Object sameObject = text;
```

The two variables `text` and `sameObject` point to **the same `String` object**, but have different compile-time types.

```java
String a = (String) identity.invokeExact(text);       // (String)String: OK
String b = (String) identity.invokeExact(sameObject); // (Object)String: error
String c = (String) identity.invoke(sameObject);      // adaptable: OK
```

- `a`: static parameter `String`, direct result cast `String` → matches `(String)String`.
- `b`: static parameter `Object` even though the actual value is `String` → call site `(Object)String`, wrong exact signature, throws `WrongMethodTypeException` **before the method handle executes the target behavior**.
- `c`: `invoke` can create an `(Object)String` adapter, check/cast the input object to `String`, so it succeeds with a value that is a `String`. If the actual object is not a `String`, reference conversion may throw `ClassCastException`; that differs from `WrongMethodTypeException` caused by an incompatible descriptor.

You can cast at the **argument** to describe the call site explicitly:

```java
String d = (String) identity.invokeExact((String) sameObject);
```

The cast `(String) sameObject` can cause `ClassCastException` *before* the method handle is invoked if the value is incompatible. When the cast succeeds, the parameter at the call site has static type `String`. Java does not automatically use the runtime type of `sameObject` to replace `Object` in the `invokeExact` descriptor.

This also holds for primitives: an `int` and a `long` can both represent the number `7`, but `(int)int` and `(long)int` are two different descriptors. `invokeExact` does not automatically widen, box, or unbox; `invoke` can adapt conversions that `asType` supports. A handle taking `int` does not mean the caller can pass any numeric type via `invoke`.

**Practical rule:** When an exact call fails, print `handle.type()` and note the static type of **each argument expression in the source**. Do not just log `value.getClass()`, because that misses an `Object` variable holding a `String` and does not help with primitives or `null`.

## 3. The Variable Type **Receiving the Result** Does Not Automatically Create the Desired Return Descriptor

This is a subtle difference between the two directions of "variable types".

### 3.1. `String result = handle.invokeExact()` Does Not Mean the Call Site Returns `String`

In Java 17, if a signature-polymorphic call **is used as an expression without a direct cast**, the return type chosen by the compiler is `Object`. Assigning the result to a `String` variable does **not** automatically turn the call-site return into `String`:

```java
MethodHandle greet = MethodHandles.constant(String.class, "hello");

// Does not compile: uncast invokeExact() expression has type Object.
// String wrong = greet.invokeExact();

Object alsoWrongAtRuntime = greet.invokeExact(); // compiles OK, runtime WMT
String correct = (String) greet.invokeExact();    // call site ()String: OK
```

The line `Object alsoWrongAtRuntime = ...` compiles but expects `()Object`, so it throws `WrongMethodTypeException` if the handle is actually `()String`.

With `var`, variable type inference cannot save the descriptor either:

```java
// var result = greet.invokeExact(); // var infers Object; runtime WMT
var result = (String) greet.invokeExact(); // var infers String; OK
```

**Distinguish clearly:** the static type of the **argument expression** determines each *parameter type*; whereas for the **return type** of a signature-polymorphic call, the special rule is **direct cast, ordinary expression, or statement**. There is no inference that "since the receiving variable is `String`, the JVM treats the call as returning `String`".

### 3.2. A Direct Cast on the Call Becomes Part of the Signature

According to Java Language Specification rule `15.12.3`, if the entire call is the **direct operand of a cast**, the type used for the cast (after erasure if generics are involved) determines the **return type of the call-site descriptor**:

```java
String text = (String) greet.invokeExact(); // ()String
Object value = (Object) greet.invokeExact(); // ()Object
int number = (int) intHandle.invokeExact(); // ()int; assuming intHandle.type() is ()int
```

Note that `(Object) greet.invokeExact()` is **not** "call to get a `String` and then cast up to `Object`". With `invokeExact`, the `(Object)` cast makes the call site directly request `()Object`; if the handle returns `String`, the call fails before any value is obtained.

If you want both to call `()String` exactly and to assign the result to `Object`, let the **innermost cast** determine the descriptor:

```java
Object upcast = (String) greet.invokeExact();          // descriptor ()String
Object alsoUpcast = (Object) (String) greet.invokeExact(); // still ()String
```

The compiler uses the cast closest to the call; widening the result afterward is a Java type conversion outside the signature-polymorphic method. Conversely, `(String) (Object) greet.invokeExact()` makes the `Object` cast closest to the call and still causes an exact error with `()String`.

### 3.3. Type Conversion Must Be an Intentional Decision

If you truly want to use the `()Object` descriptor with `invokeExact`, convert **the method handle's type** explicitly before calling:

```java
MethodHandle adapted =
        greet.asType(MethodType.methodType(Object.class)); // ()Object
Object result = (Object) adapted.invokeExact();             // OK
```

`asType` creates a handle compatible with the expected type (if the conversion rules allow it). It does not automatically convert arbitrary values or fix parameter count mismatches. The original `greet` still has `()String`; creating an adapter does not mutate the original handle.

For `invoke`, the caller can write `Object result = greet.invoke();` and let the corresponding adapter handle converting `String` to `Object`. Switching from `invokeExact` to `invoke` is only appropriate when the **intent** allows conversion, not to mask errors in the type contract.

## 4. The Role of `null`: Three Completely Different Positions

### 4.1. `null` as an **Argument**: `null` Does Not Have Type `String`

For an *uncast null literal* as an argument to `invokeExact`/`invoke`, the compiler uses the symbolic type **`java.lang.Void`** for that position in the call-site descriptor. That is the **class `Void`**, not the `void` return type.

```java
MethodHandle identity = MethodHandles.identity(String.class); // (String)String

String correct = (String) identity.invokeExact((String) null); // OK, null
String wrong = (String) identity.invokeExact(null);            // WMT
String accepted = (String) identity.invoke(null);              // OK, null
```

The illustrative code above intentionally contains the `wrong` line that throws an error at runtime; the complete program below catches that exception.

- `(String) null`: the parameter at the call site is `String`; matches `(String)String`, result is `null` normally.
- uncast `null`: the parameter at the call site is `Void`; `invokeExact` requires an exact match, so it throws `WrongMethodTypeException`.
- `invoke(null)`: in the case of a reference parameter type `String`, adaptation via `asType` can accept a `null` value, so the illustrative call returns `null`. Do not infer that every target type or every conversion from `null` is valid.

A variable with a concrete type retains that type even when its value is `null`:

```java
String s = null;
String value = (String) identity.invokeExact(s); // OK: (String)String
```

Therefore `(String) null` and `String s = null` are useful when you want to declare the call signature explicitly; a bare `null` in `invokeExact` can produce an unintended descriptor.

### 4.2. `null` as the **Actual Return Value**: The Descriptor Still Must Match

Consider a `()String` handle returning `null`:

```java
MethodHandle nullResult = MethodHandles.constant(String.class, null);
String value = (String) nullResult.invokeExact(); // OK, value == null
Object mismatch = (Object) nullResult.invokeExact(); // WrongMethodTypeException
```

A `null` value does **not** make the JVM skip signature checking. In the second line, `()Object` still differs from `()String`, so an error is raised right at type checking, even though if called successfully the value would be `null`. If you need `Object`, use `invoke` or `asType`.

### 4.3. The **MethodHandle Variable Itself** Is `null`

```java
MethodHandle absent = null;
String value = (String) absent.invokeExact(); // NullPointerException
```

This is a `null` receiver dereference error, distinct from both `WrongMethodTypeException` (signature mismatch) and `null` as an argument/result. When diagnosing, verify that the handle has been looked up/initialized before discussing `handle.type()`.

### 4.4. `null` and Primitive Unboxing

`invoke` can add a conversion from wrapper to primitive. If the **wrapper result is `null`**, unboxing fails:

```java
MethodHandle nullableInt = MethodHandles.constant(Integer.class, null);
int count = (int) nullableInt.invoke(); // NullPointerException on unboxing
```

The error here involves **the value being converted**, not "`null` itself causing `WrongMethodTypeException`". To preserve a nullable value, request `Integer` and check for `null` before unboxing.

## 5. Discarding the Result: Calling as a Statement Carries Return Type `void`

In a standalone call forming an **expression statement**:

```java
greet.invokeExact();
greet.invoke();
```

The compiler determines the **return type at the call site is `void`**. This directly affects signature checking:

- With a `()String` handle, `greet.invokeExact();` produces call site `()void` → **`WrongMethodTypeException`** (the handle returns `String`, not matching return type `void`).
- With the same handle, `greet.invoke();` can adapt the return type from `String` to `void` by **discarding the return value**; the call executes, and the result is not used.
- With a handle that is genuinely `()void`, `voidHandle.invokeExact();` matches exactly. If an `invoke` caller requests `Object` from a `()void` handle, the `asType` adapter can produce the default reference result **`null`**, according to the conversion rules from `void`.

Example:

```java
MethodHandle noResult =
        MethodHandles.empty(MethodType.methodType(void.class));

noResult.invokeExact();       // OK: ()void
Object value = noResult.invoke(); // OK: ()Object, value == null
```

**Do not confuse "ignoring the variable receiving the result" with "discarding the result via a statement".**

```java
Object ignored = greet.invoke(); // call site ()Object: receives Object
greet.invoke();                  // call site ()void: discards result
```

Both can succeed with `invoke` but produce **two different descriptors**. With `invokeExact`, `Object ignored = greet.invokeExact()` (an expression) also differs from `greet.invokeExact();` (a statement); both fail when `greet.type() == ()String` because they respectively ask for `Object` and `void`.

If a target has side effects and returns a value, calling `invoke()` as a statement still runs the target and discards the value when adaptation is valid. With `invokeExact()` failing with `WrongMethodTypeException` due to return mismatch, the target has not been called, so this cannot be treated as a way to "call and discard the result".

## 6. Primitives, Boxing, and Widening for the Result

With a handle returning `int`:

```java
MethodHandle number = MethodHandles.constant(int.class, 7); // ()int

int exact = (int) number.invokeExact(); // OK, ()int
Object boxed = number.invoke();         // OK, ()Object: boxing
long widened = (long) number.invoke();  // OK, ()long: widening
number.invoke();                        // OK, ()void: discards result
number.invokeExact();                   // WMT: ()void differs from ()int
```

The final `number.invokeExact();` line intentionally demonstrates an error and must catch `WrongMethodTypeException` if included in a program. `invoke` conversions are governed by `asType` rules and are **not a general-purpose converter**: they do not auto-parse `String` into numbers, do not implicitly narrow primitives, and do not accept arbitrary wrong arity.

When changing casts, `invokeExact` does not "auto-box the return" to match:

```java
Object x = (Object) number.invokeExact(); // ()Object, wrong for ()int
int y = (int) number.invokeExact();       // ()int, right
Object z = (Integer) number.invoke();     // can box int to Integer
```

For example, when you want exact `()Object`, you need to prepare a handle that has had `asType(methodType(Object.class))` applied. When you only want to use the result as `Object`, you can write `Object x = (String) greet.invokeExact();` if the handle returns `String`: the cast closest to the call determines descriptor `()String`, while the subsequent assignment widening is valid.

## 7. Complete Example Running on Java 17+

Save the entire program as **`MethodHandleCallSiteDemo.java`**. The example uses `MethodHandles.constant` and `identity` to separate call-site issues cleanly from access-permission lookup; each expected error is caught individually.

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;

public class MethodHandleCallSiteDemo {
    public static void main(String[] args) throws Throwable {
        MethodHandle greet = MethodHandles.constant(String.class, "hello");
        System.out.println("type=" + greet.type());

        String exact = (String) greet.invokeExact();
        System.out.println("exact=" + exact);

        try {
            Object wrong = (Object) greet.invokeExact();
        } catch (WrongMethodTypeException e) {
            System.out.println("exactObject=" + e.getClass().getSimpleName());
        }

        try {
            greet.invokeExact();
        } catch (WrongMethodTypeException e) {
            System.out.println("exactStatement=" + e.getClass().getSimpleName());
        }

        Object adapted = greet.invoke();
        System.out.println("invokeObject=" + adapted);
        greet.invoke();
        System.out.println("invokeStatement=ok");

        MethodHandle identity = MethodHandles.identity(String.class);
        String stringArg = "A";
        Object objectArg = stringArg;
        System.out.println("argExact=" + (String) identity.invokeExact(stringArg));

        try {
            String badArg = (String) identity.invokeExact(objectArg);
        } catch (WrongMethodTypeException e) {
            System.out.println("argObjectExact=" + e.getClass().getSimpleName());
        }

        System.out.println("argAdapt=" + (String) identity.invoke(objectArg));
        String typedNull = (String) identity.invokeExact((String) null);
        System.out.println("typedNull=" + (typedNull == null));

        try {
            String wrongNull = (String) identity.invokeExact(null);
        } catch (WrongMethodTypeException e) {
            System.out.println("untypedNullExact=" + e.getClass().getSimpleName());
        }

        String looseNull = (String) identity.invoke(null);
        System.out.println("untypedNullInvoke=" + (looseNull == null));

        MethodHandle nullResult = MethodHandles.constant(String.class, null);
        String actualNull = (String) nullResult.invokeExact();
        System.out.println("returnNull=" + (actualNull == null));

        try {
            Object wrongReturn = (Object) nullResult.invokeExact();
        } catch (WrongMethodTypeException e) {
            System.out.println("returnNullAsObjectExact="
                    + e.getClass().getSimpleName());
        }

        MethodHandle missing = null;
        try {
            String value = (String) missing.invokeExact();
        } catch (NullPointerException e) {
            System.out.println("handleNull=" + e.getClass().getSimpleName());
        }

        MethodHandle number = MethodHandles.constant(int.class, 7);
        int n = (int) number.invokeExact();
        Object boxed = number.invoke();
        long widened = (long) number.invoke();
        number.invoke();
        System.out.println("number=" + n + "," + boxed + "," + widened);

        try {
            number.invokeExact();
        } catch (WrongMethodTypeException e) {
            System.out.println("numberStatementExact="
                    + e.getClass().getSimpleName());
        }

        MethodHandle noResult =
                MethodHandles.empty(MethodType.methodType(void.class));
        noResult.invokeExact();
        System.out.println("voidExact=ok");
        Object fromVoid = noResult.invoke();
        System.out.println("voidInvokeObject=" + fromVoid);

        MethodHandle nullableInt =
                MethodHandles.constant(Integer.class, null);
        try {
            int primitive = (int) nullableInt.invoke();
        } catch (NullPointerException e) {
            System.out.println("nullUnbox=" + e.getClass().getSimpleName());
        }

        MethodHandle asObject =
                greet.asType(MethodType.methodType(Object.class));
        Object exactObject = (Object) asObject.invokeExact();
        System.out.println("adaptExactObject=" + exactObject);
    }
}
```

Compile and run in the directory containing the file:

```bash
javac --release 17 MethodHandleCallSiteDemo.java
java MethodHandleCallSiteDemo
```

Exact **`stdout` output**:

```text
type=()String
exact=hello
exactObject=WrongMethodTypeException
exactStatement=WrongMethodTypeException
invokeObject=hello
invokeStatement=ok
argExact=A
argObjectExact=WrongMethodTypeException
argAdapt=A
typedNull=true
untypedNullExact=WrongMethodTypeException
untypedNullInvoke=true
returnNull=true
returnNullAsObjectExact=WrongMethodTypeException
handleNull=NullPointerException
number=7,7,7
numberStatementExact=WrongMethodTypeException
voidExact=ok
voidInvokeObject=null
nullUnbox=NullPointerException
adaptExactObject=hello
```

**Why do the result groups behave this way?**

1. `type=()String` is the actual type of `greet`. The `(String)` cast lets `invokeExact` match; the `(Object)` cast or calling as a statement produces a different return type and throws `WrongMethodTypeException`.
2. `invokeObject` and `invokeStatement` show that `invoke` adapts both returning `Object` and discarding the `void` result from the same `()String` handle.
3. `argExact` and `argObjectExact` prove that the passed variable type determines the descriptor: same value `"A"`, but `String` differs from `Object` at compile time.
4. `typedNull` succeeds because `(String) null` matches handle `(String)String`; `untypedNullExact` fails with `Void`; `untypedNullInvoke` succeeds because a reference type can adapt in this case.
5. `returnNull` and `returnNullAsObjectExact` show that **a `null` result value does not exempt return descriptor checking**. `handleNull` is a `null` receiver error, while `nullUnbox` occurs during conversion to primitive.
6. `number` proves `invoke` can box `int` to `Object`, widen to `long`, and discard the result; `invokeExact` in a statement position still demands `()void` and therefore fails.
7. `voidExact` is an exact call to a handle that genuinely returns `void`. `voidInvokeObject=null` is the result of adapting `void` → `Object`. `adaptExactObject` demonstrates proactively changing the handle's type before calling exact `()Object`.

The program does **not** demonstrate that every handle can be adapted to every type; adaptability depends on `MethodType`, arity, and specific `asType` rules.

## 8. Diagnosing `WrongMethodTypeException` by Call Site

When you see `WrongMethodTypeException`, check in order:

1. **Is there a handle yet?** If the handle variable is `null`, you will get `NullPointerException` before any signature check can happen.
2. **What type does the handle require?** Print `handle.type()`. Check arity, parameter types, return type, and whether any adapter has been applied.
3. **What descriptor is the caller generating?** Inspect the static type of **each argument expression** (including an unbound receiver) and how the result expression is used. Look especially for `Object` variables holding `String`, uncast `null`, primitives/wrappers, and standalone `invokeExact()`.
4. **Is there a direct cast on the call?** `Object v = handle.invokeExact()` requests return `Object`; `Object v = (String)handle.invokeExact()` requests return `String` and only then assigns up to `Object`.
5. **Does the goal truly need exact or conversion?** If the contract permits conversion, consider `invoke` or `asType` intentionally. If the contract demands exact, fix the cast and expression types at the call site.
6. **Distinguish WMT from data errors:** `ClassCastException` can occur when an `invoke` adapter performs a reference cast, `NullPointerException` can occur when unboxing `null`, and the target can throw business exceptions. These errors are not identical to a descriptor mismatch.

Comparison table for a `MethodHandle h` with `h.type() == ()String`:

| Java Source | Return type at call site | `invokeExact` | `invoke` |
| --- | --- | --- | --- |
| `String v = (String) h.invokeX();` | `String` | Succeeds | Succeeds |
| `Object v = (Object) h.invokeX();` | `Object` | `WrongMethodTypeException` | Succeeds via reference widening |
| `Object v = h.invokeX();` | `Object` | `WrongMethodTypeException` | Succeeds via reference widening |
| `h.invokeX();` | `void` | `WrongMethodTypeException` | Succeeds, discards result |
| `Object v = (String) h.invokeX();` | `String` | Succeeds | Succeeds |

In the table, `invokeX()` is an **illustrative notation**—substitute `invokeExact()` and `invoke()` in turn to read the respective column; `invokeX` is **not** a real Java method name.

With generic code, a cast like `(List<String>) h.invokeExact()` (if the source allows an unchecked cast) produces a return descriptor with the **erased** type, namely `List`, without encoding the `String` type argument. Method handles do not automatically verify collection elements. Therefore, a generic type in the source does not guarantee runtime data safety either.

## 9. Common Mistakes and Fixes

| Common mistake | Symptom | Fix |
| --- | --- | --- |
| Looking only at the argument's runtime type | Value is actually `String`, but variable is declared `Object`, causing exact to fail | Use a variable/static cast matching the type the handle needs; or choose `invoke` if adaptation is allowed |
| Assuming a `String` receiving variable sets the return type | `String x = h.invokeExact()` does not compile | Cast **directly on the invocation**: `String x = (String) h.invokeExact()` |
| Casting the result to `Object` thinking it is just post-call widening | `(Object) h.invokeExact()` produces `()Object` | Use `Object x = (String) h.invokeExact()` or adapt the handle to `()Object` |
| Using bare `null` in `invokeExact` | Compiler records parameter `Void`, causing WMT with a handle expecting `String` | Use `(String) null` or a `String`-typed variable holding `null` |
| Discarding the result of a non-`void` handle using `invokeExact()` | Call site `()void` does not match | Call `invoke()` if you want to discard the result and the adapter supports it, or keep the result with a matching cast |
| Using `invoke` and trusting all errors will disappear | Adapter cannot convert types or data is the wrong kind | Check `asType`, arity, primitive conversions, and runtime types |
| Seeing `null` and concluding the descriptor can be ignored | A `null` result still leaves `()Object` different from `()String` in exact mode | Match types first, handle nullable values afterward |
| Assuming `invokeExact` wraps target exceptions like reflection | Code mistakenly catches `InvocationTargetException` | `invokeExact`/`invoke` propagate `Throwable` from the target directly per contract; handle the cause at the proper source |
| Using `System.out.println(h.invokeExact())` to debug | Inner call has no cast, result descriptor `Object` | Print `h.type()` first; if you need to print the value, cast directly to the right return type |

## 10. Self-Check Exercises

Suppose:

```java
MethodHandle a = MethodHandles.constant(String.class, "x"); // ()String
MethodHandle b = MethodHandles.identity(String.class);       // (String)String
MethodHandle c = MethodHandles.empty(MethodType.methodType(void.class)); // ()void
```

The following questions are **independent** of one another and can each be run separately inside a method declared `throws Throwable`:

1. `Object result = (Object) a.invokeExact();` — does this succeed?
2. `Object result = (String) a.invokeExact();` — does this succeed?
3. `a.invokeExact();` and `a.invoke();` — which line is suitable for discarding the result?
4. `String s = (String) b.invokeExact(null);` — what happens? What if `null` is replaced by `(String) null`?
5. `Object x = c.invoke();` — what is returned?
6. `Object raw = "x"; String s = (String) b.invokeExact(raw);` — is `raw` holding a `String` value enough?
7. If `a` returns `null` instead of `"x"`, does question 1 become valid?
8. Why can't `String value = a.invokeExact();` be used to "force" return type `String` for the call site?

**Answers:**

1. **No**: the direct `Object` cast produces `()Object`; `a.type()` is `()String`, so exact throws `WrongMethodTypeException`.
2. **Yes**: the cast closest to the call is `String` → descriptor `()String`. The subsequent assignment widening from `String` to `Object` is valid.
3. `a.invokeExact();` demands `()void` and thus throws `WrongMethodTypeException`; `a.invoke();` can adapt by discarding the return and runs successfully.
4. Uncast `null` is treated as parameter `Void`, which does not match `(String)String`, causing WMT; `(String) null` matches and returns `null`.
5. `invoke` adapts `void` → `Object`; `null` is received.
6. No: the **static** type of `raw` is `Object`, so exact fails; you must cast the argument `(String)raw` or use `invoke` if conversion is desired.
7. No. `null` as a result does not change `()String` of the handle or `()Object` of the call site.
8. Because a signature-polymorphic call without a direct cast is treated by the compiler as having result `Object`; `Object` cannot be implicitly assigned to `String`. Write `String value = (String) a.invokeExact();`.

## 11. References

- [Oracle Javadoc — MethodHandle, Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html): `type()`, `invokeExact`, `invoke`, call-site signatures, uncast `null` case, `void` in statements, `WrongMethodTypeException`.
- [Java Language Specification SE 17, `15.12.3 — Type of a Method Invocation`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12.3): rules for computing compile-time argument types and result type for signature-polymorphic methods.
- [Oracle Javadoc — MethodType, Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html): parameter and return types of a handle.
- [Oracle Javadoc — MethodHandle.asType, Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html#asType(java.lang.invoke.MethodType)): conversions adapting the call-site type.

**Key takeaway:** `invokeExact` only runs when the **entire** call-site descriptor, including the return type, matches `handle.type()`. For arguments, the **static type of the expression** is decisive; for the result, a **direct cast** can change the return descriptor, an **uncast expression** typically returns `Object`, and a **result-discarding statement** returns `void`. Bare `null` as an argument carries type `Void`; `null` as a result does not bypass type checking. `invoke` can adapt via `asType`, but only when the conversion is valid.
