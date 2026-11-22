# 7.8 `asSpreader`, `asCollector`, `asVarargsCollector` and `asFixedArity`

## 1. Lesson Objectives

`java.lang.invoke.MethodHandle` is a typed reference to an executable invocation. Unlike a normal method call, a `MethodHandle` can be **transformed into an adapter**: the adapter accepts an argument list in a new shape, arranges/converts them, and then invokes the target handle. The four APIs in this lesson focus on the boundary between **a single array** and **multiple positional parameters**:

- `asSpreader`: accepts **an array** and spreads its elements into **N separate arguments** before invoking the target.
- `asCollector`: accepts **N separate arguments**, collects them into **an array**, and passes it to the target.
- `asVarargsCollector`: creates a **variable-arity** adapter; when invoked with `invoke`, the number of trailing arguments can vary and is collected into an array.
- `asFixedArity`: turns off the handle's variable-arity mode; preserves the type and requires **the exact fixed argument shape**.

After this lesson, you will be able to read `MethodType` before/after transformation, choose an adapter based on data direction, invoke accurately using `invokeExact`/`invoke`, identify length/type errors, and distinguish **Java varargs** from a **variable-arity method handle**.

> Core mindset: **an adapter changes the invocation interface of a handle, without modifying the original method**. Always check `handle.type()` and `handle.isVarargsCollector()` to know exactly how a call site can supply arguments.

## 2. Background: `MethodType`, `invokeExact`, `invoke`

Suppose we have a Java method:

```java
static String pair(String label, String left, String right) {
    return label + ":" + left + "|" + right;
}
```

`MethodHandles.lookup().findStatic(...)` can create a handle of type:

```text
(String,String,String)String
     3 parameters    returns String
```

`MethodHandle.type()` returns a `MethodType` describing **the exact parameter types and return type of the handle**, which is not necessarily the original type of the source method after passing through adapters.

Two common invocation methods:

| Invocation | Rule |
| --- | --- |
| `invokeExact(...)` | The static signature at the call site, including the **return type**, must match the handle's `MethodType` exactly |
| `invoke(...)` | Can perform compatible type conversions using a mechanism close to `asType`; a variable-arity handle also has rules for collecting trailing arguments |
| `invokeWithArguments(...)` | Accepts a dynamic number of arguments via an `Object`/`List`-based API; convenient when you already have dynamic data, but does not preserve the strictness of `invokeExact` |

Because `invokeExact` and `invoke` are **signature-polymorphic**, the expression type of each argument and even the type that the result is used as/cast to in Java affect the descriptor being checked. For example, `(String) mh.invokeExact(...)` requires the handle to return `String`; if you want to receive `Object`, there must be a corresponding adapter/type.

A very common mistake: a handle actually has type `(String,String[])String`, yet you write `mh.invokeExact("P", "a", "b")`. Even if it has the variable-arity flag, `invokeExact` **does not automatically pack two Strings into an array**; a `WrongMethodTypeException` will be thrown.

The examples below use Java 17+ and print the handle type via `type()` to observe these changes.

## 3. Comparing the Four Adapters by Data Shape

| API | Requirement on initial handle | Call site shape after transformation | Arity mode |
| --- | --- | --- | --- |
| `asSpreader(A[].class, n)` | Has at least `n` trailing parameters that can accept elements from the array | Replaces the **last n parameters** with **one array** | Fixed |
| `asSpreader(pos, A[].class, n)` | Has `n` parameters starting at `pos` | Replaces that group of parameters with one array at `pos` | Fixed |
| `asCollector(A[].class, n)` | Last parameter is an array (or a type that accepts the requested array) | Replaces **one trailing array** with **n element parameters** | Fixed |
| `asCollector(pos, A[].class, n)` | Parameter at `pos` accepts the created array | Replaces the array at `pos` with `n` element parameters | Fixed |
| `asVarargsCollector(A[].class)` | Last parameter accepts an array of type `A[]` | `type()` still has **one trailing array**, but `invoke` can supply multiple trailing elements | Variable |
| `asFixedArity()` | Any handle; most useful when currently variable | `type()` is unchanged; the trailing array must be supplied in fixed form | Fixed |

In the table, `A[].class` is an illustrative notation for an **array class**, such as `String[].class` or `int[].class`. The `arrayType` parameter of the API is a `Class<?>` object representing the array type, **not an actual array of values**.

**Key difference:** `asCollector` fixes **n** into the new `MethodType`; `asVarargsCollector` leaves the number of trailing elements open at each suitable `invoke` call. These two APIs are not equivalent even though both perform array creation.

## 4. `asSpreader`: One Array Becomes Multiple Parameters

### 4.1. Spreading Trailing Parameters

Starting from:

```text
target:          pair(String label, String left, String right)
type:            (String,String,String)String

asSpreader(String[].class, 2)

adapter:         (String,String[])String
call:            adapter("P", {"A","B"})
target receives: pair("P", "A", "B")
result:          P:A|B
```

`asSpreader(String[].class, 2)` replaces **the last two parameters** of the target with **one `String[]`**. The passed array must have exactly **2 elements**; the adapter reads them in order and passes them into `left`, `right`.

Standalone Java call example in a context where `spreadTail` has been created:

```java
String result = (String) spreadTail.invokeExact(
        "P", new String[]{"A", "B"});
// result: "P:A|B"
```

**Do not confuse the direction:** the target needs three `String`s, and the new adapter takes two parameters consisting of one `String` and one `String[]`. `asSpreader` does not "concatenate arrays into one array".

### 4.2. Spreading an Array at Any Position

Java 9+ has the overload:

```java
asSpreader(int spreadArgPos, Class<?> arrayType, int arrayLength)
```

`spreadArgPos` is a **zero-based** index into the target's parameter list. With `pair(String,String,String)`:

```text
pair:             (String,String,String)String
asSpreader(0, String[].class, 2)
adapter:          (String[],String)String

adapter({"P","A"}, "B") -> pair("P","A","B")
```

This is useful when the data packed into an array is **in the middle or at the beginning** of the argument list, not necessarily at the end.

### 4.3. Rules on Length, Null, and Array Type

- `arrayLength` is the **number of elements to spread**, not an arbitrary maximum length. With `arrayLength=2`, an array of length 1 or 3 does not match, and the call can throw `IllegalArgumentException` when checking the length.
- If `arrayLength > 0`, a `null` array cannot supply elements; invoking throws an error such as `NullPointerException`. Do not use `null` to represent an empty list in this case.
- If `arrayLength=0`, the adapter still takes an additional **array parameter**, but extracts no elements; `null` may be valid for a zero-length array under this contract. This is an edge case easily overlooked when generating `MethodType` automatically.
- `arrayType` must be an actual array type. A negative `n`, a negative `pos` or one exceeding the number of parameters, or an unadaptable type combination will be rejected when creating the adapter.
- If an array element needs a type conversion to match the target parameters, Method Handle conversion rules apply; for example, unboxing/casting can succeed or throw an error at runtime.
- The array can be a **primitive array**: from `(int,int,int)int`, `asSpreader(int[].class,3)` produces `(int[])int`, not `(Integer[])int`.

### 4.4. When Should You Use It?

When data comes from a source already packed into an array, such as an API that parses into `String[]`, while the target handler requires separate parameters of **known count and types**. It is especially useful in a Method Handle processing pipeline, where you can adapt signatures without writing a manual Java wrapper for each function.

## 5. `asCollector`: Multiple Parameters Collected Into One Array

### 5.1. Collecting Trailing Parameters

Suppose the target is:

```java
static String pack(String prefix, String[] items) {
    return prefix + Arrays.toString(items);
}
```

The target has `MethodType`:

```text
(String,String[])String
```

Adapter:

```java
MethodHandle collected = packHandle.asCollector(String[].class, 3);
```

has type:

```text
(String,String,String,String)String
```

It requires **three trailing `String`s**. When calling `collected("C","a","b","c")`, the adapter creates a `String[]` containing `{"a","b","c"}` and passes it to `pack("C", array)`. The result is `C[a, b, c]`.

How it differs from `asSpreader`: `asCollector` only applies to a target that **already has an array parameter**, and the new adapter **exposes N separate element parameters** externally.

If `arrayLength=0`, the array parameter is replaced by **0 parameters**. The corresponding adapter only requires the fixed prefix part; an empty array is supplied to the target (which may be optimized by the implementation to reuse the array).

### 5.2. Collecting at Any Position

Overload since Java 9:

```java
asCollector(int collectArgPos, Class<?> arrayType, int arrayLength)
```

The parameter at `collectArgPos` of the target is replaced by `arrayLength` parameters of the element type. For example:

```text
target:      surround(String[] parts, String suffix)
type:        (String[],String)String
asCollector(0, String[].class, 2)
adapter:     (String,String,String)String

adapter("L", "R", "done")
       -> surround(new String[]{"L","R"}, "done")
       -> [L, R]/done
```

Position `0` is the first array; `suffix` at the end remains a separate parameter and is not collected. This can avoid having to permute parameter order in a pipeline.

### 5.3. Constraints on Type and Count

- `arrayType` must be an array class, and that array must be **assignable to the target's array parameter** at the collection position. For example, if the target accepts `Object[]`, you can collect into `String[]` because `String[]` is a subtype of `Object[]`.
- `arrayLength` is the **fixed** number of element parameters of the adapter; negative counts and parameter types/counts exceeding Method Handle limits are invalid.
- If the target accepts `int[]`, use `int[].class` so the new parameters are `int`, rather than defaulting to `Integer`.
- `asCollector` returns a **fixed-arity** handle, even if the input handle has the variable-arity flag. To accept varying numbers of trailing parameters across different calls, consider `asVarargsCollector`.
- Each method handle may have JVM parameter/slot count limits; collecting an overly large array into too many parameters is invalid even though a Java array itself can be much longer.

### 5.4. The Two Directions Are Not Always Strict Inverses

A chain `target.asSpreader(T[].class,n).asCollector(T[].class,n)` usually restores the original **type shape** if all type conditions are compatible, as in the `pair` example. However, conversions, casts, or length/array checks may occur, so **do not assume** the two adapters produce the exact same original handle object or are equivalent in every situation. Check `type()` and runtime values.

## 6. `asVarargsCollector`: Trailing Element Count Varies by `invoke`

### 6.1. The Type Still Has a Trailing Array

Continuing with the target `pack(String, String[])`:

```java
MethodHandle variable = packHandle.asVarargsCollector(String[].class);
```

At this point:

```text
variable.type()               -> (String,String[])String
variable.isVarargsCollector() -> true
```

`asVarargsCollector` **does not** make `type()` have a variable number of parameters. It puts the handle into a **special mode for `invoke` and `asType` calls**. Both of the following calls can succeed:

```java
String zero = (String) variable.invoke("V");
String many = (String) variable.invoke("V", "a", "b", "c");
// zero -> "V[]"
// many -> "V[a, b, c]"
```

When the caller does not already provide a trailing array of a compatible type, the adapter creates a `String[]` with a number of elements matching the remaining arguments and calls the target `pack`.

When the caller **passes a single matching trailing array**, it can pass through as an existing array. For example:

```java
String direct = (String) variable.invokeExact(
        "V", new String[]{"x", "y"});
// direct -> "V[x, y]"
```

`invokeExact` in the example above succeeds because the call site **matches `(String,String[])String` exactly**, requiring no varargs collection at all.

### 6.2. `invokeExact` Does Not Support Varying Argument Counts

A point that often leads to `WrongMethodTypeException`:

```java
// Counterexample snippet; variable has type (String,String[])String.
String wrong = (String) variable.invokeExact("V", "a", "b");
// Invalid: call site (String,String,String)String.
```

Even though `isVarargsCollector() == true`, an `invokeExact` call does not use the flexible rules of `invoke`. It requires the call site descriptor to match `type()`. If you need to pass three `String`s using `invokeExact`, **create `asCollector(String[].class,2)` first** so the handle has type `(String,String,String)String`, then invoke exact with that type.

### 6.3. Conditions for Choosing `arrayType`

The initial handle must have a **trailing array parameter or a trailing parameter type that accepts the specified array**. `arrayType` must actually be an array class. For example, a target whose last parameter is `Object[]` can accept `String[]` and be transformed into a varargs collector with a trailing `String[]` parameter; however, if the target's last parameter is `int` or `String`, which does not accept an array, `asVarargsCollector(String[].class)` cannot be used validly.

If the handle is already a varargs collector with an equivalent trailing array type, calling it again may return the same handle.

### 6.4. Java Source Varargs vs. the MethodHandle Varargs Flag

A method declared with `String... args` in Java has a bytecode parameter of `String[]`, along with the `ACC_VARARGS` flag. When `Lookup.findStatic` / `findVirtual` looks up a Java varargs method, the handle usually **already has `isVarargsCollector() == true`** without needing to call `asVarargsCollector` manually.

Conversely, the target `pack(String, String[])` in the example is declared with a **regular array**, not `String...`. The looked-up handle is initially fixed, so we **explicitly** call `asVarargsCollector(String[].class)` to enable variable-arity invocation. This **does not turn the source method into varargs**, it only adjusts the handle's behavior.

### 6.5. Interaction with `asType` and Calls With an Existing Array

A varargs collector can accept `asType` requests with a different arity or a different trailing parameter type and collect the corresponding parameters. When the caller has the same arity and a compatible trailing array type, it can take the fixed-arity conversion branch instead of packing elements individually. Therefore, to avoid ambiguity when you want to **guarantee passing an array as a whole**, use `invokeExact` with the **exact** array type and return type, or switch to `asFixedArity()`.

With an `Object[]` array and an API accepting `Object...`, casting the array to `Object` in Java source can change how a single trailing argument is recognized at the call site. Look at the **static expression type**, not just the runtime value.

## 7. `asFixedArity`: Turning Off Automatic Collection

Calling:

```java
MethodHandle fixed = variable.asFixedArity();
```

With `variable` above:

```text
variable.type()       = (String,String[])String
fixed.type()          = (String,String[])String

variable.isVarargsCollector() = true
fixed.isVarargsCollector()    = false
```

The two handles have the same `MethodType` but **different behavior** when the caller uses `invoke` with different arities.

Valid:

```java
String value = (String) fixed.invokeExact(
        "F", new String[]{"x", "y"});
// "F[x, y]"
```

Invalid:

```java
// Counterexample snippet; fixed.type() is (String,String[])String.
String wrong = (String) fixed.invoke("F", "a", "b");
// WrongMethodTypeException: no mechanism to collect String,String into String[].
```

`asFixedArity()` **does not** turn `(String,String[])String` into `(String,String)String`, does not automatically unpack the array, and does not make `invokeExact` allow mismatched types. It only disables the variable-arity capability. If the handle is already fixed, `asFixedArity()` may return the current handle itself.

This is the right choice when a framework wants **the trailing array to always be treated as a single argument**, preventing an `invoke` call from accidentally packing additional values into an array.

> If you need an API that **always takes exactly three strings** before creating an array, use `asCollector(String[].class, 3)`. If the API wants to **accept a varying number of strings each time** via `invoke`, use `asVarargsCollector(String[].class)`. If the API accepts **an already prepared array**, use a fixed-arity handle.

## 8. Complete, Runnable Java 17+ Example

This example demonstrates both **overloads with a position index**, operations on a primitive array, length errors, `invokeExact` versus `invoke`, and checking varargs status.

Save the entire content as **`HandleArrayAdaptersDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;
import java.util.Arrays;

public class HandleArrayAdaptersDemo {
    public static String pair(String label, String left, String right) {
        return label + ":" + left + "|" + right;
    }

    public static String pack(String prefix, String[] items) {
        return prefix + Arrays.toString(items);
    }

    public static String surround(String[] parts, String suffix) {
        return Arrays.toString(parts) + "/" + suffix;
    }

    public static int sum3(int a, int b, int c) {
        return a + b + c;
    }

    public static String natural(String prefix, String... parts) {
        return pack(prefix, parts);
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        MethodHandle pair = lookup.findStatic(
                HandleArrayAdaptersDemo.class, "pair",
                MethodType.methodType(String.class,
                        String.class, String.class, String.class));

        // Array -> last 2 parameters.
        MethodHandle spreadTail = pair.asSpreader(String[].class, 2);
        // Array -> 2 parameters from position 0.
        MethodHandle spreadHead = pair.asSpreader(0, String[].class, 2);

        System.out.println("pair type=" + pair.type());
        System.out.println("spread tail type=" + spreadTail.type());
        System.out.println("spread tail=" + (String) spreadTail.invokeExact(
                "P", new String[]{"A", "B"}));
        System.out.println("spread head type=" + spreadHead.type());
        System.out.println("spread head=" + (String) spreadHead.invokeExact(
                new String[]{"P", "A"}, "B"));

        MethodHandle pack = lookup.findStatic(
                HandleArrayAdaptersDemo.class, "pack",
                MethodType.methodType(
                        String.class, String.class, String[].class));

        // Last 3 String parameters -> 1 String[].
        MethodHandle collected = pack.asCollector(String[].class, 3);
        System.out.println("pack type=" + pack.type());
        System.out.println("collect type=" + collected.type());
        System.out.println("collect=" + (String) collected.invokeExact(
                "C", "a", "b", "c"));

        MethodHandle surround = lookup.findStatic(
                HandleArrayAdaptersDemo.class, "surround",
                MethodType.methodType(
                        String.class, String[].class, String.class));
        MethodHandle collectAtZero =
                surround.asCollector(0, String[].class, 2);
        System.out.println("collect at zero type=" + collectAtZero.type());
        System.out.println("collect at zero=" + (String)
                collectAtZero.invokeExact("L", "R", "done"));

        // Allow multiple arities when calling with invoke.
        MethodHandle variable = pack.asVarargsCollector(String[].class);
        MethodHandle fixed = variable.asFixedArity();

        System.out.println("variable type=" + variable.type());
        System.out.println("variable flag=" + variable.isVarargsCollector());
        System.out.println("fixed type=" + fixed.type());
        System.out.println("fixed flag=" + fixed.isVarargsCollector());

        System.out.println("variable zero=" + (String)
                variable.invoke("V"));
        System.out.println("variable many=" + (String)
                variable.invoke("V", "a", "b", "c"));
        System.out.println("variable array=" + (String)
                variable.invokeExact("V", new String[]{"x", "y"}));
        System.out.println("fixed array=" + (String)
                fixed.invokeExact("F", new String[]{"x", "y"}));

        // Fixed arity does not accept 2 Strings in place of String[].
        try {
            String ignored = (String) fixed.invoke("F", "a", "b");
            System.out.println("unexpected=" + ignored);
        } catch (WrongMethodTypeException ex) {
            System.out.println("fixed positional=WrongMethodTypeException");
        }

        // Variable arity does not make invokeExact flexible.
        try {
            String ignored = (String) variable.invokeExact("V", "a", "b");
            System.out.println("unexpected=" + ignored);
        } catch (WrongMethodTypeException ex) {
            System.out.println("exact positional=WrongMethodTypeException");
        }

        try {
            String ignored = (String) spreadTail.invokeExact(
                    "P", new String[]{"only-one"});
            System.out.println("unexpected=" + ignored);
        } catch (IllegalArgumentException ex) {
            System.out.println("spread bad length=IllegalArgumentException");
        }

        // N=0: trailing array contributes no elements.
        MethodHandle noArray = pair.asSpreader(String[].class, 0);
        System.out.println("spread zero type=" + noArray.type());
        System.out.println("spread zero=" + (String)
                noArray.invokeExact("P", "A", "B", (String[]) null));

        // Primitive array preserves the int component type.
        MethodHandle sum3 = lookup.findStatic(
                HandleArrayAdaptersDemo.class, "sum3",
                MethodType.methodType(
                        int.class, int.class, int.class, int.class));
        MethodHandle sumArray = sum3.asSpreader(int[].class, 3);
        System.out.println("sum array type=" + sumArray.type());
        System.out.println("sum array=" + (int)
                sumArray.invokeExact(new int[]{2, 3, 4}));

        // findStatic on a Java varargs method creates a variable-arity MH.
        MethodHandle javaVarargs = lookup.findStatic(
                HandleArrayAdaptersDemo.class, "natural",
                MethodType.methodType(
                        String.class, String.class, String[].class));
        System.out.println("source varargs flag="
                + javaVarargs.isVarargsCollector());
        System.out.println("collected flag=" + collected.isVarargsCollector());
        System.out.println("inverse type="
                + spreadTail.asCollector(String[].class, 2).type());
    }
}
```

Compile and run from the directory containing the file:

```bash
javac HandleArrayAdaptersDemo.java
java HandleArrayAdaptersDemo
```

**Exact stdout of the example (verified on JDK):**

```text
pair type=(String,String,String)String
spread tail type=(String,String[])String
spread tail=P:A|B
spread head type=(String[],String)String
spread head=P:A|B
pack type=(String,String[])String
collect type=(String,String,String,String)String
collect=C[a, b, c]
collect at zero type=(String,String,String)String
collect at zero=[L, R]/done
variable type=(String,String[])String
variable flag=true
fixed type=(String,String[])String
fixed flag=false
variable zero=V[]
variable many=V[a, b, c]
variable array=V[x, y]
fixed array=F[x, y]
fixed positional=WrongMethodTypeException
exact positional=WrongMethodTypeException
spread bad length=IllegalArgumentException
spread zero type=(String,String,String,String[])String
spread zero=P:A|B
sum array type=(int[])int
sum array=9
source varargs flag=true
collected flag=false
inverse type=(String,String,String)String
```

**How to interpret each group of results:**

1. `pair` has three `String` parameters; `spreadTail` replaces the last two parameters with `String[]`, while `spreadHead` replaces two parameters starting at index 0. Both adapters invoke the same `pair`, but the input-accepting interface differs.
2. `pack` has one trailing array parameter; `collected` replaces that array with three `String`s, so the type has **four** parameters in total.
3. `collectAtZero` changes the array at the beginning and keeps the trailing `suffix` unchanged. This is why the indexed API is useful.
4. `variable` and `fixed` have the same `type()`, but only `variable` supports `invoke` with 0 or more trailing elements. `invokeExact` must use an array of the exact type.
5. The `WrongMethodTypeException` errors in the example are **intentional** cases to demonstrate the difference between fixed, variable, and exact. The length error from the spreader is `IllegalArgumentException`.
6. `arrayLength=0` adds an array parameter without reading any elements, even when the array value is `null`.
7. With `int[]`, the adapter has type `(int[])int`; it is not converted to `Integer[]`.
8. `natural(String,String...)` is declared as varargs in the source code, so the lookup has `isVarargsCollector() == true`. `asCollector` creates a fixed adapter; hence `collected flag=false`.

## 9. Common Mistakes and How to Fix Them

### 9.1. Using the Wrong Adapter Direction

**Wrong for the need:** the data is already a `String[]`, the target needs `String,String`, yet `asCollector` is used.  
**Fix:** `asSpreader(String[].class,2)` creates a handle that accepts an array. `asCollector` goes in the opposite direction: the target needs an array, while the caller wants to pass individual elements.

Read by diagram:

```text
Spreader:  caller [array]        -> adapter -> target(arg1, arg2, ...)
Collector: caller (arg1,arg2,...) -> adapter -> target([array])
Varargs:   caller (0..N tail args) -> invoke/adapter -> target([array])
Fixed:     caller ([array])      -> target([array])
```

### 9.2. Assuming `asVarargsCollector` Is Equivalent to `asCollector(n)`

`asCollector(String[].class,3)` produces **a fixed `MethodType` accepting exactly three elements** at the collection region. `asVarargsCollector(String[].class)` keeps the trailing array form in `type()` while allowing `invoke` calls with a varying number of trailing elements. If the application has a fixed schema, `asCollector(n)` allows stricter signature checking.

### 9.3. Using `invokeExact` Like a Java Varargs Call

The call `variable.invokeExact("P","a","b")` is still checked against `type()`. Pass a `String[]` of the right type, or create a fixed collector with the appropriate number of parameters. The `isVarargsCollector` flag only enables behavior related to **plain `invoke`/`asType`**.

### 9.4. Ignoring the Return Type at the Call Site

For a target returning `int`, the following snippet can fail because the caller requests `Object` instead of `int`:

```java
// Illustrative snippet, not a standalone program.
Object result = sumArray.invokeExact(new int[]{2, 3, 4});
```

Correct when exact primitive is needed:

```java
int value = (int) sumArray.invokeExact(new int[]{2, 3, 4});
```

To intentionally change the handle's return type, use an appropriate `asType(...)` or call `invoke` when conversion is acceptable. Do not assume `invokeExact` performs autoboxing.

### 9.5. Equating `String[]` with `Object[]` or `int[]` with `Integer[]`

`String[]` is a subtype of `Object[]`, but `Object[]` is not automatically a `String[]`. `int[]` and `Integer[]` are **two different array types**; Method Handle has no rule to automatically turn a primitive array into a wrapper array just because boxing exists for individual elements. You must specify `arrayType` accurately according to the target.

### 9.6. Ignoring Array Length When Using a Spreader

`asSpreader(String[].class,2)` requires an array of **exactly two elements**. An array that is too short or too long is a runtime error; if passing data from JSON or network input, check the size before calling. `asCollector(n)` enforces the element count right at the handle's interface, though it can still encounter type conversion or null errors at the target.

### 9.7. Mistaking `asFixedArity` for "Removing All Adapters"

`variable.asFixedArity()` only switches to fixed mode; **it does not return the original method before all transformations**, does not reverse parameter order, and does not "undo" `asCollector` or `asSpreader`. The resulting adapter still invokes the existing target with the corresponding behavior.

### 9.8. Trying to Use Adapters to Bypass Access Control

`asSpreader`, `asCollector`, and other adapters do not change Java/module access permissions. `MethodHandles.Lookup.findStatic`/`findVirtual`, `privateLookupIn`, and module access control determine whether the target handle can be created. If `Lookup` is not permitted to find the target, adding adapters afterward does not resolve access restrictions.

## 10. Rules for Choosing an API in Practice

| Situation | Start with | Reason |
| --- | --- | --- |
| From `String[] args`, want to call a handler taking `String, String` | `asSpreader(String[].class,2)` | One array is spread into two parameters |
| Handler takes `String[]`, caller wants a signature of exactly 3 `String`s | `asCollector(String[].class,3)` | Collects 3 parameters into an array with fixed arity |
| Array is in the middle/beginning parameters, other parameters stay unchanged | `asCollector(pos,...)` or `asSpreader(pos,...)` | Controls position not necessarily at the end |
| Wrapper accepts a non-fixed number of trailing strings from various `invoke` call sites | `asVarargsCollector(String[].class)` | Chooses array length at invocation time |
| Need to ensure the trailing array is passed as a single argument | `asFixedArity()` combined with `invokeExact`/exact signature | No implicit varargs collection |
| API requires a primitive `int[]` array | Specify `int[].class` and call site type `int[]` | Avoids confusing primitive arrays with wrapper/reference arrays |
| Want to preserve varargs when changing `MethodType` with another adapter | Check `isVarargsCollector()`, consider `withVarargs(boolean)` | Many other transformations return a fixed handle |

### 10.1. Process for Designing an Adapter for a Dispatcher

Suppose a framework receives data as an array or an argument list. Before writing combinators, proceed step by step:

1. **Read the target's type:** get `target.type()`; note the full return type and every parameter type.
2. **Determine the desired type at the caller:** an existing array, a fixed number of elements, or a varying number of elements?
3. **Choose the conversion direction:** caller array → `asSpreader`; caller fixed positional → `asCollector(n)`; caller varying positional via `invoke` → `asVarargsCollector`.
4. **Determine the array class:** `String[].class`, `Object[].class`, `int[].class`... according to the actual types of the data and target; do not just look at `Object`.
5. **If the group is not at the end:** use the overload with `spreadArgPos` / `collectArgPos`, zero-indexed.
6. **Verify the new adapter:** call `type()`, `isVarargsCollector()`, and run a test with valid/invalid data.
7. **Decide the invocation API:** `invokeExact` for an exactly known signature; `invoke` if you intentionally want type conversion/variable arity; `invokeWithArguments` when you already have dynamic list-form arguments, noting Object conversion and Java varargs characteristics at the call site.
8. **Check errors at the right layer:** adapter creation errors (`IllegalArgumentException`/`WrongMethodTypeException`) differ from invocation errors (`WrongMethodTypeException`, wrong length, cast/unbox/null, exceptions from the target).

For a system receiving external data, you must validate counts, types, and nulls before invoking. Adapters help wire runtime components together, but **do not replace validation** and do not automatically create arbitrary data converters.

## 11. Self-Check Exercises

**Question 1.** The target has type `(int,int,int)int`. You want to pass an `int[]` of three elements using `invokeExact`; what do you use?  
**Answer:** `asSpreader(int[].class,3)` creates a handle of type `(int[])int`. Call site: `(int) handle.invokeExact(new int[]{1,2,3})`.

**Question 2.** The target accepts `(String,String[])String`; what type does the adapter `asCollector(String[].class,2)` have?  
**Answer:** `(String,String,String)String`. One trailing array is replaced by two positional `String`s.

**Question 3.** `variable.isVarargsCollector()==true` and `variable.type()==(String,String[])String`. Will `(String) variable.invokeExact("P","x")` automatically collect a `String`?  
**Answer:** No. `invokeExact` requires an exact `String[]` as the second parameter. `invoke` can use the variable-arity mechanism at a suitable call site.

**Question 4.** Does `fixed=variable.asFixedArity()` change `fixed.type()` to `(String,String)String`?  
**Answer:** No. The type does not change; the `isVarargsCollector()` flag switches to `false`.

**Question 5.** From `(String[],String)String`, you need the caller to pass `("a","b","tail")`. What should you choose?  
**Answer:** `asCollector(0,String[].class,2)`; turns the first two `String`s into an array and keeps the `tail` parameter.

**Question 6.** `asSpreader(String[].class,2)` receives an array of length 1. Which layer does the error belong to?  
**Answer:** An error when **invoking the adapter** because the array does not have the exact number of elements to spread; in the Java example, it throws `IllegalArgumentException`.

**Question 7.** After `lookup.findStatic` to a source method declared with `String...`, can `isVarargsCollector()` be true without calling `asVarargsCollector`?  
**Answer:** Yes. Looking up a Java varargs method creates a handle with variable-arity mode per the API contract.

**Question 8.** Will `asSpreader(int[].class,3)` accept an `Integer[]` instead via `invokeExact`?  
**Answer:** No. `int[]` and `Integer[]` are two different array classes; `invokeExact` requires the exact type.

**Question 9.** If a framework wants every call to only accept a trailing array, should you just keep `variable` and call `invoke` arbitrarily?  
**Answer:** You should convert it to fixed using `asFixedArity()` and write the call site to match the desired signature; use `invokeExact` when you have the exact type.

## 12. Key Takeaways and Official Documentation

- **Spreader**: `N positional parameters ← 1 array`. The array appears at the call site.
- **Collector**: `1 array parameter ← N positional arguments`. Positional arguments appear at the call site, with `N` fixed.
- **Varargs collector**: `type()` still contains the trailing array, but `invoke` allows multiple compatible arities; `invokeExact` does not collect automatically.
- **Fixed arity**: keeps `type()` unchanged, turns off multi-arity mode; pass a **trailing array** of the exact type at the call site.
- **Verify with `type()` and `isVarargsCollector()`** before invoking, especially when adapters are chained.

References:

- [Oracle Java SE 17 — `java.lang.invoke.MethodHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html): specification for `asSpreader`, `asCollector`, `asVarargsCollector`, `asFixedArity`, `invoke`, `invokeExact`, and `isVarargsCollector`.
- [Oracle Java SE 17 — `java.lang.invoke.MethodType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html): method handle type model, parameter list, and return type.
- [Oracle Java SE 17 — `java.lang.invoke.MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): creating target handles with `findStatic`/`findVirtual` and access control conditions.
