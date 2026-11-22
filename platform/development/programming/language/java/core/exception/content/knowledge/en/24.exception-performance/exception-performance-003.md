# Do Not Use Exceptions for Frequent Control Flow in Java

> **Topic:** Java Core → Exception → Performance. The goal is to distinguish **exceptional failures** from **normal outcomes that do not satisfy a condition**, so you can choose between `if`, return values, `Optional`/`OptionalInt`, result types, and `throw/catch`. The content explains both performance costs and API semantics, standalone Java 17 examples, anti-patterns, and how to measure before optimizing.

## 1. Principle: an exception is not a second `if` statement

Exceptions in Java are designed to represent and propagate an **exceptional condition relative to the operation's contract**. The `throw`/`catch` mechanism exits the normal execution path, transfers the cause up to a layer that can handle it, and automatically runs any necessary `finally` blocks.

A branch that occurs frequently and is **expected to be a valid outcome** — object not found, end of data, user leaving a search box empty, a temporarily empty queue — should usually be expressed explicitly with a conditional or a result type. If you write `throw` for these cases inside a hot loop, you can easily make the code harder to read, pollute logs, mask real bugs, and pay the extra cost of the exception mechanism.

Mental examples:

- **Normal:** there are no more lines in a file; a read method reaching the end of a stream returns a sentinel `-1` or `null` per its contract.
- **Normal:** looking up a valid key that has no matching entry; the API returns `null`/`Optional.empty()`/`Result.notFound` by design.
- **Exceptional:** the file has not finished reading, but storage encounters an I/O error; it may throw `IOException`.
- **Exceptional:** an internal invariant is broken, the API state is invalid, or the caller violates the published contract; an appropriate exception may be thrown.
- **Context-dependent:** unparseable text input is normal in an interactive form with many user inputs; however, it can be a serious configuration error when reading a manifest that the publisher guarantees is always valid.

Therefore, there is no rule saying “no error may ever be thrown” or “calling an API that throws an exception is bad code.” What matters is **expected frequency, contract, and where the authority to handle it lives**.

## 2. An anti-pattern: iterating a list with `IndexOutOfBoundsException`

Here is an **illustration of what not to do**:

~~~java
// Method snippet only; assumes List<String> items already exists.
int index = 0;
try {
    while (true) {
        process(items.get(index++));
    }
} catch (IndexOutOfBoundsException end) {
    // Treating an out-of-bounds error as the termination signal.
}
~~~

Problems:

1. Reaching the end of a list is a normal condition and can be checked with `index < items.size()` or an iterator.
2. Both `get(index)` and the code inside `process(...)` can throw an exception; catching too broadly in the outer loop can mistake a real bug for “iteration finished.”
3. Some `List` implementations may be modified concurrently; the example provides no consistency contract when the structure is updated.
4. Readers have to infer that an exception is being used to exit the loop, whereas `for` or `for-each` expresses the intent directly.
5. Creating and throwing exceptions frequently incurs additional overhead; the exact cost must be measured on the target JVM and real workload.

The proper way to express it:

~~~java
// Method snippet only; assumes List<String> items already exists.
for (String item : items) {
    process(item);
}
~~~

Or when you actually need the index:

~~~java
for (int i = 0; i < items.size(); i++) {
    process(items.get(i));
}
~~~

**Exceptions should not replace a loop condition when that condition is a normal part of the algorithm.**

## 3. Where does the actual cost of throwing an exception come from?

You should not oversimplify this as “the `throw` keyword is slow.” A single exception failure can involve multiple pieces of work:

1. **Creating the `Throwable` object:** constructors of many exception types call `fillInStackTrace()` to record stack information, which is typically more expensive than returning a simple value.
2. **Stack unwinding:** the runtime walks back up the stack frames to the matching handler, executing cleanup such as `finally` blocks or try-with-resources.
3. **Impact on JVM optimizations:** an unusual execution path may not be optimized by the JIT compiler in the same way as the success path; control-flow transfers and deoptimization can affect results.
4. **Allocation and GC:** many new exceptions can increase allocation and garbage collection pressure; the impact depends on the JVM, error type, and workload.
5. **Handling/logging:** formatting stack traces, serializing/logging an exception, or passing it across multiple layers can cost even more than throwing it alone.
6. **Observability:** too many false error logs make alerts, dashboards, and incident triage less effective.

However, it is important to be accurate:

- **There is no fixed speed constant** for exceptions compared to `if`; results vary by JVM, compiler, call-site hotness, frame depth, and error frequency.
- **Not every throwable builds a full stack trace:** some exceptions/constructors optionally omit the stack trace, and the JVM may have special optimizations for repeated cases.
- HotSpot has exception-related optimizations, but **do not rely on JVM-specific internals** to justify an obscure control-flow branch.
- If an exception is **very rare**, the overhead of the error path may be negligible; clear API semantics and preserving the root cause are more important than eliminating throws at all costs.
- A richer return type (`Optional`, result object) also has costs: allocation, boxing, branching, or data transfer. Do not assume that replacing `throw` with `Optional` is always faster.

**Proper optimization means choosing the right semantics first and then measuring the hot path**; performance is a strong reason, but not the only one.

## 4. Normal branches that should have their own representation

| Situation | Avoid abusing | Clearer representation | Notes |
|---|---|---|---|
| Iterating a collection to the end | Catching `IndexOutOfBoundsException` | `for`, iterator, `hasNext()` | Consider concurrency if the collection is mutated |
| End of byte stream | Catching an “end of input” exception | `InputStream.read() == -1` | `IOException` still indicates an I/O error |
| End of text lines | Catching `NullPointerException` after `readLine()` | `readLine() == null` | An empty line `""` differs from EOF |
| End of iterator elements | Catching `NoSuchElementException` | `iterator.hasNext()` | With concurrent modification, contract rules still apply |
| Record does not exist | Throwing and catching `NoSuchElementException` around repeated lookups | `Optional.empty()` or result type | An API may intentionally throw for a different invariant |
| Temporarily empty queue | Catching `NoSuchElementException` from `remove()` | `poll()` returning `null` when empty | Only suitable when `null` is not a valid element |
| Frequently invalid numeric input | Calling `parseInt` and catching in every hot loop | Parser returning success/failure | Validation must not alter grammar/overflow semantics |
| Business rule rejection | Catching an exception for every “insufficient stock” request | Explicit domain result if rejection is expected | Exceptions can still be used in APIs with a different contract |
| Missing required config option | Catching the exception and falling back to an arbitrary default | Validate config at startup and fail fast on error | This may be a real failure and should not be hidden |

**Do not rewrite an API just because the word `Exception` appears in its signature.** If a library interface chooses to throw a checked/unchecked exception for a specific situation, your adapter may need to catch it at the boundary and translate it into a result type suited to your business domain.

## 5. Standalone Java 17 example: frequent data parsing

Suppose an import reader receives many strings from users; invalid data is expected and needs to be counted/displayed. There are two illustrative approaches:

- Approach A: call `Integer.parseInt` on each string, catching `NumberFormatException` to record unparseable cases.
- Approach B: a dedicated function for **non-negative base-10 integer strings containing only ASCII `'0'..'9'` characters**, returning `OptionalInt.empty()` when invalid, without using exceptions for normal rejection outcomes.

Both approaches are tested on equivalent valid/negative inputs; **they do not share the exact same grammar for every input**: `Integer.parseInt` allows `+`/`-` signs according to its rules, whereas the result-type function in the example only allows unsigned ASCII digits. This is an **intentional contract choice** for the input data; do not treat this parser as a drop-in replacement for every `parseInt` call.

Save the whole file as **`ExceptionControlFlowDemo.java`**:

~~~java
import java.io.IOException;
import java.io.StringReader;
import java.util.OptionalInt;

public class ExceptionControlFlowDemo {
    record Summary(int accepted, int rejected, long sum) { }

    private static final String[] INPUTS =
            {"42", "7", "x", "", "2147483648", "001"};

    static Summary viaExceptions() {
        int accepted = 0;
        int rejected = 0;
        long sum = 0;

        for (String text : INPUTS) {
            try {
                int value = Integer.parseInt(text);
                accepted++;
                sum += value;
            } catch (NumberFormatException ex) {
                // Unparseable input is an expected branch.
                rejected++;
            }
        }
        return new Summary(accepted, rejected, sum);
    }

    static OptionalInt parseUnsignedDecimal(String text) {
        if (text == null || text.isEmpty()) {
            return OptionalInt.empty();
        }

        int value = 0;
        for (int i = 0; i < text.length(); i++) {
            char c = text.charAt(i);
            if (c < '0' || c > '9') {
                return OptionalInt.empty();
            }

            int digit = c - '0';
            if (value > (Integer.MAX_VALUE - digit) / 10) {
                return OptionalInt.empty(); // Prevent overflow.
            }
            value = value * 10 + digit;
        }
        return OptionalInt.of(value);
    }

    static Summary viaResult() {
        int accepted = 0;
        int rejected = 0;
        long sum = 0;

        for (String text : INPUTS) {
            OptionalInt parsed = parseUnsignedDecimal(text);
            if (parsed.isPresent()) {
                accepted++;
                sum += parsed.getAsInt();
            } else {
                rejected++;
            }
        }
        return new Summary(accepted, rejected, sum);
    }

    static void print(String label, Summary summary) {
        System.out.printf(
                "%s: accepted=%d rejected=%d sum=%d%n",
                label, summary.accepted(),
                summary.rejected(), summary.sum());
    }

    public static void main(String[] args) throws IOException {
        Summary withExceptions = viaExceptions();
        Summary withResult = viaResult();

        print("exceptions", withExceptions);
        print("results", withResult);
        System.out.println("same summary: "
                + withExceptions.equals(withResult));

        StringReader reader = new StringReader("ab");
        int count = 0;
        while (reader.read() != -1) { // EOF is a normal condition.
            count++;
        }
        System.out.println("characters: " + count);
        System.out.println("read after EOF: " + reader.read());
    }
}
~~~

Compile and run with JDK 17 or newer:

~~~bash
javac ExceptionControlFlowDemo.java
java ExceptionControlFlowDemo
~~~

**Exact stdout:**

~~~text
exceptions: accepted=3 rejected=3 sum=50
results: accepted=3 rejected=3 sum=50
same summary: true
characters: 2
read after EOF: -1
~~~

Explanation:

1. Valid inputs `"42"`, `"7"`, and `"001"` yield 42, 7, and 1 respectively, summing to 50. `"x"`, `""`, and `"2147483648"` are rejected.
2. `Integer.parseInt` throws `NumberFormatException` for the three unparseable strings. Path B returns `OptionalInt.empty()` without needing to throw an exception for rejection cases.
3. Parser B checks characters and **overflow before multiplying/adding**. If you forget the overflow check, Java's `int` can wrap around to negative values without throwing an error on its own.
4. `OptionalInt.of(0)` is a **successful** result distinct from `OptionalInt.empty()`. If you use a sentinel like `-1`, you must ensure `-1` is outside the valid output domain; for signed integers that can be negative, a sentinel easily causes ambiguity.
5. `StringReader.read()` returns `-1` at the end of data per its contract; this is a normal EOF signal, not an error that should create an exception.
6. The program **illustrates design and results**, not a performance benchmark. It does not prove that path B always runs faster than path A on every JVM/dataset.

If the parser is a reusable component, document its grammar clearly: accepted characters, plus/minus signs, whitespace, leading zeros, size limits, Unicode characters, and behavior on `null`. “Not throwing on invalid input” does not permit silently changing the set of accepted inputs.

## 6. Using `OptionalInt`, `Optional<T>`, and result types with the right semantics

### 6.1. `OptionalInt` when a result may be absent

`OptionalInt` represents **either having an `int` value** or **having no value**, avoiding sentinels inside the data domain. It can be a good fit for `tryParse...` methods, statistical lookups, or search operations.

~~~java
// Illustrative snippet inside a method.
OptionalInt result = parseUnsignedDecimal(userInput);
if (result.isPresent()) {
    use(result.getAsInt());
} else {
    showValidationError();
}
~~~

`userInput`, `use`, and `showValidationError` are hypothetical application components; this snippet is not a standalone program. `OptionalInt` makes the failure branch visible in the return type, but it only encodes **present/absent** and cannot explain *why* it failed.

### 6.2. Result type when you need to know the rejection reason

If the UI wants to report “empty,” “not a number,” or “out of range,” a `Result` carrying clear error data is usually better than creating a new exception for every invalid string.

~~~java
// Types that can be placed inside a Java 17 class.
enum ParseError {
    EMPTY, NOT_DECIMAL, OVERFLOW
}

sealed interface ParseResult
        permits Parsed, Rejected {
}

record Parsed(int value) implements ParseResult {
}

record Rejected(ParseError reason) implements ParseResult {
}
~~~

These are **illustrative type declarations**, without a full parser method. Callers can use `instanceof` or Java 17-compatible pattern matching to branch on the type. A result type can carry a message, the offset of the invalid character, or a stable error code, but do not stuff a stack trace into every normal rejection result.

### 6.3. Sentinels with a clear contract

`InputStream.read()` returns a number in `0..255` when a byte is read, and `-1` at EOF. `-1` is safe because it is not a valid byte value for a single read.

Conversely, if a position-finding function is allowed to return negative positions, using `-1` to mean “not found” causes ambiguity. A sentinel is only good if the **result domain and API documentation** guarantee a value outside the valid range.

### 6.4. `null` and absence

`Map.get(key)` can return `null` either because the key is missing **or** because the key exists and is mapped to `null` (in implementations that allow `null` values). Therefore, when you need to distinguish those two states, you may need `containsKey` or an API with a more expressive result type.

Do not turn every exception into `null`: `null` is a weak signal, and if unchecked, it can cause a `NullPointerException` in a place that is harder to investigate. Do not convert an unexpected error into `null` just to “avoid using exceptions.”

## 7. Classifying expected errors by frequency and recoverability

The same situation may need a different representation depending on the context:

| Operation | How do unparseable errors occur? | Recommendation |
|---|---|---|
| Typing character by character into a numeric UI field | Very frequently while the user is typing | Validator or parse result; do not log ERROR on every keystroke |
| Importing one million unvalidated records | An expected percentage is invalid | Parse result + error code per record, aggregated per batch |
| Reading a required environment variable at startup | Rare error; configuration must not be wrong | Fail-fast exception with the config name and cause |
| Decoding a signed token from an untrusted source | Many invalid tokens may come from clients | Verification/decoder API with an appropriate result, resource limits, no secret logging |
| Converting a value already controlled by code | Wrong type is a bug or invariant violation | Exception helps expose programming errors |
| Reading data over a socket after connection loss | I/O failure requiring caller handling or retry | `IOException` / appropriate connection error type |

**Do not turn a serious configuration error into a silent default value** just to avoid an exception: doing so can let the application run in a broken state that is harder to diagnose.

## 8. Avoid “guessing” with a pre-check and then parsing again

A common idea is to run a regex before `Integer.parseInt`:

~~~java
// Illustrative, not a general-purpose parser.
if (input.matches("[0-9]+")) {
    int value = Integer.parseInt(input);
}
~~~

Keep in mind:

- This regex **does not check for overflow**. A 100-digit string of `0..9` characters will still make `parseInt` throw an exception.
- `matches` has to evaluate a regular expression; for a given workload, this step may consume more CPU than parsing directly.
- The grammar may not match: `parseInt` accepts plus/minus signs (for appropriate inputs and radices), whereas the regex `[0-9]+` does not.
- There is a risk of checking twice on the success path: the regex scans the string, and then the parser scans it again.
- If inputs are very long and untrusted, bounding length and computation limits is just as important as choosing the error representation.

A dedicated `tryParse`-style parser should validate **the exact grammar in a single pass**, guard against overflow, and avoid throwing exceptions on normal rejection branches. However, writing your own parser carries a risk of bugs; if the standard API is only called a few times at a boundary, `Integer.parseInt` with a `catch` may still be the better choice for simplicity and maintainability.

## 9. Exceptional conditions should still be exceptions

Not using exceptions for frequent branches **does not mean abandoning exceptions**. Throw when it is the right way to express the contract:

- Invalid arguments relative to a public API: `IllegalArgumentException`, `NullPointerException` at boundaries (for example `Objects.requireNonNull`).
- Object state does not permit the operation: `IllegalStateException`.
- I/O errors other than normal EOF: `IOException`.
- Invariant violations, programming bugs, or dependency failures that the current layer cannot resolve.
- A library defines an exception as its contract for a specific situation; an adapter can convert it into a result type at the appropriate boundary.

An API designed around **exceptional failure** might choose:

~~~java
// Snippet inside an order-confirmation method.
if (orderAlreadyCommitted) {
    throw new IllegalStateException("order already committed");
}
~~~

If the `orderAlreadyCommitted` state is a rare API misuse error, an exception is very clear. However, if the system receives the same message multiple times under at-least-once delivery, “already processed earlier” may be an expected idempotent outcome, so an outcome enum such as `ALREADY_APPLIED` is more appropriate.

So ask: *Does the caller need and have the ability to handle this case as a normal outcome? How frequently does it occur?*

## 10. Exceptions as control flow also hurt readability

Beyond CPU cost, misusing exceptions changes the **reasoning structure**:

~~~java
// Illustrative anti-pattern; methods are hypothetical.
try {
    Item item = repository.findOrThrow(id);
    render(item);
} catch (NoSuchElementException ex) {
    renderEmptyState();
}
~~~

This snippet might make sense if `findOrThrow` has a “must exist” contract. But if not finding an item is a frequent occurrence in a search box, the clearer intent is:

~~~java
// Illustrative code.
Optional<Item> item = repository.find(id);
if (item.isPresent()) {
    render(item.get());
} else {
    renderEmptyState();
}
~~~

Drawbacks of using exceptions on frequent paths:

1. Readers must look for handlers that may be far from the call site just to know the normal outcome.
2. Catching at the wrong layer or catching too broadly can hide real bugs.
3. Exceptions usually carry the meaning “an error occurred,” easily leading to false logs and alerts.
4. The outcome is not explicitly expressed in the return signature, surprising callers.
5. It is harder to compose multiple expected failure states if only a vague exception type is used.

Conversely, a result type with too many branches can make code verbose if failures are genuinely rare and unrecoverable at the current layer. **Choose the construct that expresses the API's intent rather than chasing an optimization slogan.**

## 11. Stack trace cost: understand it properly, do not disable it blindly

`Throwable` can capture a stack trace to help investigators see where an exception originated. This is crucial for unexpected errors.

Some misguided “optimizations”:

- Creating a single exception instance and reusing it for all errors to avoid allocation. The stack trace can become stale, context will not match the request, and it becomes confusing across multiple threads.
- Calling `setStackTrace(new StackTraceElement[0])` on every exception: you lose diagnostic data while the cost of building the stack may already have been paid.
- Creating custom exceptions that suppress stack traces for all errors to run faster: this may save cost, but it trades away observability and requires a very clear contract and testing.
- Relying on HotSpot's *fast throw* mechanism as a general performance guarantee. Optimization details can change across JVMs, versions, and configurations.
- Measuring `throw` time in a microbenchmark loop without warmup and concluding that the result applies to production.

If you truly have a high-frequency failure branch where recording a stack trace **adds no value**, designing it as a normal result is usually clearer than customizing exception stack traces.

## 12. Do not rely on `catch` to handle repeated API misuse

Take the example of repeatedly calling `List.get(index)` with an index that may be invalid:

~~~java
// Not ideal if an out-of-range index is a normal case.
try {
    consume(items.get(index));
} catch (IndexOutOfBoundsException ex) {
    useDefault();
}
~~~

In UI-handling code where the index comes from a user and out-of-range is expected, you can write:

~~~java
if (index >= 0 && index < items.size()) {
    consume(items.get(index));
} else {
    useDefault();
}
~~~

However, for a collection accessed concurrently, checking `size()` first and then calling `get()` **does not guarantee atomicity**: another thread can modify the list between the two calls. You must follow the collection's thread-safety contract, use a snapshot, or apply proper synchronization. Do not trade exception control flow for a new race condition.

For external resources such as files, read/write operations, and networks, a pre-check sometimes cannot prevent failure because state can change between check and use. When exceptional errors can occur, you still need an appropriate exception-handling path.

## 13. Logging: do not turn a normal outcome into an incident

If 5% of millions of imported rows are invalid, logging an `ERROR` stack trace for every row is a significant waste and creates noise.

Instead of:

~~~java
// Illustrative anti-pattern; log and parseInt are application-provided.
try {
    int value = Integer.parseInt(input);
    save(value);
} catch (NumberFormatException ex) {
    log.error("invalid input", ex);
}
~~~

Consider a result-returning parser and **bounded statistical aggregation**:

~~~java
// Illustrative: parseUnsignedDecimal and metrics are declared components.
OptionalInt parsed = parseUnsignedDecimal(input);
if (parsed.isPresent()) {
    save(parsed.getAsInt());
} else {
    metrics.incrementRejectedCount();
}
~~~

If you need to help users fix their data, you can store error codes and line positions for a bounded number of errors, apply size limits, and avoid logging raw payloads containing sensitive data. A batch job can log `importId`, `accepted`, `rejected`, and `errorCategories` instead of a million stack traces.

**Log exceptions when they help investigate real errors**; distinguish `ERROR`, `WARN`, `INFO`, and metrics by severity of impact. “Not throwing” does not automatically improve observability if you swallow all causes and fail to measure rejection outcomes.

## 14. Benchmarks: verify instead of guessing

To decide whether an exception branch is causing a performance problem, measure cases close to production. **Do not draw speed conclusions from running `System.nanoTime()` in a simple loop**: JIT warmup, dead-code elimination, inlining, allocation elimination, constant folding, and GC can skew results.

### Choose valid/failure ratios

A benchmark should include:

- 100% valid.
- 99.9% valid (very rare errors).
- 95% valid, 5% rejected.
- 50% valid, 50% rejected.
- Varying input lengths and realistic error distributions (invalid character at start/end, overflow).
- Varying data rather than all constants so the JIT does not over-optimize.

If the normal branch almost never fails, standard `parseInt` can be very efficient and simple; a custom parser might add overhead. If invalid data is very frequent, exception costs can dominate throughput. **The exact threshold must be measured.**

### Tooling: JMH

Java Microbenchmark Harness (JMH, an OpenJDK project) provides warmup, multiple measurement iterations, and JVM forking, avoiding common benchmarking pitfalls. Below is an **illustrative skeleton depending on JMH**:

~~~java
// Illustrative: requires org.openjdk.jmh dependency, not standalone Java SE.
// @State(Scope.Thread)
// public class ParseBenchmark {
//     @Param({"0", "5", "50"})
//     public int invalidPercent;
//
//     @Benchmark
//     public int exceptionPath() {
//         // Use varying inputs matching invalidPercent,
//         // call the real parser, and consume the entire result.
//     }
//
//     @Benchmark
//     public int resultPath() {
//         // Use the same inputs, same grammar, and same handling policy,
//         // but represent failure without exceptions.
//     }
// }
~~~

The skeleton above is an **experimental outline**, not a complete benchmark, and it has no fabricated output or scores. When implementing a real JMH benchmark, make sure the result is consumed to avoid dead-code elimination, align the data so both branches do **equivalent work**, and avoid generating inputs inside the measured region if that is not part of the real workload.

Additional metrics to observe:

| Metric | Meaning |
|---|---|
| Throughput (ops/s) | How many items can be processed per second |
| Average and percentile latency | Whether the error branch increases tail latency |
| Allocation rate (B/op) | How many bytes are allocated per operation |
| GC count/time | Whether garbage collection pressure increases |
| CPU profile | Whether time is concentrated in the parser, `Throwable`, or logging |
| Error ratio | Actual frequency of failure cases |
| API clarity and debuggability | Do not trade correctness/observability for a few hypothetical percent |

Do not compare only the error path while ignoring the cost on the success path. Also do not change parser semantics between benchmarks: if one side accepts `+1` and the other does not, the comparison is no longer equivalent.

## 15. Rare exceptions and EAFP: when is catching directly the right choice?

Some situations cannot avoid a race between checking and acting. For example, checking if a file exists and then opening it:

~~~java
// Illustrative snippet; does not eliminate the race.
if (java.nio.file.Files.exists(path)) {
    // The file can still be deleted or have permissions changed before opening.
    readFrom(path);
}
~~~

Here, even after checking, opening/reading can still fail with `IOException`. A proper design must still handle real operation errors. If the file is required to exist and failing to open it is exceptional, using an exception is **its intended purpose**.

**EAFP** (easier to ask forgiveness than permission, a common programming term) is not an excuse to abuse exceptions for EOF or every loop element. It is useful when:

- The condition cannot be reliably checked before the operation.
- Failures are rare or carry exceptional meaning.
- The API only provides exceptions as its official contract.
- You need to preserve the `cause`, resource cleanup, and retry policies.

Conversely, **LBYL** (look before you leap) is not always faster or safer if it introduces duplicate checks, breaks grammar, or suffers from TOCTOU bugs.

Conclusion for this section: choose based on **operation semantics, thread safety, and empirical measurement**, rather than trying to replace every `try/catch` with `if`.

## 16. Do not hide bugs with overly broad exception catches

A loop like:

~~~java
while (true) {
    try {
        processNext();
    } catch (Exception ignored) {
        continue;
    }
}
~~~

can swallow:

- Expected data errors.
- `NullPointerException` caused by a bug.
- Transient connection errors that need backoff.
- `InterruptedException` from a blocking operation, causing the program to ignore cancellation signals.
- Errors that leave an object in an invalid state.

The right approach is to distinguish expected outcomes from different kinds of failures. If a worker should continue after invalid data, use a result type to record the rejected record. If I/O fails, perform bounded retry/backoff or propagate the error to the orchestration layer. If interrupted, propagate `InterruptedException` when possible; otherwise, you typically need to call `Thread.currentThread().interrupt()` and exit the loop.

The example below is **illustrative code**, not a standalone program:

~~~java
while (!Thread.currentThread().isInterrupted()) {
    try {
        String raw = queue.take();
        OptionalInt parsed = parseUnsignedDecimal(raw);
        if (parsed.isEmpty()) {
            recordRejected();
            continue;
        }
        process(parsed.getAsInt());
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        break;
    } catch (java.io.IOException ex) {
        handleInfrastructureFailure(ex);
        break;
    }
}
~~~

For this snippet to compile in a project, `process` must appropriately declare `throws IOException`, and `queue`, `recordRejected`, and `handleInfrastructureFailure` must be defined. The goal is to **keep expected rejections, cancellation, and infrastructure failures separate**.

## 17. Common design mistakes

1. **Treating EOF as an exception:** use `read() == -1` or `readLine() == null` per the API; reserve `IOException` for real read errors.
2. **Using `IndexOutOfBoundsException` as a termination condition:** replace with an iterator/`for`/`hasNext()`.
3. **Using `NoSuchElementException` for frequent “not found” cases:** consider `Optional` or a result type; however, if the contract requires existence, an exception is still reasonable.
4. **Treating invalid input as a bug:** in UI/import flows, it is usually an expected outcome; distinguish it from misconfiguration or invariant violations.
5. **Catching `RuntimeException` for every input:** swallows unrelated programming bugs.
6. **Writing a validator that diverges from the parser:** inconsistencies in `+`/`-` signs, Unicode, whitespace, or overflow.
7. **Pre-validating and then parsing again without measuring:** scanning the string twice can be slower, and can still suffer from races or inconsistent input handling.
8. **Using a sentinel that lies inside the valid value domain:** callers cannot distinguish failure from a real result.
9. **Indiscriminately replacing exceptions with `null`:** easily leads to `NullPointerException` further away.
10. **Using `Optional` everywhere because it is “lightweight”:** can complicate APIs and consume resources; you need a clear semantic reason.
11. **Measuring speed with a single `nanoTime` loop:** results may reflect JIT/GC behavior rather than real code performance.
12. **Using microbenchmark results to immediately change a public API:** consider compatibility and migration costs for callers.
13. **Disabling stack traces for all exceptions:** loses diagnostic data for rare, serious errors.
14. **Reusing a shared exception object across requests:** context/stack can be wrong and hard to debug.
15. **Logging `ERROR` for every rejected record:** increases noise, I/O, and cardinality; use bounded statistics instead.
16. **Catching and ignoring interrupts:** makes workers hard to stop and masks cancellation policies.
17. **Using exceptions to roll back and treating them as “normal”:** throwing an error does not automatically revert state; you need an explicit commit/transaction design.

## 18. Strategy for safely refactoring existing code

When you encounter a hot path using exceptions for branching:

1. **Identify the current contract:** could the error be a “normal” state expected by callers? Which exception types are being caught?
2. **Measure frequency:** error rate, call count, time spent in `Throwable` construction, logs, allocation, and GC.
3. **Choose the result type:** `boolean`, `OptionalInt`, `Optional<T>`, enum/status code, or sealed result depending on what information callers need.
4. **Preserve grammar and data domain:** test `null`, empty, whitespace, signs, overflow, Unicode, and extremely long inputs. Do not break parser compatibility.
5. **Convert at the appropriate boundary:** if an existing public API has a contract to throw exceptions, consider keeping the old method and adding `tryParse...` instead of silently changing all callers.
6. **Ensure exceptional paths still preserve `cause`:** when a dependency genuinely fails, do not coerce it into a “not found” value.
7. **Separate expected outcomes from `ERROR` logging:** record metrics/rejection counts and bounded samples when appropriate.
8. **Measure after the change:** check throughput/latency/allocation/GC on representative data and the target JVM version.
9. **Test both success and failure paths:** verify both semantics and observability of rare errors.
10. **Keep the optimization only if it is worthwhile:** simple, contract-compliant, maintainable code matters more than an unrepresentative benchmark result.

## 19. Tests you should have

| Case | Expectation |
|---|---|
| Valid data | Parsed accurately, not skipped |
| Empty or `null` string | Returns rejection status per API, no unintended NPE |
| Non-grammar characters | Rejected properly, preserving position/error code when needed |
| `Integer.MAX_VALUE` and `Integer.MAX_VALUE + 1` | Boundary accepted; overflow rejected without wraparound |
| Signed numbers, leading zeros, whitespace | Behavior matches documented grammar |
| High-frequency invalid data | No flood of exceptions/logs on the expected branch |
| Real I/O error | Exception is preserved, not turned into EOF |
| Record not found | Expected outcome, does not mask dependency errors |
| Multiple threads sharing a structure | Checks and accesses follow thread-safety rules, avoiding TOCTOU |
| Cancellation/interruption | Worker respects the signal rather than catching broadly and running forever |
| Performance under production-like load | Measurable throughput, latency, and allocation at defined error rates |
| API compatibility | Existing callers still receive results/errors per contract after refactoring |

In particular, **correctness testing must come before benchmarking**. A fast parser that accepts overflowed numbers or rejects valid data is not a successful optimization.

## 20. Summary

**Not using exceptions for frequent control flow** means not using `throw/catch` as a substitute for normal conditions that an algorithm can express directly. For EOF, loops, empty lookups, and frequently rejected user input, an explicit condition or result type is usually easier to read, easier to observe, and potentially faster than repeatedly creating exceptions.

That **does not mean avoiding exceptions at all costs**. Infrastructure failures, contract violations, or abnormal states still need semantically accurate exception paths, with proper `cause` and cleanup. Do not sacrifice grammar, invariants, thread safety, or debuggability just to reduce an unmeasured number of `throw`s.

A practical decision formula is: **identify expected conditions → choose the appropriate result channel → keep exceptions for real failures → measure hot paths with reliable benchmarks → re-verify correctness and observability**.

### References

- [Java Language Specification 11 — Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html)
- [Java SE 17 — Throwable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html)
- [Java SE 17 — NumberFormatException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NumberFormatException.html)
- [Java SE 17 — Integer.parseInt](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html#parseInt(java.lang.String))
- [Java SE 17 — OptionalInt](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/OptionalInt.html)
- [Java SE 17 — InputStream.read](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html#read())
- [Java SE 17 — BufferedReader.readLine](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html#readLine())
- [OpenJDK — Java Microbenchmark Harness (JMH)](https://openjdk.org/projects/code-tools/jmh/)
