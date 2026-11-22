# Choosing Between Loops and Streams Based on the Problem

The Java Stream API helps describe how to **transform, filter, and aggregate data** in a declarative pipeline. A `for` or `while` loop allows direct control over every execution step. Both are appropriate tools in Java; the best choice depends on **the problem, the extent of state mutation, ordering requirements, and performance measurement**.

In this Stream API overview topic, the goal is to know when to write a `filter → map → reduce/collect` pipeline, when to keep a loop, and how to evaluate the choice using concrete criteria. Techniques such as `groupingBy`, custom collectors, `Spliterator`, parallel processing, and Stream Gatherers expand what Streams can do, yet do not make Streams inherently better than loops.

## 1. Two ways to express the same processing

Suppose an e-commerce application needs the IDs of orders that are **paid** and have a value of **1,000,000 VND or more**, preserving their original order in the list.

The complete example below uses Java 17 or later (because of `record` and `Stream.toList()`):

```java
import java.util.ArrayList;
import java.util.List;

public class LoopVsStream {
    record Order(String id, String customerId, long totalVnd, boolean paid) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
            new Order("O-01", "C-01", 1_500_000, true),
            new Order("O-02", "C-02",   800_000, true),
            new Order("O-03", "C-01", 2_000_000, false),
            new Order("O-04", "C-03", 1_200_000, true)
        );

        // Approach 1: loop - describe each processing step.
        List<String> idsByLoop = new ArrayList<>();
        for (Order order : orders) {
            if (order.paid() && order.totalVnd() >= 1_000_000) {
                idsByLoop.add(order.id());
            }
        }

        // Approach 2: Stream - describe the chain of transformations.
        List<String> idsByStream = orders.stream()
            .filter(Order::paid)
            .filter(order -> order.totalVnd() >= 1_000_000)
            .map(Order::id)
            .toList();

        System.out.println(idsByLoop);              // [O-01, O-04]
        System.out.println(idsByStream);            // [O-01, O-04]
        System.out.println(idsByLoop.equals(idsByStream)); // true
    }
}
```

In the loop approach, the developer actively checks the condition and adds each element to a result list. In the Stream approach, the operations express the intent: **filter matching orders → extract order IDs → build a list**. With an ordered `List` source and a sequential pipeline as shown, both approaches produce results in the same order.

The important difference lies in the **processing model**, not the ability to solve the problem. Loops suit complex control flow; Streams are often clearer when the task is a chain of operations over data.

## 2. Understand the pipeline before deciding

A Stream pipeline consists of three parts:

1. **Data source**: `list.stream()`, `Arrays.stream(array)`, `Files.lines(path)`, ...
2. **Intermediate operations**: `filter`, `map`, `flatMap`, `distinct`, `sorted`, ... return a new Stream; most are evaluated *lazy*.
3. **Terminal operation**: `toList`, `collect`, `count`, `sum` (on primitive streams), `reduce`, `findFirst`, `anyMatch`, `forEach`, ... triggers the processing.

```text
Source                Intermediate (lazy)                 Terminal
List<Order>  ──>  filter(paid) ──> mapToLong(totalVnd)  ──>  sum()
                         │                │                  │
                  select elements   change data type   compute result
```

Example of only constructing a pipeline without **running the filter yet**:

```java
var pipeline = orders.stream()
    .filter(Order::paid)
    .map(Order::id);

// No terminal operation yet, so elements have not been processed by filter/map.
List<String> paidIds = pipeline.toList(); // Now the pipeline is consumed.
```

Each Stream can be used for only a single consumption; to run another operation, create a new Stream from the source. With operations such as `sorted` or `distinct`, a Stream may need to store internal state/buffers. "Lazy" does not mean always using constant memory or always finishing one element completely before moving to the next.

## 3. Problem-based decision matrix

| Problem indicator | Usually preferred | Reason |
| --- | --- | --- |
| Filtering, mapping, transforming a set of elements into a new result | **Stream** | The pipeline clearly expresses `filter`, `map`, `collect`, or `toList`. |
| Counting, finding matching values, aggregating with a built-in operation | **Stream or loop** | `count`, `anyMatch`, `mapToLong().sum()`, and `reduce` are concise; a loop is also very clear for simple math. |
| Grouping data, computing statistics by key | **Stream** when `groupingBy` is clear | Collectors encapsulate grouping; if state-update policies are complex, a loop can be easier to read. |
| Needing element indices, mutating an array/list in place, or coordinating multiple assignments | **Loop** | Index control and state-mutating steps are the core of the problem. |
| Needing `break` / `continue` / `return` across multiple branches or stopping after multiple actions | **Loop** | Explicit control flow; if only checking "does one exist?" or "get the first one?", `anyMatch`/`findFirst` also fit well. |
| Computation depending on previous elements' results (running balance, state machine) | **Loop** in basic cases | Sequential state can be clearer in a loop; advanced Stream approaches must be evaluated separately. |
| Processing a source with resources that must be closed, such as `Files.lines` | **Both**, with proper resource management | When using a file-backed Stream, it must be closed with `try-with-resources`. |
| Very hot paths, huge datasets, sensitive to allocation/boxing | **Measure before deciding** | Stream overhead can matter, though real optimization also depends on JVM, data source, operations, and style. |
| Independent CPU-bound computation on sufficiently large data | **Consider parallel Stream** after benchmarking | Parallelism carries overhead and constraints on state, ordering, and execution environment. |

The matrix is a starting point, not a rigid rule. If a Stream pipeline has to rely on tricks to simulate `break` or update external variables, a loop usually expresses the intent better.

## 4. Typical scenarios

### 4.1. Filter, transform, and return a result set: Streams are often readable

From the `orders` list in the first example, compute the total amount of paid orders:

```java
long totalPaidVnd = orders.stream()
    .filter(Order::paid)
    .mapToLong(Order::totalVnd)
    .sum();
```

Here `mapToLong` creates a `LongStream` to sum directly with primitive `long`, avoiding allocating many `Long` objects as would happen through `Stream<Long>`. A loop is still a good choice if the aggregation has only one short condition:

```java
long totalPaidVnd = 0L;
for (Order order : orders) {
    if (order.paid()) {
        totalPaidVnd += order.totalVnd();
    }
}
```

Both snippets describe the same conditional sum. Choose the style your team reads faster and modifies with fewer bugs. If monetary data requires decimal fractions or values that could exceed `long` limits, choose an appropriate numeric model (such as `BigDecimal`) rather than relying on Stream syntax.

### 4.2. Searching and short-circuiting: examine stopping conditions clearly

If you only need to know **whether there is any unpaid order**, `anyMatch` is both short and able to stop immediately upon finding a match:

```java
boolean hasUnpaidOrder = orders.stream()
    .anyMatch(order -> !order.paid());
```

If you need **the first unpaid order according to list order**:

```java
var firstUnpaid = orders.stream()
    .filter(order -> !order.paid())
    .findFirst(); // Optional<Order>; may be empty.
```

A loop also supports early stopping:

```java
Order firstUnpaid = null;
for (Order order : orders) {
    if (!order.paid()) {
        firstUnpaid = order;
        break;
    }
}
```

When early stopping also involves updating multiple variables, calling multiple conditional actions, or reporting errors depending on position, a loop is usually easier to reason about. Do not replace `break` with `forEach` relying on a mutable flag outside the lambda; `forEach` does not provide a `break` mechanism like a loop.

For an **ordered** Stream source, `findFirst` respects the first element in encounter order. `findAny` does not commit to picking the first element, especially when running in parallel.

### 4.3. Grouping and statistics: Streams keep focus on the result

Example of counting orders by customer:

```java
import java.util.Map;
import java.util.stream.Collectors;

Map<String, Long> numberOfOrdersByCustomer = orders.stream()
    .collect(Collectors.groupingBy(
        Order::customerId,
        Collectors.counting()
    ));
```

If you only need to group elements, `groupingBy(Order::customerId)` builds a map from customer ID to list of orders. For specialized aggregations, you can consider other built-in collectors or a **custom collector**. However, a loop with `Map.merge` is sometimes shorter and clearer when only counting:

```java
Map<String, Long> counts = new java.util.HashMap<>();
for (Order order : orders) {
    counts.merge(order.customerId(), 1L, Long::sum);
}
```

Key iteration order for `HashMap` and the map returned by `groupingBy` by default is **not guaranteed**. If the output has ordering constraints, express those constraints explicitly.

### 4.4. State depending on previous elements: loops are usually more natural

An e-wallet system receives balance changes `[+100, -25, +40]` and must return **the running balance after each transaction**, yielding `[100, 75, 115]`.

```java
List<Integer> changes = List.of(100, -25, 40);
List<Integer> runningBalances = new ArrayList<>();

int balance = 0;
for (int change : changes) {
    balance += change;
    runningBalances.add(balance);
}

System.out.println(runningBalances); // [100, 75, 115]
```

`reduce(0, Integer::sum)` produces only the **final total** (`115`), not the intermediate balances. Forcing this stateful scan into `map` using a mutable variable outside the lambda harms readability and breaks parallel safety.

If the project genuinely needs a stateful scan pipeline, you can explore Stream Gatherers (on supported JDK versions) and weigh the complexity against a loop. For a small problem like the one above, a loop has a clear advantage.

### 4.5. Working with indices and mutating data in place: prefer loops

An example of in-place computation on an array, where **index position** is part of the requirement:

```java
int[] scores = {10, 20, 30};
for (int i = 0; i < scores.length; i++) {
    scores[i] += i; // [10, 21, 32]
}
```

`IntStream.range(0, scores.length)` can also represent indices, but if the entire goal is to modify each position of the same array, a loop is usually shorter and more direct. When transforming data into a **new array**, a Stream can fit well:

```java
int[] doubled = java.util.Arrays.stream(scores)
    .map(score -> score * 2)
    .toArray();
```

### 4.6. Data from files: consider resource management and memory

`Files.lines` provides a Stream that reads file lines. It holds an I/O resource and therefore must be closed, even if the pipeline throws an exception:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

Path path = Path.of("logs.txt");
try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
    long nonEmptyLineCount = lines
        .filter(line -> !line.isBlank())
        .count();

    System.out.println(nonEmptyLineCount);
}
// Context containing this snippet must handle or declare throws IOException.
```

Only call `toList()` when you actually need to retain the lines in memory. If you need to process line by line and stream output progressively elsewhere, a loop with `BufferedReader` can express reading, writing, error handling, and early stopping more clearly.

Note: `Stream.toList()` creates an **unmodifiable** list (calling `add` throws `UnsupportedOperationException`). When a mutable list is needed, state that requirement explicitly:

```java
List<String> mutableIds = orders.stream()
    .map(Order::id)
    .collect(java.util.stream.Collectors.toCollection(ArrayList::new));
```

## 5. Performance: evaluate real cost, do not guess from syntax

You cannot conclude "Streams are always slow" or "Streams are always fast". For the same operation, results depend on input data, JDK/JVM, code hotness, JIT optimizations, allocations, element types, and pipeline structure.

When performance matters, consider:

- **Pipeline creation and lambda invocation overhead:** can be noticeable for tiny operations repeated inside a hot path.
- **Boxing/unboxing:** `Stream<Integer>` can incur object allocation overhead; for numeric computations, consider `IntStream`, `LongStream`, `DoubleStream`.
- **Stateful operations:** `sorted` or `distinct` may require extra memory; `sorted` typically has to collect many elements before producing output.
- **Collecting data:** `toList` retains results in memory, whereas a loop or streaming output can reduce stored memory depending on the problem.
- **Short-circuiting:** `findFirst`, `anyMatch`, `limit` can reduce elements read; actual effectiveness also depends on operation order and source.
- **I/O, network, and database:** external wait times usually dwarf syntactic differences between a loop and a Stream.

When deciding for a critical path, write two **semantically equivalent** versions, use representative data, and benchmark with a proper tool like **JMH** after JVM warm-up. Do not measure with a single `System.nanoTime()` call and generalize to all cases. In particular, verify that both versions process the same data, preserve the same order if order is required, and do not skip work that makes a benchmark look artificially fast.

### Should you call `parallelStream()`?

Parallel Streams can help when the element count is large enough, per-element work is relatively heavy, independent, side-effect-free, and the source splits efficiently. They are **not automatically faster** than sequential Streams or loops. Splitting/merging, synchronization, ordering overhead, and shared CPU contention can make results worse.

The following example only illustrates an aggregation that is semantically parallelizable:

```java
long totalPaid = orders.parallelStream()
    .filter(Order::paid)
    .mapToLong(Order::totalVnd)
    .sum();
```

With just a few orders like in the example, there is no practical reason to use parallelism. Never use `parallelStream().forEach(...)` to concurrently add elements to a shared `ArrayList`: that concurrent mutation is unsafe. If you must run in parallel, prefer proper reductions/collectors and verify ordering requirements. When fine control over data splitting is needed, `Spliterator` is a related concept, though not the default solution for ordinary pipelines.

## 6. Common mistakes when converting loops to Streams

| Symptom | Why it is a problem | Better approach |
| --- | --- | --- |
| `stream().filter(...).map(...);` with no terminal operation | Intermediate pipeline is never consumed | Add `toList`, `collect`, `count`, `forEach`, or a suitable terminal operation. |
| `stream.forEach(x -> result.add(transform(x)))` | Mutating an external list inside a lambda obscures intent; unsafe in parallel | Use `map(...).toList()` when a new result collection is needed. |
| Replacing every loop with a Stream even when `break` and multi-step updates are needed | Control flow becomes convoluted | Keep a loop if imperative control is the main requirement. |
| Using `peek` to execute business logic | `peek` is intended for observation/debugging; certain optimizations may skip invoking it | Move transformations to `map`, use an appropriate terminal operation, or use a loop with explicit side effects. |
| Calling two terminal operations on the same Stream | A Stream is consumed once | Recreate a fresh Stream from the source for the next calculation. |
| Assuming `toList()` returns a mutable list | The list returned by `Stream.toList()` cannot add/remove elements | Use `Collectors.toCollection(ArrayList::new)` if a mutable list is needed. |
| Enabling parallelism and writing to shared variables/collections | Can cause race conditions or wrong results | Avoid shared state; use safe collect/reduce operations and measure performance. |

Example of **unnecessary side effects** and its replacement:

```java
// Hard to scale to parallel processing, because it updates a list outside the pipeline.
List<String> ids = new ArrayList<>();
orders.stream()
    .filter(Order::paid)
    .forEach(order -> ids.add(order.id()));

// Directly expresses the output data, without mutating external state.
List<String> paidIds = orders.stream()
    .filter(Order::paid)
    .map(Order::id)
    .toList();
```

`forEach` is not wrong when the actual goal is **performing an action per element** (such as printing); the problem is using it to emulate `map + collect` via external state. When action order is required, note that parallel Stream `forEach` does not guarantee encounter order; `forEachOrdered` has different ordering semantics and can negate parallel gains.

## 7. Practical decision workflow

To choose quickly on a new problem, follow this sequence:

1. **Write down inputs and outputs clearly.** If the result is "filter → transform → return a set of values" or a standard aggregation, try a Stream first.
2. **Identify state dependencies and control flow.** If you must manage indices, previous-element state, multiple `break`/`continue` branches, or in-place updates, try a loop first.
3. **Check ordering and short-circuit constraints.** Choose `findFirst` instead of `findAny` when you genuinely need the first element; use `anyMatch` if you only need a yes/no answer.
4. **Identify resources and data size.** Close I/O-backed Streams; avoid collecting every element if you do not need to retain them.
5. **Compare readability, correctness, and local performance.** Pick whichever is clearest for the team; optimize hot paths only after measuring.

A helpful rule of thumb: try describing the problem with verbs. If the natural description is "**filter** records, **map** fields, **group** by key, **sum** totals", Stream is a strong candidate. If the description is "**iterate until**, **update state**, **step back to a prior index**, **stop on this branch**", a loop is usually more fitting.

## 8. Self-check exercises

1. Given a list of students, filter students with a score of 8 or higher and extract their email list. Write both a loop and a Stream, and explain which expresses the result more clearly.
2. Given an array of transactions sorted by time, find the first failed transaction. Compare `for + break` with `filter + findFirst`. What happens when there is no failed transaction?
3. Given a sequence of temperature changes, produce the sequence of **cumulative temperatures after each step**. Why is `reduce` insufficient to return all intermediate values?
4. Given 10 million integers, compute the sum of even numbers. Test a loop, sequential `IntStream`, and parallel `IntStream` with a sound benchmark; record correctness, memory, and execution cost.
5. Given a large log file, count lines containing a keyword. Write proper resource-closing code and explain why creating a `List<String>` of the entire file may be unnecessary.

**Remember:** Streams excel when a problem is **a chain of data transformations expressible with declarative operations**. Loops excel when a problem demands **explicit control flow and state**. Knowing how to switch between the two lets you leverage the Java Stream API while keeping code clear, correct, and maintainable.
