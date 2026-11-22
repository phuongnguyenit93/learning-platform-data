# Using Breakpoints and `peek` for Observation Under Optimization Limits

In the **Debugging and Testing Pipelines** chapter of **Java Stream API**, a very common difficulty is that code looks like it executes step by step from top to bottom, yet in practice only runs when a **terminal operation** is invoked, can short-circuit early, run concurrently, or have steps that do not affect the result **elided** by the JVM/Stream implementation.

This is especially confusing when developers set a breakpoint inside a `filter`, `map`, or `peek` lambda, or add `System.out.println` to "inspect each element." A breakpoint that never fires **does not prove a bug**; a log line that never appears **does not prove an element doesn't exist**. Before changing the algorithm, you must understand the pipeline's contract.

This lesson teaches how to:

- Use **breakpoints** to inspect values and exceptions at the right stage.
- Use `Stream.peek` as an **observation tool for diagnostics**, without modifying data.
- Understand the differences among **lazy evaluation**, **short-circuiting**, **encounter order**, **Stream optimizations**, and **JIT/debugger effects**.
- Recognize when `count()` on a sized source can **skip executing lambdas** in intermediate stages.
- Choose better techniques when verifying **business results**, **processed element counts**, or **performance**.
- Avoid turning `peek` into a place to mutate data, write audit records, call APIs, or update shared state.

> **Example version:** Java 17 or higher. `Stream.peek` has existed since Java 8. The optimization contract allowing traversal elision when computing `count()` has been documented explicitly since Java 9; exact behavior may vary across JDKs, source types, and pipelines. Never use log line counts as a test assertion.

## 1. Execution Flow Map: Describing a Pipeline Is Not Executing It

A pipeline typically has three parts:

~~~text
Source                   Intermediate operations           Terminal
------                   -----------------------           --------
orders.stream()   --->   filter -> map -> peek      --->   toList()
                           |        |        |
                        generally lazy; do not run on declaration
~~~

Example:

~~~java
import java.util.List;
import java.util.stream.Stream;

List<Integer> numbers = List.of(1, 2, 3, 4);

Stream<Integer> pipeline = numbers.stream()
        .filter(n -> n % 2 == 0)
        .map(n -> n * 10)
        .peek(n -> System.out.println("peek=" + n));

// No terminal operation yet: do not expect peek logs.
System.out.println("Pipeline prepared");

List<Integer> result = pipeline.toList();

System.out.println(result); // [20, 40]
~~~

At the moment `pipeline` is assigned, Java only builds a **description of the processing steps**. The `filter`, `map`, and `peek` lambdas generally have not processed any elements yet.

When `toList()` is called, the terminal operation demands the result and the pipeline executes. On an ordered `List` source, a sequential pipeline like this typically observes `20` and `40` in `peek`; **still, never turn `peek` invocations into a program requirement**.

Do not confuse this with `List.stream().forEach(...)`: `forEach` is a terminal operation, whereas `peek` is an intermediate operation.

## 2. What `peek` Does—and What It Does Not Do

Basic signature:

~~~java
Stream<T> peek(Consumer<? super T> action)
~~~

`peek` returns a Stream containing **semantically the same elements**, while supplying an action to observe elements as they pass through that point **if the processing step is executed**.

~~~java
List<String> values = List.of("a", "bb", "ccc");

List<Integer> lengths = values.stream()
        .map(String::length)
        .peek(length -> System.out.println(
                "Length observed: " + length))
        .toList();
~~~

`peek` does not replace `map`: any return value cannot be used because `Consumer.accept` returns `void`. `peek` also does not replace `filter`: it never decides which elements are kept.

| Method | Specified role | Output |
| --- | --- | --- |
| `map(f)` | Transforms each element via function `f` | Stream of new result type |
| `filter(p)` | Keeps only elements matching predicate | Potentially fewer elements |
| `peek(action)` | Allows action to observe elements when executed | Preserves elements in the pipeline |
| `forEach(action)` | Terminal operation executing action on results | Returns no Stream |
| `forEachOrdered(action)` | Terminal operation executing action in encounter order if any | Returns no Stream |
| `count()` | Terminal operation counting result elements | `long` |

**Important warning:** The Java API permits implementations to **skip executing certain operations or avoid traversing source elements** if the exact result can be computed otherwise. Therefore, **never use `peek` as a mandatory mechanism to run audits, write to a DB, mutate state, count callbacks, or record transaction events**.

## 3. Why Breakpoints Inside `peek` Might Never Hit: `count()` Optimization

Here is a classic scenario:

~~~java
import java.util.List;

long count = List.of("A", "B", "C").stream()
        .peek(value -> System.out.println("Seen: " + value))
        .count();

System.out.println("count=" + count); // 3
~~~

Beginners often expect three `Seen: ...` lines. Yet on modern JDKs, **there is no guarantee** that any line will be printed.

Why?

1. The source is a `List` whose exact element count is known.
2. `peek` does not alter the number of elements in the Stream.
3. `count()` only needs to return the resulting element count.
4. If the runtime can determine that number from the source and pipeline properties, it can **skip traversing** the three elements and **skip invoking the `peek` action**.

The `Stream.count()` API documentation explicitly describes this optimization: with a sized source and intermediate operations that do not change cardinality, eliding execution still yields **the exact right `count` result**.

A similar example:

~~~java
long count = List.of(1, 2, 3).stream()
        .map(n -> {
            System.out.println("Map called with: " + n);
            return n * 10;
        })
        .count();

System.out.println(count); // 3
~~~

`map` does not change cardinality; mapper invocations may be elided if unneeded to determine `count()`.

### What you may and may not conclude

**Valid conclusions:**

- `count()` correctly returns `3` for this example.
- Actions in `peek`/`map` are not a reliable counter of traversed elements.
- Breakpoints inside those lambdas **might never trigger**.

**Invalid conclusions:**

- "The IDE or debugger is broken."
- "The JVM skipped data."
- "Calling any terminal operation runs every lambda."
- "Every `count()` pipeline skips traversing data."

If there is a `filter` whose keep/drop decision depends on the data, a standard implementation must evaluate the predicate to count accurately unless other information suffices. **Do not make accompanying `peek` invocation counts a mandatory condition**, since the contract still allows optimizations wherever applicable.

## 4. `SIZED`, Source Characteristics, and Limits of Inference

Stream sources can carry metadata via `Spliterator`. Two relevant characteristics:

- `SIZED`: the exact count of remaining elements is known per the source contract.
- `SUBSIZED`: Spliterators produced by splitting also have exact sizes, useful when dividing work.

An `ArrayList`, array, or fixed-size source typically gives the runtime clear size metadata; many I/O or infinite sources do not.

Still, knowing a source has 1,000 elements **does not mean every pipeline produces 1,000 elements**:

~~~java
long count = numbers.stream()
        .filter(n -> n > 0)
        .count();
~~~

`filter` can drop elements; knowing the source size alone is not enough to determine how many elements satisfy the predicate.

Reference table:

| Intermediate step | Can it change output cardinality? | Consequence for `count` inference |
| --- | --- | --- |
| `map` | No, one element produces one element | Often no need to run mapper just to know count |
| `peek` | No | Action may be skipped when `count` optimizes |
| `filter` | Yes | Typically must evaluate predicate |
| `flatMap` | Yes, 0..N elements per input | Cannot infer from source size alone |
| `mapMulti` | Yes, 0..N elements per input | Similarly, needs actual emitted counts |
| `distinct` | May remove duplicates | Must consider data/source characteristics |
| `limit(n)` | May truncate | Can compute result count from metadata in some cases |
| `skip(n)` | May drop leading elements | Some sources can deduce remaining size |

**This table only illustrates optimization possibilities**, not a rigid list of methods that "always call" or "never call" lambdas. Specific JDK versions and sources can vary.

### Do not fake Spliterator characteristics to force the debugger

Writing a custom Spliterator and deliberately misreporting `SIZED`/`SUBSIZED` to force `count` into a desired behavior **violates the source contract**. Characteristics govern how the runtime computes, splits, and optimizes; misreporting them can break correctness.

When you need to observe real data, pick an **execution path suited for debugging**, never corrupt source metadata.

## 5. Placing `peek` Before and After `filter`/`map` to Narrow Down Issues

A useful diagnostic technique is observing data at **clearly named boundaries**:

~~~java
List<Integer> result = List.of(1, 2, 3, 4, 5, 6).stream()
        .peek(n -> System.out.println("SOURCE: " + n))
        .filter(n -> n % 2 == 0)
        .peek(n -> System.out.println("AFTER_FILTER: " + n))
        .map(n -> n * 10)
        .peek(n -> System.out.println("AFTER_MAP: " + n))
        .toList();

System.out.println(result); // [20, 40, 60]
~~~

With an ordered source, a **sequential** pipeline, and a terminal demanding all values, this example typically shows each element's path through the stages.

How to read it:

- `SOURCE`: values arriving before the filter.
- `AFTER_FILTER`: values retained by the filter.
- `AFTER_MAP`: values after transformation.
- `result`: actual output to verify.

**Key point:** a `peek` placed **after** `filter` only sees elements that passed the filter at that step. To investigate why an element was dropped, the breakpoint or log must be **inside the predicate** or **before `filter`**.

### Observation labels prevent confusion

Don't just print `System.out.println(n)` in multiple places, or you won't know which stage produced the number. When diagnosing:

~~~java
.peek(n -> System.out.printf(
        "[stage=after-map] n=%d%n", n))
~~~

If there is a business ID, print the ID instead of the entire object:

~~~java
.peek(order -> System.out.printf(
        "[stage=filtered] orderId=%s%n", order.id()))
~~~

Do not print tokens, emails, secrets, or sensitive content when logs may be stored or forwarded. Debug logs are an output channel with data-exposure risk, not a default safe zone.

## 6. Breakpoints in Lambdas: Where Should You Put Them?

Java IDE debuggers usually let you place a breakpoint right on a lambda line. However, single-line chained lambdas can be hard to step through when multiple operations share or sit near the same lines.

Example:

~~~java
List<Integer> result = values.stream()
        .filter(n -> n > 0)
        .map(n -> n * 2)
        .toList();
~~~

To debug a predicate or mapper, expand the lambda into a block:

~~~java
List<Integer> result = values.stream()
        .filter(n -> {
            boolean accepted = n > 0; // set breakpoint here
            return accepted;
        })
        .map(n -> {
            int mapped = n * 2;       // set breakpoint here
            return mapped;
        })
        .toList();
~~~

Or extract **named methods**:

~~~java
static boolean isPositive(int n) {
    return n > 0;                    // dedicated breakpoint
}

static int twice(int n) {
    return Math.multiplyExact(n, 2); // dedicated breakpoint
}
~~~

Usage:

~~~java
List<Integer> result = values.stream()
        .filter(PipelineDebugDemo::isPositive)
        .map(PipelineDebugDemo::twice)
        .toList();
~~~

Advantages:

- Breakpoints have unambiguous locations.
- You can set **conditional breakpoints** such as `n == 42`.
- Easy to inspect local variables, parameters, and the call stack.
- Separates logic so you can unit-test it without running the full Stream.
- Distinguishes data-processing bugs from pipeline observation.

### Workflow for debugging a specific element

1. Create a **finite, reproducible dataset**.
2. If predictable ordering helps, start with a sequential `stream()`.
3. Place a breakpoint in the suspected predicate/mapper rather than everywhere.
4. Use an appropriate condition like `order.id().equals("O-42")`.
5. Call a terminal operation that genuinely needs the result, such as `toList()`.
6. Inspect **input value**, **predicate/mapper result**, and **final output**.
7. If the breakpoint never hits, check **laziness, short-circuiting, source metadata, and optimizations** before blaming the IDE.

**Never use breakpoint hit counts as a business counter.** Stepping in a debugger can drastically slow down the runtime, and lambda execution counts are not always guaranteed by the Stream API.

## 7. Complete Java 17 Program: Observing and Verifying Results

The following program focuses on a realistic scenario: from orders, keep only those that are paid with a positive amount, then build summary records. It demonstrates three observation modes:

- A `toList` pipeline to verify the result.
- `count()` on a sized source illustrating **that `peek` might not execute**.
- A `forEachOrdered` terminal operation when you want to run an action on **each result of an ordered Stream**.

Save as `PipelineDebugDemo.java`:

~~~java
import java.util.List;
import java.util.stream.Stream;

public class PipelineDebugDemo {

    record Order(
            String id,
            long amountCents,
            boolean paid
    ) {}

    record Summary(String orderId, long amountCents) {}

    static boolean eligible(Order order) {
        // Breakpoint: inspect order.id(), paid, amountCents.
        return order.paid() && order.amountCents() > 0L;
    }

    static Summary summarize(Order order) {
        // Breakpoint: inspect post-filter value before creating Summary.
        return new Summary(order.id(), order.amountCents());
    }

    static List<Summary> buildSummaries(List<Order> orders) {
        return orders.stream()
                .peek(order -> System.out.println(
                        "[input] " + order.id()))
                .filter(PipelineDebugDemo::eligible)
                .peek(order -> System.out.println(
                        "[eligible] " + order.id()))
                .map(PipelineDebugDemo::summarize)
                .peek(summary -> System.out.println(
                        "[summary] " + summary.orderId()))
                .toList();
    }

    static void inspectCountElision() {
        long count = List.of(10, 20, 30).stream()
                .peek(n -> System.out.println(
                        "[count-peek] " + n))
                .count();

        // Always 3; count-peek logs are not guaranteed.
        System.out.println("count=" + count);
    }

    static void visitOrderedResults(List<Order> orders) {
        // Terminal action used to process each result,
        // rather than relying on peek as a mandatory mechanism.
        orders.stream()
                .filter(PipelineDebugDemo::eligible)
                .map(PipelineDebugDemo::summarize)
                .forEachOrdered(summary ->
                        System.out.println(
                                "[terminal] " + summary.orderId()));
    }

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("O-01", 10000L, true),
                new Order("O-02", 2500L, false),
                new Order("O-03", 0L, true),
                new Order("O-04", 7100L, true)
        );

        List<Summary> summaries = buildSummaries(orders);

        List<Summary> expected = List.of(
                new Summary("O-01", 10000L),
                new Summary("O-04", 7100L)
        );

        if (!expected.equals(summaries)) {
            throw new AssertionError(
                    "Unexpected summaries: " + summaries);
        }

        System.out.println("result=" + summaries);
        inspectCountElision();
        visitOrderedResults(orders);
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 PipelineDebugDemo.java
java PipelineDebugDemo
~~~

Output **guaranteed by the pipeline contract** on an ordered `List` source:

~~~text
result=[Summary[orderId=O-01, amountCents=10000], Summary[orderId=O-04, amountCents=7100]]
count=3
[terminal] O-01
[terminal] O-04
~~~

In a given run, `[input]`, `[eligible]`, and `[summary]` lines may interleave according to how the pipeline executes. **Do not treat `peek` line order or `peek` line count as test results to assert**; use them solely as diagnostic traces. Inside `inspectCountElision`, the JDK may print zero `[count-peek]` lines.

The crucial distinction: the program checks `summaries` content with `equals`. That is **the proof of correctness** for the business requirement; `peek` lines only help you observe execution when the runtime actually executes those actions.

## 8. Why You Shouldn't Force the Debugger to "Always Hit" Every Element

Distinguish three different things:

1. **Pipeline logic:** which elements belong in the result.
2. **Execution schedule:** which thread runs a lambda, when it is called, and whether the source is split.
3. **Debugger observation:** whether a breakpoint is detected/hit for the executed code.

The Stream API primarily specifies **results and behavioral constraints**, not a promise to invoke every lambda in source-code order.

Beyond Stream implementation optimizations, the JIT can inline or transform how code executes; the debugger and JVM cooperate to support breakpoints, yet debugging can force deoptimization and change timing. **Never interpret speed differences between Debug and Run modes as benchmark results**.

An effective workflow:

- Use breakpoints to inspect **a single value, a conditional branch, or an exception**.
- Use tests with fixed inputs to verify **outputs**.
- Use a profiler/JFR to locate **execution bottlenecks**.
- Use JMH or load tests to measure **performance**.

Do not assume the debugger will always show a call stack matching the exact layout of your pipeline in source code; steps may be inlined, fused, or skipped.

## 9. Short-Circuiting: Only Part of the Input May Be Observed

Terminal operations such as `findFirst`, `findAny`, `anyMatch`, `allMatch`, `noneMatch`, and the intermediate operation `limit` can **stop early** once enough information is available.

Example:

~~~java
List<Integer> numbers = List.of(1, 2, 3, 4, 5);

int firstEven = numbers.stream()
        .peek(n -> System.out.println("Checked: " + n))
        .filter(n -> n % 2 == 0)
        .findFirst()
        .orElseThrow();

System.out.println(firstEven); // 2
~~~

On a **sequential** pipeline with encounter order and this input, the runtime typically only needs to inspect `1` and `2`. Still, do not write tests requiring `peek` to fire exactly twice. In a parallel pipeline, speculative evaluation and result coordination may check more elements before yielding the answer.

Similarly:

~~~java
List<Integer> limited = numbers.stream()
        .peek(n -> System.out.println("Before limit: " + n))
        .limit(2)
        .toList();

System.out.println(limited); // [1, 2]
~~~

`limited` has exactly two elements; **do not conclude** that every diagnostic action before `limit` runs exactly twice across all sources, JDKs, and parallelism levels.

### `findFirst` vs. `findAny`

- `findFirst` preserves the first element in encounter order if the source is ordered.
- `findAny` may return **any matching element**, especially useful when ordering is unneeded during parallel execution.
- If the source is unordered, `peek` logs cannot be used to infer an unspecified business ordering.

**What to test is the correctness of results permitted by the API**, not which elements a log action happened to touch.

## 10. `peek` Before/After `sorted`, `distinct`, and Stateful Operations

Stateful intermediate operations such as `distinct`, `sorted`, `limit`, `skip`, and prefix operations can affect evaluation order or which elements are observed.

### `distinct`

~~~java
List<Integer> input = List.of(3, 1, 3, 2, 1);

List<Integer> unique = input.stream()
        .peek(n -> System.out.println("Before distinct: " + n))
        .distinct()
        .peek(n -> System.out.println("After distinct: " + n))
        .toList();

System.out.println(unique); // [3, 1, 2]
~~~

What is specified: `distinct` keeps unique values; on an ordered Stream, stability preserves the first occurrence of each value. When logs appear, `peek` after `distinct` shows elements **that passed deduplication**. Do not use log line counts to prove how many equality or hash comparisons actually occurred.

### `sorted`

~~~java
List<Integer> sorted = input.stream()
        .peek(n -> System.out.println("Before sorted: " + n))
        .sorted()
        .peek(n -> System.out.println("After sorted: " + n))
        .toList();

System.out.println(sorted); // [1, 1, 2, 3, 3]
~~~

`sorted` may need to collect elements before emitting sorted results. Thus traces before/after `sorted` can look different from pipelines with only stateless stages. **Do not deduce buffer allocation or internal sorting algorithms solely from log order**.

### Limits of inserting `peek` to observe

Adding `peek` **modifies the pipeline** (adding a diagnostic action); console printing also performs I/O and can affect scheduling and performance. It is a fault-isolation tool, not a clean measurement of a production pipeline's characteristics.

## 11. Parallel Streams: Encounter Order Is Not Lambda Execution Order

Example:

~~~java
List<Integer> numbers = List.of(1, 2, 3, 4, 5, 6);

List<Integer> result = numbers.parallelStream()
        .peek(n -> System.out.println(
                "peek " + n + " on "
                + Thread.currentThread().getName()))
        .map(n -> n * 10)
        .toList();

System.out.println(result);
// [10, 20, 30, 40, 50, 60]
~~~

With an ordered `List` source, `toList()` preserves the encounter order of results. Yet `peek` lines can appear **out of 1,2,3,4,5,6 order** and run across multiple threads.

Distinguish:

| Concept | Meaning |
| --- | --- |
| **Encounter order** | Logical order published by the source/pipeline |
| **Execution order** | Schedule of mapper, filter, and peek chosen by the runtime |
| **Output order** | Result element order guaranteed by the terminal operation |
| **Print order** | Order of console log lines when multiple threads print |

Do not conflate these four concepts.

### `forEach` and `forEachOrdered`

~~~java
numbers.parallelStream()
        .forEach(n -> System.out.println("any: " + n));

numbers.parallelStream()
        .forEachOrdered(n -> System.out.println("ordered: " + n));
~~~

- `forEach` does not guarantee actions execute in encounter order.
- `forEachOrdered` executes the action on result elements in encounter order for ordered sources.
- However, **`forEachOrdered` does not force preceding mappers or `peek` calls to run sequentially or in order**; it coordinates execution of the terminal action.

If business output requires ordered results, verify `toList`/`forEachOrdered` and an ordered source—never assert on log strings inside `peek`.

### Breakpoints in parallel pipelines

When multiple workers hit the same breakpoint simultaneously:

- The IDE may pause one thread or all threads depending on suspend mode.
- Pausing alters execution scheduling and can mask or expose race conditions.
- Local variables in one task do not represent the entire pipeline.
- Shared mutable state may change before you inspect it.

To debug simple logic bugs, start **sequentially**. To debug concurrency bugs, write targeted tests for concurrent state, collect thread dumps/profiler traces, and avoid generalizing from a single debug session.

## 12. Never Turn `peek` into a Counter or Side-Effecting Audit

An anti-pattern:

~~~java
int[] countSeen = {0};

long count = numbers.stream()
        .peek(n -> countSeen[0]++)
        .count();

System.out.println(countSeen[0]);
// Do not assert this always equals numbers.size().
~~~

Main issue: `peek` does not promise the action executes for every element. With a parallel Stream, updating a shared `int[]` is also **not thread-safe**.

Even switching to `AtomicInteger`:

~~~java
java.util.concurrent.atomic.AtomicInteger seen =
        new java.util.concurrent.atomic.AtomicInteger();

long count = numbers.stream()
        .peek(n -> seen.incrementAndGet())
        .count();
~~~

You eliminate the increment race, yet **you still haven't fixed the semantics**: the implementation can still skip `peek` if unneeded to compute the result.

### What to do when you truly need counts?

To count result elements, use `count()`:

~~~java
long matched = numbers.stream()
        .filter(n -> n > 0)
        .count();
~~~

To count elements per group, use `groupingBy(..., counting())`. To compute multiple metrics at once, use an appropriate collector. If mandatory auditing is required, design a **dedicated event-processing protocol** with contracts for transactions, retries, and errors; never depend on Stream `peek`.

**Never use `peek` to:**

- Write mandatory financial records.
- Delete or mutate source data.
- Call an HTTP endpoint required to fire once per element.
- Update a shared Map from a parallel Stream.
- Replace assertions on result contents.

## 13. Using the Debugger to Investigate Exceptions in Mappers/Filters

In real data, many failures arise from a single malformed element:

~~~java
List<String> raw = List.of("10", "20", "oops", "30");

List<Integer> values = raw.stream()
        .map(Integer::parseInt)
        .toList();
// NumberFormatException when encountering "oops".
~~~

There are two main ways to debug this.

### 13.1. Exception breakpoint

Configure a breakpoint for `NumberFormatException` in the debugger. When the exception is thrown, inspect the call stack and the argument being parsed. This helps when you don't know upfront which value breaks the pipeline.

### 13.2. Named method and condition

~~~java
static int parseStrict(String raw) {
    try {
        return Integer.parseInt(raw);
    } catch (NumberFormatException ex) {
        throw new IllegalArgumentException(
                "Invalid integer input: " + raw, ex);
    }
}
~~~

Usage:

~~~java
List<Integer> values = raw.stream()
        .map(PipelineDebugDemo::parseStrict)
        .toList();
~~~

This is an **additional helper method sample** for the `PipelineDebugDemo` class in Section 7; to run standalone, place the method inside that class and ensure `raw` is in scope.

### Never swallow errors inside `peek`

Do not put `try/catch` inside `peek` to "fix" data and continue the pipeline without an explicit policy. If the parser allows invalid rows, use a parse step producing a `ParseResult` representing success/failure, then count invalid records and report them explicitly.

If the pipeline reads an I/O source, file-read errors must never be converted into "0 records" just so a terminal operation returns cleanly. Debugging techniques must never weaken error-detection contracts.

## 14. Null Data and Breakpoint Pitfalls After `filter`

Suppose a list can contain `null`:

~~~java
List<String> raw = new java.util.ArrayList<>();
raw.add(" A ");
raw.add(null);
raw.add(" B ");

List<String> cleaned = raw.stream()
        .filter(java.util.Objects::nonNull)
        .map(String::trim)
        .toList();

System.out.println(cleaned); // [A, B]
~~~

If you set a breakpoint **inside `String::trim`** or in a `peek` after the filter, you will not see the `null` element that was dropped. That is expected behavior, not data mysteriously vanishing.

When your goal is finding why `null` appeared in the input, inspect data **before `filter`** or check the upstream data producer. If `null` is invalid business data, do not silently filter it out just to avoid `NullPointerException`; validate and report errors as required.

**Do not use `List.of("A", null, "B")` as a fixture** because `List.of` rejects `null` elements; this example uses `ArrayList`, which allows `null`.

## 15. I/O Resources and `peek`: Short-Circuiting Does Not Auto-Close the Source

A source like `Files.lines` owns a file handle. Adding `peek` to log or `limit` to stop early **does not replace `close()`**.

Correct example:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

static List<String> firstWarnings(Path path) throws IOException {
    try (Stream<String> lines =
            Files.lines(path, StandardCharsets.UTF_8)) {

        return lines
                .filter(line -> line.startsWith("WARN"))
                .peek(line -> System.out.println(
                        "[diagnostic] " + line))
                .limit(3)
                .toList();
    }
}
~~~

`try-with-resources` closes the Stream upon exiting the block, even if `limit(3)` already gathered enough elements or a terminal operation throws an exception.

Two points to distinguish:

- `peek` is solely observational and **may be skipped** on some execution paths.
- `Files.lines` can throw I/O errors **lazily during traversal**, not only when opening the file. Never swallow those errors to return a fake complete report.

If you need to verify that your code **actually closes the stream**, you can attach an `onClose` callback in a mock test to confirm the hook runs on close:

~~~java
java.util.concurrent.atomic.AtomicBoolean closed =
        new java.util.concurrent.atomic.AtomicBoolean(false);

try (Stream<Integer> stream = Stream.of(1, 2, 3)
        .onClose(() -> closed.set(true))) {
    stream.findFirst();
}

if (!closed.get()) {
    throw new AssertionError("Expected Stream.close()");
}
~~~

This tests the Stream close mechanism on a synthetic stream; it **does not replace** integration tests tracking real file handles.

## 16. When to Use `forEachOrdered` Instead of `peek`?

If the goal is executing an action **for each result element** when the pipeline finishes normally, use a terminal operation.

~~~java
List<String> names = List.of("Lan", "An", "Minh");

names.stream()
        .map(String::toUpperCase)
        .forEachOrdered(System.out::println);
~~~

On an ordered source, the terminal action outputs values in encounter order. Still, before using it for an audit system, remember:

1. **I/O/DB can fail** partway through.
2. A transaction or message broker may need retries/idempotency and partial-failure handling.
3. Re-running the pipeline repeats the action.
4. An exception can halt the pipeline before processing every element.
5. `forEachOrdered` does not automatically provide *exactly-once* semantics.

Thus `forEachOrdered` fits when per-element action is **the terminal goal itself**, while reliable transactional workflows require application-level design.

If your goal is purely debugging, `peek` is often handy when you want **to keep a single terminal result at the end**; never call a terminal `forEach` mid-pipeline and then try to keep using the old Stream.

## 17. Testing Results: Stronger Evidence Than Logs and Breakpoints

A test must never declare victory merely because "three log lines appeared." Instead, compare the output against a clear **oracle**.

Example:

~~~java
List<Integer> input = List.of(-1, 0, 1, 2, 3, 4);

List<Integer> actual = input.stream()
        .filter(n -> n > 0)
        .map(n -> n * 2)
        .toList();

List<Integer> expected = List.of(2, 4, 6, 8);

if (!expected.equals(actual)) {
    throw new AssertionError(
            "Expected=" + expected + ", actual=" + actual);
}
~~~

This verifies `filter` and `map` correctness on both **values and order**, regardless of how many times `peek` ran.

You can use an independent loop as an oracle:

~~~java
List<Integer> expected = new java.util.ArrayList<>();

for (int value : input) {
    if (value > 0) {
        expected.add(value * 2);
    }
}
~~~

When testing general properties, generate finite inputs using a fixed seed; record the seed and failing input on failure. Never generate random values inside a parallel pipeline's lambda expecting a debugger to reproduce the exact same execution order.

### Testing with invariants

For `filter(p)` on an ordered List:

- Every result element satisfies `p`.
- The result preserves the relative order of selected elements.
- No element appears in the result that wasn't in the source, unless the pipeline transforms values.
- Result count never exceeds input count.

These invariants are far stronger than counting how many times a log action in `peek` executed.

## 18. A Debugger Is Not a Profiler, and Logs Are Not Benchmarks

Setting breakpoints halts the program, can trigger JIT deoptimization, and alters thread scheduling. Console printing inside `peek` is slow I/O and can introduce contention when multiple threads write simultaneously.

Consequently, **never use approaches like this to draw performance conclusions**:

~~~java
// Do not benchmark with peek output:
long start = System.nanoTime();

numbers.stream()
        .peek(System.out::println)
        .mapToLong(Integer::longValue)
        .sum();

long elapsed = System.nanoTime() - start;
~~~

This measurement mixes computation cost with console I/O cost and JIT/GC state. A single run is also noisy due to warm-up, OS scheduling, and allocation.

Pick the right tool for the question:

| Question | Right tool |
| --- | --- |
| Why was record O-42 dropped? | Conditional breakpoint in predicate; minimal fixture |
| Which field is null? | Breakpoint before filter or in parser |
| Are group totals accurate? | Unit tests/oracle, assertions on Map/List |
| Was `peek` elided because of `count`? | Read Stream contract, tiny verification snippet |
| Does parallel ordering alter values? | Sequential vs. parallel tests per contract |
| Where is CPU hot? | CPU profiler or Java Flight Recorder (JFR) |
| Are allocations/GC slowing things down? | JFR, GC logs, profiler-guided benchmarks |
| Does replacing `map` with `mapToInt` help? | JMH with identical workload and terminal operation |

**Keep in mind:** Logging helps inspect data, yet log output is rarely a valid measurement of latency, throughput, or lambda invocation counts.

## 19. Controlled Logging When You Cannot Pause With a Debugger

In production environments, pausing a process with breakpoints is rarely acceptable. Structured, tightly bounded logging may be needed instead:

- Enable diagnostics only for **a single request/batch** or a tiny sample rate.
- Attach a `correlationId` or business ID instead of dumping full objects.
- Cap the number of log records, field lengths, and enablement duration.
- Exclude sensitive information, passwords, tokens, or personal data.
- Clearly treat logs as **best-effort observation**, not a complete audit.
- Disable diagnostics after investigation and re-measure performance without logging.

A diagnostic predicate might check one specific ID before returning:

~~~java
static boolean eligible(Order order) {
    if ("O-42".equals(order.id())) {
        // Set conditional breakpoint here instead of logging every order.
        System.out.println(
                "Investigating amount=" + order.amountCents());
    }
    return order.paid() && order.amountCents() > 0;
}
~~~

This is **temporary debugging code**. Do not leave `println` on a production hot path without proper observability controls.

When input recording must be guaranteed, perform it at the **system ingestion boundary** using a logging/audit mechanism with its own contract—never inside Stream `peek`, which may skip callbacks.

## 20. Commonly Misinterpreted Situations

| Observation | Likely cause | Right way to verify |
| --- | --- | --- |
| `peek` prints nothing on `count()` | Count inferred from source size without traversal | Check count result, source characteristics, and API contract |
| Breakpoint in `map` never hits | Missing terminal op, or mapper elided | Verify call path, terminal op, or temporarily use `toList` |
| `peek` after `filter` misses record X | X was dropped earlier by filter | Breakpoint in predicate or observe before filter |
| `peek` sees only a few elements | Short-circuit (`findFirst`/`limit`/`anyMatch`) | Check terminal type; do not expect full source logs |
| `peek` prints out of order | Parallel pipeline; print order differs from encounter order | Test output with `toList`/`forEachOrdered` |
| `sorted` causes strange log order | Stateful stage may buffer elements | Inspect output order; do not infer internals from logs |
| Debug mode runs slowly | Breakpoints, deoptimization, console I/O | Measure with profiler/benchmark without debugger pauses |
| `AtomicInteger` in `peek` stays 0 | Action may not execute | Count results via terminal operation, not side effects |
| Logs look fine but final output is wrong | Logs aren't an oracle; may observe only one stage | Compare against fixture or reference loop |
| File source stays open after early stop | `limit/findFirst` does not auto-close I/O | Wrap `Files.lines` in `try-with-resources` |
| Parallel fails intermittently | Shared mutable state or ordering assumptions | Reduce to deterministic test, check races and collectors |
| Exception surfaces at terminal call | Lazy pipeline; mapper errors fire on consumption | Exception breakpoint and call stack |

Never "fix" a missing log by adding a side effect to force a lambda to run. That can turn a valid pipeline into code relying on unspecified behavior.

## 21. Safe Debugging Workflow in a Real Project

A pragmatic workflow:

### Step 1 — Write down the expected output

For example: "Out of four orders in the fixture, only O-01 and O-04 have `paid=true` and `amountCents>0`."

### Step 2 — Build a small, stable fixture

Use `List.of(...)` with a few records to remove DB/network noise. If a bug appears on random data, capture the seed and failing input.

### Step 3 — Confirm a terminal operation exists

A freshly declared Stream will not traverse itself. Choose `toList`, `collect`, `sum`, or another terminal operation matching your goal.

### Step 4 — Debug sequentially first

If logic does not inherently depend on parallelism, use `stream()` to trace one element step by step. If the bug occurs only in parallel, keep a dedicated parallel test.

### Step 5 — Set a conditional breakpoint

Place it inside a named predicate/mapper keyed on a specific record ID; avoid breaking on every element and stalling the entire application.

### Step 6 — Use labeled `peek` if needed

Observe before and after the suspected step, without treating log counts as guaranteed assertions.

### Step 7 — Verify the result against an oracle

Compare Lists/Maps/Optionals per contract, not logs or thread names.

### Step 8 — Remove diagnostics and run regression tests

Delete or disable diagnostic `peek` calls; confirm the fix does not rely on side effects. Test empty sources, invalid inputs, boundary values, and ordered vs. unordered sources.

### Step 9 — Measure performance if needed

Use a profiler/JFR/JMH or load tests on representative workloads, never timing while breakpoints or console logging are active.

## 22. Practice Exercises

### Exercise 1 — Why didn't `peek` print all three lines?

~~~java
long n = List.of(10, 20, 30).stream()
        .peek(System.out::println)
        .count();
~~~

**Question:** What is `n`? Is the console required to print three numbers?

**Answer:** `n == 3`. There is no guarantee three lines are printed: the implementation can use the source's known size to return `count` without invoking the `peek` action.

### Exercise 2 — Breakpoint never hits

~~~java
Stream<String> pipeline = List.of("a", "b").stream()
        .map(String::toUpperCase);
~~~

**Question:** Why doesn't a breakpoint inside the mapper pause?

**Answer:** There is no terminal operation yet. The pipeline has not requested element processing. Add a result-consuming terminal like `toList()` to inspect output; also avoid assuming every mapper runs if using a terminal that can optimize from metadata.

### Exercise 3 — `peek` before and after `filter`

~~~java
List<Integer> data = List.of(1, 2, 3, 4);

List<Integer> out = data.stream()
        .peek(n -> System.out.println("A=" + n))
        .filter(n -> n % 2 == 0)
        .peek(n -> System.out.println("B=" + n))
        .toList();
~~~

**Question:** What is `out`? At step B, are odd numbers observed?

**Answer:** `out = [2,4]`. The `peek` after `filter` sits only on the stream of retained elements; it never sees odd numbers dropped earlier. Do not write tests asserting exact log counts.

### Exercise 4 — `findFirst` and invocation count

~~~java
int first = List.of(5, 7, 8, 10).stream()
        .peek(n -> System.out.println(n))
        .filter(n -> n % 2 == 0)
        .findFirst()
        .orElseThrow();
~~~

**Answer:** `first == 8`. On an ordered, sequential pipeline, typically only elements up to 8 need to be observed; parallelism and optimizations can change observed callback counts. Assert only the result `8`.

### Exercise 5 — How does `count` with `filter` differ from `map`?

**Question:** Why can `map(...).count()` skip running the mapper, whereas `filter(...).count()` usually must inspect input values?

**Answer:** `map` preserves element count, whereas `filter` can drop elements. When the source has a known size and stages do not change cardinality, `count` can be computed from metadata. With a data-dependent `filter`, the predicate usually must be evaluated to know how many elements remain.

### Exercise 6 — Log order in parallel

~~~java
List<Integer> out = List.of(1, 2, 3, 4)
        .parallelStream()
        .peek(System.out::println)
        .toList();
~~~

**Answer:** `out` preserves the `List` source order `[1,2,3,4]`; `peek` print order is not guaranteed to be 1,2,3,4. Never use logs as an oracle for encounter order.

### Exercise 7 — Counting with `AtomicInteger` inside `peek`?

**Question:** Can you increment an `AtomicInteger` inside `peek` to audit each element exactly once?

**Answer:** No. Atomicity only handles concurrent updates; it does not force the Stream to execute the `peek` action. Mandatory auditing requires a dedicated workflow managing errors, retries, and idempotency if needed.

### Exercise 8 — `sorted` and breakpoints

**Question:** When placing breakpoints in `peek` before and after `sorted`, why might pause order not match a simple read-one-element-then-print-immediately loop?

**Answer:** `sorted` is stateful and may collect data before emitting sorted elements. Breakpoints only show invocations executed by the runtime at that instant, not an exact guarantee of internal buffering behavior.

### Exercise 9 — Debugging a file-reading pipeline

~~~java
List<String> first = Files.lines(path)
        .peek(System.out::println)
        .limit(5)
        .toList();
~~~

**Answer:** The I/O source must be closed. Place creation and consumption of `Files.lines` inside `try-with-resources`, even when `limit` stops early. Do not rely on `peek` to verify resource closure.

### Exercise 10 — What belongs in tests vs. the debugger?

**Question:** You need to prove every paid order with a positive amount appears in the result; should you count `peek` logs or compare the `List` against an oracle?

**Answer:** Compare the `List`/`Map` against a fixture or independent oracle. Breakpoints and `peek` help locate where a bug is, not prove full correctness of the result.

## 23. Key Takeaways

- **Streams are lazy:** declaring a pipeline does not run lambdas; a terminal operation is required.
- **`peek` is an observation tool, not a callback guarantee.** Implementations may elide stages when the final result still matches the contract.
- **`count()` on a `SIZED` source** can be computed directly without traversing elements, so breakpoints in `peek`/`map` may never hit.
- **Short-circuiting operations** like `findFirst`, `anyMatch`, and `limit` can stop before traversing the whole source; never infer processed element counts from logs.
- **Encounter order differs from execution order.** `toList` or `forEachOrdered` can preserve result order even when `peek` logs in a parallel Stream appear unordered.
- **The most effective breakpoints** are conditional breakpoints inside named predicates/mappers on small, reproducible datasets.
- **Side effects in `peek` are risky:** never use them for auditing, updating shared Maps, emitting required events, or counting callback invocations.
- **Logs and debuggers are not benchmarks.** Use JFR, a profiler, JMH, or end-to-end measurements for performance conclusions.
- **I/O sources must be closed**, even when short-circuiting: wrap `Files.lines` in `try-with-resources`.
- **Prove correctness with data and outputs:** assertions, oracles, invariants, and regression tests; treat `peek` purely as a temporary diagnostic trace.

**Main takeaway:** In the Java Stream API, **breakpoints and `peek` reveal only the invocations the runtime actually performs**, not a contract that every element must pass through every line of code. Once you understand lazy evaluation, `count` optimizations, short-circuiting, and parallel execution, you know **when log traces help, when their absence is completely valid, and when to switch to result tests or a profiler** to reach accurate conclusions.
