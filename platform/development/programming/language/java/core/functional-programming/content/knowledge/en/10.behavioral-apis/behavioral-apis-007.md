# Supplier to Defer Value or Message Creation in Java

## 1. What is `Supplier<T>` and why is it useful?

`java.util.function.Supplier<T>` is a **functional interface** representing a behavior that **takes no arguments and supplies a result of type `T`** when invoked. Its single abstract method (*SAM*) is:

~~~java
T get();
~~~

Example:

~~~java
Supplier<String> greeting = () -> "Xin chào";
String text = greeting.get();
~~~

Here, `Supplier<String>` is **a recipe for obtaining a string**, meaning that creating the lambda object itself does not require the string to be computed immediately. This is useful when creating the value is expensive, when the value is only needed in one processing branch, or when you want to construct a log/error message **only when it needs to be displayed**.

**Key takeaway:** `Supplier` supports **deferred evaluation** by encapsulating work as a behavior to be called later. However, it **does not automatically** decide when to call it, does not automatically cache the result, and does not automatically guarantee single execution. The caller or the API receiving the `Supplier` decides whether and when to invoke `get()`.

Quick comparison:

| Expression | When does the work happen? | Meaning |
|---|---|---|
| `String value = expensive();` | Immediately when executing the assignment | Creates the value directly, *eager* |
| `Supplier<String> s = () -> expensive();` | The work in the lambda body only runs when `s.get()` is called | Encapsulates work for deferral |
| `String result = s.get();` | Immediately at the `get()` call | Requests execution of the work |
| `Supplier<String> s = this::expensive;` | The `expensive()` call is deferred until `get()` | Method reference clarifies which method will run |

`expensive()` is just an illustrative name for an existing method. With a method reference of the form `this::expensive`, the receiver expression `this` is evaluated when creating the reference, but **the body of `expensive()` does not run** until `get()` is called.

## 2. Structure and target types of `Supplier`

A `Supplier<T>` has **no parameters** and **a result**:

~~~text
                  get()
Supplier<T>  ───────────────► T
               no input
~~~

Common ways to create a supplier:

~~~java
// Illustrative code inside a method, assuming required types are imported.
Supplier<String> constant = () -> "ready";
Supplier<StringBuilder> builderFactory = StringBuilder::new;
Supplier<Long> timestamp = System::nanoTime;
Supplier<List<String>> listFactory = ArrayList::new;
~~~

- `constant.get()` always returns the string `"ready"` according to the logic above; the cost of computing the value is negligible.
- `builderFactory.get()` invokes the constructor and creates a `StringBuilder` on each call, rather than creating it immediately upon assignment.
- `timestamp.get()` calls `System.nanoTime()` on each `get()`; the returned number is meant for measuring relative time intervals, not a calendar timestamp.
- `listFactory.get()` creates a new `ArrayList` each time. Each result can be a different object.

`Supplier` does not support primitive type arguments in generics. If you use `Supplier<Integer>`, the result is an `Integer` reference. When you want to return a primitive and avoid boxing, Java provides specialized interfaces:

| Functional interface | SAM | Result |
|---|---|---|
| `Supplier<T>` | `T get()` | Object of type `T` |
| `IntSupplier` | `int getAsInt()` | `int` |
| `LongSupplier` | `long getAsLong()` | `long` |
| `DoubleSupplier` | `double getAsDouble()` | `double` |
| `BooleanSupplier` | `boolean getAsBoolean()` | `boolean` |

For other types such as `float` or `short`, there is no corresponding specialized primitive supplier set in `java.util.function`; you can use a closely matching type or a wrapper type depending on the API.

A lambda has no standalone target type: `var s = () -> "ready";` is **invalid** because the compiler does not yet have a functional interface to assign the lambda to. Declaring `Supplier<String> s = () -> "ready";` or casting to the corresponding target type is valid.

## 3. Complete example: creating a value only when truly needed

Save as **`SupplierEvaluationDemo.java`**:

~~~java
import java.util.Locale;
import java.util.function.Supplier;

public class SupplierEvaluationDemo {
    private static int builds = 0;

    static String build(String value) {
        builds++;
        System.out.println("build:" + value + "#" + builds);
        return value.toUpperCase(Locale.ROOT);
    }

    static void printWhen(boolean enabled, Supplier<String> message) {
        if (enabled) {
            System.out.println("message=" + message.get());
        }
    }

    public static void main(String[] args) {
        Supplier<String> deferred = () -> build("deferred");

        System.out.println("created, builds=" + builds);
        printWhen(false, deferred);
        System.out.println("afterDisabled=" + builds);
        printWhen(true, deferred);
        printWhen(true, deferred);
        System.out.println("end=" + builds);
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac SupplierEvaluationDemo.java
java SupplierEvaluationDemo
~~~

Stdout output:

~~~text
created, builds=0
afterDisabled=0
build:deferred#1
message=DEFERRED
build:deferred#2
message=DEFERRED
end=2
~~~

**Exact step-by-step explanation:**

1. `() -> build("deferred")` creates a `Supplier<String>` but **does not call `build`** immediately. Therefore, the first line prints `builds=0`.
2. `printWhen(false, deferred)` takes the disabled branch and therefore **does not call `message.get()`**, keeping the build count at `0`.
3. `printWhen(true, deferred)` calls `get()`, executes `build` for the first time, prints `build:deferred#1`, and then receives `DEFERRED`.
4. Calling it again executes `build` once more and increments the counter to `2`. `Supplier` **does not automatically remember `DEFERRED`**.
5. The API here clearly defines **the condition that triggers the work**. Deferral comes from the coordination between `Supplier` and only calling `get()` when needed.

If you write `printWhen(false, () -> build("deferred"))`, the work still does not run; however, if the API takes a `String` and the caller passes `build("deferred")`, the call will be evaluated before the API checks the `enabled` flag.

## 4. Deferring log messages and error messages

### 4.1. Why shouldn't expensive log strings be constructed too early?

When logging, some messages require formatting large data, serializing objects, or computing statistics. If the log level is disabled, you usually do not want to pay that cost.

~~~java
// Assume details() is an expensive computation and logger is already declared.
logger.fine("details=" + details());          // details() runs before the fine call.
logger.log(Level.FINE, () -> "details=" + details());
~~~

In the second approach, `java.util.logging.Logger.log(Level, Supplier<String>)` takes a supplier that constructs the message. The logger only requests message construction when the message needs to be logged according to the log-level check; when `FINE` is disabled, the supplier body **does not need to be executed**.

The snippet above is illustrative; to compile in a real program, you need a `logger` variable of type `java.util.logging.Logger`, `import java.util.logging.Level;`, and the `details()` method.

A logging API that supports a supplier is not entirely the same as an API that takes a `String`. If an API only accepts `String`, writing `logger.fine(expensiveMessage())` still evaluates the message before the call; whether the log itself is skipped cannot undo the cost already incurred.

**Do not abuse side effects in a log supplier:** an expression like `() -> updateCounterAndBuildMessage()` should not be used to perform mandatory operations, because when logging is disabled, the supplier body may not run at all. The supplier's content should primarily **build a descriptive string**, not alter business results.

### 4.2. Error messages when checking for `null`

Java 8+ has the overload:

~~~java
Objects.requireNonNull(object, Supplier<String> messageSupplier)
~~~

When `object` is not `null`, the error message **does not need to be computed**. When `object == null`, this overload calls the supplier to obtain the message for `NullPointerException`.

Example:

~~~java
// Illustrative; assuming java.util.Objects and java.util.function.Supplier are imported.
String username = "alice";
String safe = Objects.requireNonNull(
        username,
        () -> "username must not be null"
);
~~~

Here the value of `safe` is `"alice"` and the message lambda is not called. In the null case, the message is constructed in the exception-throwing branch.

This deferral is valuable if constructing the message requires querying metadata, aggregating state, or building a long string. For cheap string literals, the overload taking a `String` can also be simpler and clearer. Do not mechanically convert every fixed message to a `Supplier`.

### 4.3. Complete program: message built only on failure

Save as **`SupplierMessageDemo.java`**:

~~~java
import java.util.Objects;

public class SupplierMessageDemo {
    private static int messagesBuilt = 0;

    static String makeMessage() {
        messagesBuilt++;
        System.out.println("construct message #" + messagesBuilt);
        return "value is required";
    }

    public static void main(String[] args) {
        String valid = Objects.requireNonNull("ok", SupplierMessageDemo::makeMessage);
        System.out.println("valid=" + valid + "; messages=" + messagesBuilt);

        try {
            Objects.requireNonNull(null, SupplierMessageDemo::makeMessage);
        } catch (NullPointerException ex) {
            System.out.println("error=" + ex.getMessage());
        }

        System.out.println("final messages=" + messagesBuilt);
    }
}
~~~

Compile and run:

~~~bash
javac SupplierMessageDemo.java
java SupplierMessageDemo
~~~

Stdout:

~~~text
valid=ok; messages=0
construct message #1
error=value is required
final messages=1
~~~

`SupplierMessageDemo::makeMessage` is a method reference to a `static` method that takes no parameters and returns `String` — matching the SAM of `Supplier<String>`. It is a **recipe for creating a message**, not an already-created message string.

If a message contains sensitive content, you must control what data goes into logs/errors. Deferring message creation reduces unnecessary work, but it does **not** by itself solve security, escaping, or error-display policy issues.

## 5. `Optional.orElse` and `Optional.orElseGet`: a common eager/lazy trap

The difference between the two methods:

~~~java
T orElse(T other)
T orElseGet(Supplier<? extends T> supplier)
~~~

- `orElse(other)` takes a **value** `other`. If you write `orElse(expensiveFallback())`, Java evaluates `expensiveFallback()` **before calling `orElse`**, even when the `Optional` already has a value.
- `orElseGet(supplier)` takes a **value-producing behavior**. The supplier is only called when the `Optional` is **empty**.
- When the fallback is cheap, has no side effects, and is already available, `orElse(constant)` can be simpler; there is no need to treat `orElse` as always wrong.

### Standalone Java 17 example

Save as **`SupplierFallbackDemo.java`**:

~~~java
import java.util.Objects;
import java.util.Optional;

public class SupplierFallbackDemo {
    private static int fetches = 0;

    static String fetchBackup() {
        fetches++;
        System.out.println("fetch #" + fetches);
        return "backup-" + fetches;
    }

    public static void main(String[] args) {
        Optional<String> found = Optional.of("primary");

        String eager = found.orElse(fetchBackup());
        System.out.println("eager=" + eager);

        String lazy = found.orElseGet(SupplierFallbackDemo::fetchBackup);
        System.out.println("lazy=" + lazy);

        String missing = Optional.<String>empty()
                .orElseGet(SupplierFallbackDemo::fetchBackup);
        System.out.println("missing=" + missing);

        String present = Objects.requireNonNullElseGet(
                "set", SupplierFallbackDemo::fetchBackup);
        System.out.println("present=" + present);

        String fallback = Objects.requireNonNullElseGet(
                null, SupplierFallbackDemo::fetchBackup);
        System.out.println("fallback=" + fallback);
        System.out.println("fetches=" + fetches);
    }
}
~~~

Run:

~~~bash
javac SupplierFallbackDemo.java
java SupplierFallbackDemo
~~~

Stdout:

~~~text
fetch #1
eager=primary
lazy=primary
fetch #2
missing=backup-2
present=set
fetch #3
fallback=backup-3
fetches=3
~~~

**Branch-by-branch analysis:**

1. `found.orElse(fetchBackup())` calls `fetchBackup()` immediately, producing `backup-1` even though `found` holds `primary`. `orElse` still returns `primary` and discards the computed fallback value.
2. `found.orElseGet(SupplierFallbackDemo::fetchBackup)` does not call the fallback-producing method because `found` has data.
3. `Optional.empty().orElseGet(...)` calls the supplier to create `backup-2` because there is no value.
4. `Objects.requireNonNullElseGet("set", supplier)` returns `"set"` and does not call the supplier; this overload has been available since Java 9.
5. `Objects.requireNonNullElseGet(null, supplier)` calls the supplier, producing `backup-3`; unlike `Optional.orElseGet`, `requireNonNullElseGet` requires the value provided by the fallback to also be **non-null**, otherwise it throws `NullPointerException`.

`Optional.orElseGet` is a clear example of **an API actively deciding when to call `get()`**. There is no "lazy" magic in every method just because a parameter is a lambda: the exact behavior depends on the contract of the API receiving the supplier.

## 6. Deferring object creation: zero-argument factory

Another useful application is providing a **factory** so an API can create objects on demand:

~~~java
Supplier<List<String>> factory = ArrayList::new;

List<String> first = factory.get();
List<String> second = factory.get();
~~~

This illustrative snippet requires importing `java.util.function.Supplier`, `java.util.List`, and `java.util.ArrayList`. Calling the factory twice creates **two new mutable lists**. `Supplier` does not mean creating an empty list at declaration time and returning the same object forever.

Distinguish two designs:

~~~java
List<String> shared = new ArrayList<>();
Supplier<List<String>> sameList = () -> shared;
Supplier<List<String>> newList = ArrayList::new;
~~~

- `sameList.get()` returns **the same list** on every call.
- `newList.get()` creates a new list on every call.
- Both have type `Supplier<List<String>>`, so looking at the type alone **cannot tell you** whether the value is fresh, immutable, cached, or thread-safe. You must read **the contract and implementation**.

This approach fits when you want to defer initializing a buffer, a strategy object, or a resource needed only in one branch. If an object manages resources such as a connection, stream, or file handle, do not use a supplier to obscure the resource-closing lifecycle; you still need try-with-resources or an appropriate lifecycle management mechanism.

## 7. Distinguishing deferral, stream laziness, asynchrony, and caching

Four ideas are easy to confuse, yet they are **not the same**:

| Concept | How it works | Example |
|---|---|---|
| Deferred value creation | Encapsulates work, executes when `get()` is called or triggered by the API | `Supplier<T>` |
| Stream laziness | Intermediate stream steps typically only run when a terminal operation is invoked | `stream.map(...).filter(...).toList()` |
| Asynchrony | Work can run on another thread, not necessarily waiting for `get()`/`join()` to start | `CompletableFuture.supplyAsync(supplier)` |
| Memoization (*caching*) | Computes once and returns the stored result according to a cache policy | A supplier wrapped by a custom cache class |

`CompletableFuture.supplyAsync(supplier)` accepts a `Supplier<T>` but **schedules the work to run** when the method is called. The work may start immediately on the executor, **without** waiting for anyone to call `future.join()`. `Supplier` only represents a zero-argument task, while the API itself defines the timing mechanism.

### 7.1. `Stream.generate` can call a supplier multiple times

~~~java
Supplier<String> next = () -> "x";
List<String> values = Stream.generate(next).limit(3).toList();
~~~

With the sequential stream in this example, `generate` produces elements through the supplier when the terminal operation `toList()` runs, and the result is `[x, x, x]`. It does not create an infinite data source at declaration time. Nor should you assume the supplier runs only once: the API uses it as a **source for generating multiple elements**.

The snippet above is illustrative and requires importing `java.util.function.Supplier`, `java.util.List`, and `java.util.stream.Stream`.

### 7.2. No memoization by default

~~~java
Supplier<Long> clock = System::nanoTime;
long first = clock.get();
long second = clock.get();
~~~

Two calls can return different values. However, even if a supplier returns the same value every time, that **does not prove caching exists**. For example, `() -> "constant"` performs no significant work, yet the supplier can still be called multiple times.

If you want to compute at most once, you need to design a dedicated cache wrapper and clearly define whether `null` is cached, whether errors are cached, how concurrency is handled, and when data is refreshed. A `final Supplier<T>` variable also **does not** mean the result is stored; `final` only prevents reassigning the variable/reference.

## 8. Error contracts, `null`, and thread safety

### 8.1. Can return `null` or throw an unchecked exception

`Supplier<T>.get()` does not forbid returning `null`. You must check the contract of the API consuming the supplier:

- `Optional.orElseGet(supplier)` can receive a null result and return null when the Optional is empty.
- `Objects.requireNonNullElseGet(value, supplier)` does not allow the fallback result to be null when `value` is null; otherwise it throws `NullPointerException`.
- `Objects.requireNonNull(obj, messageSupplier)` can receive a null message for `NullPointerException`; you should not rely on the message string in business logic.

`Supplier.get()` does not declare `throws` for checked exceptions. If value-creation logic requires I/O that throws `IOException`, you must handle it inside the lambda, wrap it in an unchecked exception if appropriate, or define your own functional interface with `throws` accepted by your API. You cannot write a lambda that lets a checked exception escape from `Supplier.get()` arbitrarily.

### 8.2. Not guaranteed to be thread-safe

If multiple threads call the same supplier, the lambda body can run concurrently, especially when the supplier captures state or is used in an asynchronous API. `Supplier<T>` does not enforce single-thread execution, locking, safe retries, or side-effect restrictions.

For example, in a multi-threaded application, `() -> ++counter` where `counter` is a mutable field does not automatically become an atomic operation just because its type is `Supplier<Integer>`. Depending on requirements, consider `AtomicInteger`, synchronization, immutable data, or a stateless factory.

### 8.3. Capture and when data is observed

A lambda can capture local variables that are `final` or **effectively final**:

~~~java
String prefix = "id:";
Supplier<String> id = () -> prefix + 42;
~~~

If `prefix` is reassigned after defining the lambda, the compiler reports an error because the variable is no longer effectively final. However, if a supplier captures **a mutable object**, the contents of that object can change before `get()` is called. Therefore, "deferral" also means the value is computed based on **the state at the time of invocation**, rather than automatically taking a snapshot at declaration time.

This is very important for logging: do not defer a reference to a mutable object and assume the message later will accurately reflect the state at the moment the event occurred.

## 9. Designing APIs that accept `Supplier` behavior

When designing a method, you can use `Supplier<T>` to clearly express "I don't need the value yet; give me a way to obtain it if needed."

For example, the following method uses a fallback when a check fails:

~~~java
static <T> T choose(boolean usePrimary, T primary, Supplier<? extends T> fallback) {
    return usePrimary ? primary : fallback.get();
}
~~~

This is an **illustrative method snippet** requiring `import java.util.function.Supplier`. `choose(true, primary, fallback)` does not call the supplier; `choose(false, primary, fallback)` calls it once according to the current method body.

**Important API note:** `primary` is a **value**, so if the caller writes `choose(true, computePrimary(), fallback)`, `computePrimary()` has already run before the `choose` call. If you want to defer both branches, the API must accept two suppliers:

~~~java
static <T> T chooseLazy(
        boolean usePrimary,
        Supplier<? extends T> primary,
        Supplier<? extends T> fallback) {
    return usePrimary ? primary.get() : fallback.get();
}
~~~

When calling it:

~~~java
// Assume computePrimary/computeFallback return String and the methods already exist:
String result = chooseLazy(
        condition,
        () -> computePrimary(),
        () -> computeFallback()
);
~~~

The method calls only one of the two suppliers, depending on `condition`. This is a **lazy branch selection** design, avoiding computing one branch only to discard its result.

You should not force every API to take a `Supplier`. When a value is always needed immediately, is cheap, and has no skip condition, a direct parameter of type `T` is usually easier to read. A supplier adds a layer of indirection and can make evaluation timing harder to predict if the API does not document it clearly.

## 10. More standard API examples using `Supplier`

| Java API | What is the Supplier used for? | When is the work requested? |
|---|---|---|
| `Optional.orElseGet(Supplier<? extends T>)` | Create a fallback value | When the Optional is empty |
| `Optional.or(Supplier<? extends Optional<? extends T>>)` | Create an alternative Optional | When the Optional is empty |
| `Objects.requireNonNull(T, Supplier<String>)` | Create an error message | When the object is null |
| `Objects.requireNonNullElseGet(T, Supplier<? extends T>)` | Create a non-null fallback | When the input value is null |
| `java.util.logging.Logger.log(Level, Supplier<String>)` | Create a log message | When the logger decides the message needs to be written |
| `Stream.generate(Supplier<? extends T>)` | Create stream elements | During stream consumption |
| `ThreadLocal.withInitial(Supplier<? extends T>)` | Initialize each thread's initial value | When the thread needs the value for the first time via `get()` |
| `CompletableFuture.supplyAsync(Supplier<U>)` | Provide work that produces an asynchronous result | When the task is executed by the executor after being scheduled |

This table also shows that the same `Supplier<T>` has **different triggering contracts**. You cannot infer "every supplier only runs when needed" without knowing how the API defines it: in `Stream.generate` it can run multiple times; in `Optional.orElseGet` it may run zero times; in `supplyAsync` it can run even if the caller has not waited for the result.

## 11. Common mistakes and how to fix them

### Mistake 1: Computing the fallback first and then wrapping it in a supplier

~~~java
// Wraps an already-computed value; no longer defers the work.
String alreadyBuilt = expensiveFallback();
Supplier<String> ineffective = () -> alreadyBuilt;

// Defers the actual call:
Supplier<String> deferred = () -> expensiveFallback();
~~~

If `expensiveFallback()` is called on the first line, the cost has already occurred. The first supplier only defers **returning an already-available value**, not **creating the value**.

### Mistake 2: Assuming `get()` only runs once

~~~java
Supplier<String> value = () -> expensiveFallback();
value.get();
value.get();
~~~

The code above invokes the lambda body **twice**. If you need a shared value, you must retrieve it once and store it in a variable, or use a clearly designed cache.

### Mistake 3: Confusing `Supplier<T>` with `Function<T,R>`

~~~java
Supplier<String> message = () -> "ready";                // No parameters.
Function<Integer, String> label = n -> "id-" + n;        // One parameter.
~~~

Using `Supplier` for work that needs input forces the design to capture external data. If the value changes based on a parameter on each call, `Function` is usually more appropriate.

### Mistake 4: Keeping mandatory side effects inside a message supplier

If mandatory logic such as writing an audit record or updating an order sits inside `() -> buildLogMessageAndSaveOrder()`, a disabled log branch will skip that logic as well. Execute business logic independently and use the supplier only to build **the descriptive part**.

### Mistake 5: Assuming a method taking a supplier always calls it exactly once

`Supplier` is a type, **not a promise about invocation count**. Read the contract of `logIf`, `orElseGet`, `Stream.generate`, `supplyAsync`, or your own method to know whether it may call 0, 1, or many times.

### Mistake 6: Judging performance solely from lambda syntax

Lambdas have callback creation/storage costs and indirect call overhead in some contexts; at the same time, they can avoid heavy work when a branch is unused. For very cheap value creation that is always needed, a supplier may bring no benefit. **Measure with a profiler/benchmark** when performance is a goal; do not conclude that `() -> x` is always faster than passing `x`.

### Mistake 7: Using results from an expired or unsafe supplier

If a supplier returns an object with a short lifecycle (connection, stream), calling `get()` multiple times may create extra resources or return an already-closed resource, depending on the implementation. You cannot infer resource-management guarantees from the `Supplier<T>` type alone.

### Mistake 8: Forgetting the error policy for fallbacks

`orElseGet` may skip calling the fallback when a value is present, but if the fallback actually runs and throws an unchecked exception, that exception still escapes. A supplier does not automatically retry or swallow exceptions. Your API must clearly define whether errors are propagated, translated, or handled.

## 12. Practical checklist for lazy values and lazy messages

When considering passing a `Supplier<T>`, check yourself:

1. Can the value-creation work **be skipped** in some branches?
2. Is the supplier encapsulating **actual work** or just returning an already-computed value?
3. **Who** will call `get()`, and at what time?
4. Can it be called **0, 1, or multiple times**? Can it be called concurrently?
5. Does the result need to be **cached**, or must a new one be created each time?
6. Can captured data change between creating the supplier and calling `get()`?
7. If the supplier returns `null` or throws an exception, does the receiving API handle it properly?
8. For logs/errors, are any mandatory side effects mistakenly placed in the callback?
9. For fallbacks, should `orElseGet` be used instead of `orElse` because the fallback is expensive or has side effects?
10. Do tests verify the **invocation count** in both used and unused branches?

A simple testing technique is to have the supplier increment a counter or record a marker when `get()` runs. The API's expectations should be written clearly: in a branch that does not need the data, the counter does not increase; in a branch that needs the data, it increases by the exact committed count.

## 13. Self-check questions

**Question 1.** Does `Supplier<String> s = () -> load();` call `load()` immediately upon declaration?

**Question 2.** Why does `Optional.of("x").orElse(expensive())` still call `expensive()`, while `Optional.of("x").orElseGet(() -> expensive())` does not?

**Question 3.** If the same supplier is called twice, does Java automatically cache the value from the first call?

**Question 4.** When does `Objects.requireNonNull(value, () -> buildMessage())` need to construct the error message?

**Question 5.** Why shouldn't mandatory data-update logic be placed in a supplier used only for logging?

**Question 6.** Do the two suppliers `() -> sharedList` and `ArrayList::new` share the same contract regarding the returned list?

**Question 7.** Does `CompletableFuture.supplyAsync(supplier)` wait until `join()` to start calling the supplier?

**Question 8.** If `Supplier<String>` returns `null`, does that always violate the `Supplier` interface?

**Suggested answers:** (1) No, it is only called when `get()` or the consuming API triggers it. (2) Because the argument to `orElse` is evaluated before the call, whereas `orElseGet` receives a callback and only calls it when empty. (3) No; if you want caching, you need a separate mechanism. (4) When `value == null`. (5) Because logging may be disabled and the callback will not run. (6) No: the first may return the same object, while the second typically creates a new one via the constructor. (7) No; the task can be scheduled and executed before `join()`. (8) No; `Supplier` allows the result to be a null reference, though the consuming API may forbid it.

## 14. Official documentation

- [Java SE 17 API — Supplier<T>](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Supplier.html): the `T get()` contract.
- [Java SE 17 API — Optional](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Optional.html): `orElse`, `orElseGet`, and `or`.
- [Java SE 17 API — Objects](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html): `requireNonNull` and `requireNonNullElseGet`.
- [Java SE 17 API — Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html): the `log(Level, Supplier<String>)` overload.
- [Java SE 17 API — Stream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html): `generate` and the lazy nature of the pipeline.
- [Java SE 17 API — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): `supplyAsync`.

**Remember:** `Supplier<T>` means **"give me a way to create/obtain `T` when needed"**, not "create `T` right now." The biggest benefits appear in **expensive fallbacks**, **messages needed only when a log/error is triggered**, and **factories that create objects on demand**. To use it correctly, you must understand **which API calls `get()`, when, and how many times**; a supplier does not automatically cache, does not automatically run asynchronously, and does not automatically guarantee thread safety.