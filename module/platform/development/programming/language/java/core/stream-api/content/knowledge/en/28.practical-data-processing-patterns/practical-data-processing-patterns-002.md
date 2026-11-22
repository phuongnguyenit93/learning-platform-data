# Indexing and Detecting Duplicate Records by Business Key

## 1. Problem: From a List of Records to a Reliable Lookup Index

In the **Practical Data Processing Patterns** chapter of **JAVA_STREAM_API**, `filter`, `map`, `collect`, and `reduce` pipelines are not used only for transforming lists. An application often receives many records from APIs, files, or partner systems and needs to quickly answer:

- Are there records sharing the same **business key**?
- For each key, should we select **a representative record**, merge values, or **reject the whole group**?
- Can we build a `Map<Key, Record>` for direct lookup instead of scanning a `List` repeatedly?
- Does key normalization cause two originally distinct records to be treated as duplicates?
- How do we report duplicate records to inspect source data instead of silently overwriting?

For example, a system receives inventory records:

~~~text
Source:
[tenant=T1, sku=" book ", version=1, quantity=10]
[tenant=T1, sku="BOOK",   version=2, quantity=8]
[tenant=T1, sku="PEN",    version=1, quantity=5]
[tenant=T2, sku="BOOK",   version=1, quantity=100]

Business rules:
- SKU is case-insensitive and ignores leading/trailing whitespace.
- An SKU is unique only within a single tenant.
- Records with the same normalized tenant + SKU share the same key.
- Higher version means newer; quantity is a snapshot, NOT an amount to sum.

Normalized keys:
(T1, BOOK) -> 2 records -> check duplicates -> pick version 2
(T1, PEN)  -> 1 record  -> valid
(T2, BOOK) -> 1 record  -> independent of (T1, BOOK)
~~~

A result typically consists of **two separate artifacts**:

1. **Final index** `Map<BusinessKey, Record>` for fast lookup by key.
2. **Data-quality report** containing duplicate keys and their associated records.

If you only build the Map and discard duplicate information, you can lose the trail of a serious business error.

This lesson uses **Java 17+** with `record`, `Stream.toList()`, and `Collectors`. The goal is to design a workflow with an explicit contract while recognizing limits around `null`, ordering, mutable data, and parallel processing. This is a data-processing pattern in the Stream API module, not a replacement for uniqueness constraints in a database.

## 2. A Business Key Is Not Necessarily a Record ID

A **technical key** is typically system-generated, such as a row ID, UUID, or import sequence number. A **business key** is the set of attributes identifying an entity according to domain rules.

| Context | Technical Key | Possible Business Key |
| --- | --- | --- |
| Product per customer | `rowId` | `(tenantId, normalizedSku)` |
| Order from partner | `internalId` | `(partnerId, externalOrderId)` |
| Bank transaction | `databaseId` | Transaction code / contract idempotency identifier |
| Course enrollment | `enrollmentId` | `(studentId, courseId, term)` |
| Daily report | `rowId` | `(accountId, date, metricType)` |

Do not pick a field that merely "looks unique" without business confirmation. For instance, the same SKU may be valid across **two different tenants**; using SKU alone as the key creates **false duplicates** and drops data.

### Key Duplication Does Not Mean Two Records Are Identical

Two rows may be:

- **Exact duplicates:** same key, same version, same values across all fields.
- **Same key, different versions:** need to keep the newest record or retain history.
- **Same key and conflicting:** same version but differing values; may need to raise an error.
- **Not duplicates once scoped properly:** same SKU but different tenants are two separate entities.

Therefore, duplicate-key detection is **not equivalent** to `stream.distinct()` across the whole record: `distinct()` checks element `equals`, whereas a business key may consist only of certain fields after normalization.

## 3. Define Normalized Keys Using Immutable Records

We model imported data as `StockRow` and the business key as `BusinessKey`. A record gives us `equals` and `hashCode` based on key components, which is required for use as a `HashMap` key.

~~~java
import java.util.Locale;
import java.util.Objects;

public class StockDomain {
    record StockRow(
        String rowId,
        String tenantId,
        String sku,
        long version,
        int quantity
    ) {}

    record BusinessKey(String tenantId, String sku) {}

    static String canonicalize(String text) {
        Objects.requireNonNull(text, "business key component");
        String result = text.strip().toUpperCase(Locale.ROOT);
        if (result.isEmpty()) {
            throw new IllegalArgumentException(
                "Key component must not be empty"
            );
        }
        return result;
    }

    static BusinessKey businessKey(StockRow row) {
        Objects.requireNonNull(row, "row");
        return new BusinessKey(
            canonicalize(row.tenantId()),
            canonicalize(row.sku())
        );
    }
}
~~~

By the **example convention**, keys are case-insensitive and ignore leading/trailing whitespace. Given the data below:

~~~java
StockDomain.StockRow a = new StockDomain.StockRow(
    "row-1", " T1 ", "book", 1, 10
);

StockDomain.StockRow b = new StockDomain.StockRow(
    "row-2", "t1", " BOOK ", 2, 8
);

System.out.println(
    StockDomain.businessKey(a).equals(StockDomain.businessKey(b))
); // true
~~~

`record BusinessKey` is a **value object**: two keys with the same normalized components are equal. Avoid creating keys by concatenating strings without a separator like `tenant + sku`, because `("AB","C")` and `("A","BC")` both produce `"ABC"`.

### Normalization Must Follow the Business Contract

Calling `toUpperCase(Locale.ROOT)` here is an **assumed SKU rule**, not a safe normalization for every ID type. For example:

- Email addresses have provider-dependent case sensitivity and alias rules; do not arbitrarily strip dots or plus-addressed suffixes.
- Some partner codes are case-sensitive; uppercasing every character can create false collisions.
- Unicode can have multiple representations or visually similar characters; Unicode normalization, diacritics, and whitespace rules must be specified explicitly if needed.
- SKUs with leading zeros (such as `"0012"`) must not be coerced to number `12` if the two codes are distinct.
- For string identifiers, do not arbitrarily strip hyphens or internal whitespace unless the contract explicitly permits it.

**Design rule:** Normalize before constructing the key and use the **exact same normalization function** both when building the index and when querying it.

## 4. Approach 1 — Indexing with toMap When Keys Must Be Unique

If the input contract guarantees no duplicate keys, `Collectors.toMap(keyMapper, valueMapper)` is a concise way to build an index:

~~~java
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

public class UniqueIndex {
    record Product(String sku, String name) {}

    public static void main(String[] args) {
        List<Product> products = List.of(
            new Product("BOOK", "Book"),
            new Product("PEN", "Pen"),
            new Product("PAD", "Notebook")
        );

        Map<String, Product> bySku = products.stream()
            .collect(Collectors.toMap(
                Product::sku,
                Function.identity()
            ));

        System.out.println(bySku.get("PEN").name()); // Pen
        System.out.println(bySku.size()); // 3
    }
}
~~~

`Function.identity()` keeps the element itself as the **Map value**. The key mapper can be replaced by `StockDomain::businessKey` when the input type is `StockRow`.

### Duplicate Keys Fail by Default Instead of Silently Overwriting

~~~java
import java.util.List;
import java.util.function.Function;
import java.util.stream.Collectors;

record Product(String sku, String name) {}

List<Product> duplicates = List.of(
    new Product("BOOK", "Book A"),
    new Product("BOOK", "Book B")
);

// Throws IllegalStateException when BOOK key is duplicated:
duplicates.stream().collect(Collectors.toMap(
    Product::sku,
    Function.identity()
));
~~~

The strength of this overload is **catching conflicts immediately during collection**. It makes sense when duplicate records **are an error and the program should fail**. However, an exception is not a **complete report** of all duplicate keys; if you need to gather every conflict for feedback to the data submitter, see the `groupingBy` patterns below.

By default, `Collectors.toMap` makes no guarantees about Map implementation type, key iteration order, mutability, or thread safety of the result. Rely only on the `Map` interface unless you supply a specific `mapFactory`.

## 5. Approach 2 — Counting Frequencies to Detect Duplicate Keys

When you want to find **every duplicate key** and how many times it appears, `groupingBy(keyMapper, counting())` fits well. The result is `Map<Key, Long>`; keys with count greater than 1 are duplicates.

~~~java
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

public class CountDuplicates {
    record Row(String sku, int quantity) {}

    public static void main(String[] args) {
        List<Row> rows = List.of(
            new Row("BOOK", 2),
            new Row("PEN", 1),
            new Row("BOOK", 3),
            new Row("PAD", 1),
            new Row("PEN", 4)
        );

        Map<String, Long> frequencies = rows.stream()
            .collect(Collectors.groupingBy(
                Row::sku,
                Collectors.counting()
            ));

        Map<String, Long> duplicates = frequencies.entrySet().stream()
            .filter(entry -> entry.getValue() > 1)
            .collect(Collectors.toMap(
                Map.Entry::getKey,
                Map.Entry::getValue
            ));

        System.out.println(duplicates.get("BOOK")); // 2
        System.out.println(duplicates.get("PEN")); // 2
        System.out.println(duplicates.containsKey("PAD")); // false
    }
}
~~~

This is **duplicate detection**, not yet **duplicate resolution**. `BOOK` appears twice, yet the problem still requires deciding: should we sum quantities, pick the latest version, keep both, or reject the import?

### Count by Normalized Key, Not Raw String

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

// StockDomain.businessKey was defined in section 3.
List<StockDomain.StockRow> rows = List.of(
    new StockDomain.StockRow("1", "T1", " book ", 1, 10),
    new StockDomain.StockRow("2", "t1", "BOOK", 2, 8),
    new StockDomain.StockRow("3", "T2", "BOOK", 1, 100)
);

Map<StockDomain.BusinessKey, Long> counts = rows.stream()
    .collect(Collectors.groupingBy(
        StockDomain::businessKey,
        Collectors.counting()
    ));

System.out.println(counts.get(
    new StockDomain.BusinessKey("T1", "BOOK")
)); // 2

System.out.println(counts.get(
    new StockDomain.BusinessKey("T2", "BOOK")
)); // 1
~~~

Note that keys used for Map lookup must already be normalized. Passing a raw SKU like `" book "` to `get` will not cause the Map to normalize the lookup argument automatically.

## 6. Approach 3 — Retaining All Records Within Duplicate Groups

If the ingestion team needs to inspect **which specific rows** caused a conflict, counting alone is insufficient. Use `groupingBy` with a `toList()` downstream, then retain only groups whose size exceeds one.

~~~java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class DuplicateGroups {
    record Row(String rowId, String sku, int quantity) {}

    public static void main(String[] args) {
        List<Row> rows = List.of(
            new Row("r1", "BOOK", 2),
            new Row("r2", "PEN", 1),
            new Row("r3", "BOOK", 3),
            new Row("r4", "PAD", 1)
        );

        Map<String, List<Row>> grouped = rows.stream()
            .collect(Collectors.groupingBy(
                Row::sku,
                LinkedHashMap::new,
                Collectors.toList()
            ));

        Map<String, List<Row>> duplicateGroups =
            grouped.entrySet().stream()
                .filter(entry -> entry.getValue().size() > 1)
                .collect(Collectors.toMap(
                    Map.Entry::getKey,
                    entry -> List.copyOf(entry.getValue()),
                    (left, right) -> left,
                    LinkedHashMap::new
                ));

        System.out.println(
            duplicateGroups.get("BOOK").stream()
                .map(Row::rowId).toList()
        ); // [r1, r3]
    }
}
~~~

Decisions in this example:

1. `LinkedHashMap::new` makes the group Map iterate in **first-seen key order** over a sequential Stream with encounter order.
2. `toList()` preserves every record in the group without losing details.
3. `filter(size > 1)` identifies duplicate-key groups, not merely exact `equals` duplicates.
4. `List.copyOf(...)` creates an unmodifiable List for the group report while **forbidding null elements**.
5. `toMap(..., LinkedHashMap::new)` preserves the key iteration order of the filtered groups.

If key order does not matter, you can omit the `LinkedHashMap` factory. For large datasets, storing entire groups carries memory cost roughly proportional to **the number of input records**. Use counting alone if that is all you need.

### Exact Duplicate or Duplicate Key?

~~~java
record Row(String sku, int quantity) {}

List<Row> rows = List.of(
    new Row("BOOK", 2),
    new Row("BOOK", 3)
);

long exactDistinctCount = rows.stream().distinct().count(); // 2

long businessKeyDistinctCount = rows.stream()
    .map(Row::sku)
    .distinct()
    .count(); // 1
~~~

`distinct()` on `Row` retains both because `quantity` differs. After `map(Row::sku)`, `distinct()` compares only SKUs. However, a `Stream<String>` of distinct SKUs **does not** tell you which original records collided. To investigate, retain record groups as in the previous example.

## 7. Approach 4 — Choosing a Representative Record with mergeFunction

If keys can repeat and the application needs **one final value per key**, use the three-argument overload:

~~~java
Collectors.toMap(
    keyMapper,
    valueMapper,
    mergeFunction
)
~~~

`mergeFunction` receives two mapped values and decides which value to keep.

### 7.1. Choosing First or Last Value: Only When Order Is a Defined Rule

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record Row(String key, String value) {}

List<Row> rows = List.of(
    new Row("K", "first record"),
    new Row("K", "second record")
);

Map<String, String> firstWins = rows.stream()
    .collect(Collectors.toMap(
        Row::key,
        Row::value,
        (left, right) -> left
    ));

Map<String, String> lastWins = rows.stream()
    .collect(Collectors.toMap(
        Row::key,
        Row::value,
        (left, right) -> right
    ));

System.out.println(firstWins.get("K")); // first record
System.out.println(lastWins.get("K"));  // second record
~~~

Here the source is a **sequential List with encounter order**. If the source is unordered, or you use an `UNORDERED` collector like `toConcurrentMap`, picking by `left/right` position does not yield a reliable "first/last in time" policy.

Moreover, file order is not necessarily the entity's **update time**. If business rules say "keep the newest record", compare `version`, `updatedAt`, or a clearly defined precedence key.

### 7.2. Choosing the Latest Version via a version Field

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.function.BinaryOperator;
import java.util.function.Function;
import java.util.stream.Collectors;

public class LatestByVersion {
    record Snapshot(String sku, long version, int quantity) {}

    public static void main(String[] args) {
        List<Snapshot> rows = List.of(
            new Snapshot("BOOK", 1, 10),
            new Snapshot("BOOK", 3, 8),
            new Snapshot("PEN", 2, 5)
        );

        BinaryOperator<Snapshot> chooseLatest =
            BinaryOperator.maxBy(
                Comparator.comparingLong(Snapshot::version)
            );

        Map<String, Snapshot> latest = rows.stream()
            .collect(Collectors.toMap(
                Snapshot::sku,
                Function.identity(),
                chooseLatest
            ));

        System.out.println(latest.get("BOOK").quantity()); // 8
        System.out.println(latest.get("BOOK").version());  // 3
    }
}
~~~

**Do not sum `quantity` across two snapshots** when each record describes inventory state at a different point in time. Summing `10 + 8 = 18` is wrong for the business; the answer must be **8**, from the latest version.

If two records with the same SKU have the **same version but different quantities**, `maxBy` using a version-only comparator does not sufficiently define the winner. Two reasonable options are:

- **Report a conflict** because two snapshots with the same version contradict each other.
- **Define a tie-breaker** based on a stable, meaningful field (such as a source-priority ID), if business rules permit.

### 7.3. Handling Ties Explicitly

A merge function can reject conflicting same-version collisions:

~~~java
import java.util.function.BinaryOperator;

BinaryOperator<LatestByVersion.Snapshot> chooseOrReject =
    (left, right) -> {
        if (left.version() == right.version()) {
            if (!left.equals(right)) {
                throw new IllegalStateException(
                    "Same SKU and version but differing data"
                );
            }
            return left;
        }
        return left.version() > right.version() ? left : right;
    };
~~~

Use this logic when same-version snapshots must be **strictly identical** by contract. For records whose technical metadata differs while payloads are equivalent, compare the **business-meaningful** payload fields rather than necessarily comparing the entire record.

Throwing an exception during merge halts the import; if you want to return a **complete error list**, use `groupingBy` to collect conflicts first, then select representatives in a subsequent step.

## 8. Approach 5 — Merging Values by Key When Records Are Independent Events

Not every duplicate key is an error. When each record represents an **independent event**, multiple rows with the same SKU may need to be **accumulated**.

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class SoldUnitsIndex {
    record SaleLine(String sku, long soldUnits) {}

    public static void main(String[] args) {
        List<SaleLine> sales = List.of(
            new SaleLine("BOOK", 2),
            new SaleLine("PEN", 1),
            new SaleLine("BOOK", 3)
        );

        Map<String, Long> unitsBySku = sales.stream()
            .collect(Collectors.toMap(
                SaleLine::sku,
                SaleLine::soldUnits,
                Long::sum
            ));

        System.out.println(unitsBySku.get("BOOK")); // 5
        System.out.println(unitsBySku.get("PEN"));  // 1
    }
}
~~~

`Long::sum` is an **associative** and **commutative** merge operation under Java integer semantics; it does not depend on row order the way "last record" selection does. Still, `long` can overflow if the mathematical sum exceeds its range.

### Distinguish Snapshot Data from Event Data

| Data Kind | Two Rows Sharing a Key | Usually Valid Handling |
| --- | --- | --- |
| Inventory quantity snapshot | Two states of the same entity | Pick newest version or report conflict |
| Sales line | Two independent sales occurrences | Sum sold units |
| Customer profile | Two updates to one profile | Compare version/timestamp, handle ties |
| Course registration | Two registrations for same student/class/term | Usually report duplicate or keep one valid registration |
| Transaction event with duplicate request ID | Likely a retry of the same transaction | Check idempotency, do not add money twice |

Never pick a merge function merely because it **compiles**. It must enforce the true meaning of "duplicate key" for that kind of data.

## 9. Composite Keys and Multi-Level Identity Scope

A business key may consist of **multiple fields**. In multi-tenant inventory, `sku` is unique only within a `tenantId`:

~~~java
record BusinessKey(String tenantId, String sku) {}

record Row(String tenantId, String sku, int quantity) {}

List<Row> rows = List.of(
    new Row("T1", "BOOK", 10),
    new Row("T2", "BOOK", 20)
);

Map<BusinessKey, Row> byBusinessKey = rows.stream()
    .collect(java.util.stream.Collectors.toMap(
        row -> new BusinessKey(row.tenantId(), row.sku()),
        java.util.function.Function.identity()
    ));

System.out.println(byBusinessKey.size()); // 2
~~~

If you use `Row::sku` alone as the key, the two-argument collector throws `IllegalStateException` because both rows have SKU `BOOK`. Yet these are **two valid rows in different tenants**, so that conflict would be a **false duplicate caused by a wrong key definition**.

### When to Use Nested Maps?

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, Map<String, Row>> byTenantThenSku = rows.stream()
    .collect(Collectors.groupingBy(
        Row::tenantId,
        Collectors.toMap(
            Row::sku,
            java.util.function.Function.identity()
        )
    ));

System.out.println(byTenantThenSku.get("T1").get("BOOK").quantity()); // 10
~~~

Both designs can be appropriate:

- `Map<BusinessKey, Row>`: flat index, lookup via a single key object; convenient for comparisons, caching, and conversions.
- `Map<Tenant, Map<Sku, Row>>`: expresses hierarchical structure; convenient when fetching all SKUs for one tenant.

In the nested Map, the inner `toMap` still fails if there are **two duplicate SKUs within the same tenant**. Thus, identity boundaries are modeled accurately.

## 10. Controlling Nulls and Invalid Data Before Indexing

Collectors do not know on their own what `null` means in your domain. Specifically:

- `groupingBy` in the standard JDK does not allow classifiers to return a `null` key.
- `Collectors.toUnmodifiableMap` forbids both `null` keys and `null` values.
- `Collectors.toMap` should not be treated as a contract that accepts `null` across implementations. In many cases `null` values lead to `NullPointerException`.
- `List.of(...)` rejects null elements, whereas sources such as `Arrays.asList(...)` may contain them.

The **clearest pattern** is to decide the input policy before invoking a collector: **reject**, **filter out**, or **map into an explicit key state**.

### 10.1. Filtering Out Rows That Cannot Form a Key

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.stream.Collectors;

record Row(String sku, int quantity) {}

List<Row> raw = Arrays.asList(
    new Row("BOOK", 3),
    null,
    new Row(null, 5),
    new Row("  ", 7),
    new Row("PEN", 1)
);

List<Row> valid = raw.stream()
    .filter(row -> row != null)
    .filter(row -> row.sku() != null && !row.sku().isBlank())
    .toList();

Map<String, Row> index = valid.stream()
    .collect(Collectors.toMap(
        row -> row.sku().strip().toUpperCase(Locale.ROOT),
        row -> row
    ));

System.out.println(valid.size()); // 2
System.out.println(index.keySet()); // Contains BOOK and PEN.
~~~

Here we chose to **drop invalid records** for illustration. In financial workflows or critical data integrations, you should typically report dropped row counts and reasons, or abort the import. Do not silently convert null into a default key if doing so could accidentally merge distinct entities.

### 10.2. Detecting Nulls Before Comparing

~~~java
// Do NOT call row.sku().strip() before
// ensuring row != null and row.sku() != null.
~~~

`String::strip` and `toUpperCase` require a valid `String` instance. `filter(Objects::nonNull)` for the source row must precede field access; afterward, validate the key component fields.

### 10.3. Key Normalization Must Not Hold Hidden State

Key-building functions must be **pure**: the same record always produces the same key, without depending on counters, current time, or callback order. In a parallel stream, mappers may run in any schedule; a time-varying key mapper destroys determinism.

## 11. Output Order and Choosing the Right Map

A `Map` serves **key-based lookup**, not implicitly an ordered list. `Collectors.toMap` and `groupingBy` make no default guarantees about key iteration order.

| Requirement | Choice | Notes |
| --- | --- | --- |
| Normal lookup, order unimportant | `toMap(key, value, merge)` | Do not rely on `map.keySet()` order |
| Preserve first-seen key order from sequential List | `toMap(key, value, merge, LinkedHashMap::new)` | Insertion order, not version order |
| Sort keys by comparator | `toMap(key, value, merge, TreeMap::new)` | Comparator defines key equivalence |
| Unmodifiable Map, non-null data | `toUnmodifiableMap(key, value, merge)` | No iteration-order guarantee |
| Map suitable for concurrent updates | `toConcurrentMap(...)` | `UNORDERED` collector; must consider order independence |

Example building an index in key encounter order:

~~~java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record Row(String sku, int quantity) {}

List<Row> rows = List.of(
    new Row("PEN", 1),
    new Row("BOOK", 2),
    new Row("PEN", 3)
);

Map<String, Integer> inFirstSeenOrder = rows.stream()
    .collect(Collectors.toMap(
        Row::sku,
        Row::quantity,
        Integer::sum,
        LinkedHashMap::new
    ));

System.out.println(inFirstSeenOrder); // {PEN=4, BOOK=2}
~~~

The resulting Map is mutable. If you want to publish a **structurally unmodifiable** index while still iterating in insertion order, you can use:

~~~java
import java.util.Collections;
import java.util.LinkedHashMap;

Map<String, Integer> published =
    Collections.unmodifiableMap(
        new LinkedHashMap<>(inFirstSeenOrder)
    );
~~~

`Collections.unmodifiableMap` provides a read-only view through the wrapper reference; copying into `new LinkedHashMap<>(...)` decouples its structure from the builder Map. Still, mutable value objects (if any) remain mutable; this is **not automatically deep immutability**.

## 12. Parallelism, Collector CONCURRENT Characteristic, and Merge Functions

When datasets are large, you might consider `parallelStream()`. Correctness must be established before optimizing.

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record SaleLine(String sku, long units) {}

List<SaleLine> sales = List.of(
    new SaleLine("BOOK", 2),
    new SaleLine("BOOK", 3),
    new SaleLine("PEN", 1)
);

Map<String, Long> totals = sales.parallelStream()
    .collect(Collectors.toMap(
        SaleLine::sku,
        SaleLine::units,
        Long::sum
    ));

System.out.println(totals.get("BOOK")); // 5
~~~

`toMap` is **not** a concurrent collector, yet it can run on a parallel stream. The framework accumulates into intermediate Maps and then **merges** them. `toConcurrentMap` has both `CONCURRENT` and `UNORDERED` characteristics, fitting when you want a `ConcurrentMap` and do not need ordering.

~~~java
import java.util.concurrent.ConcurrentMap;

ConcurrentMap<String, Long> concurrentTotals =
    sales.parallelStream().collect(
        Collectors.toConcurrentMap(
            SaleLine::sku,
            SaleLine::units,
            Long::sum
        )
    );
~~~

**Do not use** `(left, right) -> right` as "pick the latest record" in an `UNORDERED` collector. For consistent results, use an **associative** merge function and, when order can vary, make it **commutative** or select representatives using a stable comparison key.

### 12.1. Retaining All Duplicate Groups in Parallel

~~~java
import java.util.concurrent.ConcurrentMap;
import java.util.List;
import java.util.stream.Collectors;

ConcurrentMap<String, List<SaleLine>> grouped =
    sales.parallelStream()
        .collect(Collectors.groupingByConcurrent(
            SaleLine::sku
        ));
~~~

`groupingByConcurrent` is `CONCURRENT` and `UNORDERED`. Group lists are not guaranteed to preserve encounter order or support arbitrary concurrent mutations **after collection**. Choose a sequential collector and an ordered Map type when duplicate-investigation reports must match source order.

### 12.2. Practical Costs

"Hot" keys with many duplicates cause updates to contend on the same entry. Hashing, key normalization, object merging, GC, and Map merging costs can outweigh parallel speedups. There is no fixed size threshold where `parallelStream` is always faster; benchmark on representative data.

## 13. Complete Import Workflow: Keeping Both Index and Duplicate Report

**Synthesis problem:** Inventory data contains tenant, SKU, version, quantity, and import row ID. Inputs may contain `null` rows or invalid key fields. Rules:

1. Rows missing tenant, SKU, or rowId, or having negative version/quantity, are counted as rejected.
2. SKU and tenant are normalized with `strip().toUpperCase(Locale.ROOT)` per exercise rules.
3. Two rows sharing `BusinessKey(tenant, sku)` are recorded as duplicates even if versions differ.
4. The final index keeps the snapshot with the **highest** version.
5. On equal versions, this illustration breaks ties lexicographically by `rowId` so results stay deterministic. **In production, confirm this policy** or raise an error when payloads contradict each other.
6. Map keys iterate in first-seen order from the input list; results are published as structurally unmodifiable Maps.

### Complete Java 17+ Solution

~~~java
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.function.BinaryOperator;
import java.util.function.Function;
import java.util.stream.Collectors;

public class StockImport {
    record StockRow(
        String rowId,
        String tenantId,
        String sku,
        long version,
        int quantity
    ) {}

    record BusinessKey(String tenantId, String sku) {}

    record ImportResult(
        Map<BusinessKey, StockRow> latestByKey,
        Map<BusinessKey, List<StockRow>> duplicateGroups,
        long rejectedRows
    ) {}

    static boolean isValid(StockRow row) {
        return row != null
            && row.rowId() != null && !row.rowId().isBlank()
            && row.tenantId() != null && !row.tenantId().isBlank()
            && row.sku() != null && !row.sku().isBlank()
            && row.version() >= 0
            && row.quantity() >= 0;
    }

    static String canonicalize(String text) {
        Objects.requireNonNull(text, "text");
        return text.strip().toUpperCase(Locale.ROOT);
    }

    static BusinessKey keyOf(StockRow row) {
        return new BusinessKey(
            canonicalize(row.tenantId()),
            canonicalize(row.sku())
        );
    }

    static ImportResult analyze(List<StockRow> source) {
        Objects.requireNonNull(source, "source");

        List<StockRow> valid = source.stream()
            .filter(StockImport::isValid)
            .toList();

        long rejectedCount = source.size() - valid.size();

        // Keep all source rows of duplicate keys for investigation.
        Map<BusinessKey, List<StockRow>> grouped = valid.stream()
            .collect(Collectors.groupingBy(
                StockImport::keyOf,
                LinkedHashMap::new,
                Collectors.toList()
            ));

        Map<BusinessKey, List<StockRow>> duplicateGroups =
            grouped.entrySet().stream()
                .filter(entry -> entry.getValue().size() > 1)
                .collect(Collectors.toMap(
                    Map.Entry::getKey,
                    entry -> List.copyOf(entry.getValue()),
                    (left, right) -> left,
                    LinkedHashMap::new
                ));

        Comparator<StockRow> newer = Comparator
            .comparingLong(StockRow::version)
            .thenComparing(StockRow::rowId);

        BinaryOperator<StockRow> chooseLatest =
            BinaryOperator.maxBy(newer);

        Map<BusinessKey, StockRow> latest = valid.stream()
            .collect(Collectors.toMap(
                StockImport::keyOf,
                Function.identity(),
                chooseLatest,
                LinkedHashMap::new
            ));

        return new ImportResult(
            Collections.unmodifiableMap(
                new LinkedHashMap<>(latest)
            ),
            Collections.unmodifiableMap(
                new LinkedHashMap<>(duplicateGroups)
            ),
            rejectedCount
        );
    }

    public static void main(String[] args) {
        List<StockRow> incoming = Arrays.asList(
            new StockRow("r1", "T1", " book ", 1, 10),
            new StockRow("r2", "t1", "BOOK", 2, 8),
            new StockRow("r3", "T1", "PEN", 1, 5),
            new StockRow("r4", "T2", "BOOK", 1, 100),
            new StockRow("r5", "T1", " ", 1, 1),
            null
        );

        ImportResult report = analyze(incoming);

        BusinessKey t1Book = new BusinessKey("T1", "BOOK");
        BusinessKey t2Book = new BusinessKey("T2", "BOOK");

        System.out.println(report.rejectedRows()); // 2
        System.out.println(report.latestByKey().size()); // 3

        System.out.println(
            report.latestByKey().get(t1Book).quantity()
        ); // 8 (version 2)

        System.out.println(
            report.latestByKey().get(t2Book).quantity()
        ); // 100 (different tenant)

        System.out.println(
            report.duplicateGroups().get(t1Book)
                .stream().map(StockRow::rowId).toList()
        ); // [r1, r2]
    }
}
~~~

### Why Compute Two Separate Structures?

- `groupingBy` retains every original record for duplicate keys, supporting diagnostics.
- `toMap` with `mergeFunction` retains one representative record, supporting frequent lookups.
- `LinkedHashMap` keeps reports easy to follow in **first-seen key order** from a sequential input `List`.
- `List.copyOf` in the duplicate report creates unmodifiable lists; `StockRow` also holds only immutable values in this example.
- `rejectedCount` preserves the count of dropped inputs; production systems may also store per-row rejection reasons.

Above, `StockRow` retains its original source fields while the **Map key** is normalized. Do not call `latestByKey().get(new BusinessKey("t1", " book "))` expecting the Map to normalize the query. Provide a `lookupKey(tenant, sku)` helper applying the same `canonicalize` before lookup.

### If Arbitrary Tie-Breaking Is Unacceptable

The tie-breaker `thenComparing(StockRow::rowId)` makes selection consistent, not guaranteed to be business-correct. If equal `version` with different quantities is a **conflict error**, detect it in `duplicateGroups` and fail **before** producing the final index. Never let a technical tie-breaker mask a data violation.

## 14. Testing Key and Index Correctness

Tests should focus on **business semantics**, not the incidental print order of a `HashMap`. Key scenarios:

| Scenario | Expected Outcome |
| --- | --- |
| Same tenant, SKU differing in case | Same key if policy is case-insensitive |
| Same SKU, different tenants | Two distinct keys |
| Same key, newer version | Selects highest version |
| Same key, equal version, differing payload | Reports conflict or applies defined tie policy |
| Null/blank key | Per policy: reject, never silently index |
| Empty source | Empty index and empty duplicate report |
| Single valid row | One entry, no duplicate groups |
| Multiple duplicate records | One index entry and a duplicate group containing all rows |
| Data consists of independent events | Merge by addition if domain-appropriate |
| Parallel/unordered | Representative selection never depends on thread scheduling |
| Mutable key | Never use keys whose state changes after Map insertion |

### A Test Independent of HashMap Order

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class IndexAssertions {
    record Row(String tenant, String sku, int quantity) {}
    record Key(String tenant, String sku) {}

    static Key keyOf(Row row) {
        return new Key(row.tenant(), row.sku());
    }

    public static void main(String[] args) {
        List<Row> rows = List.of(
            new Row("T1", "BOOK", 1),
            new Row("T2", "BOOK", 2),
            new Row("T1", "BOOK", 3)
        );

        Map<Key, Long> counts = rows.stream()
            .collect(Collectors.groupingBy(
                IndexAssertions::keyOf,
                Collectors.counting()
            ));

        if (counts.size() != 2) {
            throw new AssertionError("Wrong distinct key count");
        }
        if (!Long.valueOf(2).equals(
                counts.get(new Key("T1", "BOOK")))) {
            throw new AssertionError("Failed to detect duplicate key properly");
        }
        if (!Long.valueOf(1).equals(
                counts.get(new Key("T2", "BOOK")))) {
            throw new AssertionError("Incorrectly merged data across tenants");
        }

        System.out.println("PASS");
    }
}
~~~

This test uses `record Key` to verify key equality across **two fields**. In production, add tests for normalization, nulls, collisions, version ties, and numeric bounds.

### Should Sequential and Parallel Streams Be Compared?

Yes, if you plan to use parallelism. For associative/commutative sums, comparing Maps by content via `Map.equals` makes sense. When selecting latest by `version`, define a **total ordering** so results do not depend on chunking. Never measure correctness by `peek` log counts or callback ordering.

## 15. Performance and Limits of This Approach

### 15.1. Map Lookup Instead of Repeated List Scans

If you need to look up `k` records from a List of `n` rows, repeating `list.stream().filter(...).findFirst()` performs many linear scans. Building a Map once lets key queries via `get` run much faster across many lookups.

General cost profile:

- Building a `HashMap` via `toMap`: scales on average linearly with input size when hash and equality behave well.
- Each `Map.get`: average near O(1) for HashMap assuming good hash distribution.
- `groupingBy(..., toList())`: holds all records, so memory scales with source size.
- `TreeMap`: ordered by comparator; lookup/insert operations are typically O(log k) for `k` keys.

These are general guidelines, not fixed-time guarantees of the Stream API. Severe hash collisions, expensive normalization, or memory/GC pressure can alter real performance.

### 15.2. Do Not Build Full Group Lists When Only Counts Are Needed

`groupingBy(key, counting())` stores one count per key, whereas `groupingBy(key, toList())` stores **every row** in each group. If you only need to know whether duplicates exist without row details, counting is usually much lighter on memory.

If the dataset is very large and you must find **all duplicate groups**, consider batch processing or a database/dedicated engine. An in-memory Map does not replace persistent constraints and indexes on storage systems.

### 15.3. An In-Memory Index Does Not Guarantee Transactional Uniqueness

Two processes can read data concurrently, each see "no duplicates", and both write to the database. Duplicate checks in a Stream only validate **data within the current in-memory batch**; they do not prevent race conditions across concurrent import sessions.

For durable uniqueness guarantees, use a **unique constraint/index** or proper upsert/transaction semantics at the storage layer. Streams can catch bad batches early and build friendly reports, but they do not replace database consistency guarantees.

## 16. Common Misconceptions

### Misconception 1: `distinct()` is enough to find all business duplicates

`distinct()` checks element `equals`. If the business key is tenant + SKU, map to `BusinessKey` or group by the key function; two records with different versions can still collide on key.

### Misconception 2: `toMap` automatically overwrites duplicate records

The two-argument overload throws `IllegalStateException` on duplicate keys. To resolve duplicates, pass a `mergeFunction` and define business rules.

### Misconception 3: snapshot data can be summed like event transactions

Inventory counts of 10 and then 8 are two states, not a total of 18. Distinguish snapshots from events before choosing `Integer::sum` or `Long::sum`.

### Misconception 4: normalization is only needed at import, not at query time

Maps use `equals`/`hashCode` on the keys given to them. Querying `" book "` does not automatically become `"BOOK"`. Share the same normalization function for both index creation and lookup.

### Misconception 5: using SKU alone as the key across all tenants

An SKU can exist across multiple tenants. Use a composite key to avoid false duplicate detections and overwriting another tenant's data.

### Misconception 6: `(left, right) -> right` always picks the newest record

Processing order and thread scheduling are not business timestamps. Compare version/timestamp with an explicit tie policy.

### Misconception 7: an unmodifiable Map means deep immutability

`Map.copyOf` and `Collections.unmodifiableMap` prevent structural edits through the resulting Map, yet if values are mutable objects, their internal fields can still mutate. Choose immutable value objects or defensive copies when true snapshots are needed.

### Misconception 8: switching to `parallelStream()` always speeds things up

Merging overhead, task splitting, hot-key contention, allocations, and GC can make parallel runs slower. Before benchmarking, ensure mappers are pure and merge functions are valid.

## 17. Solution Selection Table by Goal

| Goal | Suggested Pipeline or Collector | Notes |
| --- | --- | --- |
| Index when keys must be unique | `toMap(key, identity())` | Fails on duplicate keys |
| Find every key appearing more than once | `groupingBy(key, counting())` then filter `count > 1` | Does not retain payloads |
| Keep all rows causing duplicates | `groupingBy(key, toList())` then filter groups `size > 1` | Uses more memory |
| Pick newest snapshot | `toMap(key, identity(), maxBy(versionComparator))` | Must handle ties |
| Sum independent events | `toMap(key, amountMapper, sumOperator)` | Check overflow/units |
| Index by multiple fields | `record BusinessKey(...)` as key | Ensure normalization and equality |
| Preserve first-seen key order | `toMap(..., LinkedHashMap::new)` | Sequential ordered source |
| Sort keys by comparator | `toMap(..., TreeMap::new)` | Comparator defines equivalence |
| Collect into ConcurrentMap | `toConcurrentMap(...)` | `UNORDERED`, do not rely on last-wins |
| Build groups concurrently | `groupingByConcurrent(...)` | Does not preserve encounter order |
| Publish read-only Map | Copy then wrap, or `toUnmodifiableMap` when suitable | Watch nulls, order, and mutable values |
| Maintain cross-transaction uniqueness | Unique constraint/index in database | Streams alone are insufficient |

## 18. Self-Check Questions and Extended Exercises

1. **How does a technical key differ from a business key?** A technical key identifies a stored record; a business key identifies an entity under domain rules.
2. **Why is `(tenantId, sku)` better than `sku` alone in a multi-tenant system?** The same SKU across two different tenants is not a duplicate entity.
3. **What does `Collectors.toMap(key, value)` do on duplicate keys?** It throws `IllegalStateException`.
4. **What should you use to get all duplicate keys and their counts?** `groupingBy(key, counting())` followed by filtering counts greater than 1.
5. **What should you use to inspect the conflicting rows themselves?** `groupingBy(key, toList())` followed by filtering duplicate groups.
6. **Can two records with different `quantity` values but the same tenant/SKU be considered duplicates?** Yes, if the business key consists only of tenant/SKU.
7. **Does `distinct()` across the whole record detect key duplicates regardless of version?** Not necessarily; `distinct` relies on the record's `equals`.
8. **Why must key normalization be applied both when building the index and when looking up keys?** Because Map does not normalize lookup queries automatically.
9. **Why should you avoid an unseparated concatenated string as a composite key?** Different component pairs can produce the same resulting string.
10. **Is keeping the highest-version row appropriate for aggregating sales across multiple transactions?** No; sales events usually need summing or preserving per transaction depending on the model.
11. **Why do equal versions need a tie-breaker or conflict error?** Because a version-only comparator may not uniquely identify a single valid representative.
12. **Does `Long::sum` guarantee no long overflow?** No.
13. **Should you rely on the print order of default `Collectors.toMap`?** No.
14. **When should you use `LinkedHashMap::new`?** When keys must iterate in insertion order.
15. **Does `toConcurrentMap` guarantee encounter order?** No; it is an `UNORDERED` collector.
16. **Can you pass `null` from a key mapper and expect every collector to behave the same?** No; define an explicit policy before collecting.
17. **Why avoid storing every group List if you only need to detect duplicates?** Storing payloads increases memory usage; counting may suffice.
18. **Do Stream duplicate checks replace database unique constraints?** No; they do not enforce uniqueness across processes or transactions.
19. **When should a loop be preferred over a Stream?** When you need to stop immediately with detailed error context, accumulate multiple structures with controlled side effects, or avoid unreadable nested collectors.
20. **How do immutable records and an immutable `BusinessKey` help?** They keep `equals`/`hashCode` and indexed data stable, preventing mutations from breaking lookups.

### Extended Exercise A — Detecting Version Conflicts

For snapshots sharing a `BusinessKey`, implement the rule: higher version wins; if versions are equal and quantities differ, report an error. Design a test with three records sharing a key, two having equal version and different quantities.

### Extended Exercise B — Never Drop Bad Data Silently

Replace `rejectedRows` with `List<ValidationError>` containing `rowId` and reason: missing tenant, missing SKU, negative quantity, or negative version. Design collectors or classification steps so invalid rows never enter the final Map.

### Extended Exercise C — Date-Scoped Business Key

Create `record DailyKey(String accountId, LocalDate day)`. Import transactions, group by day and account, and sum with `BigDecimal`. Test timestamps across time zones: determine the "day" in the business time zone before constructing the key.

### Extended Exercise D — Comparing Parallel Approaches

Use a 100,000-row dataset with low and high distinct-key cardinality. Compare `toMap` and `toConcurrentMap` with `Long::sum`, verify Map equality with `equals`, and benchmark. Do not assume concurrent is faster; explain the impact of hot keys.

**Key takeaway:** Reliable indexing starts with **defining the business key** and **normalization rules**, not with calling `toMap`. `toMap` fits when you want one result per key with an explicit conflict policy; `groupingBy` fits when you need counts or full duplicate groups for inspection. Distinguish snapshots from independent events, handle `null`s and ties explicitly, make sure merges fit the data domain, and remember that an in-memory Stream index never replaces storage-layer consistency constraints.
