# Designing Stable Grouping Keys and Handling Missing Keys in Java Streams

## Objectives

When grouping data with `Collectors.groupingBy(...)`, the result does not depend solely on counting or listing elements: it depends first and foremost on the **grouping key** produced by the classifier. Two records that should belong to the same group will be split apart if the key is not normalized consistently; two different groups may be merged by mistake if a colliding fallback value is used. In particular, **the classifier of `groupingBy` must not return `null`**. This remains true even if the Map type you want to use supports null keys.

This lesson focuses on three principles:

1. **Keys with stable meaning:** accurately represent the grouping criterion, have consistent `equals()`/`hashCode()`, and do not change while stored in the Map.
2. **Keys normalized according to an explicit policy:** handle case, whitespace, identifiers, and composite components intentionally.
3. **Missing keys represented explicitly:** use `Optional.empty()`, a dedicated status type, or an appropriate data strategy instead of returning `null` directly to `groupingBy`.

After this lesson, you will be able to design single and composite grouping keys, distinguish records with a missing key from valid key strings, read `Map<K,List<T>>` results, aggregate data using downstream collectors, choose `partitioningBy` when only two groups are needed, and avoid bugs related to mutable keys, ordering, comparators, and concurrent processing.

## 1. How Does groupingBy Use the Classifier?

The simplified signature of `Collectors.groupingBy`:

```java
static <T, K> Collector<T, ?, Map<K, List<T>>> groupingBy(
        Function<? super T, ? extends K> classifier);
```

This is a **simplified API signature**, not a method you need to write yourself in a project. `T` is the input element type, and `K` is the key type returned by the classifier. In a pipeline:

```java
Map<String, List<String>> byFirstLetter =
        Stream.of("An", "Anh", "Bình")
                .collect(Collectors.groupingBy(
                        name -> name.substring(0, 1)
                ));
```

`name -> name.substring(0, 1)` is the classifier. The two names starting with `A` belong to the `"A"` group; `"Bình"` belongs to the `"B"` group. The Map values are lists of the original elements because this overload uses a downstream collector equivalent to `toList()`.

Key points to understand:

- If two elements produce keys that are **equal according to the Map's contract**, they are placed in the same group.
- If they produce different keys, they are placed in separate groups, even if a user might view the two strings as "having the same meaning."
- Map iteration order is **not guaranteed** in the default overload; to choose a specific Map implementation, use the overload with `mapFactory`.
- `groupingBy` does not sanitize input data or automatically decide how to normalize text.
- `groupingBy` does not allow the classifier to return `null`: if an element produces a null key, the collection operation throws a `NullPointerException`.

An important example:

```java
record Sale(String category, int units) {}

List<Sale> sales = List.of(
        new Sale("Food", 2),
        new Sale("food", 3),
        new Sale(" Food ", 4)
);

Map<String, List<Sale>> groups = sales.stream()
        .collect(Collectors.groupingBy(Sale::category));
```

This is an **illustrative snippet** that requires importing `List`, `Map`, and `Collectors`. The Map will have three distinct String keys: `"Food"`, `"food"`, and `" Food "`. By default, `String.equals()` is case-sensitive and whitespace-sensitive; Java does not know whether business requirements treat those three strings as equivalent.

## 2. What Makes a Grouping Key Stable?

A good grouping key must satisfy both **semantic correctness** and **data type contract correctness**.

| Property | Practical Meaning | When Violated |
| --- | --- | --- |
| Accurately represents the criterion | Two records in the same group produce equal keys | Groups are fragmented or merged by mistake |
| Correct `equals()` | Two keys with the same business value compare equal | Map contains keys that "look alike" |
| Consistent `hashCode()` | Equal keys have the same hash code | `HashMap`/`LinkedHashMap`/`groupingBy` may look up the wrong group |
| Immutable while in the Map | Fields participating in comparison remain unchanged | `get`, `containsKey` may fail to find the key again |
| Transparent handling of missing state | Missing data does not cause NPE or collide with valid keys | Lost records or incorrect results |
| Policy-based normalization | Case, whitespace, and code formatting are handled consistently | Data becomes fragmented or loses necessary distinctions |

### 2.1. String Is a Good Key Once Comparison Rules Are Chosen Clearly

`String` is immutable and already implements `equals`/`hashCode` based on content. If the data is a **classification code** that is case-insensitive and where leading/trailing whitespace is insignificant, it can be normalized:

```java
String normalized = raw.strip().toLowerCase(Locale.ROOT);
```

`strip()` (Java 11+) handles whitespace according to Java's Unicode definition; `toLowerCase(Locale.ROOT)` avoids depending on the machine's default locale when normalizing **technical identifiers**. `java.util.Locale` must be imported.

However, **do not normalize every data field in the same way**. Country codes, SKUs, email addresses, product codes, and natural-language proper names have different comparison contracts. Lowercasing or stripping diacritics can merge two entities that must remain distinct. Always refer to domain documentation and data specifications.

### 2.2. Mutable Object Keys Are a Dangerous Choice

Suppose you use a class with a mutable `category` field, and `equals`/`hashCode` depend on that field. After the object is added as a key in a `HashMap`, if `category` is modified, its hash code may change. At that point, `map.get(key)` or `map.containsKey(key)` may fail, even though the object reference itself still sits in an old bucket.

Multiple threads are not required to trigger this bug; a single field update at the wrong time is enough. **Never modify fields that participate in `equals`/`hashCode` of a key already stored in a Map**.

If you must use a mutable entity as your data, **extract an immutable key** such as a normalized String ID, an enum, or a record containing only immutable components. Separate the entity's identity from presentation data or mutable data.

## 3. record as a Stable Composite Key

Suppose you need to group transactions by **region** and **category**. Grouping only by region would merge food with books; grouping only by category would merge different regions. The key must carry both components.

A Java record is a concise choice when key data is value-based:

```java
record GroupKey(String region, String category) {}
```

The compiler automatically generates the constructor, accessors, `equals`, `hashCode`, and `toString` based on the record components. Two records with the same content in both components will compare equal under value semantics. For example:

```java
GroupKey a = new GroupKey("north", "food");
GroupKey b = new GroupKey("north", "food");
System.out.println(a.equals(b)); // true
```

These are two illustrative statements inside a method where `GroupKey` has already been defined. Even though `a` and `b` are two separate objects, the record's value-based `equals` returns true.

**A record is immutable at the component reference level, not automatically deep-immutable.** If a record contains a mutable `List` and `equals/hashCode` depend on the List's contents, modifying the List after using the record as a key can still break stability. For grouping keys, prefer already-immutable components such as String, enum, integers, `Optional<String>`, or nested immutable records.

### 3.1. Preserving the Meaning of Missing Data

A record can hold null components; `new GroupKey(null, "food")` itself is a **non-null** key object, so it does not directly violate the rule that "the classifier must not return null." However, if multiple places in the code handle null differently, comparison and presentation logic become hard to maintain.

It can be designed more explicitly:

```java
record GroupKey(
        Optional<String> region,
        Optional<String> category
) {}
```

Each `Optional.empty()` component means **no valid data is present under the chosen policy**. `GroupKey` itself is always a non-null object. In this lesson's example, String and Optional hold immutable values, making the key suitable for storing in a Map.

Using Optional in record components here is an intentional modeling choice for this lesson. For larger domain models or data that needs serialization, you might choose a missing-status enum, a *sum type*, or another record with an explicit contract; do not treat Optional in every field as a mandatory rule.

## 4. Handling Missing Keys: Avoid Returning null from the Classifier

### 4.1. Why Does groupingBy Fail with a null Key?

Given the data:

```java
record Sale(String category, int units) {}

List<Sale> sales = List.of(
        new Sale("food", 2),
        new Sale(null, 1)
);

Map<String, List<Sale>> grouped =
        sales.stream().collect(
                Collectors.groupingBy(Sale::category));
```

When encountering the record with `category() == null`, the classifier returns null and `Collectors.groupingBy` throws a `NullPointerException`. This remains true for overloads using `HashMap::new` or `LinkedHashMap::new`, even though those two Map implementations can hold null keys in other operations.

**Make sure to distinguish:** "`HashMap` allows null keys" does not mean "`groupingBy` allows the classifier to return null." `groupingByConcurrent` is not a workaround for grouping directly with a null-returning classifier either.

### 4.2. Approach A — A Clearly Named Sentinel, When Guaranteed Not to Collide with Valid Data

```java
String key = rawCategory == null
        ? "__MISSING_CATEGORY__"
        : rawCategory;
```

This is one way to represent a missing state using a special string. It can be simple, but it carries a **key collision risk**: if valid data actually contains the string `"__MISSING_CATEGORY__"`, records with a real value and missing records will be merged together.

Only use a String sentinel when **the domain strictly guarantees** this string cannot be a valid value, and the entire system shares the same convention. In cross-system reporting, the risk of collision increases as new categories are added.

### 4.3. Approach B — Optional as Part of the Key Type

```java
Map<Optional<String>, List<Sale>> grouped =
        sales.stream().collect(Collectors.groupingBy(
                sale -> Optional.ofNullable(sale.category())
        ));
```

When category is null, the classifier still returns a non-null `Optional.empty()` object; when category is present, it returns `Optional.of(category)`. As a result, it never collides with valid String values even if their content is `"unknown"` or `"__MISSING_CATEGORY__"`.

If empty/blank strings should also be treated as missing, use a normalization function that returns `Optional<String>` according to policy:

```java
static Optional<String> normalize(String raw) {
    if (raw == null) return Optional.empty();

    String normalized = raw.strip().toLowerCase(Locale.ROOT);
    return normalized.isEmpty()
            ? Optional.empty()
            : Optional.of(normalized);
}
```

This is a standalone method to be placed in a class that imports `Optional` and `Locale`. Note: the decision to treat `"  "` as missing is a **business policy** of this example. If the system needs to distinguish "not provided" from "provided but empty," use separate statuses instead of collapsing both into Optional.empty().

### 4.4. Approach C — A Dedicated Status Type

If the code needs to clearly distinguish multiple kinds of missing or invalid states:

- Field absent in the source.
- Field present but containing only whitespace.
- Field present but failing validation.
- Value genuinely belonging to the `"unknown"` group.

A wrapper or dedicated status type represents this more accurately than a String sentinel. In Java 17, you can use a `sealed interface` with implementing records to express the states, or use a record with two fields `status` and `value`. What matters is that **the classifier always returns a non-null key object** with appropriate `equals/hashCode`.

Do not erase business distinctions just to avoid `NullPointerException`; the missing-data policy should be designed before writing grouping code.

### 4.5. Approach D — Filtering Out Missing Records, When Truly Permitted

```java
Map<String, List<Sale>> grouped = sales.stream()
        .filter(sale -> sale.category() != null)
        .collect(Collectors.groupingBy(Sale::category));
```

This illustrative snippet skips records with a missing category. It may be correct for reports that only summarize valid data, but it is **incorrect** for reports that must preserve the total record count. If records are dropped, the discarded count must be explicitly reported or routed to an appropriate error-handling flow.

## 5. Centralizing Key Normalization in a Single Place

A common mistake is normalizing during validation or checks, but not when grouping:

```java
String normalized = input.trim().toLowerCase();
// But the classifier still returns the unnormalized rawCategory.
```

If multiple modules handle this differently, discrepancies between `"Food"` and `" food "` easily reappear. Instead of duplicating rules, create a reusable normalization function:

```java
static Optional<String> normalize(String raw) {
    if (raw == null) return Optional.empty();
    String key = raw.strip().toLowerCase(Locale.ROOT);
    return key.isEmpty() ? Optional.empty() : Optional.of(key);
}
```

Then always build keys through the same function:

```java
static GroupKey keyOf(Sale sale) {
    return new GroupKey(
            normalize(sale.region()),
            normalize(sale.category())
    );
}
```

These are the methods from the complete program below. `GroupKey` is a record with two `Optional<String>` components.

**When normalizing, determine:**

1. Should comparison be case-sensitive? If yes, **do not lowercase**.
2. Should leading/trailing whitespace be stripped? For technical codes, usually yes; for prose text, it depends on requirements.
3. Is Unicode normalization (NFC/NFKC) needed? These options can unify visually similar strings; follow the data specification.
4. Should null and blank be merged? If they must be distinguished, use two separate states.
5. Must the original value be preserved for display or auditing? If yes, keep the raw value in the original record and normalize only the **key used for grouping**.

`Locale.ROOT` is appropriate when normalizing language-independent identifiers; for proper names and natural-language comparison rules, a different policy may be required. Do not arbitrarily strip Vietnamese diacritics or convert accented characters to unaccented ones just to reduce the number of groups.

## 6. Complete Java 17 Program

The following program uses sales data with varying region/category casing and whitespace, as well as missing data. It demonstrates four points:

- The two variants `"North"` and `" north "` produce the same grouping key.
- An immutable `record GroupKey` containing `Optional<String>` distinguishes components without data.
- `groupingBy` can be combined with `mapping`, `summingInt`, `counting`, and `partitioningBy` to produce multiple kinds of results.
- A classifier returning `null` causes a `NullPointerException`, whereas normalizing to return a valid key object avoids the error.

Create the file **`StableGroupingKeyDemo.java`**:

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.stream.Collectors;

public class StableGroupingKeyDemo {
    record Sale(String region, String category, String product, int units) {}

    record GroupKey(Optional<String> region,
                    Optional<String> category) {}

    static Optional<String> normalize(String raw) {
        if (raw == null) return Optional.empty();
        String normalized = raw.strip().toLowerCase(Locale.ROOT);
        return normalized.isEmpty()
                ? Optional.empty() : Optional.of(normalized);
    }

    static GroupKey keyOf(Sale sale) {
        return new GroupKey(normalize(sale.region()),
                            normalize(sale.category()));
    }

    public static void main(String[] args) {
        List<Sale> sales = List.of(
                new Sale("North", "Food", "Apples", 2),
                new Sale(" north ", "food", "Pears", 3),
                new Sale("South", null, "Tea", 1),
                new Sale(null, "Books", "Guide", 4),
                new Sale(" ", "  ", "Missing", 5),
                new Sale("South", "Food", "Cake", 2)
        );

        Map<GroupKey, List<String>> grouped = sales.stream().collect(
                Collectors.groupingBy(
                        StableGroupingKeyDemo::keyOf,
                        LinkedHashMap::new,
                        Collectors.mapping(
                                Sale::product, Collectors.toList())
                )
        );
        System.out.println("Groups: " + grouped);

        Map<GroupKey, Integer> units = sales.stream().collect(
                Collectors.groupingBy(
                        StableGroupingKeyDemo::keyOf,
                        LinkedHashMap::new,
                        Collectors.summingInt(Sale::units)
                )
        );
        System.out.println("Units: " + units);

        Map<Optional<String>, Long> counts = sales.stream().collect(
                Collectors.groupingBy(
                        s -> normalize(s.category()),
                        LinkedHashMap::new,
                        Collectors.counting()
                )
        );
        System.out.println("Category counts: " + counts);

        Map<Boolean, List<String>> partition = sales.stream().collect(
                Collectors.partitioningBy(
                        s -> normalize(s.category()).isEmpty(),
                        Collectors.mapping(
                                Sale::product, Collectors.toList())
                )
        );
        System.out.println("Missing category: " + partition.get(true));
        System.out.println("Present category: " + partition.get(false));

        try {
            sales.stream().collect(
                    Collectors.groupingBy(Sale::category)
            );
        } catch (NullPointerException ex) {
            System.out.println("Raw nullable key: NullPointerException");
        }

        System.out.println("Key equals: " + keyOf(sales.get(0))
                .equals(keyOf(sales.get(1))));
    }
}
```

Compile and run with **JDK 17 or higher**:

```bash
javac StableGroupingKeyDemo.java
java StableGroupingKeyDemo
```

**Exact stdout:**

```text
Groups: {GroupKey[region=Optional[north], category=Optional[food]]=[Apples, Pears], GroupKey[region=Optional[south], category=Optional.empty]=[Tea], GroupKey[region=Optional.empty, category=Optional[books]]=[Guide], GroupKey[region=Optional.empty, category=Optional.empty]=[Missing], GroupKey[region=Optional[south], category=Optional[food]]=[Cake]}
Units: {GroupKey[region=Optional[north], category=Optional[food]]=5, GroupKey[region=Optional[south], category=Optional.empty]=1, GroupKey[region=Optional.empty, category=Optional[books]]=4, GroupKey[region=Optional.empty, category=Optional.empty]=5, GroupKey[region=Optional[south], category=Optional[food]]=2}
Category counts: {Optional[food]=3, Optional.empty=2, Optional[books]=1}
Missing category: [Tea, Missing]
Present category: [Apples, Pears, Guide, Cake]
Raw nullable key: NullPointerException
Key equals: true
```

### 6.1. Why Are the Results Correct?

**Group 1:** `Sale("North","Food","Apples",2)` and `Sale(" north ","food","Pears",3)` produce the same `GroupKey(Optional[north], Optional[food])`. `strip` removes whitespace, and `toLowerCase(Locale.ROOT)` standardizes casing. The group's list is `[Apples, Pears]` and the total `units` is `2 + 3 = 5`.

**Group 2:** `Sale("South",null,"Tea",1)` has category `Optional.empty()`, but region `Optional[south]`. This is a valid composite key and is distinct from the `South/Food` group.

**Group 3:** `Sale(null,"Books","Guide",4)` has a missing region but category `Optional[books]`.

**Group 4:** `Sale(" ","  ","Missing",5)` has two blank strings. Under `normalize`'s policy, both become `Optional.empty()`; the record is still preserved in its own group.

**Group 5:** `Sale("South","Food","Cake",2)` has key `South/Food`, which differs from `North/Food`, so it is not merged by mistake.

**Category counts:** the `Optional[food]` group has three records (Apples, Pears, Cake), `Optional.empty` has two records (Tea, Missing), and `Optional[books]` has one record (Guide). `Collectors.counting()` returns `Long`.

**Partitioning:** `partitioningBy(predicate)` creates two boolean groups: `true` for records with a missing category and `false` for records with a present category. Because the predicate only checks for a missing category, the `true` group contains Tea and Missing; the `false` group contains Apples, Pears, Guide, and Cake.

**NPE:** calling `groupingBy(Sale::category)` directly on data with a null category violates the non-null classifier contract. The program catches `NullPointerException` to illustrate where the failure occurs, not to recommend using exceptions for normal data-grouping control flow.

**equals:** the first two records share the same normalized key, so `keyOf(sales.get(0)).equals(keyOf(sales.get(1)))` returns `true`.

### 6.2. Why Is the Map Output Ordered?

The program uses:

```java
Collectors.groupingBy(
        StableGroupingKeyDemo::keyOf,
        LinkedHashMap::new,
        downstream
)
```

`LinkedHashMap::new` selects a Map that preserves key insertion order. In a **sequential** program with an ordered `List.of` source that has an encounter order, groups appear in the order their keys are first encountered, producing deterministic output. Do not rely on the print order of the default `groupingBy(classifier)` overload, as it makes no guarantee about the Map type.

With parallel streams, partial Maps may be created and merged; do not treat callback log order or key-creation timing as a stable contract across runs.

## 7. Choosing a Downstream Collector to Preserve Group Semantics

The classifier returns the key; the **downstream collector** decides what data is retained for each key. You do not always need a `List<T>` containing every full record.

### 7.1. Counting Records per Group

```java
Map<GroupKey, Long> counts = sales.stream().collect(
        Collectors.groupingBy(
                StableGroupingKeyDemo::keyOf,
                Collectors.counting()
        )
);
```

Each key maps to a `Long` record count rather than a list of `Sale` objects. If you only need counts, there is no need to collect all records and then call `list.size()`.

### 7.2. Summing Quantities per Group

```java
Map<GroupKey, Integer> totals = sales.stream().collect(
        Collectors.groupingBy(
                StableGroupingKeyDemo::keyOf,
                Collectors.summingInt(Sale::units)
        )
);
```

The `summingInt` downstream collector sums `units`. If the sum can exceed the `int` range, consider `summingLong(s -> s.units())` or an overflow-checking mechanism suited to the data. `Collectors` does not replace choosing the right numeric type for the business domain.

### 7.3. Storing Only Product Names

```java
Map<GroupKey, List<String>> names = sales.stream().collect(
        Collectors.groupingBy(
                StableGroupingKeyDemo::keyOf,
                Collectors.mapping(
                        Sale::product,
                        Collectors.toList()
                )
        )
);
```

The result is `Map<GroupKey,List<String>>`. `Collectors.toList()` does not guarantee mutability of the returned List; if you need a specific collection type, use `Collectors.toCollection(ArrayList::new)` as the downstream collector.

### 7.4. Collecting Unique Names

```java
Map<GroupKey, Set<String>> uniqueNames = sales.stream().collect(
        Collectors.groupingBy(
                StableGroupingKeyDemo::keyOf,
                Collectors.mapping(
                        Sale::product,
                        Collectors.toSet()
                )
        )
);
```

This is illustrative code that requires importing `Set`. `toSet()` does not guarantee iteration order; to preserve first-appearance order in an ordered pipeline, use `toCollection(LinkedHashSet::new)`.

**Important:** key normalization and downstream collection are **two independent decisions**. Normalizing a key to match groups correctly does not mean automatically normalizing or mutating the contents of each `Sale`.

## 8. groupingBy or partitioningBy?

`Collectors.partitioningBy(predicate)` is appropriate when you need to split elements into **two partitions** based on a boolean condition, such as "missing category" and "present category."

```java
Map<Boolean, List<Sale>> partitions = sales.stream()
        .collect(Collectors.partitioningBy(
                s -> normalize(s.category()).isEmpty()
        ));
```

The result has two boolean keys: `true` and `false`. `partitioningBy` has a two-partition contract; even if one side has no elements, that side still exists as a partition with the appropriate downstream result. This differs from `groupingBy(s -> booleanCondition)`, which typically only creates keys that actually appear in the source.

Choose:

- **`partitioningBy`** when the problem genuinely has exactly two states determined by a single predicate.
- **`groupingBy`** when you need multiple key values, composite keys, or when missing data is one of several groups.
- **`filter`** when dropping unqualified records completely is permitted; consider its impact on report completeness.

For example, suppose the source has `null` categories across different regions: if you use `partitioningBy(categoryMissing)`, all records missing a category go into the same partition. If you use `groupingBy(GroupKey)`, they can still be separated by region. Thus, the two APIs are not interchangeable for all requirements.

## 9. Composite Keys and Stability Across Systems

A grouping key can use multiple components:

```java
record ReportKey(
        String regionCode,
        String productCode,
        int fiscalYear
) {}
```

With a `record` containing immutable String and int fields, Java generates `equals/hashCode` across all three values. However, if one system uses region code `"VN-S"` while another uses `"vn-s"`, the record **does not automatically know** they are the same code. An agreed-upon normalization layer is required.

### 9.1. Using a Stable ID Instead of a Display Name

Do not group by a mutable customer name if you actually want to group by **the same customer across name changes**. A stable business ID is usually the right key:

```java
Map<Long, List<Order>> byCustomerId = orders.stream()
        .collect(Collectors.groupingBy(Order::customerId));
```

This is an illustrative example assuming an `Order` class with a `customerId()` accessor. If the ID is a nullable wrapper type, missing data must still be handled before returning the key. Do not confuse this with an `Order` record having a primitive `long customerId()`, which cannot be null but could still hold an invalid sentinel value such as `0` if the domain forbids it.

### 9.2. Map Ordering Is Not Key Stability

A `HashMap` can hold stable keys while having non-deterministic iteration order. A `LinkedHashMap` can preserve insertion order in a suitable pipeline. A `TreeMap` uses a comparator or the key's natural ordering to sort entries.

Distinguish between:

- **Key stability**: the same entity/group always produces equivalent keys.
- **Output order stability**: when printing or serializing the Map, groups appear in a deterministic order.

If a report requires alphabetical order, choose an appropriate comparator or sort the entries after grouping. Do not rely on `HashMap`'s arbitrary iteration order when verifying results.

### 9.3. Be Careful with TreeMap Comparators

With `TreeMap<K,V>`, whether two keys are considered duplicates for Map storage is determined by the **comparator** or natural ordering. If the comparator treats two keys that differ under `equals()` as equivalent, they may be merged into a single entry. To keep `Map` semantics and the grouping contract consistent, the comparator should be consistent with `equals` when required by the data.

For example, a comparator that only compares `region` and ignores `category` will merge `GroupKey` instances with the same region but different categories when using a `TreeMap`. If the goal is to group by **both components**, the comparator must inspect both in the chosen order.

If the key is `Optional<String>`, do not use `TreeMap` with default natural ordering because `Optional` is not `Comparable`; provide an explicit comparator or use `HashMap`/`LinkedHashMap`.

## 10. Handling null, blank, invalid, and Literal "unknown" Data

The following four cases are **not necessarily the same**:

| Input Value | Possible Meaning | Handling Decision Needed |
| --- | --- | --- |
| `null` | No value present | Group as missing, drop, or report error |
| `""` | Empty string provided | May be treated as missing or a validation error |
| `"   "` | Whitespace only | May be `strip`ped and treated as missing |
| `"unknown"` | A real String value | May be a valid category literally named unknown |

If you use the sentinel `"unknown"` for all missing data, records whose real category is `"unknown"` get merged in by mistake. Using `Optional.empty()` in the key avoids **colliding with real strings**, but if policy requires distinguishing null from blank, two separate states are still needed.

Some domains also require classifying **invalid** values separately (for example, codes containing forbidden characters). In that case, do not silently turn invalid values into missing: report an error, group them separately, or return an explicit status structure. The representation should support data quality and missing-information metrics.

### 10.1. Null Sale Elements

If the Stream contains a **null record**, calling `Sale::category` or `keyOf(sale)` will throw an NPE due to dereferencing null, independently of whether the category component can be null. `List.of(...)` does not accept null elements, but many other sources can contain them.

Choose a policy before grouping:

```java
Stream<Sale> input = ...; // illustrates a caller-provided source
Map<GroupKey, List<Sale>> grouped = input
        .filter(Objects::nonNull)
        .collect(Collectors.groupingBy(
                StableGroupingKeyDemo::keyOf));
```

The snippet above is **illustrative only** and requires importing `Objects`. If a null record is a serious data error, validate and fail rather than filtering silently. Distinguish a **null element** from a **null field on a non-null object**.

### 10.2. A Missing Key Must Still Be a Valid Object

`Optional.empty()` is an object representing the absence of a value. `new GroupKey(Optional.empty(), Optional.empty())` is also a valid key object. However, `GroupKey key = null` is **invalid** as the classifier return value for `groupingBy`. Do not assume that using Optional allows returning a null key object.

### 10.3. Null Elements in Downstream Lists

`Collectors.toList()` may collect null elements in some cases, but that does not permit the classifier to return null. These are two separate data paths:

- Classifier key: `groupingBy` requires it to be **non-null**.
- Downstream value: depending on the collector/collection type and mapping, different null rules may apply.

If you need an output List without nulls, validate and design the downstream/pipeline accordingly.

## 11. Parallel Processing and Associativity

### 11.1. groupingByConcurrent Does Not Fix Key Design Bugs

`Collectors.groupingByConcurrent` creates a Collector for concurrent grouping according to its contract, but the classifier must still return a non-null key. It does not normalize text, fix a key's `equals/hashCode`, or turn a mutable key into an immutable one.

If **output order stability** is required, `groupingByConcurrent` is usually not the first choice; results may not preserve encounter order like a sequential pipeline using `LinkedHashMap`. Measure and design based on ordering, performance, and correctness requirements.

### 11.2. Keys Must Remain Stable When Maps Are Split and Merged

In a parallel stream, the framework may create multiple intermediate Maps and merge them. If a classifier produces keys whose `equals/hashCode` rely on mutable state, two records in the same group may produce non-equivalent keys across branches or become unfindable after merging.

Using immutable value keys with a **pure** normalization function (modifying no external state) makes results predictable. A classifier that reads a clock, a mutable counter, or calls a service whose result changes per call does not represent a stable group.

### 11.3. Do Not Mutate Keys or the Source Collection During Traversal

An example of flawed design:

```java
// Avoid: classifier mutates Sale or external data
// to determine the key during grouping.
sales.parallelStream().collect(Collectors.groupingBy(s -> {
    mutateSale(s);
    return keyOf(s);
}));
```

This is an **anti-pattern illustration**: `mutateSale` would be application-defined, not a recommendation to implement. Side effects can cause data races or order-dependent behavior. Instead, normalize from the input data and return an immutable key without mutating the record.

## 12. Testing Key-Based Grouping Design

### 12.1. Testing Data Equivalence

With case-insensitive and whitespace-trimming rules:

```java
GroupKey a = keyOf(new Sale("North", "Food", "A", 1));
GroupKey b = keyOf(new Sale(" north ", "food", "B", 1));

System.out.println(a.equals(b)); // true
System.out.println(a.hashCode() == b.hashCode()); // true
```

This is an illustrative snippet using `GroupKey` and `Sale` from the program. If `a.equals(b) == true` but `hashCode()` differs, the key class violates the HashMap/Map contract. A record with immutable String/Optional components handles the comparison implementation properly, provided the components are normalized consistently.

### 12.2. Testing Missing Data and Sentinel Collisions

Create two records:

- `category = null`.
- `category = "__MISSING_CATEGORY__"`.

If using a String sentinel as shown earlier, they can be merged erroneously. If using `Optional.empty()` and `Optional.of("__missing_category__")` after normalization, they are **two distinct keys**. This is an important test when external data may supply unexpected values.

### 12.3. Testing Total Record Count Before and After Grouping

For `groupingBy` without filtering elements, the total number of elements across all group lists must equal the number of input elements:

```java
long groupedCount = groups.values().stream()
        .mapToLong(List::size)
        .sum();
```

If `groups` is `Map<K,List<Sale>>` or `Map<K,List<String>>` and every element is placed in exactly one group, `groupedCount` must equal the original element count. If you chose `filter` to drop missing data, add the dropped record count to account for the difference.

### 12.4. Testing Ordering When Required by Reports

If an API documents group ordering, choose the appropriate Map factory/comparator and test it explicitly. If the API does **not** document ordering, verify only contents and counts without assuming HashMap iteration order.

### 12.5. Testing with Large Sources and Multiple Threads

If data needs to run in parallel, compute the same result using both sequential and parallel pipelines with associative aggregations such as `counting`/`summingInt` within a safe numeric range. Compare **Map contents** rather than print order. If discrepancies appear, check normalization functions for stateful dependencies, mutable keys, non-compliant collectors, or numeric overflow before blaming the runtime.

## 13. Quick Decision Table

| Requirement | Key Design | Handling Strategy |
| --- | --- | --- |
| Group by case-sensitive technical category code | `String` preserving original contract | `groupingBy(Sale::category)` when guaranteed non-null |
| Group by case-insensitive code | Consistently normalized `String` | `groupingBy(s -> normalizeRequired(...))` |
| Group by multiple attributes | `record CompositeKey(...)` | `groupingBy(this::keyOf)` |
| Treat null/blank as a separate group | `Optional<String>` or state key | Classifier always returns a non-null object |
| Need to distinguish null, blank, and invalid | Multi-branch status type | Do not share a single sentinel |
| Need only two groups by a condition | `Boolean` | `partitioningBy(predicate)` |
| Need only the count per group | Immutable key + `counting()` | Avoid collecting full Lists |
| Need sum of a numeric attribute per group | Immutable key + `summingInt/Long` | Check numeric range |
| Need to iterate groups in first-seen order | Stable key + `LinkedHashMap::new` | Prefer an ordered sequential pipeline |
| Need Map sorted by key | Compatible key/comparator | Use `TreeMap` with a complete comparator |
| Want parallel grouping | Immutable key + suitable collector | Do not rely on callback order |
| Source may contain null records | Check before classifier | Skip or fail per business policy |

**Rule of thumb:** decide the **definition of "same group"** first, then choose the collector. The API enforces the chosen contract; it does not infer business definitions from raw data.

## 14. Common Pitfalls

1. **Classifier returning `null`:** `Collectors.groupingBy` throws `NullPointerException`, even though `HashMap` allows null keys.
2. **Using `"unknown"` arbitrarily as a sentinel:** may collide with a valid `"unknown"` value.
3. **Inconsistent normalization:** `"Food"`, `"food"`, and `" Food "` become three groups even when the domain treats them as one.
4. **Over-normalization:** merging distinct codes that business logic needs to keep separate.
5. **Using a mutable entity as a key:** modifying fields used in `equals/hashCode` prevents the Map from finding the entry again.
6. **Overriding equals without hashCode:** violates the contract of hash-based Maps.
7. **Using a TreeMap comparator that omits components:** merges keys that are unequal under `equals` into a single entry.
8. **Relying on HashMap iteration order:** reports or tests may vary across environments.
9. **Assuming groupingByConcurrent allows null keys:** it does not; missing keys must be handled explicitly.
10. **Dropping missing records without accounting for them:** total reported record count decreases with no explanation.
11. **Conflating null records with null fields:** separate validation boundaries are required.
12. **Confusing key normalization with mutating original data:** keep raw values when auditing is needed.
13. **Forgetting composite keys:** grouping by a single component can lose an important analytical dimension.
14. **Assuming grouped Lists are mutable:** the specific collector determines the contract.
15. **Using a classifier with side effects:** leads to unpredictable behavior in parallel Streams or when reprocessing data.
16. **Not testing missing/blank/invalid keys separately:** data quality bugs can hide inside a seemingly valid group.

## 15. Practice Exercises

**Exercise 1.** Given categories `"Food"`, `" food "`, and `"FOOD"`, write a classifier that groups them into one group when the domain treats all three strings as the same code. Why should `Locale.ROOT` be used?

**Exercise 2.** Given a `List<Sale>` where one element has `category() == null`, why does `groupingBy(Sale::category)` throw an NPE even though `HashMap` supports null keys?

**Exercise 3.** Design an `Optional<String>` key to distinguish a missing category from a string whose value is `"unknown"`. Show the `equals` result between those two keys.

**Exercise 4.** Write a `record GroupKey(String region, String category)`. When grouping by region and category, which components does the record's `equals` examine?

**Exercise 5.** A key class has a mutable field that participates in `hashCode`. What can happen if the object is already in a `HashMap` and that field changes?

**Exercise 6.** Use `Collectors.groupingBy` with `Collectors.counting()` to create a `Map<K,Long>` counting elements per key. Why is collecting a `List` unnecessary?

**Exercise 7.** Use `Collectors.groupingBy` with `Collectors.summingInt(...)` to get units sold per region/category. If the total may exceed `int`, which type should you choose?

**Exercise 8.** Given `Sale` with region and category where category may be missing, use `partitioningBy` to split into "missing category" and "present category." Compare this with grouping by a two-component `GroupKey`.

**Exercise 9.** You want to output a group report in first-encountered order. Which `groupingBy` overload lets you choose `LinkedHashMap::new`? Why must you still consider whether the source is ordered?

**Exercise 10.** Using a composite record key with `Optional<String>`, write two records that produce the same normalized key and verify `equals` and `hashCode`.

**Exercise 11.** A `TreeMap` comparator only inspects region, even though the key actually contains both region and category. What can happen when two records have the same region but different categories?

**Exercise 12.** A report has 100 records, 7 of which have a null category. If the pipeline filters out nulls before `groupingBy`, what is the sum of all group List sizes? Why must the 7 dropped records be noted?

**Exercise 13.** Given `Map<GroupKey,List<Sale>>`, write a pipeline that computes the total number of elements across all groups to reconcile against the original record count.

**Exercise 14.** Name two bugs that can still occur when switching from `groupingBy` to `groupingByConcurrent` if the key is mutable and the classifier returns null.

### Answer Hints

1. `s -> s.strip().toLowerCase(Locale.ROOT)` with a non-null precondition; `Locale.ROOT` avoids default-locale dependence when normalizing codes.
2. `groupingBy` requires a non-null classifier return value; this is independent of whether a specific Map implementation allows null keys.
3. `Optional.empty()` differs from `Optional.of("unknown")`; there is no sentinel collision.
4. Both `region` and `category` participate in the record's value-based comparison.
5. `get/containsKey` may fail to find the key and grouping loses stability; create immutable keys instead.
6. `groupingBy(keyOf, counting())` returns a Map holding counts without storing all objects.
7. `summingLong(...)`, or a larger numeric type / overflow check according to business bounds.
8. `partitioningBy` produces only two branches; `GroupKey` still separates by region and category.
9. `groupingBy(classifier, LinkedHashMap::new, downstream)`; insertion order is well-defined when the source is sequential and ordered.
10. `keyOf(new Sale("North","Food",...))` and `keyOf(new Sale(" north ","food",...))` have `equals == true` and equal `hashCode`.
11. `TreeMap` may treat the two keys as equivalent under the comparator and merge them into one entry, failing to reflect two-dimensional grouping.
12. 93 if each remaining element is grouped once; the 7 missing records should be explained in the data-quality report.
13. `groups.values().stream().mapToLong(List::size).sum()`.
14. Mutable keys break `equals/hashCode` stability; a null-returning classifier still throws NPE, and concurrent execution does not fix either issue.

## Conclusion

**Good grouping key design is a prerequisite for `Collectors.groupingBy` to produce accurate results.** A key must express the exact definition of "same group," have stable `equals/hashCode`, and remain unchanged while stored in the Map. Normalization rules must be defined by the domain rather than arbitrarily discarding meaningful distinctions.

When a key or key component may be missing, **never return `null` directly from the `groupingBy` classifier**. Instead, use a valid key state such as `Optional.empty()`, a dedicated type, or a guaranteed non-colliding sentinel; or filter out records under a transparent policy. Then choose the downstream collector, Map factory, and execution mode to match the reporting goal. This keeps data grouping accurate, testable, and resilient as the application evolves.
