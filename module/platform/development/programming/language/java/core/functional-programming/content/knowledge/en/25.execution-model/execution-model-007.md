# Pipelines Without Guaranteed Side Effects When the JDK Optimizes Away Steps

## 1. When Calling a Terminal Operation, Does Every Lambda Run?

A common intuition when learning Streams is: **“I wrote a `map` or `peek` step, so the terminal operation will definitely run that step for every element.”** This reasoning is **incorrect according to the Java Stream contract**.

Consider the code:

~~~java
List<String> names = List.of("An", "Binh", "Chi");
long count = names.stream()
        .peek(System.out::println)
        .count();
System.out.println("count=" + count);
~~~

This is illustrative code inside a method; it requires `import java.util.List;`. Some people predict the program will print three names and then print `count=3`. However, on a JDK capable of inferring the cardinality of a List, the `count()` call **can immediately return 3 without traversing each element**, because `peek` does not change the element count. In that case, no names are printed.

Similarly, if a `map` only transforms each element into another value while preserving **one output per input**, running the mapper may be unnecessary to determine the count:

~~~java
long count = names.stream()
        .map(String::toUpperCase)
        .count();
// 3, and creating uppercase strings may be skipped.
~~~

This is **not a JDK bug**, nor does it mean `peek` is inherently useless. **A Stream describes how to compute a result**, rather than a list of commands that must be executed in every configuration. If the implementation can prove that skipping part of a pipeline **does not change the requested result**, it is allowed to skip invoking the functions attached to that step as well.

According to the Java SE 17 documentation on side effects, side effects of behavioral parameters are generally **not guaranteed to always occur**, except for specific contracts explicitly stated, notably the action of the `forEach` and `forEachOrdered` terminal operations.

**Key takeaway:** Do not hide **mandatory validation, data persistence, notifications, or business state updates** inside `map`/`peek` and then use a terminal operation that does not need the transformed values hoping they will be executed.

## 2. Understanding Pipeline Structure Before Discussing Optimization

A Stream pipeline consists of three parts:

~~~text
SOURCE                   INTERMEDIATE                     TERMINAL
List / Set / array  ->   filter / map / peek / sorted  ->   count / toList / sum
                            (intermediate operations)       (terminal operation)
~~~

- **The source** supplies elements according to its own contract. For example, a List typically has an encounter order and knows its size.
- **Intermediate operations** describe the creation of a new Stream; most do not process elements immediately when called. The JDK documentation describes them as **lazy**.
- **The terminal operation** requests a result or an action. It may traverse all elements, traverse part of them, or **not need to traverse at all** if the result can be inferred by other means.

Example:

~~~java
Stream<String> pipeline = names.stream()
        .filter(s -> s.length() > 2)
        .map(String::toUpperCase);

// Only from here is there a request to produce a final result:
List<String> result = pipeline.toList();
~~~

This snippet requires importing `java.util.stream.Stream`, `java.util.List`, and having the `names` variable. When `pipeline` is created, filtering and mapping do not need to run yet. When `toList()` is called, the value of each resulting string must be produced to build the list, so the computations affecting those values are evaluated as required by the pipeline.

### 2.1. Three Different Phenomena Often Lumped Together as “Skipping Steps”

| Phenomenon | Why doesn't every callback run? | Example |
| --- | --- | --- |
| **Lazy evaluation** | No terminal operation has been called yet | `stream.map(f)` without using it afterward |
| **Short-circuiting** | Enough information is available to terminate early | `anyMatch` encounters a matching element |
| **Elision/optimization** | A step or the entire pipeline is unnecessary for the result | `List.stream().peek(action).count()` |

These phenomena can combine, but their causes differ. For instance, `findFirst()` can stop after the first element without evaluating the remaining ones; `count()` on a source with a known size may not even need to **start traversal**.

What a programmer must check is **the result promised by the terminal operation**, rather than expecting every intermediate lambda to run a full number of times before a result is produced.

## 3. The Stream Optimization Contract in Java 17

The `Stream<T>` documentation allows the implementation to optimize computation and elide operations or stages if it can prove that eliding them **does not affect the computation result**. As a consequence, behavioral parameters—the lambdas/method references supplied by the programmer to operators—may not be invoked.

Java SE 17 also notes that when behavioral parameters have side effects, there are generally no guarantees regarding:
- **Whether the side effect always occurs**, because the step may be skipped.
- **The timing and order of side effects** relative to other side effects, especially in parallel Streams.
- **Which thread executes the callback** for an element, or whether steps on the same element are executed by the same thread.
- **Visibility of side effects to other threads** without proper synchronization mechanisms according to the contract.

These points are why Java encourages callbacks in most Stream operations to be **stateless** and **non-interfering**.

### 3.1. Stateless

A stateless function does not rely on external mutable state that can change during pipeline execution. Good example:

~~~java
List<Integer> squares = List.of(2, 3, 4).stream()
        .map(n -> n * n)
        .toList();
// [4, 9, 16]
~~~

The mapper depends only on `n` and returns a new value. If the framework changes the scheduling or partitioning, the data semantics remain clear.

Counterexample:

~~~java
// DO NOT use external state to compute values inside a pipeline:
// int[] counter = {0};
// List<Integer> result = numbers.parallelStream()
//         .map(n -> n + counter[0]++)
//         .toList();
~~~

The counterexample is commented out because mutating `counter` makes the value of `map` depend on order and thread; in a parallel stream there is also a data race. Even if a sequential test appears to work, that result cannot be treated as a safe contract for freely switching to parallel.

### 3.2. Non-interfering

A non-interfering lambda does not modify the Stream source while it is being traversed. Example to avoid:

~~~java
// UNSAFE: modifying the source structure while streaming.
// List<Integer> values = new ArrayList<>(List.of(1, 2, 3));
// values.stream().forEach(v -> values.add(v * 10));
~~~

Modifying a List during traversal can cause `ConcurrentModificationException` or unexpected behavior. Not every violation is necessarily reported via an exception. To produce new data, use an appropriate transformation + terminal operation instead of mutating the source inside the callback.

### 3.3. Optimization Is Not a License to Change the Result

The JDK is allowed to skip a step **only when it does not change the result according to the pipeline's contract**. For example:

~~~java
List<String> transformed = List.of("A", "BB").stream()
        .map(String::toLowerCase)
        .toList();
~~~

The required result is `[a, bb]`. It cannot simply drop the lowercasing operation, return `[A, BB]`, and still claim to be a valid optimization. Conversely, if the terminal operation only requests **the count**, those intermediate lowercase values may not need to be created.

**Distinction:** “A mapper may not be invoked in a pipeline” does not mean “the JDK can return an incorrect result.” Callback values needed for the result must be processed with the correct semantics; side effects outside the result are what you should not rely on.

## 4. Classic Case: count() and Sized Sources

`Stream.count()` returns the number of elements in the final Stream. It can compute the count from the source's metadata, especially when the source has an exact size and the intermediate steps do not change cardinality.

Some `Spliterator` implementations have the `SIZED` characteristic, allowing the JDK to know the exact size by contract. Common collections like List can provide their size without traversing every element.

~~~java
List<String> names = List.of("An", "Binh", "Chi");
long total = names.stream()
        .map(String::toUpperCase)
        .count();
// total == 3
~~~

Because `map` is a **one-input -> one-output** operation, there is no need to call `String::toUpperCase` to know there are still three elements.

Similarly:

~~~java
AtomicInteger counter = new AtomicInteger();

long total = names.stream()
        .peek(s -> counter.incrementAndGet())
        .count();
~~~

This illustrative snippet requires importing `java.util.concurrent.atomic.AtomicInteger`. On JDK 17 in this article's tests, `total=3` and `counter.get()=0`; this behavior is an example of a valid optimization, not a guaranteed callback count across all versions.

### 4.1. Why Is peek Not Guaranteed to Be Called?

`peek(action)` is an intermediate operation meant specifically for **observing elements as they actually flow through**. It neither adds nor removes elements, so computing the count may not require `peek`'s action.

The API Note of `count()` directly illustrates the case of a List with a known size and `peek(System.out::println)`: the JDK can return the count without processing the pipeline, because what gets printed does not affect the count result.

Do not interpret `peek` as:
- A mandatory “trigger” for every element.
- A mandatory validation step.
- A step for saving/writing data that is guaranteed to succeed.
- A reliable counter for processed elements via side effects.

`peek` is primarily suited for **temporary debugging** or non-essential observation. Even if you see logs in one run, do not assume the next run or a different terminal operation will behave the same way.

### 4.2. map().count() May Not Throw an Exception in the Mapper

Suppose the mapper contains data validation:

~~~java
static int validateAndMeasure(String value) {
    if (value.equals("BB")) {
        throw new IllegalArgumentException("Invalid BB");
    }
    return value.length();
}
~~~

This illustrative method must be declared inside a class. The call:

~~~java
long count = List.of("A", "BB", "CCC").stream()
        .map(MyClass::validateAndMeasure)
        .count();
~~~

Is an **illustrative snippet**, where `MyClass` is assumed to be the class containing the method. In a pipeline over a List of known size, the mapper does not change the element count. The JDK can return `count=3` **without calling validation**; the exception from `"BB"` therefore **does not necessarily occur**.

Do not turn this characteristic into a promise that “map() will never throw an error when ending with count()”. If a different source or another intermediate step forces values to be evaluated, the mapper can run and throw. **Both scenarios show that a design relying on exceptions in a mapper to validate before count is unsafe.**

### 4.3. Operations That Change Cardinality

A count cannot be inferred solely from the source size if the pipeline contains a step that makes the element count data-dependent. Example:

~~~java
long result = List.of("A", "BB", "CCC", "DDDD").stream()
        .filter(s -> s.length() > 2)
        .count();
// 2
~~~

`filter` keeps `CCC` and `DDDD`. The number of output elements requires knowing which elements satisfy the predicate; it cannot simply take the List size of 4 and return 4.

Operations that commonly affect cardinality include `filter`, `flatMap`, `distinct`, `mapMulti`, `takeWhile`, and `dropWhile`. Operations `skip` and `limit` can change the count, but in a simple pipeline over a source with a known size, the cardinality after them can be computed by a direct formula.

| Step | Preserves element count semantically? | Consequence for count |
| --- | --- | --- |
| `map(f)` | Yes, one-in/one-out | Computing `f` may be skipped |
| `peek(action)` | Yes | `action` may be skipped |
| `sorted()` | Yes | Order does not affect element count |
| `filter(predicate)` | Not necessarily | Result usually depends on data |
| `flatMap(f)` | No; one element can produce many elements | Usually needs to determine how many elements are produced |
| `distinct()` | No; duplicate elements may be removed | Result count depends on data or source characteristics |
| `limit(n)` | Can truncate | Count may be inferred if prior size is known |
| `skip(n)` | Can discard | Count may be inferred if prior size is known |

The table reflects optimization opportunities **semantically**, without guaranteeing that the JDK will apply a specific execution strategy for every source/version. When using `filter`, the JDK usually has to evaluate the predicate to compute cardinality, yet **the number of predicate invocations should not be used** as a side-effect counter guaranteed independently of the result.

## 5. Distinguishing “Step Optimized Away” from “Step Not Reached Due to Early Termination”

Take an ordered Stream:

~~~java
List<String> words = List.of("A", "BB", "CCC", "DDDD");
boolean found = words.stream()
        .anyMatch(s -> s.equals("A"));
~~~

`anyMatch` only needs to know **whether at least one element matches**. As soon as it has enough information, a sequential pipeline can return `true` without examining subsequent elements.

An example with a counter for inspection:

~~~java
AtomicInteger inspected = new AtomicInteger();

boolean found = words.stream().anyMatch(s -> {
    inspected.incrementAndGet();
    return s.equals("A");
});
~~~

In the Java 17 program in Section 9, `found=true` and `inspected.get()=1`. This is a verified result on that specific sequential pipeline. The essential point is not “anyMatch always calls the predicate exactly once,” but rather that **this terminal operation can stop before calling the predicate on every element**.

Operations commonly associated with short-circuiting:
- `findFirst()`, `findAny()`: can stop once a matching element is found according to the contract.
- `anyMatch()`: can stop once a matching element is found.
- `allMatch()`: can stop once a non-matching element is found.
- `noneMatch()`: can stop once a matching element is found.
- `limit(n)`: can restrict how many elements proceed further down the pipeline.

With a parallel Stream, multiple elements may already have been or be in the process of being evaluated when enough information is available to finish; you must not rely on **an exact callback count** or **the last processed position** as a business contract.

### 5.1. findFirst and peek May Observe Only Part of the Stream

~~~java
Optional<String> first = words.stream()
        .peek(System.out::println)
        .findFirst();
~~~

This illustrative snippet requires importing `java.util.Optional`. With a non-empty sequential List, finding the first element does not require checking the remaining elements. `peek` can only observe elements that actually pass through; subsequent elements are not guaranteed to be printed just because you wrote `peek`.

Even though `findFirst` commits to selecting the first element in encounter order, **the order of the output value** is not a guarantee that every intermediate callback runs according to a fixed traversal schedule.

### 5.2. limit and skip Are Also Not Execution-Count Guarantees

~~~java
long count = words.stream()
        .skip(1)
        .limit(2)
        .peek(System.out::println)
        .count();
~~~

The count result is 2. With a List source of known size, the JDK can calculate the number of remaining elements after skip/limit **without printing two elements**. Thus, even `limit(2)` does not prove that two `peek` callbacks executed.

**Result cardinality** and **the number of times side-effect actions execute** are two different quantities.

## 6. Which Terminal Operations Are Actually Meant for Side Effects?

The Stream documentation states an important exception regarding eliding side effects: **the action of `forEach` and `forEachOrdered`** is part of the terminal operation's contract, rather than merely a side effect outside the goal of a count computation.

~~~java
List<String> words = List.of("A", "BB", "CCC");
words.stream()
        .map(String::toLowerCase)
        .forEachOrdered(System.out::println);
~~~

With a sequential List source, the output printed is:

~~~text
a
bb
ccc
~~~

Here, the terminal operation **requires executing the action** on the elements that reach it, so it cannot simply skip the entire action and claim to satisfy its contract. Of course, an exception during traversal can interrupt processing, and preceding steps still follow the applicable rules of the Stream API.

### 6.1. How Do forEach and forEachOrdered Differ?

| Terminal operation | Meaning | Caveat |
| --- | --- | --- |
| `forEach(action)` | Performs `action` for elements of the Stream | With a parallel stream, action order is not guaranteed |
| `forEachOrdered(action)` | Performs `action` in encounter order if the Stream is ordered | May limit parallelism; does not mean all actions always run on a single thread |
| `toList()` | Produces a list of the pipeline's results | Side effects in intermediate callbacks are not an independent API goal/guarantee |
| `count()` | Returns cardinality | May not need traversal or intermediate callbacks |

If the task is genuinely to **write a result for each element**, an explicit loop or `forEach` expresses the action more clearly than `peek` or `map(...).count()`. If the task requires ordering, clearly establish the encounter order and choose `forEachOrdered` or an appropriate loop.

### 6.2. “The Action Was Called” Does Not Mean “The Transaction Succeeded”

Calling `forEach(repository::save)` means the save action is requested for each traversed element in a successfully completed execution. However:
- If one action throws an exception, execution may terminate before processing the remaining elements.
- Saves that succeeded before the error are not automatically rolled back.
- Retrying the whole batch can create duplicate records if the operation is not idempotent.
- In a parallel stream, you must manage thread safety and concurrency limits of external resources yourself.
- `forEach` does not promise ordering with parallel streams; `forEachOrdered` preserves action order for sources with an encounter order, but it does not turn saving multiple objects into a single transaction.

If the business requirement demands **all-or-nothing**, you need a transaction or an independent commit/compensation mechanism; you cannot simply pick a terminal operation and infer atomicity.

## 7. Wrong Ways and Right Ways to Write Code by Goal

### 7.1. Wrong: Using map() to Save Data and Then Calling count()

~~~java
// DO NOT USE TO GUARANTEE EVERY ELEMENT WAS SAVED:
// long saved = orders.stream()
//         .map(order -> {
//             repository.save(order);
//             return order;
//         })
//         .count();
~~~

This is a **counterexample with hypothetical variable names**; the code above is commented out and is not a standalone runnable file. `map` preserves cardinality; if the source has a known size, `count` can complete without calling `repository.save`. The `saved` result may therefore be just **the number of elements in the Stream**, not the number of writes actually performed successfully.

A clearer way to express intent:

~~~java
// Illustrating the action model:
// for (Order order : orders) {
//     repository.save(order);
// }
~~~

Or, once you have decided on the contract and properly handle errors/side effects:

~~~java
// orders.stream().forEach(repository::save);
~~~

The names `Order`, `orders`, and `repository` are hypothetical. In production, you must design transaction boundaries, exception handling, logging, and idempotency. The goal is to **place side effects in the required action step**, rather than hiding them in a mapper whose result is not needed.

### 7.2. Wrong: Validating with map() Followed by count()

~~~java
// UNRELIABLE:
// long count = inputs.stream()
//         .map(x -> {
//             validateOrThrow(x);
//             return x;
//         })
//         .count();
~~~

If every element must be validated before committing, this approach is unsuitable: the `map` step might not run. Validation must be placed in a workflow whose **result depends on validation**.

If you only need to count valid elements:

~~~java
long validCount = inputs.stream()
        .filter(this::isValid)
        .count();
~~~

This is illustrative code inside an instance method where `inputs` and `isValid` are defined. The count depends on the predicate. However, **counting valid items** is different from **requiring all element errors to be reported** or **rejecting the entire batch**. Choose the right contract.

If you want detailed per-element feedback, turn the validation result into data:

~~~java
record Check(String input, boolean valid) {}

List<Check> checks = inputs.stream()
        .map(input -> new Check(input, isValid(input)))
        .toList();
~~~

This illustrative snippet includes a type-level record declaration and a call inside a method. For a pipeline that needs to build `List<Check>`, the `Check` results containing validation info are **part of the output value**, not merely a side effect of a mapper before `count()`. If you also need error codes and positions, extend the record into a domain-specific `Success/Failure` result.

### 7.3. Wrong: Using peek() as a Mandatory Audit Log

~~~java
// DOES NOT GUARANTEE LOGGING EVERY ELEMENT:
// long total = events.stream()
//         .peek(auditLog::write)
//         .count();
~~~

If `count()` does not need to traverse, the audit log can miss everything. If the pipeline terminates early, the log may only record a subset. A **mandatory audit log** should be designed as an explicitly managed operation in the workflow, with rules for confirming successful persistence, retry/idempotency, and error handling.

If you only want to inspect data while debugging, `peek` is a more appropriate tool; you must still understand that it only observes elements that are actually processed.

### 7.4. Wrong: Accumulating via an External Variable in Parallel map/forEach

~~~java
// UNSAFE:
// List<String> output = new ArrayList<>();
// source.parallelStream().forEach(output::add);
~~~

`ArrayList` is not safe for concurrent writes. Let the framework manage the result:

~~~java
List<String> output = source.parallelStream()
        .map(String::toUpperCase)
        .toList();
~~~

This is illustrative code with `source` as a Collection of strings. The `toList()` result is constructed according to the Stream contract; callbacks do not arbitrarily write to a shared mutable list. If you need grouping or aggregation, use `collect(Collector)` or `reduce(...)` with an appropriate contract.

## 8. In Parallel Streams, Side Effects Are Even Harder to Predict

A parallel pipeline can process elements on different threads and at different times. Even when the final result of an ordered stream has a deterministic order, **the order in which mappers or predicates are called is not promised to match encounter order**.

Example:

~~~java
List<Integer> result = List.of(1, 2, 3, 4).parallelStream()
        .map(n -> n * 10)
        .toList();
// [10, 20, 30, 40]
~~~

The result is arranged in the encounter order of the List source because `toList()` has the appropriate contract, but you must not infer that the mapper ran sequentially for 1, 2, 3, 4.

### 8.1. Do Not Rely on Log Ordering

~~~java
// Do not use log timing as proof of processing order:
// List<Integer> result = numbers.parallelStream()
//         .peek(n -> System.out.println("Processing " + n))
//         .map(n -> n * 10)
//         .toList();
~~~

The `println` lines can interleave or occur across multiple threads; with other pipelines/terminals, `peek` might not run for some elements or might be elided. If an ordered log is required, organize logging at a boundary where order can be controlled, rather than inferring it from callback invocation order.

### 8.2. Synchronization Does Not Fix the Lack of an Invocation Guarantee

Using `AtomicInteger` instead of `int[]` can make incrementing a counter safe against data races in some cases. However, **atomicity does not force the JDK to call the callback**. For example, `peek(counter::incrementAndGet).count()` can still return the cardinality without the counter increasing.

Therefore, there are two independent questions:
1. If the callback runs in parallel, is the side effect thread-safe and visible?
2. Is the callback **required to run** by the terminal operation's contract?

Answering “yes” to the first question does **not** automatically answer the second.

### 8.3. Exceptions and Cancellation

An exception in an executed callback can cause the terminal operation to fail; side effects that occurred earlier are not automatically rolled back. With parallel streams, other tasks may already have started or completed part of their work before the error propagates to the caller. Do not treat an exception as a tool to “cancel all threads immediately” or as a rollback transaction.

If there are APIs for sending emails, payments, or writing data, you need to design those operations outside the Stream or in a processing layer with explicit rollback/compensation and idempotency rules.

## 9. Complete Java 17 Program and Observed Output

Create the file **StreamSideEffectOptimizationDemo.java**. The example deliberately uses `AtomicInteger` to **observe the number of callback invocations in a run**, not as a recommendation to use this counter as part of business logic.

~~~java
import java.util.List;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicInteger;

public class StreamSideEffectOptimizationDemo {
    static int validateAndMeasure(String value) {
        if (value.equals("BB")) {
            throw new IllegalArgumentException("Invalid BB");
        }
        return value.length();
    }

    public static void main(String[] args) {
        List<String> words = List.of("A", "BB", "CCC", "DDDD");

        AtomicInteger mapped = new AtomicInteger();
        long mappedCount = words.stream()
                .map(s -> { mapped.incrementAndGet(); return s.toLowerCase(Locale.ROOT); })
                .count();
        System.out.println("map+count=" + mappedCount + ", map calls=" + mapped.get());

        AtomicInteger peeked = new AtomicInteger();
        long peekCount = words.stream()
                .peek(s -> peeked.incrementAndGet())
                .count();
        System.out.println("peek+count=" + peekCount + ", peek calls=" + peeked.get());

        long unvalidated = words.stream()
                .map(StreamSideEffectOptimizationDemo::validateAndMeasure)
                .count();
        System.out.println("validation in map+count=" + unvalidated);

        AtomicInteger checked = new AtomicInteger();
        long longWords = words.stream()
                .filter(s -> {
                    checked.incrementAndGet();
                    return s.length() > 2;
                }).count();
        System.out.println("filter+count=" + longWords + ", predicate calls=" + checked.get());

        AtomicInteger evaluated = new AtomicInteger();
        List<String> lower = words.stream()
                .map(s -> {
                    evaluated.incrementAndGet();
                    return s.toLowerCase(Locale.ROOT);
                }).toList();
        System.out.println("map+toList=" + lower + ", map calls=" + evaluated.get());

        AtomicInteger inspected = new AtomicInteger();
        boolean any = words.stream()
                .anyMatch(s -> {
                    inspected.incrementAndGet();
                    return s.equals("A");
                });
        System.out.println("anyMatch=" + any + ", predicate calls=" + inspected.get());

        StringBuilder actions = new StringBuilder();
        words.stream().map(s -> s.toLowerCase(Locale.ROOT))
                .forEachOrdered(s -> {
                    if (actions.length() > 0) actions.append("|");
                    actions.append(s);
                });
        System.out.println("forEachOrdered actions=" + actions);

        AtomicInteger slicedPeeked = new AtomicInteger();
        long sliceCount = words.stream().skip(1).limit(2)
                .peek(s -> slicedPeeked.incrementAndGet()).count();
        System.out.println("slice+count=" + sliceCount + ", peek calls=" + slicedPeeked.get());
    }
}
~~~

Run on JDK 17 or later using:

~~~bash
javac --release 17 StreamSideEffectOptimizationDemo.java
java StreamSideEffectOptimizationDemo
~~~

**Actual stdout verified in the JDK environment used for this article:**

~~~text
map+count=4, map calls=0
peek+count=4, peek calls=0
validation in map+count=4
filter+count=2, predicate calls=4
map+toList=[a, bb, ccc, dddd], map calls=4
anyMatch=true, predicate calls=1
forEachOrdered actions=a|bb|ccc|dddd
slice+count=2, peek calls=0
~~~

### 9.1. Line-by-Line Explanation

1. **`map+count=4, map calls=0`:** The List source has four elements; the mapper preserves cardinality; `count` can be determined without creating any lowercase strings.
2. **`peek+count=4, peek calls=0`:** The callback only observes and does not affect the count; it is allowed not to run when `count` is inferred from the source.
3. **`validation in map+count=4`:** The `validateAndMeasure` mapper would throw an exception for `"BB"` **if called**, but in this count operation it is skipped and no exception occurs. This demonstrates why validation should not rely on a `map` side effect.
4. **`filter+count=2, predicate calls=4`:** In this run, the predicate checks all four strings to identify the two strings longer than two characters.
5. **`map+toList=[a, bb, ccc, dddd], map calls=4`:** `toList` needs the transformed values to build the result list. The mapper is actually used in this pipeline; the counter records four invocations.
6. **`anyMatch=true, predicate calls=1`:** The first value `"A"` already satisfies the condition, so the sequential pipeline terminates early. Subsequent elements do not need to be checked.
7. **`forEachOrdered actions=a|bb|ccc|dddd`:** The terminal operation's action is executed for the mapped results in source order; here a sequential Stream is used, so building the `StringBuilder` has no concurrent writes.
8. **`slice+count=2, peek calls=0`:** Skip one and limit two on a List of known size; the number of resulting elements can be inferred without running `peek`.

**Do not treat callback counts as absolute.** This is empirical output for a specific JDK/source/pipeline; the API contract guarantees **the result value** and certain terminal actions, not that `map`/`peek` will always be skipped or run the exact recorded number of times in every environment.

## 10. Three Right Alternatives for Three Different Goals

### 10.1. Goal A: Transforming Data

Use a **pure data** transformation so the result is what is requested:

~~~java
List<String> upper = words.stream()
        .map(String::toUpperCase)
        .toList();
~~~

If the goal is a list of uppercase strings, this is the right API. There is no need to add external counters, logs, or file-writing actions inside the mapper. Each output element's value is produced according to `map` semantics.

### 10.2. Goal B: Counting or Summing Statistics

Use a terminal operation that expresses the result:

~~~java
long longWordCount = words.stream()
        .filter(s -> s.length() >= 3)
        .count();

int totalLength = words.stream()
        .mapToInt(String::length)
        .sum();
~~~

In these expressions, the result value depends on the predicate or length. If a valid optimization opportunity exists, the framework is entitled to use it. There is no separate side-effect requirement that must “execute n times” for the computation to be correct.

### 10.3. Goal C: Executing a Mandatory Action on Each Element

Make the action explicit in the workflow, for example:

~~~java
for (String word : words) {
    System.out.println(word);
}
~~~

Or:

~~~java
words.stream().forEachOrdered(System.out::println);
~~~

Both illustrative snippets are code inside a method, with `words` declared beforehand. If the action fails, handle it according to the designed contract. A terminal action does not by itself provide an exactly-once guarantee across failures, retries, process crashes, or external service calls.

If you need both to **transform** and to **write externally**, it is usually better to separate the two phases: produce normalized/validated data as values, then handle writing/committing with a clear contract. Do not let a `map` step both produce a value and silently update another system when future callers might terminate with `count()`.

## 11. How to Test Without Falling Into the Side-Effects Trap

A reliable test suite should verify **the output contract**, not how many times a logger appeared inside a pipeline.

### 11.1. Testing Transformation Results

~~~java
List<String> actual = List.of("An", "Binh").stream()
        .map(String::toUpperCase)
        .toList();

// Expected: ["AN", "BINH"]
~~~

In a project with JUnit, assert `assertEquals(List.of("AN","BINH"), actual)`. Do not use an `AtomicInteger` outside the mapper as proof that the transform ran twice when the output values themselves are what need to be verified.

### 11.2. Testing Validation as Data Results

If validation must return errors for individual elements, test a `List<Result>` or a specific list of errors. For example:
- A valid string produces `Success` or `Check(valid=true)`.
- An invalid string produces `Failure` with an error code/position.
- The result list preserves positions and does not silently drop errors.
- Commit only when business policy permits.

Do not test that `map(validator).count()` throws an exception, because that **is not a reliable contract**.

### 11.3. Testing External Actions at Clear Boundaries

If you need to verify that a save method was called, place the action in the service/function responsible for writing and test the invocation count according to **that service's** contract, along with behavior on errors and retries. You may use mocks appropriate for the API under test, rather than relying on an intermediate side effect that the JDK can elide.

In particular, you should test:
- An empty source.
- A single valid element.
- An invalid element at the start, middle, and end.
- Large sources and parallel execution cases if the real system uses them.
- Failure of the storage system after some elements have already been processed.

### 11.4. Do Not Rely on the Behavior of a Single JDK

Experimental results show **what the JDK did in this run**. They do not require that:
- Another JDK will always optimize the same way.
- Other terminal operations will preserve the same callback count.
- Enabling parallel will force every lambda to run on multiple threads.
- Adding/removing an operation will not change optimization possibilities.

A good design can change how it is optimized and still return **the correct business result**.

## 12. Common Misconceptions

| Misconception | Correction according to the Stream contract |
| --- | --- |
| “Writing `peek` guarantees logging.” | `peek` is not an audit/action guarantee; it may not run |
| “Using `map` then `count` both processes and counts.” | `count` can infer cardinality without calling the mapper |
| “Enabling `parallel()` runs every lambda.” | Parallel does not remove the right to optimize away operations |
| “Having AtomicInteger ensures the callback is always called.” | Atomics only help synchronize when the callback runs; they do not force invocation |
| “Seeing no exception means every element is valid.” | Validation placed in an elided step may not have run |
| “`toList()` and `count()` always traverse the same way.” | Their goals differ; `toList` needs output values while `count` only needs the element count |
| “Adding `limit(2)` will make peek run twice.” | Cardinality after `limit` can be computed without traversal |
| “`findFirst()` has already run map for every element.” | It can short-circuit before many elements |
| “A sequential Stream always forces every intermediate callback to run.” | Sequential does not mean no optimization/elision |
| “An exception automatically rolls back side effects.” | Streams do not provide transactions/rollback |
| “forEach on parallel always follows source order.” | Only `forEachOrdered` has an encounter-order contract when the source is ordered |
| “A Record containing a List/Map is deeply immutable.” | Reference fields can still point to mutable containers |
| “Counting log lines counts processed elements.” | Logs can be skipped, stopped early, or reordered |
| “Callbacks running enough times in one benchmark is a JDK contract.” | You must rely on the API specification and verify output values |

The row mentioning `toList()` in the table highlights the difference in **result goal**, not a claim that every mapper in every form of `toList` must have side effects on a fixed schedule.

## 13. Checklist for Designing Side-Effect-Free Pipelines

Before putting a lambda into a Stream, ask yourself:

1. **Is the final goal a value or an action?** If only a value is needed, avoid side effects.
2. **Must the callback be called to produce the result?** If not, the JDK may skip it.
3. **Are you using `peek` to perform a mandatory action?** If so, redesign it.
4. **Are you using `map(...).count()` to validate/save?** If so, `count` is not sufficient proof.
5. **Is the check result represented as a value?** If full validation is needed, return an explicit Result/Failure.
6. **Can the terminal operation stop early?** `anyMatch`, `findFirst`, and `limit` do not require processing the entire source.
7. **Does the source have a known size?** If so, `count` has even more opportunity for optimization.
8. **Is output/side-effect ordering required?** Choose the right operation and an ordered source type.
9. **Is it processed in parallel?** Control thread safety, visibility, and stateless/non-interfering behavior.
10. **Is it writing to files/databases/external APIs?** Ensure error policies, timeouts, idempotency, and transactions at the boundary.
11. **Are you reusing the same Stream?** A Stream cannot be reused after a terminal operation.
12. **Have you tested the results and empty-source cases?** Do not just count `println` lines.
13. **Have you read the API Note and contract for your target Java version?** Do not rely on sequential-loop intuition.
14. **If you change the terminal operation, is the code still business-correct?** A design relying on side effects can break as soon as `toList()` is changed to `count()`.

## 14. Self-Check Questions

**Question 1.** Why might `List.of("a","b").stream().peek(System.out::println).count()` print no elements?

**Answer:** The List has a known size of two, and `peek` does not change the element count. The JDK can return the count directly without traversing and without calling `peek`'s action.

**Question 2.** Does writing `map(validateOrThrow).count()` guarantee checking every element?

**Answer:** No. `map` preserves cardinality so it can be skipped when `count` is inferred from the source, causing both validation and the exception not to occur.

**Question 3.** What does `filter(isValid).count()` return?

**Answer:** The number of elements valid according to the predicate in the Stream result. For typical sources, computing `count` requires evaluating the condition, but do not treat the predicate invocation count as an independent side-effect contract.

**Question 4.** Must `anyMatch(x -> x > 0)` on a list starting with a positive number traverse the entire list?

**Answer:** No. As soon as it finds one matching element, it can return `true`.

**Question 5.** What difference can `toList()` and `count()` have when preceded by `map(String::toLowerCase)`?

**Answer:** `toList` needs the transformed strings to build the output, whereas `count` only needs the element count, so the mapper may not need to run for `count` on a sized source.

**Question 6.** If a data-saving action is mandatory, is placing it in `peek` appropriate?

**Answer:** No. Use a workflow or a terminal action with a clear action contract, and design error handling/commit/retry at the application layer.

**Question 7.** What problem does `AtomicInteger` in a lambda solve, and what does it not solve?

**Answer:** It helps update a counter atomically across multiple threads; it does **not** force the JDK to invoke the lambda or guarantee an invocation count.

**Question 8.** Why can't `parallelStream().forEach(System.out::println)` be used to guarantee printing in source order?

**Answer:** `forEach` with parallel does not guarantee action order; if the source has an encounter order and actions must run in that order, consider `forEachOrdered` or a sequential loop.

**Question 9.** Does a terminal operation throwing an exception automatically undo what earlier side effects wrote?

**Answer:** No. Appropriate transactions or compensation are needed; Streams are not a transaction manager.

**Question 10.** When should `peek` be used?

**Answer:** Primarily for debugging or non-essential observation when elements are actually processed. Do not use it as a mandatory validation/audit/data-writing step.

## 15. Official References

- [Java SE 17 — Stream<T> and the right to optimize/elide intermediate operations](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html).
- [Java SE 17 — Stream.count() API Note](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#count()).
- [Java SE 17 — java.util.stream package summary: side effects, laziness, and non-interference](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/package-summary.html).
- [Java SE 17 — Stream.peek()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#peek(java.util.function.Consumer)).
- [Java SE 17 — Stream.forEachOrdered()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#forEachOrdered(java.util.function.Consumer)).
- [Java SE 17 — Spliterator and the SIZED characteristic](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Spliterator.html).

**Remember:** A Java Stream is a description of **the result to compute**, not a guarantee to run every intermediate callback sequentially. The JDK has the right to skip `map`/`peek` or an entire pipeline segment if the terminal operation's result remains accurate; `count()` on a sized List is a classic example. Short-circuiting operations can also stop before examining the entire source. Therefore, **do not hide validation, persistence, auditing, or mandatory side effects in intermediate operations**. Put them in an appropriate processing contract, use data values for computation, and design concurrency/transactions independently of the JDK's internal optimizations.
