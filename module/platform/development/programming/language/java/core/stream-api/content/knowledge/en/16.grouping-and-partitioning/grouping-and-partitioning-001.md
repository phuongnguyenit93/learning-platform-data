# Grouping Data with `Collectors.groupingBy`

## 1. Objectives and Problem Statement

In the **Java Stream API** (`JAVA_STREAM_API`), a pipeline processes data declaratively: obtaining a source, performing lazy intermediate operations such as `filter` and `map`, and terminating with `collect` or `reduce`. When you want to organize multiple elements by a common attribute, **`Collectors.groupingBy`** is a core tool.

For example, given a list of orders, we need to know:

- Which orders are in each category?
- How many orders are in each category?
- What is the total revenue for each category?
- Within each category, how many orders are completed?
- What key order should the resulting `Map` have?

This lesson belongs to the **Grouping and Partitioning** chapter. After this lesson, you can use all three overloads of `groupingBy`, combine downstream collectors, handle empty data or invalid keys, and understand limitations regarding ordering, resources, performance, and parallel processing. This forms the foundation for advanced topics such as custom collectors and parallel grouping.

## 2. Core Mental Model: The Classifier Turns an Element into a Group Key

`groupingBy` accepts a **classifier function** (*classifier*), used to compute a **group key** from each element. Elements whose keys are considered equal are placed into the same group.

```text
                      classifier: get category
                       │
Order DH01 (Sách)    ──┼───────────────┐
Order DH02 (Đồ dùng) ──┼───────────┐   │
Order DH03 (Sách)    ──┼───────────│───┤
Order DH04 (Đồ dùng) ──┼───────────┤   │
Order DH05 (Điện tử) ──┼───────┐   │   │
Order DH06 (Sách)    ──┼───────│───│───┤
                       ▼       ▼   ▼   ▼
                   Map<String, List<DonHang>>
                   "Điện tử" → [DH05]
                   "Đồ dùng" → [DH02, DH04]
                   "Sách"    → [DH01, DH03, DH06]
```

General view:

```java
Map<K, List<T>> ketQua = stream.collect(
    Collectors.groupingBy(phanTu -> khoaNhom)
);
```

- `T`: source element type.
- `K`: key type returned by the classifier.
- `Map<K, List<T>>`: maps each key to the list of elements belonging to that key.

**Important:** `groupingBy` is a collector passed to the `collect` terminal operation. The actual grouping happens when `collect` consumes the stream; it does not produce a new source for further stream processing like `map` or `filter`.

## 3. Complete Java 8 Example: Grouping Orders by Category

Run the following program using Java 8 or later:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class NhomDonHang {
    static final class DonHang {
        private final String ma;
        private final String danhMuc;
        private final long gia;
        private final boolean hoanTat;

        DonHang(String ma, String danhMuc, long gia, boolean hoanTat) {
            this.ma = ma;
            this.danhMuc = danhMuc;
            this.gia = gia;
            this.hoanTat = hoanTat;
        }

        public String getMa() {
            return ma;
        }

        public String getDanhMuc() {
            return danhMuc;
        }

        public long getGia() {
            return gia;
        }

        public boolean isHoanTat() {
            return hoanTat;
        }

        @Override
        public String toString() {
            return ma;
        }
    }

    static List<DonHang> duLieu() {
        return Arrays.asList(
            new DonHang("DH01", "Sách", 120_000L, true),
            new DonHang("DH02", "Đồ dùng", 80_000L, false),
            new DonHang("DH03", "Sách", 180_000L, true),
            new DonHang("DH04", "Đồ dùng", 50_000L, true),
            new DonHang("DH05", "Điện tử", 900_000L, false),
            new DonHang("DH06", "Sách", 70_000L, false)
        );
    }

    public static void main(String[] args) {
        List<DonHang> donHang = duLieu();

        Map<String, List<DonHang>> theoDanhMuc = donHang.stream()
            .collect(Collectors.groupingBy(DonHang::getDanhMuc));

        System.out.println(theoDanhMuc.get("Sách"));
        System.out.println(theoDanhMuc.get("Đồ dùng"));
        System.out.println(theoDanhMuc.get("Điện tử"));
    }
}
```

Output:

```text
[DH01, DH03, DH06]
[DH02, DH04]
[DH05]
```

Here:

1. `donHang.stream()` creates a `Stream<DonHang>`.
2. `DonHang::getDanhMuc` is a classifier of type `Function<DonHang, String>`.
3. `groupingBy` creates a `Map<String, List<DonHang>>`.
4. Each category becomes a key of the `Map`.
5. Orders with the same category are accumulated into the list for that key.

The following examples assume **the `DonHang` class and `duLieu()` method above**, placed inside `main` or another method of the same `NhomDonHang` class:

```java
List<DonHang> donHang = duLieu();
```

The examples print values key by key explicitly so as not to depend on the key iteration order of the default `Map` type.

## 4. Three Important Overloads of `groupingBy`

There are three common ways to call it since Java 8. The signatures below omit details that do not affect readability:

```java
// 1. Choose classifier, keep all elements of each group.
groupingBy(Function<? super T, ? extends K> classifier)

// 2. Choose classifier and downstream collector for each group.
groupingBy(
    Function<? super T, ? extends K> classifier,
    Collector<? super T, A, D> downstream
)

// 3. Choose classifier, resulting Map type, and downstream collector.
groupingBy(
    Function<? super T, ? extends K> classifier,
    Supplier<M> mapFactory,
    Collector<? super T, A, D> downstream
)
```

Comparison:

| Overload | Typical return type | When to use |
| --- | --- | --- |
| `groupingBy(classifier)` | `Map<K, List<T>>` | When you want to keep the elements of each group. |
| `groupingBy(classifier, downstream)` | `Map<K, D>` | When you want to count, sum, extract names, gather statistics, or reduce each group. |
| `groupingBy(classifier, mapFactory, downstream)` | A specific `Map` type | When you need to control the map implementation, such as `LinkedHashMap` or `TreeMap`. |

In the two- and three-parameter overloads, the type `D` is the **result of the downstream collector**, not necessarily `List<T>`. Therefore, `groupingBy` is a grouping tool that can combine aggregations, not just an operation for splitting data into lists.

For the classifier-only overload, the result is equivalent in intent to using downstream `Collectors.toList()`. However, there are **no guarantees** on the specific `Map` type, mutability, thread-safety, or serializability of the resulting `Map` and `List`. Do not rely on the current implementation happening to return `HashMap` or `ArrayList`.

## 5. Counting Elements in Each Group with `counting()`

If you only want count statistics without storing all elements in lists:

```java
Map<String, Long> soDon = donHang.stream()
    .collect(Collectors.groupingBy(
        DonHang::getDanhMuc,
        Collectors.counting()
    ));

System.out.println(soDon.get("Sách"));    // 3
System.out.println(soDon.get("Đồ dùng")); // 2
System.out.println(soDon.get("Điện tử")); // 1
```

Reading the types:

```text
Stream<DonHang>
    └─ classifier: DonHang -> String
    └─ downstream: multiple DonHang -> Long
                     │
                     ▼
             Map<String, Long>
```

`Collectors.counting()` returns `Long`, so `Map<String, Long>` is the correct type. Writing `Map<String, Integer>` will cause a compilation error.

**Do not confuse** `donHang.stream().count()` with `groupingBy(..., counting())`:

- `count()` returns a single `long` for the **entire stream**.
- `groupingBy(..., counting())` returns a `Map` containing **the count for each key**.

If a filter is added, only elements that pass `filter` contribute to the groups:

```java
Map<String, Long> soDonHoanTat = donHang.stream()
    .filter(DonHang::isHoanTat)
    .collect(Collectors.groupingBy(
        DonHang::getDanhMuc,
        Collectors.counting()
    ));

System.out.println(soDonHoanTat.get("Sách"));    // 2
System.out.println(soDonHoanTat.get("Đồ dùng")); // 1
System.out.println(soDonHoanTat.get("Điện tử")); // null (no key present)
```

`get("Điện tử") == null` indicates **there is no corresponding group**, which is different from a group with a count of 0. If a report must also display categories with no completed orders, populate the keys from the business category list in a separate step.

## 6. Summing and Summarizing Statistics per Key

### 6.1. Total value per category

`Collectors.summingLong` takes a function that converts an element into a `long` value and computes the sum for each group:

```java
Map<String, Long> tongGiaTri = donHang.stream()
    .collect(Collectors.groupingBy(
        DonHang::getDanhMuc,
        Collectors.summingLong(DonHang::getGia)
    ));

System.out.println(tongGiaTri.get("Sách"));    // 370000
System.out.println(tongGiaTri.get("Đồ dùng")); // 130000
System.out.println(tongGiaTri.get("Điện tử")); // 900000
```

Values in the example use hypothetical units; in real monetary problems, choose an appropriate data type, rounding rules, and overflow bounds. `long` is wider than `int` but can still overflow when the sum exceeds `Long.MAX_VALUE`.

### 6.2. Average per category

`Collectors.averagingLong` returns `Double`, even when the input is `long`:

```java
Map<String, Double> giaTrungBinh = donHang.stream()
    .collect(Collectors.groupingBy(
        DonHang::getDanhMuc,
        Collectors.averagingLong(DonHang::getGia)
    ));

System.out.println(giaTrungBinh.get("Sách"));    // 123333.33333333333
System.out.println(giaTrungBinh.get("Đồ dùng")); // 65000.0
System.out.println(giaTrungBinh.get("Điện tử")); // 900000.0
```

`double` has floating-point precision error. If you need to calculate average monetary amounts according to business rounding rules, do not use the `Double` result as an exact monetary representation.

### 6.3. Multiple statistics with `summarizingLong`

`LongSummaryStatistics` provides count, sum, min, max, and average in a single result:

```java
import java.util.LongSummaryStatistics;

Map<String, LongSummaryStatistics> thongKe = donHang.stream()
    .collect(Collectors.groupingBy(
        DonHang::getDanhMuc,
        Collectors.summarizingLong(DonHang::getGia)
    ));

LongSummaryStatistics sach = thongKe.get("Sách");

System.out.println(sach.getCount());   // 3
System.out.println(sach.getSum());     // 370000
System.out.println(sach.getMin());     // 70000
System.out.println(sach.getMax());     // 180000
```

With `summingLong`, `averagingLong`, or `summarizingLong`, you do not need to create `List<DonHang>` instances just to compute metrics. This declarative approach is typically more memory-efficient when you do not need to retain all records.

## 7. Transforming Elements Inside Each Group with `mapping()`

When you only want to keep the **order code** instead of the entire object, use the `mapping` downstream collector:

```java
Map<String, List<String>> maTheoDanhMuc = donHang.stream()
    .collect(Collectors.groupingBy(
        DonHang::getDanhMuc,
        Collectors.mapping(
            DonHang::getMa,
            Collectors.toList()
        )
    ));

System.out.println(maTheoDanhMuc.get("Sách"));
// [DH01, DH03, DH06]
```

`Collectors.mapping(mapper, downstream)` transforms each element **after grouping** into a value suitable for the downstream collector. The resulting type changes as follows:

```text
Stream<DonHang>
  ├─ classifier: DanhMuc → String
  └─ mapping: DonHang → String (order code)
      └─ toList() → List<String>
             │
             ▼
     Map<String, List<String>>
```

You can replace `Collectors.toList()` with `Collectors.toSet()` if you only need unique codes:

```java
import java.util.Set;

Map<String, Set<String>> maDuyNhat = donHang.stream()
    .collect(Collectors.groupingBy(
        DonHang::getDanhMuc,
        Collectors.mapping(
            DonHang::getMa,
            Collectors.toSet()
        )
    ));
```

**Note:** `Collectors.toSet()` does not guarantee iteration order of the set. If you need to preserve the order of first appearance of codes within each group, explicitly choose `LinkedHashSet`:

```java
import java.util.LinkedHashSet;

Map<String, LinkedHashSet<String>> maCoThuTu = donHang.stream()
    .collect(Collectors.groupingBy(
        DonHang::getDanhMuc,
        Collectors.mapping(
            DonHang::getMa,
            Collectors.toCollection(LinkedHashSet::new)
        )
    ));

System.out.println(maCoThuTu.get("Sách"));
// [DH01, DH03, DH06]
```

On an ordered `List` source and a sequential pipeline, the order within each group's collection reflects the encounter order of elements belonging to that group.

## 8. Multi-Level Grouping

You can nest another `groupingBy` as a downstream collector for two-dimensional grouping. For example: **category → completion status → list of orders**.

```java
Map<String, Map<Boolean, List<DonHang>>> theoDanhMucVaTrangThai =
    donHang.stream().collect(
        Collectors.groupingBy(
            DonHang::getDanhMuc,
            Collectors.groupingBy(DonHang::isHoanTat)
        )
    );

System.out.println(
    theoDanhMucVaTrangThai.get("Sách").get(true)
); // [DH01, DH03]

System.out.println(
    theoDanhMucVaTrangThai.get("Sách").get(false)
); // [DH06]
```

The type has nested `Map` levels because each downstream collector also returns a map. You can replace the list at the inner level with a count:

```java
Map<String, Map<Boolean, Long>> demTheoDanhMucVaTrangThai =
    donHang.stream().collect(
        Collectors.groupingBy(
            DonHang::getDanhMuc,
            Collectors.groupingBy(
                DonHang::isHoanTat,
                Collectors.counting()
            )
        )
    );

System.out.println(
    demTheoDanhMucVaTrangThai.get("Sách").get(true)
); // 2
```

Not every group has both statuses. For example, the "Điện tử" category only has uncompleted orders, so the inner map may **lack the `true` key**:

```java
System.out.println(
    demTheoDanhMucVaTrangThai.get("Điện tử").get(true)
); // null
```

You need to distinguish between an **absent key** and a **statistic value of 0**, especially when interfacing with reports or JSON. If you want to guarantee both Boolean keys exist for each group that appears, use `partitioningBy` as the downstream collector:

```java
Map<String, Map<Boolean, Long>> demHaiTrangThai =
    donHang.stream().collect(
        Collectors.groupingBy(
            DonHang::getDanhMuc,
            Collectors.partitioningBy(
                DonHang::isHoanTat,
                Collectors.counting()
            )
        )
    );

System.out.println(
    demHaiTrangThai.get("Điện tử").get(true)
); // 0
```

Here, a category key is only created when there is an element belonging to that category, but inside the inner map of each existing category, `partitioningBy` provides both the `true` and `false` branches.

## 9. Choosing the `Map` Type with the Three-Parameter Overload

By default, `groupingBy(classifier)` **does not guarantee** the `Map` class or key iteration order. Therefore, you should not rely on the print order of:

```java
Map<String, List<DonHang>> ketQua = donHang.stream()
    .collect(Collectors.groupingBy(DonHang::getDanhMuc));

System.out.println(ketQua); // Key order is not guaranteed.
```

If you need to preserve the **first-appearance order of categories** from an ordered `List` source, use `LinkedHashMap` and a sequential stream:

```java
import java.util.LinkedHashMap;

LinkedHashMap<String, List<DonHang>> theoThuTuXuatHien =
    donHang.stream().collect(
        Collectors.groupingBy(
            DonHang::getDanhMuc,
            LinkedHashMap::new,
            Collectors.toList()
        )
    );

System.out.println(theoThuTuXuatHien.keySet());
// [Sách, Đồ dùng, Điện tử]
```

`LinkedHashMap` preserves key insertion order; in an ordered sequential pipeline, that is the order in which each category first appears.

If you need keys sorted in the **natural order** of `String`, use `TreeMap`:

```java
import java.util.TreeMap;

TreeMap<String, Long> theoKhoaSapXep =
    donHang.stream().collect(
        Collectors.groupingBy(
            DonHang::getDanhMuc,
            TreeMap::new,
            Collectors.counting()
        )
    );

System.out.println(theoKhoaSapXep.firstKey());
```

`TreeMap` defaults to `String`'s natural comparison in Unicode order; this does not mean sorting Vietnamese language text according to dictionary rules. When a locale-specific order is needed, provide an appropriate `Comparator` via the map factory.

**Remember:** the map type determines how **group keys** are traversed, while the downstream collector determines the data **inside each group**. For instance, `LinkedHashMap<String, Set<DonHang>>` has ordered keys, but a general `Set` still does not guarantee value order.

## 10. How Do `groupingBy` and `partitioningBy` Differ?

Both methods classify elements, but they serve different purposes.

| Feature | `groupingBy(classifier)` | `partitioningBy(predicate)` |
| --- | --- | --- |
| Keys | Arbitrary type `K` | Only two Boolean values: `true`/`false` |
| Input function | `Function<T, K>` | `Predicate<T>` |
| Possible number of groups | From 0 up to the number of distinct keys | Always has both Boolean keys in the returned map |
| Empty source | Empty map | Both branches exist with empty/corresponding downstream results |
| Typical use cases | Grouping by category, province, multi-level status | Splitting passed/failed, completed/incomplete |

Partition example:

```java
Map<Boolean, List<DonHang>> theoHoanTat = donHang.stream()
    .collect(Collectors.partitioningBy(DonHang::isHoanTat));

System.out.println(theoHoanTat.get(true));
// [DH01, DH03, DH04]

System.out.println(theoHoanTat.get(false));
// [DH02, DH05, DH06]
```

If you use `groupingBy(DonHang::isHoanTat)`, the result may look similar when data exists in both branches, but there is **no guarantee both keys will appear** if one branch has no elements.

Example on an empty source:

```java
import java.util.Collections;

List<DonHang> rong = Collections.emptyList();

Map<Boolean, List<DonHang>> chia = rong.stream()
    .collect(Collectors.partitioningBy(DonHang::isHoanTat));

Map<Boolean, List<DonHang>> nhom = rong.stream()
    .collect(Collectors.groupingBy(DonHang::isHoanTat));

System.out.println(chia.containsKey(true));  // true
System.out.println(chia.containsKey(false)); // true
System.out.println(nhom.isEmpty());          // true
```

## 11. Empty Data, Null Keys, and Data Quality

### 11.1. Empty source

On an empty stream, `groupingBy` does not create absent groups:

```java
Map<String, List<DonHang>> rong = java.util.stream.Stream
    .<DonHang>empty()
    .collect(Collectors.groupingBy(DonHang::getDanhMuc));

System.out.println(rong.isEmpty()); // true
```

Even when the downstream collector is `counting()` or `summingLong()`, it does not automatically produce 0 results for all possible categories. To build a report covering all categories, you need a canonical list of keys from the business domain and fill them in additionally.

### 11.2. Classifier returning `null`

You should not return `null` as a grouping key. Common JDK implementations of `Collectors.groupingBy` do not accept `null` classification keys and can throw `NullPointerException` during collection, even though some plain `Map` implementations allow `null` keys.

Suppose data may lack a category; a clear way to handle it is **key normalization**:

```java
Map<String, List<DonHang>> theoDanhMuc = donHang.stream()
    .collect(Collectors.groupingBy(d -> {
        String danhMuc = d.getDanhMuc();
        return danhMuc == null ? "Uncategorized" : danhMuc;
    }));
```

Or if business requirements call for dropping records missing a category, filter first:

```java
Map<String, List<DonHang>> hopLe = donHang.stream()
    .filter(d -> d.getDanhMuc() != null)
    .collect(Collectors.groupingBy(DonHang::getDanhMuc));
```

These two approaches have **different data semantics**: the first keeps uncategorized orders, while the second drops them. Choose according to requirements rather than silently losing data.

### 11.3. Custom objects as keys

A `Map` determines duplicate keys using `equals` and `hashCode` (except for maps using a comparator or special mechanism). If the classifier returns an object as a key, use stable identifying fields and implement `equals`/`hashCode` consistently.

Avoid mutating fields that participate in the hash code after the key has been placed in the map. Lookup and grouping behavior can break if a key can change its value while in use.

## 12. Laziness, Statefulness, and Performance

`groupingBy` operates inside `collect`: **it must consume the data to be grouped** in order to determine the groups and downstream results. Upstream `filter`/`map` operations remain lazy intermediate operations, running only when requested by the terminal `collect`.

If you want aggregate statistics, avoid storing all elements unnecessarily:

```java
// Keep all orders by category:
Map<String, List<DonHang>> dayDu = donHang.stream()
    .collect(Collectors.groupingBy(DonHang::getDanhMuc));

// Keep only the count by category:
Map<String, Long> soLuong = donHang.stream()
    .collect(Collectors.groupingBy(
        DonHang::getDanhMuc,
        Collectors.counting()
    ));
```

The first approach needs space to hold references to the orders inside the lists; the second mainly holds keys and counts. Both require space that grows with the number of distinct keys.

**Do not treat `collect(groupingBy(...))` as a way to process infinite data:** if the source can be infinite and is not bounded, the collection operation may never finish or may run out of memory.

Bounded example:

```java
import java.util.stream.IntStream;

Map<Integer, Long> theoSoDu = IntStream.iterate(1, n -> n + 1)
    .limit(100)
    .boxed()
    .collect(Collectors.groupingBy(
        n -> n % 3,
        Collectors.counting()
    ));

System.out.println(theoSoDu.get(0)); // 33
System.out.println(theoSoDu.get(1)); // 34
System.out.println(theoSoDu.get(2)); // 33
```

Note that the actual number of elements is counted **after** filters and limits. Placing `limit` before or after `filter` can change the data that gets grouped.

## 13. Grouping in Parallel Streams

`groupingBy` can be used on a `parallelStream()` according to contract:

```java
Map<String, Long> tongSongSong = donHang.parallelStream()
    .collect(Collectors.groupingBy(
        DonHang::getDanhMuc,
        Collectors.summingLong(DonHang::getGia)
    ));

System.out.println(tongSongSong.get("Sách")); // 370000
```

The collector may create multiple separate accumulation containers and then **merge the group maps**. Merging has overhead, especially when the number of groups is large. `groupingBy` is not a concurrent collector; to optimize certain parallel scenarios, Java provides `groupingByConcurrent`:

```java
import java.util.concurrent.ConcurrentMap;

ConcurrentMap<String, Long> tongConcurrent = donHang.parallelStream()
    .collect(Collectors.groupingByConcurrent(
        DonHang::getDanhMuc,
        Collectors.summingLong(DonHang::getGia)
    ));
```

**Distinguish what is guaranteed:**

- `groupingByConcurrent` produces a **concurrent** and **unordered** collector; do not rely on element order within each group.
- Regular `groupingBy` can preserve encounter order semantics of value groups on an ordered source with a suitable downstream collector, but **does not guarantee key iteration order** of the default map.
- Returning a `ConcurrentMap` does not mean every inner value object is a thread-safe collection for modifications after collection finishes.
- Performance depends on the number of groups, group distribution skew, the downstream collector, and the runtime environment. Do not assume `parallelStream()` or `groupingByConcurrent` is always faster.

Avoid updating a shared `HashMap` or `ArrayList` from `parallelStream().forEach(...)` to perform manual grouping; that causes race conditions and corrupted data. Using an appropriate collector ensures accumulation conforms to the Stream API's contract.

## 14. `groupingBy` vs. `toMap`

Both collectors produce a `Map` result, but they solve different problems:

| Need | Appropriate collector | Characteristics |
| --- | --- | --- |
| A key may have **multiple elements** | `groupingBy` | Groups elements with the same key; defaults to creating a list. |
| Each key needs exactly **one value**, input has no duplicate keys | `toMap(keyMapper, valueMapper)` | Duplicate keys typically cause `IllegalStateException` without a merge function. |
| Duplicate keys must be merged into a single value | `toMap(keyMapper, valueMapper, mergeFunction)` | Requires defining a value merge function. |
| Sum or count **by group** | `groupingBy(..., summingLong/counting)` | Clearly expresses group-level aggregation intent. |

For example, `toMap` without a merge function is unsuitable if multiple orders share the same category:

```java
// DO NOT RUN: multiple orders share a category, will throw
// IllegalStateException due to duplicate keys.
Map<String, DonHang> sai = donHang.stream()
    .collect(Collectors.toMap(
        DonHang::getDanhMuc,
        d -> d
    ));
```

If the requirement is "category → list of orders", `groupingBy` expresses it more directly and safely.

## 15. Common Errors and How to Handle Them

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `Map<String, Integer>` fails to compile with `counting()` | `counting()` returns `Long` | Use `Map<String, Long>`. |
| `get("Điện tử")` returns `null` after filtering | No group exists for that key | Check `containsKey` or use `getOrDefault`; add missing keys if required by the report. |
| Key order changes when printing the map | Default `groupingBy` does not guarantee map order | Use `LinkedHashMap`/`TreeMap` via the map factory. |
| `NullPointerException` when grouping | Classifier may return a `null` key | Normalize or filter out records missing keys before collecting. |
| Group count produces only a single total number | Calling `stream.count()` instead of downstream `counting` | Use `groupingBy(classifier, counting())`. |
| Group only has `true` and is missing `false` | `groupingBy` does not create absent keys automatically | If you want both branches, use `partitioningBy`. |
| `toSet` loses code order within a group | `Collectors.toSet()` does not guarantee order | Use `toCollection(LinkedHashSet::new)`. |
| Precision error in average currency amount | `averagingLong` returns `Double` | Design proper precision/business rounding policies. |
| Corrupted data with manual parallel grouping | Modifying a shared structure from multiple threads | Use a collector and avoid side effects in the classifier. |
| Out of memory when keeping all records | Default `groupingBy` stores a list per group | Use only statistical downstream collectors if records are not needed. |
| Unstable key semantics | Inconsistent `equals`/`hashCode` or mutable keys | Use immutable keys and define equality clearly. |

## 16. Practice Exercises

Reuse the set of six orders from Section 3.

### Exercise 1: Group and count

Write a `groupingBy` pipeline to create a `Map<String, Long>` counting the number of orders in each category. Predict the counts for "Sách", "Đồ dùng", and "Điện tử".

### Exercise 2: Total value per group

Create a `Map<String, Long>` containing the total `gia` by category, **without creating intermediate `List<DonHang>` objects**. Compare with the result in Section 6.

### Exercise 3: Extract only codes and preserve order

Create a `Map<String, List<String>>` where each category maps to a list of **order codes**, preserving encounter order from the source `List`. The "Sách" group must have `[DH01, DH03, DH06]`.

### Exercise 4: Nested grouping

Create a `Map<String, Map<Boolean, Long>>` containing order counts by category and completion status. When querying the "Điện tử" group and status `true`, why might you receive `null`? What should you change the downstream collector to if you want the value 0 instead?

### Exercise 5: Controlling key order and empty sources

Use `LinkedHashMap::new` to guarantee key order in a sequential pipeline from a `List`. When `Collections.<DonHang>emptyList()` is grouped, how many keys does it have? If the UI requires always displaying all three categories, what additional step is needed?

### Reference Solutions

**Exercise 1:**

```java
Map<String, Long> dem = donHang.stream()
    .collect(Collectors.groupingBy(
        DonHang::getDanhMuc,
        Collectors.counting()
    ));

// Sách = 3, Đồ dùng = 2, Điện tử = 1
```

**Exercise 2:**

```java
Map<String, Long> tong = donHang.stream()
    .collect(Collectors.groupingBy(
        DonHang::getDanhMuc,
        Collectors.summingLong(DonHang::getGia)
    ));

// Sách = 370000, Đồ dùng = 130000, Điện tử = 900000
```

**Exercise 3:**

```java
Map<String, List<String>> ma = donHang.stream()
    .collect(Collectors.groupingBy(
        DonHang::getDanhMuc,
        Collectors.mapping(
            DonHang::getMa,
            Collectors.toList()
        )
    ));

System.out.println(ma.get("Sách")); // [DH01, DH03, DH06]
```

**Exercise 4:**

```java
Map<String, Map<Boolean, Long>> thongKe =
    donHang.stream().collect(
        Collectors.groupingBy(
            DonHang::getDanhMuc,
            Collectors.groupingBy(
                DonHang::isHoanTat,
                Collectors.counting()
            )
        )
    );
```

The `true` key does not appear in the "Điện tử" group because there are no completed orders. To always have both Boolean branches, change the inner collector to `Collectors.partitioningBy(DonHang::isHoanTat, Collectors.counting())`.

**Exercise 5:**

```java
LinkedHashMap<String, List<DonHang>> nhom =
    donHang.stream().collect(
        Collectors.groupingBy(
            DonHang::getDanhMuc,
            LinkedHashMap::new,
            Collectors.toList()
        )
    );

System.out.println(nhom.keySet());
// [Sách, Đồ dùng, Điện tử]
```

An empty stream is collected by `groupingBy` into a map with no keys. If the UI needs all categories even when there are no orders, you must take the list of valid categories from the business domain and fill in empty or 0 results per contract, rather than expecting `groupingBy` to create groups automatically.

## 17. Key Takeaways

`Collectors.groupingBy` organizes Stream elements by the **key returned by the classifier**. The same classifier can produce different result types depending on the downstream collector:

```java
// Category -> list of orders
groupingBy(DonHang::getDanhMuc)

// Category -> order count
groupingBy(DonHang::getDanhMuc, counting())

// Category -> total value
groupingBy(DonHang::getDanhMuc, summingLong(DonHang::getGia))

// Category -> list of codes
groupingBy(DonHang::getDanhMuc, mapping(DonHang::getMa, toList()))

// Category -> status -> count
groupingBy(DonHang::getDanhMuc,
    groupingBy(DonHang::isHoanTat, counting()))
```

The shorthand expressions above assume `import static java.util.stream.Collectors.*;` and are placed as the collector in `stream.collect(...)`.

When applying this in practice, determine the **key type**, **per-group result type**, **ordering requirements**, **how absent groups are handled**, and **resource limits**. Use `mapFactory` when a specific `Map` type is needed; use `partitioningBy` when splitting into two Boolean branches; and use statistical downstream collectors when there is no need to retain all records. Those choices keep pipelines declarative, clear, and easy to scale to large or parallel data processing.
