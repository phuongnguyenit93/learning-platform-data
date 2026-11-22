# Stability of `sorted()` on Ordered Streams in Java

## 1. Lesson Objectives

In the Java Stream API, `sorted()` is an **intermediate operation** for sorting elements. However, saying “sort in ascending order” is not enough: when multiple elements are evaluated as **equal** by the comparator, is their original order preserved?

That is the question of **sorting stability (stable sorting)**. The Javadoc of `Stream.sorted()` and `Stream.sorted(Comparator)` states clearly:

> For **ordered Streams**, the sort is guaranteed to be stable. For **unordered Streams**, no stability guarantee is made.

This lesson focuses on the exact meaning and limits of this guarantee. After completing it, you will be able to:

- Distinguish a Stream's **encounter order** from the order produced by a comparator.
- Define stability based on `compare(a,b) == 0`, without confusing it with `equals()`.
- Predict the order of elements with equal sort keys on an ordered Stream.
- Understand the difference between `List.stream()`, unordered sources like `HashSet`, and calling `unordered()`.
- Explain why `parallelStream().sorted(...)` is still guaranteed to be stable if the source has an encounter order, yet `forEach(...)` may observe a different order.
- Use `thenComparing(...)` when business requirements call for an **explicit secondary order**, instead of relying on the original order.
- Avoid invalid comparators, integer subtraction that causes overflow, applying `sorted`/`limit` in the wrong order, and reusing an already consumed Stream.
- Run a complete Java 17 demonstration program and verify the exact stdout.

**Scope:** stability of `sorted()` on reference Streams in Java, with some related notes on comparators, sources, and terminal operations for proper application.

## 2. Two Concepts to Keep Separate

### 2.1. What is Encounter Order?

**Encounter order** is the order of elements that an ordered pipeline receives from its source and maintains through order-preserving operations. For a `List`, the encounter order is usually the order of elements in the list:

~~~java
List<String> names = List.of("Mai", "An", "Binh");
List<String> original = names.stream().toList();
System.out.println(original); // [Mai, An, Binh]
~~~

The snippet above is a **method-level code fragment** with `java.util.List` imported. `List.stream()` provides an ordered Stream. Other sources such as `Stream.of(...)` also have a clear encounter order.

Not every Stream source is ordered. Some sources such as `HashSet` do not promise an encounter order; `unordered()` can also remove ordering constraints from a pipeline. You must not assume that observing a specific order in a single run means the source provides a corresponding ordering guarantee.

### 2.2. What is Sort Order?

`sorted()` produces an order according to **natural ordering** (typically `Comparable`). `sorted(comparator)` produces an order according to the **Comparator** provided by the caller. For example:

~~~java
List<Integer> numbers = List.of(5, 2, 4, 1, 3);
List<Integer> sorted = numbers.stream().sorted().toList();
System.out.println(sorted); // [1, 2, 3, 4, 5]
~~~

Elements are placed in order by value; this order differs from the list's original encounter order.

However, if multiple elements are considered **equal according to the comparator**, the comparator does not provide enough information to distinguish their relative order. For an ordered Stream, `sorted` must preserve the **original encounter order among those equal elements**.

### 2.3. Stability Does Not Mean Every Element Keeps Its Position

Suppose items have priorities `2, 1, 2, 1`. After sorting in ascending order of priority, the items with priority `1` move ahead of those with priority `2`. A stable sort only requires **two items with the same priority** to keep their relative order, not that every item keeps its absolute position.

## 3. Definition of Stable Sorting

Given an input sequence with an encounter order:

~~~text
Element:   A   B   C   D   E
Key:       2   1   2   1   2
Position:  0   1   2   3   4
~~~

Sorting in ascending order by key in a **stable** manner yields:

~~~text
B(1)  D(1)  A(2)  C(2)  E(2)
~~~

Elements with equal keys preserve their relative order:

- Key group `1`: `B` appears before `D` in the input, so it remains `B, D` after sorting.
- Key group `2`: `A` appears before `C`, then `E` in the input, so it remains `A, C, E` after sorting.

More precisely: if two elements `x` and `y` appear in an ordered Stream, `x` precedes `y` in encounter order, and the comparator returns `compare(x,y) == 0`, then a stable `sorted(comparator)` keeps `x` before `y` in the result.

**Do not confuse “equal” here with `equals()`.** Two objects can have different IDs, different payloads, and even `equals()` returning `false`, yet the comparator compares only one key and returns `0`. In that case, they are considered to be in the same key group **for sorting purposes**, and stability applies.

## 4. Two Overloads of `sorted()`

### 4.1. `sorted()` Using Natural Ordering

~~~java
Stream<T> sorted();
~~~

This is an **abstract API signature**, not a standalone Java snippet to declare inside a method. For a Stream of `String`, `Integer`, or objects implementing `Comparable` appropriately, you can write:

~~~java
List<String> words = List.of("pear", "apple", "banana");
List<String> sorted = words.stream().sorted().toList();

System.out.println(sorted); // [apple, banana, pear]
~~~

If there is no compatible natural ordering, sorting may fail with a `ClassCastException` at runtime. For domain objects without `Comparable`, use `sorted(Comparator)` to express the key and sorting rule instead of relying on a cast.

### 4.2. `sorted(Comparator<? super T>)` Using a Comparator

~~~java
Stream<T> sorted(Comparator<? super T> comparator);
~~~

This is also an **API signature**, expressing how to supply a comparator. For example:

~~~java
List<String> words = List.of("bb", "a", "cc", "b", "ddd", "ee");
List<String> byLength = words.stream()
        .sorted(Comparator.comparingInt(String::length))
        .toList();

System.out.println(byLength); // [a, b, bb, cc, ee, ddd]
~~~

This is a method-level code fragment with `java.util.List` and `java.util.Comparator` imported. The strings `"a"` and `"b"` have length `1`, so they preserve the order `a, b`. The strings `"bb"`, `"cc"`, `"ee"` all have length `2`, so they remain in the order `bb, cc, ee`.

If a comparator is built solely to compare length, it **does not distinguish the contents of strings of the same length**. Stability preserves the encounter order within each equal-length group, rather than arbitrarily shuffling the group.

### 4.3. Stability is a Guarantee of `sorted`, Not Dependent on Choosing a Specific Algorithm

The Javadoc specifies the behavior without requiring users to know which internal sorting algorithm the JVM uses. Avoid tying the “stability” condition to a particular algorithm or drawing conclusions from an implementation observed in a single JDK version.

## 5. Record Example: Comparing Keys, Preserving Order on Ties

Suppose we have tickets, each with a code and a priority:

~~~text
Encounter order:
C(2), B(1), A(2), D(1), F(3), E(2)
~~~

We compare only by `priority`. After `sorted(comparingInt(Ticket::priority))`, the result according to the stability contract is:

~~~text
B(1), D(1), C(2), A(2), E(2), F(3)
~~~

In the `priority` `2` group, code `C` still comes before `A` and `E`, even though alphabetical order would be `A, C, E`. This is a classic case to test understanding: **without a tie-breaker, the source order determines the order of elements whose comparator returns 0** on an ordered Stream.

A concise and safe comparator:

~~~java
Comparator<Ticket> byPriority =
        Comparator.comparingInt(Ticket::priority);
~~~

This snippet is placed inside a class that already has `record Ticket(String code, int priority)` and imports `java.util.Comparator`. `Comparator.comparingInt` avoids unnecessary boxing for integer keys and avoids writing risky subtraction by hand.

## 6. Complete Java 17 Program

Create the file **`StableSortedDemo.java`**:

~~~java
import java.util.Comparator;
import java.util.List;

public class StableSortedDemo {

    record Ticket(String code, int priority) {}

    public static void main(String[] args) {
        List<Ticket> input = List.of(
                new Ticket("C", 2),
                new Ticket("B", 1),
                new Ticket("A", 2),
                new Ticket("D", 1),
                new Ticket("F", 3),
                new Ticket("E", 2)
        );

        Comparator<Ticket> byPriority =
                Comparator.comparingInt(Ticket::priority);

        List<String> encounter = input.stream()
                .map(Ticket::code)
                .toList();

        // List.stream() has an encounter order.
        List<String> stable = input.stream()
                .sorted(byPriority)
                .map(Ticket::code)
                .toList();

        // The source remains ordered even when the pipeline runs in parallel.
        List<String> stableParallel = input.parallelStream()
                .sorted(byPriority)
                .map(Ticket::code)
                .toList();

        // Add a secondary key: the order within a priority group may change.
        List<String> withTieBreak = input.stream()
                .sorted(byPriority.thenComparing(Ticket::code))
                .map(Ticket::code)
                .toList();

        System.out.println("source=" + encounter);
        System.out.println("stable=" + stable);
        System.out.println("parallel=" + stableParallel);
        System.out.println("tie-break=" + withTieBreak);
        System.out.println("same=" + stable.equals(stableParallel));
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac -encoding UTF-8 StableSortedDemo.java
java StableSortedDemo
~~~

**Exact stdout:**

~~~text
source=[C, B, A, D, F, E]
stable=[B, D, C, A, E, F]
parallel=[B, D, C, A, E, F]
tie-break=[B, D, A, C, E, F]
same=true
~~~

### Why Does This Result Occur?

1. `source` reflects the encounter order of the `List`: `C, B, A, D, F, E`.
2. `stable` sorts in ascending order of `priority`. The `priority = 1` group is `B, D`, the `priority = 2` group is `C, A, E`, and the `priority = 3` group has only `F`.
3. `parallel` produces the same result because **`sorted` on an ordered Stream is guaranteed to be stable** even when the pipeline runs in parallel. `toList()` collects elements according to the encounter order of the ordered pipeline.
4. `tie-break` uses `thenComparing(Ticket::code)`. Within a group of the same `priority`, the comparator now distinguishes elements by `code`; `A` comes before `C`. The change is **due to the new sorting rule**, not because `sorted` lost stability.
5. `same=true` shows that the two results in the test program are equal; the reason for the general guarantee is the Javadoc contract, not just a lucky run.

## 7. A Comparator Returning 0 Does Not Mean Two Objects Are `equals`

Consider two records:

~~~java
record Person(String id, int age) {}

Person a = new Person("p-1", 20);
Person b = new Person("p-2", 20);

Comparator<Person> byAge = Comparator.comparingInt(Person::age);

System.out.println(byAge.compare(a, b)); // 0
System.out.println(a.equals(b));         // false
~~~

This is a method-level code fragment with `Comparator` imported and the record declared appropriately. `a` and `b` are not equal according to `equals()` because their `id`s differ, yet the comparator `byAge` compares only age and returns `0`. Therefore, the two people belong to a “tie” group in the sort and will preserve their original encounter order when using an ordered Stream.

**Stability is evaluated by the comparator, not by `equals`.** Do not assume `sorted` removes elements with duplicate keys: `sorted` only sorts; it does not perform `distinct` automatically. To deduplicate, you must define what counts as a duplicate and use the appropriate operation.

Additional note: a comparator does not have to be consistent with `equals` to be used with `sorted` on a Stream, whereas when used as the ordering rule of a `TreeSet`/`TreeMap`, the `compare == 0` relation strongly affects how elements/keys are distinguished; that is a separate contract to examine on its own.

## 8. Ordered Stream: The Condition for a Stability Guarantee

### 8.1. Sources That Typically Have an Encounter Order

| Source | Encounter order characteristic |
| --- | --- |
| `List.stream()` | Follows the order of elements in the List |
| `Stream.of(a,b,c)` | Follows the order of the supplied elements |
| `Arrays.stream(array)` | Follows the index order in the array |
| `IntStream.range(...)` | Follows the integer order of the range |
| `LinkedHashSet.stream()` | Follows the iteration order defined by the collection |
| `HashSet.stream()` | No guaranteed encounter order |
| `unordered()` called on a pipeline | Removes the pipeline's ordering guarantee, even if the original source was ordered |

This table describes **common sources/transformations**; it does not mean every intermediate operation preserves those characteristics. For complex pipelines, you must determine ordering from the source and the operations preceding `sorted`.

### 8.2. How Is the Guarantee of `sorted` Stated?

For a Stream with an encounter order, `sorted` is guaranteed to be stable. If the input has no encounter order, `sorted` still sorts by value/Comparator, but **makes no promise about the relative order of elements compared as equal**.

One way to illustrate this:

~~~text
ORDERED source
     |
     v
sorted(comparator)
     |
     +--> Elements with different keys according to the comparator are sorted in the right order
     |
     +--> Elements with compare == 0 preserve the relative order of the source

UNORDERED source
     |
     v
sorted(comparator)
     |
     +--> Elements with different keys are still sorted in the right order
     |
     +--> Elements with compare == 0 have NO stability guarantee
~~~

A subtle point: calling `sorted(comparator)` on an unordered source may still produce output that looks stable when run in the current environment. **Do not rely on an incidental observed result** to infer a stability contract.

## 9. `unordered()` Is Not a Random Shuffle Command

~~~java
List<String> input = List.of("bb", "a", "cc", "b");

List<String> result = input.stream()
        .unordered()
        .sorted(Comparator.comparingInt(String::length))
        .toList();
~~~

The snippet above is a method-level code fragment. `unordered()` only **removes the requirement to preserve encounter order** in the pipeline; it does not require reversing, shuffling, or randomizing elements. Thus, in a given run, strings of the same length may still appear in their original order.

However, after `unordered()`, there is no longer a stability guarantee for `sorted` on equal-key groups. If a guarantee is needed, do not drop the ordered characteristic before sorting, or specify an explicit tie-breaker.

### 9.1. `HashSet` and UnGuaranteed Ordering

~~~java
Set<String> source = new HashSet<>(List.of("bb", "cc", "a", "b"));

List<String> result = source.stream()
        .sorted(Comparator.comparingInt(String::length))
        .toList();
~~~

This illustrative snippet requires importing `Set`, `HashSet`, `List`, and `Comparator`. Sorting by length still puts the one-character group before the two-character group. However, the order between `"a"` and `"b"`, or `"bb"` and `"cc"`, **is not guaranteed** according to any fixed “original order” from the `HashSet` source.

Do not record a specific stdout like `[a,b,bb,cc]` for this snippet and claim it will always hold: neither the code nor the Javadoc promises such a tie order.

### 9.2. When You Want Completely Deterministic Output

Instead of hoping for a particular initial iteration order from an unordered source, add a secondary key:

~~~java
Comparator<String> byLengthThenText =
        Comparator.comparingInt(String::length)
                  .thenComparing(Comparator.naturalOrder());

List<String> result = source.stream()
        .sorted(byLengthThenText)
        .toList();
~~~

If all elements are non-`null` strings, this comparator compares length first and breaks ties lexicographically. As a result, the output has a clear ordering rule regardless of the order in which the `HashSet` source is traversed. `thenComparing` does not make sorting “more stable” by definition: it changes the comparison relation to reduce or eliminate unresolved `compare == 0` cases.

## 10. `parallelStream()` and Stability

### 10.1. Parallel Does Not Mean Losing Encounter Order

~~~java
List<Ticket> ordered = List.of(
        new Ticket("x", 2),
        new Ticket("y", 1),
        new Ticket("z", 2)
);

List<Ticket> output = ordered.parallelStream()
        .sorted(Comparator.comparingInt(Ticket::priority))
        .toList();
~~~

This is an example fragment inside a class that has `record Ticket`. `List.parallelStream()` is still an **ordered Stream**. Even though the sort is executed in parallel, `sorted` must preserve the relative order of `x` before `z` when both tickets have the same `priority = 2`.

The stability guarantee comes from the ordered characteristic and the `sorted` contract; it does not depend on whether the pipeline is evaluated on one or multiple threads.

### 10.2. Why Can `parallel().forEach(...)` Make You Think the Sort Is Unstable?

Consider:

~~~java
input.parallelStream()
        .sorted(byPriority)
        .forEach(ticket -> System.out.println(ticket.code()));
~~~

**Do not predict the stdout order for this snippet.** `forEach` on a parallel Stream does not guarantee executing the action in encounter order. Even though `sorted` produces the right order in the pipeline, the console-printing side effects may appear according to thread scheduling.

If the goal is to verify the sort order, use a terminal operation that preserves encounter order:

~~~java
List<String> codes = input.parallelStream()
        .sorted(byPriority)
        .map(Ticket::code)
        .toList();
System.out.println(codes);
~~~

Or if you need to execute an action in encounter order:

~~~java
input.parallelStream()
        .sorted(byPriority)
        .forEachOrdered(ticket -> System.out.println(ticket.code()));
~~~

`forEachOrdered` enforces an ordering requirement on the action; it is not a way to make arbitrary side effects thread-safe, and the ordering requirement may limit parallel performance. For testing data order, **collecting into a List and comparing** is usually simpler than reading logs from multiple threads.

### 10.3. `toList()` Preserves Result Order Consistent with Encounter Order

`Stream.toList()` in Java 17 returns an **unmodifiable** list containing the Stream's elements in encounter order, if one exists. That is why the program example in Section 6 can compare outputs from sequential and parallel pipelines. This is a direct check of contents and order, without introducing side effects into the pipeline.

## 11. Tie-Breaker: When Do You Need a Secondary Order?

### 11.1. Preserving Original Order on Ties Is a Valid Business Requirement

If ticket data is already ordered by intake sequence and you only want to group by priority levels, **stable sorting by priority** is very useful: within each priority group, an earlier-arriving ticket stays ahead of later ones.

~~~java
Comparator<Ticket> byPriority =
        Comparator.comparingInt(Ticket::priority);

List<Ticket> sorted = input.stream()
        .sorted(byPriority)
        .toList();
~~~

The `input` data here is an ordered `List<Ticket>`. Do not add a secondary key if the main requirement is to **preserve intake order** among items of equal priority.

### 11.2. To Make the Result's Secondary Order Independent of the Source, Add `thenComparing`

If the requirement is “ascending priority, and for equal priority, ascending ticket code”:

~~~java
Comparator<Ticket> byPriorityThenCode =
        Comparator.comparingInt(Ticket::priority)
                  .thenComparing(Ticket::code);

List<Ticket> sorted = input.stream()
        .sorted(byPriorityThenCode)
        .toList();
~~~

Now the comparator no longer returns 0 for `Ticket("C",2)` and `Ticket("A",2)`, because their `code`s differ; `A` comes before `C`. This does not violate stability: **the sort key has changed**.

If two tickets have the same priority and the same code yet are still distinct objects, they remain a tie under the comparator above; for an ordered Stream, the source order still governs that pair. For a completely deterministic sort, add only tie-breaker keys that are genuinely meaningful and sufficient to distinguish objects within the scope of the requirements.

### 11.3. Do Not Use Artificial Secondary Orders

Creating a secondary key using `System.identityHashCode`, randomness, current time, or mutable state can produce unpredictable ordering and violate business intent. If a stable ID is needed, use a domain ID with a clear contract. If data arrival order is needed, preserve encounter order and use stable sorting properly.

## 12. A Valid Comparator Is Mandatory

### 12.1. Avoid Subtraction as an Integer Comparator

Commonly seen but risky code:

~~~java
Comparator<Ticket> risky =
        (a, b) -> a.priority() - b.priority();
~~~

When two values are near the `Integer.MIN_VALUE` and `Integer.MAX_VALUE` bounds, subtraction can overflow, producing the wrong comparison sign and violating the comparator contract. Fix it with:

~~~java
Comparator<Ticket> safe =
        Comparator.comparingInt(Ticket::priority);
~~~

Or `(a,b) -> Integer.compare(a.priority(), b.priority())`. The stability of `sorted` **cannot fix a broken comparator**.

### 12.2. A Comparator Must Satisfy the Comparison Contract

Core conditions include antisymmetry of sign, transitivity, and consistency in identifying “compares equal” equivalence classes. If a comparator depends on state mutated while the pipeline runs, uses randomness, or yields a non-transitive relation, results may be wrong or sorting may throw `IllegalArgumentException` in cases where the implementation detects a contract violation.

Example of what not to do:

~~~java
Comparator<Ticket> inconsistent =
        (a, b) -> new java.util.Random().nextBoolean() ? 1 : -1;
~~~

This snippet is an **anti-pattern example**, not a valid comparator. The same pair may be compared differently across invocations. Do not test stability with such a comparator.

### 12.3. `null` and Comparison

`Comparator.comparingInt(Ticket::priority)` requires ticket objects to be non-`null`; if the Stream contains `null`, calling the getter will fail. For data that may be `null`, define an explicit policy:

~~~java
Comparator<Ticket> nullSafe =
        Comparator.nullsLast(
                Comparator.comparingInt(Ticket::priority));
~~~

If `priority` itself were a nullable object, you would also need a null-handling comparator **for the key**, not just for the ticket. With the `int` key of the record in this lesson, only the case of a null Ticket object needs to be considered.

### 12.4. `sorted` Does Not Guarantee Preserving Elements “by equals”

`sorted` does not deduplicate, does not modify keys, and does not sanitize data. Two elements with the same comparator key are both kept. If deduplication is required, you must choose the duplicate criterion and a different operation; `distinct()` uses `equals`, which is not synonymous with a comparator returning 0.

## 13. `sorted()` Is a Stateful Intermediate Operation

### 13.1. It Does Not Necessarily Run When Merely Building the Pipeline

~~~java
Stream<Ticket> pipeline = input.stream()
        .sorted(byPriority);
~~~

This is a fragment with `input`/`byPriority` already defined. `sorted` is a **stateful intermediate operation**. A Stream pipeline is generally lazy: merely creating `pipeline` does not mean all elements have been traversed and sorted immediately.

A terminal operation such as `toList()`, `count()`, or `forEach(...)` triggers the evaluation required by the API semantics. Note that Streams may optimize certain pipelines when full execution of all steps is unnecessary; therefore, do not put business side effects inside a comparator and expect it to be invoked a specific number of times.

### 13.2. Sorting Typically Must Examine the Entire Source

To emit the smallest element under a general comparator, `sorted` usually needs to inspect and buffer many or all elements before producing results. For very large sources, `sorted` can require significant memory and time. An infinite Stream that needs full sorting before emitting results may never complete.

On an ordered parallel Stream, the stability guarantee can also make sorting and order preservation expensive. Do not assume adding `parallel()` always makes a program faster; benchmark on real workloads when performance is a goal.

### 13.3. The Order Between `sorted` and `limit` Matters

Compare:

~~~java
List<Integer> values = List.of(9, 1, 7, 2, 5);

List<Integer> smallestTwo = values.stream()
        .sorted()
        .limit(2)
        .toList();

List<Integer> firstTwoSorted = values.stream()
        .limit(2)
        .sorted()
        .toList();

System.out.println(smallestTwo);     // [1, 2]
System.out.println(firstTwoSorted);  // [1, 9]
~~~

The two pipelines have different meanings:

- `sorted().limit(2)` selects the 2 smallest elements from the entire source.
- `limit(2).sorted()` selects only the first two elements in encounter order and then sorts those two elements.

The difference in which set of elements is processed is usually more important than the question of stability. When applying stateful or short-circuiting operations, order the operations according to the business goal.

### 13.4. An Already Consumed Stream Cannot Be Reused

~~~java
Stream<Integer> s = Stream.of(3, 1, 2);
List<Integer> first = s.sorted().toList();
// s.sorted().toList(); // Invalid with respect to the Stream lifecycle.
~~~

The snippet above is an example: once a pipeline has been consumed, the same Stream cannot be reused. Create a new Stream from the collection or original data if you need to sort again with a different comparator.

## 14. Distinguishing “Stable”, “Deterministic”, and “Preserving Encounter Order”

These three concepts are related but not identical:

| Concept | Question | Example |
| --- | --- | --- |
| **Stability** | Do pairs with `compare == 0` preserve their relative order? | `C(2)` before `A(2)` after a stable sort |
| **Determinism** | Under the same conditions/contract, is the output predictable? | With tie-breaker `priority` then `code` |
| **Encounter order** | What element order did the Stream have before sorting? | `List.stream()` following the list order |

On an ordered Stream, `sorted` is stable, yet the complete result still depends on encounter order and the comparator. If the source is an unordered `HashSet` and you want results ordered alphabetically within each key group, a tie-breaker is needed. If you use `parallel().forEach`, printing actions may still occur out of order even though the data was sorted.

**Good testing practice:** compare the resulting `List` against the expected `List` using `assertEquals` (when using a test library) or `List.equals`; this compares elements in order. Do not rely on a few lines of parallel `println` output to conclude that the sort reversed ties.

## 15. Practice Exercises

### Exercise 1 — Checking Ties by Length

Given `List<String> words = List.of("ab", "z", "cd", "x", "efg", "y");`. Sort by `String::length` on an ordered Stream. Write the expected result and explain why the length-1 group keeps the order `z, x, y` while the length-2 group keeps `ab, cd`.

**Guided answer:**

~~~text
[z, x, y, ab, cd, efg]
~~~

### Exercise 2 — Record Type with Different IDs, Same Key

Define `record Order(String id, int priority) {}` with data `("C",2),("B",1),("A",2),("D",1)`. Sort by priority using `Comparator.comparingInt(Order::priority)`; predict `[B, D, C, A]` when extracting only `id`. Compare with `thenComparing(Order::id)`.

### Exercise 3 — Parallel Yet Still Stable

Use the same ordered `List<Order>`. Compare:

~~~java
List<Order> sequential = orders.stream()
        .sorted(comparator).toList();
List<Order> parallel = orders.parallelStream()
        .sorted(comparator).toList();

System.out.println(sequential.equals(parallel));
~~~

Expect `true` if `comparator` obeys the contract, the data is unchanged, both pipelines are ordered, and no side effects affect the result. Explain why you should not replace this List check with checking the order of `parallelStream().forEach(System.out::println)`.

### Exercise 4 — Dropping the Encounter Order Guarantee

Create a `List<String>`, call `stream().unordered().sorted(comparingInt(String::length))`. Explain **what is still guaranteed** (sorting by length) and **what is not guaranteed** (original tie order). Why is a single run matching the stable result not enough to draw a conclusion?

### Exercise 5 — Comparator with a Tie-Breaker

Create a `List<Ticket>` with two tickets having the same `priority` but different codes. Write a comparator that compares only priority, then a comparator for `priority` + `code`. Compare the two results and point out that the change in order within the group is due to **the new comparator**, not a loss of stability.

### Exercise 6 — Overflow Bug in a Comparator

Try comparing `Integer.MIN_VALUE` and `Integer.MAX_VALUE` using subtraction and then using `Integer.compare`. Observe the sign of the result and explain why using `Comparator.comparingInt` is safer. Do not use the broken comparator in an actual sort.

### Exercise 7 — `sorted()` Combined with `limit()`

For `[9,1,7,2,5]`, compute `sorted().limit(2)` and `limit(2).sorted()`. Explain the difference in element selection. Try with a list containing multiple equal elements to evaluate the stable result when the pipeline preserves encounter order.

### Exercise 8 — Unordered Source

Use a `HashSet` containing strings of equal length and a comparator that compares only length. Do not write a test demanding a specific tie order. Then add `thenComparing(Comparator.naturalOrder())` to produce deterministic lexicographical output, and write a test comparing against the exact expected List.

## 16. Self-Check Questions

**1. When is `Stream.sorted()` stable?** When the input Stream has an encounter order according to the API contract.

**2. What about an unordered Stream?** Sorting still follows the comparator/natural ordering, but there is no guarantee about the relative order of elements evaluated as equal by the comparator.

**3. Is “equal” in stability `equals()` or `compare == 0`?** It is the comparator comparison returning 0 (or natural comparison for the no-comparator overload).

**4. Does `sorted()` remove records with duplicate keys?** No, it sorts; it does not remove elements automatically.

**5. Does `List.parallelStream().sorted(...)` lose stability?** No; an ordered Stream is still guaranteed to be stable even when processed in parallel.

**6. Why can the output of `parallelStream().sorted(...).forEach(...)` print out of order?** `forEach` does not guarantee executing actions in encounter order on a parallel Stream.

**7. Does `unordered()` randomly shuffle elements?** No; it removes the encounter order constraint, not perform a shuffle.

**8. When should `thenComparing` be used?** When business requirements call for an explicit secondary order, especially when deterministic output independent of source order is desired.

**9. Why should `a-b` not be used in an `int` comparator?** It can overflow and produce the wrong comparison sign.

**10. Is `sorted` intermediate or terminal?** It is a stateful intermediate operation; a terminal operation at the end triggers the necessary evaluation.

**11. Is `sorted().limit(n)` the same as `limit(n).sorted()`?** No; the order of operations determines which set of elements is selected.

**12. Can you rely on the order observed from a `HashSet` in a single run to claim stability?** No, because the source does not guarantee an encounter order.

## 17. Summary

**`sorted()` in Java guarantees a stable sort on ordered Streams.** This means elements whose comparison result is 0 preserve their relative order according to the original encounter order. It does not mean keeping the absolute position of every element, does not require `equals()` to return true, and does not automatically remove elements with duplicate keys.

For unordered Streams, sorting still obeys the comparator but **does not guarantee tie order**. Use `thenComparing` when a deterministic secondary order is needed; do not treat `unordered()` as a shuffle command. On ordered parallel Streams, `sorted` stability still holds, but parallel `forEach` may observe actions out of encounter order — use `toList()` or `forEachOrdered` when you need to inspect or execute in order.

The comparator must obey its contract; prefer `Comparator.comparingInt`/`thenComparing` over subtraction that can overflow. Remember that `sorted` is a stateful intermediate operation and can be memory-intensive on large sources.

**Official documentation:** Java SE 17 Javadoc for `java.util.stream.Stream` (sections `sorted()`, `sorted(Comparator)`, `forEach`, `forEachOrdered`, `unordered`, `toList`), `java.util.Comparator`, `java.util.Spliterator`; and the ordering section of the Java Stream package documentation.
