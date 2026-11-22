# 8.4 Transforming Inputs with `filterArguments` and Outputs with `filterReturnValue`

**Context:** Java Advance → dynamic-runtime → 8. Method Handle Combinators.

`MethodHandle` is not just a way to invoke methods as an alternative to Reflection. Java allows composing `MethodHandle`s into an **adapter**, meaning creating a handle whose signature matches the caller-side data, performs pre/post-processing on its own, and then invokes the target handle. The two most fundamental combinators for this are:

- **`MethodHandles.filterArguments(target, pos, filters...)`**: processes **inputs** before calling `target`; each filter transforms exactly **one** argument.
- **`MethodHandles.filterReturnValue(target, filter)`**: processes the **output result** after `target` runs; also supports `void`-returning targets and `void`-returning filters.

These two APIs are especially useful when connecting data from JSON/configuration/UI to a strictly typed business method, changing how a result is represented, or building a pipeline for a framework without writing a separate adapter class for each case. This lesson presents the mechanism, type rules, execution order, errors, and a verification program in Java 17.

## 1. Thinking in `MethodType` and Pipelines

Suppose the business logic is:

```java
static long total(int quantity, long unitCents) {
    return Math.multiplyExact((long) quantity, unitCents);
}
```

This is a **method snippet**, not a standalone runnable program. The corresponding `MethodType` of the target is:

```text
(int,long)long
```

However, the UI layer returns quantity and unit price as `String` values, for example `" 2 "` and `" 1500 "`. We want a dynamic API that accepts `(String,String)`, converts the quantity string to `int`, converts the unit price string to `long`, calls `total`, and then converts the cents amount into a result string.

```text
Data from caller:            (" 2 ", " 1500 ")
                                   |
                      filterArguments(target, 0,
                                      parseQuantity, parsePrice)
                                   |
               (int quantity, long unitCents) = (2, 1500)
                                   |
                          total(2, 1500)
                                   |
                             long = 3000
                                   |
                    filterReturnValue(..., format)
                                   |
                      "total=3000 cents"
```

We have three functional components:

| Component | `MethodType` Signature | Role |
| --- | --- | --- |
| `target = total` | `(int,long)long` | Business processing |
| `parseQuantity` | `(String)int` | Converts argument 0 |
| `parsePrice` | `(String)long` | Converts argument 1 |
| `filteredInputs` | `(String,String)long` | Adapter after filtering inputs |
| `format` | `(long)String` | Converts the return value |
| `pipeline` | `(String,String)String` | Complete adapter that the caller will invoke |

**Key point:** Combinators create a **new** `MethodHandle` and the signature is computed at composition time. They do not modify the declaration of `total(int,long)`, do not change the bytecode of the original method, and do not automatically choose another overload at runtime. The original handle still works with `(int,long)long`.

## 2. `filterArguments`: Transforming One or More Arguments

API signature:

```java
static MethodHandle filterArguments(
        MethodHandle target, int pos, MethodHandle... filters)
```

From left to right, each non-null filter at index `i` in `filters` is applied to **parameter `pos + i`** of `target`. `pos` starts at **0**. Arguments outside the filtered range are passed unchanged to the target.

### Exact Type Compatibility Rules

If the target has a parameter of type `A` at position `k`, the filter at that position **must have exactly one parameter** and return **the exact type `A`**:

```text
target: (P0, ..., A, ..., Pn) -> R
filter:             V -> A
adapter: (P0, ..., V, ..., Pn) -> R
```

`V` is the input type that the caller will pass to the adapter. The return type of the filter **must be identical** to the target's parameter type `A` by `Class<?>`, not merely "convertible in Java". For example:

| Target Parameter | Filter | Result |
| --- | --- | --- |
| `int` | `(String)int` | Valid, adapter accepts `String` at that position |
| `long` | `(String)long` | Valid |
| `Number` | `(String)Number` | Valid |
| `long` | `(String)int` | **Invalid at composition time**, even though `int` can widen to `long` |
| `Integer` | `(String)int` | **Invalid at composition time**, even though `int` can box to `Integer` |
| `String` | `(String,String)String` | **Invalid**, filter has two parameters instead of one |
| `int` | `()int` | **Invalid**, filter has no parameters |

Thus, `filterArguments` **does not automatically perform `asType`**, widening, boxing, or wrapper conversion to fix a mismatched filter signature. If you genuinely want a valid conversion via the `asType` mechanism, deliberately adapt the **filter** before passing it to the combinator; even better, use a filter whose types match directly to keep the contract clear.

### Position `pos` and Number of Filters

Example with target `(int,long)long`:

```java
// parseQuantity: (String)int
// parsePrice:    (String)long
MethodHandle both = MethodHandles.filterArguments(
        target, 0, parseQuantity, parsePrice);
// both.type(): (String,String)long

MethodHandle onlyPrice = MethodHandles.filterArguments(
        target, 1, parsePrice);
// onlyPrice.type(): (int,String)long
```

Both snippets are **snippets** assuming the three `MethodHandle` variables have already been validly created. The first argument `pos=1` means "start at the second argument", not "the second filter". `pos + filters.length` must not exceed `target.type().parameterCount()`; if it does, an `IllegalArgumentException` is thrown immediately when building the adapter.

### `null` Filter vs. `null` Argument

A **`null` element in the `filters` array** represents an **identity filter**: the corresponding argument is kept as-is, without needing to call a handle to process it. For example:

```java
MethodHandle keepQuantity = MethodHandles.filterArguments(
        target, 0, (MethodHandle) null, parsePrice);
// (int,String)long: argument 0 stays int, argument 1 converts String -> long
```

If every filter element is `null` or no filters are passed, the API may return `target` directly. However, **the `filters` array itself in the call must not be `null`**; for example, `(MethodHandle[]) null` causes a `NullPointerException`. Also, do not confuse this with a **`null` argument value when invoking the pipeline**: if `parsePrice` accepts `String` and its code calls `raw.strip()`, a `null` value can still cause a `NullPointerException`. The combinator does not automatically substitute, validate, or handle `null`.

### Execution Order and Side Effects

The Java 17 Javadoc guarantees that input filters run **from left to right**, and only then is the target called:

```text
filter[0](argument[pos])
filter[1](argument[pos+1])
...
target(all filtered and untouched arguments)
```

If an earlier filter throws an exception, subsequent filters and the target **do not run**. Therefore, when a filter performs validation, reads configuration, or writes logs, filter order matters. Prefer pure functions so composition is easy to reason about; do not rely on unnecessary side effects.

**Important limitation:** `filterArguments` only replaces **the type of individual positions**; it does not add/remove parameters and does not pass multiple parameters at once into a single filter. If a normalization step needs **two** inputs to produce **one** value, see `collectArguments` or `foldArguments` according to the appropriate signature.

## 3. `filterReturnValue`: Post-Processing the Target's Result

Signature:

```java
static MethodHandle filterReturnValue(
        MethodHandle target, MethodHandle filter)
```

If the target returns a value of type `R`, the filter **must have exactly one parameter of type `R`**, and can return a new type `V`:

```text
target:  (A0, A1, ..., An) -> R
filter:                      R -> V
adapter: (A0, A1, ..., An) -> V
```

For example, with target `(int,long)long` and `format` of type `(long)String`, the result is:

```text
filterReturnValue(target, format) : (int,long)String
```

When the caller invokes the adapter, **the target runs first**, its result is obtained and passed as the single argument to the filter; the value returned by the filter becomes the final result of the adapter. `filterReturnValue` **does not change the target's parameter type list**.

Like `filterArguments`, the parameter type of the output filter must **match the target's return type exactly**. For example, if the target returns `long` and the filter accepts `String` or `int`, an `IllegalArgumentException` is thrown **at composition time**, with no automatic parsing, unboxing, or widening.

### Two Special Cases Involving `void`

**Case A — `void`-returning target:** There is no value to pass into the output filter. In this case, the filter **must take 0 parameters**, and may return a new type:

```text
target:  (long)void
filter:  ()String
adapter: (long)String
```

This means calling the target to perform its work, then calling a zero-argument method and returning that method's result. This is not a mechanism for "receiving `null` from a `void` target"; the filter **receives no parameters at all**.

**Case B — `void`-returning filter:** The target produces a value `R`, and the filter accepts `R` to observe/log/send the result without returning a new value:

```text
target:  (int,long)long
filter:  (long)void
adapter: (int,long)void
```

This case can be useful for logging/auditing when the caller only needs the side effect. Note that when doing so, the caller **loses** the original return value through the adapter, even though the target still computes it internally.

In both cases, if the target throws an exception, the output filter **does not run**. If the output filter throws an exception, that exception is propagated to the caller; the API does not automatically wrap it in `InvocationTargetException` like `Method.invoke` in Core Reflection.

## 4. Bidirectional Composition: Pre-Processing Inputs, Post-Processing Output

From the component `MethodHandle`s:

```java
MethodHandle filteredInputs = MethodHandles.filterArguments(
        target, 0, parseQuantity, parsePrice);

MethodHandle pipeline = MethodHandles.filterReturnValue(
        filteredInputs, format);
```

Conceptually, `pipeline` is equivalent to the following logic (this is illustrative **pseudo-code**, not a standalone Java snippet):

```java
String pipeline(String quantityText, String priceText) {
    int quantity = parseQuantity(quantityText);
    long price = parsePrice(priceText);
    long cents = total(quantity, price);
    return format(cents);
}
```

The final adapter signature is `(String,String)String`. The caller does not need to know that the target requires `int` and `long` or what type `format` returns, as long as the final `MethodType` contract is designed properly.

Composition can be **nested in multiple layers**, for example `filterReturnValue(filterArguments(...), format)`. However, each layer still performs independent type checking, so print `.type()` right after each step when debugging. This is faster than guessing why `invokeExact` fails.

## 5. Complete Java 17 Program: Verifying Input Filters, Output Filters, `void`, and Errors

Create **`FilterPipelineDemo.java`** in a separate directory. The program requires no dependencies outside the JDK; use `--release 17` to force compilation against the Java 17 API/language.

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class FilterPipelineDemo {
    static int parseQuantity(String raw) {
        System.out.println("input.quantity");
        int value = Integer.parseInt(raw.strip());
        if (value <= 0) throw new IllegalArgumentException("quantity must be positive");
        return value;
    }

    static long parsePrice(String raw) {
        System.out.println("input.price");
        long value = Long.parseLong(raw.strip());
        if (value < 0) throw new IllegalArgumentException("price cannot be negative");
        return value;
    }

    static long total(int quantity, long unitCents) {
        System.out.println("target.total");
        return Math.multiplyExact((long) quantity, unitCents);
    }

    static String format(long cents) {
        System.out.println("output.format");
        return "total=" + cents + " cents";
    }

    static void report(long cents) {
        System.out.println("target.report=" + cents);
    }

    static String afterVoid() {
        System.out.println("output.afterVoid");
        return "reported";
    }

    static void audit(long cents) {
        System.out.println("output.audit=" + cents);
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodHandle target = lookup.findStatic(FilterPipelineDemo.class, "total",
                MethodType.methodType(long.class, int.class, long.class));
        MethodHandle quantity = lookup.findStatic(FilterPipelineDemo.class, "parseQuantity",
                MethodType.methodType(int.class, String.class));
        MethodHandle price = lookup.findStatic(FilterPipelineDemo.class, "parsePrice",
                MethodType.methodType(long.class, String.class));
        MethodHandle formatter = lookup.findStatic(FilterPipelineDemo.class, "format",
                MethodType.methodType(String.class, long.class));

        MethodHandle filteredInputs = MethodHandles.filterArguments(target, 0, quantity, price);
        MethodHandle pipeline = MethodHandles.filterReturnValue(filteredInputs, formatter);
        System.out.println("target.type=" + target.type());
        System.out.println("input.type=" + filteredInputs.type());
        System.out.println("pipeline.type=" + pipeline.type());
        System.out.println("pipeline.result=" + (String) pipeline.invokeExact(" 2 ", " 1500 "));

        MethodHandle priceOnly = MethodHandles.filterArguments(target, 1, price);
        System.out.println("priceOnly.type=" + priceOnly.type());
        System.out.println("priceOnly.result=" + (long) priceOnly.invokeExact(3, "7"));

        MethodHandle keepFirst = MethodHandles.filterArguments(target, 0,
                (MethodHandle) null, price);
        System.out.println("null-filter.type=" + keepFirst.type());

        try {
            MethodHandles.filterArguments(target, 0, price);
        } catch (IllegalArgumentException expected) {
            System.out.println("wrong-input-filter=IllegalArgumentException");
        }

        try {
            MethodHandles.filterReturnValue(target, quantity);
        } catch (IllegalArgumentException expected) {
            System.out.println("wrong-output-filter=IllegalArgumentException");
        }

        try {
            String unused = (String) pipeline.invokeExact("not-a-number", "1");
        } catch (NumberFormatException expected) {
            System.out.println("parse-failure=NumberFormatException");
        }

        MethodHandle report = lookup.findStatic(FilterPipelineDemo.class, "report",
                MethodType.methodType(void.class, long.class));
        MethodHandle afterVoid = lookup.findStatic(FilterPipelineDemo.class, "afterVoid",
                MethodType.methodType(String.class));
        MethodHandle voidTarget = MethodHandles.filterReturnValue(report, afterVoid);
        System.out.println("voidTarget.type=" + voidTarget.type());
        System.out.println("voidTarget.result=" + (String) voidTarget.invokeExact(5L));

        MethodHandle audit = lookup.findStatic(FilterPipelineDemo.class, "audit",
                MethodType.methodType(void.class, long.class));
        MethodHandle voidFilter = MethodHandles.filterReturnValue(target, audit);
        System.out.println("voidFilter.type=" + voidFilter.type());
        voidFilter.invokeExact(2, 3L);
    }
}
```

From the directory containing the file you just created:

```bash
javac --release 17 -encoding UTF-8 FilterPipelineDemo.java
java FilterPipelineDemo
```

**Exact stdout:**

```text
target.type=(int,long)long
input.type=(String,String)long
pipeline.type=(String,String)String
input.quantity
input.price
target.total
output.format
pipeline.result=total=3000 cents
priceOnly.type=(int,String)long
input.price
target.total
priceOnly.result=21
null-filter.type=(int,String)long
wrong-input-filter=IllegalArgumentException
wrong-output-filter=IllegalArgumentException
input.quantity
parse-failure=NumberFormatException
voidTarget.type=(long)String
target.report=5
output.afterVoid
voidTarget.result=reported
voidFilter.type=(int,long)void
target.total
output.audit=6
```

### Execution Order Analysis

1. `target.type()` is `(int,long)long`. `filteredInputs.type()` is `(String,String)long` after filtering both positions; `pipeline.type()` is `(String,String)String` after filtering the result.
2. When calling `pipeline.invokeExact(" 2 ", " 1500 ")`, the log records **`input.quantity` then `input.price`**. The two filters run left to right; `strip()` removes whitespace, `Integer.parseInt`/`Long.parseLong` convert types; the target multiplies `2 * 1500` to get `3000`.
3. `target.total` appears **before** `output.format`. The formatter converts `long 3000` into the string `"total=3000 cents"` and the adapter returns that string.
4. `priceOnly` uses `pos=1`, leaving the first parameter's type unchanged. It has signature `(int,String)long`; calling `priceOnly.invokeExact(3, "7")` runs the unit price filter and produces `21`.
5. `keepFirst` uses a `null` filter to keep `int` unchanged at the first position; the second argument is still converted `String → long`. Its type is also `(int,String)long`.
6. `filterArguments(target, 0, price)` attempts to use a `long`-returning filter for the target's first parameter of type `int`. The adapter is rejected **immediately at construction time** with `IllegalArgumentException`.
7. `filterReturnValue(target, quantity)` is also invalid because `target` returns `long` while `quantity` accepts `String`. It also fails immediately at construction time.
8. With `"not-a-number"`, `parseQuantity` is called first and throws `NumberFormatException`. Therefore, **there is no** `input.price`, `target.total`, or `output.format` log in this run. The exception goes straight back to the caller through `invokeExact`.
9. `voidTarget` turns `(long)void` into `(long)String`. The log shows that target `report` runs, then the zero-parameter filter `afterVoid` runs; the final result is `"reported"`.
10. `voidFilter` turns `(int,long)long` into `(int,long)void`. The target still executes to compute `6`, then `audit(long)` receives `6` and logs it, but the caller no longer receives the `long` result.

The program intentionally uses `(String) pipeline.invokeExact(...)` and `(long) priceOnly.invokeExact(...)`: `invokeExact` requires the **static signature at the call site** to match the handle's return type and parameter types exactly. If you want more flexible invocation, you can consider `invoke` (for certain valid conversions) or `asType`, but that is a **different** type adaptation mechanism from the two filters being studied here.

## 6. Detailed Type Rules and How to Choose a Combinator

### 6.1 Input Filters Must Be Unary, Output Filters See the Exact Result

Notation:

```text
T target(P0, P1, ..., Pn)
Pj filter_j(Vj)
U resultFilter(T)

filterArguments   -> adapter(..., Vj, ...) returns T
filterReturnValue -> adapter(P0, ..., Pn) returns U
```

If `resultFilter` only accepts `Object` while the target returns `String`, `filterReturnValue` **does not automatically perform a reference widening `String → Object`** to accept it. You need a filter with the exact type `(String)U` or explicitly use `asType` where appropriate.

Similarly, a target parameter of `long` and a filter returning `int` is invalid for `filterArguments`, even though normal Java method calls allow passing `int` to `long`. Combinators are defined based on **exact `MethodType`**, and do not perform Java overload resolution like the compiler.

### 6.2 Filter Inputs or Filter Output?

| Need | Appropriate API | Example |
| --- | --- | --- |
| Convert one argument before the target runs | `filterArguments` | `String → int` before `total(int,...)` |
| Convert multiple adjacent arguments, each with **one unary filter** | `filterArguments(target, pos, f1, f2)` | `(String,String) → (int,long)` |
| Keep a position unchanged between filters | `null` element in `filters` | `(int,String) → (int,long)` |
| Change the type of the result | `filterReturnValue` | `long → String` |
| Only run a task after a `void` target | `filterReturnValue` with `()R` filter | `(long)void → (long)String` |
| Observe the result then discard the final value | `filterReturnValue` with `(T)void` filter | `(int,long)long → (int,long)void` |
| One operation uses **multiple** inputs together | `collectArguments` / `foldArguments` | `(String,String) → DomainObject` |
| Change signature via JVM-permitted conversions | `MethodHandle.asType` (check its own rules) | Adapt a handle to another `MethodType` |
| Add dummy arguments or pre-bind constants | `dropArguments` / `insertArguments` | Ignore a parameter or fix the unit price |

Do not choose `filterArguments` to filter an entire list into a `List`; this API preserves positional arity and requires each filter to be unary. Also do not use `filterReturnValue` to try to insert extra parameters for the target; it only changes the return type and performs post-processing.

### 6.3 Reference and Primitive Conversions Are the Filter's Responsibility

Example of normalizing input data:

```java
static int parsePositiveQuantity(String raw) {
    int n = Integer.parseInt(raw.strip());
    if (n <= 0) throw new IllegalArgumentException("Quantity must be > 0");
    return n;
}
```

This is a **method snippet**, not a standalone program. If `raw` is `null`, the code throws `NullPointerException`; if the string is not a number, it throws `NumberFormatException`; if the number is not positive, it throws `IllegalArgumentException`. The combinator does not alter the meaning of those three errors. For arbitrary user input, design appropriate validation, error messages, and `null` handling at the application layer.

You can build multiple filters with the same input type such as `String -> int` (parse and validate) or `String -> String` (trim, normalize code); however, if a pipeline contains multiple separate steps for **the same argument**, you must **compose the filters** into a single unary handle of the right type before passing it to `filterArguments`. You cannot place multiple consecutive filters at the same `pos` and expect them to form a processing chain for one parameter.

## 7. Side Effects, Exceptions, and Return Value Control

### 7.1 If One Link Fails, Do the Remaining Steps Run?

| Where the Error Occurs | Steps That May Have Run | Steps That Do Not Run |
| --- | --- | --- |
| First input filter throws an exception | Only that filter (and code it already executed) | Subsequent input filters, target, output filter |
| Second input filter throws an exception | Earlier filters and the failing filter | Target and output filter |
| Target throws an exception | All input filters completed, target started | Output filter |
| Output filter throws an exception | Input filters and target completed, output filter started | No further post-processing step in that adapter |
| Signature mismatch when **building** the adapter | No filter/target runs | The entire pipeline is not created |

Because input filters run left to right, side effects from the first filter can still be observed even if the second filter fails. This matters for transactions, file writes, payments, or non-idempotent operations: do not treat the whole pipeline as automatically atomic just because it is represented by a single `MethodHandle`.

### 7.2 Distinguishing Configuration Errors from Invocation Errors

| Error | Which Phase Does It Occur In? | How to Check |
| --- | --- | --- |
| `IllegalArgumentException` | Building `filterArguments`/`filterReturnValue` with wrong filter signature, out-of-range `pos`, mismatched filter count | Compare `target.type()`, `filter.type()`, and `pos` before composing |
| `NullPointerException` | Passing disallowed `null` target/filter, or executing filter dereferences a `null` input | Distinguish **adapter creation** errors from filter logic errors |
| `WrongMethodTypeException` | `invokeExact` call-site signature does not match the final handle | Print `pipeline.type()` and inspect static types/return cast at the call site |
| `NumberFormatException` | A filter parses an invalid string | Validate and classify data errors at the input boundary |
| `ArithmeticException` | For example, target using `Math.multiplyExact` overflows | Check input domain, precision, and overflow |
| `IllegalAccessException` / `NoSuchMethodException` | Creating the base handle via `Lookup.findStatic`/`findVirtual` | Check `Lookup` access rights and exact `MethodType` |
| Exception thrown by target/filter | During pipeline execution | The exception is delivered to the handle's caller; not wrapped in `InvocationTargetException` by default |

**Common pitfall:** When calling `Method.invoke` in Java Reflection, exceptions thrown by the target method are wrapped in `InvocationTargetException`. When `MethodHandle.invokeExact` runs, exceptions from the target or filter **go straight** to the caller. Therefore, do not mechanically copy a `catch (InvocationTargetException)` from Reflection code into MethodHandle code.

### 7.3 Nullability and Input Types

A `(String)int` filter can accept `null` at the signature level because `String` is a reference type, but **the filter's code** determines the behavior. If the filter's return type is primitive `int`, the filter cannot return `null`; it must return an `int` value or throw an exception. The same applies to `filterReturnValue`: a filter accepting primitive `long` cannot receive `null` because the target returns a primitive; a filter accepting a reference type can handle `null` according to its contract.

State the null policy explicitly instead of relying on "reflection automatically converts `null` to a default". If a default is needed, create a filter that converts `null` to a valid value; if an error should be reported, check with `Objects.requireNonNull` and a clear message.

## 8. Performance, Readability, and Access Boundaries

`filterArguments` and `filterReturnValue` create cleanly structured adapters. The JVM/JIT can optimize stable MethodHandle chains, but **it is not guaranteed that every pipeline is faster than ordinary Java code**. Optimization must be measured against realistic workloads, considering pipeline size, call-site type stability, memory allocations, and filter cost. Do not reason from arbitrary nanosecond numbers.

Some design principles:

1. **Build the adapter once, reuse it when configuration is stable.** Do not recreate all handles for every record if the contract is the same.
2. **Name and categorize each step.** For example, `parseQuantity`, `parsePrice`, `total`, `format` are clearer than an anonymous filter chain that is hard to debug.
3. **Verify `MethodType` at boundaries.** After each composition step, call `.type()` and assert it against the expected contract in tests.
4. **Separate validation from dangerous side effects.** An input filter may be called before an error is detected in a later input filter.
5. **Do not treat MethodHandle as a way to bypass visibility.** `Lookup.findStatic`/`findVirtual` still checks access when obtaining handles; `filterArguments` and `filterReturnValue` do not grant `private` access or alter module `exports`/`opens`.
6. **Ensure thread-safety of code inside filters.** Handles may be reused across threads, but filters that access mutable state or non-thread-safe formatters still require dedicated synchronization design.
7. **Do not confuse adapters with a full validation framework.** These filters only express transformations; business contracts and user-facing error reporting remain the application code's responsibility.

**Note on varargs:** The result of `filterArguments` and `filterReturnValue` **does not preserve the variable-arity** of the target. If a method handle was previously a varargs collector, the resulting adapter has fixed arity; if you truly need a varargs collector on the final API, evaluate `asVarargsCollector` against the final signature. Do not rely on `...` in Java method source to assume combinators automatically rearrange argument counts.

## 9. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| "`filterArguments` runs after the target because its name contains `Arguments`." | It runs **before** the target to prepare the arguments. |
| "`filterReturnValue` changes all input parameters." | It only post-processes the return value; the target's inputs remain unchanged. |
| "A filter taking `String` and returning `int` can go straight into a `long` parameter." | No; the filter's return type must be **exact `long`** (or the filter must be adapted first). |
| "`pos=1` filters the first element." | Indexing is 0-based; `pos=1` filters the target's second argument. |
| "Adding two filters at the same position means two sequential steps for one input." | Each element in `filters` applies to **a different consecutive position** of the target. |
| "A `null` filter means passing a `null` argument on invoke." | A `null` filter is **identity**; a null input value is a separate concept. |
| "A `void`-returning target makes `filterReturnValue` invalid." | You can use a zero-parameter filter `()R` that runs after the target. |
| "An output filter must return a value." | The filter can return `void`, producing a `void`-returning adapter. |
| "If a filter fails, the output filter still runs for cleanup." | No; if the pipeline fails before the post-processing step, the output filter **is not called**. |
| "Adding a filter automatically opens access to call private methods." | No; `Lookup` access checks still apply when creating the target/filter handles. |
| "`invokeExact` always auto-boxes or converts types like `Method.invoke`." | It requires the call-site static signature to match the handle type exactly. |
| "Composing filters always preserves varargs collector." | These adapters have fixed arity; varargs must be handled separately. |

## 10. Self-Check and Practice

**Question 1.** `target` has type `(int,long)double`, while `f0` is `(String)int` and `f1` is `(String)long`. What is the signature of `filterArguments(target, 0, f0, f1)`?

**Answer:** `(String,String)double`. Both parameter types are replaced at positions 0 and 1; the `double` return type is unchanged.

**Question 2.** With the same target, what is the signature of `filterArguments(target, 1, f1)`?

**Answer:** `(int,String)double` because only position 1 changes from `long` to `String`.

**Question 3.** Target `(int)long` and filter `(String)int`: can you use `filterReturnValue(target, filter)`?

**Answer:** No. The output filter must accept `long` because the target returns `long`; the stated filter accepts `String`.

**Question 4.** Target `(int)void`, filter `()String`: can you use `filterReturnValue`? What is the adapter type?

**Answer:** Yes. The filter takes no parameters and runs after the target returns; the adapter type is `(int)String`.

**Question 5.** Target `(String)String`, post-processing filter `(String)void`: what is the adapter type?

**Answer:** `(String)void`. The filter receives the `String` result and returns no value to the caller.

**Question 6.** There are three input filters at positions 0, 1, 2. The second filter throws `IllegalArgumentException`. Do the third filter and the target run?

**Answer:** No. The first filter has run, the second filter fails, execution stops, and the exception is propagated to the caller.

**Question 7.** Target has a `long` parameter, filter is `(String)int`. Calling `filterArguments` throws `IllegalArgumentException` even though Java has widening `int → long`. Why?

**Answer:** The combinator requires **the filter's return type to equal the target's parameter type**; it does not perform implicit widening. Fix the filter to `(String)long` or adapt it validly and explicitly.

**Question 8.** How does `filterArguments(target, 0, null, f1)` differ from `filterArguments(target, 0, f0, f1)`?

**Answer:** In the first form, position 0 is kept unchanged and only position 1 is filtered; in the second form, both arguments are filtered. `null` in the filters array represents identity, not a null input.

**Question 9.** When target returns `long` and `format` accepts `long`, calling `(String) pipeline.invokeExact(...)` still throws `WrongMethodTypeException`. What should be checked?

**Answer:** The final `pipeline.type()` and the static types of **every argument** at the call site, plus the cast/return context of `invokeExact`. The error may be caused by the call site passing `int` instead of `long`, or having a return context other than `String` even though the filter is right.

**Question 10.** When a filter needs to process both `quantity` and `unitPrice` to create an `Order`, can `filterArguments` do this with a single `(String,String)Order` filter?

**Answer:** Not directly. `filterArguments` requires each filter to be **unary** for a specific parameter. See `collectArguments` or `foldArguments` to combine multiple inputs.

**Question 11.** Can `filterReturnValue` be used as a "finally block" that runs even if the target throws an exception?

**Answer:** No. If the target throws an exception, the output filter does not run. Cleanup on both success and failure paths requires another appropriate mechanism, such as `tryFinally` in `MethodHandles` or error handling at the application layer.

**Question 12.** If after creating the adapter, we reassign the local variable `target` to another handle, does the created adapter automatically change its target?

**Answer:** No. The adapter already holds a reference to the target handle passed at creation time; reassigning a Java variable does not modify that adapter's structure.

## 11. Key Takeaways

- `filterArguments`: **inputs → unary filters left to right → target**, can change argument types, but does not change the return type or arity.
- `filterReturnValue`: **target → output filter → caller**, preserves the parameter list, can change the return type; supports `void` targets and `void` filters with their respective signatures.
- **Types must match exactly:** an input filter returns the exact target parameter type; an output filter accepts the exact target return type. There is no overload resolution or implicit widening at composition time.
- **Use `MethodType` for verification:** `target.type()`, `filter.type()`, `adapter.type()` help catch errors early.
- **Exceptions propagate along the execution chain:** if a filter or target throws an exception, subsequent steps stop; calling through `MethodHandle` does not automatically wrap exceptions in `InvocationTargetException`.
- **`null` in `filters` is an identity filter**, not a rule for handling `null` inputs.
- **Compose with the right tool:** transform individual inputs with `filterArguments`, post-process outputs with `filterReturnValue`; use `collectArguments`/`foldArguments` for filters needing multiple inputs.
- **Keep access within scope:** combinators manage call flow, and do not grant permission to access classes/methods outside the current `Lookup`.

### Official Documentation (Java 17)

- [Oracle Java SE 17 — `MethodHandles.filterArguments` and `filterReturnValue`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html)
- [Oracle Java SE 17 — `MethodHandle.invokeExact` / `asType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html)
- [Oracle Java SE 17 — `MethodType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html)