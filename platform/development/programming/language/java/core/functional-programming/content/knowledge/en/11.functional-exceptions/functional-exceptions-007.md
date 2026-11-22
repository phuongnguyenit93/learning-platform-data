# Do Not Swallow Exceptions to Keep a Stream Pipeline Running

## 1. The problem: continuing processing does not mean hiding errors

`Stream` in Java helps express data filtering, transformation, and aggregation pipelines. A dangerous way to handle errors is to catch the exception directly inside a lambda, not record it, and then return a default value or drop the element so the pipeline appears to keep running:

```java
// Anti-pattern example: illustrative snippet, not a standalone program.
List<Integer> values = rawValues.stream()
        .map(raw -> {
            try {
                return Integer.parseInt(raw);
            } catch (Exception ignored) {
                return null;
            }
        })
        .filter(Objects::nonNull)
        .toList();
```

If `rawValues` contains the element `"abc"`, the result only includes the elements that could be converted to numbers. However, the system **does not know** that the `"abc"` record failed, why it failed, or how much data was lost. This style also catches other `RuntimeException`s besides number-parsing errors, making programming bugs easy to disguise as invalid data.

A pipeline running to completion **does not prove** that all data was processed successfully. "Not swallowing exceptions" means preserving the true semantics of errors and the agreed-upon handling policy:

- **Errors that must stop processing:** let the exception propagate to where it is responsible for being handled, or wrap it with context and rethrow it.
- **Expected errors that can be handled per element:** produce an explicit failure result, keeping the cause and record position for reporting; remaining elements can continue.
- **Data permitted to be discarded by business rules:** use `filter` or `Optional` according to published rules, while still determining whether the discarding needs to be counted or traced.

The important thing is to **choose a policy intentionally**, not to add a broad `catch` or `return null` just so the Stream completes its terminal operation.

## 2. Exception mechanics in Stream

Stream has two characteristics directly related to error handling.

### Lazy execution and terminal operations

Intermediate steps such as `map`, `filter`, and `flatMap` are typically lazy: they set up the pipeline, while the work happens when a terminal operation such as `toList()`, `collect(...)`, `count()`, `reduce(...)`, or `forEach(...)` requests elements.

```java
Stream<String> pipeline = Stream.of("10", "bad", "20");
Stream<Integer> mapped = pipeline.map(Integer::parseInt);
// Strings are not converted to numbers yet in the two lines above.

List<Integer> result = mapped.toList();
// NumberFormatException occurs during toList().
```

Here `Integer.parseInt("bad")` throws `NumberFormatException`. When an exception is not handled inside the pipeline, the terminal operation terminates abnormally; `toList()` does not return a complete result list. There is no default mechanism to "skip the faulty element and continue," and the consumed Stream cannot be reused afterward.

### Lambdas do not automatically change exception contracts

Standard functional interfaces such as `Function<T,R>`, `Predicate<T>`, and `Consumer<T>` have abstract methods that do not declare `throws` for checked exceptions. Therefore, the following code is invalid if `read` declares `throws IOException`:

```java
// Illustrative example, does not compile when read(Path) throws IOException:
List<String> lines = paths.stream()
        .map(path -> read(path))
        .toList();
```

Checked exceptions must be handled appropriately: convert them to an unchecked exception with context and rethrow, handle them at the business boundary, or represent a `Result` containing success/failure. You should not add `catch (Exception ignored)` just to make the lambda type-check.

### Do not equate data errors with system errors

A `NumberFormatException` from a non-numeric input string may be an **expected data error** in an import flow. Conversely, a `NullPointerException` due to a bug, a configuration error, an invalid object state, or an `IOException` from infrastructure should not be classified by default as a CSV row missing data. Classification is based on the business contract and specific exception-catching conditions.

## 3. Two common handling policies

| Policy | When to apply | What does the Stream do? | How are errors observed? |
| --- | --- | --- | --- |
| **Fail-fast** | A single error makes the result untrustworthy, requires rollback, or needs the caller to decide | Throws the error; the terminal operation may terminate abnormally | Exception with cause and context at the handling boundary |
| **Continue with recorded failures** | Records are independent; one record's error does not invalidate other records' results | Each element yields a `Success` or `Failure` result; the pipeline continues past expected errors | List of failures, error codes, line positions, counts, and reports |
| **Skip by defined rule** | Discarding is a valid business step, such as skipping blank lines | `filter` or an empty/no-value result is used according to the contract | Discard rules and statistics if needed |

In a data import flow, continuing after a formatting error on a single row may be acceptable. In a money transfer command consisting of interdependent steps, silently skipping a failed step can create a severely invalid state. The policy must be chosen based on recoverability and the degree of dependency between steps, not on the goal of "having no exceptions."

## 4. Fail-fast: letting exceptions reach the right handler

When an error must cause the entire operation to fail, let the exception propagate. If line information is needed, wrap the error in a contextual exception and preserve the original `cause`:

```java
// Illustrative method: place inside a class with import java.util.*.
static List<Integer> parseAllStrict(List<String> lines) {
    return java.util.stream.IntStream.range(0, lines.size())
            .mapToObj(index -> {
                String raw = lines.get(index);
                try {
                    return Integer.parseInt(raw);
                } catch (NumberFormatException cause) {
                    throw new IllegalArgumentException(
                            "Invalid integer at line " + (index + 1),
                            cause);
                }
            })
            .toList();
}
```

With `List.of("10", "bad", "20")`, the call `parseAllStrict(...)` ends with an `IllegalArgumentException` whose message indicates line 2 and whose cause is `NumberFormatException`. The faulty line is not replaced with `0`, `null`, or omitted from reporting.

Note: with a sequential ordered Stream like the example, element processing happens on demand from the terminal operation. You should not build logic assuming all elements before the error position have already been successfully written externally. If the lambda has side effects, some side effects may have already occurred before the exception escapes; Stream **does not provide transactions/rollback**. Undoing work must be handled by a transaction mechanism or business orchestration.

## 5. Continue responsibly: returning results that include failures

A flow that validates each record independently can use a result type representing two branches:

```text
Input row
   │
   ▼
Validate/parse
   ├── Success → Accepted(line, raw, value)
   └── Failure → Rejected(line, raw, reason)
                    │
                    ▼
         Aggregate results and errors
```

In Java 17, `record` stores data immutably at the level of its declared reference components, while `sealed interface` clearly restricts the two result kinds. We catch **only the expected error** (`NumberFormatException`) within the scope of number conversion; there is no broad `catch (Exception)`, and `null` is not used to signal missing data.

Business example:

- `null` or blank string: failure `missing input`.
- String not representing a valid `int` (including numbers exceeding the `int` range): failure `not a valid int`.
- Negative number: failure `negative not allowed`.
- Non-negative integer: success; `0` is allowed.

Each input has exactly **one outcome**, so you can always verify that the total number of successes plus failures equals the total number of lines.

## 6. Standalone, runnable Java 17+ example

Create the file `StreamErrorHandlingDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.stream.IntStream;

public class StreamErrorHandlingDemo {
    sealed interface Outcome permits Accepted, Rejected {}

    record Accepted(int line, String raw, int value) implements Outcome {}

    record Rejected(int line, String raw, String reason) implements Outcome {}

    static Outcome parseOne(int line, String raw) {
        if (raw == null || raw.isBlank()) {
            return new Rejected(line, raw, "missing input");
        }

        final int value;
        try {
            value = Integer.parseInt(raw.strip());
        } catch (NumberFormatException cause) {
            return new Rejected(line, raw, "not a valid int");
        }

        if (value < 0) {
            return new Rejected(line, raw, "negative not allowed");
        }
        return new Accepted(line, raw, value);
    }

    static List<Outcome> process(List<String> inputs) {
        return IntStream.range(0, inputs.size())
                .mapToObj(i -> parseOne(i + 1, inputs.get(i)))
                .toList();
    }

    static List<Integer> acceptedValues(List<Outcome> outcomes) {
        return outcomes.stream()
                .filter(Accepted.class::isInstance)
                .map(Accepted.class::cast)
                .map(Accepted::value)
                .toList();
    }

    static List<Rejected> failures(List<Outcome> outcomes) {
        return outcomes.stream()
                .filter(Rejected.class::isInstance)
                .map(Rejected.class::cast)
                .toList();
    }

    static void checkEquals(Object expected, Object actual, String label) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(
                    label + ": expected=" + expected + ", actual=" + actual);
        }
    }

    static void runTests() {
        List<String> inputs = Arrays.asList(
                "10", "abc", " 20 ", null, "-3", "30");

        List<Outcome> expected = List.of(
                new Accepted(1, "10", 10),
                new Rejected(2, "abc", "not a valid int"),
                new Accepted(3, " 20 ", 20),
                new Rejected(4, null, "missing input"),
                new Rejected(5, "-3", "negative not allowed"),
                new Accepted(6, "30", 30));

        List<Outcome> actual = process(inputs);
        checkEquals(expected, actual, "one outcome per input");
        checkEquals(List.of(10, 20, 30),
                acceptedValues(actual), "accepted values");
        checkEquals(3, failures(actual).size(), "failure count");
        checkEquals(new Accepted(1, "0", 0),
                parseOne(1, "0"), "zero is accepted");
        checkEquals(new Rejected(1, "", "missing input"),
                parseOne(1, ""), "empty string");
        checkEquals(new Rejected(1, "2147483648", "not a valid int"),
                parseOne(1, "2147483648"), "integer overflow");

        List<String> anotherInput = new ArrayList<>();
        anotherInput.add(null);
        anotherInput.add("bad");
        checkEquals(2, failures(process(anotherInput)).size(),
                "all invalid inputs have visible failures");
    }

    public static void main(String[] args) {
        runTests();
        System.out.println("tests=PASS");

        List<String> inputs = Arrays.asList(
                "10", "abc", " 20 ", null, "-3", "30");
        List<Outcome> outcomes = process(inputs);

        List<Integer> values = acceptedValues(outcomes);
        List<Rejected> errors = failures(outcomes);

        System.out.println("accepted=" + values);
        for (Rejected error : errors) {
            System.out.println("line=" + error.line()
                    + " input=" + error.raw()
                    + " reason=" + error.reason());
        }
        System.out.println("successes=" + values.size()
                + ", failures=" + errors.size());
    }
}
```

Compile and run:

```bash
javac StreamErrorHandlingDemo.java
java StreamErrorHandlingDemo
```

Stdout output:

```text
tests=PASS
accepted=[10, 20, 30]
line=2 input=abc reason=not a valid int
line=4 input=null reason=missing input
line=5 input=-3 reason=negative not allowed
successes=3, failures=3
```

**Behavior breakdown:**

1. `process` uses `IntStream.range` to preserve the source index, converting it into a 1-based line number.
2. `parseOne` always produces `Accepted` or `Rejected` for inputs under the contract; it neither returns `null` nor logs an error and pretends to succeed.
3. `NumberFormatException` is caught only around `Integer.parseInt(...)`. When a string is not an `int`, instead of treating an unspecified exception as a data error, the program returns the specific reason `not a valid int`.
4. Negative number cases are classified by a business check after successful parsing; exceptions are not used to express a normal validation condition.
5. `failures` and `acceptedValues` are read from the same `Outcome` list, so reporting does not lose any records.
6. `runTests` compares full outcomes, line ordering, values, errors, and edge cases, throwing `AssertionError` if any check fails. The tests do not depend on the JVM `-ea` option.

In this example, `raw` is displayed because the test data is non-sensitive. In real usage, avoid storing or printing account numbers, tokens, personal data, or full exception messages that may contain secrets. Prefer stable error codes, and store line numbers along with masked/redacted sensitive data.

## 7. Why `Optional.empty()` or `Stream.empty()` can still be "swallowing errors"

`Optional` and `Stream.empty()` are completely valid when the business nature is "no value" or "this element is allowed to be skipped." However, the example below hides input errors if there is no other observation mechanism:

```java
// Anti-pattern example: parse error is turned into absence, with no reason.
static java.util.stream.Stream<Integer> parseOrDrop(String text) {
    try {
        return java.util.stream.Stream.of(Integer.parseInt(text));
    } catch (NumberFormatException ignored) {
        return java.util.stream.Stream.empty();
    }
}
```

Calling `raw.stream().flatMap(MyClass::parseOrDrop).toList()` may return a list of valid numbers, but it cannot distinguish between "a line allowed to be skipped" and "a faulty line." If the criterion is **skipping blank lines per specification**, using `filter(s -> !s.isBlank())` is usually clearer. If invalid elements must be counted, create a `Rejected` result as in the full example.

You should not infer that using `Optional` is wrong: right or wrong depends on the **error-reporting contract**. When the contract defines "no data" as a normal outcome, `Optional.empty()` may be the exact appropriate representation. Avoid using it as a place to hide unexpected exceptions.

## 8. Handling checked exceptions in lambdas

I/O operation example:

```java
// Illustrative snippet in a class with import java.nio.file.* and java.io.*.
static String readText(java.nio.file.Path path) {
    try {
        return java.nio.file.Files.readString(path);
    } catch (java.io.IOException cause) {
        throw new java.io.UncheckedIOException(
                "Cannot read: " + path, cause);
    }
}
```

Usage:

```java
// Illustrative snippet, requires List<Path> paths.
List<String> texts = paths.stream()
        .map(MyClass::readText)
        .toList();
```

`UncheckedIOException` preserves the original `IOException` as the cause and forces the error to be handled at a boundary with sufficient context. If the application wants to continue reading other files, it can return `ReadSuccess`/`ReadFailure` and collect a report instead of throwing immediately. That must be decided explicitly: there are cases where failing to read one file invalidates the entire result.

**Do not catch `Throwable` or `Error` to keep the pipeline running.** Conditions such as out-of-memory or severe VM errors are not normal input errors. For `InterruptedException`, if you must catch it and cannot rethrow the checked exception, you typically need to restore the interrupt status with `Thread.currentThread().interrupt()` and transfer control according to the cancellation policy. Do not try to continue normal processing after a cancellation signal as if nothing happened.

## 9. Warnings about `parallelStream`, `peek`, and side effects

A seemingly convenient way to handle errors is to add `errors.add(...)` inside a `catch` block and let the pipeline continue:

```java
// Anti-pattern example: sharing an ArrayList is unsafe when running in parallel.
List<String> errors = new ArrayList<>();
List<Integer> values = raw.parallelStream()
        .map(s -> {
            try {
                return Integer.parseInt(s);
            } catch (NumberFormatException e) {
                errors.add(s);
                return null;
            }
        })
        .filter(Objects::nonNull)
        .toList();
```

`ArrayList` is not safe for concurrent updates, so adding errors from multiple threads can lose records or lead to corrupted state. Even with a sequential Stream, this approach makes result evaluation depend on side effects and does not clearly associate errors with individual records.

A better approach is to **return results as data**, then use a terminal operation to collect `Outcome`s. You can separate them into accepted/rejected using traversals that do not mutate the source. For large workloads, consider an appropriate collector if single-pass aggregation is needed; prioritize clarity and measure actual performance.

`peek` is mainly for observation or debugging; you should not rely on `peek` to produce mandatory business error logs. Some optimizations or terminal operations do not guarantee that the `peek` lambda is called for every element in the way you expect. When running in parallel, the timing of side effects and the order of error reporting may differ from the source data order.

If a parallel pipeline encounters an uncaught error, you should not infer that all elements before the error were processed or that other elements stopped immediately at that exact moment. In the main example, sequential `IntStream.range` is used so that error positions and reporting order are deterministic.

## 10. Testing failure behavior: what must be proven?

A good test for an error policy should verify:

| Scenario | Expected behavior |
| --- | --- |
| Valid data | Exactly one success outcome appears |
| Recoverable invalid format | `Rejected` is present with index and reason |
| Empty/`null` data | Rejected outcome per rules, no accidental `NullPointerException` |
| Integer overflow | Classified as a parse error, not replaced with `0` |
| Multiple errors interspersed with valid data | Every record has an outcome, no positions are lost |
| All elements invalid | Success list is empty, all errors are still present |
| Errors outside the allowed-to-continue scope | Exception must propagate, optionally preserving `cause`, not turned into success |
| Using parallel Stream or side effects | Thread safety and ordering policy are guaranteed when actually needed |

In the example, `runTests()` checks multiple success/failure lines, `null`, empty strings, overflow, and the all-invalid case. Beyond checking outputs, in real problems you should have tests verifying stable **error codes**, that the total input lines equal successes plus failures, that sensitive data is not logged, and that processing does not continue after non-recoverable infrastructure errors.

For fail-fast, test exceptions explicitly. With JUnit 5, you can use `assertThrows(IllegalArgumentException.class, () -> parseAllStrict(List.of("1", "bad")))` and verify `getCause() instanceof NumberFormatException`. The JUnit statement here is an illustrative example requiring the JUnit dependency and corresponding imports; the Java 17 program in section 6 does not require JUnit.

## 11. Design mistakes to avoid

**1. `catch (Exception e) { return null; }`.** Mixes data errors and programming bugs, erases cause information, and creates a risk of `NullPointerException` in later steps.

**2. `catch (RuntimeException ignored) { return defaultValue; }`.** A "valid" default value such as `0`, `false`, or an empty string can flow into aggregation, skewing statistics, revenue, or business decisions. Only use a fallback when it is clearly defined and fallback occurrences are observable.

**3. Only calling `printStackTrace()` or `log.error()` and dropping the error.** Logging aids diagnosis but does not replace a return, throw, or reporting policy. Callers may still assume everything succeeded if they receive no failure signal.

**4. Catching exceptions across the entire transformation.** An overly broad `catch` lumps parsing errors, DB errors, and formatting bugs into the same category. Place `try/catch` around the specific operation whose expected exceptions you understand.

**5. Using `filter` to hide corrupted data.** A filtering rule must explain why an element is excluded. An unexpected error does not automatically become an "unneeded element" just because it is inside a Stream.

**6. Believing a successful terminal operation means complete data.** `count()` or `toList()` can succeed even when many prior rows were silently dropped. Reconcile counts and error details according to the contract.

**7. Reusing a failed or consumed Stream.** A Stream is a one-time processing pipeline. Once a terminal operation finishes (including by failing), it cannot be treated as a stream that can "resume from the failed line"; design from a repeatable data source and a clear handling policy if retries are needed.

**8. Ignoring transactions and consistency.** A pipeline with side effects such as sending emails, writing to a DB, or calling APIs may have partially executed before an exception occurs. Do not assume Stream automatically rolls back those side effects; use transactions, idempotency, retry policies, or compensation mechanisms as appropriate for each system.

## 12. Reinforcement exercises

1. Change the negative-number rule to accept values from 0 to 100. Add the reason `too large` for values greater than 100 and test with 100, 101, and `-1`.
2. Upgrade the failure result to `Rejected(line, raw, errorCode, message)`; write a function that aggregates error counts by `errorCode` without relying on log contents.
3. Write a fail-fast function that transforms a list of strings into `List<Integer>` and test that the element `"abc"` on line 2 causes an exception clearly indicating line 2 while preserving `NumberFormatException` in `getCause()`.
4. Suppose the data contains secret lines: design an error display function that includes only the line number and error code, without returning or logging the original input string.
5. Explain the difference between skipping blank lines with `filter` per specification and dropping a line due to `NumberFormatException` without recording the error.
6. Point out what can go wrong when `parallelStream()` concurrently adds errors to an `ArrayList`, then fix it by collecting immutable `Outcome`s.

A resilient Stream pipeline must distinguish between **business conditions allowed to be skipped**, **recoverable errors that must be recorded**, and **errors that must stop processing**. When continuation is allowed, make the failure part of the result data so the system still sees what happened.
