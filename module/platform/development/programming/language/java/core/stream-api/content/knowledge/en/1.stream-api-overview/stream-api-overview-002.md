# Distinguishing Stream, Collection, Iterator, and I/O Streams

> **Chapter:** Stream API Overview  
> **Scope:** Java Stream API (`java.util.stream`), data structures in `java.util`, and input/output streams in `java.io`, `java.nio.file`.

## Learning Objectives

After this lesson, you will be able to:

1. Explain why **a Collection stores data**, **an Iterator traverses data**, and **a Stream describes processing operations over a data source**.
2. Distinguish `java.util.stream.Stream<T>` from `InputStream`, `OutputStream`, `Reader`, and `Writer`, even though they all share the word *stream*.
3. Identify a Stream pipeline consisting of **source → intermediate operations → terminal operation**, which can be evaluated lazily and consumed only once.
4. Choose the right tool for accessing elements, transforming, aggregating, reading files, and managing resources.
5. Avoid common misconceptions about memory, ordering, source mutation, and parallel processing.

## 1. Four concepts answering four different questions

Suppose an application has a list of orders. You need to keep the orders for later access, manually iterate through each order, filter valid orders to compute a total, or read order data from a file. These four needs are related, yet they are **not the same concept**.

| Concept | Core question | Java examples | Role |
|---|---|---|---|
| **Collection** | *Where is the data kept, and how is it organized?* | `List`, `Set`, `Queue` | Holds and manages elements; can be accessed/traversed multiple times. |
| **Iterator** | *How do we fetch the next element one by one?* | `Iterator<E>` | A traversal cursor, allowing the program to manually control the progress of fetching elements. |
| **Stream API** | *What processing operations should be applied to the data?* | `Stream<T>`, `IntStream` | Builds declarative pipelines such as `filter`, `map`, `reduce`, `collect`; consumed once. |
| **I/O Stream** | *How do bytes or characters enter or leave the program?* | `InputStream`, `OutputStream`, `Reader`, `Writer` | Reads/writes data from files, networks, memory, or devices; typically requires closing resources. |

Conceptual diagram:

~~~text
List / Set / data generator source
        │
        ├── iterator() ──> Iterator ──> hasNext(), next() ──> manual loop control
        │
        └── stream()   ──> Stream ──> filter() ──> map() ──> terminal operation
                                                      │
                                              result / side effect
                                                      │
                                           List, number, Optional, ...
                                           (depends on terminal operation)

File / network ──> InputStream or Reader ──> read bytes / characters
                      │
                      └── can be adapted as a source for Stream<T>
                          (e.g., Files.lines(...) -> Stream<String>)
~~~

**Key takeaway:** `Stream<T>` is not a type of `Collection<T>`, and `InputStream` is not a form of `Stream<T>`. They can be combined, but they have different APIs, contracts, and purposes.

## 2. Collection: owns the storage structure, does not describe a pipeline

`Collection<E>` is the root interface of many element containers in `java.util`: `List` preserves positions, `Set` eliminates duplicate elements according to equality rules, and `Queue` supports queue-style processing. Depending on the implementation, a collection may be mutable or unmodifiable.

~~~java
import java.util.ArrayList;
import java.util.List;

List<String> names = new ArrayList<>(List.of("An", "Bình", "Chi"));

System.out.println(names.size()); // 3
System.out.println(names.get(0)); // An: get(index) is a List method
names.add("Dũng");                 // Modifies the stored data

for (String name : names) {
    System.out.println(name);
}
~~~

Here, `names` still exists after the loop and can be traversed again. `ArrayList` holds references to elements in a mutable structure. Not every collection supports `get(index)`: this is specific to `List`. Nor does every collection allow `add` or `remove`: for instance, `List.of(...)` creates a structurally unmodifiable list.

Calling `names.stream()` **does not convert** `names` into a Stream object and **does not remove** the source data. That call creates a Stream to build processing operations that draw data from the collection.

~~~java
import java.util.List;

List<Integer> numbers = List.of(2, 3, 4, 5, 6);

List<Integer> squaredEvens = numbers.stream()
        .filter(n -> n % 2 == 0)
        .map(n -> n * n)
        .toList();

System.out.println(squaredEvens); // [4, 16, 36]
System.out.println(numbers);       // [2, 3, 4, 5, 6]
~~~

`numbers` is where the original data resides. `numbers.stream()` creates the pipeline, while `toList()` creates **a materialized result** (realized as a list) after the pipeline runs. Since Java 16, `Stream.toList()` returns a structurally unmodifiable list; do not call `add` on that result. If you need a mutable list, you can use `collect(Collectors.toCollection(ArrayList::new))`.

A Collection can be read again by creating a **new** Iterator or Stream. Once a Stream itself is consumed, it cannot be "rewound" simply by calling a terminal operation again.

## 3. Iterator: external iteration

`Iterator<E>` is an interface with two primary operations:

- `hasNext()`: are there more elements available to retrieve?
- `next()`: retrieves the next element and advances the traversal cursor.

Some iterators also support `remove()` to delete **the last element returned** from the underlying collection in accordance with the iterator contract; this capability is optional.

~~~java
import java.util.Iterator;
import java.util.List;

List<Integer> values = List.of(3, 8, 5, 12);
Iterator<Integer> it = values.iterator();

while (it.hasNext()) {
    int value = it.next();

    if (value > 10) {
        System.out.println("Found value greater than 10: " + value);
        break; // The author decides when to stop
    }
}
~~~

With an Iterator, the loop directly controls when to ask for the next element, when to stop, and when to skip or process. The `for (T value : iterable)` loop is concise syntax for Iterator-based traversal over an `Iterable` object (arrays are handled by a separate mechanism).

If the goal is to remove elements while traversing a **mutable collection**, using `Iterator.remove()` is usually more appropriate than calling `collection.remove(...)` directly inside the loop:

~~~java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;

List<Integer> numbers = new ArrayList<>(List.of(1, 2, 3, 4));
Iterator<Integer> it = numbers.iterator();

while (it.hasNext()) {
    if (it.next() % 2 == 0) {
        it.remove(); // ArrayList iterator supports remove
    }
}
System.out.println(numbers); // [1, 3]
~~~

Not every Iterator supports `remove()`. If unsupported, this method may throw `UnsupportedOperationException`. Structurally modifying a collection externally during traversal can cause undefined behavior under the iterator contract, commonly throwing `ConcurrentModificationException` in *fail-fast* iterators; this exception should not be treated as a concurrency safety guarantee.

### How Iterator differs from Stream in control

With an Iterator, your code calls `next()` to **pull** each element. With a Stream, your code declares *what to do* using operations, and the library coordinates traversal when the terminal operation is triggered (*internal iteration*). This allows Stream to apply optimizations, short-circuiting, and work splitting where appropriate.

`Spliterator` is also a source-traversal mechanism, capable of describing data characteristics and splitting traversal ranges to support parallel processing. It is an important foundation of Stream, but it is not synonymous with Stream and is not the default choice for simple manual traversal.

## 4. Stream API: declarative processing pipeline

A Stream pipeline has three parts:

1. **Source**: collection, array, file, generator function, etc.
2. **Intermediate operations**: `filter`, `map`, `distinct`, `sorted`, `limit`, etc. They usually return a new Stream and are **lazy**.
3. **Terminal operation**: `count`, `forEach`, `findFirst`, `reduce`, `collect`, `toList`, etc. Triggers consumption of the pipeline and produces a result or side effect.

~~~java
import java.util.List;

List<String> names = List.of("An", "Bình", "Bảo", "Chi");

List<String> result = names.stream()          // Source
        .filter(name -> name.startsWith("B")) // Intermediate: filter
        .map(String::toUpperCase)             // Intermediate: transform
        .toList();                            // Terminal: collect into List

System.out.println(result); // [BÌNH, BẢO]
~~~

No temporary list is **required** to be created between `filter` and `map`. A Stream describes the processing chain, and the library routes data through the steps. However, stateful operations like `sorted` or `distinct` sometimes need to store information/buffers; **lazy does not always mean O(1) memory**.

### 4.1. Lazy: defining a pipeline does not mean running it

~~~java
import java.util.List;
import java.util.Optional;
import java.util.stream.Stream;

List<String> names = List.of("An", "Bình", "Bảo", "Chi");

Stream<String> filtered = names.stream().filter(name -> {
    System.out.println("Checking: " + name);
    return name.startsWith("B");
});

System.out.println("Pipeline declared");
Optional<String> first = filtered.findFirst();
System.out.println(first.orElse("None"));
~~~

With this ordered `List` source and sequential pipeline, the observed output is:

~~~text
Pipeline declared
Checking: An
Checking: Bình
Bình
~~~

`filter` does not execute when first declared. `findFirst()` starts traversal and can **short-circuit** after the first matching element. Therefore, "having `filter` always scans the entire source" is false. With parallel streams, execution timing and the number of processed elements may differ; avoid relying on side effects like `println` inside intermediate operations.

### 4.2. A Stream is consumed only once

~~~java
import java.util.List;
import java.util.stream.Stream;

Stream<Integer> stream = List.of(1, 2, 3).stream();

long count = stream.count();         // Single consumption
System.out.println(count);          // 3

// stream.forEach(System.out::println);
// Invalid: Stream has already been consumed; typically causes IllegalStateException.
~~~

If you need two independent processing operations, create two Streams from a re-traversable source:

~~~java
List<Integer> source = List.of(1, 2, 3);

long count = source.stream().count();
int sum = source.stream().mapToInt(Integer::intValue).sum();
~~~

Recreating a Stream from a source **does not guarantee** the source is always reusable: a network connection, a closed file, or a single-read generator source may not support it. `Stream` does not automatically keep a copy of the input data.

### 4.3. Stream does not necessarily mutate the original collection

Operations like `filter` and `map` produce processed results; they do not delete or replace elements in `source`. If elements are mutable objects, code in `map` or `forEach` **can still** mutate those objects' state, but that is an application-level side effect and often makes code harder to reason about.

Do not directly modify the source while a Stream is traversing it, unless the source and traversal mechanism explicitly support it. Stream's *non-interference* rule requires processing functions not to interfere with a data source that does not support concurrent modification. In parallel pipelines, stateful functions or functions dependent on execution order are even more likely to yield unexpected results.

### 4.4. Different result types

Not every pipeline returns a Collection:

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

List<String> names = List.of("An", "Ánh", "Bình", "Bảo", "Chi");

long total = names.stream().count(); // long

boolean hasNameB = names.stream()
        .anyMatch(name -> name.startsWith("B")); // boolean

Map<Character, List<String>> byInitial = names.stream()
        .collect(Collectors.groupingBy(name -> name.charAt(0)));
        // Map<Character, List<String>>, a grouped result
~~~

In the example above, `'A'` and `'Á'` are two different characters, so groups are partitioned by the **exact first character** rather than automatically normalizing Vietnamese diacritics. Other advanced topics in this module include `reduce`, custom collectors, `Spliterator`, parallel processing, and Stream Gatherers; all of them rely on distinguishing the **data source** from the **processing pipeline**.

## 5. I/O streams: transferring bytes and characters

The word *stream* in **Stream API** and in **I/O stream** denotes different concepts:

- `java.io.InputStream`: reads **bytes** from a source.
- `java.io.OutputStream`: writes **bytes** to a destination.
- `java.io.Reader`: reads **characters**, involving byte decoding according to a charset when using the corresponding reader type.
- `java.io.Writer`: writes **characters**, which can be encoded into bytes using a charset.

I/O streams handle data transport and resource management. They do not directly provide the `filter()` / `map()` / `collect()` pipeline of `java.util.stream.Stream<T>`.

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;

Path path = Path.of("data.bin");

try (InputStream in = Files.newInputStream(path)) {
    int first = in.read(); // 0..255 or -1 if end of data
    System.out.println(first);
} catch (IOException e) {
    System.err.println("Could not read file: " + e.getMessage());
}
~~~

`read()` here fetches **one byte** (as an `int`), not an element `T` in a pipeline. The `try-with-resources` statement ensures `in.close()` is called when exiting the block, even if an exception occurs.

### 5.1. Reading text via Reader

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path path = Path.of("notes.txt");

try (BufferedReader reader =
             Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        System.out.println(line); // Manually control the read loop
    }
} catch (IOException e) {
    System.err.println("Could not read file: " + e.getMessage());
}
~~~

This snippet uses a loop to read characters line by line. It is suitable when fine-grained read/write control is needed, when handling protocols, or when each read step depends on I/O state.

### 5.2. Intersection: I/O can supply a source for the Stream API

`Files.lines(path, charset)` returns a **`Stream<String>`**. The source of this Stream is a file, so it both uses the Stream API pipeline and owns a resource that must be closed.

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

Path path = Path.of("orders.txt");

try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
    List<String> firstTen = lines
            .map(String::trim)
            .filter(line -> !line.isEmpty())
            .limit(10)
            .toList();

    firstTen.forEach(System.out::println);
} catch (IOException | UncheckedIOException e) {
    System.err.println("Error reading file: " + e.getMessage());
}
~~~

Here:

1. **`Files.lines(...)`** creates a Stream that reads lines from the file on demand, without requiring the entire file to be loaded into a list upon opening.
2. **`map`**, **`filter`**, and **`limit`** form the text-processing pipeline.
3. **`toList`** triggers the pipeline and collects the results into memory; because of `limit(10)`, the result contains at most 10 non-empty lines.
4. **`try-with-resources`** closes the Stream; for a Stream created by `Files.lines`, closing also releases the associated file resource.
5. Errors when opening the file may be `IOException`; read errors occurring during Stream consumption may be wrapped in `UncheckedIOException`.

**Important note:** Closing a `Stream` obtained from `BufferedReader.lines()` **does not guarantee** closing the `BufferedReader`. When calling `reader.lines()`, manage the lifecycle of `reader` itself with `try-with-resources`, or use `Files.lines(...)` as shown above.

### 5.3. Ordinary Streams do not need closing; I/O-backed Streams do

`Stream` extends `AutoCloseable` and supports `close()`, but most Streams from `List.stream()`, `Arrays.stream()`, or `Stream.of(...)` hold no external resources that need releasing. Conversely, Streams created by `Files.lines` or `Files.walk` can hold system resources and **must be closed** properly. Do not equate "Stream API is a stateless data flow" with "no Stream ever needs to be closed".

## 6. Putting all four approaches side by side on the same problem

Requirement: from the sequence `[5, 12, 7, 20, 9]`, select even numbers and compute their sum.

**Collection** serves as the common data source:

~~~java
List<Integer> numbers = List.of(5, 12, 7, 20, 9);
~~~

**Iterator** — actively pull each element:

~~~java
import java.util.Iterator;
import java.util.List;

List<Integer> numbers = List.of(5, 12, 7, 20, 9);
Iterator<Integer> it = numbers.iterator();

int sum = 0;
while (it.hasNext()) {
    int n = it.next();
    if (n % 2 == 0) {
        sum += n;
    }
}
System.out.println(sum); // 32
~~~

**Stream API** — describe the filtering and aggregation:

~~~java
import java.util.List;

List<Integer> numbers = List.of(5, 12, 7, 20, 9);

int sum = numbers.stream()
        .filter(n -> n % 2 == 0)
        .mapToInt(Integer::intValue)
        .sum();

System.out.println(sum); // 32
~~~

**I/O** — only needed when the numbers reside outside the program, such as in a file. Read the data first or use the file as the Stream source:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

Path path = Path.of("numbers.txt"); // Each line contains a valid integer

try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
    int sum = lines
            .map(String::trim)
            .filter(s -> !s.isEmpty())
            .mapToInt(Integer::parseInt)
            .filter(n -> n % 2 == 0)
            .sum();

    System.out.println(sum); // 32 if the file contains 5, 12, 7, 20, 9
} catch (IOException e) {
    System.err.println("Could not open/read file: " + e.getMessage());
}
~~~

The last example assumes non-empty lines are valid integers; `Integer.parseInt` will throw `NumberFormatException` if the data is malformed. If a read error occurs while consuming the Stream, `UncheckedIOException` should also be handled according to the application's error policy.

Both Iterator-based traversal and Stream can solve the problem. They differ primarily in **level of control** and **expressiveness for chains of transformations**. I/O solves a different problem: bringing external data in before or during computation.

## 7. Detailed comparison table

| Criterion | Collection | Iterator | Stream API | I/O stream / Reader / Writer |
|---|---|---|---|---|
| **Nature** | Data container | Element-by-element traversal state | Computation pipeline over a source | Channel for reading/writing bytes or characters |
| **Typical API** | `size`, `add`, `contains` | `hasNext`, `next` | `filter`, `map`, `reduce`, `collect` | `read`, `write`, `flush`, `close` |
| **Reusability** | Usually supports multiple traversals | Each iterator advances forward; typically create a new iterator to traverse again | Each Stream can be consumed only once | Usually sequential read/write; rewind capability depends on source |
| **Control model** | Access and manage elements | External iteration | Internal iteration | Control reading/writing data |
| **Lazy?** | Container already holds data; some views compute on access | Fetches elements on each `next` call | Intermediate operations are usually lazy | Reads/writes occur per call and buffer |
| **Result** | Stored elements | Next element | Value, `Optional`, array, collection, or side effect | Data read/written |
| **Resource management** | Depends on implementation/source; usually no need to close | Usually no general close | Usually not; must be managed if backed by an I/O source | Usually must be closed when owning a resource |
| **Parallelism** | Requires appropriate concurrency mechanisms | Does not split processing by default | Has `parallel()` but must follow parallel contracts | Does not automatically become a parallel pipeline |

Do not infer that one API is always faster than another. Stream helps express transformation logic, but can incur boxing/unboxing, lambda overhead, or buffering in stateful operations. Manual loops are sometimes simpler and more efficient. Parallel processing via `parallelStream()` or `parallel()` adds work-splitting, synchronization, and result-merging overhead, so it must be benchmarked on real data.

## 8. Misconceptions to avoid

**"Stream is a new kind of Collection."** False: Collection holds data; Stream describes how data is consumed. A Stream can draw data from a collection or from a non-collection source.

**"`stream()` copies the entire List."** There is no such guarantee or requirement. Pipelines generally pull data from the source as they execute. Some terminal operations like `toList()` materialize the result.

**"A single Stream can be used for multiple calculations."** No. After a terminal operation or once closed, a new Stream must be created if the source supports it.

**"Calling `filter` runs immediately."** Normally no. It is a lazy intermediate operation; a terminal operation triggers the pipeline. The library may also optimize away certain steps when doing so does not affect the result, so do not use side effects in `map`/`peek` for mandatory logic.

**"`forEach` always preserves order."** No, especially with parallel pipelines. If you need to preserve the *encounter order* of an ordered source, consider `forEachOrdered` and understand that it may reduce parallel benefits.

**"Stream mutates the source like Iterator.remove."** Not by default. Stream favors non-interfering processing; `Iterator.remove` is a source-mutating operation with a specific contract, if supported.

**"Everything named Stream has `map` and `filter`."** `InputStream` reads bytes; `Stream<T>` processes elements of type `T`; they belong to different API hierarchies.

**"`Files.lines` closes automatically when calling `count` or `toList`."** No. A terminal operation does not automatically replace `close`; use `try-with-resources`.

## 9. Which tool should you choose in practice?

| Need | Typically suitable choice | Why |
|---|---|---|
| Store a list for lookup, adding, removing, re-traversing | `List`, `Set`, `Map` (depending on the problem) | Need a persistent data-holding structure; `Map` does not extend `Collection` but is also a data structure. |
| Traverse sequentially and decide exactly when to fetch elements | `Iterator`, `for-each`, loop | Control remains with the developer. |
| Remove elements immediately while traversing a mutable collection | `Iterator.remove` if supported, or dedicated removal APIs | Respects the collection's mutation contract. |
| Filter, map, count, search, aggregate, group data | Stream API | Readable pipeline, declarative operation composition. |
| Read/write binary files or byte protocols | `InputStream`, `OutputStream` | Handles bytes and I/O resources. |
| Read/write text with a charset | `Reader`/`Writer` or corresponding `Files` APIs | Handles characters and encoding. |
| Filter or aggregate lines of a large file | `Files.lines` + Stream API inside `try-with-resources` | Combines on-demand reading with a processing pipeline. |
| Heavy CPU-bound tasks needing parallelism | Evaluate parallel Stream after benchmarking | Requires a splittable source, non-interfering functions, and suitable combining operations. |

## 10. Self-check

**Question 1.** After calling `List<Integer> data = List.of(1, 2, 3);` and then `data.stream().filter(n -> n > 1);`, how many elements are removed from `data`?

**Answer:** Zero elements are removed. Only a pipeline was defined; there is no terminal operation, and `filter` does not mutate the source collection.

**Question 2.** Why is `Stream<String> s = names.stream(); s.count(); s.findFirst();` invalid?

**Answer:** `count()` has already consumed `s`. To find the first element, create a new Stream from `names` if the source can be re-traversed.

**Question 3.** When using `Files.lines(path)` to take the first 20 lines, can you omit `try-with-resources` because `limit(20)` is used?

**Answer:** No. `limit` can stop processing early, but it does not replace `close` to release the file resource.

**Question 4.** When can using an `Iterator` be more direct than using a Stream?

**Answer:** When you need to decide for yourself when to call `next()`, control the traversal loop, or remove elements during traversal via `Iterator.remove()` if the iterator supports it.

**Question 5.** A file contains one integer per line. Which API is responsible for reading the file and which API is responsible for filtering even numbers?

**Answer:** `Files.lines` or a Reader supplies the data from the file; the Stream API provides `mapToInt`, `filter`, and `sum` to process the values.

---

**Remember:** Collection is **where elements are kept**; Iterator is **how to retrieve them one by one**; Stream API is **how to declare processing operations**; I/O streams are **how to move bytes/characters in or out**. When combining them, always verify whether the source is reusable, whether the pipeline has already been consumed, and whether any resource needs to be closed.

