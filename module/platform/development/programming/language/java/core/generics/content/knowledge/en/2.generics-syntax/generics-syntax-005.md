# Nested Parameterized Types in Java: `Map<K, List<V>>`

When a data structure holds **another data structure**, Java lets you compose generic types to fully express the type at every layer. For example, `Map<String, List<Integer>>` is a mapping from a `String` to a list of `Integer`s: each key can be associated with multiple numbers, while the compiler still checks the key type, list type, and element type.

This lesson focuses on how to **read, declare, instantiate, and manipulate nested parameterized types**, especially the `Map<K, List<V>>` pattern. After this lesson, you will be able to write generic methods for that structure, choose safe update approaches, traverse data, handle missing keys, recognize type invariance, and avoid confusing map copying with copying inner lists.

## 1. Reading `Map<K, List<V>>` Correctly from the Outside In

First, `Map<K, V>` defines a mapping from **a key of type `K`** to **a value of type `V`**. When that value is a list, substitute `List<V>` for the second type argument:

```java
Map<K, List<V>>
```

Read it in three steps:

1. **Outer layer — `Map<..., ...>`:** a key-to-value mapping structure, with each key unique in the map.
2. **First argument — `K`:** the key type; `put` and `computeIfAbsent` require keys matching this type.
3. **Second argument — `List<V>`:** the value associated with each key is a list; each element of the list has type `V`.

Here **`K` and `V` are only type parameter names**, declared by their enclosing class or method. The construct `Map<K, List<V>>` does not implicitly declare `K` or `V` in arbitrary contexts.

Concrete example:

```java
Map<String, List<Integer>> scores;
```

- `K` has been replaced by `String`: each key is a name or code as a string.
- `V` has been replaced by `Integer`: each list holds reference-type integers.
- The **map's value type** is `List<Integer>`, not `Integer`.
- Therefore, `scores.get("An")` has return type `List<Integer>`; then `scores.get("An").get(0)` has type `Integer` if the key exists and the list is non-empty.

Data model:

```text
Map<String, List<Integer>>
    "An"    -> [8, 9, 10]
    "Bình"  -> [7, 9]
    "Chi"   -> []
```

A map can have a key pointing to an empty list, lack that key altogether, or (if the implementation permits) map a key to `null`. These three states should not be treated as identical by default.

### Other Nested Type Examples

| Type | Meaning |
| --- | --- |
| `List<List<String>>` | A list where each element is a list of strings, e.g., rows of data |
| `Map<String, List<Order>>` | Each customer ID associated with multiple orders |
| `Map<Integer, Set<String>>` | Each numeric ID associated with a set of unique strings |
| `Map<String, Map<String, Integer>>` | Two-level mapping, e.g., region → item → quantity |
| `List<Map<String, Object>>` | A list of records with string field names and multi-type values |
| `Map<String, Optional<Long>>` | Each key associated with an optional value represented by `Optional` |

Types like `Order` in the table are illustrative domain types. `Map<String, List<V>>`, `Map<String, Set<V>>`, and `List<List<T>>` are all **compositions of generic types**, not an entirely new kind of Java syntax.

## 2. Declaration Syntax, Closing Brackets, and the Diamond Operator

### 2.1. Instantiation with Concrete Type Arguments

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

Map<String, List<Integer>> scores = new HashMap<>();
scores.put("An", new ArrayList<Integer>());
```

This is an **illustrative snippet within a scope where local variables can be declared**, not a standalone Java file. In `new HashMap<>()`, `<>` is the *diamond operator*: the compiler infers the type arguments of the instantiated object from the left-hand variable context. The object is still used under the `Map<String, List<Integer>>` contract.

In Java 7 and above, two consecutive `>` characters in `Map<K, List<V>>` are properly recognized as closing two type argument lists. There is no need to insert whitespace between them.

```java
Map<String, List<Integer>> a = new HashMap<>();
Map<String, Map<Integer, List<Long>>> b = new HashMap<>();
```

The second example has three consecutive `>` characters because three generic layers must be closed. When reading multi-layer syntax, pair each `>` with its matching `<` from the inside out.

### 2.2. `Map<K, List<V>>` Must Appear Within the Scope Where `K` and `V` Are Declared

**In a generic class:**

```java
final class Groups<K, V> {
    private final Map<K, List<V>> data = new HashMap<>();
}
```

**In a generic method:**

```java
static <K, V> void add(
        Map<K, List<V>> groups,
        K key,
        V value) {
    groups.computeIfAbsent(key, unused -> new ArrayList<>()).add(value);
}
```

The `<K, V>` part **preceding the `void` return type** is the method's type parameter declaration. Type parameter `K` appears in the key position, and `V` appears in the value list and the `value` parameter, allowing the compiler to check call sites against one consistent contract.

If you write a method using `K` and `V` inside a class that neither declares `K`, `V` nor declares `<K, V>` on the method itself, the code will not compile.

### 2.3. Type Inference Is Not the Same as a Raw Type

```java
Map<String, List<Integer>> typed = new HashMap<>();
Map raw = new HashMap(); // Raw type: loses type information for keys and values.
```

`new HashMap<>()` on the first line **remains type-safe** according to the `typed` variable; the second line uses a *raw type*, which can cause warnings and runtime errors. Do not confuse the two cases merely because both look short on the instantiation side.

## 3. Complete Program: Adding, Reading, Grouping Data, and Creating Snapshots

Save the following code into **`Main.java`**. The program uses `Map<String, List<Integer>>` to store multiple scores per name, and also includes generic methods reusable across multiple key and value types. A `record` is grouped by key to show the same algorithm supporting another data type.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Function;

public class Main {
    record Enrollment(String course, String student) {}

    static <K, V> void append(
            Map<K, List<V>> groups,
            K key,
            V value) {
        groups.computeIfAbsent(key, unused -> new ArrayList<>()).add(value);
    }

    static <K, V> List<V> readSnapshot(
            Map<K, List<V>> groups,
            K key) {
        List<V> values = groups.get(key);
        return values == null ? List.of() : List.copyOf(values);
    }

    static <K, V> Map<K, List<V>> snapshot(
            Map<K, List<V>> groups) {
        Map<K, List<V>> copied = new LinkedHashMap<>();
        for (Map.Entry<K, List<V>> entry : groups.entrySet()) {
            copied.put(entry.getKey(), List.copyOf(entry.getValue()));
        }
        return Collections.unmodifiableMap(copied);
    }

    static <K, V> Map<K, List<V>> groupBy(
            List<V> items,
            Function<? super V, ? extends K> keySelector) {
        Map<K, List<V>> result = new LinkedHashMap<>();
        for (V item : items) {
            K key = keySelector.apply(item);
            append(result, key, item);
        }
        return result;
    }

    public static void main(String[] args) {
        Map<String, List<Integer>> scores = new LinkedHashMap<>();
        append(scores, "An", 8);
        append(scores, "An", 9);
        append(scores, "Bình", 7);

        System.out.println("Scores: " + scores);
        System.out.println("First An: " + readSnapshot(scores, "An").get(0));
        System.out.println("Missing: " + readSnapshot(scores, "Chi"));

        Map<String, List<Integer>> frozen = snapshot(scores);
        scores.get("An").add(10);

        System.out.println("Live An: " + scores.get("An"));
        System.out.println("Snapshot An: " + frozen.get("An"));

        List<Enrollment> registrations = List.of(
                new Enrollment("Java", "An"),
                new Enrollment("SQL", "Bình"),
                new Enrollment("Java", "Chi"));

        Map<String, List<Enrollment>> byCourse =
                groupBy(registrations, Enrollment::course);

        List<String> javaStudents = byCourse.get("Java").stream()
                .map(Enrollment::student)
                .toList();

        System.out.println("Java students: " + javaStudents);
        // append(scores, "An", "wrong"); // Type mismatch: V of scores is Integer.
    }
}
```

Run with JDK 17 or higher:

```bash
javac -encoding UTF-8 Main.java
java Main
```

**Stdout:**

```text
Scores: {An=[8, 9], Bình=[7]}
First An: 8
Missing: []
Live An: [8, 9, 10]
Snapshot An: [8, 9]
Java students: [An, Chi]
```

Explanation of results:

1. `append(scores, "An", 8)` infers `K = String` and `V = Integer` from the `Map<String, List<Integer>>` argument and the passed parameters. You cannot add a `String` to the score list through a call of this same type.
2. `computeIfAbsent` creates an `ArrayList<V>` only when the key does not yet map to a non-`null` value. If a list already exists, it returns the stored list so `.add(...)` appends the element.
3. `readSnapshot` returns an empty list when no list exists for the key, avoiding calling methods on `null`. When data exists, it uses `List.copyOf` to return a list that cannot be modified from outside.
4. `snapshot` copies each list before creating an unmodifiable map. Therefore, adding score `10` to `scores` does not alter `frozen`'s list.
5. `groupBy` accepts `Enrollment::course` as the key-producing function, while keeping `Enrollment` itself as the list element type. The result `Map<String, List<Enrollment>>` accurately expresses both data layers.

**Scope of assumptions in the illustrative functions:** `snapshot` and `readSnapshot` require lists/elements being copied to be non-`null`, because `List.copyOf` throws `NullPointerException` on `null` elements. `snapshot` does not deep-copy each individual `V` object if `V` has mutable state. `readSnapshot` intentionally collapses a missing key and a `null`-mapped value into an empty list; an API that needs to distinguish those states must additionally check `containsKey`.

## 4. Accessing and Traversing Each Data Layer

Given the variable:

```java
Map<String, List<Integer>> scores = new LinkedHashMap<>();
```

the following expressions have different type meanings:

| Expression | Compile-Time Type | Notes |
| --- | --- | --- |
| `scores` | `Map<String, List<Integer>>` | The entire mapping |
| `scores.keySet()` | `Set<String>` | Set of keys |
| `scores.values()` | `Collection<List<Integer>>` | Collection of lists; **not** `List<Integer>` |
| `scores.get("An")` | `List<Integer>` | May be `null` if the key does not exist or maps to `null` |
| `scores.get("An").get(0)` | `Integer` | Only safe if the list exists and has a first element |
| `scores.entrySet()` | `Set<Map.Entry<String, List<Integer>>>` | Traverses keys and lists together |
| `scores.getOrDefault("Chi", List.of())` | `List<Integer>` | Uses default if the key **has no mapping**; does not replace an explicit `null` value bound to the key |

There are three common ways to traverse:

**Iterating over each key and list pair:**

```java
for (Map.Entry<String, List<Integer>> entry : scores.entrySet()) {
    String name = entry.getKey();
    List<Integer> grades = entry.getValue();

    for (Integer grade : grades) {
        System.out.println(name + ": " + grade);
    }
}
```

This is illustrative code using the already declared `scores` variable and assumes lists are non-`null`. Each `for` loop corresponds to one layer of parameterization. With `HashMap`, the printed line order is **not guaranteed**; choose `LinkedHashMap` if insertion order must be preserved.

**Iterating over all nested values:**

```java
for (List<Integer> grades : scores.values()) {
    for (Integer grade : grades) {
        // Process each grade.
    }
}
```

**Flattening elements from multiple lists with Stream:**

```java
List<Integer> allScores = scores.values().stream()
        .flatMap(List::stream)
        .toList();
```

In Java 17, `Stream.toList()` produces a list that cannot be modified by direct add/remove operations. It does not require reordering elements; the resulting order depends on the encounter order of the source and the generated streams. When input lists or map iteration order are unspecified, you should not assert a particular output order.

## 5. Adding Elements: Know Whether the Inner Lists Are Mutable

There are two common patterns.

### 5.1. Creating the List Manually When the Key Is Missing

```java
List<Integer> scoresOfAn = scores.get("An");
if (scoresOfAn == null) {
    scoresOfAn = new ArrayList<>();
    scores.put("An", scoresOfAn);
}
scoresOfAn.add(10);
```

This approach suits mutable maps whose list values are also mutable. It treats an absent key and a key mapped to `null` the same way.

### 5.2. Using `computeIfAbsent`

```java
scores.computeIfAbsent("An", key -> new ArrayList<>()).add(10);
```

`computeIfAbsent` works as follows: if there is no non-`null` value for the key yet, compute a new value via the lambda and insert it into the map; then return that value for immediate use. This is a clean, idiomatic pattern for **one key → multiple elements** in a suitable mutable map/list context.

**Do not confuse with `put`:**

```java
scores.put("An", new ArrayList<>(List.of(10)));
```

Calling `put` on an existing key **replaces the entire previous list**, rather than appending `10` to the existing list. If you want to accumulate elements, use `computeIfAbsent(...).add(...)` or an equivalent operation.

### Two Common Mutability Mistakes

**Unmodifiable map:**

```java
Map<String, List<Integer>> immutableMap =
        Map.of("An", List.of(8, 9));
// immutableMap.put("Bình", List.of(7)); // UnsupportedOperationException.
```

**Unmodifiable list even though the map is mutable:**

```java
Map<String, List<Integer>> mixed = new HashMap<>();
mixed.put("An", List.of(8, 9));
// mixed.get("An").add(10); // UnsupportedOperationException.
```

There is no rule that `Map<K,List<V>>` is always mutable or always immutable. Mutability of the **outer map** and the **inner lists** are two independent properties depending on the implementing objects. A mutable map can still hold immutable lists.

If an API requires immutability, determine whether it allows replacing an entire list, appending elements inside, or no mutation at all; then explicitly design the read/write contract instead of relying solely on the generic type name.

## 6. Missing Keys, Empty Lists, `null`, and Return Types

Reading:

```java
List<Integer> grades = scores.get("An");
```

You must distinguish:

- **Key does not exist:** `Map.get` usually returns `null`.
- **Key exists with `null` value:** some map implementations allow this; `get` also returns `null`, yet `containsKey("An")` is `true`.
- **Key exists with an empty list:** `get` returns a list with `isEmpty() == true`, which is non-`null`.
- **Key exists with a populated list:** can be traversed and accessed by valid indices.

If you always want an empty list when the key is absent:

```java
List<Integer> grades = scores.getOrDefault("An", List.of());
```

Note that `getOrDefault` does **not** replace a `null` value explicitly mapped to a key. If `null` should be treated the same as absent:

```java
List<Integer> grades = scores.get("An");
if (grades == null) {
    grades = List.of();
}
```

If you need to distinguish **absent** from **empty list**, keep the standard `get` contract and use `containsKey` where needed. Overusing `List.of()` as a default can discard business meaning, such as “customer history has not been loaded” vs. “history was loaded and is empty”.

`List.of()` works well as a **default read-only value** but cannot `.add(...)`; if updates are needed, construct `new ArrayList<>()` or choose an appropriate mutable structure.

## 7. Multi-Layer Type Invariance: Compilation Errors to Understand

Java generics are **invariant** by default. Even though `Integer` is a subtype of `Number`, `List<Integer>` and `List<Number>` have no subtype relationship in that direction. Nesting does not make this rule disappear:

```java
Map<String, List<Integer>> grades = new HashMap<>();

// Does not compile:
// Map<String, List<Number>> asNumbers = grades;

// Does not compile:
// Map<String, List<? extends Number>> flexible = grades;
```

Why is the second assignment still invalid? `List<Integer>` can be used where `List<? extends Number>` is expected, yet **`Map<String, List<Integer>>` is not a subtype of `Map<String, List<? extends Number>>`** because `Map`'s second type argument is also invariant. If that assignment were allowed, the receiving code could replace a list in the map with a list of `Double`, breaking the original contract.

To write a **read-only** API over numeric values from different kinds of lists, you can widen with wildcards at the appropriate layer:

```java
static double sumAll(
        Map<String, ? extends List<? extends Number>> source) {
    double total = 0;
    for (List<? extends Number> numbers : source.values()) {
        for (Number number : numbers) {
            total += number.doubleValue();
        }
    }
    return total;
}
```

This is an illustrative method, not a standalone program. The type `Map<String, ? extends List<? extends Number>>` allows accepting a map whose values are lists with matching numeric elements, including `Map<String, List<Integer>>`. However, through the `source` reference you cannot arbitrarily replace a list in the map with a `List<Number>` or add an arbitrary `Number` into a retrieved list. Broader wildcards permit reading while **restricting certain write operations** to preserve type safety.

Key takeaway: the **layer** where a wildcard is placed governs flexibility at that layer. The three signatures below are distinct:

```java
Map<String, List<Number>>
Map<String, List<? extends Number>>
Map<String, ? extends List<? extends Number>>
```

An API expecting the first type has a different contract from one expecting the second or third. Start from the usage requirement: do you need to read numeric values, add any kind of number, or replace entire lists?

### Common Mistake: Assigning a Map to `Map<Object, ...>`

```java
Map<String, List<Integer>> scores = new HashMap<>();
// Map<Object, List<Object>> other = scores; // Does not compile.
```

The fact that `String` is a subtype of `Object` and `Integer` is also a subtype of `Object` does **not** make the corresponding map types subtypes in that way. When you genuinely need to store heterogeneous keys and elements, design the data type that way from the start, such as `Map<Object, List<Object>>`, accepting reduced type precision and validating data at appropriate boundaries.

## 8. Copying: Outer Map vs. Inner Lists

A nested structure can share references across multiple places:

```java
Map<String, List<Integer>> original = new HashMap<>();
original.put("An", new ArrayList<>(List.of(8, 9)));

Map<String, List<Integer>> shallow = new HashMap<>(original);
shallow.get("An").add(10);
```

`shallow` is a **new map**, yet `original.get("An")` and `shallow.get("An")` initially point to **the exact same list object**. Hence, adding `10` through `shallow` also mutates the list seen from `original`. Copying a map **does not automatically copy** the inner reference values.

Similarly, `Collections.unmodifiableMap(original)` only creates an unmodifiable view of the map: the inner referenced lists themselves can still be mutable. `Map.copyOf(original)` creates an unmodifiable map yet does not deep-copy each list either; and it rejects `null` keys or values.

If you want a **two-layer unmodifiable snapshot**, copy the lists first:

```java
Map<String, List<Integer>> copied = new LinkedHashMap<>();
for (Map.Entry<String, List<Integer>> entry : original.entrySet()) {
    copied.put(entry.getKey(), List.copyOf(entry.getValue()));
}
Map<String, List<Integer>> frozen =
        Collections.unmodifiableMap(copied);
```

Understand the exact limitation: `List.copyOf` only copies the list structure and ensures the returned list cannot be mutated through that API; it **does not clone individual elements**. If `V` is an object with mutable state, fully isolating state requires an appropriate copying mechanism for type `V` itself. If the input data contains `null`, `List.copyOf` throws `NullPointerException`.

When the context calls for **continuous updates**, keeping a simple mutable structure such as `LinkedHashMap<K, ArrayList<V>>` internally and exposing only `Map<K,List<V>>`/copied lists in read APIs can be a sound choice, provided mutation rights and thread synchronization are handled consistently.

## 9. When to Use `Map<K,List<V>>` vs. Another Structure?

`Map<K,List<V>>` fits when:

- One key has **multiple values** and **order** or allowing duplicate elements matters.
- You need to group data by an attribute, e.g., course code → list of enrollees.
- You need fast group lookup by key followed by iterating over the group's elements.

However, not every one-to-many relationship should use `List<V>`:

| Requirement | Reference Choice | Why |
| --- | --- | --- |
| Allow duplicate values and preserve order in each group | `Map<K, List<V>>` | List represents order and retains duplicate entries |
| Disallow duplicates within each group | `Map<K, Set<V>>` | Set expresses uniqueness within each group |
| Need only one value per key | `Map<K, V>` | No extra `List` layer needed |
| Need two independent key levels | `Map<K1, Map<K2, V>>` | Each map layer carries its own key role |
| Need to preserve global order across all records | `List<Record>` or an appropriate model | Grouping by key can obscure the original interleaved order |
| Many business rules around groups | Dedicated class/domain object | Encapsulate validation and consistent operations in a named API |

`HashMap` does not guarantee iteration order, whereas `LinkedHashMap` preserves key insertion order. The `List<V>` type describes the value-layer list without specifying which outer map implementation is used. If ordering, uniqueness, or mutability carries business significance, state it clearly in the API or choose a matching structure.

### Grouping Data with Stream

One way to build a nested type is `Collectors.groupingBy`:

```java
Map<String, List<Enrollment>> byCourse =
        registrations.stream()
                .collect(java.util.stream.Collectors.groupingBy(
                        Enrollment::course));
```

`Enrollment` and `registrations` come from the complete program in Section 3. The result has the form `Map<String, List<Enrollment>>`. You should not assume the key order or exact type/mutability of the map and lists returned by the default collector; if those properties are API requirements, pick the overload with an appropriate `mapFactory`/collector or actively construct a controlled structure.

If you want to **preserve key encounter order** when grouping in a sequential stream, you can supply a map factory:

```java
Map<String, List<Enrollment>> ordered =
        registrations.stream().collect(
                java.util.stream.Collectors.groupingBy(
                        Enrollment::course,
                        LinkedHashMap::new,
                        java.util.stream.Collectors.toList()));
```

This snippet is intended in the context of `Main.java` above, not as a standalone program. Do not confuse “`LinkedHashMap` preserves key insertion order” with “every collector guarantees mutability and order across all execution modes”. Ordering behavior should be read from the collector contract and input stream characteristics.

## 10. Type Erasure and Runtime Data Checking

The type safety of `Map<String, List<Integer>>` is checked primarily **at compile time**. Java uses *type erasure*: at runtime, most type arguments such as `String` and `Integer` in a parameterized usage are not reified in an ordinary map object.

Hence the following syntax is invalid:

```java
// if (value instanceof Map<String, List<Integer>>) { ... }
// Does not compile: cannot check this full parameterized type.
```

You can check the raw structure:

```java
if (value instanceof Map<?, ?>) {
    // Only knows value is a Map; inner key and value types remain unknown.
}
```

This snippet assumes a variable `value` of type `Object` already exists in scope. When data comes from JSON, API responses, reflection, or raw code, **validate every layer**: the key type, whether each value is a list, and the type of every element before treating the data as `Map<String,List<Integer>>`.

Do not write an unchecked cast `((Map<String, List<Integer>>) value)` and treat it as a complete runtime check. An unchecked cast may be accepted at compile time with a warning, yet malformed inner data will still fail during later access. For external data, use a deserialization library with full nested type descriptors or validate manually against a schema.

Technically, a single `Class<?>` only represents a runtime class such as `Map.class` or `List.class`, not the full `Map<String,List<Integer>>`. Some JSON libraries offer a **type reference** mechanism for nested generic types; exact usage depends on the library's API rather than a built-in Java syntax feature.

## 11. Typical Mistakes and How to Fix Them

**Mistake 1 — forgetting the `List` layer:**

```java
Map<String, List<Integer>> scores = new HashMap<>();
// scores.put("An", 8); // Incorrect: map value must be List<Integer>.
scores.put("An", new ArrayList<>(List.of(8))); // Valid.
```

**Mistake 2 — reading the map as if it returned an `Integer`:**

```java
// Integer first = scores.get("An"); // Incorrect: get returns List<Integer>.
List<Integer> an = scores.get("An");
```

To obtain the first element, call `an.get(0)`, after ensuring `an != null` and `!an.isEmpty()`.

**Mistake 3 — unintentionally sharing one list across multiple keys:**

```java
List<Integer> shared = new ArrayList<>();
scores.put("An", shared);
scores.put("Bình", shared);
```

Adding an element via one key causes the other key to see the same change. If independent groups are desired, create a separate `new ArrayList<>()` for each group.

**Mistake 4 — assuming `Map.of`/`List.of` allow adding elements:**

```java
Map<String, List<Integer>> fixed = Map.of("An", List.of(8));
// fixed.get("An").add(9); // UnsupportedOperationException.
```

Use mutable implementations when updates are required, or construct a new result in an immutable style.

**Mistake 5 — misunderstanding wildcards on the inner layer:** `Map<String,List<Integer>>` cannot be assigned directly to `Map<String,List<? extends Number>>`. If a method only reads multiple kinds of numeric lists, evaluate `Map<String, ? extends List<? extends Number>>` along with its write restrictions.

**Mistake 6 — returning an internal list directly to callers:** the caller could `add`, `clear`, or reorder it, corrupting the map's state. Use `List.copyOf` or an appropriate view and document clearly whether it is a snapshot or a live view.

**Mistake 7 — treating `getOrDefault` as replacing `null` values too:** the method only uses the default when the key has no mapping; check `null` separately if the contract needs to merge both states.

**Mistake 8 — performing raw/unchecked casts on untrusted data:** generic type guarantees can break at runtime. Validate structure at data boundaries, minimize raw types, and address `unchecked` warnings deliberately.

## 12. Self-Practice

**Exercise 1.** Given:

```java
Map<String, List<Long>> ids = new HashMap<>();
```

What are the types of `ids.get("A")` and `ids.values()`?

**Answer:** `ids.get("A")` has type `List<Long>`; `ids.values()` has type `Collection<List<Long>>`. Never conclude that either expression is equivalent to `Long` or `Collection<Long>`.

**Exercise 2.** When calling:

```java
append(scores, "An", 9);
```

in the complete program, how are the two type parameters inferred?

**Answer:** `K = String`, `V = Integer` because `scores` is `Map<String,List<Integer>>`. The call `append(scores, "An", "9")` passes a string instead of an integer score and is rejected at compile time.

**Exercise 3.** Why is `new HashMap<>(scores)` not enough to prevent inner lists from being modified through another reference?

**Answer:** That constructor creates a new map yet copies the **value references**; the lists held in both maps can still be the exact same objects. You must copy the lists as well when isolating the inner structure.

**Exercise 4.** Do a key with no score yet and a key with an empty score list have the same semantics?

**Answer:** Not necessarily. `get` on an absent key may return `null`; a key mapped to `List.of()` returns an empty list. Business logic determines whether they need to be distinguished and whether `containsKey` should be used.

**Exercise 5.** Choose the appropriate signature for a function that **only reads** all numbers across the value lists:

```java
Map<String, List<Number>>
Map<String, ? extends List<? extends Number>>
```

**Answer:** The second signature is more flexible because it accepts `Map<String,List<Integer>>` or lists of other `Number` subtypes. In return, the API cannot freely replace lists or add arbitrary elements through the wildcard reference.

## Summary

With `Map<K, List<V>>`, read from the outside in: a map with keys of type `K`, where each value is a list of elements of type `V`. The strength of nested syntax is that the compiler can track **types at every layer** and enforce that `put`, `get`, `entrySet`, `computeIfAbsent`, and generic methods obey that relationship. To use it properly in real applications, also decide **whether the structure is mutable, whether order must be preserved, how missing keys are handled, and whether copying the map sufficiently isolates inner data**. Finally, remember that type invariance applies at each layer and type erasure does not replace validating data from external sources.