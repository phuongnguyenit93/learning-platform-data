# `forEachOrdered()` and the Cost of Maintaining Order in Java Stream

In Java Stream, `parallel()` allows element processing to be split into multiple tasks. However, a program sometimes still needs to **perform actions in the exact encounter order**: outputting reports in input order, writing lines to the console, or applying a sequence of order-dependent operations.

`forEachOrdered()` is the terminal operation for that requirement. It guarantees that **the final action** is executed in encounter order **when the stream has an encounter order**. In return, the framework may have to coordinate, wait, or buffer results; this overhead can sometimes significantly reduce the benefits of parallel processing.

Key point: **`forEachOrdered()` does not mean the entire pipeline ran sequentially**. `map()`, `filter()`, and upstream work can still run in parallel; ordering is enforced on the actions of `forEachOrdered()`.

## 1. Encounter order and execution order are two different concepts

**Encounter order** is the logical order of elements defined by the source or operations in the pipeline. For example, `List.of("A", "B", "C")` has encounter order `A → B → C`.

**Execution order** is the actual schedule on which callbacks run across processing threads. A parallel stream might execute `map("C")` before `map("A")`, yet assemble the result as `A, B, C` if the terminal operation must preserve order.

```text
Ordered List source:        A ------ B ------ C ------ D
Possible map schedule:      C, A, D, B  (no guarantee)
.toList() result:          [A, B, C, D]
forEachOrdered actions:     A, B, C, D
```

The "possible map schedule" line only illustrates **one possibility**, not a fixed JVM schedule. An ordered parallel stream still has encounter order, while which thread or at what time callbacks execute is a separate matter.

Related sources and operations:

| Source or operation | Encounter order guarantee |
| --- | --- |
| `List.stream()`, `List.parallelStream()` | Yes; follows list element order |
| `Arrays.stream(array)` | Yes; follows index order |
| `LinkedHashSet.stream()` | Yes; follows defined iteration order |
| `HashSet.stream()` | No guaranteed encounter order |
| `stream.sorted()` | Establishes a sorted order for downstream results |
| `stream.unordered()` | Drops the requirement to preserve encounter order if present |

`parallel()` does not automatically destroy encounter order. Conversely, `unordered()` does not automatically enable parallelism and **does not mean random shuffling**.

## 2. `forEach()` and `forEachOrdered()`: different contracts

Both are **terminal operations**, returning `void` and accepting a `Consumer<? super T>` to perform an action for the remaining elements in the stream.

```java
void forEach(Consumer<? super T> action);
void forEachOrdered(Consumer<? super T> action);
```

These are abbreviated API signatures from `Stream<T>`, not a standalone Java program.

| Criterion | `forEach()` | `forEachOrdered()` |
| --- | --- | --- |
| Does it need an ordered stream for deterministic order? | The method itself **does not guarantee** order when running in parallel | Yes; follows encounter order if defined |
| On an ordered parallel stream | Actions may run out of encounter order | Actions must occur in encounter order |
| Threads executing actions | May be multiple threads | May be executed by different threads; no fixed thread promised |
| Relationship between two consecutive actions | No ordering/happens-before guarantee in encounter order from the method | Action of earlier element **happens-before** action of next element |
| Potential cost | Fewer ordering coordination constraints | May have to wait/synchronize/buffer to preserve order |
| Purpose | Perform action when order does not matter | Perform action when output order is required |

With a sequential ordered stream, `forEach()` is often observed in traversal order. However, when designing code that may switch to parallel, do not treat that as a guarantee of `parallelStream().forEach()`. If a **clear ordering contract** is needed, use `forEachOrdered()` or design the output using `toList()`/`collect()`.

### Example without a fixed result

```java
List<Integer> nums = List.of(1, 2, 3, 4);
nums.parallelStream().forEach(System.out::println);
```

This is a snippet inside a method requiring `import java.util.List;`. All four numbers can be printed if no exception occurs, but **the print order is nondeterministic**. One run might show `3, 2, 4, 1`; another might show `1, 2, 3, 4`. Do not write tests expecting a specific print schedule.

Using:

```java
nums.parallelStream().forEachOrdered(System.out::println);
```

with the same `List` will print `1`, `2`, `3`, `4` in encounter order, one number per line.

## 3. Runnable Java 17+: ordered result despite parallel mapping

Save the entire program below as `ForEachOrderedDemo.java`:

```java
import java.util.List;

public class ForEachOrderedDemo {
    public static void main(String[] args) {
        List<Integer> numbers = List.of(4, 1, 3, 2);

        System.out.println("source = " + numbers);

        List<Integer> mapped = numbers.parallelStream()
                .map(n -> n * 10)
                .toList();
        System.out.println("mapped = " + mapped);

        System.out.println("ordered actions:");
        numbers.parallelStream()
                .map(n -> n * 10)
                .forEachOrdered(n -> System.out.println("value = " + n));

        System.out.println("sorted actions:");
        numbers.parallelStream()
                .sorted()
                .forEachOrdered(n -> System.out.println("value = " + n));

        int first = numbers.parallelStream()
                .findFirst()
                .orElseThrow();
        System.out.println("first = " + first);

        List<Integer> firstTwo = numbers.parallelStream()
                .limit(2)
                .toList();
        System.out.println("firstTwo = " + firstTwo);
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 ForEachOrderedDemo.java
java ForEachOrderedDemo
```

**Deterministic stdout:**

```text
source = [4, 1, 3, 2]
mapped = [40, 10, 30, 20]
ordered actions:
value = 40
value = 10
value = 30
value = 20
sorted actions:
value = 1
value = 2
value = 3
value = 4
first = 4
firstTwo = [4, 1]
```

**Detailed explanation:**

1. `numbers` is a `List` with encounter order `4, 1, 3, 2`.
2. `map(n -> n * 10)` may run on multiple threads on any schedule, yet `toList()` on an ordered stream preserves logical order and returns `[40, 10, 30, 20]`.
3. `forEachOrdered()` forces the four **print actions** to follow the order of values encountered after `map`. It **does not** force `map` calls to run in chronological order `4, 1, 3, 2`.
4. `sorted()` replaces encounter order with `1, 2, 3, 4`. `forEachOrdered()` respects that new order.
5. `findFirst()` returns the first element in encounter order, `4`; `limit(2)` keeps the first two elements `[4, 1]`. They also preserve ordered semantics even though they may execute in parallel.

The program creates **a new stream** for each terminal operation. After `toList()`, `forEachOrdered()`, or `findFirst()`, that stream object is not reused.

## 4. Which part does the happens-before guarantee apply to?

The documentation for `forEachOrdered()` states: the execution of the action for **one element** *happens-before* the execution of the action for **the next element** in encounter order.

Example:

```java
List<Integer> values = List.of(1, 2, 3);
values.parallelStream()
        .forEachOrdered(n -> System.out.println("item " + n));
```

The action `println("item 1")` must happen before `println("item 2")`, and `2` before `3`. However, Java **does not promise every action runs on the same thread**; the framework may choose different threads for elements.

Do not extend this guarantee to things that are not promised:

- There is no guarantee that **upstream** `map()`, `filter()`, or `peek()` all run in encounter order.
- There is no guarantee on exactly how many threads participate in processing the source.
- There is no guarantee that `parallelStream()` will be faster simply because preceding work can be parallelized.
- If the action **only submits an asynchronous task** to an executor and returns, `forEachOrdered()` may guarantee **submission/scheduling** order, but **does not automatically guarantee** that the async tasks finish in that order.

Example of the last difference: if `action` calls `executor.submit(task)`, tasks can run concurrently after submission. To ensure task results complete in order, you need an additional mechanism such as a dependency chain, a sequential queue, or collecting results first and publishing them in order.

### Does `forEachOrdered()` make all side effects safe?

No. It constrains the order between **the actions of that terminal operation itself**. If an earlier `map` updates a shared `ArrayList`, or other code concurrently modifies that data, race conditions can still happen.

Bad design example:

```java
List<Integer> shared = new ArrayList<>();
List<Integer> source = List.of(1, 2, 3, 4);

source.parallelStream()
        .map(n -> {
            shared.add(n); // WRONG: updating a shared ArrayList upstream.
            return n * 2;
        })
        .forEachOrdered(System.out::println);
```

This is a snippet **to point out a bug**, requiring `java.util.List` and `java.util.ArrayList`, not for real applications. The guarantee of `forEachOrdered` does not turn `shared.add(n)` inside `map` into a synchronized/safe operation.

## 5. Where does the cost of maintaining encounter order come from?

When actions do not need order, source partitions can be processed and consumed more independently. When actions must be ordered, the framework must ensure that a later element **does not execute its action before an earlier element**, even if the later element has already finished computing.

Possible sources of overhead:

1. **Waiting for earlier elements:** a task finishes computing element `C` but must wait for `A` and `B` to complete to emit in order.
2. **Coordination across branches:** the framework must track how to merge segments with encounter order, unable to arbitrarily emit results as soon as one branch is ready.
3. **Temporary buffering:** some results may need to be held until earlier parts finish; this creates additional memory demand.
4. **Limiting output parallelism:** if the action is very slow (e.g., writing to a single output channel), forcing actions in order can become a bottleneck and negate upstream computation gains.
5. **Parallelism management overhead:** for small pipelines, splitting, coordinating, and merging costs can exceed the time of individual `map` or `filter` steps.

**There is no fixed slowdown factor.** Cost depends on source/spliterator, element count, splitting strategy, `map` weight, short-circuiting, OS, JVM, and the type of final side effect. You cannot conclude `forEachOrdered` is always slower than `forEach` in every measurement, nor can you conclude it turns the entire pipeline sequential.

### Semantic example of "waiting for earlier elements"

```text
Encounter order:     A -> B -> C -> D
Upstream finished:   C, D, B, A
forEachOrdered:      A, B, C, D

Even though C and D are ready, they cannot run their action
before A and B.
```

The diagram is a conceptual example, not describing a specific algorithm that the JDK is required to use.

## 6. Comparing three strategies when ordered output is needed

### Approach 1 — sequential from start to finish

```java
source.stream()
        .map(this::transform)
        .forEachOrdered(this::writeResult);
```

This approach is simple when work is light, data is small, or the final action takes most of the time. The snippets assume `source`, `transform`, and `writeResult` are application-defined; not a standalone Java program.

### Approach 2 — compute in parallel, emit in order with `forEachOrdered()`

```java
source.parallelStream()
        .map(this::transform)
        .forEachOrdered(this::writeResult);
```

The `transform` part can run in parallel; `writeResult` is called in encounter order. This fits when **calling the action in exact order is mandatory**, such as sending messages to a destination that does not permit out-of-order delivery.

Make sure `transform` is **stateless, non-interfering**, and does not write to unsafe shared state. For I/O actions, you need error-handling policies, retries, and handling of partially written state.

### Approach 3 — collect results in order, then handle I/O separately

```java
List<Result> results = source.parallelStream()
        .map(this::transform)
        .toList();

results.forEach(this::writeResult);
```

This snippet requires `java.util.List` and application-defined `Result`, `transform`, and `writeResult`. `toList()` preserves encounter order when upstream is ordered; `forEach` on a list traverses in list order. This cleanly separates **transformation** from **side effects**, making testing and boundary failure handling easier.

However, it must store **the entire result list** before writing, so it can consume significant memory; it is not optimal for every large source. Meanwhile, `forEachOrdered()` may also need internal buffering, though it does not necessarily hold all results as a long-lived list kept by the application.

Which approach to choose depends on the requirement: **needing actions invoked in order**, **needing all results to validate before writing**, or **just wanting to process a simple sequential data stream**.

## 7. When should ordering requirements be dropped?

If action order **has no meaning**, such as independent idempotent and thread-safe updates, `forEach()` can avoid unnecessary ordering constraints.

```java
source.parallelStream()
        .forEach(this::processIndependent);
```

This is a snippet in a class with application-defined `source` and `processIndependent`. Before using it, ensure each action is independent, data is protected against concurrent writes, no before/after ordering is required, and error handling has a clear policy.

Do not use `parallelStream().forEach(sharedArrayList::add)` to build a result list, because `ArrayList` is not thread-safe; even if replaced with a synchronized list, insertion order still depends on callback scheduling. If the goal is creating a list, use `toList()` or `collect(Collectors.toList())` instead of external side effects.

### `unordered()` is not a tool to "be fast and keep order"

```java
List<Integer> values = List.of(10, 20, 30, 40);
values.parallelStream()
        .unordered()
        .forEachOrdered(System.out::println);
```

On this pipeline, `unordered()` has already dropped the encounter-order constraint. Therefore `forEachOrdered()` **no longer has a basis to force printing `10,20,30,40`** like the original source. The call is still valid, but no specific order is guaranteed.

If deterministic ascending order is needed, you can impose order with `sorted()` on comparable data and then use `forEachOrdered()`. However, sorting also has a cost, so do not add `sorted()` just to restore an arbitrary ordering expectation.

## 8. Do not confuse with `findFirst()`, `findAny()`, `limit()`, and `toList()`

These APIs have different semantics, even though all relate to encounter order:

| API | Key guarantee |
| --- | --- |
| `forEach()` | Executes action; does not guarantee encounter order on parallel streams |
| `forEachOrdered()` | Executes action in the stream's encounter order if present |
| `toList()` | Returns a list with elements in encounter order if present; does not promise upstream callback execution order |
| `findFirst()` | Finds the first element in encounter order, if present |
| `findAny()` | Allows choosing any element |
| `limit(n)` | On an ordered stream, selects at most `n` first elements in encounter order |
| `sorted()` | Imposes a sorted order before subsequent steps |
| `unordered()` | Allows dropping the encounter-order requirement |

A `parallelStream().limit(3).forEachOrdered(action)` on an ordered list only runs the action for at most the first three elements. `limit` is placed **before** the `forEachOrdered` terminal, so element selection and action invocation order are two distinct semantic steps.

In particular, `findFirst()` and `limit()` on ordered parallel streams can also incur order-maintenance overhead. Do not enable `unordered()` just to speed up if the result needs the "first" items from input data.

## 9. When an action fails or tasks have side effects

For example, an action writes to a file and throws an exception after writing a few lines. `forEachOrdered()` does not provide transactions or rollback:

```java
results.parallelStream().forEachOrdered(this::writeResult);
```

This is an illustrative snippet; `results` and `writeResult` belong to the application. When one action fails, actions executed earlier may have already produced side effects. Do not confuse "in the right order" with "atomic" or "exactly once" in distributed systems.

If all-or-nothing updates are required, use data-source transactions, temporary files with atomic rename when appropriate, or an explicit orchestration mechanism. If actions might be retried after network errors, handle idempotency or duplicate-operation detection.

When asynchronous processing is involved, distinguish:

- **Callback invocation order:** what `forEachOrdered()` guarantees for ordered streams.
- **Executor task submission order:** can follow order when `submit` is directly inside the callback.
- **Async task completion order:** is not automatically guaranteed by `forEachOrdered()`.
- **Database/HTTP commit order:** decided by the target system and protocol.

Ordering guarantees are only meaningful when you identify **which action** needs to be ordered.

## 10. Measuring performance properly

To evaluate overhead, compare **the same work** and **the same result requirements**, avoiding skewed measurements from console printing or variable-latency network calls.

Scenarios worth measuring:

1. `source.stream().map(f).forEachOrdered(noopOrConsumer)`: sequential path.
2. `source.parallelStream().map(f).forEachOrdered(noopOrConsumer)`: parallel computation, ordered action.
3. `source.parallelStream().map(f).toList()`: parallel transformation and ordered result collection, no external action.
4. Only if **business logic does not need order**, also compare `parallelStream().forEach(action)`. Do not treat it as contract-equivalent to `forEachOrdered` if order actually matters.

Use **JMH** for benchmarking: JVM warm-up, multiple iterations, avoiding dead-code elimination, and controlling thread counts/source sizes. Measuring with a single `System.nanoTime()` around `println` usually does not reflect Stream processing performance because it is dominated by I/O, JIT, scheduler, and synchronization.

Be careful when designing benchmark consumers/no-ops: if the terminal action produces no observable effect, ensure the framework/harness does not optimize away the measurement; consume data in a JMH-supported way. For workloads with I/O, measure CPU transformation and I/O boundary cost separately before measuring total time.

**There is no universal size threshold** saying "above N elements, parallel + forEachOrdered is faster". Results depend on the cost of `f`, memory, source, downstream work, and actual core count.

## 11. Common mistakes

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| Thinking `parallelStream()` automatically loses encounter order | Parallelism is an execution mode, not dropping logical order | Distinguish ordered/unordered from sequential/parallel |
| Using parallel `forEach()` to print in source order | `forEach` does not guarantee action order | Use `forEachOrdered` on an ordered stream |
| Thinking `forEachOrdered` forces `map` to run sequentially | Ordering guarantee only constrains the terminal action | Keep upstream stateless/non-interfering |
| Assuming all actions run on one thread | JDK does not promise a fixed thread | Do not use thread identity as a contract |
| Using `forEachOrdered` to build a list via external mutable state | Unnecessary side effects, harder to test | Use `toList`/`collect` to produce results |
| Calling `unordered().forEachOrdered` and expecting original order | Encounter order was dropped | Do not call `unordered` when order is needed |
| Using `forEachOrdered` to submit tasks and expecting ordered completion | Only callback/submission order is constrained | Coordinate completion separately |
| Thinking ordered actions are transactional | I/O can fail midway, leaving partial writes | Use proper transaction/rollback/idempotency mechanisms |
| Claiming `forEachOrdered` is always slower or always faster | No universal performance guarantee | Benchmark the actual workload and order requirements |
| Reusing a Stream after terminal `forEachOrdered` | The Stream is already consumed | Create a new stream from the source for the next pass |

## 12. Self-check quiz

**Question 1.** With `List.of(3,1,2).parallelStream().forEachOrdered(System.out::println)`, in what order do the three lines appear?

**Answer:** `3`, `1`, `2`, because the list has encounter order and `forEachOrdered` obeys that order.

**Question 2.** Can you conclude that `map(n -> heavy(n))` ran in the order `3,1,2`?

**Answer:** No. It may execute on different threads and at different times; only the terminal actions are ordered by encounter order.

**Question 3.** Does `forEachOrdered()` guarantee all actions run on the same thread?

**Answer:** No. Java may use different threads; the guarantee lies in the ordering and happens-before relationship between actions.

**Question 4.** If `forEachOrdered`'s callback submits an async task and returns, are the tasks guaranteed to finish in submission order?

**Answer:** No. The scheduler may complete them on a different schedule; a separate coordination mechanism is needed.

**Question 5.** Why might `parallelStream().forEachOrdered()` not be as fast as `parallelStream().forEach()`?

**Answer:** The framework may have to wait for earlier elements, coordinate branches, buffer temporary results, and serialize observable actions to maintain order.

**Question 6.** If you only want to create a transformed list in source-list order, is it necessary to use `forEachOrdered(list::add)`?

**Answer:** No. `map(...).toList()` is usually shorter, clearer, and avoids accumulating into external state.

## Takeaways

- `forEachOrdered()` is a **terminal operation** that executes actions in **encounter order if the stream is ordered**.
- On an ordered parallel stream, actions execute in order and an earlier action **happens-before** the next action; it does **not** guarantee a fixed thread or sequential upstream processing.
- Overhead can come from **waiting, coordination, buffering, and output bottlenecks**; there is no fixed slowdown factor.
- If you only need ordered results, `toList()`/`collect()` is usually clearer than using an external accumulator with `forEachOrdered`.
- If order does not matter, `forEach()` can reduce constraints, though actions must be safe when running concurrently.
- `unordered()` drops the obligation to preserve order; do not use it if results must follow source order.
- Action invocation order differs from **async work completion order**, **I/O commit order**, and **atomicity** of operations.