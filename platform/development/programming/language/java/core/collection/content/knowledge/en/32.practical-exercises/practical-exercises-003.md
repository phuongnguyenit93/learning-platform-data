# Frequency Counting and Grouping Data with Map

Real-world problems often require more than just storing a list; they also need to answer questions such as: **how many times** a value appears, which records belong to the **same group**, or **how many orders** are associated with each customer ID. `Map<K,V>` is the appropriate model because it maps a **key K** to **a value V**. That value can be a count, a list, a set, or another result structure.

The key design points to settle before writing code are *what the key represents*, *how two keys are considered equal*, *whether ordering must be preserved*, and *whether the grouped value should retain duplicates or eliminate them*.

## 1. From Raw Data to a Frequency Table

Given a stream of technology tags:

```text
java, spring, java, jvm, spring, java
```

Desired output:

| Key | Frequency |
| --- | ---: |
| java | 3 |
| spring | 2 |
| jvm | 1 |

If you iterate through the list and count from scratch each time, the code becomes repetitive and the cost grows quickly. With `Map<String,Integer>`, we maintain an accumulated result for each key. The invariant after processing `n` elements: the sum of all count values must equal `n` if every input is counted exactly once and the counts do not overflow.

A readable loop:

```java
Map<String, Integer> counts = new LinkedHashMap<>();
for (String technology : technologies) {
    int previous = counts.getOrDefault(technology, 0);
    counts.put(technology, previous + 1);
}
```

`getOrDefault` retrieves the currently stored value, or the default value when no corresponding mapping exists; `put` writes back the new result. If the currently mapped value is `null`, `getOrDefault` **can return `null`**, because the key actually has a mapping: when writing a counter, choose a model that does not store `null` values, or handle them separately.

With `HashMap`, the iteration order of keys is not guaranteed. `LinkedHashMap` preserves insertion order by default, which is suitable when you want to print keys in the order of their first appearance. `TreeMap` sorts keys according to a comparator/`Comparable`, which is useful when a report requires alphabetical or numerical order.

## 2. Using merge to Simplify Accumulation

`Map.merge(key, value, remappingFunction)` directly expresses the intent of combining a new value into an existing one:

```java
Map<String, Integer> counts = new LinkedHashMap<>();
for (String name : technologies) {
    counts.merge(name, 1, Integer::sum);
}
```

Mechanism:

- If the key has no mapping yet, or its mapped value is `null`, `merge` associates it with the initial value `1`.
- If the key already has a non-`null` value, the remapping function receives the **old value** and the **new value** (here `1`) and returns the result.
- If the remapping function returns `null`, the mapping is **removed**, so `null` must not be used as a valid count.
- The remapping function should be straightforward and avoid mutating the same Map or creating unpredictable side effects.

`Integer::sum` adds using `int` integers and therefore **can overflow** if the number of increments exceeds the `int` range. For systems that may count very large volumes, use `Long` and `Long::sum`, or perform overflow checks as required.

## 3. Complete Runnable Frequency Counting Program

Create `FrequencyDemo.java`:

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class FrequencyDemo {
    public static void main(String[] args) {
        List<String> technologies = List.of(
                "java", "spring", "java", "jvm", "spring", "java"
        );

        Map<String, Integer> counts = new LinkedHashMap<>();
        for (String technology : technologies) {
            counts.merge(technology, 1, Integer::sum);
        }

        System.out.println(counts);
        System.out.println("java: " + counts.getOrDefault("java", 0));
        System.out.println("kotlin: " + counts.getOrDefault("kotlin", 0));
        System.out.println("số nhóm: " + counts.size());

        int total = counts.values().stream()
                .mapToInt(Integer::intValue)
                .sum();
        System.out.println("tổng lượt: " + total);
    }
}
```

Compile and run with JDK 17+:

```text
javac -encoding UTF-8 --release 17 FrequencyDemo.java
java -Dfile.encoding=UTF-8 FrequencyDemo
```

Output:

```text
{java=3, spring=2, jvm=1}
java: 3
kotlin: 0
số nhóm: 3
tổng lượt: 6
```

`counts.size()` is the **number of distinct keys**, not the total occurrences. The total number of occurrences lies in the sum of the values. If you use a `Set` for the input data, duplicate occurrences may already be stripped out before counting; keep a `List` or the full event stream when the business logic cares about frequency.

In the `LinkedHashMap` above, the first occurrence determines the display position of the key. `merge` increments the count without creating a new key, so the insertion order of the keys remains unchanged.

## 4. Grouping Multiple Elements by a Key

Counting stores **a single number** per key. Grouping data stores **a collection** per key, typically `Map<K,List<V>>`.

For example, given the input `["Lan", "Linh", "Minh", "Mai", "Lan"]` where the key is the first letter, the required result is:

```text
L -> [Lan, Linh, Lan]
M -> [Minh, Mai]
```

Core code:

```java
Map<Character, List<String>> groups = new LinkedHashMap<>();
for (String name : names) {
    char initial = name.charAt(0);
    groups.computeIfAbsent(initial, ignored -> new ArrayList<>())
          .add(name);
}
```

Step-by-step explanation:

1. `computeIfAbsent` looks up the value currently associated with the key.
2. If no usable mapping exists yet, the function `ignored -> new ArrayList<>()` creates a list to hold that group and stores it in the Map.
3. The returned result is the list corresponding to the key; `add(name)` adds the element into the group.
4. Subsequent encounters of the key `L` reuse the exact list created earlier; since `Lan` appears twice, there are still two entries.

With `computeIfAbsent`, if the mapping function returns `null`, **no new mapping is created**; chaining `.add` in that case can throw a `NullPointerException`. In this example, `new ArrayList<>()` guarantees a non-`null` value. Do not structurally modify the Map inside the mapping function itself; each implementation's Javadoc specifies its own constraints.

## 5. Complete Runnable Data Grouping Program

Create `GroupingDemo.java`:

```java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class GroupingDemo {
    public static void main(String[] args) {
        List<String> names = List.of(
                "Lan", "Linh", "Minh", "Mai", "Lan"
        );

        Map<Character, List<String>> groups = new LinkedHashMap<>();
        for (String name : names) {
            char first = name.charAt(0);
            groups.computeIfAbsent(first, key -> new ArrayList<>())
                  .add(name);
        }

        System.out.println(groups);
        System.out.println("nhóm L: " + groups.get('L'));
        System.out.println("số nhóm: " + groups.size());
        System.out.println("số phần tử nhóm L: " + groups.get('L').size());
    }
}
```

Run:

```text
javac -encoding UTF-8 --release 17 GroupingDemo.java
java -Dfile.encoding=UTF-8 GroupingDemo
```

Output:

```text
{L=[Lan, Linh, Lan], M=[Minh, Mai]}
nhóm L: [Lan, Linh, Lan]
số nhóm: 2
số phần tử nhóm L: 3
```

Here, every name is non-empty, so `charAt(0)` is valid. If the input comes from users, you must define policies for `null`, empty strings, whitespace, Unicode characters that do not fit in a single `char`, and normalization. Do not treat "first `char`" as equivalent to "first letter" across all languages: Unicode includes supplementary characters outside the BMP, combining marks, and case differences.

## 6. Map<K,List<V>> vs. Map<K,Set<V>>

For the same grouping key, the collection value type determines the duplicate policy:

| Model | Suitable When | Things to Remember |
| --- | --- | --- |
| `Map<K,Integer>` | Only the occurrence count is needed | Does not retain the original records |
| `Map<K,Long>` | Counts can become large | Still consider potential `long` overflow in extreme cases |
| `Map<K,List<V>>` | Retaining all records, including duplicates | An element can appear multiple times |
| `Map<K,LinkedHashSet<V>>` | Deduplicating within each group while preserving insertion order | Duplication is determined by `equals`/`hashCode` of V |
| `TreeMap<K,List<V>>` | Groups must be displayed in key order | Keys require stable comparison and an appropriate comparator |

For example, "counting 5 check-in events" is not equivalent to "5 unique people"; the same person can check in multiple times. If the grouping key is a class code and the collection represents enrolled students, using a `Set` may be appropriate; if the collection represents attendance check-in history, using a `List` accurately reflects the full sequence of events.

A `List` value is a mutable object. When returning `groups.get(key)` to external code, that code can indirectly mutate the Map's state by modifying the list. If the API is meant to be read-only, consider returning `List.copyOf(list)` when it contains no nulls, or an independent copy according to the appropriate contract. `Collections.unmodifiableList(list)` is a view that disallows modification through the view itself, but still reflects changes made to the backing list.

## 7. Choosing Grouping Keys for Real-World Problems

A good key must accurately represent the grouping criterion:

- Department statistics: the key should be a **stable department ID**, not a display name that can easily change.
- Daily statistics: the key should be a `LocalDate` in a well-defined business time zone, rather than manually taking `Instant.toString().substring(...)`.
- Grouping orders by customer and status: use an immutable composite key, such as `record GroupKey(String customerId, Status status) {}`.
- Case-insensitive grouping: normalize the input **according to an explicit policy** before putting it into the Map, for example `toLowerCase(Locale.ROOT)` for technical identifiers in appropriate contexts. For personal names and multilingual text, dedicated locale and normalization rules are required.

Two keys considered equal by `equals` must have the same `hashCode`; a key must not mutate in a way that breaks its contract while residing in a `HashMap`. Do not use mutable objects whose `equals`/`hashCode` depend on mutable fields as grouping keys.

## 8. Stream groupingBy and toMap: When Should You Use Them?

Streams allow expressing grouping declaratively:

```java
Map<Character, List<String>> groups =
        names.stream().collect(
                java.util.stream.Collectors.groupingBy(
                        name -> name.charAt(0)
                )
        );
```

In terms of grouped elements, the result serves the same purpose as the loop; however, the default overload of `groupingBy` **does not guarantee the Map type or iteration order**. If insertion order is a requirement, use the overload that accepts a map supplier:

```java
Map<Character, List<String>> groups =
        names.stream().collect(
                java.util.stream.Collectors.groupingBy(
                        name -> name.charAt(0),
                        LinkedHashMap::new,
                        java.util.stream.Collectors.toList()
                )
        );
```

With `toMap`, if multiple elements produce the same key without a merge function to resolve collisions, collection can throw an `IllegalStateException`. Counting and grouping inherently **expect duplicate keys**, so `groupingBy` or `merge` typically expresses the intent more clearly.

`groupingByConcurrent` and `ConcurrentHashMap` serve certain multithreaded use cases, but they do not preserve insertion order and carry specific requirements regarding collectors and value thread-safety. Do not expose a `HashMap` to concurrent writes across multiple threads just because a single-threaded loop works; for concurrent updates, examine the `ConcurrentMap.merge` contract and synchronization strategies.

## 9. Common Mistakes and Self-Verification

1. **Confusing `size()` with total record count:** `Map.size()` only counts keys. Total frequency = sum of all counts.
2. **Under-counting due to a `Set` input:** keep raw event data if duplicate elements must be counted.
3. **Relying on `HashMap` order:** use `LinkedHashMap` for order of appearance or `TreeMap` for key order.
4. **Mistakenly merging different people by name:** a name is not a unique identifier, and normalization rules must be explicit.
5. **Adding to a null group:** verify that the mapping function does not return `null` before calling methods on the resulting collection.
6. **Overflowing accumulated counts:** choose numeric types and checks appropriate for actual data volumes.
7. **Mutating a key after insertion:** can make `HashMap` lookups unreliable.
8. **Exposing internal lists to callers:** callers may mutate the groups; return a copy or unmodifiable view depending on the contract.
9. **Ignoring empty or invalid data:** decide beforehand whether to skip it, assign it to an `UNKNOWN` group, or fail fast before running.

### Practical Exercise

Given the input `["A", "B", "A", "C", "B", "A"]`, predict `counts` when using `LinkedHashMap` with `merge`. Answer: `{A=3, B=2, C=1}`, with a total of 6 occurrences and 3 keys.

Next, extend the exercise to group a list of names by their first letter while keeping duplicate elements. Try replacing the `ArrayList` value with a `LinkedHashSet` and explain the difference between "number of occurrences" and "number of unique items".

### Explain It in Your Own Words

If you can answer the following three questions in your own words, the core concepts are clear: **(1)** Why can a Map with 3 keys represent 6 occurrences? **(2)** How do `merge` and `computeIfAbsent` differ? **(3)** When should you use `Map<K,List<V>>` instead of `Map<K,Set<V>>`?

## References

- `Map` Javadoc (Java SE 21) — `getOrDefault`, `merge`, and `computeIfAbsent`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Map.html
- `LinkedHashMap` Javadoc (Java SE 21) — insertion order: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashMap.html
- `Collectors` Javadoc (Java SE 21) — `groupingBy`, `toMap`, and their overloads: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Collectors.html
