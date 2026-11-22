# `Stream.map()` and One-to-One Transformations in Java

## 1. Goal: transforming each element of a Stream

When we have a dataset, we often want to create a new representation for **each element**: converting names to uppercase, getting string lengths, converting domain objects into DTOs, normalizing codes, or computing derived values. In the Java Stream API, the method that fits that model is **`map()`**.

~~~java
List<String> names = List.of("An", "Binh", "Chi");

List<Integer> lengths = names.stream()
        .map(String::length)
        .toList();

System.out.println(lengths); // [2, 4, 3]
~~~

Here `Stream<String>` is transformed into `Stream<Integer>` because each string is mapped to its own length. No element is actively removed or multiplied by **`map()` itself**.

The phrase **one-to-one** in this article has a practical meaning: each source element **actually processed** by `map` produces **one result element**. This is a property about the number of elements in a transformation step, not necessarily a one-to-one mapping in the mathematical *injective* sense (two different inputs can certainly produce the same output). For example, `"An"` and `"My"` both have length 2.

It is also worth noting that a Stream is a **lazy** pipeline: if there is no terminal operation yet, the mapper usually has not run; short-circuiting operations and certain optimizations may cause the callback to run on only part of the source or be omitted when the result is still valid according to the Stream contract. Therefore, do not use the number of mapper invocations as a counter with side effects.

## 2. API signature and how to read the types

On `java.util.stream.Stream<T>`, the core signature is:

~~~java
<R> Stream<R> map(Function<? super T, ? extends R> mapper);
~~~

Explanation:

- `T`: the element type before transformation, such as `String`.
- `R`: the element type after transformation, such as `Integer` or `UserDto`.
- `Function<? super T, ? extends R>`: a behavior that accepts a value compatible with `T` and returns a value compatible with `R`.
- `Stream<R>`: the new pipeline type returned. `map` is an **intermediate operation**, not yet a result like `List<R>` or `R[]`.
- The wildcard `? super T` allows the function to accept a broader input type than `T`; `? extends R` allows the result to be a subtype of `R`.

If using a lambda:

~~~java
Stream<Integer> lengths =
        Stream.of("Java", "API")
                .map(s -> s.length());
~~~

then `s -> s.length()` fulfills the role of `Function<String,Integer>`. If using a method reference:

~~~java
Stream<Integer> lengths =
        Stream.of("Java", "API")
                .map(String::length);
~~~

then `String::length` expresses the same mapping as the lambda above.

The `mapper` parameter must be a valid non-`null` function. `map(null)` does not create an "identity" transformation; it is invalid. To keep the input unchanged in an API that requires a mapper, you can use `Function.identity()` or `x -> x`.

### 2.1. `map` does not necessarily keep the same element type

~~~java
Stream<String> source = Stream.of("1", "20", "300");

Stream<Integer> parsed =
        source.map(Integer::parseInt);

List<Integer> result = parsed.toList();
System.out.println(result); // [1, 20, 300]
~~~

The input data consists of strings; the result is boxed `Integer` numbers. The `Integer.parseInt` method returns `int`, but Java can box it to `Integer` because `Stream.map` returns a reference stream.

If the goal is to work with primitive integers, you can switch to `IntStream` using `mapToInt`; see section 5.

## 3. Why is it called a one-to-one transformation?

Consider the example:

~~~java
List<String> source = List.of("a", "bb", "ccc");
List<Integer> mapped = source.stream()
        .map(String::length)
        .toList();

System.out.println(mapped); // [1, 2, 3]
~~~

The mapper itself chooses one result for each element:

~~~text
"a"   ── String::length ──> 1
"bb"  ── String::length ──> 2
"ccc" ── String::length ──> 3
~~~

If the pipeline traverses all three elements without encountering an error or an operation that changes the count, the result has three elements. `map` does not check for duplicate results and **does not** remove elements that are transformed into the same value.

~~~java
List<Integer> sameLengths = Stream.of("An", "My")
        .map(String::length)
        .toList();

System.out.println(sameLengths); // [2, 2]
~~~

Two different input elements produce two equal output elements. Therefore, **"one-to-one" here does not mean the results are always unique**. To remove duplicates, a separate operation such as `distinct()` with appropriate equality semantics is needed.

Similarly, if the mapping function returns `null`, `map` can produce **a null element**, rather than removing it automatically:

~~~java
List<String> mapped = Stream.of("A", "", "C")
        .map(s -> s.isEmpty() ? null : s)
        .toList();

System.out.println(mapped); // [A, null, C]
~~~

To remove nulls, add `filter(Objects::nonNull)` or design the callback to return an Optional and then flatten; see section 6.

## 4. Pipeline mechanics: `map` is lazy and does not mutate the source

`map` is an **intermediate, stateless, and non-interfering transformation when the API is used properly**. Whenever an element needs to pass through `map`, the mapper is used to produce the replacement value for subsequent stages of the pipeline.

~~~java
List<String> source = List.of(" java ", " stream ");
Stream<String> pipeline = source.stream()
        .map(String::trim)
        .map(String::toUpperCase);

// Mappers do not need to execute here yet.
List<String> result = pipeline.toList(); // Terminal operation.
System.out.println(result); // [JAVA, STREAM]
~~~

There are three things to separate:

1. **Creating the pipeline:** calls to `stream()` and `map(...)` describe the processing stages.
2. **Consuming the pipeline:** `toList()`, `collect(...)`, `forEach(...)`, `reduce(...)`, or another terminal operation requests the result to be computed.
3. **Final result:** may be a collection, a number, a single value, or an effect produced by the terminal operation.

A Java Stream **is not an independent data container** like a `List`. `source.stream().map(...)` also does not mean `source` has been modified. The source data remains its original values, unless the callback itself or external code mutates mutable state.

### 4.1. Order of transformations in a `map` chain

~~~java
List<String> output = Stream.of(" java ", " api ")
        .map(String::trim)
        .map(String::toUpperCase)
        .toList();

System.out.println(output); // [JAVA, API]
~~~

Each element goes through trimming and then uppercasing in the declared logical order. This corresponds to function composition:

~~~java
Function<String, String> normalize =
        ((Function<String, String>) String::trim)
                .andThen(String::toUpperCase);
~~~

For this example, `stream.map(normalize)` and `stream.map(String::trim).map(String::toUpperCase)` produce the same result for valid strings, provided they are applied to two equivalent Stream sources and have no interfering side effects.

### 4.2. Laziness does not guarantee the callback runs exactly as many times as source elements

~~~java
List<String> data = List.of("a", "b", "c");

long count = data.stream()
        .map(s -> {
            System.out.println("mapping " + s);
            return s.toUpperCase();
        })
        .count();
~~~

Do not treat the number of `mapping ...` lines as an API contract. When the source has a known size and the transformation does not change the element count, the implementation can compute `count()` **without running the mapper**. This is a valid Stream optimization. Even though `count` returns `3`, there is no guarantee the callback prints three times.

Similarly, `findFirst()`, `findAny()`, `anyMatch()`, `limit()`, and terminal operations that can short-circuit often do not need to traverse every element. With a parallel stream, the execution order of callbacks is also not a guaranteed observable order, even when the final result of an order-preserving operation is correct.

**Consequence:** a mapper should be **stateless**, not interfere with the source, and not rely on side effects to ensure program correctness. Operations that require side effects should have an explicit execution point, while still understanding the contract of the terminal operation.

## 5. `map` with objects and primitive streams

On `Stream<T>`, `map` returns `Stream<R>`. On primitive streams, the name `map` still exists, but with different signatures:

| Source | Mapper | Result |
| --- | --- | --- |
| `Stream<T>.map` | `Function<T,R>` | `Stream<R>` |
| `IntStream.map` | `IntUnaryOperator` | `IntStream` |
| `LongStream.map` | `LongUnaryOperator` | `LongStream` |
| `DoubleStream.map` | `DoubleUnaryOperator` | `DoubleStream` |
| `Stream<T>.mapToInt` | `ToIntFunction<T>` | `IntStream` |
| `Stream<T>.mapToLong` | `ToLongFunction<T>` | `LongStream` |
| `Stream<T>.mapToDouble` | `ToDoubleFunction<T>` | `DoubleStream` |
| `IntStream.mapToObj` | `IntFunction<R>` | `Stream<R>` |

Example when you already have a `Stream<String>`:

~~~java
List<String> labels = List.of("An", "Binh", "Chi");

int sum = labels.stream()
        .mapToInt(String::length)
        .sum();

System.out.println(sum); // 9
~~~

If you write `labels.stream().map(String::length)`, you get `Stream<Integer>`; it **does not have a direct `sum()` method**. `mapToInt` returns an `IntStream`, which provides specialized arithmetic terminal operations and avoids boxing intermediate values to `Integer`.

With `IntStream`:

~~~java
int sumOfSquares = IntStream.of(2, 3, 4)
        .map(n -> n * n)
        .sum();

List<String> labels = IntStream.of(2, 3, 4)
        .mapToObj(n -> "n=" + n)
        .toList();

System.out.println(sumOfSquares); // 29
System.out.println(labels);       // [n=2, n=3, n=4]
~~~

`IntStream.map` takes an `int` and returns an `int`; `mapToObj` creates objects, so the output type changes to `Stream<String>`.

Note that multiplication/summation on `int` can **overflow** according to Java integer rules. Choose `long` or check for overflow if the value range is large.

## 6. Distinguishing `map`, `filter`, and `flatMap`

These three methods are all intermediate operations, but they answer three different questions:

| Operation | Question | Effect on element count |
| --- | --- | --- |
| `map(f)` | "What value is each element transformed into?" | One output for each mapped element |
| `filter(p)` | "Which elements should be kept?" | Keeps 0 or 1 output for each element |
| `flatMap(f)` | "What sub-stream does each element produce?" | Each input can produce 0, 1, or more outputs |

### 6.1. `filter` keeps or drops data, `map` transforms data

~~~java
List<Integer> result = Stream.of("a", "bb", "ccc")
        .filter(s -> s.length() >= 2)
        .map(String::length)
        .toList();

System.out.println(result); // [2, 3]
~~~

`filter` drops the `"a"` element; `map` converts the remaining two strings into their lengths. The order matters if the transformation can affect the filter condition; place each operation according to the business requirement.

### 6.2. `map` produces nested streams, `flatMap` flattens them

~~~java
List<List<String>> groups = List.of(
        List.of("A", "B"),
        List.of("C"));

Stream<Stream<String>> nested = groups.stream()
        .map(List::stream);

List<String> flattened = groups.stream()
        .flatMap(List::stream)
        .toList();

System.out.println(flattened); // [A, B, C]
~~~

`map(List::stream)` produces **each element as a Stream<String>** (type `Stream<Stream<String>>`). `flatMap(List::stream)` concatenates the sub-streams into a single `Stream<String>`; therefore, a group of two elements can contribute two result elements. `map` does not flatten containers on its own.

### 6.3. With Optional: `map` keeps the Optional layer, `flatMap` can drop empty Optionals

Suppose we have the method:

~~~java
static Optional<Integer> parse(String text) {
    try {
        return Optional.of(Integer.parseInt(text));
    } catch (NumberFormatException ex) {
        return Optional.empty();
    }
}
~~~

When mapping:

~~~java
List<Optional<Integer>> parsed = Stream.of("10", "bad", "20")
        .map(MyParser::parse)
        .toList();
~~~

`map` produces one Optional for each element; an empty Optional is still **one output element**:

~~~text
[Optional[10], Optional.empty, Optional[20]]
~~~

If the goal is to keep only the successfully parsed numbers:

~~~java
List<Integer> numbers = Stream.of("10", "bad", "20")
        .map(MyParser::parse)
        .flatMap(Optional::stream)
        .toList();

System.out.println(numbers); // [10, 20]
~~~

`Optional.stream()` has 0 elements when empty or 1 element when a value is present. `flatMap(Optional::stream)` concatenates these streams and drops the empty branches. The difference in result count **comes from `flatMap`**, not from `map`.

In the small snippets here, `MyParser::parse` is a hypothetical name for the declared `static Optional<Integer> parse(String)` method; the standalone runnable program in section 10 uses the full class and method name.

### 6.4. `map` is not `forEach`

`map` returns a transformed pipeline for the next step; `forEach` is a **terminal operation** that accepts a `Consumer<T>` and returns `void`, typically used when you actually want to perform an action on elements.

~~~java
List<String> upper = Stream.of("a", "b")
        .map(String::toUpperCase)
        .toList();
~~~

The snippet above creates new values. By contrast:

~~~java
Stream.of("a", "b").forEach(System.out::println);
~~~

only consumes elements to print them, without returning a result list. With a parallel stream, `forEach` does not guarantee encounter order; if order is needed when consuming, see `forEachOrdered` and its cost.

## 7. Transforming entities into DTOs or presentation values

Applications often need to transform domain objects into data for display, reporting, or API responses. Using `map` helps separate the *data source* from the *conversion rules*.

~~~java
record User(String id, String name, int age) {}
record UserCard(String id, String label, boolean adult) {}

List<User> users = List.of(
        new User("u01", "An", 20),
        new User("u02", "Binh", 17));

List<UserCard> cards = users.stream()
        .map(u -> new UserCard(
                u.id(),
                u.name().toUpperCase(Locale.ROOT),
                u.age() >= 18))
        .toList();
~~~

Here each `User` produces one `UserCard`. There is no update to the original `User` objects; the lambda creates new objects. If you use `map(User::name)`, the output will be `Stream<String>`, whereas `map(u -> u)` returns the existing `User` instances themselves.

**Note on immutability:** `Stream.toList()` (Java 16+) creates an unmodifiable list; this does not mean every element object is immutable. If the mapper returns an existing mutable object, the new list can still hold a reference to that same object. If you need complete data isolation, you must construct copies according to your business requirements.

## 8. `null`, exceptions, and invalid data

### 8.1. A mapper can return null

~~~java
List<String> values = Stream.of("a", "", "b")
        .map(s -> s.isEmpty() ? null : s)
        .toList();

System.out.println(values); // [a, null, b]
~~~

`map` keeps **one output element** for the empty string: that is `null`. However, other terminal operations such as `Collectors.toUnmodifiableList()` do not accept null elements, so the null policy needs to match the terminal operation.

To drop null elements after transforming:

~~~java
List<String> values = Stream.of("a", "", "b")
        .map(s -> s.isEmpty() ? null : s)
        .filter(Objects::nonNull)
        .toList();

System.out.println(values); // [a, b]
~~~

This is a combination of `map` + `filter`; reducing the element count belongs to `filter`.

### 8.2. A mapper receiving a null input must still handle it itself

~~~java
List<String> source = Arrays.asList("a", null, "b");

List<String> safe = source.stream()
        .map(s -> s == null ? "" : s.toUpperCase(Locale.ROOT))
        .toList();

System.out.println(safe); // [A, , B]
~~~

`Stream.map` does not automatically check for or filter out `null` before calling the mapper. If you use `String::toUpperCase` directly on a null element, the callback will throw `NullPointerException`. Write a null-safe conversion function or add `filter(Objects::nonNull)` according to the desired handling policy.

### 8.3. When a callback throws an exception

~~~java
List<Integer> numbers = Stream.of("1", "bad", "3")
        .map(Integer::parseInt)
        .toList(); // NumberFormatException when encountering "bad".
~~~

With a sequential pipeline using `toList`, the error is thrown while the terminal operation executes; `map` does not catch the error or turn it into an empty Optional. If you need to continue processing valid records, convert each input into an `Optional<Integer>` or a result containing error information and then explicitly decide how to flatten/record errors. Do not arbitrarily catch every `RuntimeException` and ignore programming bugs.

### 8.4. Difference between `Stream.map` and `Optional.map`

`Optional<T>.map(Function<T,U>)` returns `Optional<U>`, and the mapper only runs if the Optional has a value. Meanwhile, `Stream<T>.map` returns `Stream<U>` and is an intermediate step of a Stream pipeline.

~~~java
Optional<String> maybeName = Optional.of("Java");
Optional<Integer> size = maybeName.map(String::length);

Stream<String> names = Stream.of("Java", "API");
Stream<Integer> sizes = names.map(String::length);
~~~

Both share the name `map`, but **the container before the dot is different**. Always check the signature and return type before using it.

## 9. Ordering, parallelism, and pure transformations

On a source with an encounter order, `map` is an operation that preserves the order relationship between input and output elements in the results of order-preserving terminal operations such as `toList()`. This remains true when the pipeline is processed in parallel, provided there is no operation that drops ordering or a terminal operation that discards order guarantees.

~~~java
List<Integer> squares = IntStream.rangeClosed(1, 4)
        .parallel()
        .map(n -> n * n)
        .boxed()
        .toList();

System.out.println(squares); // [1, 4, 9, 16]
~~~

Parallel execution does not guarantee **the execution order of callbacks**, but the `toList()` result here is constructed according to the encounter order of the ordered source.

Do not modify the source collection inside a mapper:

~~~java
List<String> source = new ArrayList<>(List.of("A", "B"));

// Avoid:
// source.stream().map(s -> {
//     source.add("C");  // Interferes with the source while the pipeline traverses it.
//     return s;
// }).toList();
~~~

The non-interference rule requires not modifying a non-concurrent source while the pipeline is executing. Mutating shared state across parallel callbacks can also cause data races or inconsistent results. Write pure mappers, such as `n -> n * n` or `String::trim`, and move side effects to an appropriate boundary.

In cases where you genuinely need side effects alongside new results, explicitly design a recording stage and a transformation stage, handle errors, and ensure thread-safety. `peek` can be used for observation/debugging, but should not be relied upon to guarantee side effects due to pipeline optimizations and short-circuiting.

## 10. Complete Java 17+ example

Save the file **`MapOneToOneDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Function;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class MapOneToOneDemo {
    record User(String id, String name, int age) {}
    record UserCard(String id, String label, boolean adult) {}

    static Optional<Integer> parseInteger(String text) {
        try {
            return Optional.of(Integer.parseInt(text));
        } catch (NumberFormatException ex) {
            return Optional.empty();
        }
    }

    public static void main(String[] args) {
        List<String> names = List.of("An", "Binh", "Chi");
        System.out.println("lengths=" + names.stream()
                .map(String::length).toList());
        System.out.println("lengthSum=" + names.stream()
                .mapToInt(String::length).sum());

        List<String> normalized = Stream.of(" java ", " api ")
                .map(String::trim)
                .map(s -> s.toUpperCase(Locale.ROOT))
                .toList();
        System.out.println("normalized=" + normalized);

        List<User> users = List.of(
                new User("u01", "An", 20),
                new User("u02", "Binh", 17));
        List<UserCard> cards = users.stream()
                .map(u -> new UserCard(
                        u.id(),
                        u.name().toUpperCase(Locale.ROOT),
                        u.age() >= 18))
                .toList();
        System.out.println("cards=" + cards);

        List<Optional<Integer>> wrapped = Stream.of("10", "bad", "-2")
                .map(MapOneToOneDemo::parseInteger)
                .toList();
        System.out.println("wrapped=" + wrapped);
        System.out.println("valid=" + Stream.of("10", "bad", "-2")
                .map(MapOneToOneDemo::parseInteger)
                .flatMap(Optional::stream)
                .toList());

        System.out.println("withNull=" + Stream.of("A", "", "C")
                .map(s -> s.isEmpty() ? null : s)
                .toList());
        System.out.println("nonNull=" + Stream.of("A", "", "C")
                .map(s -> s.isEmpty() ? null : s)
                .filter(Objects::nonNull)
                .toList());

        System.out.println("squares=" + IntStream.of(2, 3, 4)
                .map(n -> n * n)
                .boxed()
                .toList());

        AtomicInteger invoked = new AtomicInteger();
        Stream<String> lazy = Stream.of("a", "bb", "ccc")
                .map(s -> {
                    invoked.incrementAndGet();
                    return s.toUpperCase(Locale.ROOT);
                });
        System.out.println("before=" + invoked.get());
        System.out.println("lazyResult=" + lazy.toList());
        System.out.println("after=" + invoked.get());

        Function<String, Integer> length = String::length;
        System.out.println("composed=" + Stream.of("  xyz  ")
                .map(((Function<String, String>) String::trim)
                        .andThen(length))
                .toList());
    }
}
~~~

Compile and run:

~~~bash
javac MapOneToOneDemo.java
java MapOneToOneDemo
~~~

**Stdout:**

~~~text
lengths=[2, 4, 3]
lengthSum=9
normalized=[JAVA, API]
cards=[UserCard[id=u01, label=AN, adult=true], UserCard[id=u02, label=BINH, adult=false]]
wrapped=[Optional[10], Optional.empty, Optional[-2]]
valid=[10, -2]
withNull=[A, null, C]
nonNull=[A, C]
squares=[4, 9, 16]
before=0
lazyResult=[A, BB, CCC]
after=3
composed=[3]
~~~

**Reading the output along the data flow:**

- `String::length` converts `String` to `Integer`; `mapToInt` allows computing the sum directly with `IntStream.sum()`.
- Two consecutive `map` calls normalize strings with `trim` and then `toUpperCase(Locale.ROOT)`.
- The mapper creates one `UserCard` for each `User`, keeping the exact two corresponding elements.
- `parseInteger` creates an Optional for both valid and invalid data; `flatMap(Optional::stream)` is what drops empty Optionals.
- A mapper returning `null` still produces an element; `filter(Objects::nonNull)` removes that element.
- `IntStream.map` transforms `int` values without boxing before calling `boxed()`.
- With `lazy.toList()`, all three elements need to be mapped to build the result list; this example gives `before=0` and `after=3`. Do not generalize that **every** terminal operation always forces the mapper to run exactly three times.
- `Function.andThen` composes trimming followed by getting the length, yielding 3.

## 11. Design choices to keep in mind

### 11.1. Do you need to create a new object?

`map` **does not create copies on its own**. The mapper decides what to return:

~~~java
Stream<User> sameObjects = users.stream().map(u -> u);
Stream<String> names = users.stream().map(User::name);
Stream<UserCard> cards = users.stream()
        .map(u -> new UserCard(u.id(), u.name(), u.age() >= 18));
~~~

- `u -> u` keeps the exact same `User` reference.
- `User::name` returns the `String` property.
- `new UserCard(...)` creates a new object.

Do not confuse the `map` operation with copying a collection or deep-copying an object.

### 11.2. Can one element be transformed into a list?

Yes, because a list is also **one result object**:

~~~java
Stream<List<String>> nested = Stream.of("A,B", "C")
        .map(s -> List.of(s.split(",")));
~~~

The result has two elements of type `List<String>`, not three `String` elements. If you need the inner elements, use `flatMap`:

~~~java
List<String> flat = Stream.of("A,B", "C")
        .flatMap(s -> Arrays.stream(s.split(",")))
        .toList();

System.out.println(flat); // [A, B, C]
~~~

### 11.3. Is `map` required for every derived value?

No. If you only need sums, extrema, or primitive statistics, `mapToInt`/`mapToLong`/`mapToDouble` are usually clearer and avoid boxing. If the goal is only to select elements, `filter` is appropriate; if the goal is only to perform an action, consider the `forEach` terminal operation according to the specific requirement. If you need 0 or more elements per source element, `flatMap` is the natural choice.

### 11.4. Can a Stream be reused after `toList()`?

No. A Stream can only be consumed once:

~~~java
Stream<String> s = Stream.of("a", "b");
List<String> output = s.map(String::toUpperCase).toList();

// Do not reuse s for a new terminal.
~~~

If you need multiple independent results from the source data, create multiple new pipelines, or design an appropriate collector/aggregator to avoid unnecessary re-traversal.

## 12. Common mistakes

| Mistake | Consequence | How to handle |
| --- | --- | --- |
| Thinking `map` filters out elements when the mapper returns null | Produces null elements | Use `filter(Objects::nonNull)` or `flatMap` intentionally |
| Thinking `map` guarantees unique results | Results can be equal | `distinct` if deduplication is required |
| Calling `sum()` directly on `Stream<Integer>` | No such arithmetic method exists | Use `mapToInt` then `sum()` |
| Using `map` with a mapper returning Stream and expecting it to flatten | Produces `Stream<Stream<R>>` | Use `flatMap` |
| Using `map` with a mapper returning Optional and expecting it to drop empty | Produces `Stream<Optional<R>>` | Use `flatMap(Optional::stream)` |
| Assuming map mutates the source collection | The pipeline produces values that flow forward | Only mutate data if an explicit mutation operation is intended, and avoid interfering with the source |
| Relying on `map` to reliably increment a counter/log | The callback may not run due to optimization or short-circuiting | Do not put mandatory side effects in a mapper |
| Reusing a Stream that has already executed a terminal operation | `IllegalStateException` typically occurs | Create a new stream from the source |
| Calling a method reference on a null element | May throw `NullPointerException` | Check/filter/handle null according to the contract |
| Assuming `parallel().map` runs callbacks in order | Execution order is not guaranteed | Rely on a terminal result with an ordering contract, avoid side effects |
| Calling `map` with a `null` mapper | Invalid mapper | Provide an appropriate function, `Function.identity()` if you want to keep it unchanged |

## 13. Self-check exercises

**Question 1.** For `List.of("a", "bb", "cc")`, what is the result of `stream().map(String::length).toList()`? Does it remove elements with duplicate lengths?

Answer: `[1, 2, 2]`. No. `map` does not remove duplicates on its own.

**Question 2.** Does `Stream.of("A", "", "B").map(s -> s.isEmpty() ? null : s).count()` equal 2?

Answer: It equals **3**. `map` still has three outputs semantically, including null; `count()` can be computed based on the source size without running the mapper. To remove null elements, use an appropriate `filter`/`flatMap`.

**Question 3.** `List<String> names` has three elements. To get the total length, should you use `map` or `mapToInt`?

Answer: `names.stream().mapToInt(String::length).sum()` is the direct way because `IntStream` has the `sum()` terminal operation.

**Question 4.** For `List<List<String>> groups`, what type does `groups.stream().map(List::stream)` return?

Answer: `Stream<Stream<String>>`. Use `flatMap(List::stream)` if you want `Stream<String>`.

**Question 5.** Why shouldn't you use side effects in a `map` lambda to reliably count the number of source elements?

Answer: Pipelines are lazy, have short-circuiting, and have optimizations like `count()` on sized sources. Java does not promise that the callback will run for all elements just because `map` appears in the pipeline.

**Question 6.** When transforming `User` into `UserCard` via `map`, is the source `List<User>` changed into `List<UserCard>`?

Answer: No. `map` creates a result pipeline of type `Stream<UserCard>`, and then a terminal operation like `toList()` creates a separate result list. The source collection keeps its structure if there are no other mutation statements.

**Question 7.** An `Optional<Integer>` is created from each string using `map`. What should you do to drop empty Optionals?

Answer: After `map(parser)`, call `flatMap(Optional::stream)`; each Optional with a value contributes one element, while an empty Optional contributes zero elements.

## 14. Key takeaways

`Stream.map(Function<? super T, ? extends R>)` is an intermediate operation that **transforms each element from `T` to `R`**. Every element actually processed by the mapper produces one result, even if that may be a duplicate value, `null`, or another container. `map` **does not actively filter, flatten, deduplicate, or copy data**.

Distinguish the goals:

- **`map`:** transforms each value into a new value.
- **`filter`:** keeps or drops values based on a condition.
- **`flatMap`:** concatenates sources of 0 or more values into a flat stream.
- **`mapToInt`/`mapToLong`/`mapToDouble`:** transforms directly into a primitive stream for numeric operations.
- **Terminal operation:** triggers processing and obtains the result, with potential short-circuiting/optimization depending on the contract.

Choose readable mappers, prefer stateless and non-interfering behavior, pay attention to the exact types at each stage, and do not rely on how many times a callback runs when designing important side effects.
