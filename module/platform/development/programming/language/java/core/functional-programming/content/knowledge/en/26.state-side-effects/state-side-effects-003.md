# Mutating External Variables Makes Results Order-Dependent in Java Streams

## 1. The problem: a pipeline looks like a function but depends on external state

Java Streams encourage writing data-processing steps using small, focused functions:

```java
List<String> result = words.stream()
        .filter(word -> !word.isBlank())
        .map(String::strip)
        .toList();
```

If `words` is a `List` of `String` containing no `null` values, the result of each transformation depends only on the element value passed in. This is the **stateless** (*not retaining state between elements*) and **non-interfering** (*not modifying the data source being traversed*) style.

However, a common mistake is using a variable **outside the lambda** to count, number elements, record intermediate results, or make decisions:

```java
AtomicInteger number = new AtomicInteger();

List<String> numbered = words.stream()
        .map(word -> number.incrementAndGet() + ":" + word)
        .toList();
```

This snippet may print the expected order in a sequential test. Yet the result for each element is no longer a pure function `word -> result`: it depends on **which element calls `incrementAndGet()` first**. Moving `sorted`, enabling `parallel`, changing the terminal operation, or changing the source structure can cause different values to be attached to each element.

`AtomicInteger` makes counter increments **atomic**, not the execution order of elements a stable contract. "Not losing counts" is completely different from "which element receives which sequence number".

This lesson helps you:

1. Identify stateful lambdas (*stateful lambdas*) and side effects (*side effects*).
2. Distinguish **encounter order**, **execution order**, and **result order** in a Stream.
3. Understand why `sorted`, `filter`, `limit`, `count`, `parallelStream`, and `forEach` can expose design flaws.
4. Avoid confusing "a variable must be effectively final" with "the referenced state is immutable".
5. Fix the code using pure transformations, numbering via stable indices, `map`/`reduce`/`collect`, or an intentional loop.
6. Test the behavior and limits of ordering assumptions.

## 2. Two essential conditions: stateless and non-interfering

According to the Stream contract, most behavioral functions passed into a pipeline (`Predicate`, `Function`, `Consumer`, `Comparator`, etc.) should **not interfere with the source** and **not depend on mutable state during processing**.

### Stateless: results do not depend on processing history

A stateless lambda:

```java
n -> n * n
```

For the same value `n`, the transformation produces the same result, regardless of which elements ran before it.

A stateful lambda:

```java
n -> n + counter.incrementAndGet()
```

The result depends on how many times `counter` has been incremented, meaning it depends on prior calls and task execution order.

### Non-interfering: do not modify the source while the pipeline is traversing it

Incorrect example:

```java
// Avoid: modifying the same list while it is being traversed by the Stream.
List<Integer> numbers = new ArrayList<>(List.of(1, 2, 3));
numbers.stream().forEach(n -> numbers.add(n * 10));
```

This snippet illustrates a design flaw. With a source that does not support concurrent modification such as `ArrayList`, modifying the source while the pipeline is running can lead to `ConcurrentModificationException`, unpredictable results, or other consequences. Not throwing an exception during a single test run cannot be treated as a guarantee of safety.

**Distinction:** a stateful lambda does not necessarily modify the source; it can still violate the stateless requirement even if it only mutates an external counter. Mutating a shared result collection from `parallelStream` introduces an additional risk of race conditions. State, ordering, and thread safety must each be analyzed separately.

## 3. Why does Java allow a lambda to mutate an external object but forbid incrementing a local variable?

In Java, a local variable *captured* by a lambda must be `final` or **effectively final**: the variable must not be reassigned after initialization.

Example that does not compile:

```java
int counter = 0;

// Wrong: local variable counter is not effectively final.
// words.forEach(word -> counter++);
```

Yet the following code compiles:

```java
int[] counter = {0};
words.forEach(word -> counter[0]++);
```

or:

```java
AtomicInteger counter = new AtomicInteger();
words.forEach(word -> counter.incrementAndGet());
```

The reason: the `counter` reference is not reassigned, so it satisfies the capture requirement. However, the **contents of the array** or the **state of `AtomicInteger`** can still change. The compiler only enforces local variable capture rules; it does not prove that a lambda is stateless or safe for parallel execution.

Do not use a single-element array or `AtomicInteger` just to "work around" effectively final if your real goal is accumulating data in a Stream. Ask instead: can `count`, `sum`, `reduce`, `collect`, or an explicit loop be used instead?

## 4. Three different kinds of order

You need to distinguish:

| Concept | Meaning | Common misconception |
| --- | --- | --- |
| **Encounter order** | The order of elements defined by the source and order-preserving operations | Not every source has one: `HashSet` does not guarantee order |
| **Execution order** | The order and threads in which `map`/`filter`/`forEach` callbacks are actually invoked | Not synonymous with encounter order, especially with `parallel()` |
| **Result order** | The order of elements obtained in the output, if applicable | `toList()` can preserve encounter order even when callbacks run concurrently |

With `List.of("pear", "apple", "plum")`, the source has encounter order `pear`, `apple`, `plum`.

A pure pipeline:

```java
List<String> sorted = words.parallelStream()
        .map(String::toUpperCase)
        .sorted()
        .toList();
```

produces a list in sorted order. Parallel execution may split the computation, but `toList()` preserves the encounter order of the ordered pipeline. The author **does not need to rely** on which element's lambda runs first.

Conversely:

```java
AtomicInteger next = new AtomicInteger();
List<String> tagged = words.parallelStream()
        .map(word -> next.incrementAndGet() + ":" + word)
        .toList();
```

each element receives a number according to the **execution** order of `incrementAndGet`, not necessarily encounter order. The resulting list may still be collected in source order, but the number attached to each `word` can differ across runs. Do not treat a specific sample output of this parallel example as a contract.

**Key takeaway:** preserving the order of the result list does not prove that numbers were assigned in order. You might get `[2:pear, 1:apple, 3:plum]` under one schedule, even though the three elements in the list remain at positions `pear`, `apple`, `plum`.

## 5. `sorted` shows how much the order of side effects matters

Consider two numbering approaches in a **sequential** pipeline.

### Number first, then sort by word

```java
AtomicInteger next = new AtomicInteger();

List<String> result = Stream.of("pear", "apple", "plum")
        .map(word -> new Tagged(next.incrementAndGet(), word))
        .sorted(Comparator.comparing(Tagged::word))
        .map(tag -> tag.sequence() + ":" + tag.word())
        .toList();

// [2:apple, 1:pear, 3:plum]
```

Here `Tagged` is the record `record Tagged(int sequence, String word) {}` declared in the complete program in Section 8. `map` assigns numbers according to the input order `pear`, `apple`, `plum`; `sorted` then reorders the `Tagged` instances without **reassigning the numbers already attached**.

### Sort first, then number

```java
AtomicInteger next = new AtomicInteger();

List<String> result = Stream.of("pear", "apple", "plum")
        .sorted()
        .map(word -> next.incrementAndGet() + ":" + word)
        .toList();

// [1:apple, 2:pear, 3:plum]
```

Both pipelines have the same three words and the same operations (`sorted`, `map`, `toList`), but the **relative order between `sorted` and `map` differs**. When `map` generates numbers from an external counter, those numbers are tied to the execution position of the task, not an independent property of the word.

The issue is not that `sorted` "loses data"; the issue is that external state introduced an execution-order dependency into the transformation. If the business requirement is sequence numbers after sorting, separate it clearly: create the **sorted list**, then number by index. If the requirement is input line numbers, do not use a counter inside `map`: attach the original index from an index-accessible source.

## 6. `filter`, `limit`, `findFirst`, and `count` expose false assumptions

A lambda with side effects is sometimes written because the developer assumes it will run **exactly once per element**. The Stream contract does not allow relying on that assumption for business logic in all pipelines.

### Filtering before vs. after numbering differs

```java
// Illustration where words is an ordered List<String> containing no nulls.
AtomicInteger counter = new AtomicInteger();

List<String> labels = words.stream()
        .filter(s -> s.length() >= 5)
        .map(s -> counter.incrementAndGet() + ":" + s)
        .toList();
```

Only elements passing `filter` receive a number. If `map` is placed before `filter`, counting can happen even for elements that are later discarded. Reordering operations to "optimize" can break the numbered labels.

### Short-circuiting

`limit`, `findFirst`, `anyMatch`, and other short-circuiting terminal operations can cause **not every element** to be examined. Never expect a side effect in a lambda to always execute as many times as the source size. For example, `Stream.iterate(...)` can be an infinite sequence, while `limit` takes only a portion.

### `count()` can skip unnecessary callbacks

An especially important case:

```java
List<String> source = List.of("a", "b", "c");
AtomicInteger calls = new AtomicInteger();

long count = source.stream()
        .map(s -> {
            calls.incrementAndGet();
            return s.toUpperCase();
        })
        .count();
```

For a sized source such as a `List` and a pipeline that does not change the element count, the JDK can compute `count()` **without iterating through each `map`**. Do not write tests or business logic requiring `calls == 3`. The value of `count` is 3; the side effect of `map` is **not guaranteed** to execute.

This shows that a transforming lambda should not simultaneously perform primary work and be required to log, call external APIs, or update state variables for data to be considered valid. When the real goal is a side effect, design a dedicated consumption step and understand its ordering limits; when the goal is aggregation, use the appropriate terminal operation.

## 7. `forEach`, `forEachOrdered`, and `AtomicInteger` do not solve everything

### `forEach` does not guarantee order in parallel execution

```java
List<String> words = List.of("pear", "apple", "plum");
words.parallelStream().forEach(System.out::println);
```

Words may be printed in different orders; `forEach` does not guarantee preserving encounter order for parallel Streams.

### `forEachOrdered` preserves encounter order for the terminal action

```java
words.parallelStream().forEachOrdered(System.out::println);
```

For an ordered source like `List`, the terminal action is executed in encounter order. However:

- This **does not guarantee** that preceding `map` or `filter` lambdas ran in that same order.
- If `map` already assigned numbers using `AtomicInteger`, `forEachOrdered` cannot fix misassigned numbers before printing.
- Enforcing order can reduce beneficial parallelization; use it when order is genuinely required.

### Atomicity is not determinism

`AtomicInteger.incrementAndGet()` ensures each increment is atomic and calls have a linearizable order on that variable. Yet **which element gets to call it first** still depends on scheduling. If you need an index tied to the exact data position, take it from the source rather than inferring it from the order in which threads call a counter.

Using `Collections.synchronizedList`, `CopyOnWriteArrayList`, or `ConcurrentLinkedQueue` as a target for adding elements can partially address **memory/update safety**, but does not mean elements appear in the desired order. Moreover, part of a pipeline might not traverse all elements or might be optimized away. When you only need to collect results, using `toList`, `toSet`, or `collect` with an appropriate collector is clearer.

## 8. Complete Java 17 example: contrasting order-dependent code and fixes

Create the file **`ExternalStateStreamDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class ExternalStateStreamDemo {
    record Tagged(int sequence, String word) {}

    static void check(Object expected, Object actual, String label) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(
                    label + ": expected=" + expected
                            + ", actual=" + actual);
        }
    }

    static List<Integer> runningTotals(List<Integer> values) {
        // Problem that depends on the previous element: a loop is the clear choice.
        List<Integer> output = new ArrayList<>();
        int running = 0;
        for (int value : values) {
            running += value;
            output.add(running);
        }
        return List.copyOf(output);
    }

    public static void main(String[] args) {
        List<String> words = List.of("pear", "apple", "plum");

        // Order-dependent approach: illustrates only a sequential pipeline.
        AtomicInteger sequentialCounter = new AtomicInteger();
        List<String> sequential = words.stream()
                .map(w -> sequentialCounter.incrementAndGet() + ":" + w)
                .toList();

        // Numbering before sorted: numbers are tied to input order.
        AtomicInteger beforeSortCounter = new AtomicInteger();
        List<String> numberedBeforeSort = words.stream()
                .map(w -> new Tagged(
                        beforeSortCounter.incrementAndGet(), w))
                .sorted(Comparator.comparing(Tagged::word))
                .map(t -> t.sequence() + ":" + t.word())
                .toList();

        // Sorted before numbering: numbers are tied to sorted order.
        AtomicInteger afterSortCounter = new AtomicInteger();
        List<String> sortedBeforeNumber = words.stream()
                .sorted()
                .map(w -> afterSortCounter.incrementAndGet() + ":" + w)
                .toList();

        // Correct approach when fixed sequence numbers of the input data are needed.
        List<String> indexed = IntStream.range(0, words.size())
                .mapToObj(i -> (i + 1) + ":" + words.get(i))
                .toList();

        // Each index carries its own identity, so parallel execution does not change labeling.
        List<String> parallelIndexed = IntStream.range(0, words.size())
                .parallel()
                .mapToObj(i -> (i + 1) + ":" + words.get(i))
                .toList();

        // Pure transformation, with no external state.
        List<String> pure = words.stream()
                .map(s -> s.toUpperCase(Locale.ROOT))
                .sorted()
                .toList();

        // When a total sum is actually needed: use a terminal reduction.
        List<Integer> amounts = List.of(2, 3, 5);
        int sum = amounts.stream().mapToInt(Integer::intValue).sum();

        // When cumulative totals by position are actually needed: use an intentional loop.
        List<Integer> prefix = runningTotals(amounts);

        check(List.of("1:pear", "2:apple", "3:plum"),
                sequential, "sequential stateful example");
        check(List.of("2:apple", "1:pear", "3:plum"),
                numberedBeforeSort, "number before sorted");
        check(List.of("1:apple", "2:pear", "3:plum"),
                sortedBeforeNumber, "sort before numbering");
        check(List.of("1:pear", "2:apple", "3:plum"),
                indexed, "source index");
        check(indexed, parallelIndexed, "parallel stable index");
        check(List.of("APPLE", "PEAR", "PLUM"),
                pure, "pure mapping");
        check(10, sum, "sum");
        check(List.of(2, 5, 10), prefix, "running totals");
        check(List.of("pear", "apple", "plum"),
                words, "source unchanged");

        System.out.println("sequential=" + sequential);
        System.out.println("beforeSort=" + numberedBeforeSort);
        System.out.println("afterSort=" + sortedBeforeNumber);
        System.out.println("indexed=" + indexed);
        System.out.println("parallelIndexed=" + parallelIndexed);
        System.out.println("pure=" + pure);
        System.out.println("runningTotals=" + prefix);
        System.out.println("sum=" + sum);
        System.out.println("tests=PASS");
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac ExternalStateStreamDemo.java
java ExternalStateStreamDemo
```

Expected stdout:

```text
sequential=[1:pear, 2:apple, 3:plum]
beforeSort=[2:apple, 1:pear, 3:plum]
afterSort=[1:apple, 2:pear, 3:plum]
indexed=[1:pear, 2:apple, 3:plum]
parallelIndexed=[1:pear, 2:apple, 3:plum]
pure=[APPLE, PEAR, PLUM]
runningTotals=[2, 5, 10]
sum=10
tests=PASS
```

The program intentionally does **not** include the `parallelStream().map(w -> counter.incrementAndGet() + ":" + w)` example in required stdout, because its number-to-word mapping is unstable. Instead, `parallelIndexed` demonstrates the right design: `IntStream.range` generates indices by source position, and `mapToObj` builds labels solely from the index and the value at that position, without any external counter.

### Breakdown of key lines

1. `sequential` produces results in `List` order in the sequential example, but this is **behavior of that specific pipeline**, not a license to put stateful lambdas into every pipeline.
2. `beforeSort` yields `2:apple` because `apple` is the second element labeled before `sorted` reorders the elements.
3. `afterSort` yields `1:apple` because elements are sorted **before** the counter is called.
4. `indexed` reads indices from the source, so `pear` is always paired with `1`, `apple` with `2`, and `plum` with `3`.
5. `parallelIndexed` equals `indexed` because each index's result is an independent calculation. `toList` preserves the order of the ordered `IntStream` even when evaluated in parallel.
6. `pure` is a pipeline with no external state, easy to maintain and safe when changing execution mode provided the source is not mutated.
7. `sum` represents **a single total value**, whereas `runningTotals` represents **a sequence of prefix sums**. Those are two different requirements: prefix sums depend on order and state, so a sequential loop is the simple, accurate choice.
8. `check` throws `AssertionError` if the result differs from expected, so `java -ea` is not required.

## 9. Better design alternatives

### 9.1. If you need per-element transformation: use a pure function

Instead of:

```java
AtomicInteger counter = new AtomicInteger();
List<String> labels = words.stream()
        .map(w -> counter.incrementAndGet() + ":" + w)
        .toList();
```

determine **whether the labels truly need an index**. If not, use:

```java
List<String> labels = words.stream()
        .map(String::strip)
        .map(s -> s.toUpperCase(Locale.ROOT))
        .toList();
```

Each element's result depends only on that element's data, not on a variable mutated earlier. This snippet assumes `words` consists of non-null strings and `List` and `Locale` are imported.

### 9.2. If you need List sequence numbers: use the index from the source

```java
List<String> labels = IntStream.range(0, words.size())
        .mapToObj(i -> (i + 1) + ":" + words.get(i))
        .toList();
```

This works well when `words` is a `List` with efficient indexed access (such as `ArrayList` or `List.of`) that remains stable during traversal. With `LinkedList`, `get(i)` can cost O(n), making the whole algorithm O(n²). In that case, a loop using an iterator or `ListIterator` with an explicit local counter is usually more appropriate.

If you need numbering **after sorting**, create the sorted `List` first:

```java
List<String> sorted = words.stream().sorted().toList();

List<String> numbered = IntStream.range(0, sorted.size())
        .mapToObj(i -> (i + 1) + ":" + sorted.get(i))
        .toList();
```

Here the sequence "sort then number" is an explicitly expressed requirement, not an accidental byproduct of lambda call order.

### 9.3. If you need aggregation: use reduction/collectors

Incorrect or hard to maintain:

```java
int[] total = {0};
numbers.stream().forEach(n -> total[0] += n);
```

Correct for a sum requirement:

```java
int sum = numbers.stream()
        .mapToInt(Integer::intValue)
        .sum();
```

To count elements:

```java
long count = numbers.stream().count();
```

To group and count by key:

```java
Map<String, Long> counts = words.stream()
        .collect(Collectors.groupingBy(
                s -> s.substring(0, 1),
                Collectors.counting()));
```

The last snippet assumes non-empty strings, no nulls in `words`, and `Map` and `Collectors` imported. If empty strings can exist, you must define how to handle them before `substring`. `Collectors.groupingBy` rejects classifiers that return `null`. For totals, `reduce` or `collect` already defines how the framework splits/merges state; there is no need for a global variable updated outside the collector's scope.

### 9.4. If you genuinely need sequential state: use a loop

Some computations **inherently depend on order**, such as prefix sums, stateful parsers, detecting state transitions between adjacent elements, or multi-branch early-exit rules. There is no need to force them into a Stream using `AtomicInteger` or a single-element array.

```java
List<Integer> totals = new ArrayList<>();
int running = 0;

for (int amount : amounts) {
    running += amount;
    totals.add(running);
}
```

The snippet above illustrates this with an existing `amounts`. It expresses sequentiality clearly: `running` is local state for **one** pass, not shared across threads, and each update step is explicitly described.

Note: a loop's local variable **is still state**, not "purely functional". The difference is that this state is intentional, short-scoped, and has clear control flow. There is no rule requiring every task to be written with Streams.

## 10. Which side effects are acceptable?

Not all side effects are forbidden by Java. `forEach` is designed as a terminal operation for per-element actions; logging, performing I/O, or sending messages may be the actual goal of a pipeline. However, you must clearly understand:

- **Ordering**: `forEach` on a parallel Stream does not guarantee encounter order; `forEachOrdered` can preserve action order for an ordered source.
- **Thread safety**: actions may run on multiple threads; external resources must be designed for concurrent updates if needed.
- **Partial failure**: writing files, making network calls, or updating a DB can fail after some elements have already completed; Streams do not provide transactions, retries, or idempotency.
- **Short-circuiting and optimization**: do not treat side effects in intermediate operations like `map` or `peek` as mandatory steps for every element.
- **Result design**: if the goal is collecting a `List`/`Map`/total, use a terminal collector instead of building a shared `List`/`Map` from a lambda.

For example, when an application needs to log all events in order and I/O must be sequential, a `for` loop with explicit exception handling may be easier to control than `parallelStream().forEach(...)`. And if the goal is simply transforming data into a `List`, use `.map(...).toList()`.

### `peek` is not a reliable event-recording mechanism

```java
long count = words.stream()
        .peek(System.out::println)
        .count();
```

`peek` calls may not execute for every element if the terminal operation determines the result via optimization, such as when the source size is known. `peek` is intended primarily for observation/debugging and should not be the sole place responsible for mandatory business side effects.

## 11. `reduce` and `collect` must not arbitrarily mutate global variables

### `reduce` is a value-combining operation

```java
int sum = numbers.stream().reduce(0, Integer::sum);
```

A proper reduction must satisfy a neutral identity and an associative combiner suitable for partitioning, especially in parallel. Do not write:

```java
AtomicInteger external = new AtomicInteger();

int result = numbers.parallelStream()
        .reduce(0, (a, b) -> {
            external.addAndGet(b);
            return a + b;
        });
```

This anti-pattern has external state; adding to `external` is not part of the reduction result and can depend on how the framework invokes the operator. What matters is the `result` value, not side effects that can vary with splitting/combining.

### `collect` manages containers internally

For mutable accumulation, use a collector:

```java
List<String> result = words.parallelStream()
        .collect(Collectors.toList());
```

Standard collectors have mechanisms to create and merge containers when needed. Do not replace this with:

```java
List<String> shared = new ArrayList<>();
words.parallelStream().forEach(shared::add); // Not thread-safe.
```

Using `Collections.synchronizedList` can protect the `add` operation, but **does not automatically guarantee appearance order** matching the source. If what you want is a list in encounter order, a collector is the more expressive and accurate solution.

### `CONCURRENT` does not mean "I want to use parallel"

When writing a custom collector, mark it `CONCURRENT` only when the accumulator genuinely supports multiple threads updating **the same container** safely. A collector without `CONCURRENT` can still collect a parallel Stream using separate containers and a proper combiner. Do not attach `CONCURRENT` to a plain `ArrayList` or mutable counter to "speed things up".

## 12. Common misconceptions

| Misconception | Reality |
| --- | --- |
| "Captured local variables must be effectively final, so all lambdas are pure" | The reference is not reassigned, but the object or array can still be mutated |
| "Using `AtomicInteger` makes it safe" | Atomicity ensures safe variable updates, not index assignment in encounter order |
| "A Stream from an ordered `List` runs every lambda in order" | Encounter order does not mean execution order when parallel |
| "`toList()` preserves order, so counter labels will also be in order" | `toList` preserves result positions; it does not fix misassigned values |
| "`forEachOrdered` fixes labels assigned in `map`" | It only enforces order for the terminal action |
| "`peek` or `map` is guaranteed to run on every element" | Some terminal operations can short-circuit or skip callbacks that do not affect the result |
| "`synchronizedList` solves ordering" | It synchronizes operations, not the order in which threads invoke them |
| "Always use Streams instead of loops" | Sequential loops are a great fit for order-dependent stateful problems |
| "Writing to an external variable just for logging has no impact" | Side effects can make the program depend on call counts, ordering, and I/O failures |

## 13. Testing to detect order dependencies

A good test suite should ask: **does the function produce the right value from the element, or does the result depend on lambda call history?**

### Comparing sequential and parallel execution

For a pure transformation:

```java
List<String> sequential = words.stream()
        .map(String::toUpperCase)
        .toList();

List<String> parallel = words.parallelStream()
        .map(String::toUpperCase)
        .toList();
```

In this example `words` is an ordered `List` of non-null `String`s. Both results must be equal because each element transforms independently and `toList` preserves encounter order. This tests **output values**, not how many times a callback ran.

With an external counter, do not write a test expecting a specific mapping from `parallelStream`: a passing run can just be lucky thread scheduling. Do not use `Thread.sleep` to force a schedule, as it makes tests slow and unreliable; **fix the design** instead.

### Verifying correctness across operation positions

If a pipeline uses `filter`, `sorted`, or `limit`, write tests for:

1. Empty data and single-element data.
2. Duplicate data or multiple values with equal sort order.
3. Moving steps where permitted by requirements, checking whether labels change.
4. Sequential and parallel results (only when business logic permits parallelism).
5. The source remaining unmodified during traversal.
6. Ordering and index attachment when the input has encounter order.
7. Small and large data sizes, not just a single three-element case.

Testing order does not mean every callback must run one by one; test the **output and published invariants**, such as `indexed.get(i)` always starting with `(i+1) + ":"` and still pointing to `words.get(i)`.

### Invariants you can assert

For `List<String> indexed` built from `IntStream.range(0, words.size())`:

```text
indexed.size() == words.size()
indexed[i] == (i + 1) + ":" + words[i]
```

These two invariants hold for a stable source and the pure pipeline in the example. They do not rely on threads, callback counts, or the history of a counter variable. Such tests express the contract far more clearly than asserting `AtomicInteger.get() == n`.

## 14. Design mistakes to avoid

**Mistake 1: using an external variable to number elements in `map` and then enabling parallel.** This can attach numbers to the wrong elements even though all numbers remain distinct. Use the source index or separate an explicit sequential numbering step.

**Mistake 2: replacing `map` with `peek` just to update a variable.** `peek` is an intermediate operation that can be skipped due to optimization; it is not a solution for required side effects.

**Mistake 3: mutating the source `ArrayList` from `forEach`.** Violates non-interference; risks exceptions or unpredictable results.

**Mistake 4: writing directly to an external `ArrayList` from `parallelStream().forEach`.** Causes a race condition. Use `.toList()` or a collector.

**Mistake 5: using `AtomicInteger` to "fix" ordering without changing the algorithm.** Atomicity handles concurrent access, not the logical order of data.

**Mistake 6: relying on log print order to infer element order.** `System.out.println` across threads observes side effects, not the definition of encounter order.

**Mistake 7: using `forEachOrdered` when side effects already happened in an earlier step.** It cannot undo labeling already performed in `map`.

**Mistake 8: keeping an external static variable that retains state across multiple calls.** A second invocation may receive numbers continuing from the first; tests run in isolation or in a different order will produce different results.

**Mistake 9: forgetting `limit`/short-circuiting causes only part of the data to be processed.** Do not place work that must happen for every input inside an intermediate lambda if the terminal operation can short-circuit.

**Mistake 10: using a reduction with side effects instead of pure values.** Combiners must satisfy associativity and identity contracts; updating a global variable does not substitute for a proper accumulator.

**Mistake 11: assuming order is always defined.** `HashSet.stream()` and unordered sources do not have an encounter order like `List`. If you need order, establish it with an appropriate `sorted`/comparator or choose an ordered source.

**Mistake 12: converting all sequential logic to Streams just to reduce line count.** For prefix sums, stateful parsers, or workflows needing complex `break` conditions, a loop can be clearer and less error-prone.

## 15. Decision checklist for choosing a solution

When encountering Stream code that mutates an external variable, ask in order:

1. **Is this an independent per-element transformation?** If yes, write a pure `map` and pass results through the pipeline without external variables.
2. **Are sequence numbers truly needed?** If yes, do they belong to the *source index*, *post-filter position*, or *post-sort position*? Clarify before writing code.
3. **Is only a single aggregated value needed?** Use `count`, `sum`, `reduce`, or `collect`.
4. **Is a sequence of results depending on previous elements needed?** A sequential loop or a specialized scan algorithm is usually clearer.
5. **Are there external side effects?** Review ordering, retry/idempotency, transactions, partial failures, and thread safety.
6. **Does parallel execution actually make sense?** Do not enable `parallel()` just for speed when logic depends on shared mutable state.
7. **What are the tests verifying?** Verify final results and invariants, not an accidental execution schedule.

## 16. Practice exercises

1. Given `List.of("B", "A", "C")`, use `AtomicInteger` to number before `sorted` and predict the output; then `sorted` before numbering and compare. Write an explanation of where the stateful operation executes.
2. Replace numbering with `IntStream.range`, creating two versions: preserving original order and numbering after sorting. Test exact positions/values and re-run the pure indexed version with `parallel()`.
3. Explain why `AtomicInteger.incrementAndGet()` cannot promise that the first element of a `List` receives number 1 in `parallelStream`.
4. Given the pipeline `source.stream().map(x -> { counter.incrementAndGet(); return x; }).count()`, analyze why `counter` is not a reliable measure of processed elements.
5. Write a program to compute the prefix sums of `List.of(3, 1, 4, 2)`. Expected result: `[3, 4, 8, 10]`. Explain why a loop with a local `running` variable is a sound design.
6. From a list of employees, use `Collectors.groupingBy(Employee::department, counting())` to count people per department without updating a `HashMap` outside the lambda. Test the count of each group.
7. Write an example using `parallelStream().forEach` to print strings and `forEachOrdered` to print strings; describe what is guaranteed and what is not, without relying on a lucky run's output as an absolute claim.
8. Refactor `parallelStream().forEach(sharedList::add)` to a terminal collector. Test the `List` contents instead of testing `add` call order.
9. Write a test case demonstrating that `sorted` after `map` cannot reassign already-attached labels. Compare with `sorted().toList()` followed by index-based numbering.
10. For per-element logging/DB writes, propose policies for ordering, timeouts, retries, and handling a single-element failure. Explain why `.map` with side effects and a terminal `count()` is not a reliable processing guarantee.

## 17. Conclusion

**Mutating external variables inside a lambda can make results depend on execution order, callback invocation count, and state from previous runs.** A `Stream` having an encounter order does not mean every callback always runs in that order, especially in parallel. `AtomicInteger` makes updates safe at the variable level, **not which element receives which label**.

To write correct, maintainable Streams:

- Prefer **stateless, non-interfering** functions in `map`, `filter`, and other intermediate operations.
- Use the **actual source index** when stable positional numbering is required.
- Use **terminal operations** (`count`, `sum`, `reduce`, `collect`) for aggregation instead of global variables.
- Use an explicit loop when the process genuinely depends on sequential state.
- Use `forEachOrdered` only when terminal action order is needed, not as a fix for side effects from earlier stages.
- Test **final values and business invariants**, not a specific thread schedule or lambda invocation count as proof of correctness.

By cleanly separating *data* from *mutable state outside the pipeline*, your code stays understandable, testable, and easy to switch from sequential to parallel processing when appropriate.
