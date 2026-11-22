# Creating a Stream with Stream.of, Stream.empty, and Stream.ofNullable

In the Java Stream API, it is not always necessary to start a pipeline from `Collection.stream()`. The three factory methods `Stream.of(...)`, `Stream.empty()`, and `Stream.ofNullable(...)` help create a stream directly from values already present in the program, from a small set of constants, or from a possibly absent value.

This lesson belongs to the **Streams from Existing Data** chapter of the **JAVA_STREAM_API** module. The goal is to know how to choose the right stream creation method, understand the exact number of elements produced, handle `null` safely, and connect these sources to declarative pipelines with `filter`, `map`, `reduce`, `collect`, or `flatMap`. Issues related to resources, state, and performance are also pointed out where directly relevant.

## 1. At a Glance: Where Do the Three Methods Differ?

| Method | Input | Number of elements in stream | When to use? |
|---|---|---|---|
| `Stream.of(value)` | One value of type `T` | Exactly **1**, even if the value is `null` | Feeding a specific object into a pipeline |
| `Stream.of(v1, v2, ...)` | Multiple values via varargs | Equal to the number of arguments/array elements, which can be **0** | Creating a stream from a few existing values |
| `Stream.empty()` | No arguments needed | Exactly **0** | Expressing a branch with no elements |
| `Stream.ofNullable(value)` | One potentially `null` value | **0** if `null`, otherwise **1** | Turning an optional value into a 0- or 1-element stream |

`Stream.of` and `Stream.empty` have been available since Java 8; `Stream.ofNullable` was introduced in **Java 9**. All three create an initially sequential stream. `Stream.toList()` is used in some examples below and is only available from **Java 16**; on Java 8–15, you can replace it with `collect(Collectors.toList())` in examples that have no specific requirement for list immutability.

To run the examples:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.Optional;
import java.util.stream.Collectors;
import java.util.stream.IntStream;
import java.util.stream.Stream;
```

## 2. `Stream.of(...)`: From One or Many Values

### 2.1. Creating a Stream from Listed Elements

```java
List<String> technologies = Stream.of("Java", "Kotlin", "Scala")
        .map(String::toUpperCase)
        .toList();

System.out.println(technologies); // [JAVA, KOTLIN, SCALA]
```

`Stream.of("Java", "Kotlin", "Scala")` creates a `Stream<String>` with three elements in the order provided. `map` is a lazy intermediate operation: it describes the transformation; `toList()` is the terminal operation that triggers the pipeline and collects the result.

With one element:

```java
Stream<String> one = Stream.of("Java");
System.out.println(one.count()); // 1
```

With zero elements, calling `Stream.of()` also creates an empty stream; specify the type explicitly when the context is insufficient for type inference:

```java
Stream<String> none = Stream.<String>of();
System.out.println(none.count()); // 0
```

In code expressing the intent "no data", `Stream.empty()` is usually more readable than `Stream.of()`.

### 2.2. `Stream.of` Does Not Automatically Remove `null`

`Stream.of` can contain a single `null` element. It can also contain `null` interspersed among valid elements:

```java
long oneNull = Stream.of((String) null).count();
long threeValues = Stream.of("An", null, "Bình").count();

System.out.println(oneNull);     // 1
System.out.println(threeValues); // 3
```

The cast `(String) null` here is very intentional: it forces calling the overload that takes **one object**, avoiding ambiguity with the varargs overload when writing `Stream.of(null)`. If you pass a **`null` varargs reference array** such as `Stream.of((String[]) null)`, the call is not equivalent to one `null` element and can throw a `NullPointerException` when creating the stream.

The fact that a stream allows containing `null` **does not** mean all downstream operations accept it:

```java
List<String> names = Stream.of("An", null, "Bình")
        .filter(Objects::nonNull)
        .map(String::toUpperCase)
        .toList();

System.out.println(names); // [AN, BÌNH]
```

If you omit `filter(Objects::nonNull)`, `String::toUpperCase` will throw a `NullPointerException` when encountering the `null` element. Similarly, `findFirst()` and `findAny()` can throw a `NullPointerException` if the element they select is `null`. Decide explicitly whether `null` is allowed to exist in the pipeline.

### 2.3. Beware of Varargs Overloads and Arrays

For an **object** array `String[]`, `Stream.of(array)` can treat each element in the array as a stream element through the varargs overload:

```java
String[] languages = {"Java", "Go", "Rust"};

List<String> values = Stream.of(languages).toList();
System.out.println(values); // [Java, Go, Rust]

// Cast to Object to treat the entire array as ONE element:
long wholeArray = Stream.of((Object) languages).count();
System.out.println(wholeArray); // 1
```

For a **primitive array** `int[]`, elements are not expanded into `Stream<Integer>`:

```java
int[] scores = {10, 20, 30};

Stream<int[]> arrays = Stream.of(scores);
System.out.println(arrays.count());        // 1: one int[] array
System.out.println(Arrays.stream(scores).sum()); // 60: IntStream
System.out.println(IntStream.of(scores).sum());   // 60: IntStream
```

`Stream.of(scores)` contains exactly **one array object** `int[]`; `Arrays.stream(scores)` and `IntStream.of(scores)` are what create an `IntStream` over each integer. For large primitive data, prefer `IntStream`, `LongStream`, or `DoubleStream` when appropriate to avoid unnecessary boxing.

A similar confusion occurs with `Collection`:

```java
List<String> tags = List.of("core", "stream");

System.out.println(Stream.of(tags).count()); // 1: one List<String>
System.out.println(tags.stream().count());   // 2: two Strings
```

**Rule:** to traverse elements of a `List`, use `list.stream()`; to traverse elements of an array, `Arrays.stream(array)` usually expresses the intent more clearly; to pass an **entire** `List` or array as a single value, use `Stream.of(collection)` or cast the array appropriately.

### 2.4. Using `Stream.of` in a Declarative Pipeline

```java
int total = Stream.of(12, 7, 20, 5)
        .filter(n -> n >= 10)
        .map(n -> n * 2)
        .reduce(0, Integer::sum);

System.out.println(total); // 64 = 24 + 40
```

Here `Stream.of(12, 7, 20, 5)` creates a `Stream<Integer>`. `filter` keeps two elements, `map` doubles them, and `reduce` sums them. This is the declarative data processing pipeline style: stating **what to do** with the source without manually writing a loop to accumulate each element.

## 3. `Stream.empty()`: Expressing the No-Data Case

`Stream.empty()` returns an empty stream of the element type expected by the context:

```java
Stream<String> emptyNames = Stream.empty();
List<String> result = emptyNames.toList();

System.out.println(result); // []
```

If you need to declare the generic type explicitly:

```java
Stream<String> empty = Stream.<String>empty();
System.out.println(empty.count()); // 0
```

The biggest value of `Stream.empty()` is not saving a line of code; it is **keeping the same return type** `Stream<T>` across all logic branches, allowing the caller to compose a pipeline without handling `null`.

```java
static Stream<String> topicsFor(boolean enabled) {
    if (!enabled) {
        return Stream.empty();
    }
    return Stream.of("stream", "collector", "spliterator");
}

// Caller:
List<String> topics = topicsFor(false)
        .map(String::toUpperCase)
        .toList();

System.out.println(topics); // []
```

In a method returning a stream, returning `null` forces the caller to check for it or causes an error if `.map(...)` is chained onto it; returning `Stream.empty()` lets the pipeline continue naturally.

### 3.1. Terminal Operations on an Empty Stream

| Terminal operation | Result on empty stream | Interpretation |
|---|---|---|
| `count()` | `0` | No elements |
| `toList()` | `[]` | Empty list |
| `findFirst()` | `Optional.empty()` | No first element |
| `anyMatch(...)` | `false` | No matching element |
| `allMatch(...)` | `true` | No counterexample element exists |
| `noneMatch(...)` | `true` | No matching element |
| `reduce(identity, op)` | `identity` | No values to combine |

Each line below creates **a new stream**; a stream cannot be consumed twice:

```java
System.out.println(Stream.<Integer>empty().count());           // 0
System.out.println(Stream.<Integer>empty().anyMatch(n -> n > 0)); // false
System.out.println(Stream.<Integer>empty().allMatch(n -> n > 0)); // true
System.out.println(Stream.<Integer>empty().reduce(10, Integer::sum)); // 10
```

`allMatch` on an empty set returns `true` by the logical rule of *vacuous truth*. Do not infer that "an element satisfying the condition was found" when observing `allMatch` return `true` on an empty source.

### 3.2. Combining with Other Streams

```java
Stream<String> base = Stream.of("Java", "Kotlin");
Stream<String> extra = Stream.empty();

List<String> all = Stream.concat(base, extra).toList();
System.out.println(all); // [Java, Kotlin]
```

When business logic yields no elements in one branch, `Stream.empty()` serves as a "branch contributing no data" while remaining compatible with `Stream.concat` or `flatMap`.

## 4. `Stream.ofNullable(value)`: A Single Possibly Absent Value

Java 9 added `Stream.ofNullable(T value)` with a simple contract:

- `value != null`: stream contains that exact **one** element.
- `value == null`: empty stream, **does not contain** a `null` element.

```java
String nickname = null;

List<String> a = Stream.ofNullable(nickname).toList();
List<String> b = Stream.ofNullable("Java").toList();

System.out.println(a); // []
System.out.println(b); // [Java]
```

Direct comparison with `Stream.of`:

```java
String value = null;

System.out.println(Stream.of((String) value).count()); // 1
System.out.println(Stream.ofNullable(value).count());  // 0
```

With `value = "X"`, both create a single element `"X"`. **The difference only appears when the value is `null`**, yet that difference is crucial when terminal operations do not support `null` elements.

### 4.1. Combining with `flatMap` to Skip Missing Properties

Suppose each customer record has an optional email address:

```java
record Customer(String name, String email) {}

List<Customer> customers = List.of(
        new Customer("An", "an@example.com"),
        new Customer("Bình", null),
        new Customer("Chi", "chi@example.com")
);

List<String> emails = customers.stream()
        .flatMap(customer -> Stream.ofNullable(customer.email()))
        .map(String::toLowerCase)
        .toList();

System.out.println(emails); // [an@example.com, chi@example.com]
```

For each customer, `Stream.ofNullable(customer.email())` creates a stream with **0 or 1 email**. `flatMap` concatenates the sub-streams into a single flat stream, so `null` emails do not proceed down to `map`.

The same problem can be written as:

```java
List<String> emails = customers.stream()
        .map(Customer::email)
        .filter(Objects::nonNull)
        .map(String::toLowerCase)
        .toList();
```

Both approaches are reasonable. `map(...).filter(Objects::nonNull)` is usually simplest when just removing `null` after a property extraction; `flatMap(...Stream.ofNullable(...))` is useful when modeling that **each input element contributes 0 or 1 result** or when the same pipeline already needs `flatMap`.

### 4.2. Merging Multiple Potentially `null` Data Sources

```java
String primaryCode = "JAVA";
String fallbackCode = null;

List<String> codes = Stream.of(primaryCode, fallbackCode)
        .flatMap(Stream::ofNullable)
        .map(String::toLowerCase)
        .toList();

System.out.println(codes); // [java]
```

Here `Stream.of(...)` creates two elements, one of which is `null`; `flatMap(Stream::ofNullable)` turns each element into a 0- or 1-element stream to discard missing values. When you only want to remove `null`, `filter(Objects::nonNull)` is usually more direct and readable.

### 4.3. Distinguishing from `Optional.ofNullable`

```java
String token = null;

Optional<String> maybeToken = Optional.ofNullable(token);
Stream<String> tokenStream = Stream.ofNullable(token);
```

`Optional<T>` describes **a single possibly absent value** to return from an API or represent a lookup result. `Stream<T>` describes **a sequence of 0 or more elements** for running a pipeline. If you already have an `Optional<T>`, Java 9 provides `optional.stream()` to get a stream of 0 or 1 element:

```java
Optional<String> maybe = Optional.of("java");
List<String> list = maybe.stream()
        .map(String::toUpperCase)
        .toList();

System.out.println(list); // [JAVA]
```

There is no need to create an intermediate `Optional` just to turn a nullable value into a stream; `Stream.ofNullable(value)` expresses it more directly.

## 5. Choosing the Right Factory in Real Scenarios

| Existing data / requirement | Suggested usage | Reason |
|---|---|---|
| Two constants `"A"`, `"B"` | `Stream.of("A", "B")` | Two definite elements |
| One always-present object | `Stream.of(object)` | One element |
| One potentially `null` object, skip if absent | `Stream.ofNullable(object)` | Does not produce a `null` element |
| Branch with no results | `Stream.empty()` | Preserves type `Stream<T>` |
| An existing `List<T>` | `list.stream()` | Traverses list elements |
| An existing `T[]` | `Arrays.stream(array)` | Clearly traverses each array element |
| An existing `int[]` | `Arrays.stream(array)` or `IntStream.of(array)` | Produces `IntStream`, not `Stream<int[]>` |
| An existing `Optional<T>` | `optional.stream()` | Converts Optional to a 0- or 1-element stream |
| Multiple nullable properties to collect | `Stream.of(a, b).filter(Objects::nonNull)` | Removes `null` clearly and simply |

### Business Example: Collecting Optional Labels

```java
static Stream<String> labelsFor(String title, String category, boolean includeCategory) {
    Stream<String> titlePart = Stream.ofNullable(title);
    Stream<String> categoryPart = includeCategory
            ? Stream.ofNullable(category)
            : Stream.empty();

    return Stream.concat(titlePart, categoryPart)
            .map(String::trim)
            .filter(s -> !s.isEmpty());
}

// Caller:
List<String> labels = labelsFor(" Java Stream ", null, true).toList();
System.out.println(labels); // [Java Stream]
```

The method always returns `Stream<String>`, even when there are no labels. `Stream.ofNullable` handles missing values; `Stream.empty` represents the branch adding no label; `Stream.concat` joins the two sources. `map` and `filter` remain lazy until `toList()` consumes the stream.

## 6. Contracts and Limits to Remember

### 6.1. Element Order and Execution Mode

`Stream.of("C", "A", "B")` creates a stream with **encounter order** `C → A → B`; if using an order-preserving terminal operation such as `toList()`, the result is still `[C, A, B]`. `parallel()` allows processing across multiple threads, but by itself it does not eliminate encounter order:

```java
List<String> names = Stream.of("C", "A", "B")
        .parallel()
        .map(String::toLowerCase)
        .toList();

System.out.println(names); // [c, a, b]
```

`Stream.empty()` and `Stream.ofNullable(...)` have at most one element, so running them directly in parallel brings almost no benefit. If using parallel `forEach`, do not assume the action executes in order; when action order must be guaranteed on an ordered stream, use `forEachOrdered`.

### 6.2. A Stream Can Only Be Consumed Once

```java
Stream<String> stream = Stream.of("A", "B");
long size = stream.count();
System.out.println(size); // 2

// stream.toList(); // Wrong: stream has already been consumed.
```

After the terminal operation `count()`, do not reuse the same `stream` object. Create a new stream from the source values if you want to run another pipeline.

### 6.3. Arguments Are Evaluated Before the Stream Starts Running

Intermediate operations `map` and `filter` are normally lazy, yet **arguments passed into the factory are still evaluated eagerly by Java**:

```java
static String fetchValue() {
    System.out.println("fetchValue called");
    return "data";
}

Stream<String> stream = Stream.ofNullable(fetchValue());
// "fetchValue called" is already printed here, before any terminal operation.

System.out.println(stream.map(String::toUpperCase).toList()); // [DATA]
```

Do not use `Stream.of(fetchValue())` or `Stream.ofNullable(fetchValue())` to defer calling `fetchValue()`. Both methods only wrap an **already-computed value** into a stream. If data must be generated on demand, choose an appropriate lazy source (for example `Stream.generate(supplier)` with an explicit element limit).

### 6.4. Shared State, Resources, and Performance

- Do not use `map` or `peek` to arbitrarily update shared variables, especially when using `parallel()`. Prefer side-effect-free transformations and appropriate `collect` or `reduce` terminal operations.
- These three factories create streams from existing data and do not open closable resources such as files or connections. For sources that open other resources, such as `Files.lines(path)`, use `try-with-resources` to close the stream.
- `Stream.of` is convenient for a small set of values; if you already have a large `List` or array, use the appropriate source directly. Creating many single-element streams and nesting concatenations too deeply can incur unnecessary overhead; choose a clear pipeline structure and measure performance with realistic data.
- `Stream.toList()` returns an unmodifiable list, whereas `Collectors.toList()` makes no guarantee on mutability or concrete list type. If you need a mutable `ArrayList`, use `collect(Collectors.toCollection(ArrayList::new))` and import `java.util.ArrayList`.

## 7. Complete Runnable Example (Java 17+)

The following program tests multiple elements, an empty stream, nullable values, a primitive array, and combining properties:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Stream;

public class StreamFactoriesDemo {
    record User(String name, String nickname) {}

    public static void main(String[] args) {
        // 1. Multiple existing values.
        System.out.println(Stream.of("A", "B", "C").toList());
        // [A, B, C]

        // 2. No elements.
        System.out.println(Stream.<String>empty().count());
        // 0

        // 3. One potentially null object.
        String nickname = null;
        System.out.println(Stream.ofNullable(nickname).toList());
        // []
        System.out.println(Stream.ofNullable("dev").toList());
        // [dev]

        // 4. One null element differs from an empty stream.
        System.out.println(Stream.of((String) null).count());
        // 1

        // 5. Primitive arrays are not unpacked by Stream.of().
        int[] nums = {1, 2, 3};
        System.out.println(Stream.of(nums).count());
        // 1
        System.out.println(Arrays.stream(nums).sum());
        // 6

        // 6. Collecting nullable values.
        List<User> users = List.of(
                new User("An", "anna"),
                new User("Bình", null),
                new User("Chi", "chichi")
        );
        List<String> nicknames = users.stream()
                .flatMap(user -> Stream.ofNullable(user.nickname()))
                .map(String::toUpperCase)
                .toList();
        System.out.println(nicknames);
        // [ANNA, CHICHI]
    }
}
```

## 8. Self-Check

1. **What does `Stream.of((String) null).count()` return?** It returns `1` because `null` is an element of the stream.
2. **How does `Stream.ofNullable(null)` differ from `Stream.empty()`?** Both are empty in this case; `ofNullable` can also produce one element when the input is non-`null`.
3. **What does `Stream.of(List.of(1, 2, 3)).count()` return?** It returns `1`, because the sole element is the entire `List`. To get three numbers, use `List.of(1, 2, 3).stream()`.
4. **What does `Stream.of(new int[]{1, 2, 3}).count()` return?** It returns `1`; to get a stream of three integers, use `IntStream.of(1, 2, 3)` or `Arrays.stream(array)`.
5. **Why doesn't `Stream.ofNullable(fetchValue())` defer `fetchValue()`?** Because Java evaluates method arguments before calling the method; laziness applies to downstream pipeline steps.
6. **To have each customer contribute at most one email, skipping `null`, what should you use?** `customers.stream().flatMap(c -> Stream.ofNullable(c.email()))` or `map(...).filter(Objects::nonNull)`.

Choose `Stream.of` when you have concrete values, `Stream.empty` when a branch contributes no elements, and `Stream.ofNullable` when a single value may be absent. This choice determines right at the source whether the downstream pipeline sees **0, 1, or multiple elements**, especially whether `null` elements are present.
