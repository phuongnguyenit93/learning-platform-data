# stream, parallelStream, and Non-Interference Constraints

## 1. A Stream Is a Processing Pipeline Over a Data Source

Suppose a list contains the numbers from 1 to 10. We want to take the even numbers, square each one, and produce a result list. This work can be described as a chain of operations: source → filter → transform → collect.

`Stream` is the model that represents that processing chain. It is neither a list holding a pre-built copy of the data nor a separate execution thread in the sense of `Thread`. In technical terminology, it is important to distinguish:

- **Element stream (stream):** the flow of data passing through processing steps.
- **Execution thread (thread):** a unit of code execution in a program.

A stream can be processed sequentially or in parallel. When processing in parallel, the library may split the work across execution threads, but that does not change the programmer's responsibility: the data source and the processing functions must satisfy the stream's contract.

A pipeline—that is, a stream processing chain—has three components:

| Component | Role | Example |
| --- | --- | --- |
| Data source | Supplies the elements | A `List<Integer>` |
| Intermediate operations | Describe filtering, transforming, or organizing elements | `filter`, `map`, `sorted` |
| Terminal operation | Requests producing a result or performing a final action | `toList`, `sum`, `count`, `forEach` |

An illustrative example, placed inside a method that already has a `numbers` variable and the necessary `import` statements:

```java
List<Integer> squares = numbers.stream()
        .filter(n -> n % 2 == 0)
        .map(n -> n * n)
        .toList();
```

`filter` does not remove odd numbers from `numbers`. It selects which elements continue through the pipeline. `map` does not replace each slot of the source list with its square; it produces output values for the next step.

That is why streams are well suited for describing **the result to produce**. If you want to remove elements directly from a collection, choose an appropriate collection-modifying operation rather than modifying the source from inside a pipeline that is traversing it.

This lesson focuses on three questions: when the source is read, what sequential or parallel mode affects, and what boundaries must be respected so that reading is not interfered with.

## 2. Creating a Pipeline Does Not Mean the Source Has Already Been Traversed

Intermediate operations are evaluated lazily: calling `filter` or `map` typically only builds a description of the processing. Computing the result is requested when a terminal operation is called.

Therefore, you should not think of `source.stream()` as “taking an immediate snapshot of the entire source.” When the source is bound to traversal also depends on the source type and its `Spliterator`.

With `ArrayList` in the program below, adding an element after creating the stream but before starting the terminal operation will be reflected in the result. This is not modifying the source while the pipeline is actively running.

Save to `StreamLifecycleDemo.java`.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.stream.Stream;

public class StreamLifecycleDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("a", "bb", "ccc"));
        Stream<String> pipeline = source.stream()
                .filter(value -> value.length() >= 2)
                .map(value -> value.toUpperCase(Locale.ROOT));

        System.out.println("sizeWhenPipelineCreated=" + source.size());
        source.add("dddd");
        System.out.println("sizeBeforeTerminal=" + source.size());

        List<String> result = pipeline.toList();
        System.out.println("result=" + result);
        System.out.println("sourceAfterTerminal=" + source);

        try {
            pipeline.count();
        } catch (IllegalStateException e) {
            System.out.println("reuse=IllegalStateException");
        }

        source.add("eeeee");
        System.out.println("resultAfterLaterAdd=" + result);
        System.out.println("newStreamCount=" + source.stream().count());
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 StreamLifecycleDemo.java
java StreamLifecycleDemo
```

Stdout:

```text
sizeWhenPipelineCreated=3
sizeBeforeTerminal=4
result=[BB, CCC, DDDD]
sourceAfterTerminal=[a, bb, ccc, dddd]
reuse=IllegalStateException
resultAfterLaterAdd=[BB, CCC, DDDD]
newStreamCount=5
```

The program has three distinct points in time to separate:

```text
Create ArrayList
    ↓
Create stream and declare filter/map
    ↓
Add dddd to source before terminal operation
    ↓
Call toList: execute pipeline and receive result
    ↓
Add eeeee to source after pipeline has finished
```

When the pipeline is created, the source has three elements. Before `toList`, `dddd` is added to the source, so the result contains `DDDD`. The filtering and uppercasing steps only affect the result: the source list remains `[a, bb, ccc, dddd]`.

Afterward, adding `eeeee` does not automatically update the already created result list. To process the new state of the source, the program calls `source.stream()` again.

### A Stream Is Used for Only One Processing Pass

After the terminal operation, the pipeline has been consumed. Do not reuse it to perform a second aggregation, nor split a single stream object into two independently used branches.

In the example, calling `pipeline.count()` after `pipeline.toList()` throws `IllegalStateException`. The rule is not to reuse streams; do not build programs on the assumption that every improper reuse will definitely be detected. [Stream Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html)

Keeping the source and creating a new stream when you need to traverse again is different from keeping an already-executed stream. A stream from a regular collection also does not represent a live process that continuously tracks every subsequent update to the collection.

### What Version Does the Result in the Example Require?

`Stream.toList()` has been available since Java 16, so it works with Java 17 used in this lesson. It returns an unmodifiable list that does not allow structural modification. Do not assume you can call `result.add(...)` on that result.

If you need a list that allows adding or removing elements, you can explicitly request an appropriate result collection; the collection section below uses `Collectors.toCollection(ArrayList::new)`.

## 3. stream and parallelStream Differ in Execution Mode

`Collection.stream()` creates a sequential stream. `parallelStream()` allows requesting parallel processing; the default implementation creates a stream in parallel mode, although the `Collection` interface contract permits an implementation to return a sequential stream. You can check the actual mode using `isParallel()`. [Collection.stream and parallelStream Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html)

For the JDK collections used in this lesson:

| Call | Meaning |
| --- | --- |
| `source.stream()` | Starts in sequential mode |
| `source.parallelStream()` | Starts in parallel mode |
| `stream.parallel()` | Sets parallel processing mode for the pipeline |
| `stream.sequential()` | Sets sequential processing mode for the pipeline |
| `stream.isParallel()` | Queries the current mode, not the execution thread count |

Do not read a chain with `parallel()` in the middle and conclude “the earlier steps run sequentially, and the later steps run in parallel.” The most recently set mode applies to the execution of the entire pipeline when the terminal operation triggers processing.

### Experiment on Mode and Result Ordering

Save to `StreamExecutionModeDemo.java`.

```java
import java.util.List;
import java.util.StringJoiner;
import java.util.stream.IntStream;

public class StreamExecutionModeDemo {
    public static void main(String[] args) {
        List<Integer> source = IntStream.rangeClosed(1, 10).boxed().toList();

        System.out.println("streamParallel=" + source.stream().isParallel());
        System.out.println("parallelStreamParallel="
                + source.parallelStream().isParallel());
        System.out.println("afterSequential="
                + source.parallelStream().sequential().isParallel());
        System.out.println("afterParallel="
                + source.stream().parallel().isParallel());

        List<Integer> sequential = source.stream()
                .filter(n -> n % 2 == 0)
                .map(n -> n * n)
                .toList();
        List<Integer> parallel = source.parallelStream()
                .filter(n -> n % 2 == 0)
                .map(n -> n * n)
                .toList();

        System.out.println("sequential=" + sequential);
        System.out.println("parallel=" + parallel);
        System.out.println("sameResult=" + sequential.equals(parallel));

        StringJoiner ordered = new StringJoiner(",");
        source.parallelStream()
                .filter(n -> n % 2 == 0)
                .forEachOrdered(n -> ordered.add(n.toString()));
        System.out.println("orderedActions=" + ordered);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 StreamExecutionModeDemo.java
java StreamExecutionModeDemo
```

Stdout:

```text
streamParallel=false
parallelStreamParallel=true
afterSequential=false
afterParallel=true
sequential=[4, 16, 36, 64, 100]
parallel=[4, 16, 36, 64, 100]
sameResult=true
orderedActions=2,4,6,8,10
```

The two lists `sequential` and `parallel` are equal because both perform independent filtering and transformation operations on an ordered source. In this pipeline, `toList()` preserves the stream's encounter order, so the result remains `[4, 16, 36, 64, 100]`.

You cannot infer from an ordered result that the squaring operations ran one after another on the same execution thread. **The order of the result** and **when each computation executes** are two different concerns.

The `orderedActions` line uses `forEachOrdered`. When a stream has an encounter order, this operation executes the action in that order. The actions execute one at a time, with a happens-before relationship between one action's completion and the next; therefore `StringJoiner` in the example is not modified concurrently by multiple actions. This does not guarantee that all actions run on the same execution thread. [forEachOrdered Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#forEachOrdered(java.util.function.Consumer))

If you switch to `forEach` on a parallel stream, encounter order is no longer guaranteed for the actions, nor can you share `StringJoiner` as if only one party were modifying it. To collect data, use a collect operation instead of manually mutating an external result object.

### Spliterator Helps Partition the Source, Not Make the Source Thread-Safe

`Spliterator` is responsible for supporting traversal and partitioning of elements. When processing in parallel, the library can split the source into parts, process them, and then combine the results. How evenly the source splits and the cost of splitting affect the benefit of this execution mode.

Characteristics such as `ORDERED`, `SIZED`, `IMMUTABLE`, or `CONCURRENT` describe guarantees of the traversal process. They are not proof that every element object or every user-supplied function is safe to run concurrently. [Spliterator Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Spliterator.html)

Consequently, `parallelStream()` does not turn `ArrayList` into a collection that allows multiple parties to freely add or remove elements during traversal. Nor does it allocate a dedicated execution thread per element, guarantee a fixed number of threads, or automatically protect shared state in processing functions.

## 4. Non-Interference Applies to Both Modes

For regular sources that do not support concurrent updates, functions passed into a pipeline must not modify the source being processed. This applies when using `stream()` as well, not just `parallelStream()`.

In the standard terminal operations covered in this lesson, the protected window begins when the terminal operation is called and ends when that operation completes. Ways of obtaining `iterator()` or `spliterator()` to drive traversal manually are a special case: the protection responsibility must span the actual traversal. [Stream Non-Interference Rules](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/package-summary.html#NonInterference)

### “Source” Means the Actual Object, Not Just the Variable Name

Consider the following incorrect snippet. This illustrates an error inside a method, not a standalone program, and has no guaranteed stdout:

```java
List<Integer> source = new ArrayList<>(List.of(1, 2, 3, 4));

source.stream().forEach(n -> {
    if (n == 2) {
        source.add(99);
    }
});
```

While `forEach` is traversing `source`, the action adds an element to `source` itself. Using a sequential `stream()` does not make that valid. Reading and modifying can conflict with traversal rules even on a single execution thread.

You also cannot avoid the problem by modifying through a different variable name:

```java
// Incorrect illustration; source is an ArrayList being traversed by the stream.
List<Integer> alias = source;
source.stream().forEach(n -> alias.remove(n));
```

`alias` still points to the same object. Likewise, a method called inside `map` or `filter` can modify the source indirectly; it is not only obvious `source.add` calls directly visible inside the lambda that need checking.

### Not Only add and remove Need Consideration

Adding, removing, or clearing the entire source are the most obvious cases. Replacing an element with `set`, re-sorting the collection, or modifying a structurally shared view can also change the data being read while the pipeline is executing.

Specifically for `ArrayList`, `set` is not classified as a structural modification by the class's own tracking. That does not turn replacing elements while a stream is reading into a reliable processing contract. **Not incrementing the structural modification counter** and **non-interference with the source** are not the same condition.

The source can also be modified by another execution thread without any modification statement in the lambda. To run a pipeline correctly, you must control every path that modifies the source during the processing window.

### ConcurrentModificationException Is Not a Synchronization Mechanism

A source with a modification-detection mechanism may throw `ConcurrentModificationException`. However, the fail-fast mechanism only assists with error detection on a best-effort basis and does not guarantee catching every interference. The absence of an exception does not prove that the computation is correct. [ArrayList Javadoc on fail-fast](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html)

With code that violates the contract, you may encounter an exception, incorrect results, or behavior that no longer matches the program's assumptions. Do not write tests requiring that every invalid source modification must throw a specific exception at a specific element.

An exception also does not roll back changes that already occurred earlier. Trying to modify the source and catching `ConcurrentModificationException` to retry is not a safe way to implement a data processing operation.

### forEachOrdered Does Not Grant Permission to Modify the Source

`forEachOrdered` coordinates the order of the final action. It does not change the source's contract. If the action adds to or removes from the very list being traversed, the source interference problem still exists.

Keep the two requirements separate: action ordering and the validity of reading the source. Satisfying the first requirement does not automatically satisfy the second.

## 5. Produce a New Result or Separate the Source Modification Phase

Three approaches are generally more appropriate than streaming and modifying the source at the same time:

1. Use `filter` and `map` to produce a new result.
2. If you want to modify the collection directly, use an operation designed for that purpose, such as `removeIf`, outside any active traversal pipeline.
3. If you need to process a chosen state of the data, create a copy of the source at a protected point in time and process the copy.

Save to `NonInterferingTransformDemo.java`.

```java
import java.util.ArrayList;
import java.util.List;

public class NonInterferingTransformDemo {
    public static void main(String[] args) {
        List<Integer> source = new ArrayList<>(List.of(1, 2, 3, 4, 5, 6));

        List<Integer> transformed = source.parallelStream()
                .filter(n -> n % 2 == 0)
                .map(n -> n * 10)
                .toList();
        System.out.println("transformed=" + transformed);
        System.out.println("sourceUnchanged=" + source);

        List<Integer> snapshot = new ArrayList<>(source);
        source.removeIf(n -> n % 2 == 0);

        List<Integer> fromSnapshot = snapshot.parallelStream()
                .filter(n -> n % 2 == 0)
                .map(n -> n * 10)
                .toList();
        System.out.println("sourceAfterRemoveIf=" + source);
        System.out.println("snapshot=" + snapshot);
        System.out.println("fromSnapshot=" + fromSnapshot);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 NonInterferingTransformDemo.java
java NonInterferingTransformDemo
```

Stdout:

```text
transformed=[20, 40, 60]
sourceUnchanged=[1, 2, 3, 4, 5, 6]
sourceAfterRemoveIf=[1, 3, 5]
snapshot=[1, 2, 3, 4, 5, 6]
fromSnapshot=[20, 40, 60]
```

The first pass takes the even numbers and multiplies them by 10. The source still has all six numbers because the pipeline only produces `transformed`.

After that first pass finishes, the program makes a structural copy of the source into `snapshot`, then calls `removeIf` on the source. When the stream on `snapshot` runs, it reads its own separate list, so it still computes from the original six numbers even though the current source only has `[1, 3, 5]`.

`removeIf` in the example is a separate operation. Do not place it inside a processing function of a stream that is reading that same collection. The predicate expression also only reads values and does not go on to modify the collection through another path.

### The Copy Must Be Created When Reading the Source Is Valid

`new ArrayList<>(source)` is not a “make it thread-safe” button for every source. To copy correctly, reading `source` during the copy itself must also be protected from invalid updates.

In the program above, only one execution thread owns and modifies the list, so the copy is made at a stable point. In an application with multiple writers, you need an appropriate coordination mechanism for the data-acquisition phase; afterward, the structurally independent copy can be processed.

An unmodifiable wrapper such as `Collections.unmodifiableList(source)` is not a copy either. If another party still holds `source` and modifies it, the wrapper still uses that underlying data.

### A Structural Copy Does Not Deep-Copy Elements

The list of `Integer` in the example uses immutable elements. With objects that have mutable state, `new ArrayList<>(source)` still holds the same element references.

For example, copying a `List<Order>` does not automatically create new `Order` objects. If another party mutates fields inside those `Order` instances, the pipeline over the copy still needs to be evaluated for data consistency.

Mutating element state is different from adding to or removing from the collection. You cannot just see a setter call and conclude every case is wrong; you must check whether the object is shared, whether it appears multiple times, whether it is read or written concurrently, and whether it makes the result depend on execution timing. When the goal is transforming data, creating new output objects usually makes responsibilities clearer than mutating shared objects.

## 6. Not Modifying the Source Is Still Not Enough If There Is Shared State

A pipeline may leave the source collection untouched and still be wrong when its functions concurrently modify an external object.

The snippet below illustrates a bug; it is not a runnable sample program and has no reliable output:

```java
List<Integer> output = new ArrayList<>();

numbers.parallelStream()
        .map(n -> n * 2)
        .forEach(output::add);
```

`output` is not the source `numbers`, so the bug here is not adding to the source itself. The bug is that multiple actions can call `ArrayList.add` concurrently on the same unprotected list. Elements can be lost, state can be corrupted, or exceptions can occur.

Using a synchronized list can protect individual add operations, but it does not automatically preserve the required result order and creates a shared point of contention. When the goal is collecting results, let the stream's collect operation manage the accumulation containers.

### Experiment Using collect and Reduction Operations

Save to `ParallelReductionDemo.java`.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class ParallelReductionDemo {
    public static void main(String[] args) {
        List<Integer> source = IntStream.rangeClosed(1, 12).boxed().toList();

        List<Integer> doubled = source.parallelStream()
                .map(n -> n * 2)
                .collect(Collectors.toCollection(ArrayList::new));
        int sequentialSum = source.stream().mapToInt(Integer::intValue).sum();
        int parallelSum = source.parallelStream().mapToInt(Integer::intValue).sum();
        long evenCount = source.parallelStream().filter(n -> n % 2 == 0).count();

        System.out.println("doubled=" + doubled);
        System.out.println("sequentialSum=" + sequentialSum);
        System.out.println("parallelSum=" + parallelSum);
        System.out.println("evenCount=" + evenCount);
        System.out.println("source=" + source);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 ParallelReductionDemo.java
java ParallelReductionDemo
```

Stdout:

```text
doubled=[2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24]
sequentialSum=78
parallelSum=78
evenCount=6
source=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
```

`Collectors.toCollection(ArrayList::new)` provides a way to create library-managed accumulation collections. With this collection mechanism, partial results are accumulated separately and then combined appropriately; it is not all execution threads calling `add` on a single external `ArrayList`.

That is why `ArrayList` can be used as the accumulation container in this collect pattern even though `ArrayList` is not itself safe for arbitrary concurrent calls. This is a guarantee from the collection protocol, not a change in the properties of the `ArrayList` class. [Collectors Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html)

`sum` and `count` also let the library organize result accumulation instead of having the user manually increment a shared variable. In the example, the sum from 1 to 12 is 78, there are six even numbers, and the source is unmodified.

### Combining Results Must Be Mathematically Valid

If you use `reduce` or build a custom collector, you must satisfy the associativity contract. When splitting data into groups, the result must not change simply because the library chooses a different grouping.

For example, with subtraction:

```text
(10 - 3) - 2 = 5
10 - (3 - 2) = 9
```

Subtraction is not associative. Switching a reduction that uses subtraction to parallel and expecting it to always match left-to-right subtraction places an invalid requirement on the library.

In this lesson's example using small integers, the sum does not overflow and has no rounding issues. With floating-point addition, changing the grouping can introduce rounding differences; do not mechanically expect “bit-for-bit identical results” for every aggregation.

### State That Is Safe to Update Can Still Be Semantically Wrong

Suppose you use an atomic counter inside `filter` and keep the three elements that trigger the first three increments. The counter may not lose updates, but in parallel mode, the first three elements processed are not necessarily the first three elements in source order.

If the requirement is “the first three elements,” express it with `limit(3)` on an appropriately ordered stream. A thread-safe data structure only solves how state is accessed; it does not automatically turn a schedule-dependent rule into the right requirement.

### Do Not Use peek as a Mandatory Business-Logic Step

The snippet below only illustrates observation and does not promise that three lines will be printed:

```java
// Illustration snippet; numbers is an existing List<Integer>.
long count = numbers.stream()
        .peek(System.out::println)
        .count();
```

If the element count is already known and intermediate steps do not change the count, the library can compute `count` without traversing each element. In that case, `peek` may not be called at all. [Stream.count Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#count())

In addition, short-circuiting terminal operations may not need to read the entire source. Do not put an update that must occur for every element into `map`, `filter`, or `peek` and assume it will always run the full number of times. Express the desired computation via return values, aggregations, or an explicit action phase.

## 7. Source Type Determines the Policy When Data Changes

You cannot just look at the method name `stream()` and conclude that every collection type captures the same data state.

Three cases to distinguish:

| Source type | Traversal view | When data changes |
| --- | --- | --- |
| Regular `ArrayList` | Late-binding with interference detection | Changes before processing may be reflected; do not modify during processing |
| `CopyOnWriteArrayList` | Traverses a snapshot of the array at iterator/spliterator creation | Subsequent adds or removes do not enter the snapshot being traversed |
| Key set of `ConcurrentHashMap` | Iterator/spliterator supports concurrent updates, weakly consistent | Does not promise an atomic snapshot of the entire map |

Save to `SourceTraversalPoliciesDemo.java`.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Spliterator;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.stream.Stream;

public class SourceTraversalPoliciesDemo {
    public static void main(String[] args) {
        List<String> regular = new ArrayList<>(List.of("A", "B"));
        Stream<String> regularStream = regular.stream();
        regular.add("C");
        System.out.println("regularResult=" + regularStream.toList());
        System.out.println("regularConcurrent=" + regular.spliterator()
                .hasCharacteristics(Spliterator.CONCURRENT));

        CopyOnWriteArrayList<String> copyOnWrite =
                new CopyOnWriteArrayList<>(List.of("A", "B"));
        Stream<String> snapshotStream = copyOnWrite.stream();
        copyOnWrite.add("C");
        System.out.println("copyOnWriteResult=" + snapshotStream.toList());
        System.out.println("copyOnWriteCurrent=" + copyOnWrite);
        System.out.println("copyOnWriteImmutableTraversal="
                + copyOnWrite.spliterator()
                .hasCharacteristics(Spliterator.IMMUTABLE));
        System.out.println("copyOnWriteConcurrentTraversal="
                + copyOnWrite.spliterator()
                .hasCharacteristics(Spliterator.CONCURRENT));

        ConcurrentHashMap<String, Integer> concurrent = new ConcurrentHashMap<>();
        concurrent.put("B", 2);
        concurrent.put("A", 1);
        System.out.println("keySetConcurrentTraversal="
                + concurrent.keySet().spliterator()
                .hasCharacteristics(Spliterator.CONCURRENT));
        System.out.println("stableKeysForDisplay="
                + concurrent.keySet().stream().sorted().toList());
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 SourceTraversalPoliciesDemo.java
java SourceTraversalPoliciesDemo
```

Stdout:

```text
regularResult=[A, B, C]
regularConcurrent=false
copyOnWriteResult=[A, B]
copyOnWriteCurrent=[A, B, C]
copyOnWriteImmutableTraversal=true
copyOnWriteConcurrentTraversal=false
keySetConcurrentTraversal=true
stableKeysForDisplay=[A, B]
```

### With ArrayList: No Immediate Snapshot at the stream Call

`regularStream` is created when the list has `A` and `B`. Adding `C` before the terminal operation causes the result to include `C`. The `CONCURRENT` characteristic is `false`; this is not a source designed to accept arbitrary concurrent updates while a stream is reading.

Late binding narrows the window in which interference can occur. It does not remove the requirement for protection during pipeline execution.

### With CopyOnWriteArrayList: Snapshot Traversal

`CopyOnWriteArrayList` allows modifying the list itself, but its spliterator traverses an array snapshot that existed when the spliterator was created. In the program, the old stream yields `[A, B]`, while the current state of the list is already `[A, B, C]`.

The `IMMUTABLE` characteristic here describes that traversal's element source; it does not mean `add` cannot be called on the `CopyOnWriteArrayList` object. Nor does it mean the element objects themselves have become immutable. [CopyOnWriteArrayList.spliterator Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html#spliterator())

Do not choose this class just to mask a pipeline that improperly modifies its source. Every write incurs a copy cost; use it when snapshot semantics and read-heavy workloads fit the requirements.

### With ConcurrentHashMap: Supporting Updates Does Not Mean an Atomic Snapshot

`keySetConcurrentTraversal=true` shows that the key set's spliterator reports the `CONCURRENT` characteristic. This is an example of a source designed to be traversed while updates occur according to its contract.

However, a single traversal may observe state at different points in time. Do not treat an aggregated result produced while the map is changing as a consistent snapshot of the entire map at a single instant. [ConcurrentHashMap Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)

The program does not perform actual contending updates on the map, so the `stableKeysForDisplay` line simply prints the two added keys and sorts them for stable display output. That line is not an experiment proving that all concurrent updates are observed.

The concurrent-source exception also does not eliminate shared state in processing functions. If a lambda modifies an external result `ArrayList` or reads a changing variable without coordination, those issues still must be solved separately.

If business logic requires processing the entire dataset consistently at a single point in time, you must design a way to obtain a consistent state. Switching a collection to a concurrent one just to stop seeing `ConcurrentModificationException` is not enough to satisfy that requirement.

## 8. Choose Parallel Only After Processing Is Correct

Parallel mode is an execution choice, not a fix for correctness. First, verify:

- Whether the filter and transform functions can be computed independently per element.
- Whether any source is modified while the pipeline runs.
- Whether combining results satisfies the contract.
- What ordering must be preserved in the output or in actions.
- Whether there is any shared state outside the pipeline.

Only then should you weigh the cost. Splitting work, scheduling, and combining results all have overhead. Small sources or very lightweight operations may gain no benefit; sources that are hard to split evenly can also leave some partitions finishing much later than others. Do not assume `parallelStream()` is always faster than `stream()`. [Oracle Java Tutorial: Parallelism](https://docs.oracle.com/javase/tutorial/collections/streams/parallelism.html)

A stable `ArrayList` source can be read by a parallel stream even though the collection itself does not provide thread-safe operations across the board. The condition is that no party modifies the source during processing and the participating functions satisfy their contracts. You do not need to turn every read-only source into a concurrent collection just because you choose parallel mode.

If the result is correct and you need conclusions about speed, measure with realistic data and environment using proper JVM benchmarking methods. Printing thread names once or timing a very short run is not enough to prove a benefit.

The programs in this lesson use small inputs to verify behavior and results. They are not performance benchmarks.

### When Is a Loop the Right Expression?

If the task must modify multiple interrelated structures in a clear sequence, a sequential loop can express responsibilities better than a pipeline filled with side effects.

However, switching a stream to a `for-each` loop does not automatically allow adding to or removing from the collection being traversed by the loop's iterator either. To remove during traversal, choose the appropriate API and traversal rule, such as `removeIf` or the iterator's remove operation where supported.

What must be preserved is the contract of the source and the algorithm, not whether the syntax is a lambda or a loop.

## 9. Common Misconceptions That Easily Break Processing

| Misconception | What to check or fix |
| --- | --- |
| `stream()` is a copy of the data | Identify the source type and binding time; make a separate copy if needed |
| Only parallel streams forbid modifying the source | The non-interference rule applies to sequential pipelines too |
| No `ConcurrentModificationException` means it is safe | Fail-fast detection does not guarantee catching every interference |
| Replacing with `set` is definitely valid because size doesn't change | Source data is still being altered during traversal |
| Using a different variable name means no longer modifying the source | Check the actual object and all shared reference paths |
| `forEachOrdered` makes every operation valid | It handles action order, not permission to modify the source |
| Parallel stream makes the source automatically thread-safe | The source and functions must still satisfy their own contracts |
| Having an external result list means any lambda can call `add` | Use a collect operation; avoid unprotected accumulation |
| An atomic counter makes any stateful algorithm ordered correctly | Distinguish update safety from element selection semantics |
| `peek` always runs once per element | It can be optimized away or skipped on short-circuiting |
| Concurrent collections always give a fixed snapshot | Read the traversal policy; weakly consistent differs from a snapshot |
| Creating `new ArrayList<>(source)` protects all element objects too | A structural copy still shares element references |
| Adding `parallel()` in the middle only parallelizes the later part | The most recently set mode applies to the whole pipeline when it runs |

A useful self-check is to separate three questions:

1. **Is the source stable or does it have an appropriate update policy?**
2. **Do the processing functions depend on changing state or cause contention?**
3. **Do the terminal operation and combining strategy guarantee the required result?**

Answering “yes, we used a thread-safe collection” only addresses part of the first question and does not replace the remaining two.

## 10. Practice Predicting and Fixing Processing

### Exercise 1: Changes Before and After the Terminal Operation

An `ArrayList` initially contains `[1, 2]`. Create a stream with `filter(n -> n > 1)`, add `3` to the list, and then call `toList()`. After obtaining the result, add `4` to the list. Which elements does the produced result contain?

**Answer check:**

The result is `[2, 3]`. Adding `3` happens before the terminal operation and is observed by the stream on `ArrayList` in this scenario. Adding `4` afterward does not automatically update the result list. To process `4` as well, create a new stream from the source.

### Exercise 2: Modifying During Sequential Traversal

A pipeline uses `source.stream().forEach(...)`; inside the action, it calls `source.remove(...)`. Can you conclude it is safe because `parallelStream()` is not used?

**Answer check:**

No. The pipeline is reading and modifying the same regular source during a single traversal. Problems can still occur on a single execution thread. If the requirement is to remove elements matching a condition, use `removeIf` separately or create a new list with `filter`, depending on whether the source needs to be modified.

Do not treat a specific stdout or a specific exception as the contract for contract-violating code.

### Exercise 3: Collecting from a Parallel Stream

Code has `List<Integer> result = new ArrayList<>();`, then uses a parallel stream with `forEach(result::add)`. The source is completely unmodified. Does the code satisfy the conditions for correctness?

**Answer check:**

Not yet. Actions can update the same `result` concurrently. When the goal is creating a list, use `toList()` if structural modification of the result is not needed, or `collect(Collectors.toCollection(ArrayList::new))` if a mutable `ArrayList` is needed.

Source stability and result accumulation are two separate conditions.

### Exercise 4: Result Order vs. Action Order

An ordered `List` is filtered and transformed using a parallel stream. When terminated with `toList()`, the result can preserve encounter order. Does that prove the `map` function calls occurred sequentially? Does replacing the terminal operation with `forEach` guarantee the action order matches the list?

**Answer check:**

No to both questions. The library can process parts independently and then assemble the results in order. `forEach` on a parallel stream does not promise to respect encounter order. If you need action ordering on an ordered stream, consider `forEachOrdered`; you must still respect the limits on source modification and shared state.

### Exercise 5: Thread-Safe Collection and Snapshots

Create a stream from a `CopyOnWriteArrayList` containing `[A, B]`, then add `C` before calling `toList()`. Compare this with the similar scenario on `ArrayList`. Why does `SourceTraversalPoliciesDemo` produce two different results?

**Answer check:**

The stream from `CopyOnWriteArrayList` in the example traverses a snapshot taken when the spliterator was created, so it produces `[A, B]`. The stream from `ArrayList` uses late binding in that scenario, so it produces `[A, B, C]`. Calling the same `stream()` method does not override the specific contract of the source type.

### Exercise 6: Fixing a Stateful Requirement

The requirement is “take the first three elements matching a condition in source order.” One solution uses an atomic counter inside `filter` to keep the first three processed elements on a parallel stream. Why does that approach fail to express the requirement?

**Answer check:**

The order in which execution threads reach the counter is not the encounter order of elements in the source. The counter can update safely yet select the wrong three elements for the requirement. Express it by filtering on the condition and then calling `limit(3)` on an appropriately ordered stream.

### Exercise 7: Designing a Non-Interfering Transformation

Given the number list `[1, 2, 3, 4, 5, 6]`, write a program that produces a list of the squares of the odd numbers, then verify:

- The source remains `[1, 2, 3, 4, 5, 6]`.
- The result is `[1, 9, 25]`.
- Both the sequential and parallel versions produce the same ordered result.
- No external list is used to accumulate via `forEach`.
- Correctness does not rely on execution thread names, the call count of an observation step, or a fail-fast exception.

You can build on `StreamExecutionModeDemo`: change the predicate to odd numbers, keep the squaring operation, and produce the result with `toList()`. Then explain why the processing does not modify the source, has no shared state to update, and still preserves the correct result order.
