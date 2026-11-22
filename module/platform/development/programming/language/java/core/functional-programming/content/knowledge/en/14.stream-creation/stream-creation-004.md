# Stream.generate() with Supplier in Java

## 1. Concept: creating an element source on demand

`Stream.generate(Supplier<? extends T> s)` is a `static` method of `java.util.stream.Stream` used to create **a sequential stream, without a guaranteed encounter order, that is conceptually infinite**. Each time the stream source needs to generate an element, it asks the `Supplier` to provide a value via the `get()` method.

API signature:

~~~java
public static <T> Stream<T> generate(Supplier<? extends T> s)
~~~

`Supplier<T>` is a functional interface in the `java.util.function` package with a single abstract method (SAM):

~~~java
T get();
~~~

Because it takes no arguments, a supplier represents the behavior **"when requested, provide an element"**. It can be written as a lambda `() -> value`, a method reference such as `UUID::randomUUID`, or an object implementing `Supplier<T>`.

~~~java
Stream<String> messages = Stream.generate(() -> "hello");
~~~

**Note:** The snippet above only illustrates a statement inside a method that has imported `java.util.stream.Stream`; it **does not execute the supplier yet** at pipeline creation time. To obtain elements, you must use a terminal operation such as `toList()`, `forEach()`, `findFirst()`, or `count()` together with an appropriate bounding mechanism.

A more basic and safer usage is to limit the number of elements to consume:

~~~java
List<String> three = Stream.generate(() -> "hello")
        .limit(3)
        .toList();
~~~

The result is `[hello, hello, hello]`. Here `limit(3)` is an *intermediate operation*, while `toList()` triggers the consumption of the pipeline.

**Remember right away:** `generate()` declares the **rule for generating elements**, whereas the **terminal operation** actually drives the stream to run. However, being "lazy" does not mean the supplier is automatically cached, automatically thread-safe, or never causes side effects.

## 2. How it works: `Supplier`, pipeline, and terminal operation

Read the pipeline stage by stage:

~~~text
Supplier<T>             Stream<T>                  Result
  () -> T      ──► Stream.generate(s) ──► limit(n) ──► toList()
                 lazy source (infinite)     limit       consume
~~~

The roles:

1. **`Supplier`** describes how to provide a value of type `T` each time `get()` is called.
2. **`Stream.generate(s)`** creates the stream source. Calling it does not require pre-generating any elements.
3. **`limit(n)`** specifies at most `n` elements to pass downstream; it does not consume the pipeline at the time it is called.
4. **`map`, `filter`** are intermediate transformation/filtering steps, which are also lazy.
5. **`toList`, `forEach`, `reduce`, `collect`, `findFirst`, `count`** are terminal operations. They trigger traversal and may ask the supplier to generate elements.

An important difference from a collection: `List.of("a","b")` stores two elements upfront. With `Stream.generate(() -> expensive())`, values are **not pre-built into a list** when declaring the source; `expensive()` will be executed when traversal requests an element.

### 2.1. When does `get()` run?

With a simple sequential pipeline `Stream.generate(supplier).limit(3).toList()`, the supplier is called three times to produce three elements. If you only construct the pipeline without calling a terminal operation, there is no traversal. If you use `limit(0)`, the result is empty and no element needs to be requested from the source.

In complex pipelines, **do not equate the number of result elements with the number of `get()` calls**:

~~~java
List<Integer> values = Stream.generate(() -> 1)
        .filter(x -> x > 10)
        .limit(3)
        .toList();
~~~

**This is an intentionally dangerous example—do not run:** the source only produces `1`, and the condition `x > 10` is always false, so `limit(3)` never receives three elements and the terminal operation can run forever. `limit` caps **the number of elements passing through**, not always **the number of generation attempts** before a filter.

Another pipeline:

~~~java
List<Integer> values = Stream.generate(() -> 1)
        .limit(3)
        .filter(x -> x > 10)
        .toList();
~~~

The second pipeline completes and returns an empty list, because `limit(3)` limits the number of elements **before** filtering. **The order of `limit` and `filter` matters greatly** when the source can be infinite.

## 3. Complete example: verifying laziness and invocation count

Save the file **`StreamGenerateDemo.java`**:

~~~java
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;
import java.util.stream.Stream;

public class StreamGenerateDemo {
    public static void main(String[] args) {
        AtomicInteger counter = new AtomicInteger();

        Supplier<String> source = () -> {
            int current = counter.incrementAndGet();
            System.out.println("get#" + current);
            return "ticket-" + current;
        };

        Stream<String> stream = Stream.generate(source);
        System.out.println("before=" + counter.get());

        List<String> tickets = stream.limit(3).toList();
        System.out.println("tickets=" + tickets);
        System.out.println("after=" + counter.get());

        List<String> fixed = Stream.generate(() -> "ping")
                .limit(2)
                .toList();
        System.out.println("fixed=" + fixed);
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac StreamGenerateDemo.java
java StreamGenerateDemo
~~~

Stdout:

~~~text
before=0
get#1
get#2
get#3
tickets=[ticket-1, ticket-2, ticket-3]
after=3
fixed=[ping, ping]
~~~

**Reading the output:**

- `Stream.generate(source)` only creates a stream describing the generation source; at the time `before` is printed, `counter` is still `0`.
- When `toList()` requests three elements from `limit(3)`, the supplier runs sequentially and increments the counter to `1`, `2`, `3`.
- `List<String> tickets` holds the generated strings, and the `stream` variable has already been consumed by a terminal operation. **You must not reuse the same stream** to run another terminal operation.
- The final pipeline creates a **new stream** from the constant supplier `() -> "ping"`, returning two identical elements.

`AtomicInteger` in this example is only for clearly measuring the invocation count. Incrementing the counter is still a **side effect** of the supplier and is not an ideal design pattern for every pipeline. This example intentionally runs sequentially so stdout has a stable order.

## 4. When should `Stream.generate()` be used?

### 4.1. Generating independent elements using the same rule

Example generating random identifiers:

~~~java
List<UUID> ids = Stream.generate(UUID::randomUUID)
        .limit(5)
        .toList();
~~~

`UUID::randomUUID` is a method reference to a no-argument `static` method returning `UUID`; it is compatible with `Supplier<UUID>`. This snippet requires importing `java.util.List`, `java.util.UUID`, and `java.util.stream.Stream`.

Characteristic: each element is created when the source needs to supply data. However, you should not use UUIDs as proof that the stream has an encounter order or that it always makes an exact number of calls in any parallel pipeline. If you need predictable output for testing, use a deterministic supplier instead of random UUIDs.

### 4.2. Generating dummy data for testing or demos

~~~java
List<String> placeholders = Stream.generate(() -> "UNKNOWN")
        .limit(4)
        .toList();
~~~

Fixed data like `"UNKNOWN"` does not need a stateful mechanism. This approach fits when you want to create a list of size `n` with the same value, such as mock data for UI testing.

If you only need *one* value or a few known literals, using `List.of(...)` may be simpler and easier to read. Do not force `generate` into every collection-creation case.

### 4.3. Creating new objects on demand

~~~java
List<StringBuilder> buffers = Stream.generate(StringBuilder::new)
        .limit(3)
        .toList();
~~~

Here the constructor reference `StringBuilder::new` is compatible with `Supplier<StringBuilder>`. Three element allocations in a simple sequential pipeline will create three independent `StringBuilder` objects.

**Distinction:** `Stream.generate(() -> sharedBuffer)` only returns the same reference to `sharedBuffer` repeatedly. `Stream.generate(StringBuilder::new)` invokes the constructor each time to create a new object. The `Supplier<T>` signature **does not determine** whether an object is newly created or reused: that depends on the supplier's body.

## 5. Complete example: creating DTOs and combining with a pipeline

Save the file **`GeneratedRecordsDemo.java`**:

~~~java
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;
import java.util.stream.Stream;

public class GeneratedRecordsDemo {
    record Ticket(int id, String state) {}

    public static void main(String[] args) {
        AtomicInteger sequence = new AtomicInteger(100);

        Supplier<Ticket> ticketFactory = () ->
                new Ticket(sequence.incrementAndGet(), "NEW");

        List<String> descriptions = Stream.generate(ticketFactory)
                .limit(3)
                .map(t -> t.id() + ":" + t.state())
                .toList();

        System.out.println("tickets=" + descriptions);
        System.out.println("lastId=" + sequence.get());

        List<Integer> ordered = Stream.iterate(1, n -> n + 1)
                .limit(4)
                .toList();

        System.out.println("iterate=" + ordered);
    }
}
~~~

Run commands:

~~~bash
javac GeneratedRecordsDemo.java
java GeneratedRecordsDemo
~~~

Output:

~~~text
tickets=[101:NEW, 102:NEW, 103:NEW]
lastId=103
iterate=[1, 2, 3, 4]
~~~

**Why do two different generation approaches appear together?**

- `generate(ticketFactory)` pulls each `Ticket` according to the behavior provided by the supplier. A `generate` source does not pass an index to the callback. We use an external `AtomicInteger` to generate IDs for demonstration.
- `map(t -> t.id() + ":" + t.state())` transforms each generated object into a string description, and `toList()` returns the resulting list.
- `Stream.iterate(1, n -> n + 1)` is a **sequence with a relationship to the previous element**, having a clear encounter order according to `iterate`'s rule. Therefore, when you want `1,2,3,4`, `iterate` expresses intent better than a counter-incrementing `Supplier`.
- The `Ticket` record is a standard feature since Java 16; the entire example is suitable for Java 17+.

**Note on ID generation code:** the shared counter is mutable state. The example is run sequentially with a small limit for easy illustration, **not** as proof that `Stream.generate` is naturally suited for generating ordered sequences in parallel.

## 6. The "infinite" nature and why stopping conditions matter

`Stream.generate` returns **a semantically infinite stream**, meaning the source does not signal on its own that it has run out of elements. It does not allocate infinite elements at declaration time; the risk occurs when a terminal operation attempts to consume the entire source without a stopping condition.

### 6.1. Safe approach with an explicit limit

~~~java
List<Integer> ten = Stream.generate(() -> 7)
        .limit(10)
        .toList();
~~~

Ten `7` elements are collected and then it finishes. For `limit(n)`, `n` must be non-negative; `limit(-1)` throws `IllegalArgumentException`.

### 6.2. Approaches that hang or exhaust resources

~~~java
// DO NOT RUN: attempting to collect an infinite source.
List<String> neverEnds = Stream.generate(() -> "x").toList();
~~~

Without an endpoint, `toList()` tries to collect forever, which can lead to massive resource consumption or non-termination. Similarly, `count()` or `forEach()` on an unbounded infinite source may never return.

Do not confuse `findFirst()` or `findAny()` with building a full list. They are terminal operations that can short-circuit once an element is received; however, a supplier's side effects and the number of invocations in parallel/complex pipelines still should not be predicted like a simple sequential loop.

### 6.3. `filter` can prevent `limit` from ever getting enough elements

~~~java
// DO NOT RUN: no value satisfies the condition.
Stream.generate(() -> 0)
      .filter(n -> n > 0)
      .limit(5)
      .toList();
~~~

`limit(5)` requires five elements **after filtering**, but the source only generates `0` and every element is discarded. Because five results are never reached, the pipeline does not terminate normally.

To limit the number of **generation attempts**, place `limit` before `filter`:

~~~java
List<Integer> none = Stream.generate(() -> 0)
        .limit(5)
        .filter(n -> n > 0)
        .toList();
// none is [].
~~~

In the second example, at most five elements from the source are allowed through `limit(5)` in the sequential pipeline. Because all are filtered out, the result is an empty list.

**Design lesson:** you need to determine whether you want to limit **the number of input elements** or **the number of matching output elements**. Choose the placement of `limit` accordingly, especially with an unbounded source.

## 7. `generate()` and `iterate()` are not completely interchangeable

| Criterion | `Stream.generate(supplier)` | `Stream.iterate(seed, next)` |
|---|---|---|
| Generation source | A parameterless `Supplier<T>` | First element + function to compute the next element |
| Relationship between elements | Not expressed via callback parameters | `next` receives the previous element |
| Encounter order | **Unordered** source | **Ordered** source |
| Default length | Infinite | Infinite with the 2-parameter overload |
| Variant with termination condition | No overload accepting a predicate directly | `iterate(seed, hasNext, next)` overload since Java 9 |
| Suitable use cases | Independent values, new objects, supplier-driven data | Recurrence sequences, indices, consecutive dates, sequential progressions |

Example of an ordered number sequence:

~~~java
List<Integer> sequence = Stream.iterate(1, n -> n + 1)
        .limit(4)
        .toList();
// [1, 2, 3, 4]
~~~

With Java 9+ you can use the three-argument overload:

~~~java
List<Integer> bounded = Stream.iterate(
        1,
        n -> n <= 4,
        n -> n + 1
).toList();
// [1, 2, 3, 4]
~~~

The three-argument form expresses the continuation condition directly in the source. If you only need a primitive `int` sequence from 1 to 4, `IntStream.rangeClosed(1, 4)` is usually shorter, clearer, and avoids boxing to `Integer`.

**Choose by semantics:** A supplier can hold an internal counter to generate `1,2,3,...`, but that hides the ordering relationship in mutable state. `iterate` or `IntStream.range` describes that relationship directly in the API.

## 8. A supplier can provide a new object or a shared object

The following two expressions have the same type `Supplier<List<String>>` but **completely different behavior**:

~~~java
List<String> shared = new ArrayList<>();

Supplier<List<String>> same = () -> shared;
Supplier<List<String>> fresh = ArrayList::new;
~~~

These are illustrative snippets requiring imports for `java.util.List`, `java.util.ArrayList`, and `java.util.function.Supplier`. If used:

~~~java
List<List<String>> a = Stream.generate(same).limit(3).toList();
List<List<String>> b = Stream.generate(fresh).limit(3).toList();
~~~

List `a` contains **three references pointing to the same `shared`**. Modifying `shared` afterward can show up across all three positions. List `b` contains three separate new lists.

This matters for `StringBuilder`, mutable entities, buffers, or stateful objects. `Stream.toList()` returns **a result list that does not support structural modifications**, but it does not make the element objects immutable. Collection immutability is **different** from element immutability.

A classic bug is a supplier returning the same object repeatedly and downstream code trying to use it as independent elements. The result may have overwritten data or unintended shared state. When separate instances are needed, ensure the supplier actually creates a new object.

## 9. Stateful suppliers, side effects, and parallel execution

### 9.1. A supplier with mutable state may work sequentially but is hard to maintain

A supplier like:

~~~java
Supplier<Integer> next = new Supplier<>() {
    int value = 0;

    @Override
    public Integer get() {
        return ++value;
    }
};
~~~

produces increasing numbers if called sequentially on the same thread. This is an illustrative snippet of a `Supplier<Integer>`, without `main`.

However, using it as a `generate(next)` source has several issues:

- Value ordering is hidden in the supplier's state, whereas a `generate` source is specified as **unordered**.
- If the same supplier is used across multiple streams or multiple threads, state can be shared and cause race conditions.
- If a pipeline has `filter`, `limit`, short-circuiting, or changes execution mode, the number of `get()` calls may not reflect the final element count.
- When you want "the next element depends on the previous element", `Stream.iterate` or `IntStream.range` usually communicates intent more clearly.

For parallel streams, you should not build logic that relies on receiving `1,2,3,...` in a specific order from a stateful supplier.

### 9.2. `parallel()` does not make every supplier automatically thread-safe

~~~java
// Syntax-only example; stateful suppliers are not recommended.
List<String> values = Stream.generate(() -> "stable")
        .parallel()
        .limit(5)
        .toList();
~~~

The constant supplier `() -> "stable"` has no mutable state; with this pipeline, the resulting list contains five `"stable"` strings. However, `generate` is an unordered source, and when run in parallel, **there is no guarantee on the order of callback invocations or which thread executes the callback**.

If a supplier writes to a shared `ArrayList`, increments an unsynchronized `int`, or uses a non-thread-safe object, switching to `parallel()` can cause data corruption. `AtomicInteger` makes incrementing a counter atomic, but it does **not** make the entire pipeline and all side effects execute in the expected order.

According to the Stream documentation, pipeline behavioral parameters should be **non-interfering**; in most cases they should also be stateless. If you need random numbers in complex or parallel streams, consider `ThreadLocalRandom.current()` in the appropriate scope and clarify ordering/reproducibility requirements instead of sharing an unsafe mutable generator instance.

### 9.3. Do not use a supplier for mandatory side effects

Streams are designed to process elements, not to guarantee that a source-generating callback runs an exact number of times like a transactional protocol. For example, if a supplier both generates an element and writes to a database, `limit`/`filter`/short-circuiting can make the number of side effects differ from expectations. Separate critical business behavior from the purpose of merely generating stream data, or design a dedicated, controlled lifecycle/task API.

**Rule:** a supplier should primarily **provide values**; avoid using it to drive business logic through side effects that depend on exact timing or invocation counts.

## 10. When is `Stream.generate()` **not** suitable?

### 10.1. Data already exists in a collection

~~~java
List<String> names = List.of("An", "Binh", "Chi");
List<String> upper = names.stream().map(String::toUpperCase).toList();
~~~

For an existing collection, `names.stream()` is the natural source. There is no need to use `Stream.generate` to read the list element by element and manage indices and stopping conditions manually.

### 10.2. Wanting to generate a finite, ordered number sequence

~~~java
List<Integer> ids = java.util.stream.IntStream.rangeClosed(1, 3)
        .boxed()
        .toList();
~~~

`IntStream.rangeClosed` expresses `1,2,3` directly and has an endpoint. `generate` is only appropriate if you truly need **a rule for supplying independent elements**.

### 10.3. Reading resources with a termination state

When reading data from a file, network, or database, the source usually has an **EOF/end-of-stream** point and a resource lifecycle. `Stream.generate` has no built-in termination signal in `Supplier<T>`; a supplier returning `null` to signal the end can introduce `null` as an actual element and cause downstream errors.

For text files, look at `Files.lines(Path)` and close the stream as documented, for example using `try-with-resources`. For sources with custom termination, consider `Stream.iterate(seed, hasNext, next)`, `Spliterator`, or a dedicated abstraction, depending on requirements. Do not use `generate` followed by `filter(Objects::nonNull)` to handle EOF: filtering out null **does not** make an infinite source stop on its own.

### 10.4. Wanting to handle checked I/O errors

`Supplier.get()` does not declare checked exceptions. A lambda reading a file that can throw `IOException` is not allowed to let that exception escape from a standard `Supplier<T>` without handling it. If I/O is needed, consider an API with a clear resource lifecycle and error contract rather than forcing everything into `generate`.

### 10.5. Wanting an exact invocation count in transactions

A stream pipeline can vary with `limit`, `filter`, short-circuiting, and execution mode. Do not use a supplier with side effects to replace a loop that needs an exact count of external reads/writes. For transactional work, a loop or dedicated API can be clearer and more controllable.

## 11. Common mistakes when using `Stream.generate()`

| Mistake | Consequence | Fix |
|---|---|---|
| Unbounded `Stream.generate(...).toList()` | May attempt to consume an infinite source | Add an appropriate stopping condition or choose a finite source |
| `filter` never lets elements through, followed by `limit(n)` | Pipeline never reaches `n` results and fails to terminate | If you want to limit attempts, put `limit` before `filter` |
| Expecting the supplier to run immediately when `generate` is called | Misunderstanding when data is created | Remember that a terminal operation triggers traversal |
| Assuming the supplier runs only once | Missing generated values or wrong repeated logic | Check the contract; `get()` can be called multiple times |
| Keeping unsynchronized mutable state in a supplier with `parallel()` | Race conditions, unstable results | Use a stateless/thread-safe source; avoid order dependence |
| Assuming `generate` has an encounter order | Wrong order assumptions in parallel execution | Use `iterate`/`range` if an ordered sequence is needed |
| Using `null` as an end-of-source signal | Null becomes an element; source does not stop | Use an API with an appropriate termination condition/spliterator |
| Reusing the same stream after a terminal operation | `IllegalStateException` or cannot be reused | Create a new stream for subsequent processing |
| Supplier returns the same mutable object repeatedly | Elements unintentionally share state | Create a new object or accept intentional sharing |
| Forgetting to close resources inside the supplier | Resource leaks or already-closed resources | Design lifecycle, try-with-resources, and dedicated APIs |

**Note on `null`:** `Stream.generate(() -> null)` can produce `null` elements in a reference `Stream<T>`; however, many downstream operations, such as a method reference to an instance method, can throw `NullPointerException`. `null` is not automatically interpreted as a stopping point. When the domain has an "end of data" state, model it explicitly.

## 12. Design checklist for an element-generating source

Before choosing `Stream.generate`, ask yourself:

1. Can the data source be described by a **parameterless Supplier**?
2. Are the elements **logically independent**, or do they actually depend on the order of previous elements?
3. Is there a guaranteed **finite stopping point**: `limit`, a short-circuiting terminal operation, or another API?
4. If `filter` is present, is `limit` bounding generation attempts or post-filter results?
5. Does the supplier return a **new object** or a **shared reference**? Is that what you intend?
6. Does the supplier have any mutable state or side effects that pose risks under parallel execution?
7. Does the source have resources that need **closing**, I/O errors, or an EOF signal?
8. Would another pipeline be more readable with `Stream.iterate`, `IntStream.range`, or `Collection.stream`?
9. Are tests bounded with a deterministic source and reproducible results?
10. Are you confusing "lazy generation" with caching or asynchrony?

If you still choose `generate`, keep the supplier **short, independent, and easy to test**, place limits or termination conditions in a visible spot, and use a sequential source when the problem requires predictable execution order.

## 13. Self-check questions

**Question 1.** Does `Stream.generate(() -> "x")` create infinite strings in memory immediately when called?

**Question 2.** When does `Supplier.get()` start being called in the pipeline `generate(s).limit(3).toList()`?

**Question 3.** Why does `Stream.generate(() -> 0).filter(x -> x > 0).limit(3).toList()` not terminate?

**Question 4.** Does swapping `filter` and `limit` change the stopping condition?

**Question 5.** Does `Stream.generate(StringBuilder::new).limit(3).toList()` return three new objects or three references pointing to the same object?

**Question 6.** Why shouldn't you rely on `generate` producing a fixed-order sequence in a parallel stream?

**Question 7.** For an ordered sequence 1..100, should you choose `generate`, `iterate`, or `IntStream.rangeClosed`?

**Question 8.** Can `null` returned by a supplier be used to automatically signal EOF?

**Question 9.** Does `Supplier` automatically cache values or run asynchronously?

**Short answers:**

1. No; the source is created lazily and does not allocate all elements upfront.
2. When a terminal operation consumes the pipeline; in the simple sequential example, three elements are requested.
3. `filter` discards every `0`, so the downstream `limit` never gets three elements.
4. Yes; `limit` before `filter` bounds the number of input attempts, whereas `limit` after `filter` bounds the number of elements passing the filter.
5. The constructor-reference supplier is invoked each time an element is needed, creating new objects.
6. Because a `generate` source is specified as unordered and parallel traversal does not promise supplier invocation order.
7. `IntStream.rangeClosed(1,100)` is clearest if you only need a finite `int` sequence.
8. No; `null` can be an element, not a termination signal for `generate`.
9. No; caching or async requires separate tools/mechanisms.

## 14. Official references

- [Java SE 17 API — Stream.generate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#generate(java.util.function.Supplier)): describes an infinite, sequential, unordered stream and the `Supplier` requirement.
- [Java SE 17 API — Supplier](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Supplier.html): SAM `T get()`.
- [Java SE 17 API — Stream.limit](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#limit(long)): limits the number of elements and notes on encounter order/parallel sources.
- [Java SE 17 API — Stream.iterate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#iterate(T,java.util.function.UnaryOperator)): ordered source where subsequent elements depend on previous ones.
- [Java SE 17 API — IntStream.rangeClosed](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/IntStream.html#rangeClosed(int,int)): creates a finite primitive `int` sequence with an explicit bound.

**Summary:** `Stream.generate(Supplier)` is a way to express an **on-demand element source**: each time an element is needed, the stream can call `get()`. It fits generating independent values, dummy data, or new objects, but the source is **infinite and unordered**, so you must pay attention to stopping conditions, `filter`/`limit`, side effects, and safety under parallel execution. When you need a finite or order-dependent sequence, prefer sources such as `Stream.iterate` or `IntStream.rangeClosed`.