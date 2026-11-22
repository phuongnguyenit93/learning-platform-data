# Joining Strings with `joining` Using Delimiters, Prefixes, and Suffixes

> **Chapter:** Composed Collectors and Aggregation  
> **Module:** `JAVA_STREAM_API` — learn declarative data processing with the Java Stream API through lazy pipelines, `filter`, `map`, `reduce`, and `collect`; practice grouping, custom collectors, `Spliterator`, parallel processing, and Stream Gatherers, while recognizing constraints around state, resources, and performance.

In order-management, reporting, or UI rendering applications, we often need to turn a collection of elements into **a single string**: a comma-separated list of product codes, labels wrapped in square brackets, or product names joined per category. When concatenating strings manually in a loop, you have to handle the first element, last element, delimiter, and empty-list case yourself. The Java Stream API provides `Collectors.joining` to express these rules directly.

After this lesson, you can:

- Correctly use the three overloads `joining()`, `joining(delimiter)`, and `joining(delimiter, prefix, suffix)`.
- Combine `map`, `filter`, `distinct`, and `sorted` with `joining`, and distinguish results on an empty Stream.
- Join data **by group** using `groupingBy`, `mapping`, `filtering`, and downstream collectors.
- Understand string-joining limitations when data contains `null`, contains delimiter characters, comes from infinite sources, or needs ordering in parallel execution.

## 1. What is `Collectors.joining`?

`Collectors.joining` is a **collector** that accepts `CharSequence` elements (such as `String`) and produces a `String`. It only describes how data is accumulated; Stream traversal occurs when the terminal operation `collect` is invoked.

```java
import java.util.List;
import java.util.stream.Collectors;

List<String> languages = List.of("Java", "Kotlin", "Scala");

String result = languages.stream()
        .collect(Collectors.joining(", "));

System.out.println(result); // Java, Kotlin, Scala
```

Processing flow:

```text
List<String>
   │
   ▼
 stream()
   │
   ├── "Java"
   ├── "Kotlin"
   └── "Scala"
   │
   ▼
 collect(Collectors.joining(", "))
   │
   ▼
 "Java, Kotlin, Scala"
```

In the example, `", "` is the **delimiter**. The collector places the delimiter **between** adjacent elements, without adding it at the start or end.

**Key point:** `joining` differs from `map`. `map` transforms each element while still producing a Stream; `collect(joining(...))` **terminates** the pipeline and combines all elements into one string.

## 2. Three overloads of `Collectors.joining`

Java provides three methods with the following general structure:

```java
// Inserts no delimiter.
Collectors.joining()

// Inserts delimiter between elements.
Collectors.joining(CharSequence delimiter)

// Adds prefix before the entire result and suffix after the entire result.
Collectors.joining(
        CharSequence delimiter,
        CharSequence prefix,
        CharSequence suffix
)
```

They return a `Collector<CharSequence, ?, String>`. `prefix` and `suffix` **wrap the entire joined string**, and are not repeated before and after each element.

| Call | Stream of `"A", "B", "C"` | Meaning |
| --- | --- | --- |
| `joining()` | `ABC` | Concatenates strings directly. |
| `joining(", ")` | `A, B, C` | Inserts a comma and space between elements. |
| `joining(" / ", "[", "]")` | `[A / B / C]` | Delimiter, prefix, and suffix. |
| `joining("\n", "", "")` | Each value on its own line | Newline character as delimiter. |

### 2.1. Concatenating directly with `joining()`

```java
String code = List.of("VN", "-", "2026", "-", "001").stream()
        .collect(Collectors.joining());

System.out.println(code); // VN-2026-001
```

Having no delimiter does not require elements to have the same length; the collector simply concatenates content in the element order supplied by the pipeline.

### 2.2. Choosing a delimiter with `joining(delimiter)`

```java
List<String> tags = List.of("stream", "collector", "java");

String csvLike = tags.stream()
        .collect(Collectors.joining(","));
// stream,collector,java

String pathPart = tags.stream()
        .collect(Collectors.joining("/"));
// stream/collector/java
```

The example above only produces a delimited string; it is **not** safe CSV encoding or URL path encoding. If data contains commas, slashes, or special characters, the application must apply escaping/encoding rules for the target format.

### 2.3. Wrapping the whole result with prefix and suffix

```java
String display = List.of("Java", "SQL", "Docker").stream()
        .collect(Collectors.joining(" | ", "Skills: [", "]"));

System.out.println(display);
// Skills: [Java | SQL | Docker]
```

Here:

- `delimiter = " | "`: placed **between** values.
- `prefix = "Skills: ["`: placed **once at the beginning**.
- `suffix = "]"`: placed **once at the end**.

There is no need to manually check the first or last element to decide whether to append `|`.

## 3. Complete example: formatting order lines and joining by category

The Java 17+ program below uses a single source to illustrate `filter`, `map`, `distinct`, `sorted`, and `joining`, as well as composition with `groupingBy` and `mapping`.

Save to `JoiningCollectorsDemo.java`:

```java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class JoiningCollectorsDemo {
    record Item(
            String sku,
            String category,
            String name,
            int quantity,
            boolean active
    ) {}

    public static void main(String[] args) {
        List<Item> items = List.of(
                new Item("BK-01", "BOOK", "Java Stream", 2, true),
                new Item("PN-01", "PEN", "Blue pen", 4, true),
                new Item("BK-02", "BOOK", "Java Core", 1, true),
                new Item("BK-01", "BOOK", "Java Stream", 3, true),
                new Item("BG-01", "BAG", "Canvas bag", 1, false)
        );

        // Join active product names without duplicates, sorted by name.
        String uniqueNames = items.stream()
                .filter(Item::active)
                .map(Item::name)
                .distinct()
                .sorted()
                .collect(Collectors.joining(" | ", "[", "]"));

        // Join code with quantity: each Item becomes one string.
        String orderLines = items.stream()
                .filter(Item::active)
                .map(item -> item.sku() + " x" + item.quantity())
                .collect(Collectors.joining("; ", "Cart: ", "."));

        // For each category, join all active product names.
        // TreeMap sorts keys BOOK, PEN.
        Map<String, String> namesByCategory = items.stream()
                .filter(Item::active)
                .collect(Collectors.groupingBy(
                        Item::category,
                        TreeMap::new,
                        Collectors.mapping(
                                Item::name,
                                Collectors.joining(" / ", "<", ">")
                        )
                ));

        // Filter retains zero elements.
        String empty = items.stream()
                .filter(item -> item.quantity() > 100)
                .map(Item::name)
                .collect(Collectors.joining(", ", "[", "]"));

        System.out.println("Names: " + uniqueNames);
        System.out.println(orderLines);
        System.out.println("By category: " + namesByCategory);
        System.out.println("Empty: " + empty);
    }
}
```

Output:

```text
Names: [Blue pen | Java Core | Java Stream]
Cart: BK-01 x2; PN-01 x4; BK-02 x1; BK-01 x3.
By category: {BOOK=<Java Stream / Java Core / Java Stream>, PEN=<Blue pen>}
Empty: []
```

Analysis of key points:

1. `filter(Item::active)` restricts the input set **before** joining strings.
2. `map(Item::name)` produces a `Stream<String>`, compatible with `Collectors.joining`. Passing a `Stream<Item>` directly into `joining` would not match the input type.
3. `distinct()` removes duplicate names; `sorted()` sorts before `joining`, giving a deterministic order using `String` natural ordering.
4. `map(item -> item.sku() + " x" + item.quantity())` formats **each line as a string**, and then `joining` inserts `"; "` between lines.
5. `groupingBy` groups by category; `mapping(Item::name, joining(...))` then turns each group into **a single string**. `TreeMap::new` only sorts **category keys**; it does not sort names inside each group.
6. When the post-`filter` result is empty, the three-argument overload still returns `"[]"` because prefix and suffix are still applied.

## 4. Empty Stream: do delimiter, prefix, and suffix appear?

This is a common source of confusion. Compare:

```java
import java.util.stream.Collectors;
import java.util.stream.Stream;

String a = Stream.<String>empty()
        .collect(Collectors.joining());
String b = Stream.<String>empty()
        .collect(Collectors.joining(", "));
String c = Stream.<String>empty()
        .collect(Collectors.joining(", ", "[", "]"));
String d = Stream.<String>empty()
        .collect(Collectors.joining(", ", "List: ", "."));

System.out.println(a.isEmpty()); // true
System.out.println(b.isEmpty()); // true
System.out.println(c);         // []
System.out.println(d);         // List: .
```

| Collector form | Result on empty Stream |
| --- | --- |
| `joining()` | Empty string `""` |
| `joining(", ")` | Empty string `""` |
| `joining(", ", "[", "]")` | `"[]"` |
| `joining(";", "(", ")")` | `"()"` |

**Zero elements** means there are no delimiters to insert. However, `prefix` and `suffix` are formatting rules for **the entire result**, so they still appear.

### When you want to display a message instead of `[]`

If you have an input `List` used directly without filtering, you can check `isEmpty()` before creating a Stream. Yet if the pipeline has `filter`, a non-empty source list **does not guarantee** elements remain after filtering.

On Java 12+, you can use `Collectors.teeing` to compute **element count** and the **joined string** in a single traversal, then choose the output:

```java
String message = List.of("Java", "Kotlin").stream()
        .filter(word -> word.startsWith("Z"))
        .collect(Collectors.teeing(
                Collectors.counting(),
                Collectors.joining(", ", "[", "]"),
                (count, joined) -> count == 0
                        ? "(no results)"
                        : joined
        ));

System.out.println(message); // (no results)
```

Do not check `joined.equals("[]")` alone to infer an empty source: a single element equal to the empty string `""` also yields `"[]"` with prefix `"["` and suffix `"]"`. Element count reflects emptiness more accurately than string content.

## 5. Non-`String` data must be converted before `joining`

`Collectors.joining` operates on `CharSequence` — it does not automatically know how to format a `Product`, `Order`, `Integer`, or `BigDecimal` per business rules. Therefore, convert elements to strings **before** the collect step.

```java
import java.math.BigDecimal;
import java.util.List;
import java.util.stream.Collectors;

record PriceTag(String sku, BigDecimal price) {}

List<PriceTag> prices = List.of(
        new PriceTag("BK-01", new BigDecimal("120.00")),
        new PriceTag("PN-01", new BigDecimal("30.50"))
);

String labels = prices.stream()
        .map(p -> p.sku() + "=" + p.price().toPlainString())
        .collect(Collectors.joining("; ", "{", "}"));

System.out.println(labels);
// {BK-01=120.00; PN-01=30.50}
```

`toPlainString()` formats `BigDecimal` in decimal form without scientific notation. This is still raw string formatting; if currency reports need grouping separators, currency symbols, or locale rules, use an appropriate formatter with a `Locale` **before** joining.

With a primitive stream like `IntStream`, use `mapToObj`:

```java
String numbers = java.util.stream.IntStream.of(3, 5, 8)
        .mapToObj(Integer::toString)
        .collect(Collectors.joining(" + ", "(", ")"));

System.out.println(numbers); // (3 + 5 + 8)
```

Conversely, `IntStream.sum()` is the right choice if the task needs the **numeric result 16**, not the expression string `"(3 + 5 + 8)"`.

## 6. Combining `joining` with intermediate operations

`joining` typically sits at the end of a pipeline after filtering and normalizing data:

```java
String tags = List.of(" java ", "stream", "JAVA", "", "collector")
        .stream()
        .map(String::trim)
        .filter(s -> !s.isBlank())
        .map(s -> s.toLowerCase(java.util.Locale.ROOT))
        .distinct()
        .sorted()
        .collect(Collectors.joining(", ", "#", ""));

System.out.println(tags); // #collector, java, stream
```

Role of each step:

| Step | Role before joining |
| --- | --- |
| `map(String::trim)` | Strips leading and trailing whitespace from each tag. |
| `filter(s -> !s.isBlank())` | Drops empty or whitespace-only tags. |
| `map(...toLowerCase(Locale.ROOT))` | Normalizes casing independent of the default locale. |
| `distinct()` | Removes duplicate tags after normalization. |
| `sorted()` | Determines appearance order in the resulting string. |
| `joining(", ", "#", "")` | Joins with commas, adding prefix `#` to **the entire** string. |

**Common confusion:** `joining(", ", "#", "")` does not turn each tag into a hashtag. If you need `#java, #stream`, write `map(s -> "#" + s)` **before** `joining(", ")`.

```java
String hashtags = List.of("java", "stream").stream()
        .map(s -> "#" + s)
        .collect(Collectors.joining(", "));

System.out.println(hashtags); // #java, #stream
```

This distinction is essential between **formatting each element** (`map`) and **formatting the whole result** (`joining` with prefix/suffix).

## 7. Joining strings by group with `groupingBy` and `mapping`

When the requirement is no longer a single string, but **one string per group**, use a composed collector:

```java
Collectors.groupingBy(
        classifier,
        Collectors.mapping(valueMapper, Collectors.joining(delimiter))
)
```

The output has the form `Map<K, String>`:

```text
Stream<Item>
     │
     ▼
 groupingBy(Item::category)
     │
     ├── BOOK ──► mapping(Item::name) ──► joining(", ") ──► "Java Stream, Java Core"
     └── PEN  ──► mapping(Item::name) ──► joining(", ") ──► "Blue pen"
     │
     ▼
 Map<String, String>
```

Example using `items` and `Item` from the program in section 3:

```java
Map<String, String> descriptions = items.stream()
        .filter(Item::active)
        .collect(Collectors.groupingBy(
                Item::category,
                TreeMap::new,
                Collectors.mapping(
                        Item::name,
                        Collectors.joining(", ", "[", "]")
                )
        ));

System.out.println(descriptions);
// {BOOK=[Java Stream, Java Core, Java Stream], PEN=[Blue pen]}
```

In this example, calling `.map(Item::name)` **before** `groupingBy(Item::category)` would lose the `category` info and prevent grouping by that property. `Collectors.mapping` lets you **keep `Item` during grouping**, and only then turn each element in each group into a `String` for joining.

### Does `Collectors.filtering` go before or after `groupingBy`?

Since Java 9, `Collectors.filtering` acts as a downstream collector to filter **inside each group**:

```java
Map<String, String> allCategories = items.stream()
        .collect(Collectors.groupingBy(
                Item::category,
                TreeMap::new,
                Collectors.filtering(
                        Item::active,
                        Collectors.mapping(
                                Item::name,
                                Collectors.joining(", ", "[", "]")
                        )
                )
        ));

System.out.println(allCategories);
// {BAG=[], BOOK=[Java Stream, Java Core, Java Stream], PEN=[Blue pen]}
```

Here, the `BAG` group **still exists** because an `Item` belonged to `BAG`, yet downstream `filtering` rejected that element, so `joining` on the empty group returns `[]`.

Conversely, writing `items.stream().filter(Item::active).collect(groupingBy(...))` drops the `BAG` element **before grouping**, so the `BAG` key never appears. This is a notable semantic difference when reports must include groups with no qualifying elements.

## 8. `collectingAndThen`: post-processing the joined result

`Collectors.collectingAndThen(downstream, finisher)` applies **a final transformation** after the downstream collector finishes.

For example, trimming whitespace from the entire result:

```java
String summary = List.of("Java", "Stream").stream()
        .collect(Collectors.collectingAndThen(
                Collectors.joining(", ", "List: ", "  "),
                String::strip
        ));

System.out.println(summary); // List: Java, Stream
```

Note that `collectingAndThen` is unnecessary if you only want to add a prefix or suffix; the three-argument `joining` already handles that. Use `collectingAndThen` when you need **custom post-processing**, such as wrapping the result in another object, normalizing overall formatting, or applying a rule not built into `joining`.

If you only want different text when there are zero elements, use `teeing` with `counting` as in section 4, or obtain the element count prior to collecting. The joined string content is not always enough to infer element count.

## 9. `null`, delimiter characters, and data safety

### `null` in a Stream

If the source contains a `null` element, an implementation based on `StringBuilder`/`StringJoiner` can render it as the literal string **`"null"`** in the output rather than skipping it. It is better to define a clear display policy.

```java
import java.util.Arrays;
import java.util.Objects;
import java.util.stream.Collectors;

List<String> names = Arrays.asList("An", null, "Bình");

String withoutNull = names.stream()
        .filter(Objects::nonNull)
        .collect(Collectors.joining(" | "));
// An | Bình

String withPlaceholder = names.stream()
        .map(name -> name == null ? "(unnamed)" : name)
        .collect(Collectors.joining(" | "));
// An | (unnamed) | Bình
```

`List.of(...)` forbids `null` elements, which is why the example above uses `Arrays.asList(...)`. If a mapper calls `item.name()` on a **null item object**, the error happens **before** joining; filter `Objects::nonNull` at the right stage.

### `joining` does not escape content automatically

Suppose data contains the name `"Java, Advanced"`:

```java
String output = List.of("Java, Advanced", "Stream").stream()
        .collect(Collectors.joining(", "));

System.out.println(output); // Java, Advanced, Stream
```

From the resulting string alone, you cannot tell that the first comma is **part of the name** while the second comma is **the delimiter**. Therefore:

- Do not use `joining(",")` as a full CSV writer when values can contain commas, quotes, or newlines; apply CSV quoting/escaping rules.
- Do not construct JSON or SQL statements via manual string joining and treat them as safe. Use a JSON serialization library or parameterized SQL.
- For data used in HTML/URLs, apply escaping/encoding appropriate to the **target context** instead of expecting `joining` to handle it.

The three parameters `delimiter`, `prefix`, and `suffix` are **presentation rules**, not data validation or sanitization mechanisms.

## 10. Element ordering and parallel Streams

`joining` is order-dependent whenever the resulting string must be read in sequence. On a source with encounter order like `List`, a sequential pipeline preserves that order unless a step alters or drops ordering guarantees:

```java
String ordered = List.of("C", "A", "B").stream()
        .collect(Collectors.joining("-"));
// C-A-B

String sorted = List.of("C", "A", "B").stream()
        .sorted()
        .collect(Collectors.joining("-"));
// A-B-C
```

Do not assume `Collectors.joining` sorts elements on its own. If the source has no encounter order (such as some `HashSet` usages), the result has no guaranteed business order; add `sorted` when deterministic output is required.

### When using `parallelStream()`

```java
String joined = List.of("Java", "Kotlin", "Scala")
        .parallelStream()
        .collect(Collectors.joining(" | "));

System.out.println(joined); // Java | Kotlin | Scala
```

`Collectors.joining` can be used on a parallel stream. With an ordered source such as `List` and a pipeline that retains encounter order, the result must respect that order. Accumulation can happen in multiple intermediate buffers that are merged according to the collector contract.

However, parallel **is not faster by default**: splitting data, building intermediate strings, and merging them all have overhead. For small collections or string results requiring strict order, sequential processing is easier to reason about and can be more efficient. If an operation like `unordered()` drops encounter order, do not rely on joining order to define the result.

## 11. Memory, result length, and choosing the right tool

Given `n` input strings, `joining` must read the elements to build the final result; the result holds all concatenated content plus delimiters, prefix, and suffix. **Minimum memory for the resulting string grows with total character count**, and cannot be considered `O(1)` regardless of data size.

If a list has millions of elements, building one giant string can consume substantial memory or even hit JVM array/string size limits. Consider pagination, batching, or streaming to a `Writer` when materializing the entire string in RAM is unnecessary.

`joining` also requires a finite source to terminate:

```java
String firstFive = java.util.stream.Stream
        .iterate(1, n -> n + 1)
        .limit(5)
        .map(String::valueOf)
        .collect(Collectors.joining(", "));

System.out.println(firstFive); // 1, 2, 3, 4, 5
```

An unbounded infinite Stream will never finish `collect(joining(...))`. For I/O-backed Streams, close resources properly; calling `collect` does not replace `try-with-resources`.

### Comparison with `String.join`, `StringJoiner`, and `reduce`

| Approach | Best when | Notes |
| --- | --- | --- |
| `Collectors.joining(...)` | Already in a Stream pipeline, especially after `filter`/`map` or as a downstream collector. | Terminal reduction; requires `CharSequence` data. |
| `String.join(delimiter, elements)` | Already have an `Iterable<? extends CharSequence>` or `CharSequence` arguments; no pipeline needed. | Has no overload for prefix/suffix. |
| `StringJoiner` | Manually accumulating strings with delimiter/prefix/suffix. | Must call `add` per element; `joining` uses a similar mechanism internally. |
| `reduce` with string concatenation | Good for learning simple reduction. | Repeated immutable string concatenation creates many intermediate objects; not preferred for joining many strings. |

Example without Streams:

```java
String direct = String.join(", ", List.of("A", "B", "C"));
// A, B, C

java.util.StringJoiner joiner =
        new java.util.StringJoiner(", ", "[", "]");
joiner.add("A");
joiner.add("B");
System.out.println(joiner); // [A, B]
```

Once you already have a Stream with multiple transformation steps, `collect(Collectors.joining(...))` is usually more natural than pulling elements out of the pipeline to join manually in a loop.

## 12. Common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Calling `joining` directly on `Stream<Item>` | Incompatible with `CharSequence`; fails to compile. | `map(Item::name)` or format each `Item` into a string first. |
| Expecting prefix/suffix to repeat for every element | Output does not match intended format. | Use `map` for per-element prefix/suffix; use `joining(..., prefix, suffix)` for the whole result. |
| Expecting `""` on an empty Stream when prefix/suffix are set | Actually returns `prefix + suffix`. | Define display rules and check count if you must distinguish them. |
| Using `joining(",")` to write real CSV | Values with commas/quotes are not escaped. | Use a CSV serializer or proper escaping rules. |
| Failing to filter or replace `null` intentionally | Output string can contain unintended `"null"` text. | `filter(Objects::nonNull)` or `map` to a placeholder. |
| Confusing `groupingBy` and `mapping` | Loses grouping key when mapping too early. | Group on the object, then apply `mapping` inside the downstream collector. |
| Expecting deterministic order from an unordered source | Joined string order is unpredictable. | Use an ordered source or `sorted()` before collecting. |
| Assuming `parallelStream()` always speeds things up | Splitting/merging cost outweighs benefits. | Benchmark; prefer sequential for small datasets. |
| Joining infinite or huge data into one string | Never terminates or causes high memory pressure. | Use `limit`, batching, or stream sequentially to a destination. |
| Reusing the same Stream after `collect` | Stream already consumed; throws `IllegalStateException`. | Create a new Stream from a re-iterable source. |

## 13. Practice exercises

**Exercise 1 — Three overloads.** Given `List.of("x", "y", "z")`, predict the three results:

```java
List<String> values = List.of("x", "y", "z");

String a = values.stream().collect(Collectors.joining());
String b = values.stream().collect(Collectors.joining("-"));
String c = values.stream().collect(Collectors.joining("-", "<", ">"));
```

**Answer:** `a = "xyz"`, `b = "x-y-z"`, `c = "<x-y-z>"`.

**Exercise 2 — Empty source.** What is the value of `Stream.<String>empty().collect(Collectors.joining("; ", "(", ")"))`?

**Answer:** `"()"`. No delimiter is inserted since there are zero elements, yet prefix and suffix are still retained.

**Exercise 3 — Per-element prefix.** You need to turn `["java", "stream"]` into `"#java, #stream"`. Should you use `joining(", ", "#", "")`?

**Answer:** No. Use `.map(s -> "#" + s).collect(Collectors.joining(", "))`; `joining`'s prefix is added only once at the start of the whole string.

**Exercise 4 — Joining by group.** Given `Stream<Item>`, how do you create `Map<String, String>` keyed by `category`, where each value is the `Item` names separated by `"; "`?

```java
Map<String, String> result = items.stream()
        .collect(Collectors.groupingBy(
                Item::category,
                Collectors.mapping(Item::name, Collectors.joining("; "))
        ));
```

**Exercise 5 — Filter in two positions.** Why can `items.stream().filter(Item::active).collect(groupingBy(...))` produce fewer keys than `items.stream().collect(groupingBy(..., filtering(Item::active, ...)))`?

**Answer:** Filtering **before** grouping drops elements before groups are formed; groups with no matching elements can disappear. Filtering **inside the downstream** still creates groups for keys present in the input, while the joined result for a group with no matching elements can be empty or only prefix/suffix.

**Exercise 6 — Ordering.** If you need the exact same result string regardless of the list's initial order, what step should you add?

**Answer:** Sort with a deterministic comparator using `sorted()` or `sorted(comparator)` **before** `joining`. If multiple records compare equal and relative order among them matters, add a clear tie-breaker criterion.

## Key takeaway

- `Collectors.joining()` concatenates `CharSequence` values; `joining(delimiter)` inserts the delimiter **between** elements; `joining(delimiter, prefix, suffix)` adds prefix/suffix **once for the entire result**.
- On an empty Stream, the first two forms return `""`; the form with prefix/suffix returns `prefix + suffix` (such as `"[]"`).
- When the source is not `CharSequence`, `map` or `mapToObj` to strings first; `joining` does not format domain objects automatically.
- You can compose `groupingBy(..., mapping(..., joining(...)))` to build one string per group; downstream `filtering` differs from pre-grouping `filter` in keeping empty groups.
- `joining` does not escape data for CSV/JSON/HTML, does not sort automatically, and requires attention to memory, order, resources, and bounds with infinite or parallel Streams.
