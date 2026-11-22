# A Stream Pipeline Can Only Be Consumed Once in Java

## 1. Core Rule of the Stream Model

A `java.util.stream.Stream<T>` object represents **a sequence of data-processing operations** (*pipeline*), not a collection that can be traversed repeatedly at will. According to the Stream API contract, each stream should only be operated upon through its pipeline **once**; the same stream must not be reused to perform multiple traversals or create independent processing branches.

A typical pipeline consists of:

```text
Source (List, array, file, ...)
       |
       v
stream() -> filter(...) -> map(...) -> terminal operation
                         (count / toList / collect / forEach / ...)
```

- **Data source** can be a collection, array, generator, or I/O resource.
- **Intermediate operations** such as `filter`, `map`, `sorted` typically create a new pipeline to describe the processing; they are usually **lazy** (not yet starting data traversal).
- **Terminal operations** such as `count`, `toList`, `collect`, `findFirst`, `anyMatch`, `forEach`, `reduce`, `sum` initiate the processing according to the semantics of that terminal operation. The pipeline is considered **consumed** after the terminal operation is executed.
- To perform a second processing step on the same data, **create a new stream from the source**, or store results that need to be used multiple times in an appropriate collection.

Correct example:

```java
List<Integer> numbers = List.of(1, 2, 3, 4);
long count = numbers.stream().filter(n -> n % 2 == 0).count();
int sum = numbers.stream().mapToInt(Integer::intValue).sum();
```

These are illustrative statements placed in a method with `import java.util.List;`. The two calls to `numbers.stream()` create **two separate stream objects**. You are not re-traversing the same `Stream` object. The `List` can still be accessed and used to create new streams because it is the source, not consumed like the pipeline.

## 2. What Happens When Calling a Terminal Operation a Second Time?

Consider the illustrative example:

```text
Stream<String> names = Stream.of("An", "Binh", "Chi");
long count = names.count(); // 1st terminal operation
long again = names.count(); // Wrong: attempting to consume the same Stream a 2nd time
```

This is a **counter-example that intentionally violates the Stream contract**, not to be used as a valid program pattern regarding behavior. On many Java implementations, the second use throws an `IllegalStateException` with a message like `stream has already been operated upon or closed`.

**Distinguishing the API contract from error symptoms:** Java documentation states that an implementation *may* throw `IllegalStateException` if it detects that a stream is being reused. Because some methods return the stream object itself, not every improper reuse is guaranteed to be detected with an exception in every implementation. Therefore, **do not write programs relying on reuse always throwing a specific error**. Reuse is wrong according to the contract even if an operation happens not to report an error.

The rule remains the same whether the terminal operation returns a single value (`count`, `findFirst`, `anyMatch`) or a collection (`toList`), and it also does not change when a terminal operation terminates early.

## 3. Intermediate Operations Do Not Mean the Source Stream Can Be Reused Arbitrarily

An intermediate operation like `filter` can append a new stage to the pipeline, but this **does not allow branching the pipeline** from the same source stream:

```text
Stream<Integer> source = Stream.of(1, 2, 3);
Stream<Integer> even = source.filter(x -> x % 2 == 0);
Stream<Integer> doubled = source.map(x -> x * 2); // Wrong: reusing source
```

This is an **invalid organization according to the Stream contract**: after chaining `filter`, the `source` object has already participated in that pipeline. Do not use it as an independent source for another branch. Some implementations throw `IllegalStateException` immediately on the second `source.map(...)` call.

Fix this by keeping the **data source** instead of sharing the same **Stream object**:

```java
List<Integer> numbers = List.of(1, 2, 3);
List<Integer> even = numbers.stream()
        .filter(x -> x % 2 == 0)
        .toList();
List<Integer> doubled = numbers.stream()
        .map(x -> x * 2)
        .toList();
```

Inside a method body with `List` imported, the results are `even = [2]` and `doubled = [2, 4, 6]`. Two independent pipelines read the shared data in `numbers`, without sharing the lifecycle of the same Stream object.

**Note:** `map` and `filter` are not terminal operations and usually do not evaluate elements at the time they are called; however, *linking a stage* can make the upstream stream no longer a suitable object for calling another branch. "Lazy" does not mean "can be arbitrarily reused".

## 4. Complete Java 17 Program: Six Key Scenarios

Save the entire code below into `StreamOneShotDemo.java`:

```java
import java.util.List;
import java.util.function.Supplier;
import java.util.stream.Stream;

public class StreamOneShotDemo {
    public static void main(String[] args) {
        Stream<String> words = Stream.of("java", "go", "kotlin")
                .map(String::toUpperCase);
        System.out.println("firstCount=" + words.count());
        try {
            words.findFirst();
        } catch (IllegalStateException ex) {
            System.out.println("reuse=" + ex.getClass().getSimpleName());
        }

        List<Integer> data = List.of(1, 2, 3, 4);
        System.out.println("evens=" +
                data.stream().filter(n -> n % 2 == 0).toList());
        System.out.println("sum=" +
                data.stream().mapToInt(Integer::intValue).sum());

        Supplier<Stream<String>> fresh = () ->
                Stream.of("java", "go", "kotlin")
                        .filter(s -> s.length() > 2);
        System.out.println("freshCount=" + fresh.get().count());
        System.out.println("freshList=" +
                fresh.get().map(String::toUpperCase).toList());

        Stream<Integer> root = Stream.of(1, 2, 3);
        Stream<Integer> branch = root.filter(n -> n > 1);
        try {
            root.map(n -> n * 2).count();
        } catch (IllegalStateException ex) {
            System.out.println("branch=" + ex.getClass().getSimpleName());
        }
        System.out.println("branchResult=" + branch.toList());

        Stream<Integer> iteratorStream = Stream.of(7, 8);
        var iterator = iteratorStream.iterator();
        System.out.println("iteratorFirst=" + iterator.next());
        try {
            iteratorStream.count();
        } catch (IllegalStateException ex) {
            System.out.println("iteratorReuse=" + ex.getClass().getSimpleName());
        }

        Stream<Integer> closed = Stream.of(4, 5)
                .onClose(() -> System.out.println("closeHandler=ran"));
        closed.close();
        try {
            closed.count();
        } catch (IllegalStateException ex) {
            System.out.println("closedReuse=" + ex.getClass().getSimpleName());
        }
    }
}
```

Compile and run with Java 17 or later:

```bash
javac --release 17 -encoding UTF-8 StreamOneShotDemo.java
java StreamOneShotDemo
```

Verified output with Java 17:

```text
firstCount=3
reuse=IllegalStateException
evens=[2, 4]
sum=10
freshCount=2
freshList=[JAVA, KOTLIN]
branch=IllegalStateException
branchResult=[2, 3]
iteratorFirst=7
iteratorReuse=IllegalStateException
closeHandler=ran
closedReuse=IllegalStateException
```

Reading each scenario:

1. **First terminal operation:** `words.count()` yields `3` and consumes the `words` pipeline. The subsequent `words.findFirst()` call is caught in `catch`; the Java 17 implementation of the test detects reuse and throws `IllegalStateException`.
2. **Creating new streams from a List:** the two `data.stream()` expressions are two new pipelines; `toList()` yields `[2, 4]`, while `mapToInt(...).sum()` yields `10`.
3. **Factory using Supplier:** each `fresh.get()` creates a separate stream from `Stream.of(...)`; therefore one call can do `count()`, and the next can do `map(...).toList()`.
4. **Branching:** `root.filter(...)` creates `branch`. Attempting to reuse `root.map(...)` is rejected; the original `branch` can still be used once for `toList()`. Do not rely on the old branch still being runnable after an improper use in every implementation; avoid that branching code pattern.
5. **Getting an Iterator:** `iteratorStream.iterator()` is a terminal operation (even though `iterator.next()` has only been called once), so `iteratorStream.count()` cannot be used afterward.
6. **Closing a stream:** `closed.close()` executes the close handler registered with `onClose`. A closed stream must not be used further; Java 17 throws `IllegalStateException` when the program tries `count()`.

The exceptions in this program are **intentionally caught to demonstrate errors**, not to imply that you should intentionally reuse streams in real applications.

## 5. Distinguishing Between the Data Source and the Stream Object

| Object / operation | Can it be repeated? | Notes |
| --- | --- | --- |
| An available `List<T>` | Can be read or create many new streams | Data belongs to the List; each new stream has its own lifecycle |
| `List.of(...).stream()` called again | Yes | Each call returns a new stream |
| `Stream.of(...)` called again | Yes | Each call creates a new stream from the arguments |
| Variable `Stream<T> stream` after `count()` | **No** | Pipeline has been consumed |
| Same `Stream<T>` after `findFirst()` | **No** | Even though `findFirst` may read only one element |
| Same `Stream<T>` after `anyMatch()` | **No** | Short-circuiting does not allow reuse |
| Same `Stream<T>` after `iterator()` | **No** | `iterator()` is a terminal operation |
| `List<T> result = stream.toList()` | The resulting **List** can be read again | Cannot call `stream.toList()` again on the same stream |
| `Stream<T>` after `close()` | **No** | Stream is closed |
| `Supplier<Stream<T>>` creating a new stream each time | The factory can be called multiple times | True if the supplier actually builds a new stream and the source is still available |

A stream **is not like a resettable Iterator** nor is it like a `Collection`. A `Collection` can provide a new iterator/stream on every call; a `Stream` object represents only a single processing pipeline.

Even when calling `stream.toList()` and storing the result, you may only reuse the **resulting list** — you cannot re-run the old pipeline. `Stream.toList()` has been available since Java 16 and returns an **unmodifiable** list; if you want a mutable list, you can create `new ArrayList<>(stream.toList())` while the stream is still unconsumed.

## 6. Approach 1: Create a New Stream Directly Each Time

For Collection sources, it is usually unnecessary to store the stream in a variable:

```java
List<String> items = List.of("java", "go", "kotlin");

long longWords = items.stream()
        .filter(s -> s.length() > 2)
        .count();

List<String> upper = items.stream()
        .map(String::toUpperCase)
        .toList();
```

Place the above statements in a method with `import java.util.List;`. `longWords = 2`, and `upper = [JAVA, GO, KOTLIN]`. The `items.stream()` expression appears **twice**, so each terminal operation has its own pipeline.

When the input can change during processing, consider the consistency of the source: creating a new stream does not automatically take a snapshot of the data at an earlier point in time, nor does it guarantee safety when the collection is concurrently modified. If multiple processing passes over fixed data are needed, you can create an appropriate immutable snapshot before use.

## 7. Approach 2: Use Supplier<Stream<T>> to Provide a New Stream

When you want to pass "how to create a pipeline" to multiple places, instead of passing a pre-created stream object, you can pass a **factory**:

```java
Supplier<Stream<String>> factory = () ->
        Stream.of("java", "go", "kotlin")
                .filter(s -> s.length() > 2);

long count = factory.get().count();
List<String> upper = factory.get()
        .map(String::toUpperCase)
        .toList();
```

These are illustrative statements in a method with `java.util.function.Supplier`, `java.util.stream.Stream`, and `java.util.List` imported. The respective outputs are `count = 2` and `upper = [JAVA, KOTLIN]`.

The **wrong** way is a factory that just returns the same previously stored stream:

```text
Stream<String> original = Stream.of("A", "B");
Supplier<Stream<String>> broken = () -> original;
broken.get().count();
broken.get().count(); // Wrong: two get calls return the same Stream object
```

The snippet above is an **intentionally wrong counter-example regarding reuse**, even though it compiles. The second `get()` does not create a new stream. The `Supplier` type carries no magic for "refreshing"; what matters is that **the stream-creation expression must be re-executed**.

For file sources or database queries, a supplier that wants to create a new stream must **open a new resource/query appropriately**, as it cannot re-read an already consumed cursor/reader. At the same time, it must be clearly defined who is responsible for closing the created resource.

## 8. Approach 3: Materialize Results When Multiple Uses Are Needed

If the processing part is expensive and the result needs to be read repeatedly, you can **consume the stream once and store the result**:

```java
List<String> normalized = Stream.of("  Java ", " Kotlin  ")
        .map(String::strip)
        .toList();

long count = normalized.size();
String first = normalized.get(0);
long startsWithJ = normalized.stream()
        .filter(s -> s.startsWith("J"))
        .count();
```

The illustrative statements require importing `List` and `Stream`. `normalized` is the list `[Java, Kotlin]`, `count = 2`, `first = "Java"`, `startsWithJ = 1`.

This **is not re-running the old stream**: the source stream is consumed when `toList()` is called. Afterward, you operate on the saved list or create a **new stream from the list**.

There is a trade-off: `toList()` stores the entire result in memory. If the source is very large or infinite, materializing everything can consume too much memory, run forever, or be unsuitable. In that case, design a single-pass traversal, compute multiple statistics in one terminal operation, or use a re-openable source.

## 9. Short-Circuiting Still Consumes the Stream

Some terminal operations can terminate before traversing the entire source: `findFirst()`, `findAny()`, `anyMatch()`, `allMatch()`, `noneMatch()`. For example:

```java
Stream<Integer> numbers = Stream.of(2, 4, 6, 9);
boolean found = numbers.anyMatch(x -> x % 2 != 0);
```

The statements above belong to a method body with `Stream` imported. `found` is `true` because of the odd element `9`. However, **even if a terminal operation only traverses part of the source in other scenarios, that stream has still been consumed**.

Whether a terminal operation traverses **all** elements depends on the semantics of the operation, the characteristics of the source, and optimizations. For example, `count()` may leverage a known source size without running every stage as a programmer might expect; do not use `peek` or side effects in `map` to count how many times a function has run.

**Single consumption** does not mean **every element is evaluated exactly once** in all situations. What is constrained is the **pipeline lifecycle**, not a guarantee on the number of side effects.

## 10. iterator() and spliterator() Are Also Terminal Operations

A common misconception: "If I just got the iterator and haven't read all elements yet, the stream can surely still be traversed with `count()`". Wrong. `BaseStream.iterator()` and `BaseStream.spliterator()` are documented as **terminal operations**.

Example from the program in section 4:

```java
Stream<Integer> stream = Stream.of(7, 8);
var iterator = stream.iterator();
System.out.println(iterator.next()); // 7
```

After `iterator()`, the stream cannot be reused for another terminal operation, even though `iterator` has only read element `7`. If you want to traverse via an iterator, continue using **that iterator** according to its rules, rather than going back to calling a terminal method on the `Stream` object.

This also applies to `spliterator()`. Do not confuse a terminal operation that returns a **traversal-supporting structure** with an intermediate operation onto which another branch can be chained.

## 11. Closing a Stream Is Different from Consuming a Stream

There are two concepts to keep separate:

1. **Consuming** a stream via a terminal operation: the stream must not be reused, but it does not mean Java has called `close()` on all resources.
2. **Closing** a stream with `close()`: ends the usability of the stream and triggers close handlers registered via `onClose()`.

For many streams created from a `List` or array, there is usually no operating system resource to close. But `Files.lines(path)` creates a stream backed by a file resource; it needs to be **closed** after use. Terminal operations like `count()` or `toList()` **do not automatically guarantee closing the file stream**.

In section 4, the `closed` stream has an `onClose` handler. `closed.close()` runs the handler, and trying to use `closed.count()` afterward is rejected by Java 17. `close()` does not mean "reset and traverse from the beginning".

For streams sourced from files, sockets, or resources that need to be released, use **try-with-resources**; this is a resource management concern alongside the single-use rule.

## 12. Complete File Example: Re-reading by Opening a New Stream

The following program creates a temporary file itself, opens and closes two different streams, and then deletes the temporary file. Save it to `StreamFreshFileDemo.java`:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public class StreamFreshFileDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("stream-one-shot-", ".txt");
        try {
            Files.writeString(file, "alpha\nbeta\n");
            try (Stream<String> lines = Files.lines(file)) {
                System.out.println("lineCount=" + lines.count());
            }
            try (Stream<String> lines = Files.lines(file)) {
                System.out.println("upper=" +
                        lines.map(String::toUpperCase).toList());
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Compile and run:

```bash
javac --release 17 -encoding UTF-8 StreamFreshFileDemo.java
java StreamFreshFileDemo
```

Output:

```text
lineCount=2
upper=[ALPHA, BETA]
```

Explanation:

- `Files.writeString(...)` creates two lines `alpha` and `beta`; the `main` method declares `throws IOException` to handle checked exceptions at the level of an illustrative program.
- The first time, `Files.lines(file)` opens a stream with an I/O resource; `count()` consumes that stream. At the end of the `try` block, the stream is closed.
- The second time, `Files.lines(file)` is called **another time**, creating a new stream to do `map(String::toUpperCase).toList()` and yielding `[ALPHA, BETA]`. The first stream is not reused at all.
- `finally` deletes the temporary file created by the program. This is a self-contained example that needs no pre-existing data and requires no external libraries.

Keep in mind when applying this to mutable data: opening the file a second time may read new content if the file has been modified. The one-shot rule does not guarantee immutability of the source across multiple calls.

## 13. Application Consequences: How to Design APIs?

A method accepting `Stream<T>` should be understood as **taking ownership of using a pipeline once**. For example:

```java
static long countWords(Stream<String> words) {
    return words.filter(s -> !s.isBlank()).count();
}
```

This is an illustrative method placed in a class with `Stream` imported. A caller should not pass the same `Stream<String>` object into `countWords` multiple times. For frequently reused APIs, you can:

- Accept `Collection<T>` or `List<T>` and call `.stream()` for each computation yourself, if the data model allows.
- Accept `Supplier<Stream<T>>` (factory) if you want each processing pass to have a new pipeline, and document resource allocation/closing.
- Accept `Stream<T>` when the API is explicitly designed to **consume data once**. You should document the contract clearly so callers do not expect reuse.
- Compute multiple results in **a single terminal operation** if the source cannot be recreated or the result is very large; for example, use an appropriate collector or a single loop depending on the requirement.

You should not store a stream as a long-lived field for multiple public methods to share. Storing a stream in a local variable to build a pipeline and consume it once is normal; sharing the same stream across different places easily causes lifecycle bugs.

**Parallel streams are still one-shot:** `parallel()` does not turn a stream into a reusable source, nor does it create an independent copy to run multiple terminal operations. A pipeline executed in parallel is still consumed only once.

## 14. Common Mistakes and Fixes

| Mistake / misconception | Why it is wrong | How to fix |
| --- | --- | --- |
| Calling `stream.count()` then `stream.toList()` | Two terminal operations on one stream | Create two new streams from the source, or get the list first and compute size |
| `Stream<T> a = source.stream();` used in two different methods | `a` has a single-use lifecycle | Pass a collection or factory so the methods create streams themselves |
| `source.filter(...)` then `source.map(...)` as two branches | Branching from the same stream object | Call `collection.stream()` for each branch |
| Reusing after `findFirst()` because it didn't traverse everything | Short-circuiting terminal operations still consume the stream | Create a new stream |
| Calling `count()` after `iterator()` | `iterator()` is a terminal operation | Traverse using the obtained iterator or create a new stream |
| Thinking `Stream` is a `List` or `Iterable` | Stream describes a pipeline, not a re-traversable collection | Keep the source or materialize the result |
| Using `Supplier<Stream>` but returning an old stream | `get()` does not refresh if the closure holds an old stream | Each `get()` must construct a new stream |
| Calling `close()` and wanting to run the pipeline again | `close` ends the stream lifecycle | Open a new source, do not reset |
| Thinking `toList()` automatically closes `Files.lines` | Consuming is different from releasing resources | Use try-with-resources |
| Assuming improper reuse always throws `IllegalStateException` | The API only allows detecting reuse when possible | Do not write code relying on contract-violating behavior |
| Using `peek` to ensure every element is processed | Terminal ops may short-circuit or optimize | Do not rely on side effects in a pipeline for mandatory work |
| Sharing a stream across independent threads | Stream is not designed as a multi-use source | Create separate pipelines; synchronize source/resources by design |

## 15. Self-Practice (With Answers)

**Exercise 1.** Which part violates the contract?

```text
Stream<Integer> s = Stream.of(1, 2, 3);
System.out.println(s.count());
System.out.println(s.findFirst());
```

Answer: the second call `s.findFirst()` violates it; `s.count()` has already consumed the stream. Some implementations throw `IllegalStateException`.

**Exercise 2.** Rewrite the snippet above to print `3` then `Optional[1]` without reusing the stream.

```java
List<Integer> data = List.of(1, 2, 3);
System.out.println(data.stream().count());
System.out.println(data.stream().findFirst());
```

These are statements inside a method with `List` imported; each `data.stream()` call creates a new pipeline.

**Exercise 3.** Why does `Supplier<Stream<Integer>> supplier = () -> existingStream;` not guarantee multiple uses?

Answer: the supplier only returns **the same object** `existingStream`. If the first use has consumed it, the next use is still the same consumed stream. Write `() -> values.stream()` when `values` is an available collection.

**Exercise 4.** `stream.findFirst()` reads one element. Can the stream be reused to `count()` the remaining elements?

Answer: **No**. `findFirst()` is a terminal operation; to count the remaining data you need to design a different traversal approach, not rely on reusing a consumed Stream.

**Exercise 5.** After `List<String> result = source.stream().map(...).toList();`, can `result` be traversed twice?

Answer: **Yes**. `result` is a List, not the old stream. If you need to traverse via a stream, each call to `result.stream()` creates a new pipeline.

**Exercise 6.** `Files.lines(path).count()` has returned a result. Does the stream still need to be closed?

Answer: **Yes**, because this stream uses an I/O resource. Place `Files.lines(path)` in a try-with-resources block so `close()` is called when leaving the block. A terminal operation does not replace closing.

**Exercise 7.** After calling `Stream<Integer> s = Stream.of(1,2,3); s.filter(...)`, can you call `s.map(...)` to create a second branch?

Answer: **No** according to the stream contract, even though the `filter` operation is lazy and there is no terminal operation yet. To have two branches, use two new streams from the same collection or factory.

## 16. Key Takeaways

- **Each Stream object is used for only a single processing pipeline.** After a terminal operation or `close()`, it must not be reused.
- **Intermediate operations may be lazy** but do not allow branching from the same upstream object.
- **Short-circuiting operations are still terminal operations** and still consume the stream; `iterator()`/`spliterator()` are also terminal.
- **Create a new stream** from `List`, `Stream.of`, a `Supplier<Stream<T>>` that genuinely creates a new one, or reopen the source when another processing pass is needed.
- **Consumption ≠ closing resources**: I/O streams need to be closed properly, usually with try-with-resources.
- Improper reuse **may** throw `IllegalStateException`, but the API does not guarantee detecting all reuse cases. The right approach is not to reuse.
- Results materialized into a `List` can be accessed multiple times, but that does not turn the original Stream pipeline into a reusable one.

Official reference documentation: [Java SE 17 Stream API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html), [BaseStream API — close, iterator, spliterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/BaseStream.html), [Files.lines](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#lines(java.nio.file.Path)).