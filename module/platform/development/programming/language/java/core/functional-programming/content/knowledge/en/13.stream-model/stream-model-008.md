# Reading a Stream Pipeline by Data Type at Each Step

A pipeline in Java Stream is a chain of operations starting from a **data source**, passing through **zero or more intermediate operations**, and ending with a **terminal operation**. To understand a pipeline properly, do not just read the method names; ask at each step: **what is the input type, what is the element type after the transformation, and is it still holding a Stream or has it already returned a result?**

Example:

~~~java
List<String> names = orders.stream()
        .filter(order -> order.total() >= 100)
        .map(Order::customer)
        .distinct()
        .sorted()
        .toList();
~~~

If `orders` is `List<Order>` and `Order.customer()` returns `String`, we read it according to the diagram:

~~~text
List<Order>
  .stream()                         → Stream<Order>
  .filter(Order -> boolean)          → Stream<Order>
  .map(Order -> String)              → Stream<String>
  .distinct()                        → Stream<String>
  .sorted()                          → Stream<String>
  .toList()                          → List<String>
~~~

The lines above are a **type breakdown**, not standalone Java statements. At runtime, `filter`, `map`, `distinct`, and `sorted` are intermediate operations that construct a pipeline to be processed when a terminal operation is invoked; they do not mean each step must eagerly create a new list.

## 1. Quick left-to-right reading rule

For each link in the chain, note four pieces of information:

1. **Current receiver:** what type is the object to the left of the dot? For example, `Stream<Order>`, `IntStream`, `Optional<Order>`, `List<Order>`.
2. **Input type of the lambda/method reference:** the argument of `filter` or `map` is usually **a single element** of the current type, not the entire list.
3. **Return type of the lambda:** `boolean`, `R`, `Stream<R>`, `int`... determines certain transformations.
4. **Return type of the method:** is it still a stream to continue chaining, or has it terminated into a `List`, `long`, `Optional`, `Map`...?

You can annotate directly onto the API signatures:

| Operation | Typical input | Result type | Changes element type? |
| --- | --- | --- | --- |
| `Collection<T>.stream()` | Collection of elements `T` | `Stream<T>` | No |
| `Stream<T>.filter(Predicate<T>)` | `T -> boolean` | `Stream<T>` | No |
| `Stream<T>.map(Function<T,R>)` | `T -> R` | `Stream<R>` | Possibly |
| `Stream<T>.flatMap(Function<T,Stream<R>>)` | `T -> Stream<R>` | `Stream<R>` | Possibly, while also flattening |
| `Stream<T>.mapToInt(ToIntFunction<T>)` | `T -> int` | `IntStream` | Converts to primitive stream |
| `Stream<T>.distinct()` | A `Stream<T>` | `Stream<T>` | No |
| `Stream<T>.sorted()` | A `Stream<T>` | `Stream<T>` | No |
| `Stream<T>.sorted(Comparator<T>)` | Comparator comparing `T` | `Stream<T>` | No |
| `Stream<T>.limit(long)` | A `Stream<T>` | `Stream<T>` | No |
| `Stream<T>.toList()` | A `Stream<T>` | `List<T>` | Terminates stream |
| `Stream<T>.count()` | A `Stream<T>` | `long` | Terminates stream |
| `Stream<T>.findFirst()` | A `Stream<T>` | `Optional<T>` | Terminates stream |

The symbols `T` and `R` are **type parameters**, not concrete class names. For instance, if the source has `T = Order` and `map` extracts the customer name (`R = String`), from that point on the next lambda receives `String` instead of `Order`.

## 2. Standalone example: tracing each type of a pipeline

Create the file `PipelineTypeTrace.java`:

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.stream.Stream;

public class PipelineTypeTrace {
    record Order(String customer, int total) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("An", 120),
                new Order("Bình", 70),
                new Order("Chi", 180),
                new Order("An", 150)
        );

        Stream<Order> source = orders.stream();
        Stream<Order> expensive = source.filter(o -> o.total() >= 100);
        Stream<String> customers = expensive.map(Order::customer);
        Stream<String> unique = customers.distinct();
        Stream<String> alphabetical = unique.sorted();

        List<String> result = alphabetical.toList();
        System.out.println(result);
    }
}
~~~

~~~bash
javac --release 17 PipelineTypeTrace.java
java PipelineTypeTrace
~~~

Output:

~~~text
[An, Chi]
~~~

Step-by-step explanation:

- `orders.stream()`: the source object is `List<Order>`; the result is `Stream<Order>`.
- `filter(o -> o.total() >= 100)`: `o` is `Order`, the condition expression returns `boolean`; the result is still `Stream<Order>`.
- `map(Order::customer)`: the extractor function takes `Order`, returns `String`; the type becomes `Stream<String>`.
- `distinct()`: removes duplicate elements according to `equals()`, without changing `String` to another type.
- `sorted()`: sorts `String` in natural order, still `Stream<String>`.
- `toList()`: terminal operation collecting the result into `List<String>`. The list returned by `Stream.toList()` does not allow modification via operations such as `add`.

The `Stream<...>` variables in the example are only meant to reveal the static type of each stage. Writing a chained pipeline is semantically equivalent in this case:

~~~java
// Illustration snippet using the orders list declared in the example above.
List<String> result = orders.stream()
        .filter(o -> o.total() >= 100)
        .map(Order::customer)
        .distinct()
        .sorted()
        .toList();
~~~

Each stream is used once to continue the pipeline; after a terminal operation runs, do not continue using the consumed stream. If you need to perform another query on the same data, create a new stream from the source.

## 3. `filter` changes the set of elements, not the element type

Read `filter` as "keep or discard each element `T`". `Predicate<T>` returns `boolean`; the `filter` method returns `Stream<T>`.

~~~java
Stream<String> words = Stream.of("Java", "", "API");
Stream<String> nonEmpty = words.filter(s -> !s.isEmpty());
~~~

If a filter lambda uses an object's `age` field, the remaining elements **are still that object**, they do not automatically become ages:

~~~java
// Notation: Stream<Person> persons
Stream<Person> adults = persons.filter(p -> p.age() >= 18);
// Cannot assign the result directly to Stream<Integer>.
~~~

To get the age, the next step must be `map(Person::age)` or `mapToInt(Person::age)`. This often explains IDE errors like "cannot find symbol": after a type-changing `map`, the next lambda no longer receives the old object.

## 4. `map`: each `T` is transformed into one `R`

`map` takes `Function<? super T, ? extends R>` and returns `Stream<R>`. The output element of `map` is **the value returned by the lambda**:

~~~java
// Source Stream<String>:
Stream<String> names = Stream.of("An", "Bình", "Chi");

// String -> Integer (boxing the length):
Stream<Integer> lengths = names.map(String::length);
~~~

In this example, `String.length()` returns `int`; generic `Stream<R>` only accepts reference types, so `int` is boxed into `Integer` and the result has type `Stream<Integer>`.

If you chain `map(n -> n * 2)`, the lambda receives an `Integer` (auto-unboxed during calculation) and the pipeline remains `Stream<Integer>`. You cannot call `String::toUpperCase` on `Stream<Integer>`: the element type has changed.

**`map` does not flatten multi-value structures.** If the lambda returns `List<String>`, the result type is `Stream<List<String>>`; if it returns `Stream<String>`, the type is `Stream<Stream<String>>`. Each original element still corresponds to one result value from the mapper (that value may be a collection/stream).

### Typical type-inference error

~~~java
// Intentionally non-compiling illustration:
// Stream.of("abc", "d")
//       .map(String::length)         // Stream<Integer>
//       .filter(s -> s.startsWith("a")); // s here is Integer!
~~~

If you want to filter by string, place `filter(s -> s.startsWith("a"))` **before** `map(String::length)`. If you want to filter by length, write `.filter(n -> n > 1)` **after** `map`. The order of transformations changes both the static type and the business meaning.

## 5. `flatMap`: from `T -> Stream<R>` into a single `Stream<R>`

When each element has **multiple sub-elements**, `flatMap` is the step that both transforms and flattens one level. For example, `List<List<String>>`:

~~~text
List<List<String>>
  .stream()                  → Stream<List<String>>
  .map(List::stream)         → Stream<Stream<String>>
  .flatMap(List::stream)     → Stream<String>  (if used instead of map above)
~~~

The two lines `map` and `flatMap` in the diagram are **two different choices at the same point**, not two consecutive calls.

File `FlatMapTypeDemo.java`:

~~~java
import java.util.List;
import java.util.stream.Stream;

public class FlatMapTypeDemo {
    public static void main(String[] args) {
        List<List<String>> groups = List.of(
                List.of("An", "Bình"),
                List.of(),
                List.of("Chi")
        );

        Stream<List<String>> outer = groups.stream();
        Stream<String> flattened = outer.flatMap(List::stream);
        List<String> all = flattened.map(String::toUpperCase).toList();

        System.out.println(all);
    }
}
~~~

~~~bash
javac --release 17 FlatMapTypeDemo.java
java FlatMapTypeDemo
~~~

Output:

~~~text
[AN, BÌNH, CHI]
~~~

At `flatMap(List::stream)`:

- The input to the mapper is a `List<String>`.
- `List::stream` returns a `Stream<String>` for each inner list.
- `flatMap` concatenates the inner streams into a single `Stream<String>`.
- The lambda in the subsequent `map(String::toUpperCase)` receives **`String`**, not `List<String>`.

For a mapper returning null, the contract of `Stream.flatMap` treats a null inner stream as an empty stream; however, in code you should explicitly return `Stream.empty()` when you want to skip a branch, avoiding reliance on what null means in each API. `Optional.flatMap` has a different contract: an `Optional` mapper that returns a null `Optional` reference when invoked will throw `NullPointerException`.

## 6. Converting from `Stream<T>` to a primitive stream

The methods `mapToInt`, `mapToLong`, and `mapToDouble` **change the entire stream family**:

~~~text
Stream<String>
  .map(String::length)       → Stream<Integer>
  .mapToInt(String::length)  → IntStream
~~~

The two lines are **alternative choices**, not chained directly one after another in the diagram.

File `PrimitivePipelineDemo.java`:

~~~java
import java.util.List;
import java.util.stream.IntStream;

public class PrimitivePipelineDemo {
    public static void main(String[] args) {
        List<String> words = List.of("a", "Java", "abc");

        IntStream lengths = words.stream().mapToInt(String::length);
        int total = lengths.filter(n -> n >= 3).sum();
        System.out.println("total=" + total);

        List<Integer> boxed = words.stream()
                .mapToInt(String::length)
                .boxed()
                .toList();
        System.out.println("boxed=" + boxed);
    }
}
~~~

~~~bash
javac --release 17 PrimitivePipelineDemo.java
java PrimitivePipelineDemo
~~~

Output:

~~~text
total=7
boxed=[1, 4, 3]
~~~

Explanation:

1. `words.stream()` is `Stream<String>`.
2. `mapToInt(String::length)` returns `IntStream`, where each element is an `int`.
3. `IntStream.filter(IntPredicate)` still returns `IntStream`.
4. `IntStream.sum()` terminates the pipeline and returns `int` (in the example, 4 + 3 = 7).
5. `IntStream.boxed()` turns the values into `Stream<Integer>`; `toList()` then returns `List<Integer>`.

On `IntStream`, specialized APIs include `sum()`, `average()`, `summaryStatistics()`, `boxed()`, and `mapToObj()`. Some similar operations exist on `Stream<T>`, but their return types differ. For example, `IntStream.average()` returns `OptionalDouble`, not a bare `double`, because an empty stream has no defined average.

Also note that `IntStream.mapToObj(n -> "length=" + n)` returns a `Stream<String>` if the lambda produces a string; then the terminal operation `toList()` again returns `List<String>`.

## 7. From a stream to `Optional`, then to a value

A terminal operation changes the shape of the result. For example:

~~~text
Stream<Order>
  .filter(...)                      → Stream<Order>
  .findFirst()                      → Optional<Order>
  .map(Order::customer)             → Optional<String>
  .orElse("Không có")               → String
~~~

The `map` after `findFirst()` is **`Optional.map`**, no longer `Stream.map`; the two APIs share the same name but have different receivers, and `Optional` holds at most one value.

File `OptionalAfterStreamDemo.java`:

~~~java
import java.util.List;
import java.util.Optional;

public class OptionalAfterStreamDemo {
    record Order(String customer, int total) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("An", 50),
                new Order("Bình", 150)
        );

        Optional<Order> selected = orders.stream()
                .filter(o -> o.total() >= 100)
                .findFirst();

        Optional<String> customer = selected.map(Order::customer);
        String name = customer.orElse("Không có");

        System.out.println("selected=" + selected.isPresent());
        System.out.println("name=" + name);
    }
}
~~~

~~~bash
javac --release 17 OptionalAfterStreamDemo.java
java OptionalAfterStreamDemo
~~~

Output:

~~~text
selected=true
name=Bình
~~~

A common mistake is writing `.findFirst().filter(...).toList()`: `Optional.filter` exists, but `Optional` **does not have `toList()`**. Check the current type before calling the next API.

Some terminal operations to remember:

| Terminal operation | Result type | Notes |
| --- | --- | --- |
| `Stream<T>.toList()` | `List<T>` | List cannot be modified through the API. |
| `Stream<T>.toArray()` | `Object[]` | Does not automatically become `T[]` at runtime. |
| `Stream<T>.toArray(String[]::new)` | `String[]` | When elements can be stored in a `String[]` array. |
| `Stream<T>.count()` | `long` | Number of elements. |
| `Stream<T>.anyMatch(predicate)` | `boolean` | Can short-circuit. |
| `Stream<T>.findFirst()` | `Optional<T>` | For an ordered stream, picks the first element by encounter order. |
| `IntStream.sum()` | `int` | Primitive sum; empty gives sum 0. |
| `IntStream.average()` | `OptionalDouble` | Can be empty. |
| `Stream<T>.collect(collector)` | Depends on `Collector` | For example `List<T>`, `Map<K,List<T>>`, `Long`... |

## 8. `collect` can restructure into a `Map`

Not every terminal operation produces a list. With `Collectors.groupingBy`, read the key type from the classifier function and the element type from the stream **right before the collector**.

File `GroupingTypeDemo.java`:

~~~java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class GroupingTypeDemo {
    record Item(String category, String name) {}

    public static void main(String[] args) {
        List<Item> items = List.of(
                new Item("book", "Java"),
                new Item("tool", "Git"),
                new Item("book", "Kotlin")
        );

        Map<String, List<String>> namesByCategory = items.stream()
                .collect(Collectors.groupingBy(
                        Item::category,
                        TreeMap::new,
                        Collectors.mapping(Item::name, Collectors.toList())
                ));

        System.out.println(namesByCategory);
    }
}
~~~

~~~bash
javac --release 17 GroupingTypeDemo.java
java GroupingTypeDemo
~~~

Output:

~~~text
{book=[Java, Kotlin], tool=[Git]}
~~~

Here:

~~~text
List<Item>
  .stream()                                          → Stream<Item>
  .collect(groupingBy(Item::category,
                      TreeMap::new,
                      mapping(Item::name, toList())))  → Map<String, List<String>>
~~~

`groupingBy` takes the `String` key from `Item::category`; the downstream `mapping` extracts `String name` and collects into `List<String>`. `TreeMap::new` ensures keys in the result are sorted in natural order, so stdout in the example is deterministic. If you use the default `groupingBy(Item::category)`, the typical result is `Map<String,List<Item>>`, and you should not rely on the map's key iteration order.

## 9. Method call order and types help catch bugs

Consider the expression:

~~~java
// Suppose orders is List<Order> and Order.total() returns int.
orders.stream()
      .map(Order::customer)
      .filter(o -> o.total() > 100); // Type mismatch in lambda.
~~~

After `map(Order::customer)`, the type is already `Stream<String>`: the variable `o` in `filter` is `String`, no longer `Order`; there is no `total()` method.

One correct way is to filter by `Order`'s property **before** converting to names:

~~~java
orders.stream()
      .filter(o -> o.total() > 100)
      .map(Order::customer)
      .toList();
~~~

Another correct way, if the goal is to filter by customer name length, is to change the predicate after `map`:

~~~java
orders.stream()
      .map(Order::customer)
      .filter(name -> name.length() > 2)
      .toList();
~~~

These are two different business requirements. The IDE or compiler can warn about a type mismatch, but only reading the `Stream<Order> → Stream<String>` path confirms where the fix belongs.

## 10. Distinguishing element type from element count

Two questions should be kept separate:

- What is the **element type** after this step? For example, `Stream<String>`.
- How can the **element count** change? For example, `filter` can drop many elements, `flatMap` can produce 0 or many elements from one input element, and `distinct` can merge duplicates.

| Intermediate operation | Type | Typical effect on element count |
| --- | --- | --- |
| `filter` | `Stream<T> → Stream<T>` | Keeps or drops each element. |
| `map` | `Stream<T> → Stream<R>` | One input element produces one output element, even if the mapper creates a collection. |
| `flatMap` | `Stream<T> → Stream<R>` | One input element can produce 0, 1, or many output elements. |
| `distinct` | `Stream<T> → Stream<T>` | Removes duplicates by `equals` on the current result. |
| `limit(n)` | `Stream<T> → Stream<T>` | Caps the maximum number of elements at `n`. |
| `sorted` | `Stream<T> → Stream<T>` | Sorts elements without changing the element type itself. |

For example, a `Stream<List<String>>` with three elements (three lists) does not mean `Stream<String>` after `flatMap` has three elements; the result can have the total number of strings across all inner lists.

In particular, `distinct()` placed before `map` differs from `distinct()` placed after `map`: before `map` it compares source objects, while after `map` it compares transformed values. Both can be valid, but they are not arbitrarily interchangeable.

## 11. Lazy pipelines: static types exist immediately, data processing can happen later

A pipeline can be declared without consuming data yet:

~~~java
import java.util.List;
import java.util.stream.Stream;

public class LazyPipelineDemo {
    public static void main(String[] args) {
        Stream<String> pipeline = List.of("a", "bb", "ccc").stream()
                .filter(s -> {
                    System.out.println("filter=" + s);
                    return s.length() >= 2;
                })
                .map(s -> {
                    System.out.println("map=" + s);
                    return s.toUpperCase();
                });

        System.out.println("ready");
        List<String> result = pipeline.toList();
        System.out.println("result=" + result);
    }
}
~~~

~~~bash
javac --release 17 LazyPipelineDemo.java
java LazyPipelineDemo
~~~

Output for the sequential stream in the example:

~~~text
ready
filter=a
filter=bb
map=bb
filter=ccc
map=ccc
result=[BB, CCC]
~~~

Even though `filter` and `map` have been declared, their work is only executed when the terminal operation `toList()` consumes the stream. Pipeline execution can *fuse* operations per element; do not imagine it always creates an intermediate list for all `filter` results before running all `map` calls.

**Do not rely on side effects** in `map`, `filter`, or `peek` to perform business logic. Some terminal operations and optimizations may not need to run all lambdas; parallel pipelines also have different execution orders. The logging example above is mainly to illustrate laziness in this specific case. Choose a terminal operation to collect results; do not treat how many times a lambda is invoked as a contract to replace primary processing.

## 12. When types hit generic errors, declare intermediate steps to trace

For long pipelines, a useful debugging technique is to temporarily split them into explicitly typed variables:

~~~java
// Illustration inside a method that already has List<String> source.
Stream<String> words = source.stream();
Stream<Integer> lengths = words.map(String::length);
Stream<Integer> large = lengths.filter(n -> n >= 3);
List<Integer> output = large.toList();
~~~

If the snippet fails to compile, the compiler will pinpoint where the result type does not satisfy the variable type. Once understood and fixed, you can chain it back together. When writing generic helpers, also keep the result types of `map`, `flatMap`, and terminal operations clear, avoiding forced casts to hide inference errors.

In an IDE, you can use "quick documentation", expression type hints, or extract local variables. When evaluating lambdas:

- `filter(x -> ...)` must return `boolean`.
- `map(x -> ...)` can return many types `R`, including `List<R>` or `Optional<R>`, but **does not auto-flatten**.
- `flatMap(x -> ...)` on `Stream` requires the mapper to return a `Stream<R>`.
- `mapToInt(x -> ...)` requires an `int` value, not `OptionalInt`.
- `findFirst()`, `count()`, `toList()`, and `collect(...)` terminate the pipeline; afterward, the receiver is no longer a stream.

## 13. Common mistakes when reading Stream pipelines

1. **Reading `filter` as `map`:** filtering by a property does not turn the element into that property.
2. **Forgetting `map` already changed the type:** calling a method of the source class on an element that has already become `String` or `Integer`.
3. **Confusing `Stream<List<T>>` with `Stream<T>`:** `map(List::stream)` creates a nested stream; `flatMap(List::stream)` is what flattens it.
4. **Confusing primitive streams with `Stream<Integer>`:** `mapToInt` returns `IntStream`, whereas `map` with a function returning `int` boxes it into `Stream<Integer>`.
5. **Forgetting a terminal operation changes the receiver object:** after `findFirst` it is `Optional<T>`; after `toList` it is `List<T>`; you are no longer chaining on `Stream<T>`.
6. **Assuming every intermediate operation runs immediately:** they are generally lazy, and the pipeline is consumed by the terminal operation.
7. **Equating element type with cardinality:** `filter`, `flatMap`, and `distinct` can change the element count without necessarily changing the type.
8. **Assuming mutable data is always safe:** avoid modifying the source collection while the pipeline is processing, and avoid side effects on shared state when running in parallel.
9. **Assuming `toArray()` automatically returns `T[]`:** the no-arg overload on an object stream returns `Object[]`; use a generator such as `String[]::new` when you need a specific array type.
10. **Relying on the order of an unordered source:** use an ordered source and APIs that preserve encounter order if the result needs ordering; do not assume every `Set` or `Map` has a deterministic order.

## 14. Self-practice exercise: reading a pipeline

Predict the **type after each step** before running the following snippet:

~~~java
List<String> results = java.util.stream.Stream.of("Java", "SQL", "Go")
        .filter(s -> s.length() >= 3)
        .map(String::length)
        .map(n -> "len=" + n)
        .sorted()
        .toList();
~~~

Answer:

~~~text
Stream.of(...)                   → Stream<String>
filter(String -> boolean)        → Stream<String>
map(String -> Integer)           → Stream<Integer>
map(Integer -> String)           → Stream<String>
sorted()                         → Stream<String>
toList()                         → List<String>
Final value                      → [len=3, len=4]
~~~

This sorts the **strings** `"len=3"`, `"len=4"`. If you want to sort by the numeric value before formatting, change the operation order to `.map(String::length).sorted().map(n -> "len=" + n)`. Moving `sorted` can change the meaning when the string representation does not preserve numeric order, such as `"len=10"` versus `"len=2"`.

**Remember:** When reading a pipeline, always write out the type chain **`Source → Stream<T> → Stream<R> / IntStream → terminal result`**. Simply by identifying the receiver type, the lambda's input/output, and the method's return type at each dot, you will avoid most errors involving generics, lambdas, boxing, `flatMap`, and post-terminal API usage.