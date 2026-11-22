# 7.6. invokeWithArguments and the Cost of the Object-Based Call Path

## Objectives

After this lesson, you will be able to:

- Explain accurately how `MethodHandle.invokeWithArguments` accepts an `Object...` array or a `List<?>` and returns `Object`.
- Distinguish the generic call path `invokeWithArguments` from `invokeExact`, `invoke`, and the `asType`, `asSpreader` adapters.
- Point out the potential costs of boxing/unboxing, argument arrays, type conversions, and loss of static type information when looping through an `Object`-based call path.
- Identify typical errors involving argument count, data types, `null`, receivers, and Java varargs.
- Decide when flexibility is worth it and when a strongly typed call structure is needed; verify with runnable Java 17+ examples.

## 1. The Problem: You Have a MethodHandle, but the Arguments Are Only in Object Form

A `MethodHandle` is a typed reference to an executable operation: a method, constructor, field, or adapter chain. Each handle carries a `MethodType` consisting of **a parameter type list and a return type**. For example, a method `static int sum(int, int)` has a handle of type:

~~~text
(int,int)int
~~~

That is the type of the **target handle**, independent of where the program obtains its input data.

In a normal Java call, the compiler sees the number and static types of the arguments:

~~~java
// Illustrative fragment, assuming sum is a MethodHandle with type (int,int)int.
int result = (int) sum.invokeExact(20, 22);
~~~

However, an application reading commands from JSON, configuration, a plugin tool, or a data row often only has a list:

~~~java
// Illustrative fragment, not a standalone program.
Object[] arguments = { Integer.valueOf(20), Integer.valueOf(22) };
Object result = sum.invokeWithArguments(arguments);
~~~

`invokeWithArguments` is a convenient bridge between **runtime data already wrapped as Object** and **a handle with a specific MethodType**. It does not look up methods by name, does not select overloads automatically, and does not turn `Object` values into a primitive-typed `invokeExact` call site.

The central question of this lesson: **when the handle is already known and its type is stable, what are the costs and limitations of going through an Object list?**

## 2. The API Contract of invokeWithArguments

Java SE 17 defines two main overloads on `MethodHandle`:

~~~java
// API declaration for reference; not a class the learner needs to implement.
public Object invokeWithArguments(Object... arguments) throws Throwable;
public Object invokeWithArguments(java.util.List<?> arguments) throws Throwable;
~~~

These are **ordinary Java methods**. This differs from the two special names `invokeExact` and `invoke`: those two methods are **signature-polymorphic**, so the JVM inspects the argument types and return type recorded in bytecode by the compiled Java call site.

With `invokeWithArguments`:

1. **The argument count** comes from the length of the `Object[]` array or `List<?>`. Each element represents **one argument**; types are not inferred from variable names.
2. **The static types at the generic call boundary** are treated as `Object`. The JVM must adapt them to the parameters specified in `handle.type()`.
3. The corresponding conversion path can perform **reference casts**, **unboxing**, **primitive widening**, and **varargs collection** if the handle is a varargs collector.
4. **The return value** is represented as `Object`: primitive results are boxed (for example, `int` becomes `Integer`); a handle returning `void` yields `null`.
5. If the argument types or count do not match, the call may throw an error. An exception thrown by the **target method** can propagate directly as `Throwable`; it is not automatically wrapped in `InvocationTargetException` like `Method.invoke`.

The `invokeWithArguments(List<?>)` overload has semantics equivalent to taking the list elements into an array and calling the array overload (per the API contract). This is very convenient when the input is already a `List`, though it may also involve creating an intermediate array.

**Important note:** The `Object...` declaration here belongs to the **API of invokeWithArguments**; it does not automatically turn the target handle into a method taking `Object[]`. Each array element is spread out as an individual argument to the handle.

### 2.1. Three Call Paths That Look Similar but Have Different Contracts

| Call Form | Type Information at Call Site | Allowed Conversions | Result Type at Call Site | Appropriate When |
| --- | --- | --- | --- | --- |
| `invokeExact(...)` | Descriptor must **exactly match** the handle's `MethodType` | No type adaptation at the call site | Must match the handle's return type | Exact signature is known, call path is stable |
| `invoke(...)` | Descriptor is statically determined from the Java expression | Can adapt using `asType` rules | According to the call site descriptor | Call site signature is known, but valid conversions are needed |
| `invokeWithArguments(Object...)` | Arguments seen as `Object`, count from the array | General conversion like calling `invoke` through Object | Always `Object` | Actual argument list is only decided at runtime |
| `invokeWithArguments(List<?>)` | `List` elements seen as `Object` | Same semantics as the array form | Always `Object` | Bridging from a data structure that is already a list |

Do not conclude that `invoke` is always slow or `invokeExact` is always fast in every case: optimization depends on the JIT, handle type, call site stability, adapter structure, and workload. The table describes the **semantic contract**, not benchmark results.

## 3. From a Specific MethodType to an Object Call

Suppose we have a handle:

~~~text
Target MethodType:       (int, int)int
Actual data:             Object[] { Integer(20), Integer(22) }
At generic boundary:     (Object, Object)Object
                          |       |
                          v       v
                     unbox Integer to int
                          |
                     call sum(int,int)
                          |
                   int result = 42
                          |
                     box to Integer
                          |
                 return Object reference
~~~

The diagram illustrates **boundary conversions**, not a requirement that the JVM always constructs every adapter or allocates every object literally as drawn on each call. The JIT can eliminate some boxing/arrays if it proves they are unnecessary. Even so, at the API level, the generic call path still forces the program to work with `Object` instead of passing/receiving `int` directly.

What conversions can and cannot do:

- `Integer(20)` can be **unboxed** for an `int` parameter.
- `Short(20)` can be unboxed to `short`, then **primitive widened** to `int`.
- `"20"` is a `String`; it is **not automatically parsed** into the number `20`. This is not a JSON or text data-conversion mechanism.
- `null` cannot be unboxed to `int`, so it can throw `NullPointerException`.
- The number of argument elements must match the handle's arity, unless the handle has varargs-collecting capability.
- If the handle represents an **instance method without a bound receiver**, the receiver is the **first argument** in the handle's `MethodType`; the Object-based call path must pass it as well.

## 4. Full Example: invokeExact, invoke, and invokeWithArguments

Save the file **InvokeObjectBridgeDemo.java**.

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;
import java.util.List;

public class InvokeObjectBridgeDemo {
    static int sum(int left, int right) {
        return left + right;
    }

    static void record(String text) {
        System.out.println("record=" + text);
    }

    static final class Calculator {
        int triple(int n) {
            return n * 3;
        }
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodHandle sum = lookup.findStatic(
                InvokeObjectBridgeDemo.class,
                "sum",
                MethodType.methodType(int.class, int.class, int.class));

        System.out.println("type=" + sum.type());
        int exact = (int) sum.invokeExact(20, 22);
        int inexact = (int) sum.invoke(20, 22);
        Object dynamic = sum.invokeWithArguments(20, 22);
        System.out.println("exact=" + exact);
        System.out.println("invoke=" + inexact);
        System.out.println("objectResult=" + dynamic);
        System.out.println("resultClass=" + dynamic.getClass().getSimpleName());
        System.out.println("list=" + sum.invokeWithArguments(List.of(20, 22)));
        System.out.println("objectArray="
                + sum.invokeWithArguments(new Object[]{20, 22}));
        System.out.println("widen="
                + sum.invokeWithArguments(Short.valueOf((short) 20), 22));

        try {
            sum.invokeWithArguments(20);
        } catch (WrongMethodTypeException ex) {
            System.out.println("wrongArity=" + ex.getClass().getSimpleName());
        }
        try {
            sum.invokeWithArguments("20", 22);
        } catch (ClassCastException ex) {
            System.out.println("wrongType=" + ex.getClass().getSimpleName());
        }
        try {
            sum.invokeWithArguments((Object) null, 22);
        } catch (NullPointerException ex) {
            System.out.println("nullPrimitive=" + ex.getClass().getSimpleName());
        }

        MethodHandle record = lookup.findStatic(
                InvokeObjectBridgeDemo.class,
                "record",
                MethodType.methodType(void.class, String.class));
        Object noValue = record.invokeWithArguments("ok");
        System.out.println("voidReturnsNull=" + (noValue == null));

        MethodHandle triple = lookup.findVirtual(
                Calculator.class, "triple", MethodType.methodType(int.class, int.class));
        System.out.println("virtualType=" + triple.type());
        System.out.println("virtual=" + triple.invokeWithArguments(new Calculator(), 14));

        MethodHandle spread = sum.asSpreader(Object[].class, 2);
        System.out.println("spreadType=" + spread.type());
        int spreadValue = (int) spread.invokeExact(new Object[]{20, 22});
        System.out.println("spreadResult=" + spreadValue);

        MethodHandle objectAdapter = sum.asType(
                MethodType.methodType(Object.class, Object.class, Object.class));
        System.out.println("adapterType=" + objectAdapter.type());
        Object adapted = (Object) objectAdapter.invokeExact(
                (Object) Integer.valueOf(20), (Object) Integer.valueOf(22));
        System.out.println("adapterResult=" + adapted);
    }
}
~~~

Run with JDK 17+:

~~~bash
javac -encoding UTF-8 InvokeObjectBridgeDemo.java
java InvokeObjectBridgeDemo
~~~

Stdout:

~~~text
type=(int,int)int
exact=42
invoke=42
objectResult=42
resultClass=Integer
list=42
objectArray=42
widen=42
wrongArity=WrongMethodTypeException
wrongType=ClassCastException
nullPrimitive=NullPointerException
record=ok
voidReturnsNull=true
virtualType=(Calculator,int)int
virtual=42
spreadType=(Object[])int
spreadResult=42
adapterType=(Object,Object)Object
adapterResult=42
~~~

### 4.1. Why Do exact and invoke Both Produce 42?

At the two call sites:

~~~java
// Fragment from the given program:
int exact = (int) sum.invokeExact(20, 22);
int inexact = (int) sum.invoke(20, 22);
~~~

Javac generates the descriptor **(int,int)int** for both calls; it matches `sum.type()`. There is no need to convert data types. With `invokeExact`, even **the return type at the call site** must match exactly; therefore, casting the result to `int` in the expression determines the descriptor.

If you write:

~~~java
// Fragment illustrating a runtime error; not in main above:
Object wrongReturn = sum.invokeExact(20, 22);
~~~

The call site requests a descriptor returning `Object` while the actual handle returns `int`: the program can compile, but when executing the exact call it will encounter `WrongMethodTypeException`. You cannot look only at the argument types and ignore the return type of `invokeExact`.

### 4.2. Why Is objectResult an Integer?

`sum.invokeWithArguments(20, 22)` receives its arguments through the Java `Object...` path: primitive values are represented by the `Integer` wrapper at the Object boundary. The call adapts them to `int` parameters, and the method computes `int 42`; the result returns through the `Object` API, so it takes the form of an `Integer`. Hence:

~~~text
objectResult=42
resultClass=Integer
~~~

A program that wants to continue using the result as an `int` must check/cast appropriately, for example `int number = (int) sum.invokeWithArguments(20, 22);`. Such a call path has an extra boxing/unboxing boundary compared to `invokeExact` with a primitive descriptor. Do not assume a physical allocation happens every time; that is a matter of JIT optimization that requires measurement.

### 4.3. Why Is Short Accepted While String Is Rejected?

A `Short` argument can be unboxed and then widened to `int`, so `widen=42`. However, `"20"` has no valid conversion to `int` under `asType` rules; this example throws `ClassCastException`.

A call passing only one argument to `sum(int,int)` has a mismatched arity, so `WrongMethodTypeException` occurs. A call passing `null` in an `int` position requires unboxing from null, so it throws `NullPointerException`.

These three errors illustrate **three different causes**: argument count, data type, and a null value during primitive conversion. Do not lump them together as "method does not exist".

### 4.4. Why Does void Return null, and Why Does an Instance Method Add a Receiver?

The handle for `record(String)` returns `void`, but the generic API returns `Object`; by contract, the observed value is `null` after the method prints `record=ok`.

The handle `findVirtual(Calculator.class, "triple", (int)int)` has runtime type `(Calculator,int)int`. The first argument must be **the Calculator receiver**, followed by the parameter `14`. If you call `triple.invokeWithArguments(14)`, the receiver is missing and the arity is wrong. You can use `bindTo(calculator)` to create a new handle with a fixed receiver, but you should re-check `type()` after binding.

### 4.5. The Two Adapters in the Example Do Not Mean "No More Object Cost"

`sum.asSpreader(Object[].class, 2)` creates a handle that takes **one Object[]** and spreads its two elements to call `sum(int,int)`. The adapter is configured **once** when creating the handle; it can then be called with the descriptor `(Object[])int`:

~~~java
// Fragment from the full program:
MethodHandle spread = sum.asSpreader(Object[].class, 2);
int result = (int) spread.invokeExact(new Object[]{20, 22});
~~~

There is still an `Object[]` argument array and `Integer` values to unbox; the adapter mainly lets you **lock in the argument-spreading behavior upfront** instead of selecting the generic bridge path on every call.

`sum.asType(MethodType.methodType(Object.class, Object.class, Object.class))` creates a handle advertising type **(Object,Object)Object**, which can then be called via `invokeExact` with the corresponding descriptor. This can fit when the input interface **must be Object**, but it still does not turn the return type into a primitive or eliminate boxing at the boundary.

## 5. Important Trap: The Object... of invokeWithArguments Itself

There are **two different layers of varargs** to distinguish:

1. `invokeWithArguments(Object... arguments)` uses **Java caller** varargs syntax to construct/pass an `Object` list.
2. **The target handle** may be a varargs collector or a regular fixed-arity handle. These two cases interpret the trailing argument differently.

This is especially important when the target argument **is itself an array**.

### 5.1. Standalone Program Illustrating Argument Shape

Save the file **ArgumentShapeDemo.java**:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;

public class ArgumentShapeDemo {
    static String joinArray(String[] words) {
        return String.join("|", words);
    }
    static String prefixed(String prefix, String... words) {
        return prefix + "=" + String.join("|", words);
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodHandle arrayOnly = lookup.findStatic(
                ArgumentShapeDemo.class,
                "joinArray",
                MethodType.methodType(String.class, String[].class));
        System.out.println("arrayType=" + arrayOnly.type());
        System.out.println("oneArray="
                + arrayOnly.invokeWithArguments((Object) new String[]{"a", "b"}));
        try {
            arrayOnly.invokeWithArguments((Object[]) new String[]{"a", "b"});
        } catch (WrongMethodTypeException ex) {
            System.out.println("spreadMistake="
                    + ex.getClass().getSimpleName());
        }

        MethodHandle varargs = lookup.findStatic(
                ArgumentShapeDemo.class,
                "prefixed",
                MethodType.methodType(String.class, String.class, String[].class));
        System.out.println("varargsCollector=" + varargs.isVarargsCollector());
        System.out.println("variableCall="
                + varargs.invokeWithArguments("tag", "x", "y"));
        System.out.println("fixedArray="
                + varargs.asFixedArity().invokeWithArguments(
                        "tag", (Object) new String[]{"x", "y"}));
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 ArgumentShapeDemo.java
java ArgumentShapeDemo
~~~

Stdout:

~~~text
arrayType=(String[])String
oneArray=a|b
spreadMistake=WrongMethodTypeException
varargsCollector=true
variableCall=tag=x|y
fixedArray=tag=x|y
~~~

### 5.2. Why Is Casting to Object Different from Casting to Object[]?

`joinArray(String[])` has a fixed-arity handle that requires exactly **one parameter of type String[]**.

- `invokeWithArguments((Object) new String[]{"a", "b"})` tells Java to create **one Object element** holding the entire `String[]`, so the handle receives one array.
- `invokeWithArguments((Object[]) new String[]{"a", "b"})` passes the `String[]` array itself as the **argument array** for `Object...`; it becomes **two String arguments**. The target handle only accepts one `String[]`, so the arity is wrong.

This is a trap in the **Java varargs method call**, even before conversions into the target handle take place. The syntax `new Object[]{new String[]{"a", "b"}}` also expresses a single array argument explicitly.

With `prefixed(String, String...)`, `findStatic` normally returns a handle in **varargs collector** mode because the original Java method is varargs. When calling `invokeWithArguments("tag", "x", "y")`, the handle can collect the words into an appropriate `String[]`. When you want to pass **an existing array as a single array argument**, `asFixedArity()` removes the varargs collector interpretation, and the call passes `(Object) new String[]{...}` as a single array.

According to the Javadoc, `invokeWithArguments` on a varargs collector has rules for **collecting a new array**, even in some situations where an array is passed that already looks like it matches. Therefore, do not use it under the assumption that "the array will always be passed intact without creating another array".

## 6. What Makes Up the "Cost of Object"?

There is no single fixed overhead number for every application. The cost depends on the processor, JVM, JIT, data flow, and handle structure. However, there are points that should be **visible in the programming contract**:

| Source of Cost | Why It Can Happen | How Can It Be Reduced? |
| --- | --- | --- |
| **Object[] / List → array** | Java varargs may need an array; the List overload creates an array representing the elements | Use a fixed-arity call path if the signature is known; reuse suitable structures when safe |
| **Primitive boxing / unboxing** | Primitives cannot sit directly in `Object[]`; primitive results must come out as `Object` | Use `invokeExact` with a primitive descriptor if possible |
| **Parameter conversion** | Parameters at the Object boundary must undergo cast/unboxing/widening checks against the target `MethodType` | Type and validate early; stable adapters like `asType` if helpful |
| **Varargs collection on target handle** | A varargs collector may create the trailing array when receiving separate elements | `asFixedArity()` + explicit array passing if that is the desired contract |
| **General checks / dispatch** | Runtime lists have varying lengths/types, giving the optimizer less static information | Cache handles/adapters by signature; limit polymorphism on hot paths |
| **Unpacking the result** | Caller receives `Object` and must cast/unbox to use it further | Keep specific primitive/reference return types in fixed call paths |

For example, the snippet:

~~~java
// Illustrative fragment, assuming mh has type (int,int)int:
for (int i = 0; i < requests.size(); i++) {
    Object[] row = requests.get(i);       // The values are already Object
    Object answer = mh.invokeWithArguments(row);
    consume(answer);
}
~~~

**Not a standalone program**; `mh`, `requests`, and `consume` are illustrative entities. This may be appropriate if each request has a different structure, but if all of them are `sum(int,int)` operations in a hot loop, this call path misses the opportunity to express primitive arguments/results explicitly.

A stably typed path:

~~~java
// Illustrative fragment; mh has type (int,int)int:
for (int i = 0; i < count; i++) {
    int answer = (int) mh.invokeExact(left[i], right[i]);
    sink += answer;
}
~~~

This snippet still needs variable declarations and `Throwable` handling, but it exposes the fixed **(int,int)int** descriptor to the JIT. There is no need to convert every element to `Object` right at the call boundary.

### 6.1. Does Every invokeWithArguments Call Allocate an Array?

**You cannot conclude that from source code.** Java varargs/List and adaptation steps impose a structure, but the JVM can use escape analysis, inlining, and other optimizations to eliminate allocations in specific cases. Conversely, a call path carrying an `Object[]` that is genuinely stored or exchanged with external components may not optimize the same way as a static primitive path.

For that reason, you should only say **there is a risk of overhead and loss of type information**, not "it is exactly N times slower" without measuring on a real workload.

### 6.2. Overhead Also Comes from Where Data Is Created, Not Just invokeWithArguments

For example, a JSON parser creates a `List<Object>`; numeric values might be `Integer`, `Long`, `Double`, or another type depending on the library/configuration. Without a schema, parsing, validating, converting types, and dispatching are already separate costs. Replacing one `invokeWithArguments` call with `invokeExact` does not automatically eliminate all those steps.

A generally better design is to **normalize data at the boundary**:

~~~text
JSON / config / plugin input
    |
    v
validate schema + controlled value conversion
    |
    +--> rare dynamic call path, use invokeWithArguments
    |
    +--> frequently repeated call path, use typed and cached handle/adapters
~~~

## 7. Choosing an API by Situation

### 7.1. When invokeWithArguments Is Worth Using

- **Generic runtime bridge:** calling a handle from a system that has an array/list of arguments but cannot write static call sites for every MethodType.
- **Tooling and testing:** command runners, test harnesses, adapters between Reflection/JNI and MethodHandle.
- **Not-too-hot dynamic config paths:** each request has a different operation name or arity, and parsing/network/I/O cost is usually larger than invocation cost.
- **Prototyping:** when flexibility and observability are needed before optimizing a specific call path.

In these situations, correctness of **schema, argument count, data types, and error handling** matters more than micro-optimization expectations.

### 7.2. When to Use invokeExact or invoke

If the handle and parameter list are **stable** inside a loop/call site, consider:

~~~java
// Fragment: mh.type() must equal methodType(int.class,int.class,int.class).
int value = (int) mh.invokeExact(20, 22);
~~~

`invokeExact` gives the JVM a fixed descriptor without requiring automatic `Object`-to-primitive conversion at this boundary. If the types at the call site are statically determined but valid conversions are needed, `invoke` allows adapting to the target `MethodType` according to `asType` rules.

**Do not choose `invokeExact` just because "Exact" sounds fast.** If you have to perform many casts/boxings before the call site or the handle changes types constantly, overall performance still depends on the design.

### 7.3. When to Prepare an Adapter Once

`asType` creates a handle with a new MethodType; `asSpreader` turns multiple trailing arguments into an array; `asCollector` turns a trailing array into a number of explicit arguments. They help describe a **stable adaptation contract** upfront, rather than letting every call handle a completely generic situation from scratch.

For example:

~~~java
// Fragment: mh is (int,int)int.
MethodHandle spread = mh.asSpreader(Object[].class, 2);
// spread.type() is (Object[])int.
int result = (int) spread.invokeExact(new Object[]{20, 22});
~~~

This kind of adapter still has to accept an `Object[]` array. It **does not eliminate boxing** of numeric values inside the array, though it preserves the `int` return type and fixes the spreading operation. If the operation is reused many times, initialize and check the adapter early, and store it under a valid signature.

Another case is a fixed calling interface that takes `Object, Object` and returns `Object`:

~~~java
// Fragment: mh is (int,int)int.
MethodHandle objectHandle = mh.asType(
        MethodType.methodType(Object.class, Object.class, Object.class));
Object result = (Object) objectHandle.invokeExact(
        (Object) Integer.valueOf(20), (Object) Integer.valueOf(22));
~~~

This is an `invokeExact` call **on an Object-typed adapter**, not a primitive exact call. You must identify which boundaries still involve boxing before expecting performance gains.

### 7.4. If There Are Many Config-Driven Handles

Instead of calling `findStatic`/`findVirtual` and building adapters on every request, you can build a **registry** mapping allowed operation keys/signatures to cached handles. Be mindful of class/class loader identity and plugin lifecycles: do not retain handles referencing expired loaders indefinitely.

If the system does not trust its input, do not let requests arbitrarily pick classes/methods by name alone. Map valid commands to an approved set of MethodHandles, and validate argument counts and types before invoking.

## 8. Common Errors and How to Diagnose Them

| Symptom | Possible Cause | How to Handle |
| --- | --- | --- |
| `WrongMethodTypeException` | Argument count does not match fixed-arity or cannot adapt MethodType | Print `handle.type()`, check arity and varargs collector mode |
| `ClassCastException` | `Object` value cannot be cast/unboxed to the target type | Check runtime class and schema; do not assume numeric strings auto-parse |
| `NullPointerException` on primitive parameter | Unboxing a null argument | Reject null or define an explicit default value at the schema layer |
| Passing one `String[]` turns into two arguments | Java `Object...` call treats the array as the argument array | Cast to `Object` when one array is desired; or use `new Object[]{array}` |
| Varargs handle collects unexpectedly | `isVarargsCollector()==true` and the generic path may re-collect | Use `asFixedArity()` when passing an array as a fixed trailing parameter |
| Instance method is not invoked | Missing receiver as the first argument | Check `handle.type()`; consider `bindTo(receiver)` |
| Return value is `Integer` but `int` is wanted | `invokeWithArguments` returns `Object` | Cast/unbox safely; consider a typed call |
| Target method throws an exception | `throws Throwable` propagates errors from the target | Handle business exceptions properly; do not confuse them with adaptation errors |

There is one more difference to remember: `java.lang.reflect.Method.invoke` normally wraps target method exceptions in `InvocationTargetException`. `MethodHandle.invokeWithArguments` does not impose such a wrapper; manage `Throwable` based on the target method's contract.

## 9. How to Measure Performance Properly

If you make optimization decisions based on throughput or latency, measure with **JMH** or a benchmark design that includes warm-up and mechanisms to prevent optimizing away the work. Principles:

1. Compare **the same business behavior, the same data, and the same result types**.
2. Separate **lookup/adapter creation** cost from **repeated invocation** cost, if adapters are cached in the real application.
3. Measure the entire pipeline (data parsing, boxing, validation, dispatch) when that is where the application actually spends CPU.
4. Avoid overly simple loop benchmarks that suffer from constant folding or dead-code elimination; consume results with appropriate tools.
5. Account for request distribution, frequency of handle changes, JVM/JDK, JIT warm-up, and GC/allocation.
6. Report both performance and correctness: a faster call path that skips validation or mishandles varargs is not equivalent.

**Do not use stdout or single-run timing from the two demos above to draw performance conclusions.** They verify **semantics**, not microbenchmarks.

## 10. Self-Check Exercises

**Question 1.** A handle has type `(int,int)int`. Why does `invokeWithArguments(20,22)` return `Integer` as `Object`?

**Answer:** The generic API returns `Object`, while the target method returns primitive `int`; the result must be represented via the `Integer` wrapper.

**Question 2.** Why does `invokeWithArguments("20",22)` not turn `"20"` into the number `20`?

**Answer:** Handle conversion allows reference casts and appropriate unboxing/widening; it is not a text parser. For a target `int`, `String` has no valid conversion.

**Question 3.** To call a fixed-arity handle taking a single `String[]`, would you use `invokeWithArguments((Object) arr)` or `invokeWithArguments((Object[]) arr)`?

**Answer:** Use `(Object) arr` or `new Object[]{arr}` to pass **one String[] argument**. The `(Object[]) arr` form passes the elements of `arr` as the argument list.

**Question 4.** Does `invokeExact` only need to match the number of parameters, with any return type allowed?

**Answer:** No. The call site descriptor for `invokeExact` includes **the return type as well** and must match `handle.type()`.

**Question 5.** Why might `asSpreader(Object[].class,2)` not eliminate all Object-path costs?

**Answer:** It fixes the operation of spreading an array into two arguments; the input is still `Object[]` and may require boxing/unboxing for primitives.

**Question 6.** Suppose an RPC system receives `List<Object>` with varying argument counts at low frequency; is it necessary to avoid `invokeWithArguments`?

**Answer:** No. This is a suitable dynamic bridging case, provided schema/arity/argument types are validated and errors are handled clearly. Switch to typed handles only when stability and measured cost justify it.

**Question 7.** Why can you not state that `invokeWithArguments` is exact N times slower from the cost table?

**Answer:** The JVM can optimize arrays/boxing/adapters; cost also depends on inlining, call sites, data, and workload. Reliable benchmarks are needed.

## Key Takeaways

- `invokeWithArguments` is the generic call path for a **runtime argument list**, accepting arguments as `Object` and returning **`Object`**.
- When the target handle uses primitives, you may have to **unbox inputs and box outputs**; type conversion does not replace data parsing/validation.
- `Object...` on **invokeWithArguments itself** and a **target handle's varargs collector** are two different layers; arrays can be spread or collected unexpectedly.
- `invokeExact` requires an exact descriptor including return type; `invoke` adapts from the call site's descriptor; `invokeWithArguments` is most flexible when you only have `Object[]` or `List`.
- When calls have stable signatures and high frequency, prefer **typed calls or prepared/cached adapters**, and measure real workloads before concluding.
- Every call path still requires checking handle creation permissions, argument counts/types, and exceptions from the target method.

## References

- Java SE 17, **MethodHandle**, especially `invokeWithArguments`, `invoke`, `invokeExact`, `asType`, `asSpreader`, and `asFixedArity`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html
- Java SE 17, **MethodType**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html
- Java SE 17, **MethodHandles.Lookup**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html
- OpenJDK JMH (microbenchmark harness): https://github.com/openjdk/jmh
