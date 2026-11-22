# Comparator Inconsistent with `equals()` and the `Set` or `Map` Contract

## 1. The core issue: two ways to define “the same element”

In Java, `TreeSet<E>` and `TreeMap<K,V>` are ordered structures. They use **natural ordering** (`Comparable.compareTo`) or **an ordering specified by `Comparator.compare`** to search for and distinguish elements/keys. For two values `a` and `b`, they treat them as **equivalent by ordering** when:

```java
comparator.compare(a, b) == 0
```

This is the condition used to identify an equivalent position in the tree; it **does not necessarily match** `a.equals(b)`. Meanwhile, the `Set` and `Map` interfaces define element and key equality according to the `equals` contract (with appropriate `null` handling):

- `Set` must not contain two elements that are equal under `equals`.
- `Map` has each key unique under `equals`; writing again with the same logical key replaces that key's value.
- `TreeSet` and `TreeMap` use a comparison result of 0 to make equivalence decisions, so if a `Comparator` is inconsistent with `equals`, behavior in the tree may **fail to satisfy the general `Set` or `Map` contract**.

A comparator is called **consistent with `equals`** when, for every valid pair of elements in the comparison domain:

```text
comparator.compare(a, b) == 0    ⇔    a.equals(b) == true
```

The `⇔` symbol means “if and only if”: **both directions must hold**. Distinguish this from a comparator's basic requirement to maintain a consistent ordering (sign reversal, transitivity, and order-equivalent items behaving consistently against a third element). A `Comparator` can still define a valid internal ordering while being **inconsistent with `equals`**; the problem surfaces when it is used as the uniqueness rule of `TreeSet` or `TreeMap`.

According to Java documentation, tree structures still have behavior well-defined by the comparator even when the ordering is inconsistent with `equals`; however, in that case they can **violate the general contract of `Set` or `Map`**. This is an API semantics issue, not necessarily a runtime exception.

## 2. Two forms of inconsistency to distinguish

### Form A: `compare(a, b) == 0` while `!a.equals(b)`

Example: two strings `"cat"` and `"dog"` have the same length, yet different contents. A `Comparator` comparing only length:

```java
Comparator<String> byLength = Comparator.comparingInt(String::length);
System.out.println(byLength.compare("cat", "dog")); // 0
System.out.println("cat".equals("dog"));            // false
```

This is an illustrative snippet when placed inside a method with `java.util.Comparator` imported. With a `TreeSet` using `byLength`, the second string is not added as a new element because the comparator produces 0. The set can have size 1 even though `equals` treats the two strings as different; `contains("dog")` can be `true` even though the set actually holds `"cat"`.

With a `TreeMap` using the same comparator, `put("dog", value2)` can **overwrite the value** attached to key `"cat"`, because the map considers the two keys to have the same ordering rank. The stored key object typically remains the original key, while the value is updated.

In terms of the `Set` and `Map` contract, this is **erroneously merging distinct values**.

### Form B: `a.equals(b)` is `true` while `compare(a, b) != 0`

Suppose a `Ticket` class defines identity by `id`, yet the comparator prioritizes `priority` before `id`. Two tickets having the same `id="T7"` but different priorities are treated by `equals` as the same ticket, whereas the comparator distinguishes them.

`TreeSet` can hold **both tickets that are equal under `equals`** because the tree's comparison does not return 0. `TreeMap` can also contain two entries whose keys are `equals`, contrary to expectations from the `Map` interface. A `HashSet` or `HashMap` with proper `equals`/`hashCode` instead views them as the same element/key.

This is the opposite direction of the error: **erroneously splitting one logical value into multiple entries**.

| Condition on pair `a,b` | By `equals` | By comparator | Possible consequence in tree structure |
| --- | --- | --- | --- |
| `compare(a,b)==0`, `!a.equals(b)` | Different | Equivalent | `TreeSet` skips an element, `TreeMap` replaces another key's value |
| `a.equals(b)`, `compare(a,b)!=0` | Equal | Different position | `TreeSet` keeps two equal elements, `TreeMap` keeps two equal keys |
| `a.equals(b)`, `compare(a,b)==0` | Equal | Equivalent | Both mechanisms agree |
| `!a.equals(b)`, `compare(a,b)!=0` | Different | Different position | Both mechanisms agree |

The table above assumes the comparator still obeys the **ordering contract** and keys do not mutate while residing in the tree. A comparator violating transitivity or changing results over time can cause other severe issues beyond inconsistency with `equals`.

## 3. Java 17+ program illustrating both errors and how to fix them

Save the following full code as **`ComparatorContractDemo.java`**. It uses `record Word` (equality by string `text`) and `Ticket` (equality by `id`). The first part compares only length; the second part uses ordering by priority contrary to ticket identity.

```java
import java.util.*;

public class ComparatorContractDemo {
    record Word(String text) {}

    static final class Ticket {
        private final String id;
        private final int priority;

        Ticket(String id, int priority) {
            this.id = Objects.requireNonNull(id);
            this.priority = priority;
        }

        String id() {
            return id;
        }

        int priority() {
            return priority;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof Ticket t && id.equals(t.id);
        }

        @Override
        public int hashCode() {
            return id.hashCode();
        }
    }

    public static void main(String[] args) {
        Word cat = new Word("cat");
        Word dog = new Word("dog");
        Comparator<Word> byLength =
                Comparator.comparingInt(w -> w.text().length());

        TreeSet<Word> byLengthSet = new TreeSet<>(byLength);
        boolean first = byLengthSet.add(cat);
        boolean second = byLengthSet.add(dog);

        System.out.println("words equals = " + cat.equals(dog));
        System.out.println("words compare = " + byLength.compare(cat, dog));
        System.out.println("tree set add = " + first + ", " + second);
        System.out.println("tree set size = " + byLengthSet.size());
        System.out.println("tree set contains dog = "
                + byLengthSet.contains(dog));
        System.out.println("hash set size = "
                + new HashSet<>(List.of(cat, dog)).size());

        TreeMap<Word, String> wordMap = new TreeMap<>(byLength);
        wordMap.put(cat, "first");
        String previous = wordMap.put(dog, "second");

        System.out.println("tree map previous = " + previous);
        System.out.println("tree map size = " + wordMap.size());
        System.out.println("tree map get dog = " + wordMap.get(dog));
        System.out.println("tree map stored key = " + wordMap.firstKey());

        Comparator<Word> byLengthThenText =
                byLength.thenComparing(Word::text);
        TreeSet<Word> fixedWords = new TreeSet<>(byLengthThenText);
        fixedWords.add(cat);
        fixedWords.add(dog);
        System.out.println("fixed words size = " + fixedWords.size());

        Ticket low = new Ticket("T7", 1);
        Ticket high = new Ticket("T7", 9);
        Comparator<Ticket> byPriorityThenId =
                Comparator.comparingInt(Ticket::priority)
                          .thenComparing(Ticket::id);

        TreeSet<Ticket> ticketSet = new TreeSet<>(byPriorityThenId);
        ticketSet.add(low);
        ticketSet.add(high);

        TreeMap<Ticket, String> ticketMap =
                new TreeMap<>(byPriorityThenId);
        ticketMap.put(low, "low");
        ticketMap.put(high, "high");

        System.out.println("tickets equals = " + low.equals(high));
        System.out.println("tickets compare = "
                + byPriorityThenId.compare(low, high));
        System.out.println("ticket tree set size = " + ticketSet.size());
        System.out.println("ticket hash set size = "
                + new HashSet<>(List.of(low, high)).size());
        System.out.println("ticket tree map size = " + ticketMap.size());

        TreeSet<Ticket> fixedTickets =
                new TreeSet<>(Comparator.comparing(Ticket::id));
        fixedTickets.add(low);
        fixedTickets.add(high);
        System.out.println("fixed tickets size = " + fixedTickets.size());
    }
}
```

In the directory containing the file, compile and run:

```bash
javac ComparatorContractDemo.java
java ComparatorContractDemo
```

Program output:

```text
words equals = false
words compare = 0
tree set add = true, false
tree set size = 1
tree set contains dog = true
hash set size = 2
tree map previous = first
tree map size = 1
tree map get dog = second
tree map stored key = Word[text=cat]
fixed words size = 2
tickets equals = true
tickets compare = -1
ticket tree set size = 2
ticket hash set size = 1
ticket tree map size = 2
fixed tickets size = 1
```

### Interpreting the first result: over-merging comparator

- `cat.equals(dog)` returns `false` because `Word` is a `record`, comparing component `text`; `"cat"` and `"dog"` differ.
- `byLength.compare(cat,dog)` returns `0` because both have length 3.
- `byLengthSet.add(cat)` returns `true`; `add(dog)` returns `false` because the tree treats `dog` as equivalent to the existing `cat`. Final size is 1.
- `byLengthSet.contains(dog)` is `true` under the tree's lookup method, even though the stored element is `cat`. In contrast, `HashSet` relies on `Word`'s `equals`/`hashCode` so its size is 2.
- `wordMap.put(dog,"second")` returns the previous value `"first"`; size remains 1 and `get(dog)` is `"second"`. The key object in the entry is `Word[text=cat]`, showing that **the new value replaces according to the comparator, without turning the old key into the new key**.

This is a common point of confusion: the tree's `contains`, `get`, and `put` follow the supplied comparator. They do not perform a final `equals` check to patch cases where the comparator returns 0 contrary to logical identity.

### Interpreting the second result: over-splitting comparator

- `low.equals(high)` is `true` because `Ticket.equals` relies solely on `id="T7"`; `hashCode` also uses `id` so the hash contract is preserved.
- `byPriorityThenId.compare(low,high)` returns `-1` because priority 1 is less than 9, despite sharing `id`.
- `TreeSet` and `TreeMap` still keep 2 entries because the comparator treats them as different. `HashSet` views them as one logical value, so size is 1.
- `Comparator.comparing(Ticket::id)` checks only `id`; two tickets with the same `id` yield 0, so `fixedTickets` has size 1, matching `Ticket`'s equality policy.

These two scenarios illustrate **both directions that must be checked** when a comparator is required to be consistent with `equals`.

## 4. How are the `Set` and `Map` contracts specifically affected?

### 4.1. `Set`: add, search, remove, and uniqueness

The `Set` interface defines a collection of elements with **no duplicates according to `equals`**. Fundamentally, `add(e)` returns `false` if the set already contains an element equal to `e`; `contains(o)` means checking for the presence of an element equal to `o`.

With `TreeSet`, the tree uses the comparator to determine whether an element is equivalent to an existing entry:

- If `compare(a,b)==0` yet `!a.equals(b)`, adding `b` after `a` can be rejected; `contains(b)` can return `true` even though `b` differs from every currently stored object by `equals`.
- `remove(b)` can also remove the representative entry `a` if `compare(a,b)==0`, because the search target is identified by ordering.
- If `a.equals(b)` yet `compare(a,b)!=0`, the set can contain both elements, breaking the no-duplicates expectation.

With `HashSet`, the equality condition is built on `equals` and `hashCode`; no comparator is used. The discrepancy between `HashSet` and `TreeSet` in the example is a direct result of two different identification rules.

### 4.2. `Map`: equivalent keys replaced or kept as duplicates

The `Map` interface defines unique keys according to `equals`. With `HashMap`, two keys equal by `equals` with compatible hashes represent the same mapping.

`TreeMap` needs an ordering to locate keys, so it uses `compare(k1,k2)==0`:

- When the comparator returns 0 for two keys that differ by `equals`, `put(k2,v2)` can update `k1`'s entry. The previous value is replaced; `size()` does not grow. `get(k2)` finds the entry via the comparator's rule.
- When the comparator returns non-zero for two keys that are equal by `equals`, `TreeMap` can hold both entries. Then looking up with a third object equal to the keys by `equals` can depend on the comparator result and fail to match expectations of the `Map` interface.
- The `keySet()`, `entrySet()` views and ordering operations like `firstKey()`, `subMap()`, `headMap()`, `tailMap()` depend on the ordering relation, so data ranges can also differ from intuition if a user assumes “equal key” means `equals`.

**Important note:** This is a flaw in the **key-definition policy** or how the structure is used, not necessarily an internal implementation bug in `TreeMap`. If an application intentionally uses comparator-based equivalence (for instance, case-insensitive strings), the outcome may suit business requirements, but you must understand it **differs from the key type's `equals` semantics** and can break the general `Map` contract.

### 4.3. Why is “as long as the comparator sorts properly” not enough?

A comparator checking length can fully preserve ordering rules: sign reversal, transitivity, and strings of the same length behaving identically when compared against a third string. It is **valid as a sort by length**, yet unsuitable if `TreeSet` must store all strings with distinct contents.

Conversely, a comparator by priority then id can also be a valid ordering, yet unsuitable when `Ticket.equals` defines two tickets with the same id as the same ticket.

Therefore, separate two questions: **(1) Does the comparator obey the `Comparator` contract? (2) Does a 0 result accurately represent key/element equality in the tree structure?**

## 5. How to fix: design comparison criteria around logical identity

### 5.1. Add a tie-breaker for objects where `equals` differs

If `Word.equals` treats the full `text` as identity, do not compare only length. Build a comparator by **length first, content second**:

```java
Comparator<Word> byLengthThenText =
        Comparator.comparingInt((Word w) -> w.text().length())
                  .thenComparing(Word::text);
```

This is an illustrative expression in a context having `Word`, requiring `import java.util.Comparator`. It returns 0 **only when** both length and content are equal; since identical content inevitably has the same length, comparing as 0 is equivalent to `Word.equals` in the example.

`TreeSet` still sorts in ascending order of length. When lengths match, it distinguishes `"cat"` and `"dog"` lexicographically. The correct outcome is that both are kept.

Do not use arbitrary tie-breakers like `System.identityHashCode` to “force inequality”: identity hashes can still collide, and two objects equal by value can end up comparing as different. A tie-breaker must align with the **equality policy**, not seek a random number to avoid a 0 result.

### 5.2. Remove non-identity fields from the comparator used for the tree

In `Ticket`, `equals` relies solely on `id`. To use `TreeSet<Ticket>` as a `Set` by ticket identity, the comparator must yield 0 when ids match:

```java
Comparator<Ticket> byId = Comparator.comparing(Ticket::id);
```

This is an illustrative line in a context where the `Ticket` class with getter `id()` is defined. When `low` and `high` have the same id, the comparator yields 0, aligning with `equals`. Since `id` is a non-null string and participates exclusively in `equals`, this comparator also distinguishes all differing id values.

If the requirement is to **display** tickets by `priority` while still identifying by id, do not force `TreeSet` both to sort by priority and to treat same-id items as duplicates when priorities differ. You can store tickets by id using `Map<String,Ticket>`, then build a list and sort the presentation view with a priority comparator. Collection/key rules and display rules can then differ without ambiguity.

### 5.3. Should `equals` be changed to match the comparator?

`equals` should be changed **only when business requirements genuinely change the definition of identity**. For example, if a ticket has an id and a version, and you want two tickets with the same id but different versions to be two separate values, then `equals`, `hashCode`, and the comparator can all treat version as part of identity.

Do not alter `equals` merely to patch a comparator used for a sorting screen: changing `equals` also affects `HashSet`, `HashMap`, caching, deduplication, and all code relying on that type's logical value.

## 6. When is a comparator inconsistent with `equals` intentionally accepted?

### Regular list sorting

With `List.sort(comparator)` or `Collections.sort(list,comparator)`, two objects having a comparison result of 0 can coexist in the list. Sorting does not have a “each value appears only once” contract like `Set`. Therefore, **a length-only comparator** can be completely suitable when grouping strings by length in a `List`.

The condition remains that the comparator must produce a consistent ordering under the comparison contract. Sorting cannot automatically fix a comparator with cycles or missing transitivity.

### Intentionally treating keys different by `equals` as the same key

For example, an application treats `"Admin"` and `"admin"` as the same username when processed in a `TreeMap<String,V>` with `String.CASE_INSENSITIVE_ORDER`. This can be an intentional choice, yet `String.equals` remains case-sensitive. When interfacing with other APIs using `HashMap`/`HashSet`, merging and recognition results can differ.

If lowercase identity is the primary business rule, it is often easier to control by **normalizing keys before storing** (with an appropriate locale/Unicode policy) or designing a key type whose `equals`, `hashCode`, and comparator all express the policy. Avoid implicitly shifting the meaning of equality across different collections.

### `Comparable` and `BigDecimal`

The same issue also occurs with **natural ordering** provided by `compareTo` without a separate comparator. For example:

```java
BigDecimal x = new BigDecimal("2.0");
BigDecimal y = new BigDecimal("2.00");
System.out.println(x.compareTo(y)); // 0
System.out.println(x.equals(y));    // false
```

This snippet needs `import java.math.BigDecimal` and sits inside a method. `BigDecimal.compareTo` compares numeric value; `BigDecimal.equals` also checks `scale`. `TreeSet<BigDecimal>` treats these two values as equivalent by ordering, while `HashSet<BigDecimal>` can retain both. This is a familiar exception highlighting why **consistency with `equals` is critical for tree structures**.

## 7. Testing and reviewing comparators for ordered sets/maps

Do not merely check that a list sorts nicely. For every key/element type intended for `TreeSet` or `TreeMap`, check **two-way compatibility**:

```java
boolean sameByEquals = Objects.equals(a, b);
boolean sameByComparator = comparator.compare(a, b) == 0;

if (sameByEquals != sameByComparator) {
    throw new AssertionError("Comparator inconsistent with equals");
}
```

This is a **test snippet** with variables `a`, `b`, and `comparator` prepared beforehand; not a standalone runnable program. You must test pairs with equal values, different values, same primary key but different secondary fields, different primary keys but same sort field, and boundary values. Also verify that the comparator can compare objects across the domain supported by the collection.

Beyond consistency-with-equals, test the full ordering contract:

1. **Sign reversal:** `Integer.signum(compare(a,b)) == -Integer.signum(compare(b,a))`. Compare **signs**, not `compare(a,b) == -compare(b,a)` because negating `Integer.MIN_VALUE` can overflow.
2. **Transitivity:** if `compare(a,b) > 0` and `compare(b,c) > 0`, then `compare(a,c) > 0`.
3. **Consistency of ordering equivalence:** if `compare(a,b) == 0`, then the sign of `compare(a,c)` must match the sign of `compare(b,c)` for all comparable `c`.
4. **Stability:** keys must not mutate fields participating in comparison while stored in the tree. If changing a key, remove the old entry and re-add or rebuild the structure.
5. **Compatibility with equality:** for `Set`/`Map` by logical identity, check `compare(a,b)==0` if and only if `a.equals(b)`.

You can write a small test suite inserting pairs into both `TreeSet` and `HashSet`, checking size, `contains`, and `remove`; and inserting into `TreeMap`, checking `put`'s returned previous value, `size`, `get`, and `firstKey`. When the goal is using `TreeSet`/`TreeMap` under the general contract, test results must reflect **the same equality policy**.

An example check for the inconsistency condition:

```java
Comparator<String> byLength = Comparator.comparingInt(String::length);
String a = "cat";
String b = "dog";

assert !a.equals(b);
assert byLength.compare(a, b) == 0;
```

The snippet above requires `import java.util.Comparator`, runs inside a method, and runs with assertions enabled (`-ea`). It intentionally demonstrates that the length comparator is **inconsistent** with `String.equals`. To make the test suite always check even if assertions are disabled, use an `if` and throw `AssertionError` as in the previous example.

## 8. Common pitfalls and fixes

| Pitfall | Symptom | Resolution |
| --- | --- | --- |
| `Comparator.comparingInt(String::length)` used as ordering for `TreeSet<String>` needing all distinct-content strings | Two strings of equal length are merged | Add tie-breaker `thenComparing(Comparator.naturalOrder())` or compare full content |
| Comparator returns 0 for keys that `equals` treats as different | `TreeMap.put` replaces value unexpectedly | Use identifying fields as the final distinguishing criterion |
| Comparator distinguishes keys that are equal by `equals` | `TreeSet` or `TreeMap` keeps two equal entries | Remove non-identity fields from the tree's distinguishing criteria |
| Assuming `TreeSet.contains` always calls `equals` | `contains` can return confusing results | Understand it relies on `compare==0` in tree order |
| Adding a tie-breaker using identity hash | Does not guarantee uniqueness; breaks value-based equality | Use stable identity components compatible with `equals` |
| Mutating a key after adding to `TreeSet`/`TreeMap` | Tree position no longer matches the new order | Use immutable keys; remove and re-add if needed |
| Comparator fails transitivity or consistency | Sort/lookup can misbehave; some sorts may report contract errors | Test pairs and triples, use `Comparator.comparing` / `thenComparing` |
| Treating `TreeSet` and `HashSet` as completely interchangeable with any comparator | Sizes/lookups differ between the two set types | Ensure `compare==0 ⇔ equals` when identical Set semantics are needed |
| Intentionally merging keys case-insensitively without documenting policy | Data loses case distinction in tree while remaining distinct in hash | Normalize keys or design a consistent key type |

## 9. Self-check exercises

**Scenario 1.** `TreeSet<String>` uses a comparator comparing length; `"red"` is added, then `"sun"`. What can `size()` and `contains("sun")` be?

`size()` equals 1; `contains("sun")` is `true` because both have length 3. However, `"red".equals("sun")` is `false`. If both strings are desired, a content-distinguishing criterion must be added to the comparator.

**Scenario 2.** Two `Ticket`s share the same `id` but have priorities 3 and 8. `equals` checks only id, while the comparator checks priority then id. How many elements can `TreeSet` store?

Two elements, even though `equals` views them as one. The comparator distinguishes them because priorities differ. If the logical key is id, an identity-based set should compare id as the equivalence criterion.

**Scenario 3.** A comparator is consistent in sign and transitivity, yet returns 0 for two keys that differ by `equals`. Is the comparator always buggy?

No. It can be appropriate when **only sorting a `List`** or when the application intentionally groups keys under a custom policy. However, when used as the ordering for `TreeSet`/`TreeMap` where the `equals`-based `Set`/`Map` contract is expected, it is inappropriate.

**Scenario 4.** When adding a new key considered equal by the comparator to an existing key in `TreeMap`, is the original key object guaranteed to be replaced by the new key object?

No. In the section 3 example, the value is replaced yet the entry still retains `Word[text=cat]` as its key. Distinguish **updating the value** from **replacing the stored key object**.

**Rule of thumb:** For ordered sets or maps, define what “one unique element/key” means **before** writing the comparator. When strict compatibility with the `Set`/`Map` contract is required, ensure `compare(a,b)==0` holds **if and only if** `a.equals(b)`. If you only need ordering for display, different criteria can be used on a `List` without altering the data's logical identity.
