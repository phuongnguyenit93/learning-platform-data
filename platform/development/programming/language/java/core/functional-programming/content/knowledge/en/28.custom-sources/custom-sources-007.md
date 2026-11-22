# Designing Finite Sources, Deferred Sources, and Resource-Closing Responsibility in Java Streams

## 1. Lesson Objectives

When working with Java Streams, we do not only process data from a `List` or an array. Sometimes the source comes from a custom numeric range, a data generator, a cursor, a file being read incrementally, or an API providing elements on demand. In these cases, designing the **Stream source** properly is just as important as `map`, `filter`, and `reduce`.

Three questions must be resolved independently:

1. **Is the source finite or infinite?** How many elements can be provided, and can the terminal operation terminate?
2. **How lazily is the source evaluated?** Does calling the Stream-creating API read all data, open resources, or execute the element-generating function immediately?
3. **Who closes the resource?** When a source holds a file handle, reader, connection, or cursor, completing a terminal operation **does not automatically mean** the resource has been closed.

After this lesson, you will be able to:

- Choose between `Stream.of`, `Stream.iterate`, `Stream.generate`, `StreamSupport.stream`, and I/O sources.
- Create a **finite Spliterator** with valid `tryAdvance`, `trySplit`, `estimateSize`, and `characteristics`.
- Use the `StreamSupport.stream(Supplier, characteristics, parallel)` overload when **late-binding** a source is desired.
- Explain lazy evaluation and short-circuiting in `limit`, `findFirst`, and `anyMatch`.
- Manage lifecycles with `try-with-resources`, `BaseStream.close()`, and `onClose(...)`.
- Distinguish between resources opened at stream creation, at terminal invocation, and when actually fetching elements.
- Identify bugs involving infinite sets, leaked resources, `Spliterator` declaring wrong characteristics, mutable state, and parallel processing.

## 2. A Stream Pipeline Is Not a Collection

A Stream describes **the process of traversing and transforming data**, rather than being a structure storing results like a List.

~~~java
Stream<Integer> pipeline = List.of(1, 2, 3, 4)
        .stream()
        .filter(n -> n % 2 == 0)
        .map(n -> n * 10);
~~~

At the time `pipeline` is created, the lambdas in `filter` and `map` have typically **not executed yet**. They are lazily evaluated **intermediate operations**. A terminal operation is what requests producing a result:

~~~java
List<Integer> result = pipeline.toList();
System.out.println(result); // [20, 40]
~~~

A Stream can be divided into three layers:

~~~text
Data source
   |
   v
Spliterator / a Stream factory method
   |
   v
Intermediate operations (filter, map, limit, sorted, ...)
   |
   v
Terminal operation (toList, count, findFirst, reduce, ...)
   |
   v
Result or side effect per terminal contract
~~~

**Pipeline laziness does not automatically guarantee all resources are opened lazily.** A factory may open a file right when creating the stream even though no lines have been read yet. This is an important distinction when designing resource-backed sources.

## 3. Finite Sources and Infinite Sources

A **finite source** has a finite number of elements in a single traversal, such as a List, an array, or a numeric range `[start, end)`.

~~~java
Stream<Integer> finite = Stream.of(3, 1, 4);
IntStream range = IntStream.range(0, 5);
~~~

`IntStream.range(0, 5)` has five values: **0, 1, 2, 3, 4**; the upper bound is **exclusive**.

A **potentially unbounded source** can keep producing elements if the terminal operation keeps requesting them:

~~~java
Stream<Long> powers = Stream.iterate(1L, n -> n * 2);
Stream<Double> randoms = Stream.generate(Math::random);
~~~

The illustrative snippets require importing `Stream` and `IntStream`. `iterate(seed, next)` and `generate(supplier)` can keep supplying elements until bounded or short-circuited by a terminal operation. In the doubling example, the long type may eventually overflow; that does not make `iterate` stop automatically.

**Problem:** a terminal operation like `count()` or `toList()` usually cannot terminate on a truly infinite source without an appropriate bounding step.

~~~java
// Do not call directly on an infinite source:
// Stream.generate(Math::random).toList();
~~~

### 3.1. Bounding with limit

~~~java
List<Integer> firstFive = Stream.iterate(0, n -> n + 1)
        .limit(5)
        .toList();

System.out.println(firstFive); // [0, 1, 2, 3, 4]
~~~

`limit(5)` is a **short-circuiting intermediate operation**. In this simple pipeline, the terminal operation only needs five elements to finish.

However, **simply having limit at the end is not always safe**:

~~~java
// Avoid: sorted may have to wait for the entire infinite source.
// Stream.iterate(0, n -> n + 1).sorted().limit(5).toList();
~~~

If you want to take the first five elements and then sort them, write **limit(5).sorted()**; however, that carries a **different meaning** from finding the five smallest elements across the entire source. Design according to the actual problem, rather than arbitrarily swapping steps.

### 3.2. iterate with a stopping condition (Java 9+)

~~~java
List<Integer> finiteRange = Stream.iterate(
        1,
        n -> n <= 5,
        n -> n + 1
).toList();

System.out.println(finiteRange); // [1, 2, 3, 4, 5]
~~~

The three-argument overload `iterate(seed, hasNext, next)` creates a finite source if the condition eventually becomes false. If the condition stays true forever, the source may still never terminate.

Note the **check order**: `hasNext` is evaluated to determine whether the current element is emitted; if false, that element is not included in the Stream.

### 3.3. generate differs from iterate

`Stream.generate(Supplier<T>)` pulls each value from a Supplier, often used to generate mock data or independent elements.

~~~java
List<String> tickets = Stream.generate(() -> "NEW")
        .limit(3)
        .toList();

System.out.println(tickets); // [NEW, NEW, NEW]
~~~

If the Supplier relies on a mutable counter or stateful resource, safety when switching to parallel must be checked. With `generate`, Stream does not automatically commit elements to a business-numbered sequence. Use `IntStream.range` or `iterate` if a clearly ordered sequence is required.

## 4. Finite Sources Should Clearly Describe Size and Bounds

A custom-defined source needs to answer:

- What is the **first** value that can be emitted?
- What is the exact **termination condition**?
- Is the upper bound inclusive?
- If the terminal operation requests another element after exhaustion, what does the source return?
- Can a traversal be run multiple times or not?
- Can it be split into disjoint segments for parallel execution?

A simple design is an integer range from **startInclusive** to **endExclusive**:

~~~text
startInclusive = 1
endExclusive   = 6

Elements: 1, 2, 3, 4, 5
Count: endExclusive - startInclusive = 5
~~~

With an exclusive upper bound, the exhaustion condition is `current >= endExclusive`. Using an exclusive upper bound is consistent with `IntStream.range(start, end)`, helping avoid off-by-one errors.

**If endExclusive is less than startInclusive**, you must decide clearly: reject the arguments, or represent an empty source. Never simultaneously report a negative size and declare the `SIZED` characteristic.

In a general source, if the count exceeds the int range, use a long counter and compute distances carefully to avoid overflow.

## 5. Spliterator: The Boundary Between Source and Stream

Java uses **`java.util.Spliterator<T>`** to traverse and, if appropriate, split a source into processable chunks.

Important methods/properties:

| Component | Meaning |
| --- | --- |
| **tryAdvance(action)** | Attempts to forward exactly one element to Consumer, returning true if an element existed |
| **forEachRemaining(action)** | Forwards remaining elements; has a default implementation |
| **trySplit()** | Attempts to split off a portion of unprocessed source for independent traversal |
| **estimateSize()** | Estimates untraversed element count |
| **characteristics()** | Flags describing guaranteed source properties |
| **getExactSizeIfKnown()** | Returns exact size if `SIZED` is present, otherwise -1 |
| **getComparator()** | Meaningful when Spliterator reports `SORTED` |

**tryAdvance** is central: for a finite source, after the last element, subsequent calls must return **false** without calling action again.

Descriptive example:

~~~java
@Override
public boolean tryAdvance(Consumer<? super Integer> action) {
    if (current >= endExclusive) {
        return false;
    }
    action.accept(current++);
    return true;
}
~~~

This snippet assumes it is inside a class with `current` and `endExclusive` fields; `Consumer` import is required. The complete program in Section 13 provides the full definition and tests.

### 5.1. A Spliterator is traversal state, not a list

Each Spliterator typically holds a **current position**. When `tryAdvance` is called, that position changes. This does not mean the external source data is modified: the traverser's position state can be mutable even though the mathematical source is immutable.

Do not use a Spliterator that is concurrently called by multiple threads on `tryAdvance` without a corresponding design. In a properly built parallel stream, the framework orchestrates the **split** process, and each branch owns its chunks of work per the partitioning contract.

## 6. trySplit: Splitting the Source to Support Parallelism

`trySplit()` attempts to split the untraversed portion into disjoint parts. It returns:

- A new Spliterator representing one split-off part, or
- `null` when it cannot or should not split.

Suppose the segment `[1, 9)` remains:

~~~text
Before split:
[1, 2, 3, 4, 5, 6, 7, 8]

trySplit():
  returned branch [1, 2, 3, 4]
  original branch [5, 6, 7, 8]
~~~

The two branches **must not overlap elements or skip elements**. Together they must describe the exact untraversed dataset, consistent with `estimateSize`.

A simple range-splitting approach is:

~~~java
int low = current;
int mid = low + (endExclusive - low) / 2;

if (mid <= low) {
    return null;
}

current = mid; // Original branch keeps the second half.
return new RangeSpliterator(low, mid);
~~~

This is an illustrative algorithm, requiring a RangeSpliterator class with a matching constructor. If the index range might cause **endExclusive - low** to overflow int, convert the length calculation to long before dividing.

### 6.1. Is trySplit mandatory?

No. A Spliterator can always return `null`, and the source is still usable for a sequential Stream. However, a parallel Stream will generally struggle to gain benefits if the source cannot split, or if splitting costs more than the computation itself.

**Do not falsely report `SUBSIZED`** if branch sizes after splitting are not exact. For an immutable numeric range split into disjoint intervals, `SIZED | SUBSIZED` can be validly declared.

## 7. Important Characteristics

A Spliterator can declare flags from `Spliterator`:

| Flag | What Is Guaranteed | Note |
| --- | --- | --- |
| **ORDERED** | Has a defined encounter order | Does not imply sequential Stream |
| **DISTINCT** | No two duplicate elements per equals | Only report when genuinely true |
| **SORTED** | Elements follow a comparison order | Has a corresponding `getComparator()` contract |
| **SIZED** | `estimateSize()` is the exact remaining element count before split/traversal | Do not report if actual source changes size uncontrollably |
| **SUBSIZED** | Spliterators after splitting are also SIZED and SUBSIZED | Very useful for effective source partitioning |
| **NONNULL** | Does not emit null elements | Not equivalent to fields inside objects being non-null |
| **IMMUTABLE** | Source is not structurally interfered with during traversal | Internal cursor state can still change |
| **CONCURRENT** | Source is designed for concurrent modification per contract | Do not infer from a single AtomicInteger variable |

**Flags are commitments**, not arbitrary "speed hints." If **SIZED** is reported yet `estimateSize` is wrong, Stream may optimize based on wrong information and produce unexpected results.

Example for an unchanging numeric range:

~~~java
int characteristics = Spliterator.ORDERED
        | Spliterator.SIZED
        | Spliterator.SUBSIZED
        | Spliterator.NONNULL
        | Spliterator.IMMUTABLE;
~~~

You should only declare what the implementation guarantees. If the source is data from a file/cursor whose record count is unknown, **do not attach SIZED**. If the source can emit null, **do not attach NONNULL**.

### 7.1. SORTED requires an additional contract

When declaring `SORTED`, the Spliterator must support `getComparator()` semantically: returning null when sorted by natural order, or returning an appropriate Comparator for another order. Do not attach SORTED just because "usually the data looks ascending."

Reporting a wrong flag can lead the pipeline to skip a necessary sort step or make false assumptions about the source.

### 7.2. SIZED does not automatically mean finite in every problem

A finite source can **have an unknown size upfront**, such as reading lines from a reader before scanning to the end. That source is still finite yet should not report SIZED.

Conversely, an unbounded element-generating source can return `Long.MAX_VALUE` as an unknown estimate, not claiming that the source has exactly Long.MAX_VALUE elements.

## 8. Creating a Stream from a Spliterator with StreamSupport

Common way when you have a Spliterator:

~~~java
Stream<Integer> stream = StreamSupport.stream(
        spliterator,
        false // sequential
);
~~~

This is a snippet with a `spliterator` variable of type Spliterator<Integer> and Stream/StreamSupport imports. If **true** is passed, the Stream starts in parallel mode:

~~~java
Stream<Integer> parallel = StreamSupport.stream(
        spliterator,
        true
);
~~~

`parallel` does not guarantee effective work splitting if trySplit is unsupported or the source is small. Similarly, `stream.parallel()` can change the pipeline mode afterward.

**Ownership note:** if the Spliterator was created from an open resource, that resource still needs to be closed via a clear mechanism; simply calling StreamSupport.stream does not make Java automatically infer what to close.

## 9. Late-Binding with Supplier<Spliterator<T>>

Java also provides the overload:

~~~java
Stream<T> stream(
        Supplier<? extends Spliterator<T>> supplier,
        int characteristics,
        boolean parallel)
~~~

The difference is that the caller passes **a Supplier creating a Spliterator**, instead of providing an already created Spliterator.

With this overload, **the Supplier is called no earlier than when the terminal operation starts** (or during corresponding pipeline evaluation), helping defer acquiring the traverser until actually needed.

Example:

~~~java
AtomicInteger creations = new AtomicInteger();

Supplier<Spliterator<Integer>> factory = () -> {
    creations.incrementAndGet();
    return List.of(1, 2, 3).spliterator();
};

Stream<Integer> stream = StreamSupport.stream(
        factory,
        Spliterator.ORDERED
                | Spliterator.SIZED
                | Spliterator.SUBSIZED,
        false);

System.out.println(creations.get()); // 0
System.out.println(stream.toList()); // [1, 2, 3]
System.out.println(creations.get()); // 1
~~~

This is an illustrative snippet inside a method with imports `List`, `Stream`, `Spliterator`, `Supplier`, `AtomicInteger`, and `StreamSupport`.

**Do not infer** that the Supplier is always called exactly once in every Stream usage or when errors occur. The main contract is that the Supplier provides a suitable Spliterator when the Stream needs evaluation; each Stream is still meant for single consumption.

### 9.1. Characteristics must match

In the Supplier overload, the **characteristics** argument must match the characteristics of the Spliterator actually returned by the Supplier. The specification requires them to be **equal**; otherwise behavior is undefined per the API contract.

Therefore, with a custom Spliterator, use **the same flag set** in the source class and in the `StreamSupport.stream(supplier, flags, parallel)` call.

### 9.2. Supplier does not automatically handle resource closing

Deferring Spliterator creation can help defer opening the source, yet **does not make Stream automatically close a file/cursor after the terminal operation**. If the Supplier opens a resource, you must clearly design where the resource reference is held, the `onClose` action, and the error-handling policy.

If the caller closes the Stream without calling a terminal operation, `onClose` still needs to be safe for the case where **the resource has not been opened yet**. If opening fails partway through, ensure already-created resources are not leaked.

## 10. Laziness Has Several Different Layers

Distinguish between:

1. **Lazy traverser creation:** Supplier<Spliterator> has not been called yet.
2. **Lazy element fetching:** Spliterator exists, but `tryAdvance` has not been requested yet.
3. **Lazy transformation:** `map/filter` have not run yet.
4. **Lazy I/O:** each line/chunk is only read when needed, if the source supports it.
5. **Lazy resource opening:** file/connection has not been opened yet; this is **not automatically true** for every I/O Stream.

A Stream can be lazy in items 2–4 yet **already have opened the resource** right when the factory was called.

For example, the `Files.lines(path)` API opens the file to create a line-reading Stream; content processing is lazy, yet the file is a resource that must be closed. Do not treat "no terminal yet" as synonymous with "no resource held yet."

### 10.1. map/filter and short-circuiting terminals

~~~java
List<Integer> firstTwoEven = Stream.iterate(1, n -> n + 1)
        .filter(n -> n % 2 == 0)
        .limit(2)
        .toList();

System.out.println(firstTwoEven); // [2, 4]
~~~

In a simple sequential pipeline, only numbers 1,2,3,4 need to be tested to find two even numbers. The entire infinite sequence was not generated.

However, **do not use side effects in Supplier/Predicate as a guarantee of "exactly four calls" for every parallel pipeline**. Short-circuiting and work splitting can change the callback count.

## 11. A Stream Is Typically Consumed Only Once

~~~java
Stream<String> stream = Stream.of("A", "B");
long size = stream.count();

// Do not reuse the same Stream:
// stream.toList(); // May throw IllegalStateException.
~~~

A Stream is meant for one pipeline consumed once. If data needs to be reused, create a new Stream from a **replayable source** (List, array, factory returning a fresh source) or materialize valid results when needed.

A **replayable source** differs from a **replayable Spliterator**. A Spliterator object that has reached the end does not automatically rewind to the beginning. To re-traverse, create a **new Spliterator** via an appropriate factory.

If the source is a single-use file or cursor, decide clearly whether the API allows re-reading, and whether creating a new Stream needs to open a new resource.

## 12. Resources: Terminal Operations Do Not Automatically Close Streams

Streams working only on in-memory collections usually do not need to close an external resource. However, Streams from files, readers, or I/O resources may hold file descriptors, buffers, or readers.

**Key points:**

- `Stream<T>` implements `AutoCloseable` via `BaseStream`.
- `close()` is the action of closing the Stream and running registered close handlers.
- **Terminal operations do not implicitly call close()**.
- `onClose(Runnable)` registers an action to run when the Stream is closed.
- `try-with-resources` ensures Stream.close is called even when a terminal operation throws an exception, per Java language structure.
- **Whoever creates or receives ownership of a resource-holding Stream should clearly define closing responsibility**.

Standard example with a file:

~~~java
Path path = Path.of("data.txt");

try (Stream<String> lines = Files.lines(path)) {
    List<String> preview = lines
            .limit(5)
            .toList();

    System.out.println(preview);
}
~~~

This is an illustrative snippet requiring data.txt to exist and importing `Path`, `Files`, `Stream`, and `List`. Exact stdout cannot be stated without knowing the file contents.

**Files.lines(path)** provides a Stream of lines with an open resource, and the API documentation requires closing the Stream promptly. `try-with-resources` is the most readable and safest approach.

### 12.1. Do not close a Stream and then return it

Anti-pattern:

~~~java
Stream<String> loadLines(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(path)) {
        return lines; // WRONG: already closed before caller traverses.
    }
}
~~~

This is an illustrative method, not a standalone file. Upon exiting the try block, the Stream is already closed. Returning a closed Stream prevents the caller from validly using it as a fresh pipeline.

Two good design directions:

- **Process within the resource owner's scope:** the method opens the Stream, traverses and returns a **materialized result**, then closes it.
- **Transfer ownership explicitly:** the method returns an open Stream; the API documentation states the caller **must close** it in try-with-resources.

If returning a Stream to the caller, specify where I/O exceptions during terminal execution will surface, not just initial file-opening errors.

### 12.2. onClose does not run just because toList completes

~~~java
AtomicBoolean closed = new AtomicBoolean(false);

Stream<String> lines = Stream.of("A", "B")
        .onClose(() -> closed.set(true));

List<String> data = lines.toList();
System.out.println(closed.get()); // false

lines.close();
System.out.println(closed.get()); // true
~~~

This is an illustrative snippet with Stream, List, and AtomicBoolean imports. It proves `toList()` does not automatically call the close handler; `close()` is a separate operation.

**Do not treat a terminal operation returning successfully as a signal that the resource has been closed.**

## 13. Complete Java 17 Program

This example verifies three main points:

1. A **finite Spliterator** emits numbers over `[startInclusive, endExclusive)`, returning false when exhausted.
2. The source is created with **Supplier<Spliterator>**, so Spliterator creation is deferred until the terminal operation. The `filter(...).limit(2)` pipeline fetches only as many elements as needed.
3. **BufferedReader.lines()** fetches lines on demand; an `onClose` attaches the task of closing the reader to the Stream lifecycle. `toList()` does not automatically call the close handler; `try-with-resources` calls close when exiting the block.

Use `StringReader` instead of a real file so the example runs standalone without depending on machine paths. A real file source follows the same ownership principles.

Create file **CustomStreamSourceDemo.java**:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.StringReader;
import java.io.UncheckedIOException;
import java.util.List;
import java.util.Objects;
import java.util.Spliterator;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Consumer;
import java.util.function.Supplier;
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

public class CustomStreamSourceDemo {
    private static final int FLAGS =
            Spliterator.ORDERED
            | Spliterator.SIZED
            | Spliterator.SUBSIZED
            | Spliterator.NONNULL
            | Spliterator.IMMUTABLE;

    static final class RangeSpliterator
            implements Spliterator<Integer> {
        private int current;
        private final int endExclusive;
        private final AtomicInteger emitted;

        RangeSpliterator(int startInclusive,
                         int endExclusive,
                         AtomicInteger emitted) {
            if (startInclusive > endExclusive) {
                throw new IllegalArgumentException(
                        "start must not exceed end");
            }
            this.current = startInclusive;
            this.endExclusive = endExclusive;
            this.emitted = Objects.requireNonNull(emitted);
        }

        @Override
        public boolean tryAdvance(
                Consumer<? super Integer> action) {
            Objects.requireNonNull(action);

            if (current >= endExclusive) {
                return false;
            }

            int value = current++;
            emitted.incrementAndGet();
            action.accept(value);
            return true;
        }

        @Override
        public Spliterator<Integer> trySplit() {
            int low = current;
            int mid = low + (endExclusive - low) / 2;

            if (mid <= low) {
                return null;
            }

            current = mid;
            return new RangeSpliterator(low, mid, emitted);
        }

        @Override
        public long estimateSize() {
            return (long) endExclusive - current;
        }

        @Override
        public int characteristics() {
            return FLAGS;
        }
    }

    static Stream<Integer> delayedRange(
            int start,
            int end,
            AtomicInteger creations,
            AtomicInteger emitted) {
        Supplier<Spliterator<Integer>> supplier = () -> {
            creations.incrementAndGet();
            return new RangeSpliterator(start, end, emitted);
        };

        return StreamSupport.stream(supplier, FLAGS, false);
    }

    public static void main(String[] args) {
        AtomicInteger creations = new AtomicInteger();
        AtomicInteger emitted = new AtomicInteger();

        try (Stream<Integer> range = delayedRange(
                1, 8, creations, emitted)) {
            System.out.println(
                    "created before: " + creations.get());
            System.out.println(
                    "emitted before: " + emitted.get());

            List<Integer> twoEven = range
                    .filter(n -> n % 2 == 0)
                    .limit(2)
                    .toList();

            System.out.println("two even: " + twoEven);
            System.out.println(
                    "created after: " + creations.get());
            System.out.println(
                    "emitted after: " + emitted.get());
        }

        AtomicInteger parallelEmitted = new AtomicInteger();
        List<Integer> parallel = StreamSupport.stream(
                new RangeSpliterator(
                        1, 6, parallelEmitted), true)
                .map(n -> n * 10)
                .toList();

        System.out.println("parallel values: " + parallel);

        AtomicBoolean closed = new AtomicBoolean(false);
        BufferedReader reader = new BufferedReader(
                new StringReader("alpha\nbeta\ngamma"));

        Stream<String> lines = reader.lines()
                .onClose(() -> {
                    try {
                        reader.close();
                        closed.set(true);
                    } catch (IOException e) {
                        throw new UncheckedIOException(e);
                    }
                });

        try (lines) {
            System.out.println("line preview: "
                    + lines.limit(2).toList());
            System.out.println(
                    "closed inside: " + closed.get());
        }

        System.out.println(
                "closed after: " + closed.get());

        System.out.println("finite prefix: "
                + Stream.iterate(0, n -> n + 1)
                        .limit(4)
                        .toList());
    }
}
~~~

Compile and run using **JDK 17 or later**:

~~~bash
javac CustomStreamSourceDemo.java
java CustomStreamSourceDemo
~~~

**Expected output:**

~~~text
created before: 0
emitted before: 0
two even: [2, 4]
created after: 1
emitted after: 4
parallel values: [10, 20, 30, 40, 50]
line preview: [alpha, beta]
closed inside: false
closed after: true
finite prefix: [0, 1, 2, 3]
~~~

### 13.1. Why is created before 0?

`delayedRange(...)` calls the **StreamSupport.stream(supplier, FLAGS, false)** overload. When creating the Stream, the Supplier does not need to be called yet; `creations` remains 0. Once the terminal `toList()` starts evaluation, the Supplier is used to create RangeSpliterator.

This is **late-binding** of the Spliterator, unlike the overload taking **an existing Spliterator**.

### 13.2. Why is emitted after 4?

The source emits 1,2,3,4,...; `filter(n % 2 == 0)` keeps even numbers; `limit(2)` needs **the first two even values**, 2 and 4. In this sequential pipeline, RangeSpliterator emitted exactly the first four numbers to produce the result.

AtomicInteger here is only used for **observing** the test, not business logic. If the pipeline is changed to parallel or has a stateful stage, the callback count/fetch order may differ. Do not design auditing systems based on this counter.

### 13.3. trySplit and parallel

RangeSpliterator is split into disjoint ranges; `trySplit()` updates the index of the original branch and returns a new branch containing the first half. `StreamSupport.stream(..., true)` requests parallel mode, and `toList()` produces the result **in encounter order** because the Spliterator reports ORDERED.

**parallel values** is still [10,20,30,40,50]. Parallel does not mean the result will be out of order. However, the program does not rely on the actual thread count or split count.

### 13.4. Why is closed inside false?

For `BufferedReader.lines()` with custom `onClose` in the example, the terminal `toList()` does not automatically close the Stream. Inside the try block, the close handler has not been called yet, so `closed` remains false. Upon exiting the **try-with-resources** block, Stream.close() runs `onClose`, closes the BufferedReader, and sets `closed` to true.

That is a separate lifecycle responsibility from producing results.

**Note:** the example uses `StringReader` (which holds no real file descriptor), yet the closing principle still holds for a BufferedReader reading a file. When using an API that creates a Stream from an open resource, clearly decide who closes the Reader and ensure the case where the terminal operation throws an error is handled as well.

## 14. Closing Resources from the Stream or from the Owner

There are two common ownership patterns.

### 14.1. Stream owns the resource lifecycle

A factory opens the resource and returns a Stream with a close handler attached. The caller receives the Stream and must close it:

~~~java
static Stream<String> openLines(Path path)
        throws IOException {
    BufferedReader reader = Files.newBufferedReader(path);

    return reader.lines().onClose(() -> {
        try {
            reader.close();
        } catch (IOException ex) {
            throw new UncheckedIOException(ex);
        }
    });
}
~~~

This is an illustrative method, requiring Path, Files, BufferedReader, IOException, UncheckedIOException, and Stream imports and placed inside a class.

Caller:

~~~java
try (Stream<String> lines = openLines(path)) {
    lines.filter(s -> !s.isBlank())
            .limit(10)
            .forEach(System.out::println);
}
~~~

The `openLines` method can throw IOException when opening the file. During traversal, read errors can be wrapped into **UncheckedIOException**. Upon closing, if close throws IOException, the close handler above converts it to UncheckedIOException.

**A limitation of the example:** if an exception occurs between opening the reader and creating/registering the Stream, a production factory needs to clean up the opened resource. In this simple snippet, intermediate steps have no common reason to throw checked exceptions, yet the principle of cleanup on failed construction remains important.

### 14.2. Another object owns the resource

A service might own the Reader and use Stream only to traverse within the method scope. In that case, the service must close the Reader in an outer `try-with-resources`, instead of always transferring ownership to the Stream.

~~~java
try (BufferedReader reader = Files.newBufferedReader(path)) {
    List<String> values = reader.lines()
            .limit(5)
            .toList();
}
~~~

This snippet requires a path variable and corresponding imports. Reader is the resource directly managed by try-with-resources. Whether the terminal completes or throws an exception, when exiting try, Reader is still closed.

**Rule:** there should be **one clear ownership contract**. Either a Stream attaches a close handler that closes the Reader, or the Reader is managed externally. Do not both close too early and pass the object to the caller for continued use.

## 15. Files.lines, Files.list, and Files.walk

The JDK provides APIs creating Streams tied to system resources:

- **Files.lines(path)**: traverses lines in a text file.
- **Files.list(dir)**: Streams direct entries in a directory.
- **Files.walk(start)**: Streams paths when walking a directory tree.

These Streams must be **closed promptly** per the API documentation, as they may hold file/directory-related resources. Use try-with-resources.

~~~java
try (Stream<Path> paths = Files.list(directory)) {
    long files = paths
            .filter(Files::isRegularFile)
            .count();
    System.out.println(files);
}
~~~

This is an illustrative snippet, requiring Path, Files, and Stream imports, a directory variable, and IOException handling. The result depends on the real directory so no fixed stdout is stated.

### 15.1. Close even when short-circuiting

~~~java
try (Stream<String> lines = Files.lines(path)) {
    Optional<String> firstError = lines
            .filter(line -> line.startsWith("ERROR"))
            .findFirst();
}
~~~

Even though `findFirst()` can stop early, the file resource must still be closed. `try-with-resources` does that upon leaving the block.

**Do not skip closing the file because EOF was reached** by application assumption: whether the terminal got enough results or read to the end does not replace the responsibility to close.

### 15.2. Exceptions can occur at creation or during traversal

- **Opening the file** can throw IOException.
- **Reading lines in the terminal** can hit an I/O error, typically surfaced via UncheckedIOException from the relevant Stream API.
- **Closing the resource** can also encounter an exception.

API design must distinguish these three phases, define who catches/logs/propagates errors, and not equate "empty Stream" with "read error."

## 16. onClose and Close Handlers

`BaseStream.onClose(Runnable)` registers a handler to run when the Stream is closed; handlers are executed **once per the pipeline's close contract**, in registration order if multiple handlers exist.

~~~java
Stream<String> stream = Stream.of("A", "B")
        .onClose(() -> System.out.println("first close"))
        .onClose(() -> System.out.println("second close"));

try (stream) {
    System.out.println(stream.toList());
}
~~~

Result:

~~~text
[A, B]
first close
second close
~~~

Note: if multiple close handlers throw exceptions, Java still attempts to run the remaining handlers; exceptions may be attached as suppressed per the close contract. **Do not treat close handlers as the right place to perform core order-dependent business logic beyond resource cleanup.**

If there is no special resource, calling close on a Stream from a List is usually unnecessary, though using try-with-resources does no harm when a general API needs to close any Stream passed in.

### 16.1. Do not use onClose to fix a lifecycle design bug

If a file was already closed before the Stream started traversing, registering onClose cannot "reopen" the file. Ensure the resource **stays alive for the entire duration the terminal needs to read**.

If a Stream is returned outside the owner's scope, the caller must be informed of the close obligation; clear naming via API names like `openLines` and descriptive documentation can help.

## 17. Deferred Resource Opening: Careful Factory Pattern

When you genuinely want to **defer opening a resource until the terminal operation**:

1. You can use the Supplier overload of `StreamSupport.stream`.
2. The Supplier opens the resource and creates an appropriate Spliterator.
3. Register onClose aware of which resource was opened (if any).
4. Handle open errors and read errors, while ensuring the resource is cleaned up on all paths.
5. Do not report `SIZED` when the element count is unknown, and do not arbitrarily share a non-thread-safe reader across parallel branches.

Diagram:

~~~text
Create Stream
   |
   +-- resource not opened yet if factory is designed late-open
   |
   v
Terminal starts
   |
   v
Supplier opens resource, creates Spliterator
   |
   v
tryAdvance reads each element
   |
   +-- terminal may stop early (limit/findFirst)
   |
   v
Stream.close() from try-with-resources
   |
   v
onClose closes resource if opened
~~~

**This is a design pattern, not a promise that all Files.lines() implementations perform late-open as above.** Factories may choose to open resources at Stream creation time.

For single-use resources, avoid assuming you can re-process the same Stream or Spliterator after a terminal operation. If you want to repeat reading, design the factory to create **one new Stream, one new resource** per pass and require the caller to close that pass properly.

### 17.1. When is writing your own Spliterator for I/O unnecessary?

Do not write your own Spliterator just to wrap an API that already provides a suitable source and manages close itself. If you need to read file lines, **Files.lines** already has clear semantics and ownership. If you need to traverse a List, use **list.stream()**. If you need a numeric range, use **IntStream.range**.

Only build a custom Spliterator when you need a special source, splitting capability, ordering, late-binding, or termination condition not well expressed by built-in APIs.

## 18. Common Mistakes in Source Design

| Mistake | Consequence | Correct Design |
| --- | --- | --- |
| Finite source does not return false when exhausted | Terminal may never terminate or repeat values | Define termination condition in tryAdvance |
| Reporting SIZED with wrong estimateSize | Stream optimizes based on wrong info | Only report SIZED when count is exact |
| Reporting SUBSIZED for branches without exact sizes | Broken partitioning contract | Ensure every branch is SIZED/SUBSIZED or drop flag |
| trySplit returns overlapping branches | Lost/duplicated data in parallel | Split disjoint intervals |
| StreamSupport Supplier reports different characteristics from Spliterator | Behavior outside API contract | Use the exact same flag set |
| Thinking `limit` always saves `sorted` on an infinite source | Sorted may need all elements | Place a reasonable bound before sort or use another algorithm |
| Thinking terminal automatically closes files | Resource leak | try-with-resources or clear ownership |
| Returning a Stream from inside a closed try-with-resources | Caller cannot consume validly | Return materialized result or transfer ownership |
| Thinking lazy pipeline always means lazy-open | Resource may already be opened in factory | Distinguish lazy traversal from late resource acquisition |
| Using a Stream once then traversing again | IllegalStateException / source consumed | Create a new Stream from a replayable source |
| Sharing a Reader across parallel trySplit arbitrarily | Races or wrong results | Choose sequential or design safe independent splitting |
| Using onClose like an auto-running terminal | onClose only runs on close | Ensure explicit close is called |
| Closing resource before terminal finishes | Read error / resource closed | Manage lifecycle spanning the entire evaluation |
| Relying on peek/filter counts for auditing | Callbacks may be skipped or short-circuited | Audit through a process with its own contract |
| Writing a custom source when standard APIs suffice | Unnecessary complexity | Prefer Files.lines, stream, range, bounded iterate |

## 19. Practice Exercises

### Exercise 1 — Predict when Supplier is called

Suppose a Stream is created with the **StreamSupport.stream(supplier, flags, false)** overload, where supplier increments a counter when creating the Spliterator. After creating the Stream but before the terminal operation, must the counter have incremented?

**Answer:** no. The supplier overload is designed to defer acquiring the Spliterator until the pipeline needs evaluation. In the lesson's example, the counter equals 0 before the terminal operation and 1 after the terminal operation.

### Exercise 2 — Designing a finite source

Describe the termination condition for the source `[startInclusive, endExclusive)`.

**Hint:** if `current >= endExclusive`, `tryAdvance` returns false and does not call Consumer. If an element remains, call Consumer with current then increment current. `estimateSize()` returns the untraversed element count, not the initial element count.

### Exercise 3 — Proper trySplit

The source has numbers 1 through 8 remaining. Split it into two independent ranges and compute the corresponding estimateSize.

**Suggested answer:** the returned Spliterator contains [1,5) = 1,2,3,4, with size 4; the original Spliterator keeps [5,9) = 5,6,7,8, size 4. No element appears in both branches.

### Exercise 4 — Closing resources after findFirst

A function opens a file and searches for the first line starting with "ERROR". If found and findFirst returns an Optional, does the file close automatically?

**Answer:** you must not rely on the terminal operation to close it. Put the file Stream in try-with-resources; it closes when leaving scope, including when found early or throwing an exception.

### Exercise 5 — Identifying wrong flag declarations

A source reads a file line by line from a BufferedReader, does not know the line count yet returns `Spliterator.SIZED` and `estimateSize() == 1000` just because the file has around 1000 lines. Is this right?

**Answer:** no. SIZED is an exact-size commitment, not a rough estimate. The source must omit SIZED if it cannot determine the exact remaining element count.

### Exercise 6 — Distinguishing lazy opening from lazy processing

An API calls `Files.lines(path)` and adds `filter(...)` without calling a terminal operation. Have the filter lambdas run yet? Has the file likely been opened already?

**Answer:** the filter lambdas do not need to have run yet. However, Files.lines is an API creating a Stream tied to an opened resource; the Stream must be closed promptly even when no terminal operation is executed.

### Exercise 7 — Infinite sources and sort

Should `Stream.iterate(0, n -> n + 1).sorted().limit(3).toList()` be used?

**Answer:** no. General sorted needs to examine the entire source to determine order and cannot wait for an infinite source to finish. If the intent is to sort the first three numbers, place `limit(3)` before sorted, while understanding that the business requirement is now different.

### Exercise 8 — Close responsibility of a factory

You write `Stream<String> openRecords(Path path)` returning a file-reading Stream. Who must close it?

**Hint:** if the factory transfers ownership to the caller, the API docs must clearly state the caller uses `try (Stream<String> records = openRecords(path)) { ... }`. The factory needs to register a close handler or use a built-in resource Stream API. If the factory owns the resource itself, do not return a Stream that outlives the resource; return the read results or execute a callback within scope.

## 20. Remember

**A good Stream source must be clear about finiteness, element creation/reading timing, and resource ownership.** These three concerns are distinct, yet directly impact correctness and performance.

- **Finite source:** define bounds, termination condition, and size when guaranteed.
- **Potentially unbounded source:** use `limit` or a valid stopping condition; watch out for stateful operations like sorted.
- **Custom Spliterator:** implement accurate `tryAdvance`, non-overlapping `trySplit`, and contract-compliant `estimateSize` and characteristics.
- **Late-binding:** the `StreamSupport.stream(Supplier, characteristics, parallel)` overload can defer Spliterator creation; the flag set must match the actual Spliterator.
- **Lazy traversal does not necessarily mean lazy-open:** a file-reading Stream may hold a resource before the terminal operation runs.
- **Terminal does not auto-close Stream:** manage files, readers, and cursors with `try-with-resources` and `onClose` when appropriate.
- **Clear ownership:** whoever opens/receives a resource is responsible for closing it at the right time, even when the terminal fails or short-circuits.
- **Parallel must be designed specifically:** partition safely, without shared mutable state or false characteristic declarations.

Before introducing a custom source into an application, ask yourself: **"When does the source end? Who generates elements? Can it stop early and split properly? When is the resource opened and where will it be closed if there is no terminal, if the terminal succeeds, or if the terminal throws an error?"** If you can answer those questions with a clear contract, the Stream will truly be easy and safe to use.