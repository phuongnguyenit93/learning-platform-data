# 8.2 Binding Fixed Arguments with `insertArguments` and Adding Ignored Arguments with `dropArguments`

In the Java dynamic runtime, a `MethodHandle` describes an invocation point with a specific type. Sometimes the actual signature of a method does not match the signature that a dispatcher, callback, or framework needs to use: there may be parameters you want to **fix in advance**, or parameters the framework requires providing but the target logic **does not need to read**. Two combinators in `java.lang.invoke.MethodHandles` solve those two situations:

- `MethodHandles.insertArguments(target, pos, values...)`: **pre-binds values** for one or more consecutive parameters of `target`. The new handle has **fewer parameters** because the caller does not need to pass the bound values again.
- `MethodHandles.dropArguments(target, pos, types...)`: **adds accepted-but-ignored parameters** to the handle invocation. The new handle has **more parameters**; the extra arguments are not forwarded to `target`.

The name `dropArguments` often causes confusion: it **does not remove parameters from the handle's type**. It creates a handle that can *accept* additional arguments and ignore them when forwarding the call to the target.

This lesson focuses on the nature of the two transformations, the `pos` position, parameter order and types, how to read `MethodType` before/after, runnable Java 17+ examples, how to combine with a receiver, as well as common mistakes when using `invokeExact`.

## 1. General Model: Changing the Calling Contract, Keeping the Target's Work Intact

Consider a handle with the signature:

```text
target: (A, B, C)R
        ^  ^  ^
        0  1  2     Parameter indices start from 0
```

If we bind a value `b0` to parameter `B`:

```text
insertArguments(target, 1, b0)

Before: (A, B, C)R
After:  (A,    C)R

New caller: newHandle(a, c)
Equivalent: target(a, b0, c)
```

If we add parameters `X`, `Y` at position 1 to be ignored:

```text
dropArguments(target, 1, X.class, Y.class)

Before: (A,       B, C)R
After:  (A, X, Y, B, C)R

New caller:          newHandle(a, x, y, b, c)
Arguments to target: target(a, b, c)  // x, y are ignored
```

For both operations:

- The original `target` **is unchanged**; the API returns a new `MethodHandle`.
- **The return type `R` is preserved**.
- The target method is not invoked when merely **creating** an adapter with a combinator; the target code runs when you **invoke** the handle.
- Changing the parameter type list does not require generating or modifying the `.class` file of the wrapped method.
- They operate on **the existing parameters in `target.type()`**, not necessarily the parameters you see in the Java source declaration. For example, an instance method handle may contain the receiver at index 0.

### 1.1. Quick Comparison

| API | Conceptual Input | Resulting Handle | Which Arguments Reach the Original Method? |
| --- | --- | --- | --- |
| `insertArguments` | Binds values to a portion of the target signature | **Fewer** parameters | Arguments passed by the caller plus the bound values |
| `dropArguments` | Adds types that are accepted but unused | **More** parameters | Only the arguments corresponding to the original target parameters |
| `asType` | Changes parameter/return types via valid conversions | Usually keeps the parameter count | The values after conversion |
| `bindTo` | Binds the first reference argument of the handle | Reduces by one parameter | The bound reference value along with the remaining arguments |

`insertArguments` and `dropArguments` can both be chained, creating an adapter pipeline to match the signature required by a runtime dispatcher.

## 2. Prerequisites: `MethodHandle`, `MethodType`, and Exact Invocation

The examples use:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
```

When looking up a method, `MethodType.methodType(returnType, parameterTypes...)` describes the return type **first**, and parameter types **after**. For example:

```java
// Fragment: the actual method has the form static int sum(int a, int b).
MethodType signature = MethodType.methodType(
        int.class, int.class, int.class);
```

`MethodHandle.type()` returns a `MethodType` corresponding to how **that handle is called**. When transformed:

```text
base.type():      (int,int)int
newHandle.type(): (int)int    // Example after binding one parameter
```

`invokeExact(...)` must match the **entire** type of the handle, including the static type of each argument **and the return type at the call site**. An example with an `(int)int` handle:

```java
int result = (int) newHandle.invokeExact(5);
```

This is an **illustrative fragment**, assuming `newHandle` is a handle of type `(int)int`. If you call `invokeExact(5L)` or expect an `Object` result instead of `int`, the JVM may throw `WrongMethodTypeException`. Combinators do not automatically turn `invokeExact` into an invocation that allows arbitrary type casting.

**Remember:** Before applying each combinator, read `target.type()`. After applying it, read `newHandle.type()` to know the exact invocation type needed.

## 3. `insertArguments` — Fixing Parameters at a Given Position

API:

```java
public static MethodHandle insertArguments(
        MethodHandle target, int pos, Object... values)
```

The syntax above is an **illustrative API signature**, not a standalone program snippet.

Meaning:

1. `target` is the original handle.
2. `pos` is the **starting position** in the current parameter list of `target.type()`, numbered from 0.
3. `values` is one or more values to be bound to **consecutive** positions, starting at `pos`.
4. When invoking the new handle, the JVM automatically supplies the bound values to the target. The caller only provides the remaining parameters in the exact order.

Examples:

```text
target.type()                  = (String, String, int)String

insertArguments(target, 0, "Hi ")
                               = (String, int)String

insertArguments(target, 1, "Bo", 2)
                               = (String)String

insertArguments(target, 2, 3) = (String, String)String
```

When binding in the middle, do not interpret `pos` as the position in the source method after already transforming another handle. Each time you call a combinator, check **the type of the target at that exact call**.

### 3.1. Fixed Values Must Match Parameter Types

Because `values` has type `Object...`, primitive arguments such as `int` are **boxed** by Java into their corresponding wrappers before being passed to the API. `insertArguments` processes the boxed value according to the parameter type:

- For a target parameter `int`, passing `2` (boxed as `Integer`) is the right way; do not assume a string `"2"` will be parsed.
- For primitive `long`, pass `2L`; do not rely on `Integer` being arbitrarily widened during the bind step.
- For a reference type, the value must be appropriate for the target parameter; an incompatible type can cause `ClassCastException` right when creating the adapter.
- `null` has no primitive value to unbox, so it cannot be used to bind a primitive parameter; for a reference parameter, `null` can be bound if valid.
- An out-of-range index or a number of values greater than the remaining parameters causes an error when creating the adapter. There is no automatic "widening" of the signature to make room for fixed values.

The values are supplied to the adapter at **handle creation time**. For immutable primitives/wrappers, the value can be considered fixed; for a mutable object/array, the adapter holds a **reference** to that object and does not automatically deep-copy its internal state. Practice 4 will demonstrate this.

### 3.2. Binding Does Not Change Business Logic

If the original method is:

```java
static int multiply(int number, int factor) {
    return number * factor;
}
```

This is an illustrative fragment. The handle `multiplyHandle` has the form `(int,int)int`. Bind the second parameter to `4`:

```java
MethodHandle quadruple = MethodHandles.insertArguments(
        multiplyHandle, 1, 4);
// quadruple.type(): (int)int
```

When calling `quadruple(7)`, the target receives `multiply(7, 4)` and returns `28`. There is no new `quadruple(int)` method in the source or class file: this is a handle with **partial application** of arguments.

### 3.3. Scope Limit of a Single Bind

A single `insertArguments` call only binds **one consecutive slice of parameters**. If you want to bind two non-adjacent positions, you can call it multiple times in sequence, but you must **recalculate the index** after each call:

```text
Original:              (A, B, C, D)R
Bind B at pos=1:       (A,    C, D)R
Bind remaining D pos=2:(A,    C   )R
```

Do not continue using `D`'s old index of 3 in the second step, because the handle then only has three parameters with indices 0, 1, 2.

## 4. Practice 1 — Binding Prefix, Middle/End Parameters, and Primitives

Create the file **`InsertArgumentsDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class InsertArgumentsDemo {
    static String repeatName(String greeting, String name, int times) {
        return greeting + name.repeat(times);
    }

    public static void main(String[] args) throws Throwable {
        MethodHandle base = MethodHandles.lookup().findStatic(
                InsertArgumentsDemo.class, "repeatName",
                MethodType.methodType(
                        String.class, String.class, String.class, int.class));

        MethodHandle prefix = MethodHandles.insertArguments(base, 0, "Hi ");
        MethodHandle middleAndLast =
                MethodHandles.insertArguments(base, 1, "Bo", 2);
        MethodHandle count = MethodHandles.insertArguments(base, 2, 3);

        System.out.println("base: " + base.type());
        System.out.println("prefix: " + prefix.type());
        System.out.println("middle+last: " + middleAndLast.type());
        System.out.println("count: " + count.type());
        System.out.println("prefix call: "
                + (String) prefix.invokeExact("Ana", 2));
        System.out.println("middle+last call: "
                + (String) middleAndLast.invokeExact("Hey "));
        System.out.println("count call: "
                + (String) count.invokeExact("!", "go"));
    }
}
```

Compile and run with JDK 17+:

```bash
javac --release 17 InsertArgumentsDemo.java
java InsertArgumentsDemo
```

**Exact stdout:**

```text
base: (String,String,int)String
prefix: (String,int)String
middle+last: (String)String
count: (String,String)String
prefix call: Hi AnaAna
middle+last call: Hey BoBo
count call: !gogogo
```

**Analysis:**

1. `base` takes three parameters `(String greeting, String name, int times)`; its signature returns `String`.
2. `prefix` binds `greeting="Hi "` at index 0, so it still takes `name` and `times`. The string `"Ana"` is repeated twice.
3. `middleAndLast` binds **two consecutive parameters** starting at index 1: `name="Bo"` and `times=2`. The new handle only has `greeting` left.
4. `count` binds the last parameter `times=3`, so it still takes `greeting` and `name`. The result `!gogogo` shows that the numeric value is fixed.
5. None of the calls modify `base.type()` or change the `repeatName` method. Multiple independent adapters can be created from the same target.

## 5. `dropArguments` — Accepting Extra Parameters and Ignoring Them

Common API:

```java
public static MethodHandle dropArguments(
        MethodHandle target, int pos, Class<?>... valueTypes)
```

The syntax is an abbreviated API signature. The API also has an overload accepting `List<Class<?>>`.

The most easily misunderstood point: **`dropArguments` does not reduce the number of parameters of the handle at all**. It takes **parameter types to add**, inserts them into the new handle's signature at `pos`; when the new handle runs, the values at the added positions are ignored.

Example target `(String,String)String`:

```text
target: (String left, String right)String
              0          1

dropArguments(target, 0, Object.class):
        (Object ignored, String left, String right)String

dropArguments(target, 1, int.class, boolean.class):
        (String left, int ignoredA, boolean ignoredB, String right)String

dropArguments(target, 2, long.class):
        (String left, String right, long ignored)String
```

### 5.1. `pos` Is the Insertion Position, Not a Removal Position

For a target with `n` parameters, you can insert before parameter index `0..n-1` or insert **at the end** at index `n`. If the target has no parameters, insert at index 0.

The existing parameters of the target **keep their relative order**. `dropArguments(target, 1, int.class, boolean.class)` inserts `int` first, `boolean` second, starting at index 1. It does not bind any default values; the caller of the adapter **must still supply** the new arguments.

If the added parameters have type `long` or `double`, they occupy two parameter slots at the JVM level. `void.class` cannot be used as a parameter type, and signatures exceeding the slot limit will be rejected.

### 5.2. "Ignored" Does Not Mean the Argument Expression Is Not Evaluated

Java evaluates argument expressions **before performing the call**, even when the adapter will discard the computed value. For example:

```java
String result = (String) withEvaluation.invokeExact(
        "A", expensiveOperation(), "B");
```

This is an illustrative fragment if `withEvaluation.type()` is `(String,int,String)String` and `expensiveOperation()` returns `int`. Java still runs `expensiveOperation()` to obtain the argument; the adapter only discards the **value** of the argument after it has been evaluated.

This matters when an ignored argument causes side effects, I/O, throws an exception, or consumes resources. **`dropArguments` does not avoid the cost of computing arguments at the caller** and does not automatically validate data/authorization in an ignored context object.

### 5.3. Adding Parameters to a Handle That Takes No Arguments

`MethodHandles.constant(String.class, "OK")` creates a handle of type `()String`. A framework might require a callback taking `(String,int)String`; we insert two ignored parameters:

```java
MethodHandle original = MethodHandles.constant(String.class, "OK");
MethodHandle padded = MethodHandles.dropArguments(
        original, 0, String.class, int.class);
// original.type(): ()String
// padded.type():   (String,int)String
```

This is a valid fragment within a scope that has imported `MethodHandles`. When calling `padded` with `(String,int)`, the return value is always `"OK"`. This example is useful when you need to match a **callback interface** while fixed logic does not use all the data the callback passes in.

## 6. Practice 2 — Adding Ignored Arguments at Multiple Positions

Create the file **`DropArgumentsDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class DropArgumentsDemo {
    static String merge(String left, String right) {
        return left + "|" + right;
    }

    static int ignoredValue() {
        System.out.println("ignored argument expression evaluated");
        return 44;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandle base = MethodHandles.lookup().findStatic(
                DropArgumentsDemo.class, "merge",
                MethodType.methodType(
                        String.class, String.class, String.class));
        MethodHandle inMiddle = MethodHandles.dropArguments(
                base, 1, int.class, boolean.class);
        MethodHandle inFront = MethodHandles.dropArguments(
                base, 0, Object.class);
        MethodHandle withEvaluation = MethodHandles.dropArguments(
                base, 1, int.class);

        System.out.println("base: " + base.type());
        System.out.println("middle: " + inMiddle.type());
        System.out.println("middle call: "
                + (String) inMiddle.invokeExact("L", 99, true, "R"));
        System.out.println("front: " + inFront.type());
        System.out.println("front call: "
                + (String) inFront.invokeExact((Object) "metadata", "left", "right"));
        System.out.println("before evaluated call");
        String evaluated = (String) withEvaluation.invokeExact(
                "A", ignoredValue(), "B");
        System.out.println("evaluated call: " + evaluated);

        MethodHandle constant = MethodHandles.constant(String.class, "OK");
        MethodHandle padded = MethodHandles.dropArguments(
                constant, 0, String.class, int.class);
        System.out.println("constant: " + constant.type());
        System.out.println("padded: " + padded.type());
        System.out.println("padded call: "
                + (String) padded.invokeExact("unused", 42));
    }
}
```

```bash
javac --release 17 DropArgumentsDemo.java
java DropArgumentsDemo
```

**Exact stdout:**

```text
base: (String,String)String
middle: (String,int,boolean,String)String
middle call: L|R
front: (Object,String,String)String
front call: left|right
before evaluated call
ignored argument expression evaluated
evaluated call: A|B
constant: ()String
padded: (String,int)String
padded call: OK
```

**Notable points:**

- `inMiddle` has two new parameters `int` and `boolean`. Even though `99` and `true` are passed, the `merge` method only sees `"L"` and `"R"`.
- `inFront` has its first parameter **of exact type `Object`**. Because `invokeExact` checks static types, the call site uses `(Object) "metadata"`; if the expression has static type `String`, the call will not match `(Object,String,String)String`.
- `ignoredValue()` **still runs** and prints its log before the line `evaluated call: A|B`. Only the value `44` is discarded by the adapter.
- `padded` adds two parameters to a `()String` handle and still returns `"OK"`. The extra parameters do not affect the result.

## 7. Combining `insertArguments` and `dropArguments` in a Pipeline

Many applications need both steps at the same time: **fixing a policy/receiver value** and **accepting some data sent by the framework** that the target does not need.

### 7.1. Binding the Receiver of an Instance Method

When using `Lookup.findVirtual` for an instance method, the handle usually has **the receiver as the first parameter**:

```text
Source:              String Formatter.join(String left, String right)
Lookup type:         (String,String)String
Virtual handle type: (Formatter,String,String)String
                         ^
                       receiver
```

`insertArguments(virtual, 0, formatterInstance)` binds the receiver and returns a `(String,String)String` handle. Then we can bind `right="tail"` at index **1 of the new handle** to get `(String)String`; and add an ignored `long` parameter at the beginning with `dropArguments(..., 0, long.class)` to match the dispatcher's `(long,String)String` signature.

Note that indices change after each operation: the receiver is index 0 in the **virtual handle**, but after binding the receiver, index 0 is `left` and index 1 is `right`.

### 7.2. Practice 3 — Receiver, Fixed Value, and Ignored Context Parameter

Create the file **`ComposableHandleDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class ComposableHandleDemo {
    static class Formatter {
        String join(String left, String right) {
            return left + "/" + right;
        }
    }

    static int multiply(int number, int factor) {
        return number * factor;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodHandle virtual = lookup.findVirtual(
                Formatter.class, "join",
                MethodType.methodType(String.class, String.class, String.class));
        MethodHandle receiverBound =
                MethodHandles.insertArguments(virtual, 0, new Formatter());
        MethodHandle suffixBound =
                MethodHandles.insertArguments(receiverBound, 1, "tail");
        MethodHandle padded =
                MethodHandles.dropArguments(suffixBound, 0, long.class);

        System.out.println("virtual: " + virtual.type());
        System.out.println("receiver bound: " + receiverBound.type());
        System.out.println("suffix bound: " + suffixBound.type());
        System.out.println("padded: " + padded.type());
        System.out.println("padded call: "
                + (String) padded.invokeExact(99L, "head"));

        MethodHandle multiplyHandle = lookup.findStatic(
                ComposableHandleDemo.class, "multiply",
                MethodType.methodType(int.class, int.class, int.class));
        MethodHandle factorBound =
                MethodHandles.insertArguments(multiplyHandle, 1, 4);
        MethodHandle withRequestId =
                MethodHandles.dropArguments(factorBound, 0, String.class);

        System.out.println("multiply: " + multiplyHandle.type());
        System.out.println("factor bound: " + factorBound.type());
        System.out.println("request adapter: " + withRequestId.type());
        System.out.println("request adapter call: "
                + (int) withRequestId.invokeExact("request-42", 7));
    }
}
```

```bash
javac --release 17 ComposableHandleDemo.java
java ComposableHandleDemo
```

**Exact stdout:**

```text
virtual: (Formatter,String,String)String
receiver bound: (String,String)String
suffix bound: (String)String
padded: (long,String)String
padded call: head/tail
multiply: (int,int)int
factor bound: (int)int
request adapter: (String,int)int
request adapter call: 28
```

Analysis of the first pipeline:

```text
findVirtual:
(Formatter,String,String)String
    |
    | insertArguments(..., 0, new Formatter())
    v
(String,String)String
    |
    | insertArguments(..., 1, "tail")
    v
(String)String
    |
    | dropArguments(..., 0, long.class)
    v
(long,String)String
```

Calling `padded.invokeExact(99L, "head")`: the value `99L` is ignored, `"head"` becomes `left`, `right` is always `"tail"`, and the receiver is always the bound `Formatter` object.

The second pipeline illustrates a callback that requires a `requestId` parameter:

```text
multiply(number, factor): (int,int)int
   |
   | bind factor = 4
   v
(int)int
   |
   | add ignored String requestId at index 0
   v
(String,int)int
```

Even though the callback receives `"request-42"`, the adapter does not pass requestId to `multiply` and the result is still `7 * 4 = 28`. For use cases that need to validate or inspect requestId, **you cannot rely on `dropArguments`** because it intentionally does not process that value.

## 8. `bindTo` vs. `insertArguments`

`MethodHandle.bindTo(value)` also fixes an argument, but only supports **the first parameter with a reference type**. It is commonly used to bind the receiver of an instance method:

```java
// Fragment: virtual.type() = (Formatter,String,String)String
MethodHandle viaBindTo = virtual.bindTo(new Formatter());
MethodHandle viaInsert = MethodHandles.insertArguments(
        virtual, 0, new Formatter());
```

Both resulting handles have the signature `(String,String)String`, but in this example the two `new Formatter()` calls create **two different receiver objects**; you should not treat these two values as "the same receiver" just because the handle types are identical.

Differences:

| Need | `bindTo` | `insertArguments` |
| --- | --- | --- |
| Bind the first reference argument | Yes | Yes, using `pos=0` |
| Bind a primitive argument like `int` | No | Yes, using the corresponding wrapper |
| Bind parameters in the middle/end | Not directly | Yes, choose `pos` |
| Bind multiple consecutive parameters in one step | No | Yes |
| Create a new handle with fewer parameters | Yes | Yes |

When binding a receiver at position 0, either can be reasonable. When handling other parameters or primitives, `insertArguments` is more flexible.

## 9. Java Varargs Pitfall When Binding an Array

`insertArguments` has the parameter `Object... values`, which is **Java varargs**. If you want to bind a `String[]` as **a single argument**, calling `insertArguments(handle, 0, words)` can be interpreted by Java as passing **multiple array elements** into varargs (because `String[]` is compatible with `Object[]`). In that case, the number of bound values differs from expected.

The explicit way is to cast the array to **a single `Object`**:

```java
MethodHandle bound = MethodHandles.insertArguments(
        original, 0, (Object) words);
```

When the target has a parameter of type `String[]`, the adapter will bind **one reference to the array**. This is not a deep copy. The runnable verification code below also shows that mutating the array contents **after binding** affects the result of calling the handle.

### 9.1. Practice 4 — Arrays Are Held by Reference

Create the file **`ArrayBindingDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class ArrayBindingDemo {
    static String join(String[] values) {
        return String.join("-", values);
    }

    public static void main(String[] args) throws Throwable {
        MethodHandle original = MethodHandles.lookup().findStatic(
                ArrayBindingDemo.class, "join",
                MethodType.methodType(String.class, String[].class));
        String[] words = {"red", "blue"};

        MethodHandle bound =
                MethodHandles.insertArguments(original, 0, (Object) words);
        System.out.println("original: " + original.type());
        System.out.println("bound: " + bound.type());
        System.out.println("first: " + (String) bound.invokeExact());

        words[0] = "green";
        System.out.println("after mutating array: "
                + (String) bound.invokeExact());
    }
}
```

```bash
javac --release 17 ArrayBindingDemo.java
java ArrayBindingDemo
```

**Exact stdout:**

```text
original: (String[])String
bound: ()String
first: red-blue
after mutating array: green-blue
```

Meaning:

1. The original signature `(String[])String` has exactly **one** array-typed parameter.
2. `(Object) words` ensures `Object... values` receives **one element**, which is the `words` array itself.
3. After binding, `bound.type()` is `()String`, so the call `bound.invokeExact()` takes **no arguments**.
4. Changing `words[0]` mutates the state of the bound object, leading to the output `green-blue`. The adapter holds a reference; it does not take an immutable snapshot of the array.

For data that must be immutable, perform a **defensive copy** before binding: for example, `String[] safe = words.clone();`, then bind `safe`, and do not expose the `safe` reference to anywhere that could mutate it. `insertArguments` only fixes the reference; it does not enforce immutability on the object.

## 10. Comparing Signature Transformations with Behavioral Transformations

There are two groups of APIs that are easily confused:

### 10.1. `MethodType` Only Describes

`MethodType.dropParameterTypes(1, 2)` **removes a parameter type from the descriptor list**. `MethodType.insertParameterTypes(1, int.class)` **adds a parameter type to the descriptor**. They do not operate on a handle and do not create an invocable adapter.

### 10.2. `MethodHandles` Creates Invocable Adapters

- `MethodHandles.insertArguments(...)` reduces the parameters of a handle because it **supplies values** to the target.
- `MethodHandles.dropArguments(...)` increases the parameters accepted by the new handle because it **ignores the values** of the added parameters.
- `MethodHandles.permuteArguments(...)` changes the parameter mapping order, without necessarily needing fixed values.
- `MethodHandles.filterArguments(...)` invokes filter handles to transform arguments before passing them to the target.
- `MethodHandle.asType(...)` changes the signature seen by the caller using valid type conversions; it does not mean "ignore arbitrary parameters" like `dropArguments`.

| If the goal is... | Appropriate approach |
| --- | --- |
| Lock `factor` to `4` and only pass `number` | `insertArguments(multiplyHandle, 1, 4)` |
| Callback has an extra `requestId` that the target does not use | `dropArguments(target, 0, String.class)` |
| Swap two parameters | See `permuteArguments` |
| Convert `int` to `long` when calling | See `asType` with a valid type |
| Modify a **signature descriptor** without a handle yet | `MethodType.insertParameterTypes` or `dropParameterTypes` |
| Bind a reference receiver at the start of a handle | `bindTo` or `insertArguments(...,0,...)` |

Do not confuse reducing/increasing **the number of handle parameters** with changing parameters in the source method: the target's class file still keeps its original signature.

## 11. Signature Progression Table for Self-Checking Indices

Suppose `target.type()` is `(String,int,long)boolean`:

| Transformation (independent from target, unless noted) | Handle type after transformation |
| --- | --- |
| `insertArguments(target, 0, "prefix")` | `(int,long)boolean` |
| `insertArguments(target, 1, 7)` | `(String,long)boolean` |
| `insertArguments(target, 1, 7, 9L)` | `(String)boolean` |
| `dropArguments(target, 0, Object.class)` | `(Object,String,int,long)boolean` |
| `dropArguments(target, 2, double.class)` | `(String,int,double,long)boolean` |
| `dropArguments(target, 3, Object.class)` | `(String,int,long,Object)boolean` |
| Bind `int` first, then add `Object` at index 0 | `(Object,String,long)boolean` |

In the last row, the second adapter takes **the type already reduced by one parameter** as input. This is a consistent rule to avoid off-by-one errors when combining multiple combinators.

### 11.1. Track with `handle.type()` Instead of Guessing

In tooling that supports dynamic invocation, it is good practice to log each stage clearly:

```java
// Fragment: target/afterBind/afterDrop are existing MethodHandles.
System.out.println("target:    " + target.type());
System.out.println("afterBind: " + afterBind.type());
System.out.println("afterDrop: " + afterDrop.type());
```

The code above is a non-standalone fragment. The variable names and printed types help compare against the expected callback/framework signature. Do not rely on the original method name to infer the parameter count of an adapted handle.

### 11.2. Checking Static Types When Calling `invokeExact`

Suppose `handle.type()` is `(Object,int)String`. With `invokeExact`, the expression `"metadata"` has static type `String`, not `Object`. Use `(Object) "metadata"` to express the exact call-site type:

```java
// Fragment: handle.type() = (Object,int)String
String value = (String) handle.invokeExact((Object) "metadata", 3);
```

Put concisely: at runtime, the object can be a `String`, but **the call-site signature** must still use `Object` if the handle expects `Object`. `invoke(...)` can allow compatible conversions, but you should not let implicit conversions hide adapter design bugs.

## 12. Common Errors and Failure Mechanisms

| Symptom | Cause | Check/Fix |
| --- | --- | --- |
| `WrongMethodTypeException` on `invokeExact` after `insertArguments` | Still passing the bound parameter; call site has too many arguments, wrong type, or wrong return type | Print `newHandle.type()` and call using the **reduced** signature |
| `WrongMethodTypeException` on `invokeExact` after `dropArguments` | Forgot to pass the new parameter or passed the wrong static type | Print type, add the exact parameters with matching indices |
| `IllegalArgumentException` when binding | `pos` out of range or number of bound values exceeds available parameters | Count `target.type().parameterCount()` and the size of `values` |
| `ClassCastException`/`NullPointerException` when binding | Incompatible reference or unsuitable value for primitive | Match types exactly; use the right wrapper for primitives, avoid `null` |
| `IllegalArgumentException` on `dropArguments` | Invalid insertion index, contains `void.class`, or violates signature limits | Check index `0..parameterCount`, valid types, and slot count |
| Method handle with receiver bound to the wrong parameter | Forgot the receiver at position 0 of a `findVirtual` handle | Read `virtual.type()`, bind index 0 before binding source parameters |
| Passing `String[]` to `insertArguments` and having it treated as multiple values | Varargs `Object...` spreads the array elements | Use `(Object) array` to bind **a single array** |
| "Ignored" argument still causes side effects | Java evaluates the expression before the adapter discards the value | Keep input arguments pure or adjust the caller; do not expect the adapter to prevent evaluation |
| Bound an object and later saw behavior change | Bound a **reference** to a mutable object, did not clone state | Defensive copy/immutable design |
| Confused `dropArguments` with `MethodType.dropParameterTypes` | Two APIs with different semantics: adapter accepting extra args vs. descriptor losing types | Distinguish `MethodHandles` and `MethodType` classes |
| Target has return type `int` but caller assigns to `Object` | `invokeExact` constrains the return type at the call site too | Use an `int` cast/variable of the right type or an appropriate adapter |

Errors can occur right **at adapter creation time** when parameters/values are invalid; whereas `WrongMethodTypeException` at **invocation time** indicates the call signature does not match the handle. Do not silently catch these errors and continue treating the dynamic invocation as successful.

### 12.1. An Example of a Wrong Index

Suppose the initial handle has `(Formatter,String,String)String` and you bind the receiver:

```java
MethodHandle noReceiver =
        MethodHandles.insertArguments(virtual, 0, formatter);
// noReceiver.type(): (String,String)String
```

If you want to bind `right`, the correct position on `noReceiver` is `1`. Using index `2` (the position of `right` in the **old** handle) will be out of range or bind the wrong parameter. Every subsequent operation must be calculated on the **latest** type.

### 12.2. Design Limits of "Ignoring Context" Calls

A callback signature `(RequestContext,int)int` can be created from `(int)int` using `dropArguments(target, 0, RequestContext.class)`. However, if the target needs to validate context, inspect metadata, trace, or adjust business results, **do not use dropping**. You need a real method or a filter/guard that processes the context before calling the target.

Similarly, `insertArguments` can bind credentials, configuration, or service references; binding does not automatically protect those values from unintended exposure or mutation. You must design lifecycle and access control at the application layer.

## 13. When to Use in Real Applications?

### 13.1. Creating Adapters for Fixed-Signature Callbacks

A library requires a callback of type `(String requestId, int amount)int`, but business logic only needs `amount` and a fixed `factor`. Pipeline:

```text
core multiply(amount, factor)       (int,int)int
         |
         | bind factor=4 at index 1
         v
quadruple(amount)                   (int)int
         |
         | dropArguments index 0, String.class
         v
callback(requestId, amount)         (String,int)int
```

The example in `ComposableHandleDemo` does exactly this. The advantage is choosing the adapter at configuration time and reusing it; no need to write manual wrapper classes for every simple signature pair.

### 13.2. Binding the Receiver of a Configured Service

For a method handle `(Service, Input)Output`, if only one service instance will handle all calls, `insertArguments(handle, 0, service)` returns `(Input)Output`. However, holding a reference also entails lifecycle considerations: the adapter will keep a reference to the service as long as the adapter itself is referenced. If the service has mutable/concurrent state, binding does not provide thread safety or snapshot guarantees.

### 13.3. Reducing Adapter Class Duplication

When dispatching many tasks by configuration, a dispatcher can use `MethodHandle` combinators to turn callables with different signatures into a **uniform signature**. However, not every kind of difference is solved by `insertArguments` and `dropArguments`: when you need to reorder, cast, filter parameters, or combine multiple calls, choose the appropriate combinator and check `handle.type()` after each step.

## 14. Self-Check Questions

1. Why does `dropArguments` have "drop" in its name yet **increases** `parameterCount()`?
2. With `target.type() = (String,int,long)void`, what type does `insertArguments(target, 1, 5)` produce? Does the caller still pass `int`?
3. With type `(String,int)String`, what is the signature of `dropArguments(target, 2, boolean.class)`?
4. Given `virtual.type() = (Editor,String)boolean`. To fix the receiver, which `pos` should be used? Afterward, what is the first parameter of the new handle?
5. Why does calling `insertArguments(handle, 0, words)` with `words` of type `String[]` risk binding multiple values?
6. Does `dropArguments` prevent `expensive()` passed into the ignored position from running? Why?
7. Why might `String result = (String) handle.invokeExact("x", 2)` fail when `handle.type()` is `(Object,int)String`?
8. After `insertArguments(target, 1, 4)`, is the original method's bytecode modified or does `target.type()` itself change?
9. With `target.type()=(int,int)int`, to add an ignored `String requestId` at the front after binding the last parameter, what two steps do you write?
10. When binding a mutable `List`, can later changes to the list affect handle invocations?
11. Can `bindTo` be used to fix an `int` parameter in the middle of a signature?
12. When is ignoring a context argument a bad idea in a callback pipeline?

**Answer hints:**

1. Because it **drops the value when forwarding to the target**, while the new handle still accepts extra parameters.
2. `(String,long)void`; the caller does not pass `int` again because the value is already bound.
3. `(String,int,boolean)String`; `pos=2` inserts at the end.
4. `pos=0`; the remaining first parameter is `String`.
5. `Object...` can interpret `String[]` as multiple varargs elements; use `(Object) words`.
6. No; Java must evaluate argument expressions before the call, and the adapter only discards the evaluated value.
7. `invokeExact` matches the **static** type `Object`; the literal `"x"` has static type `String`. Use `(Object) "x"`.
8. No; it is a new adapter, and the original method and old target remain unchanged.
9. `bound = MethodHandles.insertArguments(target, 1, 4)`; next `callback = MethodHandles.dropArguments(bound, 0, String.class)`.
10. Yes; the adapter holds a reference to the list, without implicitly cloning it.
11. No; `bindTo` only binds the first parameter of a reference type; use `insertArguments`.
12. When you need to validate/inspect/manage context, because a dropped argument never reaches the target logic.

## 15. Official References

- [Java SE 21 API — `MethodHandles.insertArguments`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandles.html#insertArguments(java.lang.invoke.MethodHandle,int,java.lang.Object...)): defines binding fixed values, `pos` range, parameter types, and boxed values.
- [Java SE 21 API — `MethodHandles.dropArguments`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandles.html#dropArguments(java.lang.invoke.MethodHandle,int,java.lang.Class...)): creates a handle that accepts new arguments but ignores them.
- [Java SE 21 API — `MethodHandle`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandle.html): `type()`, `invokeExact`, `invoke`, `bindTo`, and signature conversions.
- [Java SE 21 API — `MethodType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodType.html): argument/return types, `parameterCount()`, and immutable descriptor objects.
- [Java SE 21 API — `MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): how to obtain method handles for static/virtual methods and the effect of the receiver.

When designing a `MethodHandle` pipeline, follow two rules: **`insertArguments` pre-binds values so the caller passes fewer**; **`dropArguments` adds slots to accept values and then ignores them so the caller passes more**. Using `handle.type()` after each step and re-checking `invokeExact` against the new signature will help you adapt invocations accurately without changing the original method.