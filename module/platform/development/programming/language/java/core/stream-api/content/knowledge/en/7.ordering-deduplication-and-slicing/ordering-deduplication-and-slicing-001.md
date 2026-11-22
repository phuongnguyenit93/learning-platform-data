# Removing Duplicate Elements with `distinct`, `equals`, and `hashCode`

In many applications, data received from APIs, input files, or databases may contain duplicates: the same product code appears multiple times, the same user is recorded across multiple lines, or a list of keywords contains repeated values. With the **Java Stream API**, you can use `distinct()` to retain elements that are **different according to Java's equality rules**.

A key point to understand right away: `distinct()` **does not automatically know** whether two products have the same code. For an object Stream, it relies on `equals()` to determine equality and `hashCode()` to help look up duplicate elements. Therefore, the result of `distinct()` depends on **how the data class defines equality**.

This lesson belongs to the **Ordering, Deduplication, and Slicing** chapter of the **JAVA_STREAM_API** module. After this lesson, you will be able to use `distinct()` in a lazy pipeline, explain the relationship between `equals` and `hashCode`, understand which element is kept when the source is ordered, recognize memory costs, and avoid bugs with mutable objects, parallel Streams, and infinite data.

## 1. The First Problem: Removing Duplicate Codes

Suppose the system receives a list of product codes:

~~~java
List<String> codes = List.of(
    "SP01", "SP02", "SP01", "SP03", "SP02"
);
~~~

The requirement is to obtain `SP01`, `SP02`, and `SP03`, each once.

~~~java
import java.util.List;
import java.util.stream.Collectors;

public class DistinctStringDemo {
    public static void main(String[] args) {
        List<String> codes = List.of(
            "SP01", "SP02", "SP01", "SP03", "SP02"
        );

        List<String> uniqueCodes = codes.stream()
            .distinct()
            .collect(Collectors.toList());

        System.out.println(uniqueCodes); // [SP01, SP02, SP03]
        System.out.println(codes.size());  // 5, source remains unchanged
    }
}
~~~

This example uses `List.of` (Java 9+); `distinct()` has been available since Java 8. With Java 16+, you can use `stream().distinct().toList()` to obtain an unmodifiable list.

We read the pipeline as follows:

1. `codes.stream()` creates a Stream from the list, preserving the **encounter order** of the `List`.
2. `distinct()` creates an intermediate Stream that emits only distinct values.
3. `collect(Collectors.toList())` is a terminal operation that produces the resulting list.

On an ordered source, `distinct()` is **stable**: if multiple elements are equal, the element that **appears first** in encounter order is kept. Therefore, the `SP01` at the first position is kept, and the duplicate `SP01` at the third position is removed.

`distinct()` does not modify the `codes` list and does not return a `Set`; the result is still a **Stream** so you can continue with `filter`, `map`, `sorted`, or other operations.

## 2. The Contract of `distinct` in the Stream API

The commonly used signature is:

~~~java
Stream<T> distinct()
~~~

`distinct()` is a **stateful intermediate operation**: to know whether a new value is a duplicate, processing must track the equivalent values already encountered.

~~~mermaid
flowchart LR
    A["Source: A, B, A, C, B"] --> B["distinct()"]
    B --> C["Stream: A, B, C"]
    C --> D["collect(toList())"]
    D --> E["List: A, B, C"]
~~~

Important characteristics:

| Question | Answer |
|---|---|
| Does `distinct()` change the element type? | **No**. `Stream<T>` remains `Stream<T>`. |
| Does it require a terminal operation? | **Yes**, to execute processing when needed; it is a lazy intermediate operation. |
| Does it modify the original collection? | **No**, the deduplication operation itself does not mutate the source. |
| Which representative does it keep when the source is ordered? | The **first** element among equal elements. |
| Does it always guarantee result ordering? | **No**, if the Stream has no encounter order or has been marked `unordered()`. |
| Must every element always be traversed? | **Not necessarily**; a short-circuiting terminal operation may only need part of the source. |
| Does it need to remember seen values? | Usually **yes**, so memory usage can be high when the number of unique values is large. |

Note the difference between **ordering** and **equality**: `distinct()` decides which elements are duplicates using `equals()`, not the comparator of `sorted()`, not `toString()`, and not any arbitrary field unless the class defines equality based on that field.

## 3. How Do `equals` and `hashCode` Decide What Is "Duplicate"?

In Java, every class inherits `equals(Object)` and `hashCode()` from `Object`. The two methods have distinct roles:

- `equals(Object)` answers the question: **are two objects considered equal?**
- `hashCode()` returns an integer used in hash-based structures to help locate objects that are potentially equal.

One way to visualize this:

~~~text
New element
    |
    v
Compute hashCode() ---> find matching candidate bucket
    |
    v
Compare with candidates using equals()
    |
    +-- Equal element already present: discard new element
    |
    +-- No equal element present: keep new element
~~~

The diagram above illustrates the **general principle of hash-based structures**, without committing to the internal algorithm of every JDK version. The contract of `Stream.distinct` is distinctness according to `Object.equals`; an optimizing implementation may choose different ways to realize it.

### 3.1. `String` Already Has Content-Based Equality

Two `String` objects with different references but the same characters are still equal:

~~~java
String first = new String("JAVA");
String second = new String("JAVA");

System.out.println(first == second);      // false: different references
System.out.println(first.equals(second)); // true: same content
System.out.println(first.hashCode() == second.hashCode()); // true

long uniqueCount = java.util.stream.Stream.of(first, second)
    .distinct()
    .count();

System.out.println(uniqueCount); // 1
~~~

Because `String` defines `equals` and `hashCode` based on content, `distinct()` works as expected when removing exact string duplicates.

However, `String.equals` is **case-sensitive** and whitespace-sensitive:

~~~java
List<String> raw = List.of("Java", "java", " Java ", "JAVA");

System.out.println(raw.stream().distinct().count()); // 4
~~~

If business logic treats those strings as the same code, you must **normalize before deduplicating**:

~~~java
import java.util.Locale;

List<String> normalized = raw.stream()
    .map(String::trim)
    .map(text -> text.toUpperCase(Locale.ROOT))
    .distinct()
    .collect(java.util.stream.Collectors.toList());

System.out.println(normalized); // [JAVA]
~~~

`Locale.ROOT` is suitable for locale-independent technical code normalization rules; for personal names or natural language, comparison policies and Unicode handling can be more complex.

### 3.2. Two Objects with the Same Data Can Still Be Considered Different

If a class does not override `equals`, the default behavior from `Object` is typically based on **object identity**. Two entities created with different `new` calls are distinct even if their fields match:

~~~java
class Product {
    String code;

    Product(String code) {
        this.code = code;
    }
}

Product a = new Product("SP01");
Product b = new Product("SP01");

System.out.println(a.equals(b)); // false: equals not overridden
System.out.println(java.util.stream.Stream.of(a, b).distinct().count()); // 2
~~~

This example is valid at the language level, but it **does not satisfy the requirement to deduplicate products by code**. To do that, you need to define equality rules for the class, or map to the code before calling `distinct()`.

## 4. Writing Consistent `equals` and `hashCode` for Business Objects

Suppose in the current application, the **product code `sku`** is the unique identifier. Two records with the same `sku` are considered the same product, even if the name description differs due to updated data.

Complete example running on Java 8+:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.stream.Collectors;

public class ProductDistinctDemo {
    static final class Product {
        private final String sku;
        private final String name;

        Product(String sku, String name) {
            this.sku = Objects.requireNonNull(sku, "sku");
            this.name = Objects.requireNonNull(name, "name");
        }

        String getSku() {
            return sku;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof Product)) {
                return false;
            }
            Product that = (Product) other;
            return sku.equals(that.sku);
        }

        @Override
        public int hashCode() {
            return sku.hashCode();
        }

        @Override
        public String toString() {
            return sku + " - " + name;
        }
    }

    public static void main(String[] args) {
        List<Product> products = Arrays.asList(
            new Product("SP01", "Blue pen"),
            new Product("SP02", "Notebook"),
            new Product("SP01", "Blue pen (re-imported data)"),
            new Product("SP03", "Ruler")
        );

        List<Product> uniqueProducts = products.stream()
            .distinct()
            .collect(Collectors.toList());

        uniqueProducts.forEach(System.out::println);
    }
}
~~~

Output:

~~~text
SP01 - Blue pen
SP02 - Notebook
SP03 - Ruler
~~~

Here:

1. `equals` compares **`sku`**, which is the chosen business rule.
2. `hashCode` is also computed from **`sku`**, so two products considered equal have the same hash code.
3. Because the source is an ordered `List`, `distinct()` keeps the first `SP01` product that appears, namely with the name `Blue pen`. The second `SP01` record is excluded from the result.

**There is no single `equals` rule that fits every problem.** If in your system two products with the same SKU but different versions must be treated as different, then `sku` alone is not enough. You must identify the complete business key (for example `sku` + `version`) and use that exact key in **both `equals` and `hashCode`**.

### 4.1. Mandatory Contract of `equals` and `hashCode`

According to Java's contract, `equals` must satisfy:

- **Reflexive:** for any non-null object, `x.equals(x)` is `true`.
- **Symmetric:** if `x.equals(y)` is `true`, then `y.equals(x)` is also `true`.
- **Transitive:** if `x.equals(y)` and `y.equals(z)` are both `true`, then `x.equals(z)` must be `true`.
- **Consistent:** as long as the information used in comparisons does not change, repeated invocations must return consistent results.
- **Non-null:** `x.equals(null)` is `false` for any non-null `x`.

For `hashCode`:

- If `x.equals(y)` is `true`, it is **mandatory** that `x.hashCode() == y.hashCode()`.
- If two objects have the same hash code, they are **not required** to be equal. This is a **hash collision**, not an error by itself.
- The hash code must remain consistent as long as the information affecting equality has not changed.

A common mistake is **overriding `equals` while forgetting `hashCode`**. Then two objects considered equal may receive different hash codes, leading to incorrect behavior in `HashSet`, `HashMap`, and hash-based deduplication operations.

Typical idiom:

~~~java
@Override
public boolean equals(Object other) {
    if (this == other) return true;
    if (!(other instanceof Product)) return false;
    Product that = (Product) other;
    return Objects.equals(sku, that.sku);
}

@Override
public int hashCode() {
    return Objects.hash(sku);
}
~~~

This is an **alternative** to the implementation in the complete example above when you want to use the `Objects` utilities. Do not insert these two methods alongside existing ones in the same class. For a single non-null `String` key, `sku.hashCode()` directly is sufficient.

### 4.2. Why Should Fields Participating in Equality Be Immutable?

If `sku` is modified while the Stream is deduplicating, the `hashCode` value and `equals` relationship can change mid-evaluation. Data recorded under the old hash code may no longer be found as intended.

Therefore, the example uses `private final String sku` and makes `Product` a `final` class. For more critical key fields, you can use immutable objects or records, and **avoid mutating source data while the pipeline is traversing it**.

If updating the business key is unavoidable, you should normally update the data **before** starting the pipeline, or construct new result objects and then deduplicate by the new key.

## 5. Records, Lombok, and Auto-Generated `equals` Classes

Since **Java 16**, `record` provides a concise way to represent data:

~~~java
record Product(String sku, String name) {}

List<Product> products = List.of(
    new Product("SP01", "Blue pen"),
    new Product("SP01", "Blue pen (new)")
);

System.out.println(products.stream().distinct().count()); // 2
~~~

By default, a record generates `equals` and `hashCode` from **all its components**: `sku` **and** `name`. Because the names differ, the two records above are **not equal**, even though their codes match.

This distinction is important:

| Design | Default / defined equality rule | Result with same SKU, different name |
|---|---|---|
| Regular class, not overriding `equals` | Object identity | Two separate objects |
| `Product` class in section 4 | By `sku` only | One element after `distinct` |
| `record Product(String sku, String name)` | By both `sku` and `name` | Two elements |

Tools like Lombok can generate `equals` and `hashCode` based on a configured set of fields. **Inspect the actual equality rule** before assuming `distinct` will deduplicate by ID.

If you only need to deduplicate **product codes**, you do not necessarily have to change equality for the entire class. `products.stream().map(Product::sku).distinct()` will yield **unique codes**, though the result is then `Stream<String>`, no longer `Stream<Product>`.

## 6. Which Order Is Preserved After `distinct`?

A Stream may have an *encounter order*: the element order determined by the source and preceding operations. `List.stream()` typically has the encounter order of the `List`.

~~~java
List<String> names = List.of("An", "Binh", "An", "Chi", "Binh");

List<String> result = names.stream()
    .distinct()
    .collect(java.util.stream.Collectors.toList());

System.out.println(result); // [An, Binh, Chi]
~~~

For a Stream with an encounter order, `distinct` **keeps the first element in each equivalence group**. This matters if two objects are equal by ID but have different display attributes: the first record might be the older one.

For sources **without an encounter order**, such as some `Set` sources, or after calling `unordered()`, you should not expect a deterministic representative element or result order.

~~~java
List<String> unorderedResult = names.stream()
    .unordered()
    .distinct()
    .collect(java.util.stream.Collectors.toList());

// Has the same value set {An, Binh, Chi}, but do not rely on this order.
~~~

`unordered()` is not a shuffle operation, and the result may sometimes **still appear in the same order**. Its meaning is to drop the encounter order constraint, giving implementations more freedom. Do not write tests that depend on ordering in that case.

### 6.1. `distinct` and `sorted` Solve Two Different Problems

~~~java
List<String> input = List.of("C", "A", "C", "B");

List<String> uniqueSorted = input.stream()
    .distinct()
    .sorted()
    .collect(java.util.stream.Collectors.toList());

System.out.println(uniqueSorted); // [A, B, C]
~~~

`distinct` determines whether elements **are duplicates**, while `sorted` determines **order**. `sorted(Comparator)` does not automatically merge two elements where `comparator.compare(a, b) == 0` if `a.equals(b)` is `false`.

An easy-to-confuse example is `BigDecimal`:

~~~java
import java.math.BigDecimal;
import java.util.List;

List<BigDecimal> values = List.of(
    new BigDecimal("1.0"),
    new BigDecimal("1.00")
);

System.out.println(values.get(0).compareTo(values.get(1))); // 0
System.out.println(values.get(0).equals(values.get(1)));    // false
System.out.println(values.stream().distinct().count());     // 2
~~~

`BigDecimal.compareTo` compares numeric value, whereas `BigDecimal.equals` also distinguishes **scale**. If you want to treat `1.0` and `1.00` as one value, decide on a normalization rule or use an appropriate equivalence key before deduplicating; for instance, `map(BigDecimal::stripTrailingZeros).distinct()` in problems where that normalization is acceptable.

## 7. Pipeline Step Ordering Changes the Result

With the same set of operations, where you place `distinct` can change the outcome.

### 7.1. Normalize Before or After `distinct`?

~~~java
List<String> source = List.of(" Java ", "JAVA", "Go");

List<String> correct = source.stream()
    .map(String::trim)
    .map(value -> value.toUpperCase(java.util.Locale.ROOT))
    .distinct()
    .collect(java.util.stream.Collectors.toList());
// [JAVA, GO]
~~~

If you call `distinct()` before normalizing, the three original source strings still differ under `String.equals`, so they pass through the deduplication step. Afterward they can be transformed into identical strings without **being deduplicated again**:

~~~java
List<String> stillDuplicated = source.stream()
    .distinct()
    .map(String::trim)
    .map(value -> value.toUpperCase(java.util.Locale.ROOT))
    .collect(java.util.stream.Collectors.toList());
// [JAVA, JAVA, GO]
~~~

The common pattern when deduplicating by **transformed values** is:

`source → normalize/map → filter if needed → distinct → collect`.

### 7.2. `distinct` Before or After `limit`?

~~~java
List<Integer> source = List.of(1, 1, 2, 3, 4);

List<Integer> distinctThenLimit = source.stream()
    .distinct()
    .limit(3)
    .collect(java.util.stream.Collectors.toList());
// [1, 2, 3]

List<Integer> limitThenDistinct = source.stream()
    .limit(3)
    .distinct()
    .collect(java.util.stream.Collectors.toList());
// [1, 2]
~~~

- `distinct().limit(3)`: finds up to **three distinct values** in source order.
- `limit(3).distinct()`: takes the **first three input elements**, then removes duplicates within that slice.

With very large datasets, `limit` before `distinct` may save work, but it changes the business meaning. Prioritize the required output semantics.

### 7.3. `filter` Before `distinct`?

If you can filter out elements without altering the definition of duplicate groups, placing `filter` before `distinct` usually reduces the number of elements inspected:

~~~java
List<Integer> result = List.of(-1, 2, 2, 3, -1, 4).stream()
    .filter(n -> n > 0)
    .distinct()
    .collect(java.util.stream.Collectors.toList());
// [2, 3, 4]
~~~

However, for objects with the same key but different attributes, **filtering before versus after choosing the first representative** can produce different results. For example, if two records share an ID and one is invalid, decide whether business logic wants to "keep the first valid record" or "deduplicate IDs by the first record" before arranging the steps.

## 8. Deduplicating by a Key While Keeping the Whole Object

A common requirement: "Keep **the entire product**, but only one product per `sku`." If the existing class defines `equals` over multiple fields and cannot be changed, calling `distinct()` directly will **not suffice**.

There are at least two clear options:

**Option A — Only the list of keys is needed:** use `map` to the key, then `distinct`.

~~~java
List<String> uniqueSkus = products.stream()
    .map(Product::sku)
    .distinct()
    .collect(java.util.stream.Collectors.toList());
~~~

This snippet assumes `Product` is a record with accessor `sku()` as in section 5. The result is `List<String>`; other product fields are no longer retained.

**Option B — Need to keep the whole object and pick the first record per key:** collect into a `LinkedHashMap` with a merge function that retains the older value.

~~~java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

// products is List<Product> from the record example in section 5.
Map<String, Product> firstBySku = products.stream()
    .collect(Collectors.toMap(
        Product::sku,
        Function.identity(),
        (first, later) -> first,
        LinkedHashMap::new
    ));

List<Product> uniqueProducts = new ArrayList<>(firstBySku.values());
~~~

Meaning of the collector arguments:

- `Product::sku`: extracts the **grouping key**.
- `Function.identity()`: keeps the **Product object** as the value.
- `(first, later) -> first`: when keys collide, **keep the previously encountered record**.
- `LinkedHashMap::new`: preserves key insertion order in the result when collecting sequentially from an ordered List.

If the **latest** record is the right one, you need to identify a timestamp or version field and a data-selection policy. Do not assume "the first record" is always right for business logic.

Avoid the trick of using `filter` with an external mutable `HashSet` such as `filter(item -> seen.add(item.getId()))`. That is a stateful predicate, hard to reason about in parallel execution, and goes against the guideline of using behavioral functions independent of external mutable state. When deduplicating by key, a collector or an algorithm with a clearly defined key is easier to maintain.

## 9. Special Cases: `null`, Primitive Types, Unbounded Data

### 9.1. `distinct` Can Keep One `null`

Not every Stream source forbids `null`. For an object Stream containing multiple `null` values, `distinct()` keeps **at most one** `null` value:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<String> values = Arrays.asList(null, "A", null, "A", "B");

List<String> unique = values.stream()
    .distinct()
    .collect(Collectors.toList());

System.out.println(unique); // [null, A, B]
~~~

Conversely, `List.of(...)` from Java 9 **does not allow `null`**, so do not use `List.of(null, ...)` to build this test source. If business logic requires discarding `null`, place `filter(Objects::nonNull)` before `distinct`.

### 9.2. `IntStream` and `LongStream` Also Have `distinct`

For primitive Streams, you do not need to write `equals` or `hashCode`:

~~~java
import java.util.Arrays;

int[] unique = Arrays.stream(new int[] {3, 1, 3, 2, 1})
    .distinct()
    .toArray();

System.out.println(Arrays.toString(unique)); // [3, 1, 2]
~~~

`IntStream.distinct()`, `LongStream.distinct()`, and `DoubleStream.distinct()` are provided by their respective primitive streams. With `DoubleStream`, note the rules for `NaN` and `+0.0`/`-0.0` according to API semantics when processing floating-point numbers; do not simply assume every `==` comparison matches deduplication.

### 9.3. Infinite Sequences Can Make `distinct` Wait Forever

~~~java
import java.util.stream.Stream;

List<Integer> three = Stream.iterate(0, n -> (n + 1) % 3)
    .distinct()
    .limit(3)
    .collect(java.util.stream.Collectors.toList());
// [0, 1, 2]
~~~

The source `0, 1, 2, 0, 1, 2, ...` is infinite, but it has **three** distinct values, so `limit(3)` after `distinct` can receive enough results and terminate.

Conversely, the pipeline:

~~~java
// Does not terminate normally: there are only 3 distinct values.
// Stream.iterate(0, n -> (n + 1) % 3)
//     .distinct()
//     .limit(4)
//     .toList();
~~~

will keep waiting for a **fourth unique value**, which does not exist. With unbounded sources, ensure the terminal operation truly has a reachable stopping condition, and account for memory when the number of unique values grows indefinitely.

## 10. Performance and Parallel Streams

Because `distinct()` is a **stateful intermediate operation**, it typically must maintain information about seen values. When data has many distinct values, the memory needed to track duplicates can grow significantly.

A common analytical model assuming a good hash structure:

- Average processing time can be close to **O(n)** for `n` elements if `hashCode` distributes well and the cost of `equals/hashCode` is reasonable.
- Memory for recording unique values typically grows with the number of **distinct** elements.
- When there are many hash collisions, expensive equality checks, or when the implementation must preserve encounter order, cost can increase.

This is a **directional estimate**, not a fixed complexity guarantee from the API contract. Implementation details, input size, ordering, and downstream operations all affect actual cost.

### 10.1. `distinct` on a Parallel Stream

~~~java
List<String> unique = names.parallelStream()
    .distinct()
    .collect(java.util.stream.Collectors.toList());
~~~

For a **Stream with an encounter order**, `distinct` in a parallel stream must still keep the **first-appearing representative**. To ensure stability, the implementation may have to coordinate multiple branches and erect significant synchronization barriers, reducing the benefit of parallel execution.

If **ordering and keeping the first representative do not matter**:

~~~java
List<String> uniqueUnordered = names.parallelStream()
    .unordered()
    .distinct()
    .collect(java.util.stream.Collectors.toList());
~~~

`unordered()` may allow a better-optimized implementation. However, do not apply it if the result requires display ordering or selecting the first record in a group. Also do not assume `parallelStream()` is faster: measure with benchmarks appropriate for your application's data and environment.

### 10.2. Do Not Turn `distinct` into a Source of Side Effects

~~~java
long count = List.of("A", "A", "B").stream()
    .map(value -> {
        System.out.println("Seen: " + value);
        return value;
    })
    .distinct()
    .count();
~~~

The number of times `map` is invoked must not be a business correctness condition. Streams are allowed to optimize pipelines when the final result does not require fully evaluating every intermediate operation in certain cases. With `distinct`, equivalence groups must be determined to return a count, yet invocation counts and callback execution order are still not an interface for guaranteeing logging or state updates. Use transformations without side effects, and design logging or business I/O at controllable boundaries.

## 11. Practice Exercise: Deduplicating a Registration Email List

The system receives a list of emails:

~~~java
List<String> emails = List.of(
    "  AN@example.com ",
    "binh@example.com",
    "an@EXAMPLE.com",
    "chi@example.com",
    "binh@example.com"
);
~~~

**Requirement:** Trim leading and trailing whitespace, normalize to lowercase using `Locale.ROOT`, remove duplicates while preserving the order of appearance of each normalized email. Then count the total number of valid emails using the simple rule that they are non-empty. Note that this exercise only performs technical normalization and **does not claim** every email system treats the part before `@` as case-insensitive.

**Solution (Java 9+):**

~~~java
import java.util.List;
import java.util.Locale;
import java.util.stream.Collectors;

public class UniqueEmailDemo {
    public static void main(String[] args) {
        List<String> emails = List.of(
            "  AN@example.com ",
            "binh@example.com",
            "an@EXAMPLE.com",
            "chi@example.com",
            "binh@example.com"
        );

        List<String> uniqueEmails = emails.stream()
            .map(String::trim)
            .map(email -> email.toLowerCase(Locale.ROOT))
            .filter(email -> !email.isEmpty())
            .distinct()
            .collect(Collectors.toList());

        System.out.println(uniqueEmails);
        System.out.println("Distinct email count: " + uniqueEmails.size());
    }
}
~~~

Output:

~~~text
[an@example.com, binh@example.com, chi@example.com]
Distinct email count: 3
~~~

**Self-check:**

1. If you put `distinct()` **before** the two normalization steps, would the result still be three unique emails? — **No**; differences in whitespace and casing exist at comparison time.
2. Does `distinct()` compare two strings with `==` or `equals`? — **`equals`**.
3. Would two products with the same `sku` but different `name` in `record Product(String sku, String name)` be merged? — **No**, a record compares both fields by default.
4. If you only override `equals` without ensuring a consistent `hashCode`, what can happen? — Hash-based structures and deduplication operations may behave incorrectly.
5. Is `unordered().distinct()` required to pick the first-appearing record? — **No**.
6. Why can `distinct().limit(4)` on an infinite source with only three unique values run without terminating? — Because **a fourth unique value never exists**.

## 12. Key Takeaways and Application Guidelines

`distinct()` is the Stream operation for **removing duplicate elements**, determining object duplication via `equals` and requiring a consistent `hashCode` contract. For Streams with an encounter order, it keeps the **first representative**; for unordered Streams, do not rely on ordering or which representative is chosen. It is a **lazy, stateful** intermediate operation, so pay attention to performance, memory, and pipeline termination.

Before applying it, answer four questions: **"Duplicate" by which fields?**; **does the class define `equals`/`hashCode` by those fields yet?**; **do you need to keep the first record or a record chosen by another rule?**; and **after deduplicating, what result ordering and size are needed?**

Once you understand these points, you can combine `filter`, `map`, `distinct`, `sorted`, `limit`, and `collect` accurately; for complex key-based deduplication, grouping or a custom collector may be more appropriate. The rules on state, ordering, and stability also serve as an important foundation when learning `Spliterator`, parallel Streams, and Stream Gatherers in subsequent sections.
