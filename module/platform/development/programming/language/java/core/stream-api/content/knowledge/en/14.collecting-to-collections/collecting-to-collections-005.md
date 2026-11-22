# Preserving Encounter Order with `ArrayList` and `LinkedHashSet`

## 1. Lesson Objectives

In the **Java Stream API**, a declarative pipeline typically draws data from a source, performs lazy intermediate operations such as `filter` and `map`, and ends with `collect`. When collecting results into a collection, the collection type determines **whether duplicate values are kept**, **in what order elements are iterated**, and **whether elements can continue to be added or removed**.

This lesson belongs to the **Collecting into Collections** chapter of the **`JAVA_STREAM_API`** module, focusing on two practical cases:

- **`ArrayList`:** retains all elements, including duplicates, in the **encounter order** of an ordered stream.
- **`LinkedHashSet`:** retains only one element per equality group according to `equals`/`hashCode`, while preserving the **first-appearance order** of unique values.

After this lesson, you will be able to:

1. Distinguish the encounter order of a stream source from the iteration order of the resulting collection.
2. Use `Collectors.toCollection(ArrayList::new)` and `Collectors.toCollection(LinkedHashSet::new)` to explicitly choose the target collection type.
3. Predict the output of pipelines containing `filter`, `map`, `distinct`, and `sorted`.
4. Recognize ordering guarantees across ordered sources, unordered sources, and parallel pipelines.
5. Avoid confusion between `toList`, `toSet`, `toCollection`, and issues involving mutable objects.

These principles are also useful when moving on to grouping, custom collectors, Spliterators, and parallel processing performance.

## 2. What Is Encounter Order?

**Encounter order** is the order of elements defined by the stream source, if the source is ordered. For example, a `List` has an order based on element positions:

```java
import java.util.Arrays;
import java.util.List;

List<String> khoaHoc = Arrays.asList(
    "Java Core", "Go", "Java Stream", "Go", "Kotlin"
);
```

The stream created by `khoaHoc.stream()` has the encounter order:

```text
Java Core → Go → Java Stream → Go → Kotlin
```

Not every source has a guaranteed encounter order:

| Source | Guaranteed encounter order? | Notes |
| --- | --- | --- |
| `ArrayList.stream()` | Yes | Follows the order of elements in the list. |
| `LinkedList.stream()` | Yes | Follows list iteration order. |
| `Arrays.stream(array)` | Yes | Follows array index order. |
| `IntStream.range(0, 5)` | Yes | Follows ascending order from 0 to 4. |
| `LinkedHashSet.stream()` | Yes | Follows the set's insertion order. |
| `HashSet.stream()` | No | Iteration order is not guaranteed. |
| `HashMap.keySet().stream()` | No | Do not rely on the key order of a `HashMap`. |

**Important point:** a `HashSet` source may happen to print in the same order across several runs, but that does not establish an ordering guarantee. Collecting the result into a `LinkedHashSet` cannot invent an original order that the source never promised.

Intermediate operations can preserve, change, or drop the ordering constraint:

- `filter` preserves the relative order of remaining elements in an ordered stream.
- `map` transforms values while preserving output positional order for an ordered stream.
- `sorted` establishes a new sorted order.
- `unordered` allows the pipeline to **drop the encounter order constraint**.
- `distinct` on an ordered stream retains the first element of each equal value.

Therefore, to evaluate result ordering, ask: **does the source have an order, and what did the steps before `collect` do to that order?**

## 3. Explicit Collector: `toCollection`

Java 8 provides the method:

```java
static <T, C extends Collection<T>> Collector<T, ?, C>
    toCollection(Supplier<C> collectionFactory)
```

`Collectors.toCollection` accepts a **supplier** used to create the resulting collection. For the two types covered here:

```java
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.stream.Collectors;

// Collect into ArrayList:
.collect(Collectors.toCollection(ArrayList::new));

// Collect into LinkedHashSet:
.collect(Collectors.toCollection(LinkedHashSet::new));
```

The syntax `ArrayList::new` and `LinkedHashSet::new` is a **constructor reference**: the supplier creates a new collection when the collector needs to accumulate data. You can equivalently write lambdas `() -> new ArrayList<>()` or `() -> new LinkedHashSet<>()`.

`toCollection` lets you decide the **concrete collection type**. On an ordered stream, the collector receives elements in encounter order and accumulates them; `ArrayList` preserves that order when iterating, while `LinkedHashSet` preserves the insertion order of the first non-duplicate elements.

### Complete Example: Collecting Both a Full List and a Unique List

The following program runs on **Java 8 and above**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.stream.Collectors;

public class ThuThapTheoThuTu {
    public static void main(String[] args) {
        List<String> ten = Arrays.asList(
            "Java", "Go", "Java", "Kotlin", "Go", "Python"
        );

        ArrayList<String> tatCa = ten.stream()
            .collect(Collectors.toCollection(ArrayList::new));

        LinkedHashSet<String> duyNhat = ten.stream()
            .collect(Collectors.toCollection(LinkedHashSet::new));

        System.out.println(tatCa);
        System.out.println(duyNhat);
        System.out.println(tatCa.getClass().getSimpleName());
        System.out.println(duyNhat.getClass().getSimpleName());
    }
}
```

Output:

```text
[Java, Go, Java, Kotlin, Go, Python]
[Java, Go, Kotlin, Python]
ArrayList
LinkedHashSet
```

We create **two separate streams** with `ten.stream()` because a stream cannot be reused after running the `collect` terminal operation.

Comparison:

| Requirement | `ArrayList` | `LinkedHashSet` |
| --- | --- | --- |
| Keeps both occurrences of `"Java"` | Yes | No |
| Preserves appearance order from an ordered source | Yes | Yes, for unique values |
| Index-based access `get(0)` | Yes | No |
| Membership lookup via `contains` | Yes, linear scan | Usually more efficient via hash table |
| Allows adding/removing elements | Yes | Yes |
| Can contain `null` elements | Yes, can repeat | Yes, at most one `null` |

Do not choose `LinkedHashSet` solely to preserve order if business rules still require keeping all duplicate records. Those are two different requirements.

## 4. Using `ArrayList` When All Elements Must Be Kept

### 4.1. `filter` and `map` Do Not Automatically Deduplicate

`ArrayList` is especially useful when you need to keep records in chronological order, search result lists, or event histories where **two equal records still carry meaning**.

```java
List<String> suKien = Arrays.asList(
    "login", "error", "login", "logout", "login"
);

ArrayList<String> lichSu = suKien.stream()
    .filter(s -> !s.equals("error"))
    .map(String::toUpperCase)
    .collect(Collectors.toCollection(ArrayList::new));

System.out.println(lichSu);
// [LOGIN, LOGIN, LOGOUT, LOGIN]
```

In this example, all three `"login"` entries remain; `filter` only removes `"error"`. `map` transforms each value rather than removing duplicates.

### 4.2. Add `sorted` When a Specific Order Is Needed

`ArrayList` preserves the **input order entering the collection step**. If the pipeline has sorted elements, the list reflects the post-sort order:

```java
List<String> ten = Arrays.asList("Kotlin", "Java", "Go");

ArrayList<String> theoAlphabet = ten.stream()
    .sorted()
    .collect(Collectors.toCollection(ArrayList::new));

System.out.println(theoAlphabet); // [Go, Java, Kotlin]
```

Here `ArrayList` does not sort on its own; `sorted()` changes the encounter order prior to collection.

### 4.3. Why Not Always Use `Collectors.toList()`?

The following syntax also collects elements into a list:

```java
List<String> ketQua = ten.stream()
    .collect(Collectors.toList());
```

However, **`Collectors.toList()` does not guarantee the implementation class, mutability, thread-safety, or serializability** of the resulting list. On some JDKs it happens to be an `ArrayList`, but you should not treat that as an API contract.

If you **genuinely need an `ArrayList`**, write:

```java
ArrayList<String> ketQua = ten.stream()
    .collect(Collectors.toCollection(ArrayList::new));

ketQua.add("Python");
System.out.println(ketQua); // [Kotlin, Java, Go, Python]
```

Since **Java 16**, `stream.toList()` collects into an **unmodifiable** list while still preserving encounter order if the stream is ordered. If the requirement is a mutable list of a concrete type, `toCollection(ArrayList::new)` remains the explicit choice.

## 5. Using `LinkedHashSet` When Uniqueness and First Position Are Needed

`LinkedHashSet` combines two traits:

1. Contains no two elements considered equal under the `equals` and `hashCode` contract.
2. Iterates over elements in **insertion order**.

With an ordered stream, whichever unique value appears first is inserted first:

```java
List<String> ten = Arrays.asList(
    "Go", "Java", "Go", "Kotlin", "Java", "Python"
);

LinkedHashSet<String> ketQua = ten.stream()
    .collect(Collectors.toCollection(LinkedHashSet::new));

System.out.println(ketQua);
// [Go, Java, Kotlin, Python]
```

When `"Go"` or `"Java"` appears again, the duplicate insertion **does not change the position** of the previously inserted element.

### 5.1. Re-adding a Duplicate Does Not Move It to the End

```java
LinkedHashSet<String> set = new LinkedHashSet<>();
set.add("A");
set.add("B");
set.add("A");

System.out.println(set); // [A, B]
```

To move `"A"` to the end according to insertion rules, you must remove and then re-add it:

```java
set.remove("A");
set.add("A");
System.out.println(set); // [B, A]
```

Do not use remove/add operations when the goal is simply deduplication; if first-seen order matters, just collect directly.

### 5.2. How Does `LinkedHashSet` Differ from `HashSet`?

Both remove duplicate values, but `HashSet` does not guarantee iteration order:

```java
import java.util.HashSet;
import java.util.LinkedHashSet;

HashSet<String> khongCamKetThuTu = ten.stream()
    .collect(Collectors.toCollection(HashSet::new));

LinkedHashSet<String> giuThuTu = ten.stream()
    .collect(Collectors.toCollection(LinkedHashSet::new));
```

If the user needs a list of unique tags in **first-appearance order in the input data**, using `LinkedHashSet` expresses that requirement accurately. If order does not matter, `HashSet` can be an appropriate choice.

`LinkedHashSet` **does not sort alphabetically**. To produce alphabetical order, call `sorted()` before collecting or use a collection with sorting semantics such as `TreeSet` (which has different semantics from encounter order).

## 6. Duplication Rules: `equals` and `hashCode`

`LinkedHashSet` determines duplicates using `Set` semantics. For `String`, two strings that are equal under `equals` are considered duplicates, whereas `"Java"` and `"java"` are distinct:

```java
List<String> ten = Arrays.asList(
    "Java", "java", "JAVA", "Go"
);

LinkedHashSet<String> ketQua = ten.stream()
    .collect(Collectors.toCollection(LinkedHashSet::new));

System.out.println(ketQua);
// [Java, java, JAVA, Go]
```

If business logic requires case-insensitive comparison, normalize values **before collecting**:

```java
import java.util.Locale;

LinkedHashSet<String> chuanHoa = ten.stream()
    .map(s -> s.toLowerCase(Locale.ROOT))
    .collect(Collectors.toCollection(LinkedHashSet::new));

System.out.println(chuanHoa); // [java, go]
```

This operation transforms the data: all values are converted to lowercase. If you need to **preserve the original first-seen casing** while checking duplicates case-insensitively, design a separate comparison key, such as using a `LinkedHashMap` with normalized keys. `LinkedHashSet<String>` itself does not accept a custom `Comparator`.

### 6.1. Custom Objects Must Follow the Equality Contract

Two objects with the same business code may be considered a single element even if display attributes differ. Java 8 example:

```java
import java.util.Arrays;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Objects;
import java.util.stream.Collectors;

public class LoaiBanGhiTrung {
    static final class GiaoDich {
        final String ma;
        final String moTa;

        GiaoDich(String ma, String moTa) {
            this.ma = ma;
            this.moTa = moTa;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) return true;
            if (!(obj instanceof GiaoDich)) return false;
            GiaoDich other = (GiaoDich) obj;
            return Objects.equals(ma, other.ma);
        }

        @Override
        public int hashCode() {
            return Objects.hashCode(ma);
        }

        @Override
        public String toString() {
            return ma + ":" + moTa;
        }
    }

    public static void main(String[] args) {
        List<GiaoDich> nguon = Arrays.asList(
            new GiaoDich("A01", "Initial record"),
            new GiaoDich("B02", "Other record"),
            new GiaoDich("A01", "Updated record")
        );

        LinkedHashSet<GiaoDich> duyNhat = nguon.stream()
            .collect(Collectors.toCollection(LinkedHashSet::new));

        System.out.println(duyNhat);
        // [A01:Initial record, B02:Other record]
    }
}
```

Because both `equals` and `hashCode` are based on `ma`, the second `"A01"` record is treated as a duplicate. `LinkedHashSet` keeps the **first-encountered `"A01"` object** and does not update `moTa` to the newer value.

If `equals` and `hashCode` are not overridden on a regular class, two distinct object instances may fail to be recognized as duplicates even if they share the same business code.

**Note:** do not mutate properties participating in `hashCode`/`equals` while the object is inside a set. Doing so can cause `contains` or `remove` to return incorrect results. Keys used in a set should be stable or immutable.

## 7. How Are `distinct` and `LinkedHashSet` Similar and Different?

For an ordered stream, `distinct()` is a **stable** deduplicating intermediate operation: it retains the first occurrence of equal elements. Afterward, you still have a stream for further operations.

```java
List<String> ten = Arrays.asList(
    "Java", "Go", "Java", "Kotlin", "Go"
);

ArrayList<String> motLanMoiTen = ten.stream()
    .distinct()
    .collect(Collectors.toCollection(ArrayList::new));

LinkedHashSet<String> motLanMoiTenSet = ten.stream()
    .collect(Collectors.toCollection(LinkedHashSet::new));

System.out.println(motLanMoiTen);
// [Java, Go, Kotlin]

System.out.println(motLanMoiTenSet);
// [Java, Go, Kotlin]
```

The two results have the same sequence of values in this example, but **different data types**:

| Approach | Result | When appropriate |
| --- | --- | --- |
| `distinct().collect(toCollection(ArrayList::new))` | `ArrayList<T>` without duplicates as of collection time | Want a list and index-based processing afterward. |
| `collect(toCollection(LinkedHashSet::new))` | Unique `LinkedHashSet<T>`, in insertion order | Want to store results as a set while preserving first-appearance order. |
| `collect(Collectors.toSet())` | `Set<T>`, no ordering guarantee | Only need uniqueness, without needing order or a concrete set type. |

You do not have to write `distinct()` before `LinkedHashSet` just to deduplicate an extra time; that is usually redundant. However, when multiple intermediate operations follow the deduplication step, placing `distinct` at the right position can clarify the pipeline's intent.

### Step Ordering Can Change Results

```java
List<String> ten = Arrays.asList("Kotlin", "Java", "Kotlin", "Go");

LinkedHashSet<String> a = ten.stream()
    .distinct()
    .sorted()
    .collect(Collectors.toCollection(LinkedHashSet::new));

LinkedHashSet<String> b = ten.stream()
    .sorted()
    .distinct()
    .collect(Collectors.toCollection(LinkedHashSet::new));

System.out.println(a); // [Go, Java, Kotlin]
System.out.println(b); // [Go, Java, Kotlin]
```

With this data, both pipelines produce the same result. However, if values are transformed differently before deduplication (such as case normalization), or sorted by a key different from the equality criterion, the resulting order and retained object can differ. Thus, specify **whether deduplication should happen on original or transformed data**.

## 8. Pipelines with `filter`, `flatMap`, `sorted`, and `limit`

### 8.1. `filter` Preserves Relative Order of Remaining Elements

```java
List<String> ten = Arrays.asList(
    "Java", "Go", "JavaScript", "Kotlin", "Java"
);

ArrayList<String> batDauBangJava = ten.stream()
    .filter(s -> s.startsWith("Java"))
    .collect(Collectors.toCollection(ArrayList::new));

System.out.println(batDauBangJava);
// [Java, JavaScript, Java]
```

`filter` only keeps or discards elements; it does not actively sort. Because the source is ordered, the order of remaining values is preserved.

### 8.2. `flatMap` Concatenates Elements in Source Order

```java
List<List<String>> nhom = Arrays.asList(
    Arrays.asList("A", "B"),
    Arrays.asList("B", "C")
);

ArrayList<String> tatCa = nhom.stream()
    .flatMap(List::stream)
    .collect(Collectors.toCollection(ArrayList::new));

LinkedHashSet<String> duyNhat = nhom.stream()
    .flatMap(List::stream)
    .collect(Collectors.toCollection(LinkedHashSet::new));

System.out.println(tatCa);  // [A, B, B, C]
System.out.println(duyNhat); // [A, B, C]
```

With an ordered stream from two lists, `flatMap`'s output concatenates sub-streams in encounter order. `LinkedHashSet` still retains only the first occurrence of `"B"`.

### 8.3. Should `limit` Apply Before or After Deduplication?

```java
List<String> ten = Arrays.asList("A", "A", "B", "C", "D");

LinkedHashSet<String> a = ten.stream()
    .limit(3)
    .collect(Collectors.toCollection(LinkedHashSet::new));

LinkedHashSet<String> b = ten.stream()
    .distinct()
    .limit(3)
    .collect(Collectors.toCollection(LinkedHashSet::new));

System.out.println(a); // [A, B]
System.out.println(b); // [A, B, C]
```

In `a`, we look only at the first three source elements and then deduplicate; in `b`, we ask for the first three **unique values**. This is a semantic difference, so place `limit` in the right spot per business requirements.

## 9. Does Collecting on a Parallel Stream Preserve Order?

**Yes, if the source and pipeline have an encounter order and the collector is used according to its contract.** Both `Collectors.toCollection(ArrayList::new)` and `Collectors.toCollection(LinkedHashSet::new)` can be used on an ordered parallel stream without manually synchronizing a shared collection.

Java 8 example:

```java
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class ThuSongSong {
    public static void main(String[] args) {
        ArrayList<Integer> danhSach = IntStream.range(0, 10)
            .parallel()
            .boxed()
            .collect(Collectors.toCollection(ArrayList::new));

        LinkedHashSet<Integer> tapHop = IntStream.range(0, 10)
            .parallel()
            .boxed()
            .collect(Collectors.toCollection(LinkedHashSet::new));

        System.out.println(danhSach);
        // [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]

        System.out.println(tapHop);
        // [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
    }
}
```

`IntStream.range(0, 10)` has an encounter order. During parallel collection, the implementation may create local collections and merge them to yield a result honoring the promised order. **Element order in the resulting collection does not imply lambda execution order** across worker threads.

### 9.1. Why Not Use `parallelStream().forEach(result::add)`?

Wrong example:

```java
List<Integer> nguon = Arrays.asList(1, 2, 3, 4, 5);
ArrayList<Integer> ketQua = new ArrayList<>();

// UNSAFE: multiple threads may mutate ArrayList concurrently.
nguon.parallelStream().forEach(ketQua::add);
```

`ArrayList` is not safe for concurrent `add` calls, and `forEach` on a parallel stream **does not guarantee encounter order**. The result may have the wrong element count, scrambled order, or hard-to-reproduce errors.

Correct approach:

```java
ArrayList<Integer> ketQua = nguon.parallelStream()
    .collect(Collectors.toCollection(ArrayList::new));

System.out.println(ketQua); // [1, 2, 3, 4, 5]
```

`LinkedHashSet` is likewise unsafe for multiple threads concurrently adding elements manually. Using a collector instead of mutating a shared collection is the right choice.

### 9.2. `forEachOrdered` Preserves Order, but Has a Different Purpose from `collect`

`forEachOrdered` can execute an action in encounter order on an ordered stream, but if you simply want to **collect into a collection**, using `collect` directly is clearer and avoids managing external state. Do not use `forEachOrdered` as a default substitute for `Collectors.toCollection`.

### 9.3. `unordered()` and Unordered Sources

```java
List<String> ten = Arrays.asList("B", "A", "C", "A");

LinkedHashSet<String> ketQua = ten.parallelStream()
    .unordered()
    .collect(Collectors.toCollection(LinkedHashSet::new));
```

`unordered()` **does not necessarily reverse or scramble order**, but it allows the pipeline to operate without encounter-order constraints. Therefore, when the requirement calls for `"B, A, C"` order based on first appearance in the source, **do not drop the ordering constraint**. Printing `[B, A, C]` on one run does not mean it always will.

If the source is a `HashSet`, the order of elements arriving at the collector is already not guaranteed:

```java
import java.util.HashSet;

HashSet<String> khongCoThuTu = new HashSet<>(
    Arrays.asList("B", "A", "C")
);

LinkedHashSet<String> ghiLaiThuTuDuyet = khongCoThuTu.stream()
    .collect(Collectors.toCollection(LinkedHashSet::new));
```

`ghiLaiThuTuDuyet` records the **actual** encounter order provided by the source, but cannot guarantee that it will be `"B", "A", "C"`. If a meaningful order is needed, construct or sort the source as required.

## 10. Mutability, Resources, and Performance

Both `ArrayList` and `LinkedHashSet` created by `toCollection` are **modifiable collections**:

```java
ArrayList<String> ds = ten.stream()
    .collect(Collectors.toCollection(ArrayList::new));

ds.add("Rust");

LinkedHashSet<String> tap = ten.stream()
    .collect(Collectors.toCollection(LinkedHashSet::new));

tap.add("Rust");
```

However, mutability does not mean thread-safety when multiple threads modify them concurrently. Do not use them as concurrent data structures without an appropriate synchronization design.

Regarding resources:

- `ArrayList` stores **every element**, so memory grows with the number of collected elements.
- `LinkedHashSet` stores each unique value only once, but requires hashing and linking structures to maintain insertion order; per-element memory overhead can exceed a list's.
- `ArrayList.contains` has linear time complexity in the number of elements; `LinkedHashSet.contains` typically has near-constant expected time with a good hash function.
- `collect` must accumulate results in memory. If a source may be infinite and has no limit, collecting everything into either collection may never finish or may run out of memory.
- `parallelStream` is not automatically faster: maintaining order and merging local results adds overhead.

**There is no rule that "`LinkedHashSet` is always faster than `ArrayList`" or vice versa.** Choose by data semantics first, then measure performance if datasets are large.

### 10.1. Infinite Sources and Collection Limits

```java
ArrayList<Integer> muoiSo = java.util.stream.Stream
    .iterate(1, n -> n + 1)
    .limit(10)
    .collect(Collectors.toCollection(ArrayList::new));

System.out.println(muoiSo);
// [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
```

`limit(10)` caps the number of elements collected; `toCollection` itself creates no stopping condition for an infinite source.

If you want both deduplication and **n distinct values**, place `distinct()` before `limit(n)`; however, ensure the source actually produces at least n distinct values, otherwise the pipeline can still wait forever.

## 11. Choosing the Right Collection in Applications

| Need | Recommended syntax | Reason |
| --- | --- | --- |
| Full list in encounter order, supports add/remove, needs `ArrayList` | `collect(toCollection(ArrayList::new))` | Keeps duplicates and guarantees concrete type. |
| Unique elements in first-appearance order | `collect(toCollection(LinkedHashSet::new))` | Unique, preserves insertion order. |
| Just a `List`, independent of implementation class | `collect(Collectors.toList())` | Simple intent, though mutability is not guaranteed. |
| Unmodifiable list on Java 16+ | `stream.toList()` | Returns an unmodifiable list, preserves encounter order if present. |
| Just a `Set`, order does not matter | `collect(Collectors.toSet())` | Promises neither order nor concrete set type. |
| Unique data but further processed as a list | `distinct().collect(toCollection(ArrayList::new))` | Deduplicates in pipeline, result is a list. |
| Unique elements in **sorted** order | `sorted().collect(toCollection(LinkedHashSet::new))` | Encounter order after `sorted` is the sorted order. |

In the table, `toCollection` refers to `Collectors.toCollection`. If only an immutable result is needed, pick the API appropriate for your Java version; do not assume `Collectors.toList()` or `Collectors.toSet()` always returns an unmodifiable collection.

## 12. Common Mistakes

| Symptom | Cause | How to handle |
| --- | --- | --- |
| `Collectors.toSet()` gives a different order than expected | No ordering guarantee | Use `toCollection(LinkedHashSet::new)`. |
| `ArrayList` still has many duplicate elements | Lists allow duplicates | Use `LinkedHashSet` or `distinct()` per business logic. |
| `LinkedHashSet` keeps only one object for a code | Two objects were treated as equal | Check `equals`/`hashCode` and choose the right identity criteria. |
| `LinkedHashSet` is not sorted alphabetically | It preserves insertion order, does not sort | Use `sorted` before collecting if needed. |
| `HashSet` source causes unstable result order | Source has no guaranteed encounter order | Use an ordered source or `sorted`. |
| `unordered()` loses order-preservation requirement | Pipeline dropped the ordering constraint | Do not use `unordered` when encounter order matters. |
| `parallelStream().forEach(list::add)` gives wrong results | Concurrent mutation on `ArrayList` and no order guarantee | Use `collect(toCollection(ArrayList::new))`. |
| Assuming `Collectors.toList()` is always `ArrayList` | Implementation class is not promised | Explicitly request `toCollection(ArrayList::new)`. |
| Calling `add` on `Stream.toList()` result fails | Java 16+ result is unmodifiable | Use `toCollection(ArrayList::new)` if add/remove is needed. |
| Object in set cannot be found after changing code | Property involved in `hashCode` changed | Use stable keys or immutable objects. |
| `limit(3)` before deduplication leaves only two elements | Limits to three inputs, not three unique values | Use `distinct().limit(3)` if three distinct values are needed. |
| Collecting infinite source causes overload | No stopping condition | Limit before `collect`. |

## 13. Practice Exercises

### Exercise 1 — Keep All or Deduplicate?

Given:

```java
List<String> ma = Arrays.asList(
    "A01", "B02", "A01", "C03", "B02"
);
```

Create an `ArrayList<String>` preserving all codes, and a `LinkedHashSet<String>` containing each code once in first-appearance order. Predict both results.

### Exercise 2 — Normalize Before Deduplicating

Given:

```java
List<String> ngonNgu = Arrays.asList(
    " Java ", "java", "Go", " GO ", "Kotlin"
);
```

Write a pipeline to trim extra whitespace, convert to lowercase using `Locale.ROOT`, and collect into a `LinkedHashSet<String>`. Which values are in the result and in what order?

### Exercise 3 — Limit Before or After Deduplication?

Given:

```java
List<Integer> so = Arrays.asList(1, 1, 2, 3, 4);
```

Find the results of:

```java
LinkedHashSet<Integer> x = so.stream()
    .limit(3)
    .collect(Collectors.toCollection(LinkedHashSet::new));

ArrayList<Integer> y = so.stream()
    .distinct()
    .limit(3)
    .collect(Collectors.toCollection(ArrayList::new));
```

### Exercise 4 — Parallel and Ordering

A list `["A", "B", "A", "C"]` must be collected into a set in first-appearance order. Choose between `Collectors.toSet()` and `Collectors.toCollection(LinkedHashSet::new)`. If `stream()` is switched to `parallelStream()` on the ordered list source, does the chosen approach still guarantee the result order?

### Exercise 5 — Choosing How to Keep the First Object

A list of records shares the code `"X01"` with two different descriptions; the **first-appearing record** must be kept. What should you watch out for regarding `equals`, `hashCode`, and mutating the code after putting it into `LinkedHashSet`?

### Reference Answers

**Exercise 1:**

```java
ArrayList<String> tatCa = ma.stream()
    .collect(Collectors.toCollection(ArrayList::new));

LinkedHashSet<String> duyNhat = ma.stream()
    .collect(Collectors.toCollection(LinkedHashSet::new));

System.out.println(tatCa);   // [A01, B02, A01, C03, B02]
System.out.println(duyNhat); // [A01, B02, C03]
```

**Exercise 2:**

```java
LinkedHashSet<String> chuanHoa = ngonNgu.stream()
    .map(String::trim)
    .map(s -> s.toLowerCase(java.util.Locale.ROOT))
    .collect(Collectors.toCollection(LinkedHashSet::new));

System.out.println(chuanHoa); // [java, go, kotlin]
```

The string `" Java "` comes first, creating the `"java"` key first; subsequent repeats are discarded.

**Exercise 3:** `x = [1, 2]` because the first three elements are `1, 1, 2`. `y = [1, 2, 3]` because `distinct` removes duplicates before `limit(3)` counts three unique values.

**Exercise 4:** Use `Collectors.toCollection(LinkedHashSet::new)` to guarantee the set type and insertion order following encounter order. With an ordered stream from a `List`, this contract-compliant collection still preserves result order during parallel execution. Do not manually insert into a shared `LinkedHashSet` via `parallelStream().forEach`.

**Exercise 5:** Define equality based on the code and implement `equals`/`hashCode` consistently. `LinkedHashSet` keeps the first-encountered object without merging descriptions. The code used for hashing must remain stable for as long as the object stays in the set.

## 14. Key Takeaways

```java
// Keep all elements, including duplicates, in encounter order:
ArrayList<T> list = stream
    .collect(Collectors.toCollection(ArrayList::new));

// Keep unique elements, in first-appearance order:
LinkedHashSet<T> set = stream
    .collect(Collectors.toCollection(LinkedHashSet::new));
```

These two lines are **generic illustration templates**: in an actual program, replace `T` and `stream` with concrete types and variables.

For the result to actually have the desired order, the source or pipeline must have a meaningful **encounter order**. `ArrayList` retains duplicates while `LinkedHashSet` deduplicates based on `equals`/`hashCode` and remembers insertion order; both are modifiable collections but should not be used as shared mutation targets across multiple threads. For parallel pipelines, use contract-compliant collectors to gather results and be mindful of the cost of maintaining order.

Understanding these differences clearly helps you pick the right result structure and avoid data-loss or out-of-order bugs when combining `filter`, `map`, `collect`, and advanced Stream API pipelines.
