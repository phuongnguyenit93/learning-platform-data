# Distinguishing Stateless Functions from Stateful Stream Operations

## 1. The Core Issue: Two Levels of "State"

When learning Java Streams and functional programming, the phrase **stateless** can be used at **two different levels**:

1. **Behavior passed into a Stream** (*behavioral parameter*) — for example, a lambda for `map`, `filter`, `peek`, or a `Comparator`. A behavior is considered stateless when its result does not depend on mutable state that can change during processing; ideally, given the same input and the same fixed conditions, it produces the same result and does not update shared state.
2. **A Stream pipeline operation** (*intermediate operation*) — some operations themselves need to remember, buffer, or coordinate information across multiple elements to decide the output. Those operations are classified as **stateful**, even when all the lambdas we pass into them are pure and have no side effects.

These two levels are **not identical**. A pipeline using stateless lambdas can still contain `sorted()` or `distinct()` — those are valid **stateful intermediate operations** built into Java by design. Conversely, `filter()` is classified as a stateless intermediate operation, yet **a programmer-written predicate can secretly hold state**, making the result unpredictable, especially when running in parallel.

Example:

~~~java
// Stateless lambda: the result depends only on n.
IntStream.rangeClosed(1, 5)
        .filter(n -> n % 2 == 0);

// Stateful stream operation: must inspect elements to remove duplicates.
IntStream.of(3, 1, 3, 2)
        .distinct();
~~~

These are **illustrative snippets** requiring `import java.util.stream.IntStream`. There is no terminal operation yet, so the stream is not consumed.

**Key takeaway:** "A Stream has a stateful operation" **does not mean** the pipeline violates functional programming. The problem usually lies in **stateful lambdas, side effects, and interfering with the data source** that the author introduces into behavioral parameters.

## 2. What Is a Stateless Function?

Consider a lambda that squares a number:

~~~java
IntUnaryOperator square = x -> x * x;
~~~

This is an illustrative snippet requiring `import java.util.function.IntUnaryOperator`.

For a fixed input `x` in the `int` domain, the lambda does not reference a changing counter, a mutable external variable, the current time, or the result of a previous call. For example, `square.applyAsInt(4)` always returns `16`. It is considered **stateless** with respect to the data being processed.

A simple predicate:

~~~java
Predicate<String> nonBlank = s -> s != null && !s.isBlank();
~~~

This is an illustrative snippet requiring `import Predicate`. It makes the same decision for the same input string and does not modify external data.

### 2.1. Stateless Does Not Necessarily Mean Using No External Data at All

A lambda can close over an **immutable** configuration:

~~~java
final int minimum = 10;
IntPredicate allowed = n -> n >= minimum;
~~~

Illustrative snippet requiring `import IntPredicate`. Using `minimum` is valid and stable: a captured local variable must be **final or effectively final**. It does not by itself turn the lambda into a stateful one.

With a configuration object:

~~~java
final Set<String> allowedCodes = Set.of("A", "B");
Predicate<String> allowed = allowedCodes::contains;
~~~

This is an illustrative snippet requiring `import Set`, `Predicate`. If the code set is not modified while the pipeline is active and the `contains` check has no side effects, the behavior aligns with being stateless. **The core point is whether the observed state is stable**, not how many variables the lambda captures.

### 2.2. Behaviors That Easily Make a Lambda Stateful

The following lambda **depends on the order and number of times it is called**:

~~~java
AtomicInteger index = new AtomicInteger();

Predicate<String> everySecond = word ->
        index.incrementAndGet() % 2 == 0;
~~~

This is an illustrative snippet requiring `import AtomicInteger`, `Predicate`.

For the same input `"java"`, the predicate may return `false` on the first call and `true` on the second call because the counter has changed. **AtomicInteger only makes the increment atomic; it does not turn order-dependent logic into stateless logic**. In a parallel stream, which element is the "second" one depends on execution scheduling.

Common forms of state dependency:

- Using `counter++`, `AtomicInteger.incrementAndGet()`, or `List.add(...)` inside `map`/`filter`.
- Reading a mutable `current` field modified by another thread while the pipeline is running.
- Making decisions based on `System.currentTimeMillis()` or data from a constantly changing external source.
- Modifying the source Collection itself while the Stream is traversing that source.
- Logging, sending a request, or updating a database inside a callback and assuming it will always run exactly once per element.

Not all of the examples above lead to compilation errors: **most of them still compile**. The risk lies in **correctness, repeatability, and parallelizability**.

## 3. How Does Java Classify Intermediate Operations?

An **intermediate operation** creates a new Stream from the previous Stream, typically not executing immediately because Streams are **lazy**. At the Stream contract level, operations are generally classified into:

| Operation | Classification | Typical Mechanism |
| --- | --- | --- |
| `map(f)` | **Stateless** | Transforms each element using `f` |
| `mapToInt(f)` / `flatMap(f)` | **Stateless** | Transforms/flattens elements without needing to remember the previous set of elements |
| `filter(p)` | **Stateless** | Decides whether to keep an element based on a predicate |
| `peek(action)` | **Stateless** | Observes elements passing through the step, without itself needing to store seen elements |
| `distinct()` | **Stateful** | Recognizes previously encountered elements to remove duplicates |
| `sorted()` | **Stateful** | Needs to examine multiple elements to determine global order |
| `limit(n)` | **Stateful** | Needs to track the number of emitted elements, with short-circuiting |
| `skip(n)` | **Stateful** | Needs to know how many elements have been skipped |
| `takeWhile(p)` / `dropWhile(p)` | **Stateful** | Determines the prefix boundary based on order and predicate results |

**Note:** The classification in the table is a **property of the Stream operation**, not a guarantee that the lambda passed by the programmer is stateless. `map(n -> counter.incrementAndGet())` still calls a **stateless intermediate operation `map`**, yet the lambda inside **depends on mutable state** — an error-prone design.

Some operations can hold very little information instead of buffering the entire source. For example, `limit(n)` tracks the count to take; it does not have to store every element. Therefore, **stateful is not synonymous with "loading all data into RAM"**.

## 4. Java 17 Example: Same Data, Two Kinds of Operations

Create the file **StreamStateKindsDemo.java**:

~~~java
import java.util.List;

public class StreamStateKindsDemo {
    public static void main(String[] args) {
        List<Integer> source = List.of(5, 2, 5, 1, 2, 3);

        List<Integer> stateless = source.stream()
                .map(n -> n * 2)
                .filter(n -> n >= 4)
                .toList();

        List<Integer> stateful = source.stream()
                .distinct()
                .sorted()
                .limit(3)
                .toList();

        System.out.println("Stateless stages: " + stateless);
        System.out.println("Stateful stages: " + stateful);
        System.out.println("Source: " + source);
    }
}
~~~

Compile and run with **JDK 17 or later**:

~~~bash
javac StreamStateKindsDemo.java
java StreamStateKindsDemo
~~~

Stdout:

~~~text
Stateless stages: [10, 4, 10, 4, 6]
Stateful stages: [1, 2, 3]
Source: [5, 2, 5, 1, 2, 3]
~~~

Explanation:

1. In the first pipeline, `map(n -> n * 2)` transforms the data into `[10,4,10,2,4,6]`. `filter(n >= 4)` discards `2` without needing to know about other elements. Both steps are **stateless intermediate operations**.
2. The second pipeline uses `distinct()` to remove duplicates: the unique values in encounter order are `[5,2,1,3]`. `sorted()` arranges them into `[1,2,3,5]`. `limit(3)` picks the first three values and returns `[1,2,3]`.
3. All three operations in the second pipeline are **classified as stateful** by the Stream API, yet they are completely valid and require neither writing a manual counter nor mutating the source.
4. `source` remains unchanged, because the operations here do not interfere with the source collection.

**A nuance:** `distinct()` on an ordered stream keeps the first representative element in encounter order. With an unordered source, the choice of representative element and traversal order may differ; one should not use a specific HashSet result as proof of encounter order.

## 5. Why Are map/filter Stateless Operations?

Conceptually, `map(f)` can apply `f` to the current element without waiting for the entire stream:

~~~text
n = 3  -> map(n * 2) -> 6
n = 5  -> map(n * 2) -> 10
n = 2  -> map(n * 2) -> 4
~~~

Similarly, `filter(p)` only needs to know `p(x)` for the current element `x` to decide whether to emit `x`. When behavioral parameters are also stateless/non-interfering, a Stream can **fuse** consecutive steps in a sequential pipeline:

~~~text
source element 1 -> map -> filter -> downstream
source element 2 -> map -> filter -> downstream
source element 3 -> map -> filter -> downstream
~~~

This is a conceptual diagram, not a guarantee of every implementation detail. Pipelines with stateful operations or parallel execution may organize data differently.

### 5.1. flatMap Is Also Classified as Stateless

`flatMap` can create a sub-Stream from **each source element** and then emit the sub-elements. Example:

~~~java
List<String> tokens = List.of("a,b", "c").stream()
        .flatMap(s -> java.util.Arrays.stream(s.split(",")))
        .toList();
~~~

This is an illustrative snippet requiring `import List`. The result is `[a, b, c]`. `flatMap` does not need to remember all tokens from previous elements to decide the tokens for the current element.

However, the mapper `s -> ...` **can still be written incorrectly** if it reuses the same sub-Stream that gets consumed multiple times or writes to shared mutable state. The fact that an operation is classified as stateless **does not certify** that every mapper is safe.

### 5.2. peek Is a Stateless Operation, Yet Its Action Has a Side Effect

`peek(action)` is commonly used for observation during debugging:

~~~java
List<Integer> values = List.of(1, 2, 3).stream()
        .peek(n -> System.out.println("seen: " + n))
        .map(n -> n * 2)
        .toList();
~~~

This is an illustrative snippet. `peek` **is not classified as stateful** just because the action prints logs; the operation itself does not need to remember elements that have passed through.

However, the action has a **side effect**, and Java Streams reserve the right to optimize certain pipelines or stop early, so **do not use `peek` for mandatory work** such as audit logging or updating state. `peek(...).count()` on a sized source may not invoke the action because the count is computed directly; logs are not reliable proof of the number of processed elements.

**Clearly distinguish three questions:**
- Does the operation maintain internal state? For `peek`: **no**.
- Does the callback have a side effect? `System.out.println`: **yes**.
- Is that side effect guaranteed to execute for every element? **Do not assume so** in a Stream pipeline.

## 6. distinct(): Requires Information About Seen Elements

`distinct()` removes duplicate elements according to `Object.equals` on object streams, or by value semantics on primitive streams. To decide whether the element under consideration is new, the operation needs information about previous elements or an equivalent structure.

Example:

~~~java
List<String> unique = List.of("A", "B", "A", "C", "B")
        .stream()
        .distinct()
        .toList();
~~~

This is an illustrative snippet requiring `import List`. With an ordered `List` source, the result is **[A, B, C]**.

**Being stateful is a valid property of `distinct`:** Java manages the duplicate-detection structure inside the framework; programmers **should not** replace it with:

~~~java
Set<String> seen = new HashSet<>();
List<String> unique = source.stream()
        .filter(seen::add)
        .toList();
~~~

This is an **illustrative anti-pattern** requiring `import Set`, `HashSet`, `List` and a `source` variable. Although in some sequential pipelines it may produce a similar result, `seen::add` **mutates an external Set** inside a predicate. In a parallel stream, `HashSet` is not thread-safe and can cause race conditions and wrong results. Using a synchronized set only partially addresses data safety and does not replace the ordered, optimized semantics of `distinct`.

Use directly:

~~~java
List<String> unique = source.stream().distinct().toList();
~~~

This is the proper way to express the intent when you want to remove duplicate elements.

### 6.1. Equality and Mutable Objects

If `distinct()` processes mutable objects whose `equals`/`hashCode` depend on fields that change during processing, the result can be unreliable. Data used for deduplication should have **stable identity and equality rules** throughout the pipeline. The statefulness managed by `distinct` does not guarantee that all input objects are immutable.

## 7. sorted(): Usually Needs to See Multiple Elements Before Emitting Results

`sorted()` or `sorted(comparator)` must determine the order of elements. For a typical finite stream, this usually leads to **buffering and sorting** the data before emitting it in the desired order.

Example:

~~~java
List<Integer> ordered = List.of(4, 1, 3, 2)
        .stream()
        .sorted()
        .toList();
~~~

Result: **[1, 2, 3, 4]**.

You cannot apply `sorted()` simply as "look at one element and immediately know the smallest first element" when the source has not ended. This is the intuitive point for understanding why `sorted` is **stateful** while `map`/`filter` are **stateless**.

### 7.1. Observing Buffering with peek

Create the file **SortedBoundaryDemo.java**:

~~~java
import java.util.List;

public class SortedBoundaryDemo {
    public static void main(String[] args) {
        List<Integer> output = List.of(4, 1, 3, 2)
                .stream()
                .peek(n -> System.out.println("before=" + n))
                .sorted()
                .peek(n -> System.out.println("after=" + n))
                .toList();

        System.out.println("result=" + output);
    }
}
~~~

Run:

~~~bash
javac SortedBoundaryDemo.java
java SortedBoundaryDemo
~~~

Stdout in the sequential pipeline of the example:

~~~text
before=4
before=1
before=3
before=2
after=1
after=2
after=3
after=4
result=[1, 2, 3, 4]
~~~

**Interpretation:** The values observed before `sorted` follow the source order, and after `sorted` follow ascending order. This is a useful illustration of a stateful boundary.

**Do not treat the order of `peek` log lines as a general contract** when switching to a parallel stream or when the JVM applies other optimizations. Verify the resulting data and encounter order requirements rather than testing an order of side effects that the API does not guarantee in all cases.

### 7.2. Comparators Should Be Stateless and Consistent

`sorted(comparator)` uses the comparator to compare many pairs of elements. A comparator should not rely on a counter variable, randomness, or mutable fields that change during sorting. If the same pair of values is compared multiple times and yields contradictory results, sorting may produce the wrong order or throw an exception for violating the comparison contract.

Suitable example:

~~~java
Comparator<String> byLengthThenText =
        Comparator.comparingInt(String::length)
                .thenComparing(Comparator.naturalOrder());
~~~

Illustrative snippet requiring `import Comparator`. The comparator is stable on immutable `String`s and returns a deterministic order: first by length, then by natural order.

## 8. limit(), skip(), takeWhile(), dropWhile(): Stateful by Position/Boundary

Not every stateful operation has to buffer the entire source. Some need to remember **relative position** or **whether a boundary has been crossed**.

### 8.1. limit(n)

`limit(n)` emits at most `n` elements (when `n` is non-negative). It is a stateful **short-circuiting intermediate operation**: once `n` output elements have been produced, the rest do not need to be requested in many pipelines.

~~~java
List<Integer> firstThree = IntStream.rangeClosed(1, 10)
        .limit(3)
        .boxed()
        .toList();
~~~

The result is **[1, 2, 3]**. This is an illustrative snippet with `import IntStream`, `List`.

### 8.2. skip(n)

`skip(n)` discards the first `n` elements of a stream with encounter order. It needs to track how many elements have been skipped, so it is stateful.

~~~java
List<Integer> remaining = IntStream.rangeClosed(1, 6)
        .skip(2)
        .boxed()
        .toList();
~~~

The result is **[3, 4, 5, 6]**.

### 8.3. takeWhile / dropWhile (Java 9+)

On an **ordered stream**, `takeWhile(p)` keeps the longest prefix of consecutive elements satisfying `p`, while `dropWhile(p)` discards that longest prefix and emits the rest.

~~~java
List<Integer> take = IntStream.of(1, 2, 3, 0, 4, 5)
        .takeWhile(n -> n > 0)
        .boxed()
        .toList();

List<Integer> drop = IntStream.of(1, 2, 3, 0, 4, 5)
        .dropWhile(n -> n > 0)
        .boxed()
        .toList();
~~~

In this example, `take = [1, 2, 3]` and `drop = [0, 4, 5]`. **Unlike `filter`**, `takeWhile` **stops taking when it encounters the first element that does not match**, and does not continue selecting the positive numbers after it.

### 8.4. Consequences of Encounter Order

For streams with encounter order, `limit`/`skip`/`takeWhile`/`dropWhile` refer to the specified prefix/positions; when the source is **unordered** or the pipeline has used `unordered()`, element selection may differ, depending on each operation's contract.

In particular, `limit` and `skip` on an **ordered parallel stream** can be more expensive because they must preserve exact relative order. Only switch to `unordered()` if **the business logic genuinely does not care which specific elements are kept or dropped**, not merely for performance optimization.

## 9. Java 17 Example: Slicing and Short-Circuiting with Infinite Data

Create the file **SliceAndWhileDemo.java**:

~~~java
import java.util.List;
import java.util.stream.IntStream;

public class SliceAndWhileDemo {
    public static void main(String[] args) {
        List<Integer> firstEven = IntStream.iterate(1, n -> n + 1)
                .filter(n -> n % 2 == 0)
                .limit(3)
                .boxed()
                .toList();

        List<Integer> take = IntStream.of(1, 2, 3, 0, 4, 5)
                .takeWhile(n -> n > 0)
                .boxed()
                .toList();

        List<Integer> drop = IntStream.of(1, 2, 3, 0, 4, 5)
                .dropWhile(n -> n > 0)
                .boxed()
                .toList();

        System.out.println("Even: " + firstEven);
        System.out.println("Take: " + take);
        System.out.println("Drop: " + drop);
    }
}
~~~

Run:

~~~bash
javac SliceAndWhileDemo.java
java SliceAndWhileDemo
~~~

Stdout:

~~~text
Even: [2, 4, 6]
Take: [1, 2, 3]
Drop: [0, 4, 5]
~~~

**Analysis:**

1. `IntStream.iterate(1, n -> n + 1)` creates a stream with no fixed endpoint. The `filter` predicate selects only even numbers.
2. `limit(3)` is a short-circuiting operation and only needs the first three even numbers. Therefore, the pipeline can terminate even though the `iterate` source is conceptually infinite.
3. `takeWhile(n > 0)` on a finite ordered stream stops when it encounters `0`; it does not select `4` and `5` even though they are still positive.
4. `dropWhile(n > 0)` skips `1, 2, 3` and then emits `0, 4, 5`.
5. The predicate `n -> n > 0` is **stateless**; the operations `takeWhile`/`dropWhile` are **stateful** because they need to remember whether the boundary has been reached.

**Performance note:** Placing `sorted()` on an **infinite stream** and then waiting for `limit(3)` normally cannot produce the first three values because `sorted` must finish sorting before knowing the global order. Conversely, `limit(3).sorted()` only has to sort a finite set of three elements. **Stage order affects not only the result, but also termination and memory usage.**

## 10. How Can a Stateful Lambda Break filter?

Create the file **StatefulPredicateDemo.java**:

~~~java
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Predicate;

public class StatefulPredicateDemo {
    public static void main(String[] args) {
        List<String> words = List.of("a", "bb", "ccc");
        AtomicInteger calls = new AtomicInteger(0);

        Predicate<String> everySecondCall = text ->
                calls.incrementAndGet() % 2 == 0;

        System.out.println("First: " + words.stream()
                .filter(everySecondCall).toList());

        System.out.println("Second: " + words.stream()
                .filter(everySecondCall).toList());

        Predicate<String> lengthAtLeastTwo =
                text -> text.length() >= 2;

        System.out.println("Stateless: " + words.stream()
                .filter(lengthAtLeastTwo).toList());

        System.out.println("Again: " + words.stream()
                .filter(lengthAtLeastTwo).toList());
    }
}
~~~

Run:

~~~bash
javac StatefulPredicateDemo.java
java StatefulPredicateDemo
~~~

Stdout of the **sequential** program:

~~~text
First: [bb]
Second: [a, ccc]
Stateless: [bb, ccc]
Again: [bb, ccc]
~~~

Explanation:

1. The first pass calls the predicate three times: count 1 (drops `"a"`), 2 (keeps `"bb"`), 3 (drops `"ccc"`).
2. The second pass **reuses the same Predicate with an unreset AtomicInteger**: count 4 (keeps `"a"`), 5 (drops `"bb"`), 6 (keeps `"ccc"`).
3. The same input list yields different filter results because the predicate depends on **the history of call counts**, not just the element value.
4. `lengthAtLeastTwo` only reads the `String` length, so both passes return the same `[bb, ccc]`.

**This stateful predicate example is used to illustrate a design flaw**, not a pattern to adopt. If switched to a parallel stream, the number of calls might still match the number of elements inspected in this particular case, but **which element receives which count is not reliable**. `AtomicInteger` protects counter updates from races at the increment level, not the meaning of "the second element in encounter order".

### 10.1. Why Is External Mutable State More Dangerous Than Using distinct?

With `distinct()`, Java knows it is a stateful intermediate operation and takes responsibility for organizing duplicate detection and combining results according to contract. With `filter(seen::add)`, Java only sees a `filter` whose behavioral parameters are expected by contract to be **non-interfering** and generally **stateless**. The `seen` state lives outside the managed collector/operation mechanism; Stream has no way to interpret it as stable-order deduplication when optimizing or parallelizing.

Therefore, **prefer `distinct()`**, and do not write a `filter` that manually maintains a seen Set. Similarly, prefer **`limit(n)`** instead of a `filter` that depends on a counter to take `n` elements.

## 11. Stateless Is Not Quite the Same as Pure; Side Effects Are Also a Separate Issue

A **pure** function typically has these properties: the same input produces the same output, and **there are no observable side effects**. A **stateless** lambda in the Stream sense usually does not depend on mutable state across calls; however, a callback can still cause side effects without needing to remember previous results.

Example:

~~~java
Consumer<String> logger = text -> System.out.println(text);
~~~

It needs no memory to decide a return value, yet **printing to the console is a side effect**. Because `Consumer` returns no value, its notion of purity must be considered in terms of actions rather than mapping functions; it is not a pure transformation.

A transformation with a side effect:

~~~java
Function<String, String> withLog = text -> {
    System.out.println("processing " + text);
    return text.strip();
};
~~~

This is an illustrative snippet requiring `import Function`. The return value is computed from `text`, yet the callback writes logs, and Stream does not guarantee every callback will be called under all optimizations.

**Separate three questions:**

| Question | Example | Consequence |
| --- | --- | --- |
| Is the operation stateful? | `sorted()` | Requires coordination across elements |
| Does the behavioral parameter use mutable state? | `filter(x -> ++count % 2 == 0)` | Easily depends on call history, unsafe |
| Does the callback have a side effect? | `peek(System.out::println)` | Do not use as mandatory business logic |

You can have a completely valid **stateful Stream operation** using a **pure comparator**. You can also have a **stateless Stream operation** using a **side-effectful callback**. You should not infer all properties from a single "stateful" label.

## 12. Non-Interference: Do Not Modify the Source Being Traversed

The Stream API generally requires behavioral parameters **not to interfere with the data source** (*non-interfering*). This means not modifying the source collection while the stream is traversing it, except for sources specifically designed to support concurrent modification under their own contract.

Anti-pattern:

~~~java
List<Integer> numbers = new ArrayList<>(List.of(1, 2, 3));

numbers.stream()
        .peek(n -> numbers.add(n + 10))
        .toList();
~~~

This is an **illustrative anti-pattern snippet** requiring `import ArrayList`, `List`; it should not be run in a real application. Calling `numbers.add(...)` mutates the very `ArrayList` serving as the source. It can throw `ConcurrentModificationException`, cause unpredictable behavior, or allow the pipeline to be optimized in a way that skips the side effect.

A clearer approach when you want to create a new list:

~~~java
List<Integer> result = numbers.stream()
        .map(n -> n + 10)
        .toList();
~~~

This is an illustrative snippet. `map` creates new output values without mutating the source.

If the actual goal is to update mutable data (such as payments or changing record status), use an **explicit workflow with clear error boundaries, ordering, and transactions**, rather than hiding updates inside `peek` or `map`.

## 13. Stateful Operations and Stream Laziness

Streams are **lazy**: intermediate operations only describe the pipeline; actual work usually occurs when a terminal operation requests the result.

Example:

~~~java
Stream<Integer> pipeline = Stream.of(3, 1, 2).sorted();
~~~

On this line, we have only created a pipeline with stateful `sorted()`; **no actual sorting is required yet** until a terminal operation consumes it.

~~~java
List<Integer> sorted = pipeline.toList();
~~~

At that point, the Stream must produce the result in sorted order.

However, **a terminal operation does not guarantee that every intermediate callback will always run**. Example:

~~~java
long count = List.of(1, 2, 3).stream()
        .map(n -> {
            System.out.println("map " + n);
            return n * 2;
        })
        .count();
~~~

This is an illustrative snippet. With a known-size source and a pipeline that does not change the number of elements, `count()` can compute **3** without traversing `map`, so there is no guarantee that three log lines will be printed.

**Implication:** Do not use side effects in behavioral parameters as proof that each element was processed. Laziness and optimization capabilities are API features, not bugs.

### 13.1. Do Stateful Operations Always Force Full Traversal?

**No.** `sorted()` on finite input without pre-existing order information usually needs all the data to sort. However, `limit(3)` can finish early; `distinct().limit(3)` can stop after finding three distinct elements without reading the entire source, depending on pipeline structure and ordering.

For that reason, **stateful** is not synonymous with **blocking the entire stream**. You need to analyze the **specific mechanism** of each operation.

## 14. Ordered, Unordered, and Parallel: When Statefulness Becomes Expensive

Some stateful operations incur extra overhead when preserving **encounter order** in a parallel pipeline:

- **distinct()** on an ordered parallel stream must preserve stability in encounter order for representative elements, which may require buffering/coordination.
- **limit(n)** and **skip(n)** on an ordered parallel stream must respect the exact prefix/offset; this can make coordination expensive.
- **sorted()** must establish a total order for the result, so it cannot be processed like an independent per-element map.
- **takeWhile/dropWhile** on an ordered parallel stream must identify the prefix boundary; the API warns this can be more expensive than sequential execution.

Sometimes `unordered()` can be used if the output **does not need to preserve position or encounter order**:

~~~java
Set<Integer> selected = IntStream.rangeClosed(1, 1000)
        .parallel()
        .unordered()
        .limit(10)
        .boxed()
        .collect(Collectors.toSet());
~~~

This is an illustrative snippet requiring `import Set`, `IntStream`, `Collectors`. It can only guarantee **at most 10 distinct elements** from the given source; **it cannot promise exactly 1..10** when the pipeline is unordered. In this example with distinct numbers, 10 elements can be obtained, but the specific set should not be relied upon as a contract.

**Do not switch to `unordered()` if the business requirement needs "the first 10 records by date"**. To optimize safely, first confirm whether ordering matters.

### 14.1. A Correct Result with Out-of-Order Logs

A parallel stream may process elements across multiple threads, so logs from `peek` or `map` can interleave even though the `toList()` result from a source with encounter order is returned in order.

Example:

~~~java
List<Integer> result = IntStream.rangeClosed(1, 5)
        .parallel()
        .map(n -> n * 10)
        .boxed()
        .toList();
~~~

This is an illustrative snippet. The result is still **[10, 20, 30, 40, 50]** in encounter order. If you add logging inside each mapper, the log order does **not** have to match the result order.

This is why a counter inside a mapper is unsuitable for defining "the element's index in the final list".

## 15. Collectors Have Mutable Accumulators, Which Does Not Mean Stateful Lambdas Are Wrongly Condoned

Learners sometimes think: "If functional programming should be stateless, why does `collect` use a mutable ArrayList/HashMap to accumulate?"

That is **a different mechanism**. `collect` is a terminal **mutable reduction**, in which a Supplier creates a container, an accumulator adds elements, and a combiner merges containers when needed. The state is **managed under the Collector's contract**, not an arbitrary shared variable written to inside `filter`.

Example:

~~~java
ArrayList<String> result = Stream.of("a", "b", "c")
        .collect(Collectors.toCollection(ArrayList::new));
~~~

This is an illustrative snippet requiring `import ArrayList`, `Stream`, `Collectors`. `ArrayList` is the target mutable container; collecting into it is completely normal.

Anti-pattern:

~~~java
List<String> outside = new ArrayList<>();

source.parallelStream()
        .forEach(outside::add);
~~~

This is an illustrative snippet assuming `source` is a suitable collection. `ArrayList` is not thread-safe for multiple threads calling `add` concurrently. Even if `synchronized` is added, the order of elements in `outside` may not correspond to encounter order. If the goal is to **collect results**, choose an appropriate Collector instead of sharing an external `List`.

**Distinguish the terminology:**

- `sorted`, `distinct`, `limit`, `skip`: **stateful intermediate operations**.
- `map`, `filter`, `peek`: **stateless intermediate operations** by Stream design.
- `collect`: **terminal mutable reduction**, managed by the Collector.
- `filter(x -> sharedCounter.incrementAndGet() ...)`: **stateful behavioral parameter**, usually dangerous for pipeline semantics.

## 16. Should All Stateful Operations Be Avoided?

**No.** Stateful operations are standard components of the Stream API for expressing real-world requirements:

- `distinct()` when duplicates need to be removed.
- `sorted()` when global ordering is needed.
- `limit(n)` and `skip(n)` when slicing by position is needed.
- `takeWhile` and `dropWhile` when processing prefixes on ordered streams.

What should be avoided is **introducing external mutable state into behavioral parameters in an uncontrolled way** or using side effects in Streams as a mandatory part of business logic.

Choosing between a Stream with stateful operations and a loop depends on **clarity, memory, termination, ordering, and performance**. If you need a complex stateful algorithm (state machines, ledger updates, ordered retries, comparing consecutive pairs of elements), an explicit loop or a dedicated abstraction is sometimes easier to understand and safer than forcing it into lambdas using external counters.

## 17. Common Mistakes

| Misconception/Mistake | What Is Wrong | How to Handle It |
| --- | --- | --- |
| "A Stream with sorted is bad functional programming because it uses state" | `sorted` manages state internally per the API | Use `sorted` when sorting is needed, and evaluate cost |
| "filter is stateless, so every predicate is stateless" | A predicate can use a counter/shared Set | Write predicates based on input and stable configuration |
| "AtomicInteger makes a lambda stateless" | Atomic only makes updates atomic | Do not use a counter to decide element order |
| "distinct is the same as filter(seen::add)" | `seen` is external mutable state with race risks | Use `distinct` |
| "takeWhile is the same as filter" | `takeWhile` only keeps a contiguous prefix | Distinguish boundary checks from full-source filtering |
| "Every stateful operation reads the entire source" | `limit` can short-circuit | Examine each operation's mechanism |
| "limit after sorted on an infinite source will still return results" | `sorted` may never terminate | Limit the source before `sorted` if that matches requirements |
| "Parallel logs will follow the result order" | Tasks run concurrently | Rely on result data/encounter order |
| "peek is a stateful operation because it prints" | The operation is stateless; the action has a side effect | Separate operation and callback concepts |
| "collect using a mutable List is wrong" | Mutable reduction is a standard contract | Use a Collector; avoid shared external lists |
| "map always runs exactly once per source element" | Laziness/optimization/short-circuiting | Do not rely on side effects in `map` |
| "unordered() always speeds things up without changing business logic" | It can change which elements are selected/kept | Only use `unordered` when order does not matter |
| "A Comparator can read random values" | Inconsistent comparison rules | Use a stable comparator that obeys its contract |
| "A stateful lambda assigning an index will match List positions" | Call order is not necessarily encounter order | Use an indexed source or an appropriate data structure |

## 18. Checklist When Writing Stream Pipelines

1. **Am I talking about the operation's state or the lambda's state?** Keep the two levels separate.
2. **Do mappers/predicates depend only on input and stable configuration?**
3. **Is there any `counter++`, `seen.add`, `List.add`, or update to a shared field?** Consider redesigning.
4. **Is the source modified during traversal?** Avoid violating non-interference.
5. **Which operations need multiple elements to decide?** Analyze `distinct`/`sorted`/`limit`/`skip`/`takeWhile`/`dropWhile`.
6. **Is there short-circuiting?** Having some elements not processed is valid.
7. **Is the source finite or infinite?** `sorted` before `limit` can prevent the pipeline from terminating.
8. **Does encounter order matter?** This determines whether `unordered`/parallel can be used.
9. **Am I using logs in `peek`/`map` to infer processing counts?** Do not turn logs into business data.
10. **Do I need to accumulate data?** Use an appropriate `collect`/`reduce`/`count`/`sum` instead of an external `List`.
11. **Will the lambda run in a parallel stream?** Avoid shared mutable state, unstable comparators, and order-dependent side effects.
12. **Have I tested empty input, duplicates, ordering, short-circuiting, and repeated runs?**

## 19. Practice Exercises

### Exercise 1: Classify Operations and Callbacks

Given the pipeline:

~~~java
words.stream()
        .map(String::strip)
        .distinct()
        .sorted()
        .filter(s -> s.length() > 2)
        .limit(5)
        .toList();
~~~

This is an illustrative snippet assuming `words` is a `List<String>` with no nulls.

Identify which intermediate operations are **stateless**, which are **stateful**, and explain why `String::strip` is stateless behavior. Answer: `map` and `filter` are stateless; `distinct`, `sorted`, and `limit` are stateful.

### Exercise 2: Element-Counting Anti-Pattern

Write a `Predicate<Integer>` based on `AtomicInteger` to keep "every second element". Run it twice on the same `List` with two new Streams while reusing the Predicate. Explain why the results can differ and why switching to parallel makes the semantics worse.

### Exercise 3: Choosing the API Instead of a Shared Set

From the List `[1,2,1,3,2]`, try `distinct().toList()` and compare it with `filter(seen::add)` when running sequentially. Why should the second approach not be used in a parallel stream? What happens if you reuse the `seen` Set from a previous run?

### Exercise 4: Stateful Operations on an Infinite Source

Create an `IntStream.iterate(1,n -> n+1)`. Compare the meaning and termination of `limit(5).sorted().toList()` versus `sorted().limit(5).toList()`. Analyze without trying to run the variant that may not terminate.

### Exercise 5: takeWhile vs filter

Use the source `[1,2,0,3,4]`. Compare `filter(n -> n > 0)`, `takeWhile(n -> n > 0)`, and `dropWhile(n -> n > 0)`. Predict the three results: `[1,2,3,4]`, `[1,2]`, and `[0,3,4]`.

### Exercise 6: Ordered Parallel and limit

Try `IntStream.rangeClosed(1,1000).parallel().limit(10)`; explain why the contract of an ordered stream still targets the first 10 elements in encounter order. Then add `unordered()` and state why you should not guarantee the same 10 elements by source position.

### Exercise 7: Distinct and Comparator

Why does `distinct()` on an object stream rely on `equals` while `sorted(comparator)` relies on the comparator? What can happen if a comparator depends on a mutable field that changes during sorting?

### Exercise 8: Parallel Collection

Replace `parallelStream().forEach(sharedList::add)` with `parallelStream().collect(Collectors.toList())` or `toCollection(ArrayList::new)`. Why can a collector create intermediate containers to combine without sharing a single `ArrayList` across all tasks?

## 20. Takeaways

**There are two different meanings of "stateful":**

- **Stateful behavioral parameter**: a lambda or method reference that depends on mutable state/call history. This is a common source of bugs when used in `map`, `filter`, `peek`, especially in parallel streams.
- **Stateful intermediate operation**: a standard operation such as **distinct, sorted, limit, skip, takeWhile, dropWhile** that inherently needs state to manage seen elements, ordering, or boundaries. These operations are **valid** and are an important part of the Stream API.

**`map`, `filter`, `flatMap`, and `peek` are stateless intermediate operations**, but the callbacks passed by the author can still cause side effects or depend on state. **`collect`** is a terminal reduction that can use a mutable accumulator under its own contract; it is not the same as an arbitrary lambda writing into a shared external `List`.

When choosing a pipeline, consider **lazy evaluation, encounter order, short-circuiting, memory requirements, infinite sources, and the cost of parallelism**. The core question before writing a lambda: **"Will this function make the same decision for the same input regardless of how many times it is called, on which thread, and in what order?"** If not, re-evaluate how state is organized instead of relying solely on the fact that the outer Stream operation is named `map` or `filter`.