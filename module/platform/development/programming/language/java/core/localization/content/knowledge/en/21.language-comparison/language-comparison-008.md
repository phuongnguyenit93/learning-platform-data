# Comparator Inconsistent with equals in TreeSet or TreeMap

## 1. The Problem: Linguistic Comparison Differs from Data Identity

A multilingual application may need to sort labels in a natural order for readers—for example using `java.text.Collator` to sort accented words. Another part of the application needs to store each string as a **distinct identifier key**, even if they differ only by case or accents.

Those two needs are not synonymous:

- **Linguistic equivalence:** a `Collator` at `PRIMARY` can return `0` when comparing `"cafe"` and `"café"`.
- **Equality under `String.equals`:** `"cafe".equals("café")` returns `false` because their UTF-16 code unit sequences differ.
- **Key equality in `TreeSet`/`TreeMap`:** based on `Comparator.compare(a,b)==0`, **not necessarily on `equals`**.

That last point is critical. When using `TreeSet` to "both sort and deduplicate," you grant the comparator authority to decide what counts as a **duplicate**. When using `TreeMap`, the comparator decides whether a `put` call **creates a new key** or **updates an existing key's value**.

### Lesson Objectives

After completing this lesson, readers will be able to:

1. Describe the `compare(a,b)==0` rule and the *consistent with equals* condition.
2. Explain why `HashSet` and `TreeSet` can retain different element counts from the same sequence of strings.
3. Reproduce `TreeSet.add` returning false, `contains` returning true, and `remove` deleting a different spelling.
4. Reproduce `TreeMap.put` overwriting a value and understand why the original key is retained.
5. Distinguish the goal of **collation equivalence** from **Object/String identity**.
6. Apply a proper tie-breaker, or design a data model separating ID from display label.
7. Detect contract-violating comparators and the risk of mutating `Collator` after the tree holds data.
8. Write tests covering accents, case, Unicode normalization, locale, and transitivity.

## 2. Comparator.compare and Object.equals: Two Different Relations

### 2.1. What Does equals Answer?

For `String`, `equals(Object)` confirms whether two strings have identical contents across UTF-16 code units. For example:

```java
System.out.println("cafe".equals("café")); // false
System.out.println("CAFE".equals("cafe")); // false
```

These statements live inside a Java method. `HashSet<String>` and `HashMap<String,V>` use `hashCode` and `equals` to detect duplicates, so they retain `"cafe"`, `"café"`, and `"CAFE"` as three separate keys.

### 2.2. What Does compare Answer?

`java.util.Comparator<T>` returns an integer:

| Result | Meaning |
| --- | --- |
| `compare(a,b)<0` | `a` comes before `b` in the defined order. |
| `compare(a,b)==0` | `a` and `b` are equivalent in the defined order. |
| `compare(a,b)>0` | `a` comes after `b` in the defined order. |

The return value **does not have to** be strictly `-1`, `0`, or `1`. Check its sign when writing tests, without assuming every comparator returns only one of those three constants.

A valid comparator must preserve these properties:

- **Reflexive ordering relation:** `compare(a,a)==0`.
- **Antisymmetry of sign:** `sgn(compare(a,b)) == -sgn(compare(b,a))`.
- **Transitivity:** if `compare(a,b)>0` and `compare(b,c)>0`, then `compare(a,c)>0`.
- **Consistent equivalence classes:** if `compare(a,b)==0`, the comparisons of `a` and `b` against any `z` must have the same sign.

These conditions are distinct from whether the comparator is consistent with `equals`. A `Collator` can be a valid comparator while still calling two non-`equals` Strings linguistically equivalent.

### 2.3. What Exactly Is "Consistent with equals"?

An ordering is considered **consistent with equals** if for every pair of elements in the domain:

```text
compare(a, b) == 0  ⇔  a.equals(b)
```

That means both:

1. If two elements are `equals`, the comparator must return 0.
2. If the comparator returns 0, the two elements must be `equals`.

For `String`, `String.compareTo` is consistent with `String.equals`. For `Collator` at levels that relax accent and case distinctions, this **is not guaranteed**.

Being inconsistent with equals does not make a comparator **invalid**; it changes the semantics of storing and looking up elements in sorted collections using that comparator.

## 3. TreeSet: Distinct Elements May Be Treated as Duplicates

`TreeSet` stores elements according to **natural ordering** or the comparator passed to its constructor. When the comparator returns 0 between a new element and an existing element, `TreeSet` treats them as duplicates.

Example:

```java
Collator collator = Collator.getInstance(Locale.FRENCH);
collator.setStrength(Collator.PRIMARY);

TreeSet<String> set = new TreeSet<>(collator);
System.out.println(set.add("cafe")); // true
System.out.println(set.add("café")); // false
System.out.println(set.add("CAFE")); // false
System.out.println(set.size());      // 1
```

This is an illustrative snippet inside a Java method importing `Collator`, `Locale`, and `TreeSet`.

`PRIMARY` in the illustrated environment treats the three spellings as equal under Collator ordering. Yet `String.equals` distinguishes all three. Consequently, only the first added element is stored; the next two `add` calls **return false**.

### contains and remove Also Follow the Comparator

```java
System.out.println(set.contains("CAFE")); // true
System.out.println(set.remove("café"));   // true
System.out.println(set.size());           // 0
```

`set.contains("CAFE")` returns true even though the set only holds `"cafe"`. Likewise, `remove("café")` deletes the stored `"cafe"` element.

This makes the API **look contradictory** compared to ordinary `equals`-based comparison. However, `TreeSet` is obeying the duplicate relation provided by the comparator. Java documentation advises that an ordering should be consistent with equals if a sorted set must satisfy the general `Set` contract.

### Potential Logic Bugs

Suppose an application needs to retain all spellings of product names for search, yet writes:

```java
Set<String> names = new TreeSet<>(collator);
names.addAll(List.of("cafe", "café", "CAFE"));
```

Two spellings disappear from the set. If the application has no other place storing the raw data, that is **data loss**. If business logic intentionally collapses collation-equivalent words, that behavior can be acceptable, provided the policy for choosing the representative spelling is documented.

## 4. TreeMap: put Can Overwrite the Value of a Differently Spelled Key

`TreeMap` also uses its comparator to decide **whether two keys are equivalent**. Consider:

```java
TreeMap<String, Integer> map = new TreeMap<>(collator);

System.out.println(map.put("cafe", 10)); // null
System.out.println(map.put("café", 20)); // 10
System.out.println(map.put("CAFE", 30)); // 20
System.out.println(map.size());         // 1
```

The first call creates an entry; the next two are equivalent per the comparator and thus **update the value** of the existing entry. These results describe the example using a PRIMARY Collator.

After the three `put` calls:

- `map.get("Café")` can return `30`.
- `map.containsKey("CAFE")` can return true.
- `map.firstKey()` may still be `"cafe"`, the first spelling inserted.
- `map.size()` remains `1`.
- `map.keySet()` shows only the key stored for that equivalence class.

**A comparator does not return a normalized string.** It only compares two elements; TreeMap does not "normalize" `"CAFE"` into `"cafe"`. The value can change, while the initial key object is typically retained in the entry when `put` is called with an equivalent key.

### Return Value of Map.put

`put(k,v)` returns the previous value or `null` if there was no prior mapping. However, if the map permits `null` values, a `null` return alone does not prove the key was absent. When policy must prevent overwriting, define the duplicate relation clearly and check key/collision properly.

### Why Is This Bug Serious?

A system treating product-name spelling as an ID might:

- Accidentally overwrite product A's inventory count with product B's.
- Lose metadata for another translation.
- Delete an entry using a different spelling when the user thought they chose an independent key.
- Be unable to recover spellings that were never saved in the map.

Never use collation-equivalent keys as unique business IDs when the domain needs to keep records distinct.

## 5. Comparison with HashSet/HashMap

| Collection | Duplicate rule | With `"cafe"`, `"café"`, `"CAFE"` |
| --- | --- | --- |
| `HashSet<String>` | `hashCode/equals` | Three elements. |
| `HashMap<String,V>` | `hashCode/equals` | Three independent keys. |
| `TreeSet<String>`, Collator PRIMARY comparator | `compare==0` | May hold only one element. |
| `TreeMap<String,V>`, Collator PRIMARY comparator | `compare==0` | May hold only one entry, value updated. |
| `TreeSet<String>` by natural order | `String.compareTo==0` | Three elements, distinguished by UTF-16. |
| `TreeSet<String>` by Collator + natural-order tie-breaker | Linguistic priority, yet compare==0 only when String.equals | Three elements. |

If the requirement is **keeping all data while sorting for display**, there is no need to put the data into a TreeSet. A clean approach:

```java
Set<String> keys = new HashSet<>(incoming);
List<String> sorted = new ArrayList<>(keys);
sorted.sort(collator);
```

This is an illustrative snippet inside a Java method with `incoming` and `collator` declared. `List.sort` does not drop elements whose comparator returns 0. If stable display ordering is desired among collation-equal elements, add a tie-breaker.

## 6. Collator and Locale Distinction Levels

`Collator` is the `java.text` API for linguistic ordering. It depends on `Locale` and the JVM's locale data source. Its `strength` levels are:

| Level | General meaning | Caution when used for keys |
| --- | --- | --- |
| `PRIMARY` | Base letter differences; often ignores accents/case in some locales. | Can collapse many different Strings. |
| `SECONDARY` | Adds secondary differences, often related to accents. | May still collapse case differences. |
| `TERTIARY` | Adds tertiary differences, often including case. | Do not assume compare==0 always equals `String.equals`. |
| `IDENTICAL` | Strongest level in the API, inspects subtle differences. | Does not automatically prove consistency with `String.equals` across all Unicode strings/configs. |

These are general guidelines. **Which characters are treated as equivalent depends on locale**, collation data, and implementation. Never apply "PRIMARY ignores all accents in all languages" as a universal rule.

### Decomposition

`Collator.setDecomposition(Collator.CANONICAL_DECOMPOSITION)` enables canonical decomposition handling for composed/combining characters. Two representations such as `"\u00E9"` and `"e\u0301"` can become collation-equivalent, yet this neither changes `String.equals` behavior nor forces merging Unicode IDs in the database.

`NO_DECOMPOSITION`, `CANONICAL_DECOMPOSITION`, and related behaviors must be chosen by intent. **Normalization, collation equivalence, and String.equals are three different concepts.**

### Collator Is Not a Permanent Identification Algorithm

Locale data and collation algorithms can evolve across JDK/provider releases. If a system requires keys stable over many years, do not treat "current JDK `Collator.PRIMARY`" as a persistent ID storage contract without version control and a migration plan.

## 7. Fixing with a Tie-Breaker Consistent with equals

When the requirement is:

1. Prioritize linguistic order for users; **and**
2. Do not drop any `String` differing under `String.equals`,

build a two-tier comparator:

```java
Comparator<String> primary = collator::compare;

Comparator<String> safeOrder =
        primary.thenComparing(Comparator.naturalOrder());
```

This is an illustrative snippet inside a Java method with an existing `collator`, requiring import of `Comparator`.

`String.compareTo` is consistent with `String.equals`. When Collator returns 0, the secondary comparator decides order by UTF-16. When Collator does not return 0, linguistic order takes precedence.

With the same three strings, the sample program yields:

```text
distinct=[CAFE, cafe, café] size=3
```

### Why Does This Work?

For any two Strings `a` and `b`:

- If `collator.compare(a,b) != 0`, the composite comparator returns non-zero. The two strings cannot be treated as the same key.
- If Collator returns 0, the comparator falls back to `a.compareTo(b)`.
- `String.compareTo` returns 0 **if and only if** `String.equals` is true.
- Hence `safeOrder.compare(a,b)==0` iff `a.equals(b)`.

As long as each component comparator obeys the contract and stays unchanged throughout the tree's lifetime, the combined ordering remains consistent. This prioritizes collation while preserving every String spelling.

### Downside of the Tie-Breaker

The secondary order is **code-unit order**, not "natural to human readers" among words that Collator considers tied. Still, when a **deterministic order** is needed for tied entries, this is reasonable. Another tie-breaker may be chosen, provided it matches the type T's `equals` definition and upholds the comparator contract.

### Mistake: Forcing 1 on All Equal Pairs

```java
Comparator<String> broken = (a, b) -> {
    int result = collator.compare(a, b);
    return result == 0 ? 1 : result;
};
```

This is an **intentionally broken example**. It makes `compare(a,a)==1` and violates antisymmetry. TreeSet/TreeMap can fail sorted collection invariants. **Never fix duplicate collapsing by making a comparator always return non-zero.**

## 8. Fixing by Separating ID from Display Label

In real applications, a **person name / product name** is not always the ID.

Example structure:

```java
record Product(long id, String displayName) {}
```

A product has its own ID, and its name may collide with another product. A sound design:

- `Map<Long, Product>` preserves identity by ID.
- For display, build a `List<Product>` from map values and sort by `displayName` using Collator.
- If two names are collation-equivalent, tie-break by ID for deterministic ordering.
- Never use `displayName` alone as the sole comparator of a `TreeSet<Product>` and expect all IDs to be retained.

Illustrative snippet inside a Java method:

```java
Comparator<Product> displayOrder =
        Comparator.comparing(
                Product::displayName, collator::compare)
                .thenComparingLong(Product::id);
```

However, note carefully: `record Product(long id, String displayName)` generates a default `equals` based on **both ID and displayName**. The name-and-ID comparator in the example **may be inconsistent with the record's equals** if two Products had the same ID, different displayNames, yet Collator considered them equal.

If you must use `TreeSet<Product>` and require **consistent with equals**, you can:

- Design class `Product` with `equals/hashCode` based on ID if that is the business identity, then tie-break the comparator by ID; or
- With the default record, add an exact `String.compareTo(displayName)` comparison alongside ID in the tie-breaker; or
- Avoid using TreeSet as the source of truth; use a Map keyed by ID and a List for display.

**Principle:** there is no magical "tie-break field." You must know exactly what an object's `equals` represents.

## 9. When Inconsistency with equals Is Intentional

Not every TreeSet using Collator PRIMARY is a bug. For instance, a screen may only want one representative per group of words considered equivalent at search sensitivity. In that case, comparator-based uniqueness can be a **business specification**.

However, you must clearly answer:

1. Which fixed locale and strength define the equivalence class?
2. Which spelling is kept when two strings have compare==0?
3. Must all original spellings still be retained for audit/search?
4. When calling `remove("café")`, is deleting the representative `"cafe"` intentional?
5. When calling `put` with another spelling, is replacing the old entry's value allowed?
6. If the JDK/provider changes collation, must indexes be rebuilt and duplicates resolved?

If all records must be preserved while still grouping by collation, maintain a `Map<ID, Item>` storing originals plus a **group index** for queries, rather than using a spelling-dropping TreeSet as the sole data store.

Never call a TreeMap with a PRIMARY comparator a "Map indexing every original key" if in reality it stores only one entry per equivalence class.

## 10. Complete, Standalone Runnable Java 17+ Example

Create file **`ComparatorEqualsDemo.java`**:

```java
import java.text.Collator;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.TreeMap;
import java.util.TreeSet;

public class ComparatorEqualsDemo {

    public static void main(String[] args) {
        Collator collator = Collator.getInstance(Locale.FRENCH);
        collator.setStrength(Collator.PRIMARY);
        collator.setDecomposition(
                Collator.CANONICAL_DECOMPOSITION);

        String plain = "cafe";
        String accent = "caf\u00E9";
        String upper = "CAFE";

        System.out.println("compareCafe="
                + collator.compare(plain, accent));
        System.out.println("stringEquals="
                + plain.equals(accent));

        TreeSet<String> words = new TreeSet<>(collator);
        System.out.println("addCafe=" + words.add(plain));
        System.out.println("addAccent=" + words.add(accent));
        System.out.println("addUpper=" + words.add(upper));
        System.out.println("set=" + words
                + " size=" + words.size()
                + " containsUpper=" + words.contains(upper));

        TreeMap<String, Integer> scores =
                new TreeMap<>(collator);
        System.out.println("putFirst=" + scores.put(plain, 10));
        System.out.println("putSecond=" + scores.put(accent, 20));
        System.out.println("putThird=" + scores.put(upper, 30));
        System.out.println("map=" + scores
                + " size=" + scores.size()
                + " lookup=" + scores.get("Caf\u00E9"));

        Comparator<String> primary = collator::compare;
        Comparator<String> stableOrder =
                primary.thenComparing(Comparator.naturalOrder());

        TreeSet<String> distinct = new TreeSet<>(stableOrder);
        distinct.addAll(List.of(plain, accent, upper));
        System.out.println("distinct=" + distinct
                + " size=" + distinct.size());

        System.out.println("hashSetSize="
                + new HashSet<>(
                        List.of(plain, accent, upper)).size());

        System.out.println("removed=" + words.remove(accent)
                + " remaining=" + words.size());
    }
}
```

Compile and run with JDK 17+ in the file's directory:

```bash
javac -encoding UTF-8 ComparatorEqualsDemo.java
java ComparatorEqualsDemo
```

**Reference stdout with Java 17 and `Locale.FRENCH` at PRIMARY:**

```text
compareCafe=0
stringEquals=false
addCafe=true
addAccent=false
addUpper=false
set=[cafe] size=1 containsUpper=true
putFirst=null
putSecond=10
putThird=20
map={cafe=30} size=1 lookup=30
distinct=[CAFE, cafe, café] size=3
hashSetSize=3
removed=true remaining=0
```

Note: locale collation can vary when JDK/provider or CLDR data changes. The example was tested on a corresponding Java 17 environment; if a project asserts **exact character-for-character** stdout, pin the JDK and supported locale providers or test key invariants rather than snapshotting the entire output.

### Reading Stdout Piece by Piece

- `compareCafe=0` yet `stringEquals=false`: comparator and equals define equivalence differently.
- `addAccent=false` / `addUpper=false`: TreeSet does not add the other two spellings because the comparator considers them equal.
- `containsUpper=true`: lookup uses the comparator rather than requiring an exact original String.
- `putSecond=10` / `putThird=20`: the old value is replaced without adding a new key.
- `map={cafe=30}`: one entry is retained, with the first spelling as the key.
- `distinct=[CAFE, cafe, café] size=3`: tie-breaker retains all three distinct Strings.
- `hashSetSize=3`: HashSet uses equals and therefore retains all three.
- `removed=true remaining=0`: passing a different spelling in the same comparator equivalence group removes the stored element.

## 11. Never Mutate a Comparator After the Tree Holds Data

`Collator` is **mutable**. One can call:

```java
collator.setStrength(Collator.TERTIARY);
collator.setStrength(Collator.PRIMARY);
```

Once a `TreeSet`/`TreeMap` has been built and holds keys in one order, changing strength/decomposition or mutating data that the comparator depends on **does not automatically rebuild the tree**. Afterward, `contains/get/remove` operations and iteration may no longer match stored ordering assumptions.

Dangerous scenarios:

- Having multiple spellings at `TERTIARY`, then lowering to `PRIMARY` so they become equivalent while the tree still holds multiple nodes.
- A comparator relying on a mutable property of a key, such as a display name; editing the name after `add` "logically moves" the key without moving its node.
- A comparator depending on the default locale and the application calling `Locale.setDefault(...)`; comparison behavior can change between operations.
- Sharing a single `Collator` and changing `setStrength` across requests.

**Mitigation:** finalize comparator configuration before creating the collection; never mutate it during the collection's lifetime. When ordering rules must change, build a new collection from **the source data** and handle newly formed equivalence classes per defined policy.

`Collator` is not guaranteed thread-safe under arbitrary concurrent access/mutation. Never share a mutable Collator and change parameters per user request. Create or clone configurations within the needed scope and manage synchronization appropriately.

## 12. Common Mistakes

| Mistake | Consequence | Better practice |
| --- | --- | --- |
| Using `TreeSet<>(collator)` instead of `HashSet` just to sort | Silently alters uniqueness rules. | Keep HashSet and sort a List; or add a tie-breaker. |
| Assuming TreeSet must rely on `equals` | `contains/add/remove` can treat other spellings as the same element. | Understand compare==0 is the duplicate relation. |
| Using `TreeMap` by display name as an ID | Can overwrite values of differently named records that are collation-equal. | Use a stable ID as key. |
| Assuming Collator PRIMARY works identically in all languages | Collation rules depend on locale/provider. | Test specific locales. |
| Choosing `TERTIARY` and assuming it is always consistent with equals | Unicode decomposition/locale can still create equivalences differing from String.equals. | Use an equals-based tie-breaker. |
| Comparator returning 1 on equality | Violates comparator contract, including compare(a,a). | Use a valid secondary comparator. |
| Tie-breaking only by a non-unique priority | Distinct objects sharing a priority can still collapse. | Tie-break by a property preserving equals identity. |
| Using a name comparator for a record whose equals checks multiple fields | Comparator may be inconsistent with record equals. | Design identity clearly; check all fields. |
| Calling `Collator.setStrength` after inserting | Tree does not rebuild, lookups become unpredictable. | Build a new collection. |
| Using Collator to create canonical keys across JDK versions | Algorithms/locale data can change. | Define an explicit versioned canonicalization. |
| Using String natural order as linguistic UI order | UTF-16 order is not natural language. | Collator for display; natural order only as tie-breaker. |
| Confusing Unicode normalization with collation and equals | Merges or splits data against policy. | Define equivalence classes explicitly. |

## 13. Properly Testing Both Comparator Contract and Collection Behavior

A good test suite should verify separately:

| Test case | Data | Goal |
| --- | --- | --- |
| Collation equivalence | `"cafe"` / `"café"` | compare==0, equals false at selected strength/locale. |
| Case differences | `"CAFE"` / `"cafe"` | Verify how Collator handles case. |
| Unicode canonical equivalence | `"\u00E9"` / `"e\u0301"` | Verify normalization/decomposition. |
| TreeSet insert | Three spellings | `add`, `size`, retained elements. |
| TreeSet lookup/remove | Different spelling with compare==0 | Ensure `contains/remove` behavior is understood. |
| TreeMap overwrite | Three `put` calls in same collation class | Previous value returned and size does not grow. |
| Comparator tie-breaker | Collator + String natural | compare==0 iff equals on the test set. |
| Immutable comparator | Insert then keep configuration fixed | Tree maintains a stable order. |
| Locale/JDK | Locales supported by product | Watch for collation data differences. |
| Null/bad input | If permitted by API | Decide `nullsFirst/nullsLast` or reject null. |

### Testing Comparator Axioms

Verify:

```text
compare(a, a) == 0
sign(compare(a, b)) == -sign(compare(b, a))
if compare(a,b) > 0 and compare(b,c) > 0:
    compare(a,c) > 0
if compare(a,b) == 0:
    sign(compare(a,z)) == sign(compare(b,z))
```

This is **pseudocode**, not literal Java. When business logic requires consistency with equals, add:

```text
for every tested pair (a,b):
    (compare(a,b) == 0) == a.equals(b)
```

Use datasets with accents, case, whitespace, combining characters, emoji, and duplicate names to uncover bugs. A finite test set cannot prove all of Unicode, yet it catches blatantly broken comparator designs.

### Nulls and Supported Scope

`TreeSet` or `TreeMap` are not required to accept `null` for every comparator. Natural String comparison typically does not support null. If you intentionally wrap with `Comparator.nullsFirst(...)`, define data `equals`/identity and test it. Never accept null blindly just to "avoid errors," since a null key may indicate missing data that should be handled before insertion.

## 14. Self-Practice Exercises

**Exercise 1 — Reproduce the bug:** create a `Collator` with `Locale.FRENCH`, `PRIMARY`; add `"cafe"`, `"café"`, `"CAFE"` to a TreeSet. Print `add`, `size`, `contains`, `remove`. Compare with HashSet and explain every difference.

**Exercise 2 — TreeMap overwrite:** `put` the three spellings with values 10, 20, 30; print `size`, `firstKey`, `get("Café")`, and each `put` return value. Explain why that map cannot be relied upon to store three independent spellings.

**Exercise 3 — Proper tie-breaker:** build a comparator with Collator first, `String.compareTo` second. Write unit tests for pairs that differ under equals yet tie under Collator. Prove the new TreeSet retains all three spellings.

**Exercise 4 — Broken comparator:** build a comparator returning 1 whenever Collator returns 0. Test `compare(a,a)` and swapping `a/b` to observe contract violations. Fix with a natural-order tie-breaker rather than trying to "force" the tree to accept elements.

**Exercise 5 — ID-based model:** create two products with different IDs and the same displayName. Store in a Map by ID, sort a List by Collator + ID. If using a default record, analyze why an ID-based comparator can differ from the record's equals definition.

**Exercise 6 — Strength levels:** test `PRIMARY`, `SECONDARY`, `TERTIARY`, `IDENTICAL` on accented, cased, and combining pairs. Record the locale/JDK provider to explain differences without generalizing across all languages.

**Exercise 7 — Changing comparison rules:** on a small test collection, insert data with a TERTIARY Collator, then switch to PRIMARY. Observe ordering/duplicate skew; then build a new TreeSet with the new comparator from the original data source.

### Checklist

- [ ] Can state the definition of "consistent with equals."
- [ ] Know that TreeSet/TreeMap use `compare==0` for uniqueness, unlike HashSet/HashMap.
- [ ] Can explain `add=false`, `contains=true`, and `remove=true` with another spelling.
- [ ] Know that `TreeMap.put` replaces value when a key is comparator-equivalent.
- [ ] Distinguish locale-based `Collator` from `String.equals` and Unicode normalization.
- [ ] Use a valid tie-breaker when wanting both locale sorting and distinct Strings.
- [ ] Separate business IDs from display names when the data model requires it.
- [ ] Never mutate comparator/Collator after inserting into a sorted collection.
- [ ] Test comparator axioms, strength levels, and actual collection behavior.

**Conclusion:** `TreeSet` and `TreeMap` treat `compare(a,b)==0` as an identity relation inside the tree. If a linguistic `Collator` collapses different spellings, the collection can collapse them too. Clearly choose between **linguistic equivalence** and **equals/ID identity**; when you want both natural sorting and every distinct String preserved, use a tie-breaker consistent with equals or separate your source dataset from the display-sorting layer.
