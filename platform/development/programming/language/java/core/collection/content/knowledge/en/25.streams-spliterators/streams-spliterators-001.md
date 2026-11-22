# Collections Store Data While Streams Describe Processing

## 1. Two Roles to Distinguish

Suppose an application holds four people's names:

~~~text
[Lan, An, Mai, Bo]
~~~

We want to select the names with at least three characters, then convert them to uppercase. There are two distinct tasks here:

- **Holding data:** which names are currently present, in what order, and at which positions.
- **Processing data:** checking lengths, skipping names that do not qualify, converting the remaining names to uppercase, and producing a result.

A `List<String>` is a form of `Collection` used to represent the group of stored elements. A `Stream<String>` describes a sequence of processing steps over a source of elements. A Stream can read from that collection, but it is not another list that was just copied out.

The Java documentation distinguishes Stream from Collection in that a Stream is not a data structure that stores elements, can process lazily, may have a source without a predetermined bound on the number of elements, and can only be used once. [Java SE 17 — java.util.stream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/package-summary.html).

Initial mental model:

~~~text
Collection holds elements
        |
        | create stream from source
        v
source -> processing steps -> terminal operation -> result
~~~

The final result can be a new list, a sum, a boolean answer, a found element, or a requested side effect. Using a Stream does not always mean creating another Collection.

After this lesson, you should be able to read a pipeline in terms of its three parts, know when element processing begins, distinguish the source from the result, and understand why you should not store a Stream to traverse it repeatedly like a list.

## 2. Collection Is a Data Model, Stream Is a Computation Model

### 2.1. Collection Answers Questions About a Group of Elements

`Collection<E>` is the root interface of the collection hierarchy. Types such as `List`, `Set`, and `Queue` provide more specific contracts. Methods such as `size`, `contains`, or `iterator` work with the group of elements being represented. Whether elements can be added or removed depends on the implementation; not every Collection is modifiable. [Java SE 17 — Collection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html).

Example:

~~~java
List<String> names = new ArrayList<>(List.of("Lan", "An", "Mai", "Bo"));
~~~

`names` holds four string references. You can read `names.get(0)`, call `names.size()`, or create multiple iterators across repeated uses.

Saying "Collection stores data" is a model for separating responsibilities; it does not mean every Collection object always owns an independent backing store. A view such as `map.values()` or `list.subList(...)` can share the underlying structure. The key point is that it represents a group of elements for access, whereas a Stream represents a processing pipeline over elements supplied by a source.

### 2.2. Stream Answers What to Do With the Elements

~~~java
Stream<String> selected = names.stream()
        .filter(name -> name.length() >= 3)
        .map(name -> name.toUpperCase(Locale.ROOT));
~~~

This is an illustrative snippet inside a method, requiring imports for `Stream`, `Locale`, and the relevant collection classes.

`selected` is not a `List` already containing `LAN` and `MAI`. It describes:

1. Take elements from `names`.
2. Pass forward only names that are at least three characters long.
3. Convert each forwarded name to uppercase.

There is no terminal operation yet to request a result. Only after adding:

~~~java
List<String> result = selected.toList();
~~~

do we get the result list `[LAN, MAI]` for the given data. `result` is a new data object holding the result; `selected` is a pipeline that has been consumed.

### 2.3. Comparison Table by Responsibility

| Question | Collection | Stream |
| --- | --- | --- |
| Does it represent a group of data for storage and access? | Yes, according to the contract of the collection type | Pulls elements from a source through a pipeline |
| Does it necessarily have indices? | Only some types, such as List | Does not have List's `get(index)` operation |
| Can it be asked to reprocess the same source? | Can create a new traversal if the source is still usable | Must create a new Stream; cannot reuse the old pipeline |
| Is the element count always known upfront? | Has a `size` method in the Collection contract | May need to be computed, and may not have a finite bound |
| Does filtering remove from the source? | A mutating operation like `removeIf` can remove if supported | `filter` selects elements for the processing pipeline |
| Must the result be a collection? | Itself represents a group of elements | No; it can be a number, Optional, boolean, or another result |

There is no conclusion that Stream is "better" than Collection. The two roles complement each other: store data using an appropriate structure, then use an appropriate traversal or computation to produce the result.

## 3. A Pipeline Consists of a Source, Intermediate Operations, and a Terminal Operation

Consider the full expression:

~~~java
List<String> result = names.stream()
        .filter(name -> name.length() >= 3)
        .map(name -> name.toUpperCase(Locale.ROOT))
        .toList();
~~~

| Part | Role in the example |
| --- | --- |
| `names.stream()` | Creates a sequential Stream from the collection source |
| `filter(...)` | Intermediate operation selecting which elements proceed |
| `map(...)` | Intermediate operation computing an output value for each proceeding element |
| `toList()` | Terminal operation collecting the results into a list |

A pipeline can have no intermediate operations at all, such as `names.stream().count()`. It can also have multiple filtering, mapping, or sorting steps before terminating.

By the `Stream` contract, computation on the source begins when the terminal operation is initiated; behavioral functions in the pipeline must comply with non-interference with the source and should generally be stateless with respect to mutable external state. [Java SE 17 — Stream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html).

### Intermediate Operations Are Not Intermediate Collections

A common misconception is to picture it as:

~~~text
finish filtering and create a new List
then uppercase that entire List
then create another new List
~~~

That is not what each call to `filter` or `map` must do. They build stages within the same pipeline. Multiple stages can be fused when processing elements without creating a full list after every stage.

However, you must not conclude from this that every pipeline needs no temporary memory. An operation such as `sorted` may need to buffer data to determine order before passing results downstream. "A Stream is not a storage structure for elements" and "an algorithm's implementation may use a buffer" are compatible statements.

## 4. Laziness: Element Processing Steps Do Not Run Until a Result Is Requested

To observe this, we can log calls in a sequential example:

~~~java
List<String> trace = new ArrayList<>();

Stream<String> plan = names.stream()
        .filter(name -> {
            trace.add("filter:" + name);
            return name.length() >= 3;
        })
        .map(name -> {
            trace.add("map:" + name);
            return name.toUpperCase(Locale.ROOT);
        });
~~~

Right after creating the pipeline, `trace` is still empty. The lambdas have not been invoked on any elements just because we wrote `filter` and `map`.

When `plan.toList()` is called, the example demonstrates the processing path:

~~~text
Lan -> passes filter -> mapped to LAN -> added to result
An  -> fails filter
Mai -> passes filter -> mapped to MAI -> added to result
Bo  -> fails filter
~~~

There is no `map:An` or `map:Bo` because those two elements were stopped at the filter step. Tracing the element-by-element path helps clarify stage fusion, instead of assuming that all filtering must always produce a new dataset before mapping can begin.

The trace entries in `trace` are only for observing this specific sequential pipeline in the lesson. They are not a design pattern for updating business state inside lambdas; nor should you take this exact example with a recording `ArrayList`, run it in parallel, and assume it is thread-safe.

### Laziness Does Not Mean Nothing Has Happened Yet

Pipeline objects may already have been created, and arguments are still evaluated and validated. An I/O source may have already opened a resource as soon as the Stream is created, even though all elements have not been read yet.

For example, `Files.lines(path)` returns a Stream tied to an open file. The fact that lines are read lazily does not excuse skipping the obligation to close the file. Therefore, the accurate statement is that intermediate operations do not by themselves execute all element processing, not "nothing at all happens before a terminal operation is called."

### Errors in Processing Functions Can Surface Late

Illustrative snippet:

~~~java
Stream<Integer> parsed = List.of("1", "bad").stream()
        .map(Integer::parseInt);
~~~

Creating the pipeline does not mean the string `"bad"` has already been parsed. A terminal operation that actually needs the numeric values, such as `parsed.mapToInt(Integer::intValue).sum()`, will fail when processing the invalid data.

You should not wrap only the Stream creation in a try-catch and assume all conversion errors are covered. Error handling must cover where the pipeline is actually executed.

## 5. The Terminal Operation Determines the Result to Compute

From the same `names` source, you can ask different questions:

~~~java
long total = names.stream().count();

long longNameCount = names.stream()
        .filter(name -> name.length() >= 3)
        .count();

int totalLength = names.stream()
        .mapToInt(String::length)
        .sum();
~~~

With `[Lan, An, Mai, Bo]`, the three results are `4`, `2`, and `10`, respectively. There is no need to create a list of lengths just to compute the sum. `mapToInt` creates an `IntStream`, which is suited for operations on primitive values.

Some terminal operations can stop before processing the entire source. For example:

~~~java
String first = names.stream()
        .filter(name -> name.startsWith("M"))
        .findFirst()
        .orElse("none");
~~~

In an ordered sequential example, once `Mai` is found, the answer is already known. There is no need to continue checking `Bo`. `findFirst` expresses the request for the first element in the encounter order of an ordered source; `Optional` models the possibility that no result is found.

Thus, "having a terminal operation" does not mean "every element must pass through every lambda." The algorithm only needs to compute enough information for the result required by the contract.

### count May Not Need to Traverse Every Element

If the count is already known and the stages do not change the number of elements, the implementation can compute `count` without executing steps that do not affect the result. The documentation explicitly notes this optimization possibility. [Java SE 17 — Stream.count](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#count()).

An illustrative snippet you should not rely on for required work:

~~~java
long count = names.stream()
        .peek(System.out::println)
        .count();
~~~

Never place a critical requirement such as recording a transaction, mandatory validation, or updating a database inside `peek` and rely on `count` to ensure it runs. The printed lines might not appear if the implementation deduces the count without traversing.

If the main goal is to perform an action on each element, use an operation designed for that purpose, or an explicit loop. Stream optimizations are part of why data transformations should be separated from side effects unrelated to the result.

## 6. A Stream Is a Single-Use Execution, Not a Freely Reusable Recipe

Common mistake:

~~~java
Stream<String> selected = names.stream()
        .filter(name -> name.length() >= 3);

long count = selected.count();
List<String> list = selected.toList();
~~~

Calling `count` has already consumed the pipeline. You cannot reuse `selected` for `toList`. In the demonstration program, reuse is detected and throws `IllegalStateException`.

You should not use exceptions as a mechanism to check whether a Stream is still usable. The contract forbids reuse; an implementation is not required to detect every possible reuse. Once a pipeline has been passed to a terminal operation, treat it as consumed.

Nor can you split two branches from the same Stream the way you would from a Collection:

~~~java
Stream<String> base = names.stream();
Stream<String> a = base.filter(name -> name.startsWith("L"));
// Continuing to branch from base is not a valid reuse pattern.
~~~

The steps in a pipeline are linked together. The variable `base` does not become a shared data store for multiple independent query branches.

### Option 1: Create a New Stream From the Source

~~~java
long count = names.stream()
        .filter(name -> name.length() >= 3)
        .count();

List<String> list = names.stream()
        .filter(name -> name.length() >= 3)
        .toList();
~~~

This reads the source twice. If the source changes between the two passes or the processing is expensive, the two results or the cost may differ from what you intended.

### Option 2: Store the Computed Result

~~~java
List<String> list = names.stream()
        .filter(name -> name.length() >= 3)
        .toList();

int count = list.size();
~~~

Now the data to keep resides in `list`. When multiple uses are needed, a result Collection usually expresses the intent more clearly than trying to hold onto a consumed Stream.

### Option 3: Store a Function That Creates a New Pipeline

~~~java
Supplier<Stream<String>> selectedNames =
        () -> names.stream().filter(name -> name.length() >= 3);

long count = selectedNames.get().count();
List<String> list = selectedNames.get().toList();
~~~

Here each call to `get` creates a new Stream because the lambda body calls `names.stream()` again. That is due to how this lambda is written, not a general guarantee of every `Supplier`. The `Supplier` contract does not require always returning a new object. [Java SE 17 — Supplier](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Supplier.html).

A supplier that merely returns the same pre-created Stream still suffers from the reuse error. Keeping a "recipe" means keeping a function that actually constructs a new execution, not renaming a variable holding an old pipeline.

## 7. A Stream Is Not an Automatic Snapshot of a Collection

In this example with `ArrayList`:

~~~java
List<String> values = new ArrayList<>(List.of("A"));
Stream<String> delayed = values.stream().filter(value -> true);

values.add("B");
List<String> result = delayed.toList();
~~~

The result is `[A, B]`. Creating the Stream before adding `B` does not automatically copy the `ArrayList` backing array to preserve the `[A]` version.

Properly designed JDK sources can reflect changes made before the terminal operation begins; this is described in the non-interference section of the Stream library. Do not infer the same behavior for every custom source or for modifying a source while processing is already underway. [Java SE 17 — Non-interference](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/package-summary.html#NonInterference).

After collecting into `result`, if `C` is added to `values`, the positions of `result` remain `[A, B]`. A new Stream reading `values` again can produce `[A, B, C]`.

Distinguish three points in time:

| Point in time | Object present |
| --- | --- |
| After creating the source | Collection holding the data |
| After building the pipeline, before running terminal | Processing description tied to the source; no automatic copy of results |
| After collecting into a list | Result collection holding the elements collected in that execution |

If you need to fix the data before building a computation, choose an appropriate copy strategy. A structural copy only separates the collection's slots; mutable element objects can still be shared. If concurrent access is involved, both the timing of the copy and the consistency level of the source must be designed explicitly.

## 8. filter and map Do Not Automatically Modify the Source

Given the source:

~~~text
[Lan, An, Mai, Bo]
~~~

a pipeline that filters for long names and converts them to uppercase can return:

~~~text
[LAN, MAI]
~~~

The source does not become `[LAN, MAI]` just because `filter` and `map` were used. `filter` decides which elements proceed; `map` computes output values. They do not mean "delete source elements" or "assign new elements into the source."

Comparison:

| Requirement | How to express it |
| --- | --- |
| Produce a result containing elements matching a condition | Stream `filter` then collect the result |
| Remove non-matching elements from a modifiable Collection | A mutating operation like `removeIf` with the corresponding condition |
| Compute new values for the result | Stream `map` |
| Replace positions of a modifiable List | A mutating operation like `replaceAll`, per List's contract |

Lambdas are still Java code and can themselves produce side effects. If inside `map` you call a setter on a source object, that object can be mutated. In that case, it is the code inside the lambda making the change, not a guarantee that "Stream automatically turns the source into the output."

Do not write:

~~~java
// Illustrates an incorrect approach with an ArrayList source being traversed.
names.stream().forEach(name -> names.remove(name));
~~~

This is interference with the source during processing, even when the Stream runs sequentially. It can throw an exception or produce results that violate the contract; you must not rely on a single run not throwing an error to treat it as valid.

If you need a new list, collect the result. If you need in-place removal, use a mutating operation with an appropriate contract or an iterator following the rules of the source structure. Choosing the right model avoids mixing data storage with transformation descriptions.

## 9. Storing Results Also Requires Choosing Mutability and Copy Depth

`Stream.toList()` returns a list that does not allow modification through list-mutating operations. It does not mean a modifiable `ArrayList`. [Java SE 17 — Stream.toList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#toList()).

If you need a result that supports adding and removing:

~~~java
List<String> editable = names.stream()
        .filter(name -> name.length() >= 3)
        .collect(Collectors.toCollection(ArrayList::new));
~~~

`Collectors.toCollection` lets you specify the target structure explicitly. [Java SE 17 — Collectors.toCollection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html#toCollection(java.util.function.Supplier)).

Afterward, `editable.add("NEW")` adds only to the result, not to `names`. The result structure and the source structure are two distinct objects with separate slots.

However, if the elements are objects with mutable state:

~~~java
StringBuilder item = new StringBuilder("seed");
List<StringBuilder> source = List.of(item);
List<StringBuilder> result = source.stream().toList();

result.get(0).append("!");
~~~

`source.get(0)` also reflects `seed!`. Both places hold references to the same `StringBuilder`. A result list that forbids adding or removing elements can still contain objects with mutable state.

Therefore, "not modifying the source via ordinary filtering/mapping" does not mean "the output is a deep copy completely independent of the input." To make the data independent at the object level, you must copy the objects or construct appropriate output objects.

## 10. Streams Can Have Non-Collection Sources

Streams can also originate from arrays, value generators, numeric ranges, or I/O resources. You do not need to pre-create a new list as a source for every problem.

Example:

~~~java
List<Integer> firstFour = Stream.iterate(1, n -> n + 1)
        .limit(4)
        .toList();
~~~

The result is `[1, 2, 3, 4]`. The `iterate` source does not need to hold a list of all numbers that will be generated beforehand. The pipeline pulls only as many elements as the result request requires.

This highlights an important distinction: a Collection has a finite size in its model, whereas a Stream source can keep generating elements without a predetermined stopping point.

Simply placing `limit` somewhere does not guarantee every pipeline will terminate. An earlier filter step might never emit an element for `limit` to count. A sorting step on an infinite source also cannot finish receiving all input to determine the full order.

Therefore, when a source may be unbounded, think in terms of data flow: which step needs to wait for how much input, which step can produce output, and whether the stopping condition is actually reachable. This is a consequence of the processing model, not a question of whether a list is large or small.

## 11. Do Not Infer Performance From the Word "Stream" Alone

A filter–map–sum pipeline can fuse steps and avoid creating full intermediate lists. Still, Streams carry pipeline management overhead, function call overhead, and the specific requirements of individual operations.

`sorted` may require buffering. `distinct` may need to track values seen so far. Collecting with `toList` still has to store the resulting data. If the output has millions of elements, rewriting a loop as a Stream does not make the output data vanish from memory.

There is also no guarantee that `parallelStream` is always faster. Work-splitting overhead, data source characteristics, ordering, combining operations, and per-element work all affect the outcome. In particular, writing a lambda that mutates a shared list from multiple threads is not made safe simply by calling `parallel`.

For simple problems, a loop can be easier to read. For a clear sequence of filtering and result computation, a Stream can express intent well. Choose the style based on contract, clarity, and proper measurement when performance is a real requirement.

### Spliterator Sits at the Element-Supply Boundary

In this topic area, you can understand `Spliterator` as a mechanism for traversing a source and, when appropriate, splitting the source into parts. `Collection.stream()` uses the source's mechanism to build a sequential Stream. [Java SE 17 — Collection.stream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html#stream()).

It does not turn a Stream into an element store. The source still supplies the data; the pipeline still describes the processing steps. The fact that a source can be split does not mean every pipeline must run in parallel or that any operation can ignore ordering requirements.

`BaseStream.iterator()` and `spliterator()` are special terminal operations that hand manual traversal control back to the caller. In those cases, pulling elements continues through the returned iterator/spliterator, rather than the terminal operation processing all data before returning. This lesson uses ordinary terminal operations such as `toList`, `count`, `sum`, and `findFirst` to observe the execution model.

## 12. Consuming a Stream and Closing Resources Are Two Different Things

A terminal operation uses the pipeline to compute a result. Closing a Stream invokes close handlers and releases resources associated with the source. These two actions must not be treated as synonymous.

`BaseStream` implements `AutoCloseable`; handlers registered with `onClose` run when the Stream is closed. [Java SE 17 — BaseStream.close](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/BaseStream.html#close()).

In the demonstration, `count` finishes, yet the `onClose` handler does not run until exiting `try-with-resources`. This is a way to observe the difference without opening a real file.

Streams created from in-memory Collections typically do not hold I/O resources that need closing. For sources such as `Files.lines`, you must follow the method's resource contract:

~~~java
// Illustrated inside a method that handles IOException.
// path is a Path provided by the application.
try (Stream<String> lines = Files.lines(path)) {
    long nonBlank = lines.filter(line -> !line.isBlank()).count();
    System.out.println(nonBlank);
}
~~~

You need to import `java.nio.file.Files`, `java.util.stream.Stream`, and handle I/O exceptions appropriately. This is an illustrative snippet that depends on an input file, rather than having fixed stdout like the standalone program below.

`Files.lines` reads lines lazily and holds a reference to the open file; closing the Stream closes the file. The documentation requires using `try-with-resources` or an equivalent mechanism to close it promptly. [Java SE 17 — Files.lines](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#lines(java.nio.file.Path)).

Do not return a file-backed Stream out of an already-closed block and expect another caller to read it. If an API returns a resource-backed Stream to a caller, ownership and closing responsibility must be clearly documented.

## 13. Complete Demonstration Program

Save the following code as **CollectionAndStreamDemo.java**. The program uses Java 17–compatible APIs, requires no external libraries, and does not read or write files.

The `trace`, `checked`, and `lifecycle` lists only record markers for observing the sequential examples. The output is not a guarantee about side-effect ordering in a parallel pipeline or about lambda invocation counts under every optimization.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.function.Supplier;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class CollectionAndStreamDemo {
    private static void rejects(
            String label,
            Class<? extends RuntimeException> expected,
            Runnable action) {
        try {
            action.run();
            throw new AssertionError(label + " did not fail");
        } catch (RuntimeException ex) {
            if (!expected.isInstance(ex)) {
                throw ex;
            }
            System.out.println(label + " -> " + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        List<String> names = new ArrayList<>(List.of("Lan", "An", "Mai", "Bo"));
        List<String> trace = new ArrayList<>();

        Stream<String> plan = names.stream()
                .filter(name -> {
                    trace.add("filter:" + name);
                    return name.length() >= 3;
                })
                .map(name -> {
                    trace.add("map:" + name);
                    return name.toUpperCase(Locale.ROOT);
                });

        System.out.println("before-terminal=" + trace);
        List<String> result = plan.toList();
        System.out.println("result=" + result);
        System.out.println("after-terminal=" + trace);
        System.out.println("source=" + names);
        rejects("reuse-plan", IllegalStateException.class, () -> plan.count());

        System.out.println("fresh-count=" + names.stream().count());
        System.out.println("long-name-count="
                + names.stream().filter(name -> name.length() >= 3).count());
        System.out.println("total-length=" + names.stream().mapToInt(String::length).sum());

        Supplier<Stream<String>> longNames =
                () -> names.stream().filter(name -> name.length() >= 3);
        System.out.println("factory-count=" + longNames.get().count());
        System.out.println("factory-list=" + longNames.get().toList());

        List<String> changing = new ArrayList<>(List.of("A"));
        Stream<String> delayed = changing.stream().filter(value -> true);
        changing.add("B");
        List<String> captured = delayed.toList();
        System.out.println("before-start-change=" + captured);
        changing.add("C");
        System.out.println("materialized-result=" + captured);
        System.out.println("new-query=" + changing.stream().toList());

        List<String> checked = new ArrayList<>();
        String first = names.stream()
                .filter(name -> {
                    checked.add(name);
                    return name.startsWith("M");
                })
                .findFirst()
                .orElse("none");
        System.out.println("first-match=" + first);
        System.out.println("checked=" + checked);

        List<Integer> generated = Stream.iterate(1, n -> n + 1)
                .limit(4)
                .toList();
        System.out.println("generated=" + generated);

        rejects("result-add", UnsupportedOperationException.class, () -> result.add("NEW"));
        List<String> editable = names.stream()
                .filter(name -> name.length() >= 3)
                .collect(Collectors.toCollection(ArrayList::new));
        editable.add("NEW");
        System.out.println("editable=" + editable);
        System.out.println("source-still=" + names);

        StringBuilder item = new StringBuilder("seed");
        List<StringBuilder> objects = List.of(item);
        List<StringBuilder> objectResult = objects.stream().toList();
        objectResult.get(0).append("!");
        System.out.println("shared-object=" + objects.get(0));

        List<String> lifecycle = new ArrayList<>();
        try (Stream<String> closable = Stream.of("A")
                .onClose(() -> lifecycle.add("closed"))) {
            System.out.println("resource-count=" + closable.count());
            System.out.println("after-terminal-close=" + lifecycle);
        }
        System.out.println("after-close=" + lifecycle);
    }
}
~~~

Compile and run:

~~~shell
javac --release 17 -encoding UTF-8 CollectionAndStreamDemo.java
java CollectionAndStreamDemo
~~~

Exact stdout:

~~~text
before-terminal=[]
result=[LAN, MAI]
after-terminal=[filter:Lan, map:Lan, filter:An, filter:Mai, map:Mai, filter:Bo]
source=[Lan, An, Mai, Bo]
reuse-plan -> IllegalStateException
fresh-count=4
long-name-count=2
total-length=10
factory-count=2
factory-list=[Lan, Mai]
before-start-change=[A, B]
materialized-result=[A, B]
new-query=[A, B, C]
first-match=Mai
checked=[Lan, An, Mai]
generated=[1, 2, 3, 4]
result-add -> UnsupportedOperationException
editable=[Lan, Mai, NEW]
source-still=[Lan, An, Mai, Bo]
shared-object=seed!
resource-count=1
after-terminal-close=[]
after-close=[closed]
~~~

The code was compiled with `--release 17` and run on JDK 24.0.2. The compiler flag verifies the Java 17 language/API level; the program is not claimed to have been run on a Java 17 JVM.

Cross-check by group:

- `before-terminal` is empty, while `after-terminal` records the steps executed when retrieving the result.
- `result` holds two uppercase strings, while `source` still retains the original four names.
- `reuse-plan` detects reusing an already-consumed pipeline.
- The counting, summing, and factory lines use a fresh Stream for each pass.
- `before-start-change` sees the modification to the `ArrayList` before the terminal operation starts; `materialized-result` afterward is already its own result data.
- `first-match` and `checked` show that a sequential search does not need to check `Bo` after finding `Mai`.
- `generated` has a value-generating source without needing a Collection that already holds the numbers.
- `result-add` and `editable` distinguish mutability across output list types.
- `shared-object` illustrates that the same element object can still be referenced by both the source and the result.
- The last two lines distinguish terminal completion from closing the Stream.

## 14. Practice With Answers

### Exercise 1 — Does the Pipeline Already Hold Result Data?

After `Stream<String> s = names.stream().filter(name -> name.length() >= 3)`, can you treat `s` as a filtered list and call `get(0)`?

**Answer:** No. `s` is a Stream describing a processing pipeline; it does not have List's `get` method and has not created a result list yet. If you need stored data for indexed access, use an appropriate terminal operation such as `toList` and operate on that List.

### Exercise 2 — Counting and Collecting a List From the Same Stream

Can you call `s.count()` and then `s.toList()` on the same `s`? State two ways to fix this depending on your needs.

**Answer:** You cannot reuse a Stream after a terminal operation. You can create a new Stream from the source for each pass, or collect the list once and take the list's `size` if both results must be based on the same collected data.

### Exercise 3 — Does Filtering Remove Elements From the Source?

The source is `[Lan, An, Mai, Bo]`. A pipeline filters for names at least three characters long and converts them to uppercase, returning `[LAN, MAI]`. Does the source still contain `An` and `Bo`?

**Answer:** Yes, the source still holds all four names as long as the lambdas do not mutate the source or source objects. `filter` only selects which elements proceed in the pipeline. To remove in place, choose a mutating operation with an appropriate contract.

### Exercise 4 — Does a Stream Freeze Data at Creation Time?

You create a Stream from an `ArrayList` containing `A`, add `B` before the terminal operation, and then collect a list. Why is the example's result `[A, B]`?

**Answer:** A Stream from this source does not automatically copy the data into a snapshot when `stream` is called. Changes made before execution begins are reflected by a compliant JDK source. Do not use this to justify modifying a source while a terminal operation is running, or to infer the behavior of all custom sources.

### Exercise 5 — Why Not Put Required Work Inside peek?

A pipeline calls `peek` to log every element and ends with `count`. Can you use a correct count to prove that every log call ran?

**Answer:** No. The implementation can deduce the count without traversing stages that do not affect the result. Use an explicit action-performing mechanism, such as a loop or an appropriate terminal operation, rather than relying on a side effect that may be elided during optimization.

### Exercise 6 — Which Supplier Actually Creates a New Execution?

How does `Supplier<Stream<String>> factory = () -> names.stream()` differ from a supplier that simply returns a previously created `savedStream` variable?

**Answer:** The first lambda calls `stream` again to create a fresh execution on each `get`. The second lambda may return the same already-consumed Stream. The `Supplier` type itself does not guarantee a new object; you must look at how it produces its result.

### Exercise 7 — Does an Unmodifiable Result Make the Objects Inside Immutable?

A `List<StringBuilder>` is passed through `stream().toList()`. Can you modify the `StringBuilder` retrieved from the result? Does the source see the change?

**Answer:** The output list forbids adding, removing, or replacing positions via List mutators, but the `StringBuilder` object itself is still mutable. If the source and output share the same reference, the source sees the new state as well. Object copying or immutable types are needed if state isolation is required.

### Exercise 8 — Does Finishing a Terminal Operation Guarantee the File Is Closed?

After `Files.lines(path).count()`, can you skip closing the Stream because `count` is already a terminal operation?

**Answer:** No. Consuming a pipeline and closing resources are two separate tasks. The Stream from `Files.lines` must be closed per its contract, typically with `try-with-resources`, even after the terminal operation completes or fails.

## 15. How to Read Code That Uses Collection and Stream

First find where the data is stored and who has permission to modify it. Then read the Stream as a single execution consisting of a source, intermediate stages, and a terminal operation. Determine whether the result needs to be stored or if only an aggregate value is needed.

When you need to reuse data, keep a Collection or create a new Stream from a still-usable source. When you need to reuse a processing recipe, keep a function that constructs a new pipeline. When a source holds resources, identify closing responsibility; when mutable objects are involved, distinguish a structural copy from a state copy.

The core model of this lesson is: **Collection represents a group of data; Stream represents a single computation pass over a source; the terminal operation produces the result the application needs.** Understanding these three roles helps you avoid treating a Stream as a temporary list, avoid re-running a consumed pipeline, and choose the right place to store results.
