# Preserving Group Order and Element Order Within Each Group

## 1. Two Kinds of Ordering to Control

When processing data with the **Java Stream API** (`JAVA_STREAM_API`), a pipeline can take a `List` source, filter and transform with `filter` / `map`, and terminate with `collect(Collectors.groupingBy(...))`. The result is a `Map` containing multiple groups. However, the question "**does the result preserve order?**" actually splits into **two separate questions**:

1. **Order of groups (`Map` key order):** when iterating `map.keySet()` or `map.entrySet()`, which group appears first?
2. **Order of elements within each group:** for a specific key, are the records inside the `List` / `Set` iterated in the source's encounter order?

These two ordering levels are controlled by **two independent choices**:

- `mapFactory` determines the `Map` implementation and how **group keys** are iterated.
- `downstream collector` determines the collection type and how **elements within each group** are iterated.

If business requirements specify "groups appear in first-encounter order, and each group preserves original order sequence", we typically choose:

```java
Collectors.groupingBy(
    DonHang::getDanhMuc,
    LinkedHashMap::new,
    Collectors.toCollection(ArrayList::new)
)
```

This lesson belongs to the **Grouping and Partitioning** chapter. After this lesson, you will be able to:

- Distinguish *encounter order*, `LinkedHashMap` insertion order, and `ArrayList` / `LinkedHashSet` element order.
- Use the three-parameter overload of `Collectors.groupingBy` to control both ordering levels.
- Sort keys or elements within each group without inadvertently altering the other ordering level.
- Predict what happens with unordered sources, `unordered()`, or `parallelStream()`.
- Write independent tests for key order, element order, and deduplication rules.

## 2. Encounter Order: The Stream's Encounter Order

**Encounter order** is the element visitation order guaranteed by a stream source and intermediate operations, if any. For example:

```java
List<String> ma = Arrays.asList(
    "DH01", "DH02", "DH03", "DH04"
);

ma.stream(); // Encounter order: DH01, DH02, DH03, DH04
```

Some sources guarantee encounter order while others do not:

| Source | Encounter order guaranteed? | Notes |
| --- | --- | --- |
| `ArrayList.stream()` | Yes | Follows index order. |
| `LinkedHashSet.stream()` | Yes | Follows element insertion order. |
| `Arrays.stream(array)` | Yes | Follows array index order. |
| `IntStream.range(0, 10)` | Yes | Follows ascending numeric order. |
| `HashSet.stream()` | No | `HashSet` iteration order is not part of its contract. |
| `HashMap.entrySet().stream()` | No | `HashMap` traversal order must not be treated as fixed. |

Certain intermediate operations can also affect order:

- `filter` preserves the relative order of remaining elements on an ordered stream.
- `map` transforms values while preserving the corresponding ordering relationship on an ordered stream.
- `sorted` establishes a new sort order.
- `distinct` on an ordered stream retains the first occurrence among equal elements.
- `unordered()` drops the encounter-order constraint; it does not mean "reverse" or "guaranteed shuffle".

`collect` is a terminal operation: preceding `filter`, `map`, and `sorted` steps may be lazy, but grouping and building the resulting collections happen when `collect` consumes the stream.

## 3. Complete Program: Preserving Both Group Order and Element Order

Use the following orders as a running example throughout the lesson (Java 8+):

| Input order | Order ID | Category | Customer | Amount |
| ---: | --- | --- | --- | ---: |
| 1 | DH01 | Sách | KH-A | 120.000 |
| 2 | DH02 | Điện tử | KH-B | 900.000 |
| 3 | DH03 | Sách | KH-C | 150.000 |
| 4 | DH04 | Đồ dùng | KH-A | 80.000 |
| 5 | DH05 | Điện tử | KH-B | 700.000 |
| 6 | DH06 | Sách | KH-A | 120.000 |

Self-contained Java code:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class NhomDonHangCoThuTu {
    static final class DonHang {
        private final String ma;
        private final String danhMuc;
        private final String khachHang;
        private final long soTien;

        DonHang(String ma, String danhMuc, String khachHang, long soTien) {
            this.ma = ma;
            this.danhMuc = danhMuc;
            this.khachHang = khachHang;
            this.soTien = soTien;
        }

        String getMa() {
            return ma;
        }

        String getDanhMuc() {
            return danhMuc;
        }

        String getKhachHang() {
            return khachHang;
        }

        long getSoTien() {
            return soTien;
        }

        @Override
        public String toString() {
            return ma;
        }
    }

    static List<DonHang> duLieu() {
        return Arrays.asList(
            new DonHang("DH01", "Sách", "KH-A", 120_000L),
            new DonHang("DH02", "Điện tử", "KH-B", 900_000L),
            new DonHang("DH03", "Sách", "KH-C", 150_000L),
            new DonHang("DH04", "Đồ dùng", "KH-A", 80_000L),
            new DonHang("DH05", "Điện tử", "KH-B", 700_000L),
            new DonHang("DH06", "Sách", "KH-A", 120_000L)
        );
    }

    public static void main(String[] args) {
        List<DonHang> donHang = duLieu();

        LinkedHashMap<String, ArrayList<DonHang>> nhom = donHang.stream()
            .collect(Collectors.groupingBy(
                DonHang::getDanhMuc,
                LinkedHashMap::new,
                Collectors.toCollection(ArrayList::new)
            ));

        System.out.println(new ArrayList<>(nhom.keySet()));
        System.out.println(nhom.get("Sách"));
        System.out.println(nhom.get("Điện tử"));
        System.out.println(nhom.get("Đồ dùng"));
    }
}
```

Output:

```text
[Sách, Điện tử, Đồ dùng]
[DH01, DH03, DH06]
[DH02, DH05]
[DH04]
```

**Why does it produce this result?**

1. The `donHang` source is a `List`, which has a deterministic encounter order.
2. Category "Sách" appears first, "Điện tử" appears second, and "Đồ dùng" appears fourth; `LinkedHashMap` preserves key insertion order by first appearance.
3. `Collectors.toCollection(ArrayList::new)` collects each category's orders into an `ArrayList`.
4. The "Sách" orders arrive in encounter order `DH01 → DH03 → DH06`; whenever the classifier yields the same key, the record is added to the corresponding group.
5. No `sorted`, `unordered`, or external side effect alters this order.

The short examples that follow assume you placed them in `main` of the class above, where this variable exists:

```java
List<DonHang> donHang = duLieu();
```

The code snippets use `Collectors` and the classes imported in the program above; if using a snippet standalone in another class, add the corresponding imports.

## 4. Three-Parameter Overload and Two Control Levels

Simplified signature of the overload to use:

```java
<T, K, D, A, M extends Map<K, D>> Collector<T, ?, M> groupingBy(
    Function<? super T, ? extends K> classifier,
    Supplier<M> mapFactory,
    Collector<? super T, A, D> downstream
);
```

Meaning of each position:

| Component | Role | Example |
| --- | --- | --- |
| `classifier` | Computes the group key from each element | `DonHang::getDanhMuc` |
| `mapFactory` | Creates the map type holding the groups | `LinkedHashMap::new`, `TreeMap::new` |
| `downstream` | Accumulates elements sharing the same key | `toList()`, `toCollection(ArrayList::new)`, `counting()` |
| Return value | A map whose per-group values are built by downstream | `LinkedHashMap<String, ArrayList<DonHang>>` |

Writing only:

```java
Map<String, List<DonHang>> nhom = donHang.stream()
    .collect(Collectors.groupingBy(DonHang::getDanhMuc));
```

carries **no guarantee on the map type or key iteration order**. Even if the current JDK happens to use `HashMap`, that is not a contract you should rely on.

Likewise, `Collectors.toList()` does not guarantee a concrete list type, mutability, thread-safety, or serializability. When you only need a `List` that preserves encounter order, `toList()` is enough; when you genuinely need a mutable `ArrayList`, use `toCollection(ArrayList::new)`.

### Pattern for choosing both ordering levels

```java
// Key order follows first-encounter order.
// Each group is an ArrayList in encounter order.
LinkedHashMap<String, ArrayList<DonHang>> nhom = donHang.stream()
    .collect(Collectors.groupingBy(
        DonHang::getDanhMuc,
        LinkedHashMap::new,
        Collectors.toCollection(ArrayList::new)
    ));
```

This pattern fits reports that must display categories in the order they appear in the source data while preserving record order inside each category.

## 5. Only Need Element Order Within Groups: `toList()`

When the UI only looks up each group by key and **does not care about key order**, you do not have to choose `LinkedHashMap`.

```java
Map<String, List<DonHang>> nhom = donHang.stream()
    .collect(Collectors.groupingBy(
        DonHang::getDanhMuc,
        Collectors.toList()
    ));

System.out.println(nhom.get("Sách")); // [DH01, DH03, DH06]
```

On an ordered stream from a `List`, `Collectors.toList()` collects elements within each group in encounter order; however, when printing the whole `nhom` map, do not assume the key order is `[Sách, Điện tử, Đồ dùng]`.

If an explicitly mutable list result is needed:

```java
Map<String, ArrayList<DonHang>> nhom = donHang.stream()
    .collect(Collectors.groupingBy(
        DonHang::getDanhMuc,
        Collectors.toCollection(ArrayList::new)
    ));
```

This changes **each group's collection type**, without adding any guarantee on the map's key iteration order.

**Conversely:** choosing `LinkedHashMap::new` with a `Collectors.toSet()` downstream only fixes key order; it **does not guarantee element order inside the set**.

## 6. Preserving Encounter Order While Deduplicating with `LinkedHashSet`

Some requirements do not want all elements: "Which **unique customers** belong to each category, in first-appearance order?" Here the downstream should use `LinkedHashSet`.

```java
import java.util.LinkedHashSet;

LinkedHashMap<String, LinkedHashSet<String>> khachTheoDanhMuc =
    donHang.stream()
        .collect(Collectors.groupingBy(
            DonHang::getDanhMuc,
            LinkedHashMap::new,
            Collectors.mapping(
                DonHang::getKhachHang,
                Collectors.toCollection(LinkedHashSet::new)
            )
        ));

System.out.println(new ArrayList<>(khachTheoDanhMuc.keySet()));
// [Sách, Điện tử, Đồ dùng]

System.out.println(khachTheoDanhMuc.get("Sách"));
// [KH-A, KH-C]

System.out.println(khachTheoDanhMuc.get("Điện tử"));
// [KH-B]
```

Meaning:

- `LinkedHashMap` preserves the **first-appearance order of categories**.
- `mapping(DonHang::getKhachHang, ...)` extracts only the customer ID from each order.
- `LinkedHashSet` keeps **unique customer IDs** in first-insertion order within the group.
- In the "Sách" group, `KH-A` first appears in `DH01`, `KH-C` in `DH03`, and the duplicate `KH-A` in `DH06` is skipped.

Differences between lists and sets:

| Downstream | Keeps duplicate elements? | Element iteration order |
| --- | --- | --- |
| `toList()` | Yes | Encounter order on an ordered stream |
| `toCollection(ArrayList::new)` | Yes | Encounter order on an ordered stream |
| `toSet()` | No | Not guaranteed |
| `toCollection(LinkedHashSet::new)` | No | Insertion order of unique values |
| `toCollection(TreeSet::new)` | No | Sorted order of `TreeSet`, not encounter order |

`LinkedHashSet` identifies duplicate elements using `equals`/`hashCode`. If the customer identifier is a custom object, implement both methods consistently and avoid mutating the key after adding it to the set.

## 7. Sorting Groups by Key with `TreeMap`

`LinkedHashMap` stores **first-seen** order, not alphabetical order. When you want keys ordered by a comparison rule, use a sorted map.

```java
import java.util.TreeMap;

TreeMap<String, List<DonHang>> nhomTheoKhoa = donHang.stream()
    .collect(Collectors.groupingBy(
        DonHang::getDanhMuc,
        TreeMap::new,
        Collectors.toList()
    ));

System.out.println(nhomTheoKhoa.keySet());
```

A `TreeMap` with its no-argument constructor uses the natural order of `String`, meaning Java string comparison by character code units; **it is not Vietnamese dictionary sorting**. If you need language-specific or business ordering, supply an appropriate comparator.

### Example of business-defined key ordering

Suppose the UI wants to display "Điện tử", "Sách", and then "Đồ dùng", regardless of encounter order:

```java
import java.util.Comparator;
import java.util.HashMap;
import java.util.TreeMap;

Map<String, Integer> thuTu = new HashMap<>();
thuTu.put("Điện tử", 0);
thuTu.put("Sách", 1);
thuTu.put("Đồ dùng", 2);

Comparator<String> thuTuNghiepVu =
    Comparator.comparingInt(thuTu::get);

TreeMap<String, List<DonHang>> nhom = donHang.stream()
    .collect(Collectors.groupingBy(
        DonHang::getDanhMuc,
        () -> new TreeMap<>(thuTuNghiepVu),
        Collectors.toList()
    ));

System.out.println(new ArrayList<>(nhom.keySet()));
// [Điện tử, Sách, Đồ dùng]
```

This example assumes **every key exists in `thuTu` and ranks are unique**. In real data, `TreeMap` uses the comparator to determine key equivalence: if two distinct keys return `0` when compared, they can be treated as the same key. Therefore, the comparator must be consistent with group equality, and you need a fallback for unknown keys or uncategorized entries.

Another approach is to group first, and then order the groups for display according to the canonical business category list. That solution is often easier to maintain when display rules change.

## 8. Sorting Elements Inside Each Group Without Changing Group Order

A common mistake is sorting **the entire stream before grouping** when you actually only want to sort elements **inside each group**. Pre-sorting can alter the first-appearance order of the group keys themselves.

### 8.1. Sorting before `groupingBy`: changes both levels

```java
import java.util.Comparator;

LinkedHashMap<String, List<DonHang>> theoGiaTri = donHang.stream()
    .sorted(Comparator.comparingLong(DonHang::getSoTien))
    .collect(Collectors.groupingBy(
        DonHang::getDanhMuc,
        LinkedHashMap::new,
        Collectors.toList()
    ));

System.out.println(new ArrayList<>(theoGiaTri.keySet()));
// [Đồ dùng, Sách, Điện tử]

System.out.println(theoGiaTri.get("Sách"));
// [DH01, DH06, DH03]

System.out.println(theoGiaTri.get("Điện tử"));
// [DH05, DH02]
```

Reason:

1. `DH04` has amount 80.000 so it appears first after `sorted`; the "Đồ dùng" key is inserted first.
2. `DH01` and `DH06` both have amount 120.000; on an ordered source, `sorted` is stable, preserving the relative order of elements that compare equal.
3. Next comes the "Điện tử" group at 700.000 and 900.000.

**Conclusion:** `sorted` before `groupingBy` changes the encounter order that the map uses to decide key insertion positions.

### 8.2. Sorting only each group's list after grouping

If you want to **keep the original group order** `[Sách, Điện tử, Đồ dùng]`, while sorting each group by ascending price, use downstream `collectingAndThen`:

```java
import java.util.Comparator;

LinkedHashMap<String, ArrayList<DonHang>> nhom = donHang.stream()
    .collect(Collectors.groupingBy(
        DonHang::getDanhMuc,
        LinkedHashMap::new,
        Collectors.collectingAndThen(
            Collectors.toCollection(ArrayList::new),
            list -> {
                list.sort(Comparator.comparingLong(DonHang::getSoTien));
                return list;
            }
        )
    ));

System.out.println(new ArrayList<>(nhom.keySet()));
// [Sách, Điện tử, Đồ dùng]

System.out.println(nhom.get("Sách"));
// [DH01, DH06, DH03]

System.out.println(nhom.get("Điện tử"));
// [DH05, DH02]
```

Here, the inner collector gathers elements into each `ArrayList`, and the finisher function sorts **each list**. Because the original stream is not sorted, `LinkedHashMap` key insertion order still follows the original encounter order.

We use `toCollection(ArrayList::new)` instead of assuming the list from `Collectors.toList()` is always mutable; the `toList()` API does not guarantee mutability.

**When multiple elements compare equal under the comparator:** `List.sort` is a stable sort, yet to keep result order independent of ties between distinct records, add a tie-breaker criterion:

```java
Comparator<DonHang> theoGiaRoiMa =
    Comparator.comparingLong(DonHang::getSoTien)
        .thenComparing(DonHang::getMa);
```

Using a multi-criteria comparator also makes results easier to test when data comes from multiple sources.

## 9. Unordered Sources: A Collector Cannot Fabricate Non-Existent History

`LinkedHashMap` only preserves **the order in which keys are inserted into the map**. It cannot deduce an original order when the source has no encounter order.

Example with a `HashSet` source:

```java
import java.util.HashSet;

HashSet<String> danhMuc = new HashSet<>(
    Arrays.asList("Sách", "Điện tử", "Đồ dùng")
);

LinkedHashMap<String, List<String>> nhom = danhMuc.stream()
    .collect(Collectors.groupingBy(
        s -> s.substring(0, 1),
        LinkedHashMap::new,
        Collectors.toList()
    ));
```

The element order supplied by `HashSet.stream()` is not guaranteed, so you must not infer a meaningful key order solely from `LinkedHashMap`.

If deterministic results are required, **establish order before grouping**:

```java
LinkedHashMap<String, List<String>> nhom = danhMuc.stream()
    .sorted()
    .collect(Collectors.groupingBy(
        s -> s.substring(0, 1),
        LinkedHashMap::new,
        Collectors.toList()
    ));
```

`sorted` establishes encounter order by `String` natural ordering. If a specific business order is desired, pass an appropriate comparator instead of relying on the collection's default iteration order.

### `unordered()` removes ordering guarantees

```java
LinkedHashMap<String, List<DonHang>> nhom = donHang.stream()
    .unordered()
    .collect(Collectors.groupingBy(
        DonHang::getDanhMuc,
        LinkedHashMap::new,
        Collectors.toList()
    ));
```

`unordered()` drops the requirement to preserve encounter order. The output may **happen to look like the original order in one run**, but that is not a contract your application may depend on. If first-appearance order matters, do not call `unordered()`.

## 10. Parallel Streams: Result Order Differs from Execution Order

An ordered stream retains its encounter order even in parallel mode. Standard `groupingBy` is a **non-concurrent** collector that supports parallel aggregation using thread-local accumulators and combining results. Thus, with an ordered source and an order-preserving downstream, you can still obtain results in encounter order.

```java
LinkedHashMap<String, ArrayList<DonHang>> nhom = donHang.parallelStream()
    .collect(Collectors.groupingBy(
        DonHang::getDanhMuc,
        LinkedHashMap::new,
        Collectors.toCollection(ArrayList::new)
    ));

System.out.println(new ArrayList<>(nhom.keySet()));
// [Sách, Điện tử, Đồ dùng]

System.out.println(nhom.get("Sách"));
// [DH01, DH03, DH06]
```

However, there are **three distinct orders** to keep apart:

1. **Encounter order:** defined by the ordered source and pipeline.
2. **Execution order:** the order in which threads invoke `classifier`, `map`, or intermediate steps; **not guaranteed** in a parallel stream.
3. **Result iteration order:** determined by the ordered stream, collector, map type, and downstream collection.

Do not inspect logs from `peek` or `map` to infer encounter order, as callbacks may run on different threads or in unintuitive sequences. If key insertion order per business workflow is a strict requirement, a sequential pipeline is usually easier to reason about and control.

### 10.1. Why not insert into a shared map using `forEach`?

Anti-pattern example:

```java
import java.util.HashMap;

Map<String, List<DonHang>> nhom = new HashMap<>();

// WRONG: mutating a shared HashMap and ArrayList from multiple threads.
// Do not use this pattern in applications.
donHang.parallelStream().forEach(d ->
    nhom.computeIfAbsent(
        d.getDanhMuc(),
        k -> new ArrayList<>()
    ).add(d)
);
```

`HashMap`, `ArrayList`, and `LinkedHashMap` are not safe for concurrent modification. The snippet above can lose records, corrupt groups, scramble order, or throw runtime errors. Use `collect(groupingBy(...))` so the Stream API manages accumulation containers.

Even if you synchronize the map manually, `parallelStream().forEach(...)` still **does not guarantee encounter order** for updates. Synchronization prevents data races, not out-of-order updates.

### 10.2. `groupingByConcurrent` is not for ordering requirements

`Collectors.groupingByConcurrent` creates a **concurrent** and **unordered** collector, useful for certain parallel aggregations yet **not preserving element order within each group**.

```java
import java.util.concurrent.ConcurrentMap;

ConcurrentMap<String, List<DonHang>> nhomConcurrent =
    donHang.parallelStream()
        .collect(Collectors.groupingByConcurrent(
            DonHang::getDanhMuc
        ));
```

Lists inside each group may not follow `DH01 → DH03 → DH06`. The resulting `ConcurrentMap` also does not provide `LinkedHashMap`-style key insertion order.

Do not confuse **safe concurrent accumulation by the collector** with **inner value lists being thread-safe for later mutation**. If you need both parallel processing and deterministic result ordering, prefer an ordered-semantics collector or sort explicitly after collection, and benchmark on real data.

## 11. Using `groupingBy` with `mapping`, `filtering`, and Other Downstreams

### 11.1. Mapping values before collecting each group

From `List<DonHang>`, extract order codes while preserving both group order and element order:

```java
LinkedHashMap<String, List<String>> maTheoDanhMuc =
    donHang.stream().collect(
        Collectors.groupingBy(
            DonHang::getDanhMuc,
            LinkedHashMap::new,
            Collectors.mapping(
                DonHang::getMa,
                Collectors.toList()
            )
        )
    );

System.out.println(maTheoDanhMuc.get("Sách"));
// [DH01, DH03, DH06]
```

`mapping` changes the **values collected into each group** without changing group keys. If you need unique codes in first-appearance order, replace `toList()` with `toCollection(LinkedHashSet::new)`.

### 11.2. Filtering before or inside each group?

When `filter` is placed **before** `groupingBy`, a group with no remaining elements can **disappear**:

```java
LinkedHashMap<String, List<DonHang>> trenMotTram =
    donHang.stream()
        .filter(d -> d.getSoTien() >= 100_000L)
        .collect(Collectors.groupingBy(
            DonHang::getDanhMuc,
            LinkedHashMap::new,
            Collectors.toList()
        ));

System.out.println(new ArrayList<>(trenMotTram.keySet()));
// [Sách, Điện tử] — Đồ dùng has no matching records.
```

Since **Java 9**, `Collectors.filtering` lets you filter **inside each group**. Groups can still appear with an empty downstream result when elements were classified into the group but failed the filter predicate:

```java
LinkedHashMap<String, List<DonHang>> trenMotTram =
    donHang.stream().collect(
        Collectors.groupingBy(
            DonHang::getDanhMuc,
            LinkedHashMap::new,
            Collectors.filtering(
                d -> d.getSoTien() >= 100_000L,
                Collectors.toList()
            )
        )
    );

System.out.println(new ArrayList<>(trenMotTram.keySet()));
// [Sách, Điện tử, Đồ dùng]

System.out.println(trenMotTram.get("Đồ dùng"));
// []
```

This difference directly affects **key order**: with upstream `filter`, the "Đồ dùng" group vanishes; with downstream `filtering`, it keeps its position in the `LinkedHashMap`. On Java 8, if you need to retain all observed groups while filtering elements inside each group, use a custom downstream collector or a post-grouping step; Java 9's `Collectors.filtering` is unavailable.

### 11.3. Counting elements per group

If you only need counts, there is no "element order within a group" because the group value is not a collection:

```java
LinkedHashMap<String, Long> demTheoDanhMuc =
    donHang.stream().collect(
        Collectors.groupingBy(
            DonHang::getDanhMuc,
            LinkedHashMap::new,
            Collectors.counting()
        )
    );

System.out.println(new ArrayList<>(demTheoDanhMuc.keySet()));
// [Sách, Điện tử, Đồ dùng]
System.out.println(demTheoDanhMuc.get("Sách")); // 3
```

Here only the `LinkedHashMap` key-ordering layer applies; `counting` returns `Long` for each group.

## 12. Empty Sources, Absent Keys, and `null` Keys

`groupingBy` creates groups only for keys that actually appear in the pipeline.

```java
import java.util.Collections;

List<DonHang> rong = Collections.emptyList();

LinkedHashMap<String, List<DonHang>> nhomRong =
    rong.stream().collect(
        Collectors.groupingBy(
            DonHang::getDanhMuc,
            LinkedHashMap::new,
            Collectors.toList()
        )
    );

System.out.println(nhomRong.isEmpty()); // true
```

There are no keys to sort or iterate. If the UI must show all categories even when there are no orders, take the **canonical list of keys from the business domain** and populate empty groups per display rules instead of expecting `groupingBy` to create keys automatically.

`groupingBy` also rejects `null` classification values in standard JDK implementations. If a `DonHang` is missing a category, handle it explicitly:

```java
LinkedHashMap<String, List<DonHang>> nhom = donHang.stream()
    .collect(Collectors.groupingBy(
        d -> d.getDanhMuc() == null
            ? "Uncategorized"
            : d.getDanhMuc(),
        LinkedHashMap::new,
        Collectors.toList()
    ));
```

This rule keeps uncategorized records in a dedicated group. If you choose `filter` to drop records missing a category, remember that both **the order of remaining keys** and the record count can change.

## 13. Testing Order: Verify Both Levels Separately

A test that only checks map size or element counts is **insufficient** to assert correct ordering. Check both the **key list** and **each group's code list**.

Java 8 test example, placed in `main` of `NhomDonHangCoThuTu`:

```java
LinkedHashMap<String, ArrayList<DonHang>> nhom = donHang.stream()
    .collect(Collectors.groupingBy(
        DonHang::getDanhMuc,
        LinkedHashMap::new,
        Collectors.toCollection(ArrayList::new)
    ));

List<String> khoaMongDoi = Arrays.asList(
    "Sách", "Điện tử", "Đồ dùng"
);

List<String> maSachMongDoi = Arrays.asList(
    "DH01", "DH03", "DH06"
);

List<String> khoaThucTe = new ArrayList<>(nhom.keySet());

List<String> maSachThucTe = nhom.get("Sách").stream()
    .map(DonHang::getMa)
    .collect(Collectors.toList());

if (!khoaMongDoi.equals(khoaThucTe)) {
    throw new AssertionError(
        "Wrong group order: " + khoaThucTe
    );
}

if (!maSachMongDoi.equals(maSachThucTe)) {
    throw new AssertionError(
        "Wrong Sách order list: " + maSachThucTe
    );
}

System.out.println("PASS: both ordering levels");
```

**Why not compare the entire `Map` with `equals`?** `Map.equals` checks key–value pairs, **not key iteration order**. Two maps with identical data in different key orders still compare equal. Similarly, `Set.equals` does not verify insertion order of a `LinkedHashSet`.

To test the order of a `LinkedHashSet`, convert it to an `ArrayList` and compare against the expected list:

```java
LinkedHashSet<String> set = new LinkedHashSet<>(
    Arrays.asList("A", "B", "A", "C")
);

boolean dungThuTu = new ArrayList<>(set)
    .equals(Arrays.asList("A", "B", "C"));

System.out.println(dungThuTu); // true
```

For larger test suites, also cover single-element groups, non-contiguous repeating keys, duplicate records, empty sources, and comparator tie-breaker ordering.

## 14. Performance, Memory, and Resources

Preserving encounter order is not always free:

- `LinkedHashMap` requires extra linked structures to preserve key insertion order compared to a map optimized solely for lookup.
- `ArrayList` stores every element of each group; if you only need counts or sums, using downstream `counting()` or `summingLong()` avoids storing large lists.
- `LinkedHashSet` deduplicates and tracks insertion order, adding hashing and link overhead; do not use it if business logic needs all records including duplicates.
- `sorted` generally must observe all input elements of the sorting step, which can cost time and memory. Sorting each group after collecting sometimes avoids sorting the entire stream, though actual efficiency depends on the data.
- `parallelStream()` incurs splitting, coordination, and local-map merging costs. `groupingByConcurrent` can reduce certain costs when appropriate, at the expense of ordering constraints.
- `collect` on a potentially infinite, unbounded source risks never finishing or exhausting resources; bound the data from the source before collecting.

If a report only needs `Map<DanhMuc, Long>` counts, do not collect `Map<DanhMuc, List<DonHang>>` and call `size()` on each group just to count. If key order is a display requirement, enforce it at the presentation step or via an appropriate `mapFactory`.

There is no rule that parallel streams are always faster than sequential streams. With modest sources and strict ordering requirements, a sequential pipeline is often simpler, easier to test, and more predictable.

## 15. Common Mistakes

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `groupingBy(classifier)` prints groups in an unexpected order | Default Map does not guarantee key order | Use `groupingBy(classifier, LinkedHashMap::new, downstream)`. |
| Used `LinkedHashMap`, yet elements inside groups are still unordered | Downstream is `toSet()` or source has no encounter order | Choose `toList()` / `toCollection(ArrayList::new)` and an ordered source. |
| Using `LinkedHashSet` drops duplicate orders | Set keeps only unique elements | Switch to `ArrayList` if all records must be kept. |
| Chose `TreeMap` expecting first-appearance order | `TreeMap` sorts keys, not insertion order | Use `LinkedHashMap` for first-seen order. |
| `sorted` before `groupingBy` changes category order | Sorting the whole source changes which key is seen first | Sort only each group's list if original key order must remain. |
| `Collectors.toList()` returns a list without the concrete type desired | API does not guarantee `ArrayList` | Use `toCollection(ArrayList::new)`. |
| `parallelStream().forEach(map::put)` corrupts data | Mutating a shared map from multiple threads; `forEach` has no order guarantee | Use a contract-compliant collector. |
| `groupingByConcurrent` alters group element order | Concurrent/unordered collector | Use regular `groupingBy` or sort explicitly after collecting. |
| `HashSet.stream()` gives unexpected group order | Source has no guaranteed order | Use an ordered source or `sorted` with an appropriate comparator. |
| `Map.equals` test passes yet UI shows wrong order | `Map.equals` ignores iteration order | Compare `new ArrayList<>(map.keySet())`. |
| `LinkedHashSet.equals` test passes despite wrong order | `Set.equals` checks membership, not order | Compare order via `new ArrayList<>(set)`. |
| Group with `null` key fails | Classifier returns `null` | Normalize or filter records missing keys. |
| Group missing after `filter` | Group had no matching elements so it was not created | Populate empty groups if required by business rules. |
| Collecting an infinite source causes out-of-memory | No bound before the collector | Limit or paginate the source; avoid collecting all elements. |

## 16. Practice Exercises

Reuse the six orders from Section 3.

### Exercise 1: Preserving two-level order

Write a pipeline returning `LinkedHashMap<String, ArrayList<DonHang>>`. Determine the key order and the order of order IDs in the "Sách" group.

### Exercise 2: Deduplicating customers while keeping first appearance

Create `LinkedHashMap<String, LinkedHashSet<String>>` containing customer IDs by category. Which customers should be in the "Sách" group, and in what order? Why does `KH-A` not appear twice?

### Exercise 3: Sorting by price without changing group order

Keep the key order `[Sách, Điện tử, Đồ dùng]`. Within each group, sort orders by ascending `soTien`. Should you put `sorted(comparingLong(DonHang::getSoTien))` before `groupingBy`? Write the proper implementation using `collectingAndThen` or a post-grouping step.

### Exercise 4: Unordered source

If you replace the `List` source with a `HashSet`, is `LinkedHashMap::new` enough to guarantee the business-desired appearance order? Propose a way to establish deterministic order based on each order's `ma`.

### Exercise 5: Spotting a bug in testing

A program produces two `LinkedHashMap` instances with identical key–value pairs, but their key orders are `[Sách, Điện tử]` and `[Điện tử, Sách]`. What does `map1.equals(map2)` return? How must you test to detect the wrong order?

### Reference Solutions

**Exercise 1:**

```java
LinkedHashMap<String, ArrayList<DonHang>> nhom =
    donHang.stream().collect(
        Collectors.groupingBy(
            DonHang::getDanhMuc,
            LinkedHashMap::new,
            Collectors.toCollection(ArrayList::new)
        )
    );

// Keys: [Sách, Điện tử, Đồ dùng]
// Sách group: [DH01, DH03, DH06]
```

**Exercise 2:**

```java
LinkedHashMap<String, LinkedHashSet<String>> nhom =
    donHang.stream().collect(
        Collectors.groupingBy(
            DonHang::getDanhMuc,
            LinkedHashMap::new,
            Collectors.mapping(
                DonHang::getKhachHang,
                Collectors.toCollection(LinkedHashSet::new)
            )
        )
    );

System.out.println(nhom.get("Sách")); // [KH-A, KH-C]
```

`LinkedHashSet` eliminates the second occurrence of `KH-A` in the "Sách" group under `String` equality.

**Exercise 3:** You should not sort the entire source when first-appearance key order must be preserved. Collect groups into `LinkedHashMap` and sort each `ArrayList` individually:

```java
LinkedHashMap<String, ArrayList<DonHang>> nhom =
    donHang.stream().collect(
        Collectors.groupingBy(
            DonHang::getDanhMuc,
            LinkedHashMap::new,
            Collectors.collectingAndThen(
                Collectors.toCollection(ArrayList::new),
                list -> {
                    list.sort(Comparator.comparingLong(DonHang::getSoTien));
                    return list;
                }
            )
        )
    );

// Keys remain [Sách, Điện tử, Đồ dùng]
// Sách group becomes [DH01, DH06, DH03]
```

**Exercise 4:** No. A `HashSet` source does not guarantee encounter order. You can write:

```java
LinkedHashMap<String, List<DonHang>> nhom =
    hashSetDonHang.stream()
        .sorted(Comparator.comparing(DonHang::getMa))
        .collect(Collectors.groupingBy(
            DonHang::getDanhMuc,
            LinkedHashMap::new,
            Collectors.toList()
        ));
```

This assumes `ma` is unique or the comparator includes a tie-breaker when codes match. In an application, `hashSetDonHang` must be a properly declared `Set<DonHang>` source.

**Exercise 5:** `Map.equals` returns `true` when two maps have the same key–value mappings, even if insertion orders differ. To verify order:

```java
boolean dungThuTu =
    new ArrayList<>(map1.keySet())
        .equals(Arrays.asList("Sách", "Điện tử"));
```

Similarly, to check order inside a `LinkedHashSet`, convert the set to a list before comparing.

## 17. Summary

To preserve the right order in `groupingBy` results, decide **both levels independently**:

```java
// 1. Groups in encounter order; keeps all elements in encounter order:
stream.collect(Collectors.groupingBy(
    classifier,
    LinkedHashMap::new,
    Collectors.toCollection(ArrayList::new)
));

// 2. Groups in encounter order; keeps unique elements in first-appearance order:
stream.collect(Collectors.groupingBy(
    classifier,
    LinkedHashMap::new,
    Collectors.toCollection(LinkedHashSet::new)
));
```

The snippets above assume appropriate stream source, classifier, and imports.

Key points to remember:

- **Group order:** `LinkedHashMap` preserves key insertion order; `TreeMap` sorts keys; `groupingBy`'s default map makes no key-order guarantee.
- **Element order within groups:** `toList` / `ArrayList` preserves encounter order of an ordered source; `LinkedHashSet` preserves first-appearance order of unique values; `toSet` makes no order guarantee.
- **Source order:** if the source is unordered or the pipeline calls `unordered()`, do not expect the collector to restore an order that does not exist.
- **Sorting:** sorting the whole stream can alter group order; sorting each list after grouping changes only element order within groups.
- **Parallelism:** distinguish callback execution order from result iteration order. `groupingByConcurrent` is an unordered collector and is unsuitable when element order inside groups is required.
- **Testing:** verify `keySet()` and lists in order, not just `Map.equals` or `Set.equals`.

Once you understand these two ordering levels, you can build `filter`, `map`, `collect`, and complex grouping pipelines with consistent, testable results aligned with business requirements.
