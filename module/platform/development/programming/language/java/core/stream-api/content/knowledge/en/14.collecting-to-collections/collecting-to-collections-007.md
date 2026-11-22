# Using toUnmodifiableList and toUnmodifiableSet

## 1. Why Collect into an Unmodifiable Collection?

In the **Java Stream API**, `filter`, `map`, and other intermediate operations describe a data processing pipeline declaratively. Only at the terminal operation `collect` is the data gathered into a result such as a `List`, `Set`, or `Map`.

Some results serve as **reference lists**, **valid code sets**, or **return values from a service layer**. If receiving code can freely add or remove elements, business rules are easily broken. The following two collectors express that **the structure of the resulting Collection cannot be modified**:

- `Collectors.toUnmodifiableList()`: creates an unmodifiable list, **retaining duplicate elements** and preserving encounter order if the Stream is ordered.
- `Collectors.toUnmodifiableSet()`: creates an unmodifiable set, **removing duplicate elements per `equals`/`hashCode`**, with no guarantee on iteration order.

Example:

```java
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

List<String> codes = List.of("A", "B", "A", "C");

List<String> asList = codes.stream()
        .collect(Collectors.toUnmodifiableList());

Set<String> asSet = codes.stream()
        .collect(Collectors.toUnmodifiableSet());

System.out.println(asList);       // [A, B, A, C]
System.out.println(asSet.size()); // 3
```

`asList` keeps all four elements in order; `asSet` holds only the three distinct values `A`, `B`, `C`. Both reject operations such as `add`, `remove`, or `clear`.

This lesson belongs to the **Collecting into Collections** chapter. After studying it, you will be able to choose the right collector based on ordering and duplicate requirements; handle `null` before collecting; distinguish unmodifiable results from deep immutability; and use these collectors in sequential, parallel, and business-reporting pipelines.

**Java version:** both `Collectors.toUnmodifiableList()` and `Collectors.toUnmodifiableSet()` have been available since **Java 10**. Complete examples in this lesson use Java 17+ for `record` and `Stream.toList()`. Java 17 is not required if you only use the two collectors above.

## 2. Return Types and Role in collect

The two methods in `java.util.stream.Collectors` have the signatures:

```java
public static <T> Collector<T, ?, List<T>> toUnmodifiableList()

public static <T> Collector<T, ?, Set<T>> toUnmodifiableSet()
```

The type arguments `Collector<T, A, R>` describe how each element `T` is accumulated into an intermediate state `A` to produce a result `R`. In both signatures above, the accumulation state is hidden by `?`, and the results are `List<T>` and `Set<T>`, respectively.

Used via the terminal operation `collect(Collector)`:

```java
List<String> labels = List.of("  Java  ", "Stream", "Java")
        .stream()
        .map(String::strip)
        .collect(Collectors.toUnmodifiableList());

Set<String> distinctLabels = List.of("  Java  ", "Stream", "Java")
        .stream()
        .map(String::strip)
        .collect(Collectors.toUnmodifiableSet());
```

The pipeline follows this flow:

```text
Stream<T> source
     |
 filter / map             Lazy intermediate operations
     |
 collect(...)             Terminal operation
     |
 +--------------------+-----------------------+
 |                    |                       |
 toUnmodifiableList() |                toUnmodifiableSet()
 |                    |                       |
 List<T>              |                    Set<T>
 keeps dups + order   |              deduplicates, no order promise
 unmodifiable struct  |              unmodifiable struct
 +--------------------+-----------------------+
```

`collect` **triggers traversal of the Stream**. Once the terminal operation finishes, that Stream cannot be reused; if you need both a List result and a Set result from the same source, create two separate pipelines or design a combined collection when a single pass is truly necessary.

## 3. toUnmodifiableList: Preserving Order and Duplicates

When data represents a **sequence of steps**, a **transaction log**, or an **occurrence history**, repeated elements can carry meaning. `toUnmodifiableList` retains those elements.

```java
List<String> events = List.of("LOGIN", "VIEW", "VIEW", "LOGOUT");

List<String> history = events.stream()
        .filter(event -> !event.isBlank())
        .collect(Collectors.toUnmodifiableList());

System.out.println(history); // [LOGIN, VIEW, VIEW, LOGOUT]
```

For a Stream with an **encounter order** such as `List.stream()`, the resulting List preserves the element encounter order. If the source is unordered, such as certain `Set`s or a pipeline calling `unordered()`, this collector cannot infer business ordering and guarantees no meaningful order.

### Cannot Modify the Structure of the Collected List

```java
List<Integer> scores = List.of(8, 9, 7)
        .stream()
        .collect(Collectors.toUnmodifiableList());

// Each operation below throws UnsupportedOperationException.
// scores.add(10);
// scores.remove(0);
// scores.set(0, 10);
// scores.clear();
```

However, **reading data** works normally: `scores.size()`, `scores.get(0)`, `scores.stream()`, and loop iteration remain valid.

A distinction to keep in mind is that an unmodifiable result does not mean every object inside it is immutable. If the List holds a mutable object, code can still call methods that change that object's state. Section 8 illustrates this clearly.

### Does the New List Depend on Source Mutations?

```java
List<String> mutableSource =
        new java.util.ArrayList<>(List.of("A", "B"));

List<String> locked = mutableSource.stream()
        .collect(Collectors.toUnmodifiableList());

mutableSource.add("C");
System.out.println(mutableSource); // [A, B, C]
System.out.println(locked);        // [A, B]
```

The `locked` result has already been collected; it is not a live view tied to the source Collection. **Element object references** can still be shared if elements are of mutable types.

## 4. toUnmodifiableSet: Ensuring Uniqueness by equals/hashCode

If data needs to represent a **set of unique codes**, **granted roles**, or **enabled feature flags**, a `Set` fits better than a list that allows duplicates.

```java
List<String> permissions = List.of(
        "READ", "WRITE", "READ", "EXPORT", "WRITE"
);

Set<String> uniquePermissions = permissions.stream()
        .collect(Collectors.toUnmodifiableSet());

System.out.println(uniquePermissions.size());         // 3
System.out.println(uniquePermissions.contains("READ")); // true
```

Do not rely on `System.out.println(uniquePermissions)` having the same order as the source. `toUnmodifiableSet` does not promise to preserve encounter order, so the example checks **size and element membership**.

### By Which Rule Are Duplicates Determined?

A Set uses element equality semantics: for ordinary object types, that means `equals` and `hashCode`. For `String`, two strings with identical contents are equal.

For custom types, two objects with different references can still be considered duplicates if they have matching equality rules. For example, a `record` automatically generates `equals`/`hashCode` based on its components:

```java
record Tag(String code, String label) {}

List<Tag> input = List.of(
        new Tag("T1", "Java"),
        new Tag("T1", "Java"),
        new Tag("T1", "Programming")
);

Set<Tag> tags = input.stream()
        .collect(Collectors.toUnmodifiableSet());

System.out.println(tags.size()); // 2
```

The first two entries are equal and therefore deduplicated; the third entry has a different `label`, so it remains a distinct element. If business rules define "duplicate" **by `code` alone**, you must normalize or choose the comparison key before collecting. `toUnmodifiableSet` does not take a custom comparator or key-extractor function.

### Which Element Is Kept When Objects Are Equal?

When elements are **equal under `equals`** yet are distinct object instances, the API allows retaining **any** element from the duplicate group. Do not rely on keeping "the first instance" or "the last instance", especially in a parallel pipeline.

When you need to pick the latest record by ID or prefer data with the best status, express the selection rule using `toMap` with a merge function, `groupingBy`, or a dedicated processing step, and only then produce an unmodifiable output.

## 5. How Do toUnmodifiableList and toUnmodifiableSet Differ?

| Property | `toUnmodifiableList()` | `toUnmodifiableSet()` |
| --- | --- | --- |
| Result type | `List<T>` | `Set<T>` |
| Retains duplicates | Yes | No |
| Encounter order | Preserved when Stream is ordered | Not promised |
| Indexed access | Yes, via `get(index)` | No indices |
| Membership check | `contains` supported | `contains` supported; fits set semantics |
| Allows `null` | No | No |
| Allows `add`/`remove`/`clear` | No | No |
| Guarantees deep immutability of inner elements | No | No |
| Guarantees concrete implementation type | No | No |

Both collectors produce **unmodifiable** results, yet neither promises a concrete implementation class like `ArrayList`, `HashSet`, or `LinkedHashSet`, nor serializability (`Serializable`). To keep code independent of implementations, program against the `List` or `Set` interface.

If you need **both order and uniqueness at the same time**, process on an ordered Stream before collecting into a List:

```java
List<String> orderedUnique = List.of("A", "B", "A", "C")
        .stream()
        .distinct()
        .collect(Collectors.toUnmodifiableList());

System.out.println(orderedUnique); // [A, B, C]
```

On an **ordered** Stream, `distinct()` keeps the first occurrence of each equal value. The resulting list preserves the chosen order. If you specifically need a Set whose iteration order is guaranteed by the Collection's design, `LinkedHashSet` is suitable; you can lock mutations after collection as shown in section 7.

## 6. Policy on null: Both Collectors Reject It

This is a critical difference from some other Collection-collecting approaches: **`toUnmodifiableList` and `toUnmodifiableSet` do not accept `null` elements**. If the Stream contains a `null` element, the terminal operation fails with `NullPointerException`.

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<String> data = Arrays.asList("A", null, "B");

// WRONG: expecting the result to contain null.
// List<String> invalid = data.stream()
//         .collect(Collectors.toUnmodifiableList());
// Throws NullPointerException.
```

The same applies to `toUnmodifiableSet`. Before collecting, decide whether `null` is invalid data, an element to skip, or a missing value to replace.

### Skipping null Elements

```java
import java.util.Objects;

List<String> nonNull = data.stream()
        .filter(Objects::nonNull)
        .collect(Collectors.toUnmodifiableList());

System.out.println(nonNull); // [A, B]
```

### Replacing null with an Explicit Value

```java
List<String> normalized = data.stream()
        .map(value -> value == null ? "UNKNOWN" : value)
        .collect(Collectors.toUnmodifiableSet());

System.out.println(normalized.contains("UNKNOWN")); // true
```

For mandatory data, replacing `null` with `"UNKNOWN"` can mask bugs. Validate and report errors before running the pipeline if business rules require it.

### Distinction from Stream.toList()

`Stream.toList()` (Java 16+) also returns an **unmodifiable List**. However, the two APIs do not share the exact same contract: `Collectors.toUnmodifiableList()` explicitly **rejects `null`**, whereas `Stream.toList()` on current JDKs allows the result to contain `null`.

```java
List<String> maybeNull = java.util.Arrays.asList("A", null).stream()
        .toList(); // May contain null; output is still unmodifiable.
```

If you want to guarantee data contains no `null`, do not just switch terminal operations and hope. Express the policy explicitly with validation, filtering, or a collector with a clear `null` constraint.

## 7. Comparison with Other Collection-Collecting Methods

The word "List" or "Set" in a collector's name is **not enough to conclude result mutability**.

| Collection method | Result | Mutability guarantee |
| --- | --- | --- |
| `collect(Collectors.toUnmodifiableList())` | `List<T>`, keeps duplicates, keeps encounter order | **Unmodifiable** |
| `collect(Collectors.toUnmodifiableSet())` | `Set<T>`, deduplicates | **Unmodifiable** |
| `stream.toList()` | `List<T>`, keeps encounter order | **Unmodifiable**, Java 16+ |
| `collect(Collectors.toList())` | `List<T>` | **No guarantee** of implementation type or mutability |
| `collect(Collectors.toSet())` | `Set<T>` | **No guarantee** of implementation type, mutability, or order |
| `collect(Collectors.toCollection(ArrayList::new))` | `ArrayList<T>` | Can add/remove elements |
| `collect(Collectors.toCollection(LinkedHashSet::new))` | `LinkedHashSet<T>` | Modifiable; iterates in insertion order |
| `List.copyOf(collection)` / `Set.copyOf(collection)` | Unmodifiable copy | Java 10+; rejects `null` |

If you intentionally need a mutable list, request the Collection type directly:

```java
List<String> editable = List.of("A", "B").stream()
        .collect(Collectors.toCollection(java.util.ArrayList::new));

editable.add("C"); // Valid.
```

If you need a **Set preserving insertion order** and want to prevent downstream code from modifying it:

```java
import java.util.Collections;
import java.util.LinkedHashSet;

Set<String> orderedUnique = List.of("A", "B", "A", "C").stream()
        .collect(Collectors.collectingAndThen(
                Collectors.toCollection(LinkedHashSet::new),
                Collections::unmodifiableSet
        ));

System.out.println(orderedUnique); // [A, B, C] in insertion order.
```

`Collections.unmodifiableSet` creates a **view that disallows modification through that view** over the passed Set. If a reference to the original Set remains, mutations via that reference still show up in the view. In the pipeline above, the intermediate Set is created internally and never exposed elsewhere, so this pattern achieves the goal of preventing callers from modifying the structure.

By contrast, `toUnmodifiableSet` directly expresses collecting into an unmodifiable Set, though it **does not promise order**. Prefer the simpler approach when ordering has no business significance.

### Difference Between Set.of and Collecting into a Set

`Set.of("A", "A")` throws `IllegalArgumentException` because the passed elements are duplicates. `Collectors.toUnmodifiableSet()` **deduplicates** during collection and does not throw an error simply because equal elements exist.

`Set.copyOf(collection)` also creates an unmodifiable Set and handles duplicates according to set rules. If duplicates should be treated as a data error, check for duplicates separately rather than relying on `toUnmodifiableSet`.

## 8. Unmodifiable Does Not Mean Deeply Immutable

Results from these two collectors forbid **modifying the Collection structure**; they **do not automatically deep-copy** mutable objects stored inside.

```java
StringBuilder mutableText = new StringBuilder("draft");

List<StringBuilder> locked = java.util.stream.Stream.of(mutableText)
        .collect(Collectors.toUnmodifiableList());

// locked.add(new StringBuilder("new")); // UnsupportedOperationException
mutableText.append("-updated");

System.out.println(locked.get(0)); // draft-updated
```

Similarly, if a Set holds mutable objects whose `equals` or `hashCode` depends on a mutable field, changing that field after insertion into the Set can cause `contains` and lookups to behave unexpectedly.

To create more stable return data, **map elements to immutable values** before collecting:

```java
List<StringBuilder> builders = List.of(
        new StringBuilder("A"),
        new StringBuilder("B")
);

List<String> stableText = builders.stream()
        .map(StringBuilder::toString)
        .collect(Collectors.toUnmodifiableList());

builders.get(0).append("-changed");
System.out.println(stableText); // [A, B]
```

For nested structures, transform each inner Collection if you want to prevent inner mutations as well. For example, `List<List<String>>` only prevents modifying the outer List while inner Lists remain mutable. You can lock both levels explicitly:

```java
List<List<String>> nested = List.of(
        new java.util.ArrayList<>(List.of("A")),
        new java.util.ArrayList<>(List.of("B"))
);

List<List<String>> deeplyLockedForStrings = nested.stream()
        .map(List::copyOf)
        .collect(Collectors.toUnmodifiableList());
```

This example locks both List layers; `String` itself is an immutable type. If elements are mutable business objects, `List.copyOf` still does not deep-copy those objects.

## 9. Preprocessing Before Collecting: filter, map, and distinct

The two collectors only decide **how the final result is stored**. Rules for selecting and normalizing data should be expressed in the pipeline.

```java
import java.util.Locale;

List<String> input = List.of("  Admin", "admin ", "Reader", "reader", " ");

Set<String> roles = input.stream()
        .map(String::strip)
        .filter(text -> !text.isEmpty())
        .map(text -> text.toUpperCase(Locale.ROOT))
        .collect(Collectors.toUnmodifiableSet());

System.out.println(roles.size());          // 2
System.out.println(roles.contains("ADMIN")); // true
System.out.println(roles.contains("READER")); // true
```

Order inside the Set is not guaranteed. If you want to **preserve the history of normalized codes**, use a List:

```java
List<String> normalizedHistory = input.stream()
        .map(String::strip)
        .filter(text -> !text.isEmpty())
        .map(text -> text.toUpperCase(Locale.ROOT))
        .collect(Collectors.toUnmodifiableList());

System.out.println(normalizedHistory);
// [ADMIN, ADMIN, READER, READER]
```

You do not need `distinct()` before `toUnmodifiableSet()` just to ensure the Set has no duplicates: the Set already enforces that constraint. `distinct()` can be useful if you want to deduplicate **before running an expensive transformation step**; evaluate ordering, cost, and pipeline semantics.

### Want to Select Objects by Key Instead of equals?

`toUnmodifiableSet` does not replace `groupingBy` or `toMap` when business rules define "unique by code" while objects carry multiple fields:

```java
record Product(String sku, String name) {}

List<Product> products = List.of(
        new Product("P01", "Blue pen"),
        new Product("P01", "Ballpoint pen"),
        new Product("P02", "Notebook")
);

Set<Product> set = products.stream()
        .collect(Collectors.toUnmodifiableSet());

System.out.println(set.size()); // 3: the two P01 Products differ in name.
```

If you only need the set of product codes, map to `sku` before collecting:

```java
Set<String> distinctSkus = products.stream()
        .map(Product::sku)
        .collect(Collectors.toUnmodifiableSet());

System.out.println(distinctSkus.size()); // 2
```

If you need to keep **one complete Product per SKU**, explicitly define how to resolve duplicate codes, such as using `Collectors.toMap(Product::sku, Function.identity(), mergeFunction)` and then converting the result to an unmodifiable form. Do not rely on Set to guess a uniqueness criterion absent from `equals`/`hashCode`.

## 10. Ordered Sources, Parallel Execution, and Predictability

### With Ordered Streams

`List.stream()` has an encounter order. `toUnmodifiableList` preserves that order:

```java
List<Integer> numbers = List.of(5, 1, 4, 1, 3);

List<Integer> sequential = numbers.stream()
        .collect(Collectors.toUnmodifiableList());

List<Integer> parallel = numbers.parallelStream()
        .collect(Collectors.toUnmodifiableList());

System.out.println(sequential); // [5, 1, 4, 1, 3]
System.out.println(parallel);   // [5, 1, 4, 1, 3]
```

Lambda **execution order** may differ across threads, but the result of a contract-compliant collection from an ordered source still preserves encounter order.

### With Sets That Have No Promised Order

`toUnmodifiableSet` guarantees a set of unique elements, **not presentation order** in sequential or parallel runs. When two objects are equal, do not rely on which object is retained.

Therefore, if the system needs a stably ordered display list, sort by a specific criterion and collect into a List:

```java
List<Integer> sortedUnique = numbers.parallelStream()
        .distinct()
        .sorted()
        .collect(Collectors.toUnmodifiableList());

System.out.println(sortedUnique); // [1, 3, 4, 5]
```

### On Performance and Memory

Both collectors are terminal operations that must **store the entire result** in a Collection. They do not replace `count`, `sum`, or `reduce` when only an aggregate number is needed. For very large sources, check result memory usage, deduplication cost, and unbounded data scenarios.

`parallelStream()` is not faster by default: splitting the source, collecting partial results, and merging them can cost more than the benefit of concurrent execution, especially when data is small or logic is lightweight.

Keep `filter` and `map` lambdas **stateless and non-interfering**: do not add/remove elements on the source being traversed or write to an external shared Collection. Let the Stream and collector manage partial results.

## 11. Complete Example: Course List and Skill Set

Suppose a learning system stores enrollment records. Two result forms are needed for a dashboard:

1. **Course history** of active enrollments: keep order and keep duplicate entries.
2. **Active skill set**: keep only unique skill codes to quickly check whether a skill appears.

Runnable example on **Java 17+**:

```java
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.stream.Collectors;

public class UnmodifiableCollectionsDemo {
    record Enrollment(
            String studentId,
            String course,
            String skill,
            boolean active
    ) {}

    public static void main(String[] args) {
        List<Enrollment> enrollments = List.of(
                new Enrollment("S01", "Java Core", "JAVA", true),
                new Enrollment("S02", "Java Stream", " STREAM ", true),
                new Enrollment("S01", "Java Stream", "STREAM", true),
                new Enrollment("S03", "SQL", "SQL", false),
                new Enrollment("S04", "Java Core", "JAVA", true)
        );

        List<String> activeCourses = enrollments.stream()
                .filter(Enrollment::active)
                .map(Enrollment::course)
                .collect(Collectors.toUnmodifiableList());

        Set<String> activeSkills = enrollments.stream()
                .filter(Enrollment::active)
                .map(Enrollment::skill)
                .map(String::strip)
                .map(skill -> skill.toUpperCase(Locale.ROOT))
                .collect(Collectors.toUnmodifiableSet());

        System.out.println(activeCourses);
        // [Java Core, Java Stream, Java Stream, Java Core]

        System.out.println(activeSkills.size());          // 2
        System.out.println(activeSkills.contains("JAVA"));  // true
        System.out.println(activeSkills.contains("STREAM")); // true
        System.out.println(activeSkills.contains("SQL"));   // false

        // Structural modification operations on the result are rejected.
        try {
            activeCourses.add("New Course");
        } catch (UnsupportedOperationException exception) {
            System.out.println("Cannot modify course list");
        }

        try {
            activeSkills.remove("JAVA");
        } catch (UnsupportedOperationException exception) {
            System.out.println("Cannot modify skill set");
        }
    }
}
```

Explanation:

1. `filter(Enrollment::active)` removes inactive enrollments before collecting.
2. `toUnmodifiableList` retains both `Java Stream` entries and both `Java Core` entries, because this is a **history** rather than a unique catalog.
3. `toUnmodifiableSet` normalizes skill codes and deduplicates them; whitespace around `" STREAM "` does not create a separate skill.
4. Both results forbid direct add/remove operations; consuming code cannot accidentally alter the published permission/catalog set.
5. Each `enrollments.stream()` creates a fresh pipeline. The original source is never modified.

Because the example uses `String` and `record` with data containing no mutable inner Collections, the output is sufficiently stable for the demonstrated values. If mutable objects are included, design appropriate mappings or defensive copies before collecting.

## 12. Common Mistakes

| Symptom | Cause | How to handle |
| --- | --- | --- |
| `UnsupportedOperationException` on `add`/`remove` | Results from `toUnmodifiableList` or `toUnmodifiableSet` are unmodifiable | If modification is truly needed, use `toCollection(ArrayList::new)` or `toCollection(HashSet::new)` |
| `NullPointerException` in terminal operation | Stream contains `null` elements | Define a policy; filter or transform `null` before `collect` |
| List still has duplicate elements | `toUnmodifiableList` does not deduplicate | Use `distinct` or `toUnmodifiableSet` if appropriate |
| Set size is smaller than expected | Set removes elements equal per `equals`/`hashCode` | Check normalization and equality criteria |
| Set order differs across runs | Collector makes no ordering guarantee | Use `distinct().sorted().collect(Collectors.toUnmodifiableList())` or an explicitly ordered Set |
| Records with duplicate codes still coexist in Set | `equals` compares fields beyond the code | Map to the code or use a Map with a merge policy |
| "Locked" Collection still has changing inner data | Elements are mutable objects | Create immutable copies/DTOs before collecting |
| `Collectors.toList()` assumed to be definitely mutable | API does not promise mutability | Use `toCollection(ArrayList::new)` when mutability is required |
| `Stream.toList()` treated as fully equivalent to `toUnmodifiableList()` | Differences in `null` contract and Java version | Explicitly choose the terminal operation and data rules |
| Parallel pipeline produces unstable Set order | Order is ignored for Set results | Compare Set contents, not print order |

## 13. Practice Exercises and Solutions

Given a list of raw data:

```java
List<String> rawCodes = List.of(
        " admin ", "reader", "ADMIN", "", " reader ", "export"
);
```

**Requirements:**

1. Normalize the codes with `strip()` and `toUpperCase(Locale.ROOT)`; discard blank codes.
2. Collect into an unmodifiable `List<String>` retaining duplicates.
3. Collect into an unmodifiable `Set<String>` keeping only unique codes.
4. If you want a **unique list preserving first-appearance order**, which operations should you combine?
5. Try adding `null` to the source using `Arrays.asList`, and predict the result when calling both collectors without filtering `null`.

**Reference solution:**

```java
List<String> normalizedList = rawCodes.stream()
        .map(String::strip)
        .filter(code -> !code.isEmpty())
        .map(code -> code.toUpperCase(Locale.ROOT))
        .collect(Collectors.toUnmodifiableList());

System.out.println(normalizedList);
// [ADMIN, READER, ADMIN, READER, EXPORT]

Set<String> normalizedSet = rawCodes.stream()
        .map(String::strip)
        .filter(code -> !code.isEmpty())
        .map(code -> code.toUpperCase(Locale.ROOT))
        .collect(Collectors.toUnmodifiableSet());

System.out.println(normalizedSet.size()); // 3

List<String> uniqueInEncounterOrder = rawCodes.stream()
        .map(String::strip)
        .filter(code -> !code.isEmpty())
        .map(code -> code.toUpperCase(Locale.ROOT))
        .distinct()
        .collect(Collectors.toUnmodifiableList());

System.out.println(uniqueInEncounterOrder);
// [ADMIN, READER, EXPORT]
```

For question 5, `Arrays.asList("admin", null, "reader")` creates a List containing `null`. If a mapper calls `String::strip` on `null`, the failure occurs **before** `collect`. If `null` reaches either collector untouched, both will also reject `null` with `NullPointerException`. To skip it, place `filter(Objects::nonNull)` **before** mappers that do not accept `null`.

**Follow-up question:** Suppose two `Product`s share the same SKU with different prices, and business logic requires selecting the record with the most recent update timestamp. Does `toUnmodifiableSet` have enough information to decide? Consider `toMap` with a timestamp-based merge function and then converting to an unmodifiable Collection. Be sure to define a clear tie-breaking rule when two update timestamps are equal.

## Key Takeaways

`Collectors.toUnmodifiableList()` and `Collectors.toUnmodifiableSet()` both create **structurally unmodifiable Collections** from a Stream. Choose **List** when order is needed and duplicates should be kept; choose **Set** when uniqueness per `equals`/`hashCode` is needed without ordering. Both collectors reject `null`, guarantee no concrete implementation class, and do not automatically make inner mutable objects deeply immutable.

Normalize, filter, and validate data before `collect`. If unique elements in order are needed, use `distinct` on an ordered Stream and collect into a List, or choose a Set structure with its own ordering contract. With parallel pipelines, evaluate result contents per the List/Set contract rather than lambda invocation order or merge timing. Only use more complex solutions when business requirements genuinely call for them.
