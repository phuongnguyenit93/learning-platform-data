# Optional: `orElse()` Evaluates Its Argument Immediately, `orElseGet()` Calls `Supplier` When Needed

## 1. Why Do Two Similar-Looking Methods Behave Differently?

`Optional<T>` represents a value that is either **present** or **absent**. When you need to retrieve the value or use a fallback value, Java provides two methods:

```java
T orElse(T other)
T orElseGet(Supplier<? extends T> supplier)
```

The two signatures above are simplified forms from the `java.util.Optional<T>` API: `orElse` takes an **already-computed fallback value**, whereas `orElseGet` takes **the behavior for supplying the fallback value** via the `Supplier` functional interface.

The key difference:

- With `optional.orElse(expensiveFallback())`, Java **evaluates `expensiveFallback()` before calling `orElse`**, even when `optional` already holds a value.
- With `optional.orElseGet(() -> expensiveFallback())`, Java creates/passes a `Supplier` expression; **the lambda body only runs when `optional` is empty**.
- If the `Optional` has a value, both **return that value**, but computing the argument to `orElse` may have already caused overhead, side effects, or an exception.
- If the `Optional` is empty, `orElse` returns the already-computed fallback value, while `orElseGet` calls `Supplier.get()` to compute the fallback value.

This is a **method argument evaluation rule in Java**, not a special exception for `Optional`. Java evaluates arguments before executing the method call; passing a lambda allows deferring **the lambda body** until the API actively invokes it.

## 2. Exact Result Table

Suppose we have `Optional<String> value` and a `fallback()` method that returns `"backup"` while also logging:

| State of `value` | Expression | Does `fallback()` run? | Return value |
| --- | --- | --- | --- |
| `Optional.of("ready")` | `value.orElse(fallback())` | **Yes** | `"ready"` |
| `Optional.of("ready")` | `value.orElseGet(() -> fallback())` | **No** | `"ready"` |
| `Optional.empty()` | `value.orElse(fallback())` | **Yes** | `"backup"` |
| `Optional.empty()` | `value.orElseGet(() -> fallback())` | **Yes** | `"backup"` |

Therefore, **the return value may be the same, but the execution behavior is not**. When the fallback is just an already-available constant, the difference is usually negligible. When the fallback queries a database, makes an HTTP call, reads a file, creates a heavy object, writes logs, or updates metrics, the difference can affect both performance and correctness.

## 3. Runnable Java 17+ Example: Comparing All Four Cases

Save the file `OptionalFallbackDemo.java`:

```java
import java.util.Optional;

public class OptionalFallbackDemo {
    private static String fallback(String source) {
        System.out.println("fallback called: " + source);
        return "backup";
    }

    public static void main(String[] args) {
        Optional<String> present = Optional.of("ready");
        Optional<String> empty = Optional.empty();

        System.out.println("1. present + orElse");
        System.out.println("result=" +
                present.orElse(fallback("orElse")));

        System.out.println("2. present + orElseGet");
        System.out.println("result=" +
                present.orElseGet(() -> fallback("orElseGet")));

        System.out.println("3. empty + orElse");
        System.out.println("result=" +
                empty.orElse(fallback("orElse")));

        System.out.println("4. empty + orElseGet");
        System.out.println("result=" +
                empty.orElseGet(() -> fallback("orElseGet")));
    }
}
```

Compile/run:

```bash
javac OptionalFallbackDemo.java
java OptionalFallbackDemo
```

**Exact** output:

```text
1. present + orElse
fallback called: orElse
result=ready
2. present + orElseGet
result=ready
3. empty + orElse
fallback called: orElse
result=backup
4. empty + orElseGet
fallback called: orElseGet
result=backup
```

How to read the log:

1. In case 1, `fallback("orElse")` runs immediately before the `orElse` call. Even though `fallback called: orElse` was printed, the result is still `ready` because the `Optional` has a value.
2. In case 2, the `Optional` has a value, so the body `() -> fallback("orElseGet")` is not called; there is no fallback log.
3. In case 3, the `Optional` is empty, so the already-computed fallback value is returned.
4. In case 4, the `Optional` is empty, so `Supplier.get()` is called, which in turn runs `fallback("orElseGet")`.

You do not need to run the code to guess whether a branch executes: you only need to determine whether **the value is already computed before the call** or **a function to compute the value is passed in**.

## 4. Evaluation Order in Java: The Origin of Eagerness

Consider:

```java
String value = optional.orElse(loadDefault());
```

In terms of evaluation semantics, Java performs the following steps in order:

1. Evaluate the receiver expression `optional`.
2. Evaluate the argument `loadDefault()` to obtain a `String` object (or fail with an exception).
3. Call `orElse` with the obtained argument.
4. Inside `orElse`, choose the value inside `Optional` if present; otherwise choose the fallback argument.

Conceptual equivalent:

```java
String computedDefault = loadDefault(); // always called
String value = optional.orElse(computedDefault);
```

These two lines illustrate the cause of eagerness; they are not strictly equivalent in every context involving complex receiver evaluation, but for an ordinary `optional` variable, they clearly show that the argument is computed beforehand.

With:

```java
String value = optional.orElseGet(() -> loadDefault());
```

The API can hold the callback until it is needed. Behaviorally, only if `Optional` is empty does a call equivalent to `supplier.get()` occur, and the lambda body itself calls `loadDefault()`. If `Optional` has a value, the callback does not run.

A simple illustration of the value selection (not the official JDK source code):

```java
// Conceptual illustration; the value variable represents the value inside Optional.
T orElse(T other) {
    return value != null ? value : other;
}

T orElseGet(Supplier<? extends T> supplier) {
    return value != null ? value : supplier.get();
}
```

This is **generic-typed pseudocode** to express the selection branch, not two standalone methods you can paste directly into a Java file. It clarifies that `orElse` already receives `other` after the caller evaluates the argument, whereas `orElseGet` has the ability to call `supplier.get()` conditionally.

## 5. Distinguishing Evaluating a `Supplier`-Creating Expression from Running `Supplier.get()`

A subtle misconception is that “`orElseGet` makes **everything** in the argument lazy.” What is actually true is: **invoking the Supplier body is deferred**. However, Java still has to evaluate the expression used to create or obtain the `Supplier` object before calling `orElseGet`.

For example:

```java
optional.orElseGet(makeSupplier());
```

If `makeSupplier()` logs or initializes a resource, it still runs **immediately** to produce the `Supplier` object, even when `optional` already has a value. Only the Supplier's `get()` is called when `Optional` is empty.

Conversely:

```java
optional.orElseGet(() -> makeSupplier().get());
```

Here, **both the `makeSupplier()` call and `get()` are inside the lambda body**, so they only run when `Optional` is empty.

### Program to Test Creation and Execution Timing

Create `SupplierTimingDemo.java`:

```java
import java.util.Optional;
import java.util.function.Supplier;

public class SupplierTimingDemo {
    private static Supplier<String> makeSupplier() {
        System.out.println("create supplier");
        return () -> {
            System.out.println("invoke supplier");
            return "backup";
        };
    }

    public static void main(String[] args) {
        Optional<String> present = Optional.of("ready");
        Optional<String> empty = Optional.empty();

        System.out.println("Case A");
        System.out.println(present.orElseGet(makeSupplier()));

        System.out.println("Case B");
        System.out.println(present.orElseGet(
                () -> makeSupplier().get()));

        System.out.println("Case C");
        System.out.println(empty.orElseGet(makeSupplier()));

        System.out.println("Case D");
        System.out.println(empty.orElseGet(
                () -> makeSupplier().get()));
    }
}
```

Run:

```bash
javac SupplierTimingDemo.java
java SupplierTimingDemo
```

Output:

```text
Case A
create supplier
ready
Case B
ready
Case C
create supplier
invoke supplier
backup
Case D
create supplier
invoke supplier
backup
```

Case A proves that the `makeSupplier()` argument is still evaluated when calling `orElseGet`. Case B proves that a lambda whose body contains `makeSupplier().get()` defers both calls. For Cases C/D, `Optional` is empty, so `get()` actually runs.

Similarly, expressions in the capture part of a lambda or method reference can be evaluated when creating the callback; therefore, you must examine **exactly what is inside the callback body**. You should not infer from the word `Supplier` that all preparatory work outside the callback is automatically deferred.

## 6. When the Fallback Is Expensive, Has Side Effects, or May Throw an Exception

### 6.1. Unnecessary Cost When Data Is Already Present

An example design that easily causes waste:

```java
String name = findName(userId)
        .orElse(fetchNameFromRemoteService(userId));
```

This is an **illustrative snippet**, assuming `findName(...)` returns `Optional<String>` and `fetchNameFromRemoteService(...)` returns `String`. In the case where `findName` already found a result, the remote service call still happens before `orElse`.

A sensible approach when you only want to call the remote service if missing:

```java
String name = findName(userId)
        .orElseGet(() -> fetchNameFromRemoteService(userId));
```

Now the lambda body only runs when `findName` returns `Optional.empty()`.

**Important exception:** if the fallback is just a fixed value or an already-computed variable, `orElse` is usually more readable:

```java
String label = optionalLabel.orElse("Unknown");
```

There is no expensive call or side effect in the `"Unknown"` argument. Wrapping a constant as `() -> "Unknown"` rarely helps.

### 6.2. Side Effects Even When the Fallback Value Is Ignored

Suppose a `nextId()` method increments a counter and returns an ID. If you use:

```java
String id = optionalId.orElse(nextId());
```

the counter will increment **regardless of whether `optionalId` has a value**, because `nextId()` is called beforehand. If you only want to generate a new ID when missing:

```java
String id = optionalId.orElseGet(() -> nextId());
```

If the intention is to increment the counter on every processing step, write that side effect as an explicit operation; do not sneakily rely on fallback argument evaluation.

### 6.3. Exceptions from the Fallback Can Occur Even When `Optional` Has a Value

If `parseDefault()` throws an exception, then:

```java
String result = Optional.of("ready").orElse(parseDefault());
```

will fail **before `orElse` is called**, even though `Optional` contains `"ready"`.

Whereas:

```java
String result = Optional.of("ready")
        .orElseGet(() -> parseDefault());
```

does not run `parseDefault()`, because the value is already present. Both snippets assume a `parseDefault()` method that returns `String` and can throw an unchecked exception; they are illustrative snippets, not standalone Java files.

Note: `Supplier.get()` in `java.util.function.Supplier` **does not declare any checked exceptions**. If the fallback calls code that throws a checked exception, the lambda must handle or convert the exception according to the contract, or a separate appropriate callback API must be designed. You cannot use a lambda that throws an uncaught `IOException` directly in `orElseGet` and expect the compiler to accept it.

## 7. Example Pattern Counting How Many Times the Fallback Runs

The following program confirms that `orElseGet` does not cache the fallback result. Each call on `Optional.empty()` invokes the Supplier again. Create `OptionalCounterDemo.java`:

```java
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;

public class OptionalCounterDemo {
    public static void main(String[] args) {
        AtomicInteger calls = new AtomicInteger();
        Optional<String> empty = Optional.empty();
        Optional<String> present = Optional.of("stored");

        System.out.println(
                present.orElseGet(() -> "generated-" +
                        calls.incrementAndGet()));
        System.out.println("calls=" + calls.get());

        System.out.println(
                empty.orElseGet(() -> "generated-" +
                        calls.incrementAndGet()));
        System.out.println(
                empty.orElseGet(() -> "generated-" +
                        calls.incrementAndGet()));
        System.out.println("calls=" + calls.get());
    }
}
```

Run:

```bash
javac OptionalCounterDemo.java
java OptionalCounterDemo
```

Output:

```text
stored
calls=0
generated-1
generated-2
calls=2
```

`Optional` is a container describing whether a value is present or absent; calling `orElseGet` does not turn the fallback value into data remembered inside `Optional`. If you need a fallback computed at most once, that is an application-level **memoization/caching** requirement. `AtomicInteger` in the example is only for demonstration and clear call counting; it does not imply that `orElseGet` itself works asynchronously.

## 8. `Supplier`, Lambdas, and Method References

`Supplier<T>` is a functional interface with the method:

```java
T get();
```

It takes no arguments. This fits the model: **when a value is missing, ask a function to supply a value**.

One way to write it:

```java
String name = optionalName.orElseGet(() -> loadDefaultName());
```

If there is already a no-argument method with a compatible signature, you can use a method reference:

```java
String name = optionalName.orElseGet(this::loadDefaultName);
```

This is a snippet inside an **instance method** of a class that has a `loadDefaultName()` method returning `String`; it is not a standalone Java file.

For a static method, you can use `SomeClass::loadDefaultName`. Note that a method reference creates a function rather than calling the fallback method immediately, provided the receiver expression has already been validly evaluated. If the receiver of a bound method reference is computed by an expensive call, resolving the receiver may still happen immediately; examine the actual expression in each case.

Compare:

```java
// Defeats lazy evaluation: calls the method immediately to get a String.
optionalName.orElse(loadDefaultName());

// Properly lazy: calls the method only when absent.
optionalName.orElseGet(() -> loadDefaultName());

// Equivalent in terms of when loadDefaultName is called for
// a normal, already-existing receiver:
optionalName.orElseGet(this::loadDefaultName);
```

If the fallback depends on input values outside `Optional`, the lambda can capture `final` or effectively final variables:

```java
String fallbackCode = "GUEST";
String code = optionalCode.orElseGet(() -> fallbackCode);
```

This case demonstrates capture, but because the value `fallbackCode` is already available and cheap, `optionalCode.orElse(fallbackCode)` is also appropriate. Choose based on **actual cost and side effects**.

## 9. Cases with `null` and `Optional.empty()`

`Optional.of(null)` throws `NullPointerException` immediately at creation time. Use `Optional.ofNullable(value)` when the source might be `null`; it returns `Optional.empty()` if the argument is `null`.

Both fallback methods can return `null`:

```java
Optional<String> missing = Optional.empty();

String first = missing.orElse(null);
String second = missing.orElseGet(() -> null);
```

Both `first` and `second` are `null`. These are lines of code placed inside a method with `java.util.Optional` imported. Choosing a fallback does not turn a `null` result into a new `Optional`; the return type of `orElse`/`orElseGet` is still `T`, not `Optional<T>`.

Avoid passing `null` as the `Supplier` object itself:

```java
Optional.<String>empty().orElseGet(null);
```

This example **compiles but throws `NullPointerException`** at runtime because it must call `get()` on a `null` reference. When `Optional` has a value, the implementation may not access the Supplier; do not use that as an excuse to design APIs that pass a `null` Supplier.

Distinguish between `orElseGet` and `Optional.or(...)`:

- `orElseGet(Supplier<? extends T>)` supplies a **value `T`** when missing and returns a result of type `T`.
- `or(Supplier<? extends Optional<? extends T>>)` (Java 9+) supplies **a replacement `Optional`** when missing and continues returning `Optional<T>`.

With both, the callback is called when empty, but their purpose and return type differ. Do not use `orElseGet` to return an `Optional<T>` and accidentally create an `Optional<Optional<T>>`.

## 10. Comparison with Other Methods and Avoiding Misunderstandings

| Method | Result | Difference |
| --- | --- | --- |
| `orElse(other)` | `T` | The argument expression `other` is evaluated **before** calling the method |
| `orElseGet(supplier)` | `T` | `supplier.get()` is only called when `Optional` is empty |
| `orElseThrow()` | `T` | Returns the value when present, throws `NoSuchElementException` when empty |
| `orElseThrow(exceptionSupplier)` | `T` | Only creates the exception via Supplier when empty, then throws the exception |
| `or(optionalSupplier)` | `Optional<T>` | Only requests another `Optional` when empty |
| `ifPresent(action)` | `void` | Only runs the `Consumer` when a value is present; does not produce a fallback value |

Example:

```java
String name = optionalName.orElseThrow(
        () -> new IllegalStateException("Missing name"));
```

Creating `IllegalStateException` inside the lambda **only happens when the value is missing**. Compare with `orElseGet`: one uses a Supplier to create a replacement value, and the other uses a Supplier to create the exception to throw.

Do not confuse `Optional` with `Stream`. Rules such as *lazy* stream pipelines or short-circuiting of `Predicate.and` are separate API concerns. The decision here is based strictly on **the signature and contract of `orElse`/`orElseGet`**.

## 11. Choosing What to Write Based on Real Requirements

**Use `orElse` when:**

- The fallback value is a literal, enum, constant, or already-existing object, e.g. `orElse("UNKNOWN")`.
- The argument is cheap with no significant side effects; the code reads more clearly than constructing a callback.
- You **intentionally** want the argument expression to be evaluated regardless of whether `Optional` already has a value. In this case, make the intent clear; usually writing the side effect on a separate line is easier to understand.

**Use `orElseGet` when:**

- The fallback may cost CPU, I/O, resource allocation, or a remote service call.
- The fallback has side effects and must only run if the value is truly missing.
- The fallback may throw an unchecked exception and should only occur in the empty branch.
- The fallback must be computed from data available at call time; a lambda or method reference provides the exact behavior to run.

**Do not overuse `orElseGet`:** `orElseGet(() -> "UNKNOWN")` is not wrong, but it offers no clear benefit over `orElse("UNKNOWN")`. Conversely, `orElse(new LargeObject(...))` can create an unused object if `Optional` has a value; in that case, consider a callback.

Actual performance also depends on fallback complexity, how often elements are present/empty, and JVM optimizations. Do not claim that lambdas are always faster or slower: choose based on **execution contract** first, then measure if performance is an issue.

## 12. Common Mistakes to Avoid

1. **Thinking `orElse(expensive())` only calls `expensive()` when `Optional.empty()`.** Wrong: the argument is evaluated first, even with `Optional.of(value)`.
2. **Thinking passing `makeSupplier()` to `orElseGet` makes `makeSupplier()` lazy.** Wrong: the call that creates the Supplier still happens immediately; only `Supplier.get()` is controlled by `orElseGet`.
3. **Ignoring fallback side effects.** Incrementing counters, logging, making HTTP calls, or writing to a DB can happen even if the fallback value is ignored when written with `orElse`.
4. **Ignoring argument exceptions.** A fallback that throws in `orElse` can halt the program before the `orElse` method gets a chance to pick the present value.
5. **Confusing `Supplier<T>` with `T`.** `orElseGet` needs a Supplier object, not a value from `supplier.get()` called early. For example, `orElseGet(() -> fallback())` differs from `orElse(fallback())`.
6. **Assuming `orElseGet` caches the fallback.** No caching is provided by this API; if called multiple times on empty, the Supplier can run multiple times.
7. **Using `Optional.of(null)`.** Causes `NullPointerException`; consider `ofNullable` when the input value may be empty/null.
8. **Using `orElseGet(null)`.** When empty, it will be unable to call `get()`; always provide a valid Supplier.
9. **Mixing up return types.** `orElseGet` returns `T`; `or` returns `Optional<T>`. When you need to continue chaining as an Optional, use the appropriate API.
10. **Using a method reference without checking how the receiver is resolved.** The body is deferred, but the expression used to select the receiver for a bound method reference may already be evaluated eagerly.

## 13. Self-Check Exercise

Suppose we have:

```java
static String generate() {
    System.out.println("generate");
    return "guest";
}
```

With this snippet inside a method:

```java
Optional<String> a = Optional.of("admin");
Optional<String> b = Optional.empty();

System.out.println(a.orElse(generate()));
System.out.println(a.orElseGet(() -> generate()));
System.out.println(b.orElse(generate()));
System.out.println(b.orElseGet(() -> generate()));
```

Questions:

1. How many times does the line `generate` appear?
2. What value is printed after each call?
3. How does changing `a.orElse(generate())` to `a.orElseGet(() -> generate())` affect the output?
4. If `generate()` calls an external service and may throw an unchecked exception, why can switching methods affect correctness?

**Answer:** `generate` appears **three times**, corresponding to `a.orElse(generate())`, `b.orElse(generate())`, and `b.orElseGet(() -> generate())`. The printed values are `admin`, `admin`, `guest`, `guest` in order. Changing the first call to `orElseGet` eliminates the unnecessary `generate` call when `a` has a value. If using `orElse`, calling the service can cause unintended cost/side effects/exceptions even when the data is already present.

## 14. Rule of Thumb

Read every expression with the question: **“Is the argument an already-computed value or a function that will compute when needed?”**

```text
optional.orElse(fallback())
                └── fallback() runs before orElse is called

optional.orElseGet(() -> fallback())
                       └── the lambda body only runs if Optional.empty()

optional.orElseGet(makeSupplier())
                   └── makeSupplier() runs immediately;
                       supplier.get() only runs if Optional.empty()
```

When the fallback is an already-available value, `orElse` is simple and sensible. When the fallback is work that only needs to be done in the case of missing data, `orElseGet` expresses the intent accurately and avoids pointless execution. This is a key distinction to master when using `Optional` in Java and designing APIs that accept behavior via `Supplier`.

**References:** Java SE API for `java.util.Optional` (`orElse`, `orElseGet`, `orElseThrow`, `or`), `java.util.function.Supplier`; Java Language Specification §15.7 on evaluation order and §15.12 on method invocation expressions.
