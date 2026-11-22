# TreeSet and TreeMap Use Comparison to Identify Equivalent Keys

## 1. What to understand first: ordering and “duplicate keys” share a single rule

In Java, `TreeSet<E>` and `TreeMap<K,V>` are **sorted** data structures based on **natural ordering** (`Comparable`) or a **comparator** (`Comparator`). That comparison does not only decide whether an element comes before or after another; it also decides whether two keys are considered **equivalent for storage and lookup**.

Core rule:

> For two valid keys `a`, `b` in the same ordered structure, `compare(a, b) == 0` means the structure treats them as **one equivalent key**.

Here `compare` is `comparator.compare(a,b)` if the structure has a comparator; or the result of natural ordering via `Comparable.compareTo` if no comparator is passed.

This can be completely different from `a.equals(b)`:

- `TreeSet` does not store two elements for which the comparator evaluates to `0`; `add` on the second element returns `false`.
- `TreeMap` treats two keys with a comparison result of `0` as the same key position; `put` with the second key updates **the entry's value** instead of increasing the number of keys.
- `contains`, `containsKey`, and `get` may treat a query object that is **different according to `equals`** as an existing key if the comparison yields `0`.
- Standard `HashSet` and `HashMap` rely on `hashCode` and `equals`, so they can produce different results from `TreeSet`/`TreeMap` on the same data.

The most important part of this lesson is distinguishing **equivalence by comparison** from **equality by `equals`**, knowing when the two relations need to be consistent, and understanding the consequences if they differ.

## 2. Key-location mechanism in an ordered tree

Imagine `TreeMap` storing a balanced search tree structure, typically a red-black tree. When adding or searching for a key `query`, the structure uses comparison against the key of the node being examined:

| Result of comparing query key with node key | Meaning for search |
| --- | --- |
| Negative value | The query key stands **before** the node key; continue searching the appropriate branch ahead (according to tree order). |
| `0` | The two keys are **equivalent according to comparison order**; the logical key the structure is looking for has been found. |
| Positive value | The query key stands **after** the node key; continue searching the appropriate branch behind. |

This is a conceptual diagram, not the concrete source code of `TreeMap`:

```text
search(query):
    node = root
    while node != null:
        result = compare(query, node.key)

        if result < 0:
            node = node.left
        else if result > 0:
            node = node.right
        else:
            return FOUND(node)  // result == 0: key equivalence
    return NOT_FOUND
```

For `TreeSet`, the deciding factor is how **elements** are compared; for `TreeMap`, it is how **keys** are compared. These two structures **do not use `hashCode` to determine position in the tree**. Nor do they require every pair of distinct keys to have distinct hash codes.

For example, with a comparator that only checks names case-insensitively: `"Java"` and `"JAVA"` both reside at one key position because `compare("Java","JAVA") == 0`, even though their `String.equals` returns `false`.

### The sign of `compare` is what matters

According to the `Comparator`/`Comparable` contract, negative, `0`, and positive results represent ordering. You must not require exact `-1` or `1`; a valid comparator can return any negative/positive integer. Writing `if (compare(a,b) == -1)` is a misinterpretation of the contract. Write `result < 0`, `result == 0`, or `result > 0`.

## 3. Comparison with HashSet and HashMap

| Structure | What is used to guide lookup | What decides duplicate keys/elements |
| --- | --- | --- |
| `HashSet<E>` | `hashCode()` of the element | Equality by `equals` (and same-reference check when appropriate) |
| `HashMap<K,V>` | `hashCode()` of the key | Equality by `equals` of the key |
| `TreeSet<E>` | `Comparable` or `Comparator` | Comparison result `0` |
| `TreeMap<K,V>` | `Comparable` or `Comparator` | Comparison result `0` of the key |

**Two points to keep separate:**

1. Matching hashes **do not prove** two keys are equal; a hash structure still has to compare for equality.
2. For an ordered tree, `compare(a,b) == 0` is **the condition for recognizing the same key under the sorting policy**, even though `a.equals(b)` may be false.

If the comparator “looks at” fewer attributes than `equals`, objects that are distinct according to `equals` may be merged into one key. If the comparator distinguishes objects that `equals` treats as equal, the tree may keep two entries that a `HashSet` merges into one.

Java recommends that the ordering used in a sorted set/map be **consistent with `equals`** so that the structures satisfy general `Set`/`Map` expectations. However, the API still permits an inconsistent comparator: in that case, ordered operations **still have a deterministic mechanism**, but the “duplicate element” outcome may be surprising or fail to follow the general contract based on `equals`.

## 4. Classic example: case-insensitive strings

`String.equals` is case-sensitive, whereas `String.CASE_INSENSITIVE_ORDER` is a comparator that sorts case-insensitively following the rules of `String.compareToIgnoreCase`.

Therefore:

```java
String a = "Java";
String b = "JAVA";

boolean sameByEquals = a.equals(b); // false
boolean sameByComparator =
        String.CASE_INSENSITIVE_ORDER.compare(a, b) == 0; // true
```

These are only illustrative expressions inside a method, not a standalone program. If you create:

```java
TreeSet<String> names =
        new TreeSet<>(String.CASE_INSENSITIVE_ORDER);

names.add("Java"); // true
names.add("JAVA"); // false
```

`TreeSet` keeps only one element because the second addition is recognized as a duplicate according to the comparator. When querying `names.contains("jAvA")`, the result is `true` even though no exact string `"jAvA"` was added. The condition is that the comparator considers this query equivalent to the existing key.

With `TreeMap`:

```java
TreeMap<String, Integer> counts =
        new TreeMap<>(String.CASE_INSENSITIVE_ORDER);

counts.put("Java", 1);
counts.put("JAVA", 2);
```

The structure has only **one entry**, and the value associated with the equivalent key is updated to `2`. In Java's `TreeMap`, the key object of the existing entry is retained when updating with a comparator-equivalent key; thus, in the example, the key seen from `firstKey()` is still `"Java"`, while `get("java")` returns `2`. Do not rely on adding a key with different casing to change the spelling of the stored key; if business logic needs a normalized key, normalize it before adding.

### When is this a reasonable policy?

Permissible cases: a search keyword, labels explicitly specified as case-insensitive, or a set of names under a custom policy.

Cases requiring consideration: product codes, discount codes, accounts, external identifiers, and multilingual Unicode strings. A case-insensitive comparator **is not synonymous** with comprehensive Unicode normalization, diacritic stripping, or locale-specific collation. The system's equality policy must be specified beforehand.

## 5. Another example: BigDecimal has natural ordering inconsistent with equals

`BigDecimal.compareTo` compares **numeric value**, whereas `BigDecimal.equals` also considers **scale** (with representations of different scales, it may treat them as different).

For example:

```java
BigDecimal x = new BigDecimal("2.0");
BigDecimal y = new BigDecimal("2.00");

System.out.println(x.compareTo(y)); // 0
System.out.println(x.equals(y));    // false
```

This is a snippet inside a method with `java.math.BigDecimal` imported. The two numeric values are equal under natural ordering yet **different according to `equals`**. Consequently:

- `TreeSet<BigDecimal>` uses natural ordering and keeps only one element for `2.0` and `2.00`.
- `HashSet<BigDecimal>` relies on `equals`/`hashCode`, so it keeps both.
- `TreeMap<BigDecimal, V>` treats these two numbers as one sorted key; `HashMap<BigDecimal, V>` treats them as two distinct keys.

This is an **intentional API characteristic**, not a bug in `TreeSet` or `HashSet`. When choosing them as keys, you must decide for yourself whether the data needs to distinguish scale.

If the business domain considers every representation with the same numeric value to be a single unique value, you can consider normalizing the `BigDecimal` representation before storing it into different collections (for example, `stripTrailingZeros` if appropriate for the policy). However, `stripTrailingZeros` can change the scale representation and display format, so requirements for currency, formatting, and data representation must be checked. Do not assume this normalization is always safe for every domain.

## 6. Standalone runnable Java 17+ program

The program below observes four scenarios simultaneously:

1. `TreeSet` and `TreeMap` use a case-insensitive comparator, so `"Java"` and `"JAVA"` occupy only one key.
2. A `HashSet` of strings distinguishes those two representations.
3. `BigDecimal` has `compareTo == 0` but `equals == false`.
4. A comparator that checks only age causes two different `Person` instances to be treated as equivalent; adding the `name` criterion produces a better distinguishing order for the example.

Save as `TreeKeyEquivalenceDemo.java`:

```java
import java.math.BigDecimal;
import java.util.Comparator;
import java.util.HashSet;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

public class TreeKeyEquivalenceDemo {
    record Person(String name, int age) {}

    public static void main(String[] args) {
        String a = "Java";
        String b = "JAVA";

        Set<String> sortedNames =
                new TreeSet<>(String.CASE_INSENSITIVE_ORDER);
        System.out.println("TreeSet add Java: " + sortedNames.add(a));
        System.out.println("TreeSet add JAVA: " + sortedNames.add(b));
        System.out.println("TreeSet size: " + sortedNames.size());
        System.out.println("TreeSet first: " + sortedNames.iterator().next());
        System.out.println("TreeSet contains jAvA: "
                + sortedNames.contains("jAvA"));
        System.out.println("String equals: " + a.equals(b));

        Set<String> hashedNames = new HashSet<>();
        hashedNames.add(a);
        hashedNames.add(b);
        System.out.println("HashSet size: " + hashedNames.size());

        TreeMap<String, Integer> scores =
                new TreeMap<>(String.CASE_INSENSITIVE_ORDER);
        System.out.println("TreeMap first put old: "
                + scores.put("Java", 1));
        System.out.println("TreeMap second put old: "
                + scores.put("JAVA", 2));
        System.out.println("TreeMap size: " + scores.size());
        System.out.println("TreeMap firstKey: " + scores.firstKey());
        System.out.println("TreeMap get java: " + scores.get("java"));

        BigDecimal x = new BigDecimal("2.0");
        BigDecimal y = new BigDecimal("2.00");
        System.out.println("BigDecimal compareTo: " + x.compareTo(y));
        System.out.println("BigDecimal equals: " + x.equals(y));

        Set<BigDecimal> sortedNumbers = new TreeSet<>();
        sortedNumbers.add(x);
        sortedNumbers.add(y);
        Set<BigDecimal> hashedNumbers = new HashSet<>();
        hashedNumbers.add(x);
        hashedNumbers.add(y);
        System.out.println("BigDecimal TreeSet size: "
                + sortedNumbers.size());
        System.out.println("BigDecimal HashSet size: "
                + hashedNumbers.size());

        Person an = new Person("An", 20);
        Person binh = new Person("Binh", 20);

        Comparator<Person> byAge =
                Comparator.comparingInt(Person::age);
        TreeSet<Person> sameAgeSet = new TreeSet<>(byAge);
        sameAgeSet.add(an);
        sameAgeSet.add(binh);

        System.out.println("Person equals: " + an.equals(binh));
        System.out.println("age-only compare: " + byAge.compare(an, binh));
        System.out.println("age-only TreeSet size: "
                + sameAgeSet.size());
        System.out.println("age-only contains Binh: "
                + sameAgeSet.contains(binh));

        Comparator<Person> byAgeThenName =
                Comparator.comparingInt(Person::age)
                          .thenComparing(Person::name);
        TreeSet<Person> distinctPersons =
                new TreeSet<>(byAgeThenName);
        distinctPersons.add(an);
        distinctPersons.add(binh);
        System.out.println("age+name TreeSet size: "
                + distinctPersons.size());
    }
}
```

Compile and run commands (JDK 17+):

```bash
javac -encoding UTF-8 TreeKeyEquivalenceDemo.java
java TreeKeyEquivalenceDemo
```

Exact output of the program:

```text
TreeSet add Java: true
TreeSet add JAVA: false
TreeSet size: 1
TreeSet first: Java
TreeSet contains jAvA: true
String equals: false
HashSet size: 2
TreeMap first put old: null
TreeMap second put old: 1
TreeMap size: 1
TreeMap firstKey: Java
TreeMap get java: 2
BigDecimal compareTo: 0
BigDecimal equals: false
BigDecimal TreeSet size: 1
BigDecimal HashSet size: 2
Person equals: false
age-only compare: 0
age-only TreeSet size: 1
age-only contains Binh: true
age+name TreeSet size: 2
```

### Analyzing surprising results

**`TreeSet add JAVA: false`:** does not mean the string `"JAVA"` is already in the tree by exact reference or exact `String.equals`. It means there is already an element equivalent to `"JAVA"` according to the comparator. Because the comparator is case-insensitive, `"Java"` is enough for the second addition to be considered a duplicate.

**`TreeMap second put old: 1`:** when adding `"JAVA"`, the map finds the comparator-equivalent key `"Java"`. It returns the old value `1` and updates it to `2`. The number of entries remains `1`; `get("java")` looks up using the same comparator and receives `2`.

**`BigDecimal TreeSet size: 1` vs `HashSet size: 2`:** `BigDecimal`'s natural ordering treats the two numeric representations as equivalent; its `equals` and hash code distinguish scale.

**`age-only contains Binh: true`:** `Person("An",20)` and `Person("Binh",20)` are different according to `record.equals`, yet the comparator checks only age, yielding `0`. Although `binh` is not stored as a separate element, the query `contains(binh)` is treated as finding an equivalent key, `an`.

**`age+name TreeSet size: 2`:** adding `name` as a secondary criterion is sufficient to distinguish the two objects in the example dataset. In a real domain, you must check **all fields that determine `equals`**; `age + name` is only consistent with `equals` if that type's equality rule also uses the corresponding two fields.

## 7. What does “consistent with equals” mean precisely?

A `Comparator` or natural ordering is said to be **consistent with `equals`** when, for the valid objects under consideration:

```text
compare(a, b) == 0   if and only if   a.equals(b) == true
```

This is a necessary condition between **the set of equivalent pairs under comparison** and **the set of equal pairs under `equals`**. It is stronger than requiring the comparator merely to sort elements in a reasonable order.

There are two ways to go wrong:

1. **Over-merging comparator:** `compare(a,b) == 0` while `a.equals(b) == false`. For example, comparing `Person` only by age. `TreeSet` loses the ability to keep multiple people of the same age; `TreeMap` may overwrite another person's data.
2. **Over-splitting comparator:** `a.equals(b) == true` while `compare(a,b) != 0`. For example, a class whose `equals` uses only `userId`, yet the comparator also uses a display name attribute that may differ. `TreeSet` may retain two elements that are equal under `equals`, violating the general expectation of a `Set`.

An age-only comparator can still be valid for numerical ordering of ages; **what is wrong is using it to identify `Person` identity** in an application that defines people by other data.

If the goal is at most one person per age, an age-based comparator may reflect a **different business key rule**. In that case, consider representing the `age` key directly and storing the person value in a `TreeMap<Integer, Person>`, instead of using `TreeSet<Person>` and misleading readers into thinking two `Person` objects are equal.

### Relationship to the general Map/Set contract

The `Set`/`Map` interfaces describe presence/duplicate keys in terms of `equals`. However, `TreeSet`/`TreeMap` are designed around a comparator or natural ordering. Java documentation recommends that comparison be **consistent with `equals`** if you want the implementation to fully satisfy those contract expectations.

Inconsistency **does not mean** Java is forced to throw an error. Most operations still run and behave strictly according to the comparator, producing observable results like the example. The risk is primarily **semantic**, especially when switching back and forth between ordered sets/maps and hash-based structures.

## 8. Conditions for a comparator not to break the tree structure

Not every function returning an integer is a valid comparator. Java requires properties corresponding to a consistent ordering. The core principles:

- **Antisymmetry by sign:** `sign(compare(a,b)) == -sign(compare(b,a))`. Swapping the two objects must invert the before/after relation, or both return `0`.
- **Transitivity of order:** if `compare(a,b) > 0` and `compare(b,c) > 0`, then `compare(a,c) > 0`; similarly for the negative direction.
- **Consistency when comparing as `0`:** if `compare(a,b) == 0`, the sign of comparing `a` with an object `z` must match the sign of comparing `b` with `z`. Otherwise, two objects treated as one key have different relative positions with respect to other keys.
- **Stability while a key resides in the tree:** data serving as the sorting basis should not change after insertion unless the tree is updated accordingly.

For example, a comparator written like this is dangerous:

```java
Comparator<Integer> bad = (a, b) -> a - b;
```

Integer (`int`) subtraction can **overflow**, return the wrong sign, and break transitivity of order. Use:

```java
Comparator<Integer> good = Integer::compare;
```

The two snippets above are illustrative expressions inside a method with `java.util.Comparator` imported. For complex objects, use `Comparator.comparing`, `comparingInt`, `thenComparing`, `nullsFirst`/`nullsLast` when aligned with policy; they make code expressive and reduce the chance of writing faulty rules.

Another severe bug is a **random or time-dependent comparator**. If the same pair of keys yields a different order each time they are compared, the tree cannot maintain the assumptions needed to locate/place data accurately.

## 9. Designing a comparator that matches domain identity

Before choosing `TreeSet` or `TreeMap`, define “two equivalent keys” in your business language.

### Case A: the key is a case-sensitive string

If codes are case-sensitive, use the natural ordering of `String`. For the two strings `"Java"` and `"JAVA"`, `String.compareTo` does not return `0`, and `String.equals` is also `false`. In this case, ordering and equality are consistent strictly according to the `String` type.

### Case B: case-insensitive username

If usernames are case-insensitive, you can use an appropriate comparator to perform operations in a `TreeMap<String,V>`, but the entire system must remain aware that `String.equals` is still case-sensitive. If a `HashMap<String,V>` is used at the same time, duplicate-key behavior will differ.

Another design is to **normalize keys** according to a published policy (for example, lowercase within a valid ASCII character domain), store the normalized key in a value object with corresponding `equals`/`hashCode`, and use a comparator consistent with that exact relation. This approach gives hash and sorted structures the same notion of identity when the application truly requires it.

With multilingual Unicode text, do not assume a rule like `equalsIgnoreCase` or `toLowerCase(Locale.ROOT)` handles all cases of Unicode case folding, canonical combining forms, accents, or locales. Comparison and canonicalization rules must be designed, documented, and tested.

### Case C: multi-field objects

If a domain record `Person(name, age)` uses `equals` across both components, a comparator checking `age` then `name` will fit the **example using non-null String and int** provided the comparator and `equals` both distinguish identical names the same way. However, if another component is added to the record, the auto-generated `equals` changes while an un-updated comparator does not, and consistency can be lost.

Instead of “sorting by age” with a comparator as a unique key, consider using `TreeMap<Integer, List<Person>>` when business logic wants to **group multiple people by age**, or using a unique key with sufficient criteria via `thenComparing` when you want a `TreeSet<Person>` that does not merge people.

## 10. Lookups, range bounds, and first/last all obey the comparator

`TreeSet` and `TreeMap` belong to the family of ordered structures, so the following operations also rely on comparison rules:

- `first()`/`last()` of `TreeSet` and `firstKey()`/`lastKey()` of `TreeMap` retrieve extremes **according to the comparator or natural ordering**, not insertion time or `equals`.
- `lower`, `floor`, `ceiling`, `higher` find the element immediately before / at-or-before / at-or-after / after in order, with inclusive or exclusive boundary rules.
- `subSet`, `headSet`, `tailSet` and `subMap`, `headMap`, `tailMap` define key ranges using **comparator ordering**. These views are backed by the underlying structure and reflect permitted changes.
- `contains`/`containsKey` checks whether an element/key exists that is **equivalent by comparison**, rather than necessarily calling `equals` to confirm as hash structures do.

For a case-insensitive comparator, a range boundary query `"JAVA"` can be equivalent to the stored key `"Java"`. Whether a range endpoint is included depends on the overload and inclusive/exclusive flag, while a comparison result of `0` determines that they belong to the same ordering mark.

### Complexity and usage needs

`TreeMap` guarantees `O(log n)` time for `containsKey`, `get`, `put`, and `remove`, assuming the cost of a single comparison is treated as constant. `TreeSet` has guaranteed `O(log n)` time for `add`, `remove`, and `contains` under the same assumption. If the comparator is expensive, actual time also depends on comparison cost.

`HashMap`/`HashSet` generally provide expected time close to `O(1)` with an appropriate hash distribution, but do not provide sorted order by a comparator. If you need ordered iteration, range queries, or finding adjacent elements, an ordered tree offers distinct capabilities.

## 11. Mutable keys, null, and errors in comparison

### 11.1. Keys mutated after insertion into the tree

For example, a `TreeSet<Person>` sorted by `person.age`. If you store a mutable `Person` object and then modify its age without removing and reinserting it, the tree's internal ordering remains built on the old value. Results of `contains`, `remove`, range queries, or iteration order may become erratic.

The same applies to `TreeMap` if a mutable key alters a field used by the comparator. **Tree structures do not automatically track changes inside key objects**. Prefer immutable keys; when a logical key must change, you generally have to remove the entry under the old key and re-add it under the new key.

### 11.2. Null and non-comparable keys

When using **natural ordering**, `TreeSet`/`TreeMap` generally do not accept `null` keys because they cannot be naturally compared, and may throw `NullPointerException`. With a custom comparator that handles `null` (for example, `Comparator.nullsFirst`) and an appropriate policy, `null` keys can be allowed in `TreeMap`/`TreeSet`.

`TreeMap` can allow `null` **values**, independent of the `null` key issue. When `get(key)` returns `null`, to distinguish between an absent key and a present key with a `null` value, use `containsKey(key)`.

If natural ordering is used and objects do not implement `Comparable` appropriately, or are not mutually comparable, tree operations may throw `ClassCastException`. A comparator should clearly define its type domain and not admit incompatible types into the structure.

### 11.3. Comparators with side effects

Do not let `compare` mutate key state, write to a database, call external services, or vary its result across calls. A structure may require multiple comparisons during a single operation, and there is no contract guaranteeing that the comparator is called only once per pair.

A comparator using environment-dependent attributes (timezone, mutable current locale, changing configuration state) also makes ordering unstable. Establish a consistent comparison policy for the lifetime of the structure; if the policy changes, rebuild the structure with the new comparator.

## 12. Common pitfalls

| Mistake | Observable impact | Solution |
| --- | --- | --- |
| Assuming `TreeSet` only deduplicates when `equals` is true | Distinct objects can be lost if the comparator returns `0`. | Check whether `compare(a,b) == 0` accurately reflects logical identity. |
| Using a comparator on only a single field like age | All objects of the same age are treated as one element, even if name/ID differ. | Add appropriate distinguishing criteria or use `TreeMap<Age,List<Person>>` to group. |
| Calling `TreeMap.put(k2,v2)` with a key having the same comparator rank and expecting a new entry | The old value is replaced; map size does not grow. | Specify key duplication; use sufficient key criteria. |
| Thinking `TreeSet` and `HashSet` always have the same element count on one dataset | `compare==0` may not correspond to `equals`. | Choose a consistent comparator or intentionally accept the difference. |
| Comparing only with `result == -1`/`result == 1` | Misinterprets valid comparator results returning an absolute value greater than 1. | Check negative/0/positive sign. |
| Writing a comparator with integer subtraction | Overflow can produce the wrong order and break the contract. | Use `Integer.compare`, `Long.compare`, or built-in comparators. |
| Comparator using mutable fields or depending on the clock | The tree may fail to find keys or iterate in the wrong order. | Use immutable keys and a stable comparison policy. |
| Using `String.CASE_INSENSITIVE_ORDER` for all Unicode strings while expecting locale-specific rules | May merge or separate data unexpectedly. | Define normalization/locale explicitly and test with real data. |
| Using `BigDecimal` and then being surprised when `TreeSet` and `HashSet` differ | `compareTo` ignores scale differences that `equals` takes into account. | Decide whether keys follow numeric value or representation; normalize when appropriate. |
| Expecting `hashCode` to affect `TreeMap` | The tree navigates by comparator; hashes do not decide branches. | Use the correct mental model of the collection's mechanism. |
| Changing the comparator after elements have been stored | The tree's ordering does not automatically update to the new policy. | Create a new structure with the new comparator and reload the data. |

## 13. Testing to confirm the contract and business policy

When designing a comparator for a custom key type, both **ordering** and **duplicate-key semantics** must be tested:

1. **Comparison sign:** if `compare(a,b) < 0`, then `compare(b,a) > 0`. Also check the `0` case and boundary values.
2. **Transitivity:** across multiple triples, if `a < b` and `b < c` by the comparator, then `a < c`. Triples involving comparator value `0` must also be consistent.
3. **Equivalence via comparator:** if `compare(a,b) == 0`, test querying `contains(b)`/`get(b)` after storing `a`; verify behavior matches business logic.
4. **Consistency with `equals`:** for pairs with the same ID, different ID, same secondary criteria, and different secondary criteria, compare both `compare==0` and `equals`. If the two relations differ, documentation must explicitly state why.
5. **Duplication behavior:** adding two keys that rank equal under the comparator in `TreeSet` must not increase size; `TreeMap.put` must update the corresponding value.
6. **Divergence from hash structures:** when identical semantics are expected, use the same data to compare size/keys between `TreeSet` and `HashSet`; if they differ, locate the pair causing the two relations to disagree.
7. **Mutable keys:** ensure attributes used for comparison are not modified while still in the tree. If there is an interface to change a key, test the workflow of removing the old key and adding the new key.
8. **Null and type boundaries:** test `null` policies, range endpoint values, Unicode characters, casing, and large/small numeric levels.
9. **Range operations:** test `floor`, `ceiling`, `subSet`/`subMap` with keys comparing as `0` to ensure boundaries are accurate.
10. **Cost and stability:** the comparator must be deterministic, free of I/O, and must not change its result for the same key state.

For critical domains, property-based tests can be used to generate many pairs/triples and test all ordering relation properties. A single passing example does not prove the entire comparator satisfies a valid contract.

## 14. Takeaways

`TreeSet` and `TreeMap` use **natural ordering or a `Comparator`** both to locate positions in the tree and **to confirm key equivalence via a comparison result of `0`**. This differs from `HashSet` and `HashMap`, which rely on the `equals`/`hashCode` contract. When `compare(a,b)==0` does not coincide with `a.equals(b)`, collections can yield different element counts and lookup results; classic examples are case-insensitive string comparison and `BigDecimal` values with different scales. Clearly define key identity, choose a comparator that satisfies that relation, ensure valid and stable ordering, prefer immutable keys, and test insertion, lookup, overwrite, and range-query behaviors.
