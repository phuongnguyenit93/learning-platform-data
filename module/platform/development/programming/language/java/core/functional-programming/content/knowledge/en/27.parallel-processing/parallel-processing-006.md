# findAny(), forEach(), and Nondeterministic Ordering Results in Java Stream

## Lesson Objectives

In Java Stream, **encounter order**, **callback execution order**, and **result observation order** are three distinct concepts. When processing in parallel, an element processed first is not necessarily the first element in the source. Two terminal operations demonstrate this very clearly:

- `findAny()` returns an `Optional<T>` containing **any element** if the source is non-empty. The method intentionally makes no promise about which element it picks.
- `forEach(action)` applies a `Consumer<T>` to elements, but **does not guarantee action order**, even when the source has encounter order.

To handle ordered requirements, you need to understand `findFirst()` and `forEachOrdered()`. This lesson also compares `unordered()`, `parallelStream()`, `toList()`, reduction operations, and managing shared side effects across threads.

After this lesson, you will be able to choose the right API, write tests independent of thread scheduling, distinguish valid nondeterministic results from data races, and use Java 17 examples to prove Stream's actual guarantees.

## 1. Encounter order, execution order, and result order

### Encounter order: logical order

`List.of(1,2,3,4)`, `Stream.of(1,2,3,4)`, and `IntStream.rangeClosed(1,4)` all create sources with encounter order 1,2,3,4 respectively. Encounter order is a property of the source/pipeline; it does not disappear just because you call `parallel()`.

```java
List<Integer> numbers = List.of(1, 2, 3, 4);

Stream<Integer> sequential = numbers.stream();
Stream<Integer> parallel = numbers.parallelStream();
```

Both sources have encounter order. The variable `parallel` indicates parallel execution mode; **it does not mean the elements themselves are randomly scrambled**.

### Execution order: runtime order

When a pipeline processes in parallel, the runtime can split the source into multiple chunks, run mappers/filters/actions on multiple threads, and combine partial results. There is no general guarantee that the callback for element 1 will finish before the callback for element 2. Even if a test program happens to print in order, that can still be coincidence.

### Result order: output order

A terminal operation can preserve encounter order in **the result** even though intermediate callbacks run in parallel. For example, `numbers.parallelStream().map(n -> n * 2).toList()` preserves the order `[2,4,6,8]` for an ordered List source. This does not allow inferring that `map` executed in the order 1,2,3,4.

| Method | Key guarantee on ordered source | Must not be assumed |
| --- | --- | --- |
| `findFirst()` | Picks first element in encounter order | Always faster than `findAny` |
| `findAny()` | Picks an available element, if any | First element or uniformly random choice |
| `forEach()` | Applies action to elements, no ordering guarantee | Logs in encounter order |
| `forEachOrdered()` | Actions in encounter order | All stages run on a single thread |
| `toList()` | Result list preserves encounter order | Every callback runs in encounter order |
| `unordered()` | Drops encounter-order constraint | Shuffles values with random probability |

## 2. findAny(): any element

Signature:

```java
Optional<T> findAny()
```

This is a **short-circuiting terminal operation**. When the Stream has elements, `findAny()` is allowed to pick an element not necessarily at the first position. If the Stream is empty, it returns `Optional.empty()`.

```java
List<Integer> numbers = List.of(10, 20, 30);

Optional<Integer> any = numbers.parallelStream().findAny();
System.out.println(any.isPresent()); // true
```

There is no reliable stdout for **the specific value** of `any`: `Optional[10]`, `Optional[20]`, and `Optional[30]` are all valid per contract.

### Why is it nondeterministic?

A search that must preserve the first element in encounter order may have to coordinate results across multiple parallel branches. `findAny` is allowed to pick a qualifying result from a branch without confirming it is the first element. It creates an optimization opportunity, **without promising performance is always better**.

Even on a sequential Stream, `findAny` **has no contract to return the first element**. Some implementations often pick the first element, but application code should not depend on this observed behavior.

### Proper testing

With a non-empty source, check the validity of the result:

```java
List<Integer> numbers = List.of(10, 20, 30);
int selected = numbers.parallelStream()
        .findAny().orElseThrow();

boolean valid = numbers.contains(selected); // true
```

If the pipeline also has `filter(n -> n % 2 == 0)`, the test must check that the selected element satisfies the predicate. If the source is empty, test `findAny().isEmpty()` is true. **Do not assert a specific value** like 20 just because a run on the current machine returned 20.

There is no uniform random distribution contract: `findAny` **is not a random sampling algorithm**. Running it 100 times and getting the same ID does not prove Java chose wrong, because the API promises neither fairness nor entropy.

### Nulls in the source

`Optional` cannot hold a `null` element. If a `findAny` terminal selects a null element, a `NullPointerException` can occur. It is best to define a null-handling policy at the source and not implicitly treat null as valid data. If business logic allows skipping nulls, you can apply `filter(Objects::nonNull)`.

## 3. findFirst(): first element only when encounter order exists

Signature:

```java
Optional<T> findFirst()
```

On a source with encounter order, it picks **the first element after intermediate operations**.

```java
int first = List.of(1, 3, 4, 6, 8)
        .parallelStream()
        .filter(n -> n % 2 == 0)
        .findFirst()
        .orElseThrow();

System.out.println(first); // 4
```

Despite parallel processing, `findFirst` must return 4 because it is the first even element in encounter order.

If `unordered()` is called before `findFirst`, this constraint no longer holds:

```java
Optional<Integer> selected = List.of(1, 2, 3, 4)
        .parallelStream()
        .unordered()
        .findFirst();
```

Once the pipeline is unordered, any present element may be the result. `unordered()` does not mean shuffling: it only removes the encounter-order constraint. Thus the value 1 may still be returned across many runs.

**Use `findFirst` when business logic needs the first element in the chosen order**; use `findAny` when any matching element will do. When you need the highest-priority element, define a comparator or min/max rule rather than depending on which CPU branch finds one first.

## 4. forEach(): action order is not guaranteed

Signature:

```java
void forEach(Consumer<? super T> action)
```

`forEach` is a terminal operation used when you need to perform an action on elements. With a parallel stream:

```java
List<Integer> numbers = List.of(1, 2, 3, 4, 5);
numbers.parallelStream().forEach(System.out::println);
```

**There is no fixed-order stdout** for this snippet. Different orders can occur. With a sequential pipeline, many practical implementations process left to right, yet the `forEach` API still does not promise to preserve encounter order; if order is part of the business contract, use `forEachOrdered`.

### Data race when mutating an ArrayList

This is an unsafe pattern:

```java
List<Integer> results = new ArrayList<>();
numbers.parallelStream().forEach(results::add);
```

`ArrayList.add` does not support unsynchronized concurrent updates from multiple threads. Elements can be lost or errors thrown. This is a **real concurrency bug**, distinct from logs printing in a valid non-ordered sequence.

If you need a concurrent container to verify which tasks executed, you can use:

```java
ConcurrentLinkedQueue<Integer> results =
        new ConcurrentLinkedQueue<>();

numbers.parallelStream().forEach(results::add);
```

The queue accepts concurrent additions, but **queue order** can differ from encounter order. If the goal is simply **collecting values into a List**, use collection instead of a shared mutable container:

```java
List<Integer> values = numbers.parallelStream()
        .map(n -> n * 2)
        .toList();
```

`toList` preserves encounter order on ordered sources; the resulting List does not allow structural modification.

### Shared counter

`int[] count = {0}; numbers.parallelStream().forEach(n -> count[0]++);` is unsafe: the increment is not atomic. `AtomicInteger` or `LongAdder` handles some concurrent counting needs, but when you only need the element count, `count()` is the clearer choice. When you need a sum, use `mapToLong(...).sum()` or a `reduce` with an appropriate associative operation.

### Side effects are not transactions

If an action writes logs, calls an API, or sends an email and one branch throws an exception, the Stream does not automatically roll back side effects that already occurred. Action scheduling is not fixed, and external operations may have already happened on other threads. Do not put critical transactional logic inside `forEach` without designing error policies, idempotency, and synchronization.

## 5. forEachOrdered(): action order

Signature:

```java
void forEachOrdered(Consumer<? super T> action)
```

On a Stream with encounter order, `forEachOrdered` **executes actions in that exact order**:

```java
List.of(1, 2, 3, 4)
        .parallelStream()
        .forEachOrdered(System.out::println);
```

Stdout is ordered 1, 2, 3, 4. The contract also states that the action for an element **happens-before** the action for the next element in encounter order. However, it does not promise all actions run on the same thread; stages before the terminal can still be processed in parallel.

Preserving order typically requires coordination and can reduce parallel gains. Do not conclude `forEachOrdered` is always slower in every case without measuring; what matters is choosing correctly for business requirements.

When a Stream is **unordered**, `forEachOrdered` does not create a desired order on its own. If you need to print names in ascending order from an unordered source, call `sorted()` first:

```java
Set<String> names = Set.of("Lan", "An", "Mai");

names.parallelStream()
        .sorted()
        .forEachOrdered(System.out::println);
```

This snippet prints An, Lan, Mai in natural String order; requires importing `Set`.

## 6. Complete Java 17 example with stable stdout

A good parallel demo must not fabricate **the value `findAny` returns** or **the order `forEach` executes**. The example below replaces non-guaranteed details with property checks: elements belong to the source, element count matches, and order is guaranteed only on appropriate APIs.

Create file **`ParallelOrderDemo.java`**:

```java
import java.util.List;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class ParallelOrderDemo {
    public static void main(String[] args) {
        List<Integer> numbers = IntStream.rangeClosed(1, 8)
                .boxed().toList();

        int first = numbers.parallelStream()
                .findFirst().orElseThrow();
        int any = numbers.parallelStream()
                .findAny().orElseThrow();
        boolean anyValid = numbers.contains(any);

        System.out.println("findFirst: " + first);
        System.out.println("findAny valid member: " + anyValid);
        System.out.println("Empty findAny: "
                + Stream.<Integer>empty().findAny().isEmpty());

        ConcurrentLinkedQueue<Integer> visited =
                new ConcurrentLinkedQueue<>();
        numbers.parallelStream().forEach(visited::add);
        boolean complete = visited.size() == numbers.size()
                && visited.stream().sorted().toList().equals(numbers);
        System.out.println("forEach visited all: " + complete);
        System.out.println("forEach count: " + visited.size());

        ConcurrentLinkedQueue<Integer> inOrder =
                new ConcurrentLinkedQueue<>();
        numbers.parallelStream().forEachOrdered(inOrder::add);
        System.out.println("forEachOrdered: " + List.copyOf(inOrder));

        List<Integer> doubled = numbers.parallelStream()
                .map(n -> n * 2).toList();
        System.out.println("parallel toList: " + doubled);

        boolean unorderedValid = numbers.parallelStream()
                .unordered().findFirst()
                .filter(numbers::contains).isPresent();
        System.out.println("unordered findFirst valid member: "
                + unorderedValid);

        boolean repeatedValid = IntStream.range(0, 100).allMatch(i ->
                numbers.contains(numbers.parallelStream()
                        .findAny().orElseThrow()));
        System.out.println("100 findAny checks valid: " + repeatedValid);
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac ParallelOrderDemo.java
java ParallelOrderDemo
```

**Exact stdout:**

```text
findFirst: 1
findAny valid member: true
Empty findAny: true
forEach visited all: true
forEach count: 8
forEachOrdered: [1, 2, 3, 4, 5, 6, 7, 8]
parallel toList: [2, 4, 6, 8, 10, 12, 14, 16]
unordered findFirst valid member: true
100 findAny checks valid: true
```

### Part-by-part analysis

1. `IntStream.rangeClosed(1,8).boxed().toList()` creates a clearly ordered List from 1 to 8.
2. `findFirst` on an ordered parallel stream returns 1. `findAny` only has to return **a number from the List**; the test checks the property rather than a specific number.
3. `Stream.empty().findAny()` yields an empty Optional.
4. `forEach` adds to `ConcurrentLinkedQueue` safely across multiple threads. The test **counts 8 elements** and **sorts observed results to compare against the source**, without assuming the order in which `add` calls occurred.
5. `forEachOrdered` preserves encounter order; the List copied from the queue is the sequence 1 to 8.
6. `map(...).toList()` on an ordered source preserves output order even though the pipeline can process elements concurrently.
7. `unordered().findFirst()` is no longer obligated to pick 1; membership checking is the valid requirement.
8. All 100 `findAny` passes pick values from the source. That **does not require** the passes to return different values.

The program uses fixed values, performs no network reads, prints no thread names, and does not rely on execution schedules. The example was compiled with `javac --release 17` and run with the stdout above.

## 7. Short-circuiting and side effects in a pipeline

`findAny` and `findFirst` are **short-circuiting** terminal operations: they do not need to process all elements to produce a result. In a parallel pipeline, other branches may still have executed callbacks before a result was chosen. Therefore, do not put a mandatory business side effect inside `filter` or `map` and expect it to always run once for every element.

Anti-pattern illustration:

```java
Optional<Integer> found = IntStream.rangeClosed(1, 1000)
        .parallel()
        .filter(n -> {
            audit(n); // This is a side effect you should not rely on.
            return n % 7 == 0;
        })
        .boxed()
        .findAny();
```

This is not a standalone program; `audit` must be defined. If auditing **all** elements is mandatory, `findAny` is the wrong requirement because it is allowed to stop early. Separate the auditing work from element selection or use a dedicated processing mechanism with appropriate guarantees.

Similarly, `peek` should not be used to process payments, perform mandatory data updates, or emit events that you assume must run on every element: optimizations and short-circuiting can alter the actual number of callback invocations observed.

## 8. Choosing APIs and testing by contract

| Need | Suitable API | Invariant to test |
| --- | --- | --- |
| Find any record matching a condition | `filter(...).findAny()` | Element belongs to source and satisfies predicate |
| Find first record after applying order | `findFirst()` | Is the first element in encounter order |
| Find min/max by property | `min/max(comparator)` | Satisfies comparison rule |
| Run order-independent action | `forEach()` | Every required element processed, action is thread-safe |
| Run action in source order | `forEachOrdered()` | Actions follow encounter order |
| Collect an ordered List | `toList()` on ordered source | Result equals expected sequence |
| Count, sum, or group | `count/sum/collect` | Reduction result is accurate |
| Drop ordering because unnecessary | `unordered()` | Content is right, do not assert order |

### Situations requiring extra care

- A `Set` source does not always have encounter order; `findFirst` does not automatically pick the "first by name" record.
- `findAny` is not a random number generator; do not use it for fair random selection.
- `forEachOrdered` guarantees action order when the source is ordered, but does not automatically synchronize other external work.
- A `Stream` can only be consumed once by a terminal operation; do not call `findAny` and then `forEach` on the same Stream object.
- `Optional.empty()` must be handled: `orElse`, `orElseThrow`, or `isPresent` checks per policy.
- If a callback throws an exception, do not assume side effects on other threads are rolled back.
- To optimize performance, benchmark properly on real sources/workloads. `parallel()` is not automatically faster, and `forEachOrdered` can increase coordination overhead.

## 9. Common mistakes

1. Testing `findAny()` against a fixed value.
2. Thinking `findAny` always returns the first element when sequential.
3. Thinking `findAny` distributes results uniformly at random.
4. Equating `parallel` with `unordered`.
5. Treating `forEach` log order as encounter order.
6. Letting multiple threads write to the same `ArrayList` from `forEach`.
7. Using an unsynchronized shared counter in callbacks.
8. Thinking `forEachOrdered` forces the entire pipeline onto one thread.
9. Using `forEachOrdered` on an unordered source and expecting natural order.
10. Using `findAny` when the contract requires the first or highest-priority record.
11. Forgetting to handle empty sources and `Optional.empty()`.
12. Not handling null elements when `findAny/findFirst` might select one.
13. Putting mandatory logging in `filter` and ending with `findAny`.
14. Thinking `toList` on an ordered parallel stream produces unordered output.
15. Using one Stream for two terminal operations.
16. Assuming that running 100 times and getting the same element is an API guarantee.

## 10. Practice exercises

**Exercise 1.** For `List.of("A","B","C").parallelStream().findAny()`, write a valid assertion without predicting which element is chosen.

**Exercise 2.** For `List.of(1,3,4,6,8)`, find the first even number using a parallel stream. What value is guaranteed?

**Exercise 3.** For `IntStream.rangeClosed(1,100)`, find any number divisible by 7. Which properties should be checked?

**Exercise 4.** Why does `parallelStream().forEach(System.out::println)` have no fixed stdout order?

**Exercise 5.** Replace `parallelStream().forEach(sharedArrayList::add)` with a safer collection operation.

**Exercise 6.** When a Set source is unordered, what operation must be added to print strings alphabetically with `forEachOrdered`?

**Exercise 7.** After `unordered()`, is `findFirst()` required to return the first element of the original List?

**Exercise 8.** Why can `forEachOrdered` still have parallel upstream stages and actions running on different threads?

**Exercise 9.** A `filter` pipeline logs events in a callback and then calls `findAny`. Why can you not guarantee every element is logged?

**Exercise 10.** If you only need to count elements matching a condition, why is `filter(predicate).count()` clearer than a shared counter?

**Exercise 11.** What does `findAny` return on an empty Stream? What happens if `orElseThrow()` is called immediately?

**Exercise 12.** Does `parallelStream().map(...).toList()` preserve encounter order from a List? Is callback order guaranteed?

### Suggested answers

1. Check that the Optional has a value and the element is in the List.
2. `4`, because the source is ordered and `findFirst` picks the first even number in encounter order.
3. Result is in `1..100` and `n % 7 == 0`.
4. Action order and thread scheduling are not guaranteed.
5. `numbers.parallelStream().toList()` or `collect(...)` as required.
6. `sorted()` before `forEachOrdered`.
7. No; the ordering constraint was removed.
8. The guarantee applies to action order, not forcing the whole pipeline onto one thread.
9. `findAny` short-circuits and may not traverse every element.
10. `count` is a terminal reduction, with no races on a shared variable.
11. `Optional.empty()`; `orElseThrow()` throws `NoSuchElementException`.
12. Preserves output order if the source is ordered; intermediate callback order is not guaranteed.

## Conclusion

`findAny()` and `forEach()` are designed **not to constrain element selection or action order** in the ways many people accidentally assume. This is valid freedom in Java Stream, especially useful for parallel computation. If business logic needs order, use `findFirst()`, `forEachOrdered()`, or `toList()` results on an ordered stream.

Testing nondeterministic behavior must rely on **invariants**, such as an element belonging to the source, satisfying a predicate, matching counts, or having correct Map/List contents, rather than predicting execution schedules. At the same time, avoid shared mutable state and unguaranteed side effects: an unexpected log order may be valid, whereas losing data due to a data race is not.