# String as a HashMap Key or HashSet Element in Java

## 1. Goal and Context

`String` is one of the most commonly used types as a **key** of `HashMap<String, V>` and as an **element** of `HashSet<String>`: product codes, configuration names, status labels, tokens, usernames, vocabulary words, or strings used for deduplication. These two collections rely on the **`hashCode()` and `equals(Object)`** method pair to identify equivalent keys/elements.

Example:

~~~java
Map<String, Integer> points = new HashMap<>();
points.put("java", 10);
points.put("spring", 20);
System.out.println(points.get("java")); // 10

Set<String> tags = new HashSet<>();
tags.add("backend");
tags.add("backend");
System.out.println(tags.size()); // 1
~~~

In the examples, imports for `java.util.Map`, `java.util.HashMap`, `java.util.Set`, and `java.util.HashSet` are required if written as a standalone Java class. Individual snippets are for illustration only; a complete program compilable with Java 17 is in section 8.

**Key takeaway:** `HashMap` and `HashSet` care about **logical content considered equal by `equals`**, not whether two variables reference the same String object.

## 2. Why Does `String` Work Well as a Key and Set Element?

`String` has **immutable content**, `equals` compares content case-sensitively, and `hashCode` is consistent with `equals`. Therefore, the same content is treated as the same key/element even when created by two different instances:

~~~java
String first = new String("Java");
String other = new String("Java");
System.out.println(first == other);      // false
System.out.println(first.equals(other)); // true
System.out.println(first.hashCode() == other.hashCode()); // true
~~~

`HashMap` uses the hash to locate a candidate region and then checks key equivalence; `HashSet` uses the same principle to eliminate duplicate elements. **Same hash does not guarantee same value**: `"FB"` and `"Ea"` have equal hashes but different content. The collection still keeps them as two distinct keys. The hash formula, collisions, and detailed conditions of the `equals–hashCode` contract are analyzed in the next lesson.

The strength of `String` is that an inserted key never changes its content. If after `put` you reassign the variable `key = key + "-admin"`, the map still keeps the old key: the assignment changes the variable's reference, **without modifying the stored String**.

~~~java
String key = "user";
Map<String, Integer> map = new HashMap<>();
map.put(key, 7);
key = key + "-admin";
System.out.println(map.get("user")); // 7
System.out.println(map.get(key));    // null
~~~

Snippets are illustrations inside a method; a standalone program with full imports is in section 8.

## 3. How Does HashMap Use String Keys?

### 3.1. `put`, `get`, and `containsKey`

Conceptual model: `HashMap` uses the hash code to determine a candidate location, then uses `equals` to distinguish different keys residing in the same storage region. Details of buckets, resizing, and collision-handling structures belong to the JDK implementation; the API guarantees behavior according to the Map contract.

~~~java
Map<String, Integer> scores = new HashMap<>();
String first = new String("Java");
String sameContent = new String("Java");

scores.put(first, 10);
System.out.println(scores.get(sameContent)); // 10

scores.put(sameContent, 20);
System.out.println(scores.size());          // 1
System.out.println(scores.get("Java"));     // 20
~~~

The second `put` call **updates the value of the equivalent key** instead of creating a new entry. A Java map does not allow two keys considered equal by `equals` to coexist. Meanwhile, `"Java"` and `"java"` are two distinct keys by default.

Commonly used methods:

| Operation | Meaning |
| --- | --- |
| `put(key, value)` | Adds a mapping if no equivalent key exists, or replaces the value associated with that key; returns the previous value or `null` per the contract. |
| `get(key)` | Retrieves the value of the equivalent key; returns `null` if there is no mapping, or if the mapping holds a `null` value. |
| `containsKey(key)` | Checks whether the key exists, helping distinguish "key absent" from "key with null value". |
| `putIfAbsent(key, value)` | Adds the value when the key has no mapping or is currently mapped to `null`; not an accumulation command. |
| `merge` / `computeIfAbsent` | Supports updating/creating values according to a rule, convenient for frequency counting or grouping. |

Frequency counting example:

~~~java
Map<String, Integer> counts = new HashMap<>();
for (String token : new String[] {"java", "sql", "java"}) {
    counts.merge(token, 1, Integer::sum);
}
System.out.println(counts.get("java")); // 2
System.out.println(counts.get("sql"));  // 1
~~~

Using `String` as a key does not mean the map automatically strips whitespace, changes letter case, or normalizes Unicode: the map stores and looks up strings **exactly as provided**.

### 3.2. Collision Is Not a Duplicate Key

~~~java
Map<String, String> collisionMap = new HashMap<>();
collisionMap.put("FB", "first");
collisionMap.put("Ea", "second");

System.out.println(collisionMap.size());      // 2
System.out.println(collisionMap.get("FB"));   // first
System.out.println(collisionMap.get("Ea"));   // second
~~~

The two strings have the same hash code but `equals` is false, so the map contains **two** entries. Collisions can make lookup slower because extra checks are needed, but a collision **must not cause data loss** as long as keys obey `equals/hashCode`.

### 3.3. Null Keys and Null Values

`HashMap` allows **one** `null` key and allows `null` values. This is specific to `HashMap` and does not apply by default to every `Map`:

~~~java
Map<String, Integer> map = new HashMap<>();
map.put(null, 42);
map.put("pending", null);
System.out.println(map.get(null));             // 42
System.out.println(map.get("pending"));        // null
System.out.println(map.containsKey("pending"));// true
~~~

In real systems, if `null` has no clear business meaning, it can be forbidden at the input boundary to keep data simpler. `Map.of(...)` and some other implementations do not accept `null` keys or values.

## 4. How Does HashSet Use String Elements?

### 4.1. Deduplicating Elements by equals/hashCode

`HashSet` is a set that does not allow elements considered equal by `equals`. It is implemented on top of `HashMap`, using the element as the internal key and a dummy value as the map value:

~~~java
Set<String> skills = new HashSet<>();

System.out.println(skills.add(new String("Java"))); // true
System.out.println(skills.add(new String("Java"))); // false
System.out.println(skills.add("java"));             // true
System.out.println(skills.size());                  // 2
System.out.println(skills.contains("Java"));        // true
~~~

`add` returns `true` when the set changes and `false` if an equivalent element already exists. Two `String` objects with different references but the same content occupy only one element; different casing yields two elements by default.

A simple scenario is extracting unique labels:

~~~java
List<String> input = List.of("red", "blue", "red", "green");
Set<String> unique = new HashSet<>(input);
System.out.println(unique.size()); // 3
~~~

**Do not rely on order** when iterating over a `HashSet`. If preserving first-seen order is required, use `LinkedHashSet`; if sorted order according to a comparator is needed, consider `TreeSet` with an appropriate comparison rule.

### 4.2. One Null Element, and API Differences

`HashSet` allows a `null` element (at most once), just like `HashMap` allows one `null` key:

~~~java
Set<String> set = new HashSet<>();
System.out.println(set.add(null)); // true
System.out.println(set.add(null)); // false
System.out.println(set.size());    // 1
~~~

Do not generalize this rule to all `Set` implementations: for example, `Set.of(...)` does not accept `null`.

## 5. Keys That Look Identical Can Still Be Two Different Values

`String.equals` compares exact UTF-16 content: differences in letter case, whitespace, combining marks, or invisible characters can all become **different keys**. Example:

~~~java
Map<String, Integer> prices = new HashMap<>();
prices.put("Café", 120);
System.out.println(prices.get("café"));       // null: different case
System.out.println(prices.get("Cafe\u0301")); // null: different Unicode representation
~~~

There is no implicit normalization during `put`/`get`. If an application's identifier truly **does not distinguish** a certain difference, build a canonical key using the **same rule** on both the write path and the read path. For example, technical codes might use `strip().toLowerCase(Locale.ROOT)` if policy allows; unifying canonical Unicode representations may require `Normalizer.Form.NFC`. However, tokens, signatures, or case-sensitive codes **must not be modified arbitrarily**. The lesson "Key Normalization vs. Preserving Display Text" covers designing separate storage for labels and keys and handling post-normalization collisions.

When results are unexpected, check `equals` directly between the stored key and the lookup key, inspect whitespace/invisible characters, and use `containsKey` if the value can be `null`. `intern` does not resolve content differences.

## 6. Why Is String Safer Than Mutable Keys?

`HashMap`/`HashSet` require that the values participating in an element's `equals` and `hashCode` **do not change while it remains in the collection**. If a custom mutable object is used as a key and the state used to compute its hash is modified, a subsequent `get` or `remove` may fail to find the previous entry; similarly `HashSet.contains` may fail. The issue comes from violating the key's contract, not from a random bug in the map.

`String` eliminates that class of risk because its content is immutable. A reference variable can still be reassigned to a new string, which does not affect the old stored object.

### 6.1. StringBuilder and Mutable Objects

`StringBuilder` can have its content modified with `append`/`replace` and does not override `equals/hashCode` to compare by content like `String`. Therefore, using a `StringBuilder` object as a map key usually fails to express value-based comparison properly. Create a `String` snapshot if a content-based key is needed:

~~~java
StringBuilder builder = new StringBuilder("part");
String safeKey = builder.toString();

Map<String, Integer> map = new HashMap<>();
map.put(safeKey, 5);
builder.append("-updated");

System.out.println(map.get("part")); // 5
~~~

The data in the builder changes, but `safeKey` still holds `"part"`. If a key must combine multiple fields, prefer an **immutable value object** with consistent `equals/hashCode` (for example, a `record` whose components are also immutable) rather than ad-hoc string concatenation that introduces delimiter ambiguity.

### 6.2. Even an Immutable String Can "Fail" Due to Input Normalization

Immutability only guarantees that the key **does not mutate after being placed into the collection**. It does not guarantee that all inputs meant to be treated as one key already share the same representation. For instance, if `put` uses `input.strip()` while `get` uses the raw input, the application will still miss lookups. Centralize the policy in a single function such as `canonicalKey(raw)` and use it on both paths.

## 7. Performance, Ordering, Concurrency, and Collection Choice

- **Average complexity:** with a well-distributed hash and reasonable table size, `HashMap.get`/`put` and `HashSet.contains`/`add` typically achieve roughly **O(1) average** time. Under high collisions or resizing, cost can increase; O(1) is never guaranteed for all operations or all inputs.
- **String hash computation cost:** computing the initial `hashCode` depends on string length; some JDKs cache a `String`'s hash after the first computation. When comparing keys with the same hash, `equals` may need to compare code units until a difference is found.
- **Memory and intern:** you do not need `intern()` to use strings as keys. `HashMap` and `HashSet` already handle identical content via `equals/hashCode`; calling `intern` in bulk can create memory management pressure and does not solve business canonicalization.
- **Iteration order:** `HashMap` and `HashSet` **make no guarantees** about insertion order or sorted order. Use `LinkedHashMap`/`LinkedHashSet` when insertion order must be preserved; use `TreeMap`/`TreeSet` when sorting is genuinely required (note that the comparator governs key identity in sorted structures).
- **Concurrency:** `String` immutability **does not make `HashMap` or `HashSet` thread-safe**. Multiple threads modifying a collection require synchronization or an appropriate concurrent structure such as `ConcurrentHashMap` / `ConcurrentHashMap.newKeySet()`; these concurrent structures have their own rules, such as disallowing `null` keys and values.
- **Choosing the key representation:** if the key domain is a finite enum, `EnumMap`/`EnumSet` are often a better fit than string keys. If the domain involves normalization rules or multiple fields, defining an explicit key type reduces bugs compared to scattering `trim` and `toLowerCase` calls throughout the codebase.

## 8. Standalone Java 17+ Example, Independent of Iteration Order

Save the following in **`StringHashCollectionsDemo.java`**:

~~~java
import java.text.Normalizer;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public class StringHashCollectionsDemo {
    public static void main(String[] args) {
        String a = new String("Java");
        String b = new String("Java");

        System.out.println("sameReference=" + (a == b));
        System.out.println("sameContent=" + a.equals(b));
        System.out.println("sameHash=" + (a.hashCode() == b.hashCode()));

        Map<String, Integer> scores = new HashMap<>();
        scores.put(a, 10);
        scores.put(b, 20);
        scores.put("java", 30);
        System.out.println("mapSize=" + scores.size());
        System.out.println("JavaValue=" + scores.get("Java"));
        System.out.println("lowercaseValue=" + scores.get("java"));

        Set<String> unique = new HashSet<>();
        System.out.println("addFirst=" + unique.add(a));
        System.out.println("addEqual=" + unique.add(b));
        System.out.println("addDifferentCase=" + unique.add("java"));
        System.out.println("setSize=" + unique.size());

        System.out.println("hashCollision="
                + ("FB".hashCode() == "Ea".hashCode()));
        Map<String, String> collisions = new HashMap<>();
        collisions.put("FB", "first");
        collisions.put("Ea", "second");
        System.out.println("collisionMapSize=" + collisions.size());
        System.out.println("collisionValues="
                + collisions.get("FB") + "/" + collisions.get("Ea"));

        String original = "\u00E9";
        String decomposed = "e\u0301";
        System.out.println("unicodeEquals=" + original.equals(decomposed));
        String normalizedKey = Normalizer.normalize(
                original, Normalizer.Form.NFC);
        String normalizedLookup = Normalizer.normalize(
                decomposed, Normalizer.Form.NFC);
        Map<String, String> normalizedMap = new HashMap<>();
        normalizedMap.put(normalizedKey, "matched");
        System.out.println("unicodeLookup="
                + normalizedMap.get(normalizedLookup));

        StringBuilder builder = new StringBuilder("part");
        String snapshot = builder.toString();
        Map<String, Integer> stable = new HashMap<>();
        stable.put(snapshot, 5);
        builder.append("-updated");
        System.out.println("snapshotLookup=" + stable.get("part"));

        Map<String, Integer> nullable = new HashMap<>();
        nullable.put("pending", null);
        System.out.println("nullValue=" + (nullable.get("pending") == null));
        System.out.println("containsNullValueKey="
                + nullable.containsKey("pending"));
    }
}
~~~

Compile and run from the directory containing the file:

~~~bash
javac --release 17 StringHashCollectionsDemo.java
java StringHashCollectionsDemo
~~~

**Exact stdout:**

~~~text
sameReference=false
sameContent=true
sameHash=true
mapSize=2
JavaValue=20
lowercaseValue=30
addFirst=true
addEqual=false
addDifferentCase=true
setSize=2
hashCollision=true
collisionMapSize=2
collisionValues=first/second
unicodeEquals=false
unicodeLookup=matched
snapshotLookup=5
nullValue=true
containsNullValueKey=true
~~~

The program **does not print the entire `HashMap` or `HashSet` directly**, because iteration order of elements/entries is not a guaranteed contract. Key-based lookups, sizes, `add` booleans, and `equals` comparisons produce completely predictable output.

## 9. Process for Designing Reliable String Keys

1. **Define what counts as the same key** according to business rules: is it case-sensitive, should whitespace be stripped, and should canonically equivalent Unicode be treated as equal?
2. **Choose canonicalization** (if needed) and apply it consistently **before `put`/`add` and before `get`/`contains`/`remove`**.
3. **Use `String` or an immutable key type**, never relying on object identity or mutable state.
4. **Choose the collection based on requirements**: `HashMap` for key → value; `HashSet` for membership/uniqueness; ordered or concurrent variants when truly needed.
5. **Test special input pairs**: same content with different objects, different case, leading/trailing spaces, zero-width characters, precomposed/decomposed Unicode, hash collisions, and `null` where allowed.

An API should express its policy clearly. For example, if technical identifiers allow stripping leading/trailing whitespace and case-insensitivity:

~~~java
import java.util.Locale;

static String canonicalKey(String raw) {
    if (raw == null) {
        throw new IllegalArgumentException("key must not be null");
    }
    return raw.strip().toLowerCase(Locale.ROOT);
}
~~~

This is an **illustration of a specific policy**, not a standard rule for every kind of key. Do not use it for values where spaces or letter case are defined as meaningful. If applying Unicode normalization, add `Normalizer.normalize(...)` to the policy after deciding the processing order, then verify with real input data.

## 10. Self-Check Questions

1. Why do two variables referencing **two objects** `new String("x")` still create only **one** entry in a `HashMap`? → Because `equals` is true and the corresponding `hashCode` values are equal.
2. Do two strings with the same `hashCode` have to be the same key? → **No**. Collisions can still hold two distinct keys, such as `"FB"` and `"Ea"`.
3. What does `HashSet.add(s)` returning `false` mean? → An equivalent element according to `equals` already exists (assuming valid hash/equals contracts for the elements).
4. Does `String` immutability guarantee `HashMap` is safe when multiple threads modify it concurrently? → **No**; thread safety is a property of the collection and synchronization strategy.
5. Why might typing `"é"` sometimes fail to match on lookup? → It may use a different Unicode representation; a consistent normalization rule must be defined and applied if business logic wants them treated as the same.
6. Why does `map.get(key) == null` not necessarily mean the key is absent? → A `HashMap` can map a key to a `null` value; check `containsKey` when you need to distinguish the two.

**Remember:** `String` works well as a key/element in hash-based structures because it is **immutable** and implements `equals/hashCode` based on **string content**. `HashMap` manages mappings and `HashSet` manages uniqueness; both follow string comparison rules on the exact values provided without normalizing data automatically.

## References

- [Java SE 17 — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): `equals`, `hashCode`, `isEmpty`, `strip`.
- [Java SE 17 — Object](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html): the `equals` and `hashCode` contract.
- [Java SE 17 — HashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html): key equivalence, null handling, performance, ordering, and concurrency issues.
- [Java SE 17 — HashSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html): membership, `add`, hashing, and ordering.
- [Java SE 17 — Normalizer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html): NFC/NFD and canonical equivalence.
