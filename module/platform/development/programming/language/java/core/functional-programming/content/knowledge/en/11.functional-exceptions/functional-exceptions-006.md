# Choosing Between Failing Fast for the Whole Batch or Representing Success and Failure Per Item in Java

## 1. Why does the same error require two different policies?

When processing a dataset with loops, lambdas, or Streams, an item may be invalid: a malformed CSV row, a negative amount, a non-existent customer ID, or a record that violates a business rule. The important question is not only **which exception to throw**, but also **how an error in one item should affect the entire operation**.

Two common choices are:

1. **Fail fast for the whole batch** (*fail-fast / abort the batch*): an unprocessable item causes the processing operation to terminate with an exception. The caller receives an error instead of a list of successful results.
2. **Representing success or failure for each item** (*per-item result*): each item is transformed into a value describing either success or error; the processor continues with the remaining items if that error can be handled locally.

This is a **decision about the processing contract**, not merely a difference in `try/catch` syntax. The same dataset may require different policies in different systems:

| Context | Usually appropriate policy | Reason |
| --- | --- | --- |
| Computing values for a financial transaction that must be completely valid | Abort or reject the whole batch | Half-correct data is unacceptable when the business requires consistency |
| Importing thousands of independent CSV rows | Per-item result | Clearly report invalid rows and continue importing valid ones |
| Updating system configuration with global constraints | Validate everything, then reject the whole batch if there are errors | Need to know all errors without applying an invalid configuration |
| Processing independent notifications per recipient | Per-item result, with appropriate retries | One failing address should not hide the status of other addresses |
| Writing data within an atomic transaction | All-or-nothing policy and a real transaction | An exception alone does not automatically roll back all changes |

**Important distinction:** "stopping at the first error" and "processing everything to collect errors, then deciding to reject the whole batch" are two different workflows, even though both may enforce the final policy of **accepting no results at all when any error occurs**.

## 2. A function-level view

Suppose we have an operation that parses a string into a positive integer:

~~~java
static int parsePositive(String raw) {
    if (raw == null || raw.isBlank()) {
        throw new IllegalArgumentException("Giá trị trống");
    }
    int value;
    try {
        value = Integer.parseInt(raw.trim());
    } catch (NumberFormatException ex) {
        throw new IllegalArgumentException("Không phải số nguyên: " + raw, ex);
    }
    if (value <= 0) {
        throw new IllegalArgumentException("Phải lớn hơn 0: " + raw);
    }
    return value;
}
~~~

The snippet above is an **illustrative method placed inside a class**, not a standalone file; the full runnable program is in section 6. With the inputs:

~~~text
["10", "bad", "25", "0", "7"]
~~~

the transformation has the following expected results per item:

| Position (1-based) | Input | Result |
| --- | --- | --- |
| 1 | `"10"` | Success, value 10 |
| 2 | `"bad"` | Failure, not an integer |
| 3 | `"25"` | Success, value 25 |
| 4 | `"0"` | Failure, must be greater than 0 |
| 5 | `"7"` | Success, value 7 |

A processing operation can be described conceptually by one of two contracts:

~~~text
Whole batch:
List<Input> -> List<Value> OR exception (does not return List<Value>)

Per item:
Input -> Result<Value, Error>
List<Input> -> List<Result<Value, Error>>
~~~

In standard Java, the notation `Result<Value, Error>` here is a **conceptual model**, not a built-in generic `Result` class in `java.util`. You can declare your own result type, use a supporting library, or design an API tailored to the domain.

## 3. Policy A: aborting the whole batch when one item throws an exception

A Stream pipeline typically looks like this:

~~~java
List<Integer> values = input.stream()
        .map(BatchResultDemo::parsePositive)
        .toList();
~~~

This snippet assumes that the `BatchResultDemo` class already has `parsePositive` and `input` is a `List<String>`. When `map` applies the parsing function to an invalid input, an exception can propagate out of the terminal operation `toList()`. Without handling, the current execution path terminates with that exception.

If the caller needs to control the error message:

~~~java
try {
    List<Integer> all = input.stream()
            .map(BatchResultDemo::parsePositive)
            .toList();
    System.out.println("Toàn lô: " + all);
} catch (IllegalArgumentException ex) {
    System.out.println("Toàn lô: lỗi - " + ex.getMessage());
}
~~~

With a sequential Stream and the sample dataset, the error on `"bad"` occurs when processing reaches the second position. No successful `List<Integer>` is assigned to the `all` variable. Subsequent items are not executed in **this specific sequential pipeline** after the exception propagates.

### 3.1. Strengths

- Easy to understand when **all inputs must be valid** before a successful result can exist.
- Keeps a convenient signature such as `List<T> -> List<R>` with exceptions used for cases that cannot complete.
- Gives the caller a single place to handle operation failure, such as at a service/API boundary.
- Reduces the need to create error-description objects for each item if the policy only needs to know whether an error occurred.

### 3.2. Limitations to be aware of

- **A propagating exception does not automatically undo side effects.** If previous items were already written to a database, sent as emails, updated in a shared variable, or output to a device, `toList()` failing does not guarantee a rollback.
- **Does not automatically provide a list of all errors.** With standard fail-fast behavior, subsequent unchecked errors will not be collected.
- **Stream pipelines are lazy.** `filter`, `map`, and most intermediate operations do not execute immediately when declared. Exceptions arise when data is actually evaluated by the corresponding terminal operation. You should not attribute every error solely to the line calling `map`.
- **Not every terminal operation traverses the entire source.** For example, `findFirst` or `anyMatch` may short-circuit based on a condition; having an error in an unvisited item does not mean an error will appear in every pipeline.
- **In a parallel stream**, multiple tasks may run concurrently. You should not promise that the error always comes from the first item in encounter order; nor should you use an exception to infer that all other work has definitely stopped immediately.

### 3.3. True all-or-nothing requires additional design

If the business requires **all items to succeed or no changes to be committed**, combine the error policy with mechanisms that guarantee atomicity:

1. **Preparation/validation phase:** parse, validate, and transform data without producing irreversible side effects.
2. **Commit phase:** perform changes inside a transaction that supports rollback or an appropriate commit mechanism.
3. **If an error occurs during commit:** apply rollback/compensation based on the external system's contract.

A fail-fast stream is not equivalent to a transaction. For external APIs such as sending emails, calling payment gateways, or writing files, reversibility is limited and must be designed separately.

## 4. Policy B: representing Success or Failure for each item

When records can be processed **independently**, we do not want one invalid input to lose all information about the other items. The idea is to turn predictable errors into **data values**, rather than letting exceptions escape the pipeline.

Java 17 provides `sealed interface` and `record` to express a closed set of states:

~~~java
sealed interface ParseResult permits Success, Failure {}

record Success(int index, String raw, int value)
        implements ParseResult {}

record Failure(int index, String raw, String reason)
        implements ParseResult {}
~~~

This is a type declaration **placed inside a class or at an appropriate top-level**; in section 6 the types are nested inside a class so the program compiles standalone.

- `Success` carries the position, raw data, and successfully parsed value.
- `Failure` carries the position, raw data, and an explanation of why the item is invalid.
- `ParseResult` is the common type for both cases. `sealed` restricts the permitted direct implementations, making the domain model clearer.
- `record` provides concise data components, accessors, and value-based equality. Records are **shallowly immutable**; with primitive and `String` fields in this example, the actual data is also stable.

Transforming a single item:

~~~java
static ParseResult parseOne(int index, String raw) {
    try {
        return new Success(index, raw, parsePositive(raw));
    } catch (IllegalArgumentException ex) {
        return new Failure(index, raw, ex.getMessage());
    }
}
~~~

Instead of returning `int` or throwing a predictable error, this method returns **one of two result forms**. It catches `IllegalArgumentException`, which is the validation error type intentionally used by `parsePositive`.

**Do not catch `Exception` or `Throwable` indiscriminately in every lambda.** Programming bugs (such as an unexpected `NullPointerException`), infrastructure failures, security issues, thread interruptions, or serious `Error`s should not automatically be treated as "a bad data row". Classify which errors can be continued from and which must halt the entire system.

### 4.1. Mapping the whole list into labeled results

~~~java
List<ParseResult> results = IntStream.range(0, input.size())
        .mapToObj(i -> parseOne(i, input.get(i)))
        .toList();
~~~

This illustrative snippet requires importing `java.util.List` and `java.util.stream.IntStream`, along with the class containing `parseOne` and the `ParseResult` type.

- `IntStream.range(0, input.size())` generates indices from `0` to `size()-1`.
- `parseOne(i, input.get(i))` preserves the **position** to distinguish items even when two rows have the same value.
- `toList()` creates the result list (structural modification of the returned list is not permitted).
- For this sequential example, the order of results corresponds to the order of source positions.

At this point, valid data errors meant for reporting have been **encapsulated**, so the pipeline can complete. This **does not guarantee** that no exceptions remain: for example, `input.get(i)` or code inside `parseOne` can still fail in an unhandled way. The `Result` contract is only resilient within the scope of the errors it is designed to represent.

### 4.2. Computing results from only the successful items

For example:

~~~java
long successCount = results.stream()
        .filter(r -> r instanceof Success).count();
long failureCount = results.size() - successCount;

int sum = results.stream()
        .filter(r -> r instanceof Success)
        .mapToInt(r -> ((Success) r).value())
        .sum();
~~~

In the sample program, 10 + 25 + 7 = **42**, with 3 successes and 2 failures. The cast in the last expression is safe for the results of the immediately preceding `instanceof Success` filter, provided the list is not unexpectedly mutated during the pipeline.

In production code, you can design dedicated helpers/accessors or collectors to avoid repeating conditions and casts. You should not force every result check into a hard-to-read Stream chain; a loop that classifies results is also completely reasonable.

## 5. A third option: process everything, yet still reject the whole batch

The policy of **processing everything to aggregate errors, then deciding whether to accept or reject** is often suitable for multi-field forms, configurations, or file imports that need full validation before committing.

After creating `List<ParseResult> results`:

~~~java
boolean hasFailure = results.stream()
        .anyMatch(r -> r instanceof Failure);

if (hasFailure) {
    // Aggregate and return the error list; do not commit any results.
} else {
    // Extract all Success items and proceed to commit according to the business policy.
}
~~~

This is an **illustrative snippet**. It differs from fail-fast in that every item has been checked and full information is available for feedback. Yet it also differs from partial success: the system **does not accept successful items** if the batch has any failure.

This can be summarized in a table:

| Workflow | Which errors are visible? | Are per-item successes returned/committed? | Does it auto-rollback? |
| --- | --- | --- | --- |
| Fail-fast with propagating exception | Usually the first error that causes the pipeline to fail | No successful whole-batch result | No |
| Each item returns a Result | Predictable errors on each processed item | Possibly, depending on policy | No |
| Collect all Results then reject all-or-nothing | Predictable errors across all items | May be recorded internally, but not committed | No; still requires transaction/commit design |

**Do not confuse the two:** collecting all results is a **diagnostic strategy**; allowing per-item results to be written into the system is a **separate business decision**.

## 6. Complete Java 17 program and verified stdout

Create the file **BatchResultDemo.java** as shown below. The example runs both policies on the same data so learners can see the difference directly.

~~~java
import java.util.List;
import java.util.stream.IntStream;

public class BatchResultDemo {
    sealed interface ParseResult permits Success, Failure {}
    record Success(int index, String raw, int value) implements ParseResult {}
    record Failure(int index, String raw, String reason) implements ParseResult {}

    static int parsePositive(String raw) {
        if (raw == null || raw.isBlank()) {
            throw new IllegalArgumentException("Giá trị trống");
        }
        int value;
        try {
            value = Integer.parseInt(raw.trim());
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException("Không phải số nguyên: " + raw, ex);
        }
        if (value <= 0) {
            throw new IllegalArgumentException("Phải lớn hơn 0: " + raw);
        }
        return value;
    }

    static ParseResult parseOne(int index, String raw) {
        try {
            return new Success(index, raw, parsePositive(raw));
        } catch (IllegalArgumentException ex) {
            return new Failure(index, raw, ex.getMessage());
        }
    }

    public static void main(String[] args) {
        List<String> input = List.of("10", "bad", "25", "0", "7");

        try {
            List<Integer> all = input.stream()
                    .map(BatchResultDemo::parsePositive)
                    .toList();
            System.out.println("Toàn lô: " + all);
        } catch (IllegalArgumentException ex) {
            System.out.println("Toàn lô: lỗi - " + ex.getMessage());
        }

        List<ParseResult> results = IntStream.range(0, input.size())
                .mapToObj(i -> parseOne(i, input.get(i)))
                .toList();

        System.out.println("Từng phần tử:");
        for (ParseResult result : results) {
            if (result instanceof Success s) {
                System.out.println("OK #" + (s.index() + 1)
                        + " " + s.raw() + " -> " + s.value());
            } else if (result instanceof Failure f) {
                System.out.println("FAIL #" + (f.index() + 1)
                        + " " + f.raw() + " -> " + f.reason());
            }
        }

        long successCount = results.stream()
                .filter(r -> r instanceof Success).count();
        long failureCount = results.size() - successCount;
        int sum = results.stream()
                .filter(r -> r instanceof Success)
                .mapToInt(r -> ((Success) r).value())
                .sum();

        System.out.println("Tổng kết: " + successCount
                + " thành công, " + failureCount
                + " thất bại, tổng=" + sum);
    }
}
~~~

Run from the directory containing the file using JDK 17 or higher:

~~~bash
javac --release 17 BatchResultDemo.java
java BatchResultDemo
~~~

**Exact stdout:**

~~~text
Toàn lô: lỗi - Không phải số nguyên: bad
Từng phần tử:
OK #1 10 -> 10
FAIL #2 bad -> Không phải số nguyên: bad
OK #3 25 -> 25
FAIL #4 0 -> Phải lớn hơn 0: 0
OK #5 7 -> 7
Tổng kết: 3 thành công, 2 thất bại, tổng=42
~~~

The program above has been compiled with `javac --release 17` and run standalone; the output matches the calculation in section 2.

**Reading the output by contract:**

- In the **whole-batch** branch, the pipeline throws `IllegalArgumentException` at `"bad"`; instead of returning a result list, the caller catches the exception and prints a single error line.
- In the **per-item** branch, that same error is converted into `Failure(index=1,...)`. Items at positions 3, 4, and 5 are still processed.
- `"0"` is a parseable integer but **does not satisfy the > 0 condition**, so it receives a different business `Failure` from `"bad"`.
- Results are **displayed with 1-based indexing**, while 0-based indexing is used internally.
- The sum 42 counts only `Success`; errors are neither treated as 0 nor silently ignored when reporting counts.

**Meaning of `IllegalArgumentException` in the example:** this is a validation error intentionally used as the contract of `parsePositive`. In production code, you may define a domain-specific exception or return an error structure directly to avoid accidentally catching an `IllegalArgumentException` raised by a bug in other logic. Using this exception type in the article is meant to clarify the two strategies, not to impose a single exception type on all systems.

## 7. How to choose the data type for Success/Failure?

### 7.1. Store enough context for users to fix errors

A useful failure object typically contains:

- **Position**: index, line number, or record ID, to identify the source item.
- **Stable error code**: such as `INVALID_NUMBER`, `NON_POSITIVE`, `UNKNOWN_CUSTOMER`, helping the UI or other systems handle it automatically.
- **Message**: a sufficiently clear explanation, which can be localized at the presentation layer.
- **Input value or source reference** when safe and necessary.

Conceptual illustrative snippet (not a standalone file):

~~~java
record ValidationError(
        int index,
        String code,
        String message) {}
~~~

An error with a stable code is usually better than parsing text from `Exception.getMessage()`. Do not use an exception's message as the sole protocol between services, because its wording/locale may change.

### 7.2. Should you keep the original Throwable inside Failure?

Not always. Keeping the original `Throwable` can help with logging/diagnostics at internal boundaries, but it also carries stack traces, sensitive data, and technology coupling. In payloads returned to clients, prefer **error code + position + safe message**; if you need to store the deeper root cause, use logging/correlation IDs at the appropriate layer.

In particular, never put sensitive inputs such as passwords, tokens, or personal data directly into public messages. The example uses simple numeric strings solely for illustration.

### 7.3. Generic Result<T,E> or a domain-specific type?

In a large project, you can define a structure such as:

~~~java
sealed interface Result<T, E> permits Ok, Err {}

record Ok<T, E>(T value) implements Result<T, E> {}
record Err<T, E>(E error) implements Result<T, E> {}
~~~

This is a **type-level illustrative snippet** (no `public`, no runnable methods). Java 17 can use a generic `sealed interface` and records like this if placed in an allowed compilation unit and scope. Advantage: success/failure logic can be reused across many data types and error types.

However, a generic type does not automatically guarantee that every branch is handled or that every value is non-null. The API needs clear conventions regarding nullability, generic variance, exception types, and object immutability. For a small domain, `ParseResult` and two concrete records can be easier to read than a general-purpose abstraction.

Libraries like **Vavr** provide `Either<L,R>` and `Try<T>` to represent similar ideas; those are **external libraries outside the JDK**, not included by default in standard Java. Choose a library when it fits the system and team conventions—there is no need to add a dependency just for a small example.

## 8. Checked exceptions in lambdas and Streams

Common functional interfaces used in Streams, such as `Function<T,R>` and `Predicate<T>`, do not declare general checked exceptions in their SAM methods. Therefore, the following snippet **intentionally does not compile** if a method `load(...)` declares `throws IOException`:

~~~java
// Assumption: static String load(Path path) throws IOException { ... }
//
// List<String> lines = paths.stream()
//         .map(path -> load(path)) // unhandled checked exception error
//         .toList();
~~~

Types like `Path` and `IOException` here are only for describing context. There are two intentional approaches:

1. **Whole batch:** perform the read operation in a service/helper layer with a clear exception contract, and let the caller/system decide to abort.
2. **Per item:** catch **the exact checked exception type that can be handled locally** inside the mapping function and return a `Failure` carrying an appropriate error code.

Illustrative example following the Result approach:

~~~java
// map(path -> {
//     try {
//         return new Success<>(read(path));
//     } catch (IOException ex) {
//         return new Failure<>(safeError(ex));
//     }
// })
~~~

This is **Java pseudocode using hypothetical type/function names** to illustrate the idea, not a standalone compilable program. For a real implementation, use the defined `Result`/`Success`/`Failure` types and exact signatures. Do not catch all `Exception`s just to ensure the pipeline "always runs to completion".

### 8.1. Cancellation, InterruptedException, and non-continuable errors

If processing involves blocking operations and encounters `InterruptedException`, that is usually a **cancellation signal** that must be respected, not bad data in a single item. When choosing to catch it to propagate appropriately, many APIs require restoring the interrupt flag with `Thread.currentThread().interrupt()` before exiting or returning a cancelled state. The decision depends on the API contract, but you should never swallow the interrupt completely and silently continue processing.

Likewise, you should not turn `OutOfMemoryError` and serious VM errors into ordinary `Failure`s. "Continuing processing" only makes sense for **errors classified as continuable**, not everything that can be thrown in Java.

## 9. Additional decisions that are often overlooked

### 9.1. Ordering and determinism

The section 6 example uses `List.of`, `IntStream.range`, and a sequential pipeline; the results preserve the input order. If you switch to `parallel()`, you must reconsider side effects, ordering, and how errors are collected. Do not rely on the first exception observed in a parallel environment to claim it is the earliest failing row by position.

If you must return a report in source order, store `index` in each result and then sort/collect by index if the processing architecture does not guarantee encounter order.

### 9.2. Continue processing or retry?

`Failure` does not have to be a terminal state. Validation errors usually require the user to fix the input; transient network errors can be retried with backoff and an idempotency key, but retries must not be applied infinitely or cause duplicate sends/writes. If using per-item results, a "pending/retrying" state may need its own type or workflow, rather than treating every error as a permanent failure.

### 9.3. Error limits and memory

Collecting an entire `List<Result>` provides detailed feedback but has memory cost proportional to the number of items. For very large batches, you can process in chunks, persist results to the system in batches, or set a threshold on the number of reported errors. Stopping after N errors is a **separate policy**; it is no longer "every item has been checked".

### 9.4. API response protocol

If an HTTP API returns only a single status for the entire request, use HTTP statuses that match the contract; per-item reporting requires a response body that clearly describes each outcome, ID/position, and summary. Do not pick a single HTTP status and implicitly assume all records succeeded. When partial success is allowed, the API documentation must clearly state "how many were committed, how many failed, and whether retries will occur".

### 9.5. Avoid placing side effects inside map/filter

In a data-modeling pipeline, separate **transformation/validation** from **writing to external systems**. Use `map` to produce results, then perform commits according to policy. Writing to a database or sending emails directly inside `map` makes fail-fast hard to roll back and retries prone to duplication. In particular, never use `parallelStream()` with an unsynchronized shared mutable error-collection variable.

## 10. Comparison with Optional and swallowing errors

A "continue" approach that looks short:

~~~java
// Not recommended if error diagnostics are needed:
// List<Integer> values = input.stream()
//     .map(x -> {
//         try { return parsePositive(x); }
//         catch (IllegalArgumentException ex) { return null; }
//     })
//     .filter(java.util.Objects::nonNull)
//     .toList();
~~~

This is an **illustrative snippet placed in a class that has `parsePositive`**; the code is commented out because it demonstrates a strategy that loses information. The result retains only the valid numbers, **with no way to know how many records failed, why, or where** without a separate reporting channel.

`Optional<Integer>` can represent **the presence or absence of a value**, but by default it does not contain an error code, position, or cause. If you only need to discard invalid items and that is permitted, `Optional` or `filter` may be sufficient. If detailed error feedback is needed, `Result` or an equivalent domain type is more appropriate.

Avoid intentionally mapping errors to 0, empty strings, or dummy values if those could be valid data. Doing so skews statistics and masks anomalies.

## 11. Choosing a policy with a checklist

Before designing a batch-processing function, answer:

1. **Are inputs independent?** Does one item failing render the other items meaningless or inconsistent?
2. **Does the business allow partial success?** If not, do you need fail-fast or checking everything before rejecting the whole batch?
3. **Do users need to see every error, or is a single error enough to fix?** For form/batch uploads, reporting all errors usually improves the experience.
4. **Which errors are bad data, and which are infrastructure/cancellation?** Only locally recoverable errors should be turned into `Failure` and continued from.
5. **Have side effects already occurred?** If so, exceptions do not guarantee rollback; you need transactions, idempotency, or compensation.
6. **Are ordering, IDs, and reconciliation logs required?** Keep the source index/ID in every result.
7. **Is the number of items and errors large?** Do you need chunking, result streaming, or size limits?
8. **Is the API contract clear?** Can it distinguish "processed", "valid", "committed", and "will retry"?

A pragmatic rule of thumb:

- **Everything must be valid and you do not need to report all errors:** consider fail-fast with a clear exception contract, while ensuring transactions if all-or-nothing is required.
- **Need to report all errors but disallow partial application:** collect `Result` for all inputs, then commit only if there are no `Failure`s.
- **Each item is independent and partial results are allowed:** return `Result` per item, report a summary, and manage retries/commits according to the contract.

## 12. Self-check questions

**Question 1.** Given the list `["10","bad","25"]` and `input.stream().map(BatchResultDemo::parsePositive).toList()`, what is the outcome?

**Answer:** on a sequential pipeline using the method in this article, `"bad"` causes `IllegalArgumentException` to be thrown; no successful `List<Integer>` is returned to the caller. If side effects were already executed before the error, they are not automatically rolled back.

**Question 2.** Why is a per-item `Result` type better than catching exceptions and returning `null`?

**Answer:** it preserves failure context (position, error code, reason) and can be clearly distinguished from success; returning `null` and then filtering loses information unless another channel is added.

**Question 3.** Does collecting all `Result`s mean partial success is allowed?

**No.** The system can aggregate all errors for feedback and then reject the whole batch, committing no successful values.

**Question 4.** When processing a CSV file that must display every invalid row, what should be prioritized?

**Answer:** per-row results or an aggregate validation mechanism with position, message, and error code; then decide whether to import valid rows or reject the whole batch according to business rules.

**Question 5.** Why should you not catch `Throwable` inside `map` so that every item produces a `Failure`?

**Answer:** because `Throwable` includes serious errors and signals that must be handled by higher layers. Continuing indiscriminately can cause corrupted data or hide system failures.

**Question 6.** Can `Result` be used to guarantee a database rollback?

**No.** `Result` is an outcome-reporting model. You need a transaction or a separate commit/rollback mechanism to guarantee atomicity.

**Question 7.** Does a parallel stream guarantee that an observed exception always belongs to the first failing row?

**No.** Processing order and timing can vary; you need an explicit strategy if you must identify the earliest error in source order.

**Question 8.** When is using only `Optional<T>` appropriate?

**Answer:** when the business only needs to know whether a value is present or absent and does not need to distinguish the cause, line number, or how to fix the error.

## 13. References

- [Java SE 17 — Stream API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html).
- [Java SE 17 — Function<T,R>](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Function.html).
- [Java SE 17 — Optional<T>](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Optional.html).
- [Java Language Specification 17, §14.20 — try statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20).
- [Java Language Specification 17, §8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10).
- [Java Language Specification 17, §9.1.4 — Sealed Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.1.4).

**Key takeaway:** Choose **fail-fast** when an error means the entire processing operation no longer has a valid result; choose **per-item Success/Failure** when predictable errors need to be reported individually and other items can continue processing. When you need to **know all errors without accepting partial success**, collect `Result` first and decide at the commit boundary. Do not conflate exceptions, transactions, rollbacks, and continuable errors; business policies must be expressed explicitly in the API.
