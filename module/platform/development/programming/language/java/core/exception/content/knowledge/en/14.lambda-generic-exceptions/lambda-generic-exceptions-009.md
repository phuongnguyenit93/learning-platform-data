# Keeping a Clear Contract When Combining Stream and Fallible Operations in Java

`Stream` lets you describe a data-processing pipeline using operations like `map`, `filter`, `flatMap`, `forEach`, and terminal operations. However, when **an operation on an element can fail**, choosing how errors are propagated becomes a key part of the **method contract**. If left unclear, the program can easily swallow errors, return results with missing elements without explanation, lose the root cause, or close resources at the wrong time.

The most prominent issue in Java is that methods like `Stream.map` use `Function.apply`, whereas `Function.apply` **does not declare any checked exceptions**. An operation that reads a file or parses data via an API declaring `throws IOException` or a custom checked exception therefore **cannot automatically throw that checked exception out through a `map` lambda**.

There are three commonly used design policies:

1. **Fail-fast:** stop the pipeline at the first error and propagate a meaningful exception; commonly used when a result is only valid if all data is valid.
2. **Per-element results:** transform each element into a structured `Success` or `Failure` so all data is processed and expected errors are aggregated.
3. **Intentional recovery:** skip, replace, or retry an element **only when the contract permits it**, and record enough context so it does not create a false success.

There is no single right handling style for every pipeline. What must stay clear is: **which errors count as a failure of the entire operation, which are per-element data errors, which are recovered from, and which party is responsible for closing resources**.

## 1. Understanding Stream Properly Before Discussing Exceptions

A typical pipeline:

```java
List<Integer> values = List.of("2", "3", "4").stream()
        .map(Integer::parseInt)
        .filter(n -> n > 2)
        .toList();
```

This snippet is valid in Java 17+. `Integer.parseInt` can throw `NumberFormatException`, which is an **unchecked exception**, so passing the method reference to `map` does not violate checked exception rules.

`Stream` is a data-processing model, not an error-handling construct in itself. Distinguish between:

- **Sources**: `Collection.stream()`, `Stream.of(...)`, `Files.lines(...)`, etc.
- **Intermediate operations**: `map`, `filter`, `peek`, `flatMap`; in general, they only set up the processing steps and do not trigger traversal of the source.
- **Terminal operations**: `toList`, `collect`, `count`, `forEach`, `findFirst`, `anyMatch`, etc.; when executed, they trigger the necessary parts of the pipeline to produce a result.
- **Single-use**: once consumed, a stream is not a reusable pipeline; to process again, you must create a new stream from an appropriate source.
- **Close/ownership**: most collection-backed streams do not need closing, but streams created from I/O sources, such as `Files.lines`, may hold resources that require `close()`.

**Specifically:** a pipeline might not traverse every element: `findFirst` or `anyMatch` can terminate early, and an exception can also cut execution short. Do not assume that calling a terminal operation always runs every lambda once on every element.

## 2. Why Checked Exceptions Do Not Pass Through Regular `map`

The relevant signature in spirit:

```java
<R> Stream<R> map(
        java.util.function.Function<? super T, ? extends R> mapper);
```

This is a **simplified illustrative signature** of the `Stream` API. The `Function<T,R>` type has the functional method:

```java
R apply(T value);
```

This method **does not have `throws IOException`, `throws SQLException`, or `throws Exception`**. Therefore:

```java
static String load(String id) throws java.io.IOException {
    return java.nio.file.Files.readString(
            java.nio.file.Path.of(id));
}
```

is a valid Java method when placed in a class. But using it like this:

```java
// Intentionally DOES NOT COMPILE.
List<String> texts = ids.stream()
        .map(id -> load(id))
        .toList();
```

is invalid if `ids` is a `List<String>` and `load` declares `throws IOException`, because the lambda body can throw a checked exception that `Function.apply` does not allow.

### Adding `throws IOException` Outside Is Not Enough

For example:

```java
// Intentionally DOES NOT COMPILE.
static List<String> loadAll(List<String> ids)
        throws java.io.IOException {

    return ids.stream()
            .map(id -> load(id))
            .toList();
}
```

Even though `loadAll` has `throws IOException`, the lambda must still conform to **`Function.apply`'s contract**. The enclosing method's `throws` clause is not automatically "forwarded" into `map`'s function descriptor.

Key takeaway: **checked exception obligations are determined by the target functional type at the lambda creation site**. This is a compile-time mechanism, not an error that only surfaces at runtime.

## 3. Choosing a Fail-Fast Contract When All Data Must Be Valid

Suppose an operation needs to convert strings into positive order quantities. If one line is invalid, you can specify that **the entire operation fails**; the caller will not receive a list that "looks successful" while silently dropping lines.

With a parser that only throws unchecked exceptions:

```java
List<Integer> quantities = List.of("2", "oops", "5")
        .stream()
        .map(Integer::parseInt)
        .toList();
```

When the pipeline executes, `Integer.parseInt("oops")` throws `NumberFormatException`; `toList()` does not return a normal `List<Integer>` to the caller. Having already processed element `2` internally **does not guarantee a valid result list is returned**.

Downside: without adding context, the message or stack trace might not clearly identify which **line ID** caused the error. In that case, use an exception type carrying structured information.

### A Meaningful Wrapper

```java
static int parseQuantity(String id, String raw) {
    try {
        int value = Integer.parseInt(raw);
        if (value <= 0) {
            throw new IllegalArgumentException(
                    "quantity must be positive");
        }
        return value;
    } catch (NumberFormatException cause) {
        throw new IllegalArgumentException(
                "invalid quantity for item " + id,
                cause);
    }
}
```

This is an **illustrative method that compiles when placed in a class**. It preserves `NumberFormatException` as the cause and adds the item ID. However, for sensitive data, only include non-secret identifiers or correlation IDs in the message; do not log raw tokens or entire payloads.

If you want to handle errors programmatically by code instead of parsing messages, you can use a custom exception with `errorCode` and `itemId`. The complete example below will illustrate this.

## 4. Errors Surface When the Terminal Operation Runs: A Consequence of Laziness

Example:

```java
var pipeline = List.of("1", "bad", "3")
        .stream()
        .map(Integer::parseInt);
```

Right after declaring `pipeline`, element parsing **has not necessarily occurred yet**. The call:

```java
List<Integer> result = pipeline.toList();
```

is the terminal operation that triggers the required processing. `NumberFormatException` is observed when the terminal operation executes, even though the stack trace also includes the lambda/`Integer.parseInt` frames.

Practical consequences:

- Place `try-catch` around where **the pipeline is consumed**, not only where the pipeline is constructed.
- If a method only returns a `Stream` and the caller invokes the terminal operation, the error timing may belong to the caller, outside the `try-catch` of the stream-creating method.
- Do not return a `Stream` that lazily reads from a closed resource, because the caller executes the pipeline after the source-creating method has already exited scope.
- A short-circuiting terminal operation might not touch a failing element; **not seeing an exception is not enough to conclude all elements are valid**.

### `findFirst` Does Not Automatically Validate the Entire Source

```java
var first = List.of("2", "bad", "4")
        .stream()
        .map(Integer::parseInt)
        .findFirst();
```

This is valid Java. For this sequential ordered stream, `findFirst()` can return `Optional.of(2)` without parsing `"bad"`. It only needs the first element to complete. No exception **does not mean** the entire list passed validation.

If you need to validate all elements, choose a terminal operation and validation policy that actually processes everything, or model each result to record per-line errors.

## 5. Complete Java 17+ Example: Fail-Fast, Lazy, and Preserving Cause

This example uses a custom **checked exception** in the parser function, then converts it into an unchecked wrapper when forced to pass it into `Stream.map`.

Save file **`StreamFailFastDemo.java`**:

```java
import java.util.List;
import java.util.function.Function;
import java.util.stream.Stream;

public class StreamFailFastDemo {

    record Item(String id, String raw) {}

    static final class InvalidItemException extends Exception {
        private static final long serialVersionUID = 1L;

        private final String itemId;

        InvalidItemException(
                String itemId,
                String message,
                Throwable cause) {
            super(message, cause);
            this.itemId = itemId;
        }

        String getItemId() {
            return itemId;
        }
    }

    static final class ItemProcessingException
            extends RuntimeException {
        private static final long serialVersionUID = 1L;

        ItemProcessingException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    @FunctionalInterface
    interface CheckedFunction<T, R, E extends Exception> {
        R apply(T value) throws E;
    }

    static int parse(Item item) throws InvalidItemException {
        System.out.println("parse " + item.id());

        final int parsed;
        try {
            parsed = Integer.parseInt(item.raw());
        } catch (NumberFormatException cause) {
            throw new InvalidItemException(
                    item.id(), "not an integer", cause);
        }

        if (parsed <= 0) {
            throw new InvalidItemException(
                    item.id(), "must be positive", null);
        }

        return parsed;
    }

    static <T, R, E extends Exception> Function<T, R> failFast(
            CheckedFunction<T, R, E> action) {

        return value -> {
            try {
                return action.apply(value);
            } catch (RuntimeException ex) {
                throw ex;
            } catch (Exception cause) {
                throw new ItemProcessingException(
                        "stream conversion failed", cause);
            }
        };
    }

    public static void main(String[] args) {
        List<Item> items = List.of(
                new Item("A", "3"),
                new Item("B", "bad"),
                new Item("C", "5"));

        System.out.println("created pipeline");

        Stream<Integer> pipeline = items.stream()
                .map(failFast(StreamFailFastDemo::parse));

        System.out.println("before terminal");

        try {
            List<Integer> values = pipeline.toList();
            System.out.println("values=" + values);
        } catch (ItemProcessingException ex) {
            InvalidItemException cause =
                    (InvalidItemException) ex.getCause();

            System.out.println("failure=" + ex.getMessage());
            System.out.println("failing id=" + cause.getItemId());
            System.out.println("detail=" + cause.getMessage());
            System.out.println(
                    "root=" + cause.getCause()
                            .getClass().getSimpleName());
        }
    }
}
```

Compile and run with **JDK 17 or later**:

```bash
javac -encoding UTF-8 StreamFailFastDemo.java
java StreamFailFastDemo
```

**Expected exact stdout:**

```text
created pipeline
before terminal
parse A
parse B
failure=stream conversion failed
failing id=B
detail=not an integer
root=NumberFormatException
```

### Why Is There No `parse C`?

This sequential pipeline starts by processing element A, continues to B, and then the parser for B throws `InvalidItemException`. The `failFast` adapter wraps it in `ItemProcessingException`, and the exception escapes `toList()`. Because the terminal operation failed, the program does not continue to element C, nor does it print `values=[...]`.

This is the **fail-fast contract**: stop on the first error, and do not act as if all data was successfully converted.

### What Error Information Is Preserved

- Outer exception: `ItemProcessingException("stream conversion failed")` — expresses the failure at the stream layer.
- Direct cause: `InvalidItemException` — belongs to the validation layer and carries `itemId="B"`.
- Deep cause: `NumberFormatException` — the original technical parsing error.
- The caller can read `getItemId()` instead of parsing the message `"not an integer"`.

In real applications, you do not always need all three exception layers. The wrapping depth depends on abstraction boundaries and the caller's responsibilities. This example intentionally has multiple layers to show how causes and context are preserved.

### Why Does the Adapter Catch `RuntimeException` Separately?

`RuntimeException` extends `Exception`. If the adapter simply caught every `Exception` and wrapped it, it would wrap unrelated unchecked errors too, potentially obscuring a meaningful error layer or making the stack trace harder to read. The example preserves original unchecked errors as-is and only wraps checked exceptions that need a contract conversion.

Do not use a "sneaky throw" adapter to bypass checked exception checks without declaring anything to the caller. Even if an error can be thrown at runtime, the `Function` type at compile time does not express the responsibility of handling that checked exception.

## 6. When Should You Not Use Fail-Fast?

Suppose an import file has 10,000 records, and the user wants to fix **all invalid records in a single pass**. Stopping on the first error forces them to fix one line, re-run, and then discover another failing line. In this case, **collecting per-element results** may be more appropriate.

A clear contract:

```text
Input item
   |
   v
parse/validate
   |
   +----> Success(itemId, parsedValue)
   |
   +----> Failure(itemId, errorCode, safeMessage, cause?)
```

In this model, expected errors such as non-numeric data or out-of-range quantities **do not necessarily get thrown out of the pipeline**. They are represented as **result values**.

Benefits:

- Can continue processing subsequent elements after a validation error on an earlier element.
- The caller receives a list of errors with stable IDs and error codes.
- No need to inspect `getMessage()` strings to classify errors.
- Can count total successes/failures and display errors line by line.
- Distinguishes **expected data errors** from **unexpected infrastructure errors**.

However, this model **does not automatically guarantee atomicity or transactionality**. If the pipeline has already written external data per element, creating a `Failure` later does not roll back earlier side effects.

## 7. Using `sealed interface` and `record` for Structured Results

Java 17 supports `record` and `sealed interface`. They help define a clear result contract:

```java
sealed interface ParseOutcome permits Success, Failure {}

record Success(String itemId, int value)
        implements ParseOutcome {}

record Failure(String itemId, String code, String message)
        implements ParseOutcome {}
```

These are illustrative types. A `parse` function can return `ParseOutcome` without throwing checked exceptions for expected validation errors.

Using this return type in `Stream.map`:

```java
List<ParseOutcome> outcomes = items.stream()
        .map(MyParser::parse)
        .toList();
```

This call is **illustrative**, assuming `MyParser.parse` and `items` have matching signatures.

### Should You Put `Throwable` Into Every `Failure`?

Not required. For invalid user input, a `Failure(code, field, safeMessage)` may be enough to return to the UI. If technical diagnostics are needed, you can keep the cause internally in the result or log it in a structured way at the proper boundary. But **do not expose raw `Throwable` objects directly in public API DTOs**.

Also avoid keeping secret inputs inside result records; any record's auto-generated `toString()` could cause those fields to be printed into logs.

## 8. Complete Java 17+ Example: Collecting All Business-Valid Errors

Save file **`StreamResultsDemo.java`**:

```java
import java.util.List;

public class StreamResultsDemo {

    record Item(String id, String raw) {}

    enum ErrorCode {
        INVALID_INTEGER,
        NOT_POSITIVE
    }

    sealed interface Outcome permits Success, Failure {}

    record Success(String itemId, int value)
            implements Outcome {}

    record Failure(
            String itemId,
            ErrorCode code,
            String message,
            Throwable cause)
            implements Outcome {}

    static Outcome parse(Item item) {
        final int number;

        try {
            number = Integer.parseInt(item.raw());
        } catch (NumberFormatException cause) {
            return new Failure(
                    item.id(),
                    ErrorCode.INVALID_INTEGER,
                    "quantity must be an integer",
                    cause);
        }

        if (number <= 0) {
            return new Failure(
                    item.id(),
                    ErrorCode.NOT_POSITIVE,
                    "quantity must be positive",
                    null);
        }

        return new Success(item.id(), number);
    }

    public static void main(String[] args) {
        List<Item> items = List.of(
                new Item("A", "2"),
                new Item("B", "bad"),
                new Item("C", "0"),
                new Item("D", "4"));

        List<Outcome> results = items.stream()
                .map(StreamResultsDemo::parse)
                .toList();

        for (Outcome result : results) {
            if (result instanceof Success ok) {
                System.out.println(
                        "OK " + ok.itemId() + "=" + ok.value());
            } else if (result instanceof Failure bad) {
                String root = bad.cause() == null
                        ? "none"
                        : bad.cause().getClass().getSimpleName();

                System.out.println(
                        "ERR " + bad.itemId() + " "
                        + bad.code() + " cause=" + root);
            }
        }

        long successCount = results.stream()
                .filter(result -> result instanceof Success)
                .count();

        long failureCount = results.stream()
                .filter(result -> result instanceof Failure)
                .count();

        System.out.println("successes=" + successCount);
        System.out.println("failures=" + failureCount);
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 StreamResultsDemo.java
java StreamResultsDemo
```

**Exact stdout:**

```text
OK A=2
ERR B INVALID_INTEGER cause=NumberFormatException
ERR C NOT_POSITIVE cause=none
OK D=4
successes=2
failures=2
```

### Analysis

- A and D parse into positive integers, so they are represented as `Success`.
- B has the string `"bad"`. `NumberFormatException` is caught inside the parser and **converted into `Failure` data** with code `INVALID_INTEGER`.
- C parses to `0`, violating the positivity rule; it returns `Failure` with code `NOT_POSITIVE`. Since this is a direct validation error, `cause` can be `null`.
- The parser processes all four elements: no unchecked exception escapes to interrupt the stream at B or C.
- `successCount` and `failureCount` are computed using **two new streams from the `results` list**, without attempting to reuse an already-consumed stream.
- `ErrorCode` is structured data. Message wording or translations can change without breaking branching logic that would otherwise parse strings.

An important policy: **when the parser catches `NumberFormatException`, that is an expected data error**. The program should not go on to catch all `Throwable` and turn system errors like `OutOfMemoryError` into a normal `Failure` row.

## 9. Aggregating Results at the Boundary, Not Returning Missing Data Silently

In the collect-results model, after obtaining `List<Outcome>`, the caller needs to decide:

- If **every element succeeded**, return the list of values in the required order.
- If there is **any `Failure`**, return the error list and do not commit data, if the task requires all-or-nothing.
- If the contract allows **partial success**, return both successes and failures with explicit statuses.
- If an error is an **infrastructure** or unrecoverable error, you may still need to fail-fast rather than trying to continue.

Dangerous example:

```java
List<Integer> values = inputs.stream()
        .map(Parser::tryParse)
        .filter(java.util.Objects::nonNull)
        .toList();
```

This is an illustrative snippet where `Parser.tryParse` is assumed to return `null` on parse failure. If the API does not advertise a rule to drop invalid data, the result has fewer elements, yet the caller **does not know which elements failed or why**.

Instead, if skipping invalid lines is intentional, at least maintain policy-compliant logging, counts, or diagnostics and reflect that in the API name or result type. For audit requirements, a `Success/Failure` collection is usually clearer.

### `Optional` Does Not Replace Full Error Information

`Optional<T>` can represent "present or absent value", but **it does not carry error type, error location, or cause**. If the caller needs to distinguish validly missing data from invalid data or I/O failures, returning only `Optional.empty()` may provide too little information.

Use `Optional` when the absence of a value is a normal, contract-compliant outcome; use a structured `Failure` when **the reason for failure matters**.

## 10. Element Errors and Pipeline Errors Are Not the Same Kind

A pipeline can encounter multiple error sources:

| Error source | Example | Contract to consider |
| --- | --- | --- |
| Per-element validation error | `"abc"` is not a number | `Failure(itemId, INVALID_INTEGER)` or fail-fast |
| Allowed missing record | Lookup yields no result | `Optional` or structured "not found" result |
| I/O unable to read source | `Files.lines` cannot open file | Checked `IOException` at source-creation boundary |
| I/O during traversal | Error reading lines after opening | Unchecked `UncheckedIOException` may appear in pipeline |
| Parsing logic bug | Parser throws `IllegalStateException` due to bug | Do not turn into an input error by default |
| Error during `close()` | Reader fails to close | Inspect close exceptions and suppressed exceptions |
| Side-effect error | API writes data mid-`forEach` | Consider transactions, idempotency, and partial consequences |

A generic `processAll` API should not mask all these cases as `List.empty()` or `null`. It must let the caller know **what the conditions for returning a successful result are**.

## 11. Streams and Resource Sources: `Files.lines` Must Be Closed in the Right Scope

Unlike `List.stream()`, some streams have I/O sources that must be closed. For example:

```java
static List<String> readNonBlankLines(
        java.nio.file.Path path)
        throws java.io.IOException {

    try (java.util.stream.Stream<String> lines =
                 java.nio.file.Files.lines(path)) {

        return lines.filter(line -> !line.isBlank())
                .toList();
    }
}
```

This is a **valid illustrative Java method when placed in a class**. `Files.lines(path)` creates a stream holding a file resource that needs closing; `try-with-resources` ensures it is closed when leaving scope, even if `toList()` throws an exception.

Points to distinguish:

1. **Opening the source**: calling `Files.lines(path)` can throw checked `IOException` immediately on open.
2. **Reading during traversal**: I/O errors occurring after opening can be wrapped in `UncheckedIOException` when the stream executes its terminal operation, depending on the API contract.
3. **Closing**: `Stream.close()` runs via `try-with-resources`; `close` can have its own failure behavior depending on the source.
4. **Result after closing**: the `List<String>` produced by `toList()` is materialized data and no longer depends on continuing to read the stream.
5. **Do not return a live stream outside a just-closed scope**: the caller cannot expect to traverse an I/O source whose lifecycle has already ended.

### Anti-Pattern: Returning an Already-Closed Stream

```java
// Intentionally WRONG design, even though it may compile.
static java.util.stream.Stream<String> broken(
        java.nio.file.Path path)
        throws java.io.IOException {

    try (var lines = java.nio.file.Files.lines(path)) {
        return lines;
    }
}
```

When `broken` returns, `try-with-resources` has already called `close()` on the stream. The caller receives an **already-closed** stream object; traversing it or chaining further operations can fail, and it cannot be used to read the file as expected.

Two proper options:

- **Materialize the result inside the resource-owning scope**, like `readNonBlankLines` returning `List<String>`.
- **Transfer ownership explicitly** via an API returning `Stream<String>` that requires the caller to close it with `try-with-resources`, while clearly documenting responsibility and error timing.

If an API is designed to return a live stream, the stream-returning method itself **must not close it** before the caller uses it.

## 12. Relationship Between Checked Exceptions and `try-with-resources` in Streams

Even when element processing throws no checked exceptions, opening or closing the source can still fail.

Example:

```java
static long count(java.nio.file.Path path)
        throws java.io.IOException {

    try (var lines = java.nio.file.Files.lines(path)) {
        return lines.count();
    }
}
```

The method declares `throws IOException` for source-opening errors. During traversal, errors from the source may surface as `UncheckedIOException`. If both a primary processing error and a closing error occur, `try-with-resources` can record the closing error as a suppressed exception on the primary error according to the standard rules.

Do not claim that all I/O errors when using `Files.lines` automatically become checked `IOException` catchable outside the pipeline. Read each API's contract: checked at the source-opening boundary, unchecked while the stream processes data, and closing errors are distinct stages.

### Do Normal Streams Need `try-with-resources`?

`List.of("a","b").stream()` normally holds no resources that must be closed, because the data source is in memory. There is no need to wrap every stream in `try-with-resources` just for "style."

For `Files.lines`, `BufferedReader.lines`, or APIs creating streams from external connections/sources, read carefully **who owns the source, whether it needs closing, and whether closing the stream also closes the underlying source**. For instance, `BufferedReader.lines()` does not replace the responsibility to close the `BufferedReader` itself: you can write `try (BufferedReader reader = ...)` and then use `reader.lines()` inside that block.

## 13. A Small Program to Observe `Stream.close()` When a Pipeline Fails

The following code illustrates the effect of `try-with-resources` with a close handler even when the terminal operation throws an unchecked exception. This is **not a real file I/O example**; it only uses `onClose` to show the execution order.

Save file **`StreamCloseDemo.java`**:

```java
import java.util.stream.Stream;

public class StreamCloseDemo {

    public static void main(String[] args) {
        try (Stream<String> values =
                     Stream.of("1", "bad", "3")
                             .onClose(
                                     () -> System.out.println("stream closed"))) {

            values.map(Integer::parseInt)
                    .forEach(number ->
                            System.out.println("value=" + number));

        } catch (NumberFormatException ex) {
            System.out.println(
                    "caught=" + ex.getClass().getSimpleName());
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 StreamCloseDemo.java
java StreamCloseDemo
```

**Exact stdout:**

```text
value=1
stream closed
caught=NumberFormatException
```

**Explanation:** `forEach` encounters `"1"`, prints `value=1`; at `"bad"`, `Integer.parseInt` throws `NumberFormatException`. While exiting `try-with-resources`, `values.close()` is invoked and the `onClose` handler prints `stream closed`. Then `catch` catches the parse error.

Do not conclude from this example that every stream automatically closes right after a terminal operation runs. **`Stream` does not automatically call `close()` simply because `toList()` or `forEach()` was called**. Closing happened because of the `try-with-resources` construct.

## 14. Errors When Closing Sources and Suppressed Exceptions

If a pipeline fails and the source's `close()` also throws an exception, distinguish between the two events:

- **Primary exception**: occurs while processing elements or reading the source.
- **Cleanup exception**: occurs while closing the source/stream.

With `try-with-resources`, if the body already has a primary exception and `close()` throws another error, Java normally **preserves the primary exception** and attaches the close error to `getSuppressed()`. If the body is about to `return` and `close()` throws, the call can **throw the close error instead of returning the result**.

Skeleton example:

```java
try (SomeAutoCloseable resource = openResource()) {
    return process(resource);
}
```

This is **illustrative code**, requiring appropriate types/methods to be defined. Do not assume `process` succeeded just because it computed a value before closing.

When investigating an I/O pipeline failure, inspect the **cause chain and suppressed exceptions at every level** rather than only printing `getMessage()` of the outer wrapper.

## 15. Exceptions and Ordering in Sequential vs. Parallel Streams

With a **sequential stream** over a `List` having an *encounter order*, the examples above produce results along an easily observable traversal path.

With a **parallel stream**:

```java
items.parallelStream()
        .map(this::convert)
        .toList();
```

this is illustrative code; `items` and `convert` must be defined in an appropriate context.

Additional risks:

- Multiple elements can be processed **concurrently on different threads**.
- If multiple lambdas fail at the same time, **do not assume the "first in the list" error will be the exception reported first**.
- Some already-started tasks may still produce side effects before the pipeline terminates abnormally.
- The order of side effects/logs from `forEach` may not reflect encounter order.
- Unsynchronized shared state variables cause race conditions.
- **"Fail-fast" in the sense of stopping result production on error does not guarantee immediately halting every concurrently running task.**

If the policy requires reliably identifying **every error across all elements**, do not rely solely on an exception escaping `parallelStream().map(...).toList()`. A per-element result representation without unnecessary external side effects may be more suitable.

### Does `forEachOrdered` Solve Everything?

`forEachOrdered` enforces encounter order for the action of the terminal operation itself on an ordered stream, but it does not turn the entire parallel pipeline into side-effect-free sequential processing. Do not use it as a complete solution for shared mutable state risks or multiple concurrent errors.

For reliable auditing, prefer **structured result data**, clear aggregation rules, and transaction handling at the business layer.

## 16. Side Effects and Transactions: Do Not Confuse Stream With Transaction

Streams are well suited for **pure transformations**. However, many real-world pipelines perform write operations:

```java
orders.stream()
        .map(this::chargeCustomer)
        .toList();
```

This is **illustrative code** where `chargeCustomer` is assumed to have a payment side effect. If the third order fails, the first two orders **may already have been charged**. `toList()` throwing an exception does not automatically undo external effects.

This is a **transaction and idempotency** problem, not just Stream syntax.

Useful principles:

1. **Validate before producing side effects** whenever possible.
2. **Separate into two phases**: parse/validate data, then execute business actions under an explicit transaction policy.
3. If you must write per element, decide **whether partial success is permitted** and record the outcomes.
4. If all-or-nothing is required, use transactions or a compensation strategy appropriate for the target system.
5. Do not assume a checked exception wrapped as unchecked will automatically roll back external systems.
6. Avoid putting blocking I/O or long-running operations into `parallelStream` arbitrarily without evaluating concurrency/throughput.

A stream API returning `List` does not replace domain consistency design.

## 17. Fallback Patterns: Which Ones Are Appropriate?

One strategy:

```java
.map(raw -> {
    try {
        return riskyTransform(raw);
    } catch (SomeCheckedException ex) {
        return defaultValue;
    }
})
```

This is an illustrative skeleton, valid only if `riskyTransform`, `SomeCheckedException`, and `defaultValue` are appropriately defined. It can be fine if **a fallback is a permitted result**, but can be extremely dangerous if:

- `defaultValue` collides with a valid value so the caller cannot tell an error occurred.
- The actual error is degrading infrastructure.
- Retrying or alerting is needed, yet the exception was discarded.
- Error-handling responsibility belongs to an outer layer, not the mapper.
- Continuing to produce side effects on remaining elements leaves state hard to recover.

Therefore, describe the contract explicitly:

| Policy | When appropriate | What the caller needs to know |
| --- | --- | --- |
| **Fail-fast** | Task is valid only if all elements succeed; an error is an exception for the whole pipeline | Which exception type, and what codes/IDs/causes it carries |
| **Collect failures** | Bulk imports, validation where multiple errors should be reported | `Outcome` type, error codes, result list |
| **Skip invalid** | Problem allows dropping some data | Skip criteria, count of dropped items, auditability |
| **Fallback** | Clear business default value exists | Fallback condition and distinguishability |
| **Retry** | Transient errors, idempotent/controlled operations | Retry count, delay, retryable error classification |
| **Abort before side effect** | Task consistency is required | Separate validation and commit phases |

Do not let a mapper silently decide an ambiguous policy via `catch (Exception) { return null; }`.

## 18. Preserve Error Information Instead of Only Messages

A familiar principle in Java exceptions: **messages are for human readers; structured data is for programs**.

For per-element errors, an exception or result can carry:

- `itemId` or a safe line number.
- Stable error codes such as `INVALID_INTEGER` or `MISSING_FIELD`.
- Necessary business context, such as the field name.
- `cause` as the original error object when there is a technical cause.
- Diagnostic message containing no secrets.
- For cleanup errors, `getSuppressed()` on the appropriate Throwable.

Do not write logic like:

```java
if (ex.getMessage().contains("bad integer")) {
    // Business branching.
}
```

Because messages can change due to translation, versioning, or wording clarifications. In the fail-fast example, the caller uses `InvalidItemException.getItemId()` and the exception type. In the collect example, the caller uses `Failure`'s `ErrorCode`.

### Do Not Lose the Cause When Wrapping Exceptions

Code:

```java
throw new IllegalStateException(
        "conversion failed", original);
```

preserves `original` via the cause-accepting constructor, provided that variable exists and has the right type.

Code:

```java
throw new IllegalStateException(
        "conversion failed: " + original.getMessage());
```

does not automatically preserve the cause; the old exception's stack trace and suppressed exceptions are not attached to the new error merely because the message was copied. Wrap with a cause when genuinely translating contracts.

## 19. Do Not Use Unchecked Exceptions to Hide Design Flaws

An adapter like:

```java
catch (Exception ex) {
    throw new RuntimeException(ex);
}
```

can get code past the compiler, but without understanding the semantics it merely hides a checked contract. Questions to answer:

- Does the stream's caller know **when the pipeline fails**?
- Is the wrapper type meaningful, or just a generic `RuntimeException`?
- Is the cause still intact?
- Should errors be handled per element instead of thrown?
- Does the mapper run repeatedly or on different threads?
- Is there a better API boundary where a `for` loop propagates checked exceptions directly?

Sometimes the best solution is simply **not using a stream**:

```java
static List<String> loadAll(List<String> ids)
        throws java.io.IOException {

    List<String> values = new java.util.ArrayList<>();

    for (String id : ids) {
        values.add(load(id));
    }

    return values;
}
```

This is an **illustrative method**, with `load(String) throws IOException` defined in the same scope. With a loop, `loadAll`'s `throws IOException` directly describes the checked error without needing an unchecked adapter. If the goal is to preserve the exact checked exception type to the caller, an explicit loop is sometimes simpler than forcing it into `Function`.

**There is no requirement to use Stream at all costs.** Choose the tool that most clearly expresses the contract for results, errors, and side effects.

## 20. Three-Tier Testing: Compile Time, Pipeline Behavior, Result Contract

A good test suite verifies more than just the final list.

### A. Compile-Time Rules

Compilation tests or small examples to confirm:

- A lambda throwing a checked exception directly **cannot** be assigned to a `Function` that does not declare `throws`.
- A custom functional interface with `throws E` permits compatible checked exceptions.
- An adapter converting to `Function` has a clear policy and can be used with `Stream.map`.

### B. Fail-Fast and Cause

Verify:

- Valid data produces the right `List`.
- Invalid data causes the terminal operation not to return a false-success list.
- The outer exception has the contract's expected type/ID/error code.
- `getCause()` preserves the appropriate underlying cause object.
- When processing a sequential ordered stream with fail-fast logic, elements after the failure point are not processed further, as in the demo case.

Do not test against the full string output of `printStackTrace()`, because file names, line numbers, and frames can change.

### C. Collect-All

Verify:

- A `Failure` **does not interrupt the pipeline** if the parser turns validation errors into data.
- Total `Success + Failure` equals total input count when the policy is one result per element.
- Structured error codes and IDs are preserved.
- An unhandled infrastructure error still fails properly rather than silently turning into a validation `Failure`.
- Clear criteria exist to decide commit vs. rollback based on the result list.

### D. Resources and Terminal Operations

For `Files.lines` or closeable sources:

- The resource is closed on the success path.
- The resource is also closed when the terminal operation throws an exception.
- The caller does not use the stream after its owner has closed it.
- If `close` throws, primary/suppressed errors are preserved and handled properly.

## 21. Common Mistakes When Combining Stream and Fallible Operations

| Mistake or misconception | Consequence | Better approach |
| --- | --- | --- |
| Calling a `throws IOException` method directly in `map` | Does not compile if the checked exception escapes `Function.apply` | Catch/wrap, custom interface + adapter, or use a loop |
| Adding `throws IOException` to the outer method thinking the lambda is valid | Does not change `Function`'s contract | Handle directly at the descriptor boundary |
| Catching all `Exception` and returning `null` | Loses error reason, easily drops data | Structured results or fail-fast |
| `filter(Objects::nonNull)` after a parser returns null on error | Silently drops elements | Only skip if the contract allows it and auditing exists |
| Logging only `ex.getMessage()` | Loses stack, cause, and suppressed exceptions | Keep the Throwable and log at the proper boundary |
| Thinking building the pipeline already processed the data | Errors appear at the terminal operation | Place handlers where execution happens |
| Using `findFirst` to conclude the entire source is valid | Short-circuits without traversing everything | Choose validation that traverses all data |
| Thinking `toList()` automatically closes file sources | Stream terminal operations do not auto-close | Use try-with-resources for closeable sources |
| Returning a `Stream` from a closed `try-with-resources` | Caller receives an unusable stream | Materialize in scope or transfer ownership |
| Reusing an already-consumed stream | `IllegalStateException` or invalid behavior | Create a new stream from an appropriate source |
| Using `parallelStream` expecting the first error by list order | Nondeterminism and tasks may already have run | Design errors and side effects explicitly |
| Using `forEach` to write to a DB thinking errors will roll back | Stream is not a transaction | Transactions/idempotency/compensation |
| Catching `Throwable` and turning it into `Failure` | Can mask serious `Error`s | Catch only errors permitted by policy |
| Mixing infrastructure and validation errors under one code | Caller retries/displays incorrectly | Classify by domain and source |
| Returning only `Optional.empty()` for all failure reasons | Loses error code and context | Use Outcome/Result when needed |
| Comparing `getMessage()` strings to make decisions | Brittle when language/wording changes | Use type, code, and fields |

## 22. Self-Check Exercises

**Exercise A — Why doesn't it compile?**

```java
// load(String) throws IOException.
List<String> loaded = ids.stream()
        .map(id -> load(id))
        .toList();
```

**Answer:** `map` takes `Function.apply`, which does not declare checked `IOException`. You need to catch/translate the error inside the lambda, use an adapter with a defined contract, or choose another processing approach.

**Exercise B — Does adding an outer `throws` solve it?**

The method containing `map` adds `throws IOException`. Is that enough?

**No.** The lambda must still conform to `Function`'s function descriptor. The enclosing method's contract does not alter this descriptor.

**Exercise C — Where does the pipeline fail?**

`var p = Stream.of("1","x").map(Integer::parseInt);`. Does creating `p` necessarily throw `NumberFormatException`?

**No.** `map` is an intermediate operation. The error normally appears when a terminal operation requests `"x"` to be parsed.

**Exercise D — Does `findFirst` validate every element?**

Can `Stream.of("1","bad").map(Integer::parseInt).findFirst()` return `1` without encountering an error?

**Yes.** `findFirst` short-circuits on a sequential stream with encounter order and does not require traversing every element.

**Exercise E — Skipping invalid elements**

A parser returns `null` on error and the pipeline uses `filter(Objects::nonNull)`. Does the caller know for sure which elements were dropped?

**No**, not without a separate reporting mechanism. That is only valid when the public contract permits skipping and sufficient observability exists.

**Exercise F — Must every error throw?**

If importing many lines and the UI needs to show all validation errors, can you return `Failure` per line instead of throwing fail-fast?

**Yes.** Structured `Success/Failure` is an appropriate choice; you still need to decide data commitment at an outer layer.

**Exercise G — `Files.lines` resources**

Does `Files.lines(path)` require caring about `close()`?

**Yes.** This stream can hold an open file. When the current scope owns it, use `try-with-resources` or explicitly transfer closing responsibility.

**Exercise H — Parallel execution**

A `parallelStream` has three mappers failing concurrently. Is it guaranteed to receive the error for the first element in the list first?

**No.** Do not rely on error appearance order or assume all other tasks stopped immediately.

**Exercise I — Does `Stream` auto-rollback?**

A mapper wrote two records to the DB and then the third failed. Does `toList()` throwing an exception automatically roll back the first two records?

**No.** Stream does not provide transactions. You need appropriate transaction, idempotency, or compensation policies.

**Exercise J — Wrapping checked into unchecked**

An adapter throws `new RuntimeException(cause.getMessage())`. What is the consequence?

**It does not preserve `cause`** if only the message is passed. Use a constructor that accepts the `cause` object, along with meaningful context.

**Exercise K — Counting all errors**

In `StreamResultsDemo`, why can it count `successes=2` and `failures=2` even though two data lines are invalid?

Because the parser converts the two expected validation errors into **`Failure` objects** rather than throwing an exception that interrupts the pipeline, so `toList()` completes with all four results.

**Exercise L — Using one stream twice**

After `List<Outcome> r = s.toList()`, should you call `s.count()` on the same variable `s`?

**No.** The stream has already been consumed. You can traverse the list `r` with a new stream, or create a new pipeline from a valid source.

## 23. Decision Checklist Before Using Stream With Fallible Operations

Before writing a pipeline, answer these questions:

1. **Does the mapper function have a checked `throws`?** If so, `map`'s `Function` will not let that type escape on its own.
2. **What is the policy for the whole task?** Fail-fast, collect-all, skip, or fallback?
3. **In what form does the caller need to see errors?** An exception with type/code/cause, or a per-element `Outcome`?
4. **Is failing-element information preserved?** ID, line number, field name, or error code, without parsing messages.
5. **Is the cause being lost?** Wrappers should preserve the original error object when appropriate.
6. **When does the pipeline run?** Errors in intermediate operations can surface when the terminal operation is called, even in another layer.
7. **Is there short-circuiting?** `findFirst` and `anyMatch` do not prove all elements were checked.
8. **Does the source have closeable resources?** For `Files.lines`, define ownership and where `try-with-resources` lives.
9. **Is a lazy stream returned out of the API?** If so, who consumes it, who closes it, and when are errors reported?
10. **Are there side effects?** File writes, DB writes, network calls, or payments need a consistency policy separate from Stream.
11. **Is there parallelism?** Do not assume error order, side-effect order, or immediate halting of all work.
12. **Can expected errors and infrastructure errors be separated?** Avoid turning every exception into a validation `Failure`.
13. **Are error paths and resource closing tested?** Verify causes, suppressed exceptions, output, and failure observability.
14. **Would a `for` loop be clearer?** If the main goal is propagating checked exceptions to the caller, do not force a pipeline just for shorter syntax.

## Conclusion

Combining `Stream` with fallible operations requires an **explicit error-handling contract**: `map`/`filter` use functional interfaces that do not declare checked exceptions, pipelines are lazy, and the terminal operation is where errors are typically observed. When one error must fail the entire task, you can use **fail-fast** with a semantically meaningful exception that preserves `cause`. When you need to process every row and report back, use **structured `Success/Failure`**. When you want to skip or fall back, you must prove that behavior is permitted rather than a way to hide errors.

Finally, **Stream is neither a transaction nor does it automatically close all data sources**. Design ownership for I/O sources, avoid uncontrolled side effects, and do not rely on error ordering in parallel pipelines. A clear contract lets the caller know **where a failure occurred, whether processing can continue, whether results are complete, and how resources must be handled**.