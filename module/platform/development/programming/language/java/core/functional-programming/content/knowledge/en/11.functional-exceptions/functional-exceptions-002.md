# Why Don't `Function` and `Consumer` Declare Checked Exceptions?

## 1. The Answer from the API Signature

Two very common functional interfaces in `java.util.function` have their single abstract method (*SAM*) defined as follows:

```java
@FunctionalInterface
public interface Function<T, R> {
    R apply(T value);
}

@FunctionalInterface
public interface Consumer<T> {
    void accept(T value);
}
```

The signatures above are **abbreviated for illustration**; the actual JDK API also has default/static methods such as `Function.andThen`, `Function.compose`, `Function.identity`, and `Consumer.andThen`. The key point is that **`apply` and `accept` have no `throws` clause declaring checked exceptions**.

Therefore, when passing a lambda or method reference to a place expecting `Function<T,R>`/`Consumer<T>`, the compiler checks the lambda body against the `apply`/`accept` contract. An operation that can throw an uncaught **checked exception**, such as `IOException`, cannot be propagated directly through these methods. Java requires handling the checked exception on the spot or using a functional interface with an appropriate `throws` signature.

Example illustrating a compilation error:

```java
import java.io.IOException;
import java.util.function.Function;

static String load(String id) throws IOException {
    return id;
}

// WRONG: Function.apply(String) does not declare throws IOException.
// Function<String, String> loader = id -> load(id);
// Function<String, String> alsoBad = MyClass::load;
```

This is an example containing a `static` method to be placed inside a hypothetical class, not a standalone program. Because `load` declares `throws IOException`, the compiler cannot use that lambda/method reference as a `Function<String,String>` if the exception is unhandled. The error appears **at compile time**, regardless of whether a specific execution path actually throws `IOException`.

**Core takeaway:** this is an **API signature design decision** and a consequence of **target-type exception checking for lambdas** in Java. There is no rule saying all lambdas forbid checked exceptions; the restriction arises when the target functional interface does not allow throwing that checked exception type.

## 2. Distinguishing Checked and Unchecked Exceptions

Java has different groups of throwables:

| Group | Examples | Compile-time check |
| --- | --- | --- |
| Checked exception | `IOException`, `SQLException`, `ParseException`, `InterruptedException` | Must be caught or declared to propagate through a permitting signature |
| Unchecked exception (`RuntimeException` and subclasses) | `IllegalArgumentException`, `NullPointerException`, `UncheckedIOException` | Not required to declare `throws` |
| `Error` and subclasses | `OutOfMemoryError`, `StackOverflowError` | Not checked exceptions; usually unsuitable for recovery like business errors |

A checked exception is a subclass of `Throwable` that is **not** a `RuntimeException` or `Error` or a subclass of either. Unchecked exceptions can be propagated through `Function.apply`/`Consumer.accept` even though neither method has a `throws` clause.

Example:

```java
Function<String, Integer> parse = Integer::parseInt;
System.out.println(parse.apply("42")); // 42
// parse.apply("abc"); // Throws NumberFormatException (unchecked).
```

`Integer.parseInt` can throw `NumberFormatException`, which is a `RuntimeException`. Therefore, the method reference above is still valid. "Does not declare checked exceptions" **does not mean** "never throws exceptions".

### Compile-time rule based on declared types

Java evaluates **an expression's potential to throw checked exceptions based on method declarations**, rather than waiting for runtime. A method declaring `throws IOException` will cause the compiler to require compatible handling, even if the current sample data does not make it throw an error. This allows the compiler to detect constraints before runtime.

Example:

```java
static String read(String code) throws java.io.IOException {
    if (code.equals("BAD")) {
        throw new java.io.IOException("cannot read");
    }
    return code;
}
```

You cannot directly use `Function<String,String> f = Example::read` if `read` is a method in the `Example` class as shown above. You must choose an appropriate exception-handling approach. Whether an exception occurs with `"GOOD"` does not change the type incompatibility.

## 3. Why Did `java.util.function` Choose Simple Signatures?

`Function` and `Consumer` are **general-purpose functional interfaces**, used across many APIs: `Stream.map`, `Stream.forEach`, `Optional.map`, `Map.computeIfAbsent`, callbacks, data transformers, etc. The JDK design chose concise SAM signatures without extra type parameters or `throws` clauses for checked exceptions.

Practical consequences:

1. **Simple to use for pure in-memory operations.** Many mappers/consumers only transform data, compare values, or record results locally and have no need to propagate checked exceptions.
2. **A uniform contract for general APIs.** `Stream.map` accepts `Function<? super T,? extends R>`, and `forEach` accepts `Consumer<? super T>`; APIs do not have to deal with a custom checked exception type on every lambda.
3. **Error policy is decided at application boundaries.** When a task touches I/O, databases, or networks, the author must choose to catch, convert, store errors as data, or define an interface with `throws`.
4. **The trade-off is overhead for I/O in pipelines.** A method reference to an API with `throws IOException` usually cannot be used directly as a `Function`. Adapter code or restructuring the processing flow is required.

One should not interpret this as "functional programming has no checked exceptions". Java still supports SAMs declaring checked exceptions, such as `Callable<V>.call() throws Exception`. The fact that `Function`/`Consumer` do not declare `throws` is **the specific contract of these two interfaces**, not a general limitation of all functional interfaces or lambdas.

## 4. Target Type Context Determines Whether a Lambda Can `throws`

Lambdas are checked against their *target type*. Two interfaces with the same input/output types can differ in exceptions:

```java
import java.io.IOException;
import java.util.function.Function;

@FunctionalInterface
interface CheckedLoader {
    String load(String id) throws IOException;
}
```

With the method `static String fetch(String id) throws IOException`:

```java
// Valid: SAM declares throws IOException.
CheckedLoader good = id -> fetch(id);

// Invalid: Function.apply does not allow checked IOException.
// Function<String, String> bad = id -> fetch(id);
```

These are **illustrative** snippets; `fetch` and the declarations need to be placed in an appropriate class/method context. The difference does not lie in the `->` syntax: the same lambda can be valid for `CheckedLoader` yet invalid for `Function<String,String>`.

Method references are also subject to this rule:

```java
CheckedLoader good = Example::fetch;
// Function<String, String> bad = Example::fetch; // Does not compile.
```

`Example::fetch` is just a reference to a method; the compiler still must verify that the referenced method's checked exceptions match the `throws` clause of the target SAM.

### `try/catch` inside a lambda is allowed

`Function` does not forbid **calling** a method with checked exceptions if the lambda handles it itself:

```java
Function<String, String> safe = id -> {
    try {
        return fetch(id);
    } catch (IOException ex) {
        return "UNAVAILABLE";
    }
};
```

Here `IOException` is caught, so the lambda body no longer lets an unhandled checked exception escape from `apply`. Choosing the string `"UNAVAILABLE"` is just an example policy: in real systems, returning a default value can hide errors, so you must clearly define how to distinguish errors from valid data.

## 5. Three Common Handling Approaches

An operation with `throws IOException` when passed into `Function`/`Consumer` typically has three main design approaches:

| Approach | Observable outcome | Suitable when |
| --- | --- | --- |
| Catch and handle directly in the lambda | Lambda continues or returns a fallback | There is a clear recovery policy |
| Wrap into an unchecked exception | Pipeline fails if caller does not catch | Error must halt the operation, caller takes responsibility |
| Return the error as a value (*Result*) | Each item has a success/failure status | Need to process multiple items and report errors per item |

There is no single always-right solution. You must consider whether the problem requires **fail-fast** (stop at the first error) or **collect-all** (continue processing other items), whether there are side effects, whether retries are needed, or whether the root cause must be preserved.

Handling a checked exception by wrapping it into an unchecked one **does not turn an error into success**. You only change how the exception passes through the Java contract of `Function`/`Consumer`. The error still occurs at runtime; the only difference is that the compiler does not force every caller of `apply` to declare `throws`.

## 6. Complete Java 17 Example: Fail-Fast, Result, and Consumer with I/O

The program below simulates a data source that can throw `IOException`. It demonstrates:

- `Function<String,String>` created with an adapter wrapping checked `IOException` into `UncheckedIOException`.
- `Function<String,Outcome>` recording errors **per item**, so subsequent valid items can still be processed.
- `Consumer<String>` performing an action that can raise `IOException` and how the error propagates through `accept`.
- Preserving `IOException` as `cause` when wrapping exceptions, helping callers identify the root cause.

Create the file **`CheckedExceptionDemo.java`**:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.function.Consumer;
import java.util.function.Function;

public class CheckedExceptionDemo {
    @FunctionalInterface
    interface CheckedFunction<T, R> {
        R apply(T value) throws IOException;
    }

    @FunctionalInterface
    interface CheckedConsumer<T> {
        void accept(T value) throws IOException;
    }

    record Outcome(String value, String error) {
        boolean success() {
            return error == null;
        }
    }

    // Acts as a data read operation that can fail.
    static String readCode(String input) throws IOException {
        if (input.equals("IO")) {
            throw new IOException("source unavailable");
        }
        return input.trim().toUpperCase(Locale.ROOT);
    }

    // Acts as a write action that can fail.
    static void writeAudit(String code) throws IOException {
        if (code.equals("IO")) {
            throw new IOException("audit unavailable");
        }
        System.out.println("Audit: " + code);
    }

    // Adapter from an interface with checked IOException to JDK Function.
    static <T, R> Function<T, R> uncheckedFunction(
            CheckedFunction<T, R> action) {
        Objects.requireNonNull(action, "action");
        return value -> {
            try {
                return action.apply(value);
            } catch (IOException ex) {
                throw new UncheckedIOException(ex);
            }
        };
    }

    // Adapter for a void action.
    static <T> Consumer<T> uncheckedConsumer(
            CheckedConsumer<T> action) {
        Objects.requireNonNull(action, "action");
        return value -> {
            try {
                action.accept(value);
            } catch (IOException ex) {
                throw new UncheckedIOException(ex);
            }
        };
    }

    // Represents failure as data to continue per item.
    static Outcome readSafely(String input) {
        try {
            return new Outcome(readCode(input), null);
        } catch (IOException ex) {
            return new Outcome(null, ex.getMessage());
        }
    }

    public static void main(String[] args) {
        List<String> inputs = List.of(" book ", "IO", " pen ");

        Function<String, String> loader =
                uncheckedFunction(CheckedExceptionDemo::readCode);

        System.out.println("Fail-fast:");
        try {
            inputs.stream()
                    .map(loader)
                    .forEach(code -> System.out.println("Code: " + code));
        } catch (UncheckedIOException ex) {
            System.out.println("Caught: " + ex.getCause().getMessage());
        }

        System.out.println("Per-item:");
        List<Outcome> outcomes = inputs.stream()
                .map(CheckedExceptionDemo::readSafely)
                .toList();

        outcomes.forEach(outcome -> {
            if (outcome.success()) {
                System.out.println("OK: " + outcome.value());
            } else {
                System.out.println("ERROR: " + outcome.error());
            }
        });

        long count = outcomes.stream()
                .filter(Outcome::success)
                .count();
        System.out.println("Success count: " + count);

        Consumer<String> audit =
                uncheckedConsumer(CheckedExceptionDemo::writeAudit);

        audit.accept("BOOK");
        try {
            audit.accept("IO");
        } catch (UncheckedIOException ex) {
            System.out.println("Audit failed: "
                    + ex.getCause().getMessage());
        }
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac --release 17 CheckedExceptionDemo.java
java CheckedExceptionDemo
```

**Exact expected stdout:**

```text
Fail-fast:
Code: BOOK
Caught: source unavailable
Per-item:
OK: BOOK
ERROR: source unavailable
OK: PEN
Success count: 2
Audit: BOOK
Audit failed: audit unavailable
```

### Section-by-Section Explanation

**Fail-fast section:** `" book "` is converted to `"BOOK"`. The next element `"IO"` causes `readCode` to throw `IOException("source unavailable")`. The adapter catches that exception and throws `UncheckedIOException`. `forEach` does not continue printing the remaining codes in this sequential program; the outer `catch` prints `Caught: source unavailable`. Because it stopped at the error, there is no `Code: PEN` in this section.

**Result section:** `readSafely` catches `IOException` itself and returns an `Outcome` with `error`. Because no exception escapes into the stream, all three items are processed. The result is two successes (`BOOK` and `PEN`) and one failure (`source unavailable`). This is how to **turn exceptions into data** so the calling layer can decide how to handle each record.

**Consumer section:** `writeAudit` is `void` and can throw checked `IOException`. `uncheckedConsumer` creates a valid `Consumer<String>` by catching/wrapping the error. For `BOOK`, it prints `Audit: BOOK`. For `IO`, the `audit unavailable` error is wrapped and then caught by the caller, reporting `Audit failed: audit unavailable`.

**Point to distinguish:** the example uses `List.of` and a sequential stream with a deterministic input order. If switched to `parallelStream`, branches can execute concurrently; one branch throwing an exception **does not guarantee** that other branches have not already produced side effects. Therefore, the meaning of "stop at the first error" must be viewed in the context of sequential/concurrent pipelines and side-effect boundaries.

## 7. Creating an Interface with `throws`: Why It Works but Cannot Be Passed Directly to Stream

You can certainly define:

```java
@FunctionalInterface
interface ThrowingFunction<T, R> {
    R apply(T input) throws IOException;
}

@FunctionalInterface
interface ThrowingConsumer<T> {
    void accept(T input) throws IOException;
}
```

The signatures have `throws IOException`, so the following lambdas/method references are valid, assuming `readCode` and `writeAudit` are declared as in the program:

```java
ThrowingFunction<String, String> loader = CheckedExceptionDemo::readCode;
ThrowingConsumer<String> writer = CheckedExceptionDemo::writeAudit;
```

However, `Stream.map`'s signature accepts **`Function<? super T,? extends R>`**, not `ThrowingFunction`. Two interfaces do not automatically convert into one another even if they have the same number of parameters and return types. Java has target typing for lambdas/method references, **not automatic "structural subtyping" between two differently named interfaces**.

Therefore, the following is invalid:

```java
// WRONG: ThrowingFunction is not java.util.function.Function.
// inputs.stream().map(loader);
```

An adapter serves as the bridge:

```java
Function<String, String> adapted = uncheckedFunction(loader);
List<String> values = inputs.stream()
        .map(adapted)
        .toList();
```

This is a **component example**, assuming `loader`, `inputs`, and `uncheckedFunction` are already declared. If `inputs` contains `"IO"`, `toList()` throws `UncheckedIOException` unless the caller catches it. The adapter **does not make Stream change `map`'s signature or add checked exceptions to its signature**.

### Why does the example only declare `throws IOException`?

Because the example handles specific I/O data, using `CheckedFunction<T,R> throws IOException` keeps the adapter small and catches the exact exception type. In large projects, you may see generic interfaces like `ThrowingFunction<T,R,E extends Exception>`, but using them with JDK APIs still requires an adapter and an error conversion policy. You should not build a new exception hierarchy just to avoid a few lines of `try/catch` if the problem is simple.

## 8. `UncheckedIOException`: Preserving the Root Cause When Converting

`UncheckedIOException` is a subclass of `RuntimeException` dedicated to wrapping `IOException`. It takes an `IOException` in its constructor and retains the original exception in `getCause()`.

```java
try {
    readCode("IO");
} catch (IOException ex) {
    throw new java.io.UncheckedIOException(ex);
}
```

This snippet is placed inside a method. Wrapping allows a method that does not declare checked `IOException` to still propagate the error outward. Compared to `throw new RuntimeException(ex)`, `UncheckedIOException` describes the **I/O source** more clearly and allows callers to catch the exact type.

You should not write:

```java
// Discouraged code: loses original error information.
// catch (IOException ex) {
//     throw new RuntimeException("failed");
// }
```

The approach above discards `ex`, making the stack trace and cause chain hard to trace. If an additional message is needed, use `new UncheckedIOException("cannot load code", ex)` or an appropriate exception that preserves `cause`.

**Note:** `UncheckedIOException` is only for `IOException` and its subclasses; do not use it to wrap all checked exceptions such as `SQLException`. For other errors, you need a handling mechanism or exception type appropriate to the domain.

## 9. Catching Exceptions in Lambdas and Error Policies

Example of returning a default:

```java
Function<String, String> fallback = id -> {
    try {
        return readCode(id);
    } catch (IOException ex) {
        return "UNKNOWN";
    }
};
```

This is an illustrative snippet placed in a scope where `readCode` can be called. This approach is easy to write, but it carries a risk: `"UNKNOWN"` might collide with a valid data value. When reporting, the caller cannot distinguish "actually read UNKNOWN" from "read failed so returned UNKNOWN".

To preserve error semantics:

- Use **Result/Outcome** to represent success or failure for each item.
- Use **`Optional<R>`** if you only need to describe the presence/absence of a value and genuinely accept losing cause details.
- Wrap the exception as **unchecked** if the workflow should stop and let the caller handle it.
- Move I/O out of the pipeline if the task requires controlling retries, timeouts, transactions, or resources step by step.

Do not catch and silently ignore exceptions without a business decision, especially when processing payments, orders, or critical data imports.

### Should you catch `Exception` or `Throwable` for all errors?

Generally **no**. Catching too broadly can hide programming bugs, resource errors, or cause the system to continue in an unsafe state. The example adapter only catches `IOException` specifically so unexpected runtime errors still propagate, making diagnostics clearer.

For `InterruptedException`, when forced to handle it in a callback that does not declare `throws`, do not treat it like `IOException` and wrap it arbitrarily. If you cannot propagate the checked exception further, you usually need to **restore the interrupt flag** with `Thread.currentThread().interrupt()` and then terminate or convert to an error matching the contract, so the calling layer does not lose the cancellation signal. Set the policy according to the task type and the application's cancellation mechanism.

## 10. `try/catch` Scope Determines Per-Item vs. Whole-Pipeline Handling

The following two structures behave differently.

### Catching outside the terminal operation: stop at the first exception

```java
try {
    inputs.stream()
            .map(uncheckedFunction(CheckedExceptionDemo::readCode))
            .forEach(System.out::println);
} catch (UncheckedIOException ex) {
    System.out.println("Failed: " + ex.getCause().getMessage());
}
```

In the example's sequential stream, the mapper throws an error on `"IO"`, so the pipeline terminates with an error. Subsequent unprocessed items will not appear in stdout. If earlier steps had side effects, they **do not automatically roll back**.

### Catching inside the mapper: can continue to the next item

```java
List<Outcome> results = inputs.stream()
        .map(CheckedExceptionDemo::readSafely)
        .toList();
```

`readSafely` does not let `IOException` escape, so the stream processes all three items and collects three Outcomes. The application layer can classify, count errors, notify, and perform selective retries.

In large data processing pipelines, sometimes failed records must be written to an error list for correction while valid records are still imported. This is when *Result as data* is appropriate. When the contract requires **all-or-nothing**, a separate transaction/atomicity mechanism is needed; merely wrapping exceptions or catching inside lambdas does not guarantee atomicity.

## 11. `Consumer.andThen` and `Function.andThen` Still Follow the SAM's Exception Contract

`Function.andThen` chains two transformations, and `Consumer.andThen` chains two actions. They do not add the ability to propagate checked exceptions to `apply`/`accept`:

```java
Function<String, Integer> parse = Integer::parseInt;
Function<Integer, String> label = n -> "Number " + n;
Function<String, String> pipeline = parse.andThen(label);

System.out.println(pipeline.apply("7")); // Number 7
```

If `parse` throws an unchecked `NumberFormatException` on `"abc"`, `label` does not run. If a mapper wraps a checked `IOException` into `UncheckedIOException`, that unchecked exception will also propagate and the subsequent step is skipped.

Similarly:

```java
Consumer<String> first = value -> System.out.println("first " + value);
Consumer<String> second = value -> {
    throw new IllegalStateException("stop");
};

first.andThen(second).accept("A");
```

The line `first A` will be printed, and then `second` throws `IllegalStateException`. The fact that `Consumer.andThen` allows unchecked errors **does not mean** it catches checked exceptions or rolls back `first`'s side effects.

## 12. Related Situations in the Java Standard Library

**`Stream.map`/`forEach`:** require `Function` and `Consumer` from `java.util.function`, which have no checked exception `throws` in their SAM, so lambdas calling I/O APIs need an adapter or in-place handling.

**`Optional.map`:** also accepts `Function`. `Optional.map`'s signature does not automatically resolve checked exceptions; a method reference to a method with `throws IOException` still needs to be adapted.

**`Map.computeIfAbsent`:** accepts `Function<? super K,? extends V>`; a mapping function throwing an unchecked exception will cause the computation to fail according to the specific map's contract. Do not use I/O arbitrarily inside a mapping function without considering errors, side effects, and concurrency rules.

**`Callable<V>`:** `V call() throws Exception` is a functional interface that can propagate checked exceptions. For example, `Callable<String> task = () -> readCode("BOOK");` is valid if `readCode` declares `throws IOException`. However, `Callable` cannot replace `Function<T,R>` in `Stream.map` because `Callable.call()` takes no input, whereas `Function.apply(T)` takes one input.

**`Files.lines(Path)`:** opening the source can throw `IOException`; after opening, I/O errors while reading content can surface as `UncheckedIOException` during stream consumption. Therefore, you must manage resources with `try-with-resources` and handle errors at the right boundary, rather than assuming switching to a stream eliminates I/O risks.

## 13. Common Mistakes

| Mistake | Why it is wrong | How to handle |
| --- | --- | --- |
| "Lambdas cannot throw checked exceptions" | Lambdas can still use SAMs declaring `throws` | Check the target functional interface |
| `Function<String,String> f = this::readFile` when `readFile` throws `IOException` | `Function.apply` does not declare checked exceptions | Catch in lambda, use an adapter, or change the API |
| Assuming `Function` cannot throw any exception at all | Unchecked exceptions are still allowed | Distinguish checked and unchecked |
| Using `RuntimeException` without preserving cause | Hard to trace the error source | Wrap with the proper type and pass `cause` |
| Returning `null` or a default string for all errors | Loses distinction between errors and valid data | Use Result/Outcome or a clear fallback contract |
| Catching `Exception` and ignoring it | Can swallow bugs or serious errors | Catch specific error types, handle per policy |
| Retrying the entire pipeline after an I/O error | Can repeat already-succeeded side effects | Idempotency, transactions, checkpoints, or selective retries |
| Thinking `andThen` runs the next step even if the previous step fails | When an exception occurs, the next step does not run | Catch errors in the previous step if recovery is valid |
| Using parallel streams with mappers that have side effects | No order guarantee and risk of race conditions | Separate side effects, synchronize, or use pure pipelines |
| Forgetting to close I/O sources when creating Streams from files | Can leak file handles | `try-with-resources` |
| Catching `InterruptedException` and forgetting the interrupt flag | Can lose the task cancellation signal | Restore the interrupt flag or propagate error per contract |

## 14. Practice Exercises

1. Write a method `static String read(String id) throws IOException`. Try assigning `Function<String,String> bad = YourClass::read`, record the compiler error, and explain why it occurs even if the method might not throw an error for a valid input.
2. Create `@FunctionalInterface interface ThrowingFunction<T,R> { R apply(T value) throws IOException; }`, then assign the method reference `YourClass::read`. Why is the assignment valid, yet you cannot pass that variable directly to `Stream.map`?
3. Write an adapter from `ThrowingFunction<T,R>` to `Function<T,R>` using `UncheckedIOException`. Verify that when an input fails, `getCause()` is still the original `IOException`.
4. Write a `Function<String,Outcome>` to process the list `"A", "IO", "B"`. When `"IO"` fails, the result must still contain three Outcomes, with two successes and one failure.
5. Replace `List.of(" book ", "IO", " pen ")` with a list without `"IO"`. Predict how many `Code: ...` lines the fail-fast section prints and whether the `Caught: ...` line still appears.
6. Write a `Consumer<String>` that calls `writeAudit(String) throws IOException` and handles errors with `UncheckedIOException`. Compare it with a `CheckedConsumer<String>` that has `throws IOException`.
7. Write a `Function<String,Integer>` using `Integer::parseInt`. Why does `"abc"` throw `NumberFormatException` yet the compiler still accepts the method reference?
8. Convert the `readSafely` example to `Optional<String>`. What error information is lost compared to `Outcome`? In which business cases is that loss acceptable?
9. Design a file-processing function using `try-with-resources` that returns a list of data before passing it into a stream. Compare the pros and cons against streaming directly from the file.
10. State separate policies for `IOException`, `SQLException`, and `InterruptedException` inside a callback that does not declare checked `throws`. Why shouldn't you wrap all of them into `UncheckedIOException`?

## 15. Checklist When Designing a Pipeline with Error-Prone Operations

- Verify whether the **target SAM** of the lambda/method reference has `throws` for checked exceptions.
- Know **which checked exception types** the inner method declares.
- Clearly choose **fail-fast** or **per-item error handling**.
- If converting to unchecked, preserve **`cause`** and choose an appropriate exception type/name.
- Do not swallow errors or return ambiguous fallbacks when the business logic requires correctness/auditability.
- For `InterruptedException`, handle the cancellation signal and interrupt flag properly.
- Consider **side effects**, retries, idempotency, transactions, and I/O resources separately from stream logic.
- Test at least the valid case, invalid input, mid-pipeline failure, and post-error state.

**Remember:** `Function.apply` and `Consumer.accept` do not declare checked exceptions, so a lambda/method reference body used with them cannot let an unhandled checked exception escape. Java still allows lambdas to throw checked exceptions when a **matching functional interface** has a `throws` signature. When I/O is needed in a pipeline, choose a clear error policy: handle on the spot, convert to unchecked while preserving the cause, or represent errors as data.
