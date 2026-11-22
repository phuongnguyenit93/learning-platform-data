# Stream.count() and Cases Where Iterating Over Every Element Is Not Needed in Java

## 1. What does count() return?

In the Java Stream API, `count()` is a **terminal operation** that returns the number of elements in the Stream as a `long`:

~~~java
long count = List.of("An", "Binh", "Chi").stream().count();
System.out.println(count); // 3
~~~

This snippet is placed inside a method and requires importing `java.util.List`. At the moment `count()` is called, the pipeline is asked to produce a numeric result: **how many elements belong to the resulting Stream**, after accounting for the operations preceding it.

For example:

~~~java
long result = List.of(1, 2, 3, 4, 5).stream()
        .filter(n -> n % 2 == 0)
        .count();
// 2
~~~

Here, `count()` counts elements **after filtering**: only 2 and 4. Just because the source has five elements does not mean every pipeline returns 5.

The surprising part is: **to know how many elements there are, Java does not necessarily have to invoke the processing function for each element**. If the implementation already knows the exact count from the source and knows the intermediate steps do not change the count, it **can** compute `count()` **without iterating** over every element and **without invoking** the lambdas in `map` or `peek`.

This is behavior explicitly documented in the Java SE 17 *API Note* for `Stream.count()`, not a bug in Stream or a bug in `peek`.

## 2. Distinguishing three types of counts and three questions

Counting operations look similar, but they answer different questions:

| Expression | Question answered | Result for [1,2,3,4,5] |
| --- | --- | --- |
| `list.size()` | How many elements does the source collection currently have? | 5 |
| `list.stream().count()` | How many elements does the source Stream have? | 5 |
| `list.stream().filter(n -> n > 3).count()` | How many elements satisfy the condition? | 2 |
| `list.stream().limit(3).count()` | How many elements are in the prefix limited to 3 elements? | 3 |
| `list.stream().skip(2).count()` | How many elements remain after skipping the first two? | 3 |

`Collection.size()` returns `int`. `Stream.count()` returns `long`. For a normal collection that is not modified during processing and a **pipeline that does not change the number of elements**, the values of the two counts may be equal; however, they are two APIs with **different contracts and scopes of applicability**.

If you only need the number of elements in an existing `Collection`, with no data processing steps, calling `collection.size()` usually expresses the intent more directly and avoids creating an unnecessary Stream. If you need to count **results after filtering or transformation steps**, use `stream().filter(...).count()` or the corresponding pipeline.

**Do not confuse `count()` with "running every callback and then incrementing a counter".** The specification allows avoiding unnecessary work to return the exact count.

## 3. Optimization mechanism: sources with a known exact size

### 3.1. Spliterator and the SIZED characteristic

A Stream reads elements from a source, usually through a `Spliterator`. Some sources and spliterators know the exact number of elements that can be traversed **without iterating through them**.

The `Spliterator.SIZED` characteristic means: at the appropriate time, the spliterator's `estimateSize()` reports the exact size of the remaining elements according to the contract. When this characteristic is present, `getExactSizeIfKnown()` can return the exact size; if `SIZED` is absent, that method returns `-1`.

Standard `List` sources, some Streams from arrays, and `IntStream.range(...)` usually provide sufficient information about the element count. Conversely, a source created by an unbounded generation operation may **not** have a known exact size upfront.

Illustrative example:

~~~java
List<String> names = List.of("An", "Binh", "Chi");
long count = names.stream().count(); // 3

long numbers = java.util.stream.IntStream.range(0, 1_000_000)
        .count(); // 1_000_000
~~~

You should not infer that Java invoked a callback one million times to produce the second result. A numeric range source has its size known from the range structure.

**Limitation to understand:** `SIZED` on a source is not enough to conclude that every pipeline can skip traversal. Subsequent processing operations can change the number of elements and make the result size impossible to compute simply from the source size.

### 3.2. Operations that preserve element count

**Semantically**, operations such as `map` or `peek` do not add or remove elements from the Stream:

~~~java
long value = List.of("a", "bb", "ccc").stream()
        .map(String::toUpperCase)
        .count(); // 3
~~~

Even though each element would be converted into a different string **if the element is mapped**, the count before and after `map` remains the same. With a source of known size, the implementation can know the `count()` result equals the source size without creating the uppercase strings.

Similarly, `peek` observes elements **when elements actually pass through this step**, but it neither adds nor removes elements from the Stream. Therefore, `peek` is not a "barrier" forcing every element to be traversed before `count()` completes.

Some operations such as `sorted()`, `unordered()`, and element type conversions preserve cardinality semantically, but that is **not a guarantee** that the implementation will always skip all of those operations. The safe rule is: **write programs that depend only on the result value and side effects guaranteed by the API contract, not on whether a specific intermediate callback ran**.

### 3.3. Operations that can change element count

| Operation | Can change element count? | Implication for inferring count |
| --- | --- | --- |
| `map(f)` | No: one in, one out | Can be inferred from the source |
| `peek(action)` | No | Can be skipped when computing count |
| `mapToInt(f)`, `mapToLong(f)` | No | Primitive result, element count unchanged |
| `sorted()` | No | May not need to perform sorting just to count |
| `filter(p)` | Yes: elements may be removed | Usually needs to determine which elements match |
| `flatMap(f)` | Yes: one element can produce 0, 1, or many elements | Usually cannot know result count from source size |
| `mapMulti(...)` | Yes: one input can produce many or zero elements | Needs additional information to know the count |
| `distinct()` | Yes: removes duplicate elements | Usually must inspect data, unless source/pipeline properties are already sufficient |
| `takeWhile(p)`, `dropWhile(p)` | Yes | Depends on predicate and source order/characteristics |
| `skip(n)` and `limit(n)` | Yes, but according to clear limit counts | Can be computed directly if input size is already known |

Saying "usually needs" does not mean it always forces running exactly one callback on every element. The terminal operation, source, sequential/parallel mode, and optimizations allow changing the number of callback executions. If the count cannot be inferred from metadata, the implementation must determine the result cardinality in a way that conforms to the contract.

## 4. Important experiment: map().count() may not call map

Consider:

~~~java
List<String> words = List.of("a", "bb", "ccc", "dddd");
AtomicInteger mapped = new AtomicInteger();

long n = words.stream()
        .map(word -> {
            mapped.incrementAndGet();
            return word.toUpperCase();
        })
        .count();

System.out.println(n);
System.out.println(mapped.get());
~~~

This is an illustrative snippet inside a method and requires importing `java.util.List` and `java.util.concurrent.atomic.AtomicInteger`.

In the Java 17 environment tested for this article, the output is:

~~~text
4
0
~~~

**Why is `mapped.get()` equal to 0?** The four source elements already have an exact count; `map` preserves the count. When only `count()` is needed, computing the uppercase value of each element does not affect the result, so the implementation can skip the mapping step.

Do not conclude:

- "`map` is always skipped if `count` follows it."
- "If `map` is present, every exception or log inside the lambda is guaranteed to happen."
- "The compiler understood whether the lambda body has side effects or not."

What is permitted is **skipping the evaluation of an intermediate step if doing so does not affect the result under the Stream contract**. Side effects that depend on invoking the lambda are not guaranteed in this situation.

Putting mandatory work inside `map` and expecting `count()` to "trigger the work" is a design flaw.

## 5. peek().count(): the official example that easily surprises

`peek(action)` is often introduced as a way to observe data passing through a pipeline:

~~~java
List<String> words = List.of("a", "bb", "ccc", "dddd");

long count = words.stream()
        .peek(System.out::println)
        .count();
~~~

In Java 17, with a `List` source as above, the implementation may print **zero lines** from `peek` while still returning `count == 4`. This is also the scenario used by the `Stream.count()` Javadoc to explain the optimization right to skip traversal. It does not contradict the meaning of `peek`: the action only occurs when elements are processed through that step.

If you want to verify with a counter:

~~~java
AtomicInteger peeked = new AtomicInteger();

long count = words.stream()
        .peek(word -> peeked.incrementAndGet())
        .count();

System.out.println("count=" + count);
System.out.println("peek calls=" + peeked.get());
~~~

When running the verified Java 17 example, `count=4` and `peek calls=0`. Remember that this is **empirical behavior of the implementation in the example**, not a promise that every Java version must execute strictly zero callbacks.

### 5.1. peek is meant primarily for observing during processing, not mandatory work

Use `peek` to:
- Temporarily debug when a pipeline actually needs to process elements.
- Observe intermediate values in a context where laziness/short-circuiting and optimization possibilities are well understood.

Do not use `peek` to:
- Save mandatory records to a database.
- Send an email/HTTP request required once per element.
- Mutate business state that must happen.
- Serve as proof that every element was processed.

If the goal is to perform an action for each element, choose an API with the appropriate **action contract**, such as `forEach(Consumer)`, or a loop. However, `forEach` on a parallel stream does not guarantee order; and all side effects still need to consider thread safety, exceptions, and idempotency.

**If you only need to count**, do not put logging or business logic into the pipeline and then use `count()` as a way to trigger them.

## 6. Why does filter().count() usually have to inspect data?

Consider:

~~~java
long count = List.of("a", "bb", "ccc", "dddd").stream()
        .filter(word -> word.length() > 2)
        .count(); // 2
~~~

From the source count of 4, **it is not possible to infer** how many strings are longer than two characters. Knowing the contents of the strings or equivalent information about the predicate is required. In a normal sequential pipeline, `filter` decides which elements are kept before `count` is known.

To observe:

~~~java
AtomicInteger tested = new AtomicInteger();

long count = words.stream()
        .filter(word -> {
            tested.incrementAndGet();
            return word.length() > 2;
        })
        .count();

System.out.println("filtered=" + count);
System.out.println("predicate calls=" + tested.get());
~~~

In the Java 17 test for this article, `filtered=2` and `predicate calls=4`. This is a concrete example of why `filter` usually removes the ability to infer cardinality from the source size.

**Do not absolutize:** other optimizations, sources carrying special characteristics, or how a terminal operation is combined can change the actual work performed. `filter` only guarantees that the result contains elements matching the predicate, not that a programmer can use the callback invocation count as an independent business metric.

### 6.1. Where do filter and map go?

Two pipelines:

~~~java
long a = words.stream()
        .map(String::toUpperCase)
        .filter(word -> word.length() >= 3)
        .count();

long b = words.stream()
        .filter(word -> word.length() >= 3)
        .map(String::toUpperCase)
        .count();
~~~

Here both results are 2 for the example data, because converting to uppercase does not change string length in this specific example context. However, the order of operations **can** change semantics, cost, and callback counts if the actual logic differs (for instance, a `map` operation that normalizes/modifies data before checking).

Only swap the two steps when you prove they do not alter the business condition and result contract. Do not reorder steps to "improve performance" if doing so changes the meaning of the data being counted.

## 7. skip(), limit(), and the ability to compute count without traversal

Suppose the source is known to have `N` elements, such as a stable `List` of size 4:

~~~java
List<String> words = List.of("a", "bb", "ccc", "dddd");
long count = words.stream()
        .skip(1)
        .limit(2)
        .count();
// 2
~~~

With this simple pipeline, the count can be computed from N and the bounds:
- After `skip(k)`: `max(0, N - k)` elements remain.
- After `limit(m)`: `min(m, remaining N)` elements remain.

If `N=4`, `k=1`, `m=2`, the count is 2. With a `List` of deterministic size and no data-dependent steps in between, computing the size can **avoid** pulling every element.

| Pipeline on a 4-element List | count result |
| --- | ---: |
| `stream().count()` | 4 |
| `stream().limit(2).count()` | 2 |
| `stream().limit(20).count()` | 4 |
| `stream().skip(1).count()` | 3 |
| `stream().skip(20).count()` | 0 |
| `stream().skip(1).limit(2).count()` | 2 |
| `stream().limit(2).skip(1).count()` | 1 |
| `stream().filter(x -> x.length() > 2).count()` | 2, needs to know the values |

**Limitation:** the formulas above rely on a source with a known size and a pipeline with the exact operations shown in the example. When `filter`, `flatMap`, or other operations make the count depend on the data, you cannot take the source size and apply simple addition and subtraction to infer the result.

### 7.1. count() after limit is not the same as "having inspected exactly limit elements"

A `count()` value of 2 does not prove that two elements were actually traversed or that earlier callbacks ran exactly twice.

If the source is a `List` and all operations before limit preserve element count, Java can infer the result. If the source is a generator without a pre-known size, obtaining n elements may require generating/evaluating elements.

Therefore, **cardinality** (the count in the result) and **work performed** (the number of elements processed/callbacks invoked) are not synonymous.

## 8. Sources without a pre-known size: generate and flatMap

An opposite case:

~~~java
AtomicInteger generated = new AtomicInteger();

long count = Stream.generate(() -> {
        generated.incrementAndGet();
        return "x";
    })
    .limit(3)
    .count();
~~~

This snippet requires importing `java.util.stream.Stream` and `AtomicInteger`. `Stream.generate` creates a source that is contractually unbounded, with no finite count advertised like `List.size()`. `limit(3)` makes the result finite.

In the tested Java 17 program:
- `count` equals 3.
- `generated.get()` equals 3.

You should not turn the number of supplier calls in one implementation into a universal rule for every API/execution schedule. More importantly: if you remove `limit(3)` and call `Stream.generate(...).count()` on an unbounded source without another termination condition, the computation has no finite result to complete normally.

With `flatMap`:

~~~java
long letters = List.of("ab", "cde").stream()
        .flatMap(word -> word.chars()
                .mapToObj(codePoint -> (char) codePoint))
        .count();
// 5
~~~

This snippet is inside a method and requires importing `java.util.List`. `flatMap` produces 2 elements from the first string and 3 elements from the second string, so the result count is 5. This result cannot be computed solely from `List.size()==2`. Note that `String.chars()` returns UTF-16 code units as int; for Unicode text with supplementary characters, "letters" in the user sense may differ from the number of UTF-16 code units. The example here uses ASCII characters to avoid conflating concepts.

## 9. Standalone runnable example in Java 17

Create the file **StreamCountOptimizationDemo.java**. The example uses AtomicInteger counters **only to observe** how many times callbacks are called in the empirical run; in production applications, do not use counters as a way to trigger work.

~~~java
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class StreamCountOptimizationDemo {
    public static void main(String[] args) {
        List<String> words = List.of("a", "bb", "ccc", "dddd");

        AtomicInteger mapped = new AtomicInteger();
        long mappedCount = words.stream()
                .map(word -> {
                    mapped.incrementAndGet();
                    return word.toUpperCase();
                })
                .count();
        System.out.println("map count=" + mappedCount
                + ", map calls=" + mapped.get());

        AtomicInteger peeked = new AtomicInteger();
        long peekCount = words.stream()
                .peek(word -> peeked.incrementAndGet())
                .count();
        System.out.println("peek count=" + peekCount
                + ", peek calls=" + peeked.get());

        AtomicInteger tested = new AtomicInteger();
        long longWords = words.stream()
                .filter(word -> {
                    tested.incrementAndGet();
                    return word.length() > 2;
                })
                .count();
        System.out.println("filtered count=" + longWords
                + ", predicate calls=" + tested.get());

        long sliced = words.stream().skip(1).limit(2).count();
        System.out.println("slice count=" + sliced);

        AtomicInteger generated = new AtomicInteger();
        long generatedCount = Stream.generate(() -> {
                    generated.incrementAndGet();
                    return "x";
                })
                .limit(3)
                .count();
        System.out.println("generated count=" + generatedCount
                + ", supplier calls=" + generated.get());

        long rangeCount = IntStream.range(0, 1_000_000).count();
        System.out.println("range count=" + rangeCount);

        long emptyCount = Stream.<String>empty().count();
        System.out.println("empty count=" + emptyCount);
    }
}
~~~

Compile and run with JDK 17 or a newer JDK supporting Java 17 target:

~~~bash
javac --release 17 StreamCountOptimizationDemo.java
java StreamCountOptimizationDemo
~~~

**Verified stdout on Java 17 in the test environment:**

~~~text
map count=4, map calls=0
peek count=4, peek calls=0
filtered count=2, predicate calls=4
slice count=2
generated count=3, supplier calls=3
range count=1000000
empty count=0
~~~

### 9.1. Why are the numbers right?

1. **`map count=4, map calls=0`:** the `List` source has length 4, `map` preserves cardinality, and the new values are not needed to compute the count.
2. **`peek count=4, peek calls=0`:** `peek` does not change cardinality. The implementation is allowed not to traverse the source when the count is known.
3. **`filtered count=2, predicate calls=4`:** the predicate selects `"ccc"` and `"dddd"`. In this run all four elements were tested to know which two elements are valid.
4. **`slice count=2`:** source of 4 elements, skip one, limit two, so the resulting cardinality is 2.
5. **`generated count=3, supplier calls=3`:** `Stream.generate` is not a finite source with a pre-known size; in the tested implementation, three elements were generated to satisfy `limit(3)`.
6. **`range count=1000000`:** `IntStream.range(0,1_000_000)` describes exactly one million integers from 0 to 999,999, providing sufficient source size information.
7. **`empty count=0`:** an empty Stream has zero elements.

**Important warning about the output:** the `count` result is the contract; the callback counts are **diagnostic data from this run**, not a guarantee that every JVM version must have the exact same call counts. You should check actual behavior on the JDK in use if investigating optimizations, but business design must not rely on those diagnostic numbers.

## 10. Does count() guarantee that exceptions in map are thrown?

**No.** If the count can be computed without evaluating `map`, an exception that `map` itself would throw **when the lambda actually runs** may also not occur.

Illustrative counterexample:

~~~java
// Do not use as a data validation step:
// long count = items.stream()
//         .map(item -> {
//             if (!isValid(item)) throw new IllegalArgumentException();
//             return transform(item);
//         })
//         .count();
~~~

Here `items`, `isValid`, and `transform` are hypothetical names; the code is commented out to emphasize **this is not a reliable validation workflow**. If the source has a known size and `map` only changes values rather than the count, `count` can return a result without calling `isValid`.

If you want to check data and report errors or tally valid elements, use an operation whose **result depends on the condition**:

~~~java
long validCount = items.stream()
        .filter(item -> isValid(item))
        .count();
~~~

This is an example with hypothetical names `items` and `isValid`. With a normal pipeline, the number of elements satisfying the condition depends on inspecting the data. However, if the requirement is to **confirm every element is valid and report full errors**, design an explicit validation workflow or a list of Success/Failure results; do not treat `filter(...).count()` as a general solution for every error-checking policy.

In particular, **do not use side effects or exceptions in `map` as a mandatory check mechanism before `count`**. This is the most important practical lesson of the `count()` optimization.

## 11. count() in parallel streams

A pipeline like:

~~~java
long count = List.of(10, 20, 30, 40)
        .parallelStream()
        .map(n -> n * n)
        .count();
// 4
~~~

still has a `List` source with known cardinality, and `map` still preserves one-to-one mapping. Enabling parallel does not take away the right to infer the count. The implementation may not need to launch parallel callbacks to complete `count()`.

With a pipeline that has `filter` and a large source, predicate evaluation may be distributed across multiple threads. In that case:
- The temporal order of predicate evaluation is not guaranteed to match the source element order.
- Do not write to an `ArrayList` or a non-thread-safe mutable counter from callbacks to predict the exact result.
- If you need conditional counting, let Stream aggregate it via `filter(...).count()`.
- Side effects may be skipped or executed differently if the implementation optimizes the pipeline.
- Do not infer "parallel is faster" solely from the method name. For `count` where size can be obtained directly, trying to enable parallel to speed it up has no clear benefit.

**Do not use `count()` to orchestrate work.** If the requirement is to run an action for each element, design appropriate actions and multithreaded coordination independently of obtaining cardinality.

## 12. Optimization and correctness: when can the count result be inferred?

A technical checklist:

1. **Does the source have an exact size?** `List`, arrays, and bounded numeric ranges are usually easy to infer; unbounded generated sources or a pipeline producing multiple elements may not be.
2. **Do the intermediate steps change the count?** `map` usually preserves it, `filter` and `flatMap` usually change it; `skip`/`limit` can be computed from a known size.
3. **Is the Stream used according to contract?** Do not modify the source during traversal, do not place callbacks that interfere with the source, and do not rely on arbitrary side effects.
4. **Are element values needed or only the count?** If only counting, the framework may not need to create intermediate transformed values.
5. **Is there an intermediate step like `sorted`?** If the element count does not change and the goal is only counting, sorting may be unnecessary work.
6. **Are you relying on a logger/counter inside `peek` or `map`?** If so, that is an unsafe contract.
7. **Is there an infinite source?** `limit` or another termination condition is required if you want the count to complete.
8. **Is there concurrency or source mutation?** You must obey the Collection/Spliterator contract for the result to be deterministic.

Also, do not infer from a Stream having `SIZED` that any operation is automatically `O(1)`. Size determinacy can be lost after processing steps, or the implementation may choose a different execution strategy. **Optimization is permitted**, not an absolute performance guarantee across all systems.

## 13. Common mistakes

| Misconception | Why it is wrong | How to understand/fix |
| --- | --- | --- |
| `count()` always iterates over every element | Cardinality can be obtained from source metadata | See `SIZED` and cardinality-changing steps |
| `peek(...).count()` always prints every element | `peek` may not be evaluated | Only use `peek` for observation, not business execution |
| `map(...).count()` forces `map` logic to run | `map` preserves element count so it can be skipped | Do not put mandatory validation/side effects in `map` before `count` |
| `filter(...).count()` equals `Collection.size()` | Filter can remove elements | Count the result after filtering |
| `count()` is always faster than `size()` | Different purposes and API structures | If only counting a Collection, consider `size()` |
| `limit(5).count()` proves five elements were processed | Cardinality and callback count are different | Do not use count to control callback count |
| `count()` returns `int` | The API returns `long` | Declare `long count` |
| With `parallelStream`, callbacks definitely run multithreaded | The pipeline can optimize away processing | Do not infer threading from the count result |
| Reusing an already-consumed Stream a second time | A terminal operation ends the Stream lifecycle | Create a new Stream from the source |
| Source mutates concurrently yet expecting a stable count | Violates or falls outside the contract of some sources | Stabilize the source or use appropriate structures/concurrency |

### 13.1. A Stream can only be used for one terminal operation

~~~java
Stream<String> stream = List.of("A", "B").stream();
long count = stream.count(); // 2

// Invalid at runtime because the Stream has already been consumed:
// List<String> again = stream.toList();
~~~

This snippet is inside a method and requires importing `java.util.stream.Stream` and `java.util.List`. If you need both the count and the list of values, consider collecting the list first and then counting `list.size()`, or creating a new Stream from the source for the separate task.

## 14. Self-check exercises

**Exercise 1.** Given `List.of(1,2,3,4)`, what is the result of `stream().map(x -> x*10).count()`? Is `map` guaranteed to run four times?

**Answer:** 4. There is no guarantee the callback runs four times; Java may know the source cardinality and `map` does not change the element count.

**Exercise 2.** Why can't `List.of("a","bb","ccc").stream().filter(s -> s.length() > 1).count()` immediately take the count 3 from the List?

**Answer:** because `filter` can exclude elements based on content. The exact result is 2, not 3.

**Exercise 3.** What does `List.of(1,2,3,4,5).stream().skip(2).limit(2).count()` return?

**Answer:** 2. Skipping the first two elements leaves three, then limiting to two. Cardinality can be computed from the pre-known size.

**Exercise 4.** If `peek(System.out::println).count()` on a List prints nothing, is that a Java bug?

**Answer:** No. The API permits skipping element traversal if counting can be done directly; therefore `peek` is not a tool that guarantees printing every element in this case.

**Exercise 5.** Why shouldn't you write `stream.map(this::sendEmail).count()` to send emails for all elements?

**Answer:** `count` may not invoke `map`, because `map` does not change the element count. Sending emails is a mandatory side effect and must be designed using an API/execution contract suited for it.

**Exercise 6.** What should `IntStream.range(0, 100).count()` return?

**Answer:** 100. A numeric range source has an exact size determined by its two endpoints.

**Exercise 7.** What happens when calling `count()` without a limit on an infinite Stream from `Stream.generate(...)`?

**Answer:** there is no finite count to complete normally. A limit or another appropriate termination mechanism is needed if you want to obtain a result.

**Exercise 8.** Is a line reporting `mapped=0` in an experiment enough to conclude that every JDK always skips `map` when counting?

**Answer:** No. That is empirical behavior of a specific implementation and pipeline. The contract only permits optimizing away work that does not affect the count result.

## 15. References

- [Java SE 17 API — Stream.count() and API Note on skipping pipeline execution](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#count()).
- [Java SE 17 API — Spliterator.SIZED and getExactSizeIfKnown()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Spliterator.html).
- [Java SE 17 API — IntStream.count()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/IntStream.html#count()).
- [Java SE 17 API — Stream.peek()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#peek(java.util.function.Consumer)).
- [Java SE 17 API — Stream pipelines and side effects](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/package-summary.html).

**Remember:** `count()` counts elements **of the resulting Stream**, it does not prove how many times callbacks executed. A source with a known exact size combined with count-preserving steps like `map`/`peek` can allow Java to return the result without traversal. Conversely, steps like `filter` and `flatMap` usually make the count depend on the data. Choose `count()` to **count**, not as a way to force validation, logging, or side effects to run.