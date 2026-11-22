# Distinguishing map() Creating a Nested Stream from flatMap() in Java

## 1. The Core Question: How Many Data Levels Remain After Transformation?

When working with `Stream` in Java, both `map()` and `flatMap()` accept an element transformation function. The most important difference is **the shape of the result**:

- **`map()`** transforms **each input element into exactly one mapped result** (a single result object, even if that object is a collection or a `Stream`). The method **does not automatically remove nesting levels**.
- **`flatMap()`** transforms each element into **a sub-`Stream`** and then **flattens** the elements of those sub-streams into **a single result `Stream`**. A single source element can produce **0, 1, or many** output elements.

Imagine an input with three lists:

~~~text
[ ["java", "stream"], [], ["lambda"] ]
~~~

With `map(List::stream)`, we get **one stream containing three sub-streams**:

~~~text
Stream<Stream<String>>
  ├── Stream("java", "stream")
  ├── Stream()
  └── Stream("lambda")
~~~

With `flatMap(List::stream)`, the elements are placed into a single shared stream:

~~~text
Stream<String>  →  "java", "stream", "lambda"
~~~

The key point is not that `map` is "wrong" and `flatMap` is "right". **`map` is right when you want to keep each result as a separate element** (for example, preserving each group). **`flatMap` is right when you want to concatenate the inner elements into one flat stream** for further filtering, counting, searching, sorting, or collecting.

## 2. Generic Signatures Help Distinguish Them Quickly

The two methods on `Stream<T>` have simplified signatures:

~~~java
<R> Stream<R> map(Function<? super T, ? extends R> mapper);

<R> Stream<R> flatMap(
        Function<? super T, ? extends Stream<? extends R>> mapper);
~~~

These are **illustrative API signatures**, not code redeclaring `Stream`.

Look at the type of **the value returned by the mapper**:

| Criterion | `map()` | `flatMap()` |
|---|---|---|
| Source input | `Stream<T>` | `Stream<T>` |
| Mapper | `T → R` | `T → Stream<R>` (simplified type view) |
| API result | `Stream<R>` | `Stream<R>` |
| One `T` element produces | One `R` | 0, 1, or many `R` |
| When mapper returns `Stream<U>` | `R = Stream<U>`, resulting in `Stream<Stream<U>>` | Unwraps `U` elements from each sub-stream, resulting in `Stream<U>` |
| Use when | Transforming each element while keeping each result as one unit | Splitting and concatenating, flattening groups or sub-sources |
| Example mappers | `String::length` | `List::stream`, `Optional::stream` |

`flatMap` **does not directly accept `List<R>` as the mapper result**. When starting from an inner list, you must convert it to a stream via `list.stream()`. A valid example is `flatMap(List::stream)`; an example like `flatMap(group -> group)` is invalid if `group` has type `List<String>`.

### 2.1. Why Can map Create a Nested Stream?

Consider a `Stream<List<String>>` source. With:

~~~java
Stream<Stream<String>> nested = groups.stream().map(List::stream);
~~~

- `T` of the source stream is `List<String>`.
- The mapper `List::stream` takes a `List<String>` and returns `Stream<String>`.
- By the `map` contract, each returned `Stream<String>` object becomes **one element `R`** of the outer stream.
- Thus `R` is `Stream<String>`, so the result is `Stream<Stream<String>>`.

Meanwhile:

~~~java
Stream<String> flat = groups.stream().flatMap(List::stream);
~~~

- The mapper still produces `Stream<String>`.
- However, `flatMap` **consumes and flattens** each sub-stream, placing the `String` elements into the result stream.
- The result has type `Stream<String>`, with no inner `Stream<...>` level remaining.

Both statements are **illustrative snippets requiring a `groups` variable of type `List<List<String>>` and imports `java.util.List`, `java.util.stream.Stream`**.

## 3. Visualizing map and flatMap by Element Count

Given input data with three groups:

~~~text
Source:      ["a", "b"]       []         ["c", "d", "e"]
                │             │                │
map(stream):   Stream(2)    Stream(0)        Stream(3)
                └──────── Stream<Stream<String>> ────────┘
flatMap:         "a" "b"      (empty)          "c" "d" "e"
                └────────── Stream<String> ─────────────┘
~~~

An easy-to-remember observation: `map()` produces **one mapped result per source element when the element is processed**, whereas `flatMap()` can **make an empty group disappear** or **expand a multi-element group**. This describes the *logical* element count and does not guarantee how many times the callback will run in a pipeline with short-circuiting or Stream optimizations.

If you need to call `String::toUpperCase` on each word afterward, `flatMap` keeps the code simpler:

~~~java
List<String> upper = groups.stream()
        .flatMap(List::stream)
        .map(String::toUpperCase)
        .toList();
~~~

The result is a flat list. If you kept `map(List::stream)`, you would have `Stream<Stream<String>>` and `map(String::toUpperCase)` on the outer level **would not type-check**: the outer elements are `Stream<String>`, not `String`.

## 4. Complete Java 17 Program: Observing Both Result Types

Save as **`MapFlatMapDemo.java`**:

~~~java
import java.util.List;
import java.util.stream.Stream;

public class MapFlatMapDemo {
    public static void main(String[] args) {
        List<List<String>> groups = List.of(
                List.of("java", "stream"),
                List.of(),
                List.of("lambda")
        );

        Stream<Stream<String>> nested =
                groups.stream().map(List::stream);

        List<List<String>> nestedValues = nested
                .map(Stream::toList)
                .toList();

        List<String> flattened = groups.stream()
                .flatMap(List::stream)
                .toList();

        List<String> upper = groups.stream()
                .flatMap(List::stream)
                .map(String::toUpperCase)
                .toList();

        int totalLength = groups.stream()
                .flatMap(List::stream)
                .mapToInt(String::length)
                .sum();

        System.out.println("nested=" + nestedValues);
        System.out.println("flat=" + flattened);
        System.out.println("upper=" + upper);
        System.out.println("length=" + totalLength);
    }
}
~~~

Compile and run with **JDK 17+**:

~~~bash
javac MapFlatMapDemo.java
java MapFlatMapDemo
~~~

Exact stdout:

~~~text
nested=[[java, stream], [], [lambda]]
flat=[java, stream, lambda]
upper=[JAVA, STREAM, LAMBDA]
length=16
~~~

**Pipeline-by-pipeline explanation:**

1. `groups` consists of three sub-lists; the second list is empty.
2. `map(List::stream)` creates a `Stream<Stream<String>>`. To **print the values** without relying on the `toString()` of a `Stream` object, the program converts each sub-stream into a `List<String>` using `map(Stream::toList)`. The resulting list is still **nested**, including the empty list.
3. `flatMap(List::stream)` spreads the `String` elements from the three sub-lists into a single stream, producing `[java, stream, lambda]`. The empty group contributes no elements.
4. After `flatMap`, `map(String::toUpperCase)` operates directly on each `String`; `Stream.toList()` collects the results.
5. `mapToInt(String::length).sum()` works with `IntStream` to sum the string lengths: `4 + 6 + 6 = 16`.
6. Each processing step needs **a new source pipeline**. `nested` has already been consumed by `toList()`; calling a second terminal operation on it is invalid. Therefore, the subsequent pipelines use a fresh `groups.stream()`.

The code uses `Stream.toList()`, added in Java 16, which is suitable for JDK 17. In this example, the stream is sequential and the `List` sources are ordered, so the output is printed in a predictable order.

## 5. Use map When Preserving Groups, flatMap When Merging Groups

Suppose an application has each department and its list of employees:

~~~java
record Department(String name, List<String> members) {}
~~~

If you want to summarize the employee count **by department**, the natural choice is **`map`** so each department produces one summary result:

~~~java
List<String> counts = departments.stream()
        .map(d -> d.name() + ":" + d.members().size())
        .toList();
~~~

The result has **one entry per department**, because the requirement wants to preserve group information.

If you want **a single list of employee names across the entire organization**:

~~~java
List<String> allMembers = departments.stream()
        .flatMap(d -> d.members().stream())
        .toList();
~~~

This is an appropriate example for **`flatMap`**, because each department has a varying number of employees and we want to combine them all into one stream of names.

Both snippets above are **illustrative code placed in a context where `departments` of type `List<Department>` is already declared**; there is no `main` method to run standalone.

### 5.1. A flatMap Step Can Still Combine with map

When you need to attach the department label to each employee:

~~~java
List<String> labeled = departments.stream()
        .flatMap(d -> d.members().stream()
                .map(member -> d.name() + "/" + member))
        .toList();
~~~

Inside the `flatMap` mapper, we call `map` on the **sub-stream** to create strings containing the department info, and then `flatMap` merges those strings into a single stream. **`map` and `flatMap` are not mutually exclusive**: they are often combined to preserve the parent element's context while emitting multiple child elements.

This is also a situation where a lambda is clearer than `flatMap(Department::members)`: the `members()` method returns `List<String>`, not `Stream<String>`, and we also need to prepend the department name to each string.

## 6. Java 17 Program: From Orders to Order Lines

Save as **`OrderFlatMapDemo.java`**:

~~~java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class OrderFlatMapDemo {
    record Line(String sku, int quantity) {}
    record Order(String code, List<Line> lines) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("A", List.of(
                        new Line("pen", 2),
                        new Line("book", 1))),
                new Order("B", List.of()),
                new Order("C", List.of(
                        new Line("pen", 3)))
        );

        List<String> labeled = orders.stream()
                .flatMap(order -> order.lines().stream()
                        .map(line -> order.code()
                                + "/" + line.sku()
                                + "=" + line.quantity()))
                .toList();

        Map<String, Integer> quantities = orders.stream()
                .flatMap(order -> order.lines().stream())
                .collect(Collectors.groupingBy(
                        Line::sku,
                        TreeMap::new,
                        Collectors.summingInt(Line::quantity)
                ));

        List<String> nonEmptyOrders = orders.stream()
                .filter(order -> !order.lines().isEmpty())
                .map(Order::code)
                .toList();

        System.out.println("labeled=" + labeled);
        System.out.println("quantities=" + quantities);
        System.out.println("orders=" + nonEmptyOrders);
    }
}
~~~

Compile/run commands:

~~~bash
javac OrderFlatMapDemo.java
java OrderFlatMapDemo
~~~

Stdout:

~~~text
labeled=[A/pen=2, A/book=1, C/pen=3]
quantities={book=1, pen=5}
orders=[A, C]
~~~

**Why is the output correct?**

1. `orders` consists of three orders: `A` has two line items, `B` has an empty list, and `C` has one line item.
2. In `flatMap(order -> ...)`, each order produces a sub-stream of `Line` objects. The inner `map` converts each line item into a string carrying both the order code and the item SKU. `flatMap` combines them into three strings; order `B` produces no lines.
3. `flatMap(order -> order.lines().stream())` puts the `Line` objects from all orders into one stream, and then `groupingBy(Line::sku, TreeMap::new, summingInt(...))` aggregates quantities by `sku`. `pen` has `2 + 3 = 5`; `book` has `1`. `TreeMap` guarantees key order when printing.
4. `filter(...).map(Order::code)` still keeps **each order as one source element**, merely filtering out orders with an empty list and extracting the order code. There is no need for `flatMap` because this requirement is "one order → one code", not "one order → many line items".
5. Flattening can lose group boundaries. If order information matters, preserve it in the result—such as a labeled string, a record holding both `orderCode` and `Line`, or a data structure with an explicit parent-child relationship.

A noteworthy design guideline: `flatMap` is a great fit for **one-to-many** relationships, but if business logic needs to aggregate **per parent**, do not flatten too early and then have to reconstruct the group information.

## 7. Turning Empty Collections or Empty Optionals into 0 Elements

### 7.1. Empty Sub-Lists

With `groups.stream().flatMap(List::stream)`, an empty sub-list produces a sub-stream with **no elements**, so it contributes nothing to the result. You do not need to add `filter(list -> !list.isEmpty())` just to avoid empty elements, unless the filter expresses a separate business condition.

### 7.2. Optional.stream() Combined with flatMap

Since **Java 9**, `Optional<T>` has a `stream()` method:

- If the `Optional` holds a value, `stream()` creates a one-element stream.
- If the `Optional` is empty, `stream()` creates an empty stream.

Therefore, you can turn a `Stream<Optional<T>>` into a `Stream<T>` with:

~~~java
List<String> values = optionals.stream()
        .flatMap(Optional::stream)
        .toList();
~~~

This is an illustrative snippet; `optionals` must have type `List<Optional<String>>` or a compatible type. This form clearly expresses "take the present values, skip the empty Optionals." It is not a call to `Optional.flatMap`; this is **`Stream.flatMap` combined with `Optional.stream`**, two different APIs.

### 7.3. Complete Java Example

Save as **`OptionalFlattenDemo.java`**:

~~~java
import java.util.List;
import java.util.Optional;

public class OptionalFlattenDemo {
    public static void main(String[] args) {
        List<Optional<String>> optionals = List.of(
                Optional.of("alpha"),
                Optional.empty(),
                Optional.of("beta")
        );

        List<List<String>> nested = optionals.stream()
                .map(value -> value.stream().toList())
                .toList();

        List<String> flat = optionals.stream()
                .flatMap(Optional::stream)
                .toList();

        System.out.println("nested=" + nested);
        System.out.println("flat=" + flat);
        System.out.println("count=" + flat.size());
    }
}
~~~

Compile/run:

~~~bash
javac OptionalFlattenDemo.java
java OptionalFlattenDemo
~~~

Stdout:

~~~text
nested=[[alpha], [], [beta]]
flat=[alpha, beta]
count=2
~~~

In `nested`, each `Optional` still corresponds to a **sub-list**, including the empty list. In `flat`, the result contains only the two actual values. Which approach you choose depends on whether you need to **preserve positions/association with the original object** or **only extract present values**.

## 8. `flatMap` with Strings: Splitting One Element into Multiple Tokens

A common scenario is a line of text containing multiple words. If you use:

~~~java
List<String[]> arrays = lines.stream()
        .map(line -> line.split("\\s+"))
        .toList();
~~~

The result is `List<String[]>`, where each line corresponds to its own array. This is right if you want to keep each line as a group.

If you want a flat list of words:

~~~java
List<String> words = lines.stream()
        .flatMap(line -> java.util.Arrays.stream(line.split("\\s+")))
        .toList();
~~~

Here `Arrays.stream(String[])` turns the token array of one line into a `Stream<String>`, and `flatMap` concatenates the tokens.

**Input note:** for empty lines, whitespace-only strings, punctuation, or various whitespace forms, `split("\\s+")` has edge cases you should check against your real data; if exact handling is needed, intentionally `strip()` and discard empty elements before collecting.

A suitable pattern for normalized strings is:

~~~java
List<String> words = lines.stream()
        .map(String::strip)
        .filter(line -> !line.isEmpty())
        .flatMap(line -> java.util.Arrays.stream(line.split("\\s+")))
        .toList();
~~~

If the input `lines` contains `null`, `String::strip` will throw a `NullPointerException`. Define your data policy before choosing the pipeline.

## 9. `flatMap` and null: Two Different Cases

**Case 1 — the mapper itself returns `null` instead of a stream:** by the `Stream.flatMap` contract, a mapped stream equal to `null` is **treated as an empty stream**. However, intentionally returning `null` makes the mapper harder to read and can hide bugs; prefer returning `Stream.empty()` explicitly.

~~~java
// Valid conceptually; returning Stream.empty() is clearer than returning null.
Stream<String> result = names.stream()
        .flatMap(name -> name.isBlank()
                ? Stream.empty()
                : Stream.of(name));
~~~

**Case 2 — a source element is `null` and the mapper calls a method on it:**

~~~java
// May throw NullPointerException if list == null.
source.stream().flatMap(List::stream);
~~~

`flatMap` does not automatically guard against `null` in **input elements**. If the source can contain null lists, you need a handling rule:

~~~java
Stream<String> result = source.stream()
        .flatMap(group -> group == null
                ? Stream.empty()
                : group.stream());
~~~

The last two snippets are **illustrative code**, requiring appropriate `Stream` types and `names` or `source` inputs. `List.of(...)` itself rejects null elements when creating a list, but other sources can still contain `null`.

**Additional distinction:** `map` can return a `null` result element; in that case the outer stream still contains **a null element** at the corresponding position. When `flatMap` receives a null mapped stream, it treats it as an empty sub-stream. This is a contract difference between the two operations, not a reason to write mappers that return null.

## 10. Laziness, Short-Circuiting, and Mapper Invocation Count

`map` and `flatMap` are **intermediate operations**. They set up the pipeline and usually do not invoke the mapper at construction time. Actual work happens when a **terminal operation** such as `toList()`, `count()`, or `findFirst()` is invoked, though the compiler/JVM and Stream API may optimize certain pipelines, so you must not rely on the number of times a mapper runs as a side-effect protocol.

### 10.1. `map()` Is Usually a Logical One-to-One Transformation

~~~java
List<Integer> lengths = List.of("a", "bb", "ccc").stream()
        .map(String::length)
        .toList();
// [1, 2, 3]
~~~

This is a per-element value transformation. If `filter` is used afterward, some results will be discarded; if short-circuiting is used, the pipeline may stop early. Do not assume that every mapper in every pipeline always runs exactly once for each initial element.

### 10.2. `flatMap` Can Produce Many Elements, Yet Downstream Stops Early

~~~java
Optional<String> first = List.of(
        List.of("a", "b"),
        List.of("c", "d")
).stream()
 .flatMap(List::stream)
 .findFirst();
~~~

The result `first` is `Optional.of("a")` in the ordered sequential pipeline above. Because the terminal operation `findFirst()` can stop early, downstream **does not need** to consume all sub-streams. Therefore, do not put mandatory business actions inside a mapper and expect all groups to be processed.

### 10.3. `flatMap` Does Not Mean Parallel Execution

`flatMap` only changes the pipeline structure. It **does not spawn threads**, does not mean "execute asynchronously", and does not guarantee better performance than `map`. Using `parallel()` is a separate decision with its own requirements around thread safety and ordering.

### 10.4. Side Effects in a Mapper Cause Unpredictability

~~~java
// Should not be used as an exact guarantee of how many times audit is recorded:
stream.flatMap(item -> {
    audit(item);           // side effect
    return item.children().stream();
});
~~~

If traversal is short-circuited, `audit(item)` may not run for every element. With optimizable sources and terminal operations, do not treat an intermediate operation's side effect as mandatory logic. Separate audit/transaction logging into its own business flow or use a design with explicit control.

## 11. Sub-Stream Lifecycle and Resource Management

According to the Java API, when `flatMap` receives a non-null mapped stream, **the mapped stream is closed after its contents have been placed into the result**. This is useful when a mapper creates sub-streams with their own lifecycle.

However, do **not** assume all external resources are automatically closed just because you called `flatMap`:

- The outer source stream may be backed by a file or resource that must be closed separately.
- If you use `Files.lines(path)` as the outer source, you must consider `try-with-resources` to close that stream.
- A mapper might open resources in a way not tied to the sub-stream's lifecycle; closing the sub-stream does not automatically close resources that are not attached to it.
- For I/O checked exceptions, `Function.apply` in `flatMap` does not declare `throws IOException`, so you cannot propagate a checked exception out of the lambda without handling it.

Illustrative example of a file source lifecycle:

~~~java
// Assume path is a valid java.nio.file.Path.
try (Stream<String> lines = java.nio.file.Files.lines(path)) {
    List<String> words = lines
            .flatMap(line -> java.util.Arrays.stream(line.split("\\s+")))
            .toList();
}
~~~

This is an **illustrative code snippet** that must be placed in a method that handles or declares `IOException` and imports `Stream` and `List`. The key point is `try-with-resources` for **the source stream holding the file resource**, not turning `flatMap` into an automatic manager for every resource.

In practice, when dealing with large data, you must also consider that `toList()` collects the entire result in memory. Choose a streaming terminal operation, batch processing, or data limits as required.

## 12. Comparison with `mapMulti` and Primitive Variants

Java provides additional related APIs, but **do not confuse them with the essence of `flatMap`**:

| API | Purpose | Result |
|---|---|---|
| `Stream.map` | One element → one result object | `Stream<R>` |
| `Stream.flatMap` | One element → sub-stream → flatten | `Stream<R>` |
| `Stream.flatMapToInt` | One element → sub-`IntStream` → flatten | `IntStream` |
| `Stream.flatMapToLong` | One element → sub-`LongStream` → flatten | `LongStream` |
| `Stream.flatMapToDouble` | One element → sub-`DoubleStream` → flatten | `DoubleStream` |
| `Stream.mapMulti` (Java 16+) | One element can emit 0..n results via a consumer | `Stream<R>` |

Example of flattening `int` lists stored in `List<List<Integer>>` when a primitive result is needed:

~~~java
int total = numbers.stream()
        .flatMapToInt(group -> group.stream()
                .mapToInt(Integer::intValue))
        .sum();
~~~

Here the `flatMapToInt` mapper returns a sub-`IntStream`, not `Stream<Integer>`. `sum()` operates on primitive `int`, avoiding some boxing overhead of an object pipeline. This snippet is illustrative and requires `numbers` of type `List<List<Integer>>`.

An example of `mapMulti` to emit multiple results:

~~~java
List<Integer> flat = groups.stream()
        .<Integer>mapMulti((group, downstream) -> {
            for (Integer value : group) {
                downstream.accept(value);
            }
        })
        .toList();
~~~

`mapMulti` can be useful when creating a sub-stream for every element is unnecessary or when the number of output elements per source is small; however, it uses a push-based callback style and is not the most readable choice by default. For familiar nested lists, `flatMap(List::stream)` usually expresses intent more clearly.

**Choose the API by output type:** if flattening objects, `flatMap`; if flattening primitives, consider `flatMapToInt`; if you need consumer-controlled emission and are on Java 16+, look at `mapMulti`.

## 13. Common Mistakes and How to Fix Them

### Mistake 1: Using map and thinking the stream is already flat

~~~java
// The type is Stream<Stream<String>>, NOT Stream<String>.
// Stream<String> wrong = groups.stream().map(List::stream);
~~~

Fix when you want `String` elements:

~~~java
Stream<String> words = groups.stream().flatMap(List::stream);
~~~

If you want to **keep** the sub-streams as separate units, `map` is not wrong at all; in that case, declare the variable with the proper type `Stream<Stream<String>>` and manage how the sub-streams are consumed.

### Mistake 2: Returning a List directly from a flatMap mapper

~~~java
// WRONG: flatMap requires the mapper to return a Stream.
// groups.stream().flatMap(group -> group);
~~~

Correct:

~~~java
groups.stream().flatMap(List::stream);
~~~

### Mistake 3: Using flatMap for a one-to-one problem

~~~java
// Verbose when you only want to turn each String into its length.
List<Integer> a = words.stream()
        .flatMap(word -> Stream.of(word.length()))
        .toList();

// Clearer:
List<Integer> b = words.stream().map(String::length).toList();
~~~

`flatMap` on the first line may still be valid, but it creates an unnecessary sub-stream layer. `map` expresses a one-to-one relationship better.

### Mistake 4: Using flatMap too early and losing parent info

If you must report by order, `orders.stream().flatMap(o -> o.lines().stream())` leaves only the line items; the order code may no longer be available in each `Line`. The fix is to keep the parent info in the result object or perform per-order aggregation **before** flattening.

### Mistake 5: Not handling null elements

`groups.stream().flatMap(List::stream)` can throw `NullPointerException` if there is a `null` group. When the data allows null, use `filter(Objects::nonNull)` or a lambda returning `Stream.empty()` according to your agreed policy.

### Mistake 6: Reusing a stream after a terminal operation

~~~java
Stream<String> stream = groups.stream().flatMap(List::stream);
long count = stream.count();
// stream.toList();  // WRONG: the stream has already been consumed.
~~~

To collect again, create a new pipeline from an appropriate source. A stream has a single-use lifecycle; it is not a collection you can iterate over repeatedly at will.

### Mistake 7: Believing `flatMap` always improves performance

`flatMap` may need to create or manage many sub-streams, whereas `map` is usually simpler for one-to-one transformations. For large volumes, benchmark in practice and examine your data organization; do not replace `map` with `flatMap` just because the name sounds "more powerful".

### Mistake 8: Assuming flatMap handles EOF on its own

`flatMap` flattens sub-streams; it does **not** turn an infinite source into a finite one. If any sub-stream is infinite, the pipeline may never advance to the next group or never terminate. You need explicit stopping conditions and an appropriate source design.

## 14. Checklist for Choosing the Right Transformation

Before writing a pipeline, ask:

1. **What element type does the source have?** `Stream<String>`, `Stream<List<String>>`, or `Stream<Optional<String>>`?
2. **How many output values should one input element produce?** One, zero, or many?
3. **Do group boundaries need to be preserved?** If yes, `map` is usually appropriate; if all child elements need to be merged, `flatMap`.
4. **What type does the mapper return?** `R` or `Stream<R>`? `flatMap` requires a sub-stream.
5. **Should the result be `Stream<R>` or a primitive stream?** Look at `flatMapToInt` and its variants when needed.
6. **Does parent info need to be kept in the flattened elements?** If so, create a record or attach parent data inside the mapper.
7. **Are there empty/null groups?** Define a policy for them.
8. **Is there short-circuiting, parallelism, or resource handling?** Do not blindly rely on side-effect order/count; close sources that need closing.
9. **Can `Optional::stream` be used?** When the source is Optional and you want to skip empty entries, this is a concise choice.
10. **Will readers understand the type shape after each step?** When it gets hard to read, introduce an intermediate variable with an explicit type to verify.

A very effective debugging tip: temporarily declare the intermediate type explicitly, e.g., `Stream<Stream<String>>` contrasted with `Stream<String>`. The compiler will reveal where a stream layer was added or missed.

## 15. Self-Check Questions

**Question 1.** Given `List<List<Integer>>`, what is the type of `groups.stream().map(List::stream)`?

**Question 2.** What is the type of `groups.stream().flatMap(List::stream)`? How many elements does an empty group contribute?

**Question 3.** Why is `flatMap(group -> group)` invalid when `group` is `List<String>`?

**Question 4.** In what way is `map(String::length)` preferable to `flatMap(s -> Stream.of(s.length()))`?

**Question 5.** Given `Stream<Optional<String>>`, what expression can be used to collect the present values?

**Question 6.** If you need to preserve the order code when flattening line items, what should you do?

**Question 7.** Can you rely on the `flatMap` mapper always being called once for every source element in a pipeline with `findFirst()`?

**Question 8.** If the source contains `null` and the mapper calls `List::stream`, what can happen?

**Question 9.** When you need an `IntStream` containing all numbers from sub-streams, which API should you look at?

**Short answers:**

1. `Stream<Stream<Integer>>`: each element of the outer stream is a sub-stream.
2. `Stream<Integer>`; an empty group contributes `0` elements.
3. Because the mapper of `flatMap` must return `Stream<? extends R>`, not `List<R>`.
4. `map` directly expresses a one-to-one transformation and avoids creating unnecessary sub-streams.
5. `flatMap(Optional::stream)`, available since Java 9.
6. Map each `Line` together with the order code into a record/DTO or labeled data before the results are flattened.
7. No; short-circuiting can stop traversal early, and the Stream API allows applicable optimizations.
8. `NullPointerException` if the mapper dereferences a null value.
9. `flatMapToInt` with a mapper returning an `IntStream`.
  
## 16. Official Documentation

- [Java SE 17 API — Stream.map](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#map(java.util.function.Function)): transforms each element into a single result.
- [Java SE 17 API — Stream.flatMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#flatMap(java.util.function.Function)): flattens sub-streams, behavior with a null mapped stream, and sub-stream lifecycle.
- [Java SE 17 API — Stream.mapMulti](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#mapMulti(java.util.function.BiConsumer)): emits multiple results in a callback style.
- [Java SE 17 API — Optional.stream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Optional.html#stream()): a present Optional becomes a one-element stream; an empty one becomes an empty stream.
- [Java SE 17 API — Stream.toList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#toList()): collects results into a list.

**Takeaway:** `map()` keeps **each mapped result as a single element**; if the mapper result is `Stream<U>`, the outer type will be `Stream<Stream<U>>`. Use `flatMap()` when the mapper returns **a sub-stream** and you want to merge all child elements into **one flat `Stream<U>`**. Choose based on **data types and whether you need to preserve groups or flatten**, not merely on which syntax is shorter.