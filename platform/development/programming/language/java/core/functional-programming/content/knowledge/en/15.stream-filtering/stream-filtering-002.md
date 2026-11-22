# Stream.distinct() and the Impact of equals() and hashCode() in Java

`distinct()` is an **intermediate operation** of the Java Stream API used to remove **duplicate** elements and keep only distinct elements according to object equality. It often appears in pipelines such as `stream().distinct().toList()`, but the result is not simply "removing objects with the same displayed data": Java relies on **`equals()`** to determine equality according to the element type's contract. Properly implementing **`hashCode()`** is essential so that hash-based structures can group and look up objects consistently, including common implementations of `distinct()`.

For example, with `List.of("Java", "Java", "Kotlin")`, the two `"Java"` strings are equal according to `String.equals()`, so `distinct()` keeps only one. Conversely, two instances of a regular class **do not automatically become equal just because all their fields have the same values**; if the class does not override `equals()`, it typically inherits identity comparison from `Object`.

This lesson explains the mechanism, order stability, the `equals`/`hashCode` contract, comparison with `record`, how to deduplicate by a business key, and pitfalls to avoid when running sequential or parallel Streams. Examples use Java 17+.

## 1. Syntax, Role, and Execution Timing

For `Stream<T>`, the basic syntax is:

```java
Stream<T> uniqueStream = sourceStream.distinct();
```

This is a **syntax pattern**; `sourceStream` must be an existing `Stream<T>` in context. `distinct()` returns **a new Stream** and does not mutate the source collection itself.

In a complete pipeline:

```java
List<String> unique = List.of("A", "B", "A", "C", "B")
        .stream()
        .distinct()
        .toList();
// [A, B, C]
```

The snippet above is a code fragment that requires `import java.util.List;` and must be placed inside a method. `distinct()` is a **stateful intermediate operation**: to determine whether an element has been seen before, the pipeline must maintain enough state to recognize previous elements (implementation details are determined by the JDK). It is **lazy**: creating the pipeline does not mean the entire list has been traversed; the terminal operation `toList()` triggers processing.

Do not expect `distinct()` to remove or update elements in the original `List`. The new Stream may contain fewer elements, but the original source is not modified by `distinct()`.

## 2. What Does "Duplicate" Mean?

The Stream API contract specifies that elements are distinct **according to `Object.equals(Object)`**. In common examples:

| Element Type | Default or Common Comparison Rule | Impact on distinct |
| --- | --- | --- |
| `String` | Content comparison, case-sensitive | `"Java"` and `"Java"` are duplicates, `"Java"` and `"java"` are different |
| `Integer` | Compares the boxed numeric value | Two `Integer` instances with the same value are considered duplicates |
| `record` | Auto-generated `equals` and `hashCode` based on components | Records of the same type with equal components are considered duplicates |
| Regular class without overriding `equals` | Inherits `Object.equals`, typically same reference | Two different instances are not automatically duplicates, even if fields are equal |
| Class overriding `equals` per contract | Equality defined by the class | Can deduplicate by ID, code, or business rule |
| Arrays, e.g., `int[]` | `Object.equals` by reference, does not compare elements | Two different arrays with the same contents are still two distinct elements |

**Distinguishing equality from identity:** the expression `a == b` checks for the same reference on objects; `a.equals(b)` checks equality as defined by the class. `distinct()` follows **equality**, not a custom `==` check.

`distinct()` also does not automatically distinguish between "duplicate by product code" and "duplicate by all attributes". That rule must be built into the element type's `equals` or represented by an explicit key in the pipeline.

## 3. Java 17 Program: String, null, and Data Normalization

Save as **`DistinctBasicsDemo.java`**:

```java
import java.util.List;
import java.util.Locale;
import java.util.stream.Stream;

public class DistinctBasicsDemo {
    public static void main(String[] args) {
        List<String> languages =
                List.of("Java", "Kotlin", "Java", "java", "Kotlin");

        System.out.println("unique=" + languages.stream()
                .distinct()
                .toList());

        System.out.println("normalized=" + languages.stream()
                .map(s -> s.toLowerCase(Locale.ROOT))
                .distinct()
                .toList());

        // Stream.of can contain null; List.of does not accept null.
        List<String> withNulls =
                Stream.of("A", null, "A", null, "B")
                        .distinct()
                        .toList();

        System.out.println("withNulls=" + withNulls);
        System.out.println("sourceSize=" + languages.size());
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 DistinctBasicsDemo.java
java DistinctBasicsDemo
```

**Exact stdout:**

```text
unique=[Java, Kotlin, java]
normalized=[java, kotlin]
withNulls=[A, null, B]
sourceSize=5
```

Explanation:

1. `String.equals` is case-sensitive, so `"Java"` and `"java"` are not equal. The second occurrences of `"Java"` and `"Kotlin"` are removed.
2. `map(s -> s.toLowerCase(Locale.ROOT))` creates normalized strings **before** distinct, so `"Java"` and `"java"` both become `"java"`.
3. This Stream has an ordered source; `distinct()` keeps the **first element encountered** in each equal group. `null` is kept at most once; `Stream.toList()` supports `null` in the resulting list, whereas `List.of(..., null, ...)` throws `NullPointerException`.
4. `languages` still has 5 elements. `distinct()` does not modify the source.

Do not assume every pipeline handles `null` safely. If you place `.map(String::toLowerCase)` before filtering `null`, the instance method call can throw `NullPointerException`. When data is nullable and needs normalization, use `.filter(Objects::nonNull)` before calling methods on strings.

## 4. equals() Rules: Deciding Whether Two Objects Are Equal

`Object.equals(Object other)` has a fundamental contract:

- **Reflexive:** if `x` is non-null, `x.equals(x)` is true.
- **Symmetric:** `x.equals(y)` and `y.equals(x)` must return the same result.
- **Transitive:** if `x.equals(y)` and `y.equals(z)` are both true, then `x.equals(z)` must be true.
- **Consistent:** as long as the relevant data does not change, comparison results should be consistent.
- **Non-null:** `x.equals(null)` must be false for non-null `x`.

For a regular class, if not overridden, `Object.equals` essentially compares for the **same object**. If you want to recognize two entities as duplicates by `id`, you need to define the corresponding equality rule.

For example, a class has two objects with the same `id` but different `name`: if `equals` is defined by `id`, `distinct()` will keep only one from the group. If business logic needs to treat two different versions as distinct, the equality rule may need the relevant fields as well or a specific version key.

**Do not change the meaning of `equals` on a domain object just to satisfy one special pipeline.** Equality is a class-wide contract and affects `HashSet`, `HashMap`, `contains`, and other parts of the application. When you need to deduplicate by a local key, consider an alternative pipeline using an explicit key.

## 5. The hashCode() Contract: Why Must It Accompany equals()?

`hashCode()` returns an integer representing the object according to the hash contract. The most important rule:

> **If `a.equals(b)` is true, then `a.hashCode() == b.hashCode()` must be true.**

The converse is **not required**: two objects with the same hash code can still be different, and `equals` can return false. Hash collisions are normal; a proper hash structure must check equality to distinguish colliding values.

Why does this matter? Many structures organize objects by hash first, then use equals to confirm whether an object already exists. If two objects are **equal according to equals but have different hashCode values**, they may be placed in different buckets and mistakenly treated as two separate values. A hash-set-based implementation of `distinct()` may exhibit unintended behavior if a class violates this contract.

**Do not infer that the Stream API guarantees using a specific internal HashSet:** the specification describes distinctness using `equals`; specific algorithms and optimizations may vary across JDK versions or pipelines. It is the class author's responsibility to provide `equals` and `hashCode` that satisfy the contract.

In addition, values participating in `equals`/`hashCode` should be **stable while the object resides in a hash structure**. Modifying a field used to compute the hash after the object has been inserted into a set can cause lookups and duplicate detection to become inaccurate or unpredictable.

## 6. Java 17 Program: Class with Custom Equality and record

Save as **`DistinctDomainDemo.java`**:

```java
import java.util.List;
import java.util.Objects;

public class DistinctDomainDemo {
    static final class Product {
        private final int id;
        private final String name;

        Product(int id, String name) {
            this.id = id;
            this.name = name;
        }

        String name() {
            return name;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof Product product)) {
                return false;
            }
            return this.id == product.id;
        }

        @Override
        public int hashCode() {
            return Integer.hashCode(id);
        }
    }

    record Book(String code, String title) {}

    static final class Plain {
        private final String name;

        Plain(String name) {
            this.name = name;
        }
    }

    public static void main(String[] args) {
        List<Product> products = List.of(
                new Product(1, "Sách Java"),
                new Product(1, "Sách Java bản cập nhật"),
                new Product(2, "Sách Kotlin"),
                new Product(2, "Sách Kotlin bản cập nhật")
        );

        System.out.println("productNames=" + products.stream()
                .distinct()
                .map(Product::name)
                .toList());

        List<Book> books = List.of(
                new Book("B1", "First"),
                new Book("B1", "Second"),
                new Book("B1", "First")
        );

        System.out.println("books=" + books.stream()
                .distinct()
                .map(Book::title)
                .toList());

        List<Plain> plain = List.of(
                new Plain("X"),
                new Plain("X")
        );
        System.out.println("plainCount=" + plain.stream().distinct().count());

        System.out.println("productEquality="
                + products.get(0).equals(products.get(1)));
        System.out.println("sameHash="
                + (products.get(0).hashCode() == products.get(1).hashCode()));
    }
}
```

Compile and run on JDK 17:

```bash
javac -encoding UTF-8 DistinctDomainDemo.java
java DistinctDomainDemo
```

**Exact stdout:**

```text
productNames=[Sách Java, Sách Kotlin]
books=[First, Second]
plainCount=2
productEquality=true
sameHash=true
```

Explanation:

1. `Product.equals` compares `id`, and `hashCode` is also based on `id`. Two products with the same `id` are considered equal even if `name` differs. Because the source is an ordered List, `distinct()` keeps the first record appearing in each group.
2. `Book` is a `record`. Java automatically generates `equals` and `hashCode` based on both `code` and `title`; `Book("B1","First")` and `Book("B1","Second")` are different, while the repeated `"First"` entry is removed.
3. `Plain` does not override `equals`, so the two `new Plain("X")` instances are two different objects; the count after distinct remains 2.
4. The first two `Product` instances have the same `id`; `equals` returns true and `hashCode` values are equal, satisfying the required contract.

The example above chooses equality by ID **for illustration purposes**. Some domain objects have requirements around unassigned IDs, composite keys, or entity lifecycles; define `equals`/`hashCode` according to your actual business contract.

## 7. The Mistake of Overriding equals Without hashCode

The following class pattern is a **warning about a broken-contract design**, not for use in real applications:

```java
class BrokenItem {
    private final int id;

    BrokenItem(int id) {
        this.id = id;
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof BrokenItem item && id == item.id;
    }

    // WRONG: does not override hashCode().
}
```

Two instances of `new BrokenItem(7)` can have `equals` return true while inheriting `Object.hashCode`, which is not guaranteed to produce the same hash code. This is a **violation of the mandatory rule**: equal objects must have equal hash codes.

Minimal fix:

```java
@Override
public int hashCode() {
    return Integer.hashCode(id);
}
```

This is an **additional code snippet inside class `BrokenItem`**, not a standalone top-level method. When designing equality across multiple fields, you can use `Objects.equals` and `Objects.hash` on the exact corresponding set of fields. When performance matters, you can compute the hash directly from fields; the core requirement is that **two equal objects must have equal hashes**.

**Do not write unit tests expecting `distinct()` to definitely remove or definitely keep a pair of objects that violate the contract.** Behavior under broken equality/hash is not a valid basis for API design. Fix the class first, then test `equals`, `hashCode`, `HashSet`, and pipeline results.

## 8. Encounter Order: Which Element Does distinct Keep?

On an **ordered Stream**, `distinct()` is **stable**: if multiple elements are equal, it keeps the element that **appears first in encounter order**. For example:

```java
List<String> values = List.of("B", "A", "B", "C", "A");
List<String> result = values.stream().distinct().toList();
// [B, A, C]
```

This illustrative snippet requires `import java.util.List;`.

With a parallel Stream that is still **ordered**, this stability remains a requirement on the result. Processing work may happen out of order across threads, but the result of `distinct().toList()` still keeps the first-seen element and preserves encounter order.

With an **unordered Stream**, the API **does not guarantee keeping the first occurrence** or the result order, because there is no encounter order to preserve. `unordered()` only removes the ordering constraint; it does not mean elements will be randomly shuffled on every run.

**Especially with objects sharing a key but having different data:** if `Product.equals` is based on ID, which duplicate is kept can carry business meaning. When you need the "latest record" or a preferred record, define an explicit selection rule instead of relying on the unguaranteed order of unordered/parallel processing.

## 9. Java 17 Program: ordered, parallel, and unordered

Save as **`DistinctOrderDemo.java`**:

```java
import java.util.List;
import java.util.TreeSet;
import java.util.stream.Collectors;

public class DistinctOrderDemo {
    public static void main(String[] args) {
        List<String> names = List.of("B", "A", "B", "C", "A", "D");

        List<String> sequential = names.stream()
                .distinct()
                .toList();

        List<String> parallel = names.parallelStream()
                .distinct()
                .toList();

        TreeSet<String> sortedDistinct = names.parallelStream()
                .unordered()
                .distinct()
                .collect(Collectors.toCollection(TreeSet::new));

        System.out.println("sequential=" + sequential);
        System.out.println("parallel=" + parallel);
        System.out.println("unorderedAsSortedSet=" + sortedDistinct);
        System.out.println("uniqueCount=" + names.parallelStream()
                .distinct()
                .count());
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 DistinctOrderDemo.java
java DistinctOrderDemo
```

**Exact stdout:**

```text
sequential=[B, A, C, D]
parallel=[B, A, C, D]
unorderedAsSortedSet=[A, B, C, D]
uniqueCount=4
```

Both `sequential` and `parallel` start from a List with encounter order, so they preserve first-occurrence order. For the `unordered()` pipeline, the program **does not assume any order returned by distinct**; instead, `TreeSet` sorts the strings in natural order to produce predictable output. The result only illustrates the set of distinct values; it does not prove in what order the unordered pipeline processed elements.

When the source contains objects with complex equality or lacks encounter order, never treat the output of one run as an ordering guarantee for another run.

## 10. distinct() on a parallel Stream: Correct but Potentially Costly

`distinct()` is a **stateful intermediate operation**. In an **ordered** parallel Stream, keeping the first occurrence of each value often requires coordination, state storage, or buffering; these steps can introduce significant overhead compared to a pipeline without deduplication.

Points to consider:

- **Data source:** a List can usually be split by index; sources that split poorly can make parallel execution inefficient.
- **Element count and duplicate rate:** large datasets with heavy processing may benefit, but managing the set of seen values also has a cost.
- **Cost of hashCode/equals:** complex hash computations or comparisons increase overhead.
- **Ordering constraints:** ordered `distinct()` requires stability; if business logic does not need the first element, `unordered()` may allow optimizations.
- **Correctness:** mutable objects or inconsistent `equals`/`hashCode` risk wrong results; parallelism cannot fix that.
- **Resources:** extra task creation, state storage, allocation, and contention can all have an impact.

Always **measure with an appropriate benchmark such as JMH** on real data before claiming parallel is faster. `parallelStream()` does not guarantee how many threads will be used, does not guarantee a speedup, and is not a solution for a broken equality algorithm.

## 11. Deduplicating by a Business Key Without Changing the Class's equals

Sometimes you want to deduplicate by `email` or `productId`, while the class's natural equality is based on multiple attributes. Avoid changing `equals` across the entire class just for a single local filter.

### 11.1. If You Only Need the List of Unique Keys

A simple, clear solution:

```java
List<String> uniqueCodes = products.stream()
        .map(Product::code)
        .distinct()
        .toList();
```

This is an **illustrative code snippet**: `products` is a source of an appropriate type and `Product::code` is an accessor that exists in the application. It returns **unique keys**, not the full product objects.

### 11.2. If You Need to Keep the First Object per Key

With an ordered `List` source, you can collect into a `LinkedHashMap` with a rule to keep the first value:

```java
record Item(String code, String label) {}

List<Item> items = List.of(
        new Item("A", "First"),
        new Item("A", "Second"),
        new Item("B", "Third")
);

List<Item> uniqueByCode = new java.util.ArrayList<>(
        items.stream()
                .collect(java.util.stream.Collectors.toMap(
                        Item::code,
                        item -> item,
                        (first, later) -> first,
                        java.util.LinkedHashMap::new))
                .values()
);
// [Item[code=A, label=First], Item[code=B, label=Third]]
```

This is a **code snippet placed inside a method**, except for the `record Item` declaration which belongs at top-level or in a nested class context. It requires `import java.util.List;`. `toMap` with the merge function `(first, later) -> first` resolves duplicate keys, while `LinkedHashMap` maintains insertion order of the keys. In this sequential Stream example with encounter order, the result keeps the first object for each key.

**Do not apply the same "first" ordering expectation directly to an unordered/parallel pipeline** without analyzing the collector and ordering contract. If you want a preferred record by timestamp, version, or a comparator, put the selection rule into the merge function or choose a transparent algorithm.

### 11.3. Using a record as a Composite Key

If "duplicate" means matching two attributes, create an immutable composite key:

```java
record Key(String category, String code) {}
```

A record automatically provides `equals` and `hashCode` for its components. In a pipeline, you can `map(item -> new Key(item.category(), item.code()))` and then `distinct()` if the goal is a list of unique **keys**. To keep the objects, use a map/collector with that key. This approach protects the domain class's equality from being altered just to serve a single report.

## 12. Subtle Cases

### 12.1. BigDecimal Where equals Differs from compareTo

`BigDecimal.equals` considers both **value and scale**, whereas `BigDecimal.compareTo` compares numeric values according to a different rule. Therefore:

```java
List<java.math.BigDecimal> values = List.of(
        new java.math.BigDecimal("1.0"),
        new java.math.BigDecimal("1.00")
);

System.out.println(values.stream().distinct().toList());
// [1.0, 1.00]
```

This is a code snippet requiring `import java.util.List;`. Two values may compare numerically with `compareTo(...) == 0`, yet `equals` returns false due to different scales, so `distinct()` keeps both. If business logic wants to treat them as the same numeric value, consider `stripTrailingZeros()` or a normalization policy before calling `distinct`, while checking business requirements regarding scale.

### 12.2. Arrays Do Not Deep-Compare Elements

```java
int[] a = {1, 2};
int[] b = {1, 2};
long count = java.util.stream.Stream.of(a, b).distinct().count();
// 2: two separate arrays, Object.equals compares references.
```

This snippet is valid when `Stream.of(a, b)` is understood as a two-element Stream of type `int[]`. If you want to deduplicate by **array contents**, create a wrapper whose equality is based on `Arrays.equals`/`Arrays.hashCode` or convert to an appropriate immutable key representation.

### 12.3. Null Differs from Objects with Empty Values

`null`, the string `""`, the number `0`, and an object with empty fields are not synonymous. `distinct()` does not merge them automatically. If you want to treat certain states as equivalent, normalize before calling distinct—for example, `trim`/lowercase or mapping invalid data to an explicit representative code.

### 12.4. distinct() Cannot Replace Every Element-Selection Operation

If the goal is to get **one element matching a condition**, you can use `filter` and `findFirst`/`findAny`. If the goal is **sorting**, use `sorted`. If the goal is **grouping by key**, use `groupingBy` or an appropriate `toMap`. `distinct()` only handles **duplicates by equality** of the elements passing through the pipeline at that position.

For example, `map(Product::id).distinct()` returns a list of IDs, not a list of Products; the position of `map` relative to `distinct` can change the meaning of "duplicate" being checked.

## 13. Side Effects, Mutation, and Reliability

Predicates and mappers in a Stream should be **non-interfering** and **stateless** whenever possible. For `distinct`, especially avoid mutating fields participating in `equals` or `hashCode` while the pipeline is processing that object.

Risky example:

```java
// Do not do this inside a Stream processing Set/hash-based uniqueness:
// product.setId(newId); // id is used in equals/hashCode
```

This is a line **illustrating a mistake to avoid**, not a standalone runnable call. Modifying an attribute involved in hashing while the object resides in a hash structure can break membership. With a parallel Stream, multiple threads mutating objects concurrently only increases the risk of race conditions.

Avoid using `peek` or a `map` with side effects to "change IDs and distinct at the same time". Perform data normalization before the pipeline and use objects/keys that remain unchanged while the result is computed.

## 14. Common Mistakes

1. **Thinking distinct uses `==`:** it uses equality via `equals`, not arbitrary reference identity.
2. **Overriding `equals` without overriding `hashCode`:** violates the contract with hash structures.
3. **Believing identical hashes mean equal objects:** hash collisions can still occur; `equals` is required.
4. **Assuming two objects with the same fields are duplicates:** regular classes inherit `Object.equals` unless overridden.
5. **Expecting a record to compare only one field:** records use all components in equality by default.
6. **Expecting distinct to automatically remove empty strings or null:** it only removes duplicates; filter by other rules if needed.
7. **Expecting distinct to ignore case differences:** `String.equals` is case-sensitive; normalize before distinct.
8. **Expecting parallel unordered to always keep the "first record":** only ordered Streams have a stability contract based on encounter order.
9. **Thinking distinct mutates the source List:** it returns a new Stream and does not modify the collection.
10. **Assuming distinct runs immediately when called:** it is a stateful intermediate operation; a terminal operation triggers the pipeline.
11. **Using equals/hashCode based on mutable fields:** mutating fields after inserting an object into a hash structure can break membership.
12. **Using distinct instead of groupingBy or selecting the latest object:** design an explicit key-based selection instead.
13. **Assuming parallel distinct is always faster:** preserving order and managing state can add overhead.
14. **Thinking `toList()` always returns a mutable ArrayList:** `Stream.toList()` returns an unmodifiable list by API contract.
15. **Assuming every terminal operation must call the mapper exactly once per element:** Streams can short-circuit or optimize; do not put mandatory logic into side effects.

## 15. Self-Check Exercises

**Question 1.** What is the result of `List.of("A", "a", "A").stream().distinct().toList()`?

**Answer:** `[A, a]`, because `String.equals` is case-sensitive.

**Question 2.** How would you write a case-insensitive deduplication (accepting lowercase results)?

```java
List<String> unique = values.stream()
        .map(s -> s.toLowerCase(java.util.Locale.ROOT))
        .distinct()
        .toList();
```

This is a code snippet requiring `values` of type `List<String>` containing no nulls.

**Question 3.** Why were the two `new Plain("X")` instances in the example not considered duplicates?

Because `Plain` does not override `equals`, so two separate instances are compared by `Object` identity.

**Question 4.** If `equals` returns true between two objects, what is required of `hashCode`?

**Answer:** Both objects must have **the same hashCode value**. The converse is not required.

**Question 5.** Given an ordered List source, does `parallelStream().distinct().toList()` preserve encounter order and the first-appearing element?

**Yes**, because an ordered Stream requires distinct to be stable, and `toList` preserves the encounter order of the result. Internal execution order across threads may still differ.

**Question 6.** If class `Product` has `equals` based on `id`, does `distinct()` distinguish two products with the same `id` and different `name`?

**No**; they are considered equal according to the class's contract. If you only want this rule for a single pipeline, use `toMap`/a key-based collector instead of changing class-wide equality.

**Question 7.** Why are `BigDecimal("1.0")` and `BigDecimal("1.00")` not collapsed into one by distinct?

Because `BigDecimal.equals` also considers scale, even though `compareTo` may return 0.

**Question 8.** Why should a pipeline with `distinct()` not rely on objects whose `id` is continuously mutated during processing?

Because equality and hash must remain consistent during processing, especially with hash structures and multiple threads; mutating data participating in equality/hash makes results unpredictable.

**Key takeaway:** **`distinct()` removes duplicates according to `equals()`; a class overriding `equals()` must maintain a consistent `hashCode()`.** Ordered Streams keep the first element encountered; unordered Streams make no such guarantee. When you need to deduplicate by a specific field, represent the business key explicitly instead of defaulting to changing `equals` for the entire class.
