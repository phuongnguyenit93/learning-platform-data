# Pipelines Are Built First and Executed When a Terminal Operation Is Called in Java Stream

In the Java Stream API, a chain of calls such as **filter**, **map**, **sorted**, or **distinct** usually only **builds a pipeline describing how to process data**, without immediately processing each element. Pipeline evaluation typically occurs when a **terminal operation** such as **toList**, **collect**, **count**, **reduce**, **forEach**, or **findFirst** is invoked.

This characteristic is called **lazy evaluation** — evaluation on demand. It allows a Stream to combine multiple processing steps without creating intermediate collections after each step. However, if you mistakenly believe that calling map/filter immediately runs the callback, a program might miss log entries, catch exceptions in the wrong place, or assume the Stream has already updated data before a result is requested.

This lesson belongs to the **Execution Model** section and focuses on the sequence **data source → pipeline construction → terminal operation → execution**, the difference between intermediate/terminal operations, element-by-element processing, short-circuiting, optimizations, resources, exceptions, single-use Streams, and runnable Java 17+ examples.

## 1. Quick Mental Model: Build First, Consume Later

Example:

~~~java
List<String> names = List.of("An", "Binh", "Mai");

Stream<String> pipeline = names.stream()
    .filter(name -> name.length() > 2)
    .map(String::toUpperCase);

// Up to this point, no result elements have been requested.

List<String> result = pipeline.toList();
System.out.println(result); // [BINH, MAI]
~~~

The two calls **filter** and **map** are intermediate operations. They create the stages of the pipeline; the **toList()** call is a terminal operation that requests a List result and causes the Stream to evaluate the necessary elements.

You can visualize it as follows:

~~~text
PHASE 1 — CONSTRUCTION
List<String> names
       │
       └── stream() ── filter(...) ── map(...)
                                      │
                                      └── pipeline is declared

PHASE 2 — EVALUATION
pipeline ── toList()
               │
               ├── pull elements from source as needed
               ├── apply filter condition
               ├── apply map transformation
               └── collect output elements into List
~~~

This diagram illustrates the **logical** meaning; it does not describe a guarantee on the number of callback invocations or fixed internal steps across every JVM. Optimizers may skip steps that do not affect the result or choose a different strategy.

**Key takeaway:** Having a Stream object and a built pipeline does not mean the source data has been traversed or any callbacks have executed.

## 2. Three Components of a Stream Pipeline

A typical pipeline has:

1. **Source:** A Collection, array, generator, range, I/O, or other source.
2. **Intermediate operations:** filter, map, flatMap, sorted, distinct, limit, skip, peek, takeWhile… Each call creates a Stream stage.
3. **A terminal operation:** toList, collect, count, reduce, sum on primitive streams, forEach, findFirst, anyMatch… This part requests completion of the result or produces a side effect according to its contract.

| Component | Example | Role | Directly returns another Stream? |
| --- | --- | --- | --- |
| Source | names.stream(), Stream.of(...) | Provides elements | Creates the initial Stream |
| Intermediate | filter(predicate) | Keeps matching elements | Yes |
| Intermediate | map(function) | Transforms element T to R | Yes |
| Intermediate | distinct(), sorted() | Deduplicates or sorts | Yes |
| Intermediate | limit(n), skip(n) | Limits/skips elements | Yes |
| Terminal | toList(), collect(...) | Collects the result | No |
| Terminal | count(), reduce(...) | Aggregates data | No |
| Terminal | findFirst(), anyMatch(...) | Finds/checks, may stop early | No |
| Terminal | forEach(action) | Consumes elements with action | No |

**Note on laziness:** Most intermediate operations on Java Stream are lazy. However, some operations such as sorted and distinct are **stateful** and may require buffering when the terminal operation runs. “Lazy” does not mean zero memory overhead or that all elements are always processed completely independently.

### 2.1. A Stream Has a Type, Not Another List

~~~java
Stream<String> stream = names.stream()
    .filter(name -> name.length() > 2);
~~~

stream is not a new List<String> already containing the filtered names. It is **an object representing a pipeline** that can be consumed to obtain a result. When you need to access the data multiple times, keep an appropriate source or collect the result into a List and create a new Stream from it.

### 2.2. Terminal Operations Do Not Necessarily Return a Collection

~~~java
long count = names.stream().filter(s -> s.length() > 2).count();

boolean anyLong = names.stream()
    .anyMatch(s -> s.length() > 4);

Optional<String> first = names.stream()
    .filter(s -> s.length() > 2)
    .findFirst();
~~~

**count** returns long; **anyMatch** returns boolean; **findFirst** returns Optional<String>. Only certain terminal operations produce a List/Map/Set or a collection via a collector. The output data type depends on the **terminal operation**, not on whether the source is a List.

## 3. Verifying Laziness with a Counter in a Controlled Example

Consider:

~~~java
List<String> source = List.of("An", "Binh", "Mai", "Duyen");
AtomicInteger visits = new AtomicInteger();

Stream<String> pipeline = source.stream()
    .filter(name -> {
        visits.incrementAndGet();
        return name.length() > 2;
    })
    .map(String::toUpperCase);

System.out.println("after-build=" + visits.get());

List<String> result = pipeline.toList();

System.out.println("result=" + result);
System.out.println("after-terminal=" + visits.get());
~~~

This is an illustrative snippet inside a method with List, Stream, and AtomicInteger imported. With the source and the **toList** terminal in the tested Java 17 example, the output is:

~~~text
after-build=0
result=[BINH, MAI, DUYEN]
after-terminal=4
~~~

**Explanation:** Before calling toList(), the visits counter remains 0. When toList() demands the result elements, four source strings are checked against the filter condition; the three strings with length greater than 2 proceed to be mapped to uppercase.

This is an **observational experiment** to learn when callbacks run, not a practice pattern for putting side effects into filter. In business code, Stream callbacks should be as **stateless** and **non-interfering** as possible. Some terminal operations and source characteristics allow optimizations that skip unnecessary callbacks, so you cannot use a counter inside map/filter as an auditing mechanism that guarantees execution counts.

### 3.1. Why Can You Build a Pipeline Without Printing Anything?

~~~java
Stream<String> pipeline = names.stream()
    .map(name -> {
        System.out.println("mapping " + name);
        return name.toUpperCase();
    });

System.out.println("constructed");
~~~

With the operations above, there is no terminal operation yet, so the map callback is **not required to run**. If pipeline.toList() is called afterward, producing the result may cause the map callback to be evaluated. However, you should not rely on the number of println calls from map to define business requirements, because the Stream API allows optimizations that eliminate steps not affecting the result.

## 4. Pipelines Are Fused Element-by-Element, Not Necessarily List-by-List

Beginners sometimes assume a pipeline always works like this:

~~~text
Step 1: filter the entire source into List A
Step 2: map the entire List A into List B
Step 3: return List B
~~~

That is **not a general requirement** of Java Stream. For a stateless pipeline like filter followed by map, the runtime can execute in a **vertical processing** data flow:

~~~text
Element "An"    → filter false → discard
Element "Binh"  → filter true  → map "BINH"  → send to terminal
Element "Mai"   → filter true  → map "MAI"   → send to terminal
Element "Duyen" → filter true  → map "DUYEN" → send to terminal
~~~

This approach avoids creating a List A after filter and a List B after map. That is one of the benefits of a pipeline.

**Do not infer an absolute callback order** from the diagram. Execution order also depends on the source, stateful operations, short-circuiting, parallel mode, and valid optimizations. The result contract matters more than the exact moment a callback is invoked.

### 4.1. Stateless Operations

Steps such as filter and map are typically **stateless intermediate operations** if the callback does not use mutable state that depends on other elements.

~~~java
List<Integer> squares = List.of(1, 2, 3, 4).stream()
    .filter(number -> number % 2 == 0)
    .map(number -> number * number)
    .toList();
~~~

The result is [4, 16]. There is no need to create a temporary List containing only 2,4 before squaring.

### 4.2. Stateful Operations

**sorted()** needs to examine the order of elements, so it usually must collect enough relevant data before it can emit properly sorted results. **distinct()** needs to remember previously seen elements, depending on the source and strategy.

~~~java
List<String> result = Stream.of("pear", "apple", "pear", "fig")
    .distinct()
    .sorted()
    .toList();
~~~

The result is [apple, fig, pear].

A “lazy pipeline” does not mean every intermediate operation processes an element immediately and discards it. With sorted on large datasets, retaining many elements in memory can be significant.

### 4.3. Building a Pipeline Does Not Mean Data Errors Have Been Detected

If a callback contains logic that can throw an exception:

~~~java
Stream<Integer> parsed = Stream.of("10", "wrong")
    .map(Integer::parseInt);
~~~

Declaring parsed does not immediately convert all data into Integer. When a terminal operation actually requests the "wrong" element, Integer.parseInt can throw NumberFormatException.

However, **not every exception is deferred**: errors during argument validation or source creation, such as calling a method on a null source variable, can happen at construction time. It is only accurate to say that **executing the per-element logic of intermediate operations is typically deferred**.

## 5. Short-Circuiting: Terminals That Do Not Need to Traverse the Entire Source

Some terminal operations can return a result early, such as **findFirst, findAny, anyMatch, allMatch, noneMatch**. This allows preceding filters or mappers to run on only part of the source.

Example with an ordered List and a sequential stream:

~~~java
List<String> source = List.of("An", "Binh", "Mai", "Duyen");
AtomicInteger tested = new AtomicInteger();

Optional<String> first = source.stream()
    .filter(name -> {
        tested.incrementAndGet();
        return name.length() >= 4;
    })
    .findFirst();

System.out.println(first.orElse("none")); // Binh
System.out.println(tested.get());         // 2
~~~

With the source above and a sequential pipeline, the first element "An" does not satisfy the condition, and the second element "Binh" satisfies it. findFirst does not need to request subsequent elements, so the number of checks in this example is 2.

**Do not treat 2 as an invariant invocation count for all stream structures.** If you switch to a parallel stream, add sorted, change the source, or change the terminal operation, the evaluation strategy may differ.

### 5.1. anyMatch and allMatch

~~~java
boolean found = Stream.of("Go", "Java", "Rust")
    .anyMatch(name -> name.length() == 4); // true
~~~

In a typical sequential stream, anyMatch can stop upon encountering "Java". Similarly:

- allMatch can stop when an element fails the condition.
- noneMatch can stop when an element satisfies the condition.
- findAny can pick any matching element without promising to preserve encounter order like findFirst on an ordered stream.

These operations have **short-circuiting opportunities**, but you should not use short-circuiting as a way to guarantee that a side effect in a callback will run exactly once.

### 5.2. limit and takeWhile

~~~java
List<Integer> firstThree = IntStream.rangeClosed(1, 100)
    .limit(3)
    .boxed()
    .toList();
~~~

The result is [1, 2, 3]. A pipeline with limit may avoid requesting elements beyond the limit when sufficient data and suitable conditions exist.

Java 9+ provides **takeWhile** and **dropWhile**. On an ordered stream, takeWhile keeps the leading contiguous prefix that still satisfies the predicate; unlike filter, it does not take every matching element at any position.

~~~java
List<Integer> prefix = Stream.of(1, 2, 3, 1, 2)
    .takeWhile(x -> x < 3)
    .toList();
~~~

The result is [1,2], not [1,2,1,2]. Intermediate steps like takeWhile remain pipeline descriptions until a terminal operation evaluates them.

## 6. Terminal Operations May Optimize and Skip Callbacks

A common misconception: “If I call count(), the preceding filter, map, or peek definitely ran on every element.” This is **not always true**.

For a source with a known size and a pipeline that does not change the number of elements, Stream can determine count **without traversing each element**. Example:

~~~java
long total = List.of("A", "BB", "CCC").stream()
    .map(String::toUpperCase)
    .count();
~~~

The result is 3. With a List source of known size, counting can be optimized without invoking map on each element. Therefore:

~~~java
// Do not expect this map callback to always execute:
long total = names.stream()
    .map(name -> {
        recordAudit(name); // hypothetical side effect
        return name.toUpperCase();
    })
    .count();
~~~

The snippet above only illustrates a design flaw; **recordAudit** is not a standard Java API or a method defined in the runnable sample program.

**Rule:** Stream is allowed to skip a step if it can prove that the step does not affect the terminal result under its contract. Side effects in intermediate operations are not a reliable mechanism for recording audits or mutating critical state.

### 6.1. peek Is Only for Conditional Observation/Debugging

~~~java
Stream<String> pipeline = names.stream()
    .peek(System.out::println);
~~~

peek is an **intermediate operation**, not a terminal one. It does not automatically print data just because the pipeline is constructed. Even when a terminal operation is present, optimizations or short-circuiting can prevent peek calls from happening as you expect.

Use peek consciously for diagnosing pipelines; do not use peek to update a database, send notifications, calculate monetary amounts, or maintain critical business state.

### 6.2. forEach Is Terminal, but Order Requires Attention

~~~java
names.stream().forEach(System.out::println);
~~~

forEach is terminal, so it requests consumption of the matching elements. With a parallel stream, **forEach does not guarantee encounter order** of the actions. If displaying in source order is strictly required, use **forEachOrdered** on an ordered stream, while accepting the corresponding performance characteristics.

Do not rely on the print order of peek/map in a parallel stream to deduce the order of collected data.

## 7. Errors from Callbacks Typically Surface During Terminal Execution

Consider:

~~~java
Stream<String> pipeline = Stream.of("ok", "bad", "later")
    .map(value -> {
        if (value.equals("bad")) {
            throw new IllegalArgumentException("bad element");
        }
        return value.toUpperCase();
    });

System.out.println("pipeline built");

try {
    pipeline.toList();
} catch (IllegalArgumentException error) {
    System.out.println(error.getMessage());
}
~~~

In this example, building the pipeline and printing "pipeline built" happen first. When toList attempts to collect the results, the map lambda encounters "bad" and throws IllegalArgumentException.

Important points:

1. **Building the pipeline** does not automatically invoke map on each element.
2. **The terminal operation** triggers the necessary processing.
3. Exceptions from a lambda can propagate through the terminal call.
4. After a failed terminal operation, do not reuse the consumed Stream; create a new Stream if you need to retry with an appropriate source.

In a callback chain receiving I/O data, exceptions can occur when the source is traversed or an element is mapped, not necessarily when calling the API that creates the source. However, some I/O sources can also throw IOException **immediately upon opening**; you must distinguish between the two phases.

## 8. A Stream Can Only Be Used Once Even After the Pipeline Is Built

A Stream pipeline has a single-use lifecycle.

~~~java
Stream<String> pipeline = names.stream()
    .filter(s -> !s.isBlank());

List<String> result = pipeline.toList();

// Wrong: the same Stream has already been used.
long count = pipeline.count();
~~~

After a terminal operation completes, the same Stream instance cannot continue processing a new pass. Some reuse scenarios can cause an **IllegalStateException**; the API contract requires not reusing it even if an implementation happens not to detect a specific kind of reuse.

If you need results from the same **Collection** multiple times:

~~~java
List<String> result = names.stream()
    .filter(s -> !s.isBlank())
    .toList();

long count = names.stream()
    .filter(s -> !s.isBlank())
    .count();
~~~

The two names.stream() calls create two new pipelines from the Collection source. It is **not** the same Stream instance being run again.

### 8.1. Supplier<Stream<T>> When You Need a Fresh Pipeline

You can define a factory:

~~~java
Supplier<Stream<String>> newStream =
    () -> names.stream().filter(s -> !s.isBlank());

List<String> result = newStream.get().toList();
long count = newStream.get().count();
~~~

Each get() call here creates a new Stream. If the factory returns a cached Stream, it does not solve the one-shot rule. With I/O sources, creating a new Stream can mean **reopening the source** and having to manage resources for each pass.

### 8.2. Do Not Call a Terminal Operation and Chain an Intermediate Operation Afterward

~~~java
// Invalid type if you continue using a Stream operator:
names.stream().count().filter(x -> true);
~~~

count returns long, not a Stream. At the API level, a terminal operation ends the pipeline call chain; at the lifecycle level, it also consumes the corresponding Stream.

## 9. Pipelines with Infinite Sources or Large Data

Laziness is beneficial when a source generates elements on demand:

~~~java
List<Integer> firstFive = Stream.iterate(1, n -> n + 1)
    .limit(5)
    .toList();
~~~

The result is [1,2,3,4,5]. Stream.iterate can generate an unbounded sequence; limit is an intermediate step that helps the terminal toList stop after obtaining enough elements.

Conversely:

~~~java
// Should not be executed with an infinite iterate source:
Stream.iterate(1, n -> n + 1).count();
~~~

count cannot finish by traversing an entire general infinite source. Processing data lazily does not mean **every terminal operation will terminate**.

### 9.1. Stateful Operations Can Cause a Pipeline to Accumulate Large Amounts of Data

Example:

~~~java
Stream<Integer> pipeline = Stream.iterate(1, n -> n + 1)
    .sorted();
~~~

If a terminal operation needs completely sorted data from an infinite source, the pipeline may be unable to produce a result in finite time. Even with a large finite source, sorted typically has to retain many elements in order to sort them.

You must understand **finiteness**, **short-circuiting**, and **stateful operations** when designing large-scale data processing.

### 9.2. Not Every Pipeline Keeps O(1) Memory

filter/map on a sequential source can execute in a one-element-at-a-time streaming fashion. However, distinct, sorted, groupingBy, toList, and other stateful operations can accumulate data. Lazy evaluation does not guarantee zero memory allocation or constant space complexity.

## 10. Data Sources, Late Binding, and Non-Interference

A Stream can be obtained from a Collection:

~~~java
List<String> names = new ArrayList<>(List.of("An", "Binh"));

Stream<String> pipeline = names.stream()
    .filter(s -> s.length() > 2);
~~~

Even though the pipeline does not have a terminal operation yet, this **does not allow arbitrarily mutating the source Collection** and expecting the result to always stay the same. The Stream contract requires callbacks not to interfere with the source and that the source state is not illegally modified while the pipeline is in use.

Some Spliterator sources have a **late binding** mechanism, meaning binding elements to the source can be deferred until the evaluation phase; however, that is no reason to rely on mutations between Stream creation and the terminal operation.

### 10.1. Safe Approach When a Snapshot Is Needed

If the source is mutable and you need results over a **data-structure snapshot**, create an appropriate independent copy beforehand:

~~~java
List<String> snapshot = List.copyOf(names);

List<String> result = snapshot.stream()
    .filter(s -> s.length() > 2)
    .toList();
~~~

List.copyOf creates a structurally unmodifiable List, but it does not automatically deep-copy mutable elements. For immutable Strings, sharing elements is reasonable; for mutable objects, consider a deep snapshot if the data can change externally.

### 10.2. Stateless Callbacks and Parallel Streams

~~~java
List<String> result = names.parallelStream()
    .filter(s -> s.length() > 2)
    .map(String::toUpperCase)
    .toList();
~~~

The pipeline can process elements across multiple threads. Do not write filter/map callbacks that depend on an unsynchronized counter or mutate the same source List. Parallelism does not change the conceptual timing: the intermediate pipeline is defined first and the terminal operation requests evaluation; however, **the order and work-splitting strategy** can differ.

## 11. Combining Stream with I/O and AutoCloseable

Some Streams do not merely read in-memory data; they can hold external resources, such as **Files.lines(Path)**.

~~~java
try (Stream<String> lines = Files.lines(path)) {
    List<String> matching = lines
        .filter(line -> line.startsWith("INFO"))
        .toList();
}
~~~

This snippet requires importing Files, Path, Stream, List and handling IOException. **Files.lines** may open the resource as soon as it is called to create the Stream; the filter pipeline is evaluated on demand by the terminal operation. Therefore, you must distinguish:

- **Creating an I/O source:** may open the file, allocate resources, or fail immediately.
- **Building the intermediate pipeline:** usually has not read/processed lines with callbacks yet.
- **Running the terminal:** may start/continue reading lines and executing filter/map.
- **Closing the Stream:** releases resources attached to the source, which must be done even if the terminal throws an error.

**A terminal operation does not automatically replace close.** Use try-with-resources for Streams with I/O sources such as Files.lines, Files.walk, Files.list, and Files.find. For pure in-memory Streams from a List, closing is normally unnecessary because no external resources are held.

### 11.1. Even Without a Terminal Operation, Opened Source Resources Must Still Be Closed

~~~java
try (Stream<String> lines = Files.lines(path)) {
    Stream<String> selected = lines.filter(s -> !s.isBlank());
    // No terminal operation is called in this example.
}
~~~

Even when line processing is not requested, Files.lines can still hold an open resource. try-with-resources ensures closing upon exiting the block. Thus, **lazy element processing does not mean lazy resource acquisition**.

### 11.2. I/O Exceptions Can Occur at Multiple Stages

- IOException can occur when calling Files.lines to open the source.
- UncheckedIOException can occur when traversing the Stream's lines, per the API contract.
- Errors in map/filter callbacks can occur when the terminal needs an element.
- Close errors can occur when exiting try-with-resources.

Code design should have error-handling boundaries aligned with the resource lifecycle, rather than only catching exceptions around an intermediate call.

## 12. Distinguishing Stream Lazy Evaluation from General Deferred Computation

Lazy evaluation in Stream does not mean every Java expression is lazy. An argument passed to a regular Java method call is still evaluated according to language rules before the method is invoked, except for specific language/API constructs.

Example:

~~~java
List<String> names = loadNames();
Stream<String> pipeline = names.stream().map(String::trim);
~~~

This illustrative snippet assumes a loadNames method exists. **loadNames() runs to produce the List before the Stream exists**; Stream.map does not make the loadNames() call lazy.

Similarly:

~~~java
String prefix = calculatePrefix();
Stream<String> pipeline = names.stream()
    .map(name -> prefix + name);
~~~

calculatePrefix runs when assigning prefix, before the terminal operation. Only applying the **map lambda to each name** is deferred by the Stream mechanism.

If you want to defer data creation, you can design a Supplier, generator, Stream.iterate/generate, or an I/O source depending on your goal; you cannot simply place a call in a Java expression and expect it to defer itself automatically.

### 12.1. A Lambda Describes Behavior; Calling the Lambda Executes Its Body

When you write:

~~~java
Function<String, String> upper = text -> text.toUpperCase();
~~~

a function object is created, but the body text.toUpperCase does not run immediately. With Stream, the callbacks are held by the pipeline operations and invoked during terminal evaluation when needed. This is why **you should not confuse defining a lambda with invoking a lambda**.

Outside the Stream API, calling upper.apply("java") executes the lambda directly; there is no concept of a Stream terminal operation here.

## 13. Complete Java 17+ Program

This program uses a List source, AtomicInteger to **observe when callbacks run**, stateful operations, short-circuiting, and a callback that intentionally throws an error. All results are printed clearly and have been tested with **javac --release 17**.

Create the file **StreamPipelineExecutionDemo.java**:

~~~java
import java.util.List;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class StreamPipelineExecutionDemo {
    public static void main(String[] args) {
        List<String> source = List.of("An", "Binh", "Mai", "Duyen");
        AtomicInteger visits = new AtomicInteger();

        Stream<String> pipeline = source.stream()
            .filter(name -> {
                visits.incrementAndGet();
                return name.length() > 2;
            })
            .map(String::toUpperCase);

        System.out.println("after-build=" + visits.get());
        System.out.println("result=" + pipeline.toList());
        System.out.println("after-terminal=" + visits.get());
        System.out.println("source=" + source);

        AtomicInteger tested = new AtomicInteger();
        Optional<String> first = source.stream()
            .filter(name -> {
                tested.incrementAndGet();
                return name.length() >= 4;
            })
            .findFirst();
        System.out.println("first=" + first.orElse("none"));
        System.out.println("tested=" + tested.get());

        System.out.println("sorted=" + Stream.of("pear", "apple", "pear", "fig")
            .distinct().sorted().toList());

        System.out.println("odd-sum=" + IntStream.rangeClosed(1, 5)
            .filter(number -> number % 2 == 1).sum());

        Stream<String> delayedError = Stream.of("ok", "bad", "later")
            .map(value -> {
                if (value.equals("bad")) {
                    throw new IllegalArgumentException("bad element");
                }
                return value.toUpperCase();
            });
        System.out.println("error-pipeline-built");
        try {
            delayedError.toList();
        } catch (IllegalArgumentException error) {
            System.out.println("terminal-error=" + error.getMessage());
        }

        try {
            pipeline.count();
        } catch (IllegalStateException error) {
            System.out.println("reuse=" + error.getClass().getSimpleName());
        }
    }
}
~~~

Compile and run in the directory containing the file using **JDK 17 or later**:

~~~bash
javac StreamPipelineExecutionDemo.java
java StreamPipelineExecutionDemo
~~~

**Exact stdout:**

~~~text
after-build=0
result=[BINH, MAI, DUYEN]
after-terminal=4
source=[An, Binh, Mai, Duyen]
first=Binh
tested=2
sorted=[apple, fig, pear]
odd-sum=9
error-pipeline-built
terminal-error=bad element
reuse=IllegalStateException
~~~

### 13.1. Explanation of the Results

**after-build=0:** Calling filter/map to create the pipeline did not request evaluation of the List elements.

**result:** toList demanded the result elements and completed the filtering/mapping in the example; the three qualifying names were converted to uppercase.

**after-terminal=4:** Four names were examined by the filter during collection into the List. This number belongs to **this specific tested pipeline**, not a general callback-count contract.

**source:** The original List remains [An, Binh, Mai, Duyen], because filter and map do not modify the source in this example.

**first=Binh and tested=2:** findFirst on an ordered sequential stream stopped upon finding the first name with at least four characters.

**sorted:** distinct removed the duplicate "pear"; sorted ordered the remaining values according to String natural order.

**odd-sum=9:** IntStream.rangeClosed generated numbers 1 to 5; filtering odd numbers and then calling sum gave 1+3+5=9.

**error-pipeline-built:** the map callback had not yet been evaluated on the "bad" element when the pipeline was created.

**terminal-error=bad element:** when toList executed the pipeline, the lambda encountered "bad" and threw IllegalArgumentException; the error was caught at the terminal boundary.

**reuse=IllegalStateException:** after toList, attempting to run count on the same Stream instance is invalid; the example illustrates the behavior observed on JDK 17.

### 13.2. Why Does the Example Use AtomicInteger?

AtomicInteger helps track the number of callback invocations in an observational experiment without needing to mutate a local int variable restricted by the effectively final rule. However, **atomic does not mean business logic should have side effects in filter**. Do not copy this counter as a required part of a parallel algorithm; if you only need to count elements, use count and the Stream contract.

## 14. Distinguishing Terminal Operations When Reading Code

| Terminal | Common result type | Things to note |
| --- | --- | --- |
| toList() | List<T> | Java 16+ returns an unmodifiable List |
| collect(toList()) | List<T> | Collector does not guarantee a specific implementation/mutability |
| count() | long | Can be optimized, does not always invoke every callback |
| reduce(...) | T, Optional<T>, or U | Requires an appropriate reduction rule |
| findFirst() | Optional<T> | Short-circuits, mind encounter order |
| findAny() | Optional<T> | Does not promise to pick the first element in order |
| anyMatch/allMatch/noneMatch | boolean | Can short-circuit |
| forEach(action) | void | Does not guarantee order on parallel streams |
| forEachOrdered(action) | void | Preserves encounter order when the source is ordered |
| min/max(comparator) | Optional<T> | Selects extremum according to comparator |
| IntStream.sum() | int | Terminal on primitive stream |

A code-reading mistake is assuming **count** necessarily executes the entire map/peek logic chain just like **toList**. Remember that different terminals need **different information**: count may only need the size, findFirst only needs the first matching element, whereas toList must build the result list.

**Summary:** Having a terminal operation **triggers the evaluation needed to produce the result**; it does not mean every callback in the pipeline is guaranteed to be called, or called the same number of times and in the same order on every JVM.

## 15. Common Misconceptions and Pitfalls

**Mistake 1 — expecting map/filter to run immediately when declared.** Intermediate operations normally only build the pipeline. When you need a result, call an appropriate terminal operation.

**Mistake 2 — building a pipeline without a terminal and assuming the logic executed.** A Stream that is created but never consumed may not run any element-processing lambdas. If you genuinely want to produce data, collect into a List/collector or use a terminal operation per its contract.

**Mistake 3 — using peek or map as a mandatory audit log.** Callbacks may not run due to optimizations, short-circuiting, or processing order; perform side effects at clearly designed boundaries.

**Mistake 4 — viewing a pipeline as a list of full-pass traversals.** Stateless operations can be fused to process element-by-element, avoiding intermediate collections.

**Mistake 5 — thinking lazy means zero RAM usage.** sorted, distinct, collect, toList, and other stateful operations can still require storing significant data.

**Mistake 6 — treating findFirst as equivalent to count.** findFirst can stop early; count usually needs to compute the count, though it can also be optimized based on a known size.

**Mistake 7 — forgetting that a Stream is single-use.** After a terminal operation, do not reuse the Stream; create a new Stream from a re-traversable source.

**Mistake 8 — confusing construction-time errors with terminal-time errors.** Argument-validation errors can happen early; errors inside element-processing lambdas usually appear when the pipeline is evaluated.

**Mistake 9 — modifying the source Collection while the pipeline is active.** Violating non-interference can cause errors or unreliable results, especially in parallel.

**Mistake 10 — thinking a parallel stream always processes in the same order.** Do not use callbacks as a place to rely on absolute order or update shared mutable state.

**Mistake 11 — forgetting to close I/O sources.** Files.lines can open resources as soon as the Stream is created; even if the pipeline has no terminal operation, it must still be closed when unused.

**Mistake 12 — assuming an infinite Stream.iterate with count will always return.** With an infinite source and no appropriate bound, the terminal operation may never terminate.

**Mistake 13 — thinking Stream.toList has the same mutability as Collectors.toList.** Stream.toList returns an unmodifiable List in Java 17; Collectors.toList makes no specific guarantee.

**Mistake 14 — using side effects to benchmark performance.** Callback counters can be elided by the optimizer and thus fail to measure true total cost, especially with parallel streams. Use proper profiling/benchmarking and semantic results as the baseline.

**Mistake 15 — calling multiple terminals to obtain multiple kinds of results.** A single Stream cannot run count and then toList. If the source is a Collection, create a new pipeline for each operation or design a single collect operation that returns multiple statistics at once.

## 16. Checklist When Reviewing a Stream Pipeline

- **What is the source?** Collection, array, I/O, or generator? Can it be traversed again?
- **Which steps are intermediate?** filter, map, sorted, distinct, limit, peek…
- **Is there a terminal operation?** toList, count, collect, reduce, findFirst…
- **When do callbacks execute?** Typically when a terminal demands element evaluation.
- **Is there short-circuiting or optimization?** count may skip map; findFirst may stop early.
- **Are there stateful operations?** sorted and distinct may require buffering.
- **Are there side effects?** Do not depend on callback invocation counts to perform mandatory business logic.
- **Is the Stream being reused?** Each instance is for a single consumption pass only.
- **Is the source mutable?** Avoid modifying the source against the contract; consider an appropriate snapshot.
- **Is I/O involved?** Manage close and errors both when opening the source and during terminal traversal.
- **Is there parallelism?** Review encounter order, concurrency, and shared state.
- **Is the source infinite?** Ensure the terminal operation is capable of terminating.

## 17. Self-Check Questions

1. Distinguish between the pipeline construction phase and the element evaluation phase of a terminal operation.
2. Why does creating a Stream with filter/map not necessarily invoke those lambdas?
3. Why does toList need the output data while count can skip map on a List source with a known size?
4. How do intermediate operations and terminal operations differ in return type?
5. Why can findFirst inspect fewer elements than count?
6. Why might sorted require buffering even though the pipeline is still lazy?
7. Why should you not log audits inside peek?
8. When can an exception from Integer.parseInt inside map be thrown?
9. After pipeline.toList(), is it valid to call pipeline.count()?
10. If you must process the same List twice, how do you create a new Stream?
11. Why might Files.lines need to be closed even when there is no terminal operation?
12. Why does laziness not mean every Java call in a pipeline-building expression is deferred?
13. Stream.generate/iterate can create infinite sources; what condition helps a terminal operation terminate?
14. With a parallel stream, which expectations about order and callback invocation counts are unsafe?
15. Why do filter/map not modify the source Collection themselves, and when can a callback cause unexpected mutation?
16. Rewrite a pipeline with side effects so that the business result does not depend on the number of callback invocations.

**Conclusion:** Java Stream **builds the pipeline with intermediate operations first**, then **evaluates the necessary data when a terminal operation is invoked**. Not every element or callback has to run for every terminal operation, due to short-circuiting, optimizations, and stateful operations. Understanding the exact timing of execution helps you write readable, correct Streams, avoid Stream reuse, avoid hidden side effects, and manage I/O resources properly.