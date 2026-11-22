# TreeMap: Comparator, compareTo, and Keys Considered Duplicates

## 1. One comparison rule decides both ordering and key identity

`TreeMap` stores key–value pairs and traverses keys in the chosen order. For example, we might want to look up data for a software version while also iterating through versions from lowest to highest. Such an ordered map needs to know which key comes before which.

An easy point to overlook is that in `TreeMap`, the comparison rule also decides **whether two keys are considered the same key**. It is not used only when printing or sorting the final result.

Suppose a comparator only compares string lengths. Two strings `"cat"` and `"dog"` have different contents, but the comparator returns 0 because both are three characters long. Inserting them one after the other into the same `TreeMap` affects the same mapping from the map's perspective. If you want to keep both as two separate keys, the comparison rule must distinguish them.

This lesson follows three questions:

1. Does `TreeMap` take its comparison rule from `Comparable.compareTo` or from `Comparator.compare`?
2. What do negative, 0, and positive results mean when looking up and updating keys?
3. How do you design a comparison rule so that you do not accidentally merge keys that should stay separate?

Here, "duplicate keys" means **duplicates according to the map's own ordering**, not the same object reference. Whether they are also equal according to `equals` is a design requirement that needs to be checked.

## 2. Two sources of ordering

### 2.1. Comparable and a type's natural ordering

A type that implements `Comparable<T>` provides the `compareTo(T other)` method. This is the natural ordering that the type declares. For example, a `Version` type can specify comparing the major version number first, and then the minor version number if the major parts are equal.

In the `Version` example below, `compareTo` compares the major version first, then the minor version. This comparability is declared directly on the key type.

When creating `new TreeMap<K, V>()`, the map uses the keys' natural ordering. Keys must be mutually comparable under that ordering. Generics do not automatically check all of these conditions at the `TreeMap` declaration site: a class that does not implement `Comparable` can still appear in the type declaration and then fail at runtime when the map has to compare keys.

### 2.2. Comparator as an externally supplied rule

`Comparator<T>` provides `compare(T left, T right)`. It is suitable when you want to choose a custom order for a specific map, when the key type cannot be modified, or when the same type needs multiple ways of ordering.

Illustrative snippet inside a method:

```java
Comparator<String> byLength = Comparator.comparingInt(String::length);
TreeMap<String, Integer> map = new TreeMap<>(byLength);
```

This map uses `byLength` to compare keys. It does not automatically fall back to `String.compareTo` when lengths are equal. If you want a secondary criterion based on string content, you must state that criterion explicitly in the comparator.

A comparator can use `compareTo` internally, such as `Comparator.naturalOrder()`. However, that is a choice inside the comparator implementation; there are not two independent passes like "comparator for order, equals for duplicate keys" in `TreeMap`.

### 2.3. The constructor selects one active rule

| How the map is created | Source of ordering | `map.comparator()` |
|---|---|---|
| `new TreeMap<>()` | Natural ordering of keys | `null` |
| `new TreeMap<>(comparator)` with non-`null` comparator | Supplied comparator | That comparator |
| Constructor receiving a `null` comparator | Natural ordering | `null` |

`comparator() == null` does not mean the map is unordered. It indicates that the map uses natural ordering. If a non-`null` comparator is provided, the key type does not have to implement `Comparable`, as long as the comparator validly compares all keys inserted into the map.

For example, a record with two fields does not automatically generate `compareTo` just because it is a record. A record can auto-generate `equals` based on its components, but ordering capability still must be declared or supplied via a comparator.

## 3. Reading comparison results by sign

Both `compareTo` and `compare` return an integer:

| Result | Meaning in the chosen ordering |
|---|---|
| `< 0` | The left key comes before the right key |
| `== 0` | The two keys are equivalent in ordering |
| `> 0` | The left key comes after the right key |

The API only requires the **sign** of the result. You must not test arbitrary comparators with `result == -1` or `result == 1`. A valid implementation may return any other negative or positive integer. The right way to check before/after relationships is to compare against 0.

"Comes before" also does not always mean "smaller numeric value." With a comparator that reverses numeric order, 10 can come before 2. The meaning of first/last and before/after in the map always follows the active rule.

### 3.1. How lookup is visualized through a tree

You do not need to implement a tree yourself to understand the effect of a comparator. You can picture that at each key being inspected, the map uses the comparison result to decide:

```text
Compare the target key with the current key
    ├─ negative → continue toward the keys that come before
    ├─ positive → continue toward the keys that come after
    └─ equal to 0 → found a key considered equivalent
```

In practice, `TreeMap` uses a red-black tree to maintain a balanced structure. Tree-rotation details do not change the key-identification rule: a comparison result of 0 is the case of encountering the same key under the ordering. This is not a matter of sorting a list after storing all objects separately.

### 3.2. How a result of 0 governs key-based operations

Suppose `compare(a, b) == 0` under the map's rule:

| Operation | What to expect |
|---|---|
| `put(a, v1)` then `put(b, v2)` | The second call updates the equivalent mapping; it does not increase the number of mappings just because `b` is a different object |
| `get(b)` when `a` is already present | Can find `a`'s mapping via a comparison result of 0 |
| `containsKey(b)` when `a` is already present | Recognizes the same equivalence group of keys |
| `remove(b)` when `a` is already present | Can remove the mapping that `a` created |

The word "equivalent" in this table does not refer to values `V`. `TreeMap` orders and identifies **keys `K`**. Two equal values do not cause two different keys to be merged; two different values also do not save two keys that the comparator already treats as equivalent.

### 3.3. Do not confuse this with hash collisions

Keys having the same hash code in `HashMap` do not mean they are the same key; a hash structure also checks equality according to its contract. `TreeMap` uses ordering comparison for key identification and does not use `hashCode` to decide where keys go.

Therefore, fixing `hashCode` does not solve a comparator returning 0 for two keys that need to stay separate. Conversely, implementing `equals` thoroughly while letting a comparator omit an important component can still cause `TreeMap` to update the wrong key group relative to the application's intent.

## 4. Program 1: compareTo defines natural ordering and duplicate keys

Save the complete program to `TreeMapComparableDemo.java`. This example is compatible with Java 17 and later. `Version` is a record with two numeric components; the `equals` provided by the record checks both components, and `compareTo` also checks both.

```java
import java.util.Comparator;
import java.util.TreeMap;

public class TreeMapComparableDemo {
    record Version(int major, int minor) implements Comparable<Version> {
        @Override
        public int compareTo(Version other) {
            int result = Integer.compare(major, other.major);
            return result != 0 ? result : Integer.compare(minor, other.minor);
        }

        @Override
        public String toString() {
            return major + "." + minor;
        }
    }

    public static void main(String[] args) {
        Version first = new Version(1, 2);
        Version later = new Version(1, 10);
        Version same = new Version(1, 2);
        System.out.println("sameReference=" + (first == same));
        System.out.println("sameEquals=" + first.equals(same));
        System.out.println("sameCompare=" + first.compareTo(same));
        System.out.println("firstBeforeLater=" + (first.compareTo(later) < 0));

        TreeMap<Version, String> natural = new TreeMap<>();
        natural.put(later, "later");
        natural.put(first, "initial");
        natural.put(new Version(2, 0), "major-two");
        System.out.println("oldValue=" + natural.put(same, "updated"));
        System.out.println("natural=" + natural);
        System.out.println("naturalSize=" + natural.size());
        System.out.println("lookup=" + natural.get(new Version(1, 2)));
        System.out.println("usesNaturalOrder=" + (natural.comparator() == null));

        TreeMap<Version, String> reverse =
                new TreeMap<>(Comparator.reverseOrder());
        reverse.putAll(natural);
        System.out.println("reverseKeys=" + reverse.keySet());
        System.out.println("reverseDuplicateCompare="
                + reverse.comparator().compare(first, same));
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 TreeMapComparableDemo.java
java TreeMapComparableDemo
```

Stdout:

```text
sameReference=false
sameEquals=true
sameCompare=0
firstBeforeLater=true
oldValue=initial
natural={1.2=updated, 1.10=later, 2.0=major-two}
naturalSize=3
lookup=updated
usesNaturalOrder=true
reverseKeys=[2.0, 1.10, 1.2]
reverseDuplicateCompare=0
```

### 4.1. Different objects can still be the same key

`first` and `same` are created via two constructor calls, so `sameReference=false`. However, they both represent 1.2, `equals` returns `true`, and `compareTo` returns 0. Calling `put(same, "updated")` updates the mapping that `first` created and returns the old value `initial`.

The map has three key groups: 1.2, 1.10, and 2.0. There were four `put` calls, but the number of mappings is three. `get(new Version(1, 2))` finds `updated` without needing the exact object instance passed on the first insertion.

That is the desired behavior when a key represents a value: you do not need to keep the exact same reference to look up the data.

### 4.2. Compare component by component, not by display string

`compareTo` compares `major` first. Only when `major` is equal does it compare `minor`. Thus 1.2 comes before 1.10 because 2 is less than 10. The program does not convert keys to strings and compare `"1.2"` against `"1.10"` lexicographically.

The `toString` method only makes the printed output readable; `TreeMap` does not call it as the key-comparison rule. The implementation uses `Integer.compare`, avoiding subtracting two integers that could overflow.

### 4.3. Reversing the order does not separate already-equivalent keys

The second map receives `Comparator.reverseOrder()` and iterates `[2.0, 1.10, 1.2]`. It still treats the two 1.2 versions as equivalent, so `reverseDuplicateCompare=0`.

Reversing direction changes the before/after relationship; it does not turn pairs that compare equal into distinct keys. If the original comparator merged two keys that needed to stay separate, adding `.reversed()` will not fix that bug.

## 5. Comparator returns 0 while equals returns false

### 5.1. Distinguishing the two equality relations

For any two valid keys `a` and `b`, an ordering rule is called **consistent with equals** when:

```text
compare(a, b) == 0  ⇔  a.equals(b)
```

The bidirectional arrow is crucial. It is not enough that `equals=true` implies comparison is 0; comparison returning 0 must also imply `equals=true`. If only one direction holds, the notion of "same key" according to the map can differ from the notion of equal value objects in other APIs.

The [TreeMap — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html) documentation explains that the map uses comparison for all keys. An ordering that is inconsistent with `equals` still gives well-defined lookup and update behavior under the comparator, but the map no longer fully obeys the general `Map` contract based on `equals`.

Do not misunderstand this as "TreeMap always checks equals after the comparator returns 0" or "TreeMap will automatically throw an exception when the two relations differ." It continues operating according to its comparison rule.

### 5.2. Case-insensitive example

`String.CASE_INSENSITIVE_ORDER` treats `"Java"`, `"JAVA"`, and `"java"` as equivalent in ordering, while `String.equals` distinguishes uppercase and lowercase characters. This is an easy example for observing how a comparator decides duplicate keys.

Save the complete program to `TreeMapCaseInsensitiveDemo.java`:

```java
import java.util.Comparator;
import java.util.HashMap;
import java.util.Map;
import java.util.TreeMap;

public class TreeMapCaseInsensitiveDemo {
    public static void main(String[] args) {
        String first = new String("Java");
        String second = new String("JAVA");
        Comparator<String> order = String.CASE_INSENSITIVE_ORDER;
        System.out.println("stringEquals=" + first.equals(second));
        System.out.println("comparison=" + order.compare(first, second));

        TreeMap<String, String> map = new TreeMap<>(order);
        map.put(first, "initial");
        System.out.println("oldValue=" + map.put(second, "updated"));
        System.out.println("size=" + map.size());
        System.out.println("storedKeys=" + map.keySet());
        System.out.println("getLowercase=" + map.get("java"));
        System.out.println("containsMixedCase=" + map.containsKey("jAvA"));
        System.out.println("removed=" + map.remove("jAvA"));
        System.out.println("sizeAfterRemove=" + map.size());

        Map<String, Integer> tree = new TreeMap<>(order);
        Map<String, Integer> hash = new HashMap<>();
        tree.put("Java", 1);
        hash.put("JAVA", 1);
        System.out.println("treeEqualsHash=" + tree.equals(hash));
        System.out.println("hashEqualsTree=" + hash.equals(tree));

        TreeMap<String, String> nullFriendly =
                new TreeMap<>(Comparator.nullsFirst(order));
        nullFriendly.put(null, "null-key");
        nullFriendly.put("A", null);
        System.out.println("nullFriendlyKeys=" + nullFriendly.keySet());
        System.out.println("nullKeyValue=" + nullFriendly.get(null));
        System.out.println("getLowercaseNullValue=" + nullFriendly.get("a"));
        System.out.println("containsLowercaseA=" + nullFriendly.containsKey("a"));
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 TreeMapCaseInsensitiveDemo.java
java TreeMapCaseInsensitiveDemo
```

Stdout:

```text
stringEquals=false
comparison=0
oldValue=initial
size=1
storedKeys=[Java]
getLowercase=updated
containsMixedCase=true
removed=updated
sizeAfterRemove=0
treeEqualsHash=false
hashEqualsTree=true
nullFriendlyKeys=[null, A]
nullKeyValue=null-key
getLowercaseNullValue=null
containsLowercaseA=true
```

### 5.3. Replacing values, looking up, and removing with a different variant

`stringEquals=false` yet `comparison=0`. After two `put` calls, `size=1`; the old value `initial` is returned and the mapping receives the new value `updated`.

In this run, `storedKeys=[Java]` shows that the key form retained for iteration is still `Java`, even though the value was updated by a call passing `JAVA`. You should not rely on updating an equivalent key as a mechanism to normalize the displayed casing of a key, nor rely on key object identity to drive business logic. If a canonical key form is needed, create and use that form explicitly before storing.

`get("java")`, `containsKey("jAvA")`, and `remove("jAvA")` all recognize the same mapping. After `remove`, the map is empty. The scope of the equivalence relation is not limited to the second insertion; it follows through lookup and removal operations as well.

### 5.4. Consequences when comparing with another map

The lines `treeEqualsHash=false` yet `hashEqualsTree=true` show a concrete manifestation of violating the general contract. The two maps hold the keys `Java` and `JAVA`; when the two directions of equality check look up keys under different key-matching rules, `equals` can lose symmetry.

In `tree.equals(hash)`, the tree's key `Java` is looked up in `hash` and does not match `JAVA` under `String.equals`. In `hash.equals(tree)`, `hash`'s key `JAVA` is looked up in `tree` and matches `Java` under the comparator. This is not a guarantee to exploit in a program. The example intentionally demonstrates why the warning about consistency with `equals` has practical impact rather than being merely a formal requirement. For maps shared across general-purpose APIs, design the key type and comparison rule to agree on what constitutes the same key.

If the business domain truly treats all case variants as the same code, one option is to determine a canonical form at the input boundary, or create a key type whose `equals`, `hashCode`, and ordering are all based on that canonical form. The normalization rule must be chosen according to the data domain; a comparator does not automatically fix `String.equals`, nor does it replace a clearly specified normalization policy.

### 5.5. Null keys and null values are two different things

At the end of the program, `Comparator.nullsFirst(order)` adds a rule for `null` keys: `null` comes before non-`null` keys, while two non-`null` keys are compared with the chosen comparator. That allows the map to hold a `null` key in this example.

`new TreeMap<>()` using natural ordering does not allow `null` keys. Another comparator that does not handle `null` may also reject it. Therefore, there is no universal rule that every `TreeMap` accepts or every `TreeMap` rejects `null` keys; it depends on the ordering rule.

A `null` value does not participate in key ordering. The mapping `A → null` still exists; `get("a")` returns `null` and `containsKey("a")` is `true` under the case-insensitive comparator. A `get == null` result alone does not prove that the key is absent.

## 6. Program 3: secondary criteria decide whether two keys stay separate

### 6.1. Comparing only priority collapses codes of the same level

Suppose a `Ticket` key has two components: `priority` and `code`. If a comparator only inspects `priority`, two tickets `1:A` and `1:B` are treated as the same key even though the record's `equals` sees them as different.

This is not a bug in `Comparator.comparingInt`. It faithfully executed the requested criterion. The issue is that this criterion does not yet express the full key-distinction relation the application expects.

When you want priority first and code second, you can chain criteria with `thenComparing`. The secondary criterion is only used when the primary criterion returns 0; it never alters a before/after result already decided by the primary criterion.

Save the complete program to `TreeMapComparatorChainDemo.java`:

```java
import java.util.Comparator;
import java.util.Objects;
import java.util.TreeMap;

public class TreeMapComparatorChainDemo {
    record Ticket(int priority, String code) {
        Ticket {
            Objects.requireNonNull(code, "code");
        }

        @Override
        public String toString() {
            return priority + ":" + code;
        }
    }

    public static void main(String[] args) {
        Ticket a = new Ticket(1, "A");
        Ticket b = new Ticket(1, "B");
        Comparator<Ticket> byPriority =
                Comparator.comparingInt(Ticket::priority);

        System.out.println("aEqualsB=" + a.equals(b));
        System.out.println("priorityCompare=" + byPriority.compare(a, b));
        TreeMap<Ticket, String> collapsed = new TreeMap<>(byPriority);
        collapsed.put(a, "alpha");
        System.out.println("collapsedOld=" + collapsed.put(b, "beta"));
        System.out.println("collapsed=" + collapsed);
        System.out.println("collapsedSize=" + collapsed.size());
        System.out.println("lookupA=" + collapsed.get(a));
        System.out.println("reverseStillEqual="
                + (byPriority.reversed().compare(a, b) == 0));

        Comparator<Ticket> fullOrder =
                byPriority.thenComparing(Ticket::code);
        TreeMap<Ticket, String> complete = new TreeMap<>(fullOrder);
        complete.put(new Ticket(2, "C"), "gamma");
        complete.put(b, "beta");
        complete.put(a, "alpha");
        System.out.println("complete=" + complete);
        System.out.println("completeSize=" + complete.size());
        System.out.println("lookupB=" + complete.get(new Ticket(1, "B")));
        System.out.println("sameKeyOld="
                + complete.put(new Ticket(1, "B"), "beta-2"));
        System.out.println("sizeAfterSameKey=" + complete.size());
        System.out.println("completeAfterUpdate=" + complete);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 TreeMapComparatorChainDemo.java
java TreeMapComparatorChainDemo
```

Stdout:

```text
aEqualsB=false
priorityCompare=0
collapsedOld=alpha
collapsed={1:A=beta}
collapsedSize=1
lookupA=beta
reverseStillEqual=true
complete={1:A=alpha, 1:B=beta, 2:C=gamma}
completeSize=3
lookupB=beta
sameKeyOld=beta
sizeAfterSameKey=3
completeAfterUpdate={1:A=alpha, 1:B=beta-2, 2:C=gamma}
```

### 6.2. Reading the result of a single-criterion map

`aEqualsB=false` yet `priorityCompare=0`. Adding `b` returns the old value `alpha`, the map has only one mapping, and `lookupA=beta`. This means the application no longer has two independent slots to store `alpha` and `beta` under the two codes.

The line `collapsed={1:A=beta}` is the observed outcome: the entry is displayed with key `1:A`, but its value was updated by the `put` call using `1:B`. If you only look at the key column and assume the value was always created from that exact original key object, you can misread the data.

`reverseStillEqual=true` again shows that reversing direction does not turn two keys with equal priority into distinct keys.

### 6.3. thenComparing clarifies when 0 is returned

The full comparator has the following logic:

```text
Compare priority
    ├─ different → use that result
    └─ equal → compare code
                 ├─ different → distinguish the two keys
                 └─ equal → return 0
```

For the record in this lesson, `equals` checks the exact two components `priority` and `code`; `code` is validated to be non-`null` at construction. The comparator also returns 0 only when both components are equal. Therefore, this ordering is consistent with `equals` over that key domain.

The map keeps all three mappings `{1:A=alpha, 1:B=beta, 2:C=gamma}`. Inserting a new object that also represents `1:B` still updates the `1:B` mapping, returns `beta`, keeps the size at three, and leaves `1:A` untouched.

### 6.4. Choose secondary criteria by key identity, not just to force arbitrary differences

Adding just any criterion is not necessarily good. If you chain `System.identityHashCode` or a random number merely to avoid returning 0, two objects representing the same business key can be split apart. Then recreating a key object for lookup may no longer find the intended equivalence group.

Identifying attributes must be stable and match the concept of "same key." In this example, the `(priority, code)` pair is the entire value of the key. If in another model only `code` is the identity while priority changes independently, you may need to use `code` as the lookup key and store priority in the value, or design a separate ordering index.

What must be decided is **which differences should cause two keys to be stored separately**. Do not pick an attribute meant only for display and assume it is sufficient as an identity for `TreeMap`.

### 6.5. thenComparing is not a way to group multiple values

If the real requirement is that one priority holds multiple tickets, the appropriate data type may be `TreeMap<Integer, List<Ticket>>`, with the list of tickets in the value. Then two tickets at the same level are not placed directly as competing keys.

That approach has a different meaning from `TreeMap<Ticket, Value>` with a full comparator. A map keyed by priority returns a group; a map keyed by a composite key returns an individual mapping for each pair of components. Choose based on the operations the application needs, rather than trying to tweak a comparator so one structure carries two meanings at once.

## 7. Program 4: BigDecimal and the difference between numeric value and representation

### 7.1. An example from the standard library

`BigDecimal` is an important case because you can encounter a comparison of 0 with `equals=false` without writing a buggy comparator yourself. With `new BigDecimal("2.0")` and `new BigDecimal("2.00")`: the numeric values are equal, but their scales differ.

`compareTo` compares by numeric value, whereas `equals` checks both value and scale. This detail is documented in [BigDecimal — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html). Do not interpret this as a rounding error in the example: both strings are constructed directly as decimal numbers without going through `double`.

Save the complete program to `TreeMapBigDecimalKeyDemo.java`:

```java
import java.math.BigDecimal;
import java.util.Comparator;
import java.util.TreeMap;

public class TreeMapBigDecimalKeyDemo {
    public static void main(String[] args) {
        BigDecimal first = new BigDecimal("2.0");
        BigDecimal second = new BigDecimal("2.00");
        System.out.println("equals=" + first.equals(second));
        System.out.println("compareTo=" + first.compareTo(second));
        System.out.println("scales=" + first.scale() + "," + second.scale());

        TreeMap<BigDecimal, String> numeric = new TreeMap<>();
        numeric.put(first, "first");
        System.out.println("numericOld=" + numeric.put(second, "second"));
        System.out.println("numeric=" + numeric);
        System.out.println("numericSize=" + numeric.size());
        System.out.println("numericLookup="
                + numeric.get(new BigDecimal("2.000")));

        Comparator<BigDecimal> numericThenScale =
                Comparator.<BigDecimal>naturalOrder()
                        .thenComparingInt(BigDecimal::scale);
        TreeMap<BigDecimal, String> representation =
                new TreeMap<>(numericThenScale);
        representation.put(first, "first");
        representation.put(second, "second");
        System.out.println("representation=" + representation);
        System.out.println("representationSize=" + representation.size());
        System.out.println("representationLookup="
                + representation.get(new BigDecimal("2.000")));
        System.out.println("normalizedEquals="
                + first.stripTrailingZeros().equals(second.stripTrailingZeros()));
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 TreeMapBigDecimalKeyDemo.java
java TreeMapBigDecimalKeyDemo
```

Stdout:

```text
equals=false
compareTo=0
scales=1,2
numericOld=first
numeric={2.0=second}
numericSize=1
numericLookup=second
representation={2.0=first, 2.00=second}
representationSize=2
representationLookup=null
normalizedEquals=true
```

### 7.2. A natural-order map merges equal numeric values

The `numeric` map receives no custom comparator, so it uses `BigDecimal.compareTo`. `compareTo=0` puts both keys into the same equivalence group. The second `put` returns `first`, and the map retains one mapping with value `second`.

`numericLookup=second` shows that a third key `2.000` also finds the same mapping. The lookup key does not need the same scale if the ordering rule only considers numeric value.

This can fit a requirement where "different ways of writing the same numeric value belong to the same group," but `BigDecimal`'s natural ordering is not consistent with `BigDecimal.equals`. When using it as a general-purpose `Map` or combining it with `equals`-based structures, be aware of that difference.

### 7.3. A map that also checks scale keeps representations separate

The comparator `numericThenScale` compares numeric value first, and then compares scale when numeric values are equal. As a result, `2.0` and `2.00` are kept separate, and the map has two mappings. `2.000` has a third scale, so `representationLookup=null` because no such key exists in the map.

For `BigDecimal`, having equal numeric value and the same scale also corresponds to the `equals` condition; this comparator produces a 0 relation that aligns with `equals`. However, it also **changes the meaning of lookup**: querying a numeric value with a different scale no longer automatically hits an existing entry.

Do not add scale just to see `size=2` and treat that as always the right choice. If scale is part of the data that must be kept distinct, this approach has a reason. If the application treats every representation of the same number as one key, model that relation consistently.

### 7.4. Normalization is a domain-level choice

`stripTrailingZeros()` in the example gives both values an equal canonical form, so `normalizedEquals=true`. If you choose normalization as the key policy, you must apply the same rule on insert, lookup, and removal; normalizing only on `put` while looking up with an unnormalized key creates a confusing contract.

Do not automatically equate key normalization with display formatting or currency rounding rules. `stripTrailingZeros` can produce a negative scale for some values; it does not mean every result always has scale 0 or always prints in the same decimal format. Choose the canonical representation based on data requirements and test its edge cases.

The key takeaway of this example is recognizing that **compareTo and equals can intentionally differ in a standard-library type**. The fact that keys belong to a standard library class does not exempt `TreeMap` users from checking the duplicate-key relation.

## 8. A Comparator must be a valid ordering relation

### 8.1. Three constraints to understand

Let `c(a, b)` denote the comparison result between two keys `a` and `b`. Besides being able to compare any keys in the allowed domain, a comparator needs consistent relations:

1. **Sign reversal when swapping arguments:** the sign of `c(a, b)` must be opposite to the sign of `c(b, a)`. If `a` comes before `b`, `b` must come after `a`. For two equivalent keys, both directions are 0.
2. **Transitivity:** if `a` comes before `b` and `b` comes before `c`, then `a` must also come before `c`. The same applies to the "comes after" direction.
3. **Consistency when equal to 0:** if `a` and `b` are considered equivalent, comparing both against any key `z` must yield the same relative sign with respect to `z`.

The third rule makes "same key group" meaningful across the entire tree, not just for a single pair. You cannot have `a` equal to `b` while `a` comes before `z` and `b` comes after `z` and expect a search structure to maintain a valid order.

For any accepted key, `c(a, a)` must be 0. A comparator must not return 1 just because two references are different or to force a new key to always be inserted. Such workarounds to avoid returning 0 break the ordering rather than creating a valid multi-value map.

Ordering constraints and consistency with `equals` are two different layers. A comparator based only on string length can be a valid ordering relation on length groups, yet not be consistent with `String.equals`. A comparator using overflowing subtraction can break even the basic ordering constraints.

### 8.2. Why integer subtraction is dangerous

`(a, b) -> a - b` looks concise for sorting numbers in ascending order. However, `int` subtraction can overflow, causing the sign of the result to no longer reflect the relationship between the two operands.

This does not just corrupt a single printout. `TreeMap` relies on the sign to choose the search path. If the sign is inconsistent, the structure has no valid relation to maintain and search. You should not test a few small numbers and conclude the comparator is correct for the entire `int` range.

The next program tests the properties of the comparison directly. It intentionally does not put the broken comparator into a map, avoiding turning the behavior of a structure with a broken order into an output a learner might rely on.

### 8.3. Program 5: observing overflow bugs in a comparator

Save to `ComparatorContractDemo.java`:

```java
import java.util.Comparator;

public class ComparatorContractDemo {
    public static void main(String[] args) {
        Comparator<Integer> bad = (left, right) -> left - right;
        Comparator<Integer> good = Integer::compare;
        int minimum = Integer.MIN_VALUE;
        int maximum = Integer.MAX_VALUE;

        System.out.println("badMinVsZero=" + bad.compare(minimum, 0));
        System.out.println("badZeroVsMin=" + bad.compare(0, minimum));
        System.out.println("badOppositeSigns="
                + (Integer.signum(bad.compare(minimum, 0))
                == -Integer.signum(bad.compare(0, minimum))));
        System.out.println("goodOppositeSigns="
                + (Integer.signum(good.compare(minimum, 0))
                == -Integer.signum(good.compare(0, minimum))));

        boolean badPremise = bad.compare(minimum, 0) < 0
                && bad.compare(0, maximum) < 0;
        boolean badConclusion = bad.compare(minimum, maximum) < 0;
        boolean goodPremise = good.compare(minimum, 0) < 0
                && good.compare(0, maximum) < 0;
        boolean goodConclusion = good.compare(minimum, maximum) < 0;
        System.out.println("badTransitivityPremise=" + badPremise);
        System.out.println("badTransitivityConclusion=" + badConclusion);
        System.out.println("goodTransitivityPremise=" + goodPremise);
        System.out.println("goodTransitivityConclusion=" + goodConclusion);
        System.out.println("negatingMinStillNegative=" + (-minimum < 0));
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 ComparatorContractDemo.java
java ComparatorContractDemo
```

Stdout:

```text
badMinVsZero=-2147483648
badZeroVsMin=-2147483648
badOppositeSigns=false
goodOppositeSigns=true
badTransitivityPremise=true
badTransitivityConclusion=false
goodTransitivityPremise=true
goodTransitivityConclusion=true
negatingMinStillNegative=true
```

### 8.4. Reading the bug through sign and transitivity

Both `minimum - 0` and `0 - minimum` produce `-2147483648` under `int` arithmetic. Both are negative, so the broken comparator is simultaneously claiming that `minimum` comes before `0` and `0` comes before `minimum`. `badOppositeSigns=false` exposes that bug.

The broken comparator also says `minimum` comes before `0` and `0` comes before `maximum`, yet does not say `minimum` comes before `maximum`. Thus `badTransitivityPremise=true` while `badTransitivityConclusion=false`.

`Integer.compare` performs the comparison without overflow-prone subtraction, so both corresponding checks pass. For `long` fields, use `Long.compare` or `Comparator.comparingLong`; do not subtract `long` values and cast to `int`.

`negatingMinStillNegative=true` shows that negating an arbitrary comparison result also has a trap at `Integer.MIN_VALUE`. To reverse a valid comparator, use `reversed()`; to reverse natural ordering, use `Comparator.reverseOrder()`. Do not try to fix an already broken comparator by merely negating its result.

Boundary values provide counterexamples sufficient to refute a broken comparator. Conversely, passing a finite set of sample tests does not prove an arbitrary comparator is right for all inputs; the implementation still needs to be built from comparisons with proper contracts.

## 9. Keep the comparison rule stable for as long as keys remain stored

### 9.1. Do not mutate fields used in comparison while a key is in the tree

Suppose a key object is placed in the tree based on a priority score of 1. If that score is mutated to 100 through another reference, `TreeMap` has no way of knowing to remove the key and re-insert it at its new position. The existing structure was already organized according to previous comparison results.

Consequences can include iteration order no longer matching the visible data, or lookups with an equivalent key failing to reach the expected node. Do not rely on one specific failure mode, because it depends on the tree structure and sequence of operations; the root problem is breaking the stability of the comparison key.

The straightforward design is to use immutable keys, such as a record containing only immutable components like `int` and `String` in the examples. If you genuinely need to change information used as the key, remove the mapping using the unmodified key, and then re-insert with the new key in a well-defined sequence. Mutating the key first and then trying to use it to `remove` does not guarantee the old mapping can still be found.

Records do not automatically make every contained object deeply immutable. A record holding a mutable list can still suffer from this issue if the comparator reads the contents of that list. Check all data that the comparison actually depends on.

### 9.2. A comparator must not change its mind mid-way either

A comparator can break stability even when the keys themselves do not change. For example, it might read an external flag to sort ascending at one moment and descending at another; or it might depend on random numbers, the current time, or a mutable lookup table.

When comparison results change after the tree has been built, the map does not automatically re-sort all entries. If you want a new ordering policy, construct a new structure with the chosen stable rule and transfer the data deliberately; do not just flip a variable read by the old comparator.

In particular, sorting keys by values fetched from another map using a comparator that depends on mutable state mixes lookup with an unstable order. If the requirement is to view results by value at a point in time, it is usually better to build separate data or a dedicated index for that purpose rather than silently making `TreeMap`'s key identity depend on updating values.

### 9.3. Value V is not the comparison key

In a normal `TreeMap<K, V>`, updating the value for a key does not make the map switch to sorting by the new value. The comparator receives keys of type `K`, not two entries to inspect `V` arbitrarily.

A value can be identical to another entry's value and both mappings will still coexist, provided their keys are not equivalent under the comparator. Conversely, using two very different values does not turn a pair of keys that compare as 0 into two separate storage slots.

## 10. Valid key domains, null, and type errors

### 10.1. All keys must be mutually comparable

In a map using natural ordering, the fact that two classes both implement `Comparable` is not enough to guarantee objects of those two classes can be compared with each other. For instance, `Integer` and `Long` do not automatically share a common natural ordering just because both are numbers.

Do not drop generics or declare an overly broad type and then insert multiple kinds of keys without a shared comparison rule. The map can throw `ClassCastException` when it needs to compare incompatible keys. The fact that `get` or `containsKey` takes an `Object` parameter also does not mean every object passed in can be compared against existing keys.

If an external comparator is used, it must validly handle every pair of keys in the domain permitted by the API. There is no requirement that all keys must be of a single concrete class if the comparator truly defines a valid common order, but that must be designed explicitly; arbitrary casting does not produce a valid ordering.

### 10.2. Two places where null can appear in configuration have different meanings

`new TreeMap<>(comparator)` with a `null` comparator argument means using natural ordering. However, `Comparator.nullsFirst(null)` has a different meaning: it treats all non-`null` keys as equal, with `null` placed before them.

Therefore, passing `null` to `nullsFirst` is not how you ask it to automatically use `compareTo` for the remaining keys. If you want an order that uses natural ordering and accepts `null` keys, the illustrative configuration inside a method is:

```java
Comparator<String> order = Comparator.nullsFirst(Comparator.naturalOrder());
TreeMap<String, Integer> map = new TreeMap<>(order);
```

This point directly affects duplicate keys: a comparator that treats every non-`null` key as equivalent will have only one non-`null` key group for storing mappings, even if the user inserts many different strings.

### 10.3. State the policy explicitly instead of relying on accidental exceptions

If an API does not accept `null` keys, document and validate that rule at the appropriate boundary. If it accepts them, choose a comparator with clear handling for both `null` and non-`null` keys. Do not write a comparator that only handles a few pairs and expect the map to fill in the rest.

When `map.comparator()` is non-`null`, that comparator might still just delegate to natural ordering—for example, a map created with `Comparator.naturalOrder()`. So the getter tells you how the configuration is stored, not that natural ordering and an external comparator always produce two different orderings.

## 11. Testing comparators and duplicate-key behavior

### 11.1. Test the relation, not just one sorted list

Iterating over a few keys that appear to be in the right order does not prove a comparator is good. You should test data groups that expose the policy:

- Two objects with different references but the same key value: must be recognized according to business intent.
- Two keys matching on the primary criterion but differing on the secondary criterion: must remain separate if required.
- Two keys that differ according to `equals` while the comparator returns 0: confirm whether this is intentional, and understand the `Map` contract limitations if you keep that design.
- Boundary numbers such as `Integer.MIN_VALUE`, `0`, and `Integer.MAX_VALUE` to catch sign and overflow bugs.
- Representation variants such as `BigDecimal` with different scales or strings with different casing if the data domain permits them.
- `null` keys if supported by the API, along with `null` values so `get` results are not misinterpreted.

At the contract level, you can test sample pairs and triples: swapping arguments must flip the sign; two consecutive "before" relations must imply transitive "before"; keys returning 0 must have the same relative sign against third keys. Then check alignment with `equals` if the map must obey the general `Map` contract.

The [Comparator — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html) and [Comparable — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Comparable.html) documentation are the reference sources for these conditions. Do not substitute observing a single sort run without errors for understanding the contract.

### 11.2. Test map operations using the same key pair

For a pair `a, b` that should be treated as duplicates, verify:

1. Inserting `a` then inserting `b` does not increase the mapping count on the second call.
2. Inserting `b` returns the old value, and the new value can be retrieved using both keys.
3. `containsKey` with a new object in the same equivalence group recognizes the mapping.
4. Removing with an equivalent key deletes that exact mapping.

For a pair that should stay separate, check the opposite: both mappings coexist, looking up each key returns its own value, and removing one key does not remove the other. Checking `size()` alone is not enough if the comparator or lookup logic still behaves unexpectedly.

`put` returning `null` can mean either a new insertion or replacing an old value that was `null`. If a test needs to distinguish these cases, observe presence or size in a well-defined context instead of treating a `null` return value as sole proof.

### 11.3. Comparison cost is also part of lookup cost

`TreeMap` has logarithmic cost in the number of mappings for basic operations such as `get`, `put`, `containsKey`, and `remove`. However, each step must still execute the comparison. A comparator that processes long strings, performs heavy computation, or loads external data will increase actual cost.

Keep comparators short, stable, and side-effect-free to support both correctness and predictable performance. Do not mutate the map itself while the comparator is being called to locate a position; the comparison should answer the relationship between two keys rather than performing other update work.

## 12. Common mistakes

| Misconception | Consequence | How to handle it |
|---|---|---|
| Comparator is only for display ordering | Unexpected mapping updates | Consider the meaning of `compare == 0` as well |
| `equals=false` means TreeMap always keeps two entries | Wrong when comparison returns 0 | Check the active ordering rule |
| With an external comparator, the map still calls equals to break ties | Two keys still merge unexpectedly | Put distinguishing criteria in the comparator or change the key model |
| Comparing only score/length/priority | Different objects with the same criterion are merged | Add the necessary identifying criteria |
| Adding a random number to avoid returning 0 | Unstable order, unable to look up keys reliably | Use stable key components |
| Comparing numbers by subtraction | Can flip signs and break transitivity on overflow | Use `compare` or numeric `comparing` methods |
| Checking exact results `-1` or `1` | Fails with comparators returning other magnitudes | Check `< 0`, `== 0`, `> 0` |
| Reversing the comparator will separate duplicate keys | A result of 0 remains 0 | Fix the criteria instead of just flipping direction |
| `BigDecimal` values with the same numeric value are always equals | Overlooks scale | Explicitly choose value-based or representation-based keys |
| Mutating key fields while stored in the map | Tree position and key data no longer match | Use immutable keys; replace keys via a deliberate process |
| Flipping an external flag makes TreeMap re-sort itself | Comparator changes while the tree is not rebuilt | Use a stable rule per structure |
| `comparator()==null` means no ordering | Misunderstands natural ordering | Read the getter's meaning accurately |

## 13. Self-check

### Questions

1. Must two keys with different object references create two mappings in `TreeMap`?
2. With a length-only comparator, inserting `cat → 1` then `dog → 2` creates how many mappings?
3. Does `TreeMap` automatically call `equals` to separate `cat` and `dog` after the comparator returns 0?
4. Why is `compare(a, b) == 1` not a general check for every comparator?
5. Must a supplied comparator automatically call `compareTo` when it returns 0?
6. When does `thenComparing` use the secondary criterion?
7. Does `reversed()` change which keys compare as 0?
8. Are `new BigDecimal("2.0")` and `new BigDecimal("2.00")` equal under both `equals` and `compareTo`?
9. Is a comparator that satisfies transitivity guaranteed to be consistent with `equals`?
10. Why does fixing `hashCode` not solve `TreeMap` merging two keys?

### Answers

1. No. Equivalence under the ordering decides; two new objects representing the same key can still update the same mapping.
2. One mapping with the new value `2`, because both lengths are three.
3. No. To keep them separate by content, you must add a criterion or choose an appropriate model.
4. The API only specifies a positive integer, not strictly `1`. Use `> 0`.
5. No. The supplied comparator is the active rule; any additional criterion must be stated explicitly.
6. When the preceding criteria treat the two keys as equivalent—that is, return 0.
7. No; reversing order only flips before/after relationships and does not split equivalence groups.
8. `compareTo` returns 0, but `equals` returns `false` because their scales differ.
9. Not necessarily. A length-based comparator can be a valid ordering yet merge strings that are not `equals`.
10. `TreeMap` does not use hash codes to detect duplicate keys; inspect the comparison and where it returns 0.

## 14. Practice with reference results

### Exercise 1: from one criterion to two criteria

Create a `TreeMap<String, Integer>` using `Comparator.comparingInt(String::length)`. Insert `cat → 1`, `dog → 2`, `ox → 3`. Predict the number of mappings, the lookup value for `"pig"`, and the order of length groups before running.

Reference result: there are two mappings, corresponding to lengths two and three. `get("pig")` finds the length-three group and returns `2` even though `"pig"` was never inserted. This is a direct consequence of keys being equivalent by length.

Repeat from an empty map using a length comparator chained with natural string ordering. Now `cat` and `dog` stay separate, the size is three, the key order is `[ox, cat, dog]`, and `get("pig")` returns `null` because no `"pig"` key exists. The two runs must use two fresh maps so both start cleanly.

### Exercise 2: checking a composite key

Use the `Ticket` record from Program 3. Insert `1:A`, `1:B`, and then a new object that is also `1:A`, with three different values. With the full comparator, predict the final size and which mapping gets updated.

Reference result: there are two mappings; the last call updates only `1:A`. If the map ends up with one mapping, the comparator is ignoring `code`. If there are three mappings, the key relation no longer matches the pair of components being represented.

### Exercise 3: choosing an explicit BigDecimal policy

Use the two maps in Program 4 and look up `2.000`. Explain why the first map returns an existing value while the second map returns `null`. Then decide for a sample application domain whether scale should be distinguished.

The completion criterion is not always making both maps have the same `size()`. You need to be able to explain what constitutes the same key, and ensure all insert/lookup/remove paths follow that decision consistently.

### Exercise 4: finding counterexamples instead of using only small numbers

With the subtraction comparator, test pairs like 1 and 2 first, then the boundary values from Program 5. State clearly which properties are violated. Then replace it with `Integer.compare` and re-verify the sign and transitivity checks.

You do not need to build a `TreeMap` with the broken comparator to do this exercise. The bug is already present in the comparison relation; fixing that relation is a prerequisite before using it as the foundation of a search structure.

## 15. Runtime environment and references

The five programs in this lesson are self-contained and use syntax and APIs compatible with Java 17. They were compiled with `javac --release 17 -encoding UTF-8` and run on JDK 24.0.2; stdout was verified from those runs. Each `public` class is saved in a matching filename, with no external libraries required.

- [TreeMap — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html): sources of ordering, meaning of keys comparing equal, and the consistency-with-equals requirement.
- [Comparable — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Comparable.html): natural ordering and the `compareTo` contract.
- [Comparator — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html): comparison contract, chaining criteria, reversing order, and `null` handling.
- [BigDecimal — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): numeric value comparison, `equals` by value and scale, and stripping trailing zeros.
