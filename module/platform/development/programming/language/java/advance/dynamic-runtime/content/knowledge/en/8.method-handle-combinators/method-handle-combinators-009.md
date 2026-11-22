# 8.9 Building a Typed Processing Pipeline and Checking MethodType After Each Combination

When using `java.lang.invoke.MethodHandle`, a dynamic invocation does not necessarily have to point to a single method. We can build a **typed invocation pipeline** by chaining multiple handles: normalizing data, converting types, checking conditions, choosing branches, fixing arguments, and producing results. Each combination creates **a new MethodHandle**; **the `MethodType` of the new handle is the contract that must be checked immediately** before chaining another step.

Target example: from a string input `" 1_240 "`, normalize it to `"1240"`, convert it to the number `1240`, branch by threshold, and then turn it into `"result=large:1240"`. The stages use different types: `String → String → int → String → String`. A correct pipeline must be type-compatible at **every connection point**, not just have a final result that looks right.

This lesson belongs to the **invocation combination** topic and focuses on how to read, compute, and verify `MethodType` after each adapter/combinator. All examples are for **Java 17+**, with complete code, compilation commands, and expected stdout.

## 1. Foundation: MethodHandle, MethodType, and Signature Notation

`MethodHandle` is an invocable object; `MethodType` is the description of **the parameter types and return type at the execution layer** of that handle. We create a `MethodType` using the API:

~~~java
MethodType a = MethodType.methodType(String.class, String.class);
MethodType b = MethodType.methodType(int.class, String.class);
MethodType c = MethodType.methodType(String.class, int.class);
MethodType d = MethodType.methodType(boolean.class, int.class);
~~~

This is an **illustrative snippet**; it requires `import java.lang.invoke.MethodType;` and must be placed inside a class/method context. The corresponding signatures are:

| `MethodType` expression | String displayed via `toString()` | Interpretation |
| --- | --- | --- |
| `methodType(String.class, String.class)` | `(String)String` | Takes `String`, returns `String` |
| `methodType(int.class, String.class)` | `(String)int` | Takes `String`, returns `int` |
| `methodType(String.class, int.class)` | `(int)String` | Takes `int`, returns `String` |
| `methodType(boolean.class, int.class)` | `(int)boolean` | Takes `int`, returns `boolean` |

The parameter order is **the actual order when invoking the handle**; with `findVirtual`, the receiver parameter is placed at the front of the unbound handle's `MethodType`, even though it is not in the declared parameter list of the instance method.

Important APIs:

- `handle.type()`: returns the current `MethodType`; **do not guess from the original method name** after passing through multiple adapters.
- `type.returnType()`: returns the `Class<?>` of the result, which can be a primitive or `void.class`.
- `type.parameterCount()`, `type.parameterType(index)`, `type.parameterArray()`: inspect the input list.
- `type.equals(expected)`: compares **the entire signature**, including the return type, structurally.
- `type.toMethodDescriptorString()`: gets the JVM method descriptor, for example `(Ljava/lang/String;)I` for `(String)int`.
- `type.changeReturnType(...)`, `type.changeParameterType(...)`, `type.insertParameterTypes(...)`, `type.dropParameterTypes(...)`: **only create a new descriptive MethodType**, without automatically changing how a handle is invoked.

`MethodType` does not store generic information such as `List<String>`. It uses runtime `Class<?>` and primitive types after erasure. If you already have a `MethodHandle` and want to change how it is invoked, use `asType` or appropriate combinators, not just replace the `MethodType` object in a variable.

## 2. Inferring Signatures Before Combining

An easy way to avoid mistakes is to treat each handle as a function with its domain and codomain written right next to it:

~~~text
normalize : (String)String
parse     : (String)int
isLarge   : (int)boolean
largeText : (int)String
smallText : (int)String
label     : (String)String
~~~

Thus we can design the pipeline:

~~~text
                 ┌── isLarge : (int)boolean ─┐
(String)          │                          │
   │             ▼                          ▼
normalize    parseInt       guardWithTest(largeText, smallText)
   │             │                          │
   └── (String)int ──────────────────────────┘
                               │
                          (String)String
                               │
                        label : (String)String
                               │
                          (String)String
~~~

The diagram is a map of **value flow and signatures**; a combinator does not automatically infer this flow from Java generics. We must proactively choose the chaining order and ensure types match. Operations such as `filterReturnValue` and `filterArguments` have **different** type contracts:

- `filterReturnValue(target, filter)`: takes **the result of target** and passes it into filter, commonly used to chain post-processing.
- `filterArguments(target, pos, filters...)`: passes the results of filters into **one or more parameter positions of target**, used for input pre-processing.
- `guardWithTest(test, target, fallback)`: checks a condition and calls one of two branches with compatible signatures.
- `collectArguments(target, pos, filter)`: replaces one parameter of target with **the entire parameter list of filter** in order to compute that argument.

Each operation gives us a new handle, whose type can be computed in advance and checked with `type()`.

## 3. Signature Formula Table for Common Combinators

In the table below, `A`, `B`, `X`, `R`, and `S` are **type placeholder symbols** for reading the formulas, not real class names. The examples do not represent every variant (such as targets returning `void`).

| Combinator | Input type example | Resulting handle type |
| --- | --- | --- |
| `filterReturnValue(t, f)` | `t: (A)R`, `f: (R)S` | `(A)S` |
| `filterArguments(t, 0, f)` | `t: (A,B)R`, `f: (X)A` | `(X,B)R` |
| `collectArguments(t, 0, f)` | `t: (A,B)R`, `f: (X,Y)A` | `(X,Y,B)R` |
| `guardWithTest(test, yes, no)` | `test: (A)boolean`, `yes/no: (A)R` | `(A)R` |
| `insertArguments(t, 1, b)` | `t: (A,B)R`, `b` compatible with `B` | `(A)R` |
| `bindTo(a)` | `t: (A,B)R`, `A` is a reference | `(B)R` |
| `dropArguments(t, 0, X.class)` | `t: (A)R` | `(X,A)R`, `X` is ignored |
| `permuteArguments(t, newType, reorder)` | `t: (A,B)R` | According to `newType` and valid position mapping |
| `asType(newType)` | `t: (A)R` | `newType` if the adapter can convert types |
| `filterReturnValue(t, f)` with `t: (A)void` | `f: ()S` | `(A)S`; special branch for `void` |

**Important point:** `filterArguments` and `collectArguments` can both feed a filter into a target, but the number of parameters of the new handle is determined differently. `filterArguments` replaces **the type of one slot** corresponding to the filter's result; `collectArguments` also replaces one slot, but can **expand into multiple inputs** from the filter, or insert a side effect in some forms with a `void`-returning filter. Therefore, always read the signature after combining.

These APIs usually throw `IllegalArgumentException` at the time of *creating* the handle if the type/position is invalid. `invokeExact` throws `WrongMethodTypeException` at *invocation* time if the call site signature does not match `type()`. These are two different error detection times.

## 4. filterReturnValue: Building a Path from the Previous Step's Output

If `normalize` has `(String)String` and `parse` has `(String)int`:

~~~java
MethodHandle normalizedNumber =
        MethodHandles.filterReturnValue(normalize, parse);
// normalizedNumber.type(): (String)int
~~~

In terms of values, `normalize` runs first; the `String` result is passed into `parse`; the final `int` result becomes the result of the new handle. Using `filterReturnValue` is valid because the parameter of `parse` matches **the return type of `normalize`**. If `parse` required `int` instead of `String`, this combinator could not chain them directly.

Continuing, if `classify` has type `(int)String`:

~~~java
MethodHandle pipeline =
        MethodHandles.filterReturnValue(normalizedNumber, classify);
// pipeline.type(): (String)String
~~~

The transformation can be read as:

~~~text
normalize       : (String)String
parse           : (String)int
normalizedNumber: (String)int
classify        : (int)String
pipeline        : (String)String
~~~

Here the final value is computed **when invoked**; the combinator does not test-process the input upon creation. If `parse` receives an invalid string, `NumberFormatException` still occurs at pipeline execution time.

**For targets returning `void`:** the post-processing filter used with `filterReturnValue` must be a filter with no parameters receiving the target's result. Do not assume every target always provides a value to the filter.

## 5. filterArguments and collectArguments: Input Pre-processing

Suppose `target` has type `(int)String` and `parse` has type `(String)int`. We need to use a `String` to produce the `int` argument:

~~~java
MethodHandle byFilter =
        MethodHandles.filterArguments(target, 0, parse);
// byFilter.type(): (String)String
~~~

`pos = 0` means the filter replaces the type of **the first parameter** of target. Previously the caller passed `int`; now the caller passes `String`, the filter converts it to `int`, and then target receives the converted value.

If we want a filter that takes **two** parameters to compute one argument of target, use `collectArguments`. For example, target has type `(int,int)int` (taking *subtotal* and *shipping*), and filter has type `(int,int)int` (computing *subtotal* from unit price and quantity). Combining them:

~~~java
MethodHandle withSubtotal =
        MethodHandles.collectArguments(target, 0, subtotal);
// withSubtotal.type(): (int,int,int)int
~~~

The three new parameters are `(unitPrice, quantity, shipping)`. The first two parameters are passed into `subtotal`, the return value is placed at slot `0` of target, and `shipping` remains unchanged. Then if we fix the shipping fee:

~~~java
MethodHandle fixedShipping =
        MethodHandles.insertArguments(withSubtotal, 2, 5);
// fixedShipping.type(): (int,int)int
~~~

`insertArguments` fixes the parameter at index `2` to `5`; the new handle only takes unit price and quantity. The signature changes **immediately when the new handle is created**, not on the first invocation.

### Points to Note When There Are Multiple Filters

`filterArguments(target, pos, filters...)` attaches the filters sequentially to consecutive parameters of target (starting at `pos`). The filters must return the exact type of the corresponding slot. With `collectArguments`, one filter and one position are specified; the filter's parameter list is **substituted into** that position. In a long pipeline, write out the signature of each operation before chaining so you do not mix up the number and order of arguments.

## 6. guardWithTest: Branching While Preserving the Same Type Contract

`MethodHandles.guardWithTest(test, target, fallback)` creates a handle that chooses a path based on a `boolean` value:

~~~text
test      : (int)boolean
target    : (int)String   [if true]
fallback  : (int)String   [if false]
------------------------------------
guard     : (int)String
~~~

In this example, the three handles share the input parameter type `int`; test returns `boolean`, and both branches return `String`. The resulting `guard` has `(int)String`. We can place `guard` after parse to form a `(String)String` pipeline.

If test is `(String)boolean` while target/fallback are `(int)String`, we cannot expect `guardWithTest` to parse the input automatically: **we must proactively adapt or chain a type-conversion step**. Test and branches must have compatible signatures according to the combinator's rules, not just similar method names.

An advantage of `guardWithTest` is that on each invocation it only executes **the test and the chosen branch**, rather than evaluating both branches and then taking one result. If the test or branch throws an exception, the exception still propagates through the pipeline just like normal handle invocations.

## 7. A Helper to Check MethodType After **Each** Step

Do not just call `System.out.println(handle.type())` manually. When building a large pipeline, you can verify it with a small function:

~~~java
static void check(String stage, MethodHandle handle, MethodType expected) {
    MethodType actual = handle.type();
    if (!actual.equals(expected)) {
        throw new AssertionError(
                stage + ": expected " + expected + ", actual " + actual);
    }
    System.out.println(stage + " -> " + actual);
}
~~~

This is an **illustrative method** that must be placed in a class with `import java.lang.invoke.*`. `MethodType.equals` checks **both the return type and the entire parameter list**, unlike checking only `parameterCount()`. Throwing `AssertionError` in this lesson makes errors appear clearly, even when the program runs without the `-ea` flag enabled.

Usage:

~~~java
MethodType expected =
        MethodType.methodType(int.class, String.class);
check("normalize+parse", normalizedNumber, expected);
~~~

If the expected signature is wrong, the program stops **before the invocation that processes real data** and states the stage name along with expected/actual. In a production library, `AssertionError` can be replaced with an appropriate configuration exception or automated unit tests; what matters is ensuring pipeline configuration errors are caught early.

When you also need to log the JVM descriptor form:

~~~java
System.out.println(expected.toMethodDescriptorString());
// (Ljava/lang/String;)I
~~~

`MethodType.toString()` serves human-readable signature inspection, while `toMethodDescriptorString()` gives the JVM descriptor syntax; in both cases, **do not parse strings as the source of truth for types**. Use the `MethodType` object and its APIs directly.

## 8. Complete Example 1: normalize → parse → guard → decorate

Create the file **TypedPipelineDemo.java**:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class TypedPipelineDemo {
    public static String normalize(String raw) {
        return raw.strip().replace("_", "");
    }

    public static int parse(String text) {
        return Integer.parseInt(text);
    }

    public static boolean isLarge(int number) {
        return number >= 1000;
    }

    public static String largeText(int number) {
        return "large:" + number;
    }

    public static String smallText(int number) {
        return "small:" + number;
    }

    public static String decorate(String value) {
        return "result=" + value;
    }

    static void check(String stage, MethodHandle handle, MethodType expected) {
        MethodType actual = handle.type();
        if (!actual.equals(expected)) {
            throw new AssertionError(
                    stage + ": expected " + expected + ", actual " + actual);
        }
        System.out.println(stage + " -> " + actual);
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        MethodType stringToString =
                MethodType.methodType(String.class, String.class);
        MethodType stringToInt =
                MethodType.methodType(int.class, String.class);
        MethodType intToBoolean =
                MethodType.methodType(boolean.class, int.class);
        MethodType intToString =
                MethodType.methodType(String.class, int.class);

        MethodHandle normalize = lookup.findStatic(
                TypedPipelineDemo.class, "normalize", stringToString);
        MethodHandle parse = lookup.findStatic(
                TypedPipelineDemo.class, "parse", stringToInt);
        MethodHandle test = lookup.findStatic(
                TypedPipelineDemo.class, "isLarge", intToBoolean);
        MethodHandle large = lookup.findStatic(
                TypedPipelineDemo.class, "largeText", intToString);
        MethodHandle small = lookup.findStatic(
                TypedPipelineDemo.class, "smallText", intToString);
        MethodHandle decorate = lookup.findStatic(
                TypedPipelineDemo.class, "decorate", stringToString);

        check("normalize", normalize, stringToString);
        check("parse", parse, stringToInt);
        check("test", test, intToBoolean);

        MethodHandle chooser =
                MethodHandles.guardWithTest(test, large, small);
        check("chooser", chooser, intToString);

        MethodHandle normalizedNumber =
                MethodHandles.filterReturnValue(normalize, parse);
        check("normalize+parse", normalizedNumber, stringToInt);

        MethodHandle classified =
                MethodHandles.filterReturnValue(normalizedNumber, chooser);
        check("classified", classified, stringToString);

        // Same meaning, written in the argument pre-processing style:
        MethodHandle alternate =
                MethodHandles.filterArguments(chooser, 0, normalizedNumber);
        check("alternate", alternate, stringToString);

        MethodHandle labeled =
                MethodHandles.filterReturnValue(classified, decorate);
        check("labeled", labeled, stringToString);

        MethodHandle adapted = labeled.asType(
                MethodType.methodType(Object.class, Object.class));
        check("adapted", adapted,
                MethodType.methodType(Object.class, Object.class));

        String first = (String) labeled.invokeExact(" 1_240 ");
        String second = (String) labeled.invokeExact(" 9 ");
        String same = (String) alternate.invokeExact(" 1_240 ");
        Object boxed = adapted.invokeExact((Object) " 9 ");

        System.out.println("case-1 -> " + first);
        System.out.println("case-2 -> " + second);
        System.out.println("alternate call -> " + same);
        System.out.println("adapted call -> " + boxed);
    }
}
~~~

Compile/run from the directory containing the file, using JDK 17 or higher:

~~~bash
javac TypedPipelineDemo.java
java TypedPipelineDemo
~~~

Stdout:

~~~text
normalize -> (String)String
parse -> (String)int
test -> (int)boolean
chooser -> (int)String
normalize+parse -> (String)int
classified -> (String)String
alternate -> (String)String
labeled -> (String)String
adapted -> (Object)Object
case-1 -> result=large:1240
case-2 -> result=small:9
alternate call -> large:1240
adapted call -> result=small:9
~~~

### Reading the Result at Each Milestone

**Milestone 1 — normalization:** `normalize.type()` is `(String)String`. Input `" 1_240 "` is stripped via `strip()` to `"1_240"` and `replace("_", "")` to `"1240"`.

**Milestone 2 — parse:** `parse.type()` is `(String)int`. When combining `filterReturnValue(normalize, parse)`, the result becomes `(String)int`: the caller still passes a string, but receives an integer.

**Milestone 3 — branching:** `guardWithTest(test, large, small)` takes an `int` and returns a `String`, with type `(int)String`. The value `1240` selects the `largeText` branch, `9` selects `smallText`.

**Milestone 4 — main path:** `filterReturnValue(normalizedNumber, chooser)` chains `(String)int` into `(int)String`, producing `(String)String`. The caller's input is still a `String`; internal invocations occur in the configured order.

**Milestone 5 — equivalent path:** `filterArguments(chooser, 0, normalizedNumber)` also produces `(String)String` because it uses the filter's result as the first `int` parameter of `chooser`. Both paths express the same transformation in this case, but their parameter/connection characteristics differ.

**Milestone 6 — decoration:** `filterReturnValue(classified, decorate)` prepends `"result="` and still keeps `(String)String`.

**Milestone 7 — adapter:** `asType((Object)Object)` creates a handle with signature `(Object)Object`. `invokeExact((Object) " 9 ")` is declared to take `Object` and the result is assigned to an `Object` variable, so the call site matches the adapted handle. Inside, the adapter checks/casts the input to `String` and outputs the `String` result as `Object`.

Note **value lifecycle differs from handle lifecycle**: all combinators above only build the "invocation network"; normalization, parsing, testing, and formatting **actually run** when calling `labeled.invokeExact(...)`, not immediately during pipeline construction.

## 9. Complete Example 2: collectArguments, insertArguments, permuteArguments, dropArguments

The second pipeline simulates an invoice problem: from **unit price, quantity** compute the subtotal, add a **fixed shipping fee**, and then create a receipt string associated with the buyer's name. We will reorder parameters and add an ignored context parameter to see how `MethodType` changes.

Create the file **ReceiptPipelineDemo.java**:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class ReceiptPipelineDemo {
    public static int subtotal(int unitPrice, int quantity) {
        return unitPrice * quantity;
    }

    public static int addShipping(int sub, int shipping) {
        return sub + shipping;
    }

    public static String receipt(String buyer, int total) {
        return buyer + ": " + total;
    }

    static void check(String stage, MethodHandle handle, MethodType expected) {
        MethodType actual = handle.type();
        if (!actual.equals(expected)) {
            throw new AssertionError(
                    stage + ": expected " + expected + ", actual " + actual);
        }
        System.out.println(stage + " -> " + actual);
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType ints =
                MethodType.methodType(int.class, int.class, int.class);

        MethodHandle subtotal = lookup.findStatic(
                ReceiptPipelineDemo.class, "subtotal", ints);
        MethodHandle addShipping = lookup.findStatic(
                ReceiptPipelineDemo.class, "addShipping", ints);
        MethodHandle receipt = lookup.findStatic(
                ReceiptPipelineDemo.class, "receipt",
                MethodType.methodType(
                        String.class, String.class, int.class));

        check("subtotal", subtotal, ints);
        check("addShipping", addShipping, ints);

        // addShipping(subtotal, shipping):
        // subtotal is computed from (unitPrice, quantity).
        MethodHandle collected =
                MethodHandles.collectArguments(addShipping, 0, subtotal);
        check("collected", collected,
                MethodType.methodType(
                        int.class, int.class, int.class, int.class));

        // Fix shipping at the third parameter.
        MethodHandle fixedShipping =
                MethodHandles.insertArguments(collected, 2, 5);
        check("fixedShipping", fixedShipping, ints);

        // receipt(buyer, fixedShipping(unitPrice, quantity))
        MethodHandle pipeline =
                MethodHandles.collectArguments(receipt, 1, fixedShipping);
        check("pipeline", pipeline,
                MethodType.methodType(
                        String.class,
                        String.class, int.class, int.class));

        // Change from (buyer, unitPrice, quantity) to
        // (unitPrice, quantity, buyer).
        MethodHandle reordered = MethodHandles.permuteArguments(
                pipeline,
                MethodType.methodType(
                        String.class,
                        int.class, int.class, String.class),
                2, 0, 1);
        check("reordered", reordered,
                MethodType.methodType(
                        String.class,
                        int.class, int.class, String.class));

        // Add an ignored context parameter at index 0.
        MethodHandle withContext = MethodHandles.dropArguments(
                reordered, 0, String.class);
        check("withContext", withContext,
                MethodType.methodType(
                        String.class,
                        String.class, int.class, int.class, String.class));

        String first = (String) pipeline.invokeExact("Lan", 7, 3);
        String second = (String) reordered.invokeExact(7, 3, "Minh");
        String third = (String) withContext.invokeExact(
                "request-42", 7, 3, "Hoa");

        System.out.println("direct -> " + first);
        System.out.println("reordered call -> " + second);
        System.out.println("context call -> " + third);
    }
}
~~~

~~~bash
javac ReceiptPipelineDemo.java
java ReceiptPipelineDemo
~~~

Stdout:

~~~text
subtotal -> (int,int)int
addShipping -> (int,int)int
collected -> (int,int,int)int
fixedShipping -> (int,int)int
pipeline -> (String,int,int)String
reordered -> (int,int,String)String
withContext -> (String,int,int,String)String
direct -> Lan: 26
reordered call -> Minh: 26
context call -> Hoa: 26
~~~

### Checking the Reason for Each Signature

1. **`subtotal`** has `(int,int)int`: unit price `7` multiplied by quantity `3` yields `21`.
2. **`addShipping`** has `(int,int)int`: takes *subtotal* and *shipping*, returns total.
3. **`collectArguments(addShipping, 0, subtotal)`** substitutes the result of `subtotal(unitPrice,quantity)` into the `sub` parameter of `addShipping`. Because the filter takes two `int` parameters, the new handle takes three parameters `(unitPrice, quantity, shipping)`, so the type is `(int,int,int)int`.
4. **`insertArguments(collected, 2, 5)`** binds `shipping=5` at index 2. The new handle has `(int,int)int`, no longer requiring the caller to pass shipping.
5. **`collectArguments(receipt, 1, fixedShipping)`** substitutes the computed amount into the second parameter (index 1) of `receipt(String buyer,int total)`, creating `(String,int,int)String`.
6. **`permuteArguments(...)`** changes the argument order to `(int,int,String)String`. The mapping array `2,0,1` means: the old parameter `buyer` is taken from new position `2`, `unitPrice` from new position `0`, and `quantity` from new position `1`. This is an **old slot → new slot mapping**, not an arbitrarily numbered list of fields.
7. **`dropArguments(reordered, 0, String.class)`** inserts an additional `String context` at the front without **passing it to the original operation**. The new handle has `(String,int,int,String)String`; the context name does not affect the billing result.
8. All three calls compute `7 × 3 + 5 = 26`, but each handle has a different input signature.

**Maintenance note:** `dropArguments` does not "automatically log" or "automatically validate" the new parameter. It **ignores** that value; if you need to check the context, design a filter/guard that actually performs the check. Similarly, `permuteArguments` does not convert types: positions in the new signature must be compatible with the selected position of the target, and duplicate mappings or dropping sources can occur under the API contract when valid.

## 10. invokeExact and invoke: Where the Pipeline Meets the Call Site

Suppose the final pipeline has `type() == (String)String`. A valid call:

~~~java
String output = (String) pipeline.invokeExact(" 7 ");
~~~

This is a `(String)String` call site. The return type is also part of the signature, not just the parameter types. The following call compiles but fails at runtime:

~~~java
Object wrong = pipeline.invokeExact(" 7 ");
~~~

This call site requests `(String)Object`; `invokeExact` **does not automatically treat `String` and `Object` as equivalent** and can throw `WrongMethodTypeException`. Conversely, `invoke` attempts to adapt types according to `asType` rules within the supported scope.

To see the difference clearly, consider two handles:

~~~java
// pipeline has type (String)String.
MethodHandle generic = pipeline.asType(
        MethodType.methodType(Object.class, Object.class));
// generic has type (Object)Object.

Object result = generic.invokeExact((Object) " 7 ");
~~~

`asType` creates a new adapter; the **original** signature of `pipeline` does not change. `generic.invokeExact` now has a `(Object)Object` call site and matches the adapter's signature. When the actual value is a `String`, the reference conversion can succeed. If an object that cannot be cast to `String` is passed, a `ClassCastException` will occur inside the adapter.

Exceptions to distinguish:

- **`IllegalArgumentException` when combining:** wrong parameter position, incompatible input/output types between filter and target, or invalid guard branch types.
- **`WrongMethodTypeException` on invokeExact:** call site signature does not match `handle.type()`; with `invoke`, this can occur if the required type conversion cannot be created.
- **`ClassCastException` when running an adapter:** an actual reference value does not match the target type.
- **Business exceptions from the target method:** for example `NumberFormatException` when parsing an invalid string, propagated through the pipeline without being automatically wrapped in `InvocationTargetException` just because method handles are used.

Not every adapter avoids boxing/unboxing or conversion; you need to look at the signatures of both handles before and after `asType`. A pipeline using primitive `int` in the middle can keep primitives along the entire path if combinators match types precisely, instead of forcing every step to `Object`.

## 11. Catching Errors When **Creating** the Pipeline, Not Waiting Until Processing Data

A good implementation principle is to treat pipeline creation time as a **configuration testing** phase. For example:

~~~java
MethodHandle wrongFilter = /* a (int)String handle */;
MethodHandle target = /* a (String)int handle */;
// filterReturnValue(target, wrongFilter) is valid:
// target returns int, wrongFilter takes int.
~~~

The two declaration lines above are **conceptual illustrative code**, not standalone compilable code. If `wrongFilter` is replaced with a `(long)String` handle, combining directly with `filterReturnValue` will fail because target's `int` output does not match the filter's `long` input as required by the combinator. When you genuinely want to widen `int` to `long`, add a valid adapter or fix the signature design, do not mistakenly force an incompatible method.

The **type-first** approach:

1. Sketch the input/output of each step, for example `(String)String`, `(String)int`, `(int)String`.
2. Look up handles with `Lookup` using the exact `MethodType` of the declared method. For `findVirtual`, remember the receiver is prepended to the `type()` of the looked-up handle.
3. After **each** `filterReturnValue`, `filterArguments`, `collectArguments`, `guardWithTest`, `insertArguments`, `permuteArguments`..., call `type()`.
4. Compare with an expected `MethodType`; you should check count, order, parameter classes, and return type, not just log the result.
5. Only when all signature checks pass should you call `invokeExact` on the final pipeline with the right call site expression.
6. Also test valid values, invalid values, `null`, overflow, and target exceptions according to business requirements.

**Do not use `MethodType.toString()` to parse back into types**: you may encounter inner classes, arrays, same class name with different class loaders, or erased generics. `MethodType` and `Class<?>` objects are more accurate information.

### Detecting Information Loss and Side Effects

A combinator can **ignore parameters** (e.g., `dropArguments`), **reorder inputs** (`permuteArguments`), **fix a value** (`insertArguments`), or **execute only one branch** (`guardWithTest`). Checking signatures is a **necessary condition**, but not a **sufficient condition** to guarantee correct business logic. You need unit tests for binding at the right position, execution order, chosen branch, and whether context data is used or accidentally ignored.

## 12. Some Advanced Combinators in Pipelines

After mastering the basic operations, Java provides many more tools. The common point remains **compute the new signature, check `type()`, then test values**:

| API | Purpose | What to check before using |
| --- | --- | --- |
| `foldArguments` | Computes the result of a combiner and passes it to target (or performs a side effect if combiner returns `void`) | Parameter order and number of forwarded values; easy to confuse with `collectArguments` |
| `filterReturnValue` | Post-processes target's result | Target return type and filter input type |
| `filterArguments` | Pre-processes individual target parameters | `pos`, each filter, filter's result type |
| `collectArguments` | Computes one target parameter using a multi-parameter filter | `pos`, new parameter list, and target slot |
| `guardWithTest` | Chooses between two branches with compatible signatures | Test must return boolean; chosen branch does not allow arbitrary new types |
| `catchException` | Catches a matching exception type and transfers to a handler | Exception class, signatures of handler and target |
| `tryFinally` | Ensures a cleanup handle runs when target finishes | Cleanup signature and how result/exception is forwarded |
| `filterArguments`/`filterReturnValue` combined with `asType` | Adapts inputs and outputs when needed | Which conversions are valid, where boxing/casts occur |
| `dropArguments` | Accepts extra parameters without using them | Avoid accidentally ignoring important data |
| `permuteArguments` | Reorders or reorganizes the input list | Size and type of every mapped position |

Advanced APIs have their own signature rules; the table only indicates **roles**, not a substitute for reading the detailed contract when implementing. When a chain becomes hard to manage, splitting it into multiple meaningfully named intermediate handles is easier to review than a deeply nested `MethodHandles.*` expression.

## 13. Designing Safe and Maintainable Pipelines

### A. Store Both the Handle and the Expected Type in the Design

If a pipeline is a long-lived configuration component, treat `MethodType` as an **execution schema**. For example, if a business flow always requires `(String)String`, then after completing all steps, assert `pipeline.type().equals(MethodType.methodType(String.class,String.class))`.

Handles are immutable in the sense that `asType`/combinators return a **new handle** without modifying the original handle. This helps store each step for inspection, while also allowing validated pipelines to be cached. However, values or receivers **bound inside** a handle may be mutable objects; handle immutability does not make the target thread-safe.

### B. Access Rights Still Belong to Lookup

`findStatic`/`findVirtual` steps and operations creating direct handles use the privileges of `MethodHandles.Lookup`. Combinators **do not grant new privileges**; they transform how an already-created handle is invoked. When integrating frameworks/modules, you must handle package exports/opens and access boundaries properly. Do not distribute handles carrying sensitive privileges to untrusted code.

### C. Avoid Automatically Converting Every Type to Object

Using `(Object)Object` for all steps looks flexible, but loses the strong signal of `MethodType`, introduces casts, boxing/unboxing, and pushes errors to runtime. If the pipeline has integer calculations, keep `int` in the appropriate segments. Only use `asType` when there is a clear reason, and check the adapter before invoking.

### D. Observe Errors at the Right Layer

- **Handle lookup errors**: wrong name/signature or missing access rights, usually involving `NoSuchMethodException`/`IllegalAccessException`.
- **Pipeline creation errors**: type or position mismatch in a combinator; usually `IllegalArgumentException`.
- **Pipeline invocation errors**: `WrongMethodTypeException` due to call-site signature not matching the handle.
- **Business data errors**: NumberFormatException, null, division by zero, or errors from the target method.

Keeping the stage name in type-check messages will significantly reduce debugging effort. Using `main throws Throwable` in examples is to illustrate the broad signature of `invokeExact`/`invoke`; in real services, handle exceptions accurately according to context.

### E. Optimize After Verifying Correctness

Look up handles and create adapters during initialization, then **reuse the pipeline** when appropriate. The JIT can optimize stable MethodHandle chains well, but actual performance depends on the JVM, call site stability, combinators, boxing, data, and how it is benchmarked. Do not conclude that a multi-combinator pipeline is always faster than direct method calls or Reflection. If performance matters, measure with the same workload, warmup, and realistic load conditions.

## 14. Common Errors When Checking Typed Pipelines

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `filterReturnValue` fails immediately at creation | Target's return type does not match filter's parameter type | Print `target.type()` and `filter.type()`; fix the type or add an intentional adapter |
| `filterArguments` reports an error | Wrong index, filter does not take the right input or returns wrong slot type | Cross-check `pos` and each `MethodType` |
| `collectArguments` creates more parameters than expected | Multi-parameter filter is expanded into target's parameter list | Rewrite the new signature before combining, check `parameterCount()` |
| `guardWithTest` cannot create handle | Test/target/fallback have incompatible types | Test returns boolean, branches share compatible signature |
| `permuteArguments` has wrong order | Misread the reorder array | Map each old target parameter to a new handle parameter position; unit test the order |
| `dropArguments` makes context data have no effect | New parameter is only accepted and ignored | Use a filter/guard if you want to validate or use context |
| `insertArguments` binds the wrong value | Indices changed after previous transformations | Call `type()` before each bind, name each new handle |
| `invokeExact` throws `WrongMethodTypeException` despite right arguments | Call site return type is inferred differently, or primitive mismatch | Cast/assign the right type and check the full return type |
| `invoke`/`asType` throws `ClassCastException` | Actual Object value cannot be cast to target reference type | Constrain input or change adapter design |
| Code works with `String` but breaks on null | Step calling `strip()` or parse does not accept null | Define null policy before building pipeline |
| Logged signature is right but logic is wrong | Types do not prove right processing order or right bound values | Test inputs/outputs and side effects of each stage |
| Generic signature mistaken for MethodType | `MethodType` does not store `List<String>` after erasure | When generic metadata is needed, use the appropriate Reflection API |

## 15. Self-Check Exercises (with Solutions)

**Exercise 1.** Given `normalize: (String)String` and `parse: (String)int`, what is the type of applying `filterReturnValue(normalize, parse)`?  
**Solution:** `(String)int`. The pipeline takes normalize's String input and returns parse's int.

**Exercise 2.** Given `target: (int)String`, `filter: (String)int`; write the pre-processing combination and the resulting type.  
**Solution:** `MethodHandles.filterArguments(target, 0, filter)` has type `(String)String`.

**Exercise 3.** Given `target: (int,int)int` and `filter: (int,int)int`, how many parameters does `collectArguments(target, 0, filter)` have?  
**Solution:** Three parameters, type `(int,int,int)int`. Two ints are used as filter inputs, and the remaining int is target's second parameter.

**Exercise 4.** To convert `(int,int,int)int` into `(int,int)int` by fixing the third value to `5`, what do you use?  
**Solution:** `MethodHandles.insertArguments(handle, 2, 5)`. Indices are counted on `handle.type()` **at the time of transformation**, not the initial signature before all adapters.

**Exercise 5.** Why does `guardWithTest(test, yes, no)` not automatically convert a String input into an int?  
**Solution:** The combinator checks signature compatibility; it does not automatically run `Integer.parseInt`. You must chain a `String → int` conversion handle at the right position before the guard.

**Exercise 6.** Pipeline has `(String)String`; is `Object result = pipeline.invokeExact("A");` guaranteed to be valid?  
**Solution:** No. The call site requests an `Object` return, which does not match the handle's `String` return; it may throw `WrongMethodTypeException`. Use `String result = (String) pipeline.invokeExact("A");`.

**Exercise 7.** What is `dropArguments(target, 0, String.class)` adding the `String context` input for?  
**Solution:** Allows the caller to pass an extra `context` parameter that target does not use. It cannot be used as a validate/log operation unless another stage performs that work.

**Exercise 8.** Has the statement `MethodType t = pipeline.type().changeReturnType(Object.class);` modified the pipeline?  
**Solution:** Not yet. It only creates a new `MethodType`. To adapt the handle, you must build an adapter such as `pipeline.asType(t)` if valid.

**Exercise 9.** Why is `MethodType.equals` more reliable than just checking `parameterCount()`?  
**Solution:** Two handles with the same parameter count can still differ in **parameter order/types** or **return type**. `equals` compares the entire signature.

**Exercise 10.** Both `filterReturnValue` and `filterArguments` can produce `(String)String` in the first example, so are they equivalent in all cases?  
**Solution:** No. One chains onto **target's result**, the other filters **target's parameter**. They only express the corresponding transformation in the chosen context; order, parameter count, and side effects may differ in a general pipeline.

## 16. Summary and Short Checklist

- **Every MethodHandle always has a current `MethodType`.** After *each combination*, query `handle.type()` again, because the new handle's type can differ completely from the initial signature.
- **Design by signature before writing combinators:** sketch the input/output flow, locate connection points, and check where receivers, primitives, and branches are needed.
- **Use the right tool:** `filterReturnValue` for post-processing; `filterArguments` for transforming input slots; `collectArguments` for computing one argument from multiple arguments; `guardWithTest` for boolean-based selection.
- **Track operations that change the parameter list:** `insertArguments` fixes, `dropArguments` adds but ignores, `permuteArguments` reorders, and `asType` adapts types when valid.
- **Check exact `MethodType.equals` at each stage**, not just by logging types and not just by testing the final result. For dynamic pipelines, asserting types at stage boundaries helps errors surface early.
- **`invokeExact` also checks the return type at the call site.** With primitives and reference types, do not assume the JVM will automatically convert `int`/`Integer` or `String`/`Object`.
- **Correct types do not guarantee correct logic:** unit test parameter order, chosen branch, exceptions, null, side effects, and receiver state.
- **Prefer keeping primitives when meaningful and cache stable pipelines.** Optimize through measurement, not by assuming every handle combination is always fast.

The sustainable workflow is **compute type → combine → check type → test values**, repeated after each transformation. When you keep the `MethodType` chain clear, `java.lang.invoke` pipelines will be much easier to verify, debug, and extend than chaining handles and only discovering errors at the final invocation.
