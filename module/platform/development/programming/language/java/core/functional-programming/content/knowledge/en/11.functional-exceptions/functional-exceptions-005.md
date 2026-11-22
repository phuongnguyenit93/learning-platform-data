# Custom Functional Interfaces with `throws` When Truly Needed in Java

## 1. The Problem: Lambdas and Checked Exceptions

Java lambdas are type-checked against their target type (functional interface). Standard interfaces such as `Function<T,R>`, `Consumer<T>`, `Predicate<T>`, and `Supplier<T>` in `java.util.function` have a single abstract method (SAM) that **does not declare any checked exceptions**.

When logic needs to read a file, call a JDBC API, handle network I/O, or use a service with `throws IOException`/`SQLException`, many simple lambdas no longer compile if passed directly to those interfaces. You can catch locally, translate the error intentionally, or — **when the callback contract needs to preserve the checked exception** — create a custom functional interface with `throws`.

Objectives of this lesson:

- Recognize the `throws` limitation of standard SAMs and the cause of compilation errors.
- Design `ThrowingFunction<T,R,E extends Exception>` and `ThrowingConsumer<T,E extends Exception>` following the single-SAM rule.
- Propagate checked exceptions through callback-accepting APIs without losing the cause.
- Know when to use a regular method, `try/catch` inside a lambda, an `UncheckedIOException` adapter, or a result type representing both success and failure.
- Understand the differences when using sequential helpers versus APIs like `Stream.map`.
- Avoid overusing custom functional interfaces, hiding exceptions, forgetting to close resources, or creating uncontrolled side effects.

The standalone examples use **Java 17 or later**.

## 2. Background: Checked and Unchecked Exceptions

### 2.1. Checked Exceptions Are Part of a Compiler-Checked Signature

`IOException` and `SQLException` are checked exceptions: they extend `Exception` but are not under the `RuntimeException` branch. A code path capable of throwing a checked exception must either **catch** it or **declare it with `throws`** according to Java rules.

Example in a class importing `java.io.BufferedReader` and `java.io.IOException`:

~~~java
static String firstLine(BufferedReader reader) throws IOException {
    return reader.readLine();
}
~~~

`BufferedReader.readLine()` declares `throws IOException`, so the method above can propagate the error to the caller. There is no need to catch the error at a layer that does not know how to handle it.

Unchecked exceptions include subclasses of `RuntimeException` such as `IllegalArgumentException`, `NullPointerException`, and `UncheckedIOException`; subclasses of `Error` are likewise not subject to the checked exception rule. “Unchecked” does not mean safe, ignorable, or unnecessary to log.

### 2.2. Why Doesn't `Function` Accept a Lambda with `IOException`?

The abstract method of `Function<T,R>` is:

~~~java
R apply(T input);
~~~

It **does not declare `throws IOException`**. Therefore, the following snippet is **intentionally erroneous code**:

~~~java
Function<BufferedReader, String> read =
        reader -> reader.readLine(); // Unhandled IOException
~~~

This snippet does not compile, even if the enclosing method has `throws IOException`. The compiler checks the lambda body against the **throws clause of the SAM target type**, not solely against the method containing the lambda declaration.

Compare this with a valid way to handle it when an API requires a `Function`:

~~~java
Function<BufferedReader, String> read = reader -> {
    try {
        return reader.readLine();
    } catch (IOException ex) {
        throw new UncheckedIOException(ex);
    }
};
~~~

`UncheckedIOException` is a wrapper for a cause of type `IOException`; the caller can use `getCause()`. This is an **error policy decision**, not a mandatory fix. If the business logic can recover or requires the checked exception to remain intact, a different approach is needed.

## 3. When Do You Truly Need a Custom Functional Interface with `throws`?

You should only create one when these real needs exist together:

1. **You need to pass behavior** as a lambda/method reference to an API that you control.
2. That behavior legitimately throws **a checked exception type**; the error type is part of the contract, not a fault to be hidden.
3. **The site receiving the callback can propagate the exception up** to the calling layer; the caller knows how to choose retry, error reporting, skipping, rollback, or aborting the task.

An API used to read and transform multiple documents via a callback is a fitting scenario. The caller wants to know where `IOException` occurs; the helper lacks sufficient context to always convert it to `"UNKNOWN"` or swallow the exception.

**You do not need to create a custom interface** if the computation does not throw a checked exception; if the operation is only called in a regular `throws IOException` method; if a suitable specialized callback already exists; or if the error is already handled properly at the current boundary. Do not duplicate all of `java.util.function` with a `Throwing` suffix just “in case”.

| Need | Usually suitable solution |
| --- | --- |
| Pure data transformation | Standard `Function` |
| Logging or side effects without checked exceptions | Standard `Consumer` |
| A single file-reading method called directly | Regular method with `throws IOException` |
| Helper accepting an I/O callback that must preserve checked errors | `ThrowingFunction`/`ThrowingConsumer` |
| Stream requiring `Function` while the operation throws `IOException` | Intentional catch/wrap adapter or restructuring |
| Wanting to report per-item errors while still processing other items | `Result`/`Outcome` type or catching inside a loop |

## 4. Defining `ThrowingFunction` Yourself

~~~java
@FunctionalInterface
interface ThrowingFunction<T, R, E extends Exception> {
    R apply(T input) throws E;
}
~~~

Explanation:

- `T`: input type.
- `R`: result type.
- `E`: declared exception type, with bound `extends Exception`.
- `throws E` on the SAM: the callback is allowed to throw that exception type, and the caller handles it according to checked exception rules.
- `@FunctionalInterface`: the compiler verifies that the interface has exactly one abstract contract per the SAM rule.

Example:

~~~java
ThrowingFunction<BufferedReader, String, IOException> read =
        BufferedReader::readLine;
~~~

This is a snippet with appropriate imports. The method reference has a compatible signature `String apply(BufferedReader) throws IOException`. When calling `read.apply(reader)`, the compiler requires the call site to catch or declare `IOException`.

A specialized variant for I/O, often easier to understand if the API only does I/O:

~~~java
@FunctionalInterface
interface IOFunction<T, R> {
    R apply(T input) throws IOException;
}
~~~

Between generic `throws E` and concrete `throws IOException`, choose **the smallest and clearest contract** that the application needs. Generic is beneficial for reusable helpers; a fixed error type is often easier to read and catch.

### `throws E` Allows Rather Than Forces Throwing an Exception

~~~java
ThrowingFunction<String, Integer, IOException> length =
        String::length;
~~~

This example is valid even though `String.length()` does not actually throw `IOException`. The static type still signals that calling `length.apply(...)` **may** throw a checked exception; the caller must fulfill the handling obligation according to the signature. This is why you should not turn every helper into “throwing” by default.

An interface can have `default`, `static`, or `private` methods with bodies while still keeping a single SAM; do not add a second abstract method and expect lambdas to remain valid.

## 5. `ThrowingConsumer` and Related Signatures

If an action **does not return a result** but can throw a checked exception:

~~~java
@FunctionalInterface
interface ThrowingConsumer<T, E extends Exception> {
    void accept(T input) throws E;
}
~~~

Example calling `Writer.write`:

~~~java
ThrowingConsumer<String, IOException> write =
        text -> writer.write(text);
~~~

This is a snippet requiring an initialized `writer` variable of type `java.io.Writer` in scope. The lambda can throw `IOException`, so the site executing the callback must catch or declare this error. Creating the lambda **does not automatically close the resource**; the owner of `writer` needs to manage its lifecycle with `try-with-resources` or an equivalent mechanism.

When parameterless forms are genuinely needed, you can design:

~~~java
@FunctionalInterface
interface ThrowingSupplier<T, E extends Exception> {
    T get() throws E;
}

@FunctionalInterface
interface ThrowingRunnable<E extends Exception> {
    void run() throws E;
}
~~~

Do not add these interfaces to every module without a use case. A functional definition is an API contract that must be maintained, so only keep variants with clear value.

## 6. Helper `mapChecked`: Preserving Checked Exceptions to the Caller

~~~java
static <T, R, E extends Exception> List<R> mapChecked(
        List<T> inputs,
        ThrowingFunction<? super T, ? extends R, E> mapper)
        throws E {

    Objects.requireNonNull(inputs, "inputs");
    Objects.requireNonNull(mapper, "mapper");

    List<R> output = new ArrayList<>();
    for (T item : inputs) {
        output.add(mapper.apply(item));
    }
    return output;
}
~~~

This is a method placed in a class importing `java.util.List`, `ArrayList`, and `Objects`.

- `? super T` means the callback can accept a type that is as wide as or wider than `T`.
- `? extends R` allows the callback to produce a result that is a subtype of `R`.
- `throws E` on the helper indicates that checked errors from the callback are **forwarded**, not lost.
- The sequential loop processes each item; if `mapper.apply` throws an exception, processing stops at that item and the method does not return a normal result list.
- Side effects that already occurred for previous items **are not automatically rolled back**.

The caller can write:

~~~java
try {
    List<String> result = mapChecked(paths, path -> Files.readString(path));
    System.out.println(result);
} catch (IOException ex) {
    System.err.println(ex.getMessage());
}
~~~

This is an illustrative snippet inside a method with `paths` as `List<Path>` and imports for `java.nio.file.Files` and `IOException`; the syntax and type inference work cleanly when type inference resolves `E=IOException`. In production code, you need to log the full path, error cause, and decide whether to continue or stop. Catching an error and only printing the message is not a sufficient handling strategy for every requirement.

### `forEachChecked` for `void` Actions

~~~java
static <T, E extends Exception> void forEachChecked(
        Iterable<T> inputs,
        ThrowingConsumer<? super T, E> action)
        throws E {

    Objects.requireNonNull(inputs, "inputs");
    Objects.requireNonNull(action, "action");

    for (T item : inputs) {
        action.accept(item);
    }
}
~~~

The standard library's `Iterable.forEach` accepts `Consumer<? super T>`, which **does not declare checked exceptions**. This helper expresses a clear difference: the callback is allowed to `throws E` and the helper forwards the error to the caller. It is a sequential traversal, creating neither concurrency nor transactions.

### Why a Helper with `throws` Is Still Not Enough If the Callback Is `Function`?

~~~java
static <T, R> R execute(Function<T, R> fn, T value)
        throws IOException {
    return fn.apply(value);
}
~~~

This example can compile on its own, but having the helper `execute` declare `throws IOException` **does not allow a lambda passed to `Function` to throw an unhandled `IOException`**. The throws rule still belongs to the SAM `Function.apply`. You must fix the target type, handle the exception inside the lambda, or write an adapter.

## 7. Adapter for `Stream.map`: When Forced to Use `Function`

`Stream.map` is defined to accept `Function<? super T, ? extends R>`; it does not accept `ThrowingFunction` directly. If you choose to wrap `IOException` as unchecked at **this boundary**, make the policy explicit:

~~~java
static <T, R> Function<T, R> uncheckedIo(
        ThrowingFunction<T, R, IOException> operation) {

    Objects.requireNonNull(operation, "operation");

    return input -> {
        try {
            return operation.apply(input);
        } catch (IOException ex) {
            throw new UncheckedIOException(ex);
        }
    };
}
~~~

Then:

~~~java
List<String> cleaned = raw.stream()
        .map(uncheckedIo(MyClass::firstLine))
        .toList();
~~~

This is a snippet: `MyClass` is a class with `firstLine(String) throws IOException`, and `raw` is `List<String>`. The adapter creates a `Function` satisfying Stream's signature. `IOException` from the callback is wrapped in `UncheckedIOException`, and `getCause()` remains the original I/O error. By catching only `IOException`, the adapter does not “swallow” `RuntimeException`, `Error`, or other errors.

**Do not use `UncheckedIOException` to arbitrarily wrap `SQLException` or any `Exception`**: its constructor takes an `IOException` cause. For other errors, use a dedicated wrapper type or strategy and preserve the cause.

### Streams Are Lazy, So Place Catch at the Right Time

~~~java
var pipeline = raw.stream()
        .map(uncheckedIo(MyClass::firstLine));
~~~

Creating the intermediate `map` pipeline usually does not invoke the lambda yet. The checked exception has been converted to unchecked, but **the exception can occur at the terminal operation** such as `toList()`, `collect(...)`, or `forEach(...)`. Therefore, the `try/catch` block must surround the pipeline execution point, not just the initialization line.

If an element causes an error, previous elements may have already performed side effects; wrapping the error does not roll back any operation. With parallel Streams, the order and number of tasks already started before the error propagates require even greater care. Do not put mandatory business logic in `peek` and assume it runs exactly once.

## 8. Complete Java 17 Program

The example uses `BufferedReader` over in-memory `StringReader` data so **no real files are needed**. `BufferedReader.readLine()` still declares `throws IOException`; a blank-line check creates an `IOException` branch that can be reliably tested.

Create the file **`CheckedFunctionsDemo.java`**:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.StringReader;
import java.io.UncheckedIOException;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.function.Function;

public class CheckedFunctionsDemo {

    @FunctionalInterface
    interface ThrowingFunction<T, R, E extends Exception> {
        R apply(T input) throws E;
    }

    @FunctionalInterface
    interface ThrowingConsumer<T, E extends Exception> {
        void accept(T input) throws E;
    }

    static <T, R, E extends Exception> List<R> mapChecked(
            List<T> inputs,
            ThrowingFunction<? super T, ? extends R, E> mapper)
            throws E {

        Objects.requireNonNull(inputs, "inputs");
        Objects.requireNonNull(mapper, "mapper");

        List<R> output = new ArrayList<>();
        for (T item : inputs) {
            output.add(mapper.apply(item));
        }
        return output;
    }

    static <T, E extends Exception> void forEachChecked(
            Iterable<T> inputs,
            ThrowingConsumer<? super T, E> action)
            throws E {

        Objects.requireNonNull(inputs, "inputs");
        Objects.requireNonNull(action, "action");

        for (T item : inputs) {
            action.accept(item);
        }
    }

    static <T, R> Function<T, R> uncheckedIo(
            ThrowingFunction<T, R, IOException> operation) {

        Objects.requireNonNull(operation, "operation");

        return input -> {
            try {
                return operation.apply(input);
            } catch (IOException ex) {
                throw new UncheckedIOException(ex);
            }
        };
    }

    static String firstLine(String input) throws IOException {
        try (BufferedReader reader =
                     new BufferedReader(new StringReader(input))) {

            String first = reader.readLine();
            if (first == null || first.isBlank()) {
                throw new IOException("empty first line");
            }

            return first.strip().toUpperCase(Locale.ROOT);
        }
    }

    public static void main(String[] args) throws IOException {
        List<String> raw = List.of(
                "  java\nignore",
                "  lambda\nignore"
        );

        // Preserve checked exception through helper.
        System.out.println(
                mapChecked(raw, CheckedFunctionsDemo::firstLine)
        );

        // ThrowingConsumer for actions that do not return a value.
        List<String> labels = new ArrayList<>();
        forEachChecked(raw, value -> labels.add(firstLine(value)));
        System.out.println(labels);

        // Stream requires Function: convert to unchecked at the boundary.
        System.out.println(raw.stream()
                .map(uncheckedIo(CheckedFunctionsDemo::firstLine))
                .toList());

        // IOException directly from helper.
        try {
            mapChecked(
                    List.of("okay", "  \nnext"),
                    CheckedFunctionsDemo::firstLine
            );
        } catch (IOException ex) {
            System.out.println("caught: " + ex.getMessage());
        }

        // IOException inside wrapper from Stream.
        try {
            List.of("  ").stream()
                    .map(uncheckedIo(CheckedFunctionsDemo::firstLine))
                    .toList();
        } catch (UncheckedIOException ex) {
            System.out.println(
                    "wrapped: " + ex.getCause().getMessage()
            );
        }
    }
}
~~~

Run with JDK 17+:

~~~bash
javac -encoding UTF-8 CheckedFunctionsDemo.java
java CheckedFunctionsDemo
~~~

**Exact stdout:**

~~~text
[JAVA, LAMBDA]
[JAVA, LAMBDA]
[JAVA, LAMBDA]
caught: empty first line
wrapped: empty first line
~~~

Result explanation:

1. `mapChecked` accepts the method reference `firstLine`, transforming `"  java\nignore"` and `"  lambda\nignore"` into `[JAVA, LAMBDA]`.
2. `forEachChecked` runs a lambda that can throw `IOException`, adding two results to the list. `List.add` returns a boolean, but the lambda is compatible with `void`; the boolean value is ignored.
3. The `uncheckedIo` adapter lets Stream accept the lambda through a standard `Function`; valid data returns the same list.
4. The first line `"  "` is `isBlank()`, so `firstLine` throws `IOException("empty first line")`. `mapChecked` propagates it out and the caller catches it directly.
5. In Stream, the same error is wrapped by the adapter into `UncheckedIOException`; `getCause()` provides access to the original `IOException`.

`main` declares `throws IOException` so the first helper calls comply with the checked exception contract, even though the sample data is valid. In real applications, an appropriate handling boundary will usually catch and handle it rather than letting the error terminate the program.

### Resources and `try-with-resources`

`firstLine` opens `BufferedReader` and closes it automatically upon completion or exception. For real files, sockets, or databases, closing the resource must belong to **the owner of the resource**, and a lambda must not be assumed to handle it on its own. `try-with-resources` also supports recording closing errors as **suppressed exceptions**; when analysis is needed, use `Throwable.getSuppressed()` alongside cause/stack trace. The example uses `StringReader` to avoid external data dependencies while still accurately demonstrating the `readLine() throws IOException` contract.

## 9. Alternatives to Custom Functional Interfaces

### 9.1. Catch and Recover Meaningfully

~~~java
Function<String, String> convert = value -> {
    try {
        return service.convert(value);
    } catch (SomeCheckedException ex) {
        return "UNKNOWN";
    }
};
~~~

This is a **non-standalone pattern**: `service`/`SomeCheckedException` only represent a real API. Only use the `"UNKNOWN"` fallback when it is the right business decision. Do not turn every I/O error into an empty result or `null`, because the caller might mistake an error for valid data.

### 9.2. Regular Method with `throws`

~~~java
static String load(Path file) throws IOException {
    return Files.readString(file);
}
~~~

This is an illustrative method requiring `Path`/`Files` imports. If you only call the method directly and have no need to pass a callback, there is **no compelling reason** to create `ThrowingFunction<Path,String,IOException>`.

### 9.3. Error Wrapper When Forced to Use Standard APIs

~~~java
Function<Path, String> load = file -> {
    try {
        return Files.readString(file);
    } catch (IOException ex) {
        throw new UncheckedIOException(
                "Cannot read: " + file, ex);
    }
};
~~~

The illustrative snippet uses a standard `Function`, preserves the cause, and adds path context. Wrapping propagates the error as unchecked; it **does not turn an error into success**. You need to determine at which layer the caller will catch the wrapper type.

### 9.4. Errors as Data When Processing Every Element

When you need to process 100 files and collect per-file errors, a fail-fast helper that throws on the first exception may not be suitable. You can return a data type containing status:

~~~java
record ReadOutcome(String file, String text, IOException error) {
    boolean success() {
        return error == null;
    }
}
~~~

This is an **illustrative record**, without enforcing invariants. A real design needs to clearly separate success and error branches (e.g., a sealed type) rather than allowing ambiguous states with both text and error. Returning `ReadOutcome` per element helps accumulate, report, selectively retry failed items, and avoid losing path context.

### Comparison Table

| Approach | Error type seen at caller | Suitable when |
| --- | --- | --- |
| Catch in standard lambda | Fallback, log, or wrapper per policy | Current layer has sufficient context |
| Custom functional interface `throws E` | Checked exception `E` | API needs a callback and explicit error propagation |
| `UncheckedIOException` adapter | Unchecked wrapper with `IOException` as cause | Mandatory Stream/`Function` boundary |
| Return stateful result | Error becomes data | Continuing remaining items, reporting multiple errors |
| Regular method `throws IOException` | Direct checked exception | No need to pass behavior through an API |

## 10. Common Mistakes

| Mistake | Why it is wrong or risky | Fix |
| --- | --- | --- |
| Assuming `throws` on the outer method fixes `Function`'s SAM | Checked exception checking is based on the target type | Use the right interface or catch inside the lambda |
| Making every callback a `ThrowingFunction` | Callers may have to handle checked errors unnecessarily | Use only when the contract requires it |
| Catching `Exception` and unconditionally returning `null` | Loses the cause and masks data errors | Only fall back when the contract allows it |
| Wrapping with `new RuntimeException()` without a cause | Loses the cause chain for debugging | Wrap with cause and context |
| Using `UncheckedIOException` for all checked exceptions | Constructor requires an `IOException` cause | Use an appropriate wrapper type or design |
| Thinking `Stream.map` runs immediately | Intermediate pipelines are typically lazy | Place catch around the terminal operation |
| Thinking helpers automatically roll back on error | Side effects before the error still persist | Handle transactions/compensation per business logic |
| Forgetting to close resources | Leaks handles/connections | Use `try-with-resources` in the right scope |
| Using `sneaky throws` to bypass the compiler | Hides checked exceptions from the contract | Propagate errors explicitly or wrap intentionally |
| Swallowing `InterruptedException` | Loses the cancellation/stop signal | Propagate or restore interrupt when needed |
| Using raw `Function`/unchecked casts | Loses type safety | Use full generics |
| Assuming `@FunctionalInterface` allows two SAMs | The annotation only checks for a single SAM | Keep exactly one abstract method |

### `InterruptedException` Requires Special Handling

A callback working with a blocking operation may throw `InterruptedException`. If the handling layer **cannot propagate the checked exception up** and must translate the error type, it usually needs to restore the interrupt with `Thread.currentThread().interrupt()` before exiting, according to the actual API contract. Do not catch broadly and ignore the thread's cancellation signal.

### Generic `E` Is Not a Way to “Trick” the Compiler

`E extends Exception` and `throws E` serve to describe an **error contract**, not an excuse to use `sneakyThrow` tricks to hide exception types from the caller. If a callback can throw multiple different checked exception types, the compiler may infer a broad supertype like `Exception`; the caller then has to handle that broad type. If an API only needs I/O errors, using a concrete signature `throws IOException` can be easier to use and semantically safer.

### Ordering, Concurrency, and Atomicity Issues

This lesson's `mapChecked` runs sequentially. It does not guarantee rolling back side effects; `Stream.parallel()` even less guarantees sequential processing order or safely synchronized shared mutable state. Converting checked to unchecked does not solve concurrency. If a callback has effects such as sending emails, debiting money, or updating a database, you must design retries, idempotency, and transactions separately.

## 11. Checklist for Designing Callback APIs with Exceptions

Before creating a custom throwing functional interface, check yourself:

1. Are you really **passing a lambda as a callback**, or do you just need a regular method?
2. Is a standard SAM already sufficient? Does the logic actually have checked exceptions or only `RuntimeException`?
3. Which checked exception type must be preserved? `IOException`, `SQLException`, or a domain type?
4. Which layer knows how to handle it and decide on retry, rollback, skipping, or error reporting?
5. Can `try/catch` be used directly in the lambda without losing business meaning?
6. If Stream is needed, how will the adapter wrap errors, where will the wrapper be caught, and who inspects the cause?
7. Where are resources opened and closed, including when the callback fails?
8. If the callback fails mid-way, how are side effects that already happened handled?
9. Does the caller need to **stop on the first error** or **aggregate errors across multiple elements**?
10. Does generic `throws E` make the API broader and harder to infer than necessary?
11. Is there any risk of hiding `InterruptedException` or stop signals?
12. Do tests cover the success path, checked errors, wrappers, and resource cases?

A good API is not one that “never throws errors”; it makes **error paths and handling responsibilities clearly visible**.

## 12. Practice Exercises

**Exercise 1 — Create `ThrowingSupplier`.** Define `T get() throws E` with `E extends Exception`. Write a method that uses this callback to read a line from `BufferedReader` and forward `IOException`. Compare with `Supplier<T>`, which does not support checked exceptions.

**Exercise 2 — Fix a broken lambda.** Given:

~~~java
Function<Path, String> read =
        path -> Files.readString(path);
~~~

Fix it (a) using `ThrowingFunction<Path,String,IOException>` and (b) using `Function` with `try/catch` converting `IOException` to `UncheckedIOException`. Explain the difference at the caller.

**Exercise 3 — Test fail-fast behavior.** Use `mapChecked` to read a list of three strings, where the second element has a blank first line. Observe the exception and explain why the third element is not processed if the helper does not catch errors.

**Exercise 4 — Catch at the execution point.** Create a Stream with `map(uncheckedIo(...))` without calling a terminal operation yet; then add `toList()` inside `try/catch`. Verify that the callback error appears when the pipeline runs rather than necessarily at declaration time.

**Exercise 5 — File-writing callback.** Write `forEachChecked` for `ThrowingConsumer<String,IOException>` using `Writer.write`. Place `try-with-resources` at the owner of the writer. Test a case where the callback throws an error and verify that the resource is still closed.

**Exercise 6 — Preserve the cause.** Create a wrapper `new UncheckedIOException("read failed", original)`. Write a test checking `getCause() == original` and the error information. Compare with a wrapper that does not pass the cause.

**Exercise 7 — Continue processing after errors.** Choose a way to represent success/failure for each document (record or sealed interface), instead of stopping on the first error. Explain how to keep the document identifier so failed items can be retried.

**Exercise 8 — When not to create a new interface.** An application has a method `loadConfig(Path) throws IOException` called in exactly one place and never passed as a callback. Explain why a regular `throws` method is easier to understand than a custom throwing interface; only switch to an interface when the need arises to pass behavior and preserve the error contract.

## 13. Self-Check Questions

1. **Why doesn't `Function<T,R>` allow a lambda to throw `IOException` directly?** The SAM `apply` does not declare that checked exception.
2. **Is adding `throws IOException` on the method containing the lambda enough?** No; the compiler checks the SAM's throws clause.
3. **How is `ThrowingFunction<T,R,E>` different?** It has `throws E` on the SAM, allowing checked errors to be propagated.
4. **What does `ThrowingConsumer` do?** It accepts one input, returns `void`, and can throw the declared checked exception.
5. **When do you not need to create a custom interface?** When you do not need a callback with a checked exception or a regular method suffices.
6. **Does `Stream.map` accept `ThrowingFunction` directly?** No; it accepts `Function`. You need an adapter or another handling approach.
7. **Why does `uncheckedIo` only catch `IOException`?** Because `UncheckedIOException` is designed for `IOException`.
8. **After catching the wrapper, how do you read the original error?** Use `getCause()`.
9. **Why is `try-with-resources` important?** It closes resources even when an error occurs and supports suppressed exceptions.
10. **Should you swallow exceptions just to stop compiler errors?** No; you must have a clear error policy.
11. **Does a custom functional interface with `throws` make errors disappear?** No; it turns the error into a contract for the caller.
12. **Should you create dozens of throwing interface variants up front?** No, only define signatures that are actually used.

## 14. Summary and References

**A custom functional interface with `throws` should be created when a checked exception is a genuine part of the callback contract.** For APIs you control, `ThrowingFunction`/`ThrowingConsumer` can preserve `IOException` or domain checked exceptions and propagate them to a layer with sufficient context to handle them. For APIs that only accept standard `Function`/`Consumer`, you need local catching, an intentional error-wrapping adapter, or a redesigned operation boundary.

Every approach must preserve the error cause, close resources appropriately, avoid swallowing interrupts, decide between fail-fast or error aggregation, and consider side effects before retrying. If there is no need to pass behavior via lambdas, **a regular method with `throws` is usually the simpler choice**.

Standard references: Java Language Specification sections **`11 Exceptions`**, **`15.27 Lambda Expressions`**; Java SE 17 Javadocs for **`java.util.function.Function`**, **`Consumer`**, **`java.io.IOException`**, **`UncheckedIOException`**, **`java.io.BufferedReader`**, **`java.util.stream.Stream`**, and **`AutoCloseable`**.
