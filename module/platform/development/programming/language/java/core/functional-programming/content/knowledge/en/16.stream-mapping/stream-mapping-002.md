# `flatMap()` and Flattening Nested Data in Java Stream

## 1. The Problem: One Element Can Contain Multiple Child Elements

In Java, `Stream.map` transforms **each input element into one output value**. However, real-world data often has a nested structure: an order contains multiple order lines, a department contains multiple employees, a class has multiple students, or a file contains multiple lines and each line contains multiple words.

Suppose a list contains three sublists:

```text
[[1, 2], [], [3, 4]]
```

When you need to process each number `1, 2, 3, 4` as elements of **a single** stream, `flatMap` helps **convert each parent element into a child stream and then concatenate the contents of those child streams into a single resulting stream**.

```text
Stream<List<Integer>>
   [1, 2] ----> Stream(1, 2) ---+
   [] --------> Stream() -------+----> Stream<Integer>: 1, 2, 3, 4
   [3, 4] ----> Stream(3, 4) ---+
```

Key points to remember:

- `map(f)`: **one input → one output**. If `f` returns a `List<T>` or `Stream<T>`, the result still contains those sublists/child streams.
- `flatMap(f)`: **one input → zero, one, or many outputs** (each input is mapped to a child stream). `flatMap` concatenates the elements of those child streams into a flat stream.
- `flatMap` does not automatically "recursively flatten all levels". **Each call** only flattens one stream level returned by the mapper.

Practical example: you need to retrieve all product codes appearing in orders, without needing a list of product codes nested per order.

## 2. Type Signature and How to Reason About It

The key signature of `Stream<T>` is:

```java
<R> Stream<R> flatMap(
        Function<? super T, ? extends Stream<? extends R>> mapper);
```

Reading from the inside out:

1. The source has type `Stream<T>`.
2. The mapper takes a `T` and returns a `Stream<? extends R>`.
3. `flatMap` extracts the `R` elements inside the child streams and returns a single `Stream<R>`.

Example:

```java
import java.util.List;
import java.util.stream.Stream;

List<List<Integer>> groups =
        List.of(List.of(1, 2), List.of(), List.of(3, 4));

Stream<List<Integer>> outer = groups.stream();

// map: each List<Integer> becomes a Stream<Integer>
Stream<Stream<Integer>> nested =
        outer.map(List::stream);

// Create a new source stream because "outer" already entered the previous pipeline.
Stream<Integer> flat =
        groups.stream().flatMap(List::stream);

System.out.println(flat.toList()); // [1, 2, 3, 4]
```

In this example, `List::stream` is a method reference equivalent to `list -> list.stream()`. With `map`, the result type is `Stream<Stream<Integer>>`; with `flatMap`, the result type is directly `Stream<Integer>`.

**Note on single-use streams:** a `Stream` is not a list that can be reused over and over. Once you start building a pipeline with an intermediate operation, you should not reuse the original stream in another branch. When you need two independent transformations, call `groups.stream()` twice as shown above.

### Visual Formula

```text
map:
T --f--> R
Stream<T> --map(f)--> Stream<R>

flatMap:
T --f--> Stream<R>
Stream<T> --flatMap(f)--> Stream<R>
```

There is no rule that "`flatMap` is always more powerful than `map`". Choose `map` when one element truly corresponds to **one result**; choose `flatMap` when one element corresponds to **a stream of results** and the goal is to traverse them as a single stream.

## 3. Basic Example: Flattening a Two-Dimensional List

```java
List<List<String>> teams = List.of(
        List.of("Lan", "Minh"),
        List.of(),
        List.of("An", "Hoa")
);

List<String> members = teams.stream()
        .flatMap(List::stream)
        .toList();

System.out.println(members);
// [Lan, Minh, An, Hoa]
```

Explanation:

- The first sublist emits `Lan`, `Minh`.
- The second list is empty, so it **emits no elements**.
- The last list emits `An`, `Hoa`.
- The result is a flat list of four elements, with no empty sublists in the result.

Equivalent version using a lambda:

```java
List<String> members = teams.stream()
        .flatMap(team -> team.stream())
        .toList();
```

`List::stream` is concise and clear when the mapper only calls `stream()`. A lambda is appropriate when you need to filter, transform, or retain additional contextual data inside the child stream.

### What Structure Would `map` Produce?

```java
List<List<String>> copiedGroups = teams.stream()
        .map(team -> team.stream().toList())
        .toList();

System.out.println(copiedGroups);
// [[Lan, Minh], [], [An, Hoa]]
```

This is a `List<List<String>>` because each team still produces **one list**. If the requirement is to display members grouped by team, this nested structure is right; if the requirement is to aggregate statistics across all members, `flatMap` is usually more convenient.

## 4. Complete Java 17 Example: Orders Containing Product Lines

Problem: there are multiple orders, each having a list of order lines. You need to:

1. Understand the difference between still-nested data and flattened data.
2. Retrieve all order lines via `flatMap`.
3. Preserve the **parent order ID** when creating a flat list of details.
4. Create a list of unique SKUs and compute the total quantity.
5. Flatten a list of numbers, `Optional` values, and words across multiple lines of text.

Create the file **`FlatMapDemo.java`**:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.Optional;
import java.util.stream.Stream;

public class FlatMapDemo {
    record Line(String sku, int quantity) {}

    record Order(String id, List<Line> lines) {
        Order {
            // Take a structural copy of the list; Line is an immutable record.
            lines = List.copyOf(lines);
        }
    }

    record OrderLine(String orderId, String sku, int quantity) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("A01", List.of(
                        new Line("BOOK", 2),
                        new Line("PEN", 3)
                )),
                new Order("A02", List.of()),
                new Order("A03", List.of(
                        new Line("BOOK", 1),
                        new Line("BAG", 1)
                ))
        );

        // map keeps one sublist per Order.
        List<List<Line>> nested = orders.stream()
                .map(Order::lines)
                .toList();
        List<Integer> groupSizes = nested.stream()
                .map(List::size)
                .toList();
        System.out.println("Nested group sizes: " + groupSizes);

        // flatMap turns each Order into a Stream<Line>,
        // then merges all order lines into a single stream.
        List<String> flatLabels = orders.stream()
                .flatMap(order -> order.lines().stream())
                .map(line -> line.sku() + "x" + line.quantity())
                .toList();
        System.out.println("Flat lines: " + flatLabels);

        // Preserve the parent order's context before flattening.
        List<OrderLine> details = orders.stream()
                .flatMap(order -> order.lines().stream()
                        .map(line -> new OrderLine(
                                order.id(),
                                line.sku(),
                                line.quantity())))
                .toList();

        List<String> withOrderId = details.stream()
                .map(d -> d.orderId() + ":" + d.sku()
                        + "x" + d.quantity())
                .toList();
        System.out.println("With order ID: " + withOrderId);

        // Combine flatMap, map, distinct, sorted.
        List<String> uniqueSkus = orders.stream()
                .flatMap(order -> order.lines().stream())
                .map(Line::sku)
                .distinct()
                .sorted()
                .toList();
        System.out.println("Unique SKUs: " + uniqueSkus);

        int totalQuantity = orders.stream()
                .flatMap(order -> order.lines().stream())
                .mapToInt(Line::quantity)
                .sum();
        System.out.println("Total quantity: " + totalQuantity);

        // List of lists, with an empty sublist.
        List<List<Integer>> groups =
                List.of(List.of(1, 2), List.of(), List.of(3));
        List<Integer> flattened = groups.stream()
                .flatMap(List::stream)
                .toList();
        System.out.println("Nested numbers: " + flattened);

        // Optional.stream produces 0 or 1 element.
        List<Optional<String>> maybeCodes = List.of(
                Optional.of("A"),
                Optional.empty(),
                Optional.of("B")
        );
        List<String> presentCodes = maybeCodes.stream()
                .flatMap(Optional::stream)
                .toList();
        System.out.println("Present codes: " + presentCodes);

        // Each text segment has multiple words; split then flatten.
        List<String> words = Stream.of("java,stream", "lambda,flatmap")
                .flatMap(line -> Arrays.stream(line.split(",")))
                .map(String::trim)
                .toList();
        System.out.println("Words: " + words);

        // If the mapper returns a null Stream, Stream.flatMap treats it as empty.
        List<String> nullMapped = Stream.of("x", "y")
                .flatMap(value -> value.equals("x")
                        ? null
                        : Stream.of(value.toUpperCase(Locale.ROOT)))
                .toList();
        System.out.println("Null stream result: " + nullMapped);
    }
}
```

Compile and run:

```bash
javac --release 17 FlatMapDemo.java
java FlatMapDemo
```

**Exact stdout:**

```text
Nested group sizes: [2, 0, 2]
Flat lines: [BOOKx2, PENx3, BOOKx1, BAGx1]
With order ID: [A01:BOOKx2, A01:PENx3, A03:BOOKx1, A03:BAGx1]
Unique SKUs: [BAG, BOOK, PEN]
Total quantity: 7
Nested numbers: [1, 2, 3]
Present codes: [A, B]
Words: [java, stream, lambda, flatmap]
Null stream result: [Y]
```

Detailed explanation:

- `groupSizes` is `[2,0,2]`: order A01 has 2 lines, A02 has none, A03 has 2 lines. `map` still preserves all three groups.
- `flatLabels` has four lines because A02 produces an **empty child stream**, emitting no elements into the flat stream.
- `details` preserves the order ID by mapping each `Line` to an `OrderLine` **inside** the `flatMap` function, while the `order` variable is still in the lambda's scope. Thus we know whether each order line came from A01 or A03.
- `uniqueSkus` collects all SKUs, removes duplicates, and sorts them in natural order: `BAG, BOOK, PEN`.
- The total quantity is `2 + 3 + 1 + 1 = 7`. The aggregation uses `mapToInt(...).sum()`, without mutating a shared counter.
- `Optional.empty().stream()` emits no elements; the two Optionals containing A and B each emit one element.
- `Arrays.stream(line.split(","))` turns each input string into a stream of multiple words; `flatMap` concatenates the two word streams into one.
- `Stream.flatMap` **treats a `null` mapper result as an empty stream**. This code only illustrates the contract; intentionally returning null is not recommended in practice.

All `List.of(...)` and `Stream.of(...)` sources have a deterministic encounter order in a sequential program, so `toList()` preserves the element order as shown in stdout. `Stream.toList()` creates a list that does not support modification via `add`/`remove` (Java 16+). Do not interpret that as automatically turning **each element inside** into an immutable object.

## 5. Distinguishing `map` and `flatMap` by Result Type

Consider each order having product lines:

```java
Stream<Order> source = orders.stream();
```

With the `Order.lines()` method returning `List<Line>`:

| Expression | Result type | Conceptual result |
| --- | --- | --- |
| `orders.stream().map(Order::lines)` | `Stream<List<Line>>` | Stream of **sublists** |
| `orders.stream().map(o -> o.lines().stream())` | `Stream<Stream<Line>>` | Stream of **child streams** |
| `orders.stream().flatMap(o -> o.lines().stream())` | `Stream<Line>` | One stream of **all order lines** |
| `orders.stream().flatMap(o -> o.lines().stream()).map(Line::sku)` | `Stream<String>` | One stream of **all SKUs** |

`source` in the opening snippet only illustrates the type; when writing real code, start a new pipeline from `orders.stream()` for each transformation. Do not try to reuse the same `Stream<Order>` object that already has a pipeline attached.

### How Deep Does `flatMap` Flatten?

Suppose the structure is:

```text
List<List<List<Integer>>>
[
  [[1, 2], [3]],
  [[4]]
]
```

One `flatMap(List::stream)` turns `Stream<List<List<Integer>>>` into `Stream<List<Integer>>`, **not yet** into `Stream<Integer>`. You need one more call:

```java
List<List<List<Integer>>> threeLevels = List.of(
        List.of(List.of(1, 2), List.of(3)),
        List.of(List.of(4))
);

List<Integer> numbers = threeLevels.stream()
        .flatMap(List::stream)
        .flatMap(List::stream)
        .toList();

System.out.println(numbers); // [1, 2, 3, 4]
```

This snippet uses the already-imported `List`. Each `flatMap` corresponds to **one level of nesting**. You should not assume the API recursively traverses arbitrary complex objects.

## 6. Turning One Element into 0, 1, or Many Elements

The most powerful aspect of `flatMap` is that each input element can produce a **variable** number of results:

```java
List<String> tokens = Stream.of("a,b", "", "c")
        .flatMap(text -> text.isEmpty()
                ? Stream.empty()
                : Arrays.stream(text.split(",")))
        .toList();

System.out.println(tokens); // [a, b, c]
```

- `"a,b"` produces two results, `a` and `b`.
- `""` produces `Stream.empty()`, meaning it produces no results.
- `"c"` produces one result, `c`.

In problems that previously required multiple nested `for` loops and a mutable `ArrayList` to append elements, `flatMap` lets you express "take each group and flatten it" directly inside the pipeline.

### Avoid Confusing It with `filter`

If each input only needs to decide whether to **keep or discard itself**, `filter` is clearer in intent:

```java
List<Integer> positives = Stream.of(-2, 0, 3, 4)
        .filter(n -> n > 0)
        .toList();
// [3, 4]
```

You could use `flatMap(n -> n > 0 ? Stream.of(n) : Stream.empty())`, but it is usually longer and harder to read. Choose `flatMap` when **there is genuinely a child stream to concatenate** or when the mapper result is a variable number of elements.

## 7. Preserving Parent Element Information When Flattening

A common design mistake is that after flattening the `Line` objects, the author **no longer knows** which order a line belongs to. If the business requirement needs the order ID, you should not just create a `Stream<Line>` and then try to look up the parent information afterward.

The solution is to map the child to a context-carrying record **inside the parent's lambda**:

```java
record OrderLine(String orderId, String sku, int quantity) {}

List<OrderLine> linesWithOrder = orders.stream()
        .flatMap(order -> order.lines().stream()
                .map(line -> new OrderLine(
                        order.id(),
                        line.sku(),
                        line.quantity())))
        .toList();
```

This snippet is an illustration placed in a class that has `Order`, `Line`, and `orders` as in the full example. The transformation flow is:

```text
Order A01
  ├─ Line BOOK x2 ──> OrderLine(A01, BOOK, 2)
  └─ Line PEN  x3 ──> OrderLine(A01, PEN, 3)

Order A02 (no Line) ──> no results

Order A03
  ├─ Line BOOK x1 ──> OrderLine(A03, BOOK, 1)
  └─ Line BAG  x1 ──> OrderLine(A03, BAG, 1)
```

This is a very useful case of **combining `flatMap` with `map`**: `flatMap` enters each group, while `map` converts each child element into a new structure carrying all required business information.

## 8. `Optional.stream()` and `Optional.flatMap()` Are Two Different APIs

### Flattening Multiple Optionals in a Stream

Since Java 9, `Optional<T>.stream()` returns:

- A stream containing **one element** if the Optional has a value.
- An **empty** stream if the Optional is empty.

Therefore:

```java
List<Optional<Integer>> possible = List.of(
        Optional.of(10),
        Optional.empty(),
        Optional.of(20)
);

List<Integer> actual = possible.stream()
        .flatMap(Optional::stream)
        .toList();

System.out.println(actual); // [10, 20]
```

This is a clean way to skip empty Optionals in a list without calling `get()`.

### `Optional.flatMap()` Flattens Nested Optionals

`Optional.flatMap` takes a function returning `Optional<U>`, not `Stream<U>`:

```java
record Account(String id, String email) {}

static Optional<String> safeEmail(Account account) {
    return Optional.ofNullable(account.email());
}

Optional<Account> account =
        Optional.of(new Account("A01", "a@example.com"));

Optional<String> email = account.flatMap(MyClass::safeEmail);
```

This snippet **illustrates the signature**; it must be placed in an appropriately named class and `MyClass` must be replaced with the class containing `safeEmail`. If you write `account.map(MyClass::safeEmail)`, the result has type `Optional<Optional<String>>`, whereas `flatMap` gives `Optional<String>`.

**Differences to remember:**

| API | Mapper returns | Result |
| --- | --- | --- |
| `Stream<T>.flatMap(...)` | `Stream<R>` | `Stream<R>` |
| `Optional<T>.flatMap(...)` | `Optional<R>` | `Optional<R>` |
| `Stream<Optional<T>>.flatMap(Optional::stream)` | `Stream<T>` for each Optional | Flat `Stream<T>` |

`Optional.flatMap` **does not accept a mapper returning a `null` reference**: if the mapper returns null instead of an actual Optional, it throws `NullPointerException`. Meanwhile, `Stream.flatMap` has a different rule for a **mapper returning a `null` stream**, covered in the next section. Do not confuse the contracts of these two APIs just because they share the name `flatMap`.

## 9. Handling Empty Lists, `null` Sources, and Mappers Returning `null`

### Empty Sublists: Normal Usage

```java
List<List<String>> groups = List.of(
        List.of("A"),
        List.of(),
        List.of("B")
);

System.out.println(groups.stream()
        .flatMap(List::stream)
        .toList()); // [A, B]
```

An empty sublist produces an empty stream and does not raise an exception.

### A `null` Sublist: Can Throw NPE

`List.of(...)` does not accept null elements, but mutable collections or legacy data may contain nulls:

```java
List<List<String>> groups = new java.util.ArrayList<>();
groups.add(List.of("A"));
groups.add(null);

 // WRONG at runtime: when encountering null, calling null.stream() throws NPE.
 // groups.stream().flatMap(List::stream).toList();
```

If null is allowed data, normalize it at the boundary or handle it explicitly:

```java
List<String> safe = groups.stream()
        .flatMap(group -> group == null
                ? Stream.<String>empty()
                : group.stream())
        .toList();

System.out.println(safe); // [A]
```

This snippet illustrates using the `groups` list above. However, do not assume by default that every null group is an "empty group": if null actually indicates corrupt data, you should report an error/validate rather than silently discarding it.

### `Stream.flatMap` Has Its Own Contract for Mappers Returning `null`

According to the `Stream.flatMap` API, if the mapper returns `null` instead of a stream, the result is treated as an **empty stream**:

```java
List<String> result = Stream.of("a", "b")
        .flatMap(value -> value.equals("a")
                ? null
                : Stream.of(value))
        .toList();

System.out.println(result); // [b]
```

This snippet is valid according to the contract, but you **should not intentionally return null** just to skip an element. Writing `Stream.empty()` makes the intent clear and avoids confusion with `Optional.flatMap` (where a mapper returning null throws NPE):

```java
.flatMap(value -> condition(value)
        ? Stream.of(value)
        : Stream.empty())
```

The lines above are **part of an illustrative pipeline**, assuming `condition(value)` already exists; they are not a standalone statement.

## 10. `flatMap` Is a Lazy Transformation, Yet Child Streams Still Need Proper Closing

`flatMap` is an **intermediate operation** of Stream. It describes a transformation without necessarily computing the entire result when the pipeline is constructed. When a terminal operation requests elements, the mapper is invoked to create each child stream and its elements are forwarded.

```java
Stream<String> words = Stream.of("A B", "C")
        .flatMap(line -> Arrays.stream(line.split(" ")));

List<String> collected = words.toList(); // [A, B, C]
```

`Stream.flatMap` also has an important contract: **each child stream created by the mapper will be closed after its contents have been placed into the result stream**. This helps manage the child stream lifecycle; however, **opening resource handles** such as files or connections inside the mapper still requires very careful design.

Conceptual example when each source is a file:

```java
// Illustrates the idea, not a standalone program.
// paths.stream().flatMap(path -> {
//     try {
//         return Files.lines(path); // Open file resource.
//     } catch (IOException ex) {
//         throw new UncheckedIOException(ex);
//     }
// });
```

`Files.lines` can throw a checked `IOException` at open time; a file-reading stream can throw `UncheckedIOException` while being consumed. Do not assume that just because `flatMap` automatically closes child streams after normal processing, the entire pipeline becomes free of resource risks, especially if the caller fails to close the source or encounters an unexpected exception/termination point.

In systems that need to process multiple files, you can use `try-with-resources` or design clear resource ownership boundaries, and handle open/close errors according to the contract. If you only need to read each file and collect results, an outer loop combined with `try-with-resources` is sometimes easier to audit than `flatMap` opening resources hidden inside a mapper.

### Short-Circuiting and Side Effects

`findFirst`, `limit`, and `anyMatch` may not need to traverse every element or every child stream. Do not place important side effects inside the mapper assuming it will **always be called exactly once for every parent element**. A more testable approach is for the mapper to only produce data, while database updates or sending emails are performed at a separate boundary.

## 11. Ordering and Parallel Streams

For sources with an encounter order (such as `List`), `flatMap` preserves the corresponding order: traversing each group in source order and the elements within each child stream in that stream's order when the result is collected in encounter order.

```java
List<String> result = List.of(
        List.of("A", "B"),
        List.of("C", "D")
).stream()
 .flatMap(List::stream)
 .toList();

System.out.println(result); // [A, B, C, D]
```

If you switch to `parallel()`, `toList()` still reflects the encounter order of an ordered stream. However, the **timing and execution order** of lambdas/mappers across multiple threads is not a linear order that can be relied upon to control side effects.

Do not do the following with a shared collection:

```java
// Dangerous anti-pattern with parallel stream.
List<String> output = new java.util.ArrayList<>();
// groups.parallelStream()
//       .flatMap(List::stream)
//       .forEach(output::add);
```

`ArrayList` is not safe when multiple threads add elements concurrently. Use an appropriate terminal collector such as `toList` or `collect(...)` so Stream manages the result, instead of manually mutating a shared accumulator in `forEach`.

**Performance note:** `flatMap` can avoid manually building an intermediate sublist at each step if the mapper creates a stream directly. However, that does not mean it is "always fastest"; child stream overhead, object allocation, boxing, data size, and parallel characteristics all matter. For performance requirements, benchmark in the actual context.

## 12. `flatMapToInt`, `flatMapToLong`, `flatMapToDouble`

If the final result consists of primitive numbers, Java provides specialized overloads:

```java
int total = List.of(
        List.of(1, 2),
        List.of(3, 4)
).stream()
 .flatMapToInt(group -> group.stream()
         .mapToInt(Integer::intValue))
 .sum();

System.out.println(total); // 10
```

`flatMapToInt` takes a mapper returning an `IntStream`, rather than a `Stream<Integer>`. This form is useful when you need aggregations like `sum`, `average`, or want to avoid unnecessary boxing/unboxing on the processing path.

In the order example, the following approach is also reasonable:

```java
int totalQuantity = orders.stream()
        .flatMapToInt(order -> order.lines().stream()
                .mapToInt(Line::quantity))
        .sum();
```

Assuming `orders` and `Line` as in the complete example, the result is `7`. The two options `flatMap(...).mapToInt(...)` and `flatMapToInt(...)` share the same goal but differ in the child stream type returned by the mapper. Choose the one that is easier to read and has benchmark evidence when optimization is needed.

## 13. When Should You Use `mapMulti` Instead of `flatMap`?

Since Java 16, `Stream.mapMulti` allows each input to **push 0 or more elements** directly to a consumer, without necessarily constructing a child stream object:

```java
List<Integer> flattened = Stream.of(
        List.of(1, 2),
        List.<Integer>of(),
        List.of(3)
).<Integer>mapMulti((group, downstream) ->
        group.forEach(downstream))
 .toList();

System.out.println(flattened); // [1, 2, 3]
```

`mapMulti` can make sense when each input element typically produces very few results or when avoiding the creation of many small streams is beneficial. However, `flatMap` is usually more intuitive for data already available as a `Collection`/`Stream` and for beginners.

`mapMulti` is not another form of `Function<T,Stream<R>>`: its callback receives the element and a consumer to emit results. Without complex performance/type requirements, `flatMap(List::stream)` is easier to understand and maintain.

## 14. Common Mistakes When Using `flatMap`

| Situation | Cause | How to fix |
| --- | --- | --- |
| `map(List::stream)` then trying to call `Line::sku` | The type at that point is `Stream<Stream<Line>>`, not `Stream<Line>` | Use `flatMap(List::stream)` |
| Using `flatMap(line -> line.sku())` | The mapper returns `String`, not `Stream<R>` | For one result, use `map(Line::sku)` |
| Getting order lines but losing the order ID | Flattening before attaching parent context | Use `flatMap(order -> order.lines().stream().map(...))` |
| An empty group but expecting a placeholder | `flatMap` emits 0 elements from an empty child stream | If a placeholder is needed, create it explicitly |
| A `null` sublist | Calling `null.stream()` throws NPE | Validate or return `Stream.empty()` if null is valid |
| Mapper returns `null` Optional thinking it behaves like `Stream.flatMap` | `Optional.flatMap` requires a non-null Optional | Return `Optional.empty()` |
| Using `Optional.get()` to filter out empty values | `get()` throws when empty | `flatMap(Optional::stream)` |
| Thinking `flatMap` flattens all levels | Each call handles one stream level | Chain multiple `flatMap` calls matching the data types |
| Manually adding to an `ArrayList` from parallel `forEach` | Race conditions and unguaranteed ordering | `toList` or an appropriate collector |
| Mapper has side effects required to run for every element | Streams are lazy/short-circuiting | Separate side effects out and design invocation counts explicitly |
| Creating child streams holding resources without understanding lifecycle | Can cause I/O errors or hard-to-control resource closing | Identify the owner and close resources per contract |
| Using `flatMap` when only a 1→1 transformation is needed | Unclear code intent, extra intermediate stream | Use `map` |

## 15. Practice Exercises

1. Given `List.of(List.of("A","B"), List.of(), List.of("C"))`, write an expression that returns `["A","B","C"]` using `flatMap(List::stream)`. Explain why the empty group does not appear.
2. Given `orders` in `FlatMapDemo`, use `map(Order::lines)` and inspect the return type and number of elements **at the outer level**. Then switch to `flatMap(o -> o.lines().stream())` and state how many order lines are emitted.
3. Create a list of `OrderLine(orderId, sku, quantity)` preserving the order ID context. Why should you not wait until after `flatMap` to look up the Order again?
4. Write a `flatMap` that splits the list of strings `["a,b", "", "c,d"]` into `["a","b","c","d"]`. Handle the empty string with `Stream.empty()`.
5. Given a `List<Optional<Integer>>` containing `Optional.of(1)`, `Optional.empty()`, `Optional.of(3)`, use `flatMap(Optional::stream)` followed by `mapToInt(Integer::intValue).sum()`. **Result:** 4.
6. Predict `Stream.of("a","b").flatMap(s -> s.equals("a") ? null : Stream.of(s)).toList()`. Explain why the result is `[b]` and why `Stream.empty()` should be used instead of null in new code.
7. Create a `List<List<List<Integer>>>` source. Write two `flatMap(List::stream)` calls to produce `List<Integer>` and explain the intermediate types.
8. Fix a program that attempts `group.stream()` when `group == null`. When should null be treated as an allowed empty group, and when should it fail fast?
9. Write a `flatMapToInt` version to calculate the total quantity of all order lines across orders. Compare it with `flatMap(...).mapToInt(...)`.
10. From a list of text segments, write a pipeline that splits words, normalizes to lowercase with `Locale.ROOT`, filters out empty words, and applies `distinct` and `sorted`. Predict the type at each step.
11. Give a scenario where `flatMap` is inappropriate even though the data has sublists: for example, needing to display order lines **grouped by each order**. How should you keep `List<List<Line>>` or model the group?
12. Compare `flatMap` and `mapMulti` when the input data is very large but each element produces one or two results; propose running a real benchmark before choosing based on performance.

## 16. Pre-Implementation Checklist

- Does the mapper need to return **a single value** or **a stream of values**?
- Is the truly desired output type `Stream<R>` or `Stream<Stream<R>>`?
- Do you need to preserve **parent element context** before flattening?
- Can a group be **empty** or a **`null` reference**, and what is the business rule?
- Are you using `Optional`: is `Optional::stream` or `Optional.flatMap` the right fit for the goal?
- Do child streams hold any I/O resources that need closing and error handling?
- Does the pipeline have side effects or run in parallel; do you need to avoid mutable shared state?
- Are you confusing `filter` (keep/discard) with `flatMap` (produce 0..n elements), or `map` (one output)?
- Have you checked **result ordering**, duplicate records, empty lists, and counts after flattening?

**Remember:** `map` preserves a one-element-to-one-element structure; `flatMap` takes a stream for each input and then **concatenates the child elements into a flat stream**. It is a core tool for handling nested collections, multi-line orders, word splitting, and combining with `Optional.stream()`. Using the right signature, handling empty/null groups per contract, and preserving parent context before flattening will keep your pipelines clear, testable, and less error-prone.
