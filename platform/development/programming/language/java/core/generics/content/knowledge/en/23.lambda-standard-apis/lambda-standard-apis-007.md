# Reading map, flatMap, and collect Signatures in Java Generics Streams

## 1. Why learn to read generic signatures instead of just memorizing examples?

`java.util.stream.Stream<T>` describes a pipeline processing elements of type **T**. Three API groups frequently appear together:

- **`map`**: turns each T into one R; produces a **Stream<R>**.
- **`flatMap`**: turns each T into a **sub-Stream**, then concatenates the sub-streams into one **Stream<R>**.
- **`collect`**: a **terminal operation** that gathers current stream elements into a result R via a Collector or three build/merge behaviors.

The tricky part lies in type parameters `T`, `R`, `A` along with wildcard bounds `? super` and `? extends`. Once you know how to read them, you can see why a pipeline compiles or fails, how the compiler infers types at each step, and why `map` is not equivalent to `flatMap`.

A typical pipeline:

~~~java
List<String> names = orders.stream()
        .filter(order -> order.total() > 0)
        .map(Order::customer)
        .collect(Collectors.toList());
~~~

This is an **illustrative snippet** assuming record `Order` and variable `orders` are defined; the complete program appears in section 9. The data flow type transforms at each step:

~~~text
List<Order>
    .stream()                  Stream<Order>
    .filter(Predicate<Order>)  Stream<Order>
    .map(Function<Order,String>)
                               Stream<String>
    .collect(Collector<String,?,List<String>>)
                               List<String>
~~~

`map` and `flatMap` are **intermediate operations**, typically lazy; `collect` is a **terminal operation**, requiring the pipeline to produce a result. A stream that has executed a terminal operation cannot be reused as a fresh stream.

## 2. Reading the actual Java 17 signatures accurately

Abridged from `java.util.stream.Stream<T>`:

~~~java
<R> Stream<R> map(
        Function<? super T, ? extends R> mapper);

<R> Stream<R> flatMap(
        Function<? super T, ? extends Stream<? extends R>> mapper);

<R, A> R collect(
        Collector<? super T, A, R> collector);

<R> R collect(
        Supplier<R> supplier,
        BiConsumer<R, ? super T> accumulator,
        BiConsumer<R, R> combiner);
~~~

The signatures above omit `public abstract` and enclosing declaration details for readability; they are not a standalone Java class to copy and run. These are **two distinct overloads** of `collect`, sharing the name while taking different kinds of arguments.

Symbol decoder table:

| Symbol | Role | Example |
| --- | --- | --- |
| `T` | Current element type of `Stream<T>` | `Order` for `Stream<Order>` |
| `R` in `map/flatMap` | Element type of the transformed stream | `String` in `Stream<String>` |
| `R` in `collect` | Type of the **final result** | `List<String>`, `Map<String,Integer>` |
| `A` | **Intermediate** accumulation type inside Collector | A mutable container, possibly different from R |
| `Function<? super T, ? extends R>` | Mapper accepting T and producing an R-compatible value | `Order::customer` |
| `Stream<? extends R>` | A sub-stream whose elements are R or a subtype of R | `List<Integer>.stream()` when R fits |
| `Collector<? super T,A,R>` | Collector consuming T values and producing R | `Collectors.toList()` |
| `Supplier<R>`, `BiConsumer<...>` | Three behaviors for allocating, accumulating, and combining results | `ArrayList::new`, `List::add`, `List::addAll` |

`<R>` placed **before the return type** declares the type parameter of the generic method itself. It does not mean the method returns an object whose class is literally named R. The compiler infers R from target context, mapper type, and generic constraints.

## 3. Wildcard rule: ? super on input, ? extends on output

In the `Stream<T>.map` signature:

~~~java
<R> Stream<R> map(Function<? super T, ? extends R> mapper);
~~~

`? super T` lets the mapper **accept** `T` values via a supertype, while `? extends R` lets the mapper **return** a result of an appropriate subtype of `R`. This is PECS for callback input/output direction; it **does not** mean `Stream<Integer>` is a subtype of `Stream<Number>`.

Example with necessary imports in context:

~~~java
Stream<Integer> integers = Stream.of(1, 2, 3);
Function<Number, String> asText = Object::toString;
List<String> result = integers.map(asText).toList();
~~~

A Function accepting `Number` can still process each `Integer`. As you continue reading `flatMap` and `collect`, keep this same direction in mind while **additionally distinguishing** a mapper returning `Stream<? extends R>` and a collector whose accumulation type `A` differs from its final return type `R`. That is the specific focus of this Stream lesson, rather than just repeating the general wildcard rule.

## 4. map: one input element produces one output element

Signature:

~~~java
<R> Stream<R> map(Function<? super T, ? extends R> mapper);
~~~

For each element T that the pipeline processes, the mapper produces one result element of type R. Those elements form a `Stream<R>`.

Example:

~~~java
List<String> languages = List.of("Java", "Go", "Kotlin");

List<Integer> lengths = languages.stream()
        .map(String::length)
        .toList();
~~~

Result:

~~~text
[4, 2, 6]
~~~

Type analysis:

~~~text
Stream<String>
    map(String::length)           Function<String,Integer>
                                   (int is boxed to Integer)
    ↓
Stream<Integer>
    toList()
    ↓
List<Integer>
~~~

`map` preserves the relationship that **each source element is transformed by applying the mapper once when that element is processed**; however, do not conclude that the mapper is always invoked for every source element in every complex pipeline. Streams may short-circuit or optimize certain operations per API semantics.

### 4.1. map when the mapper returns a collection

Suppose each order holds a list of prices:

~~~java
record Order(String customer, List<Integer> prices) {}

List<Order> orders = List.of(
        new Order("Lan", List.of(20, 30)),
        new Order("An", List.of(10))
);

List<List<Integer>> nested = orders.stream()
        .map(Order::prices)
        .toList();
~~~

Result:

~~~text
[[20, 30], [10]]
~~~

The input is `Stream<Order>`. `Order::prices` returns `List<Integer>`, so `R = List<Integer>`; after map, we have `Stream<List<Integer>>`, **not Stream<Integer>**.

This is the key point: **map does not automatically flatten a collection or stream returned by the mapper**. If the mapper returns a List, each result element of the Stream remains **a List**.

### 4.2. map and mapToInt

If the mapper returns a primitive integer value, `map` typically yields `Stream<Integer>` because generic type arguments cannot be primitive int:

~~~java
Stream<Integer> boxed = Stream.of("A", "BB")
        .map(String::length);
~~~

Whereas:

~~~java
IntStream lengths = Stream.of("A", "BB")
        .mapToInt(String::length);

int sum = lengths.sum(); // 3
~~~

`mapToInt(ToIntFunction<? super T>)` returns `IntStream`, a specialized primitive stream. Do not use `map(String::length)` and expect to call every primitive API directly as on IntStream.

## 5. flatMap: each T produces a sub-stream, then flattens one level

Signature:

~~~java
<R> Stream<R> flatMap(
        Function<? super T, ? extends Stream<? extends R>> mapper);
~~~

Unlike map, flatMap's mapper must return a **Stream** (or appropriate subtype), not a single R.

Example:

~~~java
List<List<Integer>> batches = List.of(
        List.of(1, 2),
        List.of(3),
        List.of(4, 5)
);

List<Integer> numbers = batches.stream()
        .flatMap(List::stream)
        .toList();
~~~

Result:

~~~text
[1, 2, 3, 4, 5]
~~~

Types at each step:

~~~text
Stream<List<Integer>>
    flatMap(List::stream)
        List<Integer> → Stream<Integer>
    ↓
Stream<Integer>
    toList()
    ↓
List<Integer>
~~~

`flatMap` can produce **0, 1, or many output elements per input element**, depending on the sub-stream. This makes it useful when processing multiple lists, word tokens, child records, or search results containing multiple items.

### 5.1. Not infinite recursive flattening

If the input is `Stream<List<List<String>>>`, calling `flatMap(List::stream)` once produces `Stream<List<String>>`. To get `Stream<String>`, you need to flatten one more level:

~~~java
List<List<List<String>>> levels = List.of(
        List.of(List.of("A", "B")),
        List.of(List.of("C"))
);

List<String> words = levels.stream()
        .flatMap(List::stream)
        .flatMap(List::stream)
        .toList();
~~~

Result `[A, B, C]`. Two flatMap calls handle two levels of nesting; there is no automatic rule that “flattens arbitrarily many layers”.

### 5.2. flatMap can drop elements with Stream.empty()

~~~java
List<String> source = List.of("A", "", "B");

List<String> nonBlank = source.stream()
        .flatMap(s -> s.isBlank()
                ? Stream.empty()
                : Stream.of(s))
        .toList();
~~~

Result `[A, B]`. For each blank string, the mapper returns an empty stream and produces no output element. If the task is purely filtering, `filter` is usually clearer; this example illustrates flatMap's ability to produce **0 elements** from an input.

### 5.3. Why not return a List directly?

Wrong type:

~~~java
// orders.stream().flatMap(Order::prices);
// Does not compile: Order::prices returns List<Integer>, not Stream<Integer>.
~~~

Fix:

~~~java
orders.stream().flatMap(order -> order.prices().stream());
~~~

`List.stream()` creates Stream<Integer>, satisfying the Function signature taking Order and returning Stream<? extends R>.

### 5.4. How does flatMap handle sub-streams?

When a mapped stream is used in flatMap, Java processes the sub-stream's elements and **closes the sub-stream after use** per the API contract. If a mapper returns a null stream, Stream.flatMap's contract treats it as an empty stream; however, in application code, returning `Stream.empty()` explicitly makes intent clearer and avoids relying on null.

A stream cannot be reused after a terminal operation; likewise, do not reuse an already-consumed sub-stream to map another element. For data from a collection, calling a fresh `list.stream()` each time is natural.

## 6. Comparison table of map and flatMap by types

| Input | Mapper | API | After transformation |
| --- | --- | --- | --- |
| `Stream<String>` | `String::length` returns int/Integer | `map` | `Stream<Integer>` |
| `Stream<Order>` | `Order::customer` returns String | `map` | `Stream<String>` |
| `Stream<Order>` | `Order::prices` returns List<Integer> | `map` | `Stream<List<Integer>>` |
| `Stream<Order>` | `o -> o.prices().stream()` returns Stream<Integer> | `flatMap` | `Stream<Integer>` |
| `Stream<List<String>>` | `List::stream` returns Stream<String> | `flatMap` | `Stream<String>` |
| `Stream<String>` | `s -> Stream.of(s, s)` | `flatMap` | `Stream<String>` with two results per input |

Diagnostic question before choosing an API: “Does my mapper return **one R** or **a Stream<R>**?” If it returns one result, use map; if it returns a sub-stream and you want to merge their elements, use flatMap.

A method returning Optional can also supply a sub-stream via `Optional.stream()` (Java 9+):

~~~java
List<String> present = Stream.of(
        Optional.of("A"),
        Optional.<String>empty(),
        Optional.of("B"))
        .flatMap(Optional::stream)
        .toList(); // [A, B]
~~~

This flattens Stream<Optional<String>> into Stream<String>, discarding empty Optionals.

## 7. collect is a terminal operation and differs from map/flatMap

`map` and `flatMap` only transform one `Stream<T>` into another stream; they do not gather elements into a list or map by themselves.

`collect` is a **terminal reduction**: it uses the stream's elements to build a result. There are **two main overloads** in `Stream<T>`:

~~~java
<R, A> R collect(Collector<? super T, A, R> collector);

<R> R collect(
        Supplier<R> supplier,
        BiConsumer<R, ? super T> accumulator,
        BiConsumer<R, R> combiner);
~~~

In the first overload, a **Collector** encapsulates accumulation, combination, finalization, and characteristics logic. The second overload directly takes **three behaviors** for creating and merging a mutable result.

A commonly misread point: **R of collect does not have to be the input element type**. From `Stream<Order>`, a collector can produce:
- `List<Order>`;
- `Map<String,List<Order>>`;
- `Map<String,Integer>`;
- `Long`;
- `String`;
- an application-specific result type.

Track **the T of the current stream** and **the R produced by the Collector** rather than assuming R is always List<T>.

## 8. collect(Collector<? super T,A,R>): meaning of the three type parameters

Signature:

~~~java
<R, A> R collect(Collector<? super T, A, R> collector);
~~~

Breakdown:

- `T`: the element currently processed in the stream.
- `? super T`: the collector can consume T **or a supertype of T**.
- `A`: the **intermediate accumulation container** type (*mutable accumulation type*) managed by the Collector. Callers often do not need to know it, and APIs can express it with `?`.
- `R`: the **final result** type returned by `collect`.

Example:

~~~java
List<String> names = Stream.of("Java", "Go")
        .collect(Collectors.toList());
~~~

`Collectors.toList()` has the abridged signature:

~~~java
<T> Collector<T, ?, List<T>> toList();
~~~

The `?` in position A means the implementation hides the concrete accumulator type; it does not mean Java knows nothing about the data. The result R is `List<T>`, which in this example is `List<String>`.

### 8.1. A can differ from R

For a collector with a *finisher* step, the internal accumulation container and the public result can have different types. Never claim `Collector<T,A,R>` always requires `A=R`.

A collector can use a mutable builder like `StringBuilder` to accumulate and then return a `String` upon finishing. A Collector's mechanism comprises:
- supplier: creates A;
- accumulator: takes A and T to accumulate;
- combiner: merges two A's;
- finisher: transforms A into R;
- characteristics: describes properties enabling optimizations or parallel execution per contract.

`Collectors.joining()` is an easy-to-picture example: it gathers CharSequences to produce a String result without making the caller manage a builder.

### 8.2. Why does a collector take ? super T?

Like `map`, a collector can consume a supertype of the stream element type. Writing `Collector<? super T,A,R>` avoids forcing every collector to declare the exact T. This is another manifestation of **consumer super**.

Do not infer that the wildcard `?` in `Collector<T,?,List<T>>` means “the output List holds Object”. That question mark sits in **A — the internal accumulator**, while the resulting List still preserves T.

## 9. Complete Java 17+ program demonstrating map, flatMap, and collect

Save the file **StreamSignaturesDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.function.Function;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class StreamSignaturesDemo {
    record Order(String customer, List<Integer> prices) {
        int total() {
            return prices.stream()
                    .mapToInt(Integer::intValue)
                    .sum();
        }
    }

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("Lan", List.of(20, 30)),
                new Order("An", List.of(10)),
                new Order("Lan", List.of(5, 15))
        );

        List<String> labels = orders.stream()
                .map(o -> o.customer() + ":" + o.prices().size())
                .toList();
        System.out.println("map=" + labels);

        List<List<Integer>> nested = orders.stream()
                .map(Order::prices)
                .toList();
        System.out.println("nested=" + nested);

        List<Integer> flattened = orders.stream()
                .flatMap(o -> o.prices().stream())
                .toList();
        System.out.println("flatMap=" + flattened);

        // The collect(supplier, accumulator, combiner) overload.
        List<String> threeArg = orders.stream()
                .map(Order::customer)
                .collect(ArrayList::new, List::add, List::addAll);
        System.out.println("collect3=" + threeArg);

        // Collector mapping: transforms Order into Integer inside collect.
        List<Integer> totals = orders.stream()
                .collect(Collectors.mapping(
                        Order::total, Collectors.toList()
                ));
        System.out.println("mapping=" + totals);

        // Collector flatMapping: flattens elements before downstream.
        List<Integer> withFlatMapping = orders.stream()
                .collect(Collectors.flatMapping(
                        o -> o.prices().stream(),
                        Collectors.toList()
                ));
        System.out.println("flatMapping=" + withFlatMapping);

        // TreeMap so key order in output is deterministic.
        Map<String, Integer> grouped = orders.stream()
                .collect(Collectors.groupingBy(
                        Order::customer,
                        TreeMap::new,
                        Collectors.summingInt(Order::total)
                ));
        System.out.println("grouped=" + grouped);

        Map<String, Integer> merged = orders.stream()
                .collect(Collectors.toMap(
                        Order::customer,
                        Order::total,
                        Integer::sum,
                        TreeMap::new
                ));
        System.out.println("toMap=" + merged);

        try {
            // Duplicate key "Lan" without providing a merge function.
            orders.stream().collect(Collectors.toMap(
                    Order::customer, Order::total
            ));
        } catch (IllegalStateException error) {
            System.out.println("duplicate=IllegalStateException");
        }

        Function<CharSequence, String> trim =
                s -> s.toString().trim();

        List<String> cleaned = Stream.of(" Lan ", " An ")
                .map(trim)
                .toList();
        System.out.println("wildcard=" + cleaned);

        try {
            labels.add("new");
        } catch (UnsupportedOperationException error) {
            System.out.println("toList=unmodifiable");
        }
    }
}
~~~

Compile with a JDK supporting Java 17:

~~~bash
javac --release 17 -Xlint:all StreamSignaturesDemo.java
java StreamSignaturesDemo
~~~

**Verified stdout:**

~~~text
map=[Lan:2, An:1, Lan:2]
nested=[[20, 30], [10], [5, 15]]
flatMap=[20, 30, 10, 5, 15]
collect3=[Lan, An, Lan]
mapping=[50, 10, 20]
flatMapping=[20, 30, 10, 5, 15]
grouped={An=10, Lan=70}
toMap={An=10, Lan=70}
duplicate=IllegalStateException
wildcard=[Lan, An]
toList=unmodifiable
~~~

### 9.1. Type analysis of each output line

`map=[Lan:2, An:1, Lan:2]`: turns `Order` into `String`; element count stays the same here.

`nested=[[20, 30], [10], [5, 15]]`: `Order::prices` returns `List<Integer>`, so `map` gives `Stream<List<Integer>>`, collected into `List<List<Integer>>`.

`flatMap=[20, 30, 10, 5, 15]`: mapper `o -> o.prices().stream()` returns `Stream<Integer>`, so `flatMap` concatenates the sub-streams into `Stream<Integer>`.

`collect3=[Lan, An, Lan]`: after `map(Order::customer)`, the current stream holds String; the three-argument overload creates ArrayList<String>, adds each String, and combines containers when needed.

`mapping=[50, 10, 20]`: each Order is transformed into an Integer total via `Order::total` inside `Collectors.mapping`, then downstream `toList` gathers the results.

`flatMapping=[20, 30, 10, 5, 15]`: `Collectors.flatMapping` uses each order's sub-stream as a data-preparation step before the downstream collector.

`grouped={An=10, Lan=70}`: `groupingBy` groups by customer, `summingInt` sums totals of orders with the same key, and TreeMap orders keys naturally.

`toMap={An=10, Lan=70}`: `toMap` uses customer as key, total as value, and `Integer::sum` merges values on duplicate keys; TreeMap maintains deterministic key order.

`duplicate=IllegalStateException`: the two-mapper `toMap` overload has no merge function supplied, so repeated key "Lan" triggers an exception during collection.

`wildcard=[Lan, An]`: `Function<CharSequence,String>` can serve as mapper for `Stream<String>` thanks to `? super T` in map's signature.

`toList=unmodifiable`: `Stream.toList()` (since Java 16) returns an unmodifiable list; calling add throws UnsupportedOperationException.

## 10. The collect(supplier, accumulator, combiner) overload

Signature:

~~~java
<R> R collect(
        Supplier<R> supplier,
        BiConsumer<R, ? super T> accumulator,
        BiConsumer<R, R> combiner);
~~~

In this overload **there is no separate A**: the accumulation container type is declared as R itself, which is also the return type.

Reading each component:
- `supplier`: creates a **new R container** to accumulate into.
- `accumulator`: takes an R container and a T element; mutates the container to add data.
- `combiner`: merges two R containers; especially important when the engine merges results from branches of a parallel stream.

Example:

~~~java
List<String> output = Stream.of("A", "B", "C")
        .collect(
                ArrayList::new,
                List::add,
                List::addAll
        );
~~~

Inferred types:
- Input `Stream<String>`: T = String.
- `ArrayList::new` allocates an ArrayList<String> viewable as List<String>.
- `List::add` accepts container List<String> and element String (the boolean return value is ignored when used as BiConsumer).
- `List::addAll` combines two List<String> instances, adding elements of the second container into the first.
- Result R = `List<String>`.

**Correctness requirement:** the combiner must merge properly, and supplier/accumulator/combiner must obey mutable reduction constraints. If the combiner simply ignores the second container, results may look right sequentially yet lose elements when run in parallel.

### 10.1. Why not just use a global ArrayList?

Common mistake:

~~~java
List<String> shared = new ArrayList<>();
// stream.parallel().forEach(shared::add); // Unsafe.
~~~

`ArrayList` is not thread-safe for concurrent unsynchronized mutations via `forEach`. In the three-argument collect overload, the framework can create separate containers via supplier and merge them using combiner; this reduction mechanism is designed for parallel execution when identity and associativity constraints hold.

Do not pass a supplier that always returns the same global mutable list, as that defeats independent accumulation containers.

### 10.2. Why isn't combiner used to turn T into R?

In the signature, `BiConsumer<R,R> combiner` takes **two R containers**, not an element T. Processing each T belongs to `BiConsumer<R,? super T> accumulator`. If you need to transform T into R per element, use map beforehand or handle it cleanly inside the accumulator.

## 11. Collectors.toList and Stream.toList differ

Two ways to collect into a list:

~~~java
List<String> a = Stream.of("A", "B")
        .collect(Collectors.toList());

List<String> b = Stream.of("A", "B")
        .toList();
~~~

They share the same **result type** `List<String>` and elements on a stream with matching encounter order, yet do not share every API guarantee.

- `Stream.toList()` was added in Java 16; it returns an **unmodifiable List**. Attempting to add, remove, or replace elements throws UnsupportedOperationException.
- `Collectors.toList()` gives no guarantees on the implementation type, mutability, serializability, or thread safety of the returned List. Some JDKs may return a mutable ArrayList, but **this must not be treated as a standard contract**.
- `Collectors.toCollection(ArrayList::new)` is used when you need a specific collection such as an ArrayList created by the given factory.
- `Collectors.toUnmodifiableList()` provides an unmodifiable List via a collector; by contract it rejects null elements.

Example:

~~~java
List<String> mutable = Stream.of("A", "B")
        .collect(Collectors.toCollection(ArrayList::new));

mutable.add("C"); // Valid with ArrayList.
~~~

Do not pick `Collectors.toList()` just because you want to mutate the result if your code genuinely requires a mutable ArrayList; express that requirement explicitly with `toCollection`.

## 12. groupingBy: reading classifier, mapFactory, and downstream

The basic overload of `Collectors.groupingBy` can be described as:

~~~java
<T, K> Collector<T, ?, Map<K, List<T>>> groupingBy(
        Function<? super T, ? extends K> classifier);
~~~

It groups T elements by **key K** produced by the classifier, and returns Map<K,List<T>>.

Example:

~~~java
Map<Integer, List<String>> byLength = Stream.of("A", "BB", "C")
        .collect(Collectors.groupingBy(String::length));
~~~

Types:
- T = String.
- K = Integer.
- classifier: String → Integer.
- R = Map<Integer,List<String>>.

If you need a downstream result other than List<T>, use the overload taking a Collector:

~~~java
<T, K, A, D> Collector<T, ?, Map<K, D>> groupingBy(
        Function<? super T, ? extends K> classifier,
        Collector<? super T, A, D> downstream);
~~~

Here `D` is the result for **each group**, which can be Long, Integer, Set<String>, or another structure. Hence the overall result is `Map<K,D>`.

Example counting each group:

~~~java
Map<Integer, Long> counts = Stream.of("A", "BB", "C")
        .collect(Collectors.groupingBy(
                String::length,
                Collectors.counting()
        ));
~~~

Result contents: key 1 has count 2, key 2 has count 1. Do not rely on HashMap iteration order in this example.

The full program uses the three-argument overload:

~~~java
Collectors.groupingBy(
        Order::customer,
        TreeMap::new,
        Collectors.summingInt(Order::total)
)
~~~

Meaning:
- classifier extracts customer:String → K = String;
- mapFactory creates TreeMap<String,Integer>;
- downstream sums total for each group → D = Integer;
- result `Map<String,Integer>` prints deterministically by TreeMap key order.

A very common misunderstanding: `groupingBy(classifier, downstream)` does not expect the downstream to receive **an already-grouped List<T>**; the downstream collector accumulates the T elements belonging to each group.

## 13. Collectors.mapping and Collectors.flatMapping are not Stream.map/flatMap

Two different APIs:

~~~java
orders.stream()
      .map(Order::total)
      .collect(Collectors.toList());
~~~

and:

~~~java
orders.stream()
      .collect(Collectors.mapping(
              Order::total,
              Collectors.toList()
      ));
~~~

can both produce the list of totals for each order. However:
- `Stream.map` transforms an **intermediate stream** from Stream<Order> into Stream<Integer>.
- `Collectors.mapping` is an **adapter collector**: it transforms each Order element into Integer as the downstream collector receives data.

An abridged signature:

~~~java
<T, U, A, R> Collector<T, ?, R> mapping(
        Function<? super T, ? extends U> mapper,
        Collector<? super U, A, R> downstream);
~~~

Mapper takes T and produces U; downstream collects U to return R.

Similarly:

~~~java
<T, U, A, R> Collector<T, ?, R> flatMapping(
        Function<? super T, ? extends Stream<? extends U>> mapper,
        Collector<? super U, A, R> downstream);
~~~

`Collectors.flatMapping` flattens sub-streams **right inside the collect phase**, useful as a downstream collector of groupingBy or partitioningBy.

For example, to get the set of integers in each customer group:

~~~java
Map<String, Set<Integer>> valuesByCustomer = orders.stream()
        .collect(Collectors.groupingBy(
                Order::customer,
                Collectors.flatMapping(
                        o -> o.prices().stream(),
                        Collectors.toSet()
                )
        ));
~~~

This snippet assumes importing `java.util.Set` and the `Order` type from the full program. Each customer group receives Orders, flatMapping produces Integers from price lists, and downstream `toSet` collects the Integers without creating an intermediate flattened stream and then trying to reconstruct customer associations.

**Note:** these are two different API levels; do not try calling `.flatMap(Collectors.flatMapping(...))` because `Stream.flatMap` expects a Function returning a Stream, whereas `Collectors.flatMapping` returns a Collector.

## 14. Collectors.toMap: two mappers and the duplicate-key problem

Basic overload:

~~~java
<T, K, U> Collector<T, ?, Map<K, U>> toMap(
        Function<? super T, ? extends K> keyMapper,
        Function<? super T, ? extends U> valueMapper);
~~~

That is, for each element T:
- keyMapper produces K;
- valueMapper produces U;
- the result is collected into Map<K,U>.

Example:

~~~java
Map<String, Integer> values = Stream.of("A", "BB")
        .collect(Collectors.toMap(
                word -> word,
                String::length
        ));
~~~

Input `Stream<String>`, key String, value Integer. However, if **two elements produce the same key**, this overload throws IllegalStateException.

In section 9's program, customer "Lan" appears twice. Therefore:

~~~java
orders.stream().collect(Collectors.toMap(
        Order::customer, Order::total
));
~~~

throws IllegalStateException due to the duplicate key.

To specify how values merge on duplicate keys:

~~~java
Map<String, Integer> merged = orders.stream()
        .collect(Collectors.toMap(
                Order::customer,
                Order::total,
                Integer::sum,
                TreeMap::new
        ));
~~~

In this overload:
- `BinaryOperator<U> mergeFunction` combines **two U values** for the same key, not two Order objects.
- `Supplier<M> mapFactory` chooses the Map type to create; TreeMap provides deterministic key order.
- The result has `Lan = 50 + 20 = 70`, `An = 10`.

For large data and parallel streams, the merge function should satisfy associativity requirements and avoid side effects that cause inconsistent results. Choose a merge policy reflecting business logic: keep first, keep last, sum, max, min, or fail—do not arbitrarily concatenate strings when order is not guaranteed.

### 14.1. groupingBy vs. toMap

`groupingBy` is usually appropriate when you want to **group multiple elements by key** and apply downstream reductions. `toMap` is usually appropriate when you want **one U value per key K** with an explicit duplicate-key policy.

Both can produce a summing Map<String,Integer> like the demo program, yet their code structure differs:
- groupingBy + summingInt reads as “group, then sum each group”.
- toMap + Integer::sum reads as “insert each key/value into a map and merge values on key collision”.

Neither is universally superior; choose whichever best expresses your intent and constraints on keys, nulls, ordering, and parallelism.

## 15. Type changes in a pipeline after each map/flatMap

Consider:

~~~java
Stream<Order> first = orders.stream();

Stream<String> second = first.map(Order::customer);
~~~

After map, the new stream holds String. If you try `map(Order::total)` on `second`, the compiler rejects it because that mapper needs Order, not String.

**Do not reuse `first` after an intermediate/terminal chain** as if streams can run repeatedly. Java streams are single-use pipelines; the snippet above is only for visualizing types. In real code, create a new stream from the source collection for each new terminal operation.

A properly typed chain example:

~~~java
List<Integer> lengths = orders.stream()
        .map(Order::customer)  // Stream<String>
        .map(String::length)   // Stream<Integer>
        .toList();             // List<Integer>
~~~

How to read type errors:
1. Note the stream's T before the transformation.
2. Check what the mapper accepts and returns.
3. Deduce R and the post-transformation stream type.
4. Match that R against the next operation.
5. At collect, check what the collector consumes and what final R it returns.

The compiler sometimes outputs long errors about inference variables or incompatible bounds; introducing an explicitly typed intermediate variable can pinpoint which step failed.

## 16. Compiler inference and type witnesses when generics become hard to read

Example from `Stream.of`:

~~~java
Stream<String> names = Stream.of("A", "B");
List<Integer> sizes = names.map(String::length).toList();
~~~

The compiler infers T=String from the literals and R=Integer from the mapper. Most code does not need explicit type witnesses.

However, with mappers returning generic collections, complex inference steps can lead the compiler to infer a broad supertype or fail if two lambda branches disagree:

~~~java
// If you want every output element to have type CharSequence:
List<CharSequence> output = Stream.of("A", "B")
        .<CharSequence>map(s -> s)
        .toList();
~~~

`.<CharSequence>map(...)` explicitly specifies type argument R of the generic method map. This is an **explicit type witness**; use it when you need to control the output type or assist the compiler in tricky inference cases.

Still, never use a type witness to mask a genuinely wrong mapper. For instance, `flatMap` still requires a function returning a Stream; declaring R cannot turn a List into a Stream automatically.

Another reminder: `var` only asks the compiler to infer the expression's type, without turning any type raw. Writing:

~~~java
var nested = orders.stream().map(Order::prices).toList();
~~~

infers `List<List<Integer>>` in this example; it **does not flatten** just because no explicit type was written.

## 17. Laziness, terminal operations, and never reusing a Stream

`map` and `flatMap` typically do not run the mapper when declaring the pipeline:

~~~java
Stream<String> pipeline = Stream.of("A", "B")
        .map(s -> {
            System.out.println("mapped=" + s);
            return s.toLowerCase();
        });
~~~

Creating `pipeline` alone does not request computing all results. When calling:

~~~java
List<String> result = pipeline.toList();
~~~

the pipeline executes to build the list. Never start a second terminal operation on `pipeline` after consuming it.

Distinguish:
- **Intermediate:** `map`, `flatMap`, `filter`, `peek`, `sorted`...
- **Terminal:** `collect`, `toList`, `forEach`, `count`, `reduce`, `findFirst`...

Operations may be fused or optimized by the stream engine; do not rely on mapper side effects to count evaluations in arbitrary pipelines. Especially with short-circuit operations, the mapper may not even need to run on every element.

### flatMap and sub-stream resources

If a mapper returns streams backed by resources needing closure, understand resource-closing responsibilities of the parent stream and mapped streams. `flatMap` closes each mapped stream after use, yet managing resources like file lines, I/O, or connections still demands proper design and error handling per the source API. Do not open resources and assume any non-terminated pipeline will automatically release them on time.

## 18. Parallel Streams and Collectors: reading signatures isn't enough for correctness

With `parallelStream`, a collector may accumulate across multiple branches and combine results. Important constraints:

- Mappers/flatMappers should be **non-interfering**: do not modify the stream source during processing.
- Lambdas with shared state must be properly synchronized; otherwise results may race or be wrong.
- `collect(supplier,accumulator,combiner)` requires behavior obeying **identity/associativity** for mutable reduction.
- `groupingBy` is generally not a concurrent collector; when shared concurrent accumulation is needed, consider APIs like `groupingByConcurrent` with appropriate characteristics and ordering expectations.
- Do not conclude that a Collector returning ArrayList means the framework lets multiple threads concurrently write to **the same unsynchronized ArrayList**. Reduction can use separate containers and combine them per the collector contract.

Bad design example:

~~~java
List<String> global = new ArrayList<>();

// Using it like this is unsafe for a parallel stream:
// orders.parallelStream().map(Order::customer).forEach(global::add);
~~~

Replace with an appropriate terminal collection:

~~~java
List<String> customers = orders.parallelStream()
        .map(Order::customer)
        .toList();
~~~

When order matters, check encounter order and collector semantics. `TreeMap` in the demo program guarantees key order, which does not mean every parallel stream guarantees side-effect ordering.

## 19. Nulls and duplicates in common Collectors

**With `toMap`:** in new code, treat null keys/values as something needing a clear contract. Specific collector/map implementations have their own limits; avoid relying on one overload accepting null on one JDK and assuming it is universal. Notably, standard Java releases can reject null values in `Collectors.toMap` with NullPointerException.

**With `groupingBy`:** a classifier returning a null key can be rejected by standard groupingBy implementations; prefer normalizing keys to a concrete domain-approved value.

**With `toUnmodifiableList`:** null elements are rejected. `Stream.toList()` guarantees an unmodifiable List; do not mistake that for a general content validator.

**With duplicate keys:** `toMap(keyMapper,valueMapper)` does not automatically sum or pick first/last. It throws IllegalStateException on duplicates, so if keys can repeat, pick an overload with a mergeFunction or use groupingBy.

**With `Collectors.toList`:** makes no promise of a mutable List or specific implementation class. When you need a mutable ArrayList, use `toCollection(ArrayList::new)`.

Specific policies for nulls, duplicates, ordering, and mutability are part of **API design**, not something solved by generic type arguments alone.

## 20. Common mistakes when reading the three signatures

### 20.1. Using map while expecting a flattened stream

~~~java
Stream<List<Integer>> nested = orders.stream().map(Order::prices);

// Stream<Integer> wrong = orders.stream().map(Order::prices);
// Does not compile: each mapper returns List<Integer>.
~~~

Fix with `flatMap(o -> o.prices().stream())`.

### 20.2. Using flatMap with a mapper returning only List

~~~java
// orders.stream().flatMap(Order::prices); // Invalid.
~~~

It must return `Stream<? extends R>`. Fix with `o -> o.prices().stream()`.

### 20.3. Treating A in Collector<T,A,R> as the output type

`A` is the intermediate accumulation container type, while `R` is the result type. Having `?` at A in `Collector<T,?,List<T>>` does not make the output List<?>.

### 20.4. Treating R of map and R of collect as one fixed variable

They are **separate type parameters in each generic method invocation**. `map` may yield `Stream<Integer>`; later `collect` may return `Map<String,Long>` or `List<Integer>` depending on the collector and pipeline. There is no single R persisting across all methods.

### 20.5. Using BiConsumer in collect and expecting a return value

In the three-argument overload, accumulator/combiner are **BiConsumer** with void return type. Method references `List::add` and `List::addAll`, which return boolean, still match a void-compatible target here; the boolean return value is ignored. The logic must mutate the container rather than returning a different container expecting the framework to use it.

### 20.6. Missing a proper combiner for parallel streams

An empty combiner may seem fine sequentially yet drop data in parallel streams. Choose merge operations satisfying associativity and identity, or use a standard collector.

### 20.7. Using toMap with duplicate keys

~~~java
// orders.stream().collect(Collectors.toMap(
//         Order::customer, Order::total));
// Can throw IllegalStateException when customer repeats.
~~~

Choose an explicit mergeFunction like `Integer::sum` or use groupingBy.

### 20.8. Assuming Collectors.toList returns a mutable ArrayList

This is not guaranteed by the API. Use `toCollection(ArrayList::new)` when a specific collection type is required.

### 20.9. Reusing a stream after a terminal operation

~~~java
Stream<String> names = Stream.of("A", "B");
names.collect(Collectors.toList());
// names.count(); // Do not reuse a consumed stream.
~~~

Create a fresh stream from the source for subsequent processing.

### 20.10. Forgetting primitive streams

`mapToInt`, `flatMapToInt`, `mapToLong`, etc. have different signatures from standard `map/flatMap`. If the goal is integer summation, primitive streams can be simpler and avoid boxing, though they are not the default for every data type.

## 21. Workflow for reading a complex pipeline yourself

When encountering a chain `stream().filter(...).flatMap(...).map(...).collect(...)`, proceed in order:

1. **Note the initial T**: for example `Stream<Order>`.
2. **Read filter**: Predicate takes Order; stream remains Stream<Order>.
3. **Read flatMap**: function takes Order and returns Stream<Integer>; stream becomes Stream<Integer>.
4. **Read map**: if mapping Integer → String, stream becomes Stream<String>.
5. **Read collect**: collector accepts String and returns R, e.g. List<String> or Map<String,Long>.
6. **Watch wildcards**: mappers can accept a supertype; outputs can be a subtype of R; do not replace them with casts/raw types.
7. **On compiler errors**: introduce explicitly typed intermediate variables to isolate the failing inference step.
8. **For complex collectors**: trace T, A, R on each collector and downstream; A is often hidden via `?`.
9. **Check correctness beyond type safety**: nulls, duplicate keys, ordering, parallelism, side effects, and mutability.
10. **Verify with javac** at the project's source release. A Java 17 example can use `Stream.toList()`, whereas a Java 8 project needs `collect(Collectors.toList())` or another compatible approach.

Reading method signatures is the first step; understanding terminal operation and collector contracts tells you **how the result is actually produced**.

## 22. Self-check questions

**1.** Given `Stream<String>` and `map(String::length)`, what type does the stream have after map?

**Answer:** `Stream<Integer>`, because `String.length()` returns int, which is boxed to Integer to satisfy the generic type argument R.

**2.** Why does `map(Order::prices)` give `Stream<List<Integer>>`?

**Answer:** `Order::prices` returns a single List<Integer> per Order, so R is List<Integer>. map does not extract elements inside the List.

**3.** How do you turn that result into `Stream<Integer>`?

**Answer:** `flatMap(o -> o.prices().stream())`; the mapper must return Stream<Integer>.

**4.** What does the signature `Function<? super T, ? extends R>` permit?

**Answer:** The Function can take T or a supertype of T, and return R or a subtype of R; it expresses PECS for input/output.

**5.** Must `flatMap` always return exactly one result per T?

**Answer:** No. The sub-stream can be empty, single-element, or multi-element, producing 0..n results.

**6.** What is `A` in `Collector<? super T,A,R>`?

**Answer:** The intermediate accumulation container type; it need not match R, which is the final type returned when the collector finishes.

**7.** What does `collect(ArrayList::new,List::add,List::addAll)` use the two BiConsumers for?

**Answer:** Accumulator adds each T into container R; combiner merges two R containers, needed when the framework combines partial results.

**8.** From Stream<Order>, using `Collectors.groupingBy(Order::customer)`, what is R?

**Answer:** `Map<String,List<Order>>`, because the classifier returns String and the default downstream groups Orders into List<Order>.

**9.** When using `groupingBy(Order::customer, Collectors.summingInt(Order::total))`, what is the Map's value type?

**Answer:** Integer, so the generic result type is Map<String,Integer>.

**10.** Why can `Collectors.toMap(Order::customer,Order::total)` throw IllegalStateException?

**Answer:** Two orders with the same customer produce a duplicate key; the two-mapper overload has no caller-supplied merge policy.

**11.** To sum totals per customer using toMap, what should you add?

**Answer:** A mergeFunction such as `Integer::sum`; you can also add a mapFactory `TreeMap::new` for deterministic key ordering.

**12.** How does `Collectors.mapping` differ from `Stream.map`?

**Answer:** Stream.map transforms an intermediate Stream; Collectors.mapping is an adapter Collector that converts each T into U before the downstream accumulator receives it.

**13.** How does `Stream.toList()` differ from `collect(Collectors.toList())`?

**Answer:** `Stream.toList()` guarantees an unmodifiable resulting List (Java 16+), whereas `Collectors.toList()` makes no concrete guarantees about mutability or implementation type.

**14.** Why should you avoid calling `forEach(sharedArrayList::add)` on a parallel stream?

**Answer:** A shared ArrayList is not thread-safe for concurrent additions; use a proper terminal collection without interfering side effects.

**15.** If the compiler reports incompatible bounds in a pipeline, what is the best first check?

**Answer:** Write down T before each intermediate operation, R returned by the mapper, and what the collector consumes. Use explicitly typed intermediate variables to locate the exact failing step.

## 23. Takeaways

The three APIs operate at **three different levels**:

~~~text
Stream<T>
    ├─ map(Function<T,R>)                 → Stream<R>
    ├─ flatMap(Function<T,Stream<R>>)     → Stream<R>, concatenates sub-streams
    └─ collect(Collector<T,A,R>)          → R, terminates the pipeline
~~~

The signatures in the diagram omit wildcards for memorability; **the actual signatures** use `? super` for consumed inputs and `? extends` for produced outputs.

- `map`: **one T → one R** per mapping, does not auto-flatten.
- `flatMap`: **one T → Stream<R> → 0..n R**, flattens one level.
- `collect`: **Stream<T> → R**, using a Collector or supplier/accumulator/combiner; A is the intermediate container when using Collector.
- `groupingBy`, `mapping`, `flatMapping`, `toMap` are **collector factories/adapters**, not methods of the same kind as Stream.map/flatMap.
- **Type safety does not replace behavioral correctness**: pay attention to duplicate keys, nulls, ordering, mutability, short-circuiting, parallel reduction, and sources of side effects.

The most effective habit is **reading the element type T at each step**, tracking the mapper's R, and then reading the collector's result R. Once you do that, long generic signatures become clear data-flow diagrams instead of hard-to-memorize symbol strings.