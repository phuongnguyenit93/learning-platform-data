# Building a Multi-Value Index with `Map<K, List<V>>`

## 1. Objectives and Problem Statement

After completing this lesson, you will be able to build a **one-key-to-many-values index** using Java Collections, look up data by key, add and remove elements, handle missing keys, and choose between manually maintaining an index and grouping with Streams.

Suppose each registration record contains a **course code** and a **student**. One course has multiple students; one student can also enroll in multiple courses. We want to quickly answer the question "Which students are in the Java course?" without rescanning the entire registration list every time.

Initial data:

| Course (K) | Student (V) |
| --- | --- |
| Java | S01 – An |
| Java | S02 – Binh |
| SQL | S03 – Chi |
| SQL | S01 – An |

The index should have the form:

```text
Java -> [An, Binh]
SQL  -> [Chi, An]
```

In `Map<K, List<V>>`:

- `K` is the lookup key, such as a `String` course name.
- `V` is **one** element stored under the key, such as a `Student`.
- `List<V>` is a group of multiple elements corresponding to a single key; it preserves **insertion order** and **allows duplicate elements**.
- `Map` finds the group by key; `List` manages the elements inside that group.

If you used `Map<String, Student>` and called `put("Java", student)` multiple times, each subsequent element would **overwrite** the previous one. Therefore, for a one-to-many relationship, the map value must be a collection—here, `List<Student>`.

## 2. Design Rules Before Writing Code

A useful index must have clear behavior:

1. **Add:** if the key does not exist yet, create a list; if the key already exists, append to the existing list.
2. **Find:** if the key does not exist, return an empty list, avoiding forcing callers to handle `null`.
3. **Remove:** remove a single value using `equals`; if the group becomes empty, remove the key as well so no empty entries remain.
4. **Return results:** expose a **read-only snapshot** so external code cannot corrupt the internal structure.
5. **Ordering:** this example uses `LinkedHashMap` so key iteration follows first-seen insertion order; each group list uses `ArrayList`.
6. **Null values:** this example actively rejects `null` keys and values to keep the API easy to validate and compatible with `List.copyOf`.
7. **Duplicates:** `List` allows a value to appear multiple times; this lesson retains that characteristic. If business logic requires uniqueness, a separate rule is needed.

To control updates, the program encapsulates the `Map` inside a `MultiValueIndex<K, V>` class. All operations go through `add`, `find`, `remove`, and `counts`.

## 3. Complete Java 17 Program

Create the file **`MultiValueIndexDemo.java`** with the following content:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public class MultiValueIndexDemo {
    record Student(String id, String name) {}

    record Enrollment(String course, Student student) {}

    static final class MultiValueIndex<K, V> {
        private final Map<K, List<V>> entries = new LinkedHashMap<>();

        public void add(K key, V value) {
            Objects.requireNonNull(key, "key");
            Objects.requireNonNull(value, "value");
            entries.computeIfAbsent(key, ignored -> new ArrayList<>()).add(value);
        }

        public List<V> find(K key) {
            Objects.requireNonNull(key, "key");
            List<V> values = entries.get(key);
            return values == null ? List.of() : List.copyOf(values);
        }

        public boolean remove(K key, V value) {
            Objects.requireNonNull(key, "key");
            Objects.requireNonNull(value, "value");
            List<V> values = entries.get(key);
            if (values == null) {
                return false;
            }

            boolean removed = values.remove(value);
            if (values.isEmpty()) {
                entries.remove(key);
            }
            return removed;
        }

        public Map<K, Integer> counts() {
            Map<K, Integer> result = new LinkedHashMap<>();
            entries.forEach((key, values) -> result.put(key, values.size()));
            return Collections.unmodifiableMap(result);
        }
    }

    public static void main(String[] args) {
        Student an = new Student("S01", "An");
        Student binh = new Student("S02", "Binh");
        Student chi = new Student("S03", "Chi");

        List<Enrollment> registrations = List.of(
            new Enrollment("Java", an),
            new Enrollment("Java", binh),
            new Enrollment("SQL", chi),
            new Enrollment("SQL", an)
        );

        MultiValueIndex<String, Student> byCourse = new MultiValueIndex<>();
        for (Enrollment registration : registrations) {
            byCourse.add(registration.course(), registration.student());
        }

        System.out.println("Java: " + byCourse.find("Java"));
        System.out.println("SQL: " + byCourse.find("SQL"));
        System.out.println("Kotlin: " + byCourse.find("Kotlin"));
        System.out.println("So luong: " + byCourse.counts());

        List<Student> before = byCourse.find("Java");
        System.out.println("Xoa S01 khoi Java: " + byCourse.remove("Java", an));
        System.out.println("Java sau xoa: " + byCourse.find("Java"));
        System.out.println("Ban chup truoc do: " + before);

        byCourse.add("Java", chi);
        System.out.println("Java sau them: " + byCourse.find("Java"));
        System.out.println("So luong moi: " + byCourse.counts());
    }
}
```

Compile and run from the directory containing the file (JDK 17 or later):

```bash
javac -encoding UTF-8 MultiValueIndexDemo.java
java MultiValueIndexDemo
```

Standard output:

```text
Java: [Student[id=S01, name=An], Student[id=S02, name=Binh]]
SQL: [Student[id=S03, name=Chi], Student[id=S01, name=An]]
Kotlin: []
So luong: {Java=2, SQL=2}
Xoa S01 khoi Java: true
Java sau xoa: [Student[id=S02, name=Binh]]
Ban chup truoc do: [Student[id=S01, name=An], Student[id=S02, name=Binh]]
Java sau them: [Student[id=S02, name=Binh], Student[id=S03, name=Chi]]
So luong moi: {Java=2, SQL=2}
```

`Student` and `Enrollment` are two `record` types: Java automatically generates the constructor, accessor methods (`id()`, `course()`, etc.), `equals`, `hashCode`, and `toString` based on the record components. As a result, `values.remove(an)` can use value comparison, and the printed output follows the format `Student[id=..., name=...]`. The code runs standalone without external libraries.

## 4. Explaining the Update Mechanism

### 4.1. `computeIfAbsent` Creates the List on Demand

The core statement is:

```java
entries.computeIfAbsent(key, ignored -> new ArrayList<>()).add(value);
```

- If `key` has no mapping yet, the function creates a new `ArrayList`, puts that list into the map, and returns it.
- If `key` already maps to a non-`null` list, the method returns **that exact existing list**.
- `add(value)` appends an element to the end of the returned list.
- The lambda `ignored -> ...` receives the key parameter but does not need to use it to create the list.

The manual equivalent in concept, when keys and values are non-`null` as in this example, is:

```java
List<V> values = entries.get(key);
if (values == null) {
    values = new ArrayList<>();
    entries.put(key, values);
}
values.add(value);
```

Do not use `entries.put(key, new ArrayList<>(List.of(value)))` for **every** insertion: the second addition for the same key will replace the entire previous group, causing data loss.

### 4.2. Why Is the `find` Result Copied?

`entries.get(key)` directly accesses the **mutable** list inside the index. If that reference were returned directly to callers, external code could call `clear()` or `add()` without going through the index API.

In this example, `List.copyOf(values)` creates a list that **cannot be modified via List mutator operations** and captures a snapshot of the elements at the time of the call. That is why the variable `before` still contains An and Binh after we remove An from the index. `List.of()` is the empty result and is likewise unmodifiable.

Note: this is a **shallow copy**. The `V` objects inside are not automatically cloned; if `V` is a mutable object, the internal state of that object itself could still change afterward. When deep immutability is required, you must create appropriate defensive copies of each element yourself.

Do not confuse the two options:

- `List.copyOf(list)`: the resulting list is structurally independent from the original list.
- `Collections.unmodifiableList(list)`: only a read-only wrapper view; if the backing list changes, the contents seen through the wrapper also change.

### 4.3. Removing a Single Occurrence and Cleaning Up Empty Keys

`values.remove(value)` returns `true` if it finds and removes **the first element matching `equals`**; if none is found, it returns `false`. Two identical records added twice will require two removal calls to eliminate completely.

After removal, `if (values.isEmpty()) entries.remove(key)` maintains the invariant: **no key exists with an empty group**. Consequently, `find` does not need to distinguish between an absent key and an existing key whose group is empty.

Separate verification example (illustrative snippet, to be used inside the same class or after creating a suitable index):

```java
MultiValueIndex<String, String> tags = new MultiValueIndex<>();
tags.add("java", "collections");
tags.add("java", "collections");
tags.remove("java", "collections");
System.out.println(tags.find("java")); // [collections]
tags.remove("java", "collections");
System.out.println(tags.counts());      // {}
```

### 4.4. Counting Elements per Key

`counts()` iterates over each `key -> list` pair, puts `list.size()` into a new map, and returns a read-only wrapper. This is a **count snapshot** that does not automatically update after the index changes. `LinkedHashMap` is used for the count result to preserve the same key order as the underlying index.

## 5. Alternative Approach: Single-Pass Indexing with Streams

When you **already have** the complete `registrations` list and only need to group it once, you can write it more concisely with `Collectors.groupingBy`. The following snippet uses the `Enrollment` and `Student` types and the `registrations` variable from the program in Section 3; it requires adding `import java.util.stream.Collectors;`:

```java
Map<String, List<Student>> grouped = registrations.stream()
    .collect(Collectors.groupingBy(
        Enrollment::course,
        LinkedHashMap::new,
        Collectors.mapping(
            Enrollment::student,
            Collectors.toCollection(ArrayList::new)
        )
    ));
```

- `Enrollment::course` selects the key for each record.
- `LinkedHashMap::new` preserves the first-seen order of keys.
- `Collectors.mapping` extracts the `Student` from each `Enrollment`.
- `Collectors.toCollection(ArrayList::new)` creates a mutable list and preserves encounter order in a sequential stream.

With the current data, `grouped.get("Java")` contains `[An, Binh]` (rendered via `Student.toString()` when printed). Because the example stream is **sequential**, the input encounter order is preserved as described. `groupingBy` should not be used when the classifier function can return `null` without prior handling; nor does it automatically maintain the index when the source list changes.

Choose **a loop + `computeIfAbsent`** when reading and adding records incrementally, performing incremental updates or removals, or encapsulating domain rules. Choose **`groupingBy`** when you need to aggregate the entire source into a map in a single pass.

## 6. Complexity and Collection Choices

Let `n` be the total number of values and `m` be the number of values under a single key:

| Operation | Typical Cost | Reason |
| --- | --- | --- |
| `add(key, value)` | O(1) average, amortized | Hash map lookup plus appending to the end of `ArrayList` |
| Internal list lookup by key | O(1) average | `LinkedHashMap` is hash-table based |
| `find(key)` **in this example** | O(m) | Map lookup followed by `List.copyOf` over `m` elements |
| `remove(key, value)` | O(m) | Linear scan via `equals`; `ArrayList` may shift elements after removal |
| `counts()` | O(number of keys) | Iterates through each group and reads `size()` |
| Index memory | O(n + number of keys) | Stores value references plus list and map structures |

Hash operation estimates are **average-case** assuming a well-distributed `hashCode`; they are not worst-case time guarantees. `ArrayList` occasionally resizes its backing array, so appending at the end is **amortized** O(1).

Choose a structure based on actual requirements:

| Requirement | Reference Structure |
| --- | --- |
| Allow duplicates, preserve value order | `Map<K, List<V>>` |
| Disallow duplicate values by `equals/hashCode` | `Map<K, Set<V>>`, e.g., `LinkedHashSet<V>` |
| Iterate keys in insertion order | `LinkedHashMap<K, List<V>>` |
| Sort keys by comparator / natural ordering | `TreeMap<K, List<V>>` |
| Only one value per key | `Map<K, V>` |

**There is no single best choice for every situation.** If you need to look up or remove individual values very frequently, `Set<V>` may be more appropriate. If two equal values still represent two distinct registration occurrences, `List<V>` is the meaningful choice.

## 7. Common Pitfalls in Practice

**Overwriting the list:** calling `put` with a newly created list on every record loses previously stored values. Append to the existing group using `computeIfAbsent`.

**Mutating an immutable empty list:** `map.getOrDefault(key, List.of()).add(value)` throws `UnsupportedOperationException` when the key does not exist yet because `List.of()` is an unmodifiable list. Moreover, `getOrDefault` **does not store** the default value into the map. Use `computeIfAbsent` to initialize a mutable group.

**Leaking internal data:** returning `entries.get(key)` directly allows external code to mutate the index. Return a `List.copyOf` snapshot if the goal is a read-only snapshot API.

**Unintended duplicate values:** `List` accepts duplicate elements. If the problem requires registering a student at most once per course, you must check for duplicates with `contains` or use a `Set`. `contains` on a list is O(m) and relies on `equals`.

**Out-of-sync index when source data changes:** an index is derived data. If an enrollment moves from Java to SQL, you must **remove the element from the Java group and add it to the SQL group**, or rebuild the index from the source of truth. Merely mutating a `course` field on the source object does not automatically move the element between lists.

**Mutable keys:** `HashMap` and `LinkedHashMap` rely on the key's `equals` and `hashCode`. If fields participating in those two methods are modified after inserting the key into the map, lookups can fail. Prefer stable keys such as `String` or immutable records with appropriate data components.

**Misunderstanding thread safety:** `LinkedHashMap` and `ArrayList` in this example are **not thread-safe** when multiple threads add or remove concurrently. Simply changing the map to `ConcurrentHashMap` still does not make the inner `ArrayList` thread-safe. If concurrent updates genuinely occur, you must design proper synchronization locks or concurrent structures covering group creation, list mutation, and empty-key removal together.

**Confusing an in-memory index with a database:** the map in this example lives in memory; when the program terminates, it is not automatically persisted to a file or database. Durability requires saving the source data or index data through a dedicated persistence mechanism.

## 8. Practice Exercises with Verification Criteria

1. Create a `MultiValueIndex<String, String>` to store tags for articles. Add `("p1", "java")`, `("p1", "map")`, and `("p2", "java")`. Verify that `find("p1")` returns the two tags in the exact insertion order and `find("p3")` returns an empty list.
2. Add `("p1", "java")` twice. Observe that `find("p1")` contains two `"java"` values. Change the requirement to **each tag at most once**, then test checking `contains` before adding or replacing `List` with `LinkedHashSet`.
3. Remove all values belonging to `"p2"` one by one. Verify that `counts()` no longer contains the key `"p2"`. Call `remove` with a non-existent key and verify that the result is `false`.
4. Save the result of `find("p1")` into a variable, add more data to the index, and print the old variable. Explain why the snapshot does not change and why the caller cannot call `add` directly on that returned list.
5. Build a reverse index **`Map<String, List<String>>` from tag to article ID**, for example `"java" -> ["p1", "p2"]`. Clearly specify whether an article tagged multiple times with the same tag should be stored with duplicates or not.

Self-check: you should be able to explain the difference between `Map<K,V>` and `Map<K,List<V>>`, how `computeIfAbsent` prevents overwriting, why `find` here costs O(m), the rule for cleaning up empty keys, and when to use `groupingBy`. When implementing an index for another problem, **decide up front** the rules for duplicates, ordering, updates, and whether query results may be mutated.
