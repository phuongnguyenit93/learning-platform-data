# Writing Your First Pipeline with `filter`, `map`, and `collect`

## 1. Lesson objectives

**Java Stream API** allows processing data in a **declarative** style: describing which data to select, how to transform it, and what result to collect. Instead of manually managing loops, temporary lists, and add operations, we compose processing steps into a **pipeline** (a processing chain).

After this lesson, you will be able to:

- Create a `Stream` from a `List` and write your first pipeline with the structure **data source → `filter` → `map` → `collect`**.
- Distinguish `filter` (keep or drop elements), `map` (transform elements), and `collect` (build the final result).
- Explain why `filter` and `map` do not run immediately when declared, whereas `collect` triggers execution.
- Read data types, predict outputs, and spot basic mistakes when writing pipelines.

This is the starting point for broader Stream API techniques such as `reduce`, `groupingBy`, custom collectors, or parallel processing. This lesson focuses on a sequential pipeline that is easy to understand and verify.

## 2. Problem: extract Java course names and convert to uppercase

Suppose a system has the following courses:

```text
Java Core, Python Basics, Java Stream API, Kotlin, Java Spring
```

We want to **keep only courses whose names start with `Java`**, convert their names to uppercase, and produce a new `List<String>`.

If we use a loop, we have to iterate through each element, check the condition, transform the string, and add it to a result list. With the Stream API, those three ideas appear directly in the pipeline:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.stream.Collectors;

public class StreamPipelineDauTien {
    public static void main(String[] args) {
        List<String> khoaHoc = Arrays.asList(
            "Java Core",
            "Python Basics",
            "Java Stream API",
            "Kotlin",
            "Java Spring"
        );

        List<String> tenKhoaJava = khoaHoc.stream()
            .filter(ten -> ten.startsWith("Java"))
            .map(ten -> ten.toUpperCase(Locale.ROOT))
            .collect(Collectors.toList());

        System.out.println(tenKhoaJava);
        System.out.println(khoaHoc);
    }
}
```

Output:

```text
[JAVA CORE, JAVA STREAM API, JAVA SPRING]
[Java Core, Python Basics, Java Stream API, Kotlin, Java Spring]
```

The example uses `Collectors.toList()`, available since **Java 8**. The second line confirms that the source list `khoaHoc` remains unchanged: the pipeline creates a new result without modifying the strings in the original list.

## 3. Reading each step of the pipeline

```text
List<String> khoaHoc
        │
        ▼
     stream()        creates Stream<String> from the list
        │
        ▼
  filter(condition)  keeps names starting with "Java"
        │
        ▼
    map(transform)   converts each remaining name to uppercase
        │
        ▼
 collect(toList())   collects elements into List<String>
```

| Component | Role | Input → output in the example |
| --- | --- | --- |
| `khoaHoc.stream()` | Opens a processing stream from the list | `List<String>` → `Stream<String>` |
| `.filter(ten -> ten.startsWith("Java"))` | Keeps only elements matching the condition | `Stream<String>` → `Stream<String>` |
| `.map(ten -> ten.toUpperCase(Locale.ROOT))` | Transforms each remaining element | `Stream<String>` → `Stream<String>` |
| `.collect(Collectors.toList())` | Triggers the pipeline and collects the result | `Stream<String>` → `List<String>` |

### 3.1. `filter`: selecting elements

`filter` accepts a **`Predicate<T>`**, a function that tests an element of type `T` and returns a `boolean`:

```java
.filter(ten -> ten.startsWith("Java"))
```

- `true`: the element is passed along to the next step.
- `false`: the element is dropped from the pipeline, so it will not be processed by `map`.

In the example above, `"Python Basics"` and `"Kotlin"` do not pass the filter. The condition `startsWith("Java")` is **case-sensitive**: a name starting with `"java"` will not be kept.

### 3.2. `map`: transforming elements

`map` accepts a **`Function<T, R>`**, a function that turns an element of type `T` into a value of type `R`:

```java
.map(ten -> ten.toUpperCase(Locale.ROOT))
```

Here both `T` and `R` are `String`, but `map` **can change the data type**. For instance, after selecting Java course names, we take the length of each name:

```java
List<Integer> doDaiTen = khoaHoc.stream()
    .filter(ten -> ten.startsWith("Java"))
    .map(String::length)
    .collect(Collectors.toList());

System.out.println(doDaiTen); // [9, 15, 11]
```

At this point `map(String::length)` turns `Stream<String>` into `Stream<Integer>`. The syntax `String::length` is a **method reference**, a concise equivalent to `ten -> ten.length()` in this case.

### 3.3. `collect`: gathering the result

`collect` is a **terminal operation**. It consumes the stream to build a result according to the strategy of a `Collector`:

```java
.collect(Collectors.toList())
```

`Collectors.toList()` gathers the elements into a list, preserving encounter order for an ordered source such as `List` in this sequential pipeline. You can collect in other ways depending on your needs:

```java
// Collect the names into a single string, separated by commas.
String chuoiTen = khoaHoc.stream()
    .filter(ten -> ten.startsWith("Java"))
    .collect(Collectors.joining(", "));

// Result: "Java Core, Java Stream API, Java Spring"
```

A useful detail about Java versions: since **Java 16**, you can write `stream.toList()` instead of `collect(Collectors.toList())` when you just want a list. However, `Stream.toList()` returns an **unmodifiable** list, whereas `Collectors.toList()` **makes no guarantees** about the concrete type or mutability of the returned list. If you genuinely need a mutable `ArrayList`, use `collect(Collectors.toCollection(ArrayList::new))`.

## 4. When does the pipeline run? Understanding laziness

`filter` and `map` are **intermediate operations**: calling them only builds the processing steps. They **do not traverse data immediately**. When a terminal operation like `collect` is present, the pipeline is executed.

Observe the following code (reusing the `khoaHoc` list from the first example):

```java
import java.util.stream.Stream;

Stream<String> pipeline = khoaHoc.stream()
    .filter(ten -> {
        System.out.println("filter: " + ten);
        return ten.startsWith("Java");
    })
    .map(ten -> {
        System.out.println("map: " + ten);
        return ten.toUpperCase(Locale.ROOT);
    });

System.out.println("Pipeline has been declared");

List<String> ketQua = pipeline.collect(Collectors.toList());
System.out.println(ketQua);
```

First, only `Pipeline has been declared` is printed. Afterwards, calling `collect` causes the `filter:` and `map:` lines to appear. In this simple sequential pipeline, Java typically processes **each element through the steps**: if `filter` drops a name, `map` is not called for that name. These are not two separate loops forced to scan the entire list.

The `println` statements are only for observation. In real code, treat `filter`/`map` as side-effect-free functions, avoiding mutating external data or relying on log order to drive program logic.

**Note:** Each `Stream` can be consumed only once. After calling `pipeline.collect(...)`, do not continue using the same `pipeline` for another terminal operation; to process again, create a new stream from the source using `khoaHoc.stream()`.

## 5. Step order affects the result

With clean data, `filter` before `map` skips transforming elements that are guaranteed to be dropped. However, if the filtering condition depends on a **normalized value**, you need `map` before `filter`.

For example, form input data with extra whitespace and inconsistent casing:

```java
List<String> tenNhap = Arrays.asList(
    "  Java Core  ", "java Stream API", " Python ", "   "
);

List<String> tenJava = tenNhap.stream()
    .map(String::trim)
    .filter(ten -> !ten.isEmpty())
    .filter(ten -> ten.toLowerCase(Locale.ROOT).startsWith("java"))
    .map(ten -> ten.toUpperCase(Locale.ROOT))
    .collect(Collectors.toList());

System.out.println(tenJava);
// [JAVA CORE, JAVA STREAM API]
```

Here, `trim` must run before checking whether the name starts with `java`; if you filtered directly on the raw string, `"  Java Core  "` would be missed. Having `filter` and `map` appear multiple times in the same pipeline is completely normal.

When data may contain `null`, handle it before calling `startsWith`, `trim`, or `toUpperCase`, such as using `.filter(java.util.Objects::nonNull)` before those steps. Otherwise, the pipeline may throw a `NullPointerException` when executed.

## 6. Business example: filtering product prices and calculating discounted prices

We have a list of prices in VND and want to select products **priced at 100,000 VND or more**, apply a **10%** discount, and collect them into a new list:

```java
List<Integer> giaGoc = Arrays.asList(90_000, 150_000, 300_000, 60_000);

List<Integer> giaSauGiam = giaGoc.stream()
    .filter(gia -> gia >= 100_000)
    .map(gia -> gia - gia / 10)
    .collect(Collectors.toList());

System.out.println(giaSauGiam); // [135000, 270000]
System.out.println(giaGoc);      // [90000, 150000, 300000, 60000]
```

Reading in business terms:

1. `stream()` draws each price from the source list.
2. `filter` keeps `150_000` and `300_000`, dropping the two prices below the threshold.
3. `map` subtracts 10% from each retained price.
4. `collect` gathers the two new prices into a `List<Integer>`.

The example uses integer division for ease of learning; real-world monetary calculations require clear rounding rules, an appropriate data type (usually `BigDecimal`), and overflow checks during computation.

## 7. Common mistakes

| Situation | Cause | How to handle |
| --- | --- | --- |
| Calling `stream().filter(...).map(...)` and seeing no result | Missing a terminal operation; intermediate steps are lazy | Add `collect`, `count`, or an appropriate terminal operation |
| Using `map(ten -> ten.startsWith("Java"))` to filter | `map` turns the name into a `Boolean` instead of removing elements | Use `filter(ten -> ten.startsWith("Java"))` |
| Using `forEach` and trying to assign the result to a `List` | `forEach` returns `void`, mainly for performing an action per element | Use `collect(Collectors.toList())` to collect a list |
| Trying to call `collect` twice on the same `Stream` | The Stream has already been consumed | Create a new stream from the source |
| Condition `startsWith("Java")` misses `"java Core"` | Case-sensitive comparison | Normalize or use an appropriate comparison |
| Calling string methods on a `null` element | Accessing a non-existent object | Filter out `null` before processing |
| Trying to modify the list returned by `Stream.toList()` | That list is unmodifiable | Choose a collector that produces a mutable list if truly needed |

The Stream API helps express processing intent clearly, but is **not inherently faster than a loop**. For small datasets or simple logic, prioritize readability and maintainability; there is no need to use `parallelStream()` for your first pipeline.

## 8. Practice on your own

Given the list:

```java
List<String> ngonNgu = Arrays.asList(
    "Java", "JavaScript", "Python", "Go", "Kotlin", "Python"
);
```

Write a pipeline using `filter`, `map`, and `collect` to **keep names with at least 5 characters**, **convert them to lowercase**, and **collect them into a `List<String>`**. Before running it, try predicting the output. Do duplicate values remain?

<details>
<summary>Solution hint</summary>

```java
List<String> ketQua = ngonNgu.stream()
    .filter(ten -> ten.length() >= 5)
    .map(ten -> ten.toLowerCase(Locale.ROOT))
    .collect(Collectors.toList());

System.out.println(ketQua); // [javascript, python, kotlin, python]
```

The elements `"Java"` and `"Go"` have fewer than 5 characters, so they are dropped. `filter`, `map`, and `collect(toList())` **do not automatically remove duplicates**: both occurrences of `"Python"` are kept in the result list.

</details>

## 9. Remember

A first Stream API pipeline has the form:

```java
List<R> ketQua = nguon.stream()
    .filter(phanTu -> dieuKien)
    .map(phanTu -> giaTriMoi)
    .collect(Collectors.toList());
```

Here, `filter` answers **which elements to keep**, `map` answers **what value to transform them into**, and `collect` answers **what form to gather the result in**. `filter` and `map` only describe the processing; `collect` triggers pipeline execution. Once you understand these three steps, you have the foundation to move on to `reduce`, `Collectors.groupingBy`, and more complex pipelines.
