# 8.6. Branch Selection with `MethodHandles.guardWithTest` and Unifying the Types of Both Branches

`java.lang.invoke.MethodHandles.guardWithTest(test, target, fallback)` is a **combinator** that creates a `MethodHandle` behaving similarly to `if/else`: each time the resulting handle is called, the JVM calls `test`; if it receives `true`, it runs `target`, otherwise it runs `fallback`. The hardest part does not lie in the `if` operation, but in the **type contract (`MethodType`)**: both branches must have **completely matching** types, while the test function must return a primitive `boolean` and may only read a **prefix** of the parameters of both branches.

Objectives of this lesson:

- Understand the signature, execution flow, and type-checking timing of `guardWithTest`.
- Create both `target`/`fallback` branches with the same `MethodType`, even when the original methods have different return types or parameter counts.
- Know when to use `asType`, `dropArguments`, `constant`, `insertArguments`, or `permuteArguments` to **proactively adapt** method handles before combining.
- Distinguish errors **when creating the combinator** (`IllegalArgumentException`) from errors **when invoking** (`WrongMethodTypeException`, `ClassCastException`, or an exception from the selected branch).
- Use `invokeExact` properly, avoid relying on implicit type conversion, and understand that `guardWithTest` does not automatically catch errors from a failing branch.

This lesson uses Java 17+; the standalone program in section 4 was compiled with `javac --release 17` and run to verify the exact stdout.

## 1. Thinking of It as an `if/else` Expression with an Explicit Signature

API:

```java
MethodHandle result = MethodHandles.guardWithTest(
        test, target, fallback);
```

This is an **illustrative code snippet**; `test`, `target`, and `fallback` are existing `MethodHandle`s and must satisfy the contract in the following section.

Semantics:

```text
                   invoke result(a..., b...)
                               |
                               v
                          test(a...)
                               |
                      +--------+--------+
                      |                 |
                    true              false
                      |                 |
                      v                 v
              target(a..., b...)  fallback(a..., b...)
                      |                 |
                      +--------+--------+
                               |
                       returns the same type T
```

Suppose `target` and `fallback` both accept arguments `(A..., B...)` and both return `T`, while `test` only accepts the prefix `(A...)` and returns `boolean`:

```text
test     : (A...)boolean
target   : (A..., B...)T
fallback : (A..., B...)T
result   : (A..., B...)T
```

For example:

```text
test     : (int)boolean
target   : (int, String)String
fallback : (int, String)String
result   : (int, String)String
```

On each call to `result`:

1. `test` receives the first `int` argument and returns `true` or `false`.
2. `true` selects `target`, `false` selects `fallback`.
3. The selected branch receives the **full** original arguments in the exact order.
4. The unselected branch is **not called**.
5. `result` has the same type as `target` and `fallback`, not the type of `test`.

The adapter is created **once** when calling `guardWithTest`; the test expression is run **each time** the adapter is invoked, unless the application fixes/transforms the adapter using specific techniques. There is no re-creation of the two member method handles on each call just because `test` is re-evaluated.

## 2. Mandatory Type Contract

### 2.1. Both Branches Must Be Strictly Identical

Central condition:

```java
target.type().equals(fallback.type())
```

This is a **standalone illustrative snippet**, using two existing handle variables. `MethodType.equals` compares the exact return type, parameter count, parameter order, and each `Class<?>` of the parameters.

Examples:

| `target.type()` | `fallback.type()` | Can combine directly? | Reason |
| --- | --- | --- | --- |
| `(int)String` | `(int)String` | Yes | Exact match |
| `(int, String)String` | `(int, String)String` | Yes | All types and order match |
| `(int)String` | `(long)String` | No | `int` differs from `long`, even though Java has widening on regular method calls |
| `(int)String` | `(Integer)String` | No | `int` differs from `Integer`, even though there is boxing/unboxing in other contexts |
| `(int)String` | `(int)Object` | No | `String` differs from `Object`, even though `String` is a subtype of `Object` |
| `(int, String)void` | `(int, String)String` | No | `void` differs from `String` |
| `(int, String)String` | `(String, int)String` | No | Parameter order differs |

`guardWithTest` **does not automatically call `asType`** to make the two branches compatible. If the original types differ, the programmer must choose **a common target signature**, then convert each branch in a controlled manner before combining.

A branch returning `void` is completely valid **if both branches return `void`**. In that case, the resulting handle also returns `void`.

### 2.2. `test` Must Return Primitive `boolean`

The test function must have return type **`boolean.class`**, not `Boolean.class`, `int.class`, or `Object.class`.

Examples:

```text
(int)boolean    -> valid if the parameters are a prefix
(int)Boolean    -> invalid when combining directly
()boolean       -> valid; test does not use any parameters
```

If the original predicate returns `Boolean`, you can consider adapting it with `asType` to `boolean`; keep in mind that the unboxing operation can throw `NullPointerException` if the predicate returns `null`. In most cases, designing the predicate to return primitive `boolean` is clearer.

### 2.3. Parameters of `test` Must Be a **Contiguous Prefix**

For a branch with type:

```text
(int, String, long)String
```

Valid `test` types in terms of parameter count/order are:

```text
()boolean
(int)boolean
(int, String)boolean
(int, String, long)boolean
```

Meanwhile, the following types are invalid for **direct** combination:

```text
(String)boolean             // takes the second parameter, not a prefix
(int, long)boolean          // skips String in the middle
(int, String, long, int)boolean // too many parameters
(int)Boolean                // return type is not primitive boolean
(long)boolean               // first parameter does not match int
```

If the predicate needs a parameter at a different position, you can create a new handle with the **right-positioned** signature using `dropArguments`, `permuteArguments`, `filterArguments`, or appropriate combinators. Do not assume `guardWithTest` automatically finds matching parameters by name or reorders them automatically.

### 2.4. The Result Does Not Change Type Between Calls

Because both branches share the same `MethodType`, the adapter also has that exact `MethodType`:

```java
MethodHandle result = MethodHandles.guardWithTest(
        test, target, fallback);
System.out.println(result.type().equals(target.type())); // true
```

This is a **standalone illustrative snippet** using handles that have already been validly created. Even though at runtime some calls take the `target` branch and some take `fallback`, the signature of `result` remains unchanged. Therefore, the caller can use an `invokeExact` with an explicit type without needing to know the test result.

## 3. Verification Timing and Execution Order

There are two layers to separate:

**Layer A — when combining the adapter:**

- `guardWithTest` accepts three handles, checks for `null`, the predicate's return type, the types of both branches, and the prefix rule.
- If invalid, the API throws `NullPointerException` or **`IllegalArgumentException`** right at adapter *construction* time.
- It **does not automatically run `test`, `target`, or `fallback`** to test the result during combination.
- If a member handle was previously created via `Lookup.findStatic`/`findVirtual`, the access checks of that factory are a separate matter: they already occurred when looking up the method.

**Layer B — when calling the adapter:**

- The JVM calls `test` with the parameter prefix from the call.
- If `test` returns `true`, only `target` runs; if `false`, only `fallback` runs.
- There is no automatic fallback to `fallback` when `test` throws an exception; the exception is propagated. If `target` is selected and then throws an exception, `fallback` is **not** called as a catch handler.
- The caller must still call the handle with the exact `MethodType`, especially with `invokeExact`.
- Each branch receives the original arguments, not the `boolean` value returned by `test`.

It is necessary to distinguish **passing arguments untouched** from **state immutability**: the combinator does not replace or remove arguments before passing them to the branch; however, a predicate with side effects can still mutate the **state of an object** passed by reference or shared data. Therefore, predicates should be written concisely, predictably, and ideally without side effects.

## 4. Standalone Java 17+ Program: Branch Selection and Handling Mismatches

Save all the code below into **`GuardWithTestDemo.java`**. The `GuardWithTestDemo` class uses static methods so we do not need to handle a receiver; we focus on `MethodType` and compositional logic.

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public final class GuardWithTestDemo {
    static boolean nonNegative(int value) {
        System.out.println("test(" + value + ")");
        return value >= 0;
    }

    static String accepted(int value, String tag) {
        System.out.println("target");
        return "ok[" + tag + "]=" + value;
    }

    static String rejected(int value, String tag) {
        System.out.println("fallback");
        return "no[" + tag + "]=" + value;
    }

    static Object rejectedObject(int value, String tag) {
        return "objectFallback[" + tag + "]=" + value;
    }

    static boolean vip(String tag) {
        return "vip".equals(tag);
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        // Predicate receives only the int prefix.
        MethodHandle test = lookup.findStatic(
                GuardWithTestDemo.class, "nonNegative",
                MethodType.methodType(boolean.class, int.class));

        // Both branches must have the same MethodType.
        MethodType commonType = MethodType.methodType(
                String.class, int.class, String.class);
        MethodHandle target = lookup.findStatic(
                GuardWithTestDemo.class, "accepted", commonType);
        MethodHandle fallback = lookup.findStatic(
                GuardWithTestDemo.class, "rejected", commonType);

        MethodHandle route = MethodHandles.guardWithTest(test, target, fallback);
        System.out.println("testType=" + test.type());
        System.out.println("routeType=" + route.type());
        System.out.println("first=" + (String) route.invokeExact(7, "A"));
        System.out.println("second=" + (String) route.invokeExact(-3, "B"));

        // Original fallback branch ()String: widen to accept (int,String).
        MethodHandle constantFallback = MethodHandles.dropArguments(
                MethodHandles.constant(String.class, "blocked"),
                0, int.class, String.class);
        MethodHandle blocked = MethodHandles.guardWithTest(
                test, target, constantFallback);
        System.out.println("blocked=" + (String) blocked.invokeExact(-1, "C"));

        // Invalid because one branch returns Object and the other returns String.
        MethodHandle objectFallback = lookup.findStatic(
                GuardWithTestDemo.class, "rejectedObject",
                MethodType.methodType(Object.class, int.class, String.class));
        try {
            MethodHandles.guardWithTest(test, target, objectFallback);
            System.out.println("mismatch=unexpected");
        } catch (IllegalArgumentException expected) {
            System.out.println("mismatch=rejected");
        }

        // Convert Object -> String using an explicit runtime cast.
        MethodHandle convertedFallback = objectFallback.asType(commonType);
        MethodHandle converted = MethodHandles.guardWithTest(
                test, target, convertedFallback);
        System.out.println("adapted=" + (String) converted.invokeExact(-2, "D"));

        // Predicate (String)boolean is not a prefix of (int,String).
        MethodHandle byTag = lookup.findStatic(
                GuardWithTestDemo.class, "vip",
                MethodType.methodType(boolean.class, String.class));
        try {
            MethodHandles.guardWithTest(byTag, target, fallback);
            System.out.println("nonprefix=unexpected");
        } catch (IllegalArgumentException expected) {
            System.out.println("nonprefix=rejected");
        }

        // Insert an unused int at the beginning: (int,String)boolean.
        MethodHandle tagTest = MethodHandles.dropArguments(
                byTag, 0, int.class);
        MethodHandle tagRoute = MethodHandles.guardWithTest(
                tagTest, target, fallback);
        System.out.println("vip=" + (String) tagRoute.invokeExact(5, "vip"));
        System.out.println("normal=" + (String) tagRoute.invokeExact(5, "user"));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac --release 17 GuardWithTestDemo.java
java GuardWithTestDemo
```

**Exact stdout** of the program:

```text
testType=(int)boolean
routeType=(int,String)String
test(7)
target
first=ok[A]=7
test(-3)
fallback
second=no[B]=-3
test(-1)
blocked=blocked
mismatch=rejected
test(-2)
adapted=objectFallback[D]=-2
nonprefix=rejected
target
vip=ok[vip]=5
fallback
normal=no[user]=5
```

Note how `MethodType.toString()` displays `(int,String)String` without a space after the comma. That is Java's standard representation, not an arbitrary custom string.

### 4.1. Reading the Trace of the First and Second Calls

The line `test(7)` appears before `target` because `test` runs first, returning `true`. The result `first=ok[A]=7` comes from `accepted`.

On the call `(-3, "B")`, `test(-3)` returns `false`; only `fallback` prints and `rejected` produces `second=no[B]=-3`.

The `"A"` or `"B"` argument is not passed to `nonNegative` because the test only needs `int`. However, both arguments are forwarded in their original positions to the selected branch.

### 4.2. Why Does `blocked=blocked` Not Print `fallback`?

`constantFallback` is created from:

```java
MethodHandles.constant(String.class, "blocked")
```

It has type `()String`: it returns a constant without accepting arguments. Then:

```java
MethodHandles.dropArguments(
        constant, 0, int.class, String.class)
```

(the two snippets above use an illustrative `constant` variable from the result of `constant(...)`) creates a new handle of type `(int,String)String`, **ignoring** the two arguments the adapter receives. When the test returns `false`, the new branch returns `"blocked"` immediately without calling `rejected`, because the fallback branch is now a constant adapter.

Important: `dropArguments` does not modify the original method handle and does not automatically assign default values for arguments the caller omits. It makes the new handle **accept additional** arguments and then ignore them when delegating.

### 4.3. Why Is the `Object` Branch Rejected Even Though the Actual Value Is `String`?

`rejectedObject` has signature `(int,String)Object`, even though in practice it returns a `String` object. Meanwhile, `accepted` has type `(int,String)String`.

`guardWithTest` compares the **declared `MethodType`**, without running the branch to see what class the actual object belongs to. Therefore, the first combination attempt throws `IllegalArgumentException`.

The fix in the example:

```java
MethodHandle convertedFallback = objectFallback.asType(commonType);
```

This line requests a new method handle with type `(int,String)String`. When the branch executes, the adapter performs a type conversion of the result from `Object` to `String` (provided the runtime value actually fits).

If `rejectedObject` returns an object that cannot be cast to `String`, calling the combined handle can fail with **`ClassCastException` at runtime**. `asType` resolves the **adapter signature**; it does not prove all runtime data is valid.

### 4.4. Why Is `(String)boolean` Unsuitable and How Does `dropArguments` Help?

`byTag` has type `(String)boolean`, but `target` and `fallback` accept `(int,String)`. `test` may only take a **prefix**, and the one-element prefix of `(int,String)` is `(int)`, not `(String)`.

`dropArguments(byTag, 0, int.class)` creates a new test `(int,String)boolean`: it accepts the first `int` and **ignores** it, then forwards the second `String` to the `vip` predicate.

The final two calls demonstrate that `tagRoute` selects target for the `"vip"` tag and fallback for the `"user"` tag, even though `value` is the same.

## 5. Four Techniques to Unify Types Before Combining

When handles do not yet share the same signature, follow this order: **choose a common `MethodType` → inspect the kind of difference → adapt each handle → verify `type()` → combine**.

### 5.1. `asType` — Adapting Parameter or Return Types When Valid

Verified example:

```java
MethodType commonType = MethodType.methodType(
        String.class, int.class, String.class);
MethodHandle adjustedFallback = objectFallback.asType(commonType);
```

This is an **illustrative code snippet in the context of the section 4 program**. Before adapting:

```text
objectFallback : (int,String)Object
target         : (int,String)String
```

After adapting:

```text
adjustedFallback : (int,String)String
target           : (int,String)String
```

`asType` can insert conversions supported by Java `MethodHandle`, such as reference casts, boxing/unboxing, or corresponding primitive conversions. It does **not** guarantee every conversion is safe: some errors can occur when creating the adapter (`WrongMethodTypeException` for unsupported conversions) or when invoking (e.g., invalid cast, unboxing `null`).

**Do not use `asType` to mask an unclear data model.** If two branches naturally return two different kinds of results, decide on a sensible common contract, such as a unified result interface/record, rather than forcing arbitrary casts.

### 5.2. `dropArguments` — Adding Ignored Parameters

Case where fallback does not need all arguments:

```text
constant(String.class, "blocked") : ()String
target                            : (int,String)String
```

After:

```java
MethodHandle fallbackFull = MethodHandles.dropArguments(
        MethodHandles.constant(String.class, "blocked"),
        0, int.class, String.class);
```

we have `fallbackFull.type() == (int,String)String`. This is **syntactically standalone at the expression level** given `import java.lang.invoke.MethodHandle;` and `import java.lang.invoke.MethodHandles;`, though it is only an illustrative snippet rather than a complete program.

You can place the extra arguments at an appropriate `pos`, as long as the final resulting order matches the common signature.

**Subtle note:** `dropArguments` *adds* parameters to the new handle's signature but *does not* use them. Do not confuse this with removing real parameters from a call site. If you need to bind a fixed value for the original handle, see `insertArguments`.

### 5.3. `insertArguments` — Pre-binding Values for Some Parameters

Suppose an original method is:

```java
static String prefix(String label, int number) {
    return label + number;
}
```

This is an **illustrative declaration**. When `findStatic` has returned a handle of type `(String,int)String`, you can bind the label `"OK:"`:

```java
MethodHandle adjusted = MethodHandles.insertArguments(
        original, 0, "OK:");
```

`adjusted` will have type `(int)String`, because the first `String` parameter has been pre-supplied. To combine it into a guard with both branches having type `(int)String`, the other branch must also have type `(int)String` or be adapted accordingly.

`insertArguments` does not make the predicate change its signature automatically. Before calling `guardWithTest`, compare **all three** handles after adapting; do not compare only the two branches.

### 5.4. `permuteArguments` — Reordering Arguments When Predicate or Branch Needs a Different Order

A predicate may need an argument located in the middle/end, or an original branch may have a different parameter order. `permuteArguments` lets you create a handle with a new input order and map those inputs to the arguments of the old handle.

For example, with an original handle `h` of type `(String,int)String`, we want a handle accepting `(int,String)String` that passes them to `h` in reverse order:

```java
MethodType newType = MethodType.methodType(
        String.class, int.class, String.class);
MethodHandle reordered = MethodHandles.permuteArguments(
        h, newType, 1, 0);
```

This **illustrative snippet** assumes a variable `h` of exact type `(String,int)String` already exists. `reordered` has type `(int,String)String`: `h` receives `(String)` from the new argument at index `1`, and `(int)` from the new argument at index `0`. Keep in mind that mapping indices are **zero-based**.

Do not use `permuteArguments` to automatically convert `String` to `int`. It adjusts **mapping and order**, not data parsing. If after permutation the two branches still do not have the exact same type, further adaptation is required.

## 6. Checking `MethodType` Before Combining

In frameworks or dynamically generated adapters, logging signatures often saves a lot of time:

```java
System.out.println("test=" + test.type());
System.out.println("target=" + target.type());
System.out.println("fallback=" + fallback.type());
```

This is a **standalone illustrative snippet** with handle variables already created.

If validating beforehand yourself, you can apply this sequence:

1. `test != null && target != null && fallback != null`.
2. `target.type().equals(fallback.type())`.
3. `test.type().returnType() == boolean.class`.
4. `test.type().parameterCount() <= target.type().parameterCount()`.
5. The test's parameter list equals the **same-length prefix** of `target.type().parameterList()`.

A minimal check in Java when the handles already exist:

```java
MethodType targetType = target.type();
MethodType fallbackType = fallback.type();
MethodType predicateType = test.type();

if (!targetType.equals(fallbackType)) {
    throw new IllegalArgumentException("Branches have different MethodTypes");
}
if (predicateType.returnType() != boolean.class) {
    throw new IllegalArgumentException("Test must return primitive boolean");
}
int count = predicateType.parameterCount();
if (count > targetType.parameterCount()
        || !predicateType.parameterList().equals(
                targetType.parameterList().subList(0, count))) {
    throw new IllegalArgumentException("Test parameters must be a prefix");
}
```

This is an **illustrative snippet using existing `test`, `target`, and `fallback` variables** and requires importing `MethodType`; it is not a standalone Java file. `guardWithTest` still checks these conditions itself; the validation above simply helps produce more contextual messages at the application layer.

In practical design, normalize `MethodType` before creating the adapter rather than building it and relying on exceptions to guess. However, do not wrap every `RuntimeException` and label it a "type error," because a `RuntimeException` thrown **when invoking a branch** can be a completely different business error.

## 7. `invokeExact` and `invoke`: Don't Let Call-Site Errors Mask Combination Errors

For an adapter with signature:

```text
(int,String)String
```

An exact call is:

```java
String result = (String) route.invokeExact(7, "A");
```

This is a **snippet from the program in section 4**, where `route` is a `(int,String)String` handle.

With `invokeExact`, the call site must express exact types:

- First argument is `int`, not `long` or `Integer`.
- Second argument is `String`, not an `Object` that just happens to hold a `String`.
- Return value per signature is `String`, not `Object` or a `void` context.

Because this is a signature-polymorphic invocation, the result cast expression and the static type context of the call site affect the signature the JVM expects. Code that looks like normal Java can still throw `WrongMethodTypeException` when the signature is wrong.

`invoke` allows adaptation according to MethodHandle type conversion rules, but you should not rely on it as a substitute for designing the contract. For libraries/DSLs that need stable signatures, `invokeExact` usually helps catch errors earlier and more clearly.

**Important:** `guardWithTest` succeeding **does not mean** every `invokeExact` will run. These are two different checking layers: composition type versus invocation call-site type.

## 8. When `test` or a Branch Throws an Exception

`guardWithTest` is a **branch-selection** combinator, not an exception handler.

Suppose the test is:

```java
static boolean eligible(int value) {
    if (value == 0) {
        throw new IllegalStateException("Unknown");
    }
    return value > 0;
}
```

This is an **example declaration**, not yet a standalone runnable class.

When `eligible(0)` throws an exception, neither `target` nor `fallback` is called. The adapter propagates that exception to the caller.

Similarly, if `test` returns `true`, `target` is called, and `target` throws an exception, then `fallback` is **not** a "backup branch" to catch errors. It only runs when **the predicate returns `false`**.

If the goal is to handle exceptions from target, consider another combinator such as `MethodHandles.catchException(...)`, with its own handler signature, or use an appropriate try/catch in an outer layer. If the goal is state-based execution branching that needs to be invalidated after an event, `SwitchPoint.guardWithTest` is a different API with invalidation semantics, not synonymous with `MethodHandles.guardWithTest`.

An easy trap to miss: because test is called on every invocation, a test that depends on time, thread-local state, cache, or a global flag can choose different branches on consecutive calls. `guardWithTest` does not automatically lock or make shared memory thread-safe. Designing a guard with side effects or race conditions can create hard-to-reproduce logic bugs.

## 9. Unifying Types When Two Branches Come from Different APIs

A typical situation: library A returns `int`, library B returns `long`, or one branch returns `String` and another returns `Object`. How you choose the common signature directly affects semantics:

| Issue | Right Approach | What to Consider |
| --- | --- | --- |
| Different primitive types like `int`/`long` | Choose common `long` if business logic allows and adapt in a controlled manner | Widening may be suitable; narrowing can lose data |
| `String` vs `Object` | Choose common `Object` or cast `Object` to `String` when guaranteed | Choose `String` only when the object is truly always a `String` |
| Branch does not need some parameters | `dropArguments` to add ignored parameters | Those parameters are not used/validated in that branch |
| Branch returns a constant | `constant` then `dropArguments` | A constant may hide ignored data or missing logging |
| Branch needs arguments in a different order | `permuteArguments` or an appropriate adapter | Check zero-based indices and the signature after transformation |
| Branch requires a fixed configuration value | `insertArguments` | Bound values have their own lifecycle and access rights |
| Branch returns `void`, other branch returns a value | Choose a truly sensible contract, adapt if the API allows and it makes sense | Do not accidentally discard a business-meaningful result |
| Predicate needs a parameter in the middle | Create a new predicate handle with the full signature, e.g., `dropArguments` at the appropriate position | Test may only receive a prefix after being adapted |

The `asType` example from `(int,String)Object` to `(int,String)String` in section 4 makes sense because that branch **actually returns a `String`**. If the branch could return an `Integer` or another record, that cast is no longer safe; choose `Object`/a result interface or create a clearer mapper.

There is no rule to "always pick the widest type regardless of data." Choose the common type based on the contract, not just to stop `guardWithTest` from throwing `IllegalArgumentException`.

### 9.1. The `void` Return Case

If both branches have type `(String)void`, the predicate can have type `(String)boolean` or `()boolean`. The resulting adapter has type `(String)void`; when calling `invokeExact`, use a context that **does not take a return value**.

You cannot directly combine a `(String)void` branch with a `(String)String` branch. If the `String` result is unimportant and policy allows, you can proactively adapt to discard the result; otherwise, redesign the contract so both branches return data or both return `void`. Do not let a mismatch be hidden by having one branch just print a log.

### 9.2. The Instance Method Receiver Case

`findVirtual` creates a handle with the **receiver** included in the `MethodType` parameter list, usually as the first parameter. That means **the prefix predicate sees the receiver first**, rather than seeing the first business parameter of the original method.

For example, for a handle of type `(Service,int)String`, a test of type `(int)boolean` is **not** a prefix; it must be turned into `(Service,int)boolean` or a suitable prefix. Using `dropArguments` to add an ignored receiver to the test is an option when types are exact. Avoid confusing the Java signature of the method `String serve(int)` with the instance handle signature `(Service,int)String`.

### 9.3. The Method Access Case

The three handles passed to `guardWithTest` must **already exist**. If created via `MethodHandles.Lookup`, whether `findStatic`/`findVirtual` succeeds depends on access rights and module visibility.

An `IllegalAccessException` when **looking up** a method handle is not a `guardWithTest` type-unification error. In this lesson's example, all methods to look up are inside `GuardWithTestDemo` itself, so `MethodHandles.lookup()` and `findStatic` can be used without changing JPMS openness.

## 10. Comparing `guardWithTest` with Regular `if/else`

| Criterion | Java `if/else` | `MethodHandles.guardWithTest` |
| --- | --- | --- |
| Type rules | Compiler checks expression/statement; branches can have different types depending on context | Both handles **must have the same `MethodType`** when combining |
| Predicate | Expression returning Java `boolean` | `MethodHandle` returning primitive `boolean` |
| Predicate inputs | Can use variables visible in scope | Receives an exact prefix of the adapter's inputs (unless adapted) |
| Branch determination | Each time the statement/expression executes | Each time the adapter is invoked (test runs then selects branch) |
| Construction site | Logic is in source code/bytecode | Adapter is dynamically composed from existing handles |
| Type errors | Usually appear at compile time | `IllegalArgumentException` at combination time, or call-site/adaptation error at invocation time |
| Suitable use cases | Normal business logic | Runtime frameworks, dynamic dispatch, DSLs, interpreters, handle composition |
| Readability | Usually clearer | Requires the reader to understand `MethodType` and combinators |

For normal business logic, a simple `if/else` or polymorphic method can be clearer and easier to maintain. `guardWithTest` is useful when an application **already works with MethodHandles as composable call blocks**, needing to build dynamic call flows without writing a new class for every configuration.

## 11. Diagnostic Checklist When `guardWithTest` Fails

When receiving `IllegalArgumentException` during combination:

1. Print `test.type()`, `target.type()`, and `fallback.type()`.
2. Compare **`target.type().equals(fallback.type())`**. If false, check parameter count, order, and return type.
3. Check `test.type().returnType() == boolean.class`. `Boolean.class` is not primitive `boolean`.
4. Match the test's parameter list against the **same-length prefix** of `target.type().parameterList()`. A predicate taking a parameter in the middle is not directly valid.
5. Adapt each handle separately using `asType`, `dropArguments`, `insertArguments`, `permuteArguments`, or an appropriate tool; verify the type **after** each step.
6. Recombine and confirm `result.type().equals(target.type())`.

When errors only appear **when calling**:

- `WrongMethodTypeException`: check the `invokeExact`/`invoke` signature and adapter conversion.
- `ClassCastException`: a branch may be returning an object that does not match the type chosen with `asType`.
- `NullPointerException`: may be due to code inside the predicate/branch or unboxing `null` in an adapter.
- `IllegalStateException` or other exceptions: may come from the predicate/branch itself; `fallback` does not automatically catch that error.
- Wrong result with no error: check the test condition, parameter order, and whether `target`/`fallback` were swapped when combining.
- Trace makes it look like both branches "were called": review code outside the adapter or side effects in the predicate; `guardWithTest` itself only calls **one branch** according to the test result.

**Testing tip:** write a predicate that prints a trace or increments a test counter, have both branches print distinct markers, then call the adapter sequentially with `true` and `false` inputs. Avoid putting overly verbose logging in production code on hot call paths.

## 12. Applicable Scenarios and Limitations

**Routing by request type:** the predicate classifies the request and selects the fast path/fallback path; both branches share a common result interface. When the two branches have different original signatures, transform them to the common contract where the adapter is created.

**Feature flag:** the predicate reads the flag each time to choose an implementation. Pay attention to consistency and visibility if the flag can change concurrently; `guardWithTest` does not provide synchronization on its own.

**Pre-processing validation:** a predicate checks the input, `target` processes valid cases, and `fallback` produces a rejection result. Both branches need the same `MethodType`, e.g., `(Request)Result`. If fallback only needs an error constant, use `constant` + `dropArguments` or an explicit adapter.

**Interpreter/DSL:** the engine can create handles for the condition and both branches from runtime metadata. This is a case where checking `MethodType` before combining is highly valuable; keep a signature normalization phase.

**Limitations:** a guard is not a catch handler; it does not automatically convert all types; it does not guarantee the predicate is side-effect-free; it is not a standalone security boundary; it does not automatically guarantee better performance than `if/else`. The JVM can optimize a handle graph when appropriate, but you should not claim a fixed speedup without benchmarking in a real application.

## 13. Self-Check Exercises (with Answers)

1. `target=(int,String)String`, `fallback=(int,String)String`, `test=(int)boolean`. Can they be combined? **Yes.** Test accepts a one-parameter prefix.
2. Same two branches above, but `test=(String)boolean`. Can they be combined directly? **No.** `String` is not the first parameter; you can prepend an ignored `int` using `dropArguments`.
3. `target=(int)String`, `fallback=(int)Object`. Will they combine automatically because `String extends Object`? **No.** The `MethodType` of both branches must be strictly identical.
4. `target=(int)String`, `fallback=(int)String`, `test=(int)Boolean`. Can they be combined directly? **No.** Test must return primitive `boolean`.
5. `test=()boolean` while both branches are `(int,String)String`. Is this valid? **Yes.** An empty prefix is accepted.
6. If the predicate returns `true` but `target` throws an exception, will the combinator automatically call `fallback`? **No.** Target's exception is propagated to the caller.
7. If you need fallback to always return `"blocked"` without using target's two parameters, what do you use? **`constant(String.class, "blocked")` followed by `dropArguments` to create a matching signature.**
8. If you adapt a `(int)Object` branch to `(int)String` using `asType`, what happens when the branch returns `Integer`? **It can throw `ClassCastException` at invoke time.**
9. Can `invokeExact` on a `(int,String)String` adapter use `long` as the first argument? **No**, the call site must match types, otherwise it may throw `WrongMethodTypeException`.
10. Can `guardWithTest` be used with two branches returning `void`? **Yes**, as long as both branches have the same type and the test satisfies the conditions.
11. Can the predicate receive the third parameter while skipping the first two? **Not directly**; you need to create a new predicate handle with the appropriate signature.
12. Why must the receiver be considered when using `findVirtual`? **The receiver is the first parameter in the method handle's type**, so it affects the prefix rule.
13. When is the test evaluated? **Each time the adapter is invoked**, before choosing one of the two branches.
14. Does `guardWithTest` automatically modify inputs based on the test's value? **No**; argument values are passed according to the original signature. However, the predicate can cause side effects on shared state objects.
15. In a regular project, should every `if/else` be replaced with `guardWithTest`? **No**; only use it when a compositional method handle model is needed and provides clear benefits.

## 14. Java SE 17 Reference Documentation

- [Java SE 17 — `MethodHandles.guardWithTest`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html#guardWithTest(java.lang.invoke.MethodHandle,java.lang.invoke.MethodHandle,java.lang.invoke.MethodHandle)): type conditions for predicate, target, and fallback; branch selection rules.
- [Java SE 17 — `MethodHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html): `invoke`, `invokeExact`, `asType`, runtime type checking.
- [Java SE 17 — `MethodType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html): representing and comparing method handle signatures.
- [Java SE 17 — `MethodHandles` combinators](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html): `dropArguments`, `constant`, `insertArguments`, `permuteArguments`, `catchException`.
- [Java SE 17 — `SwitchPoint`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/SwitchPoint.html): a kind of guard with an invalidation mechanism, serving a different purpose from general boolean predicates.

**Summary:** `guardWithTest` is not a type-inference mechanism. It requires `target` and `fallback` to have the **exact same `MethodType`**, `test` to return **primitive `boolean`**, and to use matching **prefix parameters**. **Normalize the handles first**, verify the signatures, and then combine; when invoked, test decides **a single branch**, and errors in a branch are not automatically routed to the other branch.