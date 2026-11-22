# Distinguishing Stream, Collection, Iterator, and I/O Streams in Java

In Java, the same word *stream* can refer to **two completely different API groups**: **java.util.stream.Stream<T>**, used to build an element-processing pipeline, and **java.io.InputStream/OutputStream**, used to read and write bytes through I/O sources and destinations. In addition, **Collection<E>** manages a group of elements, while **Iterator<E>** helps traverse elements one by one.

These four concepts can work together in the same application, but they are not directly interchangeable. A file is read using an I/O API; its lines can become a Stream<String> for filtering and transformation; the result can be collected into a List<String> for reuse. This article explains their contracts, lifecycles, common pitfalls, and how to choose among them in Java 17+.

## 1. Quick comparison

| Abstraction | Representative | Purpose | Characteristic behavior |
| --- | --- | --- | --- |
| **Collection<E>** | java.util.Collection, List, Set | Models a group of data | size, contains, add/remove if supported, iterator |
| **Iterator<E>** | java.util.Iterator | Sequential element traversal | hasNext, next, optional remove |
| **Stream<T>** | java.util.stream.Stream | Describes element-processing operations | filter, map, sorted, collect; single-pass only |
| **I/O byte stream** | java.io.InputStream/OutputStream | Byte transmission | read, write, close; may block / throw IOException |
| **I/O character stream** | java.io.Reader/Writer | Character reading/writing | read characters, write characters, decoding/encoding via adapter |

**Key takeaway:** Collection stores/represents data; Iterator drives a single traversal; the Stream API describes how elements are processed; I/O streams transport bytes/characters between the program and a source/destination.

## 2. Collection<E>: data organized as a collection

Collection is an interface of the Java Collections Framework. For example, List stores elements ordered by position, and Set maintains element uniqueness according to the equality contract.

~~~java
import java.util.ArrayList;
import java.util.List;

List<String> names = new ArrayList<>(
    List.of("An", "Binh", "Mai")
);
System.out.println(names.size());      // 3
System.out.println(names.get(0));      // An
names.add("Lan");
System.out.println(names.contains("Lan")); // true
~~~

The snippet above is illustrative code placed inside a method; a standalone runnable program is in section 9.

A Collection typically has query operations such as **size, isEmpty, contains, toArray**, and can provide **iterator()**, **stream()**, and **parallelStream()**. However, you must not assume that every Collection is mutable:

~~~java
List<String> fixed = List.of("An", "Mai");

// Throws UnsupportedOperationException:
fixed.add("Lan");
~~~

List.of returns an unmodifiable List; ArrayList in the previous example supports add/remove. Some Collections are also only a **view** over another structure, not necessarily a completely independent copy.

Map<K,V> **does not extend Collection**. Its keySet(), values(), and entrySet() methods return appropriate collection views for traversal or converting into a stream.

### 2.1. A Collection can be traversed multiple times

~~~java
List<String> names = List.of("An", "Binh", "Mai");

for (String name : names) {
    System.out.println(name);
}
for (String name : names) {
    System.out.println(name);
}
~~~

Traversing twice is valid for a typical List. The ability to create a new traversal is an important difference compared to **the same Stream instance** after it has been consumed.

However, a Collection is not necessarily immutable or guaranteed to be safe for multiple threads. When the underlying structure is modified during traversal, you must follow the implementation's contract.

## 3. Iterator<E>: the cursor of a single traversal

Iterator is not a container for elements; it provides a mechanism to move from the current element to the next element:

~~~java
boolean hasNext();
E next();
void remove(); // Optional operation
~~~

- **hasNext():** checks whether there is a next element.
- **next():** retrieves the next element and advances the traversal state; reaching the end causes NoSuchElementException.
- **remove():** if supported by the iterator, removes the element most recently returned by next from the underlying structure. Not every iterator supports this.

Example of removing short names from an ArrayList:

~~~java
List<String> names = new ArrayList<>(
    List.of("An", "Binh", "Bo")
);

Iterator<String> iterator = names.iterator();
while (iterator.hasNext()) {
    String name = iterator.next();
    if (name.length() <= 2) {
        iterator.remove();
    }
}

System.out.println(names); // [Binh]
~~~

Here **Iterator.remove() actually mutates the ArrayList**. In contrast, the Stream.filter operation in the next section only selects elements for the result without removing from the source.

You should not simultaneously remove directly using names.remove(name) inside a loop that is using an ArrayList iterator. Modifying the structure outside the iterator can cause the iterator to detect a ConcurrentModificationException. This is not a mechanism that guarantees thread-safety; fail-fast behavior is **best effort**, not to be used as a synchronization mechanism.

### 3.1. An Iterator usually cannot be reset

Once exhausted, a normal iterator does not automatically return to the beginning. For a Collection that can be traversed again, call **collection.iterator()** to obtain a new iterator. The Iterator interface does not specify reset or rewind. If bidirectional traversal is needed for a List, consider ListIterator with the appropriate previous/hasPrevious methods.

An Iterator can also be written to read elements from a data-generating source, not necessarily originating from a Collection. Therefore, you cannot infer that an Iterator always has a fixed size or holds all data in RAM.

### 3.2. For-each relates to Iterable

Enhanced for:

~~~java
for (String name : names) {
    System.out.println(name);
}
~~~

works with an array or an **Iterable** object. Collection<E> extends Iterable<E>, so it can usually be used with for-each. Stream<T> does not extend Iterable<T>, so you cannot directly write for (String name : stream). To traverse a Stream, use a terminal operation such as forEach, or obtain an iterator from the Stream and obey single-pass consumption.

## 4. Stream<T>: a pipeline, not a container

java.util.stream.Stream<T> is a sequence of elements supporting sequential or parallel aggregate operations, typically created from a Collection, array, generator, or I/O source.

~~~java
List<String> names = List.of("An", "Binh", "Mai");

List<String> upperLongNames = names.stream()
    .filter(name -> name.length() > 2)
    .map(String::toUpperCase)
    .toList();

System.out.println(upperLongNames); // [BINH, MAI]
~~~

The Stream here is not a second ArrayList automatically created when calling stream(). It describes a **pipeline**:

~~~text
Source List<String>
    |
    v
stream() -> filter() -> map() -> toList()
                          |
                          v
                  Result List<String>
~~~

### 4.1. Intermediate operations and terminal operations

| Group | Examples | Role |
| --- | --- | --- |
| Intermediate | filter, map, flatMap | Transform the stream of elements |
| Stateful intermediate | sorted, distinct | May need to retain many elements |
| Bounded intermediate | limit, skip, takeWhile | Limit or skip elements |
| Result-collecting terminal | toList, collect, count | Return a result/aggregate |
| Search terminal | findFirst, anyMatch, allMatch | Can short-circuit |
| Action terminal | forEach, reduce | Execute/aggregate according to contract |

**Intermediate operations are usually lazy:** creating a pipeline does not necessarily perform operations on the data until a terminal operation requests a result. Some pipelines can short-circuit; the compiler/runtime may optimize so that not every callback is invoked the exact number of times the author imagines.

~~~java
Stream<String> pipeline = names.stream()
    .filter(name -> name.length() > 2);

System.out.println("before terminal");
System.out.println(pipeline.count());
~~~

The print statements execute in order, but you should not use filter/map as a place that must write logs, write to a database, or increment a counter. How many times a callback is invoked depends on the pipeline and the terminal operation.

### 4.2. A Stream is consumed only once

~~~java
Stream<String> stream = names.stream();
List<String> result = stream.toList();

// INVALID: this stream has already been consumed.
long count = stream.count();
~~~

Attempting to reuse it may throw IllegalStateException; some cases of reuse might go undetected, so the proper rule is **do not reuse the same Stream instance**. Create a new stream from the Collection if you need to process it again:

~~~java
List<String> result = names.stream().toList();
long count = names.stream().count();
~~~

Do not write a Supplier<Stream<T>> whose get() returns **the same cached Stream** every time. A proper supplier must create a new Stream when called, if the goal is reprocessing.

### 4.3. Stream does not modify the source Collection by default

~~~java
List<String> source = new ArrayList<>(
    List.of("An", "Mai")
);
List<String> filtered = source.stream()
    .filter(name -> name.length() > 2)
    .toList();

// source still contains [An, Mai]; filtered is [Mai].
~~~

If you want to mutate source, you can use **source.removeIf(predicate)** on a mutable collection or an update operation with its own contract. However, do not modify source from a filter/map lambda or another thread while the pipeline is traversing; the Stream API generally requires behavioral parameters to be **non-interfering** and free of unsafe shared state.

Stream.toList() on Java 17 returns an **unmodifiable** List; the result does not automatically inherit the mutability of the source ArrayList. If a mutable ArrayList is needed, collect the result using Collectors.toCollection(ArrayList::new).

### 4.4. Sequential and parallel Streams

A Stream can be sequential or parallel. For example:

~~~java
long total = numbers.parallelStream()
    .mapToLong(Integer::longValue)
    .sum();
~~~

The snippet above requires a Collection<Integer> named numbers. A parallel stream is not automatically faster: there is overhead for splitting work, ordering contracts, source size, and computation intensity. Callbacks containing mutation, logging, or shared variables are not automatically made safe by parallelStream.

**Stream.forEach** in a parallel pipeline does not guarantee execution order; **forEachOrdered** is used when it is necessary to respect the appropriate encounter order. A for-each loop on a sequential List and a parallelStream.forEach cannot be treated as two expressions with the same ordering behavior.

## 5. I/O streams: InputStream and OutputStream

Byte I/O streams reside in **java.io**, are responsible for reading and writing **bytes**, and do not provide filter/map/toList like Stream<T>.

~~~java
int value = input.read(); // 0..255 or -1 at EOF

if (value != -1) {
    output.write(value);
}
~~~

This is an **illustrative snippet**, with input/output being appropriate InputStream/OutputStream objects. The -1 value from read() is the end-of-source marker, not data to be written. Operations can be blocking and can throw IOException.

An I/O source can be a file, socket, byte array, pipe, or device. Example of an in-memory byte stream:

~~~java
byte[] bytes = "Hi".getBytes(
    java.nio.charset.StandardCharsets.UTF_8);

try (java.io.ByteArrayInputStream input =
         new java.io.ByteArrayInputStream(bytes)) {
    String text = new String(
        input.readAllBytes(),
        java.nio.charset.StandardCharsets.UTF_8
    );
    System.out.println(text); // Hi
}
~~~

The snippet above is illustrative code inside a method that handles or declares IOException when used in a complete class. With FileInputStream, sockets, and streams holding OS resources, close is an important part of lifecycle management.

### 5.1. Reader and Writer are character I/O

Reader/Writer are abstractions for **characters**, not stream pipeline abstractions. To convert bytes to text properly, use the appropriate charset via InputStreamReader or Files methods.

~~~java
try (java.io.BufferedReader reader =
         java.nio.file.Files.newBufferedReader(
             path,
             java.nio.charset.StandardCharsets.UTF_8)) {
    String firstLine = reader.readLine();
}
~~~

This is illustrative code requiring a valid Path and IOException handling. A byte stream does not inherently know whether a sequence is UTF-8, UTF-16, or another encoding; decoding/encoding is part of the data-processing contract.

### 5.2. The lifecycle of I/O differs from a Stream pipeline

- I/O sources usually need **close()** to release file descriptors/sockets/handles.
- Reading/writing can block, encounter EOF, or throw IOException.
- An InputStream may support mark/reset depending on the implementation; you **cannot** assume every InputStream can rewind.
- readAllBytes/readAllLines may hold the entire content in memory; use caution with large data.
- Different byte streams/readers can be wrapped by buffers or adapters, and close ownership must be consistent.

Do not use Stream<T>.close in place of closing I/O resources held by another component if the API does not manage them itself.

## 6. Why is Files.lines both I/O and returning a Stream<String>?

**Files.lines(Path, Charset)** reads text lines from a file and returns a **java.util.stream.Stream<String>**. It does not return an InputStream, yet underneath it has an I/O source:

~~~text
File (bytes)
    |
    v
Read and decode by Charset
    |
    v
String lines
    |
    v
java.util.stream.Stream<String>
    |
    v
filter / map / limit / count / toList
~~~

Example:

~~~java
try (Stream<String> lines =
         Files.lines(path, StandardCharsets.UTF_8)) {
    List<String> nonBlank = lines
        .filter(s -> !s.isBlank())
        .toList();
}
~~~

The snippets in this section use the class names Files, Path, Stream, List, StandardCharsets according to their corresponding imports; see the standalone program in section 9.

**You must use try-with-resources** for I/O-backed Streams such as **Files.lines, Files.list, Files.walk, Files.find**. Terminal operations like count or toList do not automatically guarantee closing all underlying resources if an error occurs. Stream<T> extends BaseStream, which is AutoCloseable, though a pure stream from a List usually has no resources to close.

### 6.1. Files.readAllLines differs from Files.lines

~~~java
List<String> all = Files.readAllLines(
    path, StandardCharsets.UTF_8);
~~~

readAllLines returns an **already-populated List<String>**, suitable when all data can fit in memory and you want to traverse it multiple times.

~~~java
try (Stream<String> lines =
         Files.lines(path, StandardCharsets.UTF_8)) {
    long count = lines.filter(s -> !s.isBlank()).count();
}
~~~

Files.lines can process lines on demand as required by the pipeline, avoiding the need to build a List containing every line before starting. However, **lazy does not mean memory is always constant**: sorted, distinct, groupingBy, and toList can accumulate most of the data.

When processing a Stream from a file, errors on open may be IOException; I/O errors arising during traversal may also surface as **UncheckedIOException**. The Stream API does not turn I/O operations into pure computations.

### 6.2. BufferedReader.lines

BufferedReader has a lines() method returning a Stream<String> from the reader:

~~~java
try (BufferedReader reader = Files.newBufferedReader(
        path, StandardCharsets.UTF_8)) {
    List<String> firstThree =
        reader.lines().limit(3).toList();
}
~~~

The **Reader** in the snippet above is the resource managed by try-with-resources. Do not infer that any terminal operation on reader.lines() automatically closes the reader.

## 7. When to choose Iterator, when to choose Stream?

Iterator makes sense when you need **step-by-step control**, have complex conditional loops, need break, or need to use remove() on a supporting implementation.

~~~java
Iterator<String> it = names.iterator();
while (it.hasNext()) {
    String value = it.next();
    if (value.isEmpty()) {
        it.remove();
    }
}
~~~

Stream makes sense when you need a readable pipeline to filter, transform, or aggregate:

~~~java
List<String> cleaned = names.stream()
    .filter(s -> !s.isBlank())
    .map(String::trim)
    .toList();
~~~

The two snippets are **not equivalent**: the Iterator snippet mutates names, whereas the Stream snippet creates a result and leaves names unchanged as long as the callbacks do not interfere with the source.

A for loop with if/break can be clearer than a pipeline that abuses filter/peek to simulate control flow. The goal is to choose the abstraction that matches the contract, not to force every operation into a lambda.

### 7.1. Controlled conversions between them

Collection → Stream:

~~~java
Stream<String> stream = names.stream();
~~~

Stream → unmodifiable List:

~~~java
List<String> collected = names.stream()
    .map(String::toUpperCase)
    .toList();
~~~

Stream → mutable ArrayList:

~~~java
ArrayList<String> collected = names.stream()
    .map(String::toUpperCase)
    .collect(java.util.stream.Collectors.toCollection(ArrayList::new));
~~~

Iterator → Stream when only an iterator is available:

~~~java
Iterator<String> iterator = names.iterator();
java.util.Spliterator<String> spliterator =
    java.util.Spliterators.spliteratorUnknownSize(
        iterator, java.util.Spliterator.ORDERED);
Stream<String> stream =
    java.util.stream.StreamSupport.stream(spliterator, false);
~~~

Use ORDERED only when the source genuinely has an encounter order; do not declare inaccurate characteristics to arbitrarily “optimize”. The new Stream still consumes the same source iterator and does not automatically copy every element; do not traverse simultaneously with both the iterator and the stream.

Stream → Iterator:

~~~java
Iterator<String> iterator = names.stream().iterator();
~~~

This is an iterator created from a Stream and consumes that Stream. Do not reuse the Stream instance in an invalid way after starting a traversal.

## 8. Resource management and common pitfalls

### 8.1. What needs to be closed?

- **In-memory Collection:** has no standard close.
- **Standard Iterator:** has no close in the interface.
- **Stream from a Collection:** has close, but usually has no I/O resources to release.
- **Stream returned by Files.lines/list/walk/find:** may hold resources; use try-with-resources.
- **InputStream, OutputStream, Reader, Writer:** usually need closing when holding resource ownership.

A good file-reading method can wrap the entire I/O stream in try-with-resources and return the **collected data result**, instead of returning an open Stream without making clear that the caller must close it. If an API returns an I/O-backed Stream, it must make the caller's close obligation explicit.

### 8.2. Collection and Iterator do not guarantee thread safety by themselves

Modifying an ArrayList from another thread while an iterator or stream is traversing can corrupt results or throw an exception; fail-fast is not a synchronization mechanism. For concurrency, choose concurrent collections, work on snapshots, or guard state properly.

### 8.3. Avoid side effects in filter/map

Do not rely on the number of callback invocations in a Stream as the basis for audit logging, because lazy/short-circuit/optimizations/parallel execution change how it runs. With Iterator, the author controls each next call more explicitly, though reading an external source can still throw errors or cause side effects per the API contract.

### 8.4. Distinguish content, encoding, and buffering

InputStream returns bytes; Reader decodes characters. Stream<String> from Files.lines contains String lines; it does not preserve line endings as separate characters at the end of each element. To preserve exact line separators, BOM, and encoding when converting, use an appropriate I/O workflow. Do not assume the system's default charset matches the data protocol.

## 9. Complete Java 17+ program

The following program uses all four concepts, has deterministic output, and requires no pre-existing file. It creates a temporary file, writes UTF-8 data, and deletes it after use:

- ArrayList is the **Collection** storing names.
- Iterator.remove() actually mutates the ArrayList.
- Stream.filter/map produces a **result List** without mutating the source.
- The same Stream has a terminal operation called a second time, illustrating the reuse error.
- ByteArrayOutputStream and ByteArrayInputStream write/read **bytes**.
- Files.lines returns a **Stream<String>** from the file and is closed with try-with-resources.

Create the file **StreamConceptsDemo.java**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.stream.Stream;

public class StreamConceptsDemo {
    public static void main(String[] args) throws IOException {
        List<String> names = new ArrayList<>(
            List.of("An", "Binh", "Mai", "Bo"));
        System.out.println("collection=" + names);

        Iterator<String> iterator = names.iterator();
        while (iterator.hasNext()) {
            if (iterator.next().length() <= 2) {
                iterator.remove();
            }
        }
        System.out.println("after-iterator=" + names);

        Stream<String> pipeline = names.stream()
            .filter(name -> name.length() > 3)
            .map(String::toUpperCase);
        System.out.println("before-terminal=" + names);
        System.out.println("stream-result=" + pipeline.toList());
        System.out.println("after-stream=" + names);

        try {
            pipeline.count();
        } catch (IllegalStateException error) {
            System.out.println("stream-reuse=" +
                error.getClass().getSimpleName());
        }

        ByteArrayOutputStream byteOutput = new ByteArrayOutputStream();
        byteOutput.write("Hi".getBytes(StandardCharsets.UTF_8));
        try (ByteArrayInputStream byteInput =
                 new ByteArrayInputStream(byteOutput.toByteArray())) {
            System.out.println("io-bytes=" + new String(
                byteInput.readAllBytes(), StandardCharsets.UTF_8));
        }

        Path file = Files.createTempFile("java-stream-concepts-", ".txt");
        try {
            Files.writeString(file, "one\ntwo\nthree\n",
                StandardCharsets.UTF_8);
            try (Stream<String> lines =
                     Files.lines(file, StandardCharsets.UTF_8)) {
                System.out.println("file-lines=" +
                    lines.map(String::toUpperCase).toList());
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Commands to compile and run with JDK 17 or later:

~~~bash
javac StreamConceptsDemo.java
java StreamConceptsDemo
~~~

**Exact** stdout:

~~~text
collection=[An, Binh, Mai, Bo]
after-iterator=[Binh, Mai]
before-terminal=[Binh, Mai]
stream-result=[BINH]
after-stream=[Binh, Mai]
stream-reuse=IllegalStateException
io-bytes=Hi
file-lines=[ONE, TWO, THREE]
~~~

### 9.1. Explanation of each output group

**collection:** ArrayList has 4 names and can be traversed and modified according to the implementation's API.

**after-iterator:** Iterator.remove removes "An" and "Bo" because each has length 2, so the Collection actually has only Binh and Mai left.

**before-terminal:** creating the stream has not transformed the ArrayList. **stream-result:** filter keeps names with length greater than 3, then map converts Binh to BINH. **after-stream:** the source ArrayList is still [Binh, Mai].

**stream-reuse:** after toList(), count cannot be run on the same Stream. The code catches IllegalStateException and prints the class name for illustration.

**io-bytes:** the byte stream writes two UTF-8 bytes for "Hi", then reads and decodes them into a String. There are no Stream<T> filter/map operations in this step.

**file-lines:** Files.lines reads String lines from the written file; map converts them to uppercase. The I/O-backed Stream is closed before deleting the file. The temporary file name is not printed so stdout remains deterministic.

The Java literal "one\ntwo\nthree\n" contains escape sequences representing line breaks, so the file has three lines of text. If Files.deleteIfExists fails, IOException can propagate out of main; the example does not swallow resource errors.

## 10. Decision table

| What do you need to do? | Appropriate abstraction | Notes |
| --- | --- | --- |
| Hold and manage elements across multiple passes | Collection/List/Set | Verify structure and mutability |
| Traverse element by element under caller control | Iterator | next advances the cursor, remove is optional |
| Filter, map, group, or aggregate | Stream<T> | Single-use, callbacks should be non-interfering |
| Compute over int/long/double | IntStream/LongStream/DoubleStream | Avoids boxing when appropriate |
| Read/write bytes | InputStream/OutputStream | EOF, IOException, close |
| Read/write characters | Reader/Writer | Charset, decoding/encoding |
| Read a file line by line and filter immediately | Files.lines | Returns Stream<String>, must be closed |
| Read all lines into data | Files.readAllLines | Returns List<String>, may use significant RAM |
| Want Stream results for repeated use | Collect into a Collection or create a new Stream | Do not cache the same Stream |
| Want to remove elements while traversing an ArrayList | Iterator.remove or removeIf | Do not mutate source from a Stream callback |

## 11. Common misconceptions

**Mistake 1 — treating Stream<T> as an InputStream:** the names are similar, but the methods are completely different. InputStream reads bytes; Stream<T> processes elements of type T.

**Mistake 2 — thinking a Stream is a list:** Stream has no get(index) and generally cannot run a terminal operation a second time. If you want data for reuse, collect into a List.

**Mistake 3 — thinking a Collection is always modifiable:** List.of and some views/collection wrappers do not support add/remove.

**Mistake 4 — thinking Stream.filter removes from the source:** filter selects elements for the pipeline, whereas Collection.removeIf is the source-updating operation when supported.

**Mistake 5 — inferring semantics from similar names:** Collection.stream, Files.lines, and BufferedReader.lines can all return Stream<T>, but their underlying lifecycles are very different.

**Mistake 6 — forgetting close after Files.lines:** a terminal operation may finish while the I/O resource still needs to be closed; use try-with-resources.

**Mistake 7 — using readAllBytes on overly large sources:** can consume inappropriate amounts of memory. Consider buffered reading or incremental processing.

**Mistake 8 — thinking lazy means no RAM needed:** sorted, distinct, toList, and collect can retain many elements.

**Mistake 9 — mutating a Collection while a Stream is running:** can violate non-interference, leading to errors or unreliable results.

**Mistake 10 — using fail-fast as a synchronization mechanism:** ConcurrentModificationException is not guaranteed to detect every conflict.

**Mistake 11 — expecting InputStream to support reset:** mark/reset is implementation-dependent; not every source can rewind.

**Mistake 12 — misunderstanding order with parallelStream:** forEach can execute out of source order; check the encounter order contract and how aggregation works.

**Mistake 13 — ignoring I/O errors:** the fact that Files.lines returns Stream<String> does not eliminate IOException/UncheckedIOException from the file source.

**Mistake 14 — using Stream in every case:** a for/Iterator loop with complex break/continue is sometimes clearer and easier to control.

## 12. Self-check questions

1. Why can stream() be called multiple times on the same List, while the same Stream cannot be reused after toList()?
2. What does Iterator.remove mutate? Does Stream.filter mutate the original Collection?
3. What does InputStream.read return at the end of the source, and why must -1 not be treated as a data byte?
4. What type of object does Files.lines return, and how does it still depend on I/O?
5. Why does Files.lines need try-with-resources even when only calling count?
6. When is Files.readAllLines more appropriate than Files.lines, and vice versa?
7. Why do HashSet, ArrayList, and Map have different contracts?
8. Is an Iterator guaranteed to rewind to the beginning or know the number of elements in advance?
9. Why is a pipeline with sorted or toList not guaranteed to use constant memory?
10. Why is parallelStream not automatically faster?
11. How do you obtain a Stream from an Iterator when an API only provides an Iterator?
12. In the complete example, which part mutates the ArrayList, which part only transforms values, and which part reads/writes bytes?
13. If a Stream has an I/O source, who is responsible for closing it when finished?
14. In a multi-threaded scenario, why does fail-fast not replace synchronization?
15. When processing text data, why should the charset be specified right at the I/O boundary?

**Conclusion:** **Collection** is an abstraction that manages a group of elements; **Iterator** represents a single traversal; **Stream<T>** represents a pipeline for transforming and aggregating elements, typically lazy and consumed only once; and **InputStream/OutputStream/Reader/Writer** are tools for transferring bytes and characters over I/O. They can work together, but they differ in purpose, lifecycle, cost, exceptions, and resource management.