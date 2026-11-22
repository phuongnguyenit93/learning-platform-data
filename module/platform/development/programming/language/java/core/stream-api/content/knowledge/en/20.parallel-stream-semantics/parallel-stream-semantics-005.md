# Result Ordering with findAny, findFirst, forEach, and forEachOrdered

## 1. Does parallel processing mean losing order?

In the **Java Stream API**, a pipeline consists of a data source, intermediate operations such as `filter`, `map`, and `sorted`, and a terminal operation such as `findFirst`, `findAny`, `forEach`, or `collect`. When switching a pipeline to `parallel()` or creating a source via `parallelStream()`, Stream can divide work across multiple tasks for concurrent execution.

However, **execution order** and **result order** are two distinct concepts:

- **Execution order:** which task or lambda runs first on which threads. On a parallel Stream, the schedule is non-deterministic.
- **Encounter order:** the logical order of elements defined by the source and pipeline.
- **Result order:** whether a terminal operation preserves encounter order or is permitted to ignore it.

Example:

```java
import java.util.List;

List<Integer> numbers = List.of(1, 2, 3, 4, 5);

List<Integer> doubled = numbers.parallelStream()
        .map(n -> n * 2)
        .toList();

System.out.println(doubled); // [2, 4, 6, 8, 10]
```

The `map` calls **may execute on threads in different schedules**, yet `toList()` preserves the encounter order of the `List` source. Thus, switching to parallel **does not automatically scramble the result order**.

In the **Parallel Processing Semantics** chapter, this lesson focuses on four terminal operations with distinct ordering contracts:

- `findAny`: finds **any matching element**, without promising the first element.
- `findFirst`: finds **the first element in encounter order**, if the Stream is ordered.
- `forEach`: performs an action for each element, **without promising action order** in parallel execution.
- `forEachOrdered`: performs actions **in encounter order** if the Stream is ordered, even when the pipeline is in parallel mode.

**Goal:** understand when order is preserved or relaxed, choose the right terminal operation, avoid side-effect and shared-state bugs, and evaluate trade-offs in performance, short-circuiting, and work splitting.

The examples use **Java 17+** for `record` and `Stream.toList()`. All four terminal operations covered have been part of the Stream API since Java 8.

## 2. Where does encounter order come from?

A Stream may **have** or **lack** an encounter order. This is a logical property of the stream, not the JVM happening to emit data in a certain order during one run.

| Source or operation | Ordering property to remember |
| --- | --- |
| `List.stream()` / `List.parallelStream()` | Has encounter order matching List element order. |
| `Arrays.stream(array)` | Has encounter order by array index. |
| `IntStream.range(...)` | Has encounter order in increasing numeric sequence. |
| `LinkedHashSet.stream()` | Has encounter order defined by `LinkedHashSet` iteration order. |
| `TreeSet.stream()` | Has encounter order defined by the Set's sorted order. |
| `HashSet.stream()` | Does not guarantee a meaningful encounter order. |
| `HashMap.keySet().stream()` | Does not guarantee encounter order from `HashMap`. |
| `unordered()` | Relaxes the pipeline's encounter order constraint if previously present. |
| `parallel()` | Selects parallel processing mode; **does not automatically remove encounter order**. |

Example of an ordered source:

```java
List<String> names = List.of("An", "Bình", "Chi", "Dũng");

String first = names.parallelStream()
        .findFirst()
        .orElseThrow();

System.out.println(first); // An
```

The key point is not which thread processed the list, but that `findFirst` must respect the **first element in List order**.

Conversely:

```java
Set<String> namesWithoutOrder =
        new java.util.HashSet<>(List.of("An", "Bình", "Chi"));

Optional<String> selected = namesWithoutOrder.parallelStream()
        .findFirst();

// There is no guarantee that "An" is the first element.
```

`findFirst` cannot manufacture a stable "first" from a source without encounter order. If you need a result based on a criterion like "smallest by name," you must **define business ordering** or use an appropriate terminal operation such as `min`.

## 3. Contract comparison table for the four terminal operations

Signatures on `Stream<T>`:

```java
Optional<T> findAny();
Optional<T> findFirst();
void forEach(Consumer<? super T> action);
void forEachOrdered(Consumer<? super T> action);
```

| Method | Return value | On a Stream with encounter order | Can short-circuit? |
| --- | --- | --- | --- |
| `findAny()` | `Optional<T>` | Not required to select the first element | Yes |
| `findFirst()` | `Optional<T>` | Selects the first element in encounter order | Yes |
| `forEach(action)` | `void` | In parallel, action invocation order is not guaranteed | No, intended to process elements |
| `forEachOrdered(action)` | `void` | Actions are executed in encounter order | No, intended to process elements |

`findAny` and `findFirst` are **short-circuiting terminal operations**: they only need to find one matching result and can avoid consuming the entire stream. However, in a parallel pipeline, other elements **may still be processed** during coordination; do not use them to assume a mapper runs only once.

`forEach` and `forEachOrdered` are terminal operations intended for **actions**, returning no List or value. If you simply want to turn data into a list, `toList` or `collect` usually expresses the intent better.

A Stream may become empty after `filter`. In that case, both `findAny` and `findFirst` return `Optional.empty()`. `forEach` and `forEachOrdered` will not invoke the action for any element.

## 4. findAny: any element will do, as long as it matches

`findAny` may pick **any remaining element in the Stream**. This design lets the JVM use a result from a processing branch without having to prove it is globally the first element.

```java
List<Integer> numbers = List.of(10, 20, 30, 40, 50);

Optional<Integer> anyLarge = numbers.parallelStream()
        .filter(n -> n >= 30)
        .findAny();

System.out.println(anyLarge);
// Could be Optional[30], Optional[40], or Optional[50].
```

All of those results are valid. **Do not write tests requiring `findAny` to always return `30`**, even if repeated runs on a given machine happen to show the same number.

### findAny can also be used sequentially

`findAny` **does not mean** "pick the fastest-completing element," nor does it guarantee the JVM analyzes performance to pick the best result. It simply relaxes the selection contract. On a sequential pipeline, the result often looks like the first element, yet that is not a guarantee you may rely upon.

```java
Optional<String> any = names.stream()
        .filter(name -> !name.isBlank())
        .findAny();

// Do not rely on any.orElseThrow().equals("An").
```

### When is findAny the right choice?

`findAny` makes sense when **any matching record is equally acceptable**, such as finding an available server in a group, a sample record for inspection, or one element proving the result set is non-empty.

If you only need to know whether a matching element **exists**, `anyMatch` is clearer and returns `boolean`:

```java
boolean hasLarge = numbers.parallelStream()
        .anyMatch(n -> n >= 30);

System.out.println(hasLarge); // true
```

There is no need to allocate an `Optional` if the business logic does not need the selected element itself.

## 5. findFirst: prioritizing the first element in encounter order

On an ordered Stream, `findFirst` must select the first element of the stream **after intermediate operations**.

```java
List<Integer> samples = List.of(4, 9, 2, 7, 3);

int firstEven = samples.parallelStream()
        .filter(n -> n % 2 == 0)
        .findFirst()
        .orElseThrow();

System.out.println(firstEven); // 4
```

The number `2` also satisfies the condition, but appears **after `4`** in the List's encounter order. Even if the branch processing `2` finishes earlier, `findFirst` must still return `4`.

### Parallel execution is not a random element picker

If the business rule is "select the first order in chronologically sorted history," `findFirst` is the right choice. If it does not matter which order is chosen, `findAny` can give the framework more room to optimize.

```java
record Request(String id, boolean ready) {}

List<Request> requests = List.of(
        new Request("R01", false),
        new Request("R02", true),
        new Request("R03", true),
        new Request("R04", true)
);

Request firstReady = requests.parallelStream()
        .filter(Request::ready)
        .findFirst()
        .orElseThrow();

System.out.println(firstReady.id()); // R02
```

### findFirst does not automatically mean "smallest" or "newest"

`findFirst` selects **according to the existing order in the pipeline**, rather than automatically finding the smallest number or newest timestamp:

```java
List<Integer> scores = List.of(90, 70, 100, 80);

int first = scores.parallelStream()
        .findFirst()
        .orElseThrow(); // 90

int smallest = scores.parallelStream()
        .min(Integer::compareTo)
        .orElseThrow(); // 70

int sortedFirst = scores.parallelStream()
        .sorted()
        .findFirst()
        .orElseThrow(); // 70
```

`min` directly expresses retrieving the minimum value without building a full sorting pipeline. `sorted().findFirst()` also yields the smallest value here, yet `sorted` is a stateful operation that may need to process more data.

If multiple elements tie on priority, define a **tie-break rule** to ensure deterministic selection.

## 6. findFirst or findAny when the source is unordered?

`findFirst` only means "first" when the stream has an encounter order. Calling `unordered()` explicitly discards the ordering commitment:

```java
List<Integer> values = List.of(10, 20, 30, 40);

Optional<Integer> noDefinedFirst = values.parallelStream()
        .unordered()
        .findFirst();

// Could be any element; 10 is not guaranteed.
```

This is a valid `findFirst` call, yet it no longer means "the first element of the List" after dropping order. `findAny` usually communicates intent more clearly when any element is acceptable.

### Want to establish order before selecting?

```java
Set<Integer> unorderedNumbers =
        new java.util.HashSet<>(List.of(40, 10, 30, 20));

int smallestBySort = unorderedNumbers.parallelStream()
        .sorted()
        .findFirst()
        .orElseThrow();

System.out.println(smallestBySort); // 10
```

`sorted` produces a sequence ordered by comparison; with a consistent criterion, `findFirst` has a meaningful "first." However, if you only need the smallest element, `min` is usually simpler. Do not mechanically add `sorted` to every pipeline just to pick one result.

## 7. forEach: processes every element, no action order guaranteed when parallel

`forEach` accepts a `Consumer<T>` and returns no value:

```java
List<String> letters = List.of("A", "B", "C", "D");

letters.parallelStream()
        .forEach(System.out::println);

// May print in any order, e.g., C, D, B, A.
// No fixed print order is guaranteed.
```

The source is a `List` with encounter order, yet `forEach` on a parallel pipeline **is permitted to ignore order when invoking the action**. This allows branches to complete work more independently.

In a simple sequential pipeline, `forEach` typically prints in encounter order. But if the business contract **requires preserving order** if `stream()` is later replaced with `parallelStream()`, use `forEachOrdered` from the start or redesign to return an ordered Collection.

### What kinds of tasks is forEach suitable for?

Use `forEach` only for actions that genuinely need to run for each element, such as dispatching an independent operation or recording results into a concurrency-safe accumulation structure.

Do not use `forEach` to accumulate into an unsynchronized shared `ArrayList`:

```java
List<Integer> shared = new java.util.ArrayList<>();

// WRONG: multiple threads may call shared.add concurrently.
List.of(1, 2, 3, 4).parallelStream()
        .forEach(shared::add);

// May lose data, report wrong size, or fail due to race conditions.
```

If the goal is **collecting** a list, use a collecting terminal operation:

```java
List<Integer> collected = List.of(1, 2, 3, 4)
        .parallelStream()
        .toList();

System.out.println(collected); // [1, 2, 3, 4]
```

Because `toList` handles collection properly according to Stream semantics, we do not need a shared mutable List in `forEach`.

## 8. forEachOrdered: preserves encounter order of actions

When the order of the **final action** is part of the requirement, use `forEachOrdered`:

```java
List<String> letters = List.of("A", "B", "C", "D");

letters.parallelStream()
        .forEachOrdered(System.out::println);

// Prints in exact order:
// A
// B
// C
// D
```

`forEachOrdered` **does not force the entire pipeline to run sequentially**. Earlier steps can still execute in parallel, while **the actions** follow the Stream's encounter order.

By Java's contract, executing the action for one element in `forEachOrdered` **happens-before** executing the action for the next element. However, actions for different elements **do not necessarily run on the same thread**.

### Direct comparison

```java
List<Integer> ids = List.of(10, 20, 30, 40);

ids.parallelStream().forEach(System.out::println);
// Order is not guaranteed.

ids.parallelStream().forEachOrdered(System.out::println);
// Prints 10, 20, 30, 40 in exact encounter order.
```

The prerequisite is that the Stream **must have an encounter order**. With an unordered source, `forEachOrdered` cannot turn the data into a sorted list on its own:

```java
Set<Integer> hashNumbers =
        new java.util.HashSet<>(List.of(10, 20, 30, 40));

hashNumbers.parallelStream()
        .forEachOrdered(System.out::println);

// Not guaranteed to print 10, 20, 30, 40.
```

The name `forEachOrdered` does not mean `sorted`. It preserves an **already existing encounter order**, rather than creating value order.

## 9. Order of map and peek differs from order of forEachOrdered

A very common mistake is assuming `forEachOrdered` forces **every lambda in the pipeline** to run sequentially from start to finish.

```java
List<Integer> numbers = List.of(1, 2, 3, 4);

numbers.parallelStream()
        .map(n -> {
            System.out.println("map " + n
                    + " bởi " + Thread.currentThread().getName());
            return n * 10;
        })
        .forEachOrdered(n ->
                System.out.println("output " + n));
```

The `output` lines execute in the value order `10, 20, 30, 40`. However, the `map` lines **have no guaranteed execution order** and may appear interleaved with the output lines.

What `forEachOrdered` guarantees is **the execution order of the terminal action**, not the invocation order of upstream `map`, `filter`, or `peek`.

### peek is not a tool to guarantee every element produces a side effect

`peek` is often useful for debugging observation:

```java
Optional<Integer> found = numbers.parallelStream()
        .peek(n -> System.out.println("Thấy " + n))
        .findFirst();
```

The pipeline may process some elements that are not selected, or optimize away intermediate operations unnecessary for the terminal operation. Do not use `peek` or `map` for logging, sending messages, or incrementing counters that **must occur exactly once per element**.

### When an ordered list is needed

`forEachOrdered` is useful for ordered final actions such as writing lines sequentially to a channel. Yet if the goal is **producing structured data**, collecting first is usually easier to test:

```java
List<Integer> result = numbers.parallelStream()
        .map(n -> n * 10)
        .toList();

System.out.println(result); // [10, 20, 30, 40]
```

Here no consumer side effects are needed, and no manual thread coordination is required.

## 10. Stateless, non-interfering, and shared-state bugs

In Streams, lambdas passed to `filter`, `map`, and most intermediate operations should be **stateless** (not relying on external mutable state) and **non-interfering** (not modifying the source being traversed).

Wrong example:

```java
List<Integer> mutableSource =
        new java.util.ArrayList<>(List.of(1, 2, 3, 4));

// WRONG: modifying the source itself while traversing.
mutableSource.parallelStream()
        .forEach(value -> mutableSource.add(value * 10));
```

Sources like `ArrayList` do not support this kind of mutation while a Stream is traversing them. The result may be `ConcurrentModificationException`, corrupted data, or unreliable behavior.

Even counting with an ordinary variable is unsafe:

```java
int[] counter = {0};

// WRONG: unsynchronized shared updates to counter[0].
IntStream.range(0, 1_000).parallel()
        .forEach(n -> counter[0]++);

// Cannot trust that counter[0] == 1000.
```

If you only need the element count, `count()` is the proper expression:

```java
long total = IntStream.range(0, 1_000)
        .parallel()
        .count();

System.out.println(total); // 1000
```

If you truly need to accumulate a metric across independent actions, choose a suitable synchronization primitive such as `LongAdder`:

```java
import java.util.concurrent.atomic.LongAdder;
import java.util.stream.IntStream;

LongAdder sum = new LongAdder();

IntStream.rangeClosed(1, 1_000)
        .parallel()
        .forEach(sum::add);

System.out.println(sum.sum()); // 500500
```

However, **to compute a sum**, `IntStream.sum()` or `mapToLong(...).sum()` is still simpler and generally avoids updating a shared accumulator.

### Does forEachOrdered make all external state thread-safe?

No. Action ordering for **a single `forEachOrdered` call** is constrained, yet that does not protect variables from concurrent access **outside the pipeline**, nor does it make stateful intermediate lambdas valid.

For instance, two separate Stream calls writing to a shared list still need explicit coordination. And if logic requires each element's state to depend on the previous element, an explicit sequential loop may be more appropriate than forcing a parallel pipeline.

## 11. unordered(): relaxing constraints, not shuffling

`BaseStream.unordered()` returns a Stream that may be processed **without preserving encounter order**. It is **not** `shuffle` and does not promise a random permutation.

```java
List<String> ids = List.of("R01", "R02", "R03", "R04");

Optional<String> anyFirst = ids.parallelStream()
        .unordered()
        .findFirst();

// Selecting "R01" is no longer guaranteed.
```

Some parallel operations that preserve encounter order may need expensive coordination. When business logic does not care about order, dropping this constraint **may** unlock optimizations, though actual gains must be measured.

Conversely, when the output is a report that must reproducibly match source order, **do not call `unordered()` hoping to run faster**.

### forEachOrdered after unordered()

```java
ids.parallelStream()
        .unordered()
        .forEachOrdered(System.out::println);

// From here on there is no guaranteed encounter order to preserve.
```

`forEachOrdered` cannot restore a dropped commitment. If alphabetical, ID, or chronological order is required, establish explicit sorting criteria before the terminal operation.

## 12. Intermediate operations can change the meaning of "first"

Even on an ordered List, **the order and contents after intermediate steps** determine the result of `findFirst`.

### filter preserves relative order

```java
List<Integer> values = List.of(5, 2, 8, 1, 4);

int firstEven = values.parallelStream()
        .filter(n -> n % 2 == 0)
        .findFirst()
        .orElseThrow();

System.out.println(firstEven); // 2
```

`filter` preserves the relative order of surviving elements in an ordered Stream. Here `findFirst` does not return `8` or `4`, even though both are also even.

### sorted establishes value order

```java
int smallestEven = values.parallelStream()
        .filter(n -> n % 2 == 0)
        .sorted()
        .findFirst()
        .orElseThrow();

System.out.println(smallestEven); // 2
```

The output happens to match the previous example, yet the contract is different. If `values` were `List.of(8, 2, 4)`, `findFirst` after `filter` would return `8`, whereas with `sorted()` it would return `2`.

### limit and takeWhile are affected by encounter order

Operations such as `limit`, `skip`, `takeWhile`, and `dropWhile` have order-sensitive semantics. With an ordered source, keeping an exact prefix can require coordination overhead in a parallel pipeline:

```java
List<Integer> firstThree = IntStream.rangeClosed(1, 100)
        .parallel()
        .limit(3)
        .boxed()
        .toList();

System.out.println(firstThree); // [1, 2, 3]
```

Do not equate short-circuiting or slicing with "every task inspects only three elements." Especially when `sorted` or other stateful operations are present, the framework may need to process additional data to uphold the contract.

## 13. Null, Optional, and not-found cases

`findFirst` and `findAny` return `Optional<T>` because the Stream may be empty after filtering:

```java
Optional<Integer> noMatch = List.of(1, 3, 5)
        .parallelStream()
        .filter(n -> n % 2 == 0)
        .findFirst();

System.out.println(noMatch.isEmpty()); // true
```

If no element matches, `orElse` or `orElseThrow` expresses the fallback policy clearly:

```java
int fallback = noMatch.orElse(-1); // -1

// If not found is a business error:
// int required = noMatch.orElseThrow(
//         () -> new IllegalStateException("Không có phần tử phù hợp"));
```

**Null note:** `Optional` cannot hold `null`. If the element selected by `findFirst` or `findAny` is `null`, the operation may throw `NullPointerException`. When a source can contain nulls, handle them per input policy:

```java
List<String> raw = java.util.Arrays.asList(null, "A", "B");

Optional<String> firstNonNull = raw.parallelStream()
        .filter(java.util.Objects::nonNull)
        .findFirst();

System.out.println(firstNonNull.orElseThrow()); // A
```

`List.of(...)` disallows null elements, so this example intentionally uses `Arrays.asList`. Filtering nulls here still preserves the encounter order of the remaining elements.

## 14. Performance: paying the price for preserving order

**There is no rule that "parallel is always faster."** When choosing operations, weigh business requirements first, then measure on real data.

| Choice | Semantic advantage | Potential cost or limitation |
| --- | --- | --- |
| `findAny` | Allows picking any matching element | Non-deterministic result if multiple elements match |
| `findFirst` | Preserves the first element of an ordered Stream | In a parallel pipeline, may need coordination to verify no earlier match exists |
| `forEach` | Allows independent action execution without preserving order | Side-effect order is unstable; shared state must be protected |
| `forEachOrdered` | Preserves action order on an ordered Stream | Ordering constraint can reduce parallel exploitation |
| `unordered()` | Relaxes ordering constraints when unneeded | Changes semantics for `findFirst`, `limit`, `takeWhile`, and order-sensitive operations |
| `sorted()` | Establishes order by comparator | Stateful operation; may need to buffer intermediate data |

Factors affecting speed include source size, per-element compute cost, source splittability (`Spliterator.trySplit`), number of matching elements, intermediate buffering, fork/join scheduling, and actual CPU resources.

### When to consider findAny instead of findFirst?

If the task is truly "find **any** matching element" and multiple matches exist, `findAny` lets the Stream stop once a branch finds a match without proving it is "first" in encounter order. This **can** help on large sources and parallel execution. Do not promise speedup for all sources or conditions.

### When should parallel not be used?

If the source is small, each mapper is very cheap, or output requires actions to execute sequentially via `forEachOrdered`, orchestration overhead may exceed any savings.

If the work is primarily blocking I/O or bottlenecked by a shared resource, do not assume `parallelStream` is the right fit. Use a concurrency model designed around resources, task limits, and error handling.

In Java, parallel Streams typically leverage the runtime's fork/join mechanism; do not assume each element gets its own thread or bake thread names into business logic.

## 15. Complete example: selecting and displaying tasks in order

A task management system holds a list in **input order**, where each task has an ID, priority, and ready flag. Requirements:

1. Select the **first ready task in input order**.
2. When priority does not matter, select **any ready task**.
3. If the **highest-priority ready task** is needed, define sorting and tie-break criteria.
4. Print the list of ready task IDs **in exact input order** and collect them into a List.

Standalone Java 17+ program:

```java
import java.util.Comparator;
import java.util.List;
import java.util.Optional;

public class ParallelStreamOrderDemo {
    record Task(String id, int priority, boolean ready) {}

    public static void main(String[] args) {
        List<Task> tasks = List.of(
                new Task("T01", 5, false),
                new Task("T02", 2, true),
                new Task("T03", 9, true),
                new Task("T04", 7, false),
                new Task("T05", 9, true)
        );

        // 1. Select the first element in the List matching the condition.
        Task firstReady = tasks.parallelStream()
                .filter(Task::ready)
                .findFirst()
                .orElseThrow();
        System.out.println("First ready: " + firstReady.id());
        // First ready: T02

        // 2. Allow any ready element.
        Optional<Task> anyReady = tasks.parallelStream()
                .filter(Task::ready)
                .findAny();

        anyReady.ifPresent(task ->
                System.out.println("Any ready: " + task.id()));
        // Could be T02, T03, or T05.

        // 3. Select the highest-priority task; tie-break by ascending ID.
        Task highestPriority = tasks.parallelStream()
                .filter(Task::ready)
                .sorted(
                        Comparator.comparingInt(Task::priority)
                                .reversed()
                                .thenComparing(Task::id)
                )
                .findFirst()
                .orElseThrow();
        System.out.println("Highest priority: " + highestPriority.id());
        // Highest priority: T03

        // 4. forEachOrdered preserves action order on a List source.
        System.out.println("Ready IDs in input order:");
        tasks.parallelStream()
                .filter(Task::ready)
                .map(Task::id)
                .forEachOrdered(System.out::println);
        // T02
        // T03
        // T05

        // 5. Collect a List for further use instead of writing into a shared List.
        List<String> readyIds = tasks.parallelStream()
                .filter(Task::ready)
                .map(Task::id)
                .toList();

        System.out.println(readyIds); // [T02, T03, T05]

        // 6. forEach does not promise print order.
        tasks.parallelStream()
                .filter(Task::ready)
                .map(Task::id)
                .forEach(id -> System.out.println("Unordered action: " + id));
        // Three actions are executed; order is not guaranteed.
    }
}
```

Contract analysis:

1. `List.of(...)` creates a source with encounter order by element position.
2. `filter(Task::ready)` preserves the relative order of remaining tasks.
3. `findFirst` deterministically chooses `T02` from the ordered source; `findAny` only guarantees choosing one of the ready tasks.
4. The `sorted` step for highest priority uses descending priority and ascending ID as tie-breaker; since `T03` and `T05` both have priority 9, `T03` is chosen.
5. `forEachOrdered` prints IDs in encounter order, even though intermediate steps may run in parallel.
6. `toList` produces an ordered result List; `forEach` does not promise print order even on the same data.

If the task list were sourced from a `HashSet` instead of a `List`, **input order is no longer part of the source contract**. In that case, "first in input order" must be solved by retaining an ordered source or storing input index/timestamp and sorting intentionally.

## 16. Common pitfalls

| Symptom | Cause | How to fix |
| --- | --- | --- |
| `parallelStream().forEach(...)` prints backwards or out of order | `forEach` does not promise action order | Use `forEachOrdered` when the source has encounter order and actions must be ordered |
| `findAny` picks different elements across runs | Contract permits selecting any matching element | Use `findFirst`/`min`/`max` when a deterministic selection criterion exists |
| `findFirst` does not return the "smallest" | "First" does not mean "smallest" | Use `min` or `sorted` with the right comparator |
| `forEachOrdered` on `HashSet` gives unexpected order | Source lacks encounter order | Choose an ordered source or sort beforehand |
| Calling `unordered()` before `findFirst` gives unstable results | Pipeline dropped its order constraint | Remove `unordered()` if source-first is required |
| Logs inside `map` appear scrambled despite `forEachOrdered` at the end | Only the terminal action is order-constrained | Do not place mandatory side effects inside mapper/peek |
| `ArrayList` loses elements during `forEach(shared::add)` | Multiple threads concurrently mutate a non-thread-safe List | Use `toList`/`collect` or a dedicated concurrent container |
| `counter++` produces wrong counts | Race condition on shared state | Use `count`, reduce operations, or `LongAdder` when genuinely needed |
| `findFirst` returns `Optional.empty()` | No elements survive filtering | Handle with `ifPresent`, `orElse`, or `orElseThrow` as required |
| `findFirst` throws `NullPointerException` | The selected element is null | Filter or handle nulls before the terminal operation |
| Parallel `findFirst` is slower than sequential | Coordination needed to preserve encounter order, small source, or low cost | Measure in practice; consider `findAny` if business logic allows |
| Cannot reuse a Stream after a terminal operation | The Stream has already been consumed | Create a new Stream from a re-traversable source |

## 17. Practice exercises

Given a list in input order:

```java
record Job(String code, int duration, boolean eligible) {}

List<Job> jobs = List.of(
        new Job("J01", 5, false),
        new Job("J02", 7, true),
        new Job("J03", 3, true),
        new Job("J04", 9, false),
        new Job("J05", 3, true)
);
```

**Tasks:**

1. Use `parallelStream`, `filter`, and `findFirst` to get the first `eligible` job in input order.
2. Use `findAny` to get any `eligible` job. List all IDs that could be returned instead of predicting one fixed ID.
3. Compare `forEach` and `forEachOrdered` when printing the IDs of `eligible` jobs.
4. Find the `eligible` job with the smallest `duration`; on ties, choose the job with the smaller `code`.
5. After adding `unordered()` before `findFirst`, is `J02` still guaranteed to be chosen? Explain.
6. Do not use `forEach` to add into a shared `ArrayList`. Collect the codes of `eligible` jobs into a List preserving input order.

### Reference solutions

```java
Job first = jobs.parallelStream()
        .filter(Job::eligible)
        .findFirst()
        .orElseThrow();
System.out.println(first.code()); // J02

Optional<Job> any = jobs.parallelStream()
        .filter(Job::eligible)
        .findAny();
// Could be J02, J03, or J05.

jobs.parallelStream()
        .filter(Job::eligible)
        .map(Job::code)
        .forEach(System.out::println);
// Print order is not guaranteed.

jobs.parallelStream()
        .filter(Job::eligible)
        .map(Job::code)
        .forEachOrdered(System.out::println);
// J02, J03, J05 in order.

Job shortest = jobs.parallelStream()
        .filter(Job::eligible)
        .min(Comparator.comparingInt(Job::duration)
                .thenComparing(Job::code))
        .orElseThrow();
System.out.println(shortest.code()); // J03

List<String> orderedCodes = jobs.parallelStream()
        .filter(Job::eligible)
        .map(Job::code)
        .toList();
System.out.println(orderedCodes); // [J02, J03, J05]
```

`J03` and `J05` both have `duration == 3`; the ascending `code` tie-break selects `J03`. `unordered()` drops the guarantee on the List's first element, so `findFirst` after it does not necessarily choose `J02`.

**Extended experiment:** Call `findFirst` and `findAny` on a `HashSet<Job>` and analyze why you must not rely on the Set's print order. If deterministic selection is needed, define a comparator and use `min`/`max` or sort as required.

## 18. Terminal operation selection checklist

Before writing a parallel pipeline, ask yourself:

1. **Does the source have encounter order?** If not, is "first" even defined?
2. **Do you need any matching element or the first element?** Choose `findAny` or `findFirst` accurately.
3. **Do you only need to know if a match exists?** Prefer `anyMatch` over finding and checking an Optional.
4. **Do you need an action on every element?** Use `forEach` if actions are independent and order does not matter.
5. **Do you need ordered action execution?** Use `forEachOrdered` with an ordered source, while weighing coordination overhead.
6. **Do you need a result Collection?** Use `toList`, `collect`, or an appropriate collector instead of an external mutable List.
7. **Do lambdas mutate the source or read/write shared state?** Remove unnecessary side effects and design thread-safe handling when genuinely needed.
8. **Did you call `unordered()` or `sorted()`?** Re-verify what "first" and ordering mean in the pipeline.
9. **Can the source contain nulls or be empty?** Define explicit `Optional`/null handling policies.
10. **Do you have performance evidence?** Compare sequential and parallel with real data, terminal operations, and sources; do not guess from method names.

## Takeaway

**Parallel** mode changes how work may be executed, yet it does not automatically strip **encounter order**. On an ordered Stream, `findFirst` chooses the first surviving element after the pipeline; `findAny` is allowed to pick any matching element. `forEach` does not promise action order when parallel, while `forEachOrdered` runs actions in encounter order without guaranteeing upstream mappers execute in that order.

Do not use `unordered()` when business logic requires source order; do not use `forEach(sharedList::add)` to gather data into a non-thread-safe mutable structure. Choose `min`/`max` for extrema, `toList`/`collect` for result collections, and `count`/`reduce` for aggregations. Keep pipelines stateless and non-interfering, and optimize with parallelism only after verifying result correctness.