# takeWhile() and dropWhile() on Ordered Stream Sources in Java

## 1. Essence: processing a **contiguous prefix**, not filtering the entire stream

In the Java Stream API, `takeWhile(Predicate)` and `dropWhile(Predicate)` are two intermediate operations (*intermediate operations*) introduced in **Java 9**. They are especially useful when the source has an **encounter order** (the order of elements determined by the source and pipeline), such as `List`, `Stream.of(...)`, or `IntStream.range(...)`.

For an **ordered** stream, the two methods have exact behavior:

- **`takeWhile(predicate)`**: returns the **longest prefix of contiguous elements that match the predicate**, starting from the **beginning** of the encounter order. Upon encountering the first element that **does not match**, the prefix ends. That element and subsequent elements are not included in the result.
- **`dropWhile(predicate)`**: **drops the longest prefix of contiguous elements that match the predicate**, then keeps the **rest** of the encounter order, including later elements that match the predicate again.

Example with source `[2, 4, 6, 7, 8, 10]` and predicate “is even”:

```text
Encounter order:       2    4    6   | 7    8    10
Predicate even?:      yes  yes  yes | no  yes   yes
                                     ^
                        first non-matching boundary

takeWhile(even):       [2, 4, 6]
dropWhile(even):       [7, 8, 10]
filter(even):          [2, 4, 6, 8, 10]
```

Crucially, **`takeWhile` does not search for every matching element**. It takes **a prefix**; `dropWhile` does not remove every matching element, only that **prefix**. If you simply want to “get all even numbers at any position”, use `filter()`.

## 2. What is encounter order and why does it matter?

**Encounter order** is the order in which elements are observed according to the semantics of the source and stream operations. When an encounter order exists, the concept of “from the beginning up to the first non-matching element” has a clear meaning.

Some common cases:

| How the source or pipeline is created | Ordering characteristic to remember |
| --- | --- |
| `List.of(2, 4, 6).stream()` | Has an encounter order following the order of the List elements |
| `Stream.of("a", "b", "c")` | Has an encounter order following the argument order |
| `IntStream.range(1, 6)` | Has an encounter order following the sequence `1, 2, 3, 4, 5` |
| `Stream.iterate(seed, next)` | Ordered according to the generated sequence of values |
| `HashSet.stream()` | Should not be expected to have a deterministic, meaningful encounter order |
| `source.stream().unordered()` | Removes the encounter order constraint in the pipeline, even if observed output happens to have the same order |

**Having an encounter order does not mean the data is sorted in ascending order.** For example, `List.of(2, 4, 6, 7, 8, 10)` has an order even without comparing value sizes. The stream follows the List order, rather than searching for a “best” segment in the middle.

Conversely, a source without an encounter order means the concept of “longest prefix” is no longer guaranteed. That is why this topic focuses on **ordered sources**: the prefix-taking/dropping behavior can then be predicted by inspection and tested accurately.

## 3. API signatures and execution characteristics

On `Stream<T>`, the two operations have the form:

```java
Stream<T> takeWhile(Predicate<? super T> predicate);
Stream<T> dropWhile(Predicate<? super T> predicate);
```

These are **illustrative API signatures**, not methods you need to implement yourself. The predicate receives an element `T` (or a compatible supertype) and returns `boolean`.

Example inside a method where `List` is imported:

```java
List<Integer> data = List.of(2, 4, 6, 7, 8, 10);

List<Integer> prefix = data.stream()
        .takeWhile(n -> n % 2 == 0)
        .toList();

List<Integer> suffix = data.stream()
        .dropWhile(n -> n % 2 == 0)
        .toList();
```

`prefix` is `[2, 4, 6]`, while `suffix` is `[7, 8, 10]`.

Both `takeWhile` and `dropWhile` are **stateful intermediate operations**: the result can depend on elements at other positions, specifically the position where the predicate fails for the first time. `takeWhile` is a **short-circuiting** operation; `dropWhile` is a stateful operation that may have to traverse the leading part before keeping the remainder. Calling an intermediate operation **does not necessarily traverse the source immediately**; a terminal operation such as `toList()` or `count()` triggers the pipeline according to Stream evaluation rules.

**`dropWhile` does not mean “drop only the first non-matching element”.** It drops **all contiguous matching elements from the start**, keeping the first non-matching element and everything after it.

## 4. Comparing takeWhile(), dropWhile(), and filter()

With the same source `[2, 4, 6, 7, 8, 10]` and the same predicate `n -> n % 2 == 0`:

| Method | Question | Result |
| --- | --- | --- |
| `takeWhile(even)` | How many **contiguous** even numbers are there from the start? | `[2, 4, 6]` |
| `dropWhile(even)` | After dropping the **leading contiguous** even numbers, what remains? | `[7, 8, 10]` |
| `filter(even)` | Which even numbers exist **in the entire source**? | `[2, 4, 6, 8, 10]` |
| `filter(n -> n % 2 != 0)` | Which odd numbers exist **in the entire source**? | `[7]` |

The difference becomes clear when a **non-matching** element appears before elements that **match again** later. `takeWhile` **does not pick up** `8` and `10` again; `dropWhile` **still keeps** them.

Another example:

```java
List<Integer> mixed = List.of(1, 2, 3, 0, 4);
List<Integer> firstPositive = mixed.stream()
        .takeWhile(n -> n > 0)
        .toList(); // [1, 2, 3]
List<Integer> afterFirstNonPositive = mixed.stream()
        .dropWhile(n -> n > 0)
        .toList(); // [0, 4]
```

`filter(n -> n > 0)` would produce `[1, 2, 3, 4]`, which is **not the same** as `takeWhile`.

In summary: **filter by property at any position → `filter`**; **split data at the first non-matching boundary → `takeWhile` / `dropWhile`**.

## 5. Complete Java 17 program: verifiable behavior

Create a file `OrderedTakeDropDemo.java` with the following content:

```java
import java.util.List;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class OrderedTakeDropDemo {
    public static void main(String[] args) {
        List<Integer> numbers = List.of(2, 4, 6, 7, 8, 10);
        System.out.println("takeEven=" + numbers.stream().takeWhile(n -> n % 2 == 0).toList());
        System.out.println("dropEven=" + numbers.stream().dropWhile(n -> n % 2 == 0).toList());
        System.out.println("filterEven=" + numbers.stream().filter(n -> n % 2 == 0).toList());
        System.out.println("filterOdd=" + numbers.stream().filter(n -> n % 2 != 0).toList());

        List<Integer> mixed = List.of(1, 2, 3, 0, 4);
        System.out.println("takePositive=" + mixed.stream().takeWhile(n -> n > 0).toList());
        System.out.println("dropPositive=" + mixed.stream().dropWhile(n -> n > 0).toList());
        System.out.println("filterPositive=" + mixed.stream().filter(n -> n > 0).toList());

        System.out.println("sortedTake=" +
                Stream.of(8, 2, 6, 1, 4).sorted().takeWhile(n -> n < 6).toList());
        System.out.println("sortedDrop=" +
                Stream.of(8, 2, 6, 1, 4).sorted().dropWhile(n -> n < 6).toList());

        System.out.println("rangeTake=" +
                IntStream.range(1, 10).takeWhile(n -> n < 5).boxed().toList());
        System.out.println("rangeDrop=" +
                IntStream.range(1, 10).dropWhile(n -> n < 5).boxed().toList());

        System.out.println("iterateTake=" +
                Stream.iterate(1, n -> n + 1).takeWhile(n -> n <= 5).toList());

        System.out.println("parallelTake=" +
                numbers.parallelStream().takeWhile(n -> n % 2 == 0).toList());
        System.out.println("parallelDrop=" +
                numbers.parallelStream().dropWhile(n -> n % 2 == 0).toList());

        System.out.println("noneTake=" + numbers.stream().takeWhile(n -> n < 0).toList());
        System.out.println("noneDrop=" + numbers.stream().dropWhile(n -> n < 0).toList());
        System.out.println("allDrop=" + numbers.stream().dropWhile(n -> n > 0).toList());
        System.out.println("emptyTake=" + Stream.<Integer>empty().takeWhile(n -> n > 0).toList());
    }
}
```

Compile and run with JDK 17:

```bash
javac --release 17 -encoding UTF-8 OrderedTakeDropDemo.java
java OrderedTakeDropDemo
```

Exact output:

```text
takeEven=[2, 4, 6]
dropEven=[7, 8, 10]
filterEven=[2, 4, 6, 8, 10]
filterOdd=[7]
takePositive=[1, 2, 3]
dropPositive=[0, 4]
filterPositive=[1, 2, 3, 4]
sortedTake=[1, 2, 4]
sortedDrop=[6, 8]
rangeTake=[1, 2, 3, 4]
rangeDrop=[5, 6, 7, 8, 9]
iterateTake=[1, 2, 3, 4, 5]
parallelTake=[2, 4, 6]
parallelDrop=[7, 8, 10]
noneTake=[]
noneDrop=[2, 4, 6, 7, 8, 10]
allDrop=[]
emptyTake=[]
```

Explanation of the result groups:

1. **`takeEven`/`dropEven`/`filterEven`/`filterOdd` group:** immediately shows the difference between a prefix boundary and a condition applied across the entire source.
2. **`takePositive`/`dropPositive` group:** `0` is the first stopping point for the predicate `n > 0`; `4` after it is **neither picked up again** by `takeWhile` **nor dropped** by `dropWhile`.
3. **`sortedTake`/`sortedDrop` group:** `sorted()` reorders by value before finding the prefix; the result differs from applying `takeWhile` directly to `[8, 2, 6, 1, 4]`.
4. **`rangeTake`/`rangeDrop` group:** `IntStream.range(1, 10)` is an ascending sequence with an encounter order; `boxed()` converts `IntStream` to `Stream<Integer>` to collect into a list in the example.
5. **`iterateTake`:** `Stream.iterate(1, n -> n + 1)` generates an unbounded sequence, and `takeWhile(n -> n <= 5)` extracts the finite segment `[1, 2, 3, 4, 5]`.
6. **`parallelTake`/`parallelDrop`:** `parallelStream()` from a `List` still has an encounter order; despite parallel processing, the result must respect the prefix boundary according to that order.
7. **Edge cases:** a predicate false on the very first element causes `takeWhile` to return `[]` and `dropWhile` to keep all elements. A predicate true for all elements causes `dropWhile` to return `[]`. An empty source always produces an empty result.

The program does not use `unordered()` to print results as answers, because the specific result of `takeWhile` / `dropWhile` on an unordered stream is **not guaranteed to be the prefix of the original list**.

## 6. The boundary is determined by the first non-matching element

Suppose data is ordered by time:

```text
[08:00, 08:15, 08:30, 09:10, 08:45]
                 first point not satisfying < 09:00
```

If you execute `takeWhile(t -> t.isBefore(09:00))`, only the first three timestamps are included. The `08:45` timestamp at the end is **not included**, even though it is still earlier than `09:00`, because the stopping point already occurred at `09:10`.

This matters when designing algorithms: if you want to “get **all** records before 09:00”, you can only use `takeWhile` when the data has an order guaranteeing that matching records form **a contiguous prefix**. If the time source is out of order, use `filter`, or `sorted` first and then `takeWhile` if business rules allow reordering.

A common property of predicates here is **monotonicity along the encounter order**: once the predicate becomes false, it never becomes true again for subsequent elements. When the source is sorted by the relevant key and the predicate has this property, `takeWhile` is well suited for splitting off the leading portion.

**Do not confuse encounter order with sorted order:** a `List` has a traversal order, but that does not prove the condition is monotonic. Business correctness requires checking both.

## 7. Combining sorted() with takeWhile()/dropWhile()

Example:

```java
List<Integer> values = List.of(8, 2, 6, 1, 4);

List<Integer> small = values.stream()
        .sorted()
        .takeWhile(n -> n < 6)
        .toList();

List<Integer> large = values.stream()
        .sorted()
        .dropWhile(n -> n < 6)
        .toList();
```

These are illustrative statements inside a method that has imported `java.util.List`; `small` is `[1, 2, 4]`, and `large` is `[6, 8]`. Each call to `values.stream()` creates a new stream because a pipeline can only be consumed once.

`sorted()` increases computational cost and typically requires buffering data; you should not add it automatically just to “make `takeWhile` work”. First determine whether the initial data already has the required order and whether reordering records is permitted.

When comparing strings, dates/times, or complex objects, an appropriate comparator is needed. For example, `sorted(Comparator.comparing(Event::timestamp))` is only **illustrative syntax** assuming an `Event` class, a `timestamp` method, and the corresponding `Comparator` import; it is not a standalone runnable program.

In many cases where you only want elements matching a criterion rather than requiring a prefix, `filter` avoids the sorting cost and reflects intent better.

## 8. What if the source is unordered or unordered() is called?

This is the easiest point to misunderstand when learning `takeWhile` and `dropWhile`.

**On a stream with an encounter order:** Java must respect the **longest prefix**. For example, `Stream.of(2,4,6,7,8,10)` is guaranteed to be split at `7`.

**On an unordered stream:** the Java documentation permits:

- `takeWhile(predicate)` selects **an arbitrary subset** of the elements matching the predicate, **not necessarily** all matching elements.
- `dropWhile(predicate)` **drops an arbitrary subset** of the elements matching the predicate; non-matching elements are still kept, while matching elements may be kept or dropped as a valid implementation choice.

Therefore, an example such as:

```java
List<Integer> data = List.of(2, 4, 6, 7, 8, 10);
var result = data.stream()
        .unordered()
        .takeWhile(n -> n % 2 == 0)
        .toList();
```

These are illustrative statements placed inside a method that has imported `List`. **It cannot be asserted** that `result` will definitely be `[2, 4, 6]`, or `[2, 4, 6, 8, 10]`, or any specific set based solely on the input. Results observed on one machine are not a guarantee of the API.

Nor should `unordered()` be understood as a **random shuffle** operation. It removes an ordering constraint, with no contract that elements must be rearranged. In an actual run, you may still see the same order as the input; that does not restore the guarantees of an ordered stream.

Sources like `HashSet` generally have no deterministic encounter order, so `takeWhile`/`dropWhile` are **unsuitable** if the business requirement is to split by position in a specific list. When a deterministic boundary is needed, create a source with an appropriate encounter order or sort by the business key first.

## 9. Parallel streams: still correct results, but potentially costly

For an **ordered** source, such as `List.parallelStream()`, Java must still respect the prefix when using `takeWhile` and `dropWhile`. Parallelism does not mean encounter order may be ignored.

Example from the main program:

```java
List<Integer> numbers = List.of(2, 4, 6, 7, 8, 10);
List<Integer> head = numbers.parallelStream()
        .takeWhile(n -> n % 2 == 0)
        .toList(); // [2, 4, 6]
List<Integer> tail = numbers.parallelStream()
        .dropWhile(n -> n % 2 == 0)
        .toList(); // [7, 8, 10]
```

These are illustrative statements inside a method that has imported `List`. The result is guaranteed to follow the encounter order in the example, even though internal task scheduling may vary.

This also explains a performance trade-off: on a parallel yet ordered stream, `takeWhile`/`dropWhile` may require **synchronization, buffering, or extra processing** to determine the exact prefix boundary. In some cases, sequential processing is faster.

The Javadoc suggests that if the data **does not need** an encounter order and unordered stream behavior is sufficient, removing the ordering constraint can help performance. However, **only do so when the result does not require a specific prefix boundary**; do not trade correctness for speed.

Do not rely on the predicate being called in order or exactly once per element in a parallel stream. The predicate should be **side-effect-free**, independent of shared mutable state, and safe in a parallel environment.

## 10. takeWhile() on potentially infinite sequences

A natural application of `takeWhile` is producing finite output from a potentially infinite source:

```java
List<Integer> values = Stream.iterate(1, n -> n + 1)
        .takeWhile(n -> n <= 5)
        .toList();
```

This illustrative snippet is placed inside a method that has imported `java.util.List` and `java.util.stream.Stream`; the result is `[1, 2, 3, 4, 5]`.

`Stream.iterate(1, n -> n + 1)` is ordered, generating the sequence `1, 2, 3, ...`. The predicate `n <= 5` is true for the first five elements, then false at `6`; `takeWhile` has a boundary at which to stop. This is why `takeWhile` is often suitable when you need to **take up to before a threshold**.

However:

- If the predicate is **always true** on an infinite source, `takeWhile` has no boundary to stop at; `toList()` cannot complete normally.
- If the predicate is **always true** on an infinite source, `dropWhile` also cannot reach the first non-matching element to begin emitting output data.
- If the source is infinite but the predicate soon becomes false, `dropWhile` retains a **suffix that may still be infinite**. Calling `toList()` on that suffix is still inappropriate; a bounding terminal operation or appropriate stream processing is required.

Do not assume that `takeWhile` is “always fast” or “always terminates” just because its name implies selecting a leading segment.

## 11. Value at the boundary: inclusive or exclusive?

With the ordered source `[1, 2, 3, 4, 5]` and the condition `n < 4`:

```text
takeWhile(n < 4) -> [1, 2, 3]
dropWhile(n < 4) -> [4, 5]
```

The first **non-matching** element (`4`) is **excluded from `takeWhile`** and **retained in `dropWhile`**.

This is useful when processing logs, events, or transaction histories:

- `takeWhile(event -> event.isBefore(cutoff))`: takes the contiguous leading part **before** the boundary (if the source is sorted in ascending time order).
- `dropWhile(event -> event.isBefore(cutoff))`: drops that part and keeps from the boundary onward.

If you want the result to **include** the boundary element itself in the leading segment, `takeWhile` has no built-in `inclusive` option. You need to adjust the predicate if business rules allow, or design a custom stateful partitioning operation. For instance, with an ascending sequence of numbers, using `n -> n <= 4` will include `4`, but this approach only works when the boundary criterion is a comparison that permits such an adjustment.

Do not write a **mutable stateful** predicate just to mark “a failing element has been seen” in a parallel stream, as it is unsafe and makes the code harder to understand.

## 12. Are takeWhile and dropWhile two complementary halves?

For **the same sequence with an encounter order** and the same pure predicate, `takeWhile` and `dropWhile` can be viewed as two parts split at **the same boundary position**:

```text
original = prefix + suffix
prefix = takeWhile(predicate)
suffix = dropWhile(predicate)
```

This identity expresses the **content in encounter order** of the two results; it does not mean you are allowed to **call two terminal operations on the same Stream object**.

Wrong:

```text
Stream<Integer> once = Stream.of(1, 2, 3, 4);
var prefix = once.takeWhile(n -> n < 3).toList();
var suffix = once.dropWhile(n -> n < 3).toList(); // Wrong: reuse
```

This is an **intentionally invalid counterexample about Stream lifecycle** that may compile but violates the Stream contract. Fix it by **creating two independent streams from the same source**:

```java
List<Integer> data = List.of(1, 2, 3, 4);
List<Integer> prefix = data.stream()
        .takeWhile(n -> n < 3).toList();
List<Integer> suffix = data.stream()
        .dropWhile(n -> n < 3).toList();
```

These statements are placed inside a method with `List` imported. The results are `prefix = [1, 2]`, `suffix = [3, 4]`, and concatenating them in order reconstructs the source sequence.

For large, expensive, or single-read sources (files, network cursors), splitting without re-reading may require a different algorithm or deliberately **materializing** the results. Do not assume an already-used stream can be reset.

## 13. Edge cases to know

With the ordered source `[2, 4, 6, 7]`:

| Scenario | `takeWhile` | `dropWhile` |
| --- | --- | --- |
| Predicate false on the first element (`n < 0`) | `[]` | `[2, 4, 6, 7]` |
| Predicate true for all elements (`n > 0`) | `[2, 4, 6, 7]` | `[]` |
| False at the fourth element (`n % 2 == 0`) | `[2, 4, 6]` | `[7]` |
| Empty source | `[]` | `[]` |

Neither operation returns `null` when there are no elements; when collected with `toList()`, the result can be an empty list.

**Do not put required logic into a predicate with side effects.** When optimizing a pipeline, predicate evaluation may not match the intuition of “called once per element in order”, especially under parallel execution. Use a **stateless** and **non-interfering** predicate (one that does not modify the data source being traversed).

If the predicate throws an unchecked exception, the pipeline may terminate with that exception instead of returning a list. `takeWhile` and `dropWhile` do not catch errors, convert them to default values, or skip failing elements.

## 14. Performance and choosing the right API for the goal

A sound design principle is to express the **data intent** accurately before optimizing:

- **Take the contiguous leading elements matching a condition in encounter order:** `takeWhile`.
- **Drop the contiguous leading elements matching a condition and process the remainder:** `dropWhile`.
- **Filter all elements matching a condition at any position:** `filter`.
- **Take the first N elements regardless of value:** `limit(N)`.
- **Skip the first N elements regardless of value:** `skip(N)`.
- **Need a value-based boundary but the source is not appropriately sorted:** consider `sorted(...)` first, or use `filter` depending on requirements.

`takeWhile` can avoid traversing an entire sequential source if the predicate fails early; however, actual cost still depends on the source, pipeline, terminal operation, execution strategy, and whether the stream is ordered or parallel. `dropWhile` must find the first boundary before keeping the remainder, so it is not inherently cheaper than `filter`.

In particular, calling `sorted()` before `takeWhile` has a cost and can alter semantics when users care about the **original order** of logs, transactions, or events. Only apply it when the sorted order matches the goal.

If no prefix guarantee is needed, you can use a simpler operation with fewer ordering constraints; do not use `unordered()` as a default optimization trick.

## 15. Common mistakes

| Misconception or mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| `takeWhile` is the same as `filter` | `takeWhile` stops taking once the prefix hits the first failing element | Use `filter` if you want all matching elements |
| `dropWhile` is the same as `filter(predicate.negate())` | `dropWhile` keeps matching elements that appear after the boundary | Use `filter` if you want to remove all matching elements |
| A stream from a `List` is always sorted by value | Encounter order is different from sorted order | Use `sorted` when business logic requires sorting |
| `takeWhile` always gets all matching elements on an unordered stream | There is no prefix guarantee on an unordered stream | Preserve encounter order or switch to `filter` |
| Calling `unordered()` to “shuffle” data | `unordered()` only removes the order constraint, not a shuffle | Use a proper shuffling algorithm if actually needed |
| The predicate is always called once per element in order | The pipeline may short-circuit, optimize, or run in parallel | Use a side-effect-free predicate |
| `takeWhile` automatically includes the first non-matching element | That element itself marks the end of the prefix | Use a different criterion if an inclusive boundary is needed |
| `dropWhile` also drops matching elements that appear after the boundary | It only drops the prefix, not filtering the entire stream | Use `filter` if filtering at all positions is needed |
| Running both `takeWhile(...).toList()` and `dropWhile(...).toList()` on the same `Stream` | A stream is single-use | Create two streams from the source or design a single-pass approach |
| An infinite source + always-true predicate can still `toList()` quickly | There is no finite boundary | Choose a predicate with a stopping point or bound the data |
| Switching a parallel stream to unordered while still expecting a fixed prefix | Removing encounter order loses the prefix constraint | Keep it ordered when the result depends on order |
| Adding `sorted` unconditionally to “fix” `takeWhile` | Changes source semantics and adds overhead | Re-check the data meaning and condition first |

## 16. Self-check and answers

**Exercise 1 — Boundary.** Given source `[1, 3, 5, 2, 7]` and predicate `n -> n % 2 == 1`, give the results of `takeWhile`, `dropWhile`, and `filter`.

Answer: `takeWhile` → `[1, 3, 5]`; `dropWhile` → `[2, 7]`; `filter` → `[1, 3, 5, 7]`.

**Exercise 2 — First non-matching point.** Given `List.of(2, 4, 6, 7, 8, 10)`, why does `dropWhile(n -> n % 2 == 0)` still keep `8` and `10`?

Answer: because `7` already ended the **contiguous even prefix**; `dropWhile` keeps the entire suffix starting from `7`, regardless of even elements in the suffix.

**Exercise 3 — Sorting.** Given source `[8, 2, 6, 1, 4]`, what is the result of `stream().sorted().takeWhile(n -> n < 6)`?

Answer: `sorted()` produces the order `[1, 2, 4, 6, 8]`; the prefix matching `n < 6` is `[1, 2, 4]`.

**Exercise 4 — Short circuit.** With `IntStream.range(1, 10).takeWhile(n -> n < 5).boxed().toList()`, what is the result? Does `5` appear?

Answer: `[1, 2, 3, 4]`. `5` is the first element that does **not** match, so it is excluded from the result.

**Exercise 5 — Unordered.** Can you assert that `Stream.of(1, 2, 3, 4).unordered().takeWhile(n -> n < 3)` will always return `[1, 2]`?

Answer: **No**. Removing the encounter order means the API no longer guarantees taking the prefix in the original order; the result can be any valid subset of the matching elements.

**Exercise 6 — Choosing an API.** To get **all** elements with `score >= 80` from an unsorted list, which operation should you use?

Answer: `filter(score -> score >= 80)`, because the requirement is not limited to a prefix. `takeWhile` could miss valid elements appearing after an element with `score < 80`.

**Exercise 7 — Two parts of the same source.** A stream has already been used for `takeWhile(...).toList()`. Can you then call `dropWhile` on **the same stream object**?

Answer: **No**. Each stream is consumed once. Call `list.stream()` twice or use a single-pass splitting algorithm depending on the requirement.

## 17. Key takeaways

1. For a source **with an encounter order**, `takeWhile(P)` takes the **longest contiguous prefix** matching `P`.
2. `dropWhile(P)` **drops that exact prefix**, then keeps the entire suffix from the first non-matching element onward.
3. `filter(P)` differs because it inspects **every element** in the source, not just the prefix.
4. **Encounter order is not synonymous with sorted order**; if business logic requires a value-based threshold, ensure the input order is appropriate.
5. On an unordered stream, do not assume a deterministic prefix; `unordered()` is also not a shuffle.
6. On an ordered parallel stream, the result must still respect the prefix boundary, though it may incur higher overhead.
7. `takeWhile` can terminate an infinite sequence when the predicate becomes false; it does not automatically guarantee that every pipeline on an infinite source terminates.
8. To obtain both prefix and suffix for independent processing, **create a new stream for each pipeline** rather than reusing the same `Stream`.

Official documentation: [Java SE 17 Stream.takeWhile/dropWhile](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#takeWhile(java.util.function.Predicate)), [Stream.dropWhile](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#dropWhile(java.util.function.Predicate)), [IntStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/IntStream.html).