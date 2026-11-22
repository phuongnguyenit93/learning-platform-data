# 8.3 Reordering, Duplicating, or Dropping Argument Positions with permuteArguments

`MethodHandles.permuteArguments` is a Java MethodHandle *combinator*: it creates a **new handle** with an input parameter list of our choosing, then maps those parameters to the positions that the original handle (*target*) expects. Its three most important uses are **reordering**, **duplicating an argument**, and **dropping unnecessary input arguments**. As a result, an existing method can be adapted to a new call interface without rewriting the method body, creating manual wrapper classes, or repeatedly using Reflection.

This lesson belongs to topic **8. Method-Handle Combinators**. It explains the exact `reorder` index convention, target and new `MethodType`s, type validity conditions, invocation with `invokeExact`, as well as use cases for event routers, callback adapters, pipeline logic, and dynamic invokers. Examples use Java 17+.

**After this lesson, you will:**

- Be able to read `target.type()` and `newType`, and design the correct `reorder` mapping.
- Distinguish between “the inputs of the new handle” and “the arguments that the target receives”.
- Use the same mechanism for swapping positions, duplicating positions, and dropping unused positions.
- Identify mapping array length errors, out-of-bounds indices, and mismatched parameter or return types.
- Know when to use `permuteArguments`, `dropArguments`, `insertArguments`, `filterArguments`, or `asType` to chain processing steps.

## 1. Signature and Data Model

JDK 17 API:

```java
public static MethodHandle permuteArguments(
        MethodHandle target, MethodType newType, int... reorder)
```

This is a **reference signature**, not a standalone Java program. The three parameters mean:

| Parameter | Role |
| --- | --- |
| `target` | The original handle that will be executed last; has type `target.type()` |
| `newType` | The full type (parameters and return type) that **the returned new handle** must have |
| `reorder` | An index array indicating **which position in the new handle's inputs** each parameter of `target` is taken from |

Let:

- **Incoming**: the parameter list that *the caller of the new handle* passes in, described by `newType`. Numbered from `0`.
- **Outgoing**: the parameter list actually forwarded to `target`, described by `target.type()`. Also numbered from `0`.

The central rule is:

```text
targetArgument[i] = incomingArgument[reorder[i]]
i = 0, 1, ..., target.type().parameterCount() - 1
```

The `=` sign here describes value mapping, not an assignment into a concrete Java array that the learner must create. **The index `i` belongs to a parameter of target**, while **the value `reorder[i]` points to a position in the input list of the new handle**.

The length of `reorder` must **equal the number of parameters of target**, not the number of parameters of `newType`:

```text
reorder.length == target.type().parameterCount()
0 <= reorder[i] < newType.parameterCount()
```

In addition:

- `newType.returnType() == target.type().returnType()`.
- For each position `i` of target: `newType.parameterType(reorder[i]) == target.type().parameterType(i)`.
- The `==` sign between `Class<?>` objects here represents **the exact same type**, including primitives, interfaces, arrays, and classes; it does not automatically convert to a supertype or boxed type.
- For input positions not mentioned in `reorder`, the types can be anything according to `newType`; target does not see them.
- The resulting handle has `type()` **exactly equal to `newType`**. The original handle is not modified.

To understand the mapping, always write down the parameter lists of target and newType first and then fill in each `reorder[i]`, instead of looking at the index array and guessing.

## 2. Reordering Arguments: Swapping Positions

Suppose we have the method:

```java
static String render(String left, int amount, String right) {
    return left + ":" + amount + ":" + right;
}
```

This declaration snippet is illustrative. The original handle has type:

```text
target.type() = (String,int,String)String

Target receives: [left:String, amount:int, right:String]
Position:             0           1           2
```

The new calling system provides the order `(String left, String right, int amount)`. We want:

```text
newType = (String,String,int)String

Incoming:      [left:String, right:String, amount:int]
Position:            0             1            2

Target position 0 (left:String)   <- incoming position 0
Target position 1 (amount:int)    <- incoming position 2
Target position 2 (right:String)  <- incoming position 1

reorder = [0, 2, 1]
```

Thus, the expression to create the adapter is:

```java
MethodHandle adapted = MethodHandles.permuteArguments(
        target,
        MethodType.methodType(String.class,
                String.class, String.class, int.class),
        0, 2, 1);
```

This is an illustrative snippet assuming `target` has already been looked up for the `render` method. The new handle has type `(String,String,int)String`. When calling `adapted("left", "right", 7)`, target receives `("left", 7, "right")` and returns `"left:7:right"`.

**Verification table by each target position:**

| Target's `i` | Target needs type | `reorder[i]` | Corresponding new incoming |
| --- | --- | --- | --- |
| `0` | `String` | `0` | `left` at new index 0 |
| `1` | `int` | `2` | `amount` at new index 2 |
| `2` | `String` | `1` | `right` at new index 1 |

A simple swap with `subtract(int a, int b)` whose target has type `(int,int)int`: use the same `newType` and `reorder = [1,0]`. When calling the new handle with `(2,10)`, target actually receives `(10,2)`, so the result is `8` instead of `-8`.

## 3. Duplicating an Argument: Copying Positions, Not Objects

`reorder` is not required to be a mathematical *permutation* where each index appears once. Indices **are allowed to repeat**.

Suppose target computes `sum(int a, int b)` with type `(int,int)int`. We want the new handle to accept only **one `int`** and add that value to itself:

```text
newType:          (int)int
incoming index:     0

target input 0 = incoming[0]
target input 1 = incoming[0]

reorder = [0, 0]
```

```java
MethodHandle twice = MethodHandles.permuteArguments(
        sum,
        MethodType.methodType(int.class, int.class),
        0, 0);
```

When calling `twice(21)`, target receives `sum(21,21)` and returns `42`.

**Type condition:** both target positions wired to incoming index 0 must have the exact same type. You cannot use the same incoming `int` for one `int` target parameter and one `long` parameter, because `permuteArguments` **does not perform automatic widening**.

If the incoming argument is a **reference to a mutable object**, “duplicating” only reuses the same reference; it **does not clone** the object. A target method receiving two reference parameters will see both pointing to the exact same instance. For immutable data or primitives, this usually causes no issues; for mutable state, you need to understand aliasing and side effects.

## 4. Dropping One or More Input Positions

Target `identify(String name)` has type `(String)String`. The new call interface has type `(String,boolean,long)String`, but target only needs the name. We can create:

```java
MethodHandle adapter = MethodHandles.permuteArguments(
        identify,
        MethodType.methodType(String.class,
                String.class, boolean.class, long.class),
        0);
```

`reorder = [0]` because target only has one parameter and needs incoming index 0. Incoming index 1 (`boolean`) and index 2 (`long`) **do not appear** in `reorder`, so they are dropped. Calling the adapter with `("Ada", true, 99L)` will invoke target with `("Ada")`.

Important rules:

- `reorder` does not contain a special value like `-1` to represent “drop”.
- To drop incoming index `j`, simply **omit `j` from the reorder array**.
- Dropped incoming arguments **must still be passed to the new handle** because `newType` declares them. They cannot be omitted at the `invokeExact` call site.
- Argument expression evaluation still happens **before the call** according to Java semantics. Dropping a position does not eliminate side effects that occur when computing the expression passed to that position.
- A dropped argument can be of any valid Java type declared in `newType`, as long as the used positions preserve their exact types.

**Zero-parameter target case:** if target `fixed()` has type `()String`, `reorder` must be an **empty** array. Then newType can be `(int,String)String` and all inputs are dropped:

```java
MethodHandle ignored = MethodHandles.permuteArguments(
        fixed,
        MethodType.methodType(String.class, int.class, String.class));
```

Having no `reorder` indices after `newType` is valid because the varargs parameter `int... reorder` accepts an empty list. The result still only calls `fixed()` once.

## 5. All Three Operations Can Be Combined in the Same Mapping

Take a target of type `(String,String)String`, executing `prefix(a,b)` which returns `a + "/" + b`. We want the new handle to accept `(long,String,boolean,String)String`, where target uses:

- target argument 0 ← incoming argument 3: the last string.
- target argument 1 ← incoming argument 1: the middle string.
- incoming arguments 0 (`long`) and 2 (`boolean`) are dropped.

`reorder = [3,1]` creates the exact adapter. If newType is `(String)String` and `reorder = [0,0]`, the same target is used to **duplicate** the input into `"x/x"`. You can simultaneously reorder, duplicate, and drop, as long as the type and count conditions are satisfied.

Application example: a legacy callback accepts `(String topic,String action)`, while the new router provides `(long timestamp,String action,boolean dryRun,String topic)`. `permuteArguments` replaces a manual wrapper class with the mapping `[3,1]` and returns a handle reporting the exact new type.

## 6. Complete Java 17+ Program: Swapping, Duplicating, Dropping, and Errors

Create the file **`PermuteArgumentsDemo.java`** with the following content:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class PermuteArgumentsDemo {
    public static String render(String left, int amount, String right) {
        return left + ":" + amount + ":" + right;
    }

    public static int sum(int a, int b) {
        return a + b;
    }

    public static int subtract(int a, int b) {
        return a - b;
    }

    public static String identify(String name) {
        return "id=" + name;
    }

    public static String fixed() {
        return "ready";
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodHandle render = lookup.findStatic(PermuteArgumentsDemo.class, "render",
                MethodType.methodType(String.class, String.class, int.class, String.class));
        MethodHandle reordered = MethodHandles.permuteArguments(render,
                MethodType.methodType(String.class, String.class, String.class, int.class),
                0, 2, 1);
        System.out.println("render original=" + render.type());
        System.out.println("render new=" + reordered.type());
        System.out.println("render=" + (String) reordered.invokeExact("left", "right", 7));

        MethodHandle sum = lookup.findStatic(PermuteArgumentsDemo.class, "sum",
                MethodType.methodType(int.class, int.class, int.class));
        MethodHandle twice = MethodHandles.permuteArguments(sum,
                MethodType.methodType(int.class, int.class), 0, 0);
        System.out.println("twice type=" + twice.type());
        System.out.println("twice=" + (int) twice.invokeExact(21));

        MethodHandle subtract = lookup.findStatic(PermuteArgumentsDemo.class, "subtract",
                MethodType.methodType(int.class, int.class, int.class));
        MethodHandle swapped = MethodHandles.permuteArguments(subtract,
                subtract.type(), 1, 0);
        System.out.println("subtract=" + (int) subtract.invokeExact(2, 10));
        System.out.println("swapped=" + (int) swapped.invokeExact(2, 10));

        MethodHandle identify = lookup.findStatic(PermuteArgumentsDemo.class, "identify",
                MethodType.methodType(String.class, String.class));
        MethodHandle ignored = MethodHandles.permuteArguments(identify,
                MethodType.methodType(String.class, String.class, boolean.class, long.class), 0);
        System.out.println("ignored type=" + ignored.type());
        System.out.println("ignored=" + (String) ignored.invokeExact("Ada", true, 99L));

        MethodHandle fixed = lookup.findStatic(PermuteArgumentsDemo.class, "fixed",
                MethodType.methodType(String.class));
        MethodHandle zero = MethodHandles.permuteArguments(fixed,
                MethodType.methodType(String.class, int.class, String.class));
        System.out.println("zero=" + (String) zero.invokeExact(3, "unused"));

        try {
            MethodHandles.permuteArguments(sum,
                    MethodType.methodType(int.class, long.class, int.class), 0, 1);
        } catch (IllegalArgumentException e) {
            System.out.println("type mismatch=" + e.getClass().getSimpleName());
        }
        try {
            MethodHandles.permuteArguments(sum,
                    MethodType.methodType(int.class, int.class), 0, 1);
        } catch (IllegalArgumentException e) {
            System.out.println("bad index=" + e.getClass().getSimpleName());
        }
        try {
            MethodHandles.permuteArguments(sum,
                    MethodType.methodType(int.class, int.class, int.class), 0);
        } catch (IllegalArgumentException e) {
            System.out.println("wrong length=" + e.getClass().getSimpleName());
        }
        try {
            MethodHandles.permuteArguments(sum,
                    MethodType.methodType(long.class, int.class, int.class), 0, 1);
        } catch (IllegalArgumentException e) {
            System.out.println("return mismatch=" + e.getClass().getSimpleName());
        }
    }
}
```

Using JDK 17 or newer, save with the exact filename (matching `public class`), compile, and run:

```bash
javac --release 17 PermuteArgumentsDemo.java
java PermuteArgumentsDemo
```

Full `stdout`, matching the program:

```text
render original=(String,int,String)String
render new=(String,String,int)String
render=left:7:right
twice type=(int)int
twice=42
subtract=-8
swapped=8
ignored type=(String,boolean,long)String
ignored=id=Ada
zero=ready
type mismatch=IllegalArgumentException
bad index=IllegalArgumentException
wrong length=IllegalArgumentException
return mismatch=IllegalArgumentException
```

The `render` lines show mapping `[0,2,1]`; `twice` tests `[0,0]`; `swapped` tests `[1,0]`; `ignored` keeps index 0 and drops the remaining indices. `zero` demonstrates that a `()String` target can be attached to an interface that accepts inputs without using them.

The last four exceptions all occur **when creating the adapter**, before target is invoked. This is structural validation of `permuteArguments`, not exceptions from the body of `sum`:

1. `type mismatch`: target needs `int` at position 0, but newType provides `long` at index 0.
2. `bad index`: target has two parameters; newType has one, but `reorder[1] == 1` exceeds the valid index range (only `0`).
3. `wrong length`: target has two parameters, but the mapping array only has one element.
4. `return mismatch`: target returns `int`, whereas newType declares returning `long`.

## 7. An Instance Method's Receiver Is Also a Handle Parameter

It is not only arguments in the method declaration that can be swapped: for a `MethodHandle` to an **instance method**, the receiver object sits at **index 0 in the handle's parameter list**. Therefore, you can also change the receiver's position using `permuteArguments`.

For example, the JDK has `StringBuilder.append(int)`. If looked up via:

```java
MethodHandle append = MethodHandles.lookup().findVirtual(
        StringBuilder.class, "append",
        MethodType.methodType(StringBuilder.class, int.class));
```

`append.type()` is `(StringBuilder,int)StringBuilder`, meaning the `StringBuilder` receiver comes first, then the `int` value. An adapter for the order `(int,StringBuilder)StringBuilder` uses `reorder=[1,0]`.

Complete program **`ReceiverRoutingDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class ReceiverRoutingDemo {
    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodHandle append = lookup.findVirtual(StringBuilder.class, "append",
                MethodType.methodType(StringBuilder.class, int.class));
        MethodHandle valueFirst = MethodHandles.permuteArguments(append,
                MethodType.methodType(StringBuilder.class, int.class, StringBuilder.class),
                1, 0);
        System.out.println("original=" + append.type());
        System.out.println("permuted=" + valueFirst.type());
        StringBuilder result = (StringBuilder) valueFirst.invokeExact(7, new StringBuilder("n="));
        System.out.println("result=" + result);

        MethodHandle prefix = lookup.findStatic(ReceiverRoutingDemo.class, "prefix",
                MethodType.methodType(String.class, String.class, String.class));
        MethodHandle duplicate = MethodHandles.permuteArguments(prefix,
                MethodType.methodType(String.class, String.class), 0, 0);
        System.out.println("duplicate=" + (String) duplicate.invokeExact("x"));
        MethodHandle route = MethodHandles.permuteArguments(prefix,
                MethodType.methodType(String.class, long.class, String.class,
                        boolean.class, String.class), 3, 1);
        System.out.println("route=" + (String) route.invokeExact(55L, "inner", true, "outer"));
    }

    public static String prefix(String a, String b) {
        return a + "/" + b;
    }
}
```

```bash
javac --release 17 ReceiverRoutingDemo.java
java ReceiverRoutingDemo
```

`stdout`:

```text
original=(StringBuilder,int)StringBuilder
permuted=(int,StringBuilder)StringBuilder
result=n=7
duplicate=x/x
route=outer/inner
```

Explanation:

- `valueFirst` has type `(int,StringBuilder)StringBuilder`. The caller provides the value `7` first, then a `StringBuilder`; target still receives the receiver in the first position after swapping.
- `duplicate` turns `prefix(a,b)` into a single-parameter callable, and both original parameters receive `"x"`.
- `route` accepts four new parameters, but only forwards incoming index 3 (`"outer"`) and 1 (`"inner"`) to target. It drops the timestamp `55L` and the flag `true`.

Note: `MethodType.methodType(StringBuilder.class, int.class, StringBuilder.class)` has `int` as the first parameter and `StringBuilder` as the second. The return type is still `StringBuilder`. `permuteArguments` does not create a new instance; it calls the exact original method, so the `StringBuilder` can be mutated just like any normal `append` call.

## 8. Exact Types Matter More Than Names and Intent

`permuteArguments` **does not perform conversions** on arguments or return values. Compatibility requires **identical** types on every edge of the mapping; unlike the conversions that can happen at a `MethodHandle.invoke` call site or via `asType`.

### 8.1. Primitive and Wrapper Types

| Target needs | New incoming used | Valid in `permuteArguments`? |
| --- | --- | --- |
| `int` | `int` | Yes |
| `int` | `long` | No |
| `int` | `Integer` | No |
| `String` | `String` | Yes |
| `Object` | `String` | No, even though `String` is a subtype of `Object` |
| `String[]` | `String[]` | Yes |
| `String[]` | `Object[]` | No |
| Target returns `int` | NewType returns `long` | No, even though Java has widening when needed |

To convert types, you can use `MethodHandle.asType` before or after the `permuteArguments` step, depending on the exact types needed at each edge. This requires you to determine the transformation order clearly: `permuteArguments` only does **routing**, while `asType` handles supported conversions.

For example, with the `twice` handle of type `(int)int` (from the first program), you can adapt it to `(Integer)Integer` after choosing the right mapping:

```java
MethodHandle boxed = twice.asType(
        MethodType.methodType(Integer.class, Integer.class));
Integer value = (Integer) boxed.invokeExact(Integer.valueOf(21));
System.out.println(value); // 42
```

This is an illustrative snippet depending on `twice` from the complete program. `asType` uses unboxing on the input and boxing on the result; `permuteArguments` itself does not provide these two conversions.

### 8.2. invokeExact Uses the Call-Site Type

`MethodHandle.invokeExact` requires the signature at the call site to match `handle.type()` **exactly**, including the return type. For instance, `reordered` has type `(String,String,int)String`:

```java
String ok = (String) reordered.invokeExact("left", "right", 7);
```

If you change the expected return type to `Object`, or pass `long` instead of `int`, the call may compile but will throw `WrongMethodTypeException` at runtime. `invoke` can adapt types within supported limits, whereas `invokeExact` does not adapt; neither changes the chosen `reorder` mapping.

`permuteArguments` returns a **fixed-arity handle**, even when the original target is a *varargs collector*. If a varargs interface is needed later, you must design an additional appropriate conversion step; do not assume the varargs flag of the old handle is preserved.

### 8.3. The Return Type Always Stays the Same

You can change the positions and count of **inputs** of the new handle using `newType` and `reorder`, but you cannot use `permuteArguments` to change the return type. For a target returning `int`, `newType` must return `int`. To discard the return value, use `MethodHandles.dropReturn` on supported JDKs; to adapt the return value via type conversion, look at `asType` or `filterReturnValue` with an appropriate filter.

## 9. Distinguishing from Related Combinators

| API | What it does | When to choose it |
| --- | --- | --- |
| `permuteArguments` | Selects incoming positions to feed into each target parameter; can reorder, duplicate, drop incoming args | Parameter shapes no longer have the same order, or an incoming arg needs to be duplicated |
| `dropArguments` | Adds “dummy” parameters at a position, ignoring them when calling target | Only need to insert unused inputs while preserving the relative order of old inputs |
| `insertArguments` | Binds fixed values to one or more parameters of target | Some arguments are known in advance, e.g., binding a fixed ID |
| `bindTo` | Binds an object to the first parameter of a handle | Commonly binding the receiver or a first input that is a reference |
| `filterArguments` | Passes one or more parameters through a filter before calling target | Need to **transform/preprocess values**, not just change positions |
| `filterReturnValue` | Filters/transforms the return value of target using another handle | Want to change the result without changing input routing |
| `asType` | Creates a type-converting adapter if supported by the JVM | Target/new caller needs boxing, casting, or valid primitive conversions |
| `asSpreader` / `asCollector` | Packs/unpacks an array into parameters when the contract matches | Need to convert between an array shape and a parameter list |

For example, when you **only** want to add a `long timestamp` argument before a target of type `(String)String`, you can use:

```java
MethodHandle withTimestamp =
        MethodHandles.dropArguments(target, 0, long.class);
// New type: (long,String)String.
```

This illustrative snippet assumes `target` already has type `(String)String`; it is not standalone. You could also do this with `permuteArguments`, but you would have to declare `newType=(long,String)String`, `reorder=[1]`. If you also need to reorder and duplicate, `permuteArguments` is usually clearer.

**Note on composition:** combinators create new handles; the original handle is immutable. You can build a chain of adaptation steps (routing, binding, filtering, conversion), but you must determine the exact type of **each step** before chaining. There is no “auto matching” between combinators.

## 10. Validation Checklist Before Creating Adapters in Dynamic Systems

When the index mapping comes from configuration or runtime logic, check deliberately before calling `MethodHandles.permuteArguments`:

1. **Choose the specific target**, knowing `target.type()` and the invocation permissions for its handle. The handle can come from `findStatic`, `findVirtual`, `unreflect`, or another combinator.
2. **Determine the desired interface**: `newType` must include the exact parameters the caller will provide and the same return type as target.
3. **Create the `reorder` array with length equal to target's parameter count**. Provide one element for **each target position**, even when multiple positions take the same incoming argument.
4. **Check valid indices** in the range `0...newType.parameterCount()-1`. If newType has no parameters, target must also have 0 parameters to be mappable.
5. **Check identical types** for each pair `target.type().parameterType(i)` and `newType.parameterType(reorder[i])`.
6. **Only create the handle after passing validation** and cache it if appropriate. `permuteArguments` re-checks on creation and throws `IllegalArgumentException` if invalid.
7. **Print/log `handle.type()`, the mapping, and target type** when diagnosing errors, avoiding printing secret argument data. When running `invokeExact`, ensure the actual call-site types match `newType`.

A mapping validation function might look like this (illustrative, requires importing `MethodHandle`, `MethodType`):

```java
static boolean mappingMatches(MethodHandle target, MethodType newType, int[] reorder) {
    MethodType old = target.type();
    if (old.returnType() != newType.returnType()) return false;
    if (reorder.length != old.parameterCount()) return false;

    for (int i = 0; i < reorder.length; i++) {
        int j = reorder[i];
        if (j < 0 || j >= newType.parameterCount()) return false;
        if (old.parameterType(i) != newType.parameterType(j)) return false;
    }
    return true;
}
```

This method only checks the core invariants of `permuteArguments`; in real integrations you must handle null inputs, MethodType resolution errors, JVM parameter/slot limits, access permissions, and the application's error-handling policy. For valid mappings, you can call `MethodHandles.permuteArguments` directly without an extra validation wrapper if the application does not require specialized error reporting.

### 10.1. Why Not Pass Indices the Other Way Around?

Suppose target has 2 parameters while newType has 3. `reorder` always has length **2**, because each target parameter needs one source. Do not create an array of length 3 and write the destination of each incoming argument; that is the **reverse** mapping direction and can lead to misconfiguration.

With target `(String,int)void`, newType `(int,String,boolean)void`, the right mapping is `[1,0]` (target String ← incoming String index 1; target int ← incoming int index 0); incoming boolean index 2 is dropped. The array `[1,0,2]` is wrong because length 3 differs from target's arity of 2.

### 10.2. Can You Duplicate an Index of a Different Type?

With target `(int,long)void` and newType `(int)void`, `[0,0]` is **invalid**: incoming index 0 has type `int`, whereas target position 1 needs `long`. If you want to declare one incoming `int` to supply both `int` and `long`, use an appropriate type-converting/value-distributing combinator instead of relying on an implicit cast from `permuteArguments`.

## 11. Common Exceptions and Mistakes

| Error or Symptom | Cause | How to Fix |
| --- | --- | --- |
| `IllegalArgumentException` when calling `permuteArguments` | `reorder.length` differs from target arity; negative/out-of-bounds index; source–target types not identical; different return type | Check `target.type()`, `newType`, and each `reorder[i]` |
| `NullPointerException` when creating adapter | `target`, `newType`, or `reorder` array is `null` | Validate input data; do not pass null for mapping |
| `WrongMethodTypeException` at `invokeExact` | Compile-time signature at call site does not match `handle.type()` | Check exact `parameterType`, `returnType`, and call expression types |
| `ClassCastException` in a pipeline using `asType` | Runtime value cannot be cast to the required reference type | Validate input objects; inspect the type-converting adapter step |
| Target called with reversed parameters | Misunderstood `reorder` as mapping from incoming to target | Write a table: which incoming index each **target position** takes from |
| “Dropped” input still causes side effects | Java evaluates argument expressions before invoking the handle | Only the **value in the target call** is dropped, not the evaluation of the input argument |
| Duplicated object mutated unexpectedly | Duplicated the same mutable reference | Distinguish aliasing from data copying; design side-effect handling |
| Dynamic invoker expected to pick another overload | Handle already points to a fixed target | Choose the right MethodHandle upfront; do not expect automatic overload resolution |
| Target is varargs but adapter is no longer varargs | `permuteArguments` adapter is always fixed arity | Add a varargs handling step if the caller contract requires it |
| Calling handle from config with wrong param count | `newType` differs from the number of inputs the caller actually passes | Define the contract upfront; compare `newType.parameterCount()` with the call site |

**Do not confuse creation-time errors with invocation-time errors:** structurally invalid mappings are rejected at `permuteArguments` (usually `IllegalArgumentException`). A successfully created adapter can still be called with the wrong type at `invokeExact` (usually `WrongMethodTypeException`), or the target's code can throw its own exceptions. MethodHandle does not automatically wrap target exceptions in `InvocationTargetException` like Reflection's `Method.invoke`.

## 12. Self-Check Exercises

**Exercise 1 — Swap parameters:** target `(int,int)int` computes `a-b`; we want the new handle to still accept two ints but produce `b-a`. Write the mapping.

**Answer:** `newType=(int,int)int`, `reorder=[1,0]`.

**Exercise 2 — Duplicate parameter:** target `(String,String)String` concatenates `a+"/"+b`; we want to pass only one `String`. Write the mapping and predict the result for `"x"`.

**Answer:** `newType=(String)String`, `reorder=[0,0]`; target receives `("x","x")` and returns `"x/x"`.

**Exercise 3 — Drop parameters:** target `(String,int)String`; the new interface is `(long,int,String,boolean)String`. Choose the mapping.

**Answer:** `reorder=[2,1]`. Incoming index 2 is `String`, incoming index 1 is `int`; indices 0 and 3 are dropped.

**Exercise 4 — Count mapping array:** target `(int,int,int)void`, newType `(int)void`. Can one input be duplicated for all three?

**Answer:** Yes; `reorder=[0,0,0]`, length 3 equals target arity. Target receives the same `int` three times.

**Exercise 5 — Distinguish type conversion:** target `(long,long)long`, newType `(int)long`, mapping `[0,0]`. Is it valid?

**Answer:** No. Target needs `long`, incoming index 0 has type `int`. `permuteArguments` does not widen; design a separate compatible type-conversion step, such as creating an appropriately `asType`-adapted handle before permuting.

**Exercise 6 — Receiver:** instance handle has type `(Account,String)boolean`. Callback interface needs `(String,Account)boolean`. What is the mapping?

**Answer:** `[1,0]`; new input index 1 supplies the `Account` receiver to target position 0.

**Exercise 7 — Zero-parameter target:** target `()String`, newType `(int,boolean)String`. How long is `reorder`?

**Answer:** 0. All new inputs are dropped; `permuteArguments(target,newType)` is the right call.

## Source References

- [JDK 17 — MethodHandles.permuteArguments](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html#permuteArguments(java.lang.invoke.MethodHandle,java.lang.invoke.MethodType,int...)): mapping definition, type constraints, duplicate/drop, exceptions, and fixed-arity rules.
- [JDK 17 — MethodHandle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html): `type()`, `invokeExact`, `invoke`, `asType`, and adaptation mechanisms.
- [JDK 17 — MethodType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html): parameter/return value structure and how to construct `methodType`.
- [JDK 17 — MethodHandles](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html): `dropArguments`, `insertArguments`, `filterArguments`, `filterReturnValue`, and related combinators.

**Key takeaway:** `permuteArguments(target, newType, reorder)` defines for **each target position** an input index of the **new handle**. Indices can be **reordered**, **appear multiple times**, or **not appear at all**. Every mapping edge must have **exact equal types**, `reorder` length must equal target's parameter count, and the return type remains unchanged. That is the key to composing handles accurately without writing manual wrappers.
