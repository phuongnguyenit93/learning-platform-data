# Deduplicating Data While Preserving Appearance Order in Java Collections

## 1. The Problem and Correctness Criteria

Given a sequence of potentially repeating elements, remove duplicate elements while **preserving the first-appearance order** of each element. The result must contain each logical value exactly once, at the position corresponding to its first occurrence in the source data.

For example:

```text
Input: [Java, SQL, Java, null, Go, SQL, null, Kotlin, Go]
Output: [Java, SQL, null, Go, Kotlin]
```

In this example, the second `Java`, the second `SQL`, the second `null`, and the second `Go` are removed. The first `null` remains if the collection and business policy allow `null` values.

It is important to distinguish three commonly confused requirements:

- **No duplicates:** each group of elements considered equal appears only once.
- **Order preservation:** if the first occurrence of `A` comes before the first occurrence of `B`, then `A` still comes before `B` in the result.
- **Keeping the first record:** when two objects share the same key but have different attributes, the result keeps the object that appeared first, unless the problem specifies a different rule.

This is a Java Collections practical exercise. Choosing the right data structure depends on whether you need to return a `List` or a `Set`, whether modifying the input data is allowed, and whether "duplicate" is defined by the entire object or by a business key.

## 2. The Simple Approach: `LinkedHashSet`

`LinkedHashSet` is a set that removes duplicate elements based on `equals()` and `hashCode()` while maintaining **insertion order** during iteration. When an element already present in the set is added again, the set does not create a new entry and does not move the position of the existing element.

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashSet;
import java.util.List;

public class LinkedHashSetDemo {
    public static void main(String[] args) {
        List<String> input = Arrays.asList(
                "Java", "SQL", "Java", null, "Go",
                "SQL", null, "Kotlin", "Go"
        );

        List<String> unique = new ArrayList<>(new LinkedHashSet<>(input));

        System.out.println("Input : " + input);
        System.out.println("Unique: " + unique);
    }
}
```

Save as `LinkedHashSetDemo.java`; run with JDK 17 or later:

```bash
javac -encoding UTF-8 LinkedHashSetDemo.java
java LinkedHashSetDemo
```

Output:

```text
Input : [Java, SQL, Java, null, Go, SQL, null, Kotlin, Go]
Unique: [Java, SQL, null, Go, Kotlin]
```

Explanation:

1. The constructor `new LinkedHashSet<>(input)` iterates through the elements of `input` and attempts to add each one to the set in turn.
2. The first time a value is encountered, the set stores it; subsequent occurrences determined to be equal by `equals()` are not added.
3. `LinkedHashSet` preserves insertion order, so iterating through the set yields the order of first appearance.
4. `new ArrayList<>(...)` converts the result back into a `List` when index-based access or compatibility with APIs accepting `List` is required.

If the output can be a `Set`, simply keep the `LinkedHashSet`:

```java
LinkedHashSet<String> uniqueSet = new LinkedHashSet<>(input);
```

`LinkedHashSet` allows one `null` element; however, `List.of(...)` disallows `null` elements right at initialization. That is why the example uses `Arrays.asList(...)`. This approach creates a new collection and does not modify `input`.

### Why Not Use `HashSet` or `TreeSet` to Obtain the Result Directly?

- `HashSet` removes duplicates but **makes no guarantee about iteration order**. An output that appears to be in the right order during a single run is not an API guarantee.
- `TreeSet` sorts elements according to natural ordering or a `Comparator` rather than preserving first-appearance order. It also imposes additional comparability requirements, and duplicate detection is based on `compare(...) == 0`.
- `LinkedHashSet` simultaneously satisfies the requirements of uniqueness and insertion-order preservation. Do not write code like `new ArrayList<>(new HashSet<>(input))` if the output is required to preserve the original order.

## 3. The Single-Pass Approach: Tracking `HashSet` + Result `ArrayList`

If you want to make the algorithm explicit, or need custom keep/discard conditions, iterate through the input from left to right, use a `Set` to mark values already seen, and add a value to the result `List` only on its first appearance.

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public class SeenSetDemo {
    public static void main(String[] args) {
        List<String> input = Arrays.asList(
                "Java", "SQL", "Java", null, "Go",
                "SQL", null, "Kotlin", "Go"
        );
        Set<String> seen = new HashSet<>();
        List<String> unique = new ArrayList<>();

        for (String value : input) {
            if (seen.add(value)) {
                unique.add(value);
            }
        }
        System.out.println(unique);
    }
}
```

Run:

```bash
javac -encoding UTF-8 SeenSetDemo.java
java SeenSetDemo
```

```text
[Java, SQL, null, Go, Kotlin]
```

`Set.add(value)` returns `true` if the set changed because a previously absent element was added; it returns `false` if the element was already present. This performs both checking and marking in a single operation, avoiding redundant `contains(value)` calls before `add(value)`.

Note: `HashSet` here is **not** iterated over to build the result; it only tracks "already seen" state. It is the `ArrayList`, populated in loop order, that determines the output order. Therefore, using a `HashSet` as a tracking set still completely satisfies the order-preservation requirement.

An alternative way to modify a **mutable** list in place:

```java
List<String> mutable = new ArrayList<>(input);
Set<String> seen = new HashSet<>();
mutable.removeIf(value -> !seen.add(value));
```

`removeIf` removes the second and subsequent occurrences while preserving the relative order of the remaining elements. This approach mutates `mutable`; it cannot be applied directly to `List.of(...)` or the fixed-size list returned by `Arrays.asList(...)`, because they do not support removal operations. Prefer creating a new result list if you need to keep the input intact or want clearer code.

## 4. Stream API with `distinct()`

With Java Streams, the `distinct()` operator removes duplicate elements based on `Object.equals(Object)`. For an **ordered stream**, `distinct()` preserves the first element in each duplicate group according to encounter order—the order in which the data source feeds elements into the stream.

```java
import java.util.Arrays;
import java.util.List;

public class StreamDistinctDemo {
    public static void main(String[] args) {
        List<String> input = Arrays.asList(
                "Java", "SQL", "Java", null, "Go",
                "SQL", null, "Kotlin", "Go"
        );

        List<String> unique = input.stream()
                .distinct()
                .toList();

        System.out.println(unique);
    }
}
```

```bash
javac -encoding UTF-8 StreamDistinctDemo.java
java StreamDistinctDemo
```

```text
[Java, SQL, null, Go, Kotlin]
```

Key points to remember:

- `List.stream()` is an ordered stream following the list's iteration order. With this source, `distinct()` keeps the first occurrence.
- `Stream.toList()` was introduced in Java 16 and returns an **unmodifiable** `List`; calling `add` or `remove` on the result will throw `UnsupportedOperationException`. If you need a mutable list, use `new ArrayList<>(input.stream().distinct().toList())` or `collect(Collectors.toCollection(ArrayList::new))`.
- `stream().unordered()` drops the requirement to preserve encounter order. On an unordered stream, do not rely on which element is kept within a duplicate group or on the output order.
- `parallelStream().distinct()` on an ordered stream must still guarantee the stability of `distinct`, but the coordination required to preserve order can incur significant memory and synchronization overhead; do not assume parallel execution will be faster by default.
- `distinct()` does not accept a key-extraction function. If "duplicate" is defined by an `id`, `email`, or custom normalization rule, you need a key-based algorithm as shown in the next section.

## 5. Object Duplicates: `equals()`, `hashCode()`, and Business Keys

For object elements, what counts as a "duplicate" depends on how equality is defined. `HashSet` and `LinkedHashSet` use `equals()` and `hashCode()`: if two objects are equal according to `equals()`, they **must** have the same `hashCode()`. If a class overrides one of these methods without honoring the general contract, hash-based collections may behave incorrectly.

For example, a Java `record` automatically generates `equals()` and `hashCode()` based on all declared components. Two `Employee` instances with the same `id` but different `name` values are still **distinct** under the record's default equality. To deduplicate by `id` while keeping the first record, explicitly separate the business key from whole-object equality.

```java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.function.Function;

public class DistinctByKeyDemo {
    record Employee(long id, String name) {}

    static <T, K> List<T> distinctByKey(
            Iterable<T> items,
            Function<? super T, ? extends K> keyExtractor) {
        Objects.requireNonNull(items, "items");
        Objects.requireNonNull(keyExtractor, "keyExtractor");

        Set<K> seenKeys = new HashSet<>();
        List<T> result = new ArrayList<>();

        for (T item : items) {
            K key = keyExtractor.apply(item);
            if (seenKeys.add(key)) {
                result.add(item);
            }
        }
        return result;
    }

    public static void main(String[] args) {
        List<Employee> employees = List.of(
                new Employee(1, "An"),
                new Employee(2, "Bình"),
                new Employee(1, "An cập nhật"),
                new Employee(3, "Chi"),
                new Employee(2, "Bình mới")
        );

        System.out.println(distinctByKey(employees, Employee::id));
    }
}
```

```bash
javac -encoding UTF-8 DistinctByKeyDemo.java
java DistinctByKeyDemo
```

```text
[Employee[id=1, name=An], Employee[id=2, name=Bình], Employee[id=3, name=Chi]]
```

The algorithm retains the exact first object for each `id`; subsequent records with the same `id` are discarded even though their `name` differs. Because the method accepts `Iterable<T>`, it works with `List<T>` or any source that can be iterated in a deterministic order.

Several design decisions should be clarified before applying this approach:

- **Which key defines duplication?** The entire object, an `id`, a normalized email, or a combination of multiple attributes? Different rules can produce different results.
- **Which record should be kept?** This exercise keeps the **first record**. If the requirement is to keep the last record or merge fields, the algorithm must be changed and the desired output order clearly specified.
- **Is a `null` key valid?** `HashSet` accepts a single `null`, so all elements yielding a `null` key will fall into the same group; validate or reject empty/null keys before insertion if the business domain forbids them.
- **Is the key stable?** Avoid mutating fields that participate in `equals()/hashCode()` while an object is stored in a `HashSet` or `LinkedHashSet`. Changing hash codes or equality after insertion can break lookups and deduplication.
- **Is the source order deterministic?** If you iterate from an input `HashSet`, the source itself makes no ordering guarantee; the algorithm only preserves the order actually provided by the iterator and cannot recover an insertion order that was already lost.

## 6. Normalization Before Duplicate Checking

Sometimes `"Java"` and `"java"` are considered duplicates, yet the exact casing of the **first occurrence** must be preserved. There is no need to transform the element added to the result; only normalize the **key** used for comparison.

```java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

public class CaseInsensitiveDemo {
    public static void main(String[] args) {
        List<String> input = List.of("Java", "java", "GO", "go", "SQL");

        Set<String> seenKeys = new HashSet<>();
        List<String> unique = new ArrayList<>();

        for (String value : input) {
            String key = value.toLowerCase(Locale.ROOT);
            if (seenKeys.add(key)) {
                unique.add(value);
            }
        }
        System.out.println(unique);
    }
}
```

```bash
javac -encoding UTF-8 CaseInsensitiveDemo.java
java CaseInsensitiveDemo
```

```text
[Java, GO, SQL]
```

`Locale.ROOT` provides a locale-independent lowercase rule suitable for technical keys. However, simple lowercasing is **not** a complete Unicode normalization for all human languages. If the data contains diacritics, combining characters, whitespace, or email addresses, define the equivalence rule explicitly; depending on requirements, you may need `trim()`, `Normalizer`, or domain-specific rules. Do not strip diacritics or whitespace on your own unless the specification calls for it, as doing so can erroneously merge distinct values.

If the input may contain `null`, establish a policy before invoking methods on elements—for example, allowing a single `null` or filtering `null` out. The example above uses `List.of` and contains only non-null strings.

## 7. Complexity and How to Choose

Let `n` be the number of input elements and `u` be the number of distinct values/keys (`u ≤ n`).

| Approach | Preserves first-appearance order? | Expected time | Auxiliary space | Characteristics |
| --- | --- | --- | --- | --- |
| `LinkedHashSet` then convert to `ArrayList` | Yes | Average `O(n)` | `O(u)` | Concise, leaves input untouched, compares whole objects by default |
| `HashSet` + `ArrayList` during iteration | Yes | Average `O(n)` | `O(u)` | Flexible keys/conditions; first-occurrence rule is explicit |
| `stream().distinct().toList()` on an ordered stream | Yes | Typically near `O(n)` | Implementation-dependent and proportional to distinct elements | Expressive; `toList()` result is unmodifiable |
| Iterate and check `result.contains(value)` | Yes | Worst-case `O(n²)` | `O(u)` | Easy to write, unsuitable for large datasets |

Hash complexity estimates assume a well-distributed `hashCode()` and reasonable cost for computing hash/`equals()`; there is no guarantee that every input will achieve `O(n)` in every situation. Auxiliary memory does not count the input itself, and the resulting `List` may take an additional `O(u)` beyond the tracking structure.

One cannot assume that `LinkedHashSet` is always faster than Streams across all dataset sizes or environments; if performance is critical, benchmark with representative data. For everyday tasks, `LinkedHashSet` is the most direct choice; when deduplicating **by a business key**, use a loop with `seenKeys` and `result`.

## 8. Common Pitfalls

1. **Using `HashSet` as the output and assuming order is preserved.** The API makes no such guarantee, even if a few test inputs happen to look "right".
2. **Using `TreeSet` when first-appearance order is required.** Sorted order is not appearance order; moreover, a `Comparator` returning `0` for two objects causes them to be treated as duplicates.
3. **Failing to define what "duplicate" means.** Two records with the same `id` but different names are not duplicates under default `equals`; sometimes you need a key rather than the entire object.
4. **Dropping Stream ordering.** With `unordered()`, there is no guarantee that the first encountered element will be kept.
5. **Mutating the input unintentionally.** `removeIf` mutates the list in place; use it only when permitted and when the list supports removal.
6. **Attempting to mutate the list returned by `Stream.toList()`.** That list is unmodifiable; wrap or collect into a new `ArrayList` if further mutation is required.
7. **Forgetting to handle `null`.** `List.of` cannot contain `null`; normalization functions such as `value.toLowerCase(...)` cannot be called on `null` either.
8. **Relying on the order of an inherently unordered source.** If the input is a `HashSet`, you cannot claim the result preserves the "original order" in which data was previously inserted.
9. **Sharing `seen` state across multiple calls.** If not cleared properly, subsequent runs will drop valid elements; each deduplication call normally needs its own `seen` set.
10. **Concurrently adding to an unsynchronized `HashSet`/`ArrayList` from multiple threads.** These collections are not thread-safe. Concurrent processing requires dedicated synchronization and ordering design; do not split a loop across threads arbitrarily.

## 9. Self-Testing with Test Cases

A solid solution must pass a variety of inputs, not just a single example with a few strings:

| Input | Expected Output | Purpose |
| --- | --- | --- |
| `[]` | `[]` | Empty list |
| `[A]` | `[A]` | Single element |
| `[A, A, A]` | `[A]` | All elements identical |
| `[B, A, B, C, A]` | `[B, A, C]` | Does not reorder elements |
| `[null, A, null]` | `[null, A]` | Accepts one `null` when policy allows |
| `[Java, java, JAVA]` | `[Java, java, JAVA]` | Default string comparison is case-sensitive |
| `[Java, java, JAVA]` with lowercase key | `[Java]` | Deduplicates by key while preserving first spelling |

You can write a simple reusable method to test yourself:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.List;

public class UniqueInOrder {
    static <T> List<T> uniqueInOrder(Collection<? extends T> input) {
        return new ArrayList<>(new LinkedHashSet<>(input));
    }

    public static void main(String[] args) {
        System.out.println(uniqueInOrder(List.of("B", "A", "B", "C", "A")));
        System.out.println(uniqueInOrder(List.<String>of()));
    }
}
```

```bash
javac -encoding UTF-8 UniqueInOrder.java
java UniqueInOrder
```

```text
[B, A, C]
[]
```

`Collection` is suitable when the input is already a collection; the parameter `Collection<? extends T>` also accepts collections of subtypes of `T`. The resulting `ArrayList` is mutable. If the input argument is `null`, the `LinkedHashSet` constructor throws a `NullPointerException`; depending on your API contract, validate the input upfront and report a clear error message before calling it.

## 10. Extended Exercises and Conclusion

1. Given `List<Integer> [4, 2, 4, 1, 2, 5]`, produce `[4, 2, 1, 5]` using both `LinkedHashSet` and a loop with `seen`. Explain why sorting is not needed.
2. Given records `(id=1, name=An)`, `(id=2, name=Bình)`, `(id=1, name=An mới)`, deduplicate by `id` and explain clearly why the first `An` record is retained.
3. Given mixed-case text data, define a key-normalization function and demonstrate that the element added to the result is still the original form of the first occurrence.

**Core rule:** iterate through the data in the given order; the first time you see a value or key, keep it, and on subsequent occurrences, discard it. `LinkedHashSet` encapsulates this rule for default equality, whereas a tracking `Set` combined with a result `List` allows you to apply custom duplication rules while preserving first-appearance order.
